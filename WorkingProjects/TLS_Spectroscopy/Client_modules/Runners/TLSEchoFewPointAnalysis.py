"""Conditional contrast analysis for the twelve-condition few-point echo screen.

Columns are phase-major: short, long, late at 0, 90, 180 and 270 degrees.
All twelve conditions in a row form one acquisition cycle. The short echo is
an amplitude reference; the late pair of pi/2 pulses tests projection after
the same flux hold as the long echo. Their controls only partially constrain
local pulse errors: they do not calibrate the refocusing pi pulse or separate
T1 loss from dephasing. A dip remains a candidate needing repeated full curves.

IQ is projected on the shared ground/excited reference axis without clipping
individual shots. Visibility is twice the four-phase sinusoidal amplitude.
The reported ratio uses sqrt(max(0, |contrast|**2 - trace(mean covariance)))
to reduce the positive magnitude floor; raw magnitudes and their ratio remain
available. This moment correction is not an unbiased amplitude estimator near
zero. In particular, zero means unresolved amplitude, not proven zero coherence.

Bootstrap intervals resample complete cycles and the shared reference samples.
They describe conditional sampling uncertainty, not frequency drift, pulse
systematics, or all 101 comparisons in a scan. Pooled bracket references need
an independent stability check by the runner. Raw shot arrays belong in the
run archive, not in this small JSON report. This module never fits T2.
"""
from __future__ import annotations

import math

import numpy as np

PHASES_DEG = (0, 90, 180, 270)
GROUPS = ('short', 'long', 'late')
MIN_CYCLES = 20
MIN_REFERENCE_SHOTS = 20
MIN_REFERENCE_SNR = 5.0
MIN_CONTROL_SNR = 3.0
MIN_SHORT_VISIBILITY = .55
MIN_LATE_VISIBILITY = .44
EXTREMUM_TOLERANCE = .25
PAIR_SUM_TOLERANCE = .15
PAIR_SUM_SIGMAS = 3.0


def _number(value):
    """JSON has no NaN or infinity; unavailable uncertainty stays explicit."""
    value = float(value)
    return value if math.isfinite(value) else None


def _snr(signal, noise):
    # Exact deterministic inputs have no estimable noise, not infinite JSON.
    return _number(signal / noise) if noise > 0 else None


def _significant(signal, noise, minimum):
    return bool(signal > 0 and (noise == 0 or signal >= minimum * noise))


def _group_report(response, raw_scale):
    means = np.mean(response, axis=0)
    x_shots = response[:, 0] - response[:, 2]
    y_shots = response[:, 1] - response[:, 3]
    xy = np.array([np.mean(x_shots), np.mean(y_shots)])
    covariance = np.cov(np.array([x_shots, y_shots]), ddof=1) / len(response)
    noise_squared = max(0., float(np.trace(covariance)))
    visibility = float(np.linalg.norm(xy))
    debiased = math.sqrt(max(0., visibility ** 2 - noise_squared))
    pair_sum = response[:, 0] + response[:, 2] - response[:, 1] - response[:, 3]
    pair_error = float(np.std(pair_sum, ddof=1) / math.sqrt(len(response)))
    pair_difference = float(np.mean(pair_sum))
    fit_valid = abs(pair_difference) <= max(PAIR_SUM_TOLERANCE,
                                           PAIR_SUM_SIGMAS * pair_error)
    center = float(np.mean(means))
    minimum, maximum = center - visibility / 2, center + visibility / 2
    noise = math.sqrt(noise_squared)
    return {
        'phase_response': {str(p): float(v) for p, v in zip(PHASES_DEG, means)},
        'raw_phase_response': {str(p): float(v * raw_scale)
                               for p, v in zip(PHASES_DEG, means)},
        'x': float(xy[0]), 'y': float(xy[1]),
        'phase_rad': float(math.atan2(xy[1], xy[0])),
        'visibility': visibility, 'raw_visibility': visibility * raw_scale,
        'debiased_visibility': debiased,
        'visibility_noise_rms': noise, 'visibility_snr': _snr(visibility, noise),
        'visibility_noise_scope': 'whole-cycle shot covariance; shared readout uncertainty in bootstrap',
        'contrast_mean_covariance': covariance.tolist(),
        'center': center, 'minimum': minimum, 'maximum': maximum,
        'opposite_pair_sum_difference': pair_difference,
        'opposite_pair_sum_standard_error': pair_error,
        'phase_fit_valid': bool(fit_valid),
        'signal_resolved': _significant(visibility, noise, MIN_CONTROL_SNR),
    }


