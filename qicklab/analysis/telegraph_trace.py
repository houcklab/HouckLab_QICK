"""Showcase telegraph trace for undriven single shots: readout-dropout gate, point score, window.

Used by UndrivenSingleShot.display() to save a `_trace.png` per acquisition
(docs/experiments/undriven_single_shot.md#outputs). Nothing here feeds the saved rates.

The gate removes a periodic readout-gain dropout (2026-11-04: a ~2 Hz square wave that scales
the IQ signal by ~0.53 for ~40% of each cycle while the noise stays put). It bins |IQ| in ~1 ms
bins, looks for a Welch line in `band_hz`, refines the frequency by the folded variance, splits
the phase bins in two by 2-means on their mean IQ, and keeps the half with the larger spread,
minus one edge bin on each side. Without a line every shot is kept.
"""

import numpy as np
from scipy.signal import welch

N_PHASE = 40


def readout_dropout_gate(
    i_shots, q_shots, t_us, band_hz=(1.5, 2.5), line_ratio_min=30.0, n_phase=N_PHASE
):
    """Keep mask that drops the low-gain phase of a periodic readout dropout.

    Returns dict(keep, modulated, f0_hz, line_ratio, kept_fraction, dt_us). `keep` is all True
    when no line stands `line_ratio_min` above the 0.3-20 Hz median of the |IQ| spectrum or the
    record is too short (< 4 periods of the band's low edge).
    """
    i = np.asarray(i_shots, dtype=float).ravel()
    q = np.asarray(q_shots, dtype=float).ravel()
    t = np.asarray(t_us, dtype=float).ravel()
    n = i.size
    out = dict(
        keep=np.ones(n, bool),
        modulated=False,
        f0_hz=np.nan,
        line_ratio=np.nan,
        kept_fraction=1.0,
        dt_us=np.nan,
    )
    if n < 16:
        return out
    dt = float(np.median(np.diff(t[: min(n, 1000)])))
    out["dt_us"] = dt
    if not dt > 0:
        return out
    nb = max(1, int(round(1000.0 / dt)))  # ~1 ms bins
    nbin = n // nb
    fs = 1e6 / (dt * nb)
    if nbin * nb * dt * 1e-6 < 4.0 / band_hz[0] or nbin < 64:
        return out
    amp = np.hypot(i, q)[: nbin * nb].reshape(nbin, nb).mean(1)
    fr, p = welch(amp - amp.mean(), fs=fs, nperseg=min(nbin, int(fs * 16)))
    band = (fr > band_hz[0]) & (fr < band_hz[1])
    ref = (fr > 0.3) & (fr < 20)
    if not band.any() or not ref.any():
        return out
    f0 = float(fr[band][np.argmax(p[band])])
    floor = float(np.median(p[ref]))
    ratio = float(p[band].max() / floor) if floor > 0 else np.inf
    out["line_ratio"] = ratio

    # refine the line frequency on the binned series: maximise the folded variance
    tb = t[: nbin * nb].reshape(nbin, nb).mean(1)
    best_var, best_f = -1.0, f0
    df = 2 * (fr[1] - fr[0]) if fr.size > 1 else 0.04
    for ff in np.linspace(f0 - df, f0 + df, 161):
        bb = np.minimum(((tb * 1e-6 * ff) % 1.0 * n_phase).astype(int), n_phase - 1)
        mm = np.bincount(bb, amp, n_phase) / np.maximum(np.bincount(bb, None, n_phase), 1)
        if mm.var() > best_var:
            best_var, best_f = mm.var(), ff
    out["f0_hz"] = float(best_f)

    b = np.minimum(((t * 1e-6 * best_f) % 1.0 * n_phase).astype(int), n_phase - 1)
    cnt = np.maximum(np.bincount(b, None, n_phase), 1)
    pts = np.c_[np.bincount(b, i, n_phase) / cnt, np.bincount(b, q, n_phase) / cnt]
    # 2-means on the per-phase mean IQ (two gain levels)
    ca, cb = pts[np.argmin(pts[:, 0])], pts[np.argmax(pts[:, 0])]
    lab = np.zeros(n_phase, bool)
    for _ in range(20):
        lab = np.linalg.norm(pts - ca, axis=1) > np.linalg.norm(pts - cb, axis=1)
        if lab.all() or (~lab).all():
            break
        ca, cb = pts[~lab].mean(0), pts[lab].mean(0)
    if lab.all() or (~lab).all():
        return out
    step = float(np.linalg.norm(ca - cb))
    noise = float(np.sqrt(np.var(i) + np.var(q)))
    if not (ratio > line_ratio_min and step > 6 * noise / np.sqrt(cnt.min())):
        return out

    # full-gain half: the larger IQ spread (signal separation scales with gain, noise does not)
    def spread(bins):
        sel = np.isin(b, bins)
        return np.var(i[sel]) + np.var(q[sel])

    half_a, half_b = np.where(~lab)[0], np.where(lab)[0]
    good = half_b if spread(half_b) > spread(half_a) else half_a
    gs = set(good.tolist())
    core = [j for j in good if (j - 1) % n_phase in gs and (j + 1) % n_phase in gs]
    keep = np.isin(b, core)
    out.update(keep=keep, modulated=True, kept_fraction=float(keep.mean()))
    return out


