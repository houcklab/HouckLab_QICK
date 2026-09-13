import numpy as np
import pytest

from fluxpred.core import Filter, render
from fluxpred.validation import flatness, build_shot, acceptance, load_candidate


def test_metric_definitions_and_support_are_explicit():
    t = np.arange(1000, 498000, 4000)
    f = np.where(t <= 21000, 1.0, 0.0)
    support = np.ones(len(t), bool); support[0] = False; f[0] = 1000
    result = flatness(t, f, support, smooth_window=1)
    assert result['early_minus_late_mhz'] == 1
    assert result['smooth_rms_mhz'] == pytest.approx(np.sqrt(5/124))
    assert result['supported_fraction'] == pytest.approx(124/125)


def test_no_acceptance_from_smoothing_missing_support_or_only_model_predictions():
    passing = {'smooth_rms_mhz': .1, 'early_minus_late_mhz': .2, 'supported_fraction': 1}
    assert acceptance([passing]*3, held_out_supported=True)['numerical_targets_pass']
    assert not acceptance([passing]*3, held_out_supported=False)['scientific_gate_pass']
    assert not acceptance([dict(passing, smooth_rms_mhz=.3)]*3, held_out_supported=True)['scientific_gate_pass']
    assert not acceptance([dict(passing, supported_fraction=.5)]*3, held_out_supported=True)['scientific_gate_pass']
    assert not acceptance([passing]*3, held_out_supported=True)['hardware_ready']


def test_short_recovery_cannot_be_silently_cut():
    model = Filter([8000, 128000], [1], [[.02, -.015]])
    with pytest.raises(ValueError, match="tail"):
        build_shot(model, amplitude=1, hold_ns=100000, recovery_ns=40000)


@pytest.mark.parametrize('hold', [1000, 13000, 100000, 497000])
@pytest.mark.parametrize('reset_dwell', [16000, 124000])
def test_active_reset_variable_dwell_and_holds_preserve_history(hold, reset_dwell):
    model = Filter([8000, 128000], [1], [[.02, -.015]])
    # Reset is at park; a previous shot's state decays instead of being zeroed.
    _, state = render(model, [(1, 60000), (0, 40000)])
    full, _ = render(model, [(0, reset_dwell), (.8, hold), (0, 1600000)], initial_state=state)
    park, decayed = render(model, [(0, reset_dwell)], initial_state=state)
    shot = build_shot(model, amplitude=.8, hold_ns=hold, recovery_ns=1600000, initial_state=decayed)
    assert np.allclose(np.r_[park.values, shot['command'].values[:-1]], full.values)
    assert shot['command'].values[-1] == 0
    assert shot['terminal_tail_bound'] < 1e-5
    assert shot['target_end_ns'] == hold


def test_candidate_schema_and_calibration_binding(tmp_path):
    model = Filter([8000], [1], [[.02]])
    import json
    path = tmp_path/'candidate.json'
    document = {'schema_version': 1, 'model': model.to_dict(), 'coordinate': {'park': .18, 'scale': .24, 'unit': 'V'},
                'evidence': {'scientific_gate_pass': False, 'hardware_ready': False}}
    path.write_text(json.dumps(document))
    assert load_candidate(path, park=.18, scale=.24, unit='V')[0].to_dict() == model.to_dict()
    with pytest.raises(ValueError, match='coordinate'):
        load_candidate(path, park=.1625, scale=.24, unit='V')
    with pytest.raises(ValueError, match='gate'):
        load_candidate(path, park=.18, scale=.24, unit='V', require_scientific_gate=True)
