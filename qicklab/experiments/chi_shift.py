import time

import matplotlib.pyplot as plt
import numpy as np
from qick import AveragerProgram
from tqdm.notebook import tqdm

from qicklab.core.experiment import ExperimentClass


class ChiProgram(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        cfg["rounds"] = 1
        self.declare_gen(
            ch=cfg["res_ch"], nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0]
        )
        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["readout_length"]),
                freq=cfg["pulse_freq"],
                gen_ch=cfg["res_ch"],
            )

        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])

        self.freq_01 = self.freq2reg(cfg["qubit_freq"], gen_ch=qubit_ch)
        freq = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])

        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=freq,
            phase=0,
            gain=cfg["pulse_gain"],
            length=self.us2cycles(cfg["length"]),
        )

        # 4-sigma envelope: docs/concepts/timing_and_units.md#pulse-envelopes
        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
        self.add_gauss(
            ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_lenth
        )
        if cfg["flattop_length"] != None:
            flattop_length = self.us2cycles(self.cfg["flattop_length"], gen_ch=self.cfg["qubit_ch"])
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="flat_top",
                freq=self.freq_01,
                phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]),
                gain=cfg["pi_gain"],
                waveform="qubit",
                length=flattop_length,
            )
            self.pulse_qubit_lenth += flattop_length
        else:
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="arb",
                freq=self.freq_01,
                phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]),
                gain=cfg["pi_gain"],
                waveform="qubit",
            )

    def body(self):
        self.sync_all(self.us2cycles(0.05))
        if self.cfg["pulse_01"]:
            self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(0.1))

        self.sync_all(self.us2cycles(0.05))
        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=[0],
            adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=self.us2cycles(10),
        )

        self.sync_all(self.us2cycles(self.cfg["cav_relax_delay"]))
        if self.cfg["pulse_01"]:
            self.sync_all(self.us2cycles(self.cfg["relax_delay"] - self.cfg["cav_relax_delay"]))


class ChiShift(ExperimentClass):
    """Dispersive shift: transmission sweep without and with a pi pulse; chi from the two
    transmission minima. Half-open grid around pulse_freq + cavity_shift
    (docs/experiments/chi_shift.md)."""

    def __init__(
        self,
        soc=None,
        soccfg=None,
        path="",
        outerFolder="",
        prefix="data",
        cfg=None,
        config_file=None,
        progress=None,
    ):
        super().__init__(
            soc=soc,
            soccfg=soccfg,
            path=path,
            outerFolder=outerFolder,
            prefix=prefix,
            cfg=cfg,
            config_file=config_file,
            progress=progress,
        )

    def acquire(self, progress=False, debug=False):
        expt_cfg = {
            "center": self.cfg["pulse_freq"] + self.cfg["cavity_shift"],
            "span": self.cfg["TransSpan"],
            "expts": self.cfg["TransNumPoints"],
        }
        expt_cfg["step"] = 2 * expt_cfg["span"] / expt_cfg["expts"]
        expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
        fpts = expt_cfg["start"] + expt_cfg["step"] * np.arange(expt_cfg["expts"])
        results_ground = []
        results_01 = []

        start = time.time()
        for f in tqdm(fpts, position=0, disable=True):
            self.cfg["pulse_freq"] = f

            self.cfg["pulse_01"] = False
            prog = ChiProgram(self.soccfg, self.cfg)
            results_ground.append(prog.acquire(self.soc, load_pulses=True))

            self.cfg["pulse_01"] = True
            prog = ChiProgram(self.soccfg, self.cfg)
            results_01.append(prog.acquire(self.soc, load_pulses=True))

        print(f"Time: {time.time() - start}")
        results_ground = np.transpose(results_ground)
        results_01 = np.transpose(results_01)

        data = {
            "config": self.cfg,
            "data": {"results_ground": results_ground, "results_01": results_01, "fpts": fpts},
        }
        self.data = data
        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data

        x_pts = (data["data"]["fpts"] + self.cfg["cavity_LO"] / 1e6) / 1e3  # GHz

        sig = data["data"]["results_ground"][0][0][0] + 1j * data["data"]["results_ground"][0][0][1]
        avgamp_ground = np.abs(sig)

        sig = data["data"]["results_01"][0][0][0] + 1j * data["data"]["results_01"][0][0][1]
        avgamp_01 = np.abs(sig)

        idx_ground = np.argmin(avgamp_ground)
        idx_01 = np.argmin(avgamp_01)

        f_ground = x_pts[idx_ground]  # GHz
        f_01 = x_pts[idx_01]  # GHz

        chi_shift_ghz = f_01 - f_ground
        chi_shift_mhz = chi_shift_ghz * 1e3

        print(f"Ground peak frequency: {f_ground:.9f} GHz")
        print(f"|1> peak frequency:    {f_01:.9f} GHz")
        print(f"Chi shift:             {chi_shift_ghz:.9f} GHz = {chi_shift_mhz:.6f} MHz")

        plt.figure(figNum + 1)
        plt.plot(x_pts, avgamp_ground, label="Ground", color="red", ls="-", marker=".")
        plt.plot(x_pts, avgamp_01, label="01", color="blue", ls="-", marker=".")

        plt.axvline(
            f_ground, color="red", ls="--", alpha=0.7, label=f"Ground peak = {f_ground:.6f} GHz"
        )
        plt.axvline(f_01, color="blue", ls="--", alpha=0.7, label=f"01 peak = {f_01:.6f} GHz")

        plt.ylabel("a.u.")
        plt.xlabel("Cavity Frequency (GHz)")
        plt.legend()
        plt.title(self.titlename + f"\nChi shift = {chi_shift_mhz:.3f} MHz")

        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)

    def save_data(self, data=None):
        print(f"Saving {self.fname}")
        super().save_data(data=data["data"])
