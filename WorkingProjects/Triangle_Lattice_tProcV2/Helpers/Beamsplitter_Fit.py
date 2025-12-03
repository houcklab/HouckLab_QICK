import numpy as np
from numpy import nan
from scipy.optimize import curve_fit
from scipy.ndimage import gaussian_filter1d
from scipy.signal import argrelmin, argrelmax

def reconstruct_double_beamsplitter_fit(popt, g_sorted, gains_unsorted, Z):
    """Reconstruct all fit data from minimal saved parameters."""
    R = popt.shape[0]
    g0, g1 = float(g_sorted[0]), float(g_sorted[-1])
    g_dense = np.linspace(g0, g1, 500)

    def model(x, dpar, w, phi):
        return np.sqrt(np.cos(w * x + phi) ** 2 + (dpar ** 2) * np.sin(w * x + phi) ** 2)

    def candidates(w, phi, phase_target):
        """Find gain values where phase equals phase_target."""
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

    order = np.argsort(gains_unsorted)
    contrast_norm, contrast_fit_dense = [], []
    pi_list, zero_list = [], []

    for r in range(R):
        if np.any(np.isnan(popt[r])):
            contrast_norm.append(None)
            contrast_fit_dense.append(None)
            pi_list.append([])
            zero_list.append([])
            continue

        dpar, w, phi = popt[r]

        # Reconstruct contrast_norm
        Z_r = Z[r, order, :]
        contrast = np.max(Z_r, axis=1) - np.min(Z_r, axis=1)
        cmin, cmax = float(np.min(contrast)), float(np.max(contrast))
        c_norm = (contrast - cmin) / (cmax - cmin) if (cmax - cmin) > 0 else np.zeros_like(contrast)
        contrast_norm.append(c_norm)

        # Reconstruct dense fit
        contrast_fit_dense.append(model(g_dense, dpar, w, phi))

        # Find phase points
        pi_cands = candidates(w, phi, 0.0)
        zero_cands = candidates(w, phi, np.pi / 2)

        pi_list.append(pi_cands)
        zero_list.append(zero_cands)

    return {
        'g_dense': g_dense,
        'contrast_norm': contrast_norm,
        'contrast_fit_dense': contrast_fit_dense,
        'pi': pi_list,
        'zero': zero_list
    }

def fit_double_beamsplitter(Z, gains):
    """Fit double beamsplitter to sqrt(cos^2 + d^2 sin^2)."""
    R, G, T = Z.shape

    # Normalize gains input
    if np.ndim(gains) == 0:
        gains = np.array([gains])
    if G < 2:
        return {
            'popt': np.full((R, 3), np.nan),
            'pcov': np.full((R, 3, 3), np.nan),
            'g_sorted': gains
        }

    # Sort gains
    order = np.argsort(gains)
    g_sorted = gains[order]
    g0, g1 = float(g_sorted[0]), float(g_sorted[-1])
    span = max(g1 - g0, 1.0)

    # Model
    def model(x, dpar, w, phi):
        return np.sqrt(
            np.cos(w * x + phi)**2 +
            (dpar**2) * np.sin(w * x + phi)**2
        )

    # Allocate result arrays
    popt_array = np.full((R, 3), np.nan)
    pcov_array = np.full((R, 3, 3), np.nan)

    # Loop over readouts
    for r in range(R):
        Z_r = Z[r, order, :]
        contrast = np.max(Z_r, axis=1) - np.min(Z_r, axis=1)

        cmin, cmax = float(np.min(contrast)), float(np.max(contrast))
        if cmax - cmin <= 0:
            continue

        c_norm = (contrast - cmin) / (cmax - cmin)

        # Densify if needed
        if G < 15:
            g_dense = np.concatenate([g_sorted, (g_sorted[:-1] + g_sorted[1:]) / 2])
            c_dense = np.concatenate([c_norm, (c_norm[:-1] + c_norm[1:]) / 2])
            order_dense = np.argsort(g_dense)
            g_fit = g_dense[order_dense]
            c_fit = c_dense[order_dense]
        else:
            g_fit, c_fit = g_sorted, c_norm

        # FFT guess for w
        fft = np.fft.rfft(c_fit - np.mean(c_fit))
        freqs = np.fft.rfftfreq(len(c_fit), d=np.mean(np.diff(g_fit)))
        w_guess = 2 * np.pi * freqs[np.argmax(np.abs(fft[1:])) + 1]

        # Multi-start
        bounds = ([0, 0, -10 * np.pi], [1, np.inf, 10 * np.pi])
        best_popt, best_pcov = None, None
        best_resid = np.inf

        for d0 in [0.1, 0.5, 0.9]:
            for w0 in [w_guess * f for f in [0.5, 1, 1.5, 2]]:
                for phi0 in [0, np.pi/4, np.pi/2, -np.pi/2]:
                    try:
                        p0 = [d0, w0, phi0]
                        popt, pcov = curve_fit(
                            model, g_fit, c_fit,
                            p0=p0, bounds=bounds, maxfev=20000
                        )

                        resid = np.sum((model(g_fit, *popt) - c_fit)**2)

                        if resid < best_resid:
                            best_resid = resid
                            best_popt = popt
                            best_pcov = pcov

                    except:
                        continue

        # Save best result
        if best_popt is not None:
            popt_array[r] = best_popt
            pcov_array[r] = best_pcov

    return {
        'popt': popt_array,
        'pcov': pcov_array,
        'g_sorted': g_sorted
    }

