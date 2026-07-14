"""
Flux -> qubit-frequency model for a flux-tunable (asymmetric-SQUID) transmon,
plus the forward evaluator and a numeric local inverse (freq -> voltage).

Ported from the QUA repo:
  - LabCode/Helpers/fit_functions.py::flux_tunable_transmon_frequency
  - LabCode/Control/Flux_Tunable/flux_predistortion.py::_estimate_fit_frequency_ghz_array
                                                         _frequency_to_local_flux_branch

FLUX_FIT_PARAMS convention (matches TLSSpectroscopy.py):
    [EJmax (GHz), Ec (GHz), period (V), phase_offset (V), d, tilt (GHz/V, optional)]

Pure numpy; unit-tested without hardware.
"""

import numpy as np
from scipy.optimize import curve_fit


def flux_tunable_transmon_frequency(x, EJmax, Ec, period_volts, phase_offset_volts, d):
    """f(V) in GHz for an asymmetric-SQUID transmon.

    phase   = pi * (V - phase_offset) / period
    EJ_eff  = EJmax * sqrt(cos^2(phase) + d^2 * sin^2(phase))
    f       = sqrt(8 * EJ_eff * Ec) - Ec
    """
    x = np.asarray(x, dtype=float)
    phase = np.pi * (x - phase_offset_volts) / period_volts
    e_j_eff = EJmax * np.sqrt(np.cos(phase) ** 2 + d ** 2 * np.sin(phase) ** 2)
    return np.sqrt(8.0 * e_j_eff * Ec) - Ec


def _coerce_params(flux_fit_params):
    """Accept a 5- or 6-tuple/list or a dict -> (EJmax, Ec, period, offset, d, tilt)."""
    if isinstance(flux_fit_params, dict):
        p = flux_fit_params
        return (float(p['EJmax']), float(p['Ec']), float(p['period_volts']),
                float(p['phase_offset_volts']), float(p['d']),
                float(p.get('tilt_slope', 0.0)))
    vals = [float(v) for v in flux_fit_params]
    if len(vals) == 5:
        vals = vals + [0.0]
    if len(vals) != 6:
        raise ValueError("flux_fit_params must have 5 or 6 elements "
                         "[EJmax, Ec, period, offset, d, (tilt)]")
    return tuple(vals)


def estimate_fit_frequency_ghz_array(flux_fit_params, dc_offsets):
    """Vectorized qubit frequency (GHz) at each DC voltage, including the tilt term."""
    EJmax, Ec, period, offset, d, tilt = _coerce_params(flux_fit_params)
    dc = np.asarray(dc_offsets, dtype=float)
    base = flux_tunable_transmon_frequency(dc, EJmax, Ec, period, offset, d)
    return base + tilt * dc


def estimate_fit_frequency_ghz(flux_fit_params, dc_offset):
    """Scalar convenience wrapper for :func:`estimate_fit_frequency_ghz_array`."""
    return float(estimate_fit_frequency_ghz_array(flux_fit_params, np.array([float(dc_offset)]))[0])


def frequency_to_local_flux_branch(flux_fit_params, freq_ghz, baseline_v, target_v,
                                   fine_points=200001):
    """Invert the transmon spectrum on the LOCAL monotonic branch between two
    voltages (baseline -> target).

    The spectrum is many-to-one globally, so we restrict to the branch spanned by
    [baseline_v, target_v], build a dense monotone lookup of f(V) there, and
    interpolate V(f).  Returns an array of effective voltages the same shape as
    ``freq_ghz``.  Used by step 3 to convert a measured f_q(t) trace back to an
    effective flux voltage before solving the predistortion.
    """
    lo, hi = (baseline_v, target_v) if baseline_v <= target_v else (target_v, baseline_v)
    if hi <= lo:
        hi = lo + 1e-9
    v_grid = np.linspace(lo, hi, int(fine_points))
    f_grid = estimate_fit_frequency_ghz_array(flux_fit_params, v_grid)
    # make f monotone-increasing in the interp domain
    if f_grid[-1] < f_grid[0]:
        f_grid = f_grid[::-1]
        v_grid = v_grid[::-1]
    freq = np.asarray(freq_ghz, dtype=float)
    return np.interp(freq, f_grid, v_grid, left=v_grid[0], right=v_grid[-1])


