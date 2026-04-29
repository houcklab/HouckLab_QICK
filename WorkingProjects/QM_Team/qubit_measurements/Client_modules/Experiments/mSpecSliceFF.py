from qick import *
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
from utils import *

class QubitSpecSliceFFProg(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.declare_gen(
            ch=cfg["res_ch"],
            nqz=cfg["nqz"],
            mixer_freq=cfg["mixer_freq"],
            ro_ch=cfg["ro_chs"][0],) # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch

        ### Start fast flux
        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value

        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])

        # add qubit and readout pulses to respective channels
        if cfg['Gauss']:
            self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
            self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_start,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_length_us = cfg["sigma"] * 4
        else:
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0, gain=cfg["qubit_gain"],
                                     length=self.us2cycles(cfg["qubit_length"]))
            self.qubit_length_us = cfg["qubit_length"]
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        print("\n--- Initializing QubitSpec ---")



    def body(self):
        self.sync_all()
        self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(1))  # play probe pulse
        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.sync_all(self.us2cycles(0.5))
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0, 1],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index
# ====================================================== #

class QubitSpecSliceFF(ExperimentClass):
    """
    Basic spec experiement that takes a single slice of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):


        prog = QubitSpecSliceFFProg(self.soccfg, self.cfg)
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False)# , debug=False)
        # Convert avgi and avgq to NumPy arrays
        avgi = np.asarray(avgi)
        avgq = np.asarray(avgq)

        # Compute the complex signal
        signal = (avgi + 1j * avgq) * np.exp(
            1j * (2 * np.pi * self.cfg['cavity_winding_freq'] *
                  self.cfg["pulse_freq"] + self.cfg['cavity_winding_offset'])
        )

        # Separate back into real and imaginary parts
        avgi = signal.real
        avgq = signal.imag

        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']

        #### find the frequency corresponding to the qubit dip
        sig = avgi + 1j * avgq
        avgamp0 = np.abs(sig)
        peak_loc = np.argmax(avgamp0)
        self.qubitFreq = x_pts[peak_loc]

        return data

    def display(self, data=None, plotDisp=False, figNum=1, min_sep=0.1, **kwargs):
        def _lorentzian(x, y0, A, x0, gamma):
            return y0 + A * (gamma ** 2 / ((x - x0) ** 2 + gamma ** 2))

        def _fit_lorentzian_near_peak(x, y, peak_x, fit_window_mhz):
            x = np.asarray(x, dtype=float)
            y = np.asarray(y, dtype=float)

            mask = np.abs(x - peak_x) <= fit_window_mhz
            if np.sum(mask) < 6:
                return None

            xf = x[mask]
            yf = y[mask]

            y0_guess = np.median(yf)
            A_guess = np.max(yf) - y0_guess
            gamma_guess = max((np.max(xf) - np.min(xf)) / 8, 1e-6)

            p0 = [y0_guess, A_guess, peak_x, gamma_guess]

            bounds = (
                [-np.inf, 0, np.min(xf), 1e-9],
                [np.inf, np.inf, np.max(xf), np.max(xf) - np.min(xf)]
            )

            try:
                popt, pcov = curve_fit(
                    _lorentzian,
                    xf,
                    yf,
                    p0=p0,
                    bounds=bounds,
                    maxfev=50000
                )

                yfit = _lorentzian(xf, *popt)
                ss_res = np.sum((yf - yfit) ** 2)
                ss_tot = np.sum((yf - np.mean(yf)) ** 2)
                r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan

                y0, A, x0, gamma = popt

                # reject bad/unphysical fits
                if not np.isfinite(r2) or r2 < 0.60:
                    return None
                if gamma <= 0 or gamma >= (np.max(xf) - np.min(xf)):
                    return None
                if x0 < np.min(xf) or x0 > np.max(xf):
                    return None

                return {
                    "popt": popt,
                    "pcov": pcov,
                    "x_fit": xf,
                    "y_fit": yfit,
                    "r2": r2,
                    "center": x0,
                    "gamma": gamma,
                    "fwhm": 2 * gamma,
                    "amplitude": A,
                    "offset": y0,
                }

            except Exception:
                return None

        if data is None:
            data = self.data

        x_pts = np.asarray(data['data']['x_pts'], dtype=float)
        avgi = np.asarray(data['data']['avgi'][0][0], dtype=float)
        avgq = np.asarray(data['data']['avgq'][0][0], dtype=float)

        sig = avgi + 1j * avgq
        avgamp0 = np.abs(sig) ** 2

        min_sep_mhz = kwargs.get("min_sep_mhz", min_sep)
        fit_window_mhz = kwargs.get("fit_window_mhz", 3 * min_sep_mhz)
        prominent_ratio = kwargs.get("prominent_ratio", 0.35)

        # -----------------------------
        # Find candidate local maxima
        # -----------------------------
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

        # -----------------------------
        # Fit at most two Lorentzians
        # -----------------------------
        lorentz_fits = []
        for idx in selected_peaks:
            fit = _fit_lorentzian_near_peak(
                x=x_pts,
                y=avgamp0,
                peak_x=x_pts[idx],
                fit_window_mhz=fit_window_mhz
            )
            if fit is not None:
                lorentz_fits.append(fit)

        # -----------------------------
        # Store fit results in data
        # -----------------------------
        data['data']['two_tone_peak_freqs'] = np.array([x_pts[i] for i in selected_peaks])
        data['data']['two_tone_peak_amps'] = np.array([avgamp0[i] for i in selected_peaks])
        data['data']['lorentz_num_fits'] = len(lorentz_fits)
        data['data']['lorentz_centers'] = np.array([f["center"] for f in lorentz_fits])
        data['data']['lorentz_fwhm'] = np.array([f["fwhm"] for f in lorentz_fits])
        data['data']['lorentz_gamma'] = np.array([f["gamma"] for f in lorentz_fits])
        data['data']['lorentz_amplitudes'] = np.array([f["amplitude"] for f in lorentz_fits])
        data['data']['lorentz_offsets'] = np.array([f["offset"] for f in lorentz_fits])
        data['data']['lorentz_r2'] = np.array([f["r2"] for f in lorentz_fits])

        self.data = data

        print("I Max", x_pts[np.argmax(avgi)])
        print("Q Max", x_pts[np.argmax(avgq)])
        print("Max Amplitude ^2", x_pts[np.argmax(avgamp0)], "Amplitude ^2", np.max(avgamp0))

        for k, idx in enumerate(selected_peaks):
            print(f"Peak {k + 1}: freq = {x_pts[idx]:.6f} MHz, amplitude^2 = {avgamp0[idx]:.6f}")

        for k, fit in enumerate(lorentz_fits):
            print(
                f"Lorentzian {k + 1}: center={fit['center']:.6f} MHz, "
                f"FWHM={fit['fwhm']:.6f} MHz, R2={fit['r2']:.3f}"
            )

        # -----------------------------
        # Plot I/Q
        # -----------------------------
        fig = plt.figure(figNum)
        plt.plot(x_pts, avgi, '.-', color='Orange', label="I")
        plt.plot(x_pts, avgq, '.-', color='Blue', label="Q")

        for k, idx in enumerate(selected_peaks):
            plt.axvline(x_pts[idx], linestyle='--', label=f"Peak {k + 1}: {x_pts[idx]:.6f} MHz")

        plt.ylabel("a.u.")
        plt.xlabel("Qubit Frequency")
        plt.title(self.titlename)
        plt.legend()
        plt.tight_layout()
        plt.savefig(self.iname[:-4] + '_IQ.png')

        if plotDisp:
            plt.show()
        else:
            fig.clf(True)
            plt.close(fig)

        # -----------------------------
        # Plot amplitude^2 + Lorentzian fits
        # -----------------------------
        fig = plt.figure(figNum + 1)
        plt.plot(x_pts, avgamp0, '.-', color='Purple', label="|I+iQ|^2")

        for k, idx in enumerate(selected_peaks):
            plt.axvline(x_pts[idx], linestyle='--', alpha=0.7, label=f"Peak {k + 1}: {x_pts[idx]:.6f}")
            plt.plot(x_pts[idx], avgamp0[idx], 'o')

        for k, fit in enumerate(lorentz_fits):
            plt.plot(
                fit["x_fit"],
                fit["y_fit"],
                '-',
                linewidth=2,
                label=f"Lorentz {k + 1}: center={fit['center']:.6f}, FWHM={fit['fwhm']:.4f}"
            )

        plt.ylabel("a.u.")
        plt.xlabel("Qubit Frequency")
        plt.title(self.titlename + " Amplitude^2 + Lorentzian Fits")
        plt.legend()
        plt.tight_layout()
        plt.savefig(self.iname[:-4] + '_Amp2_LorentzFits.png')

        if plotDisp:
            plt.show()
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)


    def get_amplitude_slice(self, data=None):
        if data is None:
            data = self.data
        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]
        sig = avgi + 1j * avgq
        avgamp0 = np.abs(sig)
        return x_pts, avgamp0, avgi, avgq


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


