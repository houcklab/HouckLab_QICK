"""
Fit models + fitters for the TLS spectroscopy pipeline (pure numpy / scipy).

Ported from the QUA repo's LabCode/Helpers/fit_functions.py, trimmed to what the
six TLS steps actually use, and wrapped in convenience ``fit_*`` helpers that
return ``(params_dict, perr_dict)`` so the QICK ExperimentClass ``analyze`` methods
stay short.  Everything here is host-side numpy and unit-tested without hardware.
"""

import numpy as np
from scipy.optimize import curve_fit


# --------------------------------------------------------------------------- #
#  Model functions
# --------------------------------------------------------------------------- #
def exp_decay(t, P0, P1, T1):
    """T1 relaxation: population(t) = P0 + (P1 - P0) * exp(-t / T1)."""
    return P0 + (P1 - P0) * np.exp(-t / T1)


def exponential_1(x, a, b, c):
    """a*exp(-x/b) + c  (b == T1)."""
    return a * np.exp(-x / b) + c


def decaying_cosine(x, a, freq, phase_deg, offset, T2):
    """Ramsey / decaying Rabi: a*exp(-x/T2)*cos(2*pi*freq*x + phase) + offset."""
    return a * np.exp(-x / T2) * np.cos(2 * np.pi * freq * x + phase_deg * np.pi / 180.0) + offset


def lorentzian(x, f0, fwhm, amp, offset):
    """Symmetric Lorentzian peak (amp>0) / dip (amp<0)."""
    return offset + amp / (1.0 + (2.0 * (x - f0) / fwhm) ** 2)


def asymmetric_lorentzian_peak(x, ofs, height, phi, fr, fwhm):
    """Resonator S21 log-magnitude (dB), asymmetric (Fano) Lorentzian.

    20*log10|1 + height*exp(i*phi)/(1 + 2i*(x-fr)/fwhm)| + ofs
    """
    z = 1.0 + height * np.exp(1j * phi) / (1.0 + 2j * (x - fr) / fwhm)
    return 20.0 * np.log10(np.abs(z)) + ofs


# --------------------------------------------------------------------------- #
#  Fitters (return dicts so callers don't juggle positional params)
# --------------------------------------------------------------------------- #
def fit_T1(t_us, y, require_monotone=False):
    """Fit an exponential T1 decay.  Returns (params, perr).

    params: {'P0','P1','T1'} in the units of ``t_us`` for T1.
    Returns (None, None) if the fit fails or there are < 4 finite points.
    """
    t = np.asarray(t_us, dtype=float)
    y = np.asarray(y, dtype=float)
    good = np.isfinite(t) & np.isfinite(y)
    t, y = t[good], y[good]
    if t.size < 4:
        return None, None
    ymin, ymax = float(np.min(y)), float(np.max(y))
    # seed T1 from the time to fall to ~1/e of the span
    span = ymax - ymin
    if span <= 0:
        return None, None
    try:
        half = t[np.argmin(np.abs(y - (ymin + span / np.e)))]
        t1_seed = max(half, (t[-1] - t[0]) / 5.0, 1e-3)
        p0 = [ymin, ymax, t1_seed]
        bounds = ([-0.5, -0.5, 1e-3], [1.5, 1.5, 1e9])
        popt, pcov = curve_fit(exp_decay, t, y, p0=p0, bounds=bounds, maxfev=20000)
        perr = np.sqrt(np.diag(pcov))
        return ({'P0': popt[0], 'P1': popt[1], 'T1': popt[2]},
                {'P0': perr[0], 'P1': perr[1], 'T1': perr[2]})
    except (RuntimeError, ValueError):
        return None, None


def fit_spec_dip(freq, amp, kind='auto'):
    """Locate a qubit-spectroscopy feature (dip or peak) with a Lorentzian.

    Returns (params, perr) with params {'f0','fwhm','amp','offset'}; f0 in the
    units of ``freq``.  Falls back to argmin/argmax if the fit fails.
    """
    f = np.asarray(freq, dtype=float)
    a = np.asarray(amp, dtype=float)
    good = np.isfinite(f) & np.isfinite(a)
    f, a = f[good], a[good]
    if f.size < 5:
        return None, None
    offset = float(np.median(a))
    dip_depth = offset - float(np.min(a))
    peak_height = float(np.max(a)) - offset
    if kind == 'auto':
        kind = 'dip' if dip_depth >= peak_height else 'peak'
    if kind == 'dip':
        f0_seed = f[np.argmin(a)]
        amp_seed = -max(dip_depth, 1e-9)
    else:
        f0_seed = f[np.argmax(a)]
        amp_seed = max(peak_height, 1e-9)
    span = float(f[-1] - f[0]) or 1.0
    p0 = [f0_seed, abs(span) / 10.0, amp_seed, offset]
    try:
        popt, pcov = curve_fit(lorentzian, f, a, p0=p0, maxfev=20000)
        perr = np.sqrt(np.diag(pcov))
        return ({'f0': popt[0], 'fwhm': abs(popt[1]), 'amp': popt[2], 'offset': popt[3]},
                {'f0': perr[0], 'fwhm': perr[1], 'amp': perr[2], 'offset': perr[3]})
    except (RuntimeError, ValueError):
        return {'f0': float(f0_seed), 'fwhm': abs(span) / 10.0,
                'amp': amp_seed, 'offset': offset}, None


