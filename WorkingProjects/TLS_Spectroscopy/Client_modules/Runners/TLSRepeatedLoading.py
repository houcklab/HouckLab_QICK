"""Finite q3 repeated-loading screen, before any write--erase experiment.

All doses contain 32 visits. The final N visits prepare e; earlier filler
visits prepare g. Every preparation follows fixed-duration feedback reset.
Matched detuned trains, zero-dose trains and short probes test carryover.
"""
import argparse
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import shutil
import subprocess
import uuid
import numpy as np

from . import Q3QuasiparticlePumping as qp
from . import TLSAfterglowDiagonal as diagonal
from . import TLSControlledNoise as noise
from . import TLSPumpProbeHeralded as heralded
from . import TLSPumpProbeLocalizer as localizer

FREQUENCIES_GHZ = (4.020, 4.026, 4.030, 4.037, 4.040, 4.046, 4.060, 4.080)
PILOT_FREQUENCIES_GHZ = (4.026, 4.037, 4.046)
DOSES = (0, 1, 8, 32)
SLOTS, RESET_ROUNDS = 32, 4
PROBES_US = (.1, 40.)
SHOTS, BLOCKS, REFERENCE_SHOTS = 600, 2, 600
LOAD_US, WASHOUT_US, GUARD_US = 10., 5000., 20.
RESET_WORDS = 2 * (RESET_ROUNDS + 1)
RECORD_WORDS = (SLOTS + 1) * RESET_WORDS + 2


def write_schedule(n):
    if not isinstance(n, (int, np.integer)) or not 0 <= n <= SLOTS:
        raise ValueError('write count must be an integer from 0 to 32')
    return [0] * (SLOTS - n) + [1] * n


def feedback_decision(i, q, calibration):
    return calibration.project(i, q) > calibration.excited_threshold


def minimum_ground_confidence(loop):
    ground = float(loop.holdout.get('ground_accept', 1.))
    excited = float(loop.holdout.get('false_ground_accept', 0.))
    return excited + .8 * (ground-excited)


def tasks(*, shots=SHOTS, pilot=False):
    if not isinstance(shots, (int, np.integer)) or shots < 2:
        raise ValueError('shots must be an integer greater than one')
    rng = np.random.default_rng(1102026)
    # Reverse the entire task list AND within-shot probe order for block two.
    frequencies = PILOT_FREQUENCIES_GHZ if pilot else FREQUENCIES_GHZ
    doses = (0, 32) if pilot else DOSES
    base = [(float(f), n, s) for f in rng.permutation(frequencies)
            for n, s in [tuple(x) for x in rng.permutation(
                np.asarray([(n, s) for n in doses for s in ('on', 'off')], dtype=object))]]
    result = []
    for block, order in enumerate((base, base[::-1])):
        for f, n, location in order:
            result.append(dict(index=len(result), name=f'b{block}_f{round(f*1000)}_{location}_n{n}',
                               block=block, frequency_ghz=f, writes=int(n), location=location,
                               load_ghz=round(f - (.016 if location == 'off' else 0), 6),
                               probes_us=list(PROBES_US if block == 0 else PROBES_US[::-1]),
                               shots=int(shots)))
    return result


def plan(*, pilot=False):
    frequencies = PILOT_FREQUENCIES_GHZ if pilot else FREQUENCIES_GHZ
    doses = (0, 32) if pilot else DOSES
    programs = len(frequencies)*len(doses)*2*BLOCKS
    return dict(qubit='q3', mode='pilot' if pilot else 'dose_screen',
                frequencies_ghz=list(frequencies), doses=list(doses),
                visits_per_train=SLOTS, load_us=LOAD_US, probes_us=list(PROBES_US),
                detuned_loading_offset_mhz=-16., detuned_site_is_assumed_quiet=False,
                shots_per_condition_per_block=SHOTS, blocks=BLOCKS,
                science_programs=programs, probe_shots=programs*SHOTS*2,
                reset='four fixed feedback opportunities plus final verification; no early exit',
                reset_rounds=RESET_ROUNDS, return_us=40., washout_between_trials_us=WASHOUT_US,
                washout_inside_train_us=0., raw_words_per_probe=RECORD_WORDS,
                nominal_dose_note='actual reset confidence is recorded at every visit',
                no_loss_site_selection=True, automatic_erase=False, automatic_full_run=False,
                approximate_minutes=('8--12' if pilot else '40--60')+' including calibration, compilation and transport',
                interpretation='exploratory accumulation screen; memory must survive the programmed cycle time')


