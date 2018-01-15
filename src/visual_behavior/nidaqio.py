import PyDAQmx
import ctypes
import logging
import numpy as np


class NIDAQNotFoundError(Exception):
    ...


class NIDAQTask(PyDAQmx.Task):
    def __init__(self):
        super().__init__()


class NIDAQDigitalTask(NIDAQTask):
    def __init__(self, device_name, channel, mode='di'):
        super().__init__()
        self.device_name = device_name
        self.channel = channel
        self.mode = mode

        self.fq_channel = f'{device_name}/{channel}'
        logging.info(f'Creating task: {self.fq_channel}')
        self.task = PyDAQmx.Task()
        if mode == 'di':
            self.task.CreateDIChan(self.fq_channel.encode(), ''.encode(), PyDAQmx.DAQmx_Val_ChanForAllLines)
        elif mode == 'do':
            self.task.CreateDOChan(self.fq_channel.encode(), ''.encode(), PyDAQmx.DAQmx_Val_ChanForAllLines)
        else:
            raise ValueError(f'Unknown mode: {mode}.  Valid modes are \'di\' and \'do\'.')

    def read(self):
        if self.mode != 'di':
            raise TypeError(f'{self.fq_channel} is not configured for read.')
        read = PyDAQmx.int32()
        data = np.zeros(1000, dtype=np.uint32)
        self.task.ReadDigitalU32(-1, .1, PyDAQmx.DAQmx_Val_GroupByChannel, data, 1000, ctypes.byref(read), None)
        return data[0]

    def write(self, data):
        if self.mode != 'do':
            raise TypeError(f'{self.fq_channel} is not configured for write.')
        self.StartTask()
        self.WriteDigitalLines(1, 1, len(data), PyDAQmx.DAQmx_Val_GroupByChannel, data, None, None)
        self.StopTask()


class NIDAQAnalogTask(NIDAQTask):
    def __init__(self, device_name, channel, mode='ao_volt'):
        super().__init__()
        self.device_name = device_name
        self.channel = channel
        self.mode = mode

        self.fq_channel = f'{device_name}/{channel}'
        logging.info(f'Creating task: {self.fq_channel}')

        if mode == 'ao_volt':
            self.CreateAOVoltageChan(f'{self.fq_channel}'.encode(), b'', -10.0, 10.0, PyDAQmx.DAQmx_Val_Volts,
                                          None)
        else:
            raise ValueError(f'Unknown mode: {mode}.  Valid modes are \'ao_volt\'.')

    def write(self, data):
        if self.mode != 'ao_volt':
            raise TypeError(f'{self.fq_channel} is not configured for write.')
        logging.debug(f'Writing analog voltage to {self.fq_channel}')
        self.StartTask()
        self.WriteAnalogF64(len(data), False, -1, PyDAQmx.DAQmx_Val_GroupByChannel, data, PyDAQmx.int32(len(data)),
                                None)
        self.StopTask()


class NIDAQio(object):
    def __init__(self):
        buffer_size = 1024
        buffer = ctypes.create_string_buffer(buffer_size)
        result = PyDAQmx.DAQmxGetSysDevNames(buffer, buffer_size)
        if result != 0:
            raise NIDAQNotFoundError(f'Could not find NIDAQ device: {result}')
        self.device_name = buffer.value
        logging.info(f'Found NIDAQ device: {self.device_name.decode()}')

    def _can_add_task(self, name, overwrite):
        """

        :param name:
        :param overwrite:
        :return:
        """
        if hasattr(self, name):
            task = getattr(self, name)
            if not overwrite:
                raise NameError(f'Can\'t create task {name}.  {self.device_name} already has an attribute named {name}.')
            if not isinstance(task, PyDAQmx.Task):
                raise TypeError(f'Can\'t overwrite attribute {name}.  Existing attribute is not a PyDAQmx Task.')
            return task
        return None

    def create_digital_out_task(self, name, channel, overwrite=False):
        """

        :param name:
        :param channel:
        :return:
        """
        old_task = self._can_add_task(name, overwrite)
        if old_task:
            old_task.StopTask()

        task = NIDAQDigitalTask(self.device_name.decode(), channel, mode='do')
        setattr(self, name, task)

    def create_digital_in_task(self, name, channel, overwrite=False):
        """

        :param name:
        :param channel:
        :return:
        """
        old_task = self._can_add_task(name, overwrite)
        if old_task:
            old_task.StopTask()

        task = NIDAQDigitalTask(self.device_name.decode(), channel, mode='di')
        setattr(self, name, task)

    def create_analog_out_voltage_task(self, name, channel, overwrite=False):
        old_task = self._can_add_task(name, overwrite)
        if old_task:
            old_task.StopTask()

        task = NIDAQAnalogTask(self.device_name.decode(), channel, mode='ao_volt')
        setattr(self, name, task)
