"""Ramsey fit models and automatic one/two-tone and envelope fits (T2R)."""

import numpy as np
from scipy.optimize import curve_fit
from scipy.signal import find_peaks

from qicklab.analysis.iq import principal_axis_angle


def ramsey_1f(t, A, T2, f, phi, C):
    return A * np.exp(-t / T2) * np.cos(2 * np.pi * f * t + phi) + C


def ramsey_2f(t, A1, A2, T2, f1, f2, phi1, phi2, C):
    env = np.exp(-t / T2)
    return (
        env * (A1 * np.cos(2 * np.pi * f1 * t + phi1) + A2 * np.cos(2 * np.pi * f2 * t + phi2)) + C
    )


def envelope_exp(t, A, T2, C):
    return A * np.exp(-t / T2) + C


def envelope_gauss(t, A, T2, C):
    return A * np.exp(-((t / T2) ** 2)) + C


def find_prominent_fft_peaks(t, y, prominence_frac=0.2):
    """rFFT of y - mean(y); non-DC peaks above prominence_frac x max, tallest first."""
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)

    dt = np.mean(np.diff(t))
    y0 = y - np.mean(y)

    freqs = np.fft.rfftfreq(len(t), d=dt)
    spec = np.abs(np.fft.rfft(y0))

    if len(spec) < 3:
        return freqs, spec, []

    peak_inds, props = find_peaks(spec[1:], prominence=np.max(spec[1:]) * prominence_frac)
    peak_inds = peak_inds + 1  # skipped DC

    peak_inds = sorted(peak_inds, key=lambda k: spec[k], reverse=True)
    peak_freqs = [freqs[k] for k in peak_inds]

    return freqs, spec, peak_freqs


def project_ramsey_iq(avgi, avgq, n_sign=1):
    """Project a Ramsey IQ trace onto its g-e oscillation (principal) axis.

    Returns ``(sig_rot, ang)``: ``sig_rot = (sig - mean(sig)) * exp(-1j * ang)``, so the fringe is
    in ``Re(sig_rot)`` around 0, with its sign chosen so the mean of the first ``n_sign`` points
    (t = 0, about |e>) is positive; ``ang`` (rad, in (-pi, pi]) is the axis that was projected on.
    Keep ``n_sign = 1``: the mean of the first 3 points is ~ cos x (2 cos x + 1), x = 2 pi f dt,
    which is negative for f dt in (1/4, 1/3) (2.5-3.3 MHz at dt = 0.1 us); the fit seeds phi = 0
    with A >= 0, so a wrong sign there often makes it collapse.
    """
    sig = np.asarray(avgi, dtype=float) + 1j * np.asarray(avgq, dtype=float)
    dev = sig - np.mean(sig)
    ang = principal_axis_angle(dev)
    sig_rot = dev * np.exp(-1j * ang)
    if np.mean(np.real(sig_rot[:n_sign])) < 0:
        sig_rot = -sig_rot
        ang = float(np.angle(np.exp(1j * (ang + np.pi))))
    return sig_rot, float(ang)


def ramsey_fit_limits(x):
    """(f_max, T2_min) from the sampling: Nyquist 0.5/dt (MHz) and dt/2 (us).
    Falls back to the old fixed (2.0, 1.0) when dt cannot be determined (< 2 points)."""
    x = np.asarray(x, dtype=float)
    dt = abs(float(np.mean(np.diff(x)))) if x.size > 1 else 0.0
    if not np.isfinite(dt) or dt <= 0:
        return 2.0, 1.0
    return 0.5 / dt, 0.5 * dt


