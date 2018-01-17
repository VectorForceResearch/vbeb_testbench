from aibsmw import ZROHost, RemoteObjectService
from visual_behavior import stage, nidaqio, source_project_configuration, init_log
import logging
import argparse
import asyncio
import numpy as np
import threading
import time

class RemoteStageController(object):
    def __init__(self):
        self.config = source_project_configuration('visual_behavior_v1.yml', override_local=False)
        self._stage = self.setup_stage()
        self._daq = self.setup_daq()

        self.async_loop = asyncio.get_event_loop()

        # related to monitoring the  daq signals for limit switches
        self._monitor_limits = False
        self._limit_tripped = [ False ] * 3
        self._limits = {0: self._daq.x_limit,
                        1: self._daq.y_limit,
                        2: self._daq.z_limit}
        self._limit_direction = self._limit_direction = [-1, -1, 1]
        self._homing_mode = False
        self._current_homing_axis = 0

        """
        This corresponds to the signaling the air solenoids that release the motor brake after the limit switch has been
        hit.  The number of samples is somewhat arbitrary - it isn't clear how many have to be sent to make the nidaq /
        arduino interface sensitive to the change.
        
        It's also possible there is a kind of race condition since the signals aren't simultaneous.  It looks like a 
        very minimal risk thus far.
                 ao0 ao1
        default:  0   0
         x-axis (0):  0   1
         y-axis (1):  1   0
         z-axis (2):  1   1
        """
        self.clamp_table = {2: [np.zeros(1000), np.ones(1000) * 5],
                            1: [np.ones(1000) * 5, np.zeros(1000)],
                            0: [np.ones(1000) * 5, np.ones(1000) * 5],
                            'reset': [np.zeros(1000), np.zeros(1000)]}

        self.limit_lock = threading.Lock()
    @property
    def phidget_stage(self):
        return self._stage

    @property
    def is_engaged(self):
        return self._stage.is_engaged

    @property
    def is_moving(self):
        return self._stage.is_moving

    @property
    def stage_serial(self):
        return self._stage.serial

    @property
    def position(self):
        return self._stage.position

    def append_move(self, coordinates):
        self._stage.append_move(coordinates)


    @property
    def limits(self):
        return self._limit_tripped

    @property
    def daq(self):
        return self._daq

    def stop_motion(self):
        self._stage.stop_motion()

    def extend_lickspout(self):
        logging.info('extending lickspout')
        self._daq.air_sol_1.write(np.ones(10, dtype=np.uint8))
        self._daq.air_sol_2.write(np.zeros(10, dtype=np.uint8))


    def retract_lickspout(self):
        logging.info('retracting lickspout')
        self._daq.air_sol_1.write(np.zeros(10, dtype=np.uint8))
        self._daq.air_sol_2.write(np.ones(10, dtype=np.uint8))


    def setup_stage(self):
        stage_ = stage.PhidgetStage(x_channel=self.config.phidget.channels.x,
                                    y_channel=self.config.phidget.channels.y,
                                    z_channel=self.config.phidget.channels.z)
        stage_.initialize_axis(self.config.phidget.channels.x)
        stage_.initialize_axis(self.config.phidget.channels.y)
        stage_.initialize_axis(self.config.phidget.channels.z)
        stage_.serial = stage_._axes[0].getDeviceSerialNumber()
        logging.info(f'connected to stage {stage_.serial}')
        return stage_

    def setup_daq(self):
        daq = nidaqio.NIDAQio()
        daq.create_digital_out_task('air_sol_1', self.config.nidaq.air_solenoid_1)
        daq.create_digital_out_task('air_sol_2', self.config.nidaq.air_solenoid_2)
        daq.create_digital_in_task('x_limit', self.config.nidaq.limit_switch_x)
        daq.create_digital_in_task('y_limit', self.config.nidaq.limit_switch_y)
        daq.create_digital_in_task('z_limit', self.config.nidaq.limit_switch_z)
        daq.create_analog_out_voltage_task('clamp_0', self.config.nidaq.clamp_0)
        daq.create_analog_out_voltage_task('clamp_1', self.config.nidaq.clamp_1)

        logging.info(f'connected to nidaq device {daq.device_name}')
        return daq

    def start_hardware(self, executor=None):
        """
        Async stuff
        :return:
        """

        self.monitor_thread = threading.Thread(target=self.monitor_limits)
        self.stage_thread = threading.Thread(target=self._stage.process_queue)

        self._monitor_limits = True
        self.monitor_thread.start()
        self._stage._queue_active = True
        self.stage_thread.start()


    def monitor_limits(self):
        """

        :return:
        """

        while self._monitor_limits:
            for axis, task in self._limits.items():
                if not task.read() and not self._limit_tripped[axis]:
                    logging.info(f'axis {axis} is at the limit switch')
                    self._stage._axes[axis].setEngaged(False)
                    self._limit_tripped[axis] = True
                    t = threading.Thread(target = self.move_off_limit, args = (axis, 5))
                    t.start()

            time.sleep(.1)

    def move_off_limit(self, axis, step_size):
        self.limit_lock.acquire()
        logging.info(f'attempting to move axis {axis} off limit switch')
        self._daq.clamp_0.write(self.clamp_table[axis][0])
        self._daq.clamp_1.write(self.clamp_table[axis][1])
        self._stage._axes[axis].setEngaged(0)
        while not self._limits[axis].read():
            if self._stage._axes[axis].getIsMoving():
                time.sleep(.1)
            position = self._stage.position
            position[axis] += (step_size * self._limit_direction[axis] * -1)
            self._stage.move_to(position)

        self._daq.clamp_0.write(self.clamp_table['reset'][0])
        self._daq.clamp_1.write(self.clamp_table['reset'][1])
        self._limit_tripped[axis] = False
        self.limit_lock.release()
        if self._homing_mode:
            axis += 1
            if axis > 2:
                self._homing_mode = False
                self.zero_stage()
                logging.info('staged homed')
            else:
                self.drive_axis_home(axis)

    def drive_axis_home(self, axis):
        logging.info(f'driving axis {axis} to home')
        position = self._stage.position
        position[axis] += (10000 * self._limit_direction[axis])
        self._stage.append_move(position)

    def zero_stage(self):
        logging.info('stage axis zeroed')
        self._stage.zero_axes()

    def home_stage(self):
        logging.info('homing stage')
        self._homing_mode = True
        self._current_homing_axis = 0
        self._stage.stop_motion()
        self.drive_axis_home(self._current_homing_axis)

    def move_to(self, coords):
        self._stage.move_to(coords)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', help='port to run the remote service on', type=int)
    args = parser.parse_args()

    init_log(override_local=False)
    config = source_project_configuration('visual_behavior_v1.yml', override_local=False)

    port = args.port or config.phidget.port
    remote = RemoteStageController()
    host = ZROHost(remote)
    host.add_service(RemoteObjectService, service_host=('*', port))
    remote.start_hardware()
    host.start()

if __name__ == '__main__':
    main()
