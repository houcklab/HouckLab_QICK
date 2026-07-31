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
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import (
    SingleShot1Q, discriminate_shots)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import (
    suppress_stdout)


QUBIT = "q4"
SIGMAS_US = [0.25, 0.15, 0.10]
FREQUENCIES_MHZ = [2534.50, 2534.55]
GAIN_SCALES = [0.90, 0.95, 1.00, 1.05, 1.10]
SURVEY_COUNTS = [1, 2, 3, 4]
SURVEY_SHOTS = 300
FINE_COUNTS = [1, 2, 3, 4, 5, 6, 7, 8]
FINE_SHOTS = 500
FINE_BLOCKS = 3
FINE_PER_SIGMA = 2
ORDER_SEED = 20260731


def rounded_gain(value):
    return int(25 * round(float(value) / 25.0))


def build_candidates(base_config=BaseConfig):
    base_sigma = float(base_config["sigma"])
    base_gain = int(base_config["qubit_pi2_gain"])
    candidates = []
    for sigma in SIGMAS_US:
        center = base_gain * base_sigma / float(sigma)
        for freq in FREQUENCIES_MHZ:
            for scale in GAIN_SCALES:
                x90_gain = rounded_gain(center * float(scale))
                candidates.append({
                    "sigma_us": float(sigma),
                    "freq_mhz": float(freq),
                    "x90_gain": x90_gain,
                    "x180_gain": 2 * x90_gain,
                })
    return candidates


def candidate_key(candidate):
    return (float(candidate["sigma_us"]), float(candidate["freq_mhz"]),
            int(candidate["x90_gain"]))


def ordered_candidates(candidates, block, seed=ORDER_SEED):
    rng = np.random.default_rng(int(seed))
    base = list(candidates)
    rng.shuffle(base)
    shift = int(block) // 2
    order = base[shift:] + base[:shift]
    return order if int(block) % 2 == 0 else list(reversed(order))


def ideal_population(count):
    return float(0.5 * (1.0 - np.cos(int(count) * np.pi / 2.0)))


def acquire_reference(soc, soccfg, outer_folder, shots):
    cfg = dict(BaseConfig)
    cfg.update({
        "reset_mode": "passive",
        "shots": int(shots),
        "reps": int(shots),
        "qubit_gain": int(cfg["qubit_pi_gain"]),
    })
    with suppress_stdout():
        ss = SingleShot1Q(
            soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
            suffix="X90_Pulse_Train_Reference", cfg=cfg, plot=False,
            save=False, repeats=1, min_F=0.0)
        ss.acquire(progress=False, plotDisp=False)
    assignment = {
        "P_g": float(np.mean(discriminate_shots(
            ss.I_0, ss.Q_0, ss.calib_params))),
        "P_e": float(np.mean(discriminate_shots(
            ss.I_1, ss.Q_1, ss.calib_params))),
    }
    assignment["contrast"] = assignment["P_e"] - assignment["P_g"]
    return dict(ss.calib_params), assignment


def measure_population(soc, soccfg, outer_folder, candidate, gain, count,
                       shots, calib_params, assignment):
    cfg = dict(BaseConfig)
    cfg.update({
        "reset_mode": "passive",
        "sigma": float(candidate["sigma_us"]),
        "qubit_pi_freq": float(candidate["freq_mhz"]),
        "qubit_freq": float(candidate["freq_mhz"]),
        "qubit_gain": int(gain),
        "shots": int(shots),
        "reps": int(shots),
    })
    with suppress_stdout():
        ss = SingleShot1Q(
            soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outer_folder,
            suffix="X90_Pulse_Train_Point", cfg=cfg, plot=False,
            save=False, repeats=int(count), min_F=0.0)
        ss.acquire(progress=False, plotDisp=False)
    measured = float(np.mean(discriminate_shots(
        ss.I_1, ss.Q_1, calib_params)))
    contrast = float(assignment["contrast"])
    corrected = ((measured - float(assignment["P_g"])) / contrast
                 if contrast > 0.0 else np.nan)
    return measured, corrected


