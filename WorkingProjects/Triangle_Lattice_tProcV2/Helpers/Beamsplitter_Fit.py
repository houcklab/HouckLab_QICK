import numpy as np
from numpy import nan
from scipy.optimize import curve_fit
from scipy.ndimage import gaussian_filter1d
from scipy.signal import argrelmin, argrelmax

def fit_double_beamsplitter(Z, gains, debug_fft=False):
    """
    Compute contrast(gain), fit to sqrt(cos^2(w x + phi) + d^2 sin^2(w x + phi)),
    and store all the fit parameters, candidates, and error.

    Fitting strategy:
      - No smoothing on the data used for the fit - I found this actually ruins the fit.
      - If there are too few gain points, we densify by inserting midpoints.
      - We do a multi-start fit over several candidate w0 values instead of relying
        on FFT for the initial frequency guess. Sometimes FFT is good sometimes bad.
      - FFT (if debug_fft=True) is only used for visualization, not necessarily the actual guess.
    """
    R, G, T = Z.shape

    # Sort gains
    order = np.argsort(gains)
    g_sorted = gains[order]
    g0, g1 = float(g_sorted[0]), float(g_sorted[-1])
    span = max(g1 - g0, 1.0)

    # The model itself
    def model(x, dpar, w, phi):
        return np.sqrt(
            np.cos(w * x + phi) ** 2 +
            (dpar ** 2) * np.sin(w * x + phi) ** 2
        )

    # Densification Midpoint-interpolator helper: insert midpoints between existing x's
    def densify_midpoints(x, y, factor=2):
        """ Returns x_dense, y_dense, is_original_mask """
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        n = x.size
        if n < 2 or factor <= 1:
            return x, y, np.ones_like(x, dtype=bool)

        xs = [x[0]]
        ys = [y[0]]
        mask = [True]

        for i in range(n - 1):
            x0, x1 = x[i], x[i + 1]
            y0, y1 = y[i], y[i + 1]
            dx = x1 - x0
            dy = y1 - y0

            # insert factor-1 evenly spaced points between x0 and x1
            for k in range(1, factor):
                alpha = k / factor
                xs.append(x0 + alpha * dx)
                ys.append(y0 + alpha * dy)
                mask.append(False)  # artificial

            xs.append(x1)
            ys.append(y1)
            mask.append(True)  # original

        xs = np.array(xs, float)
        ys = np.array(ys, float)
        mask = np.array(mask, bool)
        return xs, ys, mask

    # Bounds on parameters
    bounds = ([0.0, 0.0, -np.pi], [1.0, np.inf, np.pi])
    # Measured contrast aligned to g_sorted
    contrast_sorted = (Z.max(axis=2) - Z.min(axis=2))[:, order]  # (R, G)
    # Outputs for plotting/lines on original gain grid
    contrast_norm = np.full_like(contrast_sorted, np.nan, dtype=float)  # (R, G)
    contrast_fit = np.full_like(contrast_sorted, np.nan, dtype=float)  # (R, G)
    # Outputs for smooth plotting on a dense gain grid (used for smooth fit plot)
    N_dense = max(200, 5 * G)  # 200 points or 5x oversampling, whichever is larger
    g_dense = np.linspace(g0, g1, N_dense)
    contrast_fit_dense = np.full((R, N_dense), np.nan, dtype=float)  # (R, N_dense)

    fit_params = [nan] * R
    pi_cands_per_r, zero_cands_per_r, perr_r = [], [], []

    # Densification settings
    min_points_for_fit = 100  # if G < this, densify with midpoints, I set to some arbitrary parameter
    densify_factor = 2  # 2 means 1 midpoint between each pair

    # Precompute FFT ingredients once per readout IF desired for debug
    def compute_fft(x, y):
        """
        Computes FFT for debugging
        Returns: xf, yf, f_dom  (freq axis, spectrum, dominant frequency)
        """
        G_local = x.size
        if G_local < 2:
            return None, None, None

        x_uniform = np.linspace(g0, g1, G_local)
        y_uniform = np.interp(x_uniform, x, y - np.mean(y))

        N_fft = int(2 ** np.ceil(np.log2(G_local)))
        yf = np.fft.rfft(y_uniform, n=N_fft)
        xf = np.fft.rfftfreq(N_fft, d=(x_uniform[1] - x_uniform[0]))

        if len(xf) <= 1:
            return xf, yf, None

        idx_peak = 1 + np.argmax(np.abs(yf[1:]))
        f_dom = xf[idx_peak]
        return xf, yf, f_dom

    # Performinmg actual fitting on each dataset
    for r in range(R):
        c = contrast_sorted[r]  # (G,)

        # Normalize measured contrast to [0,1]
        cmin, cmax = float(np.min(c)), float(np.max(c))
        if cmax - cmin <= 0:
            # Degenerate trace – nothing to fit
            fit_params[r] = nan
            contrast_fit[r] = np.full_like(c, np.nan, dtype=float)
            contrast_norm[r] = np.zeros_like(c, dtype=float)
            pi_cands_per_r.append([])
            zero_cands_per_r.append([])
            perr_r.append(np.array([np.nan, np.nan, np.nan]))
            continue

        c_norm = (c - cmin) / (cmax - cmin)
        contrast_norm[r] = c_norm  # store what we actually measured

        # Decide whether to densify
        if G < min_points_for_fit:
            x_fit, y_fit, is_orig = densify_midpoints(g_sorted, c_norm, factor=densify_factor)
        else:
            x_fit, y_fit = g_sorted, c_norm
            is_orig = np.ones_like(g_sorted, dtype=bool)

        # IMPORTANT SECTION: Initial Guesses

        # Multi-start: several candidate frequencies based on span
        # base frequency scale -> π / span
        base_w = np.pi / span if span > 0 else 1.0
        xf, yf, f_dom = compute_fft(g_sorted, c_norm)  # FFT based guess

        # A small set of candidate w0 values
        w_candidates = [
            0.5 * base_w,
            1.0 * base_w,
            2.0 * base_w,
            4.0 * base_w,
            2.0 * np.pi * f_dom,  # This is the guess from FFT
        ]
        # ensure positivity
        w_candidates = [w for w in w_candidates if w > 0]
        # We’ll also try a few phi0 values
        phi_candidates = [0.0, np.pi / 4, -np.pi / 4]
        best_popt = None
        best_pcov = None
        best_resid = np.inf

        # Try multiple initial guesses, keep the one with the smallest residual
        for w0 in w_candidates:
            for phi0 in phi_candidates:
                p0 = [0.5, w0, phi0]
                try:
                    popt, pcov = curve_fit(model, x_fit, y_fit, p0=p0, bounds=bounds, maxfev=20000)
                    # compute residual on original gain points to compare
                    y_model_orig = model(g_sorted, *popt)
                    resid = np.sum((y_model_orig - c_norm) ** 2)
                    if resid < best_resid and np.isfinite(resid):
                        best_resid = resid
                        best_popt = popt
                        best_pcov = pcov
                except Exception:
                    continue

        if best_popt is None:
            # All fits failed: fall back to simple max/min indicators
            fit_params[r] = nan
            contrast_fit[r] = np.full_like(c_norm, np.nan, dtype=float)

            idx_max = int(np.argmax(c_norm))
            idx_min = int(np.argmin(c_norm))
            pi_cands_per_r.append([float(g_sorted[idx_max])])
            zero_cands_per_r.append([float(g_sorted[idx_min])])
            perr_r.append(np.array([np.nan, np.nan, np.nan]))
            continue

        # Successful best fit
        fit_params[r] = best_popt
        # model evaluated on original gain grid (for consistency)
        contrast_fit[r] = model(g_sorted, *best_popt)
        # Model evaluated on dense grid (for smooth plotting)
        contrast_fit_dense[r] = model(g_dense, *best_popt)

        perr = np.sqrt(np.diag(best_pcov)) if best_pcov is not None else np.array(
            [np.nan, np.nan, np.nan]
        )
        perr_r.append(perr)

        # -----------------------------
        # DEBUG PLOT (WITH ARTIFICIAL POINTS SHOWN) + FFT
        # -----------------------------
        if debug_fft and r == 0:
            dpar_fit, w_fit, phi_fit = best_popt
            f_fit = w_fit / (2.0 * np.pi)

            fig_fft, (ax_sig, ax_spec) = plt.subplots(2, 1, figsize=(6, 5))

            # Top: contrast vs gain
            # original points
            ax_sig.plot(g_sorted, c_norm, "o", ms=4,
                        label="contrast (orig)")
            # artificial densified points (if any)
            if x_fit.size > g_sorted.size:
                x_art = x_fit[~is_orig]
                y_art = y_fit[~is_orig]
                ax_sig.plot(x_art, y_art, "x", ms=4,
                            label="contrast (interp)")

            # fitted curve on the original x-grid
            ax_sig.plot(g_sorted, contrast_fit[r], "--", lw=1.5,
                        label="fit (model)")
            ax_sig.set_xlabel("Gain")
            ax_sig.set_ylabel("Contrast (norm)")
            ax_sig.set_title("Contrast vs gain (r=0)")
            ax_sig.legend(loc="best", fontsize=8)

            # Bottom: |FFT| vs frequency (debug only)
            if xf is not None and yf is not None:
                ax_spec.plot(xf, np.abs(yf), "-", lw=1.0, label="|FFT|")
                if f_dom is not None:
                    ax_spec.axvline(f_dom, color="r", ls="--",
                                    label=f"FFT peak f={f_dom:.3g}")
                ax_spec.axvline(f_fit, color="k", ls=":",
                                label=f"fit w/2π={f_fit:.3g}")
                ax_spec.set_xlabel("Frequency (cycles per gain-unit)")
                ax_spec.set_ylabel("|FFT|")
                ax_spec.set_title("FFT of contrast (r=0)")
                ax_spec.legend(loc="best", fontsize=8)
            else:
                ax_spec.text(0.5, 0.5, "FFT not available (too few points)",
                             ha="center", va="center", transform=ax_spec.transAxes)
                ax_spec.set_axis_off()

            fig_fft.tight_layout()

        # -----------------------------
        # Extracting Candidate π / 0 points from the fit
        # -----------------------------
        dpar, w, phi = fit_params[r]

        def candidates(phase_target):
            xs = []
            if w <= 0:
                return xs
            n_start = int(np.floor((w * g0 + phi - phase_target) / np.pi)) - 1
            n_end = int(np.ceil((w * g1 + phi - phase_target) / np.pi)) + 1
            for n in range(n_start, n_end + 1):
                x = (phase_target - phi + n * np.pi) / w
                if g0 - 1e-9 <= x <= g1 + 1e-9:
                    xs.append(float(x))
            return xs

        pi_cands = candidates(0.0)  # maxima (pi)
        zero_cands = candidates(np.pi / 2)  # minima (pi/2)

        pi_cands_per_r.append(pi_cands)
        zero_cands_per_r.append(zero_cands)

    def make_homogenous_nan(lst):
        max_len = max(len(x) for x in lst) if lst else 0
        return np.array([x + [nan] * (max_len - len(x)) for x in lst])

    fit = {
        "g_sorted": np.array(g_sorted),  # (G,)
        "g_dense": np.array(g_dense),  # (N_dense,)
        "contrast_norm": np.array(contrast_norm),  # (R, G) measured
        "contrast_fit": np.array(contrast_fit),  # (R, G) model on orig grid
        "contrast_fit_dense": np.array(contrast_fit_dense),  # (R, N_dense) smooth
        "fit_params": fit_params,  # list of [d,w,phi] or None
        "pi_candidates": make_homogenous_nan(pi_cands_per_r),
        "zero_candidates": make_homogenous_nan(zero_cands_per_r),
        "perrors": np.array(perr_r),
    }

    return fit


