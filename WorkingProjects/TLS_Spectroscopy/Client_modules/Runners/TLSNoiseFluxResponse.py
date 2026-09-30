"""q3 even-phase flux-response diagnostic at the validated 4.288-GHz site.

A Hahn echo samples either a 298-ns static offset or eight 37-ns balanced
chips in its first free interval. Opposite polarities separate even from odd
phase. Even phase is a directly measured observable; interpreting it as flux
power requires an odd/linear line response and negligible pulse transients.
This is not a complete transfer function or certification of the TLS waveforms.
"""
import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import time
import uuid
import numpy as np
from . import TLSControlledNoise as noise
from . import Q3QuasiparticlePumping as qp
from . import TLSPumpProbeLocalizer as localizer

TARGET_GHZ, DRIVE_MHZ = 4.288, 4290.5
PRE_US, POST_US = 29.51, .05
PHASES = (0,90,180,270)
AMPLITUDES = (64,250,375)
PLACEMENTS = ('early','late')
BLOCKS, SHOTS = 4, 600


def timing(fabric_mhz):
    if not math.isfinite(fabric_mhz) or not math.isclose(fabric_mhz,430.08,rel_tol=1e-8):
        raise ValueError('requires the verified 430.08-MHz fabric/tProc clock')
    half,full=round(.045*fabric_mhz),round(.0907*fabric_mhz)
    elapsed=4*round(1.35*fabric_mhz/4)
    lead=208
    starts=[lead,lead+elapsed//2+(half-full)//2,lead+elapsed]
    return dict(fabric_mhz=fabric_mhz,pi2_cycles=half,pi_cycles=full,
                lead_cycles=lead,elapsed_cycles=elapsed,elapsed_us=elapsed/fabric_mhz,
                pulse_starts=starts,pulse_lengths=[half,full,half],
                window_cycles=lead+elapsed+half+16,
                noise_starts={'early':lead+64,'late':lead+96},noise_cycles=128)


def offset_waveform(t,pattern,amplitude,polarity,placement,*,seed):
    if pattern not in ('off','static','fast') or placement not in PLACEMENTS:
        raise ValueError('unknown waveform or placement')
    if amplitude not in (0,*AMPLITUDES) or (pattern=='off' and (amplitude or polarity)) or (
            pattern!='off' and (amplitude==0 or polarity not in (-1,1))):
        raise ValueError('unsupported amplitude or polarity')
    result=np.zeros(t['window_cycles'],dtype=np.int64)
    if pattern=='off':return result
    values=np.ones(128,dtype=int)
    if pattern=='fast':
        signs=np.r_[np.ones(4,dtype=int),-np.ones(4,dtype=int)]
        np.random.default_rng(20261000+int(seed)).shuffle(signs)
        values=np.repeat(signs,16)
    start=t['noise_starts'][placement]
    result[start:start+128]=int(polarity)*int(amplitude)*values
    for at,length in zip(t['pulse_starts'],t['pulse_lengths']):
        if np.any(result[max(0,at-32):at+length+32]):
            raise ValueError('flux offset overlaps microwave pulse guard')
    return result


def conditions(kind,block):
    result=[dict(name='g',state='g',phase=0,polarity=0),
            dict(name='e',state='e',phase=0,polarity=0)]
    if kind=='pulse_control':
        result += [dict(name=s,state=s,phase=0,polarity=0) for s in ('half','two_pi')]
    polarities=(-1,1) if kind in ('static','fast') else (0,)
    for p in polarities:
        result += [dict(name=f'p{p}_a{a}',state='phase',phase=a,polarity=p) for a in PHASES]
    if block%2:result.reverse()
    shift=block%len(result)
    return result[shift:]+result[:shift]


def tasks():
    result=[]
    def add(kind,block,amplitude=0,placement='early'):
        result.append(dict(name=f'p{len(result):03d}_{kind}',index=len(result),
                           kind=kind,block=block,seed=block,amplitude=amplitude,
                           placement=placement,shots=SHOTS,conditions=conditions(kind,block)))
    add('pulse_control',-1)
    for b in range(BLOCKS):
        add('off',b)
        settings=[(p,a,d) for p in ('static','fast') for a in AMPLITUDES for d in PLACEMENTS]
        for i in np.random.default_rng(20261000+b).permutation(len(settings)):
            p,a,d=settings[i];add(p,b,a,d)
        add('off',b)
    add('pulse_control',BLOCKS)
    return result


def plan():
    ts=tasks()
    return dict(qubit='q3',target_ghz=TARGET_GHZ,drive_mhz=DRIVE_MHZ,
                timing=timing(430.08),amplitudes_dac=list(AMPLITUDES),
                placements=list(PLACEMENTS),blocks=BLOCKS,shots_per_condition=SHOTS,
                programs=len(ts),probes=sum(t['shots']*len(t['conditions']) for t in ts),
                pre_us=PRE_US,return_us=40.,passive_washout_us=1000.,
                five_point_scout=False,approximate_minutes='8–15',
                observable='even phase, principal modulo pi; per-seed polarity pairing',
                interpretation=__doc__)


def decode(words,task,bundle):
    words=np.asarray(words)
    count=len(task['conditions']);shots=task['shots']
    if words.shape!=(shots*count,2):raise ValueError('incomplete phase IQ stream')
    words=words.reshape(shots,count,2)
    rows=[]
    for i,c in enumerate(task['conditions']):
        x=bundle.payload.project(words[:,i,0],words[:,i,1]).astype(float)
        rows.append(dict(**c,mean=float(x.mean()),sem=float(x.std(ddof=1)/np.sqrt(shots)),shots=shots))
    return rows


def phase_circle(rows,*,contrast):
    if set(map(str,PHASES))!=set(rows) or not math.isfinite(contrast) or contrast<=0:
        raise ValueError('phase circle needs four phases and positive reference contrast')
    mu=np.array([rows[str(p)]['mean'] for p in PHASES])
    variances=np.array([rows[str(p)]['sem']**2 for p in PHASES])
    if not np.all(np.isfinite(mu+variances)):raise ValueError('nonfinite phase-circle data')
    x,y=mu[0]-mu[2],mu[1]-mu[3]
    vx,vy=variances[0]+variances[2],variances[1]+variances[3]
    radius=float(np.hypot(x,y));phi=float(np.arctan2(y,x))
    error=float(np.sqrt((y*y*vx+x*x*vy)/radius**4)) if radius>0 else math.pi
    residual=float(abs(mu[0]+mu[2]-mu[1]-mu[3]))
    valid=bool(radius/contrast>=.12 and error<=.20 and
               residual<=max(.10*contrast,4*np.sqrt(variances.sum())))
    return dict(x=float(x/contrast),y=float(y/contrast),phase_rad=phi,
                visibility=radius/contrast,error_rad=error,valid=valid,
                quadrature_residual=residual/contrast)


def even_phase(plus,minus,off):
    angle=math.atan2(math.sin(plus['phase_rad']+minus['phase_rad']-2*off['phase_rad']),
                     math.cos(plus['phase_rad']+minus['phase_rad']-2*off['phase_rad']))
    error=math.sqrt(.25*(plus['error_rad']**2+minus['error_rad']**2)+off['error_rad']**2)
    valid=bool(all(c['valid'] for c in (plus,minus,off)) and
               abs(angle)+3*2*error<math.pi)
    return dict(phase_rad=angle/2,error_rad=error,valid=valid,
                branch='principal modulo pi; no automatic unwrapping')


def entry_report(entry):
    rows={r['name']:r for r in entry['rows']}
    contrast=rows['e']['mean']-rows['g']['mean']
    error=math.hypot(rows['e']['sem'],rows['g']['sem'])
    if contrast<=max(0.,8*error):return dict(valid=False,reason='unresolved g/e reference',circles={})
    result=dict(valid=True,contrast=contrast,circles={})
    for polarity in (-1,1) if entry['task']['kind'] in ('static','fast') else (0,):
        result['circles'][str(polarity)]=phase_circle(
            {str(a):rows[f'p{polarity}_a{a}'] for a in PHASES},contrast=contrast)
    if entry['task']['kind']=='pulse_control':
        normalized={s:(rows[s]['mean']-rows['g']['mean'])/contrast for s in ('half','two_pi')}
        result.update(normalized=normalized)
        result['valid']=bool(.3<=normalized['half']<=.7 and abs(normalized['two_pi'])<=.2 and
                             result['circles']['0']['valid'] and result['circles']['0']['visibility']>=.5)
    return result


def analyze(entries):
    reports={e['task']['name']:entry_report(e) for e in entries}
    controls=[reports[e['task']['name']] for e in entries if e['task']['kind']=='pulse_control']
    control_valid=len(controls)==2 and all(r['valid'] for r in controls)
    result=dict(entries=reports,even_phase=[],groups=[],complete_blocks=[],
                pulse_controls_valid=control_valid,
                interpretation='Even phase is modulo pi and echo-weighted, including tails. Away from the sweet spot, even line distortion also contributes through the linear frequency slope. No automatic power, amplitude or transfer certification.')
    for b in range(BLOCKS):
        group=[e for e in entries if e['task']['block']==b]
        refs=[e for e in group if e['task']['kind']=='off']
        if len(refs)!=2:continue
        left,right=(reports[e['task']['name']] for e in refs)
        if not left['valid'] or not right['valid']:continue
        lo,hi=left['circles']['0'],right['circles']['0']
        drift=math.atan2(math.sin(hi['phase_rad']-lo['phase_rad']),math.cos(hi['phase_rad']-lo['phase_rad']))
        stable=bool(lo['valid'] and hi['valid'] and abs(drift)<=math.radians(25) and
                    min(lo['visibility'],hi['visibility'])/max(lo['visibility'],hi['visibility'])>=.65)
        result['complete_blocks'].append(dict(block=b,off_valid=stable,phase_drift_rad=drift))
        for e in group:
            task=e['task']
            if task['kind'] not in ('static','fast'):continue
            report=reports[task['name']]
            if not report['valid']:continue
            fraction=(e['midpoint_s']-refs[0]['midpoint_s'])/(refs[1]['midpoint_s']-refs[0]['midpoint_s'])
            if not 0<=fraction<=1:raise ValueError('phase probe is not bracketed in time')
            off=dict(phase_rad=lo['phase_rad']+fraction*drift,
                     error_rad=math.hypot((1-fraction)*lo['error_rad'],fraction*hi['error_rad']),valid=stable)
            r=even_phase(report['circles']['1'],report['circles']['-1'],off)
            result['even_phase'].append(dict(name=task['name'],block=b,seed=task['seed'],
                                            kind=task['kind'],amplitude=task['amplitude'],
                                            placement=task['placement'],off_fraction=fraction,**r))
    # Never select just the seeds with favorable visibility: require all four.
    for kind in ('static','fast'):
        for amplitude in AMPLITUDES:
            for placement in PLACEMENTS:
                rows=[r for r in result['even_phase'] if (r['kind'],r['amplitude'],r['placement'])==(kind,amplitude,placement)]
                g=dict(kind=kind,amplitude=amplitude,placement=placement,
                       valid=control_valid and len(rows)==BLOCKS and all(r['valid'] for r in rows),blocks=len(rows),
                       phase_data_valid=len(rows)==BLOCKS and all(r['valid'] for r in rows))
                if g['phase_data_valid']:
                    values=np.array([r['phase_rad'] for r in rows]);errs=np.array([r['error_rad'] for r in rows])
                    g.update(phase_rad=float(values.mean()),error_rad=float(np.sqrt(max(
                        values.var(ddof=1)/BLOCKS,np.sum(errs**2)/BLOCKS**2))))
                result['groups'].append(g)
    # A scaling discrepancy flags ambiguity; agreement cannot prove that the
    # principal half-angle is the correct branch. Never unwrap to a model.
    result['scaling_checks']=[]
    for kind in ('static','fast'):
        for placement in PLACEMENTS:
            pair=[next(g for g in result['groups'] if (g['kind'],g['placement'],g['amplitude'])==(kind,placement,a)) for a in (250,375)]
            check=dict(kind=kind,placement=placement,resolved=all(g['valid'] for g in pair))
            if check['resolved']:
                low,high=pair;ratio=(375/250)**2
                difference=high['phase_rad']-ratio*low['phase_rad']
                error=math.hypot(high['error_rad'],ratio*low['error_rad'])
                check.update(residual_rad=difference,error_rad=error,
                             scaling_or_branch_warning=abs(difference)>3*error,
                             note='Agreement does not resolve modulo-pi ambiguity or even line rectification.')
            result['scaling_checks'].append(check)
    return result


def plot_summary(folder,summary):
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(10,4),layout='constrained')
    for ax,placement in zip(axes,PLACEMENTS):
        for kind in ('static','fast'):
            rows=[r for r in summary['groups'] if r['kind']==kind and r['placement']==placement and r['valid']]
            if rows:ax.errorbar([r['amplitude'] for r in rows],[r['phase_rad'] for r in rows],
                                yerr=[r['error_rad'] for r in rows],fmt='o-',capsize=3,label=kind)
        ax.axhline(0,color='gray',ls='--');ax.set(title=placement.capitalize()+' placement',
            xlabel='Command amplitude (DAC)',ylabel='Even echo phase (rad), ±1 SE')
        if ax.lines:ax.legend()
    fig.suptitle('q3 flux-response diagnostic; unresolved/gated groups omitted')
    fig.savefig(Path(folder)/'even_phase.png',dpi=160);plt.close(fig)


