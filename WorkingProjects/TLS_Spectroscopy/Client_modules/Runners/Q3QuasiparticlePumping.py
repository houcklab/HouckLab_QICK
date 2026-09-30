"""Finite q3 park-frequency quasiparticle-pumping screen.

No TLS scout or flux excursion. Equal-duration idle, spaced pi trains and
equal-count +pi/-pi pairs precede matched ground/excited relaxation probes.
Fresh active reset separates conditioning from probing; its complete telemetry
is retained because feedback can itself perturb or erase the conditioned bath.
--feedback-free instead uses passive preparation and one final readout only.
"""

import argparse
from dataclasses import dataclass
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
ARMS = ('idle', 'pump_4', 'paired_4', 'pump_20', 'paired_20')
DELAYS_US = (0.1, 2., 5., 15., 30., 60., 120., 250., 500.)
BLOCKS, SHOTS = 4, 250
PERIOD_US, WASHOUT_US, RINGDOWN_US = 30., 2000., 10.
FEEDBACK_FREE_RECOVERY_US = 50.


def base_config():
    """Explicit q3 settings; never inherit a measurement-PC q4 override.

    Park pi verified 2026-09-29 (q3_park_pi2_calibration_...223007Z_7464f640).
    Readout/reset calibration is freshly measured, not copied from that run.
    """
    return dict(
        res_ch=0, qubit_ch=1, ff_ch=3, ro_chs=[0], nqz=2, qubit_nqz=2,
        ff_nqz=1, mixer_freq=0., cavity_LO=0, reps=SHOTS,
        relax_delay=1000., flux_settle_time_us=.5, ff_ramp_length=4.,
        adc_trig_offset=.5, res_phase=165., read_pulse_style='const',
        read_length=3.5, readout_guard_us=1., readout_thermalization_us=10.,
        read_pulse_gain=1880, read_pulse_freq=6933.026,
        qubit_pulse_style='arb', qubit_freq=4367.292, qubit_pi_freq=4367.292,
        qubit_pi_gain=13500, qubit_pi2_gain=7993, qubit_gain=13500,
        qubit_drag_beta=0., qubit_anharmonicity_mhz=-180.,
        qubit_length=.25, sigma=.2, flat_top_length=None,
        reset_read_delay_us=2., reset_meas_syncdelay_us=10., reset_max_iters=3,
        ff_park_gain=-25146, ff_park_settle_us=1.,
        FF_Qubits={'1': {'channel': 3, 'delay_time': 0.}},
        trig_buffer_start=.02, trig_buffer_end=.02, trig_delay=.082,
        use_switch=False, cavity_winding_freq=0, cavity_winding_offset=0,
        do_ff=False, opx_reference_flux_cycle=False,
        # Same verified timing as FivePointApplesToApples, for BOTH calibration
        # and science. Do not fall back to the legacy 2-us accumulator wait.
        opx_feedback_read_timing='official_wait_all',
        opx_feedback_pre_measure_sync=True, opx_feedback_flush_mode='off',
        opx_read_delay_us=10.,
    )


def plan(*, feedback_free=False):
    return dict(qubit='q3', frequency_mhz=4367.292, readout_mhz=6933.026,
                park_gain=-25146, arms=list(ARMS), delays_us=list(DELAYS_US),
                blocks=BLOCKS, shots_per_block=SHOTS, period_us=PERIOD_US,
                conditioning_us=20 * PERIOD_US + 1., washout_us=WASHOUT_US,
                post_reset_ringdown_us=None if feedback_free else RINGDOWN_US,
                final_readout_ringdown_us=RINGDOWN_US,
                feedback_free=bool(feedback_free),
                post_conditioning_wait_us=FEEDBACK_FREE_RECOVERY_US if feedback_free else None,
                total_probe_shots=BLOCKS * SHOTS * len(DELAYS_US) * len(ARMS) * 2,
                reset=('2000 us passive wait; no feedback in science shots' if feedback_free
                       else 'fresh q3 active reset before and after conditioning'),
                approximate_minutes='5–10; depends on feedback and NAS transport')


