import importlib
import json

import numpy as np
import pytest


def module():
    return importlib.import_module(
        'WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.Q3QuasiparticlePumping')


def test_plan_uses_q3_and_is_finite_without_hardware(capsys):
    m = module()
    assert m.main(['--plan']) == 0
    p = json.loads(capsys.readouterr().out)
    assert p['qubit'] == 'q3'
    assert p['blocks'] == 4 and p['shots_per_block'] == 250
    assert p['total_probe_shots'] == 90000
    c = m.base_config()
    assert (c['ff_park_gain'], c['qubit_pi_freq'], c['read_pulse_freq']) == (
        -25146, 4367.292, 6933.026)
    assert (c['sigma'], c['qubit_pi_gain']) == (.2, 13500)
    assert c['do_ff'] is False
    c['FF_Qubits']['1']['channel'] = 99
    assert m.base_config()['FF_Qubits']['1']['channel'] == 3


def test_conditioning_equal_duration_and_equal_pulse_count_controls():
    m = module()
    schedules = {a: m.conditioning_schedule(a, pulse_ticks=80, period_ticks=3000,
                                            pair_gap_ticks=4, lead_ticks=100)
                 for a in m.ARMS}
    assert {s['duration_ticks'] for s in schedules.values()} == {60100}
    assert schedules['idle']['pulses'] == []
    for n in (4, 20):
        pump, paired = [schedules[f'{a}_{n}']['pulses'] for a in ('pump', 'paired')]
        assert len(pump) == len(paired) == n
        assert np.diff([p['start_tick'] for p in pump]).tolist() == [3000] * (n - 1)
        assert paired[-1]['start_tick'] == pump[-1]['start_tick']
        for first, second in zip(paired[::2], paired[1::2]):
            assert second['start_tick'] - first['start_tick'] == 84
            assert (first['phase_deg'], second['phase_deg']) == (0, 180)
        assert all(a['start_tick'] + 80 <= b['start_tick']
                   for a, b in zip(paired, paired[1:]))
    assert schedules['pump_4']['pulses'] == schedules['pump_20']['pulses'][-4:]
    with pytest.raises(ValueError):
        m.conditioning_schedule('paired_20', pulse_ticks=2000, period_ticks=3000,
                                pair_gap_ticks=4, lead_ticks=100)


def test_each_delay_interleaves_every_arm_and_both_probe_preparations():
    m = module()
    orders = [m.conditions(b) for b in range(4)]
    expected = {(a, s) for a in m.ARMS for s in ('g', 'e')}
    for order in orders:
        assert len(order) == 10
        assert {(x['arm'], x['state']) for x in order} == expected
    assert orders[0] != orders[1]
    assert orders[0][0]['state'] != orders[1][0]['state']
    tasks = m.tasks()
    assert len(tasks) == 36
    for b in range(4):
        assert {r['delay_us'] for r in tasks if r['block'] == b} == set(m.DELAYS_US)


