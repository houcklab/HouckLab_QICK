#### testing driver for agilent 33250a

import pyvisa

rm = pyvisa.ResourceManager()

#####
# burst_cmd_list = ["BURSt:MODE{0}", "BURSt:NCYCles{0}", "BURSt:INTernal:PERiod{0}", "BURSt:PHASe{0}",
#                       "BURSt:STATe{0}", "UNIT:ANGLe{0}", "BURSt:GATE:POLarity{0}"]
#####

#### define class

class agilent33250a():
    def __init__(self, address):
        self.awg = rm.open_resource(address)

    def set_freq(self, freq):
        self.awg.write('FREQuency %f' % freq)
    def set_period(self, period):
        self.awg.write('FREQuency %s' % str(1/period))

    def set_waveform(self, waveform):
        waveforms_list = ['SIN', 'SQUARE', 'RAMP', 'PULSE', 'NOISE', 'DC']
        self.awg.write('FUNCtion %s' % waveform)

    def set_duty_cycle(self, duty_cycle):
        self.awg.write('FUNCtion:SQUare:DCYCle %.8f' % duty_cycle)

    def set_voltage(self, volt):
        self.awg.write('VOLTage %f' % volt)

    def set_offset(self, offset):
        self.awg.write('VOLTage:OFFSet %f' % offset)

    def outputON(self):
        self.awg.write('OUTPut 1')

    def outputOFF(self):
        self.awg.write('OUTPut 0')


##### running the control
duty_cycle = 20
waveform = 'SQUARE'
freq = 1e6
period = 0.1
volts = 0.5
offset = 0.0

awg = agilent33250a('GPIB1::9::INSTR')

awg.set_waveform(waveform)
awg.set_period(period)
awg.set_duty_cycle(duty_cycle)
awg.set_voltage(volts)
awg.set_offset(volts / 2)

awg.outputON()