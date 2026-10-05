import importlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

NAME = 'WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSFastLossMap'


def module():
    return importlib.import_module(NAME)


def block(grid, shots=40, center=4.1):
    rng = np.random.default_rng(78)
    f = np.asarray(grid)
    loss = .55/(1+((f-center)/.002)**2)
    probabilities = np.array([np.full(len(f), .1), np.full(len(f), .85),
                              .1+.75*(1-.3*loss), .1+.75*(1-loss), .1+.75*(1-loss)])
    states = (rng.random((5, len(f), shots)) < probabilities[..., None]).astype(int)
    return dict(i=states.copy(), q=np.zeros_like(states), states=states,
                frequency_ghz=f, realized_frequency_ghz=f, dc_gains=np.arange(len(f)),
                started_epoch_s=100., finished_epoch_s=101., started_monotonic_s=20.,
                finished_monotonic_s=21., compile_s=.1, telemetry={'reset_mode':'opx_unbounded'},
                transfers=[{'records_received':5*len(f)*shots,'host_epoch_s':101.}])


def test_canonicalization_restores_alternating_frequency_order_without_losing_shots():
    m = module()
    records = [SimpleNamespace(final_i=x, final_q=-x) for x in range(30)]
    i,q = m.canonical_iq(records, shots=2, points=3)
    assert i.shape == (5,3,2)
    assert i[0,:,0].tolist() == [0,5,10]
    assert i[0,:,1].tolist() == [25,20,15]
    assert q[4,2,1] == -19
    with pytest.raises(ValueError, match='incomplete'):
        m.canonical_iq(records[:-1],shots=2,points=3)


def test_selects_loss_in_both_orders_without_requiring_two_lines_or_ef_bias():
    m = module()
    b=block(np.arange(3.8,4.3001,.002),250)
    result=m.select_feature(b)
    assert result['center_ghz'] == pytest.approx(4.1,abs=.0021)
    grid=m.local_grid(result['center_ghz'])
    assert len(grid)==21
    assert np.diff(grid)==pytest.approx(np.full(20,.001))
    assert min(grid)>=3.8 and max(grid)<=4.3


def test_flat_or_one_order_artifact_does_not_start_targeted_stream():
    m=module()
    b=block(np.arange(3.8,4.3001,.002),1000,center=5.)
    with pytest.raises(ValueError,match='loss'):
        m.select_feature(b)
    b['states'][4,145:155,::2]=0
    with pytest.raises(ValueError,match='loss'):
        m.select_feature(b)


def test_reference_drift_is_reported_instead_of_mislabelled_line_motion():
    m=module()
    pre=block(np.arange(4.09,4.111,.001),5000)
    post=block(np.arange(4.09,4.111,.001),5000)
    assert m.reference_check(pre,post)['valid']
    post['states'][1]=post['states'][0]
    assert not m.reference_check(pre,post)['valid']


def test_collect_preserves_each_frame_and_acquisition_gaps(tmp_path):
    m=module()
    called=[]
    def acquire(grid,shots,name):
        called.append((name,shots,len(grid)))
        b=block(grid,shots)
        n=len(called)
        b.update(started_epoch_s=100+2*n, finished_epoch_s=101+2*n,
                 started_monotonic_s=2*n,finished_monotonic_s=2*n+1)
        return b
    manifest={'status':'initializing','completed':[]}
    result=m.collect(tmp_path,acquire,manifest,frames=3)
    assert [c[0] for c in called]==['scout','local_pre','frame_0000','frame_0001','frame_0002','local_post']
    assert result['frame_start_period_s']['median']==2.
    assert result['frame_acquisition_s']['median']==1.
    for n in range(3):
        with np.load(tmp_path/f'frame_{n:04d}.npz') as z:
            assert z['states'].shape==(5,21,40)
            assert len(z['shot_scan_direction'])==40
    assert json.loads((tmp_path/'manifest.json').read_text())['status']=='complete'


def test_interruption_keeps_completed_data_and_has_no_automatic_retry(tmp_path):
    m=module()
    called=[]
    def acquire(grid,shots,name):
        called.append(name)
        if name=='frame_0001':raise KeyboardInterrupt
        return block(grid,shots)
    manifest={'status':'initializing','completed':[]}
    with pytest.raises(KeyboardInterrupt):m.collect(tmp_path,acquire,manifest,frames=3)
    assert called[-1]=='frame_0001'
    assert (tmp_path/'frame_0000.npz').exists()
    assert manifest['completed']==['scout','local_pre','frame_0000']


