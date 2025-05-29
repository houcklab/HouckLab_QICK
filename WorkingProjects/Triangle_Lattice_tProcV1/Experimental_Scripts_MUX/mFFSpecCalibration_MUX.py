from jupyterlab.labextensions import list_flags
from qick import *
import matplotlib.pyplot as plt
from WorkingProjects.Triangle_Lattice_tProcV1.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import datetime
import time
from scipy.signal import savgol_filter
import WorkingProjects.Triangle_Lattice_tProcV1.Helpers.FF_utils as FF
from WorkingProjects.Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mTransmissionFFMUX import CavitySpecFFProg
from WorkingProjects.Triangle_Lattice_tProcV1.Basic_Experiments_Programs.AveragerProgramFF import RAveragerProgramFF
from WorkingProjects.Triangle_Lattice_tProcV1.Basic_Experiments_Programs.SweepExperimentR1D import SweepExperimentR1D
import numpy as np

class FFSpecCalibrationProgram(RAveragerProgramFF):
    def initialize(self):
        cfg = self.cfg

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
        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch

        FF.FFDefinitions(self)

        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])

        self.qubit_length_us = cfg["sigma"] * 6
        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_length = self.us2cycles(self.qubit_length_us, gen_ch=self.cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_length)
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_start,
                                 phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["Gauss_gain"],
                                 waveform="qubit")
        # print(self.pulse_qubit_length)
        # print(cfg["mixer_freq"], cfg["pulse_freqs"], cfg["pulse_gains"], cfg["length"], self.cfg["adc_trig_offset"])

    def body(self):
        # print(self.FFRamp, self.FFExpts, self.FFReadouts, self.delay)
        self.sync_all(50, gen_t0=self.gen_t0)
        self.FFPulses(self.FFRamp, 2.0 + 0.00232*16) # used to be 2.02
        # self.FFPulses(self.FFExpts,self.cycles2us(self.delay) + 0.5)
        self.FFPulses_direct(list_of_gains=self.FFExpts, length_dt=(self.cfg['delay'] + self.pulse_qubit_length + 200) * 16,
                             previous_gains=self.FFRamp, IQPulseArray=self.cfg["IDataArray"])
        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(2.0, gen_ch=self.cfg["qubit_ch"]) + self.cfg['delay'])  # play probe pulse
        self.sync_all(gen_t0=self.gen_t0)
        # self.sync_all()
        self.FFPulses(self.FFReadouts, self.cfg["res_length"])
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))

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