def conditioning_schedule(arm, *, pulse_ticks, period_ticks, pair_gap_ticks, lead_ticks):
    """Absolute tProc start times; paired controls end at the same last slot.

    Small trains occupy the final four slots of the same twenty-slot window.
    Opposite phases cancel systematic pulse-area error to first order. They
    are a low-excitation control, not an assumption of perfectly zero heating.
    """
    if arm not in ARMS:
        raise ValueError(f'unknown conditioning arm {arm}')
    if min(pulse_ticks, period_ticks, pair_gap_ticks, lead_ticks) <= 0:
        raise ValueError('pulse timing must be positive')
    if 2 * pulse_ticks + pair_gap_ticks >= period_ticks:
        raise ValueError('paired pulses do not fit one period')
    pulses = []
    if arm != 'idle':
        kind, count = arm.split('_')
        count = int(count)
        for slot in range(20 - count, 20):
            if kind == 'pump':
                pulses.append(dict(start_tick=lead_ticks + slot * period_ticks, phase_deg=0))
            elif slot % 2:
                end = lead_ticks + slot * period_ticks
                pulses.extend([dict(start_tick=end - pulse_ticks - pair_gap_ticks, phase_deg=0),
                               dict(start_tick=end, phase_deg=180)])
    return dict(duration_ticks=lead_ticks + 20 * period_ticks, pulses=pulses)


def conditions(block):
    # Adjacent g/e at each arm; reverse state and arm order in alternate blocks,
    # and rotate the starting arm. Every condition occurs in each hardware shot.
    arms = list(ARMS)
    shift = block % len(arms)
    arms = arms[shift:] + arms[:shift]
    if block % 2:
        arms.reverse()
    states = ('g', 'e') if block % 2 == 0 else ('e', 'g')
    return [dict(arm=arm, state=state) for arm in arms for state in states]


def tasks():
    rng = np.random.default_rng(3092026)
    result = []
    for block in range(BLOCKS):
        for delay in rng.permutation(DELAYS_US):
            result.append(dict(index=len(result), block=block, delay_us=float(delay),
                               conditions=conditions(block)))
    return result


@dataclass(frozen=True)
class PumpRecord:
    before: object
    conditioned: object
    probe: object

    def to_words(self):
        return self.before.to_words() + self.conditioned.to_words() + self.probe.to_words()


def decode_records(words, expected_records=None):
    from ..active_reset_OPX.records import decode_records as decode_shots
    flat = np.asarray(words).ravel()
    if len(flat) % 24:
        raise ValueError('quasiparticle records require multiples of 24 words')
    count = len(flat) // 24
    if expected_records is not None and count != expected_records:
        raise ValueError(f'expected {expected_records} records, received {count}')
    shots = decode_shots(flat)
    return [PumpRecord(*shots[i:i + 3]) for i in range(0, len(shots), 3)]


def save_json(path, value):
    from ..active_reset_OPX.analysis import json_safe
    from .TLSPumpProbeProtocolCheck import checkpoint
    checkpoint(path, json_safe(value))


def collect(output, acquire, *, run_tasks=None, manifest=None):
    """Checkpoint every acquisition; hardware errors and interrupts stop once."""
    output = Path(output)
    manifest = {} if manifest is None else manifest
    manifest.update(status='running', completed=[], current=None)
    started = time.monotonic()
    path = output / 'manifest.json'
    save_json(path, manifest)
    rows = []
    try:
        for task in tasks() if run_tasks is None else run_tasks:
            manifest['current'] = task
            save_json(path, manifest)
            result = acquire(task)
            rows.extend(result['rows'])
            manifest['completed'].append(dict(task=task, **result))
            manifest['elapsed_s'] = time.monotonic() - started
            save_json(path, manifest)
            save_json(output / 'summary.json', analyze(rows))
        manifest.update(status='acquired', current=None)
        save_json(path, manifest)
        return rows
    except BaseException as exc:
        manifest.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
                        error=f'{type(exc).__name__}: {exc}')
        save_json(path, manifest)
        raise


