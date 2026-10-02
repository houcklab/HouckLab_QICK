"""Finite q4 frequency and rotation diagnostic before repeated Hahn echo.

No initialization edits or automatic changes to the repeated echo runner.
"""
import argparse
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

SHOTS = 250
BLOCK_SIZE = 24
CENTER_MHZ = 4367.760


def spectroscopy_conditions():
    frequencies = CENTER_MHZ + np.linspace(-.25, .25, 51)
    frequencies = np.random.default_rng(421).permutation(frequencies)
    arms = [dict(kind='drive', frequency_mhz=float(f), gain=32000, count=1,
                 delay_us=.1) for f in frequencies]
    off = dict(kind='drive', frequency_mhz=CENTER_MHZ, gain=0, count=1, delay_us=.1)
    return [dict(off)] + arms[:24] + [dict(off)] + arms[24:48] + [dict(off)] + arms[48:] + [dict(off)]


def ramsey_conditions(center):
    return [dict(kind='ramsey', frequency_mhz=float(center+offset), gain=16000,
                 delay_us=float(delay), phase_deg=phase)
            for delay in np.linspace(.2, 40.2, 81)
            for offset in (-.025, .025) for phase in (0, 90, 180, 270)]


def gain_conditions(frequency):
    arms = [dict(kind='drive', frequency_mhz=float(frequency), gain=int(gain),
                 count=count, delay_us=.1)
            for gain in np.random.default_rng(422).permutation(np.arange(0,32001,1000))
            for count in (1, 3)]
    arms += [dict(kind='drive', frequency_mhz=float(frequency), gain=int(gain),
                  count=4, delay_us=.1)
             for gain in np.random.default_rng(423).permutation(np.arange(8000,22001,500))]
    return arms


def payload_pulses(arm):
    gain, frequency, delay = arm['gain'], arm['frequency_mhz'], arm['delay_us']
    if not isinstance(gain, (int,np.integer)) or not 0<=gain<=32000:
        raise ValueError('diagnostic pulse gain must be an integer in 0..32000')
    if not math.isfinite(frequency) or abs(frequency-CENTER_MHZ)>.3:
        raise ValueError('diagnostic frequency must stay within 300 kHz of q4')
    if not math.isfinite(delay) or not .01<=delay<=50:
        raise ValueError('diagnostic pulse gap must be in 0.01..50 us')
    if arm['kind']=='ramsey':
        if arm['phase_deg'] not in (0,90,180,270): raise ValueError('invalid Ramsey phase')
        return [(gain,0),(gain,arm['phase_deg'])]
    if arm['kind']=='drive' and arm['count'] in (1,3,4):
        return [(gain,0)]*arm['count']
    raise ValueError('unknown diagnostic condition or pulse count')


def select_frequency(arms, populations):
    rows=sorted((a['frequency_mhz'],float(y)) for a,y in zip(arms,populations) if a['gain'])
    f,y=np.array(rows).T
    baseline=float(np.mean([v for a,v in zip(arms,populations) if not a['gain']]))
    smooth=np.convolve(np.pad(y,1,mode='edge'),[.25,.5,.25],mode='valid')
    k=int(np.argmax(smooth))
    if k<4 or k>len(f)-5 or smooth[k]-baseline<.15:
        raise ValueError('q4 spectroscopy has no interior resolved peak; raw scan saved')
    return dict(frequency_mhz=float(f[k]),ground_reference=baseline,
                excess=float(smooth[k]-baseline),method='coarse smoothed peak, not final frequency calibration')


