"""Catch unmatched noise exposures, invalid rate extraction and q4 leakage."""
import importlib
from types import SimpleNamespace
import numpy as np
import pytest


class NoiseModule:
    def __getattr__(self, key):
        name = 'WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSControlledNoise'
        assert importlib.util.find_spec(name), 'controlled-noise runner is not implemented'
        return getattr(importlib.import_module(name), key)


@pytest.fixture
def noise():
    return NoiseModule()


def test_noise_pair_has_equal_exposure_and_different_time_order(noise):
    for core in (512, 1536):
        a = noise.noise_signs(core, 'fast', seed=3)
        b = noise.noise_signs(core, 'slow', seed=3)
        assert len(a) == core + 32
        assert np.array_equal(np.sort(a), np.sort(b))
        assert np.sum(a) == np.sum(b) == 0
        assert np.all(a[:16] == 0) and np.all(a[-16:] == 0)
        assert np.count_nonzero(np.diff(a)) > np.count_nonzero(np.diff(b))
        assert np.array_equal(a, noise.noise_signs(core, 'fast', seed=3))
    assert not np.array_equal(a, noise.noise_signs(1536, 'fast', seed=7))


def test_waveforms_share_correction_and_never_clip(noise):
    args = dict(segments=[(1., 10.)], park_gain=-1000, target_gain=-500,
                endpoint_gains=(-540, -460), core_cycles=512, fabric_mhz=100.,
                samples_per_clock=4, max_gain=1000, seed=7)
    waves, report = noise.waveforms(**args)
    assert np.array_equal(np.sort(waves['fast']), np.sort(waves['slow']))
    assert set(np.unique(waves['fast'])) == {-540, -500, -460}
    assert sum(n for _, n in report['off_segments']) == 544
    assert report['duration_us'] == pytest.approx(5.44)
    with pytest.raises(ValueError, match='range'):
        noise.waveforms(**dict(args, endpoint_gains=(-1500, 500)))


def test_correction_is_common_and_exactly_covers_each_arm(noise):
    waves, report = noise.waveforms(
        segments=[(.9, .3), (1., 10.)], park_gain=-1000, target_gain=-500,
        endpoint_gains=(-540, -460), core_cycles=512, fabric_mhz=100.,
        samples_per_clock=4, max_gain=1000, seed=1)
    dc = np.repeat(np.concatenate([np.full(n, v) for v, n in report['off_segments']]), 4)
    for pattern in ('fast', 'slow'):
        assert len(waves[pattern]) == len(dc)
        assert set(np.unique(waves[pattern].astype(int) - dc)) <= {-40, 0, 40}


def test_q3_context_does_not_inherit_or_modify_q4_settings(noise):
    old = dict(ff_park_gain=0, qubit_pi_gain=32000, sigma=2.)
    tls = SimpleNamespace(BaseConfig=old, QUBIT='q4', SET_YOKO=True,
                          outerFolder='old', FLUX_FIT_PARAMS=[0])
    with noise.q3_context(tls, 'new'):
        assert tls.BaseConfig['ff_park_gain'] == -25146
        assert tls.BaseConfig['qubit_pi_gain'] == 13500
        assert tls.QUBIT == 'q3' and tls.SET_YOKO is False
    assert tls.BaseConfig is old and tls.QUBIT == 'q4'
    assert tls.FLUX_FIT_PARAMS == [0]


def test_selects_one_line_without_requiring_a_second_line(noise):
    rows = []
    for mhz in range(3800, 4301, 2):
        r = {'target_frequency_ghz': mhz/1000}
        rate = .01 + .12 / (1 + ((mhz-4100)/2)**2)
        for suffix in ('', '_scan_up', '_scan_down'):
            r['P0'+suffix] = .1
            r['P1'+suffix] = .9
            for t in (10, 25):
                r[f'Ps_{t}us'+suffix] = .1+.8*np.exp(-t*rate)
        rows.append(r)
    selected = noise.select_candidate(rows)
    assert abs(selected['center_ghz'] - 4.1) <= .002
    assert abs(selected['control_offset_mhz']) == 16
    flat = [dict(r, **{f'Ps_{t}us{s}': .8 for t in (10,25)
                      for s in ('','_scan_up','_scan_down')}) for r in rows]
    assert noise.select_candidate(flat) is None


