import importlib
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


def module():
    return importlib.import_module('WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSEchoFewPointMap')


def test_first_screen_is_bounded_dense_and_phase_cycled(capsys):
    m = module()
    p = m.plan()
    grid = m.frequency_grid()
    assert len(grid) == 101
    assert grid[0] == 4.3 and grid[-1] == 4.25
    assert np.diff(grid) == pytest.approx(np.full(100, -.0005))
    assert p['shots_per_condition'] == 200
    assert p['conditions_per_cycle'] == 12
    assert p['echo_elapsed_us'] == [.35, 1.35]
    assert p['anchor_ghz'] == 4.288
    assert p['t1_scans'] is None
    assert p['full_decay_fit'] is False
    assert p['reference_every_points'] == 10
    assert m.main(['--plan']) == 0
    assert json.loads(capsys.readouterr().out) == p


def test_submegahertz_site_keys_never_collide():
    m = module()
    keys = [m.site_key(i, f) for i, f in enumerate(m.frequency_grid())]
    assert len(set(keys)) == 101
    assert '4299500kHz' in keys[1]


def test_whole_first_screen_preserves_raw_data_checks_and_unique_configs(tmp_path, monkeypatch, capsys):
    m = module()
    calls = []
    compiled = []
    rng = np.random.default_rng(22)

    def build(frequency, kind, shots, condition=None):
        cfg = dict(frequency_ghz=frequency, kind=kind, shots=shots,
                   condition=condition, compiled_marker=7)
        compiled.append(cfg)
        return SimpleNamespace(cfg=cfg)

    def acquire(program, shots, subshots):
        cfg = program.cfg
        calls.append(cfg)
        assert subshots == (12 if cfg['kind'] == 'batch' else 1)
        if cfg['kind'] == 'batch':
            values = []
            for phase in (0, 90, 180, 270):
                for amplitude in (.40, .18, .48):
                    values.append(.5 + amplitude*np.cos(np.deg2rad(phase)))
            if cfg['frequency_ghz'] == 4.275:
                values = np.full(12, .5)
            return np.array(values)[None, :] + rng.normal(0, .08, (shots, 12)) + 1j*rng.normal(0, .08, (shots, 12))
        if cfg['kind'] == 'individual':
            c = cfg['condition']
            amplitude = {'short': .4, 'long': .18, 'late': .48}[c['group']]
            mean = .5 + amplitude*np.cos(np.deg2rad(c['phase_deg']))
        else:
            mean = 0. if cfg['kind'] == 'ground' else 1.
        return mean + rng.normal(0, .08, shots) + 1j*rng.normal(0, .08, shots)

    @contextmanager
    def hardware(data_root, correction):
        yield SimpleNamespace(build=build, acquire=acquire,
            metadata={'board_configuration': {'clock_mhz': 430.08}},
            realized_frequency={f: f-.00001 for f in (*m.frequency_grid(), 4.288)})

    correction = tmp_path/'correction.json'
    correction.write_text('{}')
    monkeypatch.setattr(m.localizer, 'checked_correction', lambda *_: correction)
    monkeypatch.setattr(m, '_hardware_session', hardware)
    path = m.run(data_root=tmp_path)
    saved = json.loads(path.read_text())
    assert saved['status'] == 'complete_few_point_screen'
    assert len(saved['sites']) == 101
    assert len(saved['anchors']) == 3
    assert len(saved['references']) == 12
    assert len([c for c in calls if c['kind'] == 'batch']) == 104
    assert len([c for c in calls if c['kind'] == 'individual']) == 12
    assert len([c for c in calls if c['kind'] in ('ground', 'excited')]) == 24
    assert len({c['raw_npz'] for c in saved['acquisitions']}) == len(calls)
    configs = [c['program_config_json'] for c in saved['acquisitions']]
    assert len(set(configs)) == len(calls)
    for c in saved['acquisitions']:
        assert c['status'] == 'complete'
        cfg = json.loads(Path(c['program_config_json']).read_text())
        assert cfg['compiled_marker'] == 7
        with np.load(c['raw_npz']) as data:
            assert data['iq'].shape == ((200, 12) if c['kind'] == 'batch' else
                                       (200,) if c['kind'] == 'individual' else (400,))
    bad = next(s for s in saved['sites'] if s['frequency_ghz'] == 4.275)
    assert bad['analysis']['valid'] is False
    assert len(saved['sites']) == 101  # Bad local contrast never stops other sites.
    good = next(s for s in saved['sites'] if s['frequency_ghz'] == 4.288)
    assert good['analysis']['valid'] is True
    assert good['analysis']['ratio'] == pytest.approx(.45, abs=.06)
    assert good['realized_frequency_ghz'] == pytest.approx(4.28799)
    assert saved['batching_bridge']['batched']['ratio'] == pytest.approx(.45, abs=.06)
    assert saved['batching_bridge']['individual']['ratio'] == pytest.approx(.45, abs=.06)
    assert Path(saved['summary_csv']).is_file()
    assert capsys.readouterr().out == ''


