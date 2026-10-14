import time

import matplotlib.pyplot as plt
import numpy as np
from qick import AveragerProgram, RAveragerProgram
from tqdm.notebook import tqdm

from qicklab.analysis.fitting import cos_func, fit_rabi_cosine
from qicklab.analysis.iq import min_q_range_phase
from qicklab.core.experiment import ExperimentClass


def iq_rotation_angle(signal_trace):
    """Angle (rad) of the principal (maximum-variance) axis of an IQ trace; rotating by
    -angle puts the Rabi oscillation in I. Not a cable-winding correction:
    docs/concepts/iq_conventions.md section 3."""
    i = np.real(signal_trace).astype(float)
    q = np.imag(signal_trace).astype(float)
    i = i - np.mean(i)
    q = q - np.mean(q)
    return 0.5 * np.arctan2(2.0 * np.mean(i * q), np.mean(i * i) - np.mean(q * q))


class AmplitudeRabiFFProg(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        for ch in [0, 1]:
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["readout_length"]),
                freq=cfg["pulse_freq"],
                gen_ch=cfg["res_ch"],
            )

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        # 4-sigma envelope: docs/concepts/timing_and_units.md#pulse-envelopes
        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
        print(self.pulse_sigma, self.pulse_qubit_lenth)

        if cfg["flattop_length"] != None:
            print("yes!")
            flattop_length = self.us2cycles(self.cfg["flattop_length"], gen_ch=self.cfg["qubit_ch"])
            print(flattop_length)
            self.add_gauss(
                ch=cfg["qubit_ch"],
                name="qubit",
                sigma=self.pulse_sigma,
                length=self.pulse_qubit_lenth,
            )
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="flat_top",
                freq=f_ge,
                phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]),
                gain=cfg["start"],
                waveform="qubit",
                length=flattop_length,
            )  # flat segment ignores the swept gain: docs/experiments/amplitude_rabi.md
            self.pulse_qubit_lenth += flattop_length
        else:
            self.add_gauss(
                ch=cfg["qubit_ch"],
                name="qubit",
                sigma=self.pulse_sigma,
                length=self.pulse_qubit_lenth,
            )

            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="arb",
                freq=f_ge,
                phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]),
                gain=cfg["start"],
                waveform="qubit",
            )

        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=f_res,
            phase=cfg["res_phase"],
            gain=cfg["pulse_gain"],
            length=self.us2cycles(cfg["length"]),
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
            t=self.us2cycles(1 + self.cfg["trig_delay"] - self.cfg["trig_buffer_start"]),
            width=self.trig_length,
        )

        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(1))
        self.sync_all(self.us2cycles(0.05))

        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=[0, 1],
            adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=self.us2cycles(10),
        )

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, "+", self.cfg["step"])


