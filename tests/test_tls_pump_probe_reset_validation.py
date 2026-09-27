import importlib
import json
import subprocess
import sys
import pytest

MODULE = 'WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResetValidation'


def test_validation_plan_is_hardware_free_and_balances_conditions():
    from collections import Counter
    p = subprocess.run([sys.executable, '-m', MODULE, '--plan'], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    plan = json.loads(p.stdout)
    assert plan['hardware_access'] is False
    assert plan['benchmark_shots'] == 19200
    assert plan['reference_shots'] == 16000
    assert len(plan['points']) == 48
    positions = [Counter() for _ in range(4)]
    for repeat in range(12):
        entries = plan['points'][repeat * 4:(repeat + 1) * 4]
        assert {e['not_before_offset_s'] for e in entries} == {30 * repeat}
        assert {(e['reset_scheme'], e['preparation']) for e in entries} == {
            ('opx_unbounded', 'g'), ('opx_unbounded', 'e'), ('none', 'g'), ('none', 'e')}
        for i, e in enumerate(entries):
            positions[i][e['reset_scheme'], e['preparation']] += 1
    assert all(set(c.values()) == {3} for c in positions)


def test_runtime_preserves_calibration_and_candidate_timing_after_session_overrides():
    m = importlib.import_module(MODULE)
    base = {'ff_park_gain': -25146, 'qubit_pi_gain': 13500, 'read_length': 3.5}
    calibration = {'marker': 'fresh'}
    cfg = m.runtime_config(base, calibration, 4367.292)
    assert cfg['opx_reset_calibration'] == calibration
    assert cfg['opx_loop_recovery_us'] == 20
    assert cfg['opx_read_delay_us'] == 10
    assert cfg['opx_feedback_read_timing'] == 'official_wait_all'
    assert cfg['opx_feedback_pre_measure_sync'] is True
    assert cfg['opx_persistent_park'] is True and cfg['opx_hard_flux_steps'] is True
    assert cfg['opx_inter_shot_delay_us'] == 500
    assert cfg['opx_verification_delay_us'] == 20
    assert cfg['qubit_pi_gain'] == 13500
    assert cfg['qubit_pi_freq'] == cfg['reset_pi_freq'] == 4367.292
    assert 'opx_reset_calibration' not in base


def test_incomplete_records_are_saved_before_rejection(tmp_path):
    from types import SimpleNamespace
    import numpy as np
    import pytest
    m = importlib.import_module(MODULE)
    record = SimpleNamespace(preparation=0, initial_z=1, reset_attempts=2, pi_pulses=1,
                             terminal_status=0, final_i=3, final_q=4, last_z=5)
    path = tmp_path / 'partial.npz'
    with pytest.raises(RuntimeError, match='Incomplete benchmark block'):
        m.save_and_summarize(path, [record], None)
    with np.load(path) as raw:
        assert raw['final_i'].tolist() == [3]
        assert raw['reset_attempts'].tolist() == [2]


@pytest.mark.parametrize("outcome", ["complete", "complete_delay", "complete_memory", "rejected_initial", "timeout"])
def test_full_mocked_run_keeps_one_classifier_and_saves_final_references(tmp_path, monkeypatch, outcome):
    from contextlib import nullcontext
    from types import SimpleNamespace
    import numpy as np
    m = importlib.import_module(MODULE)
    package = importlib.import_module('WorkingProjects.TLS_Spectroscopy.Client_modules.Runners')
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import calibration, integration, programs
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import ReferenceAxis
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.classifier import fit_classifier
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.records import TerminalStatus
    gi = np.tile(np.arange(-100, -80), 100); ei = gi + 200; q = np.zeros(2000, dtype=int)
    fits = [fit_classifier(gi,q,ei,q,context=c,ground_confidence_fidelity=.7) for c in ['payload','loop']]
    bundle = calibration.CalibrationBundle(1, *fits, ReferenceAxis.from_centers(-90,0,110,0), {})
    if outcome == 'rejected_initial':
        from dataclasses import replace
        bundle = replace(bundle, loop=replace(bundle.loop, holdout={**bundle.loop.holdout, 'ground_accept': 0.}))
    raw = {c: {'ground': {'i': gi, 'q': q}, 'excited': {'i': ei, 'q': q}} for c in ['payload','loop']}
    base = dict(ff_park_gain=-25146, qubit_pi_freq=4367.292, qubit_pi_gain=13500, read_length=3.5, ro_chs=[0], read_pulse_gain=1880)
    fake_tls = SimpleNamespace(BaseConfig=base, makeProxy=lambda: (object(), object()))
    fake_five = SimpleNamespace(install_scan_calibration=lambda tls: None)
    monkeypatch.setattr(package, 'TLSSpectroscopy', fake_tls, raising=False)
    monkeypatch.setattr(package, 'FivePointApplesToApples', fake_five, raising=False)
    monkeypatch.setattr(m.localizer, 'checked_correction', lambda *args: tmp_path / 'correction.json')
    monkeypatch.setattr(m.localizer, 'scan_environment', lambda *args: nullcontext())
    monkeypatch.setenv('Q3_CODE_COMMIT', 'mock-test')
    monkeypatch.setattr(m.reference, 'wait_for_reference_slot', lambda *args: None)
    references = []
    def acquire_reference(soc, soccfg, cfg, **kwargs):
        references.append(dict(cfg))
        return bundle, raw
    monkeypatch.setattr(calibration, 'acquire_calibration', acquire_reference)
    configs = []
    class Program:
        def __init__(self, soccfg, cfg, payload, loop):
            assert payload is bundle.payload and loop is bundle.loop
            self.cfg = cfg
            configs.append(cfg)
        def us2cycles(self, *args, **kwargs):
            return 1075
    monkeypatch.setattr(programs, 'OPXResetBenchmarkProgram', Program)
    monkeypatch.setattr(programs, 'OPXReadoutMemoryBenchmarkProgram', Program)
    def acquire(soc, program, timeout, cfg, *, total_shots):
        assert total_shots == 400
        active = cfg['opx_reset_scheme'] == 'opx_unbounded'
        status = TerminalStatus.CONFIRMED_GROUND if active else TerminalStatus.NO_RESET
        records = [SimpleNamespace(preparation=int(cfg['prep_excited']), initial_z=100,
                reset_attempts=2 if active else 0, pi_pulses=1 if active else 0,
                terminal_status=status, final_i=-90, final_q=0, last_z=-100) for _ in range(total_shots)]
        if outcome == 'timeout':
            from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.acquisition import AcquisitionTimeout
            raise AcquisitionTimeout('simulated watchdog', completed_shots=3, partial_records=records[:3])
        return records
    monkeypatch.setattr(integration, '_run_program', acquire)
    if outcome not in ('complete', 'complete_delay', 'complete_memory'):
        with pytest.raises((ValueError, RuntimeError), match='confident|simulated watchdog'):
            m.run(data_root=tmp_path)
        path = next((tmp_path/'q3').glob('*/manifest.json'))
        manifest = json.loads(path.read_text())
        assert manifest['status'] == 'failed'
        assert len(references) == 1
        assert (path.parent/'initial_reference'/'calibration_raw.npz').is_file()
        assert not (path.parent/'final_reference').exists()
        if outcome == 'rejected_initial':
            assert configs == []
            assert manifest['initial_reference']['accepted'] is False
            assert all(e['status'] == 'pending' for e in manifest['points'])
        else:
            entry = manifest['points'][0]
            assert entry['status'] == 'failed'
            assert entry['partial_acquisition']['completed_shots'] == 3
            with np.load(entry['partial_acquisition']['raw_npz']) as data:
                assert data['final_i'].shape == (3,)
                assert data['reset_attempts'].tolist() == [2, 2, 2]
            assert 'AcquisitionTimeout: simulated watchdog' in manifest['error']
        return
    delay_check = outcome == 'complete_delay'
    memory_check = outcome == 'complete_memory'
    path = m.run(data_root=tmp_path, delay_check=delay_check, readout_memory_check=memory_check)
    expected_blocks = 144 if delay_check or memory_check else 48
    manifest = json.loads(path.read_text())
    assert manifest['status'] == 'complete' and len(manifest['points']) == expected_blocks + 1
    assert len(configs) == expected_blocks and len(references) == 2
    assert references[0] == references[1]
    assert references[0]['opx_loop_recovery_us'] == 20
    assert all(c['opx_loop_recovery_us'] == 20 for c in configs)
    assert {c['opx_verification_delay_us'] for c in configs} == ({20.,100.,500.} if delay_check or memory_check else {20.})
    assert all(c['opx_verification_delay_us'] == e['verification_delay_us'] for c,e in zip(configs, manifest['points'][:-1]))
    assert all(c['opx_reset_calibration'] == bundle.to_dict() for c in configs)
    if memory_check:
        assert {c['opx_reset_scheme'] for c in configs} == {'none'}
        assert {c['opx_benchmark_initial_readout_gain'] for c in configs} == {0,1880}
        assert all(c['read_pulse_gain'] == 1880 for c in configs)
        for c,e in zip(configs, manifest['points'][:-1]):
            assert e['verification_readout_gain'] == 1880
            assert c['opx_benchmark_initial_readout_gain'] == e['initial_readout_gain'] == (0 if e['initial_readout']=='zero' else 1880)
    for entry in manifest['points'][:-1]:
        assert entry['status'] == 'complete' and 'acquisition_started_at' in entry
        with np.load(path.parent / (entry['name'] + '.npz')) as data:
            assert data['final_i'].shape == (400,)
            assert np.all(data['preparation'] == int(entry['preparation'] == 'e'))
    for stage in ['initial_reference', 'final_reference']:
        assert (path.parent/stage/'calibration.json').is_file()
        assert (path.parent/stage/'calibration_raw.npz').is_file()


def test_delay_plan_balances_all_conditions_without_changing_reset_settings():
    from collections import Counter
    p = subprocess.run([sys.executable, '-m', MODULE, '--plan', '--delay-check'],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    plan = json.loads(p.stdout)
    assert plan['hardware_access'] is False and plan['delay_check'] is True
    assert plan['benchmark_shots'] == 57600 and plan['reference_shots'] == 16000
    assert len(plan['points']) == 144
    expected = {(scheme, prep, delay) for scheme in ['opx_unbounded','none']
                for prep in ['g','e'] for delay in [20.,100.,500.]}
    positions = [Counter() for _ in range(12)]
    for repeat in range(12):
        es = plan['points'][12*repeat:12*(repeat+1)]
        assert {e['not_before_offset_s'] for e in es} == {30*repeat}
        conditions = [(e['reset_scheme'],e['preparation'],e['verification_delay_us']) for e in es]
        assert set(conditions) == expected
        for pos, condition in enumerate(conditions):positions[pos][condition] += 1
    assert all(set(c.values()) == {1} and set(c) == expected for c in positions)


def test_readout_memory_plan_pairs_normal_and_zero_initial_drive_without_feedback():
    p = subprocess.run([sys.executable, '-m', MODULE, '--plan', '--readout-memory-check'], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    plan = json.loads(p.stdout)
    assert plan['hardware_access'] is False and plan['readout_memory_check'] is True
    assert plan['benchmark_shots'] == 57600 and plan['reference_shots'] == 16000
    assert len(plan['points']) == 144
    for repeat in range(12):
        es = plan['points'][12*repeat:12*(repeat+1)]
        assert {e['reset_scheme'] for e in es} == {'none'}
        assert {(e['initial_readout'], e['preparation'], e['verification_delay_us']) for e in es} == {
            (drive, prep, delay) for drive in ['normal','zero'] for prep in ['g','e'] for delay in [20.,100.,500.]}


def test_readout_memory_program_changes_only_first_readout_gain(monkeypatch):
    from types import SimpleNamespace
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import programs
    cls = programs.OPXReadoutMemoryBenchmarkProgram
    traces = []
    def project(self, calibration, context):
        self.events.append(('measure_project',context))
    monkeypatch.setattr(programs.OPXResetBenchmarkProgram, '_measure_project', project)
    for gain in [0,1880]:
        p = SimpleNamespace(cfg={'res_ch':0,'ro_chs':[0],'read_pulse_gain':1880,
            'read_pulse_freq':6933.026,'read_length':3.5,'adc_trig_offset':.2,
            'opx_benchmark_initial_readout_gain':gain}, events=[],
            freq2reg=lambda *a,**k:123, deg2reg=lambda *a,**k:0,
            us2cycles=lambda x,**k:int(100*x))
        # The subclass method uses super(), so retain the actual class identity.
        obj = object.__new__(cls)
        obj.__dict__.update(p.__dict__)
        obj.set_pulse_registers = lambda **kw: obj.events.append(('registers',kw))
        cls._measure_project(obj, None, 'payload')
        assert [e[0] for e in obj.events] == ['registers','measure_project','registers']
        assert obj.events[0][1]['gain'] == gain
        assert obj.events[-1][1]['gain'] == 1880
        assert obj.cfg['read_pulse_gain'] == 1880
        traces.append(obj.events)
    traces[0][0][1]['gain'] = 1880
    assert traces[0] == traces[1]


def test_readout_memory_rejects_feedback_before_constructing_hardware_program():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import programs
    with pytest.raises(ValueError, match='requires no feedback'):
        programs.OPXReadoutMemoryBenchmarkProgram(None, {'opx_reset_scheme':'opx_unbounded'}, None, None)


@pytest.mark.parametrize('extra,match', [({'ro_mode_periodic':True}, 'pulsed readout'),
    ({'opx_benchmark_initial_readout_gain':17}, 'zero or the normal')])
def test_readout_memory_rejects_unsupported_gain_or_periodic_mode(extra, match):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import programs
    cfg = {'opx_reset_scheme':'none', 'read_pulse_gain':1880, 'opx_benchmark_initial_readout_gain':0, **extra}
    with pytest.raises(ValueError, match=match):
        programs.OPXReadoutMemoryBenchmarkProgram(None,cfg,None,None)
