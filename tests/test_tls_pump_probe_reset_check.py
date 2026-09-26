import importlib
import json
import subprocess
import sys
from types import SimpleNamespace

MODULE = 'WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeResetCheck'


def runner():
    return importlib.import_module(MODULE)


def test_reset_check_plan_is_hardware_free_and_counterbalances_profiles():
    result = subprocess.run([sys.executable, '-m', MODULE, '--plan'], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan['hardware_access'] is False
    assert plan['shots_per_state_per_context'] == 2000
    assert [e['profile'] for e in plan['points']] == [
        'legacy', 'official', 'official_guard20', 'official_guard20', 'official', 'legacy']
    assert len({e['name'] for e in plan['points']}) == 6
    assert plan['total_reference_shots'] == 48000


def test_timing_profiles_preserve_drive_and_only_change_requested_timing():
    m = runner()
    baseline = {'read_pulse_freq': 6933.026, 'qubit_pi_freq': 4367.292,
                'qubit_pi_gain': 13500, 'opx_loop_recovery_us': 10.,
                'opx_feedback_syncdelay_us': 8., 'opx_inter_shot_delay_us': 400.,
                'opx_persistent_park': False, 'opx_hard_flux_steps': False}
    legacy = m.profile_config(baseline, 'legacy')
    assert legacy == baseline and legacy is not baseline
    official = m.profile_config(baseline, 'official')
    assert official == {**baseline, 'opx_feedback_read_timing': 'official_wait_all',
                        'opx_feedback_pre_measure_sync': True, 'opx_feedback_flush_mode': 'off',
                        'opx_read_delay_us': 10.}
    guard = m.profile_config(baseline, 'official_guard20')
    assert guard == {**official, 'opx_loop_recovery_us': 20.}
    assert baseline['opx_loop_recovery_us'] == 10.


def test_calibration_report_records_rejection_without_weakening_the_guard():
    m = runner()
    bundle = SimpleNamespace(
        payload=SimpleNamespace(holdout={'excited_fire': .6, 'peak_fidelity': .72}),
        loop=SimpleNamespace(holdout={'ground_accept': .001, 'excited_fire': .67, 'peak_fidelity': .6755}))
    result = m.calibration_report(bundle)
    assert result['accepted'] is False
    assert 'loop.ground_accept=0.0010' in result['rejection_reason']
    assert result['loop']['peak_fidelity'] == .6755
    bundle.loop.holdout['ground_accept'] = .5
    assert m.calibration_report(bundle)['accepted'] is True
