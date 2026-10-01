"""Short park-only readout-train diagnostic; no feedback or TLS loading.

Test how prior readouts, their spacing and their drive affect nominal g/pi
references. Failed fits are results, not reasons to repeat or relax a gate.
No diagnostic classifier is installed in the loading experiment.
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
PROFILES = (
    ('no_prior', 0, 20., 1880),
    ('one_prior', 1, 20., 1880),
    ('two_prior', 2, 20., 1880),
    ('four_prior', 4, 20., 1880),
    ('four_guard50', 4, 50., 1880),
    ('four_guard100', 4, 100., 1880),
    ('four_zero_drive', 4, 20., 0),
    ('four_half_drive', 4, 20., 940),
)


def tasks():
    return [dict(name=f'b{block}_{p[0]}', profile=p[0], rounds=p[1],
                 guard_us=p[2], prior_gain=p[3], block=block, shots=SHOTS,
                 states=['ground', 'excited'] if block == 0 else ['excited', 'ground'])
            for block, order in enumerate((PROFILES, PROFILES[::-1])) for p in order]


def plan():
    return dict(qubit='q3', profiles=[p[0] for p in PROFILES], blocks=2,
                shots_per_state_per_block=SHOTS, total_reference_shots=16*2*SHOTS,
                approximate_minutes='1--3 including program transport',
                final_readout_gain=1880, automatic_calibration_install=False,
                feedback=False, tls_loading=False,
                note='Nominal g/pi references after prior readouts; this does not measure reset fidelity.')


def profile_config(task):
    cfg = loading.calibration_config()
    cfg.update(opx_reference_context='loop', loading_reference_rounds=task['rounds'],
               loading_reference_guard_us=task['guard_us'],
               loading_reference_prior_gain=task['prior_gain'])
    loading.reference_settings(cfg)
    return cfg


def reference_report(raw):
    from ..active_reset_OPX.classifier import fit_classifier
    from ..active_reset_OPX.benchmark_settings import q3_benchmark_settings
    report = dict(passes_loop_guard=False, fit_error=None)
    try:
        cal = fit_classifier(raw['ground_i'], raw['ground_q'], raw['excited_i'], raw['excited_q'],
                             context='loop', **q3_benchmark_settings().calibration_options())
        report['classifier'] = cal.to_dict()
        cal.assembly_plan()
        report['passes_loop_guard'] = bool(
            cal.holdout['ground_accept'] >= .2 and cal.holdout['excited_fire'] >= .2)
    except ValueError as exc:
        report['fit_error'] = str(exc)
    return report


def run(*, data_root=loading.localizer.DATA_ROOT, progress=True):
    from tqdm.auto import tqdm
    from . import TLSSpectroscopy as tls
    from .TLSRepeatedLoadingProgram import LoadingReferenceProgram
    from ..active_reset_OPX.acquisition import chunk_sizes, dmem_words_from_soccfg, run_dmem_block
    from ..active_reset_OPX.records import max_records

    data_root = Path(data_root)
    folder = data_root/'q3'/('q3_repeated_loading_reset_check_' +
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    path = folder/'manifest.json'
    manifest = dict(schema='q3.repeated-loading-reset-check.v1', plan=plan(),
                    status='initializing', completed=[], current=None,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    commit=subprocess.check_output(['git','rev-parse','HEAD'],
                        cwd=Path(__file__).parent, text=True).strip())
    loading.qp.save_json(path, manifest)
    soc = None
    try:
        with loading.noise.q3_context(tls, data_root):
            soc, soccfg = tls.makeProxy()
            loading.qp.save_json(folder/'board_configuration.json', soccfg.get_cfg())
            manifest['status'] = 'acquiring'
            capacity = max_records(dmem_words_from_soccfg(soccfg), 32, 2)
            with tqdm(total=plan()['total_reference_shots'], desc='SS cal', unit='shot',
                      disable=not progress,
                      bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed} elapsed, ETA {remaining}]') as bar:
                for task in tasks():
                    manifest['current'] = dict(task=task, started_at=datetime.now(timezone.utc).isoformat())
                    loading.qp.save_json(path, manifest)
                    cfg = profile_config(task)
                    loading.qp.save_json(folder/(task['name']+'_config.json'), cfg)
                    raw = {}
                    for state in task['states']:
                        records = []
                        for count in chunk_sizes(task['shots'], capacity):
                            p = LoadingReferenceProgram(soccfg, dict(cfg, reps=count, shots=count,
                                prep_excited=state == 'excited'))
                            loading.noise.preflight(p)
                            try:
                                records.extend(run_dmem_block(soc, p, timeout_s=20.))
                            except BaseException as exc:
                                records.extend(getattr(exc, 'partial_records', None) or [])
                                np.savez_compressed(folder/(task['name']+'_'+state+'.partial.npz'),
                                    i=np.asarray([r.final_i for r in records]),
                                    q=np.asarray([r.final_q for r in records]))
                                raise
                            bar.update(count)
                        raw[state+'_i'] = np.asarray([r.final_i for r in records])
                        raw[state+'_q'] = np.asarray([r.final_q for r in records])
                        # Retain the first state even if the second acquisition fails.
                        np.savez_compressed(folder/(task['name']+'.npz'), **raw)
                    report = reference_report(raw)
                    manifest['completed'].append(dict(task=task, report=report,
                        raw_file=task['name']+'.npz', completed_at=datetime.now(timezone.utc).isoformat()))
                    loading.qp.save_json(path, manifest)
            manifest.update(status='complete', current=None)
    except BaseException as exc:
        loading.diagonal.abort_and_record(soc, manifest)
        manifest.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
                        error=f'{type(exc).__name__}: {exc}')
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
    parser.add_argument('--data-root', default=str(loading.localizer.DATA_ROOT))
    args = parser.parse_args(argv)
    if args.run:
        run(data_root=args.data_root, progress=not args.quiet)
    else:
        print(json.dumps(plan(), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
