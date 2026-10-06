"""q3 fast loss maps using production active-reset timing.

One optional 3.8--4.3 GHz scout, one local window, a finite number of low-shot
five-condition frames, and high-shot local references before/after. Optional
--loop repeats these finite batches with fresh calibration until interrupted.
Readout gain defaults to 1880; --readout-gain 940 is an explicit experimental
override applied to both fresh calibration and science readouts.
No adaptive FPGA
estimator, passive fallback, target microwave pulses, or production edits.
"""
import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

import numpy as np

from .tls_fast_support import checkpoint

DELAYS_US = (2., 10., 25.)
REFERENCE_US = .1
SCOUT_SHOTS, FRAME_SHOTS, FRAMES = 250, 40, 40


def atomic_npz(path, **arrays):
    path=Path(path)
    pending=path.with_suffix(path.suffix+'.pending')
    with pending.open('wb') as stream:
        np.savez_compressed(stream,**arrays)
    os.replace(pending,path)


def readout_base_config(base_cfg,readout_gain):
    if (isinstance(readout_gain,bool) or not isinstance(readout_gain,(int,np.integer))
            or readout_gain not in (940,1880)):
        raise ValueError('readout gain must be 940 or 1880')
    return dict(base_cfg,read_pulse_gain=int(readout_gain))


def plan(*,frames=FRAMES,center_ghz=None,width_mhz=20,step_mhz=1.,continuous=False,readout_gain=1880):
    readout_gain=readout_base_config({},readout_gain)['read_pulse_gain']
    if not isinstance(frames,int) or not 1<=frames<=2000:
        raise ValueError('frames must be an integer between 1 and 2000')
    if continuous and center_ghz is None:
        raise ValueError('loop mode requires an explicit center-ghz; no repeated discovery gate')
    grid=local_grid(4.05 if center_ghz is None else center_ghz,width_mhz=width_mhz,step_mhz=step_mhz)
    period=.3+6.48*len(grid)/251
    return dict(qubit='q3', reset='production active-reset timing throughout',
                readout_gain=readout_gain,readout_gain_override=readout_gain!=1880,
                readout_gain_scope='same gain for fresh reset calibration and all science readouts',
                scout_ghz=[3.8, 4.3] if center_ghz is None else None,
                scout_step_mhz=2. if center_ghz is None else None,
                scout_shots=SCOUT_SHOTS if center_ghz is None else 0,
                window_center_ghz=center_ghz,
                window_selection='fresh wide scout' if center_ghz is None else 'explicit window; no scout or fresh-feature claim',
                local_width_mhz=width_mhz, local_step_mhz=step_mhz, local_points=len(grid),
                frames=frames, shots_per_condition_per_frame=FRAME_SHOTS,
                repeat_batches=bool(continuous),total_frame_limit=None if continuous else frames,
                batch_calibration='fresh production active-reset calibration before every batch',
                loop_stop_policy='Ctrl+C or any acquisition/calibration error; retain and flag reference drift',
                conditions=['P0', 'P1', 'Ps_2us', 'Ps_10us', 'Ps_25us'],
                reference_hold_us=REFERENCE_US, full_corrected_return_us=5.,
                local_pre_post_shots=SCOUT_SHOTS,
                timing='per-frame wall time and monotonic time, per-transfer host receipt time; no individual hardware timestamps',
                estimated_frame_period_s=[period,1.3*period],
                approximate_minutes=f'{.5+(frames+12.5)*period/60:.1f}--{2+(frames+12.5)*period*1.3/60:.1f} per batch; extrapolated from 251-point hardware timing, including reference maps; actual cadence is measured',
                interpretation='finite cadence and line-contrast pilot; no automatic switching or intrinsic-linewidth claim')


def canonical_iq(records, *, shots, points):
    if len(records) != shots*points*5:
        raise ValueError('incomplete five-condition acquisition')
    i=np.asarray([r.final_i for r in records],dtype=np.int64).reshape(shots,points,5)
    q=np.asarray([r.final_q for r in records],dtype=np.int64).reshape(shots,points,5)
    i[1::2]=i[1::2,::-1]
    q[1::2]=q[1::2,::-1]
    return i.transpose(2,1,0),q.transpose(2,1,0)


