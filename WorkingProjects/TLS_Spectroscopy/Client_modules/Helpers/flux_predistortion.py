"""
Flux-line predistortion engine (pure numpy / scipy), ported from the QUA repo's
LabCode/Helpers/flux_predistortion.py + m_qubit_step_response.py.

Pipeline (step 3 of the TLS workflow):
  1. Measure the flux-line STEP RESPONSE: the normalized qubit response
     (0 = still at baseline, 1 = settled at target) vs delay t after a flux step.
  2. Fit it to a compact ``rise_decay_bump`` plant model (smooths the noisy trace).
  3. Solve a PIECEWISE-CONSTANT precompensation: one multiplier per time segment
     so that, given the plant's own measured step response, the OUTPUT is flat.
  4. Save/load the compensation as JSON; the fast-flux experiments (steps 4 & 6)
     bake it into the ff-DAC waveform to cancel the flux line's slow settling.

QICK note: the QUA version played the multipliers as a real-time ``set_dc_offset``
staircase.  QICK has no in-program DC-offset primitive, so the SAME multipliers are
instead baked into the sampled fast-flux ``idata`` waveform via
``build_predistorted_ff_samples`` below (a piecewise-constant array on the ff DAC).
This is the one genuine QUA->QICK reimplementation; the solver math is unchanged.
"""

import os
import glob
import json
import datetime

import numpy as np
from scipy.optimize import least_squares


# --------------------------------------------------------------------------- #
#  rise_decay_bump plant model
# --------------------------------------------------------------------------- #
def rise_decay_bump_model(t, asymptote, late_amplitude, late_tau_ns,
                          bump_amplitude, rise_tau_ns, bump_tau_ns):
    """asymptote + late_amplitude*exp(-t/late_tau)
                 + bump_amplitude*(1-exp(-t/rise_tau))*exp(-t/bump_tau)

    'late' = slow settling tail; 'bump' = short transient that rises then decays
    (the early over/undershoot).  ``t`` in ns.
    """
    t = np.asarray(t, dtype=float)
    late = late_amplitude * np.exp(-t / late_tau_ns)
    bump = bump_amplitude * (1.0 - np.exp(-t / rise_tau_ns)) * np.exp(-t / bump_tau_ns)
    return asymptote + late + bump


