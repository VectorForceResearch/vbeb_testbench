import PyDAQmx
import ctypes
import logging

class NIDAQNotFoundError(Exception):
    ...


class NIDAQio(object):
    def __init__(self):
        buffer_size = 20
        buffer = ctypes.create_string_buffer('\000' * buffer_size)
        result = PyDAQmx.DAQmxGetSysDevNames(buffer, buffer_size)
        if result != 0:
            raise NIDAQNotFoundError(f'Could not find NIDAQ device: {result}')
        self.device_name = buffer.value()
        logging.info(f'Found NIDAQ device: {self.device_name}')

    def _can_add_task(self, name, overwrite):
        if hasattr(self, name):
            task = getattr(self, name)
            if not overwrite:
                raise NameError('Can\'t create task {name}.  {self.device_name} already has an attribute named {name}.')
            if not isinstance(task, PyDAQmx.Task):
                raise TypeError('Can\'t overwrite attribute {name}.  Existing attribute is not a PyDAQmx Task.')
            return task
        return None

    def create_DO_task(self, name, channel, overwrite=False):
        """

        :param name:
        :param channel:
        :return:
        """
        old_task = self._can_add_task(name, overwrite)
        if old_task:
            old_task.StopTask()

        task = PyDAQmx.Task()
        task.CreateDOChan(f'/{self.device_name}/{channel}'.encode(), ''.encode(),PyDAQmx.DAQmx_Val_ChanForAllLines)
        setattr(self, name, task)