@dataclass(frozen=True)
class LoadingRecord:
    words: tuple

    def to_words(self):
        return list(self.words)


def decode_records(words, expected_records=None):
    from ..active_reset_OPX.records import signed32
    flat = np.asarray(words).ravel()
    if flat.size % RECORD_WORDS:
        raise ValueError('incomplete repeated-loading record')
    count = flat.size // RECORD_WORDS
    if expected_records is not None and count != expected_records:
        raise ValueError(f'expected {expected_records} records, got {count}')
    signed = np.asarray([signed32(v) for v in flat], dtype=np.int64).reshape(-1, RECORD_WORDS)
    return [LoadingRecord(tuple(map(int, row))) for row in signed]


def summarize_program(words, task, loop, axis, payload=None):
    data = np.asarray(words)
    shots = task['shots']
    if data.shape != (shots * 2, RECORD_WORDS):
        raise ValueError('incomplete short/long repeated-loading stream')
    data = data.reshape(shots, 2, RECORD_WORDS)
    payload = loop if payload is None else payload
    conditions, influences, iq_influences = [], [], []
    for j, t in enumerate(task['probes_us']):
        resets = data[:, j, :-2].reshape(shots, SLOTS + 1, RESET_ROUNDS + 1, 2)
        out_of_range = int(np.count_nonzero(np.any(np.abs(resets) > 32767, axis=(1, 2, 3))))
        flips = feedback_decision(resets[:, :, 0, 0], resets[:, :, 0, 1], payload).astype(int)
        flips += np.sum(feedback_decision(resets[:, :, 1:RESET_ROUNDS, 0],
                                          resets[:, :, 1:RESET_ROUNDS, 1], loop), axis=2)
        verified = loop.project(resets[:, :, -1, 0], resets[:, :, -1, 1]) <= loop.ground_threshold
        mask = verified[:, -1]  # Never condition on the eventual probe outcome.
        projection = heralded._projection(data[:, j, -2] + 1j * data[:, j, -1], axis)
        y = (projection > axis['threshold']).astype(float)
        iq = (projection - axis['low']) / (axis['high'] - axis['low'])
        accepted = int(mask.sum())
        p, v = (float(y[mask].mean()), float(iq[mask].mean())) if accepted else (None, None)
        influences.append(mask * (y-p) / mask.mean() if accepted else np.zeros(shots))
        iq_influences.append(mask * (iq-v) / mask.mean() if accepted else np.zeros(shots))
        dose = np.asarray(write_schedule(task['writes']), dtype=bool)
        confirmed = verified[:, :SLOTS][:, dose].sum(axis=1)
        conditions.append(dict(probe_us=t, accepted=accepted, acceptance=accepted/shots,
                               pe=p, iq=v, all_shot_pe=float(y.mean()), all_shot_iq=float(iq.mean()),
                               reset_confident_by_slot=verified.mean(axis=0).tolist(),
                               mean_feedback_pi_by_slot=flips.mean(axis=0).tolist(),
                               feedback_iq_out_of_range=out_of_range,
                               mean_verified_writes=float(confirmed.mean()),
                               verified_write_fraction=float(confirmed.mean()/task['writes']) if task['writes'] else None))
    cov = np.cov(influences, ddof=1)/shots
    iqcov = np.cov(iq_influences, ddof=1)/shots
    a = np.asarray([-1. if t == .1 else 1. for t in task['probes_us']])
    minimum_confident = minimum_ground_confidence(loop)
    valid = all(c['accepted'] >= max(50, shots*minimum_confident) and c['feedback_iq_out_of_range'] == 0
                for c in conditions)
    # A conservative ground zone can accept <50% of genuinely ground shots.
    # Compare with that classifier's holdout response, not with perfect detection.
    dose_valid = all(c['verified_write_fraction'] is None or c['verified_write_fraction'] >= minimum_confident
                     for c in conditions)
    return dict(block=task['block'], frequency_ghz=task['frequency_ghz'], location=task['location'],
                writes=task['writes'], conditions=conditions, valid=valid and dose_valid,
                write_confidence_minimum=minimum_confident,
                growth=float(a @ [c['pe'] or 0. for c in conditions]) if valid else None,
                growth_error=math.sqrt(max(0., a @ cov @ a)),
                iq_growth=float(a @ [c['iq'] or 0. for c in conditions]) if valid else None,
                iq_growth_error=math.sqrt(max(0., a @ iqcov @ a)),
                all_shot_growth=float(a @ [c['all_shot_pe'] for c in conditions]),
                covariance=cov.tolist(), iq_covariance=iqcov.tolist())


