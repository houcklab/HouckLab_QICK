"""q3 single-delay loss maps with sparse references and production active reset.

Science is one excited-prepared 25 us probe per frequency, without P0/P1 or
other decay delays. Separate periodic blocks measure P0/P1/the same probe.
Raw shots are authoritative; interpolated reference normalization is a proxy,
not a fitted T1. --loop repeats fresh finite batches until Ctrl+C or an error.
"""
import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import uuid
import numpy as np
from . import TLSFastLossMap as fast

FRAMES=100
SHOTS=40
REFERENCE_EVERY=20
REFERENCE_SHOTS=250


def plan(*,frames=FRAMES,shots=SHOTS,reference_every=REFERENCE_EVERY,delay_us=25.,
         center_ghz=3.970,width_mhz=50,step_mhz=.5,readout_gain=940,continuous=False,
         reference_shots=None):
    grid=fast.local_grid(center_ghz,width_mhz=width_mhz,step_mhz=step_mhz)
    fast.readout_base_config({},readout_gain)
    for value,name,lo,hi in [(frames,'frames',1,2000),(shots,'shots',4,250),(reference_every,'reference_every',1,2000)]:
        if isinstance(value,bool) or not isinstance(value,int) or not lo<=value<=hi:
            raise ValueError(f'{name} must be an integer between {lo} and {hi}')
    reference_shots=shots if reference_shots is None else reference_shots
    if isinstance(reference_shots,bool) or not isinstance(reference_shots,int) or not 4<=reference_shots<=250:
        raise ValueError('reference_shots must be an integer between 4 and 250')
    if shots%2 or reference_shots%2:raise ValueError('shots must be even to balance sweep directions')
    if not np.isfinite(delay_us) or not .1<=delay_us<=100.:
        raise ValueError('delay_us must be finite and between .1 and 100 us')
    refs=2+(frames-1)//reference_every
    return dict(qubit='q3',science_conditions=[f'Ps_{delay_us:g}us'],
                reference_conditions=['P0','P1',f'Ps_{delay_us:g}us'],delay_us=float(delay_us),
                window_center_ghz=float(center_ghz),local_width_mhz=width_mhz,local_step_mhz=step_mhz,
                local_points=len(grid),frames=frames,shots_per_condition_per_frame=shots,
                science_records_per_frame=len(grid)*shots,science_measurement_reduction_vs_five_point=5,
                reference_every_science_frames=reference_every,periodic_reference_shots=reference_shots,
                local_pre_post_shots=REFERENCE_SHOTS,reference_blocks_per_batch=refs,
                readout_gain=readout_gain,reset='production active-reset timing throughout',
                full_corrected_return_us=5.,repeat_batches=bool(continuous),
                total_frame_limit=None if continuous else frames,
                batch_calibration='fresh production active-reset calibration for every batch',
                loop_stop_policy='Ctrl+C or acquisition/calibration error; retain and flag reference drift',
                normalization='Time interpolation between bracketing periodic P0/P1 blocks within one batch; no extrapolation',
                interpretation='Single-delay survival proxy; no fitted T1 or automatic switching claim',
                timing='Host block/transfer timestamps and shot order; no individual hardware timestamps',
                cadence='Measured on hardware; fewer measurements does not guarantee fivefold faster host cadence')


def block_config(base,gains,shots,*,kind,delay_us):
    if base.get('reset_mode')!='opx_unbounded':raise ValueError('production active reset is required')
    if kind not in ('science','reference'):raise ValueError('unknown block kind')
    return dict(base,shots=shots,reps=shots,opx_reset_scheme='opx_unbounded',
                opx_t1_3pt_shots=shots,opx_t1_3pt_dc_gains=list(gains),
                opx_t1_5pt_delays_us=[float(delay_us)],opx_t1_5pt_reference_hold_us=.1,
                opx_t1_include_references=(kind=='reference'),opx_t1_survival_probe_state='e',
                opx_reverse_survival_order=False,opx_t1_survival_index_offset=0,
                ff_hold=.1+float(delay_us),t1_wait_us=.1+float(delay_us),opx_resident_dmem_stream=True)


def canonical_iq(records,*,shots,points,conditions):
    if len(records)!=shots*points*conditions:raise ValueError('incomplete single-point acquisition')
    i=np.asarray([r.final_i for r in records],dtype=np.int64).reshape(shots,points,conditions)
    q=np.asarray([r.final_q for r in records],dtype=np.int64).reshape(shots,points,conditions)
    i[1::2]=i[1::2,::-1];q[1::2]=q[1::2,::-1]
    return i.transpose(2,1,0),q.transpose(2,1,0)


