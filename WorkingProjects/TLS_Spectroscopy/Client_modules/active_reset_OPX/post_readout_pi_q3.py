import csv
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys

import numpy as np


_source = Path(__file__).resolve()
_repo_root = None
for _parent in _source.parents:
    if (_parent / "WorkingProjects").is_dir():
        _repo_root = _parent
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break
if _repo_root is None:
    raise RuntimeError("Could not locate the HouckLab_QICK repository root")


from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import (
    BaseConfig,
    outerFolder,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import (
    ReferenceAxis,
    summarize_post_readout_pi,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs import (
    TimingMatchedReferenceProgram,
)


QUBIT = "q3"
SHOTS = 500
PASSIVE_RESET_US = 400.0
READ_DELAY_US = 2.0
PRE_PI_DELAYS_US = [2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0, 32.0, 48.0, 66.0]
RESET_SETTLE_US = 0.05
MIN_TRANSFER_CONTRAST = 0.4
MAX_FIRST_PREPARATION_DELTA = 0.2
MIN_SECOND_PI_POPULATION = 0.4
MAX_ABS_SECOND_GROUND_POPULATION = 0.3
RANDOM_SEED = 20260905


def _git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=_repo_root,
            text=True,
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
    Path(path).write_text(
        json.dumps(_json_safe(values), indent=2, sort_keys=True) + "\n"
    )


def _make_output_dir():
    now = datetime.now()
    day = Path(outerFolder) / QUBIT / f"{QUBIT}_{now:%Y_%m_%d}"
    output = day / f"{QUBIT}_{now:%H_%M_%S}_active_reset_OPX_post_readout_pi"
    output.mkdir(parents=True, exist_ok=False)
    return output


def _base_config():
    cfg = dict(BaseConfig)
    cfg.pop("flux_tail_compensation", None)
    cfg.update({
        "shots": int(SHOTS),
        "reps": int(SHOTS),
        "relax_delay": float(PASSIVE_RESET_US),
        "opx_read_delay_us": float(READ_DELAY_US),
        "opx_reset_settle_us": float(RESET_SETTLE_US),
        "opx_park_latch_us": 0.02,
    })
    return cfg


def _acquire_payload(soc, soccfg, cfg, prep_excited):
    run_cfg = dict(cfg)
    run_cfg.update({
        "prep_excited": bool(prep_excited),
        "opx_reference_context": "payload",
    })
    program = TimingMatchedReferenceProgram(soccfg, run_cfg)
    i_values, q_values = program.acquire(
        soc,
        load_pulses=True,
        progress=False,
    )
    return np.asarray(i_values, dtype=np.int64), np.asarray(q_values, dtype=np.int64)


def _acquire_pair(soc, soccfg, cfg, pre_pi_delay_us, prep_excited):
    run_cfg = dict(cfg)
    run_cfg.update({
        "prep_excited": bool(prep_excited),
        "opx_reference_context": "loop",
        "opx_feedback_syncdelay_us": float(pre_pi_delay_us),
    })
    program = TimingMatchedReferenceProgram(soccfg, run_cfg)
    i_reads, q_reads = program.acquire_readouts(
        soc,
        load_pulses=True,
        progress=False,
    )
    return np.asarray(i_reads, dtype=np.int64), np.asarray(q_reads, dtype=np.int64)


def _write_csv(path, rows):
    fields = tuple(rows[0])
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _plot(summary, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = summary["rows"]
    delay = np.asarray([row["pre_pi_delay_us"] for row in rows])
    first_ground = np.asarray([row["first_ground_population"] for row in rows])
    first_pi = np.asarray([row["first_pi_population"] for row in rows])
    second_ground = np.asarray([row["second_ground_population"] for row in rows])
    second_pi = np.asarray([row["second_pi_population"] for row in rows])
    contrast = np.asarray([row["transfer_contrast"] for row in rows])
    passed = np.asarray([row["passed"] for row in rows], dtype=bool)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    axes[0].plot(delay, first_ground, "o-", label="first readout, control")
    axes[0].plot(delay, first_pi, "o-", label="first readout, later pi")
    axes[0].axhline(0.0, color="black", linewidth=1)
    axes[0].set(
        xscale="log",
        xlabel="ADC end to pi pulse [us]",
        ylabel="population from payload references",
        title="First readout extraction control",
    )
    axes[0].legend()
    axes[0].grid(alpha=0.25)

    axes[1].plot(delay, second_ground, "o-", label="second readout, no pi")
    axes[1].plot(delay, second_pi, "o-", label="second readout, pi")
    axes[1].plot(delay, contrast, "o--", label="pi transfer contrast")
    if np.any(passed):
        axes[1].scatter(delay[passed], second_pi[passed], s=80, facecolors="none", edgecolors="C2")
    axes[1].axhline(0.0, color="black", linewidth=1)
    axes[1].axhline(1.0, color="black", linewidth=1, linestyle="--")
    axes[1].set(
        xscale="log",
        xlabel="ADC end to pi pulse [us]",
        ylabel="population from payload references",
        title="Post-readout pi response",
    )
    axes[1].legend()
    axes[1].grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main():
    import qick

    if str(qick.__version__) != "0.2.133":
        raise RuntimeError(
            f"This diagnostic is validated for qick 0.2.133, found {qick.__version__}"
        )
    cfg = _base_config()
    output_dir = _make_output_dir()
    print(f"\nPost-readout pi diagnostic | {QUBIT}")
    print(f"Output: {output_dir}\n")
    soc, soccfg = makeProxy()

    print("stage=payload_references")
    payload_ground_i, payload_ground_q = _acquire_payload(
        soc,
        soccfg,
        cfg,
        False,
    )
    payload_excited_i, payload_excited_q = _acquire_payload(
        soc,
        soccfg,
        cfg,
        True,
    )
    axis = ReferenceAxis.from_centers(
        np.mean(payload_ground_i),
        np.mean(payload_ground_q),
        np.mean(payload_excited_i),
        np.mean(payload_excited_q),
    )

    rng = np.random.default_rng(RANDOM_SEED)
    conditions = [
        (float(delay), bool(preparation))
        for delay in PRE_PI_DELAYS_US
        for preparation in (False, True)
    ]
    raw = {}
    print("stage=delay_sweep")
    for index in rng.permutation(len(conditions)):
        delay, preparation = conditions[int(index)]
        print(
            f"pre_pi_delay_us={delay:g} prep_after_readout={'pi' if preparation else 'none'}",
            flush=True,
        )
        raw[(delay, preparation)] = _acquire_pair(
            soc,
            soccfg,
            cfg,
            delay,
            preparation,
        )

    pre_pi = np.asarray(PRE_PI_DELAYS_US, dtype=float)
    ground_i = np.stack([raw[(float(delay), False)][0] for delay in pre_pi])
    ground_q = np.stack([raw[(float(delay), False)][1] for delay in pre_pi])
    pi_i = np.stack([raw[(float(delay), True)][0] for delay in pre_pi])
    pi_q = np.stack([raw[(float(delay), True)][1] for delay in pre_pi])

    first_ground = np.asarray([
        axis.mean_population(ground_i[index, :, 0], ground_q[index, :, 0])
        for index in range(pre_pi.size)
    ])
    first_pi = np.asarray([
        axis.mean_population(pi_i[index, :, 0], pi_q[index, :, 0])
        for index in range(pre_pi.size)
    ])
    second_ground = np.asarray([
        axis.mean_population(ground_i[index, :, 1], ground_q[index, :, 1])
        for index in range(pre_pi.size)
    ])
    second_pi = np.asarray([
        axis.mean_population(pi_i[index, :, 1], pi_q[index, :, 1])
        for index in range(pre_pi.size)
    ])
    summary = summarize_post_readout_pi(
        pre_pi_delay_us=pre_pi,
        read_delay_us=READ_DELAY_US,
        first_ground_population=first_ground,
        first_pi_population=first_pi,
        second_ground_population=second_ground,
        second_pi_population=second_pi,
        min_transfer_contrast=MIN_TRANSFER_CONTRAST,
        max_first_preparation_delta=MAX_FIRST_PREPARATION_DELTA,
        min_second_pi_population=MIN_SECOND_PI_POPULATION,
        max_abs_second_ground_population=MAX_ABS_SECOND_GROUND_POPULATION,
    )
    summary.update({
        "read_delay_us": float(READ_DELAY_US),
        "shots_per_condition": int(SHOTS),
        "payload_ground_center": [
            float(np.mean(payload_ground_i)),
            float(np.mean(payload_ground_q)),
        ],
        "payload_excited_center": [
            float(np.mean(payload_excited_i)),
            float(np.mean(payload_excited_q)),
        ],
        "criteria": {
            "min_transfer_contrast": float(MIN_TRANSFER_CONTRAST),
            "max_first_preparation_delta": float(MAX_FIRST_PREPARATION_DELTA),
            "min_second_pi_population": float(MIN_SECOND_PI_POPULATION),
            "max_abs_second_ground_population": float(MAX_ABS_SECOND_GROUND_POPULATION),
        },
    })

    np.savez_compressed(
        output_dir / "post_readout_pi_raw.npz",
        pre_pi_delay_us=pre_pi,
        payload_ground_i=payload_ground_i,
        payload_ground_q=payload_ground_q,
        payload_excited_i=payload_excited_i,
        payload_excited_q=payload_excited_q,
        ground_i=ground_i,
        ground_q=ground_q,
        pi_i=pi_i,
        pi_q=pi_q,
    )
    _write_csv(output_dir / "summary.csv", summary["rows"])
    _write_json(output_dir / "summary.json", summary)
    _write_json(output_dir / "run_metadata.json", {
        "created": datetime.now().isoformat(),
        "source_commit": _git_commit(),
        "qick_version": str(qick.__version__),
        "qubit": QUBIT,
        "ff_park_gain": int(cfg.get("ff_park_gain", 0)),
        "qubit_pi_freq_mhz": float(cfg["qubit_pi_freq"]),
        "qubit_pi_gain": int(cfg["qubit_pi_gain"]),
        "read_pulse_freq_mhz": float(cfg["read_pulse_freq"]),
        "read_pulse_gain": int(cfg["read_pulse_gain"]),
        "read_length_us": float(cfg["read_length"]),
        "shots": int(SHOTS),
        "passive_reset_us": float(PASSIVE_RESET_US),
        "read_delay_us": float(READ_DELAY_US),
        "pre_pi_delays_us": pre_pi.tolist(),
        "reset_settle_us": float(RESET_SETTLE_US),
    })
    _plot(summary, output_dir / "post_readout_pi.png")

    print("\nResults:")
    for row in summary["rows"]:
        print(
            f"  pre_pi_delay={row['pre_pi_delay_us']:6.2f} us "
            f"P1_control={row['first_ground_population']:+.3f} "
            f"P1_pi={row['first_pi_population']:+.3f} "
            f"P2_control={row['second_ground_population']:+.3f} "
            f"P2_pi={row['second_pi_population']:+.3f} "
            f"contrast={row['transfer_contrast']:+.3f} "
            f"pass={row['passed']}"
        )
    print(
        f"selected_pre_pi_delay_us={summary['selected_pre_pi_delay_us']}"
    )
    print(f"\nCompleted: {output_dir}")


if __name__ == "__main__":
    main()
