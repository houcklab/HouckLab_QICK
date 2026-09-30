"""Timing, polarity cancellation and refusal to infer transfer from bad circles."""
import importlib
import numpy as np
import pytest


@pytest.fixture
def response():
    name='WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSNoiseFluxResponse'
    assert importlib.util.find_spec(name), 'flux-response runner is not implemented'
    return importlib.import_module(name)


def test_noise_is_confined_between_microwave_pulses(response):
    t=response.timing(430.08)
    assert t['pi2_cycles']==19 and t['pi_cycles']==39
    for placement in response.PLACEMENTS:
        for pattern in ('static','fast'):
            a=response.offset_waveform(t,pattern,375,1,placement,seed=2)
            b=response.offset_waveform(t,pattern,375,-1,placement,seed=2)
            assert np.array_equal(a,-b)
            assert np.count_nonzero(a)==128
            for start,length in zip(t['pulse_starts'],t['pulse_lengths']):
                assert not np.any(a[max(0,start-32):start+length+32])
            if pattern=='fast':assert a.sum()==0
    # Combined polarities have exactly matched FULL code distributions.
    for placement in response.PLACEMENTS:
        values={p:np.concatenate([response.offset_waveform(t,p,250,s,placement,seed=0)
                                 for s in (-1,1)]) for p in ('static','fast')}
        np.testing.assert_array_equal(np.sort(values['static']),np.sort(values['fast']))


def test_off_arm_and_unsafe_requests(response):
    t=response.timing(430.08)
    assert not np.any(response.offset_waveform(t,'off',0,0,'early',seed=0))
    for kwargs in (dict(amplitude=400),dict(polarity=0),dict(placement='invalid')):
        with pytest.raises(ValueError):
            response.offset_waveform(t,**(dict(pattern='fast',amplitude=250,polarity=1,
                                              placement='early',seed=1)|kwargs))


def test_echo_centers_and_clock_requirements(response):
    t=response.timing(430.08)
    centers=np.array(t['pulse_starts'])+np.array(t['pulse_lengths'])/2
    assert centers[1]==pytest.approx((centers[0]+centers[2])/2)
    assert t['lead_cycles']>=208
    assert t['window_cycles']/430.08+response.PRE_US+.5+response.POST_US<32
    with pytest.raises(ValueError):response.timing(float('nan'))


def test_schedule_has_bracketed_phase_references_and_paired_polarities(response):
    ts=response.tasks()
    assert len({t['name'] for t in ts})==len(ts)
    for b in range(response.BLOCKS):
        group=[t for t in ts if t['block']==b]
        assert group[0]['kind']=='off' and group[-1]['kind']=='off'
        assert len([t for t in group if t['kind'] in ('static','fast')])==12
    for task in ts:
        names=[c['name'] for c in task['conditions']]
        assert len(set(names))==len(names) and 'g' in names and 'e' in names
        if task['kind'] in ('static','fast'):
            assert {(c['polarity'],c['phase']) for c in task['conditions'] if c['name'] not in ('g','e')}=={
                (p,a) for p in (-1,1) for a in response.PHASES}


def circle(phi,visibility=.65):
    return {str(p):dict(mean=.4+.3*visibility*np.cos(np.deg2rad(p)-phi),sem=.004)
            for p in (0,90,180,270)}


def test_even_phase_cancels_wrapped_linear_term_and_has_uncertainty(response):
    off=response.phase_circle(circle(.7),contrast=.6)
    plus=response.phase_circle(circle(.7+7.8-.4),contrast=.6)
    minus=response.phase_circle(circle(.7-7.8-.4),contrast=.6)
    r=response.even_phase(plus,minus,off)
    assert r['valid'] and r['phase_rad']==pytest.approx(-.4)
    assert r['error_rad']>0
    assert r['branch']=='principal modulo pi; no automatic unwrapping'


def test_invalid_circle_not_silently_used_as_gain(response):
    bad=response.phase_circle(circle(.2,visibility=.01),contrast=.6)
    good=response.phase_circle(circle(.4),contrast=.6)
    assert not bad['valid']
    assert not response.even_phase(good,bad,good)['valid']
    with pytest.raises(ValueError):response.phase_circle({'0':dict(mean=0,sem=.1)},contrast=.6)


def test_stream_decoding_keeps_phase_and_polarity_labels(response):
    task=next(t for t in response.tasks() if t['kind']=='fast')
    n=len(task['conditions']);raw=np.zeros((task['shots']*n,2))
    raw[:,0]=np.tile(np.arange(n),task['shots'])
    class Axis:
        def project(self,i,q):return i
    class Bundle:payload=Axis()
    rows=response.decode(raw,task,Bundle())
    assert [r['mean'] for r in rows]==list(range(n))
    assert [r['name'] for r in rows]==[c['name'] for c in task['conditions']]
    with pytest.raises(ValueError):response.decode(raw[:-1],task,Bundle())


def synthetic_entries(response):
    result=[]
    for i,task in enumerate(response.tasks()):
        rows=[]
        for c in task['conditions']:
            mean={'g':0.,'e':1.,'half':.5,'two_pi':0.}.get(c['state'])
            if c['state']=='phase':
                phi=.2+.01*task['block']
                if task['kind'] in ('static','fast'):
                    # Linear phase differs radically between seeds: cancellation
                    # must happen inside each block, never before phase extraction.
                    phi+=c['polarity']*(.9+2*task['seed'])-.3*(task['amplitude']/250)**2
                mean=.5+.35*np.cos(np.deg2rad(c['phase'])-phi)
            rows.append(dict(**c,mean=mean,sem=.002,shots=600))
        result.append(dict(task=task,rows=rows,midpoint_s=i+1.))
    return result


def test_pairing_precedes_seed_averaging_and_does_not_censor_bad_seeds(response):
    entries=synthetic_entries(response)
    summary=response.analyze(entries)
    assert summary['pulse_controls_valid']
    for g in summary['groups']:
        assert g['valid']
        assert g['phase_rad']==pytest.approx(-.3*(g['amplitude']/250)**2)
    damaged=next(e for e in entries if e['task']['kind']=='fast' and e['task']['amplitude']==250)
    for row in damaged['rows']:
        if row['state']=='phase':row['mean']=.5
    group=next(g for g in response.analyze(entries)['groups'] if (g['kind'],g['amplitude'],g['placement'])==('fast',250,damaged['task']['placement']))
    assert group['blocks']==4 and not group['valid']


def test_post_control_failure_gates_claim_but_preserves_phase_data(response):
    entries=synthetic_entries(response)
    next(row for row in entries[-1]['rows'] if row['name']=='two_pi')['mean']=.8
    summary=response.analyze(entries)
    assert not summary['pulse_controls_valid']
    assert all(not g['valid'] and g['phase_data_valid'] for g in summary['groups'])
    assert all('phase_rad' in g for g in summary['groups'])


def test_off_drift_and_modulo_branch_are_flagged(response):
    entries=synthetic_entries(response)
    refs=[e for e in entries if e['task']['block']==0 and e['task']['kind']=='off']
    for row in refs[-1]['rows']:
        if row['state']=='phase':row['mean']=.5+.35*np.cos(np.deg2rad(row['phase'])-.9)
    summary=response.analyze(entries)
    assert not summary['complete_blocks'][0]['off_valid']
    assert not any(g['valid'] for g in summary['groups'])
    off=dict(phase_rad=0,error_rad=.01,valid=True)
    near=dict(phase_rad=np.pi/2-.01,error_rad=.01,valid=True)
    assert not response.even_phase(near,near,off)['valid']