def test_schedule_pairs_all_arms_and_samples_multiple_seeds(noise):
    tasks = noise.tasks(4.1, 16, fabric_mhz=430.08)
    assert len(tasks) == 128
    assert len({t['seed'] for t in tasks}) == 8
    for t in tasks:
        assert {(c['pattern'],c['state']) for c in t['conditions']} == {
            (p,s) for p in ('off','slow','fast') for s in ('g','e')}
    assert len({t['name'] for t in tasks}) == len(tasks)


def test_rate_comparison_cancels_starting_population(noise):
    rows=[]
    for b in range(8):
        for pattern,amp,rate in [('off',.8,.1),('slow',.4,.03),('fast',.6,.08)]:
            for t in (1.,3.):
                for state in ('g','e'):
                    p=.08+(amp*np.exp(-rate*t) if state=='e' else 0)
                    rows.append(dict(block=b, offset_mhz=0., frequency_ghz=4.1,
                                     pattern=pattern,state=state,hold_us=t,
                                     shots=10000,pe=p))
    s=noise.analyze(rows)
    point=s['sites'][0]
    assert point['rates']['fast']['rate_per_us'] == pytest.approx(.08)
    assert point['fast_minus_slow']['rate_difference_per_us'] == pytest.approx(.05)
    # Killing contrast must produce an unresolved result, not a spurious rate.
    for r in rows:
        if r['pattern']=='fast': r['pe']=.1
    assert noise.analyze(rows)['sites'][0]['rates']['fast']['valid'] is False


def test_incomplete_stream_is_not_classified_as_a_complete_program(noise):
    task=noise.tasks(4.1,16,fabric_mhz=430.08)[0]
    with pytest.raises(ValueError,match='incomplete'):
        noise.rows_from_words(np.zeros((2999,2)),task,None)


def test_preflight_rejects_memory_overrun_at_an_addressed_waveform(noise):
    p=SimpleNamespace(compile=lambda:[0]*20,
                      soccfg={'tprocs':[{'pmem_size':32}], 'gens':[{'maxlen':64}]},
                      pulses=[{'w':{'addr':60,'data':np.zeros((8,2))}}],record_words=2)
    with pytest.raises(ValueError,match='waveform'):
        noise.preflight(p)
    p.pulses[0]['w']['addr']=40
    assert noise.preflight(p)['waveform_memory'][0]['used_samples']==48
    p.compile=lambda:[0]*33
    with pytest.raises(ValueError,match='instruction'):
        noise.preflight(p)


def test_strong_decay_seeds_are_not_dropped_from_the_effect(noise):
    rows=[]
    for b in range(8):
        for pattern,rate in [('off',.2),('slow',.2),('fast',.1 if b<2 else 1.)]:
            for t in (1.26488095238,3.64583333333):
                for state in ('g','e'):
                    rows.append(dict(block=b,offset_mhz=0.,frequency_ghz=4.1,
                                     pattern=pattern,state=state,hold_us=t,shots=500,
                                     pe=.08+(.8*np.exp(-rate*t) if state=='e' else 0)))
    point=noise.analyze(rows)['sites'][0]
    effect=point['fast_minus_slow']
    assert effect['valid'] and effect['blocks']==8
    assert effect['rate_difference_per_us']>.1


def test_long_hold_keeps_noise_exposure_with_playable_constant_segments(noise):
    waves, report = noise.waveforms(
        segments=[(.9,.3),(1.,20.)],park_gain=-1000,target_gain=-500,
        endpoint_gains=(-540,-460),core_cycles=4352,fabric_mhz=430.08,
        samples_per_clock=16,max_gain=1000,seed=3,dc_tick_quantum=16)
    assert report['duration_us']==pytest.approx(4384/430.08)
    dc=np.concatenate([np.full(n,g) for g,n in report['off_segments']])
    for pattern in ('slow','fast'):
        segments=report['pattern_segments'][pattern]
        assert min(n for _,n in segments)>=16
        rebuilt=np.repeat(np.concatenate([np.full(n,g) for g,n in segments]),16)
        np.testing.assert_array_equal(rebuilt,waves[pattern])
    np.testing.assert_array_equal(np.sort(waves['fast'][::16]-dc),
                                  np.sort(waves['slow'][::16]-dc))