def fit_contrast(t, c, error):
    """An exponential descriptor, with shape diagnostics, not a QP-count fit."""
    from scipy.optimize import curve_fit
    result = dict(valid=False)
    if len(t) < 5 or c[0] < .2 or c[0] <= 5 * error[0]:
        return result
    try:
        def decay(x, amplitude, tau):
            return amplitude * np.exp(-x / tau)
        pars, cov = curve_fit(decay, t, c, sigma=error, absolute_sigma=True,
                             p0=(min(c[0], .95), 60.),
                             bounds=([0., .05], [1.5, 10000.]), maxfev=10000)
        err = np.sqrt(np.diag(cov))
        chi2 = np.sum(((c - decay(t, *pars)) / error) ** 2)
        valid = bool(np.all(np.isfinite(err)) and err[1] < pars[1] / 2
                     and .1 < pars[1] < 2 * max(t)
                     and c[-1] < .7 * c[0])
        result.update(valid=valid, amplitude=float(pars[0]), tau_us=float(pars[1]),
                      tau_error_us=float(err[1]), chi2=float(chi2), dof=len(t) - 2,
                      exponential_adequate=bool(chi2 / (len(t) - 2) < 3.))
    except (RuntimeError, ValueError, FloatingPointError):
        pass
    return result


def _curve(rows):
    t, c, variance, g, e = [], [], [], [], []
    for delay in sorted({r['delay_us'] for r in rows}):
        groups = [[r for r in rows if r['delay_us'] == delay and r['state'] == s]
                  for s in ('g', 'e')]
        if not all(groups):
            continue
        populations, variances = [], []
        for group in groups:
            n = sum(r['shots'] for r in group)
            p = sum(r['shots'] * r['pe'] for r in group) / n
            populations.append(p)
            variances.append(max(p * (1 - p), .25 / n) / n)
        t.append(delay)
        g.append(populations[0])
        e.append(populations[1])
        c.append(e[-1] - g[-1])
        variance.append(sum(variances))
    return tuple(np.asarray(x) for x in (t, c, variance, g, e))


def _area(t, c, variance):
    if len(t) != len(DELAYS_US) or not np.allclose(t, DELAYS_US) or c[0] <= .2:
        return None
    w = np.zeros(len(t))
    w[:-1] += np.diff(t) / 2
    w[1:] += np.diff(t) / 2
    area = np.dot(w, c) / c[0]
    jac = w / c[0]
    jac[0] -= area / c[0]
    return float(area), float(np.dot(jac ** 2, variance))


def analyze(rows):
    result = dict(interpretation='conditioning screen; not a quasiparticle identification',
                  arms={}, comparisons={})
    for arm in ARMS:
        selected = [r for r in rows if r['arm'] == arm]
        if not selected:
            continue
        t, c, v, g, e = _curve(selected)
        if not len(t):
            continue
        # Between-block scatter is included where it exceeds shot noise.
        block_curves = [_curve([r for r in selected if r['block'] == b])
                        for b in sorted({r['block'] for r in selected})]
        full = [x[1] for x in block_curves if np.array_equal(x[0], t)]
        if len(full) > 1:
            v = np.maximum(v, np.var(full, axis=0, ddof=1) / len(full))
        result['arms'][arm] = dict(delays_us=t.tolist(), contrast=c.tolist(),
                                  contrast_error=np.sqrt(v).tolist(),
                                  ground=g.tolist(), excited=e.tolist(),
                                  fit=fit_contrast(t, c, np.sqrt(v)),
                                  block_curves=[dict(delays_us=x[0].tolist(),
                                                     contrast=x[1].tolist()) for x in block_curves])
    pairs = [(f'pump_{n}', control) for n in (4, 20)
             for control in ('idle', f'paired_{n}')] + [('paired_20', 'idle')]
    for left, right in pairs:
        differences, variances = [], []
        for block in sorted({r['block'] for r in rows}):
            values = [_area(*_curve([r for r in rows if r['arm'] == arm
                                     and r['block'] == block])[:3])
                      for arm in (left, right)]
            if all(x is not None for x in values):
                differences.append(values[0][0] - values[1][0])
                variances.append(values[0][1] + values[1][1])
        if differences:
            n = len(differences)
            var = sum(variances) / n ** 2
            if n > 1:
                var = max(var, float(np.var(differences, ddof=1) / n))
            result['comparisons'][left + '_minus_' + right] = dict(
                normalized_area_difference_us=float(np.mean(differences)),
                error_us=math.sqrt(var), block_differences_us=differences, blocks=n,
                window_us=[DELAYS_US[0], DELAYS_US[-1]])
    return result


