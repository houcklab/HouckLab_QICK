import importlib
import json
from types import SimpleNamespace

import numpy as np
import pytest


def module():
    return importlib.import_module(
        'WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.Q4RepeatedT1')


def test_q4_plan_is_independent_of_q3_initialization(capsys):
    m = module()
    assert m.main(['--plan']) == 0
    p = json.loads(capsys.readouterr().out)
    assert p['qubit'] == 'q4'
    assert p['reset_mode'] == 'opx_unbounded'
    assert p['shots_per_delay'] == 1000
    assert len(p['delays_us']) == 71
    assert p['delays_us'][0] == 1.0
    assert p['delays_us'][-1] == 1500.0
    assert np.all(np.diff(p['delays_us']) > 0)
    cfg = m.base_config()
    assert (cfg['qubit_pi_freq'], cfg['read_pulse_freq']) == (4367.760, 7026.520)
    assert (cfg['qubit_pi_gain'], cfg['sigma']) == (32000, 2.0)
    assert cfg['ff_park_gain'] == 0
    cfg['FF_Qubits']['1']['channel'] = 99
    assert m.base_config()['FF_Qubits']['1']['channel'] == 3


def test_calibration_retains_long_passive_wait_and_runtime_uses_feedback():
    m = module()
    cal = m.calibration_config()
    run = m.measurement_config({'fixture': 'classifier'})
    assert cal['opx_inter_shot_delay_us'] == 1800
    assert cal['relax_delay'] == 1800
    assert run['opx_inter_shot_delay_us'] == 10
    assert run['opx_park_preroll_us'] == 1800
    assert run['reset_pi_freq'] == 4367.760
    assert run['opx_reset_calibration'] == {'fixture': 'classifier'}
    assert run['opx_reset_scheme'] == 'opx_unbounded'
    assert run['do_ff'] is False and run['ff_gain'] == 0
    assert cal['sigma'] == run['sigma'] == 2.0


def test_snapshot_keeps_source_and_local_overrides_byte_for_byte(tmp_path):
    m = module()
    source = tmp_path / 'initialize.py'
    override = tmp_path / 'initialize.local.py'
    source.write_bytes(b'# original\r\nBaseConfig = {}\r\n')
    override.write_bytes(b'BaseConfig = {"sigma": 0.2}\n')
    out = tmp_path / 'archive'
    report = m.snapshot_initialize(out, source=source)
    assert (out / source.name).read_bytes() == source.read_bytes()
    assert (out / override.name).read_bytes() == override.read_bytes()
    assert len(report['initialize.py']['sha256']) == 64
    assert source.read_bytes() == b'# original\r\nBaseConfig = {}\r\n'


def test_series_saves_every_curve_and_recalibrates_by_elapsed_time(tmp_path):
    m = module()
    clock = [0.0]
    calibration_ids = []

    def calibrate(index):
        calibration_ids.append(index)
        return {'id': index}

    def measure(index, calibration):
        clock[0] += 1000
        return {'index': index, 'calibration_id': calibration['id'], 'T1_us': 300.0}

    result = m.collect_runs(tmp_path, hours=12, max_runs=3,
                            calibrate=calibrate, measure=measure,
                            clock=lambda: clock[0])
    assert result['status'] == 'complete'
    assert calibration_ids == [1, 2]
    assert [r['calibration_id'] for r in result['runs']] == [1, 1, 2]
    saved = json.loads((tmp_path / 'manifest.json').read_text())
    assert len(saved['runs']) == 3 and saved['status'] == 'complete'
    assert len((tmp_path / 't1_summary.csv').read_text().splitlines()) == 4


@pytest.mark.parametrize('error', [RuntimeError('hardware timeout'), KeyboardInterrupt()])
def test_failure_preserves_completed_curves_and_never_retries_measurement(tmp_path, error):
    m = module()
    attempted = []

    def measure(index, calibration):
        attempted.append(index)
        if index == 2:
            raise error
        return {'index': index, 'T1_us': 300.0}

    with pytest.raises(type(error)):
        m.collect_runs(tmp_path, hours=12, max_runs=5,
                       calibrate=lambda _: {}, measure=measure)
    assert attempted == [1, 2]
    saved = json.loads((tmp_path / 'manifest.json').read_text())
    assert len(saved['runs']) == 1
    assert saved['status'] in ('failed', 'interrupted')
    assert saved['current_run'] == 2


