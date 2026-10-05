import importlib
import numpy as np
import pytest

NAME='WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSFastLossReadoutCheck'


def test_power_check_matches_production_calibration_except_readout_gain():
    m=importlib.import_module(NAME)
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.Q3QuasiparticlePumping import base_config
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import build_calibration_config
    original=base_config()
    original.update(dt_pulseplay=.5,dt_pulsedef=.002)
    standard=build_calibration_config(original,original['qubit_pi_freq'])
    assert m.reference_config(1880)==standard
    half=m.reference_config(940)
    assert half['read_pulse_gain']==940
    assert {k:v for k,v in half.items() if k!='read_pulse_gain'}=={k:v for k,v in standard.items() if k!='read_pulse_gain'}
    assert original['read_pulse_gain']==1880
    for invalid in [0,939,941,1881,940.5,True]:
        with pytest.raises(ValueError):m.reference_config(invalid)


def test_task_order_reverses_power_and_never_installs_a_calibration():
    m=importlib.import_module(NAME)
    assert [t['readout_gain'] for t in m.tasks()]==[1880,940,940,1880]
    assert len({t['name'] for t in m.tasks()})==4
    assert m.plan()['shots_per_state_per_context']==2000
    assert m.plan()['automatic_calibration_install'] is False


def test_report_rejects_overlap_without_lowering_production_criteria():
    m=importlib.import_module(NAME)
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.calibration import CalibrationBundle
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.classifier import fit_classifier
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import ReferenceAxis
    rng=np.random.default_rng(548)
    g=rng.normal(0,1000,2000).astype(int);e=rng.normal(6000,1000,2000).astype(int);zero=np.zeros(2000,int)
    good=fit_classifier(g,zero,e,zero,context='payload',ground_confidence_fidelity=.7)
    bad=fit_classifier(g,zero,g+100,zero,context='loop',ground_confidence_fidelity=.7)
    bundle=CalibrationBundle(1,good,bad,ReferenceAxis.from_centers(0,0,6000,0),{})
    before=bundle.to_dict()
    report=m.reference_report(bundle)
    assert not report['valid'] and 'loop.ground_accept' in report['rejection']
    assert bundle.to_dict()==before
    passing=CalibrationBundle(1,good,good,bundle.reference_axis,{})
    assert m.reference_report(passing)['valid']
