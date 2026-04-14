
from scipy.optimize import curve_fit

from qick.asm_v2 import QickSweep1D

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import \
    QubitSpecSliceFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.IQ_contrast import IQ_contrast

class QubitSpecSlice2ndProg(FFAveragerProgramV2):
    def _initialize(self, cfg):
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"],
                         mixer_freq=cfg["qubit_mixer_freq"])  # Qubit

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"],
                         mux_gains= cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=cfg["readout_lengths"][iCh],
                                 freq=cfg["res_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.add_pulse(ch=cfg["res_ch"], name="res_drive", style="const", mask=cfg["ro_chs"],
                                 length=cfg["res_length"])


        ### Start fast flux
        FF.FFDefinitions(self)

        self.add_loop("qubit_freq_loop", self.cfg["SpecNumPoints"])
        qubit_freq_sweep = QickSweep1D("qubit_freq_loop",
                                    start=cfg["qubit_freqs"][1] - cfg["SpecSpan"],
                                    end=cfg["qubit_freqs"][1] + cfg["SpecSpan"])

        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=4 * cfg["sigma"])
        # add ge qubit pulse
        # self.add_gauss(ch=cfg["qubit_ch"], name="qubit01", sigma=cfg["sigma01"], length=4 * cfg["sigma01"])
        self.add_pulse(ch=cfg["qubit_ch"], name='qubit01_drive', style="arb", envelope="qubit",
                       freq=cfg['qubit_freqs'][0],
                       phase=90, gain=cfg["qubit_gains"][0])
        print(cfg["qubit_gains"])
        # add ef qubit pulse
        # self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=4 * cfg["sigma"])
        self.add_pulse(ch=cfg["qubit_ch"], name='qubit12_drive', style="arb", envelope="qubit",
                       freq=qubit_freq_sweep,
                       phase=90, gain=cfg["qubit_gains"][1])
        self.qubit_length_us = cfg["sigma"] * 4

        # print(self.FFPulse)


    def _body(self, cfg):
        # print(self.FFPulse)
        FF_pulse_delay = 1
        self.FFPulses(self.FFPulse, self.qubit_length_us + FF_pulse_delay + 0.05)
        self.pulse(ch=cfg["qubit_ch"], name="qubit01_drive", t = FF_pulse_delay)
        self.pulse(ch=cfg["qubit_ch"], name="qubit12_drive", t = FF_pulse_delay+4*cfg["sigma"])  # play probe pulse
        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.delay_auto()

        self.FFPulses(self.FFReadouts, cfg["res_length"])
        for ro_ch, adc_trig_delay in zip(self.cfg["ro_chs"], self.cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0],t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)  # us

        self.FFPulses(-1 * self.FFReadouts, cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, self.qubit_length_us + FF_pulse_delay + 0.05)

    def loop_pts(self):
        return (self.get_pulse_param("qubit12_drive", "freq", as_array=True) + self.cfg.get('qubit_LO', 0),)
# ====================================================== #

class QubitSpecSlice2nd(QubitSpecSliceFFMUX):
    """
    Basic spec experiment that takes a single slice of data
    """

    def acquire(self, progress=False, use_lorentzian=False):
        cfg = self.cfg

        prog = QubitSpecSlice2ndProg(self.soccfg, cfg=self.cfg, reps=self.cfg["reps"],
                                    final_delay=self.cfg["relax_delay"], initial_delay=10.0)
        iq_list = prog.acquire(self.soc, load_envelopes=True,
                               rounds=self.cfg.get('rounds', 1),
                               progress=progress)
        # print(np.array(iq_list).shape)

        # shape of results: [num of ROs, 1 (num triggers?), SpecNumPoints, 2 (I or Q)],
        #              e.g. [1, 1, 71, 2]
        avgi, avgq = iq_list[0][0, :, 0], iq_list[0][0, :, 1]
        x_pts = prog.get_pulse_param("qubit12_drive", "freq", as_array=True) + self.cfg.get('qubit_LO', 0)

        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        # Fit to find frequency
        self.analyze(data=data, use_lorentzian=use_lorentzian)

        return data