def local_grid(center,*,width_mhz=20,step_mhz=1.):
    center=float(center)
    if not np.isfinite(center) or not 3.8<=center<=4.3:
        raise ValueError('local center outside the calibrated band')
    if (not isinstance(width_mhz,int) or not 2<=width_mhz<=500
            or step_mhz not in (.5,1.,2.) or width_mhz/step_mhz!=int(width_mhz/step_mhz)):
        raise ValueError('local grid requires integer width 2--500 MHz, step 0.5/1/2 MHz, and an integer number of intervals')
    if width_mhz/step_mhz+1>801:
        raise ValueError('local grid exceeds the validated 801-point limit; use a larger step or smaller width')
    lower=max(3.8,min(4.3-width_mhz/1000,center-width_mhz/2000))
    return np.round(lower+step_mhz/1000*np.arange(int(width_mhz/step_mhz)+1),6)


def select_feature(block):
    """Rank bilateral troughs with a conservative shot-noise/search guard.

    Propagate the paired binary shots through the reference normalization;
    retain covariance between conditions and frequencies in each scan shot.
    This gate chooses a pilot window, not a significance claim about a TLS.
    """
    f=np.asarray(block['frequency_ghz'])
    states=np.asarray(block['states'])
    candidates=[]
    for j in range(5,len(f)-5):
        depth={}; scores={}; errors={}
        for label,part in [('all',slice(None)),('forward',slice(None,None,2)),('reverse',slice(1,None,2))]:
            shots=states[...,part]
            p=shots.mean(axis=-1)
            contrast=p[1]-p[0]
            idx=np.r_[j-5:j-2,j-1:j+2,j+3:j+6]
            if np.min(contrast[idx])<.2:
                break
            survival=(p[4]-p[0])/np.maximum(contrast,1e-9)
            influence=((survival-1)[:,None]*(shots[0]-p[0,:,None])
                       -survival[:,None]*(shots[1]-p[1,:,None])
                       +(shots[4]-p[4,:,None]))/np.maximum(contrast[:,None],1e-9)
            center=float(np.mean(survival[j-1:j+2]))
            sides=[];side_scores=[];side_errors=[]
            for flank in (slice(j-5,j-2),slice(j+3,j+6)):
                difference=float(survival[flank].mean()-center)
                paired=influence[flank].mean(axis=0)-influence[j-1:j+2].mean(axis=0)
                se=float(paired.std(ddof=1)/np.sqrt(shots.shape[-1]))
                sides.append(difference);side_errors.append(se)
                side_scores.append(difference/max(se,1e-9))
            depth[label]=min(sides); scores[label]=min(side_scores);errors[label]=side_errors
        if (len(depth)==3 and depth['all']>=.12 and scores['all']>=4.5
                and min(depth['forward'],depth['reverse'])>=.06
                and min(scores['forward'],scores['reverse'])>=2.):
            candidates.append(dict(center_ghz=float(f[j]),depth=depth,shot_noise_scores=scores,
                flank_difference_se=errors,selection_scope='conservative pilot-window gate; no formal TLS significance claim'))
    if not candidates:
        raise ValueError('no resolved bidirectional loss trough in the scout')
    return max(candidates,key=lambda r:r['depth']['all'])


def reference_check(pre,post):
    rows=[]
    for condition in (0,1):
        a=np.asarray(pre['states'])[condition].ravel()
        b=np.asarray(post['states'])[condition].ravel()
        delta=float(b.mean()-a.mean())
        se=float(np.sqrt(a.var(ddof=1)/a.size+b.var(ddof=1)/b.size))
        rows.append(dict(condition=('P0','P1')[condition],before=float(a.mean()),after=float(b.mean()),
                         delta=delta,se=se,valid=bool(abs(delta)<=.05+3*se)))
    contrasts=[float((np.asarray(x['states'])[1]-np.asarray(x['states'])[0]).mean()) for x in (pre,post)]
    return dict(valid=all(r['valid'] for r in rows) and min(contrasts)>=.2,
                reference_contrasts=contrasts,conditions=rows,
                scope='pooled preparation/readout-reference drift check; not proof of per-frequency or sub-frame stability')


