"""Curve-fit models and fitters: hanger transmission, dispersive shift, Lorentzian features,
Rabi cosine, single-shot pi-gain contrast."""

import warnings

import numpy as np
from scipy.optimize import OptimizeWarning, curve_fit, least_squares


def hanger_model_db(f, f0, Qtot, Qext, asym, offset):
    """Hanger |S21| in dB (MATLAB-style model): f, f0 in the same units; Qtot, Qext; asymmetry
    ``asym``; vertical ``offset`` in dB."""
    numerator = (Qtot / Qext) - 2j * Qtot * asym / (f0 * 2 * np.pi)
    denominator = 1 + 2j * Qtot * (f - f0) / f0
    s21 = 1 - numerator / denominator
    return 20 * np.log10(np.abs(s21)) + offset


def hanger_model_db_qint(f, f0, Qint, Qext, asym, offset):
    """``hanger_model_db`` parameterised by (Qint, Qext), with Qtot = 1/(1/Qint + 1/Qext) derived.

    The parameterisation ``fit_hanger_transmission`` fits in: positive Qint and Qext force
    Qtot/Qext < 1, so the magnitude-only fit cannot reach the unphysical Qtot > Qext twin of a
    dip (|S21| is invariant under Qtot/Qext -> 2 - Qtot/Qext)."""
    Qtot = 1.0 / (1.0 / Qint + 1.0 / Qext)
    return hanger_model_db(f, f0, Qtot, Qext, asym, offset)


HANGER_START_RATIO_LIMITS = (0.01, 0.99)  # Qtot/Qext of the start point
HANGER_NOISE_FLOOR = 1e-2  # |S21| floor (relative to the fitted baseline) of the dB noise model


