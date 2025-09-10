from WorkingProjects.Triangle_Lattice_tProcV1.Helpers.RampHelpers import generate_ramp
from WorkingProjects.Triangle_Lattice_tProcV1.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Triangle_Lattice_tProcV1.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
import WorkingProjects.Triangle_Lattice_tProcV1.Helpers.FF_utils as FF
from WorkingProjects.Triangle_Lattice_tProcV1.Helpers.rotate_SS_data import *
from WorkingProjects.Triangle_Lattice_tProcV1.Basic_Experiments_Programs.AveragerProgramFF import AveragerProgramFF
import scipy

class TwoPartProgram(AveragerProgramFF):
    def initialize(self):
        cfg = self.cfg

        # Qubit (Equal sigma for all)
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_length = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_length)

        # Readout (MUX): resonator DAC gen and readout ADCs
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains= cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"], #gain=cfg["res_gain"],
                                 length=self.us2cycles(cfg["res_length"]))

        FF.FFDefinitions(self)

        self.sync_all(200)


    def body(self):
        # 1: FFPulse
        self.sync_all(gen_t0=self.gen_t0)
        self.FFPulses(self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)
        for i in range(len(self.cfg["qubit_gains"])):
            gain_ = self.cfg["qubit_gains"][i]
            freq_ = self.freq2reg(self.cfg["f_ges"][i], gen_ch=self.cfg["qubit_ch"])
            time_ = self.us2cycles(1) if i==0 else 'auto'

            self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=freq_, phase=0,
                                 gain=gain_,
                                 waveform="qubit", t=time_)

        # 2: FFReadouts
        self.sync_all(self.cfg['delay_cycles'], gen_t0=self.gen_t0)
        self.FFPulses(self.FFReadouts, self.cfg["res_length"])

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))

        # End: invert FF pulses to ensure pulses integrate to 0
        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
        self.FFPulses(-self.FFExpt - 2*(self.FFReadouts - self.FFExpt), 2.32515/1e3*3)

        self.FFPulses(-1 * self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01)
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))