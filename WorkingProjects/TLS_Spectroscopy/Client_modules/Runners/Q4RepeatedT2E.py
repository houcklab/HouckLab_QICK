"""Repeated fixed-frequency q4 Hahn echo; --forever stops with Ctrl+C.

71 logarithmic free-evolution delays, two analysis phases, 500 shots per phase.
Uses the q4 T1 settings, waveform reuse and active-reset calibration. Every
curve saves phase-resolved raw IQ and an exponential echo-contrast fit.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil
import subprocess
import time
import uuid

import numpy as np
from . import Q4RepeatedT1 as t1

SHOTS_PER_PHASE = 500
POINTS_PER_PROGRAM = 16


def delays_us(max_delay_us=1000.):
    return t1.delays_us(max_delay_us)


def delay_chunks(delays):
    return [np.asarray(delays)[k:k+POINTS_PER_PROGRAM]
            for k in range(0,len(delays),POINTS_PER_PROGRAM)]


def plan(*, max_delay_us=1000., hours=12., max_runs=None):
    if hours is not None and (not math.isfinite(hours) or hours <= 0):
        raise ValueError('hours must be positive and finite, or None')
    if max_runs is not None and (not isinstance(max_runs,int) or max_runs <= 0):
        raise ValueError('max_runs must be a positive integer')
    return dict(qubit='q4', sequence='X(pi/2)-tau/2-Y(pi)-tau/2-+/-X(pi/2)',
        max_delay_us=max_delay_us, delays_us=delays_us(max_delay_us).tolist(),
        delay_definition='sum of the two free gaps; finite pulse durations excluded',
        delay_points=71, shots_per_phase=SHOTS_PER_PHASE, shots_per_delay=2*SHOTS_PER_PHASE,
        records_per_curve=71*2*SHOTS_PER_PHASE, analysis_phases_deg=[0,180],
        hours=hours, max_runs=max_runs, recalibration_minutes=30,
        reset_mode='opx_unbounded', flux_gain=0, qubit_frequency_mhz=4367.760,
        readout_frequency_mhz=7026.520, pi_gain=32000, pi2_gain=16000, sigma_us=2.,
        fit='signed phase contrast, offset + amplitude * exp(-free_delay/T2E)',
        echo_signal_check='stop if first curve has no detectable echo, or three subsequent curves lose contrast')


def measurement_config(calibration):
    cfg = t1.measurement_config(calibration)
    cfg.update(shots=SHOTS_PER_PHASE, reps=SHOTS_PER_PHASE)
    return cfg


def contrast_statistics(classified):
    a = np.asarray(classified, dtype=float)
    if a.ndim != 3 or a.shape[1] != 2 or a.shape[2] < 2 or not np.all(np.isfinite(a)):
        raise ValueError('expected finite delay x two phases x shots')
    difference = a[:,0,:]-a[:,1,:]
    return difference.mean(axis=1), difference.std(axis=1,ddof=1)/np.sqrt(a.shape[2])


def fit_echo(delays, contrast, errors):
    from scipy.optimize import curve_fit
    t,y,se = [np.asarray(v,dtype=float) for v in (delays,contrast,errors)]
    result = dict(fit_valid=False, signal_valid=False, T2E_us=None, T2E_err_us=None)
    if t.ndim != 1 or t.shape != y.shape or t.shape != se.shape or len(t)<5:
        return dict(result,reason='invalid echo arrays')
    if not all(np.all(np.isfinite(v)) for v in (t,y,se)):
        return dict(result,reason='nonfinite echo data')
    short = float(np.mean(y[:5])); short_se = float(np.sqrt(np.sum(se[:5]**2))/5)
    result.update(short_contrast=short, short_contrast_se=short_se,
                  signal_valid=bool(short > max(.10,5*short_se)))
    sigma = np.maximum(se, 1/SHOTS_PER_PHASE)
    try:
        popt,cov = curve_fit(lambda x,c,a,tau:c+a*np.exp(-x/tau),t,y,
            p0=[float(np.clip(y[-5:].mean(),-.5,.5)), max(.05,short-y[-5:].mean()),float(t[-1]/3)],
            bounds=([-1.,0.,.05],[1.,2.,100*t[-1]]),sigma=sigma,absolute_sigma=True,maxfev=20000)
        c,a,tau = map(float,popt); err=float(np.sqrt(cov[2,2]))
        reduced=float(np.sum(((y-(c+a*np.exp(-t/tau)))/sigma)**2)/(len(t)-3))
        valid=bool(result['signal_valid'] and np.isfinite(err) and err/tau < .5
                   and tau<5*t[-1] and reduced<=5)
        result.update(fit_valid=valid,T2E_us=tau if valid else None,T2E_err_us=err if valid else None,
                      offset=c,amplitude=a,tau_fit_us=tau,tau_fit_err_us=err,reduced_chi2=reduced)
    except (RuntimeError,ValueError,FloatingPointError) as exc:
        result['reason']=str(exc)
    return result


SUMMARY_FIELDS=('index','started_at','elapsed_s','duration_s','calibration_id',
                'T2E_us','T2E_err_us','fit_valid','signal_valid','short_contrast',
                'reduced_chi2','raw_file')


def collect_runs(output, *, hours, calibrate, measure, max_runs=None,
                 max_delay_us=1000., clock=time.monotonic):
    protocol=plan(max_delay_us=max_delay_us,hours=hours,max_runs=max_runs)
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    started=clock(); deadline=math.inf if hours is None else started+hours*3600
    manifest=dict(protocol,started_at=datetime.now(timezone.utc).isoformat(),status='running',runs=[])
    path=output/'manifest.json'
    t1.save_json(path,manifest)
    calibration=None; calibrated_at=-math.inf; calibration_id=0; weak_curves=0
    try:
        with (output/'t2e_summary.csv').open('x',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=SUMMARY_FIELDS,extrasaction='ignore')
            writer.writeheader(); stream.flush()
            while clock()<deadline and (max_runs is None or len(manifest['runs'])<max_runs):
                index=len(manifest['runs'])+1
                manifest['current_run']=index
                if calibration is None or clock()-calibrated_at>=1800:
                    manifest['stage']='calibration'; t1.save_json(path,manifest)
                    calibration_id+=1; calibration=calibrate(calibration_id); calibrated_at=clock()
                if clock()>=deadline: break
                manifest['stage']='T2E';t1.save_json(path,manifest)
                result=measure(index,calibration)
                result.update(calibration_id=calibration_id,elapsed_s=clock()-started)
                writer.writerow(result);stream.flush()
                manifest['runs'].append(result);t1.save_json(path,manifest)
                weak_curves=0 if result['signal_valid'] else weak_curves+1
                if (index==1 and weak_curves) or weak_curves>=3:
                    raise RuntimeError('insufficient echo contrast; completed curves saved; check q4 pulse calibration')
        manifest.update(status='complete',stage='complete',current_run=None)
    except BaseException as exc:
        manifest.update(status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',
                        error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        manifest.update(elapsed_s=clock()-started,completed_at=datetime.now(timezone.utc).isoformat())
        t1.save_json(path,manifest)
    return manifest


def measure_curve(soc,soccfg,output,index,calibration,*,progress=True,max_delay_us=1000.):
    from tqdm import tqdm
    import matplotlib.pyplot as plt
    from .Q4RepeatedT2EProgram import Q4EchoSweepProgram
    from ..active_reset_OPX.integration import runtime_bundle,classify_payload_iq
    started=time.monotonic();started_at=datetime.now(timezone.utc).isoformat()
    stem=Path(output)/f'run_{index:06d}'
    cfg=measurement_config(calibration['bundle']); bundle=runtime_bundle(cfg)
    delays=delays_us(max_delay_us)
    t1.save_json(stem.with_suffix('.config.json'),cfg)
    programs=[];preflight=[]
    for group in delay_chunks(delays):
        p=Q4EchoSweepProgram(soccfg,dict(cfg,opx_t1_shots=SHOTS_PER_PHASE,
            opx_t1_delays_us=np.repeat(group,2).tolist(),opx_resident_dmem_stream=True),bundle.payload,bundle.loop)
        words=len(p.compile());capacity=int(soccfg['tprocs'][0]['pmem_size'])
        if words>capacity: raise RuntimeError(f'echo program needs {words}/{capacity} instructions')
        preflight.append(dict(instructions=words,capacity=capacity,echo_timing=p.echo_timing,
                              waveform_memory=t1.validate_waveform_memory(p)))
        programs.append(p)
    t1.save_json(stem.with_suffix('.preflight.json'),preflight)
    i=np.full((71,2,SHOTS_PER_PHASE),np.nan);q=i.copy(); realized=np.full(71,np.nan)
    offset=0;telemetry=[]
    with tqdm(total=71000,desc=f'T2E {index}',unit='shot',disable=not progress,
              bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed} elapsed, ETA {remaining}]') as bar:
        for block,p in enumerate(programs):
            n=len(p.cfg['opx_t1_delays_us'])//2
            def update(done,total): bar.update(offset*1000+int(done)*n*2-bar.n)
            try:
                iv,qv,meta=t1.acquire_curve_iq(soc,p,cfg,update)
                if iv.shape!=(2*n,SHOTS_PER_PHASE) or qv.shape!=iv.shape:
                    raise RuntimeError('incomplete echo IQ block')
                i[offset:offset+n]=iv.reshape(n,2,SHOTS_PER_PHASE)
                q[offset:offset+n]=qv.reshape(n,2,SHOTS_PER_PHASE)
                realized[offset:offset+n]=[v['free_us'] for v in p.echo_timing[::2]]
                telemetry.append(meta);offset+=n
                np.savez_compressed(stem.with_suffix('.partial.npz'),requested_delays_us=delays,
                                    delays_us=realized,i=i,q=q,completed_delay_points=offset)
            except BaseException as exc:
                partial=getattr(exc,'partial_records',None) or []
                np.savez_compressed(stem.with_suffix('.partial.npz'),requested_delays_us=delays,
                    delays_us=realized,i=i,q=q,completed_delay_points=offset,inflight_block=block,
                    inflight_raw_i=[r.final_i for r in partial],inflight_raw_q=[r.final_q for r in partial])
                raise
    np.savez_compressed(stem.with_suffix('.npz'),requested_delays_us=delays,delays_us=realized,
                        analysis_phases_deg=[0,180],i=i,q=q)
    stem.with_suffix('.partial.npz').unlink()
    t1.save_json(stem.with_suffix('.telemetry.json'),telemetry)
    classified=classify_payload_iq(cfg,i,q,telemetry[0]['read_length_cycles'])
    contrast,se=contrast_statistics(classified)
    fit=fit_echo(realized,contrast,se)
    result=dict(index=index,started_at=started_at,duration_s=time.monotonic()-started,
                raw_file=str(stem.with_suffix('.npz')),calibration_file=calibration['file'],
                delays_us=realized.tolist(),phase_populations=np.mean(classified,axis=2).tolist(),
                contrast=contrast.tolist(),contrast_se=se.tolist(),**fit)
    t1.save_json(stem.with_suffix('.json'),result)
    fig,axs=plt.subplots(1,2,figsize=(10,3.6),layout='constrained')
    for k,phase in enumerate((0,180)):
        axs[0].plot(realized,np.mean(classified[:,k,:],axis=1),'.-',ms=3,label=f'Final phase {phase}°')
    axs[0].set(ylabel='Classified excited fraction');axs[0].legend(fontsize=8)
    axs[1].errorbar(realized,contrast,yerr=se,fmt='.',capsize=2)
    if 'tau_fit_us' in fit:
        x=np.geomspace(realized[0],realized[-1],400)
        axs[1].plot(x,fit['offset']+fit['amplitude']*np.exp(-x/fit['tau_fit_us']))
    axs[1].set(ylabel='Echo contrast: P(0°) − P(180°)')
    for ax in axs:
        ax.set(xscale='log',xlabel='Total free-evolution delay (µs)');ax.grid(alpha=.2)
    title=(f"q4 T2E = {fit['T2E_us']:.1f} ± {fit['T2E_err_us']:.1f} µs"
           if fit['fit_valid'] else 'q4 T2E: unresolved fit; raw data saved')
    fig.suptitle(title);fig.savefig(stem.with_suffix('.png'),dpi=150);plt.close(fig)
    print(f'T2E {index}: '+(f"{fit['T2E_us']:.2f} +/- {fit['T2E_err_us']:.2f} us" if fit['fit_valid'] else 'unresolved fit; raw data saved'),flush=True)
    return result


def run(*,data_root=t1.DATA_ROOT,hours=12.,max_runs=None,progress=True,max_delay_us=1000.):
    protocol=plan(max_delay_us=max_delay_us,hours=hours,max_runs=max_runs)
    output=Path(data_root)/'q4'/('q4_repeated_t2e_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    output.mkdir(parents=True)
    t1.snapshot_initialize(output/'initialize_snapshot')
    for name in ('Q4RepeatedT2E.py','Q4RepeatedT2EProgram.py','Q4RepeatedT1.py'):
        shutil.copyfile(Path(__file__).with_name(name),output/name)
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=Path(__file__).parent,text=True).strip()
    t1.save_json(output/'plan.json',dict(protocol,commit=revision))
    t1.save_json(output/'requested_config.json',t1.base_config())
    print(f'q4 repeated T2E: {output}',flush=True)
    import matplotlib
    matplotlib.use('Agg')
    from ..CoreLib.socProxy import makeProxy
    from ..active_reset_OPX.acquisition import _safe_abort
    soc,soccfg=makeProxy()
    try:
        t1.save_json(output/'board_configuration.json',soccfg.get_cfg())
        collect_runs(output,hours=hours,max_runs=max_runs,max_delay_us=max_delay_us,
            calibrate=lambda n:t1.calibrate_reset(soc,soccfg,output,n,purpose='Q4RepeatedT2E'),
            measure=lambda n,c:measure_curve(soc,soccfg,output,n,c,progress=progress,max_delay_us=max_delay_us))
    finally:
        _safe_abort(soc)
    return output


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',action='store_true');p.add_argument('--plan',action='store_true')
    duration=p.add_mutually_exclusive_group()
    duration.add_argument('--hours',type=float,default=12.)
    duration.add_argument('--forever',dest='hours',action='store_const',const=None)
    p.add_argument('--max-runs',type=int);p.add_argument('--max-delay-us',type=float,default=1000.)
    p.add_argument('--data-root',default=t1.DATA_ROOT);p.add_argument('--quiet',action='store_true')
    a=p.parse_args(argv)
    if a.run and not a.plan:
        run(data_root=a.data_root,hours=a.hours,max_runs=a.max_runs,progress=not a.quiet,max_delay_us=a.max_delay_us)
    else: print(json.dumps(plan(hours=a.hours,max_runs=a.max_runs,max_delay_us=a.max_delay_us),indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
