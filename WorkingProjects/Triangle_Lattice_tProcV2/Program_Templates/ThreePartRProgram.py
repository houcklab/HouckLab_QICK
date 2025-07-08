from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.RampHelpers import generate_ramp
from WorkingProjects.Triangle_Lattice_tProcV2.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils_NEW as FF
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.rotate_SS_data import *
from WorkingProjects.Triangle_Lattice_tProcV2.Basic_Experiments_Programs.AveragerProgramFF import RAveragerProgramFF
import scipy

# get waveforms of less than 3 clock cycles by padding the first 3 cycles of the arbitrary pulse
# with FFPulses.
THREE = 3
# I declare this as a variable so that someone reading the code knows the purpose of the 3.

class ThreePartRProgram(RAveragerProgramFF):
    def initialize(self):

        cfg = self.cfg
        # print(cfg)
        if cfg["start"]+cfg["step"]*cfg["expts"] >= 4096 - THREE:
            raise ValueError("Not enough waveform memory, must be less than 4096 - 3 cycles")

        FF.FFDefinitions(self)
        # Pages and "mode" registers for each fast flux generator
        self.ff_rps = [self.ch_page(ch)  for ch in self.FFChannels]
        self.r_mode = [self.sreg(ch, "mode") for ch in self.FFChannels]

        # Register to store waveform length
        self.r_length = 3
        for page in self.ff_rps:
            self.regwi(page, self.r_length, cfg["start"] + THREE)

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
                         ro_ch=cfg["ro_chs"][0])
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and down-conversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"],
                                 length=self.us2cycles(cfg["res_length"]))

        self.sync_all(200, gen_t0=self.gen_t0)

    def body(self):
        # 1: FFPulses
        self.synci(200)
        self.FFPulses(self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01, t_start=0)
        for i in range(len(self.cfg["qubit_gains"])):
            gain_ = self.cfg["qubit_gains"][i]
            freq_ = self.freq2reg(self.cfg["qubit_freqs"][i], gen_ch=self.cfg["qubit_ch"])
            time_ = self.us2cycles(1) if i==0 else 'auto'

            self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=freq_, phase=0,
                                 gain=gain_, waveform="qubit", t=time_)
        # 2: FFExpt
        self.synci(self.us2cycles(len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01))

        # To get wait times of < 3 clock cycles
        print(self.cfg["IDataArray"])
        padded_IDataArray = [np.pad(arr, (THREE*16, 0), constant_values=prev_gain) for arr, prev_gain in zip(self.cfg["IDataArray"], self.FFPulse)]
        FF.FFPulses_directSET_REGS(self, self.FFExpts, 16*(THREE + self.cfg["start"] + self.cfg["step"] * self.cfg["expts"]),
                                   self.FFPulse,
                                   IQPulseArray= padded_IDataArray)
        # Update pulse length, which is stored in the last 16 bits of the generator's "mode" register
        for ff_page, mode_reg in zip(self.ff_rps, self.r_mode):
            # self.bitwi(ff_page, mode_reg, mode_reg, '&', 0b111_1111_1111_1111_0000_0000_0000_0000)
            self.bitwi(ff_page, mode_reg, mode_reg, '|', 0b0_1111_1111_1111)
            self.bitwi(ff_page, mode_reg, mode_reg, '^', 0b0_1111_1111_1111)
            self.math(ff_page, mode_reg, mode_reg, '+', self.r_length)

        FF.FFPulses_directPULSE(self, t_start=0)
        self.sync(self.ff_rps[0], self.r_length)

        # 3: FFReadouts
        # self.FFPulses(self.FFExpts + 2*(self.FFReadouts - self.FFExpts), 2.32515/1e3*3) # Overshoot to freeze dynamics
        FF.FFPulses(self, self.FFReadouts, self.cfg["res_length"], t_start=0)

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_delay=self.us2cycles(self.cfg["adc_trig_delay"]), t=0,
                     wait=False,
                     syncdelay=None)

        # Don't use sync_all from this point forward in order to avoid pulse timing weirdness
        measure_time_us = max(self.cfg["res_length"], self.cfg["adc_trig_delay"]+self.cfg["readout_length"])
        self.waiti(0, self.us2cycles(measure_time_us, gen_ch=self.cfg["res_ch"]))
        self.synci(self.us2cycles(measure_time_us + 10, gen_ch=self.cfg["res_ch"]))

        # End: invert FF pulses to ensure pulses integrate to 0
        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"], t_start=0)
        self.synci(self.us2cycles(self.cfg["res_length"], gen_ch=self.cfg["res_ch"]))
        # self.FFPulses(-self.FFExpts - 2*(self.FFReadouts - self.FFExpts), 2.32515/1e3*3)
        inverted_IDataArray = [-1 * np.flip(arr) for arr in padded_IDataArray]
        FF.FFPulses_directSET_REGS(self, self.FFExpts,
                                   16 * (THREE + self.cfg["start"] + self.cfg["step"] * self.cfg["expts"]),
                                   self.FFPulse,
                                   IQPulseArray=inverted_IDataArray)
        for ff_page, mode_reg in zip(self.ff_rps, self.r_mode):
            # self.bitwi(ff_page, mode_reg, mode_reg, '&', 0b111_1111_1111_1111_0000_0000_0000_0000)
            self.bitwi(ff_page, mode_reg, mode_reg, '|', 0b0_1111_1111_1111)
            self.bitwi(ff_page, mode_reg, mode_reg, '^', 0b0_1111_1111_1111)
            self.math(ff_page, mode_reg, mode_reg, '+', self.r_length)


        FF.FFPulses_directPULSE(self, t_start=0)
        self.sync(self.ff_rps[0], self.r_length)
        self.FFPulses(-1 * self.FFPulse, len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01, t_start=0)
        self.synci(self.us2cycles(len(self.cfg["qubit_gains"]) * self.cfg["sigma"] * 4 + 1.01))
        self.synci(self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        for ff_page in set(self.ff_rps): # set() to avoid double adding for generators sharing a page
            self.mathi(ff_page, self.r_length, self.r_length, '+', self.cfg["step"])