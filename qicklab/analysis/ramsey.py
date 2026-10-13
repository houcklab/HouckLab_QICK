"""Ramsey fit models and automatic one/two-tone and envelope fits (from mT2R)."""

import numpy as np
from scipy.optimize import curve_fit
from scipy.signal import find_peaks

from qicklab.analysis.iq import rotate_iq


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
