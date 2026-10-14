"""Ramsey (T2*) experiment: tProc program and ExperimentClass wrapper."""

import traceback

import matplotlib.pyplot as plt
import numpy as np
from qick import RAveragerProgram

from qicklab.analysis.ramsey import (
    find_prominent_fft_peaks,
    fit_magnitude_envelope,
    fit_ramsey_auto,
    project_ramsey_iq,
)
from qicklab.core.experiment import ExperimentClass


class T2RProgram(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_wait = 3
        self.r_phase2 = 4
        self.r_phase = self.sreg(cfg["qubit_ch"], "phase")
        self.regwi(self.q_rp, self.r_wait, cfg["start"])
        self.regwi(self.q_rp, self.r_phase2, 0)

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        for ch in cfg["ro_chs"]:
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

        self.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="arb",
            freq=f_ge,
            phase=0,
            gain=cfg["pi2_gain"],
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

        self.sync_all(self.us2cycles(0.2))

    def body(self):
        self.regwi(self.q_rp, self.r_phase, 0)

        self.pulse(ch=self.cfg["qubit_ch"])
        self.mathi(self.q_rp, self.r_phase, self.r_phase2, "+", 0)
        self.sync_all()
        self.sync(self.q_rp, self.r_wait)

        self.pulse(ch=self.cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.05))
        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=self.ro_chs,
            adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=self.us2cycles(self.cfg["relax_delay"]),
        )

    def update(self):
        self.mathi(self.q_rp, self.r_wait, self.r_wait, "+", self.us2cycles(self.cfg["step"]))
        self.mathi(self.q_rp, self.r_phase2, self.r_phase2, "+", self.cfg["phase_step"])


class T2R(ExperimentClass):
    """Ramsey T2*: two pi/2 pulses (plain Gaussian, pi2_gain), register-swept wait and
    optional phase advance; FFT-seeded fit (docs/experiments/t2_ramsey.md)."""

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
        prog = T2RProgram(self.soccfg, self.cfg)

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
        data = {"config": self.cfg, "data": {"x_pts": x_pts, "avgi": avgi, "avgq": avgq}}
        self.data = data

        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        """Fit and plot. A failed fit does not raise: ``osc_fit`` / ``env_fit`` get
        ``{'ok': False, 'error': ...}`` and the projected data and FFT are still plotted."""
        if data is None:
            data = self.data

        x_pts = np.asarray(data["data"]["x_pts"], dtype=float)
        avgi = np.asarray(data["data"]["avgi"][0][0], dtype=float)
        avgq = np.asarray(data["data"]["avgq"][0][0], dtype=float)

        try:
            osc_fit = fit_ramsey_auto(x_pts, avgi, avgq)
            osc_fit["ok"] = True
        except Exception as e:
            traceback.print_exc()
            sig_rot, iq_axis_rad = project_ramsey_iq(avgi, avgq)
            freqs, spec, peaks = find_prominent_fft_peaks(
                x_pts, np.real(sig_rot), prominence_frac=0.25
            )
            osc_fit = {
                "ok": False,
                "error": repr(e),
                "mode": None,
                "sig_rot": sig_rot,
                "iq_axis_rad": iq_axis_rad,
                "fft_freqs": freqs,
                "fft_spec": spec,
                "fft_peaks": peaks,
            }

        try:
            env_fit = fit_magnitude_envelope(x_pts, avgi, avgq)
            env_fit["ok"] = True
        except Exception as e:
            traceback.print_exc()
            env_fit = {"ok": False, "error": repr(e)}

        sig_rot = osc_fit["sig_rot"]
        y_rot = np.real(sig_rot)

        # The FFT is a seed and a sanity check; the reported frequency is always the fitted one.
        fft_freqs = np.asarray(osc_fit["fft_freqs"], dtype=float)
        fft_spec = np.asarray(osc_fit["fft_spec"], dtype=float)
        fft_peaks = np.asarray(osc_fit["fft_peaks"], dtype=float)

        dominant_fft_freq = None
        if len(fft_peaks) > 0:
            peak_amps = np.array([fft_spec[np.argmin(np.abs(fft_freqs - fp))] for fp in fft_peaks])
            dominant_fft_freq = float(fft_peaks[np.argmax(peak_amps)])
        osc_fit["dominant_fft_freq"] = dominant_fft_freq

        # One FFT bin, 1 / (N dt).
        fft_bin = fft_freqs[1] - fft_freqs[0] if len(fft_freqs) > 1 else np.inf

        if osc_fit["ok"]:
            perr = np.sqrt(np.diag(osc_fit["pcov"]))
            osc_fit["perr"] = perr

            if osc_fit["mode"] == "1f":
                A, T2, f, phi, C = osc_fit["popt"]
                dA, dT2, df, dphi, dC = perr
                f_fits = [f]
                f_report = f
                label = f"1f fit: T2*={T2:.2f}±{dT2:.2f} us, f={f:.4f}±{df:.4f} MHz"
            else:
                A1, A2, T2, f1, f2, phi1, phi2, C = osc_fit["popt"]
                dA1, dA2, dT2, df1, df2, dphi1, dphi2, dC = perr
                f_fits = [f1, f2]
                f_report = f1
                label = (
                    f"2f fit: T2*={T2:.2f}±{dT2:.2f} us, "
                    f"f1={f1:.4f}±{df1:.4f} MHz, "
                    f"f2={f2:.4f}±{df2:.4f} MHz"
                )

            mismatch = dominant_fft_freq is not None and bool(
                min(abs(ff - dominant_fft_freq) for ff in f_fits) > fft_bin
            )
            osc_fit["fft_fit_mismatch"] = mismatch
            if mismatch:
                label += (
                    f"\nWARNING: fit and FFT peak ({dominant_fft_freq:.4f} MHz) differ by > 1 bin"
                )
        else:
            f_report = None
            label = f"fit failed: {osc_fit['error']}"

        osc_fit["f_report"] = f_report
        self.osc_fit = osc_fit
        self.env_fit = env_fit

        print(label)

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig = plt.figure(figNum)
        plt.plot(x_pts, y_rot, "o-", label="projected I")
        if osc_fit["ok"]:
            plt.plot(x_pts, osc_fit["fit_y"], "-", linewidth=2, label=label)
        plt.xlabel("Wait time (us)")
        plt.ylabel("a.u.")
        plt.legend()
        plt.title(self.titlename + " projected quadrature" + ("" if osc_fit["ok"] else " (no fit)"))
        plt.tight_layout()
        plt.savefig(self.iname[:-4] + "RotatedI_Fit.png")

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

        fig = plt.figure(figNum + 2)
        plt.plot(fft_freqs, fft_spec, "-", label="FFT")

        for fp in fft_peaks[:5]:
            plt.axvline(fp, linestyle="--", alpha=0.6)

        if f_report is not None:
            plt.axvline(f_report, linewidth=2, label=f"fit {f_report:.4f} MHz")

        plt.xlabel("Frequency (MHz)")
        plt.ylabel("FFT amplitude")
        plt.title(self.titlename + " FFT")
        plt.legend()
        plt.tight_layout()
        plt.savefig(self.iname[:-4] + "FFT.png")

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f"Saving {self.fname}")
        super().save_data(data=data["data"])