def test_keyboard_interrupt_aborts_hardware_before_saving_partial_bank(tmp_path,monkeypatch):
    m=module()
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import integration
    events=[]
    soc=SimpleNamespace(tproc=SimpleNamespace(reset=lambda:events.append('stopped')),
                        reset_gens=lambda:events.append('generators_reset'))
    program=SimpleNamespace(transferred_records=[SimpleNamespace(final_i=12,final_q=-5)],
                            transfer_receipts=[{'records_received':1}])
    def interrupted(*a,**kw):raise KeyboardInterrupt
    monkeypatch.setattr(integration,'_run_program',interrupted)
    with pytest.raises(KeyboardInterrupt):
        m.acquire_records(soc,program,{},40,100,tmp_path,'frame_0000')
    assert events==['stopped','generators_reset']
    with np.load(tmp_path/'frame_0000.partial.npz') as z:
        assert z['i_acquisition_order'].tolist()==[12]
        assert z['q_acquisition_order'].tolist()==[-5]


def test_decoder_keeps_received_records_even_without_progress_callback():
    m=module()
    Program=m.make_program_class()
    p=Program.__new__(Program)
    p.transferred_records=[];p.transfer_receipts=[]
    p.decode_dmem_records(np.array([1,2,3,4],dtype=np.uint32),expected_records=2)
    p.decode_dmem_records(np.array([5,6],dtype=np.uint32),expected_records=1)
    assert [r.final_i for r in p.transferred_records]==[1,3,5]
    assert [r['records_received'] for r in p.transfer_receipts]==[2,3]


def test_low_contrast_flat_scout_at_actual_shot_count_cannot_seed_noise_feature():
    m=module()
    rng=np.random.default_rng(0)
    p=np.array([.2,.5,.4,.4,.4])[:,None,None]
    b=block(np.arange(3800,4301,2)/1000,250)
    b['states']=(rng.random((5,251,250))<p).astype(int)
    with pytest.raises(ValueError,match='loss'):m.select_feature(b)


def test_run_pins_q3_and_correction_then_restores_pc_settings_on_failure(tmp_path,monkeypatch):
    pytest.importorskip('qick')
    import os
    from WorkingProjects.TLS_Spectroscopy.Client_modules import Runners
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSPumpProbeLocalizer as localizer
    m=module()
    previous={'qubit_freq':4367.760,'read_pulse_freq':7026.520,'sigma':2.}
    tls=SimpleNamespace(BaseConfig=previous,QUBIT='q4',SET_YOKO=True,outerFolder='previous',
                        FLUX_FIT_PARAMS=['previous'],BASELINE_DC_OFFSET=0,TARGET_DC_OFFSET=0,
                        FLUX_TAIL_COMPENSATION_GAIN=2.)
    correction=tmp_path/'production.json';correction.write_text('{}')
    monkeypatch.setenv('Q3_FLUX_TAIL_GAIN','2.0')
    monkeypatch.setenv('Q3_5PT_CORRECTION_JSON','previous.json')
    monkeypatch.setattr(localizer,'checked_correction',lambda *a:correction)
    monkeypatch.setattr(Runners,'TLSSpectroscopy',tls,raising=False)
    def load(*args):
        assert tls.QUBIT=='q3' and not tls.SET_YOKO
        assert tls.BaseConfig['read_pulse_freq']==6933.026
        assert tls.BaseConfig['sigma']==.2
        assert tls.FLUX_TAIL_COMPENSATION_GAIN==1.
        assert os.environ['Q3_5PT_CORRECTION_JSON']==str(correction)
        return []
    tls._load_correction=load
    def no_hardware():raise RuntimeError('intentional hardware boundary failure')
    tls.makeProxy=no_hardware
    folder=m.run(data_root=tmp_path,progress=False)
    manifest=json.loads((folder/'manifest.json').read_text())
    assert manifest['status']=='failed' and 'intentional hardware boundary' in manifest['error']
    assert tls.BaseConfig is previous and tls.QUBIT=='q4' and tls.SET_YOKO
    assert tls.FLUX_TAIL_COMPENSATION_GAIN==2.
    assert tls.FLUX_FIT_PARAMS==['previous']
    assert os.environ['Q3_FLUX_TAIL_GAIN']=='2.0'
    assert os.environ['Q3_5PT_CORRECTION_JSON']=='previous.json'


def test_block_save_refuses_float_iq_in_place_of_raw_integer_records(tmp_path):
    m=module();b=block(np.arange(4.09,4.111,.001))
    b['i']=b['i'].astype(float)
    with pytest.raises(ValueError,match='integer'):m.save_block(tmp_path,'bad',b)


def test_interrupted_npz_write_never_publishes_corrupt_final_block(tmp_path,monkeypatch):
    m=module();b=block(np.arange(4.09,4.111,.001))
    def interrupted(destination,**kwargs):
        if hasattr(destination,'write'):destination.write(b'partial archive')
        else:open(destination,'wb').write(b'partial archive')
        raise KeyboardInterrupt
    monkeypatch.setattr(np,'savez_compressed',interrupted)
    with pytest.raises(KeyboardInterrupt):m.save_block(tmp_path,'frame_0000',b)
    assert not (tmp_path/'frame_0000.npz').exists()


