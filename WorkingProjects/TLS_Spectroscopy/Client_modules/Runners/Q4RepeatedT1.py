"""Repeated fixed-frequency q4 T1, with independent settings and native reset.

No import or modification of Calib.initialize: snapshot that file (and its
local override) before connecting. Uses the existing OPX T1 sweep and fitter.
The supplied 2-us Gaussian sigma means an 8-us envelope, not qubit_length.
"""

import argparse
import csv
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


DATA_ROOT = 'Z:/FluxTeam/Data/FTT02_AlOxJJ_2026_08_28/RFSOC'
INITIALIZE = Path(__file__).resolve().parents[1] / 'Calib' / 'initialize.py'


def base_config():
    """Fresh, complete q4 config from the user's September 30 settings."""
    return {
        'res_ch': 0, 'qubit_ch': 1, 'ff_ch': 3, 'ro_chs': [0],
        'nqz': 2, 'qubit_nqz': 2, 'ff_nqz': 1, 'mixer_freq': 0.0,
        'cavity_LO': 0, 'reps': 1000, 'relax_delay': 1800,
        'flux_settle_time_us': 0.5, 'ff_ramp_length': 4.0,
        'adc_trig_offset': 0.5, 'res_phase': 165.0,
        'read_pulse_style': 'const', 'read_length': 5.0,
        'readout_guard_us': 1.0, 'read_pulse_gain': 1880,
        'read_pulse_freq': 7026.520,
        'qubit_pulse_style': 'arb', 'qubit_freq': 4367.760,
        'qubit_pi_freq': 4367.760, 'qubit_pi_gain': 32000,
        'qubit_pi2_gain': 16000, 'qubit_drag_beta': 0.0,
        'qubit_anharmonicity_mhz': -180.0, 'qubit_gain': 32000,
        'qubit_length': 0.25, 'sigma': 2.0, 'flat_top_length': None,
        'reset_read_delay_us': 2.0, 'reset_meas_syncdelay_us': 2.0,
        'reset_max_iters': 3, 'ff_park_gain': 0, 'ff_park_settle_us': 1.0,
        'FF_Qubits': {'1': {'channel': 3, 'delay_time': 0.0}},
        'trig_buffer_start': 0.02, 'trig_buffer_end': 0.02,
        'trig_delay': 0.082, 'use_switch': False,
        'cavity_winding_freq': 0, 'cavity_winding_offset': 0,
    }


def delays_us():
    return np.geomspace(1.0, 1500.0, 71)


def plan():
    return {
        'qubit': 'q4', 'reset_mode': 'opx_unbounded',
        'qubit_frequency_mhz': 4367.760, 'readout_frequency_mhz': 7026.520,
        'shots_per_delay': 1000, 'delays_us': delays_us().tolist(),
        'spacing': 'logarithmic', 'default_hours': 12.0,
        'recalibration_minutes': 30.0, 'flux_gain': 0,
    }


def calibration_config():
    from ..active_reset_OPX.benchmark_settings import q3_benchmark_settings
    cfg = base_config()
    cfg.update(q3_benchmark_settings().opx_overrides())
    cfg.update(reset_pi_freq=cfg['qubit_pi_freq'],
               opx_persistent_park=False, opx_hard_flux_steps=False,
               opx_reference_flux_cycle=False, opx_inter_shot_delay_us=1800.0)
    return cfg


def measurement_config(calibration):
    from ..active_reset_OPX.production import ProductionResetSession
    cfg = ProductionResetSession.active(calibration, 4367.760).apply(base_config())
    cfg.update(shots=1000, reps=1000, ff_gain=0, ff_hold_gain=0,
               do_ff=False, do_pi=True, opx_reset_scheme='opx_unbounded',
               opx_park_preroll_us=1800.0)
    return cfg