def _hanger_edge_db(ydata):
    """Off-resonant level in dB: mean of the medians of the first and last tenth (>= 3 points)."""
    n = max(3, len(ydata) // 10)
    return 0.5 * (np.median(ydata[:n]) + np.median(ydata[-n:]))


def hanger_startpoint(freq, ydata):
    """Start point [f0, Qtot, Qext, asym, offset] for a hanger dip in ``ydata`` (dB) on ``freq``.

    f0 = the lowest point; Qtot = max(|f0| / (span/10), 1e3); offset = the edge level
    (``_hanger_edge_db``); Qext from the dip depth below that level,
    Qext = Qtot / (1 - 10^(-depth_dB/20)), with Qtot/Qext clipped to HANGER_START_RATIO_LIMITS
    (so Qint = Qtot Qext/(Qext - Qtot) is finite and positive); asym = 0."""
    freq = np.asarray(freq, dtype=float)
    ydata = np.asarray(ydata, dtype=float)
    idx_min = int(np.argmin(ydata))
    f0 = float(freq[idx_min])
    span = float(np.max(freq) - np.min(freq))
    qtot = max(abs(f0) / max(span / 10, 1e-6), 1e3)
    offset = float(_hanger_edge_db(ydata))
    depth_db = offset - float(ydata[idx_min])
    ratio = float(np.clip(1.0 - 10 ** (-depth_db / 20), *HANGER_START_RATIO_LIMITS))
    return [f0, qtot, qtot / ratio, 0.0, offset]


def _qint_start(startpoint, lower, upper):
    """Convert a [f0, Qtot, Qext, asym, offset] start point to [f0, Qint, Qext, asym, offset].

    A start with Qtot >= Qext is reflected to its |S21| twin Qtot/Qext -> 2 - Qtot/Qext, the
    ratio clipped to HANGER_START_RATIO_LIMITS; every value is then clipped inside the bounds."""
    f0, qtot, qext, asym, offset = (float(v) for v in startpoint)
    ratio = qtot / qext
    if ratio >= 1.0:
        ratio = 2.0 - ratio
    ratio = float(np.clip(ratio, *HANGER_START_RATIO_LIMITS))
    p0 = np.array([f0, qtot / (1.0 - ratio), qtot / ratio, asym, offset])
    lower, upper = np.asarray(lower, dtype=float), np.asarray(upper, dtype=float)
    inset = 1e-9 * (upper - lower)
    return np.clip(p0, lower + inset, upper - inset)


def _hanger_covariance(freq, ydata, popt_q):
    """Covariance of the unweighted dB least-squares estimate ``popt_q`` under Gaussian IQ noise.

    The noise of a dB point is proportional to 1/|S21| (|S21| of the fitted model relative to its
    baseline, floored at HANGER_NOISE_FLOOR), so the plain (J^T J)^-1 s^2 of an unweighted fit
    is wrong near a deep dip. Sandwich estimator A J^T diag(s^2 sigma^2) J A, A = (J^T J)^-1,
    with s^2 = sum((r/sigma)^2)/(N - 5); J by central differences, the f0 step 1e-6 linewidths
    (|f0|/Qtot; a step relative to |f0| would span a sizeable part of a high-Q dip) and the
    others 1e-6 relative. inf if J^T J is singular."""
    freq = np.asarray(freq, dtype=float)
    popt_q = np.asarray(popt_q, dtype=float)
    steps = 1e-6 * np.maximum(np.abs(popt_q), 1.0)
    qtot = 1.0 / (1.0 / popt_q[1] + 1.0 / popt_q[2])
    steps[0] = 1e-6 * max(abs(popt_q[0]) / qtot, np.finfo(float).tiny)
    jac = np.empty((freq.size, popt_q.size))
    for k, h in enumerate(steps):
        p_hi, p_lo = popt_q.copy(), popt_q.copy()
        p_hi[k] += h
        p_lo[k] -= h
        jac[:, k] = (hanger_model_db_qint(freq, *p_hi) - hanger_model_db_qint(freq, *p_lo)) / (
            p_hi[k] - p_lo[k]
        )
    y_model = hanger_model_db_qint(freq, *popt_q)
    sigma = 1.0 / np.maximum(10 ** ((y_model - popt_q[4]) / 20), HANGER_NOISE_FLOOR)
    resid = np.asarray(ydata, dtype=float) - y_model
    s2 = np.sum((resid / sigma) ** 2) / max(freq.size - popt_q.size, 1)
    try:
        bread = np.linalg.inv(jac.T @ jac)
    except np.linalg.LinAlgError:
        return np.full((popt_q.size, popt_q.size), np.inf)
    return bread @ (jac.T * (s2 * sigma**2)) @ jac @ bread


def fit_hanger_transmission(freq, amp_linear=None, amp_db=None, startpoint=None, bounds=None):
    """Fit the hanger model to ``amp_linear`` (converted to dB) or ``amp_db``.

    Fits ``hanger_model_db_qint`` in (f0, Qint, Qext, asym, offset), Qint and Qext > 0, so
    Qtot = 1/(1/Qint + 1/Qext) < Qext always (the |S21|-identical Qtot > Qext branch is not
    reachable). ``startpoint`` is [f0, Qtot, Qext, asym, offset] (default ``hanger_startpoint``);
    ``bounds`` apply to (f0, Qint, Qext, asym, offset) (default: f0 in the swept range, Qint and
    Qext in [1e2, 1e9], asym in [-1e7, 1e7], offset in [-200, 200] dB). The fit is unweighted
    in dB (a 1/|S21|-weighted fit lets an unmodelled background tilt pull it onto a broad Fano
    shape away from the dip); its covariance is ``_hanger_covariance`` (dB noise ~ 1/|S21|).

    Returns dict: popt [f0, Qtot, Qext, asym, offset] (for ``hanger_model_db``), pcov and perr
    in that layout (propagated from the fit's full covariance), model (``hanger_model_db``),
    popt_qint / pcov_qint (the fitted (f0, Qint, Qext, asym, offset) and its covariance), Qint,
    Qint_err, Qext_err, Qtot_err, kappa_tot = |f0|/Qtot and kappa_ext = |f0|/Qext (freq units)
    with kappa_tot_err and kappa_ext_err; every error from the full covariance."""
    freq = np.asarray(freq)

    if amp_db is None:
        if amp_linear is None:
            raise ValueError("Provide either amp_linear or amp_db.")
        ydata = 20 * np.log10(np.asarray(amp_linear))
    else:
        ydata = np.asarray(amp_db)

    if startpoint is None:
        startpoint = hanger_startpoint(freq, ydata)

    if bounds is None:
        bounds = ([np.min(freq), 1e2, 1e2, -1e7, -200], [np.max(freq), 1e9, 1e9, 1e7, 200])

    p0 = _qint_start(startpoint, *bounds)

    popt_q, _ = curve_fit(hanger_model_db_qint, freq, ydata, p0=p0, bounds=bounds, maxfev=200000)
    pcov_q = _hanger_covariance(freq, ydata, popt_q)

    f0_fit, Qint_fit, Qext_fit, asym_fit, offset_fit = popt_q
    Qtot_fit = 1.0 / (1.0 / Qint_fit + 1.0 / Qext_fit)
    popt = np.array([f0_fit, Qtot_fit, Qext_fit, asym_fit, offset_fit])

    # Jacobian of (f0, Qtot, Qext, asym, offset) and of (kappa_tot, kappa_ext) w.r.t. the fit's
    # (f0, Qint, Qext, asym, offset); errors from the full covariance (Qint, Qext and f0 are
    # correlated, so the diagonal alone misstates the derived errors).
    jac = np.eye(5)
    jac[1, 1] = (Qtot_fit / Qint_fit) ** 2
    jac[1, 2] = (Qtot_fit / Qext_fit) ** 2
    pcov = jac @ pcov_q @ jac.T
    perr = np.sqrt(np.diag(pcov))

    sign_f0 = np.sign(f0_fit)
    kappa_tot = abs(f0_fit) / Qtot_fit
    kappa_ext = abs(f0_fit) / Qext_fit
    jac_kappa = np.zeros((2, 5))
    jac_kappa[0, :3] = [sign_f0 / Qtot_fit, -abs(f0_fit) / Qint_fit**2, -abs(f0_fit) / Qext_fit**2]
    jac_kappa[1, [0, 2]] = [sign_f0 / Qext_fit, -abs(f0_fit) / Qext_fit**2]
    kappa_err = np.sqrt(np.diag(jac_kappa @ pcov_q @ jac_kappa.T))

    return {
        "popt": popt,
        "perr": perr,
        "pcov": pcov,
        "model": hanger_model_db,
        "popt_qint": popt_q,
        "pcov_qint": pcov_q,
        "Qint": Qint_fit,
        "Qint_err": float(np.sqrt(pcov_q[1, 1])),
        "Qext_err": float(perr[2]),
        "Qtot_err": float(perr[1]),
        "kappa_tot": kappa_tot,
        "kappa_ext": kappa_ext,
        "kappa_tot_err": float(kappa_err[0]),
        "kappa_ext_err": float(kappa_err[1]),
    }


def hanger_s21(f, fr, kappa, depth, asym):
    """Complex hanger S21 relative to the off-resonant line, in linewidth form:
    ``1 - (depth - 1j*asym) / (1 + 2j*(f - fr)/kappa)``.

    ``kappa`` is the FWHM of the |S21|^2 dip (= fr/Qtot, units of f), ``depth`` = Qtot/Qext
    (= kappa_ext/kappa), ``asym`` the dimensionless Fano asymmetry (``hanger_model_db``'s asym
    times Qtot/(pi f0)). No phase or delay factor: those are common to any mixture of states."""
    return 1.0 - (depth - 1j * asym) / (1.0 + 2j * (np.asarray(f) - fr) / kappa)


def dispersive_mixture_magnitude(f, fr, kappa, depth, asym, delta, p, amp):
    """|S21| of a readout of a qubit in |e> with probability ``p``:
    ``amp * |(1 - p) S(f; fr) + p S(f; fr + delta)|``, S = ``hanger_s21`` (shared kappa, depth,
    asym). The two state responses add as complex amplitudes at each point (the averaged IQ is
    the population-weighted mean), so the mixture is not a weighted sum of magnitudes."""
    return amp * np.abs(
        (1.0 - p) * hanger_s21(f, fr, kappa, depth, asym)
        + p * hanger_s21(f, fr + delta, kappa, depth, asym)
    )


CHI_FIT_PARAMS = ("fr", "kappa", "depth", "asym", "delta", "a", "b", "amp")
CHI_FIT_A_BOUNDS = (0.0, 0.5)  # excited population of the no-pi trace (thermal)
CHI_FIT_B_BOUNDS = (0.5, 1.0)  # excited population of the pi trace
CHI_FIT_B_SEEDS = (0.5, 0.9)
CHI_FIT_A_SEED = 0.02
CHI_FIT_MIN_DEPTH_SIGMAS = 6.0  # ok needs the fitted g dip >= 6 x the residual rms
CHI_FIT_MIN_DELTA_SIGMAS = 2.0  # 'resolved' flags |delta| >= 2 x its standard error (not in ok)
CHI_FIT_MIN_PI_POPULATION = 0.6  # b below this: the caller warns of a bad pi pulse
CHI_FIT_MAX_NFEV = 500  # per start; a fit to a real dip converges in ~20 evaluations


def _chi_fit_result(freq, popt, perr, redchi2=np.nan, ok=True, error=None):
    fr, kappa, depth, asym, delta, a, b, amp = popt
    resolved = bool(ok and abs(delta) >= CHI_FIT_MIN_DELTA_SIGMAS * perr[4])

    def curve(p):
        if not np.all(np.isfinite(popt)):
            return np.full(np.shape(freq), np.nan)
        return dispersive_mixture_magnitude(freq, fr, kappa, depth, asym, delta, p, amp)

    return {
        "ok": ok,
        "error": error,
        "resolved": resolved,
        "popt": popt,
        "perr": perr,
        "delta": float(delta),
        "delta_err": float(perr[4]),
        "fr": float(fr),
        "fr_err": float(perr[0]),
        "kappa": float(kappa),
        "kappa_err": float(perr[1]),
        "a": float(a),
        "a_err": float(perr[5]),
        "b": float(b),
        "b_err": float(perr[6]),
        "redchi2": float(redchi2),
        "yfit_g": curve(a),
        "yfit_pi": curve(b),
    }


def _chi_fit_failed(freq, error):
    nan = np.full(len(CHI_FIT_PARAMS), np.nan)
    return _chi_fit_result(freq, nan, nan, ok=False, error=error)


def _power_fwhm(freq, amp, idx, baseline):
    """Width of the contiguous run around ``idx`` below half the |S21|^2 dip (linear ``amp``,
    off-resonant level ``baseline``): point count times the grid step."""
    step = float(np.median(np.abs(np.diff(freq))))
    beyond = amp <= np.sqrt(0.5 * (baseline**2 + amp[idx] ** 2))
    lo = hi = idx
    while lo > 0 and beyond[lo - 1]:
        lo -= 1
    while hi < amp.size - 1 and beyond[hi + 1]:
        hi += 1
    return (hi - lo + 1) * step


def fit_dispersive_shift(freq, amp_g, amp_pi):
    """Joint fit of the no-pi (``amp_g``) and pi-pulsed (``amp_pi``) |S21| traces on ``freq``
    for the dispersive shift delta = f_e - f_g (= 2 chi); docs/experiments/chi_shift.md#analysis.

    Both traces are ``dispersive_mixture_magnitude`` with shared fr, kappa, depth, asym, delta
    and amp; the excited weight is ``a`` in CHI_FIT_A_BOUNDS for the g trace (thermal
    population) and ``b`` in CHI_FIT_B_BOUNDS for the pi trace (pi infidelity, decay before and
    during the readout). Magnitudes, not complex IQ: each point and state is a separately
    compiled program, so no phase reference is shared between them. Unweighted least squares on
    f - (centre of the sweep); seeds fr = g argmin, kappa = |S21|^2 FWHM of the g dip, depth from
    the g minimum, asym 0, a = CHI_FIT_A_SEED, b in CHI_FIT_B_SEEDS, delta in {d, 2d, -2d}
    (d = pi argmin - g argmin; +-kappa/2 when d = 0); the lowest cost wins. Covariance
    (J^T J)^-1 times the reduced chi-square.

    Never raises: returns {ok, error, resolved, popt (CHI_FIT_PARAMS order, fr on the freq
    axis), perr, delta, delta_err, fr, fr_err, kappa, kappa_err, a, a_err, b,
    b_err, redchi2, yfit_g, yfit_pi (on freq)}. delta is f_e - f_g (= 2chi); there is
    deliberately no chi / chi_err key, so ``*_err`` always means the error of delta, as the h5
    ``chi_fit`` / ``chi_err`` fields of ChiShift do. ``ok`` is False (reason in ``error``) when the
    inputs are unusable, the optimiser fails from every start, an error is not finite, fr or
    kappa ends on a bound, or the fitted g dip is under CHI_FIT_MIN_DEPTH_SIGMAS residual rms;
    popt is kept when a fit exists. ``resolved`` (ok and |delta| >= CHI_FIT_MIN_DELTA_SIGMAS
    delta_err) is information only and deliberately not part of ``ok``: gating on it would
    keep only the fits that scattered away from zero, so a small shift would be overestimated
    whenever it passes and replaced by a fallback whenever it does not. An ok fit with
    resolved False is still the least biased estimate of delta; its error says how well."""
    freq = np.asarray(freq, dtype=float).ravel()
    amp_g = np.asarray(amp_g, dtype=float).ravel()
    amp_pi = np.asarray(amp_pi, dtype=float).ravel()
    n_par = len(CHI_FIT_PARAMS)
    if not freq.size == amp_g.size == amp_pi.size:
        return _chi_fit_failed(freq, "freq / trace length mismatch")
    if 2 * freq.size <= n_par + 2:
        return _chi_fit_failed(freq, f"too few points ({freq.size}) for a {n_par}-parameter fit")
    if not all(np.all(np.isfinite(v)) for v in (freq, amp_g, amp_pi)):
        return _chi_fit_failed(freq, "non-finite freq or trace")
    f_lo, f_hi = float(np.min(freq)), float(np.max(freq))
    span = f_hi - f_lo
    step = float(np.median(np.abs(np.diff(freq))))
    if not (span > 0 and step > 0):
        return _chi_fit_failed(freq, "freq has no spread")
    n_edge = max(3, freq.size // 10)
    edges = np.concatenate([amp_g[:n_edge], amp_g[-n_edge:], amp_pi[:n_edge], amp_pi[-n_edge:]])
    baseline = float(np.median(edges))
    if not baseline > 0:
        return _chi_fit_failed(freq, "off-resonant level <= 0")

    f_ref = 0.5 * (f_lo + f_hi)
    x = freq - f_ref
    idx_g, idx_pi = int(np.argmin(amp_g)), int(np.argmin(amp_pi))
    d0 = float(freq[idx_pi] - freq[idx_g])
    kappa_lo, kappa_hi = 0.5 * step, span
    kappa0 = float(np.clip(_power_fwhm(freq, amp_g, idx_g, baseline), 2 * step, 0.5 * span))
    depth0 = float(np.clip(1.0 - amp_g[idx_g] / baseline, 0.05, 0.95))
    amp_hi = 10 * max(float(np.max(amp_g)), float(np.max(amp_pi)))
    lower = np.array(
        [f_lo - f_ref, kappa_lo, 0.0, -2.0, -span, CHI_FIT_A_BOUNDS[0], CHI_FIT_B_BOUNDS[0], 0.0]
    )
    upper = np.array(
        [f_hi - f_ref, kappa_hi, 1.0, 2.0, span, CHI_FIT_A_BOUNDS[1], CHI_FIT_B_BOUNDS[1], amp_hi]
    )
    inset = 1e-6 * (upper - lower)

    def resid(p):
        fr, kappa, depth, asym, delta, a, b, amp = p
        return np.concatenate(
            [
                dispersive_mixture_magnitude(x, fr, kappa, depth, asym, delta, a, amp) - amp_g,
                dispersive_mixture_magnitude(x, fr, kappa, depth, asym, delta, b, amp) - amp_pi,
            ]
        )

    deltas = (d0, 2 * d0, -2 * d0) if d0 != 0 else (0.5 * kappa0, -0.5 * kappa0)
    best = None
    for delta0 in deltas:
        for b0 in CHI_FIT_B_SEEDS:
            p0 = [x[idx_g], kappa0, depth0, 0.0, delta0, CHI_FIT_A_SEED, b0, baseline]
            p0 = np.clip(p0, lower + inset, upper - inset)
            try:
                sol = least_squares(
                    resid, p0, bounds=(lower, upper), x_scale="jac", max_nfev=CHI_FIT_MAX_NFEV
                )
            except (ValueError, np.linalg.LinAlgError):
                continue
            if sol.success and np.isfinite(sol.cost) and (best is None or sol.cost < best.cost):
                best = sol
    if best is None:
        return _chi_fit_failed(freq, "optimiser failed from every start")

    dof = 2 * freq.size - n_par
    redchi2 = 2 * float(best.cost) / dof
    try:
        perr = np.sqrt(np.abs(np.diag(np.linalg.inv(best.jac.T @ best.jac) * redchi2)))
    except np.linalg.LinAlgError:
        perr = np.full(n_par, np.inf)
    popt = best.x.copy()
    popt[0] += f_ref
    fr, kappa, depth, asym, delta, a, b, amp = popt
    dip = float(np.ptp(dispersive_mixture_magnitude(freq, fr, kappa, depth, asym, delta, a, amp)))
    rms = float(np.sqrt(redchi2))

    error = None
    if not np.all(np.isfinite(perr)):
        error = "covariance not finite (parameters not constrained by the data)"
    elif not lower[0] + inset[0] < best.x[0] < upper[0] - inset[0]:
        error = f"fr = {fr:.6g} on the edge of the swept range"
    elif not kappa_lo * (1 + 1e-3) < kappa < kappa_hi * (1 - 1e-3):
        error = f"kappa = {kappa:.4g} on a bound [{kappa_lo:.4g}, {kappa_hi:.4g}]"
    elif not dip >= CHI_FIT_MIN_DEPTH_SIGMAS * rms:
        error = f"fitted dip {dip:.4g} < {CHI_FIT_MIN_DEPTH_SIGMAS:g} x residual rms {rms:.4g}"
    return _chi_fit_result(freq, popt, perr, redchi2, ok=error is None, error=error)


RESONATOR_GATE_MIN_DEPTH_SIGMAS = 6.0  # feature depth >= 6 robust sigma of the baseline
RESONATOR_GATE_BASELINE_LINEWIDTHS = 3.0  # baseline = points more than 3 linewidths from f0
RESONATOR_GATE_MIN_BASELINE_POINTS = 10
RESONATOR_GATE_MIN_LINEWIDTH_STEPS = 2.0  # linewidth >= 2 frequency steps
RESONATOR_GATE_MAX_LINEWIDTH_FRAC_SPAN = 0.5  # linewidth < half the span
RESONATOR_GATE_EDGE_LINEWIDTHS = 2.0  # f0 >= 2 linewidths inside the span


def _half_depth_points(y_db, idx, baseline_db, dip):
    """Number of contiguous points around ``idx`` beyond half the feature height in linear
    power (half-way from ``baseline_db`` to ``y_db[idx]`` in |S21|^2, where the Lorentzian FWHM
    is defined; half the dB depth would make a deep, near-critically-coupled notch look one
    point wide). The run's width in x is this count times the grid step."""
    half_db = 10 * np.log10(0.5 * (10 ** (baseline_db / 10) + 10 ** (y_db[idx] / 10)))
    beyond = (y_db <= half_db) if dip else (y_db >= half_db)
    lo = hi = idx
    while lo > 0 and beyond[lo - 1]:
        lo -= 1
    while hi < y_db.size - 1 and beyond[hi + 1]:
        hi += 1
    return hi - lo + 1


def _at_least(value, threshold):
    """``value >= threshold`` up to float rounding of step ratios (2 steps may come out as
    1.9999999999)."""
    return bool(value >= threshold * (1 - 1e-9))


def assess_resonator_feature(x, y_db, f0, linewidth=None, dip=True, y_model=None):
    """Quality gate for carrying a resonator frequency ``f0`` found in the trace ``y_db(x)``.

    Checks (docs/experiments/transmission_fit.md#carry-over-gate): (a) the dip (``dip=True``) or
    peak depth, from the off-resonant baseline median to the extreme point within one linewidth
    of f0, is at least 6 x 1.4826 x MAD of that baseline (points more than 3 linewidths from f0;
    at least 10 of them; with ``y_model``, the fitted curve on ``x``, the MAD is of the residuals
    ``y_db - y_model`` there, so a Fano-skewed baseline is not counted as noise; a straight line
    fitted to those baseline points is removed first, so a tilted background is not either);
    (b) the linewidth is at least 2 frequency steps and below half the span, and with a given
    ``linewidth`` (a fit) the data's own half-power width (``_half_depth_points``) around the
    extreme point within one linewidth of f0 is at least 2 steps too, so a fit that settles on a
    single bad point fails; (c) f0 is at least 2 linewidths inside the span. The baseline rule
    caps a centred linewidth at about (span - 10 steps)/6. ``linewidth`` (x units) defaults to
    the full width at half power of the feature around the point nearest f0 (no fit, e.g. a raw
    peak), counted in grid points times the step.
    Never raises on finite data. Returns ``(ok, reasons, metrics)``: reasons lists every failed
    check (empty when ok), metrics the numbers they were judged on.
    """
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y_db, dtype=float).ravel()
    order = np.argsort(x)
    x, y = x[order], y[order]
    resid = y if y_model is None else y - np.asarray(y_model, dtype=float).ravel()[order]
    f0 = float(f0)
    span = float(x[-1] - x[0])
    step = float(np.median(np.diff(x)))
    if linewidth is None:
        idx = int(np.argmin(np.abs(x - f0)))
        linewidth = _half_depth_points(y, idx, float(np.median(y)), dip) * step
        source = "half-power width"
    else:
        source = "fit"
    lw = abs(float(linewidth))

    off = np.abs(x - f0) > RESONATOR_GATE_BASELINE_LINEWIDTHS * lw
    near = np.abs(x - f0) <= lw
    if not near.any():
        near = np.abs(x - f0) == np.min(np.abs(x - f0))
    n_base = int(off.sum())
    if n_base:
        baseline = float(np.median(y[off]))
        r_off = resid[off]
        if n_base >= RESONATOR_GATE_MIN_BASELINE_POINTS:  # remove a linear background tilt
            r_off = r_off - np.polyval(np.polyfit(x[off] - f0, r_off, 1), x[off] - f0)
        noise = estimate_noise_floor(r_off)[1]
    else:
        baseline, noise = np.nan, np.nan
    i_near = np.flatnonzero(near)
    i_ext = int(i_near[np.argmin(y[near])] if dip else i_near[np.argmax(y[near])])
    depth = (baseline - y[i_ext]) if dip else (y[i_ext] - baseline)
    edge = float(min(f0 - x[0], x[-1] - f0) / lw) if lw > 0 else np.inf

    metrics = {
        "f0": f0,
        "linewidth": lw,
        "linewidth_source": source,
        "linewidth_steps": lw / step if step > 0 else np.nan,
        "span": span,
        "depth_db": depth,
        "noise_db": noise,
        "depth_sigmas": depth / noise if n_base and noise > 0 else np.nan,
        "n_baseline": n_base,
        "edge_linewidths": edge,
    }
    if source == "fit":  # needs a baseline: without one only the baseline check is reported
        data_n = _half_depth_points(y, i_ext, baseline, dip) if n_base else np.nan
        metrics["data_width_steps"] = float(data_n)
    kind = "dip" if dip else "peak"
    narrow_hint = (
        f"a resonance too narrow for the grid (step {step:.3g}); if the trace shows a real "
        f"{kind} there, raise num_points or narrow span (do not widen it)"
    )
    reasons = []
    if n_base < RESONATOR_GATE_MIN_BASELINE_POINTS:
        reasons.append(
            f"only {n_base} points more than {RESONATOR_GATE_BASELINE_LINEWIDTHS:g} linewidths "
            f"from f0 (< {RESONATOR_GATE_MIN_BASELINE_POINTS}): no baseline to judge the {kind} by"
        )
    elif not metrics["depth_sigmas"] >= RESONATOR_GATE_MIN_DEPTH_SIGMAS:
        reasons.append(
            f"{kind} depth {depth:.3g} dB is {metrics['depth_sigmas']:.2f} x the baseline noise "
            f"{noise:.3g} dB (< {RESONATOR_GATE_MIN_DEPTH_SIGMAS:g})"
        )
    if not _at_least(metrics["linewidth_steps"], RESONATOR_GATE_MIN_LINEWIDTH_STEPS):
        reasons.append(
            f"linewidth {lw:.3g} is {metrics['linewidth_steps']:.2f} frequency steps "
            f"(< {RESONATOR_GATE_MIN_LINEWIDTH_STEPS:g}): {narrow_hint}"
        )
    if (
        source == "fit"
        and n_base
        and not _at_least(metrics["data_width_steps"], RESONATOR_GATE_MIN_LINEWIDTH_STEPS)
    ):
        reasons.append(
            f"the data's half-power width around the {kind} is "
            f"{metrics['data_width_steps']:.2f} frequency steps "
            f"(< {RESONATOR_GATE_MIN_LINEWIDTH_STEPS:g}): a single-point {kind}, either a "
            f"spike or {narrow_hint}"
        )
    if not lw < RESONATOR_GATE_MAX_LINEWIDTH_FRAC_SPAN * span:
        reasons.append(
            f"linewidth {lw:.3g} is not below {RESONATOR_GATE_MAX_LINEWIDTH_FRAC_SPAN:g} x the "
            f"span {span:.3g}"
        )
    if not _at_least(edge, RESONATOR_GATE_EDGE_LINEWIDTHS):
        reasons.append(
            f"f0 {f0:.6f} is {edge:.2f} linewidths from the sweep edge "
            f"(< {RESONATOR_GATE_EDGE_LINEWIDTHS:g})"
        )
    return not reasons, reasons, metrics


def assess_resonator_fit(x, y_db, popt):
    """``assess_resonator_feature`` for a hanger fit: f0 = popt[0], linewidth = |f0|/Qtot (the
    hanger FWHM on the fit axis), dip, noise from the fit residuals. Neither Qtot <= Qext (a
    popt with Qtot > Qext is the |S21| twin of Qtot/Qext -> 2 - Qtot/Qext, judged the same; the
    fit itself always returns Qtot < Qext) nor perr (tiny on pure noise) is used."""
    f0, qtot = float(popt[0]), float(popt[1])
    y_model = hanger_model_db(np.asarray(x, dtype=float), *popt)
    return assess_resonator_feature(
        x, y_db, f0, linewidth=abs(f0) / qtot, dip=True, y_model=y_model
    )


def lorentzian_dip(f, y0, A, f0, gamma):
    return y0 - A / (1.0 + ((f - f0) / gamma) ** 2)


def lorentzian_peak(f, y0, A, f0, gamma):
    return y0 + A / (1.0 + ((f - f0) / gamma) ** 2)


def fit_lorentzian_feature(x, y, fit_dip=True):
    """Fit lorentzian_dip / lorentzian_peak over the whole trace; returns popt, pcov, perr,
    yfit, rss, model. Raises if curve_fit fails."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    y_max = np.max(y)
    y_min = np.min(y)
    x_span = np.max(x) - np.min(x)

    if fit_dip:
        idx0 = np.argmin(y)
        y0_guess = np.median(y)
        A_guess = max(y0_guess - y_min, 1e-12)
    else:
        idx0 = np.argmax(y)
        y0_guess = np.median(y)
        A_guess = max(y_max - y0_guess, 1e-12)

    f0_guess = x[idx0]
    gamma_guess = max(x_span / 20.0, 1e-6)

    model = lorentzian_dip if fit_dip else lorentzian_peak
    p0 = [y0_guess, A_guess, f0_guess, gamma_guess]

    bounds = ([-np.inf, 0.0, np.min(x), 1e-12], [np.inf, np.inf, np.max(x), x_span])

    popt, pcov = curve_fit(model, x, y, p0=p0, bounds=bounds, maxfev=50000)
    perr = np.sqrt(np.diag(pcov))
    yfit = model(x, *popt)

    residuals = y - yfit
    rss = np.sum(residuals**2)

    return {
        "popt": popt,
        "pcov": pcov,
        "perr": perr,
        "yfit": yfit,
        "rss": rss,
        "model": model,
    }


def estimate_noise_floor(y, *, zero_mad=None):
    """Robust baseline and noise sigma of a 1-D trace.

    Uses the median as the baseline and the median-absolute-deviation (MAD)
    scaled to a Gaussian sigma. Unlike (max - min), this is insensitive to a
    handful of tall qubit peaks or single-sample spikes, so it gives a stable
    noise estimate to threshold against.

    zero_mad : callable(baseline) -> sigma, optional
        Sigma to return when the MAD sigma is zero or not finite. Default: the
        standard deviation, then 1e-12.

    Returns
    -------
    (baseline, sigma) : tuple of float
    """
    y = np.asarray(y, dtype=float)
    baseline = float(np.median(y))
    mad = float(np.median(np.abs(y - baseline)))
    sigma = 1.4826 * mad  # MAD -> Gaussian-equivalent std
    if not np.isfinite(sigma) or sigma <= 0:
        if zero_mad is not None:
            return baseline, float(zero_mad(baseline))
        sigma = float(np.std(y))
        if not np.isfinite(sigma) or sigma <= 0:
            sigma = 1e-12
    return baseline, sigma


def cos_func(x, y0, A, P, phi):
    return y0 + A * np.cos(2 * np.pi * x / P + phi)


RABI_FLAG_PHASE = 1  # |phi mod pi| > 0.3 rad: the trace does not start at an extremum
RABI_FLAG_PI_OUT_OF_RANGE = 2  # P/2 outside the swept gain range
RABI_FLAG_UNDERSAMPLED = 4  # fewer than 0.75 periods in the sweep


def _rabi_period_seed_fft(x, y, pad=16):
    """Period at the peak of the zero-padded rFFT of ``y - mean`` (DC bin zeroed); None if
    undefined. A non-uniform grid is resampled onto a uniform one of the same length."""
    n = x.size
    dx = (x[-1] - x[0]) / (n - 1)
    xu = x[0] + dx * np.arange(n)
    yu = np.interp(xu, x, y) - np.mean(y)
    n_fft = int(2 ** np.ceil(np.log2(pad * n)))
    spec = np.abs(np.fft.rfft(yu, n_fft))
    spec[0] = 0.0
    k = int(np.argmax(spec))
    if k == 0 or spec[k] == 0:
        return None
    return 1.0 / np.fft.rfftfreq(n_fft, d=dx)[k]


def fit_rabi_cosine(x, y):
    """Cosine fit ``y0 + A cos(2 pi x / P + phi)`` for amplitude Rabi; ``pi_gain = P / 2``,
    ``dpi_gain = dP / 2``. Two period seeds (zero-padded FFT peak, and the gain span) times
    two signs of A, phi = 0; the lowest-residual fit wins. P is bounded below by 2 median
    grid steps (Nyquist), so an aliased short period cannot win on residual. Raises
    RuntimeError on flat or too-short data; the quality checks never raise: ``flags`` (list
    of str) and ``flag_code`` (bitmask of the RABI_FLAG_* constants) report them. See
    docs/experiments/amplitude_rabi.md."""
    x_in = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    good = np.isfinite(x_in) & np.isfinite(y)
    order = np.argsort(x_in[good])
    x, y = x_in[good][order], y[good][order]
    if x.size < 5 or x[-1] <= x[0]:
        raise RuntimeError("Rabi fit needs at least 5 distinct gain points.")
    x_min, x_max = float(x[0]), float(x[-1])
    x_span = x_max - x_min
    y0_guess = float(np.mean(y))
    A_guess = 0.5 * float(np.max(y) - np.min(y))
    if A_guess == 0:
        raise RuntimeError("Flat Rabi data.")

    # Nyquist floor on P: a period shorter than 2 grid steps is an alias of a longer one with
    # the same residual (the -A start can land on it), so it is excluded from the fit.
    P_min = 2.0 * float(np.median(np.diff(np.unique(x))))
    seeds = [max(x_span, 1.0)]
    p_fft = _rabi_period_seed_fft(x, y)
    if p_fft is not None:
        seeds.append(p_fft)
    seeds = [max(P_guess, 1.01 * P_min) for P_guess in seeds]

    bounds = ([-np.inf, -np.inf, P_min, -4 * np.pi], [np.inf, np.inf, np.inf, 4 * np.pi])
    best = None
    for P_guess in seeds:
        for A_sign in (1.0, -1.0):
            p0 = [y0_guess, A_sign * A_guess, P_guess, 0.0]
            try:
                popt, pcov = curve_fit(cos_func, x, y, p0=p0, bounds=bounds, maxfev=50000)
            except (RuntimeError, ValueError):
                continue
            sse = float(np.sum((y - cos_func(x, *popt)) ** 2))
            if best is None or sse < best[0]:
                best = (sse, popt, pcov)
    if best is None:
        raise RuntimeError("All Rabi cosine fits failed.")
    _, popt, pcov = best
    perr = np.sqrt(np.diag(pcov))

    y0_fit, A_fit, P_fit, phi_fit = popt
    dy0_fit, dA_fit, dP_fit, dphi_fit = perr
    pi_gain = P_fit / 2.0
    n_periods = x_span / P_fit

    flags, flag_code = [], 0
    phi_mod = (phi_fit + np.pi / 2) % np.pi - np.pi / 2  # phi wrapped modulo pi
    if abs(phi_mod) > 0.3:
        flag_code |= RABI_FLAG_PHASE
        flags.append(f"phase {phi_fit:.2f} rad is {phi_mod:+.2f} rad from 0 or pi")
    if not x_min <= pi_gain <= x_max:
        flag_code |= RABI_FLAG_PI_OUT_OF_RANGE
        flags.append(f"pi gain {pi_gain:.4g} outside the sweep [{x_min:.4g}, {x_max:.4g}]")
    if n_periods < 0.75:
        flag_code |= RABI_FLAG_UNDERSAMPLED
        flags.append(f"only {n_periods:.2f} periods in the sweep (< 0.75)")

    return {
        "popt": popt,
        "perr": perr,
        "yfit": cos_func(x_in, *popt),
        "y0": y0_fit,
        "A": A_fit,
        "P": P_fit,
        "phi": phi_fit,
        "dy0": dy0_fit,
        "dA": dA_fit,
        "dP": dP_fit,
        "dphi": dphi_fit,
        "pi_gain": pi_gain,
        "dpi_gain": dP_fit / 2.0,
        "n_periods": n_periods,
        "flags": flags,
        "flag_code": flag_code,
    }


PI_GAIN_FIT_MIN_PTS = 5  # fewer points: no fit, the caller keeps the scan argmax
PI_GAIN_FIT_P_HALF_WIDTH = 0.3  # P window: centre x [1 - h, 1 + h], h <= 0.5 / rotations
PI_GAIN_FIT_MAX_REL_DEV = 0.6  # points with |g / centre - 1| above this are not fitted
PI_GAIN_FIT_GRID_PTS = 241


def _pi_gain_model(rotations):
    """Contrast model ``B - A cos(pi rotations g / P)`` (cos_func with period 2 P / rotations)."""
    return lambda g, B, A, P: cos_func(g, B, -A, 2.0 * P / rotations, 0.0)


def fit_pi_gain_contrast(gains, contrast, centre, rotations=1.0):
    """Gain at which ``rotations`` pi rotations land on |e>, from a single-shot contrast scan.

    Model ``C(g) = B - A cos(pi rotations g / P)`` (C = Cread sin^2(pi rotations g / (2 P))
    for B = A = Cread / 2): a maximum at g = P when A > 0. rotations = N for N pi pulses,
    N / 2 for N pi/2 pulses. Only points with |g / centre - 1| <= PI_GAIN_FIT_MAX_REL_DEV are
    fitted (at low excitation the rectified histogram contrast is unreliable). (B, A) are
    linear least squares on a grid of P over the window centre x [1 - h, 1 + h], h = min(0.3,
    0.5 / rotations) (other solutions of the same data lie ~1 / rotations away: a minimum, or
    the next fringe), then curve_fit refines (B, A, P) with P held in the window. Never
    raises: ``ok`` is False, with ``reason``, for fewer than PI_GAIN_FIT_MIN_PTS points, a
    failed fit, A <= 0, P on the window edge, or P outside the fitted gains. Returns dict:
    ok, reason, P, dP, A, B, n (points fitted). See docs/experiments/auto_coherence.md.
    """
    g = np.asarray(gains, dtype=float).ravel()
    c = np.asarray(contrast, dtype=float).ravel()
    centre = float(centre)
    rotations = float(rotations)
    out = {"ok": False, "reason": "", "P": np.nan, "dP": np.nan, "A": np.nan, "B": np.nan, "n": 0}
    keep = np.isfinite(g) & np.isfinite(c)
    if centre > 0:
        keep &= np.abs(g / centre - 1.0) <= PI_GAIN_FIT_MAX_REL_DEV + 1e-9
    g, c = g[keep], c[keep]
    out["n"] = int(g.size)
    if centre <= 0:
        out["reason"] = f"scan centre {centre} <= 0"
        return out
    if g.size < PI_GAIN_FIT_MIN_PTS or np.unique(g).size < PI_GAIN_FIT_MIN_PTS:
        out["reason"] = f"{g.size} points (< {PI_GAIN_FIT_MIN_PTS} distinct gains)"
        return out

    h = min(PI_GAIN_FIT_P_HALF_WIDTH, 0.5 / rotations)
    P_lo, P_hi = centre * (1.0 - h), centre * (1.0 + h)
    best = None
    for P in np.linspace(P_lo, P_hi, PI_GAIN_FIT_GRID_PTS):
        design = np.column_stack([np.ones_like(g), -np.cos(np.pi * rotations * g / P)])
        (B, A), *_ = np.linalg.lstsq(design, c, rcond=None)
        sse = float(np.sum((c - design @ np.array([B, A])) ** 2))
        if best is None or sse < best[0]:
            best = (sse, B, A, P)
    _, B0, A0, P0 = best

    model = _pi_gain_model(rotations)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", OptimizeWarning)
            popt, pcov = curve_fit(
                model,
                g,
                c,
                p0=[B0, A0, P0],
                bounds=([-np.inf, -np.inf, P_lo], [np.inf, np.inf, P_hi]),
                maxfev=10000,
            )
    except (RuntimeError, ValueError, OptimizeWarning) as exc:
        out["reason"] = f"fit failed ({type(exc).__name__})"
        return out
    perr = np.sqrt(np.diag(pcov))
    B, A, P = (float(v) for v in popt)
    out.update(B=B, A=A, P=P, dP=float(perr[2]))
    if not np.all(np.isfinite(popt)) or not np.all(np.isfinite(perr)):
        out["reason"] = "fit failed (non-finite parameters or covariance)"
    elif A <= 0:
        out["reason"] = f"A = {A:.4g} <= 0 (P is a contrast minimum)"
    elif not P_lo + 1e-6 * centre < P < P_hi - 1e-6 * centre:
        out["reason"] = f"P = {P:.1f} on the edge of the window [{P_lo:.0f}, {P_hi:.0f}]"
    elif not g.min() <= P <= g.max():
        out["reason"] = f"P = {P:.1f} outside the fitted gains [{g.min():.0f}, {g.max():.0f}]"
    else:
        out["ok"] = True
    return out


def exp_decay(x, a, T1, c):
    return a * np.exp(-1 * x / T1) + c


EXP_DECAY_T_MIN_FRAC_DX = 0.5  # T lower bound: half the median sample spacing
EXP_DECAY_T_MAX_FRAC_SPAN = 20.0  # T upper bound: 20 x the sweep span
EXP_DECAY_A_MAX_FRAC_PTP = 10.0  # |a| bound: 10 x the peak-to-peak of the data
EXP_DECAY_MAXFEV = 10000
EXP_DECAY_MIN_A_SIGMAS = 3.0  # ok needs the decay amplitude >= 3 standard errors


def _exp_decay_failed(x_pts, error, popt=None, perr=None, T_bounds=None):
    nan3 = np.full(3, np.nan)
    popt = nan3 if popt is None else np.asarray(popt, dtype=float)
    perr = nan3 if perr is None else np.asarray(perr, dtype=float)
    return {
        "ok": False,
        "T": float(popt[1]),
        "T_err": float(perr[1]),
        "a": float(popt[0]),
        "c": float(popt[2]),
        "popt": popt,
        "perr": perr,
        "yfit": exp_decay(np.asarray(x_pts, dtype=float), *popt),
        "T_bounds": T_bounds,
        "error": error,
    }


def fit_exp_decay(x_pts, y, sigma=None):
    """Bounded single-exponential fit ``a exp(-x/T) + c`` for T1 / T2E (docs/experiments/t1.md#analysis).

    ``sigma`` (optional, per point, all > 0) weights the points as ``curve_fit(sigma=...)`` with
    ``absolute_sigma=False``: relative weights, the covariance is rescaled by the reduced
    chi-square (T1_SS: docs/experiments/t1_single_shot.md#analysis). None = unweighted.

    Start values: ``a = y[0] - y[-1]``, ``c = y[-1]``, T = the x where y is closest to
    ``a/2.6 + c`` (about the 1/e point), clipped into the bounds. Bounds come from the
    sampling: ``T`` in ``[dx/2, 20 * span]`` (dx = median spacing, span = max - min of x),
    ``|a| <= 10 * ptp(y)``, ``c`` free. Never raises: returns a dict
    ``{ok, T, T_err, a, c, popt, perr, yfit, T_bounds, error}``. ``ok`` is False (with the reason
    in ``error``) when the optimiser fails, the data are too short or non-finite, T ends on a
    bound (decay faster than the sampling or not resolved within the sweep), or the
    covariance is not finite, T_err >= T, or ``|a| < 3 a_err`` (no significant decay). ``popt`` / ``yfit`` are kept when a fit exists
    (NaN otherwise) so a caller may still draw it. ``ok`` is a quality flag, not an unbiased
    selection: on marginal data the fits it rejects are mostly the ones that overestimate T
    (docs/experiments/t1.md#analysis).
    """
    x = np.asarray(x_pts, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    if x.size != y.size:
        return _exp_decay_failed(x, f"x/y length mismatch ({x.size} vs {y.size})")
    if x.size < 4:
        return _exp_decay_failed(x, f"need >= 4 points for a 3-parameter fit, got {x.size}")
    if not (np.all(np.isfinite(x)) and np.all(np.isfinite(y))):
        return _exp_decay_failed(x, "non-finite x or y")
    if sigma is not None:
        sigma = np.asarray(sigma, dtype=float).ravel()
        if sigma.size != y.size or not np.all(np.isfinite(sigma) & (sigma > 0)):
            return _exp_decay_failed(x, "sigma must be finite, > 0 and one per point")

    span = float(np.max(x) - np.min(x))
    dx = float(np.median(np.abs(np.diff(np.sort(x)))))
    ptp = float(np.ptp(y))
    if span <= 0 or dx <= 0:
        return _exp_decay_failed(x, "x has no spread")
    if ptp <= 0:
        return _exp_decay_failed(x, "y is constant")
    t_lo = EXP_DECAY_T_MIN_FRAC_DX * dx
    t_hi = EXP_DECAY_T_MAX_FRAC_SPAN * span
    a_max = EXP_DECAY_A_MAX_FRAC_PTP * ptp
    lb = np.array([-a_max, t_lo, -np.inf])
    ub = np.array([a_max, t_hi, np.inf])
    bounds = (lb, ub)

    a_guess = y[0] - y[-1]
    b_guess = y[-1]
    approx_t1_val = a_guess / 2.6 + b_guess
    index_t1_guess = np.argmin(np.abs(y - approx_t1_val))
    t1_guess = x[index_t1_guess]
    guess = np.clip([a_guess, t1_guess, b_guess], lb, ub)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", OptimizeWarning)
            popt, pcov = curve_fit(
                exp_decay,
                x,
                y,
                p0=guess,
                sigma=sigma,
                absolute_sigma=False,
                bounds=bounds,
                maxfev=EXP_DECAY_MAXFEV,
            )
    except (RuntimeError, ValueError) as e:
        return _exp_decay_failed(x, repr(e), T_bounds=(t_lo, t_hi))
    perr = np.sqrt(np.abs(np.diag(pcov)))

    T, T_err = float(popt[1]), float(perr[1])
    error = None
    if np.isclose(T, t_lo, rtol=1e-3, atol=0) or np.isclose(T, t_hi, rtol=1e-3, atol=0):
        error = f"T = {T:.4g} on a bound [{t_lo:.4g}, {t_hi:.4g}]: decay not resolved by the sweep"
    elif not np.all(np.isfinite(perr)):
        error = "covariance not finite (parameters not constrained by the data)"
    elif not T_err < T:
        error = f"T_err = {T_err:.4g} >= T = {T:.4g}"
    elif not abs(popt[0]) >= EXP_DECAY_MIN_A_SIGMAS * perr[0]:
        error = (
            f"|a| = {abs(popt[0]):.4g} < {EXP_DECAY_MIN_A_SIGMAS:g} x a_err = {perr[0]:.4g}:"
            " no significant decay"
        )
    if error is not None:
        return _exp_decay_failed(x, error, popt=popt, perr=perr, T_bounds=(t_lo, t_hi))

    return {
        "ok": True,
        "T": T,
        "T_err": T_err,
        "a": float(popt[0]),
        "c": float(popt[2]),
        "popt": np.asarray(popt, dtype=float),
        "perr": np.asarray(perr, dtype=float),
        "yfit": exp_decay(x, *popt),
        "T_bounds": (t_lo, t_hi),
        "error": None,
    }


def exp_decay_fit_fields(fit, prefix):
    """Flat float fields of a ``fit_exp_decay`` result for the h5, keys ``<prefix>_fit_*``.

    ``_ok`` (1/0), ``_us`` (T), ``_err_us`` (sigma_T), ``_a``, ``_c``, ``_popt`` [a, T, c],
    ``_perr``; NaN where the fit has no value (failed fit, or a ``{'ok': False, 'error'}``
    stub from a guarded display). Key names are stable (docs/experiments/t1.md#outputs).
    """
    nan3 = np.full(3, np.nan)
    return {
        f"{prefix}_fit_ok": bool(fit.get("ok", False)),
        f"{prefix}_fit_us": float(fit.get("T", np.nan)),
        f"{prefix}_fit_err_us": float(fit.get("T_err", np.nan)),
        f"{prefix}_fit_a": float(fit.get("a", np.nan)),
        f"{prefix}_fit_c": float(fit.get("c", np.nan)),
        f"{prefix}_fit_popt": np.asarray(fit.get("popt", nan3), dtype=float),
        f"{prefix}_fit_perr": np.asarray(fit.get("perr", nan3), dtype=float),
    }
