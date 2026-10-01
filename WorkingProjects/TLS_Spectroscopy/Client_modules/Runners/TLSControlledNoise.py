"""Finite q3 loss-profile comparison under slow/fast balanced frequency noise.

One wide scout selects one loss site. Every science shot interleaves passive
g/e preparations and off/slow/fast arms; readout follows the corrected return.
The two noise arms have identical commanded offset histograms, not a certified
identical delivered distribution. A positive result is a candidate temporal
response requiring on-chip transfer calibration before a Zeno interpretation.
"""
import argparse
from contextlib import contextmanager, redirect_stdout
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import uuid
import numpy as np
from . import Q3QuasiparticlePumping as qp
from . import TLSPumpProbeLocalizer as localizer

PATTERNS = ('off', 'slow', 'fast')
OFFSETS_MHZ = (-8, -4, -2, 0, 2, 4, 8)
AMPLITUDE_MHZ = 4.
CORE_CYCLES = (512, 1536)
LONG_CORE_CYCLES = (512, 4352)
GUARD_CYCLES = 16
CHIP_CYCLES = {'fast': 16, 'slow': 128}
BLOCKS, SHOTS = 8, 500
PRE_US = .05


def _validate_request(anchor_ghz=None,seed_offset=0):
    if anchor_ghz is not None and (not math.isfinite(anchor_ghz) or not 3.8<=anchor_ghz<=4.3):
        raise ValueError('anchor must be a finite frequency in the 3.8–4.3 GHz band')
    if not isinstance(seed_offset,(int,np.integer)) or not 0<=seed_offset<=1000000:
        raise ValueError('seed offset must be an integer from 0 to 1000000')


def plan(*, long_hold=False,anchor_ghz=None,seed_offset=0,paired_polarity=False):
    _validate_request(anchor_ghz,seed_offset)
    if paired_polarity and not long_hold:raise ValueError('paired polarity requires --long-hold')
    cores=LONG_CORE_CYCLES if long_hold else CORE_CYCLES
    return dict(qubit='q3', scout_ghz=[3.8, 4.3], scout_step_mhz=2.,
                anchor_ghz=anchor_ghz,anchor_radius_mhz=8. if anchor_ghz is not None else None,
                seed_offset=int(seed_offset),
                offsets_mhz=list(OFFSETS_MHZ), control='quieter of ±16 MHz',
                programmed_excursion_mhz=AMPLITUDE_MHZ,
                chip_cycles=CHIP_CYCLES, core_cycles=list(cores),
                long_hold=bool(long_hold),
                playback='const_segments' if long_hold else 'arb',
                zero_guard_cycles_each_end=GUARD_CYCLES,
                expected_holds_us=[(c+2*GUARD_CYCLES)/430.08 for c in cores],
                noise_ensemble='eight frozen balanced realizations, repeated per hardware shot',
                blocks=BLOCKS, shots_per_condition_per_block=SHOTS,
                paired_polarity=bool(paired_polarity),
                commanded_histogram_match='full DAC codes across both polarities' if paired_polarity else 'additive offsets only',
                science_programs=128, total_science_probes=640000 if paired_polarity else 384000,
                reset='1000 us passive washout', return_us=40.,
                approximate_minutes=('16–25' if paired_polarity else '12–20')+' including scout, calibration and NAS overhead',
                interpretation=__doc__)


@contextmanager
def q3_context(tls, data_root):
    keys=('BaseConfig','QUBIT','SET_YOKO','outerFolder','FLUX_FIT_PARAMS',
          'BASELINE_DC_OFFSET','TARGET_DC_OFFSET','FLUX_TAIL_COMPENSATION_GAIN')
    missing=object()
    saved={k:getattr(tls,k,missing) for k in keys}
    tls.BaseConfig=qp.base_config()
    tls.QUBIT, tls.SET_YOKO, tls.outerFolder='q3',False,str(data_root)
    try:
        yield
    finally:
        for k,v in saved.items():
            if v is missing:
                if hasattr(tls,k): delattr(tls,k)
            else: setattr(tls,k,v)