def snapshot_initialize(output, *, source=INITIALIZE):
    output, source = Path(output), Path(source)
    output.mkdir(parents=True, exist_ok=True)
    report = {}
    for path in (source, source.with_suffix('.local.py')):
        if path.exists():
            target = output / path.name
            with target.open('xb') as stream:
                stream.write(path.read_bytes())
            report[path.name] = {'source': str(path),
                                 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
    if source.name not in report:
        raise FileNotFoundError(source)
    (output / 'snapshot.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def save_json(path, value):
    from ..active_reset_OPX.analysis import json_safe
    from .TLSPumpProbeProtocolCheck import checkpoint
    checkpoint(path, json_safe(value))


SUMMARY_FIELDS = ('index', 'started_at', 'elapsed_s', 'duration_s',
                  'calibration_id', 'T1_us', 'T1_err_us', 'fit_valid',
                  'P0', 'P1', 'raw_file')


def collect_runs(output, *, hours, calibrate, measure, max_runs=None,
                 clock=time.monotonic):
    """Finish each curve, checkpoint it, and stop on any acquisition failure."""
    if not math.isfinite(hours) or hours <= 0:
        raise ValueError('hours must be positive and finite')
    if max_runs is not None and max_runs <= 0:
        raise ValueError('max_runs must be positive')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    started = clock()
    manifest = {**plan(), 'hours': hours, 'max_runs': max_runs,
                'started_at': datetime.now(timezone.utc).isoformat(),
                'status': 'running', 'runs': [], 'current_run': None}
    path = output / 'manifest.json'
    save_json(path, manifest)
    calibration, calibrated_at, calibration_id = None, -math.inf, 0
    try:
        with (output / 't1_summary.csv').open('x', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=SUMMARY_FIELDS, extrasaction='ignore')
            writer.writeheader()
            stream.flush()
            while clock() - started < hours * 3600:
                index = len(manifest['runs']) + 1
                if max_runs is not None and index > max_runs:
                    break
                manifest['current_run'] = index
                if calibration is None or clock() - calibrated_at >= 1800:
                    manifest['stage'] = 'calibration'
                    save_json(path, manifest)
                    calibration_id += 1
                    calibration = calibrate(calibration_id)
                    calibrated_at = clock()
                if clock() - started >= hours * 3600:
                    break
                manifest['stage'] = 'T1'
                save_json(path, manifest)
                result = measure(index, calibration)
                result.update(calibration_id=calibration_id, elapsed_s=clock() - started)
                writer.writerow(result)
                stream.flush()
                manifest['runs'].append(result)
                manifest['elapsed_s'] = clock() - started
                save_json(path, manifest)
        manifest.update(status='complete', stage='complete', current_run=None)
        save_json(path, manifest)
        return manifest
    except BaseException as exc:
        manifest.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
                        error=f'{type(exc).__name__}: {exc}', elapsed_s=clock() - started)
        save_json(path, manifest)
        raise


def calibrate_reset(soc, soccfg, output, index):
    from ..active_reset_OPX.benchmark_settings import q3_benchmark_settings
    from ..active_reset_OPX.calibration import (
        acquire_calibration, save_calibration, save_raw_calibration,
        validate_confident_calibration)
    cfg = calibration_config()
    print('SS cal: q4 readout and active-reset thresholds', flush=True)
    for attempt in range(1, 4):
        folder = Path(output) / f'calibration_{index:04d}_attempt{attempt}'
        folder.mkdir()
        save_json(folder / 'config.json', cfg)
        bundle, raw = acquire_calibration(
            soc, soccfg, cfg, shots=2000,
            **q3_benchmark_settings().calibration_options(),
            metadata={'qubit': 'q4', 'purpose': 'Q4RepeatedT1',
                      'created': datetime.now(timezone.utc).isoformat()})
        save_calibration(folder / 'calibration.json', bundle)
        save_raw_calibration(folder / 'calibration_raw.npz', raw)
        try:
            validate_confident_calibration(bundle, min_confident_fraction=0.2)
        except ValueError:
            if attempt == 3:
                raise
            print('SS cal: insufficient confident assignments; recalibrating', flush=True)
            continue
        print('SS cal complete.', flush=True)
        return {'bundle': bundle.to_dict(), 'file': str(folder / 'calibration.json')}


def reuse_reset_waveform(program):
    """Alias identical q4 envelopes before any reset address is compiled.

    QICK 0.2.133's generator manager and loader share this pulse table. Both
    names may load the same samples at the same address without using a second
    55040-sample slot. Do not replace a differently shaped reset waveform.
    """
    pulses = program.pulses[int(program.cfg['qubit_ch'])]
    payload, reset = pulses['qubit'], pulses['qubit_reset']
    if not np.array_equal(payload['data'], reset['data']):
        raise ValueError('q4 waveform reuse requires identical preparation and reset envelopes')
    pulses['qubit_reset'] = payload


def make_t1_program():
    from ..active_reset_OPX.programs import OPXResetT1SweepProgram

    class Q4T1SweepProgram(OPXResetT1SweepProgram):
        def _declare_experiment(self):
            super()._declare_experiment()
            reuse_reset_waveform(self)

    return Q4T1SweepProgram


def validate_waveform_memory(program):
    """Check addressed sample ranges as well as instruction-memory capacity."""
    report = []
    for ch, pulses in enumerate(program.pulses):
        capacity = int(program.soccfg['gens'][ch]['maxlen'])
        used = 0
        for name, pulse in pulses.items():
            start = int(pulse['addr'])
            end = start + len(pulse['data'])
            if start < 0 or end > capacity:
                raise ValueError(f'channel {ch} {name}: waveform memory range '
                                 f'{start}..{end} exceeds {capacity} samples')
            used = max(used, end)
        report.append({'channel': ch, 'used_samples': used,
                       'capacity_samples': capacity})
    return report


def acquire_curve_iq(soc, program, cfg, progress):
    """Run the exact preflighted program through the existing DMem transport."""
    from ..active_reset_OPX.integration import _run_program, _block_timeout_s
    delays = program.cfg['opx_t1_delays_us']
    shots = int(program.cfg['opx_t1_shots'])
    timing_cfg = dict(cfg, ff_hold=max(delays))
    records = _run_program(soc, program,
                           _block_timeout_s(timing_cfg, shots * len(delays)),
                           cfg, total_shots=shots, progress=progress)
    cycles = int(program.us2cycles(cfg['read_length'], ro_ch=cfg['ro_chs'][0]))
    i_values = np.array([r.final_i for r in records], dtype=float)
    q_values = np.array([r.final_q for r in records], dtype=float)
    return (i_values.reshape(shots, len(delays)).T / cycles,
            q_values.reshape(shots, len(delays)).T / cycles,
            {'shots_per_point': shots, 'points': len(delays), 'blocks': 1,
             'resident_stream': True, 'records': len(records),
             'order': 'shot_delay', 'read_length_cycles': cycles})


def measure_curve(soc, soccfg, output, index, calibration, *, progress=True):
    from ..active_reset_OPX.integration import (
        classify_payload_iq, runtime_bundle)
    from ..Experiments.mCoherence import _fit_exp_decay
    from tqdm import tqdm
    import matplotlib.pyplot as plt

    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    cfg, delays = measurement_config(calibration['bundle']), delays_us()
    stem = Path(output) / f'run_{index:06d}'
    save_json(stem.with_suffix('.config.json'), cfg)
    # Check with the current classifier coefficients before loading hardware.
    bundle = runtime_bundle(cfg)
    compile_cfg = dict(cfg, opx_t1_shots=cfg['shots'],
                       opx_t1_delays_us=delays.tolist(),
                       opx_resident_dmem_stream=True)
    program = make_t1_program()(soccfg, compile_cfg, bundle.payload, bundle.loop)
    words = len(program.compile())
    capacity = int(soccfg['tprocs'][0]['pmem_size'])
    if words > capacity:
        raise RuntimeError(f'T1 program needs {words} instructions; capacity={capacity}')
    memory = validate_waveform_memory(program)
    save_json(stem.with_suffix('.preflight.json'), {
        'program_instructions': words, 'program_capacity': capacity,
        'waveform_memory': memory, 'reset_reuses_preparation_envelope': True})
    with tqdm(total=71000, desc=f'T1 {index}', unit='shot', disable=not progress,
              bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} '
                         '[{elapsed} elapsed, ETA {remaining}]') as bar:
        def update(done, total):
            # Stream progress counts full 71-delay passes, not individual IQs.
            bar.update(int(done) * len(delays) - bar.n)
        try:
            i_values, q_values, telemetry = acquire_curve_iq(soc, program, cfg, update)
        except BaseException as exc:
            partial = getattr(exc, 'partial_records', [])
            if partial:
                np.savez_compressed(stem.with_suffix('.partial.npz'),
                                    i=np.array([r.final_i for r in partial]),
                                    q=np.array([r.final_q for r in partial]))
            raise
    # Preserve IQ even if the fit or plotting fails later.
    np.savez_compressed(stem.with_suffix('.npz'), delays_us=delays,
                        i=i_values, q=q_values)
    save_json(stem.with_suffix('.telemetry.json'), telemetry)
    if i_values.shape != (71, 1000) or q_values.shape != (71, 1000):
        raise RuntimeError(f'Incomplete T1 array: I={i_values.shape}, Q={q_values.shape}')
    classified = classify_payload_iq(cfg, i_values, q_values,
                                    telemetry['read_length_cycles'])
    pe = np.mean(classified, axis=1)
    fit = _fit_exp_decay(delays, pe)
    valid = bool(fit and fit['decaying'] and np.isfinite(fit['tau_err_us']))
    result = {'index': index, 'started_at': started_at,
              'duration_s': time.monotonic() - started,
              'T1_us': fit['tau_us'] if valid else None,
              'T1_err_us': fit['tau_err_us'] if valid else None,
              'fit_valid': valid, 'fit': fit,
              'P0': fit['P0'] if fit else None, 'P1': fit['P1'] if fit else None,
              'raw_file': str(stem.with_suffix('.npz')),
              'calibration_file': calibration['file'],
              'program_instructions': words, 'program_capacity': capacity,
              'waveform_memory': memory,
              'delays_us': delays.tolist(), 'population_pe': pe.tolist()}
    save_json(stem.with_suffix('.json'), result)
    fig, ax = plt.subplots(figsize=(7, 4), constrained_layout=True)
    ax.errorbar(delays, pe, yerr=np.sqrt(pe * (1 - pe) / 1000), fmt='.', capsize=2)
    if valid:
        axis = np.geomspace(delays[0], delays[-1], 400)
        ax.plot(axis, fit['P0'] + (fit['P1'] - fit['P0']) * np.exp(-axis / fit['tau_us']))
        title = f"q4 T1 = {fit['tau_us']:.1f} ± {fit['tau_err_us']:.1f} µs"
        print(f"T1 {index}: {fit['tau_us']:.2f} +/- {fit['tau_err_us']:.2f} us", flush=True)
    else:
        title = 'q4: no valid decaying fit'
        print(f'T1 {index}: invalid fit; raw data saved', flush=True)
    ax.set(xscale='log', xlabel='Delay (µs)', ylabel='P(excited), classified',
           title=title, ylim=(-.05, 1.05))
    fig.savefig(stem.with_suffix('.png'), dpi=140)
    plt.close(fig)
    return result