def fit_beamsplitter_offset(Z, offsets, wait_times, debug=False):
    """
    Fit beamsplitter offset data:
    1. Find first column with good oscillations
    2. For readout 0: use first dark blot center as zero
       For readout 1: use first bright blot center as zero
    3. Fit sine function
    4. Extract π/2, π, 2π points after zero
    """
    R, O, T = Z.shape

    # Handle offsets - ensure it's an array
    if np.ndim(offsets) == 0:
        offsets = np.array([offsets])

    if O < 2:
        print(f"Warning: Need at least 2 offset points for fitting, got {O}")
        return {
            "offset_sorted": offsets,
            "error": "Insufficient offset points"
        }

    # Sort offsets
    order = np.argsort(offsets)
    offset_sorted = offsets[order]
    o0, o1 = float(offset_sorted[0]), float(offset_sorted[-1])
    span = max(o1 - o0, 1.0)

    # Create dense grid for smooth plotting
    offset_dense = np.linspace(o0, o1, 500)

    # Sine model with exponential decay envelope for dephasing
    def sine_model(x, A, w, phi, offset, gamma):
        return A * np.exp(-gamma * (x - o0)) * np.sin(w * x + phi) + offset

    # Storage for results
    fit_params = [nan] * R
    contrast_norm = [nan] * R
    contrast_fit_dense = [nan] * R
    best_wait_idx_per_r = []
    zero_point_offsets = []
    zero_point_waits = []
    twopi_cands_per_r = []
    pi_cands_per_r = []
    pihalf_cands_per_r = []
    perr_r = []

    # Find the first column with good oscillations (shared across readouts)
    # Use average contrast across readouts to find best column
    avg_contrasts = np.zeros(T)
    for r in range(R):
        Z_r = Z[r, order, :][:]  # Manually skip first rows since those usually bad
        contrasts = np.max(Z_r, axis=0) - np.min(Z_r, axis=0)
        avg_contrasts += contrasts
    avg_contrasts /= R

    # Find first column with significant contrast
    # Look for first column that has contrast > XX% of max contrast
    max_contrast = np.max(avg_contrasts)
    threshold = 0.85 * max_contrast

    first_col_idx = None
    for t in range(T):
        if avg_contrasts[t] >= threshold:
            first_col_idx = t
            break

    if first_col_idx is None:
        # Fallback: use column with max contrast
        first_col_idx = int(np.argmax(avg_contrasts))

    if debug:
        print(f"\nFirst column with oscillations: index {first_col_idx}, wait time {wait_times[first_col_idx]:.2f}")

    # Process each readout
    for r in range(R):
        Z_r = Z[r, order, :]  # (O, T) - reordered by offset

        # Use the first column with oscillations
        best_wait_idx = first_col_idx
        best_wait_idx_per_r.append(best_wait_idx)

        # Extract the column data
        column_data = Z_r[:, best_wait_idx]  # (O,)

        # Normalize to [0, 1]
        cmin, cmax = float(np.min(column_data)), float(np.max(column_data))
        if cmax - cmin <= 0:
            # Degenerate trace
            fit_params[r] = nan
            contrast_norm[r] = np.zeros_like(column_data, dtype=float)
            contrast_fit_dense[r] = np.full_like(offset_dense, np.nan, dtype=float)
            zero_point_offsets.append(nan)
            zero_point_waits.append(nan)
            twopi_cands_per_r.append([])
            pi_cands_per_r.append([])
            pihalf_cands_per_r.append([])
            perr_r.append(np.array([np.nan, np.nan, np.nan, np.nan, np.nan]))
            continue

        c_norm = (column_data - cmin) / (cmax - cmin)
        contrast_norm[r] = c_norm

        # Initial guesses for sine fit
        A_guess = 1
        offset_guess = 0.5
        gamma_guess = 0.01  # Small decay rate

        # Estimate frequency by counting oscillations (peaks/valleys)
        smoothed_for_freq = gaussian_filter1d(c_norm, sigma=2.0) if len(c_norm) > 5 else c_norm
        order_freq = max(2, len(c_norm) // 15)
        n_minima = len(argrelmin(smoothed_for_freq, order=order_freq)[0])
        n_maxima = len(argrelmax(smoothed_for_freq, order=order_freq)[0])
        n_extrema = n_minima + n_maxima

        # Number of periods ≈ number of extrema / 2
        n_periods = max(1, n_extrema / 2.0)
        w_guess = 2 * np.pi * n_periods / span

        if debug and r == 0:
            print(f"  Frequency estimate: {n_extrema} extrema -> {n_periods:.1f} periods -> w={w_guess:.4f}")

        # Phase guess: assume first minimum is near the start
        phi_guess = -np.pi / 2 - w_guess * o0

        # Multiple initial guesses
        w_candidates = [w_guess * 0.5, w_guess, w_guess * 1.5, w_guess * 2]
        phi_candidates = [phi_guess, phi_guess + np.pi / 4, phi_guess - np.pi / 4, 0, -np.pi / 2]
        gamma_candidates = [0.0, 0.001, 0.01, 0.05]  # Different decay rates

        # Bounds: (A, w, phi, offset, gamma)
        # gamma >= 0 (no negative decay), upper bound allows strong decay
        bounds = ([0, 0, -10 * np.pi, -1, 0], [2, np.inf, 10 * np.pi, 2, 1.0])

        best_popt = None
        best_pcov = None
        best_resid = np.inf

        for w0 in w_candidates:
            for phi0 in phi_candidates:
                for gamma0 in gamma_candidates:
                    p0 = [A_guess, w0, phi0, offset_guess, gamma0]
                    try:
                        popt, pcov = curve_fit(sine_model, offset_sorted, c_norm,
                                               p0=p0, bounds=bounds, maxfev=20000)
                        y_model = sine_model(offset_sorted, *popt)
                        resid = np.sum((y_model - c_norm) ** 2)
                        if resid < best_resid and np.isfinite(resid):
                            best_resid = resid
                            best_popt = popt
                            best_pcov = pcov
                    except Exception:
                        continue

        if best_popt is None:
            # Fit failed
            fit_params[r] = nan
            contrast_fit_dense[r] = np.full_like(offset_dense, np.nan, dtype=float)
            zero_point_offsets.append(nan)
            zero_point_waits.append(nan)
            twopi_cands_per_r.append([])
            pi_cands_per_r.append([])
            pihalf_cands_per_r.append([])
            perr_r.append(np.array([np.nan, np.nan, np.nan, np.nan, np.nan]))
            continue

        # Successful fit
        fit_params[r] = best_popt
        contrast_fit_dense[r] = sine_model(offset_dense, *best_popt)

        perr = np.sqrt(np.diag(best_pcov)) if best_pcov is not None else np.array(
            [np.nan, np.nan, np.nan, np.nan, np.nan]
        )
        perr_r.append(perr)

        A, w, phi, offset_param, gamma = best_popt

        if debug:
            print(f"\nReadout {r}:")
            print(
                f"  Fit params: A={A:.4f}, w={w:.4f}, phi={phi:.4f}, offset={offset_param:.4f}, gamma={gamma:.4f}")

        # Simple approach: use origin as t=0
        zero_offset = o0
        zero_wait = wait_times[best_wait_idx]
        zero_point_offsets.append(zero_offset)
        zero_point_waits.append(zero_wait)

        # Calculate phase at origin
        phase_at_zero = w * zero_offset + phi

        # Find π/2, π, and 2π by adding phase increments
        def find_offset_at_phase(target_phase):
            """Find offset where phase equals target_phase"""
            if w <= 0:
                return None
            offset = (target_phase - phi) / w
            if o0 <= offset <= o1:
                return float(offset)
            return None

        pihalf_offset = find_offset_at_phase(phase_at_zero + np.pi / 2)
        pi_offset = find_offset_at_phase(phase_at_zero + np.pi)
        twopi_offset = find_offset_at_phase(phase_at_zero + 2 * np.pi)

        if debug:
            print(f"  Zero point (origin): offset={zero_offset:.2f}")
            if pihalf_offset:
                print(f"  π/2 point: offset={pihalf_offset:.2f}")
            if pi_offset:
                print(f"  π point: offset={pi_offset:.2f}")
            if twopi_offset:
                print(f"  2π point: offset={twopi_offset:.2f}")

        pihalf_cands = [pihalf_offset] if pihalf_offset is not None else []
        pi_cands = [pi_offset] if pi_offset is not None else []
        twopi_cands = [twopi_offset] if twopi_offset is not None else []

        pihalf_cands_per_r.append(pihalf_cands)
        pi_cands_per_r.append(pi_cands)
        twopi_cands_per_r.append(twopi_cands)

    def make_homogenous_nan(lst):
        max_len = max(len(x) for x in lst) if lst else 0
        return np.array([x + [nan] * (max_len - len(x)) for x in lst])

    fit = {
        "offset_sorted":  np.array(offset_sorted),  # (O,)
        "offset_dense":  np.array(offset_dense),  # (N_dense,)
        "best_wait_idx": np.array(best_wait_idx_per_r, dtype=int),  # (R,)
        "zero_point_offsets":  np.array(zero_point_offsets),  # (R,)
        "zero_point_waits":  np.array(zero_point_waits),  # (R,)
        "contrast_norm": np.array(contrast_norm),  # (R, O)
        "contrast_fit_dense": np.array(contrast_fit_dense),  # (R, N_dense)
        "fit_params": fit_params,  # (R, 5) with NaN rows where fit failed
        "twopi_candidates": make_homogenous_nan(twopi_cands_per_r),  # (R,)
        "pi_candidates": make_homogenous_nan(pi_cands_per_r),  # (R,)
        "pihalf_candidates": make_homogenous_nan(pihalf_cands_per_r),  # (R,)
        "perrors": np.array(perr_r),  # (R, 5)
    }

    return fit



