"""Check fixed-grid chronology, carryover controls and reference validity."""
import importlib
import numpy as np
import pytest


@pytest.fixture
def experiment():
    class Module:
        def __getattr__(self, key):
            name = 'WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSAfterglowTimeMap'
            assert importlib.util.find_spec(name), 'afterglow time-map runner is missing'
            return getattr(importlib.import_module(name), key)
    return Module()


def test_fixed_grid_reverses_both_frequency_and_condition_order(experiment):
    request = experiment.plan()
    a, b = (experiment.tasks(request, pass_index=i) for i in (0, 1))
    assert request['frequency_points'] == 26
    assert len(a) == len(b) == 26
    assert [t['frequency_ghz'] for t in a] == list(reversed([t['frequency_ghz'] for t in b]))
    assert sorted(t['frequency_ghz'] for t in a) == pytest.approx(np.arange(4000, 4051, 2)/1000)
    assert set(t['name'] for t in a).isdisjoint(t['name'] for t in b)
    for x, y in zip(a, reversed(b)):
        assert x['conditions'] == list(reversed(y['conditions']))
        assert {(c['pump_state'], c['probe_us']) for c in x['conditions']} == {
            (state, delay) for state in ('g', 'e') for delay in (.1, 10., 40.)}
        assert all(c['pump_ghz'] == c['probe_ghz'] == x['frequency_ghz'] for c in x['conditions'])
    assert request['probe_records_per_pass'] == sum(t['shots']*6 for t in a)
    assert request['passes'] == 1 and not request['active_reset']


@pytest.mark.parametrize('kwargs', [dict(freq_start=3.7), dict(freq_stop=4.4),
    dict(freq_stop=4.049), dict(step_mhz=0), dict(shots=1), dict(shots=400.5),
    dict(passes=-1), dict(freq_start=float('nan'))])
def test_invalid_requests_fail_before_connection(experiment, kwargs):
    with pytest.raises(ValueError):
        experiment.plan(**kwargs)


AXES = dict(herald=dict(theta_rad=0., ground_limit=0.),
            final=dict(theta_rad=0., threshold=0.))


def cells(module, deltas):
    task = module.tasks(module.plan(shots=4000, freq_stop=4.), pass_index=0)[0]
    rng = np.random.default_rng(2)
    words = np.zeros((4000, 6, 4), dtype=np.int64)
    for j, arm in enumerate(task['conditions']):
        words[:, j, 0] = np.where(rng.random(4000)<.8, -10, 10)
        p = .1 + (deltas[arm['probe_us']] if arm['pump_state']=='e' else 0.)
        words[:, j, 2] = np.where(rng.random(4000)<p, 10, -10)
    summary = module.diagonal.summarize_program(words.reshape(-1, 4), task, AXES, (-10., 10.))
    return [dict(task=task, summary=summary, started_at='2026-10-04T12:00:03+00:00',
                 completed_at='2026-10-04T12:00:15+00:00', realized_ghz=4.00001)]


def test_rows_preserve_point_times_and_separate_growth_from_carryover(experiment):
    bounds = [dict(pass_index=0, started_at='2026-10-04T12:00:00+00:00',
        completed_at='2026-10-04T12:05:00+00:00', controls='valid')]
    records = cells(experiment, {.1:.2, 10.:.1, 40.:.03})
    rows = experiment.map_rows(records, bounds)
    assert len(rows) == 3 and all(r['valid'] for r in rows)
    assert all(r['cell_started_at']==records[0]['started_at'] for r in rows)
    assert all(r['realized_frequency_ghz']==4.00001 for r in rows)
    long = next(r for r in rows if r['probe_us']==40.)
    assert long['excess'] > 0 and long['growth'] < -.1
    assert long['growth_error'] > 0
    assert long['hot_accepted'] > 0 and long['cold_accepted'] > 0
    assert next(r for r in rows if r['probe_us']==.1)['growth'] == 0.


def test_failed_or_pending_reference_rows_are_not_validated(experiment):
    records = cells(experiment, {.1:0., 10.:.2, 40.:.1})
    for state in ('pending', 'invalid'):
        rows = experiment.map_rows(records, [dict(pass_index=0,
            started_at=records[0]['started_at'], completed_at=None, controls=state)])
        assert not any(r['valid'] for r in rows)
        assert all(r['controls']==state for r in rows)
        assert next(r for r in rows if r['probe_us']==10.)['growth'] > .1