def analyze(cells, *, controls_valid, pilot=False):
    indexed = {(c['frequency_ghz'], c['block'], c['location'], c['writes']): c for c in cells}
    if len(indexed) != len(cells):
        raise ValueError('duplicate accumulation cell')
    sites, candidates, pilot_followups = [], [], []
    for f in sorted({c['frequency_ghz'] for c in cells}):
        dose_reports = []
        for n in ((32,) if pilot else DOSES[1:]):
            blocks = []
            for b in range(BLOCKS):
                group = [indexed.get((f, b, loc, dose))
                         for loc, dose in (('on', n), ('on', 0), ('off', n), ('off', 0))]
                if not all(c and c['valid'] for c in group):
                    continue
                g = np.array([c['growth'] for c in group])
                q = np.array([c['iq_growth'] for c in group])
                variance = np.array([c['growth_error']**2 for c in group])
                blocks.append(dict(block=b, on=float(g[0]-g[1]), off=float(g[2]-g[3]),
                                   local=float(g @ [1,-1,-1,1]), variance=float(variance.sum()),
                                   on_variance=float(variance[:2].sum()),
                                   iq_local=float(q @ [1,-1,-1,1]),
                                   iq_on=float(q[0]-q[1])))
            report = dict(writes=n, blocks=blocks, valid=len(blocks) == BLOCKS)
            for key in ('on', 'local'):
                if blocks:
                    values = [v[key] for v in blocks]
                    varname = 'on_variance' if key == 'on' else 'variance'
                    variance = sum(v[varname] for v in blocks)/len(blocks)**2
                    if len(blocks) > 1:
                        variance = max(variance, float(np.var(values, ddof=1)/len(blocks)))
                    report[key] = float(np.mean(values))
                    report[key+'_error'] = math.sqrt(variance)
            dose_reports.append(report)
        high = dose_reports[-1]
        eligible = bool(controls_valid and all(v['valid'] for v in dose_reports)
                        and high.get('on', 0.) > max(.03, 3.35*high.get('on_error', math.inf))
                        and high.get('local', 0.) > max(.03, 3.35*high.get('local_error', math.inf))
                        and (pilot or high.get('on', 0.) > dose_reports[0].get('on', math.inf))
                        and all(v['on'] > .02 and v['local'] > .02
                                and v['iq_on'] > 0 and v['iq_local'] > 0 for v in high['blocks']))
        if eligible:
            (pilot_followups if pilot else candidates).append(f)
        sites.append(dict(frequency_ghz=f, doses=dose_reports, candidate=eligible and not pilot,
                          pilot_followup=eligible and pilot))
    return dict(controls_valid=bool(controls_valid), sites=sites,
                candidate_frequencies_ghz=candidates, automatic_erase=False, automatic_full_run=False,
                pilot_followup_frequencies_ghz=pilot_followups, dose_dependence_tested=not pilot,
                interpretation=('pilot: zero-versus-32 return contrast only; no dose curve; a null does not exclude smaller signals or other sites' if pilot else
                                'exploratory only; inspect reset histories, order effects and post calibration; no automatic erase'))


def reference_tasks(phase):
    return [dict(name=f'ref_{s}_{phase}', shots=REFERENCE_SHOTS, writes=0,
                 location='on', load_ghz=4.040, frequency_ghz=4.040, block=-1,
                 probes_us=[.1], reference_state=s) for s in ('g', 'e')]


def calibration_config():
    cfg = qp.calibration_config()
    cfg.update(opx_feedback_syncdelay_us=GUARD_US, opx_loop_recovery_us=GUARD_US,
               opx_inter_shot_delay_us=1000.)
    return cfg