def noise_signs(core_cycles, pattern, *, seed):
    if pattern not in CHIP_CYCLES or core_cycles not in (*CORE_CYCLES,*LONG_CORE_CYCLES):
        raise ValueError('invalid noise pattern or duration')
    chip=CHIP_CYCLES[pattern]
    count=core_cycles//chip
    signs=np.r_[np.ones(count//2,dtype=int),-np.ones(count//2,dtype=int)]
    np.random.default_rng(300926+101*int(seed)+(pattern=='fast')).shuffle(signs)
    return np.r_[np.zeros(GUARD_CYCLES,dtype=int),np.repeat(signs,chip),
                 np.zeros(GUARD_CYCLES,dtype=int)]


def waveforms(*, segments, park_gain, target_gain, endpoint_gains, core_cycles,
              fabric_mhz, samples_per_clock, max_gain, seed, dc_tick_quantum=1,polarity=1):
    """Common correction on fabric ticks; additive endpoint offsets, no clipping.

    The off arm uses lossless run-length encoding of the SAME DC samples as
    both noise arms, avoiding a third full-size envelope in QICK memory.
    """
    n=int(core_cycles)+2*GUARD_CYCLES
    if polarity not in (-1,1):raise ValueError('noise polarity must be -1 or +1')
    lengths=np.asarray([t for _,t in segments],float)
    levels=np.asarray([v for v,_ in segments],float)
    if not len(lengths) or np.any(lengths<=0) or not np.all(np.isfinite(lengths+levels)):
        raise ValueError('invalid correction segments')
    if fabric_mhz<=0 or int(samples_per_clock)!=samples_per_clock or samples_per_clock<1:
        raise ValueError('invalid generator clock')
    t=np.arange(n)/float(fabric_mhz)
    if n/fabric_mhz>sum(lengths)+1e-8:
        raise ValueError('correction does not cover noise duration')
    ix=np.minimum(np.searchsorted(np.cumsum(lengths),t,side='right'),len(levels)-1)
    dc=np.rint(float(park_gain)+levels[ix]*(target_gain-park_gain)).astype(np.int64)
    if dc_tick_quantum not in (1,16): raise ValueError('unsupported DC clock quantum')
    original_dc=dc.copy()
    # Long holds use constant segments. Align DC boundaries to the fastest
    # noise chip so no segment is shorter than the tProc can issue it.
    dc=np.repeat(dc[::dc_tick_quantum],dc_tick_quantum)[:n]
    edges=np.r_[0,np.flatnonzero(np.diff(dc))+1,n]
    # axis_signal_gen_v4 constant pulses require at least three fabric clocks.
    # Remove sub-three-clock DC slivers identically in every arm, recording it.
    merged=0
    for start,stop in zip(edges[:-1],edges[1:]):
        if stop-start<3:
            dc[start:stop]=dc[start-1] if start else dc[stop]
            merged+=int(stop-start)
    edges=np.r_[0,np.flatnonzero(np.diff(dc))+1,n]
    off=[(int(dc[a]),int(b-a)) for a,b in zip(edges[:-1],edges[1:])]
    if any(count<3 for _,count in off):
        raise ValueError('DC correction contains an unplayable short segment')
    values={}; reports={}; pattern_segments={}
    for pattern in ('slow','fast'):
        signs=int(polarity)*noise_signs(core_cycles,pattern,seed=seed)
        offset=np.where(signs<0,endpoint_gains[0]-target_gain,
                        np.where(signs>0,endpoint_gains[1]-target_gain,0))
        code=np.rint(dc+offset)
        if not np.all(np.isfinite(code)) or np.max(np.abs(code))>min(max_gain,32767):
            raise ValueError('noise command exceeds DAC range')
        values[pattern]=np.repeat(code.astype(np.int16),int(samples_per_clock))
        edges=np.r_[0,np.flatnonzero(np.diff(code))+1,n]
        pattern_segments[pattern]=[(int(code[a]),int(b-a)) for a,b in zip(edges[:-1],edges[1:])]
        reports[pattern]=dict(chip_us=CHIP_CYCLES[pattern]/fabric_mhz,
                              switches=int(np.count_nonzero(np.diff(signs))),
                              positive_cycles=int(np.sum(signs==1)),
                              negative_cycles=int(np.sum(signs==-1)),
                              command_min=int(code.min()),command_max=int(code.max()))
    if np.max(np.abs(dc))>min(max_gain,32767):
        raise ValueError('DC command exceeds DAC range')
    return values,dict(duration_us=n/fabric_mhz,cycles=n,off_segments=off,
                      pattern_segments=pattern_segments,
                      dc_tick_quantum=dc_tick_quantum,
                      dc_quantization_changed_cycles=int(np.count_nonzero(dc!=original_dc)),
                      dc_sliver_cycles_merged=merged, patterns=reports,
                      correction_note='same DC correction; AC transfer is uncalibrated')


def paired_waveforms(**kwargs):
    """Swap endpoint assignments at every tick, leaving DC correction intact.

    Pooling a waveform with its inverse matches the full code distribution
    between slow and fast even with asymmetric endpoints and changing DC.
    This does not certify identical delivered frequency distributions.
    """
    waves,report=waveforms(**kwargs,polarity=1)
    inverse,other=waveforms(**kwargs,polarity=-1)
    if report['off_segments']!=other['off_segments']:
        raise ValueError('polarity pair has different DC correction')
    for p in ('slow','fast'):
        name=p+'_inverse';waves[name]=inverse[p]
        report['patterns'][name]=other['patterns'][p]
        report['pattern_segments'][name]=other['pattern_segments'][p]
    matched=np.array_equal(np.sort(np.r_[waves['slow'],waves['slow_inverse']]),
                           np.sort(np.r_[waves['fast'],waves['fast_inverse']]))
    if not matched:raise ValueError('paired full DAC-code histograms do not match')
    report['paired_full_code_histograms_equal']=bool(matched)
    return waves,report


def select_candidate(rows,*,anchor_ghz=None):
    """One bidirectionally visible site; no second-line or empty-band gate."""
    _validate_request(anchor_ghz)
    indexed={round(float(r['target_frequency_ghz']),3):r for r in rows}
    def survival(f,t,suffix=''):
        nearby=[indexed.get(round(f+d,3)) for d in (-.002,0,.002)]
        if any(r is None for r in nearby): return math.nan
        try:
            c=sum(float(r['P1'+suffix])-float(r['P0'+suffix]) for r in nearby)
            y=sum(float(r[f'Ps_{t}us'+suffix])-float(r['P0'+suffix]) for r in nearby)
            return y/c if c/3>=.2 else math.nan
        except (KeyError,ValueError,TypeError): return math.nan
    candidates=[]
    for f in sorted(indexed):
        if not 3.824<=f<=4.276: continue
        if anchor_ghz is not None and abs(f-anchor_ghz)>.008000001: continue
        depths=[]
        for suffix in ('','_scan_up','_scan_down'):
            for t in (10,25):
                depths.append(min(survival(f-.012,t,suffix),survival(f+.012,t,suffix))
                              -survival(f,t,suffix))
        if not all(map(math.isfinite,depths)): continue
        if depths[0]<.06 or depths[1]<.12 or min(depths[2:])<.02: continue
        control=max((-16,16),key=lambda o:survival(f+o/1000,25))
        candidates.append(dict(center_ghz=f,depth_10us=depths[0],depth_25us=depths[1],
                               directional_depths=depths[2:],control_offset_mhz=control))
    return max(candidates,key=lambda c:c['depth_10us']+.25*c['depth_25us']) if candidates else None


def tasks(center, control_offset, *, fabric_mhz, long_hold=False,seed_offset=0,paired_polarity=False):
    _validate_request(seed_offset=seed_offset)
    if paired_polarity and not long_hold:raise ValueError('paired polarity requires long hold')
    offsets=(*OFFSETS_MHZ,int(control_offset))
    if len(set(offsets))!=8: raise ValueError('control must be separate from local profile')
    result=[]
    for block in range(BLOCKS):
        settings=[(off,core) for off in offsets for core in (LONG_CORE_CYCLES if long_hold else CORE_CYCLES)]
        np.random.default_rng(300930+block).shuffle(settings)
        patterns=list(PATTERNS)
        patterns=patterns[block%3:]+patterns[:block%3]
        if block%2: patterns.reverse()
        states=('g','e') if block%2==0 else ('e','g')
        for off,core in settings:
            index=len(result)
            conditions=[dict(pattern=p,state=s) for p in patterns for s in states]
            if paired_polarity:
                polarities=(1,-1) if block%2==0 else (-1,1)
                conditions=[dict(pattern=p,state=s,polarity=pol) for p in patterns
                            for pol in ((0,) if p=='off' else polarities) for s in states]
            result.append(dict(name=f'b{block:02d}_p{index:03d}',index=index,block=block,
                               seed=int(seed_offset)+block,offset_mhz=float(off),
                               frequency_ghz=round(center+off/1000,6),core_cycles=core,
                               playback='const_segments' if long_hold else 'arb',
                               hold_us=(core+2*GUARD_CYCLES)/fabric_mhz,shots=SHOTS,
                               paired_polarity=bool(paired_polarity),conditions=conditions))
    return result


def rows_from_words(words, task, bundle):
    words=np.asarray(words)
    count=len(task['conditions'])
    if words.shape!=(task['shots']*count,2): raise ValueError('incomplete science IQ stream')
    data=words.reshape(task['shots'],count,2)
    rows=[]
    for i,condition in enumerate(task['conditions']):
        z=bundle.payload.project(data[:,i,0],data[:,i,1])
        pe=float(np.mean(z>bundle.payload.excited_threshold))
        rows.append(dict(block=task['block'],offset_mhz=task['offset_mhz'],
                         frequency_ghz=task['frequency_ghz'],hold_us=task['hold_us'],
                         shots=task['shots'],pe=pe,**condition))
    return rows


def _rate(rows):
    times=sorted({r['hold_us'] for r in rows})
    if len(times)!=2: return dict(valid=False,reason='missing hold')
    contrast=[];variance=[]
    for t in times:
        means=[];variances=[]
        for state in ('g','e'):
            group=[r for r in rows if r['hold_us']==t and r['state']==state]
            n=sum(r['shots'] for r in group)
            if not n: return dict(valid=False,reason='missing preparation')
            p=sum(r['shots']*r['pe'] for r in group)/n
            means.append(p);variances.append(max(p*(1-p),.25/n)/n)
        contrast.append(means[1]-means[0]);variance.append(sum(variances))
    c=np.asarray(contrast);v=np.asarray(variance)
    valid=bool(c[0]>.15 and c[1]>.06 and np.all(c>3*np.sqrt(v)))
    result=dict(valid=valid,holds_us=times,contrast=contrast,contrast_error=np.sqrt(v).tolist())
    if valid:
        dt=times[1]-times[0]
        result.update(rate_per_us=float(np.log(c[0]/c[1])/dt),
                      error_per_us=float(np.sqrt(np.sum(v/c**2))/dt))
    else: result['reason']='unresolved preparation contrast'
    return result


def analyze(rows):
    result=dict(sites=[],interpretation='finite-window decay; programmed noise comparison, transfer uncalibrated',
                estimator='all-seed pooled log contrast ratios; no contrast-based seed selection')
    if rows and all('polarity' in r for r in rows):
        result['polarity_pairing']='both polarities pooled before log contrast ratio; delivered transfer uncalibrated'
    for off in sorted({r['offset_mhz'] for r in rows}):
        selected=[r for r in rows if r['offset_mhz']==off]
        blocks=sorted({r['block'] for r in selected})
        per_block={str(b):{p:_rate([r for r in selected if r['pattern']==p and r['block']==b])
                           for p in PATTERNS} for b in blocks}
        # Missing acquisitions may be excluded; a measured low contrast may not.
        # All arms use the same completed seeds, including strongly decaying seeds.
        complete=[b for b in blocks if all('contrast' in per_block[str(b)][p] for p in PATTERNS)]
        pooled=[r for r in selected if r['block'] in complete]
        rates={p:_rate([r for r in pooled if r['pattern']==p]) for p in PATTERNS}
        shot_variance={p:r.get('error_per_us',0.)**2 for p,r in rates.items()}
        for p,r in rates.items():
            r['blocks']=len(complete)
            if r['valid'] and len(complete)>1:
                dt=np.diff(r['holds_us'])[0]
                gradient=np.array([1.,-1.])/(dt*np.asarray(r['contrast']))
                values=np.asarray([per_block[str(b)][p]['contrast'] for b in complete])
                variance=float(gradient@np.cov(values,rowvar=False,ddof=1)@gradient/len(complete))
                r['error_per_us']=float(np.sqrt(max(shot_variance[p],variance)))
        effect=dict(valid=False,blocks=len(complete),incomplete_blocks=len(blocks)-len(complete))
        if len(complete)>=2 and rates['fast']['valid'] and rates['slow']['valid']:
            fast,slow=rates['fast'],rates['slow']
            dt=np.diff(fast['holds_us'])[0]
            gradient=np.array([1.,-1.,-1.,1.])/(dt*np.asarray(fast['contrast']+slow['contrast']))
            values=np.asarray([per_block[str(b)]['fast']['contrast']+per_block[str(b)]['slow']['contrast']
                               for b in complete])
            variance=float(gradient@np.cov(values,rowvar=False,ddof=1)@gradient/len(complete))
            effect.update(valid=True,rate_difference_per_us=fast['rate_per_us']-slow['rate_per_us'],
                          error_per_us=float(np.sqrt(max(shot_variance['fast']+shot_variance['slow'],variance))),
                          complete_block_ids=complete)
        result['sites'].append(dict(offset_mhz=off,frequency_ghz=selected[0]['frequency_ghz'],
                                    rates=rates,fast_minus_slow=effect,blocks=per_block))
    return result


def plot_summary(output, summary):
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(11,4.5),layout='constrained')
    for p in PATTERNS:
        points=[s for s in summary['sites'] if s['rates'][p]['valid']]
        axes[0].errorbar([s['offset_mhz'] for s in points],
                         [s['rates'][p]['rate_per_us'] for s in points],
                         yerr=[s['rates'][p]['error_per_us'] for s in points],fmt='o-',label=p)
    points=[s for s in summary['sites'] if s['fast_minus_slow']['valid']]
    axes[1].errorbar([s['offset_mhz'] for s in points],
                     [s['fast_minus_slow']['rate_difference_per_us'] for s in points],
                     yerr=[s['fast_minus_slow']['error_per_us'] for s in points],fmt='o')
    axes[1].axhline(0,color='gray',ls='--')
    axes[0].set(ylabel='Finite-window decay rate (1/µs)',title='q3 controlled frequency noise')
    axes[1].set(ylabel='Fast − slow rate (1/µs)',title='Paired by noise block; ±1 SE')
    for ax in axes: ax.set_xlabel('Offset from initial loss site (MHz)')
    axes[0].legend()
    fig.savefig(Path(output)/'noise_loss_profile.png',dpi=170)
    plt.close(fig)


def science_config(bundle, tls, compensation):
    cfg=qp.measurement_config(bundle,feedback_free=True)
    cfg.update(dt_pulseplay=tls.BaseConfig['dt_pulseplay'],dt_pulsedef=tls.BaseConfig['dt_pulsedef'],
               apply_flux_tail_compensation=True,flux_tail_compensation=compensation,
               flux_fit_params=list(tls.FLUX_FIT_PARAMS),flux_settle_time_us=.5,
               flux_predistortion_return_prefix_us=.5,flux_predistortion_recovery_us=40.,
               flux_predistortion_overlap_payload_readout=False,
               flux_predistortion_round_trip_mode='stateful',ff_ramp_length=1.,do_ff=True,
               opx_hard_flux_steps=True,opx_persistent_park=True,
               opx_park_preroll_us=1000.,opx_inter_shot_delay_us=1000.,relax_delay=1000.)
    return cfg


def const_issue_cycles(instructions):
    """tProc v1 ctrl.sv: regwi=2 clocks; set=4 including FETCH (no FIFO stall).

    Restrict this fast path to the verified register-write/output opcodes.
    https://github.com/openquantumhardware/qick/blob/main/firmware/ip/axis_tproc64x32_x8_v1/src/ctrl.sv
    """
    costs={'regwi':2,'set':4}
    if any(i['name'] not in costs for i in instructions):
        raise ValueError('unverified opcode in constant noise issue sequence')
    return sum(costs[i['name']] for i in instructions)


def preflight(program):
    instructions=len(program.compile())
    capacity=int(program.soccfg['tprocs'][0]['pmem_size'])
    if instructions>capacity: raise ValueError('instruction memory exceeded')
    memory=[]
    for ch,pulses in enumerate(program.pulses):
        limit=int(program.soccfg['gens'][ch]['maxlen'])
        used=max((int(p['addr'])+len(p['data']) for p in pulses.values()),default=0)
        if used>limit: raise ValueError('waveform memory exceeded')
        memory.append(dict(channel=ch,used_samples=used,capacity_samples=limit))
    return dict(instructions=instructions,capacity=capacity,waveform_memory=memory,
                record_words=program.record_words)


def run(*,data_root=localizer.DATA_ROOT,correction_json=None,progress=True,long_hold=False,
        anchor_ghz=None,seed_offset=0,paired_polarity=False):
    request=plan(long_hold=long_hold,anchor_ghz=anchor_ghz,seed_offset=seed_offset,paired_polarity=paired_polarity)
    data_root=Path(data_root)
    correction=localizer.checked_correction(data_root,correction_json)
    prefix='q3_controlled_noise_long_' if long_hold else 'q3_controlled_noise_'
    if paired_polarity:prefix='q3_controlled_noise_paired_'
    folder=data_root/'q3'/(prefix+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    path=folder/'manifest.json'
    manifest=dict(schema='q3.controlled-noise.v1',status='scouting',plan=request,completed=[],
                  created_at=datetime.now(timezone.utc).isoformat(),correction_sha256=localizer.CORRECTION_SHA256)
    manifest['commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=Path(__file__).parent,text=True).strip()
    for name in ('TLSControlledNoise.py','TLSControlledNoiseProgram.py','Q3QuasiparticlePumping.py'):
        source=Path(__file__).with_name(name);shutil.copy2(source,folder/name)
        manifest[name+'_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
    qp.save_json(path,manifest)
    import matplotlib
    matplotlib.use('Agg')
    from tqdm import tqdm
    from . import TLSPumpProbeWidePassiveScan as wide, TLSDualTransitionLoss as dual
    from . import FivePointApplesToApples as five, TLSSpectroscopy as tls
    from .ThreePointApplesToApples import _integer_dc_grid
    from .TLSControlledNoiseProgram import make_program_class
    from ..active_reset_OPX.integration import _run_program
    from ..active_reset_OPX.acquisition import _safe_abort
    soc=None
    try:
        with q3_context(tls,data_root),localizer.scan_environment(correction):
            five.install_scan_calibration(tls)
            scout=localizer.run(data_root=data_root,correction_json=correction,
                                parameter_overrides={**wide.parameters(),'output_suffix':'TLS_Controlled_Noise_Scout'},announce=False)
            manifest['scout_csv']=str(scout)
            selected=select_candidate(dual.read_scout(scout),anchor_ghz=anchor_ghz)
            manifest['selected']=selected
            if selected is None:
                manifest.update(status='complete_no_qualified_feature',completed_at=datetime.now(timezone.utc).isoformat())
                qp.save_json(path,manifest)
                return folder
            center=selected['center_ghz']
            soc,soccfg=tls.makeProxy()
            qp.save_json(folder/'board_configuration.json',soccfg.get_cfg())
            bundle=qp.calibrate(soc,soccfg,folder,'pre',feedback_free=True)
            compensation=tls._load_correction(str(correction),str(data_root))
            cfg=science_config(bundle,tls,compensation)
            qp.save_json(folder/'config.json',cfg)
            run_tasks=tasks(center,selected['control_offset_mhz'],fabric_mhz=soccfg['gens'][cfg['ff_ch']]['f_fabric'],
                            long_hold=long_hold,seed_offset=seed_offset,paired_polarity=paired_polarity)
            requested=sorted({round(t['frequency_ghz']+o/1000,6) for t in run_tasks for o in (-AMPLITUDE_MHZ,0,AMPLITUDE_MHZ)})
            gains,realized=_integer_dc_grid(wide.parameters(),np.asarray(requested),tls)
            lookup=dict(zip(requested,map(int,gains)))
            manifest['flux_grid']=[dict(requested_ghz=f,realized_ghz=float(r),gain=int(g)) for f,r,g in zip(requested,realized,gains)]
            Program=make_program_class()
            def build(task):
                f=task['frequency_ghz']
                # Retain compiler diagnostics (including the known 1-us startup
                # park ramp vs 4-us calibration-context warning) in the run.
                with (folder/'compile.log').open('a',encoding='utf-8') as log, redirect_stdout(log):
                    program=Program(soccfg,cfg,task,bundle.payload,bundle.loop,
                                    center_gain=lookup[f],endpoint_gains=(lookup[round(f-.004,6)],lookup[round(f+.004,6)]))
                return program
            manifest['startup_ramp_note']=(
                '1-us startup/shutdown park ramp matches previous modulation runners; '
                'pinned correction metadata records 4 us. Target/return steps retain '
                'the pinned correction. Each science cell has a 1000-us park wait. '
                'Compiler diagnostics are retained in compile.log.')
            manifest['preflight']=[]
            # Every site/duration (both DAC extrema occur in every realization).
            for task in (run_tasks if paired_polarity else run_tasks[:16]):
                p=build(task)
                manifest['preflight'].append(dict(name=task['name'],**preflight(p),noise=p.waveform_report))
            manifest['status']='acquiring';qp.save_json(path,manifest)
            rows=[]
            conditions_per_shot=10 if paired_polarity else 6
            with tqdm(total=len(run_tasks)*SHOTS*conditions_per_shot,desc='T1 noise comparison',unit='shot',disable=not progress,
                      bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed} elapsed, ETA {remaining}]') as bar:
                for task in run_tasks:
                    manifest['current']=task;qp.save_json(path,manifest)
                    program=build(task)
                    info=preflight(program)
                    stem=folder/task['name']
                    qp.save_json(stem.with_suffix('.json'),dict(task=task,config=program.cfg,
                                                               preflight=info,waveform_report=program.waveform_report))
                    np.savez_compressed(folder/(task['name']+'_waveforms.npz'),**program.waveforms)
                    offset=task['index']*SHOTS*conditions_per_shot
                    def update(done,total): bar.update(offset+int(done)*conditions_per_shot-bar.n)
                    try:
                        records=_run_program(soc,program,60.,cfg,total_shots=SHOTS,progress=update)
                    except BaseException as exc:
                        _safe_abort(soc)
                        partial=getattr(exc,'partial_records',None)
                        if partial is not None:
                            np.savez_compressed(folder/(task['name']+'.partial.npz'),words=np.asarray([[r.i,r.q] for r in partial],dtype=np.int64))
                        raise
                    words=np.asarray([[r.i,r.q] for r in records],dtype=np.int64)
                    np.savez_compressed(stem.with_suffix('.npz'),words=words)
                    new_rows=rows_from_words(words,task,bundle);rows.extend(new_rows)
                    manifest['completed'].append(dict(task=task,rows=new_rows,raw_file=stem.with_suffix('.npz').name,
                                                       completed_at=datetime.now(timezone.utc).isoformat()))
                    qp.save_json(path,manifest)
                    qp.save_json(folder/'summary.json',analyze(rows))
            summary=analyze(rows);plot_summary(folder,summary)
            manifest['status']='post_calibrating';qp.save_json(path,manifest)
            post=qp.calibrate(soc,soccfg,folder,'post',feedback_free=True)
            post_rows=[]
            for entry in manifest['completed']:
                with np.load(folder/entry['raw_file']) as data:
                    post_rows.extend(rows_from_words(data['words'],entry['task'],post))
            qp.save_json(folder/'post_calibration_summary.json',analyze(post_rows))
            manifest.update(status='complete',current=None,completed_at=datetime.now(timezone.utc).isoformat())
            qp.save_json(path,manifest)
    except BaseException as exc:
        if soc is not None: _safe_abort(soc)
        manifest.update(status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',error=f'{type(exc).__name__}: {exc}')
        qp.save_json(path,manifest)
        raise
    finally:
        if soc is not None: _safe_abort(soc)
    return folder


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--plan',action='store_true')
    parser.add_argument('--data-root',default=str(localizer.DATA_ROOT))
    parser.add_argument('--correction-json')
    parser.add_argument('--quiet',action='store_true')
    parser.add_argument('--long-hold',action='store_true',help='1.265/10.193-us comparison using constant flux segments')
    parser.add_argument('--anchor-ghz',type=float,help='select a fresh loss site within ±8 MHz of this frequency')
    parser.add_argument('--seed-offset',type=int,default=0,help='first noise-realization seed (0–1000000)')
    parser.add_argument('--paired-polarity',action='store_true',help='pair each waveform with its inverse; requires --long-hold')
    args=parser.parse_args(argv)
    if args.run: run(data_root=args.data_root,correction_json=args.correction_json,
                     progress=not args.quiet,long_hold=args.long_hold,
                     anchor_ghz=args.anchor_ghz,seed_offset=args.seed_offset,paired_polarity=args.paired_polarity)
    else: print(json.dumps(plan(long_hold=args.long_hold,anchor_ghz=args.anchor_ghz,
                               seed_offset=args.seed_offset,paired_polarity=args.paired_polarity),indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