def fit_resonator_dip(freq, mag_db):
    """Fit resonator |S21| in dB with the asymmetric Lorentzian; returns fr (same
    units as ``freq``) in params['fr'].  Falls back to argmin."""
    f = np.asarray(freq, dtype=float)
    m = np.asarray(mag_db, dtype=float)
    good = np.isfinite(f) & np.isfinite(m)
    f, m = f[good], m[good]
    if f.size < 5:
        return None, None
    ofs = float(np.median(m))
    fr_seed = f[np.argmin(m)]
    depth_lin = 10 ** ((float(np.min(m)) - ofs) / 20.0) - 1.0  # negative
    span = float(f[-1] - f[0]) or 1.0
    p0 = [ofs, depth_lin, 0.0, fr_seed, abs(span) / 10.0]
    try:
        popt, pcov = curve_fit(asymmetric_lorentzian_peak, f, m, p0=p0, maxfev=20000)
        perr = np.sqrt(np.diag(pcov))
        keys = ['ofs', 'height', 'phi', 'fr', 'fwhm']
        return (dict(zip(keys, popt)), dict(zip(keys, perr)))
    except (RuntimeError, ValueError):
        return {'ofs': ofs, 'height': depth_lin, 'phi': 0.0,
                'fr': float(fr_seed), 'fwhm': abs(span) / 10.0}, None


def fit_ramsey(t_us, y, detuning_seed=1.0):
    """Fit a decaying cosine (Ramsey).  params: {'A','freq','phase','offset','T2'}.
    ``freq`` in cycles per unit of ``t_us``; T2 in the same units as ``t_us``."""
    t = np.asarray(t_us, dtype=float)
    y = np.asarray(y, dtype=float)
    good = np.isfinite(t) & np.isfinite(y)
    t, y = t[good], y[good]
    if t.size < 5:
        return None, None
    a_seed = (np.max(y) - np.min(y)) / 2.0
    off_seed = float(np.mean(y))
    t2_seed = (t[-1] - t[0]) / 2.0 if t[-1] > t[0] else 1.0
    p0 = [a_seed, detuning_seed, 0.0, off_seed, t2_seed]
    try:
        popt, pcov = curve_fit(decaying_cosine, t, y, p0=p0, maxfev=20000)
        perr = np.sqrt(np.diag(pcov))
        keys = ['A', 'freq', 'phase', 'offset', 'T2']
        return (dict(zip(keys, popt)), dict(zip(keys, perr)))
    except (RuntimeError, ValueError):
        return None, None


def cosine_vs_flux(x, amplitude, frequency, phi, offset):
    """Resonator-dip-vs-flux periodicity: amplitude*cos(2*pi*frequency*x+phi)+offset."""
    return amplitude * np.cos(2 * np.pi * frequency * x + phi) + offset


def fit_cosine_vs_flux(dc, dip):
    """Fit resonator dip frequency vs flux voltage with a cosine.  Returns
    (params, perr) with {'amplitude','frequency','phi','offset'} (frequency in 1/V)."""
    x = np.asarray(dc, dtype=float)
    y = np.asarray(dip, dtype=float)
    good = np.isfinite(x) & np.isfinite(y)
    x, y = x[good], y[good]
    if x.size < 4:
        return None, None
    y0 = y - np.mean(y)
    # seed period from the dominant FFT bin of the (nonuniform-tolerant) trace
    amp_seed = (np.max(y) - np.min(y)) / 2.0 or 1.0
    span = float(x[-1] - x[0]) or 1.0
    freq_seed = 1.0 / span
    try:
        fft = np.abs(np.fft.rfft(y0))
        freqs = np.fft.rfftfreq(x.size, d=abs(span) / max(x.size - 1, 1))
        if fft.size > 1:
            freq_seed = max(freqs[1 + np.argmax(fft[1:])], 1e-6)
    except Exception:
        pass
    p0 = [amp_seed, freq_seed, 0.0, float(np.mean(y))]
    try:
        popt, pcov = curve_fit(cosine_vs_flux, x, y, p0=p0, maxfev=20000)
        perr = np.sqrt(np.diag(pcov))
        keys = ['amplitude', 'frequency', 'phi', 'offset']
        return (dict(zip(keys, popt)), dict(zip(keys, perr)))
    except (RuntimeError, ValueError):
        return None, None
