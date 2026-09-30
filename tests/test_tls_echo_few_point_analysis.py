"""Statistical checks for the paired, four-phase few-point echo screen."""
import importlib
import json

import numpy as np
import pytest


MODULE = ('WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.'
          'TLSEchoFewPointAnalysis')


def analyze(*args, **kwargs):
    return importlib.import_module(MODULE).analyze_site(*args, **kwargs)


def sample(*, visibility=(.9, .405, .94), phase=.37, shots=256, noise=.10):
    rng = np.random.default_rng(700)
    angles = np.repeat(np.deg2rad([0, 90, 180, 270]), 3)
    amplitudes = np.tile(visibility, 4)
    response = .5 + .5 * amplitudes * np.cos(angles - phase)
    g, axis = 1 - 2j, 2 + 1j
    iq = g + axis * (response + rng.normal(0, noise, (shots, 12)))
    iq += 1j * axis * rng.normal(0, noise, (shots, 12))
    ground = g + axis * (rng.normal(0, noise, 400) +
                         1j * rng.normal(0, noise, 400))
    excited = g + axis * (1 + rng.normal(0, noise, 400) +
                          1j * rng.normal(0, noise, 400))
    return iq, ground, excited


def test_recovers_two_delay_ratio_without_calling_it_a_t2_or_hotspot():
    result = analyze(*sample(), bootstrap_draws=100)
    assert result['valid'] and result['status'] == 'resolved'
    assert result['ratio'] == pytest.approx(.45, abs=.035)
    assert result['groups']['short']['visibility'] == pytest.approx(.9, abs=.035)
    assert result['groups']['late']['visibility'] == pytest.approx(.94, abs=.035)
    assert result['ratio_ci95'][0] < .45 < result['ratio_ci95'][1]
    assert result['groups']['long']['visibility_snr'] > 3
    assert 't2_us' not in result and 'hotspot' not in result
    json.dumps(result, allow_nan=False)


def test_iq_offset_scale_and_rotation_leave_ratio_and_controls_invariant():
    iq, g, e = sample()
    baseline = analyze(iq, g, e, bootstrap_draws=40, seed=14)
    transform = -2 * np.exp(.8j)
    other = analyze(iq * transform + 7j, g * transform + 7j,
                    e * transform + 7j, bootstrap_draws=40, seed=14)
    assert other['valid'] == baseline['valid']
    assert other['ratio'] == pytest.approx(baseline['ratio'], abs=1e-12)
    assert other['ratio_ci95'] == pytest.approx(baseline['ratio_ci95'], abs=1e-12)
    assert other['groups']['short']['raw_visibility'] == pytest.approx(
        2 * baseline['groups']['short']['raw_visibility'])


def test_echo_phase_rotation_does_not_make_false_coherence_dip():
    a = analyze(*sample(phase=.1, noise=0), bootstrap_draws=20)
    b = analyze(*sample(phase=1.9, noise=0), bootstrap_draws=20)
    assert a['valid'] and b['valid']
    assert a['ratio'] == pytest.approx(.45, abs=1e-12)
    assert b['ratio'] == pytest.approx(.45, abs=1e-12)


def test_long_signal_may_be_zero_without_failing_control_gate():
    result = analyze(*sample(visibility=(.9, 0, .94)), bootstrap_draws=60)
    assert result['valid']
    assert result['ratio'] < .035
    assert result['groups']['long']['visibility_snr'] < 3
    assert result['groups']['long']['debiased_visibility'] <= result['groups']['long']['visibility']
    assert result['ratio_ci95'][0] == 0


def test_low_snr_short_denominator_is_unresolved_even_with_positive_magnitude():
    result = analyze(*sample(visibility=(0, 0, .94)), bootstrap_draws=30)
    assert not result['valid']
    assert result['ratio'] is None and result['ratio_ci95'] is None
    assert any('short' in reason for reason in result['reasons'])
    assert result['groups']['short']['visibility'] > 0


def test_late_pulse_control_failure_preserves_measured_science_but_masks_ratio():
    result = analyze(*sample(visibility=(.9, .405, .15)), bootstrap_draws=30)
    assert not result['valid'] and result['status'] == 'unresolved'
    assert result['ratio'] is None
    assert result['raw_ratio'] == pytest.approx(.45, abs=.04)
    assert any('late' in reason for reason in result['reasons'])


def test_four_phase_shape_failure_is_detected_for_controls():
    iq, g, e = sample(noise=.01)
    # A first-harmonic phase circle cannot have different opposite-pair sums.
    iq[:, 0] += .5 * (2 + 1j)
    result = analyze(iq, g, e, bootstrap_draws=30)
    assert not result['valid']
    assert not result['groups']['short']['phase_fit_valid']
    assert any('phase' in reason for reason in result['reasons'])


@pytest.mark.parametrize('bad', ['identical', 'nan', 'too_noisy'])
def test_bad_reference_axis_returns_json_safe_unresolved(bad):
    iq, g, e = sample()
    if bad == 'identical':
        g = np.zeros(400, complex)
        e = g.copy()
    elif bad == 'nan':
        e[5] = np.nan
    else:
        rng = np.random.default_rng(33)
        g = rng.normal(0, 100, 400).astype(complex)
        e = rng.normal(0, 100, 400).astype(complex)
    result = analyze(iq, g, e, bootstrap_draws=30)
    assert not result['valid'] and result['ratio'] is None
    assert any('readout' in reason for reason in result['reasons'])
    json.dumps(result, allow_nan=False)


def test_shared_cycle_and_reference_resampling_preserve_exact_paired_ratio():
    rng = np.random.default_rng(22)
    phase = np.repeat(np.deg2rad([0, 90, 180, 270]), 3)
    amplitudes = np.tile([.9, .36, .95], 4)
    # Every whole cycle has exactly the same long/short ratio, despite noise.
    scale = rng.uniform(.8, 1.2, 200)
    offset = rng.uniform(-.3, .3, 200)
    iq = (.5 + offset[:, None] +
          .5 * scale[:, None] * amplitudes * np.cos(phase)).astype(complex)
    g = rng.normal(0, .08, 400).astype(complex)
    e = (1 + rng.normal(0, .08, 400)).astype(complex)
    result = analyze(iq, g, e, bootstrap_draws=100, seed=7)
    assert result['valid']
    assert result['ratio'] == pytest.approx(.4, abs=1e-12)
    assert result['ratio_ci95'] == pytest.approx([.4, .4], abs=1e-12)
    assert result['bootstrap']['ratio_standard_error'] < 1e-12


def test_analysis_validates_shape_and_does_not_hide_missing_records():
    _, g, e = sample()
    with pytest.raises(ValueError, match='12'):
        analyze(np.zeros((200, 11), complex), g, e)
    result = analyze(np.zeros((10, 12), complex), g, e, bootstrap_draws=30)
    assert not result['valid'] and result['ratio'] is None
    assert any('cycles' in reason for reason in result['reasons'])


def test_gross_long_phase_shape_failure_masks_candidate_without_requiring_long_signal():
    iq, g, e = sample(noise=.02)
    # Corrupt only the long-delay 0-degree arm, leaving both controls healthy.
    iq[:, 1] += .5 * (2 + 1j)
    result = analyze(iq, g, e, bootstrap_draws=30)
    assert result['groups']['short']['phase_fit_valid']
    assert result['groups']['late']['phase_fit_valid']
    assert not result['groups']['long']['phase_fit_valid']
    assert not result['valid'] and result['ratio'] is None
    assert any('long' in reason and 'phase' in reason for reason in result['reasons'])
    assert result['raw_ratio'] is not None