def calibrate(soc, soccfg, folder):
    """Fresh classifier with this experiment's readout train and zero-pi timing."""
    import json
    import qick
    from .TLSRepeatedLoadingProgram import LoadingReferenceProgram
    from ..active_reset_OPX.acquisition import chunk_sizes, dmem_words_from_soccfg, run_dmem_block
    from ..active_reset_OPX.records import max_records
    from ..active_reset_OPX.calibration import CalibrationBundle, save_calibration, save_raw_calibration
    from ..active_reset_OPX.classifier import fit_classifier
    from ..active_reset_OPX.analysis import ReferenceAxis
    from ..active_reset_OPX.benchmark_settings import q3_benchmark_settings
    cfg = calibration_config()
    capacity = max_records(dmem_words_from_soccfg(soccfg), cfg.get('opx_record_base', 32), 2)
    for attempt in range(1, 4):
        print('SS cal: q3 fixed-reset readout references', flush=True)
        out = Path(folder)/f'calibration_pre_{attempt}'
        out.mkdir()
        qp.save_json(out/'config.json', cfg)
        raw, fits = {}, {}
        for context in ('payload', 'loop'):
            raw[context] = {}
            for state in ('ground', 'excited'):
                records = []
                for count in chunk_sizes(2000, capacity):
                    p = LoadingReferenceProgram(soccfg, dict(cfg, reps=count, shots=count,
                                                            opx_reference_context=context,
                                                            prep_excited=state=='excited'))
                    noise.preflight(p)
                    records.extend(run_dmem_block(soc, p, timeout_s=20.))
                raw[context][state] = dict(i=np.asarray([r.final_i for r in records]),
                                           q=np.asarray([r.final_q for r in records]))
            g, e = raw[context]['ground'], raw[context]['excited']
            # Preserve each context even if fitting the next context fails.
            np.savez_compressed(out/(context+'_raw.npz'), ground_i=g['i'], ground_q=g['q'],
                                excited_i=e['i'], excited_q=e['q'])
            fits[context] = fit_classifier(g['i'], g['q'], e['i'], e['q'], context=context,
                                            **q3_benchmark_settings().calibration_options())
        save_raw_calibration(out/'raw.npz', raw)
        g, e = raw['loop']['ground'], raw['loop']['excited']
        axis = ReferenceAxis.from_centers(g['i'].mean(), g['q'].mean(), e['i'].mean(), e['q'].mean())
        bundle = CalibrationBundle(1, fits['payload'], fits['loop'], axis,
                                   dict(purpose='TLSRepeatedLoading', qubit='q3',
                                        qick_version=qick.__version__,
                                        created_at=datetime.now(timezone.utc).isoformat(),
                                        config_sha256=hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest(),
                                        shots_per_state_per_context=2000,
                                        fixed_reset_rounds=RESET_ROUNDS, guard_us=GUARD_US,
                                        ground_reference_plays_zero_gain_waveform=True))
        save_calibration(out/'calibration.json', bundle)
        try:
            qp.validate_reference(bundle)
        except ValueError:
            if attempt == 3:
                raise
            continue
        print('SS cal complete.', flush=True)
        return bundle


def reference_axis(ground, excited, loop, *, frozen=None):
    def values(words):
        w = np.asarray(words)
        keep = loop.project(w[:, -4], w[:, -3]) <= loop.ground_threshold
        return w[keep, -2] + 1j*w[keep, -1], float(keep.mean())
    g, ga = values(ground); e, ea = values(excited)
    # Fit alternating shots, validate the held-out half; frozen-axis validation
    # uses the complete independent mid/post references.
    invalid = dict(valid=False, axis=frozen, ground_acceptance=ga, excited_acceptance=ea)
    if min(len(g), len(e)) < 100:
        return dict(invalid, reason='too few ground-conditioned reference shots')
    try:
        axis = heralded.fit_readout_axis(g[::2], e[::2]) if frozen is None else dict(frozen)
    except (RuntimeError, ValueError) as exc:
        return dict(invalid, reason=str(exc))
    gv = heralded._projection(g[1::2] if frozen is None else g, axis)
    ev = heralded._projection(e[1::2] if frozen is None else e, axis)
    fidelity = float((np.mean(gv < axis['threshold'])+np.mean(ev > axis['threshold']))/2)
    if frozen is None:
        axis.update(low=float(np.median(heralded._projection(g[::2], axis))),
                    high=float(np.median(heralded._projection(e[::2], axis))))
    return dict(axis=axis, fidelity=fidelity, ground_acceptance=ga, excited_acceptance=ea,
                valid=bool(len(gv) >= 50 and len(ev) >= 50 and fidelity >= .75
                           and min(ga, ea) >= minimum_ground_confidence(loop)
                           and axis['high'] > axis['low']))