def measure_candidate(soc, soccfg, outer_folder, stage, block, visit,
                      candidate, counts, shots, calib_params, assignment):
    record = {
        "stage": str(stage),
        "block": int(block),
        "visit": int(visit),
        **candidate,
        "shots": int(shots),
        "assignment": dict(assignment),
        "populations": {},
    }
    started = time.time()
    try:
        for count in counts:
            measured, corrected = measure_population(
                soc, soccfg, outer_folder, candidate,
                candidate["x90_gain"], count, shots, calib_params, assignment)
            record["populations"][str(int(count))] = {
                "measured": measured,
                "corrected": corrected,
                "ideal": ideal_population(count),
            }
        measured, corrected = measure_population(
            soc, soccfg, outer_folder, candidate,
            candidate["x180_gain"], 1, shots, calib_params, assignment)
        record["x180_population"] = {
            "measured": measured,
            "corrected": corrected,
            "ideal": 1.0,
        }
        errors = [
            values["corrected"] - values["ideal"]
            for values in record["populations"].values()
        ]
        errors.append(corrected - 1.0)
        record["rmse"] = float(np.sqrt(np.mean(np.square(errors))))
        p1 = record["populations"].get("1", {}).get("corrected", np.nan)
        p2 = record["populations"].get("2", {}).get("corrected", np.nan)
        p4 = record["populations"].get("4", {}).get("corrected", np.nan)
        record["passed"] = bool(
            assignment["contrast"] >= 0.20
            and np.isfinite(record["rmse"])
            and record["rmse"] <= 0.20
            and abs(p1 - 0.50) <= 0.20
            and p2 >= 0.70
            and abs(p4) <= 0.20
            and corrected >= 0.70)
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["rmse"] = np.nan
        record["passed"] = False
    record["elapsed_s"] = time.time() - started
    return record


def survey_summary(records):
    rows = [row for row in records if row["stage"] == "survey"
            and not row.get("error")]
    return sorted(rows, key=lambda row: float(row["rmse"]))


def fine_summary(records):
    groups = {}
    for record in records:
        if record["stage"] != "fine" or record.get("error"):
            continue
        groups.setdefault(candidate_key(record), []).append(record)
    result = []
    for key, rows in groups.items():
        rmses = np.asarray([row["rmse"] for row in rows], dtype=float)
        median_rmse = float(np.nanmedian(rmses))
        mad_rmse = float(np.nanmedian(np.abs(rmses - median_rmse)))
        counts = sorted(int(value) for value in rows[0]["populations"])
        populations = {
            str(count): float(np.nanmedian([
                row["populations"][str(count)]["corrected"] for row in rows
            ])) for count in counts
        }
        result.append({
            "sigma_us": key[0],
            "freq_mhz": key[1],
            "x90_gain": key[2],
            "x180_gain": 2 * key[2],
            "blocks_completed": len(rows),
            "pass_fraction": float(np.mean([row["passed"] for row in rows])),
            "median_rmse": median_rmse,
            "rmse_mad": mad_rmse,
            "robust_rmse": median_rmse + mad_rmse,
            "median_x180_population": float(np.nanmedian([
                row["x180_population"]["corrected"] for row in rows
            ])),
            "median_populations": populations,
        })
    result.sort(key=lambda row: (
        row["blocks_completed"] != FINE_BLOCKS,
        row["pass_fraction"] < 2.0 / 3.0,
        row["robust_rmse"]))
    return result


def select_survey_candidates(summary):
    selected = []
    for sigma in SIGMAS_US:
        matches = [row for row in summary
                   if np.isclose(row["sigma_us"], sigma)]
        selected.extend(matches[:FINE_PER_SIGMA])
    return [{key: row[key] for key in (
        "sigma_us", "freq_mhz", "x90_gain", "x180_gain")}
        for row in selected]


def select_recommendation(summary):
    return next((row for row in summary
                 if row["blocks_completed"] == FINE_BLOCKS
                 and row["pass_fraction"] >= 2.0 / 3.0), None)


def flattened_rows(records):
    rows = []
    for record in records:
        base = {
            "stage": record["stage"],
            "block": record["block"],
            "visit": record["visit"],
            "sigma_us": record["sigma_us"],
            "freq_mhz": record["freq_mhz"],
            "x90_gain": record["x90_gain"],
            "x180_gain": record["x180_gain"],
            "shots": record["shots"],
            "assignment_P_g": record["assignment"]["P_g"],
            "assignment_P_e": record["assignment"]["P_e"],
            "assignment_contrast": record["assignment"]["contrast"],
            "rmse": record.get("rmse"),
            "passed": record.get("passed"),
            "x180_population": record.get(
                "x180_population", {}).get("corrected"),
            "elapsed_s": record["elapsed_s"],
            "error": record.get("error"),
        }
        for count, values in record.get("populations", {}).items():
            rows.append({
                **base,
                "pulse_count": int(count),
                "measured_population": values["measured"],
                "corrected_population": values["corrected"],
                "ideal_population": values["ideal"],
            })
        if not record.get("populations"):
            rows.append({**base, "pulse_count": None,
                         "measured_population": None,
                         "corrected_population": None,
                         "ideal_population": None})
    return rows


