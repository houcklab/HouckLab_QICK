"""Catch mismatched controls, carryover mistaken for return, and lost banks."""
import importlib
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def experiment():
    name = 'WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSAfterglowFeedbackPilot'
    assert importlib.util.find_spec(name), 'feedback afterglow pilot is missing'
    return importlib.import_module(name)


def test_pilot_interleaves_sham_and_feedback_with_short_controls_and_reverses_order(experiment):
    ts = experiment.tasks()
    assert len(ts) == 6
    assert [t['frequency_ghz'] for t in ts] == [3.984, 3.862, 4.046, 4.046, 3.862, 3.984]
    for a, b in zip(ts[:3], ts[3:][::-1]):
        assert a['conditions'] == list(reversed(b['conditions']))
        assert {(c['pump_state'], c['feedback'], c['probe_us']) for c in a['conditions']} == {
            (s, feedback, t) for s in ('g', 'e') for feedback in (False, True) for t in (.1, 40.)}
    assert experiment.plan()['science_records'] == 28800
    assert experiment.plan()['automatic_long_scan'] is False
    with pytest.raises(ValueError):
        experiment.tasks(shots=2.5)


def make_cell(m, deltas, *, hot_fraction=.8):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.classifier import ClassifierCalibration
    c = ClassifierCalibration(1, 'loop', 0., 0, 1, 0, -20, 0, 100, {})
    bundle = SimpleNamespace(payload=c, loop=c)
    task = m.tasks(shots=4000)[0]
    w = np.zeros((4000, 8, 12), dtype=np.int64)
    rng = np.random.default_rng(421)
    for j, arm in enumerate(task['conditions']):
        w[:, j, 0:10:2] = -100
        mask = rng.random(4000) < (hot_fraction if arm['pump_state']=='e' else .8)
        w[:, j, 8] = np.where(mask, -100, 100)
        p = .10 + (deltas[arm['probe_us']] if arm['pump_state']=='e' else 0.)
        w[:, j, 10] = np.where(rng.random(4000)<p, 100, -100)
    axis = dict(theta_rad=0., threshold=0., low=-100., high=100.)
    return m.summarize_program(w.reshape(-1, 12), task, axis, bundle), w, task, axis, bundle


def test_positive_long_offset_without_growth_does_not_qualify(experiment):
    cell, *_ = make_cell(experiment, {.1:.20, 40.:.10})
    summary = experiment.analyze([cell, dict(cell, block=1)], controls_valid=True)
    r = summary['sites'][0]['feedback']
    assert r['long_excess'] > .05
    assert r['growth'] < -.05
    assert not r['preparation_comparable']
    assert not summary['followup_frequencies_ghz']


def test_ground_verified_growth_keeps_paired_covariance_and_failed_shots(experiment):
    cell, w, task, axis, bundle = make_cell(experiment, {.1:0., 40.:.25})
    assert cell['valid']
    assert len(cell['covariance']) == 8
    assert all(c['accepted'] < 4000 for c in cell['conditions'])
    # Hand-compute the conditional influence covariance, retaining every shot.
    keep = w[:, :, 8] < 0
    y = w[:, :, 10] > 0
    means = [y[:, j][keep[:, j]].mean() for j in range(8)]
    influence = keep*(y-np.array(means))/keep.mean(axis=0)
    assert cell['covariance'] == pytest.approx(np.cov(influence.T, ddof=1)/4000)
    summary = experiment.analyze([cell, dict(cell, block=1)], controls_valid=True)
    assert summary['sites'][0]['feedback']['growth'] > .20
    assert summary['followup_frequencies_ghz'] == [3.984]
    assert not experiment.analyze([cell, dict(cell, block=1)], controls_valid=False)['followup_frequencies_ghz']
    with pytest.raises(ValueError, match='duplicate'):
        experiment.analyze([cell, cell], controls_valid=True)
    w[0, 0, 0] = 32768
    assert not experiment.summarize_program(w.reshape(-1, 12), task, axis, bundle)['valid']


def test_reset_verification_and_both_blocks_are_required(experiment):
    cell, *_ = make_cell(experiment, {.1:0., 40.:.25}, hot_fraction=.01)
    assert not cell['valid']
    assert not experiment.analyze([cell, dict(cell, block=1)], controls_valid=True)['followup_frequencies_ghz']
    good, *_ = make_cell(experiment, {.1:0., 40.:.25})
    assert not experiment.analyze([good], controls_valid=True)['followup_frequencies_ghz']


def test_selection_only_growth_does_not_qualify_for_followup(experiment):
    cell, w, task, axis, bundle = make_cell(experiment, {.1:0., 40.:.25}, hot_fraction=.5)
    for j, arm in enumerate(task['conditions']):
        # Accepted hot shots rise; rejected hot shots remain cold, whereas
        # rejected cold-control shots heat. The all-shot trend is opposite.
        if arm['probe_us']==40.:
            bad = w[:, j, 8] > 0
            w[bad, j, 10] = -100 if arm['pump_state']=='e' else 100
    cell = experiment.summarize_program(w.reshape(-1, 12), task, axis, bundle)
    summary = experiment.analyze([cell, dict(cell, block=1)], controls_valid=True)
    r = summary['sites'][0]['feedback']
    assert r['growth'] > .2
    assert r['all_iq_growth'] < 0
    assert not summary['followup_frequencies_ghz']


def test_decoder_retains_complete_transferred_banks_on_interruption(experiment):
    p = experiment.FeedbackPilotProgram.__new__(experiment.FeedbackPilotProgram)
    p.transferred_records = []
    a = p.decode_dmem_records(np.zeros((5, 12), dtype=np.uint32), expected_records=5)
    assert len(a) == len(p.transferred_records) == 5
    p.decode_dmem_records(np.ones((3, 12), dtype=np.uint32), expected_records=3)
    assert len(p.transferred_records) == 8
    with pytest.raises(ValueError):
        p.decode_dmem_records(np.ones(11, dtype=np.uint32))
    assert len(p.transferred_records) == 8


def test_timing_tracking_calls_the_actual_program_base(experiment, monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs import OPXResetT1Program
    p = experiment.FeedbackPilotProgram.__new__(experiment.FeedbackPilotProgram)
    p._sync_ticks = 10
    p._dac_ts, p._adc_ts = [2., 4.], [3.]
    # Replace the external QICK timeline call, retaining the pilot accounting.
    monkeypatch.setattr(OPXResetT1Program, 'sync_all', lambda self, t: None, raising=False)
    p.sync_all(7)
    assert p._sync_ticks == 21