def make_program_class():
    from ..active_reset_OPX.programs import OPXResetT1NPointProgram
    class SinglePointProgram(OPXResetT1NPointProgram):
        """Use existing N-point pulse instructions; observe decoded receipts."""
        def __init__(self,*args,**kwargs):
            self.transferred_records=[];self.transfer_receipts=[]
            super().__init__(*args,**kwargs)
        def decode_dmem_records(self,words,expected_records=None):
            records=super().decode_dmem_records(words,expected_records)
            self.transferred_records.extend(records)
            self.transfer_receipts.append(dict(records_received=len(self.transferred_records),
                host_epoch_s=time.time(),host_monotonic_s=time.perf_counter()))
            return records
    return SinglePointProgram


def save_block(folder,name,block,*,kind,delay_us):
    a=np.asarray(block['states']);conditions=3 if kind=='reference' else 1
    if a.ndim!=3 or a.shape[0]!=conditions or a.shape[1]!=len(block['frequency_ghz']):
        raise ValueError('malformed single-point condition block')
    if a.shape[2]<1 or not np.all((a==0)|(a==1)):raise ValueError('nonbinary or empty classified states')
    for k in ('i','q'):
        v=np.asarray(block[k])
        if v.shape!=a.shape or not np.issubdtype(v.dtype,np.integer):raise ValueError('raw IQ must be complete integer arrays')
    fast.atomic_npz(Path(folder)/(name+'.npz'),i=block['i'],q=block['q'],states=a,
                    frequency_ghz=block['frequency_ghz'],realized_frequency_ghz=block['realized_frequency_ghz'],
                    dc_gains=block['dc_gains'],shot_scan_direction=np.where(np.arange(a.shape[2])%2==0,1,-1))
    meta={k:v for k,v in block.items() if k not in ('i','q','states')}
    meta.update(kind=kind,delay_us=float(delay_us),array_order='condition, canonical frequency, shot; raw integer integrated IQ',
                condition_order=(['P0','P1'] if kind=='reference' else [])+[f'Ps_{delay_us:g}us'],
                shot_order='even shots follow stored frequency order; odd shots reverse it; fixed condition order')
    if kind=='reference':meta['pooled_reference_probabilities']=a[:2].mean(axis=(1,2)).tolist()
    fast.checkpoint(Path(folder)/(name+'.json'),meta)


def normalize_frames(frames,references):
    points=len(frames[0][1]['frequency_ghz']) if frames else len(references[0][1]['frequency_ghz'])
    n=len(frames)
    raw=np.empty((n,points));p0=np.full_like(raw,np.nan);p1=np.full_like(raw,np.nan)
    bracketed=np.zeros(n,dtype=bool);valid=np.zeros(n,dtype=bool);weights=np.full(n,np.nan)
    left=['']*n;right=['']*n;mid=np.empty(n)
    ref_times=np.array([(x['started_epoch_s']+x['finished_epoch_s'])/2 for _,x in references])
    if len(ref_times)>1 and not np.all(np.diff(ref_times)>0):raise ValueError('reference times must strictly increase')
    for j,(name,science) in enumerate(frames):
        mid[j]=(science['started_epoch_s']+science['finished_epoch_s'])/2
        raw[j]=science['states'][0].mean(axis=1)
        k=int(np.searchsorted(ref_times,mid[j],side='right'))
        if k==0 or k==len(references):continue
        ln,lb=references[k-1];rn,rb=references[k]
        if not np.array_equal(lb['frequency_ghz'],science['frequency_ghz']) or not np.array_equal(rb['frequency_ghz'],science['frequency_ghz']):
            raise ValueError('normalization reference frequency mismatch')
        w=(mid[j]-ref_times[k-1])/(ref_times[k]-ref_times[k-1]);weights[j]=w
        l=lb['states'][:2].mean(axis=2);r=rb['states'][:2].mean(axis=2)
        p0[j],p1[j]=(1-w)*l+w*r
        left[j]=ln;right[j]=rn;bracketed[j]=True
        valid[j]=fast.reference_check(lb,rb)['valid']
    contrast=p1-p0
    good=(contrast>=.2)&valid[:,None]&bracketed[:,None]
    survival=(raw-p0)/np.where(good,contrast,np.nan)
    return dict(raw_probability=raw,p0=p0,p1=p1,contrast=contrast,survival=survival,
                mid_epoch=mid,bracketed=bracketed,reference_valid=valid,reference_weight=weights,
                left_reference=np.asarray(left,dtype=str),right_reference=np.asarray(right,dtype=str))


