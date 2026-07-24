import numpy as np
from scipy.optimize import curve_fit


def flux_tunable_transmon_frequency(x, EJmax, Ec, period_volts, phase_offset_volts, d):
    x = np.asarray(x, dtype=float)
    phase = np.pi * (x - phase_offset_volts) / period_volts
    e_j_eff = EJmax * np.sqrt(np.cos(phase) ** 2 + d ** 2 * np.sin(phase) ** 2)
    return np.sqrt(8.0 * e_j_eff * Ec) - Ec


def _coerce_params(flux_fit_params):
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
    EJmax, Ec, period, offset, d, tilt = _coerce_params(flux_fit_params)
    dc = np.asarray(dc_offsets, dtype=float)
    base = flux_tunable_transmon_frequency(dc, EJmax, Ec, period, offset, d)
    return base + tilt * dc


def estimate_fit_frequency_ghz(flux_fit_params, dc_offset):
    return float(estimate_fit_frequency_ghz_array(flux_fit_params, np.array([float(dc_offset)]))[0])


def frequency_to_local_flux_branch(flux_fit_params, freq_ghz, baseline_v, target_v,
                                   fine_points=200001):
    lo, hi = (baseline_v, target_v) if baseline_v <= target_v else (target_v, baseline_v)
    if hi <= lo:
        hi = lo + 1e-9
    v_grid = np.linspace(lo, hi, int(fine_points))
    f_grid = estimate_fit_frequency_ghz_array(flux_fit_params, v_grid)
    if f_grid[-1] < f_grid[0]:
        f_grid = f_grid[::-1]
        v_grid = v_grid[::-1]
    freq = np.asarray(freq_ghz, dtype=float)
    return np.interp(freq, f_grid, v_grid, left=v_grid[0], right=v_grid[-1])


def flux_fit_params_to_notebook(flux_fit_params):
    EJmax, Ec, period, offset, d, _tilt = _coerce_params(flux_fit_params)
    f_max_ghz = np.sqrt(8.0 * EJmax * Ec) - Ec
    return [f_max_ghz, Ec, d, period, offset]


def notebook_to_flux_fit_params(f_max_ghz, Ec, d, period_v, sweet_v):
    EJmax = (f_max_ghz + Ec) ** 2 / (8.0 * Ec)
    return [EJmax, Ec, period_v, sweet_v, d, 0.0]


def build_freq_uniform_dc_vec(dc_min, dc_max, freq_step_hz, flux_fit_params,
                              fine_points=200001):
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