def test_long_hold_plan_and_tasks_agree(noise):
    plan=noise.plan(long_hold=True)
    tasks=noise.tasks(4.1,16,fabric_mhz=430.08,long_hold=True)
    assert len(tasks)==plan['science_programs']==128
    assert {t['core_cycles'] for t in tasks}=={512,4352}
    assert {t['playback'] for t in tasks}=={'const_segments'}
    assert max(t['hold_us'] for t in tasks)>10
    assert sum(t['shots']*len(t['conditions']) for t in tasks)==384000


def test_const_issue_budget_counts_set_fetch_and_rejects_unverified_opcodes(noise):
    assert noise.const_issue_cycles([{'name':'regwi'}]*5+[{'name':'set'}])==14
    with pytest.raises(ValueError,match='unverified'):
        noise.const_issue_cycles([{'name':'regwi'},{'name':'mathi'},{'name':'set'}])


def test_confirmation_uses_fresh_seeds_without_changing_exposure_or_order(noise):
    first=noise.tasks(4.042,-16,fabric_mhz=430.08,long_hold=True)
    confirm=noise.tasks(4.042,-16,fabric_mhz=430.08,long_hold=True,seed_offset=100)
    assert {t['seed'] for t in confirm}==set(range(100,108))
    assert [(t['offset_mhz'],t['core_cycles'],t['conditions']) for t in first]==[
        (t['offset_mhz'],t['core_cycles'],t['conditions']) for t in confirm]
    for pattern in ('fast','slow'):
        a=noise.noise_signs(4352,pattern,seed=0)
        b=noise.noise_signs(4352,pattern,seed=100)
        assert not np.array_equal(a,b)
        np.testing.assert_array_equal(np.sort(a),np.sort(b))
    with pytest.raises(ValueError,match='seed'):
        noise.tasks(4.042,-16,fabric_mhz=430.08,seed_offset=-1)


def test_anchor_keeps_confirmation_near_original_feature(noise):
    rows=[]
    for mhz in range(3800,4301,2):
        rate=.01+.12/(1+((mhz-4044)/2)**2)+.22/(1+((mhz-4160)/2)**2)
        r={'target_frequency_ghz':mhz/1000}
        for suffix in ('','_scan_up','_scan_down'):
            r['P0'+suffix]=.1;r['P1'+suffix]=.9
            for t in (10,25):r[f'Ps_{t}us'+suffix]=.1+.8*np.exp(-t*rate)
        rows.append(r)
    assert noise.select_candidate(rows)['center_ghz']==pytest.approx(4.160)
    assert noise.select_candidate(rows,anchor_ghz=4.044)['center_ghz']==pytest.approx(4.044)
    assert noise.select_candidate(rows,anchor_ghz=4.250) is None
    with pytest.raises(ValueError,match='anchor'):
        noise.plan(anchor_ghz=float('nan'))


def test_polarity_pair_matches_full_codes_during_changing_correction(noise):
    args=dict(segments=[(.9,.3),(.95,.4),(1.,20.)],park_gain=-1000,target_gain=-500,
              endpoint_gains=(-541,-459),core_cycles=4352,fabric_mhz=430.08,
              samples_per_clock=16,max_gain=1000,seed=203,dc_tick_quantum=16)
    # Deliberately asymmetric DAC offsets must be swapped, not negated.
    args['endpoint_gains']=(-541,-458)
    waves,report=noise.paired_waveforms(**args)
    fast=np.r_[waves['fast'],waves['fast_inverse']]
    slow=np.r_[waves['slow'],waves['slow_inverse']]
    np.testing.assert_array_equal(np.sort(fast),np.sort(slow))
    assert report['paired_full_code_histograms_equal']
    dc=np.repeat(np.concatenate([np.full(n,g) for g,n in report['off_segments']]),16)
    for p in ('fast','slow'):
        paired=waves[p].astype(int)+waves[p+'_inverse'].astype(int)-2*dc
        assert set(np.unique(paired))=={0,1}
        for name in (p,p+'_inverse'):
            rebuilt=np.repeat(np.concatenate([np.full(n,g) for g,n in report['pattern_segments'][name]]),16)
            np.testing.assert_array_equal(rebuilt,waves[name])