def collect(folder,acquire,manifest,*,frames=FRAMES,shots=SHOTS,reference_every=REFERENCE_EVERY,
            delay_us=25.,center_ghz=3.970,width_mhz=50,step_mhz=.5,update=None,acquire_saves_block=False,
            reference_shots=None):
    requested=plan(frames=frames,shots=shots,reference_every=reference_every,delay_us=delay_us,
         center_ghz=center_ghz,width_mhz=width_mhz,step_mhz=step_mhz,reference_shots=reference_shots)
    reference_shots=requested['periodic_reference_shots']
    folder=Path(folder);grid=fast.local_grid(center_ghz,width_mhz=width_mhz,step_mhz=step_mhz)
    science=[];refs=[];rows=[]
    def measure(name,kind,count):
        manifest.update(status='acquiring',current=name);fast.checkpoint(folder/'manifest.json',manifest)
        x=acquire(grid,count,name,kind)
        if not acquire_saves_block:save_block(folder,name,x,kind=kind,delay_us=delay_us)
        manifest['completed'].append(name);fast.checkpoint(folder/'manifest.json',manifest)
        if update:update()
        return x
    try:
        refs.append(('local_pre',measure('local_pre','reference',REFERENCE_SHOTS)))
        for j in range(frames):
            name=f'frame_{j:04d}';x=measure(name,'science',shots);science.append((name,x))
            rows.append(dict(index=j,started_epoch_s=x['started_epoch_s'],finished_epoch_s=x['finished_epoch_s'],
                             start=x['started_monotonic_s'],end=x['finished_monotonic_s'],compile_s=x['compile_s']))
            if (j+1)%reference_every==0 and j+1<frames:
                name=f'reference_{j+1:04d}';refs.append((name,measure(name,'reference',reference_shots)))
        refs.append(('local_post',measure('local_post','reference',REFERENCE_SHOTS)))
    finally:
        # No extrapolation after a stop: frames after the last reference remain raw only.
        if refs:
            normalized=normalize_frames(science,refs)
            fast.atomic_npz(folder/'normalized.npz',frequency_ghz=grid,**normalized)
            pairs=[dict(left=a[0],right=b[0],**fast.reference_check(a[1],b[1])) for a,b in zip(refs,refs[1:])]
            durations=np.array([x['end']-x['start'] for x in rows]);periods=np.diff([x['start'] for x in rows])
            def stats(x):
                return dict(median=float(np.median(x)),min=float(np.min(x)),max=float(np.max(x))) if len(x) else None
            summary=dict(science_frames=len(science),reference_blocks=len(refs),frames=rows,
                         frame_acquisition_s=stats(durations),frame_start_period_s=stats(periods),
                         reference_pairs=pairs,reference_check=dict(valid=bool(pairs) and all(x['valid'] for x in pairs)),
                         bracketed_frames=int(normalized['bracketed'].sum()),
                         normalized_frequency_time_cells=int(np.isfinite(normalized['survival']).sum()),
                         normalization_scope='Periodic references interpolated in actual time within a batch; drift-flagged/low-contrast/unbracketed cells masked; raw IQ retained',
                         interpretation='Single-delay survival, not fitted T1; equilibrium population is not determined',
                         automatic_switching_claim=False,timing_scope='Host block/receipt times; ordered sweeps have no individual hardware timestamps')
            fast.checkpoint(folder/'summary.json',summary)
            manifest['summary']=summary
    manifest.update(status='complete' if summary['reference_check']['valid'] else 'complete_reference_drift',current=None)
    fast.checkpoint(folder/'manifest.json',manifest)
    return summary