def test_incomplete_batch_is_saved_as_failure_and_never_called_complete(tmp_path, monkeypatch):
    m = module()
    correction = tmp_path/'correction.json'
    correction.write_text('{}')
    monkeypatch.setattr(m.localizer, 'checked_correction', lambda *_: correction)

    @contextmanager
    def hardware(*_):
        yield SimpleNamespace(
            build=lambda f,k,s,condition=None: SimpleNamespace(cfg={'kind':k}),
            acquire=lambda p,s,n: np.zeros((s-1,12), complex) if n==12 else np.zeros(s,complex),
            metadata={}, realized_frequency={f:f for f in (*m.frequency_grid(),4.288)})
    monkeypatch.setattr(m, '_hardware_session', hardware)
    with pytest.raises(RuntimeError, match='incomplete'):
        m.run(data_root=tmp_path)
    manifests = list(tmp_path.glob('q3/q3_echo_few_point_*/manifest.json'))
    assert len(manifests) == 1
    saved = json.loads(manifests[0].read_text())
    assert saved['status'] == 'failed'
    assert saved['acquisitions'][-1]['status'] == 'incomplete'
    assert Path(saved['acquisitions'][-1]['raw_npz']).is_file()


def test_nonfinite_second_reference_bracket_has_json_safe_failure():
    m = module()
    before = {'ground': np.zeros(30,complex), 'excited': np.ones(30,complex)}
    after = {'ground': np.full(30,complex(float('nan'), 0)), 'excited': np.ones(30,complex)}
    report = m._reference_stability(before, after)
    assert report['valid'] is False
    json.dumps(report, allow_nan=False)


def test_reference_brackets_reject_movement_and_rotation():
    m = module()
    before = {'ground': np.zeros(30,complex), 'excited': np.ones(30,complex)}
    assert m._reference_stability(before, before)['valid'] is True
    shifted = {key: value + .3 for key,value in before.items()}
    rotated = {key: value * 1j for key,value in before.items()}
    assert m._reference_stability(before, shifted)['valid'] is False
    assert m._reference_stability(before, rotated)['valid'] is False


def test_timeout_keeps_recovered_complete_cycles(tmp_path, monkeypatch):
    m = module()
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.acquisition import AcquisitionTimeout
    correction = tmp_path/'correction.json'
    correction.write_text('{}')
    monkeypatch.setattr(m.localizer, 'checked_correction', lambda *_: correction)

    def acquire(program, shots, subshots):
        if subshots == 12:
            raise AcquisitionTimeout('lost stream', completed_shots=3,
                partial_records=[SimpleNamespace(iq=tuple(complex(i, -i) for i in range(12))) for _ in range(3)])
        return np.ones(shots,complex) if program.cfg['kind']=='excited' else np.zeros(shots,complex)

    @contextmanager
    def hardware(*_):
        yield SimpleNamespace(build=lambda f,k,s,condition=None: SimpleNamespace(cfg={'kind':k}),
            acquire=acquire, metadata={}, realized_frequency={f:f for f in (*m.frequency_grid(),4.288)})
    monkeypatch.setattr(m, '_hardware_session', hardware)
    with pytest.raises(AcquisitionTimeout, match='lost stream'):
        m.run(data_root=tmp_path)
    path = next(tmp_path.glob('q3/q3_echo_few_point_*/manifest.json'))
    saved = json.loads(path.read_text())
    assert saved['status'] == 'failed'
    current = saved['acquisitions'][-1]
    with np.load(current['raw_npz']) as raw:
        assert raw['iq'].shape == (3,12)
        assert raw['iq'][0,11] == 11-11j
    assert current['partial_records_saved'] == 3
    assert current['status'] == 'failed'
