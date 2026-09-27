"""Pump-off operational reset check at q3 park using candidate timing.

Acquire one fresh official_guard20 reference calibration and require the existing
quality guard. Compare native unbounded reset with no feedback, starting with
no pi or a pi pulse, and collect a separate verification readout 20 us after the
last decision readout. Save every shot's verification IQ, reset attempts, pi
count, terminal status and decision projections. Twelve balanced rounds start
30 seconds apart. Repeat the reference calibration at the end without updating
the runtime classifier. No pump or target excursion is used.

No-feedback and active arms have different elapsed times and measurement counts.
Verification fractions are uncorrected classifier observables, not reset fidelity.
This operational check does not validate the full pump-probe sequence or change
production defaults. Rejected starting calibration stops before feedback runs.

--delay-check repeats the same benchmark at verification delays 20, 100, and
500 us. Only the delay before the final verification readout changes; the reset
decision timing, calibration profile, and thresholds remain fixed. This tests
starting-state dependence versus elapsed time, not a TLS or reset lifetime fit.

--readout-memory-check instead compares normal and zero-amplitude first readout
pulses with feedback disabled in every arm, at delays 20/100/500 us. The first
ADC capture and digital sequence remain; only its drive amplitude changes.
The final verification pulse always uses the normal gain. This tests the effect
of the preceding readout drive on the later observable, not a specific mechanism.

--readout-gain-check screens first-readout amplitude fractions 0/.25/.5/.75/1
at 20-us verification delay, with feedback off and normal final readout gain.
Ten balanced rounds retain initial decision projections for a fixed-axis
separation check; this is not a fully recalibrated readout optimization.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import uuid

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeLocalizer as localizer, TLSPumpProbePilot as pilot,
    TLSPumpProbeProtocolCheck as protocol, TLSPumpProbeResetCheck as reference,
)

PROFILE = 'official_guard20'
SHOTS = 400


def plan(*, delay_check=False, readout_memory_check=False, readout_gain_check=False):
    if sum((delay_check, readout_memory_check, readout_gain_check)) > 1:
        raise ValueError('Choose only one verification follow-up stage')
    delays = [20., 100., 500.] if delay_check or readout_memory_check else [20.]
    conditions = [(scheme, prep, delay, 'normal', 1.) for delay in delays
                  for scheme, prep in [('opx_unbounded', 'g'), ('opx_unbounded', 'e'), ('none', 'g'), ('none', 'e')]]
    if readout_memory_check:
        conditions = [('none', prep, delay, drive, 0. if drive == 'zero' else 1.) for delay in delays
                      for drive in ('normal', 'zero') for prep in ('g', 'e')]
    if readout_gain_check:
        conditions = [('none', prep, 20., f'amplitude_{fraction:g}', fraction)
                      for fraction in (0., .25, .5, .75, 1.) for prep in ('g', 'e')]
    points = []
    for repeat in range(10 if readout_gain_check else 12):
        offset = repeat % len(conditions)
        order = conditions[offset:] + conditions[:offset]
        for scheme, preparation, delay, drive, fraction in order:
            points.append(dict(name=f'point_{len(points):04d}', repeat=repeat,
                               reset_scheme=scheme, preparation=preparation,
                               verification_delay_us=delay,
                               initial_readout=drive,
                               initial_readout_fraction=fraction,
                               not_before_offset_s=repeat * 30.))
    return dict(hardware_access=False, profile=PROFILE, delay_check=bool(delay_check),
                readout_memory_check=bool(readout_memory_check), readout_gain_check=bool(readout_gain_check), shots_per_block=SHOTS,
                benchmark_shots=len(points) * SHOTS, reference_shots=2 * 4 * reference.SHOTS,
                points=points, note=__doc__)


def runtime_config(base, calibration, frequency):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import ProductionResetSession
    # apply() restores benchmark defaults, so apply the candidate profile last.
    cfg = ProductionResetSession.active(calibration, frequency).apply(base)
    cfg = reference.profile_config(cfg, PROFILE)
    cfg.update(opx_inter_shot_delay_us=500., opx_verification_delay_us=20.,
               opx_resident_dmem_stream=True, shots=SHOTS, reps=SHOTS,
               qubit_pi_freq=float(frequency))
    return cfg


def save_records(path, records):
    import numpy as np
    fields = ('preparation', 'initial_z', 'reset_attempts', 'pi_pulses',
              'terminal_status', 'final_i', 'final_q', 'last_z')
    arrays = {k: np.asarray([int(getattr(r, k)) for r in records], dtype=np.int64) for k in fields}
    np.savez_compressed(path, **arrays)
    return arrays


def save_and_summarize(path, records, bundle):
    import numpy as np
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import reset_telemetry
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.records import TerminalStatus
    arrays = save_records(path, records)
    if len(records) != SHOTS:
        raise RuntimeError(f'Incomplete benchmark block saved to {path}: {len(records)}/{SHOTS}')
    result = dict(reset_telemetry(records), raw_npz=str(path),
                  confirmed_ground_records=int(np.sum(arrays['terminal_status'] == int(TerminalStatus.CONFIRMED_GROUND))))
    for context in ('payload', 'loop'):
        fit = getattr(bundle, context)
        z = fit.project(arrays['final_i'], arrays['final_q'])
        result[f'verification_excited_fraction_{context}'] = float(np.mean(z > fit.excited_threshold))
    return result


def run(*, data_root=localizer.DATA_ROOT, correction_json=None, delay_check=False,
        readout_memory_check=False, readout_gain_check=False):
    run_plan = plan(delay_check=delay_check, readout_memory_check=readout_memory_check,
                    readout_gain_check=readout_gain_check)
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    with localizer.scan_environment(correction):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import FivePointApplesToApples as five, TLSSpectroscopy as tls
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import build_calibration_config
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.benchmark_settings import q3_benchmark_settings
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.calibration import (
            acquire_calibration, save_calibration, save_raw_calibration, validate_confident_calibration,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs import (
            OPXResetBenchmarkProgram, OPXReadoutMemoryBenchmarkProgram,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import _run_program, _block_timeout_s
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.acquisition import AcquisitionTimeout
        if int(tls.BaseConfig['ff_park_gain']) != -25146:
            raise RuntimeError('Unexpected q3 park configuration')
        tls.QUBIT, tls.SET_YOKO, tls.outerFolder = 'q3', False, str(data_root)
        five.install_scan_calibration(tls)
        frequency = next(float(tls.BaseConfig[k]) for k in ('reset_pi_freq', 'qubit_pi_freq', 'qubit_freq') if tls.BaseConfig.get(k) is not None)
        cal_cfg = reference.profile_config(build_calibration_config(tls.BaseConfig, frequency), PROFILE)
        prefix = 'q3_pump_probe_reset_delay_check_' if delay_check else 'q3_pump_probe_reset_validation_'
        if readout_memory_check:
            prefix = 'q3_pump_probe_readout_memory_check_'
        if readout_gain_check:
            prefix = 'q3_pump_probe_readout_gain_check_'
        session_id = prefix + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:8]
        folder = data_root / 'q3' / session_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / 'manifest.json'
        manifest = dict(schema='q3.pump-probe-reset-validation.v1', session_id=session_id,
                        created_at=datetime.now(timezone.utc).isoformat(), status='calibrating',
                        code_commit=os.environ['Q3_CODE_COMMIT'], parameters=run_plan,
                        points=[dict(p, status='pending') for p in run_plan['points']])
        # Final references are part of collection, so complete means they were saved too.
        manifest['points'].append(dict(name='final_reference', kind='reference', status='pending'))
        protocol.checkpoint(path, manifest)
        print(f'[reset-validation] manifest={path}', flush=True)
        try:
            soc, soccfg = tls.makeProxy()

            def acquire_reference(name):
                out = folder / name
                out.mkdir(exist_ok=False)
                (out / 'config.json').write_text(json.dumps(cal_cfg, default=pilot.json_default, indent=2) + '\n')
                bundle, raw = acquire_calibration(soc, soccfg, cal_cfg, shots=reference.SHOTS,
                    **q3_benchmark_settings().calibration_options(),
                    metadata={'purpose': 'TLSPumpProbeResetValidation', 'stage': name, 'session_id': session_id})
                save_calibration(out / 'calibration.json', bundle)
                save_raw_calibration(out / 'calibration_raw.npz', raw)
                return bundle, dict(reference.calibration_report(bundle), output=str(out))

            bundle, report = acquire_reference('initial_reference')
            manifest['initial_reference'] = report
            protocol.checkpoint(path, manifest)
            validate_confident_calibration(bundle)  # Never retry a quality rejection here.
            cfg = runtime_config(tls.BaseConfig, bundle.to_dict(), frequency)
            (folder / 'config.json').write_text(json.dumps(cfg, default=pilot.json_default, indent=2) + '\n')
            manifest['status'] = 'running'
            protocol.checkpoint(path, manifest)
            start = time.monotonic()

            def acquire(entry):
                if entry.get('kind') == 'reference':
                    _, final_report = acquire_reference('final_reference')
                    return final_report
                reference.wait_for_reference_slot(start, entry['not_before_offset_s'])
                entry['acquisition_started_at'] = datetime.now(timezone.utc).isoformat()
                entry['acquisition_start_offset_s'] = time.monotonic() - start
                run_cfg = dict(cfg, opx_reset_scheme=entry['reset_scheme'], prep_excited=entry['preparation'] == 'e',
                               opx_verification_delay_us=entry['verification_delay_us'])
                program_class = OPXResetBenchmarkProgram
                if readout_memory_check or readout_gain_check:
                    run_cfg['opx_benchmark_initial_readout_gain'] = int(round(
                        int(cfg['read_pulse_gain']) * entry['initial_readout_fraction']))
                    entry['initial_readout_gain'] = run_cfg['opx_benchmark_initial_readout_gain']
                    entry['verification_readout_gain'] = int(cfg['read_pulse_gain'])
                    program_class = OPXReadoutMemoryBenchmarkProgram
                program = program_class(soccfg, run_cfg, bundle.payload, bundle.loop)
                try:
                    records = _run_program(soc, program, _block_timeout_s(run_cfg, SHOTS), run_cfg, total_shots=SHOTS)
                except AcquisitionTimeout as exc:
                    partial_path = folder / (entry['name'] + '_partial.npz')
                    save_records(partial_path, exc.partial_records)
                    entry['partial_acquisition'] = dict(raw_npz=str(partial_path),
                        completed_shots=exc.completed_shots, recovered_records=len(exc.partial_records))
                    raise
                result = save_and_summarize(folder / (entry['name'] + '.npz'), records, bundle)
                result['read_length_cycles'] = int(program.us2cycles(cfg['read_length'], ro_ch=cfg['ro_chs'][0]))
                if entry['reset_scheme'] == 'opx_unbounded' and result['confirmed_ground_records'] != SHOTS:
                    raise RuntimeError('Active benchmark returned non-ground terminal records; raw data saved')
                print(f"[reset-validation] {entry['name']} {entry['reset_scheme']} {entry['preparation']} "
                      f"delay={entry['verification_delay_us']:g} us "
                      f"first_readout={entry['initial_readout']} "
                      f"verification={result['verification_excited_fraction_loop']:.3f} "
                      f"attempts={result['mean_reset_attempts']:.2f}", flush=True)
                return result

            pilot.collect_points(manifest, path, acquire)
        except BaseException as exc:
            manifest.update(status='failed', error=f'{type(exc).__name__}: {exc}')
            protocol.checkpoint(path, manifest)
            raise
        print(f"[reset-validation] complete; final reference accepted={manifest['points'][-1]['result']['accepted']}; no production defaults changed. {path}", flush=True)
        return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--plan', action='store_true')
    mode.add_argument('--run', action='store_true')
    stage = parser.add_mutually_exclusive_group()
    stage.add_argument('--delay-check', action='store_true',
                        help='compare verification delays of 20, 100, and 500 us')
    stage.add_argument('--readout-memory-check', action='store_true',
                       help='compare normal/zero first readout drive with feedback off at all delays')
    stage.add_argument('--readout-gain-check', action='store_true',
                       help='screen reduced first-readout amplitudes at 20-us verification delay')
    parser.add_argument('--data-root', type=Path, default=localizer.DATA_ROOT)
    parser.add_argument('--correction-json', type=Path)
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(delay_check=args.delay_check, readout_memory_check=args.readout_memory_check,
                              readout_gain_check=args.readout_gain_check), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json, delay_check=args.delay_check,
            readout_memory_check=args.readout_memory_check, readout_gain_check=args.readout_gain_check)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