def fit_two_blobs_1d(x, max_points=100_000, random_state=0):
    """Two-Gaussian fit of a projection: (means, sigmas, weights) sorted by mean, or None."""
    x = np.asarray(x, dtype=float).ravel()
    x = x[np.isfinite(x)]
    if x.size < 20 or np.std(x) <= 0:
        return None
    from sklearn.mixture import GaussianMixture

    sub = x[:: max(1, x.size // max_points)].reshape(-1, 1)
    g = GaussianMixture(2, random_state=random_state).fit(sub)
    mu, sd, w = g.means_.ravel(), np.sqrt(g.covariances_.ravel()), g.weights_.ravel()
    o = np.argsort(mu)
    return mu[o], sd[o], w[o]


def trace_point_quality(i_shots, q_shots, t_us, max_shots=1_000_000, **gate_kw):
    """Gate, re-fit the IQ axis on the kept shots and score the point for a showcase trace.

    Uses the first `max_shots` shots. score = separation_sigma * 4 * w0 * w1 (separation in
    units of the mean blob sigma, as analyze_undriven_cloud; weighted by population balance).
    Returns a dict with the arrays the figure needs (i, q, t_us, keep, center, axis, z) and the
    scalars (separation_sigma, weights, means_z, sigmas_z, score, gate diagnostics);
    z = (projection - proj_mid) / proj_sigma, the projection measured from `center` along `axis`.
    """
    i = np.asarray(i_shots, dtype=float).ravel()[:max_shots]
    q = np.asarray(q_shots, dtype=float).ravel()[:max_shots]
    t = np.asarray(t_us, dtype=float).ravel()[:max_shots]
    gate = readout_dropout_gate(i, q, t, **gate_kw)
    keep = gate["keep"]
    out = dict(
        gate,
        i=i,
        q=q,
        t_us=t,
        n_used=int(i.size),
        score=0.0,
        separation_sigma=np.nan,
        weights=np.array([np.nan, np.nan]),
        means_z=np.array([np.nan, np.nan]),
        sigmas_z=np.array([np.nan, np.nan]),
        center=np.array([np.nan, np.nan]),
        axis=np.array([np.nan, np.nan]),
        z=np.full(i.size, np.nan),
    )
    if keep.sum() < 20:
        return out
    ik, qk = i[keep], q[keep]
    center = np.array([np.median(ik), np.median(qk)])
    ev, evec = np.linalg.eigh(np.cov(np.vstack([ik, qk])))
    axis = evec[:, int(np.argmax(ev))]
    if axis[0] < 0:
        axis = -axis
    proj = (i - center[0]) * axis[0] + (q - center[1]) * axis[1]
    out.update(center=center, axis=axis)
    fit = fit_two_blobs_1d(proj[keep])
    if fit is None:
        return out
    mu, sd, w = fit
    sig = float(np.mean(sd))
    if not sig > 0:
        return out
    sep = float(abs(mu[1] - mu[0]) / sig)
    mid = 0.5 * (mu[0] + mu[1])
    out.update(
        z=(proj - mid) / sig,
        means_z=(mu - mid) / sig,
        sigmas_z=sd / sig,
        weights=w,
        separation_sigma=sep,
        score=float(sep * 4 * w[0] * w[1]),
        proj_mid=float(mid),
        proj_sigma=sig,
    )
    return out


def _hysteresis_states(x, thr):
    s = np.empty(x.size, np.int8)
    cur = 1 if x.size and x[0] > 0 else 0
    for j, v in enumerate(x):
        if cur == 0 and v > thr:
            cur = 1
        elif cur == 1 and v < -thr:
            cur = 0
        s[j] = cur
    return s


def pick_trace_window(
    t_us, z, keep, separation_sigma, window_ms=20.0, smooth_us=250.0, target_switches=8
):
    """Choose a `window_ms` stretch of kept, gap-free shots that shows the telegraph well.

    z is the projection in units of the blob sigma with the blobs at +-separation/2. Windows step
    by ~1 ms; each is scored 4 f (1 - f) exp(-((n - target) / 4)^2), f the occupancy of the upper
    state and n the number of switches of a hysteresis-thresholded `smooth_us` moving average.
    Returns dict(start, n_shots, smooth_shots, smoothed) with start None if no window fits.
    """
    t = np.asarray(t_us, dtype=float)
    z = np.asarray(z, dtype=float)
    keep = np.asarray(keep, bool)
    dt = float(np.median(np.diff(t[: min(t.size, 1000)]))) if t.size > 1 else np.nan
    out = dict(start=None, n_shots=0, smooth_shots=1, smoothed=z)
    if not dt > 0 or not np.isfinite(separation_sigma):
        return out
    w = int(round(window_ms * 1000.0 / dt))
    k = max(1, int(round(smooth_us / dt)))
    zf = np.where(np.isfinite(z), z, 0.0)
    zs = np.convolve(zf, np.ones(k) / k, mode="same")
    out.update(n_shots=w, smooth_shots=k, smoothed=zs)
    if w < 2 or z.size <= w:
        return out
    states = _hysteresis_states(zs, 0.35 * separation_sigma / 2)
    best, best_score = None, -1.0
    for s0 in range(0, z.size - w, max(1, int(round(1000.0 / dt)))):
        if not keep[s0 : s0 + w].all() or (t[s0 + w - 1] - t[s0]) > 1.05 * window_ms * 1000.0:
            continue
        seg = states[s0 : s0 + w]
        f = float(seg.mean())
        n_sw = int(np.count_nonzero(np.diff(seg)))
        score = 4 * f * (1 - f) * np.exp(-(((n_sw - target_switches) / 4.0) ** 2))
        if score > best_score:
            best, best_score = s0, score
    out["start"] = best
    return out
