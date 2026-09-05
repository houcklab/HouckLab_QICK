from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np


_root = Path(__file__).resolve()
for parent in _root.parents:
    if (parent / "WorkingProjects").is_dir():
        if str(parent) not in sys.path:
            sys.path.insert(0, str(parent))
        _repo_root = parent
        break
else:
    raise RuntimeError("Could not locate the HouckLab_QICK repository root")


from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import NpEncoder
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mRabiChevronSS import sweep_gain_populations
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import SingleShot1Q
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.benchmark_settings import q3_benchmark_settings
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.calibration import acquire_calibration, save_calibration, save_raw_calibration, validate_confident_calibration


QUBIT = "q3"
CALIBRATION_SHOTS = 1000
SS_CAL_SHOTS = 1000
RABI_SHOTS = 200
GAIN_POINTS = 9
GAIN_MAX_FACTOR = 2.0
PASSIVE_RESET_US = 400.0
ACTIVE_INTER_SHOT_US = 25.0
HOST_WATCHDOG_S = 2.0
MIN_CONFIDENT_STATE_FRACTION = 0.2
MAX_CURVE_RMSE = 0.15
MAX_PEAK_GAIN_STEPS = 1
MIN_CONTRAST = 0.5


def main():
    import qick

    if str(qick.__version__) != "0.2.133":
        raise RuntimeError(f"Expected qick 0.2.133, found {qick.__version__}")

    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    now = datetime.now()
    output_dir = (
        Path(outerFolder)
        / QUBIT
        / f"{QUBIT}_{now:%Y_%m_%d}"
        / f"{QUBIT}_{now:%H_%M_%S}_active_reset_OPX_Rabi_equivalence"
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    soc, soccfg = makeProxy()
    settings = q3_benchmark_settings()
    calibration_cfg = dict(BaseConfig)
    calibration_cfg.update(settings.opx_overrides())
    calibration_cfg["relax_delay"] = float(PASSIVE_RESET_US)
    calibration_cfg["opx_inter_shot_delay_us"] = float(ACTIVE_INTER_SHOT_US)
    calibration_cfg["opx_unbounded_watchdog_s"] = float(HOST_WATCHDOG_S)
    try:
        source_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=_repo_root, text=True
        ).strip()
    except Exception:
        source_commit = "unknown"
    bundle, raw = acquire_calibration(
        soc,
        soccfg,
        calibration_cfg,
        shots=int(CALIBRATION_SHOTS),
        **settings.calibration_options(),
        metadata={
            "qubit": QUBIT,
            "created": now.isoformat(),
            "source_commit": source_commit,
            "purpose": "Rabi opx_unbounded equivalence",
        },
    )
    validate_confident_calibration(
        bundle, min_confident_fraction=MIN_CONFIDENT_STATE_FRACTION
    )
    save_calibration(output_dir / "calibration.json", bundle)
    save_raw_calibration(output_dir / "calibration_raw.npz", raw)
    ss_cfg = dict(BaseConfig)
    ss_cfg.update({
        "reset_mode": "passive",
        "shots": int(SS_CAL_SHOTS),
        "reps": int(SS_CAL_SHOTS),
        "relax_delay": float(PASSIVE_RESET_US),
        "qubit_gain": int(BaseConfig["qubit_pi_gain"]),
    })
    ss = SingleShot1Q(
        soc=soc,
        soccfg=soccfg,
        path=QUBIT,
        outerFolder=str(output_dir),
        suffix="Rabi_equivalence_SS",
        cfg=ss_cfg,
        repeats=1,
        plot=False,
        save=False,
    )
    ss.acquire(progress=False, plotDisp=False)
    calib_params = dict(ss.calib_params)
    pi_gain = int(BaseConfig["qubit_pi_gain"])
    gains = np.round(
        np.linspace(0, GAIN_MAX_FACTOR * pi_gain, int(GAIN_POINTS))
    ).astype(int)
    common = dict(BaseConfig)
    common.update({
        "shots": int(RABI_SHOTS),
        "reps": int(RABI_SHOTS),
        "n_pulses": 1,
        "rabi_drive_freq": float(BaseConfig["qubit_pi_freq"]),
        "ff_hold_gain": 0,
        "readout_after_park": True,
    })
    experiment = type("Experiment", (), {"soc": soc, "soccfg": soccfg})()
    passive_cfg = dict(common)
    passive_cfg.update({
        "reset_mode": "passive",
        "relax_delay": float(PASSIVE_RESET_US),
    })
    active_cfg = dict(common)
    active_cfg.update(settings.opx_overrides())
    active_cfg.update({
        "reset_mode": "opx_unbounded",
        "relax_delay": float(ACTIVE_INTER_SHOT_US),
        "opx_inter_shot_delay_us": float(ACTIVE_INTER_SHOT_US),
        "opx_unbounded_watchdog_s": float(HOST_WATCHDOG_S),
        "opx_reset_calibration": bundle.to_dict(),
    })
    started = time.monotonic()
    passive = sweep_gain_populations(
        experiment, passive_cfg, gains, calib_params, progress=False
    )
    passive_seconds = time.monotonic() - started
    started = time.monotonic()
    try:
        active = sweep_gain_populations(
            experiment, active_cfg, gains, calib_params, progress=False
        )
    finally:
        reset_gens = getattr(soc, "reset_gens", None)
        if callable(reset_gens):
            reset_gens()
    active_seconds = time.monotonic() - started
    finite = bool(np.all(np.isfinite(passive)) and np.all(np.isfinite(active)))
    rmse = float(np.sqrt(np.mean((active - passive) ** 2))) if finite else float("inf")
    gain_step = int(gains[1] - gains[0])
    passive_peak = int(gains[int(np.argmax(passive))])
    active_peak = int(gains[int(np.argmax(active))])
    peak_steps = abs(active_peak - passive_peak) / max(abs(gain_step), 1)
    passive_contrast = float(np.ptp(passive))
    active_contrast = float(np.ptp(active))
    passed = bool(
        finite
        and rmse <= MAX_CURVE_RMSE
        and peak_steps <= MAX_PEAK_GAIN_STEPS
        and passive_contrast >= MIN_CONTRAST
        and active_contrast >= MIN_CONTRAST
    )
    summary = {
        "status": "pass" if passed else "fail",
        "rabi_equivalent": passed,
        "gains_dac": gains,
        "passive_population": passive,
        "active_population": active,
        "curve_rmse": rmse,
        "maximum_curve_rmse": float(MAX_CURVE_RMSE),
        "passive_peak_gain_dac": passive_peak,
        "active_peak_gain_dac": active_peak,
        "peak_difference_steps": float(peak_steps),
        "maximum_peak_difference_steps": int(MAX_PEAK_GAIN_STEPS),
        "passive_contrast": passive_contrast,
        "active_contrast": active_contrast,
        "minimum_contrast": float(MIN_CONTRAST),
        "passive_seconds": float(passive_seconds),
        "active_seconds": float(active_seconds),
        "speedup": float(passive_seconds / active_seconds),
        "single_shot_fidelity": float(ss.max_F),
        "payload_holdout": bundle.payload.holdout,
        "loop_holdout": bundle.loop.holdout,
    }
    metadata = {
        "created": now.isoformat(),
        "source_commit": source_commit,
        "qubit": QUBIT,
        "base_config": BaseConfig,
        "passive_config": passive_cfg,
        "active_config": active_cfg,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, cls=NpEncoder, indent=2, sort_keys=True) + "\n"
    )
    (output_dir / "run_metadata.json").write_text(
        json.dumps(metadata, cls=NpEncoder, indent=2, sort_keys=True) + "\n"
    )
    np.savez_compressed(
        output_dir / "raw.npz",
        gains_dac=gains,
        passive_population=passive,
        active_population=active,
    )
    fig, axis = plt.subplots(figsize=(8, 5))
    axis.plot(gains, passive, "o-", label="passive 400 us")
    axis.plot(gains, active, "o-", label="opx unbounded 25 us")
    axis.set_xlabel("Qubit gain [DAC]")
    axis.set_ylabel("Excited population")
    axis.set_ylim(-0.05, 1.05)
    axis.legend()
    axis.set_title(f"{QUBIT} Rabi reset equivalence: {summary['status']}")
    fig.tight_layout()
    fig.savefig(output_dir / "rabi_equivalence.png", dpi=160)
    plt.close(fig)
    print(f"status={summary['status']}")
    print(f"curve_rmse={rmse:.6f}")
    print(f"passive_peak_gain_dac={passive_peak}")
    print(f"active_peak_gain_dac={active_peak}")
    print(f"speedup={summary['speedup']:.3f}")
    print(f"output={output_dir}")
    if not passed:
        raise RuntimeError("Rabi active-reset equivalence gate failed")


if __name__ == "__main__":
    main()