def test_processing_interrupt_preserves_received_iq_after_hardware_returns(tmp_path,monkeypatch):
    m=module()
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import integration
    events=[]
    soc=SimpleNamespace(tproc=SimpleNamespace(reset=lambda:events.append('stopped')),
                        reset_gens=lambda:events.append('generators_reset'))
    records=[SimpleNamespace(final_i=14,final_q=-9)]
    program=SimpleNamespace(transferred_records=records,transfer_receipts=[])
    monkeypatch.setattr(integration,'_run_program',lambda *a,**kw:records)
    def interrupted(records):raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        m.acquire_records(soc,program,{},40,100,tmp_path,'frame_0000',process=interrupted)
    assert events==['stopped','generators_reset']
    with np.load(tmp_path/'frame_0000.partial.npz') as z:
        assert z['i_acquisition_order'].tolist()==[14]


def test_extended_plan_is_finite_and_keeps_validated_shots_and_grid():
    m=module();p=m.plan(frames=1000)
    assert p['frames']==1000 and p['shots_per_condition_per_frame']==40
    assert p['local_points']==21 and p['full_corrected_return_us']==40.
    assert m.plan()['frames']==40
    for invalid in (0,-1,2001):
        with pytest.raises(ValueError,match='frames'):m.plan(frames=invalid)


def test_cli_passes_extended_count_to_runner_without_implicit_loop(tmp_path,monkeypatch):
    m=module();counts=[]
    def run(**kwargs):
        counts.append(kwargs['frames'])
        (tmp_path/'manifest.json').write_text('{"status":"complete"}')
        return tmp_path
    monkeypatch.setattr(m,'run',run)
    assert m.main(['--run','--frames','1000'])==0
    assert counts==[1000]


def test_explicit_window_records_even_flat_data_without_a_scout_gate(tmp_path):
    m=module();called=[]
    def acquire(grid,shots,name):
        called.append((name,grid.copy(),shots))
        return block(grid,shots,center=5.)
    manifest={'status':'initializing','completed':[]}
    result=m.collect(tmp_path,acquire,manifest,frames=3,center_ghz=4.108)
    assert [x[0] for x in called]==['local_pre','frame_0000','frame_0001','frame_0002','local_post']
    assert called[0][1]==pytest.approx(np.arange(4098,4119)/1000)
    assert all(np.array_equal(x[1],called[0][1]) for x in called)
    assert result['automatic_switching_claim'] is False
    assert manifest['selection']['mode']=='explicit_window'
    assert manifest['selection']['fresh_feature_claim'] is False


def test_explicit_plan_and_cli_keep_local_reference_maps_and_validate_band(tmp_path,monkeypatch):
    m=module();p=m.plan(frames=1000,center_ghz=4.108)
    assert p['scout_shots']==0 and p['scout_ghz'] is None
    assert p['window_center_ghz']==4.108
    assert p['local_pre_post_shots']==250 and p['shots_per_condition_per_frame']==40
    for invalid in (3.79,4.31,float('nan')):
        with pytest.raises(ValueError,match='band'):m.plan(center_ghz=invalid)
    observed=[]
    def run(**kwargs):
        observed.append(kwargs)
        (tmp_path/'manifest.json').write_text('{"status":"complete"}')
        return tmp_path
    monkeypatch.setattr(m,'run',run)
    assert m.main(['--run','--frames','1000','--center-ghz','4.108'])==0
    assert observed[0]['center_ghz']==4.108 and observed[0]['frames']==1000


def test_wider_window_keeps_the_same_point_and_shot_budget(tmp_path):
    m=module();called=[]
    def acquire(grid,shots,name):
        called.append((grid.copy(),shots,name))
        return block(grid,shots)
    manifest={'status':'initializing','completed':[]}
    m.collect(tmp_path,acquire,manifest,frames=3,center_ghz=4.108,width_mhz=40,step_mhz=2.)
    assert all(len(grid)==21 for grid,_,_ in called)
    assert called[0][0]==pytest.approx(np.arange(4088,4129,2)/1000)
    assert [shots for _,shots,_ in called]==[250,40,40,40,250]
    assert m.plan(center_ghz=4.108,width_mhz=40,step_mhz=2.)['local_points']==21


def test_cli_wider_window_and_invalid_grids_are_checked_before_hardware(tmp_path,monkeypatch):
    m=module();observed=[]
    def run(**kwargs):
        observed.append(kwargs)
        (tmp_path/'manifest.json').write_text('{"status":"complete"}')
        return tmp_path
    monkeypatch.setattr(m,'run',run)
    assert m.main(['--run','--frames','200','--center-ghz','4.108','--width-mhz','40','--step-mhz','2'])==0
    assert observed[0]['width_mhz']==40 and observed[0]['step_mhz']==2.
    for options in ({'width_mhz':101},{'width_mhz':0},{'step_mhz':.1},{'width_mhz':3,'step_mhz':2.}):
        with pytest.raises(ValueError,match='grid'):m.plan(**options)
    for center in [3.8,4.3]:
        grid=m.local_grid(center,width_mhz=40,step_mhz=2.)
        assert len(grid)==21 and grid.min()>=3.8 and grid.max()<=4.3
