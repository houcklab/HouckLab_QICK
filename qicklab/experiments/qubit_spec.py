import matplotlib.pyplot as plt
import numpy as np
from qick import RAveragerProgram

from qicklab.analysis.iq import project_iq_signal
from qicklab.analysis.spectroscopy import fit_lorentzian_near_peak
from qicklab.core.experiment import ExperimentClass


class QubitSpecSliceFFProg(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.declare_gen(
            ch=cfg["res_ch"],
            nqz=cfg["nqz"],
            mixer_freq=cfg["mixer_freq"],
            ro_ch=cfg["ro_chs"][0],
        )
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        for ch in [0, 1]:
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["readout_length"]),
                freq=cfg["pulse_freq"],
                gen_ch=cfg["res_ch"],
            )

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)

        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])

        if cfg["Gauss"]:
            # 4-sigma envelope: docs/concepts/timing_and_units.md#pulse-envelopes
            self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
            self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
            self.add_gauss(
                ch=cfg["qubit_ch"],
                name="qubit",
                sigma=self.pulse_sigma,
                length=self.pulse_qubit_lenth,
            )
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="arb",
                freq=self.f_start,
                phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]),
                gain=cfg["qubit_gain"],
                waveform="qubit",
            )
            self.qubit_length_us = cfg["sigma"] * 4
        else:
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="const",
                freq=self.f_start,
                phase=0,
                gain=cfg["qubit_gain"],
                length=self.us2cycles(cfg["qubit_length"]),
            )
            self.qubit_length_us = cfg["qubit_length"]
        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=f_res,
            phase=cfg["res_phase"],
            gain=cfg["pulse_gain"],
            length=self.us2cycles(cfg["length"]),
        )

        print("\n--- Initializing QubitSpec ---")

    def body(self):
        self.sync_all()
        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(1))
        self.sync_all(self.us2cycles(0.5))
        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=[0, 1],
            adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=self.us2cycles(10),
        )

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, "+", self.f_step)