def plot_result(folder):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    folder=Path(folder)
    with np.load(folder/'normalized.npz') as z:
        h=z['mid_epoch'];f=z['frequency_ghz'];loss=1-z['survival']
    if len(h)<2:return
    h=(h-h[0])/3600
    fig,ax=plt.subplots(figsize=(8,7),layout='constrained')
    mesh=ax.pcolormesh(h,f,loss.T,shading='nearest',cmap='inferno',vmin=.17699115044247782,vmax=.6346153846153846,rasterized=True)
    ax.set(xlabel='Elapsed wall-clock time (h)',ylabel='Qubit frequency (GHz)',title='AlOx q3',ylim=(f.min(),f.max()),box_aspect=1)
    delay=json.loads((folder/'manifest.json').read_text())['plan']['delay_us']
    cb=fig.colorbar(mesh,ax=ax,extend='both');cb.set_label(f'{delay:g} µs normalized loss (1 − S)')
    fig.savefig(folder/'single_point_map.png',dpi=200);plt.close(fig)


def run(*,data_root=None,correction_json=None,progress=True,frames=FRAMES,shots=SHOTS,
        reference_every=REFERENCE_EVERY,delay_us=25.,center_ghz=3.970,width_mhz=50,step_mhz=.5,
        readout_gain=940,continuous=False,reference_shots=None):
    requested=plan(frames=frames,shots=shots,reference_every=reference_every,delay_us=delay_us,
                   center_ghz=center_ghz,width_mhz=width_mhz,step_mhz=step_mhz,readout_gain=readout_gain,continuous=continuous,
                   reference_shots=reference_shots)
    from tqdm import tqdm
    from . import tls_fast_support as noise, tls_fast_support as localizer
    from . import FivePointApplesToApples as five,TLSSpectroscopy as tls,ThreePointApplesToApples as three
    from ..active_reset_OPX import production,integration,programs,classifier,acquisition
    root=Path(data_root or localizer.DATA_ROOT);correction=localizer.checked_correction(root,correction_json)
    folder=root/'q3'/('q3_fast_single_point_map_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]);folder.mkdir(parents=True,exist_ok=False)
    sources={}
    for source in [Path(__file__),*(Path(m.__file__) for m in [fast,programs,production,integration,classifier,acquisition])]:
        shutil.copyfile(source,folder/source.name);sources[source.name]=hashlib.sha256(source.read_bytes()).hexdigest()
    shutil.copyfile(correction,folder/'correction.json')
    manifest=dict(schema='q3.fast-single-point-map.v1',status='initializing',plan=requested,completed=[],current=None,
                  created_at=datetime.now(timezone.utc).isoformat(),sources=sources,
                  correction_sha256=hashlib.sha256(correction.read_bytes()).hexdigest(),
                  commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=Path(__file__).parent,text=True).strip())
    fast.checkpoint(folder/'manifest.json',manifest);soc=None;bar=None
    try:
        with noise.q3_context(tls,root),localizer.scan_environment(correction):
            tls.BaseConfig=fast.readout_base_config(tls.BaseConfig,readout_gain)
            five.install_scan_calibration(tls)
            compensation=tls._load_correction(str(correction),str(root))
            soc,soccfg=tls.makeProxy();fast.checkpoint(folder/'board_configuration.json',soccfg.get_cfg())
            print(f'SS cal: q3 active-reset calibration (readout gain {readout_gain})',flush=True)
            session=production.prepare_reset_session('active',outer_folder=str(folder),qubit='q3',base_cfg=tls.BaseConfig,soc=soc,soccfg=soccfg,purpose='TLSFastSinglePointMap')
            base=fast.science_config(tls,compensation,session);fast.checkpoint(folder/'config.json',base)
            manifest['reset_calibration']=str(session.calibration_output);bundle=integration.runtime_bundle(base);Program=make_program_class()
            bar=tqdm(total=frames+requested['reference_blocks_per_batch'],desc='1pt loss maps',unit='map',disable=not progress,
                     bar_format='{desc}: {n_fmt}/{total_fmt} [{elapsed} elapsed, ETA {remaining}]')
            def acquire(grid,count,name,kind):
                began=time.perf_counter()
                with (folder/'compile.log').open('a',encoding='utf-8') as log,redirect_stdout(log):
                    gains,realized=three._integer_dc_grid(dict(five.P6_5PT_APPLES_TO_APPLES,dc_min=-25146,freq_step_mhz=step_mhz),grid,tls)
                    cfg=block_config(base,gains.tolist(),count,kind=kind,delay_us=delay_us)
                    program=Program(soccfg,cfg,bundle.payload,bundle.loop);check=noise.preflight(program)
                compile_s=time.perf_counter()-began
                fast.checkpoint(folder/(name+'_config.json'),dict(config=program.cfg,preflight=check,stream_plan=program.stream_plan))
                epoch=time.time();mono=time.perf_counter();conditions=3 if kind=='reference' else 1
                def process(records):
                    finished=time.perf_counter();finished_epoch=time.time()
                    i,q=canonical_iq(records,shots=count,points=len(grid),conditions=conditions)
                    cycles=int(program.us2cycles(cfg['read_length'],ro_ch=cfg['ro_chs'][0]))
                    states=integration.classify_payload_iq(cfg,i/cycles,q/cycles,cycles)
                    x=dict(i=i,q=q,states=states,frequency_ghz=grid,realized_frequency_ghz=realized,dc_gains=gains,
                           started_epoch_s=epoch,finished_epoch_s=finished_epoch,started_monotonic_s=mono,finished_monotonic_s=finished,
                           compile_s=compile_s,transfers=program.transfer_receipts,
                           telemetry=dict(reset_mode=base['reset_mode'],read_length_cycles=cycles,stream_plan=program.stream_plan,config_file=name+'_config.json'))
                    save_block(folder,name,x,kind=kind,delay_us=delay_us);return x
                return fast.acquire_records(soc,program,cfg,count,count*len(grid)*conditions,folder,name,process=process)
            collect(folder,acquire,manifest,frames=frames,shots=shots,reference_every=reference_every,delay_us=delay_us,
                    center_ghz=center_ghz,width_mhz=width_mhz,step_mhz=step_mhz,update=lambda:bar.update(1),acquire_saves_block=True,
                    reference_shots=reference_shots)
            plot_result(folder)
    except KeyboardInterrupt:manifest.update(status='interrupted',error='KeyboardInterrupt')
    except ValueError as exc:manifest.update(status='unresolved',error=str(exc))
    except Exception as exc:manifest.update(status='failed',error=f'{type(exc).__name__}: {exc}')
    finally:
        if soc is not None and manifest['status'] not in ('complete','complete_reference_drift'):
            try:acquisition._safe_abort(soc)
            except Exception as exc:manifest['cleanup_error']=f'{type(exc).__name__}: {exc}'
        if bar is not None:bar.close()
        manifest['finished_at']=datetime.now(timezone.utc).isoformat();fast.checkpoint(folder/'manifest.json',manifest)
    print(f"1pt scan complete: {folder} ({manifest['status']})",flush=True)
    if manifest.get('error'):print(manifest['error'],flush=True)
    return folder


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--plan',action='store_true');mode.add_argument('--run',action='store_true')
    parser.add_argument('--loop',action='store_true');parser.add_argument('--quiet',action='store_true')
    parser.add_argument('--data-root',type=Path);parser.add_argument('--correction-json',type=Path)
    parser.add_argument('--frames',type=int,default=FRAMES);parser.add_argument('--shots',type=int,default=SHOTS)
    parser.add_argument('--reference-every',type=int,default=REFERENCE_EVERY)
    parser.add_argument('--reference-shots',type=int,default=None,
                        help='Shots per periodic reference condition; defaults to science shots. Endpoints remain 250.')
    parser.add_argument('--delay-us',type=float,default=25.)
    parser.add_argument('--center-ghz',type=float,default=3.970);parser.add_argument('--width-mhz',type=int,default=50)
    parser.add_argument('--step-mhz',type=float,choices=(.5,1.,2.),default=.5)
    parser.add_argument('--readout-gain',type=int,choices=(940,1880),default=940)
    args=parser.parse_args(argv)
    options=dict(frames=args.frames,shots=args.shots,reference_every=args.reference_every,delay_us=args.delay_us,
                 center_ghz=args.center_ghz,width_mhz=args.width_mhz,step_mhz=args.step_mhz,
                 readout_gain=args.readout_gain,continuous=args.loop,reference_shots=args.reference_shots)
    try:requested=plan(**options)
    except ValueError as exc:parser.error(str(exc))
    if args.plan:print(json.dumps(requested,indent=2));return 0
    def once():return run(data_root=args.data_root,correction_json=args.correction_json,progress=not args.quiet,**options)
    if args.loop:return fast.repeat_runs(once)
    folder=once();status=json.loads((folder/'manifest.json').read_text())['status']
    return 0 if status=='complete' else 130 if status=='interrupted' else 1


if __name__=='__main__':raise SystemExit(main())
