from PyDAQmx import *
import numpy
from ctypes import byref
import time


class CallbackTask(Task):
    def __init__(self, channel):
        Task.__init__(self)
        self.data = numpy.zeros(1000, dtype=numpy.uint32)
        self.a = []
        self.channel = f'Dev9/port0/{channel}'.encode()
        self.CreateDIChan(self.channel, b'', DAQmx_Val_ChanPerLine)

        # self.CreateAIVoltageChan(self.channel, b'',DAQmx_Val_RSE,-10.0,10.0,DAQmx_Val_Volts,None)
        # self.CfgSampClkTiming(b'',10000.0,DAQmx_Val_Rising,DAQmx_Val_ContSamps,1000)
        # self.AutoRegisterEveryNSamplesEvent(DAQmx_Val_Acquired_Into_Buffer,1000,0)
        # self.AutoRegisterDoneEvent(0)

    def start(self):
        while True:
            read = int32()
            self.ReadDigitalU32(-1, .1, DAQmx_Val_GroupByChannel, self.data, 1000, byref(read), None)
            self.a.extend(self.data.tolist())
            print(f'channel: {self.channel} ... {self.data[0]}')
            # print ("Status",status.value)
            time.sleep(.1)

    def EveryNCallback(self):
        read = int32()
        self.ReadDigitalU32(1000, .1, DAQmx_Val_GroupByChannel, self.data, 1000, 1000)

        # self.ReadAnalogF64(1000,10.0,DAQmx_Val_GroupByScanNumber,self.data,1000,byref(read),None)
        self.a.extend(self.data.tolist())
        print(f'channel: {self.channel} ... {self.data[0]}')
        return 0  # The function should return an integer

    def DoneCallback(self, status):
        print("Status", status.value)
        return 0  # The function should return an integer


task = CallbackTask('line5')
task.StartTask()
task.start()
input('Acquiring samples continuously. Press Enter to interrupt\n')

task.StopTask()
task.ClearTask()

exit()

chx = Task()
chy = Task()
chz = Task()

read = int32()
data = numpy.zeros((1000,), dtype=numpy.float64)

# DAQmx Configure Code
analog_input.CreateAIVoltageChan("Dev9/ai0", b"", DAQmx_Val_Cfg_Default, -10.0, 10.0, DAQmx_Val_Volts, None)
analog_input.CfgSampClkTiming(b"", 10000.0, DAQmx_Val_Rising, DAQmx_Val_FiniteSamps, 1000)

# DAQmx Start Code
analog_input.StartTask()

# DAQmx Read Code
analog_input.ReadAnalogF64(1000, 10.0, DAQmx_Val_GroupByChannel, data, 1000, byref(read), None)

print(f"Acquired {read.value} points")