class QubitSpecSliceFF(ExperimentClass):
    """Two-tone qubit spectroscopy: register-swept qubit frequency, fixed readout tone.

    Peak picking and Lorentzian fits in display(): docs/experiments/two_tone_spec.md."""

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

        prog = QubitSpecSliceFFProg(self.soccfg, self.cfg)
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
        avgi = np.asarray(avgi)
        avgq = np.asarray(avgq)

        signal = (avgi + 1j * avgq) * np.exp(
            1j
            * (
                2 * np.pi * self.cfg["cavity_winding_freq"] * self.cfg["pulse_freq"]
                + self.cfg["cavity_winding_offset"]
            )
        )

        avgi = signal.real
        avgq = signal.imag

        data = {"config": self.cfg, "data": {"x_pts": x_pts, "avgi": avgi, "avgq": avgq}}
        self.data = data

        # [0][0] = ADC 0, read 0 (a flat argmax overruns x_pts); projection, not |I + iQ|
        # (docs/concepts/iq_conventions.md section 2).
        signal_trace = project_iq_signal(avgi[0][0], avgq[0][0])
        peak_loc = np.argmax(signal_trace)
        self.qubitFreq = x_pts[peak_loc]

        return data

    def display(self, data=None, plotDisp=False, figNum=1, min_sep=0.1, **kwargs):
        if data is None:
            data = self.data

        x_pts = np.asarray(data["data"]["x_pts"], dtype=float)
        avgi = np.asarray(data["data"]["avgi"][0][0], dtype=float)
        avgq = np.asarray(data["data"]["avgq"][0][0], dtype=float)

        # Projection, not |I + iQ| (docs/concepts/iq_conventions.md section 2).
        avgamp0 = project_iq_signal(avgi, avgq)

        min_sep_mhz = kwargs.get("min_sep_mhz", min_sep)
        fit_window_mhz = kwargs.get("fit_window_mhz", 3 * min_sep_mhz)
        prominent_ratio = kwargs.get("prominent_ratio", 0.35)

        candidate_inds = []
        n = len(avgamp0)

        if n == 1:
            candidate_inds = [0]
        else:
            if avgamp0[0] > avgamp0[1]:
                candidate_inds.append(0)

            for i in range(1, n - 1):
                if avgamp0[i] > avgamp0[i - 1] and avgamp0[i] >= avgamp0[i + 1]:
                    candidate_inds.append(i)

            if avgamp0[-1] > avgamp0[-2]:
                candidate_inds.append(n - 1)

        if len(candidate_inds) == 0:
            candidate_inds = list(range(n))

        candidate_inds = sorted(candidate_inds, key=lambda i: avgamp0[i], reverse=True)

        selected_peaks = []
        for idx in candidate_inds:
            if len(selected_peaks) == 0:
                selected_peaks.append(idx)
            else:
                far_enough = all(abs(x_pts[idx] - x_pts[j]) >= min_sep_mhz for j in selected_peaks)
                strong_enough = avgamp0[idx] >= prominent_ratio * avgamp0[selected_peaks[0]]
                if far_enough and strong_enough:
                    selected_peaks.append(idx)

            if len(selected_peaks) == 2:
                break

        selected_peaks = sorted(selected_peaks, key=lambda i: x_pts[i])

        lorentz_fits = []
        for idx in selected_peaks:
            fit = fit_lorentzian_near_peak(
                x=x_pts, y=avgamp0, peak_x=x_pts[idx], fit_window_mhz=fit_window_mhz
            )
            if fit is not None:
                lorentz_fits.append(fit)

        data["data"]["two_tone_peak_freqs"] = np.array([x_pts[i] for i in selected_peaks])
        data["data"]["two_tone_peak_amps"] = np.array([avgamp0[i] for i in selected_peaks])
        data["data"]["lorentz_num_fits"] = len(lorentz_fits)
        data["data"]["lorentz_centers"] = np.array([f["center"] for f in lorentz_fits])
        data["data"]["lorentz_fwhm"] = np.array([f["fwhm"] for f in lorentz_fits])
        data["data"]["lorentz_gamma"] = np.array([f["gamma"] for f in lorentz_fits])
        data["data"]["lorentz_amplitudes"] = np.array([f["amplitude"] for f in lorentz_fits])
        data["data"]["lorentz_offsets"] = np.array([f["offset"] for f in lorentz_fits])
        data["data"]["lorentz_r2"] = np.array([f["r2"] for f in lorentz_fits])

        self.data = data

        print("I Max", x_pts[np.argmax(avgi)])
        print("Q Max", x_pts[np.argmax(avgq)])
        print("Max Rotated Projection", x_pts[np.argmax(avgamp0)], "value", np.max(avgamp0))

        for k, idx in enumerate(selected_peaks):
            print(f"Peak {k + 1}: freq = {x_pts[idx]:.6f} MHz, amplitude^2 = {avgamp0[idx]:.6f}")

        for k, fit in enumerate(lorentz_fits):
            print(
                f"Lorentzian {k + 1}: center={fit['center']:.6f} MHz, "
                f"FWHM={fit['fwhm']:.6f} MHz, R2={fit['r2']:.3f}"
            )

        q_gain = self.cfg.get("qubit_gain", "?")
        if self.cfg.get("Gauss", False):
            sigma_us = self.cfg.get("sigma", "?")
            pulse_info = f"gain={q_gain}  Gauss σ={sigma_us} µs"
        else:
            q_len = self.cfg.get("qubit_length", "?")
            pulse_info = f"gain={q_gain}  length={q_len} µs"

        fig = plt.figure(figNum)
        plt.plot(x_pts, avgi, ".-", color="Orange", label="I")
        plt.plot(x_pts, avgq, ".-", color="Blue", label="Q")

        for k, idx in enumerate(selected_peaks):
            plt.axvline(x_pts[idx], linestyle="--", label=f"Peak {k + 1}: {x_pts[idx]:.6f} MHz")

        plt.ylabel("a.u.")
        plt.xlabel("Qubit Frequency")
        plt.title(f"{self.titlename}\n{pulse_info}")
        plt.legend()
        plt.tight_layout()
        plt.savefig(self.iname[:-4] + "_IQ.png")

        if plotDisp:
            plt.show()
        fig.clf(True)
        plt.close(fig)

        fig = plt.figure(figNum + 1)
        plt.plot(x_pts, avgamp0, ".-", color="Purple", label="rotated IQ projection")

        for k, idx in enumerate(selected_peaks):
            plt.axvline(
                x_pts[idx], linestyle="--", alpha=0.7, label=f"Peak {k + 1}: {x_pts[idx]:.6f}"
            )
            plt.plot(x_pts[idx], avgamp0[idx], "o")

        for k, fit in enumerate(lorentz_fits):
            plt.plot(
                fit["x_fit"],
                fit["y_fit"],
                "-",
                linewidth=2,
                label=f"Lorentz {k + 1}: center={fit['center']:.6f}, FWHM={fit['fwhm']:.4f}",
            )

        plt.ylabel("a.u.")
        plt.xlabel("Qubit Frequency")
        plt.title(f"{self.titlename} Rotated IQ Projection + Lorentzian Fits\n{pulse_info}")
        plt.legend()
        plt.tight_layout()
        plt.savefig(self.iname[:-4] + "_Amp2_LorentzFits.png")

        if plotDisp:
            plt.show()
            plt.pause(0.1)
        fig.clf(True)
        plt.close(fig)

    def save_data(self, data=None):
        print(f"Saving {self.fname}")
        super().save_data(data=data["data"])