def save_outputs(records, survey, fine, base_path):
    recommendation = select_recommendation(fine)
    payload = {
        "settings": {
            "qubit": QUBIT,
            "sigmas_us": SIGMAS_US,
            "frequencies_mhz": FREQUENCIES_MHZ,
            "gain_scales": GAIN_SCALES,
            "survey_counts": SURVEY_COUNTS,
            "survey_shots": SURVEY_SHOTS,
            "fine_counts": FINE_COUNTS,
            "fine_shots": FINE_SHOTS,
            "fine_blocks": FINE_BLOCKS,
            "fine_per_sigma": FINE_PER_SIGMA,
            "order_seed": ORDER_SEED,
        },
        "base_config": BaseConfig,
        "recommended": recommendation,
        "best_observed": fine[0] if fine else None,
        "survey_summary": survey,
        "fine_summary": fine,
        "records": records,
    }
    json_path = f"{base_path}.json"
    with open(json_path, "w") as handle:
        json.dump(payload, handle, indent=2, default=str)
    raw_rows = flattened_rows(records)
    csv_path = f"{base_path}_raw.csv"
    with open(csv_path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(raw_rows[0]))
        writer.writeheader()
        writer.writerows(raw_rows)
    summary_path = f"{base_path}_summary.csv"
    if fine:
        fields = [key for key in fine[0] if key != "median_populations"]
        fields.extend(f"P{count}" for count in FINE_COUNTS)
        with open(summary_path, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in fine:
                writer.writerow({
                    **{key: value for key, value in row.items()
                       if key != "median_populations"},
                    **{f"P{count}": row["median_populations"].get(str(count))
                       for count in FINE_COUNTS},
                })
    plot_path = f"{base_path}.png"
    if fine:
        fig, axes = plt.subplots(
            len(SIGMAS_US), 1, figsize=(9, 3.2 * len(SIGMAS_US)),
            sharex=True, constrained_layout=True)
        axes = np.atleast_1d(axes)
        counts = np.asarray(FINE_COUNTS, dtype=int)
        ideal = np.asarray([ideal_population(count) for count in counts])
        for ax, sigma in zip(axes, SIGMAS_US):
            ax.plot(counts, ideal, "k--", lw=2, label="ideal X90 train")
            for row in fine:
                if not np.isclose(row["sigma_us"], sigma):
                    continue
                values = [row["median_populations"].get(str(count), np.nan)
                          for count in counts]
                label = (f"{row['freq_mhz']:.2f} MHz, g={row['x90_gain']}, "
                         f"RMSE={row['robust_rmse']:.3f}")
                ax.plot(counts, values, "o-", label=label)
            ax.set(ylabel="Excited population", title=f"sigma = {sigma:.2f} us")
            ax.set_ylim(-0.15, 1.15)
            ax.grid(alpha=0.25)
            ax.legend(fontsize=8)
        axes[-1].set_xlabel("Back-to-back X90 pulse count")
        fig.savefig(plot_path, dpi=180, bbox_inches="tight")
        plt.close(fig)
    return csv_path, summary_path, json_path, plot_path


def run(soc, soccfg, outer_folder=outerFolder):
    now = datetime.datetime.now()
    folder = os.path.join(
        outer_folder, QUBIT, f"{QUBIT}_{now:%Y_%m_%d}")
    os.makedirs(folder, exist_ok=True)
    base_path = os.path.join(folder, f"{QUBIT}_{now:%H_%M_%S}_X90_Pulse_Train_Audit")
    records = []
    candidates = build_candidates()
    total_survey = len(candidates)
    started = time.time()
    print("=" * 92)
    print("X90 PULSE-TRAIN AND PULSE-LENGTH AUDIT")
    print(f"survey: {len(candidates)} candidates, counts {SURVEY_COUNTS}, "
          f"{SURVEY_SHOTS} shots")
    print(f"fine: top {FINE_PER_SIGMA} per sigma, counts {FINE_COUNTS}, "
          f"{FINE_BLOCKS} blocks x {FINE_SHOTS} shots")
    print(f"checkpoint prefix: {base_path}")
    print("=" * 92)
    calib, assignment = acquire_reference(
        soc, soccfg, outer_folder, SURVEY_SHOTS)
    if assignment["contrast"] < 0.20:
        raise RuntimeError(
            f"survey assignment contrast {assignment['contrast']:.3f} is too small")
    for visit, candidate in enumerate(ordered_candidates(candidates, 0)):
        record = measure_candidate(
            soc, soccfg, outer_folder, "survey", 0, visit, candidate,
            SURVEY_COUNTS, SURVEY_SHOTS, calib, assignment)
        records.append(record)
        elapsed = time.time() - started
        eta = elapsed / (visit + 1) * (total_survey - visit - 1)
        if record.get("error"):
            detail = record["error"]
        else:
            pops = record["populations"]
            detail = (f"P1 {pops['1']['corrected']:.3f}  "
                      f"P2 {pops['2']['corrected']:.3f}  "
                      f"P4 {pops['4']['corrected']:.3f}  "
                      f"Ppi {record['x180_population']['corrected']:.3f}  "
                      f"RMSE {record['rmse']:.3f}")
        print(f"survey {visit + 1:>2}/{total_survey}  "
              f"sigma {candidate['sigma_us']:.2f} us  "
              f"{candidate['freq_mhz']:.2f} MHz  "
              f"g90 {candidate['x90_gain']:>5}  {detail}  "
              f"ETA {eta / 60:.1f} min", flush=True)
    survey = survey_summary(records)
    selected = select_survey_candidates(survey)
    if len(selected) != len(SIGMAS_US) * FINE_PER_SIGMA:
        raise RuntimeError("survey did not produce enough successful candidates")
    save_outputs(records, survey, [], base_path)
    print("\nselected for repeated fine scan")
    for candidate in selected:
        print(f"  sigma {candidate['sigma_us']:.2f} us  "
              f"{candidate['freq_mhz']:.2f} MHz  "
              f"g90 {candidate['x90_gain']}  g180 {candidate['x180_gain']}")
    for block in range(FINE_BLOCKS):
        calib, assignment = acquire_reference(
            soc, soccfg, outer_folder, FINE_SHOTS)
        if assignment["contrast"] < 0.20:
            raise RuntimeError(
                f"fine block {block + 1} assignment contrast "
                f"{assignment['contrast']:.3f} is too small")
        print(f"fine block {block + 1}/{FINE_BLOCKS}, reference contrast "
              f"{assignment['contrast']:.3f}")
        for visit, candidate in enumerate(ordered_candidates(selected, block)):
            record = measure_candidate(
                soc, soccfg, outer_folder, "fine", block, visit, candidate,
                FINE_COUNTS, FINE_SHOTS, calib, assignment)
            records.append(record)
            if record.get("error"):
                detail = record["error"]
            else:
                pops = record["populations"]
                detail = (f"P1 {pops['1']['corrected']:.3f}  "
                          f"P2 {pops['2']['corrected']:.3f}  "
                          f"P4 {pops['4']['corrected']:.3f}  "
                          f"P8 {pops['8']['corrected']:.3f}  "
                          f"Ppi {record['x180_population']['corrected']:.3f}  "
                          f"RMSE {record['rmse']:.3f}")
            print(f"  {visit + 1}/{len(selected)}  "
                  f"sigma {candidate['sigma_us']:.2f} us  "
                  f"{candidate['freq_mhz']:.2f} MHz  "
                  f"g90 {candidate['x90_gain']:>5}  {detail}", flush=True)
        fine = fine_summary(records)
        save_outputs(records, survey, fine, base_path)
        print(f"saved checkpoint after fine block {block + 1}", flush=True)
    fine = fine_summary(records)
    paths = save_outputs(records, survey, fine, base_path)
    print("\nranked fine candidates")
    print(" rank  sigma    frequency  g90    g180   RMSE    pass  P1     P2     P4     P8     Ppi")
    for rank, row in enumerate(fine, start=1):
        pops = row["median_populations"]
        print(f" {rank:>3}   {row['sigma_us']:.2f} us  "
              f"{row['freq_mhz']:.2f} MHz  {row['x90_gain']:>5}  "
              f"{row['x180_gain']:>5}  {row['robust_rmse']:.3f}  "
              f"{row['pass_fraction']:.2f}  {pops['1']:.3f}  "
              f"{pops['2']:.3f}  {pops['4']:.3f}  {pops['8']:.3f}  "
              f"{row['median_x180_population']:.3f}")
    recommendation = select_recommendation(fine)
    if recommendation is None:
        print("\nNO VALID COHERENT PULSE SET")
        print("Do not update initialize.py or run the round-trip timing audit.")
    else:
        print("\nrecommended parameters")
        print(f"sigma = {recommendation['sigma_us']:.2f}")
        print(f"qubit_pi_freq = {recommendation['freq_mhz']:.2f}")
        print(f"qubit_pi2_gain = {recommendation['x90_gain']}")
        print(f"qubit_pi_gain = {recommendation['x180_gain']}")
    print("\noutputs")
    for path in paths:
        print(path)
    return {
        "records": records,
        "survey_summary": survey,
        "fine_summary": fine,
        "recommended": recommendation,
        "paths": paths,
    }


def main():
    soc, soccfg = makeProxy()
    run(soc, soccfg, outerFolder)


if __name__ == "__main__":
    main()
