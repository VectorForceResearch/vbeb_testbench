import numpy as np
import PyDAQmx
from visual_behavior import nidaqio

d = nidaqio.NIDAQio()
d.create_analog_out_voltage_task('clamp_0', 'ao0')
t = d.clamp_0
t.write(np.zeros(100))
