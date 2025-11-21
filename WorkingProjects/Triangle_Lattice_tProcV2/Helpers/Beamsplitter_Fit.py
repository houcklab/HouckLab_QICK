import numpy as np
from scipy.optimize import curve_fit

def fit_double_beamsplitter(self, Z, gains, debug_fft=False):
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

    fit_params = [None] * R
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
            fit_params[r] = None
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
            fit_params[r] = None
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

    fit = {
        "g_sorted": np.array(g_sorted),  # (G,)
        "g_dense": np.array(g_dense),  # (N_dense,)
        "contrast_norm": np.array(contrast_norm),  # (R, G) measured
        "contrast_fit": np.array(contrast_fit),  # (R, G) model on orig grid
        "contrast_fit_dense": np.array(contrast_fit_dense),  # (R, N_dense) smooth
        "fit_params": fit_params,  # list of [d,w,phi] or None
        "pi_candidates": pi_cands_per_r,
        "zero_candidates": zero_cands_per_r,
        "perrors": np.array(perr_r),
    }

    return fit