def fit_ramsey(delays, z, errors):
    from scipy.optimize import least_squares
    t=np.asarray(delays,float); z=np.asarray(z,complex); se=np.asarray(errors,float)
    result=dict(valid=False)
    if t.ndim!=1 or z.shape!=t.shape or se.shape!=(2,len(t)) or len(t)<10:
        return dict(result,reason='invalid Ramsey array shapes')
    if not all(np.all(np.isfinite(v)) for v in (t,z,se)) or np.any(se<0):
        return dict(result,reason='nonfinite Ramsey data')
    se=np.maximum(se,.004)
    def model(p):
        return (p[0]+1j*p[1])*np.exp(-t/p[5]+2j*np.pi*p[4]*t)+p[2]+1j*p[3]
    def residual(p):
        d=model(p)-z
        return np.concatenate((d.real/se[0],d.imag/se[1]))
    candidates=[]
    for beat in np.linspace(-.175,.175,701):
        x=np.column_stack((np.exp(-t/80+2j*np.pi*beat*t),np.ones(len(t))))
        a,c=np.linalg.lstsq(x,z,rcond=None)[0]
        p=[a.real,a.imag,c.real,c.imag,beat,80.]
        candidates.append((float(np.sum(residual(p)**2)),p))
    try:
        best=None
        for _,seed in sorted(candidates,key=lambda v:v[0])[:3]:
            seed=np.clip(seed,[-1.9,-1.9,-.9,-.9,-.174,1.01],[1.9,1.9,.9,.9,.174,9999.])
            fit=least_squares(residual,seed,bounds=([-2,-2,-1,-1,-.175,1.],
                                                  [2,2,1,1,.175,10000.]),max_nfev=2000)
            if best is None or fit.cost<best.cost: best=fit
        cov=np.linalg.inv(best.jac.T@best.jac)
        p=best.x; err=float(np.sqrt(cov[4,4])); reduced=float(2*best.cost/(2*len(t)-6))
        amplitude=float(np.hypot(p[0],p[1]))
        valid=bool(best.success and amplitude>.15 and err<.002 and reduced<=5 and abs(p[4])<.17)
        result.update(valid=valid,beat_mhz=float(p[4]),beat_err_mhz=err,
                      amplitude=amplitude,decay_us=float(p[5]),reduced_chi2=reduced,
                      parameters=p.tolist())
    except (ValueError,RuntimeError,np.linalg.LinAlgError) as exc: result['reason']=str(exc)
    return result


def resolve_frequency(drives, fits):
    result=dict(valid=False)
    if len(fits)!=2 or not all(f.get('valid') for f in fits):
        return dict(result,reason='both Ramsey frequencies must resolve')
    df=float(drives[1]-drives[0]); beats=np.array([f['beat_mhz'] for f in fits])
    err=np.array([f['beat_err_mhz'] for f in fits]); shift=float(beats[1]-beats[0])
    if df<=0 or abs(abs(shift)-df)>max(.003,3*float(np.hypot(*err))):
        return dict(result,reason='Ramsey beat does not follow the known drive shift')
    slope=1 if shift>0 else -1
    estimates=np.array(drives)-beats/slope
    weights=1/np.maximum(err,.00005)**2
    frequency=float(np.average(estimates,weights=weights))
    uncertainty=float(np.sqrt(1/weights.sum()))
    valid=abs(frequency-np.mean(drives))<=.04 and uncertainty<=.002
    return dict(valid=bool(valid),frequency_mhz=frequency,frequency_err_mhz=uncertainty,
                measured_beat_slope=shift/df,phase_convention_slope=slope,
                independent_frequency_estimates_mhz=estimates.tolist())


def fit_gain(gains, populations, errors, count):
    from scipy.optimize import curve_fit
    g=np.asarray(gains,float); y=np.asarray(populations,float); se=np.maximum(errors,.004)
    result=dict(valid=False,pulse_count=int(count))
    if g.shape!=y.shape or g.shape!=np.shape(se) or len(g)<8:
        return dict(result,reason='invalid gain arrays')
    def model(x,c,a,pi): return c+a*(1-np.cos(count*np.pi*x/pi))/2
    candidates=[]
    for pi in np.linspace(18000,44000,261):
        shape=(1-np.cos(count*np.pi*g/pi))/2
        c,a=np.linalg.lstsq(np.column_stack((np.ones(len(g)),shape))/se[:,None],y/se,rcond=None)[0]
        if a>0: candidates.append((float(np.sum(((model(g,c,a,pi)-y)/se)**2)),[c,a,pi]))
    if not candidates: return dict(result,reason='no positive Rabi contrast')
    try:
        seed=min(candidates,key=lambda v:v[0])[1]
        p,cov=curve_fit(model,g,y,p0=np.clip(seed,[-.49,.001,18001],[.99,1.49,43999]),
                       sigma=se,absolute_sigma=True,bounds=([-.5,0,18000],[1,1.5,44000]),maxfev=10000)
        err=float(np.sqrt(cov[2,2])); reduced=float(np.sum(((model(g,*p)-y)/se)**2)/(len(g)-3))
        valid=bool(p[1]>.15 and err/p[2]<.1 and reduced<=5 and 18100<p[2]<43900)
        result.update(valid=valid,pi_gain=float(p[2]),pi_gain_err=err,
                      offset=float(p[0]),amplitude=float(p[1]),reduced_chi2=reduced)
    except (ValueError,RuntimeError) as exc: result['reason']=str(exc)
    return result


