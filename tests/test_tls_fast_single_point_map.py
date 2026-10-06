import importlib
import json
from types import SimpleNamespace
import numpy as np
import pytest

NAME='WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSFastSinglePointMap'
def module():
    try:return importlib.import_module(NAME)
    except ModuleNotFoundError as exc:
        if exc.name==NAME:pytest.fail('single-point runner is not implemented')
        raise


def block(grid,shots,kind,index=0):
    c=3 if kind=='reference' else 1
    states=np.zeros((c,len(grid),shots),dtype=np.int32)
    if kind=='reference':
        states[0,:,:shots//10]=1;states[1,:,:shots*8//10]=1;states[2,:,:shots//2]=1
    else:states[0,:,:shots//2]=1
    return dict(states=states,i=states.astype(np.int64),q=np.zeros_like(states,dtype=np.int64),
                frequency_ghz=np.asarray(grid),realized_frequency_ghz=np.asarray(grid),
                dc_gains=np.arange(len(grid)),started_epoch_s=100.+2*index,finished_epoch_s=101.+2*index,
                started_monotonic_s=2.*index,finished_monotonic_s=2.*index+1,compile_s=.1,
                transfers=[dict(records_received=states.size)],kind=kind,delay_us=25.)


def test_single_delay_configuration_omits_refs_and_keeps_active_reset():
    m=module();base={'reset_mode':'opx_unbounded','read_pulse_gain':940,'flux_predistortion_recovery_us':40.}
    cfg=m.block_config(base,[-10,-20],40,kind='science',delay_us=25.)
    assert cfg['opx_t1_include_references'] is False
    assert cfg['opx_t1_5pt_delays_us']==[25.]
    assert cfg['opx_t1_3pt_dc_gains']==[-10,-20]
    assert cfg['opx_t1_3pt_shots']==40
    assert cfg['reset_mode']=='opx_unbounded' and cfg['read_pulse_gain']==940
    assert 'opx_t1_include_references' not in base
    ref=m.block_config(base,[-10,-20],40,kind='reference',delay_us=25.)
    assert ref['opx_t1_include_references'] is True
    with pytest.raises(ValueError,match='active'):m.block_config(dict(base,reset_mode='passive'),[-10],40,kind='science',delay_us=25.)


def test_hardware_condition_emission_is_one_probe_or_three_reference_conditions():
    m=module();Program=m.make_program_class();p=object.__new__(Program);emitted=[]
    p._emit_tagged_condition=lambda *args:emitted.append(args)
    p.cfg=m.block_config({'reset_mode':'opx_unbounded'},[-10],40,kind='science',delay_us=25.)
    p._matched_condition_count=1;p._emit_t1_conditions({},'TEST_UP')
    assert emitted==[('TEST_UP_PS0',True,True,25.1,2)]
    emitted.clear();p.cfg=m.block_config({'reset_mode':'opx_unbounded'},[-10],40,kind='reference',delay_us=25.)
    p._matched_condition_count=3;p._emit_t1_conditions({},'TEST_UP')
    assert emitted==[('TEST_UP_P0',False,True,.1,0),('TEST_UP_P1',True,True,.1,1),('TEST_UP_PS0',True,True,25.1,2)]


@pytest.mark.parametrize('conditions',[1,3])
def test_canonical_iq_restores_reverse_sweep_without_changing_shot_order(conditions):
    m=module();records=[SimpleNamespace(final_i=i,final_q=-i) for i in range(6*conditions)]
    i,q=m.canonical_iq(records,shots=2,points=3,conditions=conditions)
    assert i.shape==(conditions,3,2)
    assert i[0,:,0].tolist()==[0,conditions,2*conditions]
    assert i[0,:,1].tolist()==[5*conditions,4*conditions,3*conditions]
    assert np.array_equal(q,-i)
    with pytest.raises(ValueError,match='incomplete'):m.canonical_iq(records[:-1],shots=2,points=3,conditions=conditions)


def test_collection_inserts_periodic_refs_but_science_contains_only_one_condition(tmp_path):
    m=module();calls=[]
    def acquire(grid,shots,name,kind):
        calls.append((name,kind,shots));return block(grid,shots,kind,len(calls))
    manifest={'status':'initializing','completed':[],'plan':m.plan(frames=5,reference_every=2)}
    summary=m.collect(tmp_path,acquire,manifest,frames=5,reference_every=2)
    assert calls==[('local_pre','reference',250),('frame_0000','science',40),('frame_0001','science',40),
                   ('reference_0002','reference',40),('frame_0002','science',40),('frame_0003','science',40),
                   ('reference_0004','reference',40),('frame_0004','science',40),('local_post','reference',250)]
    assert summary['science_frames']==5 and summary['reference_blocks']==4
    assert summary['normalization_scope'].startswith('Periodic')
    with np.load(tmp_path/'frame_0000.npz') as z:
        assert z['states'].shape==(1,101,40) and z['shot_scan_direction'].tolist()==[1,-1]*20
    meta=json.loads((tmp_path/'frame_0000.json').read_text());assert meta['condition_order']==['Ps_25us']
    with np.load(tmp_path/'normalized.npz') as z:assert np.isfinite(z['survival']).all()
    assert manifest['status']=='complete'


def test_interruption_retains_raw_and_masks_frames_without_a_later_reference(tmp_path):
    m=module();calls=[]
    def acquire(grid,shots,name,kind):
        calls.append(name)
        if name=='frame_0003':raise KeyboardInterrupt
        return block(grid,shots,kind,len(calls))
    manifest={'status':'initializing','completed':[],'plan':m.plan(frames=5,reference_every=2)}
    with pytest.raises(KeyboardInterrupt):m.collect(tmp_path,acquire,manifest,frames=5,reference_every=2)
    assert manifest['completed']==['local_pre','frame_0000','frame_0001','reference_0002','frame_0002']
    assert (tmp_path/'frame_0002.npz').exists()
    with np.load(tmp_path/'normalized.npz') as z:
        assert np.isfinite(z['survival'][:2]).all()
        assert np.isnan(z['survival'][2]).all()
        assert z['bracketed'].tolist()==[True,True,False]


def test_periodic_normalization_interpolates_references_in_real_time_not_frame_index():
    m=module();grid=np.array([3.98]);pre=block(grid,100,'reference');post=block(grid,100,'reference');science=block(grid,100,'science')
    pre.update(started_epoch_s=0.,finished_epoch_s=2.);post.update(started_epoch_s=10.,finished_epoch_s=12.)
    science.update(started_epoch_s=5.,finished_epoch_s=7.)
    post['states'][0,:,:]=0;post['states'][0,:,:20]=1
    post['states'][1,:,:]=0;post['states'][1,:,:90]=1
    result=m.normalize_frames([('frame_0',science)],[('pre',pre),('post',post)])
    assert result['survival'][0,0]==pytest.approx(.5)
    assert result['p0'][0,0]==pytest.approx(.15) and result['p1'][0,0]==pytest.approx(.85)
    assert result['reference_weight'].tolist()==[.5]
    result=m.normalize_frames([('frame_0',science)],[('pre',pre)])
    assert np.isnan(result['survival']).all() and not result['bracketed'][0]


def test_low_reference_contrast_is_masked_without_clipping_science_or_faking_t1():
    m=module();grid=np.array([3.98]);pre=block(grid,100,'reference');post=block(grid,100,'reference');science=block(grid,100,'science')
    pre.update(started_epoch_s=0.,finished_epoch_s=1.);post.update(started_epoch_s=10.,finished_epoch_s=11.);science.update(started_epoch_s=5.,finished_epoch_s=6.)
    for r in [pre,post]:r['states'][1]=r['states'][0]
    result=m.normalize_frames([('f',science)],[('pre',pre),('post',post)])
    assert np.isnan(result['survival']).all()
    assert not result['reference_valid'][0]
    assert 't1' not in result


def test_invalid_plan_never_reaches_hardware_and_record_budget_is_reduced():
    m=module();p=m.plan(frames=100,reference_every=20)
    assert p['science_conditions']==['Ps_25us'] and p['science_records_per_frame']==4040
    assert p['science_measurement_reduction_vs_five_point']==5
    assert p['readout_gain']==940 and p['qubit']=='q3'
    assert p['reference_blocks_per_batch']==6
    for opts in [{'frames':0},{'reference_every':0},{'delay_us':float('nan')},{'delay_us':0},{'shots':3},{'readout_gain':950}]:
        with pytest.raises(ValueError):m.plan(**opts)


def test_cli_repeats_single_point_batches_until_interrupt_and_keeps_options(tmp_path,monkeypatch):
    m=module();calls=[]
    def run(**kw):
        folder=tmp_path/f'b{len(calls)}';folder.mkdir();(folder/'manifest.json').write_text(json.dumps({'status':'complete' if not calls else 'interrupted'}));calls.append(kw);return folder
    monkeypatch.setattr(m,'run',run)
    assert m.main(['--run','--loop','--frames','100','--reference-every','20'])==130
    assert len(calls)==2 and all(k['delay_us']==25 and k['readout_gain']==940 for k in calls)
    assert all(k['continuous'] for k in calls)


def test_save_rejects_incorrect_science_condition_count_and_float_raw_iq(tmp_path):
    m=module();b=block([3.98],40,'reference')
    with pytest.raises(ValueError,match='condition'):m.save_block(tmp_path,'bad',b,kind='science',delay_us=25)
    b=block([3.98],40,'science');b['i']=b['i'].astype(float)
    with pytest.raises(ValueError,match='integer'):m.save_block(tmp_path,'bad',b,kind='science',delay_us=25)


@pytest.mark.parametrize('kind,records',[('science',4040),('reference',12120)])
def test_constructor_uses_correct_stream_record_budget_before_parent_initialization(monkeypatch,kind,records):
    m=module()
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import programs
    monkeypatch.setattr(programs.OPXResetT1Program,'__init__',lambda self,board,cfg,*a:setattr(self,'cfg',cfg))
    cfg=m.block_config({'reset_mode':'opx_unbounded','opx_t1_3pt_gain_lookup':True},list(range(-1000,-899)),40,kind=kind,delay_us=25.)
    p=m.make_program_class()({'tprocs':[{'dmem_size':16384}]},cfg,None,None)
    assert p.cfg['reps']==records
    assert p._records_per_dc()==(1 if kind=='science' else 3)
    p.decode_dmem_records(np.array([1,2,3,4],dtype=np.uint32),expected_records=2)
    assert [r.final_i for r in p.transferred_records]==[1,3]
    assert p.transfer_receipts[-1]['records_received']==2


def test_periodic_reference_drift_masks_derived_results_but_preserves_raw_shots(tmp_path):
    m=module();calls=[]
    def acquire(grid,shots,name,kind):
        calls.append(name);x=block(grid,shots,kind,len(calls))
        if name=='reference_0002':x['states'][1]=0
        return x
    manifest={'status':'initializing','completed':[],'plan':m.plan(frames=3,reference_every=2)}
    m.collect(tmp_path,acquire,manifest,frames=3,reference_every=2)
    assert manifest['status']=='complete_reference_drift'
    with np.load(tmp_path/'normalized.npz') as z:
        assert np.isnan(z['survival']).all() and np.isfinite(z['raw_probability']).all()
    assert np.load(tmp_path/'frame_0002.npz')['states'].size==4040


def test_wide_minimum_shot_plan_keeps_reference_precision_independent():
    m=module();p=m.plan(frames=1000,shots=4,reference_every=100,reference_shots=40,
                       center_ghz=4.1,width_mhz=400,step_mhz=.5,continuous=True)
    assert p['local_points']==801 and p['science_records_per_frame']==3204
    assert p['periodic_reference_shots']==40 and p['full_corrected_return_us']==5
    assert p['reference_blocks_per_batch']==11 and p['total_frame_limit'] is None
    grid=m.fast.local_grid(4.1,width_mhz=400,step_mhz=.5)
    assert grid[0]==3.9 and grid[-1]==4.3
    assert m.plan(shots=4)['periodic_reference_shots']==4  # Existing behavior retained.


@pytest.mark.parametrize('shots',[0,3,251,True,float('nan')])
def test_invalid_independent_reference_shots_rejected(shots):
    with pytest.raises(ValueError):module().plan(reference_shots=shots)


def test_independent_reference_shots_reach_collection_and_repeated_cli(tmp_path,monkeypatch):
    m=module();calls=[]
    def acquire(grid,shots,name,kind):
        calls.append((kind,shots));return block(grid,shots,kind,len(calls))
    manifest={'completed':[],'plan':m.plan(frames=3,shots=4,reference_every=2,reference_shots=40)}
    m.collect(tmp_path,acquire,manifest,frames=3,shots=4,reference_every=2,reference_shots=40)
    assert calls==[('reference',250),('science',4),('science',4),('reference',40),('science',4),('reference',250)]
    with np.load(tmp_path/'reference_0002.npz') as z:assert z['states'].shape==(3,101,40)
    options=[]
    def run(**kw):
        folder=tmp_path/f'b{len(options)}';folder.mkdir()
        (folder/'manifest.json').write_text(json.dumps({'status':'complete' if not options else 'interrupted'}))
        options.append(kw);return folder
    monkeypatch.setattr(m,'run',run)
    assert m.main(['--run','--loop','--shots','4','--reference-shots','40'])==130
    assert len(options)==2 and all(x['reference_shots']==40 and x['shots']==4 for x in options)