def reconstruct_beamsplitter_offset_fit(popt, offset_sorted, best_wait_idx, wait_times, offsets_unsorted, Z):
    """Reconstruct all fit data from minimal saved parameters (simple: origin as zero)."""
    R = popt.shape[0]
    o0, o1 = float(offset_sorted[0]), float(offset_sorted[-1])
    offset_dense = np.linspace(o0, o1, 500)

    def sine_model(x, A, w, phi, offset, gamma):
        return A * np.exp(-gamma * (x - o0)) * np.sin(w * x + phi) + offset

    order = np.argsort(offsets_unsorted)
    contrast_norm, contrast_fit_dense = [], []
    zero_offsets, zero_waits = [], []
    pihalf_list, pi_list, twopi_list = [], [], []

    for r in range(R):
        if np.any(np.isnan(popt[r])):
            contrast_norm.append(None)
            contrast_fit_dense.append(None)
            zero_offsets.append(None)
            zero_waits.append(None)
            pihalf_list.append([])
            pi_list.append([])
            twopi_list.append([])
            continue

        A, w, phi, offset_param, gamma = popt[r]

        # Reconstruct contrast_norm
        Z_r = Z[r, order, :]
        col_data = Z_r[:, best_wait_idx[r]]
        cmin, cmax = float(np.min(col_data)), float(np.max(col_data))
        c_norm = (col_data - cmin) / (cmax - cmin) if (cmax - cmin) > 0 else np.zeros_like(col_data)
        contrast_norm.append(c_norm)

        # Reconstruct dense fit
        contrast_fit_dense.append(sine_model(offset_dense, A, w, phi, offset_param, gamma))

        # Simple: zero at origin
        zero_offset = o0
        zero_waits.append(wait_times[best_wait_idx[r]])
        zero_offsets.append(zero_offset)

        # Calculate phase at origin and find other points
        phase_at_zero = w * zero_offset + phi

        def find_offset_at_phase(target_phase):
            if w <= 0:
                return None
            offset = (target_phase - phi) / w
            return float(offset) if o0 <= offset <= o1 else None

        pihalf_offset = find_offset_at_phase(phase_at_zero + np.pi / 2)
        pi_offset = find_offset_at_phase(phase_at_zero + np.pi)
        twopi_offset = find_offset_at_phase(phase_at_zero + 2 * np.pi)

        pihalf_list.append([pihalf_offset] if pihalf_offset else [])
        pi_list.append([pi_offset] if pi_offset else [])
        twopi_list.append([twopi_offset] if twopi_offset else [])

    return {
        'offset_dense': offset_dense,
        'contrast_norm': contrast_norm,
        'contrast_fit_dense': contrast_fit_dense,
        'zero_offsets': zero_offsets,
        'zero_waits': zero_waits,
        'pihalf': pihalf_list,
        'pi': pi_list,
        'twopi': twopi_list
    }

