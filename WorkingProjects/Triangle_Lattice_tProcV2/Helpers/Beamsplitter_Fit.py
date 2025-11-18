import numpy as np
from scipy.optimize import curve_fit

def fit_double_beamsplitter(Z, gains):
    """
    Compute contrast(gain), fit to sqrt(cos^2(w x + phi) + d^2 sin^2(w x + phi)),
    and store:
      - contrast_norm (measured, normalized to [0,1]) at g_sorted
      - contrast_fit  (model evaluated at g_sorted)
      - pi_candidates and zero_candidates inside the sweep window
    """
    R, G, T = Z.shape

    # Sort gains once for stability
    order = np.argsort(gains)
    g_sorted = gains[order]
    g0, g1 = float(g_sorted[0]), float(g_sorted[-1])
    span = max(g1 - g0, 1.0)

    # Model
    def model(x, dpar, w, phi):
        return np.sqrt(np.cos(w * x + phi) ** 2 + (dpar ** 2) * np.sin(w * x + phi) ** 2)

    # Seeds & bounds (simple, robust)
    p0 = [0.5, np.pi / span, 0.0]  # ~half-period over the span
    bounds = ([0.0, 0.0, -np.pi], [1.0, np.inf, np.pi])

    # Measured contrast aligned to g_sorted
    contrast_sorted = (Z.max(axis=2) - Z.min(axis=2))[:, order]  # (R, G)

    # Outputs for plotting/lines
    contrast_norm = np.full_like(contrast_sorted, np.nan, dtype=float)  # (R, G)
    contrast_fit = np.full_like(contrast_sorted, np.nan, dtype=float)  # (R, G)
    fit_params = [None] * R
    pi_cands_per_r, zero_cands_per_r, perr_r = [], [], []

    for r in range(R):
        c = contrast_sorted[r]  # (G,)

        # Normalize measured contrast to [0,1]
        cmin, cmax = float(np.min(c)), float(np.max(c))
        c_norm = (c - cmin) / (cmax - cmin)
        c_norm_extra = np.convolve(c_norm, np.ones(5) / 5, mode='same')

        # Fit to the normalized contrast
        try:
            popt, pcov = curve_fit(model, g_sorted, c_norm_extra, p0=p0, bounds=bounds, maxfev=20000)
            fit_params[r] = popt
            contrast_fit[r] = model(g_sorted, *popt)
            perr = np.sqrt(np.diag(pcov))
        except Exception:
            # Fit failed → fall back to one empirical max/min so you still see lines
            fit_params[r] = None
            contrast_fit[r] = np.full_like(c_norm, np.nan, dtype=float)

            idx_max = int(np.argmax(c_norm))
            idx_min = int(np.argmin(c_norm))
            pi_cands_per_r.append([float(g_sorted[idx_max])])
            zero_cands_per_r.append([float(g_sorted[idx_min])])

            contrast_norm[r] = c_norm
            continue

        # Generate all model candidates in [g0, g1]
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

        pi_cands = candidates(0.0)  # maxima (π)
        zero_cands = candidates(np.pi / 2)  # minima (π/2)

        pi_cands_per_r.append(pi_cands)
        zero_cands_per_r.append(zero_cands)
        contrast_norm[r] = c_norm
        perr_r.append(perr)

    fit = {
        'g_sorted': np.array(g_sorted),  # (G,)
        'contrast_norm': np.array(contrast_norm),  # (R, G) normalized measured
        'contrast_fit': np.array(contrast_fit),  # (R, G) fitted values
        'fit_params': fit_params,  # list of [d,w,phi] or None
        'pi_candidates': pi_cands_per_r,  # list[list[float]] per readout
        'zero_candidates': zero_cands_per_r,  # list[list[float]] per readout
        'perrors': np.array(perr_r),
    }
    return fit