def calibration_config():
    from ..active_reset_OPX.benchmark_settings import q3_benchmark_settings
    cfg = base_config()
    cfg.update(q3_benchmark_settings().opx_overrides())
    # Match the persistent park used by the measurement, including readout
    # recovery. Avoid moving flux between classifier references.
    cfg.update(reset_pi_freq=cfg['qubit_pi_freq'], opx_inter_shot_delay_us=1000.,
               opx_park_preroll_us=WASHOUT_US)
    return cfg


def validate_reference(bundle, *, feedback_free=False):
    if not feedback_free:
        from ..active_reset_OPX.calibration import validate_confident_calibration
        validate_confident_calibration(bundle, min_confident_fraction=.2)
        return
    # Feedback thresholds and loop-reference quality are irrelevant when no
    # feedback is played. Require useful discrimination at the analysis threshold.
    h = bundle.payload.holdout
    fidelity = float(h.get('peak_fidelity', 0.))
    contrast = float(h.get('excited_fire', 0.)) - float(h.get('false_pi', 1.))
    if not (math.isfinite(fidelity) and math.isfinite(contrast)
            and fidelity >= .70 and contrast >= .30):
        raise ValueError(f'insufficient readout reference: fidelity={fidelity:.3f}, contrast={contrast:.3f}')


def calibrate(soc, soccfg, output, label, *, feedback_free=False):
    from ..active_reset_OPX.benchmark_settings import q3_benchmark_settings
    from ..active_reset_OPX.calibration import (
        acquire_calibration, save_calibration, save_raw_calibration)
    print('SS cal: q3 readout' if feedback_free else 'SS cal: q3 readout and active-reset thresholds', flush=True)
    cfg = calibration_config()
    for attempt in range(1, 4):
        folder = Path(output) / f'calibration_{label}_{attempt}'
        folder.mkdir()
        save_json(folder / 'config.json', cfg)
        bundle, raw = acquire_calibration(
            soc, soccfg, cfg, shots=2000,
            **q3_benchmark_settings().calibration_options(),
            metadata={'qubit': 'q3', 'purpose': 'Q3QuasiparticlePumping',
                      'created_at': datetime.now(timezone.utc).isoformat()})
        save_calibration(folder / 'calibration.json', bundle)
        save_raw_calibration(folder / 'raw.npz', raw)
        try:
            validate_reference(bundle, feedback_free=feedback_free)
        except ValueError:
            if attempt == 3:
                raise
            print('SS cal: insufficient reference quality; recalibrating', flush=True)
            continue
        print('SS cal complete.', flush=True)
        return bundle


def measurement_config(bundle, *, feedback_free=False):
    from ..active_reset_OPX.production import ProductionResetSession
    cfg = ProductionResetSession.active(bundle.to_dict(), 4367.292).apply(base_config())
    cfg.update(opx_reset_scheme='opx_unbounded', opx_park_preroll_us=WASHOUT_US,
               opx_resident_dmem_stream=True, qp_shots=SHOTS,
               qp_feedback_free=bool(feedback_free),
               qp_recovery_us=FEEDBACK_FREE_RECOVERY_US if feedback_free else 0.)
    if feedback_free:
        cfg.update(reset_mode='passive', opx_reset_scheme='none',
                   relax_delay=WASHOUT_US, opx_inter_shot_delay_us=WASHOUT_US)
    return cfg


def preflight(program):
    instructions = len(program.compile())
    capacity = int(program.soccfg['tprocs'][0]['pmem_size'])
    if instructions > capacity:
        raise RuntimeError(f'program needs {instructions} instructions; capacity={capacity}')
    memory = []
    for ch, pulses in enumerate(program.pulses):
        limit = int(program.soccfg['gens'][ch]['maxlen'])
        used = max((int(p['addr']) + len(p['data']) for p in pulses.values()), default=0)
        if used > limit:
            raise RuntimeError(f'channel {ch}: waveform memory {used} exceeds {limit}')
        memory.append(dict(channel=ch, used_samples=used, capacity_samples=limit))
    return dict(instructions=instructions, capacity=capacity, waveform_memory=memory,
                conditioning=program.conditioning_timing,
                delay_us=program.cycles2us(program.us2cycles(program.cfg['qp_delay_us'])),
                record_words=program.record_words, order='shot_condition_stage_word',
                stages=['probe'] if program.record_words == 2 else ['before', 'conditioned', 'probe'],
                feedback_free=bool(program.cfg.get('qp_feedback_free', False)),
                post_conditioning_wait_us=program.cfg.get('qp_recovery_us', 0.))