def test_paired_schedule_and_decoder_retain_every_polarity(noise):
    plan=noise.plan(long_hold=True,paired_polarity=True,seed_offset=200)
    tasks=noise.tasks(4.044,16,fabric_mhz=430.08,long_hold=True,paired_polarity=True,seed_offset=200)
    assert plan['total_science_probes']==sum(t['shots']*len(t['conditions']) for t in tasks)==640000
    assert len(tasks)==128 and {t['seed'] for t in tasks}==set(range(200,208))
    task=tasks[0];n=len(task['conditions']);assert n==10
    assert {(c['pattern'],c['state'],c['polarity']) for c in task['conditions']}=={
        (p,s,pol) for p in ('off','slow','fast') for s in ('g','e') for pol in ((0,) if p=='off' else (-1,1))}
    words=np.zeros((task['shots']*n,2),dtype=int)
    words[:,0]=np.tile(np.arange(n),task['shots'])
    axis=SimpleNamespace(project=lambda i,q:i,excited_threshold=5)
    rows=noise.rows_from_words(words,task,SimpleNamespace(payload=axis))
    assert len(rows)==10 and [r['pe'] for r in rows]==[float(i>5) for i in range(n)]
    assert [r['polarity'] for r in rows]==[c['polarity'] for c in task['conditions']]
    with pytest.raises(ValueError,match='long'):
        noise.plan(paired_polarity=True)
    with pytest.raises(ValueError,match='incomplete'):
        noise.rows_from_words(words[:-1],task,SimpleNamespace(payload=axis))


def test_switching_sweep_matches_commands_but_separates_chip_durations(noise):
    expected={16,32,64}
    plan=noise.plan(long_hold=True,paired_polarity=True,switching_sweep=True,seed_offset=300)
    tasks=noise.tasks(4.042,16,fabric_mhz=430.08,long_hold=True,
                      paired_polarity=True,switching_sweep=True,seed_offset=300)
    assert len(tasks)==plan['science_programs']==192
    assert sum(t['shots']*len(t['conditions']) for t in tasks)==plan['total_science_probes']==960000
    assert {t['offset_mhz'] for t in tasks}=={-4,0,2,16}
    assert {t['fast_chip_cycles'] for t in tasks}==expected
    for block in range(8):
        group=[t for t in tasks if t['block']==block]
        assert {(t['offset_mhz'],t['core_cycles'],t['fast_chip_cycles']) for t in group}=={
            (o,c,k) for o in (-4,0,2,16) for c in (512,4352) for k in expected}
    waves=[]
    for chip in sorted(expected):
        signs=noise.noise_signs(4352,'fast',seed=300,chip_cycles=chip)
        assert len(signs)==4384 and np.sum(signs)==0
        edges=np.flatnonzero(np.diff(signs[16:-16]))+1
        assert all(v%chip==0 for v in edges)
        w,report=noise.paired_waveforms(segments=[(.9,.3),(1.,20.)],park_gain=-1000,
            target_gain=-500,endpoint_gains=(-541,-458),core_cycles=4352,fabric_mhz=430.08,
            samples_per_clock=16,max_gain=1000,seed=300,dc_tick_quantum=16,fast_chip_cycles=chip)
        assert report['patterns']['fast']['chip_us']==pytest.approx(chip/430.08)
        assert report['patterns']['slow']['chip_us']==pytest.approx(128/430.08)
        waves.append(np.sort(np.r_[w['fast'],w['fast_inverse']]))
    for w in waves[1:]:np.testing.assert_array_equal(waves[0],w)
    with pytest.raises(ValueError,match='paired'):
        noise.plan(long_hold=True,switching_sweep=True)
    with pytest.raises(ValueError,match='chip'):
        noise.noise_signs(512,'fast',seed=300,chip_cycles=24)