def test_map_refuses_duplicate_cells_or_reversed_timestamps(experiment):
    records = cells(experiment, {.1:0., 10.:.2, 40.:.1})
    bounds = [dict(pass_index=0, started_at=records[0]['started_at'],
                   completed_at=records[0]['completed_at'], controls='valid')]
    with pytest.raises(ValueError, match='duplicate'):
        experiment.map_rows(records*2, bounds)
    records[0]['completed_at'] = '2026-10-04T11:59:59+00:00'
    with pytest.raises(ValueError, match='time'):
        experiment.map_rows(records, bounds)
    records[0]['started_at'] = '2026-10-04T12:00:00'
    records[0]['completed_at'] = '2026-10-04T12:00:15+00:00'
    with pytest.raises(ValueError, match='time'):
        experiment.map_rows(records, bounds)


def test_csv_and_plot_keep_missing_frequency_cells_blank(experiment, tmp_path):
    request = experiment.plan()
    records = cells(experiment, {.1:0., 10.:.2, 40.:.1})
    bounds = [dict(pass_index=0, started_at=records[0]['started_at'],
                   completed_at=records[0]['completed_at'], controls='valid')]
    rows = experiment.map_rows(records, bounds)
    experiment.write_csv(tmp_path/'afterglow_vs_wall_clock.csv', rows)
    import csv
    with (tmp_path/'afterglow_vs_wall_clock.csv').open() as f:
        saved = list(csv.DictReader(f))
    assert len(saved)==3 and saved[0]['cell_started_at']==records[0]['started_at']
    arrays = experiment.map_arrays(request, rows, bounds, metric='growth')
    assert arrays[10.].shape == (1, 26)
    assert np.isfinite(arrays[10.]).sum()==1
    experiment.plot_results(tmp_path, request, rows, bounds)
    assert (tmp_path/'afterglow_vs_wall_clock.png').stat().st_size > 1000
    assert (tmp_path/'afterglow_growth_vs_wall_clock.png').stat().st_size > 1000
    assert (tmp_path/'afterglow_latest_spectrum.png').stat().st_size > 1000


def test_finalization_preserves_acquisition_error_and_completed_raw_data(experiment, tmp_path, monkeypatch):
    acquired = RuntimeError('stream interrupted')
    manifest = dict(status='failed')
    events = []
    monkeypatch.setattr(experiment.diagonal, 'abort_and_record', lambda soc, m: events.append('abort'))
    module = importlib.import_module('WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSAfterglowTimeMap')
    monkeypatch.setattr(module, 'plot_results', lambda *args: (_ for _ in ()).throw(OSError('plot unavailable')))
    def save(path, value):
        events.append(('save', path.name, dict(value)))
    records = cells(experiment, {.1:0.,10.:.2,40.:.1})
    passes = [dict(pass_index=0, started_at=records[0]['started_at'],completed_at=None,controls='pending')]
    experiment.finalize(tmp_path, manifest, records, passes, experiment.plan(), object(), save, acquired)
    assert events[0]=='abort'
    assert (tmp_path/'afterglow_vs_wall_clock.csv').exists()
    assert 'plot unavailable' in manifest['finalization_error']
    assert events[-1][1]=='manifest.json'
    with pytest.raises(OSError, match='plot unavailable'):
        experiment.finalize(tmp_path, manifest, records, passes, experiment.plan(), object(), save, None)


def test_bank_decoder_retains_transferred_records_for_ctrl_c_recovery(experiment):
    program = experiment.TimeMapProgram.__new__(experiment.TimeMapProgram)
    program.received_records = []
    words = np.arange(24).reshape(6, 4)
    decoded = program.decode_dmem_records(words, expected_records=6)
    assert len(program.received_records)==6
    assert experiment.diagonal.words_from_records(program.received_records).tolist()==words.tolist()
    assert program.received_records==decoded
    with pytest.raises(ValueError):
        program.decode_dmem_records([1,2,3], expected_records=1)
    assert len(program.received_records)==6


def test_large_workload_cannot_run_hours_between_reference_checks(experiment):
    with pytest.raises(ValueError, match='workload'):
        experiment.plan(freq_start=3.8,freq_stop=4.3,step_mhz=.5,shots=4000)
    wide = experiment.plan(freq_start=3.8,freq_stop=4.3,shots=200)
    assert wide['science_sequence_minimum_minutes'] == pytest.approx(25.1)


def test_cli_reports_uncertain_references_as_nonzero_exit(experiment, tmp_path, monkeypatch, capsys):
    module = importlib.import_module('WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSAfterglowTimeMap')
    import json
    (tmp_path/'manifest.json').write_text(json.dumps(dict(status='complete_controls_uncertain')))
    monkeypatch.setattr(module,'run',lambda **kwargs:tmp_path)
    assert experiment.main(['--run'])==2
    assert 'complete_controls_uncertain' in capsys.readouterr().out
