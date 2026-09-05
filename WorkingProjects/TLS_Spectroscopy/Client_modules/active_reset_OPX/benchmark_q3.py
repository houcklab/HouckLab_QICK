"""Standalone q3 runner for the isolated OPX-style active-reset prototype.

Run this file directly on the measurement PC.  It deliberately does not modify
or participate in TLSSpectroscopy.py, T1, or any other production workflow.
"""

import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime

import numpy as np


_root = Path(__file__).resolve()
for parent in _root.parents:
    if (parent / "WorkingProjects").is_dir():
        if str(parent) not in sys.path:
            sys.path.insert(0, str(parent))
        break
else:
    raise RuntimeError("Could not locate the HouckLab_QICK repository root")


from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import (
    BaseConfig,
    outerFolder,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.acquisition import (
    AcquisitionTimeout,
    chunk_sizes,
    dmem_words_from_soccfg,
    run_dmem_block,
    timeout_for_reset_scheme,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import (
    append_records_csv,
    build_interleaved_schedule,
    summarize_records,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.calibration import (
    acquire_calibration,
    load_calibration,
    save_calibration,
    save_raw_calibration,
    validate_confident_calibration,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.benchmark_settings import (
    q3_benchmark_settings,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs import (
    OPXResetBenchmarkProgram,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.records import (
    RECORD_WORDS,
    ShotRecord,
    TerminalStatus,
    max_records,
)


# ---------------------------------------------------------------------------
# User-editable settings
# ---------------------------------------------------------------------------

QUBIT = "q3"

# "smoke" is the first run to send back for inspection.  Change to "full" only
# after the smoke run has sane calibration clouds and zero malformed/time-out
# records.
PROFILE = "full"

RUN_CALIBRATION = True
RUN_BENCHMARK = True

# Required when RUN_CALIBRATION=False.  Nothing is auto-discovered because using
# a stale threshold would defeat the timing-matched calibration.
CALIBRATION_JSON = None

PROFILES = {
    "smoke": {
        "calibration_shots": 1000,
        "blocks": 1,
        "shots_per_condition_per_block": 200,
        "methods": ("none", "opx"),
    },
    "full": {
        "calibration_shots": 4000,
        "blocks": 4,
        "shots_per_condition_per_block": 1000,
        "methods": ("none", "current", "opx"),
    },
}

RANDOM_SEED = 20260904
MIN_CONFIDENT_STATE_FRACTION = 0.2
CURRENT_RESET_ITERS = 3

# At eight words/shot, a 4096-word tProc DMem fits 508 shots from address 32.
# Smaller chunks save progress more often and make failures easier to localize.
MAX_SHOTS_PER_TPROC_BLOCK = 400

Q3_BENCHMARK_SETTINGS = q3_benchmark_settings()
OPX_OVERRIDES = {
    "opx_max_reset_attempts": 8,
    "opx_read_delay_us": 2.0,
    "opx_reset_settle_us": 0.05,
    "opx_verification_delay_us": 0.25,
    "opx_inter_shot_delay_us": 400.0,
    "opx_record_base": 32,
    "opx_done_addr": 1,
    "opx_poll_interval_s": 0.002,
    "opx_timeout_margin": 3.0,
    "opx_unbounded_watchdog_s": 2.0,
    "opx_park_latch_us": 0.02,
    **Q3_BENCHMARK_SETTINGS.opx_overrides(),
}


def _git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=_root.parents[4], text=True
        ).strip()
    except Exception:
        return "unknown"


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _write_json(path, values):
    Path(path).write_text(json.dumps(_json_safe(values), indent=2, sort_keys=True) + "\n")


def _make_output_dir():
    now = datetime.now()
    day = Path(outerFolder) / QUBIT / f"{QUBIT}_{now:%Y_%m_%d}"
    output = day / f"{QUBIT}_{now:%H_%M_%S}_active_reset_OPX_{PROFILE}"
    output.mkdir(parents=True, exist_ok=False)
    return output


def _worst_case_timeout_s(cfg, shots):
    read_us = (
        float(cfg["read_length"])
        + float(cfg.get("adc_trig_offset", 0.0))
        + float(cfg.get("readout_guard_us", 1.0))
        + float(cfg["opx_read_delay_us"])
        + float(cfg["opx_feedback_syncdelay_us"])
    )
    pi_us = 4.0 * float(cfg.get("sigma", 0.1))
    attempts = int(cfg["opx_max_reset_attempts"])
    per_shot_us = (
        (attempts + 2) * read_us
        + attempts * (pi_us + float(cfg["opx_reset_settle_us"]))
        + float(cfg["opx_verification_delay_us"])
        + float(cfg["opx_inter_shot_delay_us"])
        + 2.0 * float(cfg.get("ff_ramp_length", 0.0))
        + 100.0
    )
    return max(10.0, per_shot_us * int(shots) * 1e-6 * float(cfg["opx_timeout_margin"]) + 5.0)


def _run_custom_condition(
    soc,
    soccfg,
    cfg,
    bundle,
    *,
    method,
    preparation,
    shots,
    block,
    csv_path,
    assembly_path,
):
    dmem_words = dmem_words_from_soccfg(soccfg)
    capacity = max_records(dmem_words, int(cfg["opx_record_base"]), RECORD_WORDS)
    capacity = min(capacity, int(MAX_SHOTS_PER_TPROC_BLOCK))
    output = []
    assembly_saved = Path(assembly_path).exists()
    for chunk in chunk_sizes(shots, capacity):
        run_cfg = dict(cfg)
        run_cfg.update({
            "shots": int(chunk),
            "reps": int(chunk),
            "prep_excited": bool(preparation),
            "opx_reset_scheme": str(method),
        })
        program = OPXResetBenchmarkProgram(
            soccfg, run_cfg, bundle.payload, bundle.loop
        )
        if not assembly_saved and method in ("opx", "opx_unbounded"):
            Path(assembly_path).write_text(program.asm())
            binary = np.asarray(program.compile(), dtype=np.uint64)
            Path(str(assembly_path) + ".sha256").write_text(
                __import__("hashlib").sha256(binary.tobytes()).hexdigest() + "\n"
            )
            assembly_saved = True
        try:
            records = run_dmem_block(
                soc,
                program,
                timeout_s=timeout_for_reset_scheme(
                    method,
                    bounded_timeout_s=_worst_case_timeout_s(run_cfg, chunk),
                    unbounded_watchdog_s=run_cfg["opx_unbounded_watchdog_s"],
                ),
                poll_interval_s=float(run_cfg["opx_poll_interval_s"]),
            )
        except AcquisitionTimeout as exc:
            if exc.partial_records:
                append_records_csv(
                    csv_path,
                    exc.partial_records,
                    axis=bundle.reference_axis,
                    assignment=bundle.loop,
                    method=method,
                    block=block,
                )
            raise
        append_records_csv(
            csv_path,
            records,
            axis=bundle.reference_axis,
            assignment=bundle.loop,
            method=method,
            block=block,
        )
        output.extend(records)
    return output


def _run_current_condition(soc, soccfg, cfg, bundle, *, preparation, shots):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mResetBench import (
        BenchResetProgram,
    )

    run_cfg = dict(cfg)
    thresholds = bundle.payload.assembly_thresholds()
    run_cfg.update({
        "shots": int(shots),
        "reps": int(shots),
        "prep_excited": bool(preparation),
        "reset_scheme": "rot2",
        "reset_max_iters": int(CURRENT_RESET_ITERS),
        "rot_c_int": int(bundle.payload.c_int),
        "rot_s_int": int(bundle.payload.s_int),
        "rot_excite_threshold": int(thresholds["excited"]),
    })
    program = BenchResetProgram(soccfg, run_cfg)
    i_values, q_values = program.acquire(soc, load_pulses=True, progress=False)
    return [
        ShotRecord(
            preparation=int(preparation),
            initial_z=0,
            reset_attempts=int(CURRENT_RESET_ITERS),
            pi_pulses=-1,
            terminal_status=TerminalStatus.NO_RESET,
            final_i=int(i_value),
            final_q=int(q_value),
            last_z=0,
        )
        for i_value, q_value in zip(i_values, q_values)
    ]


def _plot_calibration(raw, bundle, path):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(11, 9))
    for row, (context, calibration) in enumerate((
        ("payload", bundle.payload), ("loop", bundle.loop)
    )):
        ground = raw[context]["ground"]
        excited = raw[context]["excited"]
        axes[row, 0].scatter(ground["i"], ground["q"], s=3, alpha=0.25, label="g")
        axes[row, 0].scatter(excited["i"], excited["q"], s=3, alpha=0.25, label="e")
        axes[row, 0].set(title=f"{context} raw I/Q", xlabel="I", ylabel="Q")
        axes[row, 0].legend()
        zg = calibration.project(ground["i"], ground["q"])
        ze = calibration.project(excited["i"], excited["q"])
        axes[row, 1].hist(zg, bins=80, alpha=0.55, density=True, label="g")
        axes[row, 1].hist(ze, bins=80, alpha=0.55, density=True, label="e")
        axes[row, 1].axvline(calibration.ground_threshold, color="C2", ls="--")
        axes[row, 1].axvline(calibration.excited_threshold, color="C3", ls="--")
        axes[row, 1].set(title=f"{context} projected", xlabel="canonical z")
        axes[row, 1].legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _plot_summary(summary, path):
    import matplotlib.pyplot as plt

    keys = sorted(summary)
    labels = [f"{method}\nprep {prep}" for method, prep in keys]
    residuals = [summary[key]["verification_excited_fraction"] for key in keys]
    timeouts = [summary[key]["timeout_fraction"] for key in keys]
    attempts = [summary[key]["mean_reset_attempts"] for key in keys]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    axes[0].bar(labels, residuals)
    axes[0].set(title="Post-reset excited fraction", ylim=(0, max(0.15, max(residuals) * 1.2)))
    axes[1].bar(labels, timeouts)
    axes[1].set(title="Max-iteration fraction", ylim=(0, max(0.02, max(timeouts) * 1.2)))
    axes[2].bar(labels, attempts)
    axes[2].set(title="Mean corrective attempts")
    for axis in axes:
        axis.tick_params(axis="x", rotation=30)
        axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main():
    if PROFILE not in PROFILES:
        raise ValueError(f"PROFILE must be one of {tuple(PROFILES)}")
    profile = dict(PROFILES[PROFILE])
    cfg = dict(BaseConfig)
    cfg.update(OPX_OVERRIDES)
    cfg.pop("flux_tail_compensation", None)
    output_dir = _make_output_dir()
    print(f"\nOPX-style active reset | {QUBIT} | profile={PROFILE}")
    print(f"Output: {output_dir}")
    print("Production experiment modules are not modified or selected by this runner.\n")

    import qick
    if str(qick.__version__) != "0.2.133":
        raise RuntimeError(
            f"This prototype is validated for qick 0.2.133, found {qick.__version__}"
        )
    soc, soccfg = makeProxy()
    metadata = {
        "qubit": QUBIT,
        "profile": PROFILE,
        "created": datetime.now().isoformat(),
        "source_commit": _git_commit(),
        "qick_version": str(qick.__version__),
        "profile_settings": profile,
        "opx_overrides": OPX_OVERRIDES,
    }
    _write_json(output_dir / "run_metadata.json", metadata)

    if RUN_CALIBRATION:
        print("[1/2] Acquiring timing-matched payload and in-loop references ...")
        bundle, raw = acquire_calibration(
            soc,
            soccfg,
            cfg,
            shots=int(profile["calibration_shots"]),
            **Q3_BENCHMARK_SETTINGS.calibration_options(),
            metadata=metadata,
        )
        calibration_path = save_calibration(output_dir / "calibration.json", bundle)
        save_raw_calibration(output_dir / "calibration_raw.npz", raw)
        _plot_calibration(raw, bundle, output_dir / "calibration.png")
        print(f"  calibration saved: {calibration_path}")
        print(f"  payload holdout: {bundle.payload.holdout}")
        print(f"  loop holdout:    {bundle.loop.holdout}")
    else:
        if CALIBRATION_JSON is None:
            raise FileNotFoundError(
                "RUN_CALIBRATION=False requires an explicit CALIBRATION_JSON; "
                "stale calibrations are never auto-selected"
            )
        bundle = load_calibration(CALIBRATION_JSON)

    validate_confident_calibration(
        bundle,
        min_confident_fraction=MIN_CONFIDENT_STATE_FRACTION,
    )

    if not RUN_BENCHMARK:
        print("RUN_BENCHMARK=False: calibration complete; stopping.")
        return

    print("\n[2/2] Running interleaved reset benchmark ...")
    csv_path = output_dir / "shots.csv"
    assembly_path = output_dir / "opx_reset.asm"
    accumulated = {}
    schedule = build_interleaved_schedule(
        methods=profile["methods"], blocks=profile["blocks"], seed=RANDOM_SEED
    )
    shots = int(profile["shots_per_condition_per_block"])
    for index, (block, method, preparation) in enumerate(schedule, start=1):
        print(
            f"  [{index:02d}/{len(schedule):02d}] block={block + 1} "
            f"method={method:<7} prep={'e' if preparation else 'g'} shots={shots}",
            flush=True,
        )
        if method in ("none", "opx"):
            records = _run_custom_condition(
                soc,
                soccfg,
                cfg,
                bundle,
                method=method,
                preparation=preparation,
                shots=shots,
                block=block,
                csv_path=csv_path,
                assembly_path=assembly_path,
            )
        elif method == "current":
            records = _run_current_condition(
                soc, soccfg, cfg, bundle,
                preparation=preparation, shots=shots,
            )
            append_records_csv(
                csv_path,
                records,
                axis=bundle.reference_axis,
                assignment=bundle.loop,
                method=method,
                block=block,
            )
        else:
            raise ValueError(f"unknown benchmark method {method!r}")
        accumulated.setdefault((method, preparation), []).extend(records)
        partial_summary = {
            f"{key[0]}_prep_{key[1]}": summarize_records(value, bundle.reference_axis, bundle.loop)
            for key, value in accumulated.items()
        }
        _write_json(output_dir / "summary_partial.json", partial_summary)

    summary = {
        key: summarize_records(records, bundle.reference_axis, bundle.loop)
        for key, records in accumulated.items()
    }
    serializable = {f"{key[0]}_prep_{key[1]}": value for key, value in summary.items()}
    _write_json(output_dir / "summary.json", serializable)
    _plot_summary(summary, output_dir / "benchmark.png")
    print("\nResults:")
    for (method, preparation), values in sorted(summary.items()):
        print(
            f"  {method:<7} prep={'e' if preparation else 'g'}: "
            f"P(e)={values['verification_excited_fraction']:.4f}, "
            f"timeouts={values['timeout_fraction']:.4f}, "
            f"mean attempts={values['mean_reset_attempts']:.2f}"
        )
    print(f"\nCompleted: {output_dir}")


if __name__ == "__main__":
    main()