class AmplitudeRabiFF(ExperimentClass):
    """Amplitude Rabi with a register-swept gain (start/step/expts), principal-axis IQ
    rotation and optional cosine fit. Use the Gaussian envelope here: the flat-top branch
    ignores the swept gain, so flat-top Rabi is AmplitudeRabiFF_N (docs/experiments/amplitude_rabi.md)."""

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
        prog = AmplitudeRabiFFProg(self.soccfg, self.cfg)

        x_pts, avgi, avgq = prog.acquire(
            self.soc,
            threshold=None,
            angle=None,
            load_pulses=True,
            readouts_per_experiment=1,
            save_experiments=None,
            start_src="internal",
            progress=False,
        )

        avgi = np.asarray(avgi, dtype=np.float64)
        avgq = np.asarray(avgq, dtype=np.float64)
        x_pts = np.asarray(x_pts, dtype=np.float64)

        phase = (
            2 * np.pi * self.cfg["cavity_winding_freq"] * self.cfg["pulse_freq"]
            + self.cfg["cavity_winding_offset"]
        )
        signal = (avgi + 1j * avgq) * np.exp(1j * phase)

        # Principal-axis rotation on top of the winding phase (axis estimated over both ADCs).
        rot_angle = iq_rotation_angle(np.ravel(signal))
        signal = signal * np.exp(-1j * rot_angle)
        print(f"[AmplitudeRabiFF] IQ rotation angle = {np.rad2deg(rot_angle):.2f} deg")

        avgi = signal.real
        avgq = signal.imag

        data = {
            "config": self.cfg,
            "data": {"x_pts": x_pts, "avgi": avgi, "avgq": avgq, "iq_rotation_rad": rot_angle},
        }
        self.data = data

        return data

    def display(self, data=None, plotDisp=True, figNum=1, fit=False, **kwargs):
        if data is None:
            data = self.data

        x_pts = np.asarray(data["data"]["x_pts"], dtype=float).ravel()
        avgi = np.asarray(data["data"]["avgi"][0][0], dtype=float).ravel()
        avgq = np.asarray(data["data"]["avgq"][0][0], dtype=float).ravel()

        fit_i = None
        fit_q = None

        print("Raw extrema:")
        print("  Max I gain:", x_pts[np.argmax(avgi)], " Max Q gain:", x_pts[np.argmax(avgq)])
        print("  Min I gain:", x_pts[np.argmin(avgi)], " Min Q gain:", x_pts[np.argmin(avgq)])

        if fit:
            try:
                fit_i = fit_rabi_cosine(x_pts, avgi)
                data["data"]["fit_i_popt"] = np.asarray(fit_i["popt"])
                data["data"]["fit_i_pi_gain"] = np.asarray(fit_i["pi_gain"])
                print(f"I fit: P={fit_i['P']:.3f}, pi={fit_i['pi_gain']:.3f}")
            except Exception as err:
                print(f"I fit failed: {err}")

            try:
                fit_q = fit_rabi_cosine(x_pts, avgq)
                data["data"]["fit_q_popt"] = np.asarray(fit_q["popt"])
                data["data"]["fit_q_pi_gain"] = np.asarray(fit_q["pi_gain"])
                print(f"Q fit: P={fit_q['P']:.3f}, pi={fit_q['pi_gain']:.3f}")
            except Exception as err:
                print(f"Q fit failed: {err}")

        self.fit_i = fit_i
        self.fit_q = fit_q
        self.data = data

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig = plt.figure(figNum)
        plt.plot(x_pts, avgi, "o", color="orange", label="I data")
        plt.plot(x_pts, avgq, "o", color="blue", label="Q data")

        if fit_i is not None:
            if "x_fit_dense" not in fit_i:
                fit_i["x_fit_dense"] = np.linspace(np.min(x_pts), np.max(x_pts), 5000)
                fit_i["y_fit_dense"] = cos_func(fit_i["x_fit_dense"], *fit_i["popt"])

            plt.plot(
                fit_i["x_fit_dense"],
                fit_i["y_fit_dense"],
                "-",
                color="orange",
                label=f"I fit, pi={fit_i['pi_gain']:.1f}",
            )
            plt.axvline(fit_i["pi_gain"], linestyle="--", color="orange", alpha=0.7)

        if fit_q is not None:
            if "x_fit_dense" not in fit_q:
                fit_q["x_fit_dense"] = np.linspace(np.min(x_pts), np.max(x_pts), 5000)
                fit_q["y_fit_dense"] = cos_func(fit_q["x_fit_dense"], *fit_q["popt"])

            plt.plot(
                fit_q["x_fit_dense"],
                fit_q["y_fit_dense"],
                "-",
                color="blue",
                label=f"Q fit, pi={fit_q['pi_gain']:.1f}",
            )
            plt.axvline(fit_q["pi_gain"], linestyle="--", color="blue", alpha=0.7)

        plt.ylabel("a.u.")
        plt.xlabel("qubit gain")
        plt.legend()
        plt.title(self.titlename)
        plt.tight_layout()
        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f"Saving {self.fname}")
        super().save_data(data=data["data"])


class AmplitudeRabiPointProg(AveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        for ch in [0, 1]:
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["readout_length"]),
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
        if cfg["flattop_length"] != None:
            flattop_length = self.us2cycles(self.cfg["flattop_length"], gen_ch=self.cfg["qubit_ch"])
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="flat_top",
                freq=f_ge,
                phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]),
                gain=cfg["qubit_gain"],
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
                gain=cfg["qubit_gain"],
                waveform="qubit",
            )

        trig_length = cfg["trig_buffer_start"] + cfg["trig_buffer_end"] + cfg["sigma"] * 4
        if cfg["flattop_length"] != None:
            trig_length += self.cfg["flattop_length"]
        self.trig_length = self.us2cycles(trig_length)

        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=f_res,
            phase=cfg["res_phase"],
            gain=cfg["pulse_gain"],
            length=self.us2cycles(cfg["length"]),
        )

        self.sync_all(self.us2cycles(0.05))

    def body(self):
        self.sync_all()
        self.trigger(
            pins=[0],
            t=self.us2cycles(1 + self.cfg["trig_delay"] - self.cfg["trig_buffer_start"]),
            width=self.trig_length,
        )

        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(1))
        self.sync_all(self.us2cycles(0.05))

        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=[0, 1],
            adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=self.us2cycles(10),
        )

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))


