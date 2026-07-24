import numpy as np
from scipy import optimize, signal
from scipy.signal import savgol_filter, medfilt
from scipy.ndimage import gaussian_filter

STRIPE_EXCESS_DB = 1.2
STRIPE_BASELINE_MEDIAN_PTS = 51
STRIPE_EXPAND_PTS = 9
EMISSION_SMOOTH_SIGMA_FREQ_PX = 1.0
EMISSION_SMOOTH_SIGMA_DC_PX = 0.8
DP_LAMBDA = 0.001
DP_MAX_JUMP_MHZ = 50.0
LOCAL_FIT_HALF_WINDOW_MHZ = 20.0
MIN_FWHM_MHZ = 0.30
MAX_FWHM_MHZ = 70.0
CONFIDENCE_THR_DB = 0.8
SCAN_EDGE_MARGIN_GHZ = 0.02
MAX_REASONABLE_PER_STEP_MHZ = 50.0
EC_INIT_GRID_GHZ = (0.10, 0.15, 0.18, 0.22, 0.25, 0.30)
TRANSMON_OUTLIER_GHZ = 0.10
TRANSMON_OUTLIER_FLOOR_GHZ = 0.025
TRANSMON_OUTLIER_SHRINK = 0.6
TRANSMON_MAX_ITER = 8
CONFIDENCE_Z_THR = 5.0
CONFIDENCE_FLOOR_DB = 0.15
DP_LAMBDA_SLOPE = 0.004

def detect_stripe_rows(magnitude_dbm):
    row_median = np.nanmedian(magnitude_dbm, axis=1)
    row_baseline = medfilt(row_median, kernel_size=STRIPE_BASELINE_MEDIAN_PTS)
    excess = row_median - row_baseline
    excess_mad = np.nanmedian(np.abs(excess - np.nanmedian(excess))) + 1e-12
    stripe = excess > min(STRIPE_EXCESS_DB, max(0.4, 5.0 * excess_mad))
    if STRIPE_EXPAND_PTS > 1:
        stripe = signal.convolve(stripe.astype(int),
                                 np.ones(STRIPE_EXPAND_PTS, dtype=int), mode="same") > 0
    return stripe, row_median, excess


def compute_emission_map(magnitude_dbm, frequency_ghz, stripe_mask):
    row_median = np.nanmedian(magnitude_dbm, axis=1)
    mag_h = magnitude_dbm - row_median[:, None]
    mag_h = mag_h - np.nanmedian(mag_h, axis=0)[None, :]
    col_mad = np.nanmedian(np.abs(mag_h - np.nanmedian(mag_h, axis=0)[None, :]), axis=0)
    col_scale = np.clip(col_mad / (np.nanmedian(col_mad) + 1e-12), 1.0, None)
    mag_h = mag_h / col_scale[None, :]
    signed = mag_h.copy()
    mag_h[stripe_mask, :] = np.nanmin(mag_h)
    emission = gaussian_filter(mag_h, sigma=(EMISSION_SMOOTH_SIGMA_FREQ_PX,
                                             EMISSION_SMOOTH_SIGMA_DC_PX))
    return emission, signed


def dp_path_through_emission(emission, frequency_ghz, dc_axis=None):
    step_mhz = float(np.nanmedian(np.diff(frequency_ghz))) * 1e3
    n_freq, n_dc = emission.shape
    dv_mv = 1.0
    if dc_axis is not None and len(dc_axis) > 1:
        dv_mv = max(float(np.nanmedian(np.abs(np.diff(dc_axis)))) * 1e3, 1e-3)
    max_jump_mhz = max(DP_MAX_JUMP_MHZ, 40.0 * dv_mv)
    max_jump_px = max(1, int(round(max_jump_mhz / step_mhz)))
    deltas = np.arange(-max_jump_px, max_jump_px + 1, dtype=np.int32)
    jump_penalty = DP_LAMBDA_SLOPE * ((deltas.astype(float) * step_mhz) / dv_mv) ** 2
    cost = np.full((n_freq, n_dc), -np.inf)
    backptr = np.zeros((n_freq, n_dc), dtype=np.int32)
    cost[:, 0] = emission[:, 0]
    for i in range(1, n_dc):
        padded = np.pad(cost[:, i - 1], max_jump_px, mode="constant", constant_values=-1e9)
        windowed = np.lib.stride_tricks.sliding_window_view(padded, 2 * max_jump_px + 1)
        candidate = windowed - jump_penalty[None, :]
        best = np.argmax(candidate, axis=1)
        cost[:, i] = emission[:, i] + candidate[np.arange(n_freq), best]
        backptr[:, i] = best - max_jump_px
    path = np.zeros(n_dc, dtype=np.int32)
    path[-1] = int(np.argmax(cost[:, -1]))
    for i in range(n_dc - 1, 0, -1):
        path[i - 1] = path[i] + backptr[path[i], i]
    return path


