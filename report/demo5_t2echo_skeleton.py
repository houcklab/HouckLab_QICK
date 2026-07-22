"""Hahn-echo (T2E) experiment — minimal skeleton."""
import numpy as np
import matplotlib.pyplot as plt
import scipy.optimize
from qick.asm_v2 import QickSweep1D

from WorkingProjects.triangle_lattice_quench.Experiment import ExperimentClass
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
import WorkingProjects.triangle_lattice_quench.Helpers.FF_utils as FF
from WorkingProjects.triangle_lattice_quench.Helpers.IQ_contrast import IQ_contrast


class EchoProg(FFAveragerProgramV2):
    def _initialize(self, cfg):
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"],
                         mixer_freq=cfg["qubit_mixer_freq"])
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["res_nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["res_freqs"], mux_gains=cfg["res_gains"],
                         ro_ch=cfg["ro_chs"][0])
        for ch, f in zip(cfg["ro_chs"], cfg["res_freqs"]):
            self.declare_readout(ch=ch, length=cfg["readout_lengths"][0],
                                 freq=f, gen_ch=cfg["res_ch"])
        self.add_pulse(ch=cfg["res_ch"], name="res_drive", style="const",
                       mask=cfg["ro_chs"], length=cfg["res_length"])

        FF.FFDefinitions(self)

        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"],
                       length=4 * cfg["sigma"])
        self.add_pulse(ch=cfg["qubit_ch"], name="pi2",
                       style="arb", envelope="qubit",
                       freq=cfg["qubit_freqs"][0], phase=0,
                       gain=cfg["qubit_gains"][0] / 2.0)
        self.add_pulse(ch=cfg["qubit_ch"], name="pi",
                       style="arb", envelope="qubit",
                       freq=cfg["qubit_freqs"][0], phase=0,
                       gain=cfg["qubit_gains"][0])
        # Inner sweep: half-delay tau (so total wait is 2*tau).
        self.add_loop("tau_loop", cfg["expts"])
        self.tau = QickSweep1D("tau_loop", start=0, end=cfg["stop_delay_us"] / 2)

    def _body(self, cfg):
        FF_pad = 10
        # Hold flux during the whole pulse train.
        total = self.qubit_length_us := cfg["sigma"] * 4
        self.FFPulses(self.FFPulse, 3 * total + FF_pad + cfg["stop_delay_us"])
        self.pulse(ch=cfg["qubit_ch"], name="pi2", t=FF_pad)
        self.delay(self.tau, tag="tau1")
        self.pulse(ch=cfg["qubit_ch"], name="pi", t="auto")
        self.delay(self.tau, tag="tau2")
        self.pulse(ch=cfg["qubit_ch"], name="pi2", t="auto")
        self.delay_auto()

        # Standard mux readout.
        self.FFPulses(self.FFReadouts, cfg["res_length"])
        for ro_ch, td in zip(cfg["ro_chs"], cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0], t=td)
        self.pulse(cfg["res_ch"], name="res_drive")
        self.wait_auto()
        self.delay_auto(10)
        # Compensation
        self.FFPulses(-1 * self.FFReadouts, cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, 3 * total + FF_pad + cfg["stop_delay_us"])


class T2EchoMUX(ExperimentClass):
    def acquire(self, progress=False):
        prog = EchoProg(self.soccfg, cfg=self.cfg, reps=self.cfg["reps"],
                        final_delay=self.cfg["relax_delay"], initial_delay=10.0)
        iq_list = prog.acquire(self.soc, load_envelopes=True,
                               rounds=self.cfg.get("rounds", 1), progress=progress)
        avgi, avgq = iq_list[0][0, :, 0], iq_list[0][0, :, 1]
        x_pts = 2 * prog.get_time_param("tau2", "t", as_array=True)
        self.data = {"config": self.cfg,
                     "data": {"x_pts": x_pts, "avgi": avgi, "avgq": avgq}}
        return self.data

    def display(self, data=None, plotDisp=False, ax=None, **kwargs):
        if data is None: data = self.data
        x_pts = data["data"]["x_pts"]
        c = IQ_contrast(data["data"]["avgi"], data["data"]["avgq"])
        if ax is None:
            fig, ax = plt.subplots(); own = True
        else:
            fig = ax.figure; own = False
        ax.plot(x_pts, c, "o-")
        ax.set_xlabel("Total wait (us)")
        ax.set_ylabel("IQ contrast")
        ax.set_title("Hahn echo")
        fig.savefig(self.iname[:-4] + ".png")
        if plotDisp and own:
            plt.show(block=False)

    def save_data(self, data=None):
        super().save_data(data=data["data"])
