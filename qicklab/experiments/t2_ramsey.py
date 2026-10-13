"""Ramsey (T2*) experiment: tProc program and ExperimentClass wrapper."""

import matplotlib.pyplot as plt
import numpy as np
from qick import RAveragerProgram

from qicklab.analysis.ramsey import fit_magnitude_envelope, fit_ramsey_auto
from qicklab.core.experiment import ExperimentClass


class T2RProgram(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.q_rp = self.ch_page(cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_wait = 3
        self.r_phase2 = 4
        self.r_phase = self.sreg(cfg["qubit_ch"], "phase")
        self.regwi(self.q_rp, self.r_wait, cfg["start"])
        self.regwi(self.q_rp, self.r_phase2, 0)

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in cfg["ro_chs"]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["readout_length"]),
                freq=cfg["pulse_freq"],
                gen_ch=cfg["res_ch"],
            )

        f_res = self.freq2reg(
            cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0]
        )  # conver f_res to dac register value
        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        # add qubit and readout pulses to respective channels

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

        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.mathi(self.q_rp, self.r_phase, self.r_phase2, "+", 0)
        self.sync_all()
        self.sync(self.q_rp, self.r_wait)

        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.sync_all(self.us2cycles(0.05))
        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=self.ro_chs,
            adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=self.us2cycles(self.cfg["relax_delay"]),
        )

    def update(self):
        self.mathi(
            self.q_rp, self.r_wait, self.r_wait, "+", self.us2cycles(self.cfg["step"])
        )  # update the time between two π/2 pulses
        self.mathi(
            self.q_rp, self.r_phase2, self.r_phase2, "+", self.cfg["phase_step"]
        )  # advance the phase of the LO for the second π/2 pulse


class T2R(ExperimentClass):
    """
    Basic T2R
    """

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

        #### pull the data from the amp rabi sweep
        # prog = PulseProbeSpectroscopyProgram(self.soccfg, self.cfg)
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
        )  # debug=False)
        data = {"config": self.cfg, "data": {"x_pts": x_pts, "avgi": avgi, "avgq": avgq}}
        self.data = data

        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data

        x_pts = np.asarray(data["data"]["x_pts"], dtype=float)
        avgi = np.asarray(data["data"]["avgi"][0][0], dtype=float)
        avgq = np.asarray(data["data"]["avgq"][0][0], dtype=float)

        osc_fit = fit_ramsey_auto(x_pts, avgi, avgq)
        env_fit = fit_magnitude_envelope(x_pts, avgi, avgq)

        sig_rot = osc_fit["sig_rot"]
        y_rot = np.real(sig_rot)

        # ------------------------------------------------------------
        # Use FFT frequency if one peak is clearly dominant
        # ------------------------------------------------------------
        fft_peak_dominance = kwargs.get("fft_peak_dominance", 2.5)

        fft_freqs = np.asarray(osc_fit["fft_freqs"], dtype=float)
        fft_spec = np.asarray(osc_fit["fft_spec"], dtype=float)
        fft_peaks = np.asarray(osc_fit["fft_peaks"], dtype=float)

        use_fft_freq = False
        dominant_fft_freq = None

        if len(fft_peaks) > 0:
            peak_amps = np.array([fft_spec[np.argmin(np.abs(fft_freqs - fp))] for fp in fft_peaks])

            order = np.argsort(peak_amps)[::-1]
            best_amp = peak_amps[order[0]]
            best_freq = float(fft_peaks[order[0]])

            if len(order) == 1:
                use_fft_freq = True
                dominant_fft_freq = best_freq
            else:
                second_amp = peak_amps[order[1]]
                if second_amp <= 0 or best_amp > fft_peak_dominance * second_amp:
                    use_fft_freq = True
                    dominant_fft_freq = best_freq

        osc_fit["use_fft_freq"] = use_fft_freq
        osc_fit["dominant_fft_freq"] = dominant_fft_freq

        # ------------------------------------------------------------
        # Build fit label and reported Ramsey frequency
        # ------------------------------------------------------------
        perr = np.sqrt(np.diag(osc_fit["pcov"]))
        osc_fit["perr"] = perr

        if osc_fit["mode"] == "1f":
            A, T2, f, phi, C = osc_fit["popt"]
            dA, dT2, df, dphi, dC = perr

            if use_fft_freq:
                f_report = dominant_fft_freq
                label = (
                    f"1f fit: T2*={T2:.2f}±{dT2:.2f} us, "
                    f"f_fit={f:.4f} MHz, f_FFT={f_report:.4f} MHz USED"
                )
            else:
                f_report = f
                label = f"1f fit: T2*={T2:.2f}±{dT2:.2f} us, f={f:.4f}±{df:.4f} MHz"

        else:
            A1, A2, T2, f1, f2, phi1, phi2, C = osc_fit["popt"]
            dA1, dA2, dT2, df1, df2, dphi1, dphi2, dC = perr

            if use_fft_freq:
                f_report = dominant_fft_freq
                label = (
                    f"2f fit: T2*={T2:.2f}±{dT2:.2f} us, "
                    f"f1_fit={f1:.4f} MHz, f2_fit={f2:.4f} MHz, "
                    f"f_FFT={f_report:.4f} MHz USED"
                )
            else:
                f_report = f1
                label = (
                    f"2f fit: T2*={T2:.2f}±{dT2:.2f} us, "
                    f"f1={f1:.4f}±{df1:.4f} MHz, "
                    f"f2={f2:.4f}±{df2:.4f} MHz"
                )

        osc_fit["f_report"] = f_report
        self.osc_fit = osc_fit
        self.env_fit = env_fit

        print(label)

        # ------------------------------------------------------------
        # Rotated quadrature plot
        # ------------------------------------------------------------
        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig = plt.figure(figNum)
        plt.plot(x_pts, y_rot, "o-", label="rotated I")
        plt.plot(x_pts, osc_fit["fit_y"], "-", linewidth=2, label=label)
        plt.xlabel("Wait time (us)")
        plt.ylabel("a.u.")
        plt.legend()
        plt.title(self.titlename + " rotated quadrature")
        plt.tight_layout()
        plt.savefig(self.iname[:-4] + "RotatedI_Fit.png")

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

        # ------------------------------------------------------------
        # FFT plot
        # ------------------------------------------------------------
        fig = plt.figure(figNum + 2)
        plt.plot(fft_freqs, fft_spec, "-", label="FFT")

        for fp in fft_peaks[:5]:
            plt.axvline(fp, linestyle="--", alpha=0.6)

        if use_fft_freq:
            plt.axvline(dominant_fft_freq, linewidth=2, label=f"USED {dominant_fft_freq:.4f} MHz")

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
