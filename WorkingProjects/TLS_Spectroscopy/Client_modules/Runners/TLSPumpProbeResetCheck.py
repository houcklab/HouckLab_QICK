"""Bounded q3 calibration-only comparison after a pump-probe reset rejection.

Run on the measurement PC with other acquisitions stopped. No TLS pump or
location scan is run. Compare the unchanged production calibration timing,
the pump-probe acquisition's official feedback timing, and the latter with
20-us loop recovery. Acquire both payload and loop ground/pi references using
the existing per-shot park calibration program. Save every fit and raw record,
including rejected fits. The 70% fit policy and 20% acceptance guard remain
unchanged; no result is automatically installed as an experiment calibration.

--stability-check instead repeats the unchanged legacy profile twelve times,
with scheduled starts 30 seconds apart. All raw references are retained for
offline comparison using fixed and refitted classifiers. This tests reference
stability without a pump; it does not directly measure active-reset fidelity.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import uuid

from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbePilot as pilot,
    TLSPumpProbeProtocolCheck as protocol,
)

SHOTS = 2000
PROFILES = ("legacy", "official", "official_guard20")


def plan(*, stability_check=False):
    profiles = ('legacy',) * 12 if stability_check else (*PROFILES, *reversed(PROFILES))
    points = [{"name": f"point_{i:04d}_{profile}", "profile": profile}
              for i, profile in enumerate(profiles)]
    if stability_check:
        for i, point in enumerate(points):
            point['not_before_offset_s'] = i * 30.0
    return {
        "hardware_access": False,
        "stability_check": bool(stability_check),
        "shots_per_state_per_context": SHOTS,
        "total_reference_shots": len(points) * 4 * SHOTS,
        "points": points,
        "note": __doc__,
    }


def wait_for_reference_slot(start, offset_s, *, clock=time.monotonic, sleep=time.sleep):
    """Use monotonic deadlines; acquire late slots immediately, never skip them."""
    while True:
        remaining = start + offset_s - clock()
        if remaining <= 0:
            return
        sleep(min(remaining, 10.0))


def profile_config(baseline, profile):
    if profile not in PROFILES:
        raise ValueError(f"Unknown calibration timing profile: {profile}")
    cfg = dict(baseline)
    if profile != "legacy":
        # Same four settings as FivePointApplesToApples.apply_verified_feedback_timing;
        # keep profile construction independent of that runner's QICK imports.
        cfg.update({"opx_feedback_read_timing": "official_wait_all",
                    "opx_feedback_pre_measure_sync": True,
                    "opx_feedback_flush_mode": "off", "opx_read_delay_us": 10.0})
    if profile == "official_guard20":
        cfg["opx_loop_recovery_us"] = 20.0
    return cfg


def calibration_report(bundle):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.calibration import (
        validate_confident_calibration,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
        MIN_CONFIDENT_STATE_FRACTION,
    )
    reason = None
    try:
        validate_confident_calibration(bundle, min_confident_fraction=MIN_CONFIDENT_STATE_FRACTION)
    except ValueError as exc:
        reason = str(exc)
    return {"accepted": reason is None, "rejection_reason": reason,
            "payload": dict(bundle.payload.holdout), "loop": dict(bundle.loop.holdout)}


def run(*, data_root=localizer.DATA_ROOT, correction_json=None, stability_check=False):
    run_plan = plan(stability_check=stability_check)
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    with localizer.scan_environment(correction):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
            FivePointApplesToApples as five, TLSSpectroscopy as tls,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
            build_calibration_config,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.benchmark_settings import (
            q3_benchmark_settings,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.calibration import (
            acquire_calibration, save_calibration, save_raw_calibration, _config_digest,
        )

        if int(tls.BaseConfig['ff_park_gain']) != -25146:
            raise RuntimeError('Unexpected q3 park configuration.')
        tls.QUBIT, tls.SET_YOKO, tls.outerFolder = 'q3', False, str(data_root)
        five.install_scan_calibration(tls)
        frequency = next(float(tls.BaseConfig[k]) for k in ('reset_pi_freq', 'qubit_pi_freq', 'qubit_freq')
                         if tls.BaseConfig.get(k) is not None)
        baseline = build_calibration_config(tls.BaseConfig, frequency)
        prefix = 'q3_pump_probe_reference_stability_' if stability_check else 'q3_pump_probe_reset_check_'
        session_id = prefix + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:8]
        folder = data_root / 'q3' / session_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / 'manifest.json'
        manifest = {
            'schema': 'q3.pump-probe-reset-check.v1', 'session_id': session_id,
            'status': 'starting', 'created_at': datetime.now(timezone.utc).isoformat(),
            'code_commit': os.environ['Q3_CODE_COMMIT'], 'shots_per_state_per_context': SHOTS,
            'stability_check': bool(stability_check),
            'total_reference_shots': run_plan['total_reference_shots'],
            'method_frequency_mhz': frequency, 'baseline_config_sha256': _config_digest(baseline),
            'calibration_options': q3_benchmark_settings().calibration_options(),
            'note': __doc__, 'points': [dict(p, status='pending') for p in run_plan['points']],
        }
        protocol.checkpoint(path, manifest)
        print(f'[reset-check] manifest={path}', flush=True)
        try:
            soc, soccfg = tls.makeProxy()
            manifest['status'] = 'running'
            protocol.checkpoint(path, manifest)
            schedule_start = time.monotonic()

            def acquire(entry):
                wait_for_reference_slot(schedule_start, entry.get('not_before_offset_s', 0.0))
                cfg = profile_config(baseline, entry['profile'])
                output = folder / entry['name']
                output.mkdir(exist_ok=False)
                (output / 'config.json').write_text(json.dumps(cfg, default=pilot.json_default, indent=2) + '\n', encoding='utf-8')
                # collect_points.started_at includes the scheduled wait; retain the
                # actual acquisition start separately for reference-drift analysis.
                entry['acquisition_started_at'] = datetime.now(timezone.utc).isoformat()
                entry['acquisition_start_offset_s'] = time.monotonic() - schedule_start
                bundle, raw = acquire_calibration(
                    soc, soccfg, cfg, shots=SHOTS,
                    **q3_benchmark_settings().calibration_options(),
                    metadata={'purpose': 'TLSPumpProbeResetCheck', 'profile': entry['profile'],
                              'method_frequency_mhz': frequency, 'session_id': session_id},
                )
                save_calibration(output / 'calibration.json', bundle)
                save_raw_calibration(output / 'calibration_raw.npz', raw)
                result = calibration_report(bundle)
                result.update(output=str(output), config_sha256=_config_digest(cfg))
                print(f"[reset-check] {entry['name']} accepted={result['accepted']} "
                      f"payload_peak={result['payload']['peak_fidelity']:.4f} "
                      f"loop_peak={result['loop']['peak_fidelity']:.4f} "
                      f"loop_ground_accept={result['loop']['ground_accept']:.4f}", flush=True)
                return result

            pilot.collect_points(manifest, path, acquire)
        except BaseException as exc:
            manifest.update(status='failed', error=f'{type(exc).__name__}: {exc}')
            protocol.checkpoint(path, manifest)
            raise
        accepted = sum(p['result']['accepted'] for p in manifest['points'])
        print(f"[reset-check] diagnostic complete: {accepted}/{len(manifest['points'])} fits accepted; no calibration installed. {path}", flush=True)
        return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--plan', action='store_true')
    mode.add_argument('--run', action='store_true')
    parser.add_argument('--stability-check', action='store_true',
                        help='repeat the original reference calibration 12 times, 30 seconds apart')
    parser.add_argument('--data-root', type=Path, default=localizer.DATA_ROOT)
    parser.add_argument('--correction-json', type=Path)
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(stability_check=args.stability_check), indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json,
            stability_check=args.stability_check)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
