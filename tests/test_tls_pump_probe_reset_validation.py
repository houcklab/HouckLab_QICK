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


@pytest.mark.parametrize("outcome", ["complete", "rejected_initial", "timeout"])
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
    base = dict(ff_park_gain=-25146, qubit_pi_freq=4367.292, qubit_pi_gain=13500, read_length=3.5, ro_chs=[0])
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
    if outcome != 'complete':
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
    path = m.run(data_root=tmp_path)
    manifest = json.loads(path.read_text())
    assert manifest['status'] == 'complete' and len(manifest['points']) == 49
    assert len(configs) == 48 and len(references) == 2
    assert references[0] == references[1]
    assert references[0]['opx_loop_recovery_us'] == 20
    assert all(c['opx_loop_recovery_us'] == 20 and c['opx_verification_delay_us'] == 20 for c in configs)
    assert all(c['opx_reset_calibration'] == bundle.to_dict() for c in configs)
    for entry in manifest['points'][:-1]:
        assert entry['status'] == 'complete' and 'acquisition_started_at' in entry
        with np.load(path.parent / (entry['name'] + '.npz')) as data:
            assert data['final_i'].shape == (400,)
            assert np.all(data['preparation'] == int(entry['preparation'] == 'e'))
    for stage in ['initial_reference', 'final_reference']:
        assert (path.parent/stage/'calibration.json').is_file()
        assert (path.parent/stage/'calibration_raw.npz').is_file()
