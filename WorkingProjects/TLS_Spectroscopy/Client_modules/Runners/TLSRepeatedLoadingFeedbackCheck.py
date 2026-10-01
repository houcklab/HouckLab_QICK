"""Bounded q3 half-gain feedback test before resuming repeated TLS loading.

Compare four fixed feedback opportunities with equal-time zero-gain pulses,
from both nominal g and e initial preparations. Save five weak IQ pairs and
an independent strong final readout. No flux excursions or automatic loading.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import uuid

import numpy as np

from . import TLSRepeatedLoading as loading

SHOTS = 500
RECORD_WORDS = 12


def tasks():
    def refs(phase, states):
        return [dict(name=f'ref_{s}_{phase}', initial_state='g', reference_state=s,
                     feedback=False, block=-1, shots=SHOTS) for s in states]
    base = [(s, f) for s in ('g', 'e') for f in (False, True)]
    science = [dict(name=f'b{b}_{s}_{"feedback" if f else "sham"}', initial_state=s,
                    reference_state=None, feedback=f, block=b, shots=SHOTS)
               for b, order in enumerate((base, base[::-1])) for s, f in order]
    return refs('pre', ('g', 'e')) + science + refs('post', ('e', 'g'))


def plan(*, conservative=False):
    return dict(qubit='q3', feedback_readout_gain=940, final_readout_gain=1880,
                feedback_rounds=4, weak_readouts_per_trial=5,
                shots_per_condition_per_block=SHOTS, blocks=2,
                total_probe_shots=12*SHOTS, calibration_shots=8000,
                recovery_us=1000., guard_us=20., approximate_minutes='1--3',
                false_pi_training_limit=.02 if conservative else None,
                false_pi_holdout_maximum=.04 if conservative else None,
                automatic_loading=False, automatic_calibration_install=False,
                note='Compare all shots and ground-conditioned shots; classification fractions are not absolute reset fidelity.')


def decode_records(words, expected_records=None):
    from ..active_reset_OPX.records import signed32
    flat = np.asarray(words).ravel()
    if flat.size % RECORD_WORDS:
        raise ValueError('incomplete feedback-check record')
    n = flat.size//RECORD_WORDS
    if expected_records is not None and n != expected_records:
        raise ValueError('unexpected feedback-check record count')
    signed = np.asarray([signed32(v) for v in flat]).reshape(n, RECORD_WORDS)
    return [loading.LoadingRecord(tuple(map(int, row))) for row in signed]


def program_config(task):
    cfg = loading.calibration_config(readout_gain=940)
    cfg.update(reps=task['shots'], shots=task['shots'], check_initial_state=task['initial_state'],
               check_reference_state=task['reference_state'], check_feedback=task['feedback'],
               reset_pi_gain=cfg['qubit_pi_gain'] if task['feedback'] else 0)
    return cfg


def summarize_records(words, axis, bundle, *, feedback):
    w = np.asarray(words)
    if w.ndim != 2 or w.shape[1] != RECORD_WORDS or len(w) < 2:
        raise ValueError('incomplete feedback-check data')
    r = w[:, :10].reshape(-1, 5, 2)
    out_of_range = np.any(np.abs(r) > 32767, axis=(1, 2))
    confident = bundle.loop.project(r[:, -1, 0], r[:, -1, 1]) <= bundle.loop.ground_threshold
    projected = loading.heralded._projection(w[:, -2]+1j*w[:, -1], axis)
    y = projected > axis['threshold']
    iq = (projected-axis['low'])/(axis['high']-axis['low'])
    flips = loading.feedback_decision(r[:, 0, 0], r[:, 0, 1], bundle.payload).astype(int)
    flips += loading.feedback_decision(r[:, 1:4, 0], r[:, 1:4, 1], bundle.loop).sum(axis=1)
    n = int(confident.sum())
    return dict(shots=len(w), ground_verification_fraction=float(confident.mean()), accepted=n,
                final_excited_all=float(y.mean()),
                final_excited_given_ground=float(y[confident].mean()) if n else None,
                normalized_iq_all=float(iq.mean()),
                normalized_iq_given_ground=float(iq[confident].mean()) if n else None,
                mean_feedback_pi_count=float(flips.mean()) if feedback else 0.,
                feedback_iq_out_of_range=int(out_of_range.sum()))


def analyze(raw, entries, bundle):
    def iq(name):
        w = raw[name]
        return w[:, -2]+1j*w[:, -1]
    def ref(phase, frozen=None):
        g, e = iq('ref_g_'+phase), iq('ref_e_'+phase)
        result = dict(valid=False, axis=None)
        try:
            axis = dict(frozen) if frozen else loading.heralded.fit_readout_axis(g[::2], e[::2])
            if frozen is None:
                axis.update(low=float(np.median(loading.heralded._projection(g[::2], axis))),
                            high=float(np.median(loading.heralded._projection(e[::2], axis))))
            a, b = (g, e) if frozen else (g[1::2], e[1::2])
            pg = float(np.mean(loading.heralded._projection(a, axis) > axis['threshold']))
            pe = float(np.mean(loading.heralded._projection(b, axis) > axis['threshold']))
            fidelity = (1-pg+pe)/2
            result.update(valid=fidelity >= .75 and axis['high'] > axis['low'], axis=axis,
                          fidelity=fidelity, ground_excited_fraction=pg, excited_excited_fraction=pe)
        except (ValueError, RuntimeError) as exc:
            result['error'] = str(exc)
        return result
    pre = ref('pre')
    post = ref('post', pre['axis']) if pre['axis'] else dict(valid=False)
    post_refit = ref('post')
    cells, post_cells = [], []
    for entry in entries:
        task = entry['task']
        if task['reference_state'] is not None:
            continue
        for target, axis in ((cells, pre['axis']), (post_cells, post_refit['axis'])):
            if axis:
                target.append(dict(task=task, **summarize_records(raw[task['name']], axis, bundle,
                                                                 feedback=task['feedback'])))
    return dict(references=dict(pre=pre, post=post, post_refit=post_refit), cells=cells,
                post_refit_cells=post_cells,
                controls_valid=bool(pre['valid'] and post['valid'] and all(c['feedback_iq_out_of_range']==0 for c in cells)),
                automatic_loading=False, interpretation=plan()['note'])


def run(*, data_root=loading.localizer.DATA_ROOT, progress=True, conservative=False):
    from tqdm.auto import tqdm
    from . import TLSSpectroscopy as tls
    from .TLSRepeatedLoadingProgram import LoadingFeedbackCheckProgram
    from ..active_reset_OPX.acquisition import chunk_sizes, dmem_words_from_soccfg, run_dmem_block
    from ..active_reset_OPX.records import max_records
    data_root = Path(data_root)
    folder = data_root/'q3'/('q3_repeated_loading_feedback_check_'+
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    path = folder/'manifest.json'
    manifest = dict(schema='q3.repeated-loading-feedback-check.v1', plan=plan(conservative=conservative), status='initializing',
                    completed=[], created_at=datetime.now(timezone.utc).isoformat(),
                    commit=subprocess.check_output(['git','rev-parse','HEAD'], cwd=Path(__file__).parent, text=True).strip())
    loading.qp.save_json(path, manifest)
    soc = None
    try:
        with loading.noise.q3_context(tls, data_root):
            soc, soccfg = tls.makeProxy()
            loading.qp.save_json(folder/'board_configuration.json', soccfg.get_cfg())
            bundle = loading.calibrate(soc, soccfg, folder, readout_gain=940, attempts=1,
                                       false_pi_limit=.02 if conservative else None)
            manifest['status'] = 'acquiring'
            capacity = max_records(dmem_words_from_soccfg(soccfg), 32, RECORD_WORDS)
            raw = {}
            with tqdm(total=plan()['total_probe_shots'], desc='Reset check', unit='shot', disable=not progress,
                      bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed} elapsed, ETA {remaining}]') as bar:
                for task in tasks():
                    manifest['current'] = task
                    loading.qp.save_json(path, manifest)
                    cfg = program_config(task)
                    loading.qp.save_json(folder/(task['name']+'_config.json'), cfg)
                    records = []
                    for count in chunk_sizes(task['shots'], capacity):
                        p = LoadingFeedbackCheckProgram(soccfg, dict(cfg, reps=count, shots=count), bundle.payload, bundle.loop)
                        loading.noise.preflight(p)
                        try:
                            records.extend(run_dmem_block(soc, p, timeout_s=20.))
                        except BaseException as exc:
                            loading.diagonal.abort_and_record(soc, manifest)
                            records.extend(getattr(exc, 'partial_records', None) or [])
                            np.savez_compressed(folder/(task['name']+'.partial.npz'),
                                                words=np.asarray([r.to_words() for r in records]))
                            raise
                        np.savez_compressed(folder/(task['name']+'.partial.npz'),
                                            words=np.asarray([r.to_words() for r in records]))
                        bar.update(count)
                    words = np.asarray([r.to_words() for r in records])
                    if words.shape != (task['shots'], RECORD_WORDS):
                        raise RuntimeError('incomplete feedback-check acquisition')
                    np.savez_compressed(folder/(task['name']+'.npz'), words=words)
                    (folder/(task['name']+'.partial.npz')).unlink()
                    raw[task['name']] = words
                    manifest['completed'].append(dict(task=task, raw_file=task['name']+'.npz'))
                    loading.qp.save_json(path, manifest)
            summary = analyze(raw, manifest['completed'], bundle)
            loading.qp.save_json(folder/'summary.json', summary)
            manifest.update(status='complete' if summary['controls_valid'] else 'complete_controls_uncertain', current=None)
    except BaseException as exc:
        loading.diagonal.abort_and_record(soc, manifest)
        manifest.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        loading.diagonal.abort_and_record(soc, manifest)
        manifest['completed_at'] = datetime.now(timezone.utc).isoformat()
        loading.qp.save_json(path, manifest)
    return folder


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--quiet', action='store_true')
    parser.add_argument('--conservative', action='store_true', help='calibrate a 2%% false-correction target on training ground shots')
    parser.add_argument('--data-root', default=str(loading.localizer.DATA_ROOT))
    args = parser.parse_args(argv)
    if args.run:
        run(data_root=args.data_root, progress=not args.quiet, conservative=args.conservative)
    else:
        print(json.dumps(plan(conservative=args.conservative), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
