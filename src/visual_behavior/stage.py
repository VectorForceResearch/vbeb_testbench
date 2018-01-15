import os.path
import platform
import threading
import logging
from Phidget22.Devices.Stepper import *
from Phidget22.Net import *
from abc import abstractmethod
from .exceptions import *
import asyncio
from queue import Queue
import time

class Stage(object):
    def __init__(self):
        pass

    @property
    @abstractmethod
    def serial(self):
        """

        :return:
        """

    @serial.setter
    @abstractmethod
    def serial(self, value):
        """

        :param value:
        :return:
        """

    @abstractmethod
    def move_to(self, coordinates):
        """

        :param coordinates:
        :return:
        """

    @abstractmethod
    def position(self):
        """

        :return:
        """

    @abstractmethod
    def append_move(self, coordinates):
        """

        :param coordinates:
        :return:
        """

    @property
    @abstractmethod
    def initialized(self):
        """

        :return:
        """

    @abstractmethod
    def process_queue(self):
        """

        :return:
        """


class MockStage(Stage):
    def __init__(self, serial=12345):
        super().__init__()
        logging.info(f'Initializing {self.__name__}')
        self._serial = serial
        self._queue = Queue()
        self._position = [0, 0, 0]
        self._axes = [None, None, None]

    @property
    def initialized(self):
        return True

    def append_move(self, coordinates):
        if not self._validate_coordinates(coordinates):
            return
        self._queue.put(coordinates)

    def move_to(self, coordinates):
        if not self._validate_coordinates(coordinates):
            return
        self._position = list(coordinates)

    @property
    def position(self):
        if not self._queue.empty():
            self._position = self._queue.get()
        return tuple(self._position())

    @property
    def serial(self):
        return self._serial

    @staticmethod
    def _validate_coordinates(coordinates):
        if not isinstance(coordinates, (list, tuple)) or len(coordinates) != 3:
            logging.error(f'Expected coordinates to be list-like of length 3')
            return False

        return True