def acquire_stage(soc,soccfg,output,name,arms,calibration,*,progress=True):
    from tqdm import tqdm
    from .Q4EchoTuneupProgram import Q4TuneupProgram
    from ..active_reset_OPX.integration import runtime_bundle,classify_payload_iq
    cfg=t1.measurement_config(calibration['bundle']);cfg.update(shots=SHOTS,reps=SHOTS)
    bundle=runtime_bundle(cfg);stem=Path(output)/name
    t1.save_json(stem.with_suffix('.config.json'),cfg)
    t1.save_json(stem.with_suffix('.conditions.json'),arms)
    i=np.full((len(arms),SHOTS),np.nan);q=i.copy();completed=0;reports=[];telemetry=[]
    with tqdm(total=len(arms)*SHOTS,desc=name,unit='shot',disable=not progress,
              bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed} elapsed, ETA {remaining}]') as bar:
        try:
            for start in range(0,len(arms),BLOCK_SIZE):
                group=arms[start:start+BLOCK_SIZE]
                p=Q4TuneupProgram(soccfg,dict(cfg,q4_tuneup_conditions=group,
                    opx_t1_delays_us=[a['delay_us'] for a in group],opx_t1_shots=SHOTS,
                    opx_resident_dmem_stream=True),bundle.payload,bundle.loop)
                instructions=len(p.compile());capacity=int(soccfg['tprocs'][0]['pmem_size'])
                if instructions>capacity: raise RuntimeError('q4 diagnostic exceeds program memory')
                reports.append(dict(start=start,instructions=instructions,capacity=capacity,
                                    waveform_memory=t1.validate_waveform_memory(p),timing=p.timing))
                t1.save_json(stem.with_suffix('.preflight.json'),reports)
                def update(done,total): bar.update(start*SHOTS+int(done)*len(group)-bar.n)
                iv,qv,meta=t1.acquire_curve_iq(soc,p,cfg,update)
                if iv.shape!=(len(group),SHOTS) or qv.shape!=iv.shape:
                    raise RuntimeError('incomplete q4 diagnostic block')
                i[start:start+len(group)],q[start:start+len(group)]=iv,qv
                completed=start+len(group);telemetry.append(meta)
                np.savez_compressed(stem.with_suffix('.partial.npz'),i=i,q=q,completed_conditions=completed)
        except BaseException as exc:
            partial=getattr(exc,'partial_records',None) or []
            np.savez_compressed(stem.with_suffix('.partial.npz'),i=i,q=q,completed_conditions=completed,
                inflight_raw_i=[r.final_i for r in partial],inflight_raw_q=[r.final_q for r in partial])
            raise
    np.savez_compressed(stem.with_suffix('.npz'),i=i,q=q)
    stem.with_suffix('.partial.npz').unlink()
    t1.save_json(stem.with_suffix('.telemetry.json'),telemetry)
    y=classify_payload_iq(cfg,i,q,telemetry[0]['read_length_cycles'])
    data=dict(populations=y.mean(axis=1).tolist(),errors=(y.std(axis=1,ddof=1)/np.sqrt(SHOTS)).tolist())
    t1.save_json(stem.with_suffix('.json'),data)
    return y,data