class AmplitudeRabiFF_N(ExperimentClass):
    """Amplitude Rabi as a Python loop over gains (one program per gain); needed for
    flat-top pulses (docs/experiments/amplitude_rabi.md)."""

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
        self.cfg["reps"] *= self.cfg["rounds"]
        self.cfg["rounds"] = 1
        gainpts = np.linspace(
            self.cfg["gain_start"], self.cfg["gain_end"], self.cfg["gainNumPoints"]
        )
        results = []
        start = time.time()
        for g in tqdm(gainpts, position=0, disable=True):
            self.cfg["qubit_gain"] = int(g)
            prog = AmplitudeRabiPointProg(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
        print(f"Time: {time.time() - start}")
        results = np.transpose(results)
        signal = (results[0][0][0] + 1j * results[0][0][1]) * np.exp(
            1j
            * (
                2 * np.pi * self.cfg["cavity_winding_freq"] * self.cfg["pulse_freq"]
                + self.cfg["cavity_winding_offset"]
            )
        )

        avgi = [[signal.real]]
        avgq = [[signal.imag]]
        data = {"config": self.cfg, "data": {"x_pts": gainpts, "avgi": avgi, "avgq": avgq}}
        self.data = data

        return data

    def display(self, data=None, plotDisp=False, figNum=1, fit=True, rotate=True, **kwargs):
        if data is None:
            data = self.data

        x_pts = np.asarray(data["data"]["x_pts"], dtype=float)
        avgi = np.asarray(data["data"]["avgi"][0][0], dtype=float)
        avgq = np.asarray(data["data"]["avgq"][0][0], dtype=float)

        # Puts the Rabi contrast in I (docs/concepts/iq_conventions.md section 3).
        if rotate:
            rot_phase = min_q_range_phase(avgi, avgq, 500)
            rotated = (avgi + 1j * avgq) * np.exp(1j * rot_phase)
            avgi, avgq = rotated.real, rotated.imag
            self.rotation_phase = rot_phase
            print(f"IQ rotation phase = {rot_phase:.4f} rad")

        x_min, x_max = float(np.min(x_pts)), float(np.max(x_pts))

        fit_i = fit_q = None
        if fit:
            fit_i = fit_rabi_cosine(x_pts, avgi)
            fit_q = fit_rabi_cosine(x_pts, avgq)

            print("Raw extrema:")
            print("  Max I gain:", x_pts[np.argmax(avgi)], " Max Q gain:", x_pts[np.argmax(avgq)])
            print("  Min I gain:", x_pts[np.argmin(avgi)], " Min Q gain:", x_pts[np.argmin(avgq)])

            print("\nCosine fit results:")
            print(f"  I fit period P       = {fit_i['P']:.3f} ± {fit_i['dP']:.3f}")
            print(f"  I fit phase phi      = {fit_i['phi']:.3f} ± {fit_i['dphi']:.3f}")
            print(f"  I-derived pi gain    = {fit_i['pi_gain']:.3f}")

            print(f"  Q fit period P       = {fit_q['P']:.3f} ± {fit_q['dP']:.3f}")
            print(f"  Q fit phase phi      = {fit_q['phi']:.3f} ± {fit_q['dphi']:.3f}")
            print(f"  Q-derived pi gain    = {fit_q['pi_gain']:.3f}")

        self.fit_i = fit_i
        self.fit_q = fit_q

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig = plt.figure(figNum)
        plt.plot(x_pts, avgi, "o", label="I data", color="orange")
        plt.plot(x_pts, avgq, "o", label="Q data", color="blue")

        if fit:
            plt.plot(
                x_pts, fit_i["yfit"], "-", label=f"I fit, pi={fit_i['pi_gain']:.1f}", color="orange"
            )
            plt.plot(
                x_pts, fit_q["yfit"], "-", label=f"Q fit, pi={fit_q['pi_gain']:.1f}", color="blue"
            )

            # A failed fit has a runaway period: hide out-of-range markers (amplitude_rabi.md).
            for f, color, lbl in ((fit_i, "orange", "I pi gain"), (fit_q, "blue", "Q pi gain")):
                if x_min <= f["pi_gain"] <= x_max:
                    plt.axvline(f["pi_gain"], linestyle="--", color=color, alpha=0.7, label=lbl)
                else:
                    print(
                        f"  [warn] {lbl} = {f['pi_gain']:.3g} outside swept range "
                        f"[{x_min:.0f}, {x_max:.0f}] -- fit likely failed, marker hidden."
                    )

        plt.xlim(x_min, x_max)
        plt.ylabel("a.u.")
        plt.xlabel("qubit gain")
        plt.legend()
        plt.title(self.titlename)
        plt.tight_layout()
        plt.savefig(self.iname)

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