def fit_rise_decay_bump_response_model(time_ns, response):
    """Multi-start, BIC-selected fit of :func:`rise_decay_bump_model`.

    Returns a dict {asymptote, late_amplitude, late_tau_ns, bump_amplitude,
    rise_tau_ns, bump_tau_ns, rss, bic, success} or {'success': False}.
    """
    t = np.asarray(time_ns, dtype=float)
    y = np.asarray(response, dtype=float)
    good = np.isfinite(t) & np.isfinite(y)
    t, y = t[good], y[good]
    n = t.size
    if n < 6:
        return {'success': False}

    span = float(t[-1] - t[0]) or 1.0
    asymptote0 = float(np.median(y[-max(3, n // 5):]))
    late0 = float(y[0] - asymptote0)

    # deterministic seed grid (no RNG so results are reproducible)
    tau_grid = np.array([0.05, 0.2, 1.0, 5.0]) * span
    bump_sign = [+1.0, -1.0]

    def resid(p, y_):
        return rise_decay_bump_model(t, *p) - y_

    best = None
    lb = [-np.inf, -np.inf, 1e-3, -np.inf, 1e-3, 1e-3]
    ub = [np.inf, np.inf, 1e12, np.inf, 1e12, 1e12]
    for late_tau in tau_grid:
        for rise_tau in tau_grid * 0.2:
            for bump_tau in tau_grid:
                for sgn in bump_sign:
                    p0 = [asymptote0, late0, max(late_tau, 1e-3),
                          sgn * 0.2 * (abs(late0) + 1e-3),
                          max(rise_tau, 1e-3), max(bump_tau, 1e-3)]
                    try:
                        res = least_squares(resid, p0, args=(y,), bounds=(lb, ub),
                                            max_nfev=4000)
                    except Exception:
                        continue
                    rss = float(np.sum(res.fun ** 2))
                    k = len(p0)
                    bic = n * np.log(max(rss, 1e-30) / n) + k * np.log(n)
                    if best is None or bic < best['bic']:
                        best = {'params': res.x, 'rss': rss, 'bic': bic,
                                'success': bool(res.success)}
    if best is None:
        return {'success': False}
    keys = ['asymptote', 'late_amplitude', 'late_tau_ns',
            'bump_amplitude', 'rise_tau_ns', 'bump_tau_ns']
    out = dict(zip(keys, [float(v) for v in best['params']]))
    out.update(rss=best['rss'], bic=best['bic'], success=best['success'])
    return out


# --------------------------------------------------------------------------- #
#  Piecewise DC correction (segment-superposition deconvolution)
# --------------------------------------------------------------------------- #
def default_dc_tail_segment_edges(max_time_ns):
    """Log-coarsening segment grid (ns): dense early (fast transient), sparse late.

    500 ns steps <1 us, 1 us to 4 us, 2 us to 8 us, 4 us to 16 us, 8 us to 32 us,
    then 10 us.  Always starts at 0.  (Mirrors the QUA default.)
    """
    max_time_ns = float(max_time_ns)
    edges = [0.0]
    plan = [(1e3, 500.0), (4e3, 1e3), (8e3, 2e3), (16e3, 4e3), (32e3, 8e3),
            (np.inf, 10e3)]
    t = 0.0
    for upper, step in plan:
        while t + step < min(upper, max_time_ns):
            t += step
            edges.append(t)
        if t >= max_time_ns:
            break
    edges = np.array(sorted(set(e for e in edges if e < max_time_ns)))
    if edges.size == 0 or edges[0] != 0.0:
        edges = np.concatenate([[0.0], edges])
    return edges


def _resolve_desired_level(step_response, desired_response):
    if isinstance(desired_response, (int, float)):
        return float(desired_response)
    r = np.asarray(step_response, dtype=float)
    r = r[np.isfinite(r)]
    if r.size == 0:
        return 1.0
    return {'unity': 1.0, 'initial': float(r[0]), 'median': float(np.median(r)),
            'mean': float(np.mean(r))}.get(desired_response, float(np.median(r)))


def calculate_piecewise_dc_correction(time_ns, step_response, segment_edges_ns,
                                      desired_response='median',
                                      regularization=0.02, final_weight=1.0,
                                      min_multiplier=0.5, max_multiplier=1.5,
                                      correction_gain=1.0):
    """Solve one multiplier per time segment so the plant output is flat.

    A piecewise-constant command = superposition of delayed steps of size
    ``jump_k = level_k - level_{k-1}`` (level_{-1}=0) applied at ``segment_edges_ns[k]``.
    The plant output is ``sum_k jump_k * h(t - edge_k)`` where ``h`` is the measured
    normalized step response (h(tau<0)=0).  We least-squares-fit the levels
    (multipliers) so the output equals ``desired_level``, with a ridge toward
    no-op (level=1) and an anchor on the final segment.

    Returns a dict with segment_edges_ns, multipliers (after gain+clip),
    undamped_multipliers (raw solve), correction_gain, desired_response_level,
    success, multiplier_clipped.
    """
    t = np.asarray(time_ns, dtype=float)
    h = np.asarray(step_response, dtype=float)
    good = np.isfinite(t) & np.isfinite(h)
    t, h = t[good], h[good]
    edges = np.asarray(segment_edges_ns, dtype=float)
    edges = np.unique(edges[edges < t[-1]]) if t.size else np.unique(edges)
    if edges.size == 0 or edges[0] != 0.0:
        edges = np.concatenate([[0.0], edges])
    n_seg = edges.size

    desired_level = _resolve_desired_level(h, desired_response)

    def plant(tau):
        # measured normalized step response at delay tau (>=0), 0 for tau<0
        out = np.interp(tau, t, h, left=h[0], right=h[-1])
        return np.where(tau < 0, 0.0, out)

    # step_matrix[t, k] = h(t - edge_k)
    step_matrix = np.stack([plant(t - e) for e in edges], axis=1)  # (n_t, n_seg)

    # jumps = levels - shift(levels, fill=0)   ->   linear map J: levels -> jumps
    J = np.eye(n_seg) - np.eye(n_seg, k=-1)

    def levels_to_response(levels):
        jumps = J @ levels
        return step_matrix @ jumps

    def resid(levels):
        r = levels_to_response(levels) - desired_level
        reg = np.sqrt(max(regularization, 0.0)) * (levels - 1.0)
        anchor = np.sqrt(max(final_weight, 0.0)) * np.array([levels[-1] - 1.0])
        return np.concatenate([r, reg, anchor])

    x0 = np.ones(n_seg)
    try:
        res = least_squares(resid, x0, bounds=(min_multiplier, max_multiplier),
                            max_nfev=8000)
        undamped = res.x
        success = bool(res.success)
    except Exception:
        undamped = x0
        success = False

    applied = 1.0 + float(correction_gain) * (undamped - 1.0)
    clipped_arr = np.clip(applied, min_multiplier, max_multiplier)
    multiplier_clipped = bool(np.any(np.abs(clipped_arr - applied) > 1e-9))
    undamped_clipped = bool(np.any((undamped <= min_multiplier + 1e-9) |
                                   (undamped >= max_multiplier - 1e-9)))

    return {
        'segment_edges_ns': [float(e) for e in edges],
        'multipliers': [float(m) for m in clipped_arr],
        'undamped_multipliers': [float(m) for m in undamped],
        'correction_gain': float(correction_gain),
        'desired_response': desired_response,
        'desired_response_level': desired_level,
        'success': success and not multiplier_clipped,
        'multiplier_clipped': multiplier_clipped,
        'undamped_multiplier_clipped': undamped_clipped,
    }


def scale_compensation_gain(compensation, gain, min_multiplier=0.5, max_multiplier=1.5):
    """Re-derive multipliers for a new correction_gain WITHOUT refitting:
    m_applied = 1 + gain*(undamped - 1), clipped.  Mirrors the QUA _scale_gain."""
    comp = dict(compensation)
    undamped = comp.get('undamped_multipliers') or comp.get('multipliers', [])
    undamped = np.asarray(undamped, dtype=float)
    applied = 1.0 + float(gain) * (undamped - 1.0)
    clipped = np.clip(applied, min_multiplier, max_multiplier)
    comp['multipliers'] = [float(m) for m in clipped]
    comp['correction_gain'] = float(gain)
    comp['multiplier_clipped'] = bool(np.any(np.abs(clipped - applied) > 1e-9))
    return comp


# --------------------------------------------------------------------------- #
#  Bake the multipliers into a sampled fast-flux waveform (QICK-specific)
# --------------------------------------------------------------------------- #
def build_predistorted_ff_samples(compensation, hold_ns, dt_ns, target_amp,
                                  start_amp=0.0):
    """Return a piecewise-constant fast-flux sample array (length ceil(hold_ns/dt))
    that plays ``start + multiplier[k]*(target-start)`` on segment k.

    This is the QICK stand-in for the QUA real-time ``set_dc_offset`` staircase:
    the same multipliers, rendered as ff-DAC ``idata`` samples at ``dt_ns`` spacing.
    ``target_amp``/``start_amp`` are in whatever amplitude units the caller feeds
    the generator (DAC gain or normalized).
    """
    edges = np.asarray(compensation['segment_edges_ns'], dtype=float)
    mult = np.asarray(compensation['multipliers'], dtype=float)
    n = max(int(np.ceil(hold_ns / dt_ns)), 1)
    tt = (np.arange(n) + 0.5) * dt_ns
    seg_idx = np.clip(np.searchsorted(edges, tt, side='right') - 1, 0, mult.size - 1)
    levels = mult[seg_idx]
    return start_amp + levels * (target_amp - start_amp)


# --------------------------------------------------------------------------- #
#  Compensation JSON I/O
# --------------------------------------------------------------------------- #
DEFAULT_METHOD = 'rise_decay_bump_set_dc_offset_correction'


def save_compensation_json(json_path, compensation, method=DEFAULT_METHOD,
                           metadata=None, rise_decay_bump_model=None):
    """Write a compensation dict to JSON in the QUA-compatible schema."""
    payload = {
        'enabled': True,
        'method': method,
        'success': bool(compensation.get('success', False)),
        'created_at': None,   # timestamps passed in metadata to keep this deterministic
        'segment_edges_ns': list(compensation['segment_edges_ns']),
        'multipliers': list(compensation['multipliers']),
        'undamped_multipliers': list(compensation.get('undamped_multipliers',
                                                      compensation['multipliers'])),
        'correction_gain': float(compensation.get('correction_gain', 1.0)),
        'desired_response': compensation.get('desired_response', 'median'),
        'desired_response_level': compensation.get('desired_response_level'),
        'multiplier_clipped': bool(compensation.get('multiplier_clipped', False)),
        'undamped_multiplier_clipped': bool(compensation.get('undamped_multiplier_clipped', False)),
        'rise_decay_bump_model': rise_decay_bump_model,
        'metadata': metadata or {},
    }
    with open(json_path, 'w') as f:
        json.dump(payload, f, indent=2)
    return json_path


def load_compensation_json(json_path, require_success=True):
    """Load + validate a compensation JSON into a flux_tail_compensation dict.

    Rejects (ValueError) payloads that are unsuccessful or clipped, or lack
    segment_edges_ns/multipliers -- an under-correcting comp should hard-fail
    rather than silently apply.  Mirrors QUA load_dc_compensation_json.
    """
    with open(json_path) as f:
        p = json.load(f)
    if not p.get('segment_edges_ns') or not p.get('multipliers'):
        raise ValueError(f"{json_path}: missing segment_edges_ns/multipliers")
    if require_success and not p.get('success', False):
        raise ValueError(f"{json_path}: compensation success=False")
    if p.get('multiplier_clipped', False):
        raise ValueError(f"{json_path}: multiplier_clipped=True (refusing to apply)")
    return {
        'enabled': True,
        'method': p.get('method'),
        'source': str(json_path),
        'segment_edges_ns': [float(e) for e in p['segment_edges_ns']],
        'multipliers': [float(m) for m in p['multipliers']],
        'undamped_multipliers': [float(m) for m in p.get('undamped_multipliers', p['multipliers'])],
        'correction_gain': float(p.get('correction_gain', 1.0)),
        'metadata': p.get('metadata', {}),
    }


def find_latest_compensation_json(outer_folder, qubit, baseline_dc_offset=None,
                                  dc_offset=None, require_success=True):
    """Return the newest valid compensation JSON under ``outer_folder/qubit`` whose
    metadata matches the requested baseline/target DC (np.isclose), or None."""
    pattern = os.path.join(outer_folder, str(qubit), "**",
                           f"*_dc_compensation.json")
    candidates = []
    for path in glob.glob(pattern, recursive=True):
        try:
            with open(path) as f:
                p = json.load(f)
        except Exception:
            continue
        if not p.get('segment_edges_ns') or not p.get('multipliers'):
            continue
        if require_success and not p.get('success', False):
            continue
        if p.get('multiplier_clipped', False):
            continue
        meta = p.get('metadata', {})
        if baseline_dc_offset is not None and 'baseline_dc_offset' in meta:
            if not np.isclose(float(meta['baseline_dc_offset']), float(baseline_dc_offset), atol=1e-9):
                continue
        if dc_offset is not None and 'dc_offset' in meta:
            if not np.isclose(float(meta['dc_offset']), float(dc_offset), atol=1e-9):
                continue
        candidates.append((os.path.getmtime(path), path))
    if not candidates:
        return None
    return sorted(candidates)[-1][1]


def build_inclusive_sweep(vmin, vmax, step):
    """np.arange that includes the upper endpoint when on-grid (QUA build_inclusive_sweep)."""
    step = float(step)
    if step <= 0:
        raise ValueError("step must be > 0")
    return np.arange(float(vmin), float(vmax) + 0.5 * step, step)
