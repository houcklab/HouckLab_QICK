from qick.asm_v2 import QickSweep1D

import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF

import numpy as np

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.SweepExperiment2D_plots import SweepExperiment2D_plots


class FFSpecCalibrationProgram(FFAveragerProgramV2):
    def _initialize(self, cfg):
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains=cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=cfg["readout_lengths"][iCh],
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.add_pulse(ch=cfg["res_ch"], name="res_drive", style="const", mask=cfg["ro_chs"],
                       length=cfg["res_length"])
        # Qubit configuration
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"], mixer_freq=cfg["qubit_mixer_freq"])


        FF.FFDefinitions(self)

        self.add_loop("qubit_freq_loop", self.cfg["SpecNumPoints"])
        qubit_freq_sweep = QickSweep1D("qubit_freq_loop",
                                       start=cfg["SpecStart"],
                                       end=cfg["SpecEnd"])

        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=4 * cfg["sigma"])
        self.add_pulse(ch=cfg["qubit_ch"], name='qubit_drive', style="arb", envelope="qubit",
                       freq=qubit_freq_sweep, phase=90, gain=cfg["Gauss_gain"] / 32766)
        self.qubit_length_us = cfg["sigma"] * 4
        self.qubit_length_cycles = self.us2cycles(self.qubit_length_us)

    def _body(self, cfg):
        self.FFPulses(self.FFExpts, 2.0 + self.cycles2us(8)) # used to be 2.02
        # self.FFPulses(self.FFExpts,self.cycles2us(self.delay) + 0.5)
        self.FFPulses_direct(list_of_gains=self.FFBS, length_dt=(cfg['delay'] + self.qubit_length_cycles + 8 + 22) * 16,
                             previous_gains=self.FFExpts, IQPulseArray=cfg["IDataArray"])
        self.pulse(ch=cfg["qubit_ch"], name='qubit_drive', t=2.0 + self.cycles2us(cfg['delay']))  # play probe pulse
        self.delay_auto()

        self.FFPulses(self.FFReadouts, cfg["res_length"])
        for ro_ch, adc_trig_delay in zip(cfg["ro_chs"], cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0],t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        # self.FFPulses(-1 * self.FFRamp, 2.05)
        self.FFPulses(-1 * self.FFExpts, 2.0 + self.cycles2us(8))
        self.FFPulses(-1 * self.FFBS, self.cycles2us(cfg['delay']+self.qubit_length_cycles+8+22))
        self.FFPulses(-1 * self.FFReadouts, cfg["res_length"])
        self.delay_auto()

    def loop_pts(self):
        return (self.get_pulse_param("qubit_drive", "freq", as_array=True),)

class FFSpecCalibrationMUX(SweepExperiment2D_plots):
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
        self.x_name = 'qubit_freq_loop'
        self.z_value = 'contrast'  # contrast or population
        self.ylabel = 'Delay time (4.65 ns)'  # for plotting
        self.xlabel = 'Spec frequency (MHz)'  # for plotting

        self.cfg |= {
            "step": (self.cfg["SpecEnd"] - self.cfg["SpecStart"]) / (self.cfg["SpecNumPoints"] - 1),
            "start": self.cfg["SpecStart"],
            "expts": self.cfg["SpecNumPoints"]
        }