def rows_from_records(records, task, bundle, *, feedback_free=False):
    from ..active_reset_OPX.integration import reset_telemetry
    count = len(task['conditions'])
    if len(records) % count:
        raise ValueError('incomplete condition cycle')
    rows = []
    for i, condition in enumerate(task['conditions']):
        selected = records[i::count]
        row = dict(block=task['block'], delay_us=task['delay_us'], **condition,
                   shots=len(selected), feedback_free=bool(feedback_free),
                   probe_preparation='pi' if condition['state'] == 'e' else 'no_pi')
        for stage in ('probe',) if feedback_free else ('before', 'conditioned', 'probe'):
            data = selected if feedback_free else [getattr(r, stage) for r in selected]
            projected = bundle.payload.project(
                np.asarray([r.final_i for r in data], dtype=np.int64),
                np.asarray([r.final_q for r in data], dtype=np.int64))
            row[stage + '_pe'] = float(np.mean(projected > bundle.payload.excited_threshold))
            if not feedback_free:
                row[stage + '_reset'] = reset_telemetry(data)
        row['pe'] = row['probe_pe']
        rows.append(row)
    return rows


def acquire_task(soc, program, cfg, output, task, bundle, progress):
    from ..active_reset_OPX.acquisition import _safe_abort
    from ..active_reset_OPX.integration import _run_program
    stem = Path(output) / f'block_{task["block"]:02d}_point_{task["index"]:03d}'
    info = preflight(program)
    save_json(stem.with_suffix('.json'), dict(task=task, preflight=info,
                                            started_at=datetime.now(timezone.utc).isoformat()))
    try:
        # The transport watchdog resets whenever new records arrive. Two seconds
        # is generous for a bank of these ~3-ms experimental cells.
        records = _run_program(soc, program, 3., cfg, total_shots=cfg['qp_shots'],
                               progress=progress)
    except BaseException as exc:
        # In particular, the shared stream catches Exception, not Ctrl+C.
        # Stop pulses BEFORE any potentially slow/unavailable NAS operation.
        _safe_abort(soc)
        partial = getattr(exc, 'partial_records', [])
        if partial:
            np.savez_compressed(stem.with_suffix('.partial.npz'),
                                words=np.asarray([r.to_words() for r in partial], dtype=np.int64))
        raise
    # Raw accumulator IQ (and reset records in the original mode) precedes analysis.
    words = np.asarray([r.to_words() for r in records], dtype=np.int64)
    np.savez_compressed(stem.with_suffix('.npz'), words=words)
    if len(records) != cfg['qp_shots'] * len(task['conditions']):
        raise RuntimeError(f'incomplete acquisition: {len(records)} records')
    rows = rows_from_records(records, task, bundle,
                             feedback_free=cfg.get('qp_feedback_free', False))
    return dict(rows=rows, raw_file=stem.with_suffix('.npz').name,
                completed_at=datetime.now(timezone.utc).isoformat())


def plot_summary(output, summary, *, feedback_free=False):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for arm, curve in summary['arms'].items():
        t = np.asarray(curve['delays_us'])
        c = np.asarray(curve['contrast'])
        axes[0].errorbar(t, c, yerr=curve['contrast_error'], marker='.', label=arm)
        axes[1].plot(t, curve['ground'], marker='.', label=arm)
    axes[0].set(ylabel='π − no-π probe contrast' if feedback_free else 'Excited − ground preparation contrast',
                title='q3 relaxation after conditioning')
    axes[1].set(ylabel='Classified excited fraction',
                title=('No-π probe' if feedback_free else 'Ground-prepared probe') + ' (readout floor included)')
    for ax in axes:
        ax.set(xlabel='Probe delay (µs)', xscale='symlog')
        ax.legend(fontsize=8)
    fig.savefig(Path(output) / 'relaxation.png', dpi=160)
    plt.close(fig)