def analyze_ramsey(arms,y):
    drives=sorted({a['frequency_mhz'] for a in arms});fits=[];traces=[]
    for drive in drives:
        rows=[k for k,a in enumerate(arms) if a['frequency_mhz']==drive]
        values=y[rows].reshape(-1,4,SHOTS)
        t=np.array([arms[k]['delay_us'] for k in rows[::4]])
        dx=values[:,0]-values[:,2];dy=values[:,1]-values[:,3]
        z=dx.mean(axis=1)+1j*dy.mean(axis=1)
        se=np.array([dx.std(axis=1,ddof=1),dy.std(axis=1,ddof=1)])/np.sqrt(SHOTS)
        fits.append(fit_ramsey(t,z,se))
        traces.append(dict(drive_mhz=drive,delays_us=t.tolist(),x=z.real.tolist(),y=z.imag.tolist(),errors=se.tolist()))
    return dict(drives_mhz=drives,fits=fits,frequency=resolve_frequency(drives,fits),traces=traces)


def analyze_gains(arms,data,frequency):
    fits=[]
    for count in (1,3,4):
        rows=[k for k,a in enumerate(arms) if a['count']==count]
        fits.append(fit_gain([arms[k]['gain'] for k in rows],
            np.array(data['populations'])[rows],np.array(data['errors'])[rows],count))
    result=dict(fits=fits,valid=False)
    if not all(f['valid'] for f in fits): return result
    p1,p3,p4=[f['pi_gain'] for f in fits];errors=[f['pi_gain_err'] for f in fits]
    consistent=abs(p1-p3)<max(.08*p3,3*np.hypot(errors[0],errors[1]))
    consistent &= abs(p4-p3)<max(.08*p3,3*np.hypot(errors[2],errors[1]))
    valid=bool(frequency['valid'] and consistent and 0<p3<=32000 and 0<p4/2<=22000)
    result.update(valid=valid,train_agreement=bool(consistent),pi_gain=int(round(p3)),
                  pi2_gain=int(round(p4/2)),frequency_mhz=frequency.get('frequency_mhz'),
                  application='suggestion only; inspect measured echo before overnight acquisition')
    return result


def save_plot(output,arms,data,ramsey,gain_arms,gain_data,gains):
    import matplotlib.pyplot as plt
    fig,axs=plt.subplots(2,2,figsize=(11,7),layout='constrained')
    rows=sorted([k for k,a in enumerate(arms) if a['gain']],key=lambda k:arms[k]['frequency_mhz'])
    axs[0,0].errorbar([1000*(arms[k]['frequency_mhz']-CENTER_MHZ) for k in rows],
        np.array(data['populations'])[rows],yerr=np.array(data['errors'])[rows],fmt='.-',ms=3)
    axs[0,0].set(xlabel='Drive offset from 4367.760 MHz (kHz)',ylabel='Classified excited fraction',title='Single-pulse resonance')
    for trace,fit,ax in zip(ramsey['traces'],ramsey['fits'],axs[1]):
        t=np.array(trace['delays_us'])
        for part,color in (('x','C0'),('y','C1')):
            ax.plot(t,trace[part],'.',color=color,label=part)
        if 'parameters' in fit:
            p=fit['parameters'];grid=np.linspace(t[0],t[-1],500)
            z=(p[0]+1j*p[1])*np.exp(-grid/p[5]+2j*np.pi*p[4]*grid)+p[2]+1j*p[3]
            ax.plot(grid,z.real,color='C0');ax.plot(grid,z.imag,color='C1')
        ax.set(xlabel='Ramsey free gap (µs)',ylabel='Signed phase contrast',title=f"Drive {trace['drive_mhz']:.6f} MHz")
        ax.legend()
    for count,fit in zip((1,3,4),gains['fits']):
        rows=sorted([k for k,a in enumerate(gain_arms) if a['count']==count],key=lambda k:gain_arms[k]['gain'])
        x=np.array([gain_arms[k]['gain'] for k in rows])
        line=axs[0,1].errorbar(x,np.array(gain_data['populations'])[rows],yerr=np.array(gain_data['errors'])[rows],fmt='.',label=f'{count} pulses')
        if 'pi_gain' in fit:
            grid=np.linspace(x.min(),x.max(),300)
            axs[0,1].plot(grid,fit['offset']+fit['amplitude']*(1-np.cos(count*np.pi*grid/fit['pi_gain']))/2,color=line[0].get_color())
    axs[0,1].set(xlabel='Pulse gain',ylabel='Classified excited fraction',title='Rotation checks');axs[0,1].legend()
    for ax in axs.flat:ax.grid(alpha=.2)
    fig.suptitle('q4 pulse diagnostic — candidate settings require measured echo validation')
    fig.savefig(Path(output)/'diagnostic.png',dpi=160);plt.close(fig)


