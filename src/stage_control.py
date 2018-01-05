#!/usr/bin/env python
# -*- coding: utf-8 -*-


import socket

import yaml
from qtmodern import styles, windows
from qtpy import uic, QtCore

from qtpy.QtGui import QPixmap, QIcon
from qtpy.QtWidgets import *
from qtpy.QtCore import QTimer
import PyDAQmx
import sys
import visual_behavior
from visual_behavior import PhidgetStage
from visual_behavior import InitializationError

from Phidget22.Net import PhidgetException
import datetime
import logging
from functools import partial
import redis
from PyDAQmx import *
import numpy as np
from ctypes import byref
from itertools import product
import time


class AxisControl(object):
    leds = None

    def __init__(self, index, lcd_velocity=None, dial_velocity=None, lcd_accel=None, dial_accel=None, btn_plus=None,
                 btn_minus=None, led=None):
        self.index = index
        self.lcd_velocity = lcd_velocity
        self.dial_velocity = dial_velocity
        self.lcd_accel = lcd_accel
        self.dial_accel = dial_accel
        self.btn_plus = btn_plus
        self.btn_minus = btn_minus
        self.led = led

        if not self.leds:
            self.leds = dict(clear=QPixmap(visual_behavior.__path__[0] + '/resources/led_clear.png').scaledToHeight(20),
                             blue=QPixmap(visual_behavior.__path__[0] + '/resources/led_blue.png').scaledToHeight(20),
                             red=QPixmap(visual_behavior.__path__[0] + '/resources/led_red.png').scaledToHeight(20),
                             green=QPixmap(visual_behavior.__path__[0] + '/resources/led_green.png').scaledToHeight(20))
        self.led_color = 'clear'

    @property
    def led_color(self):
        return self.led.getPixmap()

    @led_color.setter
    def led_color(self, color):
        if color in self.leds:
            self.led.setPixmap(self.leds[color])


