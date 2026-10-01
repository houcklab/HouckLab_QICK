import importlib
from types import SimpleNamespace

import numpy as np
import pytest


def module():
    return importlib.import_module('WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSRepeatedLoadingFeedbackCheck')


def test_feedback_tasks_have_matched_sham_both_initial_states_and_reversed_repeat():
    m = module()
    ts = m.tasks()
    assert len(ts) == 12
    assert ts[0]['reference_state'] == 'g' and ts[-1]['reference_state'] == 'g'
    science = [t for t in ts if t['reference_state'] is None]
    for b in (0, 1):
        assert {(t['initial_state'], t['feedback']) for t in science if t['block'] == b} == {
            (s, f) for s in ('g', 'e') for f in (True, False)}
    assert [(t['initial_state'], t['feedback']) for t in science[:4]] == [
        (t['initial_state'], t['feedback']) for t in science[4:]][::-1]
    assert m.plan()['total_probe_shots'] == 6000
    assert m.plan()['automatic_loading'] is False


def test_half_gain_calibration_is_explicit_and_does_not_change_existing_default():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSRepeatedLoading as m
    assert m.calibration_config()['read_pulse_gain'] == 1880
    assert m.calibration_config(readout_gain=940)['read_pulse_gain'] == 940
    for gain in (0, -1, 1881, 940.5):
        with pytest.raises(ValueError):
            m.calibration_config(readout_gain=gain)


def test_feedback_decode_and_no_postselection_only_success():
    m = module()
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.classifier import ClassifierCalibration
    c = ClassifierCalibration(1, 'loop', 0., 0, 1, 0, -20, 0, 100, {})
    bundle = SimpleNamespace(payload=c, loop=c)
    w = np.full((100, 12), -100, dtype=np.int64); w[:, 1::2] = 0
    w[50:, -4] = 100  # failed final weak verification
    w[50:, -2] = 100  # terminal readout also hot
    w[:, 0] = 100  # first feedback correction should fire
    records = m.decode_records(w.astype(np.uint32), expected_records=100)
    assert records[0].to_words() == list(w[0])
    with pytest.raises(ValueError):
        m.decode_records(w.ravel()[:-1])
    axis = dict(theta_rad=0., threshold=0., low=-100., high=100.)
    r = m.summarize_records(w, axis, bundle, feedback=True)
    assert r['final_excited_all'] == .5
    assert r['final_excited_given_ground'] == 0.
    assert r['ground_verification_fraction'] == .5
    assert r['mean_feedback_pi_count'] == 1.
    assert m.summarize_records(w, axis, bundle, feedback=False)['mean_feedback_pi_count'] == 0.
    w[0, 0] = 32768
    assert m.summarize_records(w, axis, bundle, feedback=True)['feedback_iq_out_of_range'] == 1