def fit_ramsey_auto(x, avgi, avgq):
    """1-frequency Ramsey fit, or 2-frequency when the FFT shows two peaks and RSS2 < 0.85 RSS1,
    on the principal-axis projection of the IQ trace. Raises if curve_fit fails.
    Constants and bounds: docs/experiments/t2_ramsey.md."""
    x = np.asarray(x, dtype=float)

    sig_rot, iq_axis_rad = project_ramsey_iq(avgi, avgq)
    y = np.real(sig_rot)

    freqs, spec, peak_freqs = find_prominent_fft_peaks(x, y, prominence_frac=0.25)

    f_max, T2_min = ramsey_fit_limits(x)
    T2_max = 1e5

    C0 = np.mean(y)
    A0 = 0.5 * (np.max(y) - np.min(y))
    T20 = float(np.clip(max((x[-1] - x[0]) * 0.7, 1.0), T2_min, T2_max))

    result = {
        "mode": None,
        "sig_rot": sig_rot,
        "iq_axis_rad": iq_axis_rad,
        "fft_freqs": freqs,
        "fft_spec": spec,
        "fft_peaks": peak_freqs,
    }

    def bounds_1f():
        return (
            [0.0, T2_min, 0.0, -2 * np.pi, np.min(y) - abs(A0)],
            [10 * abs(A0) + 1e-12, T2_max, f_max, 2 * np.pi, np.max(y) + abs(A0)],
        )

    if len(peak_freqs) < 2:
        f0 = float(np.clip(peak_freqs[0] if len(peak_freqs) else 0.05, 0.0, f_max))

        p0 = [A0, T20, f0, 0.0, C0]
        popt, pcov = curve_fit(ramsey_1f, x, y, p0=p0, bounds=bounds_1f(), maxfev=50000)

        result.update(
            {
                "mode": "1f",
                "popt": popt,
                "pcov": pcov,
                "fit_y": ramsey_1f(x, *popt),
            }
        )
        return result

    f1, f2 = np.clip(sorted(peak_freqs[:2]), 0.0, f_max)

    p0 = [A0 * 0.6, A0 * 0.4, T20, f1, f2, 0.0, 0.0, C0]
    bounds = (
        [0.0, 0.0, T2_min, 0.0, 0.0, -2 * np.pi, -2 * np.pi, np.min(y) - abs(A0)],
        [
            10 * abs(A0) + 1e-12,
            10 * abs(A0) + 1e-12,
            T2_max,
            f_max,
            f_max,
            2 * np.pi,
            2 * np.pi,
            np.max(y) + abs(A0),
        ],
    )

    try:
        popt2, pcov2 = curve_fit(ramsey_2f, x, y, p0=p0, bounds=bounds, maxfev=100000)
        fit2 = ramsey_2f(x, *popt2)
        rss2 = np.sum((y - fit2) ** 2)

        p01 = [A0, T20, f1, 0.0, C0]
        popt1, pcov1 = curve_fit(ramsey_1f, x, y, p0=p01, bounds=bounds_1f(), maxfev=50000)
        fit1 = ramsey_1f(x, *popt1)
        rss1 = np.sum((y - fit1) ** 2)

        if rss2 < 0.85 * rss1:
            result.update(
                {
                    "mode": "2f",
                    "popt": popt2,
                    "pcov": pcov2,
                    "fit_y": fit2,
                    "rss1": rss1,
                    "rss2": rss2,
                }
            )
        else:
            result.update(
                {
                    "mode": "1f",
                    "popt": popt1,
                    "pcov": pcov1,
                    "fit_y": fit1,
                    "rss1": rss1,
                    "rss2": rss2,
                }
            )
        return result

    except Exception:
        p01 = [A0, T20, f1, 0.0, C0]
        popt1, pcov1 = curve_fit(ramsey_1f, x, y, p0=p01, bounds=bounds_1f(), maxfev=50000)
        result.update(
            {
                "mode": "1f",
                "popt": popt1,
                "pcov": pcov1,
                "fit_y": ramsey_1f(x, *popt1),
            }
        )
        return result


def fit_magnitude_envelope(x, avgi, avgq):
    """Exponential vs Gaussian envelope fit on |I + iQ|; the lower RSS wins."""
    x = np.asarray(x, dtype=float)
    mag = np.abs(np.asarray(avgi) + 1j * np.asarray(avgq))

    A0 = np.max(mag) - np.min(mag)
    C0 = np.min(mag)
    T20 = max((x[-1] - x[0]) * 0.7, 1.0)

    p0e = [A0, T20, C0]
    boundse = ([0.0, 1.0, 0.0], [10 * A0 + 1e-12, 1e5, np.max(mag)])
    popte, pcove = curve_fit(envelope_exp, x, mag, p0=p0e, bounds=boundse, maxfev=50000)
    fit_e = envelope_exp(x, *popte)
    rss_e = np.sum((mag - fit_e) ** 2)

    p0g = [A0, T20, C0]
    boundsg = ([0.0, 1.0, 0.0], [10 * A0 + 1e-12, 1e5, np.max(mag)])
    poptg, pcovg = curve_fit(envelope_gauss, x, mag, p0=p0g, bounds=boundsg, maxfev=50000)
    fit_g = envelope_gauss(x, *poptg)
    rss_g = np.sum((mag - fit_g) ** 2)

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
