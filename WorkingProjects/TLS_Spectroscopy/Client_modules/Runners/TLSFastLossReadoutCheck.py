"""Compare q3 readout power using the fast-map production calibration timing.

References only: no feedback, flux spectroscopy, automatic installation, or
relaxed quality criteria. Both payload and repeated-readout contexts are saved.
"""
import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import shutil
import subprocess
import uuid

SHOTS = 2000
POWERS = (1880, 940)


def tasks():
    return [dict(name=f'b{block}_gain{gain}', block=block, readout_gain=gain)
            for block, order in enumerate((POWERS, POWERS[::-1])) for gain in order]


def plan():
    return dict(qubit='q3', tasks=tasks(), shots_per_state_per_context=SHOTS,
                contexts=['payload', 'loop'], total_reference_shots=4*4*SHOTS,
                timing='Same per-shot references as production fast-map calibration',
                automatic_calibration_install=False, feedback=False,
                approximate_minutes='1--3; actual transport time may vary',
                purpose='Check whether half-power readout retains both reference contrasts')


def reference_config(gain):
    if isinstance(gain, bool) or gain not in POWERS:
        raise ValueError('readout gain must be 940 or 1880')
    from .Q3QuasiparticlePumping import base_config
    from ..active_reset_OPX.production import build_calibration_config
    base = base_config()
    # Frozen park ramp timing installed by FivePointApplesToApples.
    base.update(dt_pulseplay=.5, dt_pulsedef=.002)
    base['read_pulse_gain'] = int(gain)
    return build_calibration_config(base, base['qubit_pi_freq'])


def reference_report(bundle):
    from ..active_reset_OPX.calibration import validate_confident_calibration
    report = dict(valid=True, rejection=None,
                  payload=dict(bundle.payload.holdout), loop=dict(bundle.loop.holdout),
                  scope='Prepared-reference discrimination; not measured reset fidelity')
    try:
        validate_confident_calibration(bundle, min_confident_fraction=.2)
    except ValueError as exc:
        report.update(valid=False, rejection=str(exc))
    return report


def run(*, data_root=None, progress=True):
    from tqdm.auto import tqdm
    from .TLSPumpProbeLocalizer import DATA_ROOT
    from .TLSPumpProbeProtocolCheck import checkpoint
    from ..CoreLib.socProxy import makeProxy
    from ..active_reset_OPX import calibration, production, programs, classifier, benchmark_settings
    from ..active_reset_OPX.acquisition import _safe_abort
    root = Path(data_root or DATA_ROOT)
    folder = root/'q3'/('q3_fast_loss_readout_check_' +
                       datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True, exist_ok=False)
    sources = {}
    for source in [Path(__file__), *(Path(mod.__file__) for mod in
                     [calibration, production, programs, classifier, benchmark_settings])]:
        shutil.copyfile(source, folder/source.name)
        sources[source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = dict(schema='q3.fast-loss-readout-check.v1', status='initializing',
                    plan=plan(), completed=[], current=None,
                    created_at=datetime.now(timezone.utc).isoformat(), sources=sources,
                    commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                                                   cwd=Path(__file__).parent, text=True).strip())
    path = folder/'manifest.json'
    checkpoint(path, manifest)
    soc = None
    try:
        soc, soccfg = makeProxy()
        checkpoint(folder/'board_configuration.json', soccfg.get_cfg())
        manifest['status'] = 'acquiring'
        with tqdm(total=len(tasks()), desc='SS cal', unit='reference pair', disable=not progress,
                  bar_format='{desc}: {n_fmt}/{total_fmt} [{elapsed} elapsed, ETA {remaining}]') as bar:
            for task in tasks():
                manifest['current'] = dict(task, started_at=datetime.now(timezone.utc).isoformat())
                checkpoint(path, manifest)
                cfg = reference_config(task['readout_gain'])
                checkpoint(folder/(task['name']+'_config.json'), cfg)
                with (folder/'acquisition.log').open('a', encoding='utf-8') as log, redirect_stdout(log):
                    bundle, raw = calibration.acquire_calibration(
                        soc, soccfg, cfg, shots=SHOTS,
                        **benchmark_settings.q3_benchmark_settings().calibration_options(),
                        metadata=dict(task, purpose='TLSFastLossReadoutCheck'))
                calibration.save_calibration(folder/(task['name']+'_calibration.json'), bundle)
                calibration.save_raw_calibration(folder/(task['name']+'_raw.npz'), raw)
                manifest['completed'].append(dict(task=task, report=reference_report(bundle),
                                                  completed_at=datetime.now(timezone.utc).isoformat()))
                checkpoint(path, manifest)
                bar.update(1)
        manifest.update(status='complete', current=None)
    except BaseException as exc:
        manifest.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
                        error=f'{type(exc).__name__}: {exc}')
        if soc is not None:
            try:
                _safe_abort(soc)
            except Exception as cleanup:
                manifest['cleanup_error'] = f'{type(cleanup).__name__}: {cleanup}'
        raise
    finally:
        manifest['finished_at'] = datetime.now(timezone.utc).isoformat()
        checkpoint(path, manifest)
    print(f'SS cal complete: {folder}', flush=True)
    return folder


def main(argv=None):
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--quiet', action='store_true')
    parser.add_argument('--data-root', type=Path)
    args = parser.parse_args(argv)
    if args.run:
        run(data_root=args.data_root, progress=not args.quiet)
    else:
        print(json.dumps(plan(), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