def flux_fit_params_to_notebook(flux_fit_params):
    """Convert [EJmax, Ec, period, offset, d, tilt] -> the notebook fit convention
    [f_max_GHz, E_C_GHz, d, V_period_V, V_sweet_V] used by the ...FromFit T1 sizing.
    (Mirrors TLSSpectroscopy._flux_fit_params_to_notebook.)"""
    EJmax, Ec, period, offset, d, _tilt = _coerce_params(flux_fit_params)
    f_max_ghz = np.sqrt(8.0 * EJmax * Ec) - Ec
    return [f_max_ghz, Ec, d, period, offset]


def notebook_to_flux_fit_params(f_max_ghz, Ec, d, period_v, sweet_v):
    """Inverse of :func:`flux_fit_params_to_notebook` -> canonical FLUX_FIT_PARAMS."""
    EJmax = (f_max_ghz + Ec) ** 2 / (8.0 * Ec)
    return [EJmax, Ec, period_v, sweet_v, d, 0.0]


def build_freq_uniform_dc_vec(dc_min, dc_max, freq_step_hz, flux_fit_params,
                              fine_points=200001):
    """A DC-voltage sweep whose points are (approximately) UNIFORM in qubit
    frequency, using the flux fit -- so a TLS T1-vs-flux scan spends equal effort
    per MHz.  Mirrors TLSSpectroscopy._build_freq_uniform_dc_vec.
    """
    dc_min, dc_max, freq_step_hz = float(dc_min), float(dc_max), float(freq_step_hz)
    if dc_max <= dc_min:
        raise ValueError("dc_max must be greater than dc_min")
    if freq_step_hz <= 0:
        raise ValueError("freq_step_hz must be positive")
    v_fine = np.linspace(dc_min, dc_max, int(fine_points))
    f_hz = estimate_fit_frequency_ghz_array(flux_fit_params, v_fine) * 1e9
    cum = np.concatenate([[0.0], np.cumsum(np.abs(np.diff(f_hz)))])
    total = float(cum[-1])
    if total <= 0:
        raise ValueError("Flux fit gives no frequency variation over [dc_min, dc_max].")
    targets = np.arange(0.0, total + 0.5 * freq_step_hz, freq_step_hz)
    if targets[-1] < total - 1e-6:
        targets = np.append(targets, total)
    dc_vec = np.interp(targets, cum, v_fine)
    return np.unique(np.round(dc_vec, 9))


def fit_qubit_freq_vs_flux(dc_vec, freq_ghz, p0=None):
    """Least-squares fit of measured f01(V) to the transmon model.  Returns
    (FLUX_FIT_PARAMS[EJmax,Ec,period,offset,d,tilt=0], perr) or (None, None).

    A robust global fit (the QUA ridge-tracker + annealed fit) is out of scope
    here; this is a direct curve_fit that works well once the qubit trace has
    been extracted per flux point.
    """
    x = np.asarray(dc_vec, dtype=float)
    y = np.asarray(freq_ghz, dtype=float)
    good = np.isfinite(x) & np.isfinite(y)
    x, y = x[good], y[good]
    if x.size < 6:
        return None, None
    if p0 is None:
        f_max = float(np.max(y))
        Ec0 = 0.2
        EJmax0 = (f_max + Ec0) ** 2 / (8.0 * Ec0)
        offset0 = float(x[np.argmax(y)])
        span = float(x[-1] - x[0]) or 1.0
        p0 = [EJmax0, Ec0, 2.0 * abs(span), offset0, 0.1]
    try:
        popt, pcov = curve_fit(flux_tunable_transmon_frequency, x, y, p0=p0, maxfev=40000)
        perr = np.sqrt(np.diag(pcov))
        return list(popt) + [0.0], list(perr) + [0.0]
    except (RuntimeError, ValueError):
        return None, None
