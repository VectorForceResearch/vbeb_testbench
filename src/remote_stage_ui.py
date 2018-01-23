#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# TODO:  Mouse ID

import logging
import socket
from functools import partial
from itertools import product
import redis
import visual_behavior
from visual_behavior import hardware_proxy
import yaml
import sys
# from PyDAQmx import *
from qtmodern import styles, windows
from qtpy import uic, QtCore
from qtpy.QtCore import QTimer
from qtpy.QtGui import QIcon, QPixmap
from qtpy.QtWidgets import *
import hashlib
from aibsmw import ZROProxy


class StageUI(QMainWindow):
    col_connected = 0
    col_port = 1
    col_position = 2
    col_moving = 3
    col_engaged = 4
    col_limit = 5

    def __init__(self):
        """
        Stage Controller PyQt UI Object
        """
        super(QMainWindow, self).__init__()
        self.module_path = visual_behavior.__path__
        self.config = visual_behavior.source_project_configuration('visual_behavior_v1.yml')
        self.admin_digest = b'!#/)zW\xa5\xa7C\x89J\x0eJ\x80\x1f\xc3'  # obviously get this from db
        self.admin_enabled = False

        self.hw_proxy = hardware_proxy.RemoteStageController()
        self.stage = None
        self.daq = None

        self.ui = uic.loadUi(self.module_path[0] + '/resources/remote_stage_controller.ui')
        self.setCentralWidget(self.ui)

        self.setup_ui()
        self.log('Stage Controller Ready')
        self.table_timer = QTimer()
        self.table_timer.timeout.connect(self.update_table)

        self.coordinates = {'home': None,
                            'working': None,
                            'load': None,
                            'mouse': None}
        self._ignore_limits = False
        self.db = self.setup_db()
        self._spout_state = 0

        self.signal_connect_to_rig('localhost')

    def log(self, message):
        logging.info(message)
        self.ui.statusBar.showMessage(message)

    def setup_db(self):
        db = {}
        return db

    def load_stage_coordinates(self):
        """

        :return:
        """

        key = f'{self.stage.serial}'

        safe_coords = f'{key}_working'
        if safe_coords in self.db:
            self.coordinates['working'] = yaml.load(self.db[safe_coords])
            self.ui.lbl_coords_safe.setText(f'({coords[0]}, {coords[1]}, {coords[2]})')

        origin_coords = f'{key}_load'
        if origin_coords in self.db:
            self.coordinates['load'] = yaml.load(self.db[origin_coords])
            self.ui.lbl_coords_origin.setText(f'({coords[0]}, {coords[1]},{coords[2]})')

    def load_mouse_coordinates(self):
        """

        :return:
        """

        key = f'{self.stage.serial}_{self.ui.le_mouse_id}'
        if key in self.db:
            self.coordinates['mouse'] = yaml.load(self.db[key])
            self.log(f'loaded mouse offset: ({coords[0]}, {coords[1]}, {coords[2]})')
        else:
            self.log(f'Could not find mouse offset: {key}')

    def setup_ui(self):
        """

        :return:
        """


        self.ui.btn_moveto.clicked.connect(self.signal_move_to)
        self.ui.btn_air_1.clicked.connect(self.signal_extend_lickspout)
        self.ui.btn_air_2.clicked.connect(self.signal_retract_lickspout)
        self.ui.btn_water_1.clicked.connect(self.signal_water_sol_1)
        self.ui.btn_water_2.clicked.connect(self.signal_water_sol_2)
        self.ui.btn_home.clicked.connect(self.signal_home_stage)

        self.ui.btn_z_plus.clicked.connect(partial(self.axis_step, 2, 1))
        self.ui.btn_z_minus.clicked.connect(partial(self.axis_step, 2, -1))
        self.ui.btn_y_plus.clicked.connect(partial(self.axis_step, 1, 1))
        self.ui.btn_y_minus.clicked.connect(partial(self.axis_step, 1, -1))
        self.ui.btn_x_plus.clicked.connect(partial(self.axis_step, 0, 1))
        self.ui.btn_x_minus.clicked.connect(partial(self.axis_step, 0, -1))
        self.ui.btn_stop.clicked.connect(self.signal_stop)
        self.ui.btn_emergency.clicked.connect(self.signal_emergency)
        self.ui.btn_register_working.clicked.connect(partial(self.register_coordinates, 'working'))
        self.ui.btn_register_load.clicked.connect(partial(self.register_coordinates, 'load'))
        self.ui.btn_register_mouse.clicked.connect(partial(self.register_coordinates, 'mouse'))
        self.ui.le_mouse_id.editingFinished.connect(self.load_mouse_coordinates)

        self.ui.btn_working.clicked.connect(partial(self.move_to_coordinates, 'working'))
        self.ui.btn_load.clicked.connect(partial(self.move_to_coordinates, 'load'))
        self.ui.btn_mouse.clicked.connect(partial(self.move_to_coordinates, 'mouse'))


        self.icon_clear = QIcon(self.module_path[0] + '/resources/led_clear.png')
        self.icon_red = QIcon(self.module_path[0] + '/resources/led_red.png')
        self.icon_blue = QIcon(self.module_path[0] + '/resources/led_blue.png')
        self.icon_green = QIcon(self.module_path[0] + '/resources/led_green.png')

        self.ui.btn_x_release.clicked.connect(partial(self.set_clamp, 0))
        self.ui.btn_x_release.clicked.connect(partial(self.set_clamp, 1))
        self.ui.btn_x_release.clicked.connect(partial(self.set_clamp, 2))
        self.ui.btn_reset.clicked.connect(partial(self.set_clamp, 'reset'))
        self.ui.cb_limits.toggled.connect(self.signal_ignore_limits)

        for c, r in product([self.col_port, self.col_position], range(3)):
            item = QTableWidgetItem()
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.ui.tbl_stage.setItem(r, c, item)

        for c, r in product([self.col_connected, self.col_moving, self.col_engaged, self.col_limit], range(3)):
            button = QPushButton()
            button.setFlat(True)
            button.setIcon(self.icon_clear)
            self.ui.tbl_stage.setCellWidget(r, c, button)

        channels = self.config.phidget.channels
        self.ui.tbl_stage.item(0, self.col_port).setText(str(channels.x))
        self.ui.tbl_stage.item(1, self.col_port).setText(str(channels.y))
        self.ui.tbl_stage.item(2, self.col_port).setText(str(channels.z))

        self.disable_user_controls()

    def set_clamp(self, axis):
        self.hw_proxy.clamp_signal(axis)

    def signal_emergency(self):
        self.signal_retract_lickspout()
        self.hw_proxy.stop_motion()

    def signal_ignore_limits(self, state):
        if self.ui.cb_limits.isChecked():
            self._ignore_limits = True
            self.hw_proxy.ignore_limits(True)
        else:
            self._ignore_limits = False
            self.hw_proxy.ignore_limits(False)

    def update_table(self):
        moving = self.stage.is_moving
        engaged = self.stage.is_engaged
        limits = self.stage.limits
        position = self.stage.position
        if any(moving):
            self.ui.lbl_status.setText('Status: Stage Moving')
        else:
            self.ui.lbl_status.setText('Status:')

        for i in range(3):
            if moving[i]:
                self.ui.tbl_stage.cellWidget(i, self.col_moving).setIcon(self.icon_blue)
            else:
                self.ui.tbl_stage.cellWidget(i, self.col_moving).setIcon(self.icon_clear)
            if engaged[i]:
                self.ui.tbl_stage.cellWidget(i, self.col_engaged).setIcon(self.icon_blue)
            else:
                self.ui.tbl_stage.cellWidget(i, self.col_engaged).setIcon(self.icon_clear)
            if limits[i]:
                self.ui.tbl_stage.cellWidget(i, self.col_limit).setIcon(self.icon_red)
            else:
                self.ui.tbl_stage.cellWidget(i, self.col_limit).setIcon(self.icon_blue)
            self.ui.tbl_stage.item(i, self.col_position).setText(str(position[i]))

    def axis_step(self, axis, sign=1):
        """
        Step the axis by a value defined by sb_step.
        If the axis has hit it's limit switch, send the analog signal to release the break before sending a move_stage
        :param axis:
        :param sign:
        :param sb_step:
        :return:
        """
        if not self.stage:
            return

        if self.ui.le_step_size.text() != '':
            step = float(self.ui.le_step_size.text())
        else:
            step = self.config.phidget.step_size
        position = self.stage.position
        position[axis] += step * sign
        self.stage.append_move(position)

    def register_coordinates(self, name):
        """

        :param name:
        :param label:
        :return:
        """
        try:
            key = f'{self.stage.serial}_{name}'
            coords = list(self.stage.position)
            self.coordinates[name] = coords
            self.log('setting {name} to {coords}')
            self.db[key] = yaml.dump(coords)

            '''There is a hardware mixup preventing proper registration o Load/Unload.  For now it is set as an 
            x-translation o working'''

            if name == 'working':
                coords[0] += self.config.load_x_translation
                self.log(f'setting load to {coords}')
                self.coordinates['load'] = coords
                self.db[f'{self.hw_proxy.serial}_load'] = yaml.dump(coords)

                ''' b/c we can get stuck on the monument, we will retract the lickspout, move about, and extend again'''
                self.signal_retract_lickspout()
                coords = list(self.stage.position)
                coords[2] -= 10
                self.move_to_coordinates(coords)
                QTimer.singleShot(200, self.signal_extend_lickspout)

        except Exception as err:
            self.log(f'Error recording {name} coordinates to the db')
            self.log(f'{err}')

    def move_to_coordinates(self, name):

        coords = self.coordinates[name]
        try:
            self.log(f'Driving to {name}: {coords}')
            if coords:
                self.hw_proxy.move_to(coords)
        except KeyError as err:
            self.log(f'Error: {key} has not been registered.')

    def signal_stop(self):
        self.how_proxy.stop_motion()

    def signal_home_stage(self):
        self.hw_proxy.home_stage()

    def signal_retract_lickspout(self):
        self.hw_proxy.retract_lickspout()

    def signal_extend_lickspout(self):
        self.hw_proxy.extend_lickspout()

    def signal_water_sol_1(self):
        self.hw_proxy.signal_water_sol_1()

    def signal_water_sol_2(self):
        self.hw_proxy.signal_water_sol_2()

    def signal_move_to(self):
        try:
            x = float(self.ui.le_x.text())
            y = float(self.ui.le_y.text())
            z = float(self.ui.le_z.text())
            self.stage.append_move([x, y, z])
        except Exception as err:
            print('error:', err)
            pass

    def signal_connect_to_rig(self, host):
        host = 'localhost'

        self.stage = self.hw_proxy
        # self.daq = self.hw_proxy.daq
        # self.load_stage_coordinates()
        self.log(f'Connected to stage: {self.hw_proxy.stage_serial}')
        self.enable_user_controls()
        for i in range(3):
            self.ui.tbl_stage.cellWidget(i, self.col_connected).setIcon(self.icon_blue)
        self.table_timer.start(500)

    def disable_user_controls(self):
        user_controls = [self.ui.btn_x_minus, self.ui.btn_x_plus, self.ui.btn_y_minus, self.ui.btn_y_plus,
                         self.ui.btn_z_minus, self.ui.btn_z_plus, self.ui.btn_home, self.ui.btn_load,
                         self.ui.btn_working, self.ui.btn_mouse, self.ui.btn_stop ]

        for control in user_controls:
            control.setEnabled(False)

    def enable_user_controls(self):
        user_controls = [self.ui.btn_x_minus, self.ui.btn_x_plus, self.ui.btn_y_minus, self.ui.btn_y_plus,
                         self.ui.btn_z_minus, self.ui.btn_z_plus, self.ui.btn_home, self.ui.btn_load,
                         self.ui.btn_working, self.ui.btn_mouse, self.ui.btn_stop]

        for control in user_controls:
            control.setEnabled(True)

    def keyPressEvent(self, event):
        """

        :param event:
        :return:
        """
        modifiers = QApplication.keyboardModifiers()
        if event.key() == QtCore.Qt.Key_A:
            self.axis_step(0, -1)
        if event.key() == QtCore.Qt.Key_Space:
            if not self.admin_enabled:
                return

            if self._spout_state:
                self.signal_retract_lickspout()
                self._spout_state = 0
            else:
                self.signal_extend_lickspout()
                self._spout_state = 1

        if event.key() == QtCore.Qt.Key_D:
            if modifiers == (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier):
                if self.admin_enabled:
                    self.admin_enabled = False
                else:
                    if self.authenticate_admin():
                        logging.info('Admin mode enabled.')
                        self.admin_enabled = True
            else:
                self.axis_step(0, 1)
        elif event.key() == QtCore.Qt.Key_W:
            self.axis_step(1, 1)
        elif event.key() == QtCore.Qt.Key_S:
            self.axis_step(1, -1)
        elif event.key() == QtCore.Qt.Key_Q:
            self.axis_step(2, -1)
        elif event.key() == QtCore.Qt.Key_E:
            self.axis_step(2, 1)

    def authenticate_admin(self):
        """


        :return:
        """
        text, ok = QInputDialog.getText(self, 'Administration Panel', 'Password:', echo=QLineEdit.Password)
        if ok:
            if hashlib.md5(text.encode()).digest() == self.admin_digest:
                return True
            else:
                dialog = QMessageBox()
                dialog.setWindowTitle('Invalid Password')
                dialog.setText('Unable to enable administration mode.  Invalid Password.')

                dialog.exec_()
        return False


def main():
    """
    Boilerplate PyQT init
    :return:
    """
    visual_behavior.init_log()
    app = QApplication(sys.argv)
    main_window = StageUI()
    main_window.setFixedWidth(600)
    main_window.setFixedHeight(575)
    hostname = socket.gethostname()
    main_window.setWindowTitle(f'Stage Controller ({hostname})')
    styles.dark(app)
    styled_window = windows.ModernWindow(main_window)
    styled_window.show()
    app.exec_()
    sys.exit()


if __name__ == '__main__':
    main()
