import csv
import datetime
import json
import os
import time

import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import (
    BaseConfig, outerFolder)
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mOptimize1Q import (
    QubitPulseOptimize)


QUBIT = "q4"
GAINS = [2650, 2700, 2750, 2800, 2850]
FREQUENCIES_MHZ = [2534.50, 2534.55]
BLOCKS = 5
SHOTS_PER_BLOCK = 500
RAMSEY_ROUNDS = 2
ORDER_SEED = 20260730


def candidate_order(candidates, block_index, seed=ORDER_SEED):
    rng = np.random.default_rng(int(seed))
    base = list(candidates)
    rng.shuffle(base)
    shift = int(block_index) // 2
    order = base[shift:] + base[:shift]
    return order if int(block_index) % 2 == 0 else list(reversed(order))


def block_quality(record):
    metrics = record["metrics"]
    values = (
        record["population_1x"], record["population_4x"],
        metrics["coherence_magnitude"], metrics["reference_contrast"],
    )
    if not all(np.isfinite(float(value)) for value in values):
        return float("nan"), False
    eligible = bool(
        abs(float(record["population_1x"]) - 0.5) <= 0.30
        and float(metrics["reference_contrast"]) >= 0.20)
    quality = (float(metrics["coherence_magnitude"])
               - abs(float(record["population_4x"])))
    return quality, eligible


def summarize(records):
    groups = {}
    for record in records:
        if record.get("error"):
            continue
        key = (float(record["freq_mhz"]), int(record["gain"]))
        groups.setdefault(key, []).append(record)
    summary = []
    for (freq, gain), rows in groups.items():
        quality = np.asarray([row["quality"] for row in rows], dtype=float)
        p1 = np.asarray([row["population_1x"] for row in rows], dtype=float)
        p4 = np.asarray([row["population_4x"] for row in rows], dtype=float)
        coherence = np.asarray(
            [row["metrics"]["coherence_magnitude"] for row in rows], dtype=float)
        ramsey_i = np.asarray(
            [row["metrics"]["ramsey_i"] for row in rows], dtype=float)
        ramsey_q = np.asarray(
            [row["metrics"]["ramsey_q"] for row in rows], dtype=float)
        median_quality = float(np.nanmedian(quality))
        quality_mad = float(np.nanmedian(np.abs(quality - median_quality)))
        item = {
            "freq_mhz": freq,
            "gain": gain,
            "blocks_completed": len(rows),
            "completion_fraction": float(len(rows) / BLOCKS),
            "eligible_fraction": float(np.mean([row["eligible"] for row in rows])),
            "validation_pass_fraction": float(
                np.mean([bool(row["passed"]) for row in rows])),
            "median_population_1x": float(np.nanmedian(p1)),
            "median_abs_population_4x": float(np.nanmedian(np.abs(p4))),
            "median_coherence": float(np.nanmedian(coherence)),
            "median_ramsey_i": float(np.nanmedian(ramsey_i)),
            "median_ramsey_q": float(np.nanmedian(ramsey_q)),
            "median_quality": median_quality,
            "quality_mad": quality_mad,
            "robust_score": median_quality - quality_mad,
        }
        summary.append(item)
    summary.sort(key=lambda row: (
        row["blocks_completed"] == BLOCKS,
        row["eligible_fraction"] >= 0.6,
        row["robust_score"],
        row["validation_pass_fraction"]), reverse=True)
    return summary