class StageUI(QMainWindow):
    col_connected = 0
    col_port = 1
    col_position = 2
    col_moving = 3
    col_engaged = 4

    def __init__(self):
        """
        Stage Controller PyQt UI Object
        """
        super(QMainWindow, self).__init__()
        self.module_path = visual_behavior.__path__
        self.config = visual_behavior.source_project_configuration('visual_behavior_v1.yml')

        self.stage = None
        self.ui = uic.loadUi(self.module_path[0] + '/resources/stage_controller.ui')
        self.setCentralWidget(self.ui)
        self.icon_clear = QIcon(self.module_path[0] + '/resources/led_clear.png')
        self.icon_red = QIcon(self.module_path[0] + '/resources/led_red.png')
        self.icon_blue = QIcon(self.module_path[0] + '/resources/led_blue.png')
        self.icon_green = QIcon(self.module_path[0] + '/resources/led_green.png')
        self.setup_ui()

        self.setup_signals()
        self.db = redis.StrictRedis(host=self.config.redis.host, db=self.config.redis.db, port=self.config.redis.port)
        db_string = f'{self.config.redis.host}:{self.config.redis.port} ({self.config.redis.db})'
        try:
            self.db.info()
            self.log(f'Connected to database: {db_string}')
        except ConnectionRefusedError as err:
            self.log(f'Failed to connected to database: {db_string}: {err}')

        self.control_widgets = [self.ui.btn_x_minus, self.ui.btn_x_plus, self.ui.btn_y_minus,
                                self.ui.btn_y_plus, self.ui.btn_z_minus, self.ui.btn_z_plus,
                                self.ui.btn_register_safe, self.ui.btn_register_home, self.ui.btn_goto_safe,
                                self.ui.btn_goto_home, self.ui.sb_xy_stepsize, self.ui.sb_z_stepsize,
                                self.ui.btn_goto_custom, self.ui.btn_goto_origin, self.ui.btn_register_origin,
                                self.ui.btn_register_custom, self.ui.le_custom, self.ui.list_custom, self.ui.btn_zero]
        self.axes = ['x', 'y', 'z']

        self.x_controls = AxisControl(0,
                                      btn_plus=self.ui.btn_x_plus,
                                      btn_minus=self.ui.btn_x_minus,
                                      led=self.ui.lbl_x_channel)
        self.y_controls = AxisControl(1,
                                      btn_plus=self.ui.btn_y_plus,
                                      btn_minus=self.ui.btn_y_minus,
                                      led=self.ui.lbl_y_channel)
        self.z_controls = AxisControl(2,
                                      btn_plus=self.ui.btn_z_plus,
                                      btn_minus=self.ui.btn_z_minus,
                                      led=self.ui.lbl_z_channel)

        self.axes_widgets = dict(x=self.x_controls, y=self.y_controls, z=self.z_controls)

        self.axis_timer = QTimer()
        # noinspection PyUnresolvedReferences
        self.axis_timer.timeout.connect(self.update_table)

        self.limit_timer = QTimer()
        # noinspection PyUnresolvedReferences
        self.limit_timer.timeout.connect(self.limit_timeout)


        """
        Corresponds to the inputs to receive from NIDAQ to check if a limit switch has been tripped.
        The intent is to call a stop on the moving axis.
        """
        self.nidaq_dis = {}
        for axis, line_name in self.config.lines._asdict().items():
            task = Task()
            channel = f'/{self.config.device_name}/port{self.config.port}/line{line_name}'.encode()
            task.CreateDIChan(channel, b'', PyDAQmx.DAQmx_Val_ChanPerLine)
            self.nidaq_dis[axis] = task

        self.axis_last_move = {'x': 0,
                               'y': 0,
                               'z': 0}
        self.axis_disabled = {'x': 0,
                              'y': 0,
                              'z': 0}

        self.air_sol0
        self.air_sol1

        """
        This corresponds to the signaling for ao0 and ao1 that releases the motor brake after the limit switch has been
        hit.  The number of samples is somewhat arbitrary - it isn't clear how many have to be sent to make the nidaq /
        arduino interface sensitive to the change.
        
        It's also possible there is a kind of race condition since the signals aren't simultaneous.  It looks like a 
        very minimal risk thus far.
                 ao0 ao1
        default:  0   0
         x-axis:  0   1
         y-axis:  1   0
         z-axis:  1   1
        """
        self.task_a0 = Task()
        self.task_a0.CreateAOVoltageChan(f'/{self.config.device_name}/{self.config.analog_0}'.encode(), b'',
                                         -10.0, 10.0, PyDAQmx.DAQmx_Val_Volts, None)
        self.task_a1 = Task()
        self.task_a1.CreateAOVoltageChan(f'/{self.config.device_name}/{self.config.analog_1}'.encode(), b'',
                                         -10.0, 10.0, PyDAQmx.DAQmx_Val_Volts, None)

        self.analog_table = {'x': [np.zeros(100), np.ones(100) * 5],
                             'y': [np.ones(100) * 5, np.zeros(100)],
                             'z': [np.ones(100) * 5, np.ones(100) * 5],
                             'reset': [np.zeros(100), np.zeros(100)]}
        self.current_drive_axis = -1
        self.data_values = [0, 0, 0]

    def drive_to_home(self):

        dialog = QMessageBox()
        dialog.setWindowTitle('Stage Controller Notification')
        dialog.setText('Click continue to drive the stage to the home position.')
        dialog.setInformativeText('It is normal to hear clicks during this process.\n\You can click "Stop" to abort '
                                  'this operation and manually drive the stage.')
        dialog.exec_()
        QTimer.singleShot(100, self.drive_timeout)

    def drive_timeout(self):
        if -1 < self.current_drive_axis < len(self.axes) and self.stage.is_moving[self.current_drive_axis]:
            QTimer.singleShot(1000, self.drive_timeout)
            return

        self.current_drive_axis += 1

        if self.current_drive_axis > len(self.axes) - 1:
            self.signal_zero_stage()
            self.register_coordinates('HOME', self.ui.lbl_coords_home)
            self.log('Stage registered at HOME')
            return

        self.axis_last_move[self.axes[self.current_drive_axis]] = 1

        self.log(f'Attempting to drive the {self.axes[self.current_drive_axis]} axis to the home position.')
        position = self.stage.position
        if self.current_drive_axis < 2:
            position[self.current_drive_axis] -= 10000
        else:
            position[self.current_drive_axis] += 10000
        self.stage.move_to(position)
        QTimer.singleShot(1000, self.drive_timeout)

    def limit_timeout(self):
        """

        :return:
        """
        # axis need better abstraction
        # temporary hack       axis plus = 1       axis minus = -1

        buttons = {'x': [None, self.ui.btn_x_plus, self.ui.btn_x_minus],
                   'y': [None, self.ui.btn_y_plus, self.ui.btn_y_minus],
                   'z': [None, self.ui.btn_z_plus, self.ui.btn_z_minus]}

        axmap = {'x': 0,
                 'y': 1,
                 'z': 2}

        read = int32()

        data = np.zeros(1000, dtype=np.uint32)
        for axis, task in self.nidaq_dis.items():
            task.ReadDigitalU32(-1, .1, PyDAQmx.DAQmx_Val_GroupByChannel, data, 1000, byref(read), None)
            if data[0] == 0 and self.axis_last_move[axis]:  # limit switch was tripped
                if self.axis_disabled[axis] == 0:
                    self.axis_disabled[axis] = self.axis_last_move[axis]
                    self.stage._axes[axmap[axis]].setEngaged(False)
                    buttons[axis][self.axis_last_move[axis]].setEnabled(False)
                    self.axis_last_move[axis] = 0
                elif self.axis_last_move[axis] == self.axis_disabled[axis]:
                    self.stage._axes[axmap[axis]].setEngaged(False)
                    buttons[axis][self.axis_last_move[axis]].setEnabled(False)
                    self.axis_last_move[axis] = 0

            elif data[0] >= 1:
                buttons[axis][1].setEnabled(True)
                buttons[axis][2].setEnabled(True)
            self.data_values[axmap[axis]] = data[0]
            self.display_position()

    def update_table(self):
        """

        :return:
        """
        moving = self.stage.is_moving
        # hacky, will fix when limit switches come through
        for axis, m in enumerate(moving):
            if not m:
                try:
                    self.stage._axes[axis].setEngaged(False)
                except PhidgetException:
                    pass

        engaged = self.stage.is_engaged
        for i in range(3):
            if moving[i]:
                self.ui.tbl_stage.cellWidget(i, self.col_moving).setIcon(self.icon_blue)
            else:
                self.ui.tbl_stage.cellWidget(i, self.col_moving).setIcon(self.icon_clear)
            if engaged[i]:
                self.ui.tbl_stage.cellWidget(i, self.col_engaged).setIcon(self.icon_blue)
            else:
                self.ui.tbl_stage.cellWidget(i, self.col_engaged).setIcon(self.icon_clear)

    def setup_ui(self):
        for c, r in product([self.col_port, self.col_position], range(3)):
            item = QTableWidgetItem()
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.ui.tbl_stage.setItem(r, c, item)

        for c, r in product([self.col_connected, self.col_moving, self.col_engaged], range(3)):
            button = QPushButton()
            button.setFlat(True)
            button.setIcon(self.icon_clear)
            self.ui.tbl_stage.setCellWidget(r, c, button)

        channels = self.config.channels
        self.ui.tbl_stage.item(0, self.col_port).setText(str(channels.x))
        self.ui.tbl_stage.item(1, self.col_port).setText(str(channels.y))
        self.ui.tbl_stage.item(2, self.col_port).setText(str(channels.z))

        self.ui.le_serial.setText(str(self.config.stage_serial_no))
        self.ui.le_platform_id.setText(self.config.platform_id)

    def go_to_coordinates(self, name):
        """

        :param name:
        :return:
        """
        key = f'{self.stage.serial}_{self.ui.le_platform_id.text()}_{name}'
        try:
            coords = yaml.load(self.db[key])
            self.log(f'Driving stage to {name}: ({coords[0]}, {coords[1]}, {coords[2]})')
            self.stage.move_to(coords)
        except KeyError as err:
            self.log(f'Error: {key} not found in database. {err})')

    def register_coordinates(self, name, label):
        """

        :param name:
        :param label:
        :return:
        """
        key = f'{self.stage.serial}_{self.ui.le_platform_id.text()}_{name}'
        coords = list(self.stage.position)
        self.db[key] = yaml.dump(coords)
        label.setText(str(coords))

    def load_stored_values(self):
        """

        :return:
        """

        key = f'{self.stage.serial}_{self.ui.le_platform_id.text()}'
        home_coords = f'{key}_HOME'
        if self.db.exists(home_coords):
            coords = yaml.load(self.db[home_coords])
            self.ui.lbl_coords_home.setText(f'({coords[0]}, {coords[1]}, {coords[2]})')

        safe_coords = f'{key}_SAFE'
        if self.db.exists(safe_coords):
            coords = yaml.load(self.db[safe_coords])
            self.ui.lbl_coords_safe.setText(f'({coords[0]}, {coords[1]}, {coords[2]})')

        origin_coords = f'{key}_ORIGIN'
        if self.db.exists(origin_coords):
            coords = yaml.load(self.db[origin_coords])
            self.ui.lbl_coords_origin.setText(f'({coords[0]}, {coords[1]},{coords[2]})')

        custom_coords = f'{key}_CUSTOM'
        if self.db.exists(custom_coords):
            customs = yaml.load(self.db[custom_coords])
            for custom in customs:
                self.ui.list_custom.addItem(custom)

    def register_custom(self):
        """

        :return:
        """
        key = f'{self.stage.serial}_{self.ui.le_platform_id.text()}_CUSTOM'
        custom_name = self.ui.le_custom.text()
        customs = {}
        if self.db.exists(key):
            customs = yaml.load(self.db[key])
        coords = list(self.stage.position)
        customs[custom_name] = coords
        self.db[key] = yaml.dump(customs)

        for idx in range(self.ui.list_custom.count()):
            item = self.ui.list_custom.item(idx)
            text = item.text()
            if text == custom_name:
                break
        else:
            self.ui.list_custom.addItem(custom_name)

    def go_to_custom(self):
        """

        :return:
        """
        key = f'{self.stage.serial}_{self.ui.le_platform_id.text()}_CUSTOM'
        if not self.db.exists(key):
            self.log(f'error: key not found: {key}')
            return
        customs = yaml.load(self.db[key])
        custom_name = self.ui.le_custom.text()
        if custom_name not in customs:
            self.log(f'error: custom registration not found: {custom_name}')
            return
        coords = customs[custom_name]
        self.log(f'Driving stage to {custom_name}: ({coords[0]}, {coords[1]}, {coords[2]})')
        self.stage.move_to(coords)

    def custom_item_clicked(self, item):
        text = item.text()
        self.ui.le_custom.setText(text)

    def signal_zero_stage(self):
        self.stage.zero_axes()
        self.log(f'axes zeroed')

    def setup_signals(self):
        """
        Connects signals to widgets.
        :return:
        """
        self.ui.btn_zero.clicked.connect(self.signal_zero_stage)
        self.ui.btn_connect.clicked.connect(self.signal_connect_to_stage)
        self.ui.btn_register_home.clicked.connect(partial(self.register_coordinates, 'HOME', self.ui.lbl_coords_home))
        self.ui.btn_register_safe.clicked.connect(partial(self.register_coordinates, 'SAFE', self.ui.lbl_coords_safe))
        self.ui.btn_register_origin.clicked.connect(partial(self.register_coordinates, 'ORIGIN',
                                                            self.ui.lbl_coords_origin))
        self.ui.btn_goto_origin.clicked.connect(partial(self.go_to_coordinates, 'ORIGIN'))
        self.ui.btn_goto_safe.clicked.connect(partial(self.go_to_coordinates, 'SAFE'))
        self.ui.btn_goto_home.clicked.connect(partial(self.go_to_coordinates, 'HOME'))
        self.ui.btn_register_custom.clicked.connect(self.register_custom)
        self.ui.btn_goto_custom.clicked.connect(self.go_to_custom)
        self.ui.list_custom.itemClicked.connect(self.custom_item_clicked)

        self.ui.btn_z_plus.clicked.connect(partial(self.axis_step, 2, self.ui.sb_z_stepsize, 1))
        self.ui.btn_z_minus.clicked.connect(partial(self.axis_step, 2, self.ui.sb_z_stepsize, -1))
        self.ui.btn_y_plus.clicked.connect(partial(self.axis_step, 1, self.ui.sb_xy_stepsize, 1))
        self.ui.btn_y_minus.clicked.connect(partial(self.axis_step, 1, self.ui.sb_xy_stepsize, -1))
        self.ui.btn_x_plus.clicked.connect(partial(self.axis_step, 0, self.ui.sb_xy_stepsize, 1))
        self.ui.btn_x_minus.clicked.connect(partial(self.axis_step, 0, self.ui.sb_xy_stepsize, -1))
        self.ui.btn_stop.clicked.connect(self.signal_stop)

    def on_position_changed(self, previous, current):
        """
        Called when one of the stepper motors changes it's position.  it updates the position display in the ui
        :param previous: previos value of the stepper postion
        :param current: current value of the stepper psotion
        :return:
        """
        if previous == current:
            return
        self.display_position()

    def display_position(self):
        """
        Utility function Display position text on ui.lbl_position.
        """
        try:
            coordinates = self.stage.position
            text = f'Position: ({coordinates[0]}, {coordinates[1]}, {coordinates[2]})'
            text2 = f' || Voltage: ({self.data_values[0]}, {self.data_values[1]}, {self.data_values[2]}'
            self.ui.lbl_position.setText(f'{text}{text2}')
            for i in range(3):
                item = self.ui.tbl_stage.item(i, 2).setText(str(coordinates[i]))
        except PhidgetException as err:
            print('err: ', err.details)

    def disable_control_widgets(self):
        for widget in self.control_widgets:
            widget.setEnabled(False)

    def enable_control_widgets(self):
        for widget in self.control_widgets:
            widget.setEnabled(True)

    def signal_connect_to_stage(self):
        """
        Reads UI values to determine how to connect to stage and initializes the stage object.
        TODO: Loads platform specific data for the stage, i.e. registration data
        :return:
        """
        serial = int(self.ui.le_serial.text())

        x_channel = int(self.ui.tbl_stage.item(0, self.col_port).text())
        y_channel = int(self.ui.tbl_stage.item(1, self.col_port).text())
        z_channel = int(self.ui.tbl_stage.item(2, self.col_port).text())

        self.stage = PhidgetStage(serial, x_channel, y_channel, z_channel)


        for name, axis in self.axes_widgets.items():
            try:
                self.stage.initialize_axis(axis.index)
                self.log(f'Connected to axis {name}')
                self.ui.tbl_stage.cellWidget(axis.index, self.col_connected).setIcon(self.icon_blue)
            except InitializationError as err:
                self.ui.tbl_stage.cellWidget(axis.index, self.col_connected).setIcon(self.icon_red)
                self.log(err)
        self.stage.stop_motion()
        # self.ui.le_serial.setEnabled(False)
        self.ui.btn_connect.setText('Disconnect')
        self.ui.btn_connect.clicked.disconnect()
        self.ui.btn_connect.clicked.connect(self.signal_close_stage_connection)
        self.display_position()
        self.enable_control_widgets()
        self.log('Connected to stage.')
        self.stage.position_changed_callback = self.on_position_changed
        self.load_stored_values()
        self.ui.btn_stop.setEnabled(True)
        self.axis_timer.start(500)
        self.limit_timer.start(100)
        self.drive_to_home()

    def signal_close_stage_connection(self):
        """
        Closes the stage connection and resets widgets to the correct states.
        TODO:  proper stage closure.
        :return:
        """
        self.stage.close()
        for axis in self.axes_widgets:
            self.axes_widgets[axis].led_color = 'clear'
        self.ui.le_serial.setEnabled(True)
        self.ui.btn_connect.setText('Connect')
        self.ui.btn_connect.clicked.disconnect()
        self.disable_control_widgets()
        self.ui.btn_connect.clicked.connect(self.signal_connect_to_stage)
        self.stage.close()

    def signal_stop(self):
        self.axis_step(0)
        self.axis_step(1)
        self.axis_step(2)

    def axis_step(self, axis, sb_step=None, sign=1):
        """
        Step the axis by a value defined by sb_step.
        If the axis has hit it's limit switch, send the analog signal to release the break before sending a move_stage
        :param axis:
        :param sign:
        :param sb_step:
        :return:
        """
        # if self.axis_disabled[axis]:
        # if not self.axis_last_move[axis]:
        #     self.task_a0.StartTask()
        #     self.task_a1.StartTask()
        #     self.task_a0.WriteAnalogF64(100, False, -1, PyDAQmx.DAQmx_Val_GroupByChannel, self.analog_table[axis][0],
        #                                 int32(100), None)
        #     self.task_a1.WriteAnalogF64(100, False, -1, PyDAQmx.DAQmx_Val_GroupByChannel, self.analog_table[axis][1],
        #                                 int32(100), None)
        #     self.task_a0.WriteAnalogF64(100, False, -1, PyDAQmx.DAQmx_Val_GroupByChannel, self.analog_table['reset'][0],
        #                                 int32(100), None)
        #
        #     self.task_a1.WriteAnalogF64(100, False, -1, PyDAQmx.DAQmx_Val_GroupByChannel, self.analog_table['reset'][1],
        #                                 int32(100), None)
        #
        #     self.task_a0.StopTask()
        #     self.task_a1.StopTask()
        self.axis_last_move[self.axes[axis]] = sign
        position = self.stage.position
        step = sb_step.value() if sb_step else 0
        position[axis] += step * sign
        self.stage.move_to(position)

    def log(self, message):
        """
        Append log to the log list widget with date / time
        :param message:
        :return:
        """
        try:
            dt = datetime.datetime.now().time()
            time_string = f'{dt.hour:02}:{dt.minute:02}:{dt.second:02}'
            item = QListWidgetItem()
            text = str(time_string + ' ' + message)
            item.setText(text)
            self.ui.list_eventlog.insertItem(0, item)
        except Exception as error:
            logging.error(error)

    def closeEvent(self, event):
        """
        Handle necessary shutdown tasks; i.e. stop threads and do proper hardware shutdown
        :param event: QT event, not used.
        :return:
        """
        self.stage.close()


def main():
    """
    Boilerplate PyQT init
    :return:
    """
    app = QApplication(sys.argv)
    main_window = StageUI()
    main_window.setFixedWidth(1175)
    main_window.setFixedHeight(818)
    hostname = socket.gethostname()
    main_window.setWindowTitle(f'Stage Controller ({hostname})')
    styles.dark(app)
    styled_window = windows.ModernWindow(main_window)
    styled_window.show()
    app.exec_()
    sys.exit()


if __name__ == '__main__':
    main()