def test_hours_limit_finishes_current_curve_but_starts_no_extra_curve(tmp_path):
    m = module()
    clock = [0.0]

    def measure(index, _):
        clock[0] += 3601
        return {'index': index, 'T1_us': 300.0}

    result = m.collect_runs(tmp_path, hours=1, calibrate=lambda _: {},
                            measure=measure, clock=lambda: clock[0])
    assert len(result['runs']) == 1
    assert result['status'] == 'complete'


def test_deadline_during_calibration_starts_no_new_measurement(tmp_path):
    m = module()
    clock = [0.0]

    def calibrate(_):
        clock[0] = 3601
        return {}

    result = m.collect_runs(tmp_path, hours=1, calibrate=calibrate,
                            measure=lambda *_: pytest.fail('past deadline'),
                            clock=lambda: clock[0])
    assert result['runs'] == []


def test_identical_long_reset_envelope_reuses_preparation_address():
    m = module()
    # Each 8-us envelope fits, but the original second upload ends at 110080.
    data = np.zeros((55040, 2), dtype=np.int16)
    data[:, 0] = np.arange(55040) % 32767
    program = SimpleNamespace(cfg={'qubit_ch': 1}, pulses=[{}, {
        'qubit': {'addr': 0, 'data': data},
        'qubit_reset': {'addr': 55040, 'data': data.copy()}}],
        soccfg={'gens': [{'maxlen': 65536}, {'maxlen': 65536}]})
    with pytest.raises(ValueError, match='waveform memory'):
        m.validate_waveform_memory(program)
    m.reuse_reset_waveform(program)
    assert program.pulses[1]['qubit_reset']['addr'] == 0
    np.testing.assert_array_equal(program.pulses[1]['qubit_reset']['data'], data)
    report = m.validate_waveform_memory(program)
    assert report[1]['used_samples'] == 55040
    assert report[1]['capacity_samples'] == 65536


def test_distinct_reset_shape_is_never_silently_replaced():
    m = module()
    program = SimpleNamespace(cfg={'qubit_ch': 1}, pulses=[{}, {
        'qubit': {'addr': 0, 'data': np.zeros((16, 2), dtype=np.int16)},
        'qubit_reset': {'addr': 16, 'data': np.ones((16, 2), dtype=np.int16)}}])
    with pytest.raises(ValueError, match='identical'):
        m.reuse_reset_waveform(program)
    assert program.pulses[1]['qubit_reset']['addr'] == 16


def test_memory_guard_checks_address_plus_length_not_length_alone():
    m = module()
    program = SimpleNamespace(pulses=[{'offset': {
        'addr': 65530, 'data': np.zeros((16, 2), dtype=np.int16)}}],
        soccfg={'gens': [{'maxlen': 65536}]})
    with pytest.raises(ValueError, match='waveform memory'):
        m.validate_waveform_memory(program)


def test_acquisition_runs_preflighted_program_and_decodes_shot_major_iq(monkeypatch):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import integration
    m = module()
    program = SimpleNamespace(
        cfg={'opx_t1_delays_us': [1., 1500.], 'opx_t1_shots': 2},
        us2cycles=lambda *_a, **_k: 2)

    def transport(soc, actual_program, timeout, cfg, *, total_shots, progress):
        assert actual_program is program
        assert total_shots == 2
        return [SimpleNamespace(final_i=i, final_q=-i) for i in [2, 4, 6, 8]]

    monkeypatch.setattr(integration, '_run_program', transport)
    i, q, telemetry = m.acquire_curve_iq(
        None, program, {'read_length': 5., 'ro_chs': [0]}, None)
    np.testing.assert_array_equal(i, [[1., 3.], [2., 4.]])
    np.testing.assert_array_equal(q, [[-1., -3.], [-2., -4.]])
    assert telemetry['records'] == 4 and telemetry['read_length_cycles'] == 2
