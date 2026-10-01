"""Reject qubit carryover, incomplete streams and unreplicated screen peaks."""
import importlib
import numpy as np
import pytest


@pytest.fixture
def experiment():
    name = 'WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSAfterglowDiagonal'
    assert importlib.util.find_spec(name), 'diagonal afterglow screen is not implemented'
    return importlib.import_module(name)


def test_blind_grid_pairs_short_probe_and_loaded_controls_in_every_shot(experiment):
    specs = experiment.tasks()
    assert len(specs) == 122
    assert len({s['frequency_ghz'] for s in specs}) == 61
    for spec in specs:
        assert {(a['pump_state'], a['probe_us']) for a in spec['conditions']} == {
            (s, t) for s in ('g', 'e') for t in (.1, 10., 40.)}
        assert all(a['pump_ghz'] == a['probe_ghz'] == spec['frequency_ghz']
                   for a in spec['conditions'])
        assert all(a['pump_us'] == 10. and a['probe_state'] == 'g'
                   and a['interstage_extra_us'] == 0 for a in spec['conditions'])
    for f in {s['frequency_ghz'] for s in specs}:
        pair = [s for s in specs if s['frequency_ghz'] == f]
        assert pair[0]['conditions'] == list(reversed(pair[1]['conditions']))
    assert experiment.plan()['probe_shots'] == sum(s['shots'] * 6 for s in specs)
    assert experiment.plan()['automatic_two_frequency_scan'] is False


def sample_words(module, task, deltas, *, seed=0, shots=4000):
    rng = np.random.default_rng(seed)
    words = np.zeros((shots, 6, 4), dtype=np.int64)
    for j, arm in enumerate(task['conditions']):
        # Clean references define IQ units; heralding accepts independent 75%.
        words[:, j, 0] = np.where(rng.random(shots) < .75, -10, 10)
        p = .10 + (deltas[arm['probe_us']] if arm['pump_state'] == 'e' else 0.)
        words[:, j, 2] = np.where(rng.random(shots) < p, 10, -10)
    return words.reshape(-1, 4)


AXES = dict(herald=dict(theta_rad=0., ground_limit=0.),
            final=dict(theta_rad=0., threshold=0.))


def test_analysis_requires_growth_after_short_probe_not_just_hot_qubit(experiment):
    tasks = [s for s in experiment.tasks(shots=4000) if s['frequency_ghz'] == 4.05]
    def report(deltas):
        cells = [experiment.summarize_program(
            sample_words(experiment, s, deltas, seed=i), s, AXES, (-10., 10.))
                 for i, s in enumerate(tasks)]
        return experiment.analyze(cells, controls_valid=True)
    carryover = report({.1: .20, 10.: .10, 40.: .03})
    assert not carryover['candidate_frequencies_ghz']
    returning = report({.1: .00, 10.: .15, 40.: .08})
    assert returning['candidate_frequencies_ghz'] == [4.05]
    assert returning['sites'][0]['delays'][0]['excess'] == pytest.approx(0., abs=.03)
    assert returning['sites'][0]['delays'][1]['growth'] > .10


def test_no_screen_hit_with_bad_references_one_block_or_reversed_sign(experiment):
    tasks = [s for s in experiment.tasks(shots=4000) if s['frequency_ghz'] == 4.05]
    cells = [experiment.summarize_program(
        sample_words(experiment, s, {.1: 0., 10.: .15, 40.: .10}, seed=i),
        s, AXES, (-10., 10.)) for i, s in enumerate(tasks)]
    assert not experiment.analyze(cells, controls_valid=False)['candidate_frequencies_ghz']
    assert not experiment.analyze(cells[:1], controls_valid=True)['candidate_frequencies_ghz']
    cells[1] = experiment.summarize_program(
        sample_words(experiment, tasks[1], {.1: 0., 10.: -.05, 40.: -.05}, seed=10),
        tasks[1], AXES, (-10., 10.))
    assert not experiment.analyze(cells, controls_valid=True)['candidate_frequencies_ghz']


def test_herald_uses_only_first_readout_and_saves_all_shot_result(experiment):
    task = experiment.tasks(shots=400)[0]
    words = sample_words(experiment, task, {.1: 0., 10.: 0., 40.: 0.}, shots=400)
    result = experiment.summarize_program(words, task, AXES, (-10., 10.))
    changed = words.copy()
    changed[changed[:, 0] > 0, 2] = 10000
    other = experiment.summarize_program(changed, task, AXES, (-10., 10.))
    for a, b in zip(result['conditions'], other['conditions']):
        assert a['accepted'] == b['accepted']
        assert a['conditional_pe'] == b['conditional_pe']
        assert a['conditional_iq'] == b['conditional_iq']
    with pytest.raises(ValueError, match='incomplete'):
        experiment.summarize_program(words[:-1], task, AXES, (-10., 10.))


def test_paired_growth_uncertainty_uses_shared_baseline_covariance(experiment):
    task = experiment.tasks(shots=4000)[0]
    result = experiment.summarize_program(
        sample_words(experiment, task, {.1: 0., 10.: .1, 40.: .1}),
        task, AXES, (-10., 10.))
    assert np.shape(result['covariance']) == (6, 6)
    assert np.linalg.eigvalsh(result['covariance']).min() > -1e-12
    assert result['contrasts'][0]['growth'] == 0.
    assert result['contrasts'][0]['growth_error'] == 0.


def test_failed_abort_is_recorded_without_masking_original_error(experiment, monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import acquisition
    def broken_abort(soc):
        raise ConnectionError('board disconnected during stop')
    monkeypatch.setattr(acquisition, '_safe_abort', broken_abort)
    manifest = dict(status='failed', error='original acquisition error')
    experiment.abort_and_record(object(), manifest)
    assert manifest['error'] == 'original acquisition error'
    assert 'board disconnected' in manifest['abort_errors'][0]


def test_small_noisy_positive_difference_is_not_a_candidate(experiment):
    # A 0.04 effect with 0.04 SE in each order would pass a sign-only screen.
    cells = [dict(block=b, frequency_ghz=4.05, contrasts=[
        dict(probe_us=t, valid=True, excess=.04, excess_error=.04,
             growth=0. if t == .1 else .04, growth_error=0. if t == .1 else .04,
             iq_excess=.04, iq_growth=.04)
        for t in (.1, 10., 40.)]) for b in (0, 1)]
    result = experiment.analyze(cells, controls_valid=True)
    assert result['candidate_frequencies_ghz'] == []