def run(*, data_root=DATA_ROOT, hours=12.0, max_runs=None, progress=True):
    if not math.isfinite(hours) or hours <= 0 or (max_runs is not None and max_runs <= 0):
        raise ValueError('hours and max_runs must be positive')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = Path(data_root) / 'q4' / f'q4_repeated_t1_{stamp}_{uuid.uuid4().hex[:8]}'
    output.mkdir(parents=True)
    snapshot_initialize(output / 'initialize_snapshot')
    shutil.copyfile(__file__, output / Path(__file__).name)
    save_json(output / 'requested_config.json', base_config())
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=Path(__file__).parent,
                              capture_output=True, text=True, check=True).stdout.strip()
    save_json(output / 'plan.json', {**plan(), 'hours': hours, 'max_runs': max_runs,
                                    'commit': revision})
    print(f'q4 repeated T1: {output}', flush=True)
    import matplotlib
    matplotlib.use('Agg')
    from ..CoreLib.socProxy import makeProxy
    from ..active_reset_OPX.acquisition import _safe_abort
    soc, soccfg = makeProxy()
    save_json(output / 'board_configuration.json', soccfg.get_cfg())
    try:
        result = collect_runs(
            output, hours=hours, max_runs=max_runs,
            calibrate=lambda index: calibrate_reset(soc, soccfg, output, index),
            measure=lambda index, cal: measure_curve(
                soc, soccfg, output, index, cal, progress=progress))
    finally:
        # Includes Ctrl+C, which the shared acquisition layer does not catch.
        _safe_abort(soc)
    print(f'q4 repeated T1 complete: {len(result["runs"])} curves; {output}', flush=True)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--run', action='store_true')
    action.add_argument('--plan', action='store_true')
    parser.add_argument('--data-root', default=DATA_ROOT)
    parser.add_argument('--hours', type=float, default=12.0)
    parser.add_argument('--max-runs', type=int)
    parser.add_argument('--quiet', action='store_true', help='hide progress bars')
    args = parser.parse_args(argv)
    if args.run:
        run(data_root=args.data_root, hours=args.hours, max_runs=args.max_runs,
            progress=not args.quiet)
    else:
        print(json.dumps(plan(), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
