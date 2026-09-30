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