def run(*,data_root=t1.DATA_ROOT,progress=True):
    output=Path(data_root)/'q4'/('q4_echo_tuneup_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    output.mkdir(parents=True);t1.snapshot_initialize(output/'initialize_snapshot')
    for name in ('Q4EchoTuneup.py','Q4EchoTuneupProgram.py','Q4RepeatedT1.py'):
        shutil.copyfile(Path(__file__).with_name(name),output/name)
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=Path(__file__).parent,text=True).strip()
    manifest=dict(commit=revision,status='running',started_at=datetime.now(timezone.utc).isoformat(),
                  shots_per_condition=SHOTS,reset='opx_unbounded',flux_gain=0,stages=[])
    t1.save_json(output/'manifest.json',manifest);print(f'q4 pulse calibration: {output}',flush=True)
    import matplotlib
    matplotlib.use('Agg')
    from ..CoreLib.socProxy import makeProxy
    from ..active_reset_OPX.acquisition import _safe_abort
    soc=None;started=time.monotonic()
    try:
        soc,soccfg=makeProxy();t1.save_json(output/'board_configuration.json',soccfg.get_cfg())
        calibration=t1.calibrate_reset(soc,soccfg,output,1,purpose='Q4EchoTuneup')
        arms=spectroscopy_conditions()
        _,spec=acquire_stage(soc,soccfg,output,'Spectroscopy',arms,calibration,progress=progress)
        coarse=select_frequency(arms,spec['populations']);manifest.update(coarse_frequency=coarse,stages=['Spectroscopy'])
        t1.save_json(output/'manifest.json',manifest)
        rarms=ramsey_conditions(coarse['frequency_mhz'])
        y,_=acquire_stage(soc,soccfg,output,'Ramsey',rarms,calibration,progress=progress)
        ramsey=analyze_ramsey(rarms,y);t1.save_json(output/'ramsey_analysis.json',ramsey)
        manifest['stages'].append('Ramsey');manifest['frequency']=ramsey['frequency']
        t1.save_json(output/'manifest.json',manifest)
        frequency=ramsey['frequency']
        gain_frequency=frequency['frequency_mhz'] if frequency['valid'] else coarse['frequency_mhz']
        garms=gain_conditions(gain_frequency)
        _,gdata=acquire_stage(soc,soccfg,output,'Rabi',garms,calibration,progress=progress)
        gains=analyze_gains(garms,gdata,frequency);gains['measured_at_mhz']=gain_frequency
        t1.save_json(output/'gain_analysis.json',gains)
        save_plot(output,arms,spec,ramsey,garms,gdata,gains)
        manifest.update(status='complete',stages=['Spectroscopy','Ramsey','Rabi'],candidate=gains)
        print('Qubit calibration complete; results saved for review.',flush=True)
    except BaseException as exc:
        manifest.update(status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        if soc is not None:_safe_abort(soc)
        manifest.update(duration_s=time.monotonic()-started,completed_at=datetime.now(timezone.utc).isoformat())
        t1.save_json(output/'manifest.json',manifest)
    return output


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true');parser.add_argument('--data-root',default=t1.DATA_ROOT)
    parser.add_argument('--quiet',action='store_true');args=parser.parse_args(argv)
    if args.run:run(data_root=args.data_root,progress=not args.quiet)
    else:print(json.dumps(dict(qubit='q4',shots_per_condition=SHOTS,
        spectroscopy_conditions=len(spectroscopy_conditions()),ramsey_conditions=len(ramsey_conditions(CENTER_MHZ)),
        gain_conditions=len(gain_conditions(CENTER_MHZ)),automatic_echo_start=False),indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