def _bootstrap(iq, ground, excited, draws, seed):
    """Keep phase/delay covariance and one shared axis in every realization."""
    rng = np.random.default_rng(seed)
    ratios, visibility = [], {name: [] for name in GROUPS}
    # Bounded vectorization avoids allocating draws*ncycles*12 for large runs.
    for start in range(0, draws, 32):
        count = min(32, draws - start)
        g = ground[rng.integers(len(ground), size=(count, len(ground)))].mean(axis=1)
        e = excited[rng.integers(len(excited), size=(count, len(excited)))].mean(axis=1)
        axis = e - g
        rows = rng.integers(len(iq), size=(count, len(iq)))
        selected = iq[rows]
        usable = np.abs(axis) > np.finfo(float).eps
        safe_axis = np.where(usable, axis, 1. + 0j)
        response = np.real((selected - g[:, None, None]) /
                           safe_axis[:, None, None])
        corrected = []
        for index, name in enumerate(GROUPS):
            phases = response[:, :, index::3]
            x = phases[:, :, 0] - phases[:, :, 2]
            y = phases[:, :, 1] - phases[:, :, 3]
            magnitude_squared = x.mean(axis=1) ** 2 + y.mean(axis=1) ** 2
            noise_squared = (x.var(axis=1, ddof=1) +
                             y.var(axis=1, ddof=1)) / len(iq)
            value = np.sqrt(np.maximum(0., magnitude_squared - noise_squared))
            corrected.append(value)
            visibility[name].extend(value[usable].tolist())
        good = usable & (corrected[0] > 0)
        ratios.extend((corrected[1][good] / corrected[0][good]).tolist())
    values = np.asarray(ratios)
    interval = (np.quantile(values, [.025, .975]).tolist()
                if len(values) >= 2 else None)
    return {
        'draws': int(draws), 'seed': int(seed),
        'valid_draws': int(len(values)), 'valid_fraction': len(values) / draws,
        'ratio_interval_95': interval,
        'ratio_standard_error': float(np.std(values, ddof=1)) if len(values) >= 2 else None,
        'visibility_intervals_95': {
            name: np.quantile(v, [.025, .975]).tolist() if len(v) >= 2 else None
            for name, v in visibility.items()},
        'resampling': 'shared complete cycle rows and shared ground/excited references',
        'scope': 'conditional sampling uncertainty; excludes drift and systematic errors',
    }