def test_decoder_preserves_all_three_readouts_and_signed_iq():
    m = module()
    words = []
    for j in range(6):
        words += [j % 2, 1, j, j // 2, 0, -10 - j, 20 + j, -1]
    records = m.decode_records(np.asarray(words, dtype=np.int64).astype(np.uint32), 2)
    assert len(records) == 2
    assert records[0].before.final_i == -10
    assert records[0].conditioned.reset_attempts == 1
    assert records[1].probe.final_q == 25
    assert records[1].to_words() == words[24:]
    with pytest.raises(ValueError, match='24'):
        m.decode_records(words[:-8])
    with pytest.raises(ValueError, match='expected'):
        m.decode_records(words, 3)


def test_ground_excited_difference_rejects_population_offset_and_finds_decay_change():
    m = module()
    t = np.asarray(m.DELAYS_US)
    rows = []
    for block in range(4):
        for arm in m.ARMS:
            tau = 100 if arm == 'pump_20' else 50
            # A hotter initial population changes amplitude and the common baseline,
            # but is not a longer T1. paired_20 has exactly that confound.
            amp = .45 if arm == 'paired_20' else .75
            baseline = .2 if arm == 'paired_20' else .08
            for delay in t:
                for state in ('g', 'e'):
                    p = baseline + (amp * np.exp(-delay / tau) if state == 'e' else 0)
                    rows.append(dict(block=block, arm=arm, state=state,
                                     delay_us=delay, pe=p, shots=10000))
    result = m.analyze(rows)
    assert result['arms']['paired_20']['fit']['tau_us'] == pytest.approx(50, rel=.001)
    assert result['arms']['pump_20']['fit']['tau_us'] == pytest.approx(100, rel=.001)
    assert result['arms']['idle']['fit']['tau_us'] == pytest.approx(50, rel=.001)
    assert result['comparisons']['pump_20_minus_paired_20']['normalized_area_difference_us'] > 30
    assert result['comparisons']['paired_20_minus_idle']['normalized_area_difference_us'] == pytest.approx(0, abs=1e-6)
    assert result['interpretation'] == 'conditioning screen; not a quasiparticle identification'


def test_incomplete_and_flat_traces_do_not_produce_valid_t1():
    m = module()
    assert m.analyze([])['arms'] == {}
    rows = [dict(block=0, arm='idle', state=s, delay_us=t,
                 pe=.1 if s == 'g' else .11, shots=250)
            for t in m.DELAYS_US for s in ('g', 'e')]
    assert not m.analyze(rows)['arms']['idle']['fit']['valid']


@pytest.mark.parametrize('error', [RuntimeError('transport failed'), KeyboardInterrupt()])
def test_checkpointed_acquisition_does_not_retry_failed_hardware(tmp_path, error):
    m = module()
    attempted = []

    def acquire(task):
        attempted.append(task['index'])
        if task['index'] == 1:
            raise error
        return {'rows': [], 'raw_file': 'saved.npz'}

    with pytest.raises(type(error)):
        m.collect(tmp_path, acquire, run_tasks=m.tasks()[:3])
    assert attempted == [0, 1]
    manifest = json.loads((tmp_path / 'manifest.json').read_text())
    assert manifest['status'] in ('failed', 'interrupted')
    assert len(manifest['completed']) == 1
    assert manifest['current']['index'] == 1


def test_each_condition_resets_before_train_and_probe_then_reads_after_delay():
    p = importlib.import_module(
        'WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.Q3QuasiparticleProgram')
    events = []

    def record(stage, payload):
        payload()
        events.append(('readout_and_reset', stage))

    p.emit_cell(wait=lambda t: events.append(('wait', t)), record=record,
                condition=lambda: events.append('condition'),
                prepare_probe=lambda: events.append('prepare'),
                delay_us=15., washout_us=2000., ringdown_us=10.)
    assert events == [('wait', 2000.), ('readout_and_reset', 'before'),
                      ('wait', 10.), 'condition', ('readout_and_reset', 'conditioned'),
                      ('wait', 10.), 'prepare', ('wait', 15.),
                      ('readout_and_reset', 'probe'), ('wait', 10.)]


def test_fresh_calibration_and_measurement_use_verified_q3_feedback_timing():
    from types import SimpleNamespace
    m = module()
    configs = [m.calibration_config(), m.measurement_config(SimpleNamespace(to_dict=lambda: {}))]
    for cfg in configs:
        assert cfg['opx_feedback_read_timing'] == 'official_wait_all'
        assert cfg['opx_feedback_pre_measure_sync'] is True
        assert cfg['opx_feedback_flush_mode'] == 'off'
        assert cfg['opx_read_delay_us'] == 10.
        assert cfg['opx_persistent_park'] and cfg['opx_hard_flux_steps']


def test_keyboard_interrupt_aborts_hardware_before_partial_data_save(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import acquisition, integration
    m = module()
    events = []
    interrupt = KeyboardInterrupt()
    interrupt.partial_records = [SimpleNamespace(to_words=lambda: [0] * 24)]

    def fail(*args, **kwargs):
        raise interrupt

    monkeypatch.setattr(m, 'preflight', lambda _: {})
    monkeypatch.setattr(m, 'save_json', lambda *args: None)
    monkeypatch.setattr(integration, '_run_program', fail)
    monkeypatch.setattr(acquisition, '_safe_abort', lambda _: events.append('abort'))
    monkeypatch.setattr(m.np, 'savez_compressed', lambda *args, **kwargs: events.append('save'))
    with pytest.raises(KeyboardInterrupt):
        m.acquire_task(object(), object(), {'qp_shots': 250}, tmp_path, m.tasks()[0], None, None)
    assert events == ['abort', 'save']


def test_feedback_free_plan_names_passive_preparation_and_fixed_wait(capsys):
    m = module()
    assert m.main(['--plan', '--feedback-free']) == 0
    p = json.loads(capsys.readouterr().out)
    assert p['feedback_free'] is True
    assert p['post_conditioning_wait_us'] == 50.
    assert p['reset'] == '2000 us passive wait; no feedback in science shots'
    assert p['total_probe_shots'] == 90000


def test_feedback_free_cell_has_only_one_final_measurement():
    p = importlib.import_module(
        'WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.Q3QuasiparticleProgram')
    events = []
    p.emit_feedback_free_cell(
        wait=lambda t: events.append(('wait', t)),
        condition=lambda: events.append('condition'),
        prepare_probe=lambda: events.append('prepare'),
        measure=lambda: events.append('measure'), delay_us=15.,
        washout_us=2000., recovery_us=50., ringdown_us=10.)
    assert events == [('wait', 2000.), 'condition', ('wait', 50.),
                      'prepare', ('wait', 15.), 'measure', ('wait', 10.)]


def test_feedback_free_records_keep_shot_order_without_invented_reset_telemetry():
    from types import SimpleNamespace
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.records import PayloadRecord
    m = module()
    task = m.tasks()[0]
    # Two interleaved cycles, with excited preparation detected in only one.
    records = [PayloadRecord(2 if s == 0 and c['state'] == 'e' else -2, 0)
               for s in range(2) for c in task['conditions']]
    bundle = SimpleNamespace(payload=SimpleNamespace(
        project=lambda i, q: np.asarray(i), excited_threshold=0))
    rows = m.rows_from_records(records, task, bundle, feedback_free=True)
    for row, c in zip(rows, task['conditions']):
        assert row['arm'] == c['arm'] and row['state'] == c['state']
        assert row['shots'] == 2
        assert row['pe'] == (.5 if c['state'] == 'e' else 0.)
        assert row['feedback_free'] is True
        assert not any(k.endswith('_reset') for k in row)


def test_feedback_free_calibration_checks_payload_without_requiring_reset_thresholds():
    from types import SimpleNamespace
    m = module()
    payload = SimpleNamespace(holdout={'peak_fidelity': .80, 'excited_fire': .65, 'false_pi': .08})
    # No loop classifier: it is not used by feedback-free science.
    m.validate_reference(SimpleNamespace(payload=payload), feedback_free=True)
    payload.holdout['peak_fidelity'] = .55
    with pytest.raises(ValueError, match='readout reference'):
        m.validate_reference(SimpleNamespace(payload=payload), feedback_free=True)