def save_block(folder,name,block):
    states=np.asarray(block['states'])
    if states.ndim!=3 or states.shape[0]!=5 or states.shape[1]!=len(block['frequency_ghz']):
        raise ValueError('malformed five-condition raw block')
    if np.shape(block['i'])!=states.shape or np.shape(block['q'])!=states.shape or not np.all(np.isfinite(block['i'])) or not np.all(np.isfinite(block['q'])):
        raise ValueError('incomplete or nonfinite raw IQ')
    if not all(np.issubdtype(np.asarray(block[k]).dtype,np.integer) for k in ('i','q')):
        raise ValueError('raw integrated IQ must have integer dtype')
    atomic_npz(Path(folder)/(name+'.npz'),i=block['i'],q=block['q'],states=states,
                        frequency_ghz=block['frequency_ghz'],realized_frequency_ghz=block['realized_frequency_ghz'],
                        dc_gains=block['dc_gains'],shot_scan_direction=np.where(np.arange(states.shape[2])%2==0,1,-1))
    metadata={k:v for k,v in block.items() if k not in ('i','q','states')}
    metadata['array_order']='condition, canonical frequency, shot; raw integer integrated IQ'
    metadata['condition_order']=['P0','P1','Ps_2us','Ps_10us','Ps_25us']
    metadata['shot_order']='even shots follow stored frequency order; odd shots reverse frequency order; condition order fixed'
    metadata['pooled_reference_probabilities']=states[:2].mean(axis=(1,2)).tolist()
    checkpoint(Path(folder)/(name+'.json'),metadata)


def collect(folder,acquire,manifest,*,frames=FRAMES,update=None,acquire_saves_block=False,
            center_ghz=None,width_mhz=20,step_mhz=1.):
    folder=Path(folder)
    def measure(grid,shots,name):
        manifest.update(status='acquiring',current=name)
        checkpoint(folder/'manifest.json',manifest)
        result=acquire(grid,shots,name)
        if not acquire_saves_block:save_block(folder,name,result)
        manifest['completed'].append(name)
        checkpoint(folder/'manifest.json',manifest)
        if update:update()
        return result
    if center_ghz is None:
        scout=measure(np.round(np.arange(3800,4301,2)/1000,6),SCOUT_SHOTS,'scout')
        selected=select_feature(scout)
    else:
        # Validate before acquiring; a chosen window is not a detected feature.
        local_grid(center_ghz,width_mhz=width_mhz,step_mhz=step_mhz)
        selected=dict(center_ghz=float(center_ghz),mode='explicit_window',fresh_feature_claim=False,
                      selection_scope='requested model-frequency window; record even if loss weakens or leaves it')
    manifest['selection']=selected
    grid=local_grid(selected['center_ghz'],width_mhz=width_mhz,step_mhz=step_mhz)
    pre=measure(grid,SCOUT_SHOTS,'local_pre')
    rows=[]
    for n in range(frames):
        b=measure(grid,FRAME_SHOTS,f'frame_{n:04d}')
        rows.append(dict(index=n,started_epoch_s=b['started_epoch_s'],finished_epoch_s=b['finished_epoch_s'],
                         start=b['started_monotonic_s'],end=b['finished_monotonic_s'],compile_s=b['compile_s']))
    post=measure(grid,SCOUT_SHOTS,'local_post')
    durations=np.array([b['end']-b['start'] for b in rows])
    periods=np.diff([b['start'] for b in rows])
    def stats(x):
        return dict(median=float(np.median(x)),min=float(np.min(x)),max=float(np.max(x))) if len(x) else None
    refs=reference_check(pre,post)
    summary=dict(frames=rows,frame_acquisition_s=stats(durations),frame_start_period_s=stats(periods),
                 reference_check=refs,automatic_switching_claim=False,
                 timing_scope='frame acquisition includes hardware configuration/transport; start-to-start also includes analysis, recompilation and NAS checkpoint gaps')
    checkpoint(folder/'summary.json',summary)
    manifest.update(status='complete' if refs['valid'] else 'complete_reference_drift',current=None,summary=summary)
    checkpoint(folder/'manifest.json',manifest)
    return summary


def make_program_class():
    from ..active_reset_OPX.programs import OPXResetT15PointProgram
    class FastT1Program(OPXResetT15PointProgram):
        """Production instructions unchanged; only observe decoded bank receipt."""
        def __init__(self,*args,**kwargs):
            self.transferred_records=[]
            self.transfer_receipts=[]
            super().__init__(*args,**kwargs)
        def decode_dmem_records(self,words,expected_records=None):
            records=super().decode_dmem_records(words,expected_records)
            self.transferred_records.extend(records)
            self.transfer_receipts.append(dict(records_received=len(self.transferred_records),
                host_epoch_s=time.time(),host_monotonic_s=time.perf_counter()))
            return records
    return FastT1Program