def run(*, data_root=DATA_ROOT, progress=True, feedback_free=False):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    mode = 'feedback_free_' if feedback_free else ''
    output = Path(data_root) / 'q3' / f'q3_quasiparticle_pumping_{mode}{stamp}_{uuid.uuid4().hex[:8]}'
    output.mkdir(parents=True, exist_ok=False)
    manifest = dict(schema='q3.quasiparticle-pumping.v1', plan=plan(feedback_free=feedback_free),
                    created_at=datetime.now(timezone.utc).isoformat(), status='calibrating')
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=Path(__file__).parent,
                              capture_output=True, text=True, check=True).stdout.strip()
    manifest['commit'] = revision
    for source in (Path(__file__), Path(__file__).with_name('Q3QuasiparticleProgram.py')):
        shutil.copyfile(source, output / source.name)
        manifest[source.name + '_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    save_json(output / 'manifest.json', manifest)
    save_json(output / 'requested_config.json', base_config())
    print(f'q3 T1 conditioning: {output}', flush=True)
    import matplotlib
    matplotlib.use('Agg')
    from tqdm import tqdm
    from ..CoreLib.socProxy import makeProxy
    from ..active_reset_OPX.acquisition import _safe_abort
    from .Q3QuasiparticleProgram import make_program_class
    soc = None
    try:
        soc, soccfg = makeProxy()
        save_json(output / 'board_configuration.json', soccfg.get_cfg())
        bundle = calibrate(soc, soccfg, output, 'pre', feedback_free=feedback_free)
        cfg = measurement_config(bundle, feedback_free=feedback_free)
        save_json(output / 'config.json', cfg)
        run_tasks = tasks()
        programs = []
        for task in run_tasks:
            point_cfg = dict(cfg, qp_conditions=task['conditions'], qp_delay_us=task['delay_us'])
            program = make_program_class()(soccfg, point_cfg, bundle.payload, bundle.loop)
            preflight(program)
            programs.append(program)
        with tqdm(total=plan()['total_probe_shots'], desc='T1 conditioning', unit='shot',
                  disable=not progress,
                  bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} '
                             '[{elapsed} elapsed, ETA {remaining}]') as bar:
            def acquire(task):
                offset = task['index'] * SHOTS * len(task['conditions'])
                def update(done, total):
                    bar.update(offset + int(done) * len(task['conditions']) - bar.n)
                return acquire_task(soc, programs[task['index']], cfg, output, task, bundle, update)
            rows = collect(output, acquire, run_tasks=run_tasks, manifest=manifest)
        summary = analyze(rows)
        save_json(output / 'summary.json', summary)
        plot_summary(output, summary, feedback_free=feedback_free)
        manifest['status'] = 'post_calibrating'
        save_json(output / 'manifest.json', manifest)
        post = calibrate(soc, soccfg, output, 'post', feedback_free=feedback_free)
        # Reclassify the saved measurements with the post-run axis as an explicit
        # sensitivity check. Never mix different thresholds within a trace.
        post_rows = []
        for entry in manifest['completed']:
            with np.load(output / entry['raw_file']) as saved:
                if feedback_free:
                    from ..active_reset_OPX.records import decode_payload_records
                    records = decode_payload_records(saved['words'])
                else:
                    records = decode_records(saved['words'])
            post_rows.extend(rows_from_records(records, entry['task'], post,
                                                feedback_free=feedback_free))
        save_json(output / 'post_calibration_summary.json', analyze(post_rows))
        manifest.update(status='complete', completed_at=datetime.now(timezone.utc).isoformat())
        save_json(output / 'manifest.json', manifest)
    except BaseException as exc:
        if soc is not None:
            _safe_abort(soc)
        manifest.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
                        error=f'{type(exc).__name__}: {exc}')
        save_json(output / 'manifest.json', manifest)
        raise
    finally:
        if soc is not None:
            _safe_abort(soc)
    print(f'T1 conditioning complete: {output}', flush=True)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--run', action='store_true')
    action.add_argument('--plan', action='store_true')
    parser.add_argument('--feedback-free', action='store_true',
                        help='passive preparation; no intermediate readout or feedback')
    parser.add_argument('--data-root', default=DATA_ROOT)
    parser.add_argument('--quiet', action='store_true', help='hide progress bar')
    args = parser.parse_args(argv)
    if args.run:
        run(data_root=args.data_root, progress=not args.quiet, feedback_free=args.feedback_free)
    else:
        print(json.dumps(plan(feedback_free=args.feedback_free), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
