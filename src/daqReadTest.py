import PyDAQmx
from PyDAQmx import *
import numpy
from ctypes import byref
import time

tasks = {}
for idx in [5, 3, 1]:
    task = Task()
    print(f'creating task for DI Channel: Dev9/port0/line{idx}')
    task.CreateDIChan(f'Dev9/port0/line{idx}'.encode(), b'', PyDAQmx.DAQmx_Val_ChanPerLine)
    tasks[idx] = task
    task.StartTask()

while True:
    read = int32()
    data = numpy.zeros(10, dtype=numpy.uint32)
    values = []
    for idx, task in tasks.items():
        task.ReadDigitalU32(-1, .1, PyDAQmx.DAQmx_Val_GroupByChannel, data, 10, byref(read), None)
        values.append(data[0])
    print(f'voltages: {values}')
    values = []
    time.sleep(.1)