def acquire_records(soc,program,cfg,shots,total_records,folder,name,*,process=None):
    """Keep interruption protection through processing and block publication."""
    from ..active_reset_OPX.integration import _run_program,_block_timeout_s
    from ..active_reset_OPX.acquisition import _safe_abort
    started=time.time()
    try:
        records=_run_program(soc,program,_block_timeout_s(cfg,total_records),cfg,total_shots=shots)
        return process(records) if process is not None else records
    except BaseException:
        cleanup_error=None
        try:
            _safe_abort(soc)
        except Exception as exc:
            cleanup_error=f'{type(exc).__name__}: {exc}'
        records=program.transferred_records
        atomic_npz(Path(folder)/(name+'.partial.npz'),
            i_acquisition_order=np.asarray([r.final_i for r in records],dtype=np.int64),
            q_acquisition_order=np.asarray([r.final_q for r in records],dtype=np.int64))
        checkpoint(Path(folder)/(name+'.partial.json'),dict(transfers=program.transfer_receipts,
            started_epoch_s=started,finished_epoch_s=time.time(),
            cleanup_error=cleanup_error,error='acquisition interrupted or failed'))
        raise


def science_config(tls,compensation,session):
    from . import FivePointApplesToApples as five
    base=dict(tls.BaseConfig)
    base.update(shots=FRAME_SHOTS,apply_flux_tail_compensation=True,
                flux_tail_compensation=compensation,flux_fit_params=tls.FLUX_FIT_PARAMS,
                qubit_pulse_style='arb',flux_settle_time_us=.5,
                flux_predistortion_return_prefix_us=5.,flux_predistortion_recovery_us=5.,
                flux_predistortion_overlap_payload_readout=False,flux_predistortion_timing_matched_off=False,
                readout_thermalization_us=10.,opx_t1_3pt_gain_lookup=True,
                opx_reverse_survival_order=False)
    base=session.apply(base)
    five.apply_verified_feedback_timing(base)
    if base['reset_mode']!='opx_unbounded':
        raise ValueError('fast loss pilot requires production active reset')
    return base


def plot_result(folder,summary):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    folder=Path(folder)
    with np.load(folder/'local_pre.npz') as a,np.load(folder/'local_post.npz') as b:
        p=(a['states'].mean(axis=-1)+b['states'].mean(axis=-1))/2
        f=a['realized_frequency_ghz']*1000
    contrast=p[1]-p[0]
    edges=np.r_[f[0]-(f[1]-f[0])/2,(f[:-1]+f[1:])/2,f[-1]+(f[-1]-f[-2])/2]
    polygons=[];values=[]
    origin=summary['frames'][0]['start']
    for row in summary['frames']:
        with np.load(folder/f"frame_{row['index']:04d}.npz") as z:
            survival=(z['states'][3].mean(axis=-1)-p[0])/np.maximum(contrast,.001)
        for j,y in enumerate(survival):
            polygons.append([(edges[j],row['start']-origin),(edges[j+1],row['start']-origin),
                             (edges[j+1],row['end']-origin),(edges[j],row['end']-origin)])
            values.append(y if contrast[j]>=.2 else np.nan)
    fig,ax=plt.subplots(figsize=(8,5),constrained_layout=True)
    collection=PolyCollection(polygons,array=np.asarray(values),cmap='viridis',edgecolors='none')
    collection.set_clim(0,1)
    ax.add_collection(collection);ax.autoscale_view()
    ax.set(xlabel='Realized model qubit frequency (MHz)',ylabel='Frame acquisition intervals, elapsed time (s)',
           title='q3 fast loss-map pilot — 10 µs normalized survival'+
           ('\nReference drift: interpretation unresolved' if not summary['reference_check']['valid'] else ''))
    fig.colorbar(collection,ax=ax,label='Survival / pooled pre–post reference contrast')
    for suffix in ('png','svg'):fig.savefig(folder/('fast_loss_map.'+suffix),dpi=180)
    plt.close(fig)


