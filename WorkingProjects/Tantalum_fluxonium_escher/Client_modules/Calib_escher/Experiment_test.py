# This exists to test simple experiment bodies, all in one file (run this)
from qick import NDAveragerProgram

from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.CoreLib.socProxy import makeProxy


class Experiment_test(NDAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        # Declare channel
        pass
#        self.readout_ch = 0 # used for both ADC and DAC, will break if they're not the same
#        self.qubit_ch = 1
#
#        self.declare_gen(ch=self.readout_ch, nqz=2)  # Readout
#        self.declare_gen(ch=self.qubit_ch, nqz=1)
#
#        # Create qubit pulse
#        qubit_len = 1 # us
#        qubit_freq = 940 # MHz
#        length_reg = self.us2cycles(qubit_len, gen_ch=self.qubit_ch)
#        self.set_pulse_registers(ch=self.qubit_ch, style="const", freq=qubit_freq, phase=0, gain=32000, length=length_reg)
#
#        # Declare readout
#        read_length = 5 # us
#        read_freq = 5500 # MH
#        self.declare_readout(ch=self.readout_ch, length=self.us2cycles(read_length, ro_ch=self.readout_ch),
#                                 freq=read_freq, gen_ch=self.readout_ch)
#
#        # Readout pulse
#        self.set_pulse_registers(ch=self.readout_ch, style="const",
#                                 freq=self.freq2reg(read_freq, gen_ch=self.readout_ch, ro_ch=self.readout_ch), phase=0,
#                                 gain=6000, length=self.us2cycles(read_length, gen_ch=self.readout_ch))
#
#        self.sync_all(self.us2cycles(0.1))

    def body(self):
        pass
#        adc_trig_offset_cycles = self.us2cycles(0.5) # Do NOT include channel, it's wrong!
#
#        self.pulse(ch = self.qubit_ch)
#        self.sync_all(self.us2cycles(0.01))  # Wait a few ns to align channels
#
#        # trigger measurement, play measurement pulse, wait for relax_delay_1. Once per experiment.
#        self.measure(pulse_ch=self.readout_ch, adcs=[self.readout_ch], adc_trig_offset=adc_trig_offset_cycles,
#                     wait=True,  # t = 0,
#                     syncdelay=self.us2cycles(0.3, gen_ch=self.readout_ch))
#
#        self.sync_all(self.us2cycles(0.01))  # Wait for a few ns to align channels
#
#        # Cycle the fr ramp as requested.
#        for c in range(50):
#            self.pulse(ch = self.qubit_ch)
#            self.sync_all(self.us2cycles(0.01))
#
#        # trigger measurement, play measurement pulse, wait for relax_delay_2. Once per experiment.
#        self.measure(pulse_ch=self.readout_ch, adcs=[self.readout_ch], adc_trig_offset=adc_trig_offset_cycles,
#                     t = 0, wait = True,
#                     syncdelay=self.us2cycles(0.1))




# Main code
soc, soccfg = makeProxy()
cfg = {'reps': 1e6}
prog = Experiment_test(soccfg, cfg)
prog.run_rounds(soc, threshold=None, angle=None, load_pulses=True, save_experiments=None, start_src="internal", progress=True)
