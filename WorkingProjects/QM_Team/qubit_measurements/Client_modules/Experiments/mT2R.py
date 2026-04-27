from qick import *
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
from scipy.optimize import curve_fit
from scipy.signal import find_peaks

def rotate_iq(avgi, avgq):
    sig = np.asarray(avgi) + 1j*np.asarray(avgq)
    theta = -np.angle(np.mean(sig))
    sig_rot = sig * np.exp(1j*theta)
    return sig_rot

def ramsey_1f(t, A, T2, f, phi, C):
    return A * np.exp(-t / T2) * np.cos(2*np.pi*f*t + phi) + C

def ramsey_2f(t, A1, A2, T2, f1, f2, phi1, phi2, C):
    env = np.exp(-t / T2)
    return env * (
        A1 * np.cos(2*np.pi*f1*t + phi1) +
        A2 * np.cos(2*np.pi*f2*t + phi2)
    ) + C

def envelope_exp(t, A, T2, C):
    return A * np.exp(-t / T2) + C

def envelope_gauss(t, A, T2, C):
    return A * np.exp(-(t / T2)**2) + C

def find_prominent_fft_peaks(t, y, prominence_frac=0.2):
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)

    dt = np.mean(np.diff(t))
    y0 = y - np.mean(y)

    freqs = np.fft.rfftfreq(len(t), d=dt)
    spec = np.abs(np.fft.rfft(y0))

    if len(spec) < 3:
        return freqs, spec, []

    peak_inds, props = find_peaks(spec[1:], prominence=np.max(spec[1:]) * prominence_frac)
    peak_inds = peak_inds + 1  # because we skipped DC

    # sort by descending spectral height
    peak_inds = sorted(peak_inds, key=lambda k: spec[k], reverse=True)
    peak_freqs = [freqs[k] for k in peak_inds]

    return freqs, spec, peak_freqs

def fit_ramsey_auto(x, avgi, avgq):
    x = np.asarray(x, dtype=float)

    # rotate IQ so oscillation mostly appears in Re part
    sig_rot = rotate_iq(avgi, avgq)
    y = np.real(sig_rot)

    freqs, spec, peak_freqs = find_prominent_fft_peaks(x, y, prominence_frac=0.25)

    C0 = np.mean(y)
    A0 = 0.5 * (np.max(y) - np.min(y))
    T20 = max((x[-1] - x[0]) * 0.7, 1.0)

    result = {
        "mode": None,
        "sig_rot": sig_rot,
        "fft_freqs": freqs,
        "fft_spec": spec,
        "fft_peaks": peak_freqs,
    }

    # single-tone default
    if len(peak_freqs) < 2:
        f0 = peak_freqs[0] if len(peak_freqs) else 0.05

        p0 = [A0, T20, f0, 0.0, C0]
        bounds = (
            [0.0, 1.0, 0.0, -2*np.pi, np.min(y)-abs(A0)],
            [10*abs(A0)+1e-12, 1e5, 2.0, 2*np.pi, np.max(y)+abs(A0)]
        )

        popt, pcov = curve_fit(ramsey_1f, x, y, p0=p0, bounds=bounds, maxfev=50000)

        result.update({
            "mode": "1f",
            "popt": popt,
            "pcov": pcov,
            "fit_y": ramsey_1f(x, *popt),
        })
        return result

    # try two-tone if two strong peaks exist
    f1, f2 = sorted(peak_freqs[:2])

    p0 = [A0*0.6, A0*0.4, T20, f1, f2, 0.0, 0.0, C0]
    bounds = (
        [0.0, 0.0, 1.0, 0.0, 0.0, -2*np.pi, -2*np.pi, np.min(y)-abs(A0)],
        [10*abs(A0)+1e-12, 10*abs(A0)+1e-12, 1e5, 2.0, 2.0, 2*np.pi, 2*np.pi, np.max(y)+abs(A0)]
    )

    try:
        popt2, pcov2 = curve_fit(ramsey_2f, x, y, p0=p0, bounds=bounds, maxfev=100000)
        fit2 = ramsey_2f(x, *popt2)
        rss2 = np.sum((y - fit2)**2)

        # also compare to 1-tone
        p01 = [A0, T20, f1, 0.0, C0]
        bounds1 = (
            [0.0, 1.0, 0.0, -2*np.pi, np.min(y)-abs(A0)],
            [10*abs(A0)+1e-12, 1e5, 2.0, 2*np.pi, np.max(y)+abs(A0)]
        )
        popt1, pcov1 = curve_fit(ramsey_1f, x, y, p0=p01, bounds=bounds1, maxfev=50000)
        fit1 = ramsey_1f(x, *popt1)
        rss1 = np.sum((y - fit1)**2)

        if rss2 < 0.85 * rss1:
            result.update({
                "mode": "2f",
                "popt": popt2,
                "pcov": pcov2,
                "fit_y": fit2,
                "rss1": rss1,
                "rss2": rss2,
            })
        else:
            result.update({
                "mode": "1f",
                "popt": popt1,
                "pcov": pcov1,
                "fit_y": fit1,
                "rss1": rss1,
                "rss2": rss2,
            })
        return result

    except Exception:
        # fall back to single-tone
        p01 = [A0, T20, f1, 0.0, C0]
        bounds1 = (
            [0.0, 1.0, 0.0, -2*np.pi, np.min(y)-abs(A0)],
            [10*abs(A0)+1e-12, 1e5, 2.0, 2*np.pi, np.max(y)+abs(A0)]
        )
        popt1, pcov1 = curve_fit(ramsey_1f, x, y, p0=p01, bounds=bounds1, maxfev=50000)
        result.update({
            "mode": "1f",
            "popt": popt1,
            "pcov": pcov1,
            "fit_y": ramsey_1f(x, *popt1),
        })
        return result

