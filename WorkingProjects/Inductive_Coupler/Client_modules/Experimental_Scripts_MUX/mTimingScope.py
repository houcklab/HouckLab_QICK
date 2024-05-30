from qick import *
# from WorkingProjects.Inductive_Coupler.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
import WorkingProjects.Inductive_Coupler.Client_modules.Helpers.FF_utils as FF

class TimingProg(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        self.f_ge = self.freq2reg(5000, gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_ge, phase=0, gain=cfg["qubit_gain"],
                                 length=self.us2cycles(cfg["length"], gen_ch=self.cfg["qubit_ch"]))

        FF.FFDefinitions(self)
        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        cfg = self.cfg
        self.sync_all(gen_t0=self.gen_t0)
        print('wo', self._dac_ts)
        self.FFPulses([900, 900, 900, 900], self.cfg["length"], t_start = 30)
        # self.pulse(ch=self.cfg["qubit_ch"],t=30)
        self.sync_all(self.us2cycles(cfg['relax_delay']), gen_t0=self.gen_t0)
        print(self.cycles2us(1, gen_ch=0), self.cycles2us(1))

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)

    # ====================================================== #


from qick import *
# from WorkingProjects.Inductive_Coupler.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
import WorkingProjects.Inductive_Coupler.Client_modules.Helpers.FF_utils as FF

class CavitySpecFFProg(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains= cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"], #gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"], gen_ch = self.cfg["res_ch"]))

        FF.FFDefinitions(self)
        self.synci(200)  # give processor some time to configure pulses

    def body(self):

        cfg = self.cfg
        self.sync_all(gen_t0=self.gen_t0)
        print('wo', self._dac_ts)
        self.FFPulses([900, 900, 900, 900], self.cfg["length"], t_start = 30)
        # self.pulse(ch=self.cfg["qubit_ch"],t=30)
        self.sync_all(self.us2cycles(cfg['relax_delay']), gen_t0=self.gen_t0)
        print(self.cycles2us(1, gen_ch=0), self.cycles2us(1))


        cfg = self.cfg
        self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFReadouts, self.cfg["length"])
        self.pulse(ch=self.cfg["res_ch"],t=0)

        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"], #gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"], gen_ch = self.cfg["res_ch"]))
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=False,
                     syncdelay=self.us2cycles(10))
        self.FFPulses(-1 * self.FFReadouts, self.cfg["length"])
        self.sync_all(self.us2cycles(self.cfg["cav_relax_delay"]), gen_t0=self.gen_t0)

    def FFPulses(self, list_of_gains, length_us, t_start='auto'):
        FF.FFPulses(self, list_of_gains, length_us, t_start)
