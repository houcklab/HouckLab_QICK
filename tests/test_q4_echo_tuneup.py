import importlib
import numpy as np
import pytest


def module():
    return importlib.import_module('WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.Q4EchoTuneup')


def test_tuneup_has_balanced_ramsey_axes_at_two_drive_frequencies():
    m = module()
    arms = m.ramsey_conditions(4367.76)
    assert len(arms) == 648
    for delay in {a['delay_us'] for a in arms}:
        group = [a for a in arms if a['delay_us'] == delay]
        assert len(group) == 8
        assert {round(a['frequency_mhz'] - 4367.76, 6) for a in group} == {-.025, .025}
        for frequency in {a['frequency_mhz'] for a in group}:
            assert {a['phase_deg'] for a in group if a['frequency_mhz'] == frequency} == {0, 90, 180, 270}


@pytest.mark.parametrize('sign', [-1, 1])
def test_signed_ramsey_fit_recovers_frequency_and_resolves_hardware_phase_convention(sign):
    m = module()
    t = np.linspace(.2, 40.2, 81)
    fits = []
    for drive in (4367.760, 4367.785):
        beat = sign * (4367.748 - drive)
        z = .63*np.exp(-t/85)*np.exp(1j*(2*np.pi*beat*t + .4)) + .01-.02j
        fit = m.fit_ramsey(t, z, np.full((2, 81), .04))
        assert fit['valid']
        assert fit['beat_mhz'] == pytest.approx(beat, abs=.0001)
        fits.append(fit)
    selected = m.resolve_frequency([4367.760, 4367.785], fits)
    assert selected['valid']
    assert selected['frequency_mhz'] == pytest.approx(4367.748, abs=.0001)


def test_flat_ramsey_and_inconsistent_frequency_shift_are_not_recommended():
    m = module(); t = np.linspace(.2, 40.2, 81)
    assert not m.fit_ramsey(t, np.zeros(81, complex), np.full((2, 81), .04))['valid']
    fits = [dict(valid=True, beat_mhz=x, beat_err_mhz=.0002) for x in (.02,.021)]
    assert not m.resolve_frequency([4367.760,4367.785], fits)['valid']


@pytest.mark.parametrize('count', [1, 3, 4])
def test_gain_fit_uses_rotation_period_and_retains_independent_train_checks(count):
    m = module(); gain = np.linspace(0,32000,33)
    y = .04 + .78*(1-np.cos(count*np.pi*gain/30600))/2
    fit = m.fit_gain(gain,y,np.full(len(gain),.025),count)
    assert fit['valid'] and fit['pi_gain'] == pytest.approx(30600, rel=.001)
    assert not m.fit_gain(gain,np.full(len(gain),.4),np.full(len(gain),.025),count)['valid']


def test_frequency_scout_rejects_edge_or_flat_response():
    m = module(); arms=m.spectroscopy_conditions()
    y=np.array([.05+.75*np.exp(-((a['frequency_mhz']-4367.79)/.055)**2)
                if a['gain'] else .05 for a in arms])
    assert m.select_frequency(arms,y)['frequency_mhz'] == pytest.approx(4367.79,abs=.011)
    with pytest.raises(ValueError): m.select_frequency(arms,np.full(len(arms),.1))
    y=np.array([.05+.7*(a['frequency_mhz']>4367.98) if a['gain'] else .05 for a in arms])
    with pytest.raises(ValueError): m.select_frequency(arms,y)


def test_pulse_plan_and_bounds():
    m=module()
    a=dict(kind='ramsey',frequency_mhz=4367.76,gain=16000,delay_us=4.,phase_deg=270)
    assert m.payload_pulses(a)==[(16000,0),(16000,270)]
    a.update(kind='drive',count=3,gain=31000)
    assert m.payload_pulses(a)==[(31000,0)]*3
    for changes in ({'gain':40000},{'frequency_mhz':4300},{'count':100}):
        with pytest.raises(ValueError): m.payload_pulses(dict(a,**changes))
