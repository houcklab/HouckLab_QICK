import time

import matplotlib.pyplot as plt
import numpy as np
from qick import AveragerProgram, RAveragerProgram
from tqdm.notebook import tqdm

from qicklab.analysis.fitting import cos_func, fit_rabi_cosine
from qicklab.analysis.iq import principal_axis_angle
from qicklab.core.experiment import ExperimentClass
from qicklab.core.readout import cover_readout_window


def _print_fit_flags(label, fit):
    """Print the quality flags of a fit_rabi_cosine result (docs/experiments/amplitude_rabi.md)."""
    for flag in fit["flags"]:
        print(f"  [warn] {label} Rabi fit: {flag} -- check the pi gain by eye.")


# Below this principal/minor variance ratio the IQ axis is mostly noise (pure noise gives
# about 1.3-1.9 on 101 points and 1.7-4.3 on 21 points, median to 99th percentile).
_MIN_AXIS_CONTRAST_RATIO = 5.0


def iq_rotation_angle(signal_trace):
    """Angle (rad, in (-pi, pi]) to rotate one amplitude-Rabi IQ trace by (multiply by
    exp(-1j*angle)) so the oscillation lies in I and I increases from the start of the sweep
    (gain ~ 0, |g>) toward the pi pulse. The axis is the principal (maximum-variance) axis of the
    mean-subtracted trace (analysis.iq.principal_axis_angle), defined modulo pi; the sign is fixed
    by putting the mean of the first k = max(1, min(3, N // 20)) points of the sweep below the
    trace mean. The window is a fixed few points, not a fraction of the sweep, so the rule holds
    while those points span less than half a Rabi period (up to about (N - 1) / 4 periods for
    k = 3; with a window growing with N it failed beyond ~5 periods). Pass one read's trace in
    sweep order, starting near gain 0. Not a cable-winding correction:
    docs/concepts/iq_conventions.md section 3."""
    trace = np.asarray(signal_trace, dtype=complex).ravel()
    dev = trace - np.mean(trace)
    angle = principal_axis_angle(dev)
    proj = (dev * np.exp(-1j * angle)).real
    k = max(1, min(3, proj.size // 20))
    if np.mean(proj[:k]) > 0:
        angle += np.pi
    return float(np.angle(np.exp(1j * angle)))


def iq_axis_contrast_ratio(signal_trace):
    """Variance along the principal IQ axis over the variance across it (eigenvalue ratio of the
    2x2 IQ covariance of the mean-subtracted trace), >= 1. Near 1 the trace has no preferred axis
    (no oscillation, pure noise) and the rotation angle is arbitrary; inf for a noiseless line,
    NaN for a constant trace."""
    trace = np.asarray(signal_trace, dtype=complex).ravel()
    dev = trace - np.mean(trace)
    total = float(np.sum(np.abs(dev) ** 2))  # lambda_major + lambda_minor
    split = float(np.abs(np.sum(dev**2)))  # lambda_major - lambda_minor
    if total == 0.0:
        return float("nan")
    minor = total - split
    return float((total + split) / minor) if minor > 1e-12 * total else float("inf")


def _print_axis(label, angle, ratio):
    print(
        f"[{label}] IQ rotation angle = {np.rad2deg(angle):.2f} deg, axis contrast ratio = {ratio:.3g}"
    )
    if not ratio >= _MIN_AXIS_CONTRAST_RATIO:
        print(
            f"  [warn] {label}: axis contrast ratio {ratio:.3g} < {_MIN_AXIS_CONTRAST_RATIO:g}: "
            "little or no Rabi contrast, the IQ rotation is noise-driven."
        )


class AmplitudeRabiFFProg(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        cover_readout_window(self, cfg)
        # ADC 0 and 1 regardless of ro_chs (docs/concepts/readout_window.md#known-issues).
        for ch in [0, 1]:
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["readout_length"], ro_ch=ch),
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
            length=self.readout_tone_cycles,
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
            adc_trig_offset=self.adc_trig_offset_cycles,
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

    gain_sweep_keys = ("start", "step", "expts")

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

        # Principal-axis rotation on top of the winding phase. The axis and sign come from the
        # analysed read (ADC 0, the trace display() fits); the same rotation is applied to both
        # ADCs so the saved (2, 1, N) shape is unchanged.
        rot_angle = iq_rotation_angle(signal[0][0])
        contrast_ratio = iq_axis_contrast_ratio(signal[0][0])
        signal = signal * np.exp(-1j * rot_angle)
        _print_axis("AmplitudeRabiFF", rot_angle, contrast_ratio)

        avgi = signal.real
        avgq = signal.imag

        data = {
            "config": self.cfg,
            "data": {
                "x_pts": x_pts,
                "avgi": avgi,
                "avgq": avgq,
                "iq_rotation_rad": rot_angle,
                "iq_axis_contrast_ratio": contrast_ratio,
            },
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
                data["data"]["fit_i_perr"] = np.asarray(fit_i["perr"])
                data["data"]["fit_i_pi_gain_err"] = np.asarray(fit_i["dpi_gain"])
                data["data"]["fit_i_flag"] = np.asarray(fit_i["flag_code"])
                print(f"I fit: P={fit_i['P']:.3f}, pi={fit_i['pi_gain']:.3f}")
                _print_fit_flags("I", fit_i)
            except Exception as err:
                print(f"I fit failed: {err}")

            try:
                fit_q = fit_rabi_cosine(x_pts, avgq)
                data["data"]["fit_q_popt"] = np.asarray(fit_q["popt"])
                data["data"]["fit_q_pi_gain"] = np.asarray(fit_q["pi_gain"])
                data["data"]["fit_q_perr"] = np.asarray(fit_q["perr"])
                data["data"]["fit_q_pi_gain_err"] = np.asarray(fit_q["dpi_gain"])
                data["data"]["fit_q_flag"] = np.asarray(fit_q["flag_code"])
                print(f"Q fit: P={fit_q['P']:.3f}, pi={fit_q['pi_gain']:.3f}")
                _print_fit_flags("Q", fit_q)
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
        cover_readout_window(self, cfg)
        # ADC 0 and 1 regardless of ro_chs (docs/concepts/readout_window.md#known-issues).
        for ch in [0, 1]:
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["readout_length"], ro_ch=ch),
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
            length=self.readout_tone_cycles,
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
            adc_trig_offset=self.adc_trig_offset_cycles,
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
            sig = avgi + 1j * avgq
            rot_angle = iq_rotation_angle(sig)
            self.iq_axis_contrast_ratio = iq_axis_contrast_ratio(sig)
            rotated = sig * np.exp(-1j * rot_angle)
            avgi, avgq = rotated.real, rotated.imag
            self.rotation_phase = -rot_angle  # multiplier phase: rotated = raw * exp(1j * phase)
            _print_axis("AmplitudeRabiFF_N", rot_angle, self.iq_axis_contrast_ratio)

        x_min, x_max = float(np.min(x_pts)), float(np.max(x_pts))

        fit_i = fit_q = None
        if fit:
            print("Raw extrema:")
            print("  Max I gain:", x_pts[np.argmax(avgi)], " Max Q gain:", x_pts[np.argmax(avgq)])
            print("  Min I gain:", x_pts[np.argmin(avgi)], " Min Q gain:", x_pts[np.argmin(avgq)])

            print("\nCosine fit results:")
            fits = []
            for lbl, y in (("I", avgi), ("Q", avgq)):
                try:
                    f = fit_rabi_cosine(x_pts, y)
                except Exception as err:
                    print(f"  {lbl} fit failed: {err}")
                    fits.append(None)
                    continue
                print(f"  {lbl} fit period P       = {f['P']:.3f} ± {f['dP']:.3f}")
                print(f"  {lbl} fit phase phi      = {f['phi']:.3f} ± {f['dphi']:.3f}")
                print(f"  {lbl}-derived pi gain    = {f['pi_gain']:.3f} ± {f['dpi_gain']:.3f}")
                _print_fit_flags(lbl, f)
                fits.append(f)
            fit_i, fit_q = fits

        # saved by save_data (docs/experiments/amplitude_rabi.md#outputs)
        if rotate:
            data["data"]["rotation_phase"] = np.asarray(self.rotation_phase)
        for q, f in (("i", fit_i), ("q", fit_q)):
            if f is None:
                continue
            data["data"][f"fit_{q}_popt"] = np.asarray(f["popt"])
            data["data"][f"fit_{q}_perr"] = np.asarray(f["perr"])
            data["data"][f"fit_{q}_pi_gain"] = np.asarray(f["pi_gain"])
            data["data"][f"fit_{q}_pi_gain_err"] = np.asarray(f["dpi_gain"])
            data["data"][f"fit_{q}_flag"] = np.asarray(f["flag_code"])

        self.fit_i = fit_i
        self.fit_q = fit_q

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig = plt.figure(figNum)
        plt.plot(x_pts, avgi, "o", label="I data", color="orange")
        plt.plot(x_pts, avgq, "o", label="Q data", color="blue")

        for f, color, lbl in ((fit_i, "orange", "I"), (fit_q, "blue", "Q")):
            if f is None:
                continue
            plt.plot(x_pts, f["yfit"], "-", label=f"{lbl} fit, pi={f['pi_gain']:.1f}", color=color)

            # A failed fit has a runaway period: hide out-of-range markers (amplitude_rabi.md).
            lbl = f"{lbl} pi gain"
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
