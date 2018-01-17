
import PyDAQmx
import ctypes
import logging
import numpy as np

t = PyDAQmx.Task()
t.create_analog_out_voltage_task('clamp_0', 'ao0')
t = d.clamp_0
t.write(np.zeros(100))