def build_program(soccfg, base, task, lookup, bundle):
    from .TLSRepeatedLoadingProgram import RepeatedLoadingProgram
    cfg = dict(base, ff_gain=lookup[task['load_ghz']], ff_hold=LOAD_US,
               loading_task=task, loading_probe_gain=lookup[task['frequency_ghz']],
               reps=task['shots']*len(task['probes_us']))
    return RepeatedLoadingProgram(soccfg, cfg, bundle.payload, bundle.loop)


def plot_summary(folder, summary):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True, constrained_layout=True)
    for site in summary['sites']:
        reports = [d for d in site['doses'] if d['valid']]
        if not reports:
            continue
        for ax, key in zip(axes, ('on', 'local')):
            ax.errorbar([d['writes'] for d in reports], [d[key] for d in reports],
                        yerr=[d[key+'_error'] for d in reports], fmt='o-',
                        label=f"{site['frequency_ghz']:.3f} GHz")
    axes[0].set(title='q3 repeated loading: excitation acquired during probing',
                ylabel='On-target growth minus zero dose')
    axes[1].set(xlabel='Nominal excited writes (32 total visits)',
                ylabel='On-target minus detuned growth')
    for ax in axes:
        ax.axhline(0, color='k', lw=.8); ax.grid(alpha=.25)
        if ax.lines:
            ax.legend(fontsize=8, ncol=4)
    if not summary['controls_valid']:
        fig.suptitle('Reference controls unvalidated: descriptive only', color='darkred')
    fig.savefig(Path(folder)/'repeated_loading.png', dpi=160)
    plt.close(fig)