def run(*,data_root=localizer.DATA_ROOT,correction_json=None,progress=True):
    import matplotlib
    matplotlib.use('Agg')
    from tqdm import tqdm
    from . import FivePointApplesToApples as five, TLSSpectroscopy as tls, TLSPumpProbeWidePassiveScan as wide
    from . import TLSEchoSquareMap as square
    from .ThreePointApplesToApples import _integer_dc_grid
    from .TLSNoiseFluxResponseProgram import make_program_class
    from ..active_reset_OPX.integration import _run_program
    from ..active_reset_OPX.acquisition import _safe_abort
    data_root=Path(data_root);correction=localizer.checked_correction(data_root,correction_json)
    source=data_root/'q3'/square.SOURCE_SESSION/'manifest.json'
    square.validate_source(json.loads(source.read_text()))
    folder=data_root/'q3'/('q3_noise_flux_response_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True);path=folder/'manifest.json'
    manifest=dict(schema='q3.noise-flux-response.v1',status='calibrating',plan=plan(),completed=[],
                  created_at=datetime.now(timezone.utc).isoformat(),correction_sha256=localizer.CORRECTION_SHA256)
    manifest['commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=Path(__file__).parent,text=True).strip()
    for name in ('TLSNoiseFluxResponse.py','TLSNoiseFluxResponseProgram.py','TLSControlledNoise.py',
                 'Q3QuasiparticlePumping.py','TLSPumpProbeResidentDrive.py','TLSPumpProbeShotAlternating.py'):
        p=Path(__file__).with_name(name);shutil.copy2(p,folder/name)
        manifest[name+'_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    shutil.copy2(source,folder/'pulse_source_manifest.json')
    qp.save_json(path,manifest);soc=None
    try:
        with noise.q3_context(tls,data_root),localizer.scan_environment(correction):
            five.install_scan_calibration(tls)
            gains,realized=_integer_dc_grid(wide.parameters(),np.array([TARGET_GHZ]),tls)
            target=int(gains[0])
            if target!=-20130:raise ValueError('target bias differs from validated phase-control site')
            soc,soccfg=tls.makeProxy();qp.save_json(folder/'board_configuration.json',soccfg.get_cfg())
            bundle=qp.calibrate(soc,soccfg,folder,'pre',feedback_free=True)
            cfg=noise.science_config(bundle,tls,tls._load_correction(str(correction),str(data_root)))
            qp.save_json(folder/'config.json',cfg)
            Program=make_program_class();ts=tasks();started=time.monotonic()
            def build(task):
                with (folder/'compile.log').open('a') as log,redirect_stdout(log):
                    return Program(soccfg,cfg,task,bundle.payload,bundle.loop,center_gain=target)
            # Every waveform is compiled/checked before loading the first program.
            manifest['preflight']=[]
            for task in ts:
                p=build(task);manifest['preflight'].append(dict(name=task['name'],**noise.preflight(p),timing=p.timing_report))
            manifest['status']='acquiring';qp.save_json(path,manifest)
            done=0
            with tqdm(total=plan()['probes'],desc='Flux response',unit='shot',disable=not progress,
                      bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed} elapsed, ETA {remaining}]') as bar:
                for task in ts:
                    manifest['current']=task;qp.save_json(path,manifest)
                    p=build(task);info=noise.preflight(p);stem=folder/task['name'];n=len(task['conditions'])
                    qp.save_json(stem.with_suffix('.json'),dict(task=task,config=p.cfg,preflight=info,timing=p.timing_report))
                    np.savez_compressed(folder/(task['name']+'_waveforms.npz'),**p.waveforms)
                    def update(count,total):bar.update(done+int(count)*n-bar.n)
                    begin=time.monotonic()
                    try:records=_run_program(soc,p,60.,cfg,total_shots=task['shots'],progress=update)
                    except BaseException as exc:
                        _safe_abort(soc)
                        partial=getattr(exc,'partial_records',None)
                        if partial is not None:np.savez_compressed(folder/(task['name']+'.partial.npz'),words=np.asarray([[r.i,r.q] for r in partial],dtype=np.int64))
                        raise
                    end=time.monotonic();words=np.asarray([[r.i,r.q] for r in records],dtype=np.int64)
                    np.savez_compressed(stem.with_suffix('.npz'),words=words)
                    entry=dict(task=task,rows=decode(words,task,bundle),raw_file=stem.with_suffix('.npz').name,
                               midpoint_s=(begin+end)/2-started,completed_at=datetime.now(timezone.utc).isoformat())
                    manifest['completed'].append(entry);done+=task['shots']*n
                    qp.save_json(path,manifest)
                    if task['kind']=='pulse_control' and task['index']==0 and not entry_report(entry)['valid']:
                        manifest.update(status='complete_controls_unresolved',current=None,
                                        completed_at=datetime.now(timezone.utc).isoformat())
                        qp.save_json(folder/'summary.json',analyze(manifest['completed']))
                        qp.save_json(path,manifest)
                        return folder
                    qp.save_json(folder/'summary.json',analyze(manifest['completed']))
            summary=analyze(manifest['completed']);plot_summary(folder,summary)
            manifest['status']='post_calibrating';qp.save_json(path,manifest)
            post=qp.calibrate(soc,soccfg,folder,'post',feedback_free=True)
            post_entries=[]
            for entry in manifest['completed']:
                with np.load(folder/entry['raw_file']) as data:
                    post_entries.append(dict(entry,rows=decode(data['words'],entry['task'],post)))
            qp.save_json(folder/'post_calibration_summary.json',analyze(post_entries))
            manifest.update(status='complete' if summary['pulse_controls_valid'] else 'complete_controls_unresolved',
                            current=None,completed_at=datetime.now(timezone.utc).isoformat())
            qp.save_json(path,manifest)
    except BaseException as exc:
        if soc is not None:_safe_abort(soc)
        manifest.update(status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',error=f'{type(exc).__name__}: {exc}')
        qp.save_json(path,manifest);raise
    finally:
        if soc is not None:_safe_abort(soc)
    return folder


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true');parser.add_argument('--plan',action='store_true')
    parser.add_argument('--data-root',default=str(localizer.DATA_ROOT))
    parser.add_argument('--correction-json');parser.add_argument('--quiet',action='store_true')
    a=parser.parse_args(argv)
    if a.run:run(data_root=a.data_root,correction_json=a.correction_json,progress=not a.quiet)
    else:print(json.dumps(plan(),indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
