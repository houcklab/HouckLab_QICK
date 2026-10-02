import importlib
import json
import numpy as np
import pytest


def module():
    return importlib.import_module('WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.Q4RepeatedT2E')


def test_q4_echo_plan_and_phase_pair_budget():
    m = module()
    p = m.plan(hours=None)
    assert p['hours'] is None and p['max_delay_us'] == 1000
    assert p['delay_points'] == 71 and p['shots_per_phase'] == 500
    assert p['shots_per_delay'] == 1000 and p['records_per_curve'] == 71000
    assert p['analysis_phases_deg'] == [0, 180]
    blocks = m.delay_chunks(m.delays_us())
    assert [len(x) for x in blocks] == [16, 16, 16, 16, 7]
    np.testing.assert_equal(np.concatenate(blocks), m.delays_us())
    cfg = m.measurement_config({'test': 'calibration'})
    assert cfg['qubit_pi_freq'] == 4367.760 and cfg['qubit_pi2_gain'] == 16000
    assert cfg['qubit_pi_gain'] == 32000 and cfg['sigma'] == 2.
    assert not cfg['do_ff'] and cfg['ff_park_gain'] == 0


def test_tuned_payload_preserves_reset_settings_and_records_split_refocusing():
    m=module()
    cfg=m.measurement_config({'test':'calibration'},tuned_pulses=True)
    assert cfg['qubit_pi_freq']==pytest.approx(4367.786623)
    assert cfg['qubit_pi2_gain']==20104
    assert cfg['q4_echo_refocus_count']==2 and cfg['q4_echo_refocus_gap_us']==.1
    assert cfg['reset_pi_freq']==4367.760 and cfg['reset_pi_gain']==32000
    assert cfg['sigma']==2 and cfg['qubit_pi_gain']==32000
    p=m.plan(tuned_pulses=True,max_runs=1)
    assert p['refocus_gain']==20104 and p['refocus_pulse_count']==2
    assert p['pi_gain'] is None and 'source_session' in p['pulse_tuneup']


def test_split_refocusing_keeps_equal_outer_gaps_and_centered_net_pi():
    m=module()
    # 8-tick envelopes, each free gap 3 ticks, inner half-pulse gap 1 tick.
    starts=m.echo_pulse_starts(8,3,2,1)
    assert starts==[0,11,20,31]
    centers=np.array(starts)+4
    assert (centers[1]+centers[2])/2 == (centers[0]+centers[-1])/2
    assert starts[1]-(starts[0]+8)==starts[-1]-(starts[-2]+8)==3
    assert m.echo_pulse_starts(8,3,1,1)==[0,11,22]
    with pytest.raises(ValueError):m.echo_pulse_starts(8,3,3,1)


def test_contrast_is_signed_phase_difference_with_paired_standard_error():
    m = module()
    y = np.array([[[1,1,1,0], [0,0,1,0]], [[1,0,1,0], [0,1,0,1]]])
    c, se = m.contrast_statistics(y)
    np.testing.assert_allclose(c, [.5, 0.])
    np.testing.assert_allclose(se, np.std(y[:,0]-y[:,1], axis=1, ddof=1)/2)
    with pytest.raises(ValueError):
        m.contrast_statistics(y[:, :1])


def test_echo_fit_recovers_exponential_and_marks_absent_signal():
    m = module()
    t = m.delays_us()
    y = .01 + .72*np.exp(-t/250.)
    fit = m.fit_echo(t, y, np.full(71,.025))
    assert fit['fit_valid'] and fit['signal_valid']
    assert fit['T2E_us'] == pytest.approx(250., rel=.01)
    assert not m.fit_echo(t, np.zeros(71), np.full(71,.025))['signal_valid']


def test_echo_fit_rejects_model_mismatch_without_discarding_signal_or_raw_fit():
    m = module()
    t = m.delays_us()
    y = .02 + .65*np.exp(-t/220) + .20*np.sin(3*np.log(t))
    fit = m.fit_echo(t, y, np.full(71, .025))
    assert fit['signal_valid'] and fit['reduced_chi2'] > 5
    assert not fit['fit_valid'] and fit['T2E_us'] is None
    assert np.isfinite(fit['tau_fit_us'])


def test_forever_saves_completed_echo_curves_and_refreshes_calibration(tmp_path):
    m = module(); now=[0.]; ids=[]
    def cal(i): ids.append(i); return {'id':i}
    def measure(i,c):
        if i == 3: raise KeyboardInterrupt()
        now[0] += 13*3600
        return dict(index=i,T2E_us=250.,fit_valid=True,signal_valid=True)
    with pytest.raises(KeyboardInterrupt):
        m.collect_runs(tmp_path,hours=None,calibrate=cal,measure=measure,clock=lambda:now[0])
    saved=json.loads((tmp_path/'manifest.json').read_text())
    assert saved['status']=='interrupted' and len(saved['runs'])==2
    assert ids==[1,2,3]
    assert len((tmp_path/'t2e_summary.csv').read_text().splitlines())==3


def test_single_curve_limit_and_invalid_initial_echo_are_saved(tmp_path):
    m=module()
    def measure(i,c): return dict(index=i,T2E_us=None,fit_valid=False,signal_valid=False)
    with pytest.raises(RuntimeError,match='echo contrast'):
        m.collect_runs(tmp_path/'bad',hours=None,calibrate=lambda _: {},measure=measure)
    bad=json.loads((tmp_path/'bad/manifest.json').read_text())
    assert len(bad['runs'])==1 and bad['status']=='failed'
    result=m.collect_runs(tmp_path/'one',hours=None,max_runs=1,calibrate=lambda _: {},
                          measure=lambda i,c:dict(index=i,T2E_us=250,fit_valid=True,signal_valid=True))
    assert len(result['runs'])==1 and result['status']=='complete'


@pytest.mark.parametrize('maximum',[0,1,float('nan'),float('inf'),-10])
def test_bad_delay_rejected(maximum):
    with pytest.raises(ValueError): module().delays_us(maximum)