def fit_beamsplitter_offset(Z, offsets, wait_times):
    """Fit sine with exponential decay to beamsplitter data."""
    R, O, T = Z.shape

    if np.ndim(offsets) == 0:
        offsets = np.array([offsets])
    if O < 2:
        return {
            'popt': np.full((R, 5), np.nan),
            'pcov': np.full((R, 5, 5), np.nan),
            'offset_sorted': offsets,
            'best_wait_idx': np.zeros(R, dtype=int)
        }

    order = np.argsort(offsets)
    offset_sorted = offsets[order]
    o0, o1 = float(offset_sorted[0]), float(offset_sorted[-1])
    span = max(o1 - o0, 1.0)

    def sine_model(x, A, w, phi, offset, gamma):
        return A * np.exp(-gamma * (x - o0)) * np.sin(w * x + phi) + offset

    # Find first column with oscillations
    avg_contrasts = np.mean(
        [np.max(Z[r, order, :], axis=0) - np.min(Z[r, order, :], axis=0) for r in range(R)],
        axis=0
    )
    threshold = 0.85 * np.max(avg_contrasts)
    first_col_idx = next(
        (t for t in range(T) if avg_contrasts[t] >= threshold),
        int(np.argmax(avg_contrasts))
    )

    popt_array = np.full((R, 5), np.nan)
    pcov_array = np.full((R, 5, 5), np.nan)
    best_wait_idx_array = np.full(R, first_col_idx, dtype=int)

    for r in range(R):
        Z_r = Z[r, order, :]
        col_data = Z_r[:, first_col_idx]

        cmin, cmax = float(np.min(col_data)), float(np.max(col_data))
        if cmax - cmin <= 0:
            continue

        c_norm = (col_data - cmin) / (cmax - cmin)

        # Estimate frequency
        smoothed = gaussian_filter1d(c_norm, sigma=2.0) if len(c_norm) > 5 else c_norm
        order_freq = max(2, len(c_norm) // 15)
        n_extrema = (
            len(argrelmin(smoothed, order=order_freq)[0]) +
            len(argrelmax(smoothed, order=order_freq)[0])
        )
        n_periods = max(1, n_extrema / 2.0)
        w_guess = 2 * np.pi * n_periods / span

        # Multi-start fit
        bounds = ([0, 0, -10 * np.pi, -1, 0],
                  [2, np.inf, 10 * np.pi, 2, 1.0])
        best_popt, best_pcov = None, None
        best_resid = np.inf

        for w0 in [w_guess * f for f in [0.5, 1, 1.5, 2]]:
            for phi0 in [-np.pi / 2 - w_guess * o0, 0, -np.pi / 2]:
                for gamma0 in [0.0, 0.01]:
                    try:
                        p0 = [0.5, w0, phi0, 0.5, gamma0]
                        popt, pcov = curve_fit(
                            sine_model,
                            offset_sorted,
                            c_norm,
                            p0=p0,
                            bounds=bounds,
                            maxfev=20000
                        )
                        resid = np.sum((sine_model(offset_sorted, *popt) - c_norm) ** 2)
                        if resid < best_resid:
                            best_resid = resid
                            best_popt = popt
                            best_pcov = pcov
                    except:
                        continue

        if best_popt is not None:
            popt_array[r] = best_popt
            pcov_array[r] = best_pcov

    return {
        'popt': popt_array,
        'pcov': pcov_array,
        'offset_sorted': offset_sorted,
        'best_wait_idx': best_wait_idx_array
    }