def sweep_rows():
    rows=[]
    for b in range(8):
        for chip in (16,32,64):
            for off in (-4,0,2,16):
                for pattern in ('off','slow','fast'):
                    rate=.025
                    if pattern=='fast':rate+=(.008 if off==2 else -.006 if off==-4 else 0)*(16/chip)
                    for hold in (1.26488095238,10.19345238095):
                        for state in ('g','e'):
                            for polarity in ((0,) if pattern=='off' else (-1,1)):
                                rows.append(dict(block=b,offset_mhz=off,frequency_ghz=4.042+off/1000,
                                    fast_chip_cycles=chip,pattern=pattern,state=state,polarity=polarity,
                                    hold_us=hold,shots=500,pe=.08+(.7*np.exp(-hold*rate) if state=='e' else 0)))
    return rows


def test_switching_analysis_never_pools_different_speeds(noise):
    summary=noise.analyze(sweep_rows())
    assert summary['mode']=='switching_sweep'
    assert [c['fast_chip_cycles'] for c in summary['comparisons']]==[16,32,64]
    for c in summary['comparisons']:
        upper=next(s for s in c['profile']['sites'] if s['offset_mhz']==2)
        assert upper['rates']['fast']['rate_per_us']==pytest.approx(.025+.008*16/c['fast_chip_cycles'])
    primary=summary['primary_comparison']
    assert primary['valid'] and primary['complete_blocks']==8
    assert primary['difference_per_us']==pytest.approx(.014*(1-.25))
    assert primary['error_per_us']>0 and len(primary['ci95_t'])==2
    partial=[r for r in sweep_rows() if r['block']<3]
    assert noise.analyze(partial)['primary_comparison']['complete_blocks']==3
    mixed=sweep_rows();mixed[0].pop('fast_chip_cycles')
    with pytest.raises(ValueError,match='mixed'):
        noise.analyze(mixed)


def test_switching_primary_uses_pooled_contrasts_and_common_blocks(noise):
    rows=sweep_rows()
    # Unequal preparation contrasts and decay rates make the mean of individual
    # log-rates differ from the required logarithm after pooling shots.
    for r in rows:
        if r['state']=='e':
            extra=(.06 if r['block']==0 else 0) if (r['fast_chip_cycles'],r['offset_mhz'],r['pattern'])==(16,2,'fast') else 0
            contrast=r['pe']-.08
            r['pe']=.08+contrast*np.exp(-extra*r['hold_us'])*(.5 if r['block']==0 else 1.)
    terms=[(16,2,'fast',1),(16,2,'slow',-1),(16,-4,'fast',-1),(16,-4,'slow',1),
           (64,2,'fast',-1),(64,2,'slow',1),(64,-4,'fast',1),(64,-4,'slow',-1)]
    holds=sorted({r['hold_us'] for r in rows});expected=0
    for chip,off,pattern,weight in terms:
        contrast=[]
        for hold in holds:
            means=[np.mean([r['pe'] for r in rows if (r['fast_chip_cycles'],r['offset_mhz'],r['pattern'],r['hold_us'],r['state'])==(chip,off,pattern,hold,state)]) for state in ('g','e')]
            contrast.append(means[1]-means[0])
        expected+=weight*np.log(contrast[0]/contrast[1])/(holds[1]-holds[0])
    result=noise.analyze(rows)['primary_comparison']
    assert result['difference_per_us']==pytest.approx(expected)
    # Remove one acquisition from one endpoint: all terms must use the same
    # seven complete blocks, even though other endpoint rows are present.
    partial=[r for r in rows if not (r['block']==7 and r['fast_chip_cycles']==64 and r['offset_mhz']==2 and r['hold_us']==holds[-1])]
    result=noise.analyze(partial)['primary_comparison']
    assert result['complete_blocks']==7 and result['block_ids']==list(range(7))
    assert not result['full_run']
