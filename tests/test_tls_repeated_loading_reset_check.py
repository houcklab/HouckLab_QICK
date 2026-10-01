"""Bounded diagnosis of the repeated-readout reference failure."""
import importlib

import numpy as np
import pytest


def module():
    return importlib.import_module(
        'WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSRepeatedLoadingResetCheck')


def test_check_reverses_profiles_and_state_order_without_changing_final_readout():
    m = module()
    tasks = m.tasks()
    assert len(tasks) == 16
    assert [t['profile'] for t in tasks[:8]] == [t['profile'] for t in tasks[8:]][::-1]
    assert all(t['states'] == ['ground', 'excited'] for t in tasks[:8])
    assert all(t['states'] == ['excited', 'ground'] for t in tasks[8:])
    for task in tasks:
        cfg = m.profile_config(task)
        assert cfg['read_pulse_gain'] == 1880
        assert cfg['ff_park_gain'] == -25146 and cfg['qubit_pi_gain'] == 13500
        assert cfg['opx_inter_shot_delay_us'] == 1000.
        assert not cfg['do_ff']
    assert m.plan()['total_reference_shots'] == 16000
    assert not m.plan()['automatic_calibration_install']


def test_existing_reference_defaults_and_invalid_diagnostic_values():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSRepeatedLoading as m
    cfg = dict(m.calibration_config(), opx_reference_context='loop')
    assert m.reference_settings(cfg) == (4, 20., 1880)
    assert m.reference_settings(dict(cfg, opx_reference_context='payload')) == (0, 20., 1880)
    assert m.reference_settings(dict(cfg, loading_reference_rounds=0)) == (0, 20., 1880)
    for key, value in [('loading_reference_rounds', 1.5), ('loading_reference_rounds', 5),
                       ('loading_reference_guard_us', 0.), ('loading_reference_guard_us', np.nan),
                       ('loading_reference_prior_gain', -1), ('loading_reference_prior_gain', 1881)]:
        with pytest.raises(ValueError):
            m.reference_settings(dict(cfg, **{key: value}))


def test_rejected_references_are_reported_without_using_or_relaxing_classifier():
    m = module()
    rng = np.random.default_rng(831)
    raw = dict(ground_i=rng.normal(0, 1000, 1000).astype(int), ground_q=np.zeros(1000, int),
               excited_i=rng.normal(250, 1000, 1000).astype(int), excited_q=np.zeros(1000, int))
    report = m.reference_report(raw)
    assert not report['passes_loop_guard']
    assert report['classifier']['holdout']['peak_fidelity'] < .7
    raw['excited_i'] += 7000
    assert m.reference_report(raw)['passes_loop_guard']
    raw['ground_i'][:] = raw['excited_i'][:] = 0
    failed = m.reference_report(raw)
    assert not failed['passes_loop_guard'] and failed['fit_error']