class PhidgetStage(Stage):
    def __init__(self, serial=0, x_channel=0, y_channel=1, z_channel=3):
        """

        :param serial:
        :param x_channel:
        :param y_channel:
        :param z_channel:
        """
        super().__init__()

        # Load drivers dependent on system architecture
        __arch = platform.architecture()
        if __arch[0] == '64bit':
            __drivers = os.path.abspath('drivers/x64')
        else:
            __drivers = os.path.abspath('drivers/x86')
        os.environ['PATH'] = __drivers + ";" + os.environ['PATH']

        self._connected = False
        self._serial = serial
        self._channels = [x_channel, y_channel, z_channel]
        self._axes = [Stepper(), Stepper(), Stepper()]
        self._initialized = [False] * 3
        self._position_changed_callback = None
        self._queue_active = False
        self._queue = Queue()


    @property
    def serial(self):
        """
        Serial number associated with phidget board
        :return: serial number defined in __init__( ... )
        """
        return self._serial

    @serial.setter
    def serial(self, value):
        """
        Serial number associated with phidget board
        :return: serial number defined in __init__( ... )
        """
        self._serial=value

    @property
    def min_velocity(self, axis=None):
        """
        Minimum velocity limit for an axis or all axis.
        :param axis: default None.  If axis is specified ('x', 'y', 'z') then the minimum velocity for that axis is
        returned.  If axis is None, a list of minimum velocities is provided.
        :return:
        """
        velocity = []
        if not axis:
            for axis in self._axes:
                velocity.append(axis.getMinVelocityLimit())
        else:
            velocity = self._axes[axis].getMinVelocityLimit()
        return velocity

    @property
    def max_velocity(self):
        velocity = []
        for axis in self._axes:
            velocity.append(axis.getVelocityLimit())
        return velocity

    @property
    def velocity(self):
        velocity = []
        for axis in self._axes:
            velocity.append(axis.getVelocity())
        return velocity

    @property
    def acceleration(self):
        acceleration = []
        for axis in self._axes:
            acceleration.append(axis.getAcceleration())
        return acceleration

    @property
    def max_acceleration(self):
        acceleration = []
        for axis in self._axes:
            acceleration.append(axis.getMaxAcceleration())
        return acceleration

    @property
    def min_acceleration(self):
        acceleration = []
        for axis in self._axes:
            acceleration.append(axis.getMinAcceleration())
        return acceleration

    @property
    def position(self):
        """

        :return:
        """
        coords = []
        for axis in self._axes:
            coords.append(axis.getPosition())
        return coords

    @property
    def position_changed_callback(self):
        return self._position_changed_callback

    @property
    def initialized(self):
        return True

    @position_changed_callback.setter
    def position_changed_callback(self, callback):
        for axis in self._axes:
            axis.setOnPositionChangeHandler(callback)

    def initialize_axis(self, axis):
        """

        :param axis:
        :return:
        """
        print(f'initializing axis {axis}')
        index = axis
        axis = self._axes[index]
        #axis.setDeviceSerialNumber(self._serial)
        axis.setChannel(self._channels[index])
        axis.setOnAttachHandler(self._phidget_stepper_attached)
        axis.setOnDetachHandler(self._phidget_stepper_detached)
        axis.setOnErrorHandler(self._phidget_error_event)
        axis_label = chr(ord('x') + index)
        try:
            axis.openWaitForAttachment(1000)
            logging.info(f'Axis "{axis_label}" connected')
        except PhidgetException as e:
            self._phidget_error_event(e)
            raise InitializationError


        axis.setVelocityLimit(200.0)
        axis.setAcceleration(2500.0)

    def _initialize_motion_queue(self):
        """

        :return:
        """
        self._queue_active = True
        self._queue_thread = threading.Thread(target=self._motion_queue)
        self._queue_thread.start()

    def zero_axes(self):
        """

        :return:
        """
        try:
            for a in self._axes:
                a.setEngaged(0)
                a.addPositionOffset(-a.getPosition())
        except PhidgetException as e:
            self._phidget_error_event(e)
            raise StageNotConnectedError

    def move_to(self, coordinates):
        """

        :param coordinates:
        :return:
        """
        if not isinstance(coordinates, (list, tuple)) or len(coordinates) != len(self._axes):
            logging.error(f'Expected coordinates to be list-like of length {len(self._axes)}')
            raise InvalidCoordinatesError
       # ax = [self._axes[0], self._axes[2]]
        try:
            for index, axis in enumerate(self._axes):
                print(f'Axis {index}')
                axis.setEngaged(True)
                print(f'Engaged')
                axis.setTargetPosition(coordinates[index])

        except PhidgetException as e:
            print('dafuq')
            logging.error(e)

    def append_move(self, coordinates):
        """

        :param coordinates:
        :return:
        """
        if not isinstance(coordinates, (list, tuple)) or len(coordinates) != len(self._axes):
            logging.error(f'Expected coordinates to be list-like of length {len(self._axes)}')
            raise InvalidCoordinatesError
        try:
            self._queue.put(coordinates)
        except Exception:
            raise StageNotConnectedError

    @property
    def axes_engaged(self):
        return [axis.getEngaged() for axis in self._axes]

    def cycle_axes(self, cycles, delta):
        """

        :param cycles:
        :param delta:
        :return:
        """
        try:
            self.zero_axes()
            for i in range(cycles):
                self.append_move((delta, delta, delta))
                self.append_move((0, 0, 0))
        except Exception:
            raise StageNotConnectedError

    def stop_motion(self):
        """

        :return:
        """
        try:
            while not self._queue.empty():
                self._queue.get()
                self._queue.task_done()

            for a in self._axes:
                a.setEngaged(False)
        except asyncio.QueueEmpty:
            pass
        except Exception:
            raise StageNotConnectedError

    def close(self):
        """

        :return:
        """
        self._queue_active = False
        for axis in self._axes:
            try:
                if axis.getEngaged():
                    axis.setEngaged(False)
                axis.close()
            except PhidgetException as err:
                print(err.details)

    @property
    def is_moving(self):
        try:
            return [axis.getIsMoving() for axis in self._axes]
        except PhidgetException:
            return [False] * 3

    @property
    def is_engaged(self):
        try:
            return [axis.getEngaged() for axis in self._axes]
        except PhidgetException:
            return [False] * 3

    def _motion_queue(self):
        """

        :return:
        """
        while self._queue_active:
            for a in self._axes:
                if not a.getIsMoving():
                    a.setEngaged(False)

            position = self._queue.get()
            for idx, axis in enumerate(self._axes):
                axis.setEngaged(True)
                axis.setTargetPosition(position[idx])

    @staticmethod
    def _phidget_stepper_attached(e):
        try:
            print("\tMotor %d on board %d online." % (e.getChannel(), e.getDeviceSerialNumber()))
        except PhidgetException:
            raise

    @staticmethod
    def _phidget_stepper_detached(e):
        detached = e
        try:
            print("\tBoard %d offline." % detached.getDeviceSerialNumber())
            raise Exception("NOMO")
        except Exception:
            raise Exception("NOMO")

    @staticmethod
    def _phidget_error_event(e):
        code = e.code
        details = e.details
        print("Phidget Error %i : %s" % (code, details))

    def process_queue(self):
        """

        :return:
        """
        while self._queue_active:
            for axis in self._axes:
                if not axis.getIsMoving():
                    axis.setEngaged(False)

            if not any(self.is_moving) and not self._queue.empty():
                try:
                    pos = self._queue.get_nowait()
                    self.move_to(pos)
                except asyncio.QueueEmpty:
                    pass

            time.sleep(.1)

    def start_queue(self, loop=None, executor=None):
        if loop is None:
            loop = asyncio.get_event_loop()
        self._queue_active = True
        return loop.run_in_executor(executor, self.process_queue)

    def stop_queue(self):
        self._queue_active = False