def lorentzian_with_slope(f_hz, offset, slope, height, center, fwhm):
    detuning = (f_hz - center) / fwhm
    return offset + slope * (f_hz - center) + height / (1.0 + 4.0 * detuning ** 2)


def subpixel_lorentzian_refit(magnitude_dbm, frequency_ghz, path_idx):
    step_hz = float(np.nanmedian(np.diff(frequency_ghz))) * 1e9
    freq_hz = frequency_ghz * 1e9
    n_freq, n_dc = magnitude_dbm.shape
    half_pts = max(15, int(round(LOCAL_FIT_HALF_WINDOW_MHZ * 1e6 / step_hz)))
    refit_ghz = np.full(n_dc, np.nan)
    refit_fwhm = np.full(n_dc, np.nan)
    refit_sign = np.zeros(n_dc, dtype=np.int8)
    for i in range(n_dc):
        j = int(path_idx[i])
        lo = max(0, j - half_pts); hi = min(n_freq, j + half_pts + 1)
        x = freq_hz[lo:hi]; y = magnitude_dbm[lo:hi, i]
        if x.size < 11:
            continue
        bg = float(np.nanmedian(y))
        sign = +1 if (np.nanmax(y) - bg) >= (bg - np.nanmin(y)) else -1
        yy = y if sign > 0 else -y
        off0 = float(np.nanmedian(np.r_[yy[:3], yy[-3:]]))
        h0 = float(max(np.nanmax(yy) - off0, 0.1))
        try:
            popt, _ = optimize.curve_fit(
                lorentzian_with_slope, x, yy,
                p0=[off0, 0.0, h0, freq_hz[j], 3e6],
                bounds=([np.nanmin(yy) - 5.0, -1e-3, 0.05, float(x[0]), MIN_FWHM_MHZ * 1e6],
                        [np.nanmax(yy) + 5.0, 1e-3, 10.0 * h0 + 2.0, float(x[-1]), MAX_FWHM_MHZ * 1e6]),
                maxfev=8000)
            if MIN_FWHM_MHZ * 1e6 <= popt[4] <= MAX_FWHM_MHZ * 1e6:
                refit_ghz[i] = popt[3] / 1e9
                refit_fwhm[i] = popt[4] / 1e6
                refit_sign[i] = sign
        except Exception:
            pass
    return refit_ghz, refit_fwhm, refit_sign

def flux_tunable_transmon_frequency_with_tilt(V, EJmax, Ec, period_volts,
                                              phase_offset_volts, d, tilt_slope):
    phase = np.pi * (np.asarray(V, dtype=float) - phase_offset_volts) / period_volts
    e_j_eff = EJmax * np.sqrt(np.cos(phase) ** 2 + d ** 2 * np.sin(phase) ** 2)
    return np.sqrt(8.0 * e_j_eff * Ec) - Ec + tilt_slope * np.asarray(V, dtype=float)