def save_outputs(records, summary, base_path):
    record_fields = [
        "block", "visit", "freq_mhz", "gain", "elapsed_s", "passed",
        "eligible", "quality", "population_1x", "population_4x",
        "P_g", "P_e", "P_i", "P_q", "reference_contrast", "ramsey_i",
        "ramsey_q", "coherence_magnitude", "coherence_phase_rad", "error",
    ]
    record_csv = f"{base_path}_blocks.csv"
    with open(record_csv, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=record_fields)
        writer.writeheader()
        for record in records:
            metrics = record.get("metrics", {})
            writer.writerow({
                "block": record["block"],
                "visit": record["visit"],
                "freq_mhz": record["freq_mhz"],
                "gain": record["gain"],
                "elapsed_s": record["elapsed_s"],
                "passed": record.get("passed"),
                "eligible": record.get("eligible"),
                "quality": record.get("quality"),
                "population_1x": record.get("population_1x"),
                "population_4x": record.get("population_4x"),
                "P_g": metrics.get("P_g"),
                "P_e": metrics.get("P_e"),
                "P_i": metrics.get("P_i"),
                "P_q": metrics.get("P_q"),
                "reference_contrast": metrics.get("reference_contrast"),
                "ramsey_i": metrics.get("ramsey_i"),
                "ramsey_q": metrics.get("ramsey_q"),
                "coherence_magnitude": metrics.get("coherence_magnitude"),
                "coherence_phase_rad": metrics.get("coherence_phase_rad"),
                "error": record.get("error"),
            })
    summary_csv = f"{base_path}_summary.csv"
    with open(summary_csv, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    payload = {
        "settings": {
            "qubit": QUBIT,
            "gains": GAINS,
            "frequencies_mhz": FREQUENCIES_MHZ,
            "blocks": BLOCKS,
            "shots_per_block": SHOTS_PER_BLOCK,
            "ramsey_rounds": RAMSEY_ROUNDS,
            "order_seed": ORDER_SEED,
        },
        "base_config": BaseConfig,
        "recommended": summary[0],
        "summary": summary,
        "records": records,
    }
    json_path = f"{base_path}.json"
    with open(json_path, "w") as handle:
        json.dump(payload, handle, indent=2, default=str)
    gains = np.asarray(GAINS, dtype=float)
    freqs = np.asarray(FREQUENCIES_MHZ, dtype=float)
    shape = (len(gains), len(freqs))
    maps = {key: np.full(shape, np.nan) for key in (
        "median_coherence", "median_abs_population_4x", "robust_score",
        "median_population_1x")}
    for row in summary:
        i = int(np.where(gains == row["gain"])[0][0])
        j = int(np.where(np.isclose(freqs, row["freq_mhz"]))[0][0])
        for key in maps:
            maps[key][i, j] = row[key]
    fig, axes = plt.subplots(2, 2, figsize=(10, 9), constrained_layout=True)
    labels = {
        "median_coherence": "Median |C|",
        "median_abs_population_4x": "Median |P4|",
        "robust_score": "Median(|C|-|P4|) - MAD",
        "median_population_1x": "Median P1",
    }
    for ax, key in zip(axes.flat, maps):
        image = ax.imshow(maps[key], origin="lower", aspect="auto",
                          extent=[freqs[0] - 0.025, freqs[-1] + 0.025,
                                  gains[0] - 25, gains[-1] + 25])
        fig.colorbar(image, ax=ax)
        ax.set(xlabel="Qubit frequency [MHz]", ylabel="X90 gain [DAC]",
               title=labels[key])
        ax.plot(summary[0]["freq_mhz"], summary[0]["gain"], "wx", ms=12, mew=2)
    plot_path = f"{base_path}.png"
    fig.savefig(plot_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return record_csv, summary_csv, json_path, plot_path


def run(soc, soccfg, outer_folder=outerFolder):
    candidates = [(float(freq), int(gain))
                  for gain in GAINS for freq in FREQUENCIES_MHZ]
    records = []
    started = time.time()
    total = BLOCKS * len(candidates)
    completed = 0
    now = datetime.datetime.now()
    folder = os.path.join(
        outer_folder, QUBIT, f"{QUBIT}_{now:%Y_%m_%d}")
    os.makedirs(folder, exist_ok=True)
    base_path = os.path.join(folder, f"{QUBIT}_{now:%H_%M_%S}_X90_Candidate_Audit")
    print("=" * 88)
    print("X90 CANDIDATE AUDIT")
    print(f"{len(candidates)} candidates x {BLOCKS} balanced blocks x "
          f"{SHOTS_PER_BLOCK} shots")
    print("quality = |C| - |P4|; final rank uses median quality minus its MAD")
    print(f"checkpoint prefix: {base_path}")
    print("=" * 88)
    for block in range(BLOCKS):
        order = candidate_order(candidates, block)
        print(f"block {block + 1}/{BLOCKS}")
        for visit, (freq, gain) in enumerate(order):
            cfg = dict(BaseConfig)
            cfg.update({
                "reset_mode": "passive",
                "pulse_type": "X90",
                "num_pi": 1,
                "x90_validation_shots": SHOTS_PER_BLOCK,
                "x90_validation_rounds": RAMSEY_ROUNDS,
            })
            exp = QubitPulseOptimize(
                soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
                suffix="X90_Candidate_Audit", cfg=cfg,
                freqs_mhz=np.asarray([freq]), gains=np.asarray([gain]),
                shots=SHOTS_PER_BLOCK, num_pi=1, pulse_type="X90", save=False)
            t0 = time.time()
            try:
                result = exp._validate_x90(freq, gain)
                quality, eligible = block_quality(result)
                record = {
                    "block": block,
                    "visit": visit,
                    "freq_mhz": freq,
                    "gain": gain,
                    "elapsed_s": time.time() - t0,
                    "eligible": eligible,
                    "quality": quality,
                    **result,
                }
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                record = {
                    "block": block,
                    "visit": visit,
                    "freq_mhz": freq,
                    "gain": gain,
                    "elapsed_s": time.time() - t0,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            records.append(record)
            completed += 1
            elapsed = time.time() - started
            eta = elapsed / completed * (total - completed)
            if record.get("error"):
                detail = record["error"]
            else:
                detail = (f"P1 {record['population_1x']:.3f}  "
                          f"P4 {record['population_4x']:.3f}  "
                          f"|C| {record['metrics']['coherence_magnitude']:.3f}  "
                          f"quality {record['quality']:+.3f}")
            print(f"  {completed:>2}/{total}  {freq:.5f} MHz  gain {gain:>4}  "
                  f"{detail}  ETA {eta / 60:.1f} min", flush=True)
        checkpoint = summarize(records)
        if checkpoint:
            save_outputs(records, checkpoint, base_path)
            print(f"saved checkpoint after block {block + 1}", flush=True)
    summary = summarize(records)
    if not summary:
        raise RuntimeError("no X90 candidate completed successfully")
    paths = save_outputs(records, summary, base_path)
    print("\nranked candidates")
    print(" rank     frequency   gain   P1     |P4|    |C|    robust   blocks  eligible  pass")
    for index, row in enumerate(summary, start=1):
        print(f" {index:>3}   {row['freq_mhz']:.5f}  {row['gain']:>4}  "
              f"{row['median_population_1x']:.3f}  "
              f"{row['median_abs_population_4x']:.3f}  "
              f"{row['median_coherence']:.3f}  {row['robust_score']:+.3f}  "
              f"{row['blocks_completed']:>2}/{BLOCKS:<2}   "
              f"{row['eligible_fraction']:.2f}      "
              f"{row['validation_pass_fraction']:.2f}")
    best = summary[0]
    print("\nrecommended parameters")
    print(f"qubit_pi_freq = {best['freq_mhz']:.5f}")
    print(f"qubit_pi2_gain = {best['gain']}")
    if best["blocks_completed"] < BLOCKS or best["eligible_fraction"] < 0.6:
        print("WARNING: the recommendation is incomplete or was not eligible in a "
              "majority of blocks; do not update initialize.py from this run.")
    print("\noutputs")
    for path in paths:
        print(path)
    return {"records": records, "summary": summary, "recommended": best,
            "paths": paths}


def main():
    soc, soccfg = makeProxy()
    run(soc, soccfg, outerFolder)


if __name__ == "__main__":
    main()
