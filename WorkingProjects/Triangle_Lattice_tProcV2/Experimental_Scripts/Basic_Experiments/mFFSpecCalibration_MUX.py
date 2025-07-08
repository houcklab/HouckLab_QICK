from jupyterlab.labextensions import list_flags
from qick import *
import matplotlib.pyplot as plt
from qick.asm_v2 import QickSweep1D

from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import datetime
import time
from scipy.signal import savgol_filter
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts_MUX.mTransmissionFFMUX import CavitySpecFFProg
from WorkingProjects.Triangle_Lattice_tProcV2.Basic_Experiments_Programs.AveragerProgramFF import RAveragerProgramFF
from WorkingProjects.Triangle_Lattice_tProcV2.Basic_Experiments_Programs.SweepExperimentR1D import SweepExperimentR1D
import numpy as np

from WorkingProjects.Triangle_Lattice_tProcV2.Program_Templates.AveragerProgramFF import FFAveragerProgramV2


class FFSpecCalibrationProgram(FFAveragerProgramV2):
    def _initialize(self, cfg):
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains=cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"],  # gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["res_length"], gen_ch=self.cfg["res_ch"]))
        # Qubit configuration
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"], mixer_freq=cfg["qubit_mixer_freq"])


        FF.FFDefinitions(self)

        self.add_loop("qubit_freq_loop", self.cfg["SpecNumPoints"])
        qubit_freq_sweep = QickSweep1D("qubit_freq_loop",
                                       start=cfg["qubit_freqs"][0] - cfg["SpecSpan"],
                                       end=cfg["qubit_freqs"][0] + cfg["SpecSpan"])

        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=4 * cfg["sigma"])
        self.add_pulse(ch=cfg["qubit_ch"], name='qubit_drive', style="arb", envelope="qubit",
                       freq=qubit_freq_sweep,
                       phase=90, gain=cfg["Gauss_gain"] / 32766.)
        self.qubit_length_us = cfg["sigma"] * 4

    def _body(self, cfg):
        self.FFPulses(self.FFRamp, 2.0 + 0.00232*16) # used to be 2.02
        # self.FFPulses(self.FFExpts,self.cycles2us(self.delay) + 0.5)
        self.FFPulses_direct(list_of_gains=self.FFExpts, length_dt=(self.cfg['delay'] + self.pulse_qubit_length + 200) * 16,
                             previous_gains=self.FFRamp, IQPulseArray=self.cfg["IDataArray"])
        self.pulse(ch=self.cfg["qubit_ch"], t=2.0 + self.cfg['delay'])  # play probe pulse
        self.delay_auto()

        self.FFPulses(self.FFReadouts, self.cfg["res_length"])
        self.trigger(ros=cfg["ro_chs"], pins=[0],
                     t=cfg["adc_trig_delay"])
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        # self.FFPulses(-1 * self.FFRamp, 2.05)
        self.FFPulses(-1 * self.FFRamp, 2.0 + 0.00232*16)
        self.FFPulses(-1 * self.FFExpts, self.cycles2us(self.cfg['delay']+200))
        self.FFPulses(-1 * self.FFReadouts, self.cfg["res_length"])
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]), gen_t0=self.gen_t0)

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)


class FFSpecCalibrationMUX(SweepExperimentR1D):
    """
    Spec experiment that finds the qubit frequency during and after a fast-flux pulse
    Notes:
        - this is set up such that it plots out the rows of data as it sweeps through delay times
    """

    def init_sweep_vars(self):
        self.Program = FFSpecCalibrationProgram
        self.y_key = 'delay'
        self.y_points = self.cfg["delay_start"] + self.cfg["delay_step"] * np.arange(self.cfg["delay_points"])
        # For the RAveragerProgram, you should define the cfg entries start, step, and stop too
        self.x_name = 'specfreqs'
        self.z_value = 'contrast'  # contrast or population
        self.ylabel = 'Delay time (2.32 ns)'  # for plotting
        self.xlabel = 'Spec frequency (MHz)'  # for plotting

        self.cfg |= {
            "step": (self.cfg["SpecEnd"] - self.cfg["SpecStart"]) / (self.cfg["SpecNumPoints"] - 1),
            "start": self.cfg["SpecStart"],
            "expts": self.cfg["SpecNumPoints"]
        }