def fit_transmon_iterative(dc_axis, freq_axis):
    finite = np.isfinite(dc_axis) & np.isfinite(freq_axis)
    V = np.asarray(dc_axis)[finite]; fobs = np.asarray(freq_axis)[finite]
    if V.size < 8:
        raise RuntimeError(f"Not enough finite trace points to fit ({V.size}).")
    fmax = float(np.nanmax(fobs)); fmin = float(np.nanmin(fobs))
    V_at_max = float(V[np.nanargmax(fobs)]); V_at_min = float(V[np.nanargmin(fobs)])
    period_guess = max(2.0 * abs(V_at_max - V_at_min), 0.30)
    best = None
    for ec_g in EC_INIT_GRID_GHZ:
        EJmax_g = (fmax + ec_g) ** 2 / (8.0 * ec_g)
        EJmin_g = max((fmin + ec_g) ** 2 / (8.0 * ec_g), 1e-3)
        d_g = float(np.sqrt(min(EJmin_g / EJmax_g, 0.95)))
        p0 = [EJmax_g, ec_g, period_guess, V_at_max, d_g, 0.0]
        lb = [1e-3, 0.05, 0.20, V_at_max - 0.30, 0.01, -5.0]
        ub = [200.0, 0.45, 2.00, V_at_max + 0.30, 0.99, 5.0]
        Vi = V.copy(); fi = fobs.copy(); popt = None
        threshold = TRANSMON_OUTLIER_GHZ
        for _ in range(TRANSMON_MAX_ITER):
            try:
                res = optimize.least_squares(
                    lambda p, V=Vi, f=fi: (flux_tunable_transmon_frequency_with_tilt(V, *p) - f) / 0.005,
                    p0, bounds=(lb, ub), loss="soft_l1", f_scale=0.02, max_nfev=200_000)
            except Exception:
                break
            popt = res.x
            p0 = popt
            outliers = np.abs(fi - flux_tunable_transmon_frequency_with_tilt(Vi, *popt)) > threshold
            if outliers.sum():
                Vi, fi = Vi[~outliers], fi[~outliers]
            if Vi.size < 8:
                break
            threshold = max(threshold * TRANSMON_OUTLIER_SHRINK, TRANSMON_OUTLIER_FLOOR_GHZ)
        if popt is None:
            continue
        rms_kept = float(np.sqrt(np.mean((fi - flux_tunable_transmon_frequency_with_tilt(Vi, *popt)) ** 2)))
        resid_all = np.abs(fobs - flux_tunable_transmon_frequency_with_tilt(V, *popt))
        keep = resid_all < max(3.0 * rms_kept, TRANSMON_OUTLIER_FLOOR_GHZ)
        if keep.sum() >= 8:
            try:
                res = optimize.least_squares(
                    lambda p, Vk=V[keep], fk=fobs[keep]: (flux_tunable_transmon_frequency_with_tilt(Vk, *p) - fk) / 0.005,
                    popt, bounds=(lb, ub), loss="soft_l1", f_scale=0.02, max_nfev=200_000)
                popt = res.x
                Vi, fi = V[keep], fobs[keep]
            except Exception:
                pass
        rms = float(np.sqrt(np.mean((fi - flux_tunable_transmon_frequency_with_tilt(Vi, *popt)) ** 2)))
        if best is None or rms < best["rms"]:
            best = {"popt": popt, "rms": rms, "V_fit": Vi, "f_fit": fi, "ec_init": ec_g,
                    "n_kept": int(Vi.size), "n_dropped": int(V.size - Vi.size)}
    if best is None:
        raise RuntimeError("All transmon initial guesses failed.")
    return best


def extrema_within_range(popt, dc_lo, dc_hi):
    Vd = np.linspace(dc_lo, dc_hi, 200_001)
    fd = flux_tunable_transmon_frequency_with_tilt(Vd, *popt)
    dfd = np.gradient(fd, Vd)
    sign_change = np.where(np.diff(np.sign(dfd)) != 0)[0]
    out = []
    for k in sign_change:
        Vc = 0.5 * (Vd[k] + Vd[k + 1])
        fc = float(flux_tunable_transmon_frequency_with_tilt(np.atleast_1d(Vc), *popt)[0])
        kind = "max (upper sweet spot)" if dfd[k] > 0 else "min (lower sweet spot)"
        out.append((float(Vc), fc, kind))
    return out


def extract_confident_trace(tdc, tf, tmag):
    stripe, _, _ = detect_stripe_rows(tmag)
    emission, _ = compute_emission_map(tmag, tf, stripe)
    path_idx = dp_path_through_emission(emission, tf, tdc)
    cols = np.arange(tdc.size)
    argmax_idx = np.nanargmax(emission, axis=0)
    f_off = np.abs(tf[:, None] - tf[argmax_idx][None, :])
    bg = np.where(f_off > 0.06, emission, np.nan)
    col_med = np.nanmedian(bg, axis=0)
    col_mad = np.nanmedian(np.abs(bg - col_med[None, :]), axis=0) + 1e-9
    z_path = (emission[path_idx, cols] - col_med) / col_mad
    z_amax = (emission[argmax_idx, cols] - col_med) / col_mad
    use_amax = z_amax > np.maximum(z_path, CONFIDENCE_Z_THR)
    pick_idx = np.where(use_amax, argmax_idx, path_idx)
    dp_ghz = tf[pick_idx]
    refit_ghz, refit_fwhm, _ = subpixel_lorentzian_refit(tmag, tf, pick_idx)
    reliable = np.isfinite(refit_ghz) & (np.abs(refit_ghz - dp_ghz) * 1e3 < LOCAL_FIT_HALF_WINDOW_MHZ)
    lor_ghz = np.where(reliable, refit_ghz, dp_ghz)
    conf = emission[pick_idx, cols]
    conf_z = np.where(use_amax, z_amax, z_path)
    at_edge = (lor_ghz <= tf[0] + SCAN_EDGE_MARGIN_GHZ) | (lor_ghz >= tf[-1] - SCAN_EDGE_MARGIN_GHZ)
    confident = (conf_z > CONFIDENCE_Z_THR) & (conf > CONFIDENCE_FLOOR_DB) & ~at_edge
    trace = np.where(confident, lor_ghz, np.nan)
    return trace, confident