def ramsey_func(self, t, A, T2star, f, phi, C):
    return A * np.exp(-t / T2star) * np.cos(2 * np.pi * f * t + phi) + C

def guess_ramsey_params(x, y):
    x = np.asarray(x)
    y = np.asarray(y)

    C0 = np.mean(y)
    y0 = y - C0
    A0 = 0.5 * (np.max(y) - np.min(y))

    # crude T2* guess
    T20 = 0.5 * (x[-1] - x[0]) if x[-1] > x[0] else 1.0

    # frequency guess from FFT
    if len(x) > 1:
        dx = np.mean(np.diff(x))
        freqs = np.fft.rfftfreq(len(x), d=dx)
        fft_mag = np.abs(np.fft.rfft(y0))
        if len(freqs) > 1:
            idx = np.argmax(fft_mag[1:]) + 1  # ignore DC
            f0 = freqs[idx]
        else:
            f0 = 1.0 / (x[-1] - x[0])
    else:
        f0 = 1.0

    phi0 = 0.0
    return [A0, T20, f0, phi0, C0]

def fit_ramsey(self, x, y):
    p0 = self.guess_ramsey_params(x, y)

    bounds = (
        [-np.inf, 0, 0, -2 * np.pi, -np.inf],
        [np.inf, np.inf, np.inf, 2 * np.pi, np.inf]
    )

    popt, pcov = curve_fit(
        self.ramsey_func,
        x,
        y,
        p0=p0,
        bounds=bounds,
        maxfev=20000
    )
    return popt, pcov

def fit_magnitude_envelope(x, avgi, avgq):
    x = np.asarray(x, dtype=float)
    mag = np.abs(np.asarray(avgi) + 1j*np.asarray(avgq))

    A0 = np.max(mag) - np.min(mag)
    C0 = np.min(mag)
    T20 = max((x[-1] - x[0]) * 0.7, 1.0)

    # exponential fit
    p0e = [A0, T20, C0]
    boundse = ([0.0, 1.0, 0.0], [10*A0 + 1e-12, 1e5, np.max(mag)])
    popte, pcove = curve_fit(envelope_exp, x, mag, p0=p0e, bounds=boundse, maxfev=50000)
    fit_e = envelope_exp(x, *popte)
    rss_e = np.sum((mag - fit_e)**2)

    # gaussian fit
    p0g = [A0, T20, C0]
    boundsg = ([0.0, 1.0, 0.0], [10*A0 + 1e-12, 1e5, np.max(mag)])
    poptg, pcovg = curve_fit(envelope_gauss, x, mag, p0=p0g, bounds=boundsg, maxfev=50000)
    fit_g = envelope_gauss(x, *poptg)
    rss_g = np.sum((mag - fit_g)**2)

    if rss_g < rss_e:
        return {
            "mode": "gaussian_env",
            "mag": mag,
            "popt": poptg,
            "pcov": pcovg,
            "fit_y": fit_g,
            "rss": rss_g,
        }
    else:
        return {
            "mode": "exp_env",
            "mag": mag,
            "popt": popte,
            "pcov": pcove,
            "fit_y": fit_e,
            "rss": rss_e,
        }

class T2RProgram(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.q_rp=self.ch_page(cfg["qubit_ch"])     # get register page for qubit_ch
        self.r_wait = 3
        self.r_phase2 = 4
        self.r_phase=self.sreg(cfg["qubit_ch"], "phase")
        self.regwi(self.q_rp, self.r_wait, cfg["start"])
        self.regwi(self.q_rp, self.r_phase2, 0)

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in cfg["ro_chs"]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        # add qubit and readout pulses to respective channels

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)

        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=f_ge,
                                 phase=0, gain=cfg["pi2_gain"],
                                 waveform="qubit")
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

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
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.ro_chs,
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_wait, self.r_wait, '+', self.us2cycles(self.cfg["step"]))  # update the time between two π/2 pulses
        self.mathi(self.q_rp, self.r_phase2, self.r_phase2, '+',
                   self.cfg["phase_step"])  # advance the phase of the LO for the second π/2 pulse


class T2R(ExperimentClass):
    """
    Basic T2R
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        #### pull the data from the amp rabi sweep
        # prog = PulseProbeSpectroscopyProgram(self.soccfg, self.cfg)
        prog = T2RProgram(self.soccfg, self.cfg)

        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False,) # debug=False)
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
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
            peak_amps = np.array([
                fft_spec[np.argmin(np.abs(fft_freqs - fp))]
                for fp in fft_peaks
            ])

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
                label = (
                    f"1f fit: T2*={T2:.2f}±{dT2:.2f} us, "
                    f"f={f:.4f}±{df:.4f} MHz"
                )

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
            plt.axvline(
                dominant_fft_freq,
                linewidth=2,
                label=f"USED {dominant_fft_freq:.4f} MHz"
            )

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
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