def run(*, data_root=localizer.DATA_ROOT, correction_json=None, progress=True, pilot=False):
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    prefix = 'q3_repeated_loading_pilot_' if pilot else 'q3_repeated_loading_'
    folder = data_root/'q3'/(prefix+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    manifest = dict(schema='q3.repeated-loading.v1', status='initializing', plan=plan(pilot=pilot),
                    completed=[], references={}, created_at=datetime.now(timezone.utc).isoformat(),
                    correction_sha256=localizer.CORRECTION_SHA256,
                    commit=subprocess.check_output(['git','rev-parse','HEAD'], cwd=Path(__file__).parent, text=True).strip())
    path = folder/'manifest.json'
    for name in ('TLSRepeatedLoading.py','TLSRepeatedLoadingProgram.py','TLSAfterglowDiagonal.py',
                 'TLSPumpProbeHeralded.py','Q3QuasiparticlePumping.py'):
        source = Path(__file__).with_name(name)
        shutil.copy2(source, folder/name)
        manifest[name+'_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    qp.save_json(path, manifest)
    import matplotlib
    matplotlib.use('Agg')
    from tqdm import tqdm
    from . import FivePointApplesToApples as five, TLSSpectroscopy as tls
    from . import TLSPumpProbeWidePassiveScan as wide
    from .ThreePointApplesToApples import _integer_dc_grid
    from ..active_reset_OPX.integration import _run_program
    soc = None
    try:
        with noise.q3_context(tls, data_root), localizer.scan_environment(correction):
            five.install_scan_calibration(tls)
            run_tasks = tasks(pilot=pilot)
            grid = sorted({t[k] for t in run_tasks + reference_tasks('pre')
                           for k in ('frequency_ghz','load_ghz')})
            gains, realized = _integer_dc_grid(dict(wide.parameters(), freq_step_mhz=1.), np.asarray(grid), tls)
            lookup = dict(zip(grid, map(int, gains)))
            cfg = diagonal.science_config(tls, tls._load_correction(str(correction), str(data_root)))
            soc, soccfg = tls.makeProxy()
            qp.save_json(folder/'board_configuration.json', soccfg.get_cfg())
            bundle = calibrate(soc, soccfg, folder)
            # Existing calibrator only supplies thresholds; the fixed reset is
            # experiment-local and never changes the production reset policy.
            qp.save_json(folder/'config.json', cfg)
            manifest['flux_grid'] = [dict(requested_ghz=f, realized_ghz=float(r), gain=g)
                                     for f, r, g in zip(grid, realized, map(int, gains))]
            def build(task):
                with (folder/'compile.log').open('a', encoding='utf-8') as log, redirect_stdout(log):
                    return build_program(soccfg, cfg, task, lookup, bundle)
            manifest['preflight'] = []
            for task in run_tasks + reference_tasks('pre'):
                p = build(task)
                manifest['preflight'].append(dict(name=task['name'], timing=p.timing,
                                                   **noise.preflight(p)))
            qp.save_json(path, manifest)

            def acquire(task, callback=None):
                p = build(task)
                manifest['current'] = task
                qp.save_json(path, manifest)
                qp.save_json(folder/(task['name']+'.json'), dict(task=task, config=p.cfg,
                                                               timing=p.timing, preflight=noise.preflight(p)))
                try:
                    records = _run_program(soc, p, 90., cfg, total_shots=task['shots'], progress=callback)
                except BaseException as exc:
                    diagonal.abort_and_record(soc, manifest)
                    if getattr(exc, 'partial_records', None) is not None:
                        np.savez_compressed(folder/(task['name']+'.partial.npz'),
                                            words=np.asarray([r.to_words() for r in exc.partial_records], dtype=np.int64))
                    raise
                words = np.asarray([r.to_words() for r in records], dtype=np.int64)
                np.savez_compressed(folder/(task['name']+'.npz'), words=words)
                if words.shape != (task['shots']*len(task['probes_us']), RECORD_WORDS):
                    raise RuntimeError('incomplete repeated-loading acquisition')
                return words

            raw = {}
            def references(phase, frozen=None):
                print('SS cal: fixed-reset and final-readout checks', flush=True)
                for task in reference_tasks(phase):
                    raw[task['name']] = acquire(task)
                g, e = [raw[f'ref_{s}_{phase}'] for s in ('g','e')]
                result = reference_axis(g, e, bundle.loop, frozen=frozen)
                manifest['references'][phase] = result
                qp.save_json(path, manifest)
                print('SS cal complete.' if result['valid'] else 'SS cal checks failed.', flush=True)
                return result

            pre = references('pre')
            if not pre['valid']:
                raise RuntimeError('fixed-reset/reference validation failed; science was not started')
            axis, cells = pre['axis'], []
            manifest['status'] = 'acquiring'
            offset = 0
            with tqdm(total=sum(t['shots']*2 for t in run_tasks), desc='Repeated loading', unit='shot', disable=not progress,
                      bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed} elapsed, ETA {remaining}]') as bar:
                for task in run_tasks:
                    if task['index'] == len(run_tasks)//2:
                        references('mid', axis)
                    def update(done, total):
                        bar.update(offset + int(done)*2 - bar.n)
                    words = acquire(task, update)
                    offset += task['shots']*2
                    cell = summarize_program(words, task, bundle.loop, axis, bundle.payload)
                    cells.append(cell)
                    manifest['completed'].append(dict(task=task, summary=cell, raw_file=task['name']+'.npz'))
                    qp.save_json(path, manifest)
                    qp.save_json(folder/'summary.json', analyze(cells, controls_valid=False, pilot=pilot))
            post = references('post', axis)
            valid = all(manifest['references'][p]['valid'] for p in ('pre','mid','post'))
            summary = analyze(cells, controls_valid=valid, pilot=pilot)
            qp.save_json(folder/'summary.json', summary)
            plot_summary(folder, summary)
            fitted = reference_axis(raw['ref_g_post'], raw['ref_e_post'], bundle.loop)
            manifest['references']['post_refit'] = fitted
            post_cells = []
            if fitted['axis'] is not None:
                for entry in manifest['completed']:
                    with np.load(folder/entry['raw_file']) as saved:
                        post_cells.append(summarize_program(saved['words'], entry['task'], bundle.loop, fitted['axis'], bundle.payload))
            post_summary = analyze(post_cells, controls_valid=valid and fitted['valid'], pilot=pilot)
            post_summary['sensitivity_check'] = 'final-readout axis refit only; hardware reset classifier remains frozen'
            qp.save_json(folder/'post_calibration_summary.json', post_summary)
            manifest.update(status='complete' if valid else 'complete_controls_uncertain', current=None)
    except BaseException as exc:
        diagonal.abort_and_record(soc, manifest)
        manifest.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
                        error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        diagonal.abort_and_record(soc, manifest)
        manifest['completed_at'] = datetime.now(timezone.utc).isoformat()
        qp.save_json(path, manifest)
    return folder


def main(argv=None):
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--quiet', action='store_true')
    parser.add_argument('--pilot', action='store_true', help='short zero-versus-32 pilot at three sites; stops for review')
    parser.add_argument('--data-root', default=str(localizer.DATA_ROOT))
    parser.add_argument('--correction-json')
    args = parser.parse_args(argv)
    if args.plan or not args.run:
        print(json.dumps(plan(pilot=args.pilot), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json, progress=not args.quiet, pilot=args.pilot)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