def fit_qubit_spec_map(dc_v, freq_ghz, mag_dbm,
                       trim_low_dc_v=0.02, trim_high_dc_v=0.0,
                       fit_dc_min_v=None, fit_dc_max_v=None,
                       trace_freq_min_ghz=None, trace_freq_max_ghz=None):
    dc_v = np.asarray(dc_v, dtype=float)
    freq_ghz = np.asarray(freq_ghz, dtype=float)
    mag_dbm = np.asarray(mag_dbm, dtype=float)
    lo = dc_v.min() if fit_dc_min_v is None else max(float(fit_dc_min_v), dc_v.min())
    hi = dc_v.max() if fit_dc_max_v is None else min(float(fit_dc_max_v), dc_v.max())
    lo = lo + float(trim_low_dc_v)
    hi = hi - float(trim_high_dc_v)
    dcm = (dc_v >= lo - 1e-9) & (dc_v <= hi + 1e-9)
    fm = np.isfinite(freq_ghz)
    if trace_freq_min_ghz is not None:
        fm &= freq_ghz >= float(trace_freq_min_ghz)
    if trace_freq_max_ghz is not None:
        fm &= freq_ghz <= float(trace_freq_max_ghz)
    if dcm.sum() < 10 or fm.sum() < 20:
        raise RuntimeError("Fit window too small after trimming.")
    tdc = dc_v[dcm]
    tf = freq_ghz[fm]
    tmag = mag_dbm[np.ix_(fm, dcm)]
    finite_cols = np.isfinite(tmag).any(axis=0)
    if not finite_cols.all():
        tdc, tmag = tdc[finite_cols], tmag[:, finite_cols]
    trace, confident = extract_confident_trace(tdc, tf, tmag)
    fit = fit_transmon_iterative(tdc, trace)
    popt = [float(x) for x in fit["popt"]]
    extrema = extrema_within_range(fit["popt"], float(lo), float(hi))
    return {
        "params": popt,
        "rms_mhz": float(fit["rms"] * 1e3),
        "n_kept": int(fit["n_kept"]),
        "n_dropped": int(fit["n_dropped"]),
        "dc": tdc,
        "trace": trace,
        "confident_frac": float(np.isfinite(trace).mean()),
        "extrema": [[float(v), float(f), str(k)] for v, f, k in extrema],
        "fit_window_v": [float(lo), float(hi)],
    }


def print_fit_report(result, label="Advanced qubit-spec fit"):
    lo, hi = result["fit_window_v"]
    print(f"{label}: RMS = {result['rms_mhz']:.2f} MHz over DC "
          f"{lo:+.4f}..{hi:+.4f} V ({result['n_kept']} pts kept, "
          f"confident fraction {result['confident_frac']:.2f})")
    if result["extrema"]:
        print("df/dV = 0 points inside the window:")
        for v, f, kind in result["extrema"]:
            print(f"    V = {v:+.5f} V,  f = {f:.5f} GHz   [{kind}]")
    else:
        print("df/dV = 0 points inside the window: none (monotonic)")
    print("paste into TLSSpectroscopy.py:")
    print("FLUX_FIT_PARAMS = [")
    for v in result["params"]:
        print(f"    {v:.12g},")
    print("]")


def save_fit_overlay_png(png_path, dc_v, freq_ghz, mag_dbm, result, title=None):
    import matplotlib.pyplot as plt
    dc_v = np.asarray(dc_v, dtype=float)
    freq_ghz = np.asarray(freq_ghz, dtype=float)
    fm = np.isfinite(freq_ghz)
    fig, ax = plt.subplots(1, 1, figsize=(11, 6), constrained_layout=True)
    mesh = ax.pcolormesh(dc_v, freq_ghz[fm], np.asarray(mag_dbm, dtype=float)[fm, :],
                         shading="auto", cmap="viridis")
    fig.colorbar(mesh, ax=ax, pad=0.015, label="Magnitude [dBm]")
    lo, hi = result["fit_window_v"]
    dense = np.linspace(lo, hi, 1500)
    ax.plot(dense, flux_tunable_transmon_frequency_with_tilt(dense, *result["params"]),
            "-", lw=2.0, color="red",
            label=f"Transmon fit (RMS {result['rms_mhz']:.1f} MHz)")
    ax.set_xlabel("DC offset [V]")
    ax.set_ylabel("Probe frequency [GHz]")
    if title:
        ax.set_title(title)
    ax.legend(loc="best", fontsize=9)
    fig.savefig(png_path, bbox_inches="tight")
    plt.close(fig)
    return png_path
