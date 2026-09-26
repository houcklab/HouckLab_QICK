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


def test_stability_plan_repeats_only_original_settings_over_several_minutes():
    result = subprocess.run([sys.executable, '-m', MODULE, '--plan', '--stability-check'],
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    p = json.loads(result.stdout)
    assert p['hardware_access'] is False
    assert p['stability_check'] is True
    assert p['total_reference_shots'] == 96000
    assert len(p['points']) == 12
    assert {e['profile'] for e in p['points']} == {'legacy'}
    assert [e['not_before_offset_s'] for e in p['points']] == list(range(0, 360, 30))
    assert len({e['name'] for e in p['points']}) == 12


def test_reference_schedule_waits_to_deadline_and_does_not_wait_if_late():
    m = runner()
    now = [105.]
    waits = []
    def sleep(seconds):
        waits.append(seconds)
        now[0] += seconds
    m.wait_for_reference_slot(100., 30., clock=lambda: now[0], sleep=sleep)
    assert now[0] == 130.
    assert sum(waits) == 25.
    waits.clear()
    m.wait_for_reference_slot(100., 20., clock=lambda: now[0], sleep=sleep)
    assert waits == []


def test_timing_stability_plan_balances_order_within_each_time_slot():
    from collections import Counter
    from itertools import permutations
    result = subprocess.run([sys.executable, '-m', MODULE, '--plan', '--stability-check',
                             '--compare-timing'], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    p = json.loads(result.stdout)
    assert p['hardware_access'] is False and p['compare_timing'] is True
    assert p['total_reference_shots'] == 288000
    points = p['points']
    assert len(points) == len({e['name'] for e in points}) == 36
    orders = []
    for group in range(12):
        entries = points[group * 3:(group + 1) * 3]
        assert {e['comparison_round'] for e in entries} == {group}
        assert {e['not_before_offset_s'] for e in entries} == {group * 30.}
        orders.append(tuple(e['profile'] for e in entries))
    assert Counter(orders) == Counter({order: 2 for order in permutations(runner().PROFILES)})


def test_compare_timing_requires_stability_mode_before_any_hardware_access():
    for mode in ['--plan', '--run']:
        result = subprocess.run([sys.executable, '-m', MODULE, mode, '--compare-timing'],
                                text=True, capture_output=True)
        assert result.returncode == 2
        assert '--compare-timing requires --stability-check' in result.stderr
