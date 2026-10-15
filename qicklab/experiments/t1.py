import traceback

import matplotlib.pyplot as plt
import numpy as np
from qick import RAveragerProgram

from qicklab.analysis.fitting import exp_decay_fit_fields, fit_exp_decay
from qicklab.analysis.iq import decay_axis_phase
from qicklab.core.experiment import ExperimentClass
from qicklab.core.readout import cover_readout_window
from qicklab.core.schedule import realised_wait_axis_us


class T1Program(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_wait = 3
        self.regwi(self.q_rp, self.r_wait, cfg["start"])

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        cover_readout_window(self, cfg)
        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.readout_window_cycles[ch],
                freq=cfg["pulse_freq"],
                gen_ch=cfg["res_ch"],
            )

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        # 4-sigma envelope: docs/concepts/timing_and_units.md#pulse-envelopes
        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
        self.add_gauss(
            ch=cfg["qubit_ch"], name="qubit", sigma=self.pulse_sigma, length=self.pulse_qubit_lenth
        )

        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=f_res,
            phase=cfg["res_phase"],
            gain=cfg["pulse_gain"],
            length=self.readout_tone_cycles,
        )

        if cfg["flattop_length"] != None:
            flattop_length = self.us2cycles(self.cfg["flattop_length"], gen_ch=self.cfg["qubit_ch"])
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="flat_top",
                freq=f_ge,
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
                freq=f_ge,
                phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]),
                gain=cfg["pi_gain"],
                waveform="qubit",
            )

        trig_length = cfg["trig_buffer_start"] + cfg["trig_buffer_end"] + cfg["sigma"] * 4

        if cfg["flattop_length"] != None:
            trig_length += self.cfg["flattop_length"]
        self.trig_length = self.us2cycles(trig_length)

        self.sync_all(self.us2cycles(0.05))

    def body(self):
        self.sync_all()
        self.trigger(
            pins=[0],
            t=self.us2cycles(0.01 + self.cfg["trig_delay"] - self.cfg["trig_buffer_start"]),
            width=self.trig_length,
        )
        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(0.01))
        self.sync_all()
        self.sync(self.q_rp, self.r_wait)

        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=self.ro_chs,
            adc_trig_offset=self.adc_trig_offset_cycles,
            wait=True,
            syncdelay=self.us2cycles(self.cfg["relax_delay"]),
        )

    def update(self):
        self.mathi(self.q_rp, self.r_wait, self.r_wait, "+", self.us2cycles(self.cfg["step"]))


class T1FF(ExperimentClass):
    """T1: pi pulse, register-swept wait (from the pulse end), readout; principal-axis IQ
    rotation (excited end up) and a single-exponential fit (docs/experiments/t1.md)."""

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
        prog = T1Program(self.soccfg, self.cfg)

        _, avgi, avgq = prog.acquire(
            self.soc,
            threshold=None,
            angle=None,
            load_pulses=True,
            readouts_per_experiment=1,
            save_experiments=None,
            start_src="internal",
            progress=False,
        )
        # realised register-swept wait, not start + i*step:
        # docs/concepts/timing_and_units.md#register-swept-wait-axis
        x_pts = realised_wait_axis_us(
            self.soccfg, self.cfg["start"], self.cfg["step"], self.cfg["expts"]
        )

        avgi = np.asarray(avgi, dtype=np.float64)
        avgq = np.asarray(avgq, dtype=np.float64)

        signal = (avgi + 1j * avgq) * np.exp(
            1j
            * (
                2 * np.pi * self.cfg["cavity_winding_freq"] * self.cfg["pulse_freq"]
                + self.cfg["cavity_winding_offset"]
            )
        )
        avgi = signal.real
        avgq = signal.imag

        data = {
            "config": self.cfg,
            "data": {"x_pts": x_pts, "avgi": avgi, "avgq": avgq, "qfreq": self.cfg["f_ge"]},
        }
        if "rotation_angle" in self.cfg:
            data["rotation_angle"] = self.cfg["rotation_angle"]
        if "min_max" in self.cfg:
            data["min_max"] = self.cfg["min_max"]
        self.data = data

        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data["data"]["x_pts"]
        avgi = data["data"]["avgi"][0][0]
        avgq = data["data"]["avgq"][0][0]

        fixed_rotation = "rotation_angle" in self.cfg
        if not fixed_rotation:
            rotation_angle = decay_axis_phase(avgi, avgq)
        else:
            rotation_angle = self.cfg["rotation_angle"]
        rotated_IQ = (avgi + 1j * avgq) * np.exp(1j * rotation_angle)

        avgi = rotated_IQ.real
        avgq = rotated_IQ.imag

        # Fixed g/e levels only mean something on the fixed rotation they were measured with.
        normalise = fixed_rotation and "min_max" in data
        if normalise:
            ground = data["min_max"][0]
            excited = data["min_max"][-1]
            avgi = (avgi - ground) / (excited - ground)

        # Guarded: a failed fit leaves self.fit = {'ok': False, 'error': ...} and the data plot.
        try:
            fit = fit_exp_decay(x_pts, avgi)
        except Exception as e:
            traceback.print_exc()
            fit = {"ok": False, "error": repr(e)}
        self.fit = fit
        # Saved by save_data (finish() displays first): docs/experiments/t1.md#outputs
        data["data"].update(exp_decay_fit_fields(fit, "t1"))
        data["data"]["t1_fit_rotation_rad"] = float(rotation_angle)
        if not fit["ok"]:
            print(f"T1 fit not reliable: {fit['error']}")

        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig = plt.figure(figNum)
        plt.plot(x_pts, avgi, "o", label="i", color="orange")
        if fit["ok"]:
            plt.plot(x_pts, fit["yfit"], "-", label="fit", color="black")
        elif "yfit" in fit and np.all(np.isfinite(fit["yfit"])):
            plt.plot(x_pts, fit["yfit"], "--", label="fit (not reliable)", color="gray")
        plt.ylabel("a.u.")
        if normalise:
            plt.ylabel("Population")
        plt.xlabel("Wait time (us)")
        plt.legend()
        plt.title(
            "Qubit: "
            + str(self.cfg["Qubit_number"])
            + " ; "
            + self.titlename
            + (
                "  ; T1 = "
                + str(round(fit["T"], 1))
                + r" $\pm$ "
                + str(round(fit["T_err"], 1))
                + "us"
                if fit["ok"]
                else "  ; T1 fit not reliable"
            )
        )
        plt.savefig(self.iname[:-4] + "I_Data.png")

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

        fig = plt.figure(figNum + 1)
        plt.plot(x_pts, avgq, "o", label="q")

        plt.ylabel("a.u.")
        plt.xlabel("Wait time (us)")
        plt.legend()
        plt.title(self.titlename)
        plt.savefig(self.iname[:-4] + "Q_Data.png")

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        new_name = self.fname[:-3] + "_Q" + str(self.cfg["Qubit_number"]) + ".h5"
        self.fname = new_name
        print(f"Saving {self.fname}")
        super().save_data(data=data["data"])