def run(*,data_root=None,correction_json=None,progress=True,frames=FRAMES,center_ghz=None,
        width_mhz=20,step_mhz=1.,continuous=False,readout_gain=1880):
    requested_plan=plan(frames=frames,center_ghz=center_ghz,width_mhz=width_mhz,step_mhz=step_mhz,
                        continuous=continuous,readout_gain=readout_gain)
    from tqdm import tqdm
    from . import tls_fast_support as noise, tls_fast_support as localizer
    from . import FivePointApplesToApples as five, TLSSpectroscopy as tls
    from . import ThreePointApplesToApples as three
    from ..active_reset_OPX.production import prepare_reset_session
    from ..active_reset_OPX.integration import runtime_bundle,classify_payload_iq
    data_root=Path(data_root or localizer.DATA_ROOT)
    correction=localizer.checked_correction(data_root,correction_json)
    folder=data_root/'q3'/('q3_fast_loss_map_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True,exist_ok=False)
    source=Path(__file__)
    shutil.copy2(source,folder/source.name);shutil.copy2(correction,folder/'correction.json')
    manifest=dict(schema='q3.fast-loss-map.v1',status='initializing',plan=requested_plan,completed=[],
                  created_at=datetime.now(timezone.utc).isoformat(),commit=subprocess.check_output(
                      ['git','rev-parse','HEAD'],cwd=source.parent,text=True).strip(),
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  correction_sha256=hashlib.sha256(correction.read_bytes()).hexdigest())
    checkpoint(folder/'manifest.json',manifest)
    bar=None
    soc=None
    try:
        with noise.q3_context(tls,data_root),localizer.scan_environment(correction):
            tls.BaseConfig=readout_base_config(tls.BaseConfig,readout_gain)
            five.install_scan_calibration(tls)
            compensation=tls._load_correction(str(correction),str(data_root))
            soc,soccfg=tls.makeProxy()
            checkpoint(folder/'board_configuration.json',soccfg.get_cfg())
            print(f'SS cal: q3 active-reset calibration (readout gain {readout_gain})',flush=True)
            session=prepare_reset_session('active',outer_folder=str(folder),qubit='q3',
                    base_cfg=tls.BaseConfig,soc=soc,soccfg=soccfg,purpose='TLSFastLossMap')
            base=science_config(tls,compensation,session)
            checkpoint(folder/'config.json',base)
            manifest['reset_calibration']=str(session.calibration_output)
            bundle=runtime_bundle(base)
            Program=make_program_class()
            bar=tqdm(total=frames+(3 if center_ghz is None else 2),desc='5pt loss maps',unit='map',disable=not progress,
                     bar_format='{desc}: {n_fmt}/{total_fmt} [{elapsed} elapsed, ETA {remaining}]')
            def acquire(grid,shots,name):
                compiled=time.perf_counter()
                with (folder/'compile.log').open('a',encoding='utf-8') as log,redirect_stdout(log):
                    gains,realized=three._integer_dc_grid(dict(five.P6_5PT_APPLES_TO_APPLES,
                        dc_min=-25146,freq_step_mhz=2. if name=='scout' else step_mhz),grid,tls)
                    cfg=dict(base,shots=shots,reps=shots,opx_reset_scheme='opx_unbounded',
                        opx_t1_3pt_shots=shots,opx_t1_3pt_dc_gains=gains.tolist(),
                        opx_t1_5pt_delays_us=list(DELAYS_US),opx_t1_5pt_reference_hold_us=REFERENCE_US,
                        ff_hold=REFERENCE_US+DELAYS_US[-1],t1_wait_us=REFERENCE_US+DELAYS_US[-1],
                        opx_resident_dmem_stream=True)
                    program=Program(soccfg,cfg,bundle.payload,bundle.loop)
                    check=noise.preflight(program)
                compile_s=time.perf_counter()-compiled
                checkpoint(folder/(name+'_config.json'),dict(config=program.cfg,preflight=check,stream_plan=program.stream_plan))
                started_epoch=time.time();started=time.perf_counter()
                def process(records):
                    finished=time.perf_counter();finished_epoch=time.time()
                    i,q=canonical_iq(records,shots=shots,points=len(grid))
                    cycles=int(program.us2cycles(cfg['read_length'],ro_ch=cfg['ro_chs'][0]))
                    states=classify_payload_iq(cfg,i/cycles,q/cycles,cycles)
                    block=dict(i=i,q=q,states=states,frequency_ghz=grid,realized_frequency_ghz=realized,
                        dc_gains=gains,started_epoch_s=started_epoch,finished_epoch_s=finished_epoch,
                        started_monotonic_s=started,finished_monotonic_s=finished,compile_s=compile_s,
                        transfers=program.transfer_receipts,telemetry=dict(reset_mode=base['reset_mode'],
                            read_length_cycles=cycles,stream_plan=program.stream_plan,config_file=name+'_config.json'))
                    save_block(folder,name,block)
                    return block
                return acquire_records(soc,program,cfg,shots,shots*len(grid)*5,folder,name,process=process)
            summary=collect(folder,acquire,manifest,frames=frames,update=lambda:bar.update(1),
                            acquire_saves_block=True,center_ghz=center_ghz,width_mhz=width_mhz,step_mhz=step_mhz)
            plot_result(folder,summary)
    except KeyboardInterrupt:
        manifest.update(status='interrupted',error='KeyboardInterrupt')
    except ValueError as exc:
        manifest.update(status='unresolved',error=str(exc))
    except Exception as exc:
        manifest.update(status='failed',error=f'{type(exc).__name__}: {exc}')
    finally:
        if soc is not None and manifest['status'] not in ('complete','complete_reference_drift'):
            from ..active_reset_OPX.acquisition import _safe_abort
            try:
                _safe_abort(soc)
            except Exception as exc:
                manifest['cleanup_error']=f'{type(exc).__name__}: {exc}'
        if bar is not None:bar.close()
        manifest['finished_at']=datetime.now(timezone.utc).isoformat()
        checkpoint(folder/'manifest.json',manifest)
    print(f"5pt scan complete: {folder} ({manifest['status']})",flush=True)
    if manifest.get('error'):print(manifest['error'],flush=True)
    return folder


def repeat_runs(run_once):
    """Repeat complete finite batches; never retry a failed acquisition."""
    try:
        while True:
            folder=Path(run_once())
            status=json.loads((folder/'manifest.json').read_text())['status']
            if status=='interrupted':return 130
            if status not in ('complete','complete_reference_drift'):return 1
    except KeyboardInterrupt:
        print('5pt scan interrupted between batches.',flush=True)
        return 130


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--plan',action='store_true');mode.add_argument('--run',action='store_true')
    parser.add_argument('--data-root',type=Path);parser.add_argument('--correction-json',type=Path)
    parser.add_argument('--quiet',action='store_true')
    parser.add_argument('--frames',type=int,default=FRAMES,help='frames per finite batch, 1--2000 (default: 40)')
    parser.add_argument('--loop',action='store_true',help='repeat finite batches with fresh calibration until Ctrl+C; requires center-ghz; stop on acquisition errors')
    parser.add_argument('--center-ghz',type=float,help='record explicit local window without a scout/feature-selection gate')
    parser.add_argument('--width-mhz',type=int,default=20,help='window width, 2--500 MHz, at most 801 points (default: 20)')
    parser.add_argument('--step-mhz',type=float,choices=(.5,1.,2.),default=1.,help='local grid spacing (default: 1 MHz)')
    parser.add_argument('--readout-gain',type=int,choices=(940,1880),default=1880,
                        help='reset and final readout gain; 940 is experimental (default: 1880)')
    args=parser.parse_args(argv)
    try:requested_plan=plan(frames=args.frames,center_ghz=args.center_ghz,width_mhz=args.width_mhz,
                            step_mhz=args.step_mhz,continuous=args.loop,readout_gain=args.readout_gain)
    except ValueError as exc:parser.error(str(exc))
    if args.plan:
        print(json.dumps(requested_plan,indent=2));return 0
    def run_once():
        return run(data_root=args.data_root,correction_json=args.correction_json,progress=not args.quiet,
                   frames=args.frames,center_ghz=args.center_ghz,width_mhz=args.width_mhz,
                   step_mhz=args.step_mhz,continuous=args.loop,readout_gain=args.readout_gain)
    if args.loop:return repeat_runs(run_once)
    folder=run_once()
    status=json.loads((folder/'manifest.json').read_text())['status']
    return 0 if status=='complete' else 1


if __name__=='__main__':raise SystemExit(main())