def analyze_site(iq, ground_iq, excited_iq, *, bootstrap_draws=400, seed=0):
    """Analyze one frequency; failed controls mask only the accepted ratio.

    Bad shapes and bootstrap settings are programming errors. Missing/nonfinite
    experimental data return an unresolved JSON-safe report so a scan can retain
    the point and continue. The runner must persist original IQ separately.
    """
    iq = np.asarray(iq, dtype=complex)
    ground = np.asarray(ground_iq, dtype=complex).reshape(-1)
    excited = np.asarray(excited_iq, dtype=complex).reshape(-1)
    if iq.ndim != 2 or iq.shape[1] != 12:
        raise ValueError('iq must have shape (ncycles, 12), in phase-major order')
    if isinstance(bootstrap_draws, bool) or int(bootstrap_draws) != bootstrap_draws or bootstrap_draws < 20:
        raise ValueError('bootstrap_draws must be an integer of at least 20')
    report = {
        'valid': False, 'status': 'unresolved', 'reasons': [],
        'cycles': int(len(iq)), 'reference_shots': {
            'ground': int(len(ground)), 'excited': int(len(excited))},
        'ratio': None, 'raw_ratio': None, 'ratio_ci95': None,
        'ratio_estimator': 'noise-debiased magnitude long/short; raw_ratio also retained',
        'groups': {name: {'visibility': None} for name in GROUPS},
        'readout': None, 'bootstrap': None,
        'thresholds': {
            'minimum_cycles': MIN_CYCLES,
            'minimum_reference_shots': MIN_REFERENCE_SHOTS,
            'minimum_readout_snr': MIN_REFERENCE_SNR,
            'minimum_control_snr': MIN_CONTROL_SNR,
            'minimum_short_visibility': MIN_SHORT_VISIBILITY,
            'minimum_late_visibility': MIN_LATE_VISIBILITY,
            'late_extremum_tolerance': EXTREMUM_TOLERANCE,
            'opposite_pair_sum_tolerance': PAIR_SUM_TOLERANCE,
            'opposite_pair_sum_sigmas': PAIR_SUM_SIGMAS},
    }
    reasons = report['reasons']
    if len(iq) < MIN_CYCLES:
        reasons.append('too few complete cycles')
    if min(len(ground), len(excited)) < MIN_REFERENCE_SHOTS:
        reasons.append('too few readout reference shots')
    if not np.isfinite(iq).all():
        reasons.append('nonfinite science IQ')
    if not np.isfinite(ground).all() or not np.isfinite(excited).all():
        reasons.append('nonfinite readout reference IQ')
    if reasons:
        return report

    g, e = ground.mean(), excited.mean()
    axis = e - g
    scale = abs(axis)
    if scale <= np.finfo(float).eps * max(1., abs(g), abs(e)):
        reasons.append('readout reference axis is zero')
        return report
    unit = axis / scale
    ground_projection = np.real(ground * np.conj(unit))
    excited_projection = np.real(excited * np.conj(unit))
    reference_noise = math.sqrt(float(ground_projection.var(ddof=1) / len(ground) +
                                      excited_projection.var(ddof=1) / len(excited)))
    report['readout'] = {'separation': float(scale),
                         'separation_standard_error': reference_noise,
                         'separation_snr': _snr(scale, reference_noise),
                         'ground_mean_iq': [float(g.real), float(g.imag)],
                         'excited_mean_iq': [float(e.real), float(e.imag)]}
    if not _significant(scale, reference_noise, MIN_REFERENCE_SNR):
        reasons.append('readout reference separation unresolved')
        return report

    response = np.real((iq - g) / axis)
    groups = {name: _group_report(response[:, index::3], scale)
              for index, name in enumerate(GROUPS)}
    report['groups'] = groups
    short, long, late = [groups[name] for name in GROUPS]
    if short['visibility'] > 0:
        report['raw_ratio'] = long['visibility'] / short['visibility']
    if short['visibility'] < MIN_SHORT_VISIBILITY or not short['signal_resolved']:
        reasons.append('short echo contrast unresolved or below control threshold')
    late_valid = (late['visibility'] >= MIN_LATE_VISIBILITY and
                  late['signal_resolved'] and
                  abs(late['minimum']) <= EXTREMUM_TOLERANCE and
                  abs(late['maximum'] - 1.) <= EXTREMUM_TOLERANCE)
    if not late_valid:
        reasons.append('late pulse projection control failed')
    # A zero long contrast is allowed. A grossly incompatible phase shape
    # is an acquisition/pulse warning at any delay, not evidence of a dip.
    for name in GROUPS:
        if not groups[name]['phase_fit_valid']:
            reasons.append(f'{name} four-phase shape failed')
    if short['debiased_visibility'] <= 0:
        reasons.append('short echo denominator undefined after noise correction')
    bootstrap = _bootstrap(iq, ground, excited, int(bootstrap_draws), int(seed))
    report['bootstrap'] = bootstrap
    if bootstrap['valid_fraction'] < .9:
        reasons.append('short denominator unresolved in bootstrap samples')
    if not reasons:
        report.update(valid=True, status='resolved',
                      ratio=long['debiased_visibility'] / short['debiased_visibility'],
                      ratio_ci95=bootstrap['ratio_interval_95'])
    return report
