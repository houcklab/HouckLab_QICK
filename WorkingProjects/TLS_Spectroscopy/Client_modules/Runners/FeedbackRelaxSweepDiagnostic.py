"""Standalone q3 feedback-reset spacing diagnostic.

Copy this complete file to ``test.py`` in the HouckLab_QICK repository root on
the measurement PC and run it with that repository's virtual-environment
Python.  It does not modify calibration files or production configuration.
"""

import copy
import csv
import datetime
import json
import math
import os
import sys
import time


# Allow this file to be copied to any location inside the repository.
_repo = os.path.dirname(os.path.abspath(__file__))
while _repo != os.path.dirname(_repo):
    if os.path.isdir(os.path.join(_repo, "WorkingProjects")):
        if _repo not in sys.path:
            sys.path.insert(0, _repo)
        break
    _repo = os.path.dirname(_repo)
else:
    raise RuntimeError(
        "Could not find the HouckLab_QICK repository root. Put test.py inside "
        "the repository before running it."
    )

from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import (
    BaseConfig,
    outerFolder,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset


QUBIT = "q3"

# This is the only independent variable in the diagnostic.
FEEDBACK_RELAX_US = [25, 50, 100, 200, 400, 800]

# These retain the pulse amplitudes, park gain, ramp, readout, and reset timing
# from BaseConfig.  Only shot counts and inter-shot spacing are changed here.
DRIFT_CAL_SHOTS = 500
RESET_PROBE_SHOTS = 1000
PASSIVE_REFERENCE_RELAX_US = 1500.0
RESET_MAX_ITERS = 3
RESET_THERMALIZATION_US = 2.0

# Diagnostic labels only; no hardware action depends on these thresholds.
MIN_CONTRAST_FRACTION_OF_PASSIVE = 0.80
MAX_P_E_NO_PI = 0.15


CSV_FIELDS = [
    "feedback_relax_us",
    "status",
    "P_e_no_pi",
    "P_e_with_pi",
    "contrast",
    "passive_contrast",
    "contrast_fraction_of_passive",
    "reset_pi_offset_mhz",
    "post_reset_pi_offset_mhz",
    "reset_pi_freq_step_mhz",
    "elapsed_s",
    "started_at_iso",
    "finished_at_iso",
    "error",
]


def _json_default(value):
    try:
        import numpy as np

        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
    except Exception:
        pass
    return str(value)


def validate_settings(relax_values, drift_shots, probe_shots, reset_max_iters):
    values = [float(value) for value in relax_values]
    if not values or any(not math.isfinite(value) or value <= 0.0 for value in values):
        raise ValueError("FEEDBACK_RELAX_US must contain finite positive values")
    if any(right <= left for left, right in zip(values, values[1:])):
        raise ValueError("FEEDBACK_RELAX_US must be strictly increasing with no duplicates")
    if int(drift_shots) <= 0 or int(probe_shots) <= 0:
        raise ValueError("shot counts must be positive")
    if int(reset_max_iters) <= 0:
        raise ValueError("RESET_MAX_ITERS must be positive")
    return values


def summarize_point(relax_us, drift_result):
    required = (
        "reset_pi_offset_mhz",
        "post_reset_pi_offset_mhz",
        "reset_pi_freq_step_mhz",
        "residual",
        "contrast",
        "passive_contrast",
    )
    missing = [key for key in required if key not in drift_result]
    if missing:
        raise ValueError(f"drift calibration result is missing {missing}")
    values = {key: float(drift_result[key]) for key in required}
    if any(not math.isfinite(value) for value in values.values()):
        raise ValueError("drift calibration returned a non-finite result")
    if values["passive_contrast"] <= 0.0:
        raise ValueError("passive reference contrast must be positive")
    p_no_pi = values["residual"]
    contrast = values["contrast"]
    return {
        "feedback_relax_us": float(relax_us),
        "status": "ok",
        "P_e_no_pi": p_no_pi,
        "P_e_with_pi": p_no_pi + contrast,
        "contrast": contrast,
        "passive_contrast": values["passive_contrast"],
        "contrast_fraction_of_passive": contrast / values["passive_contrast"],
        "reset_pi_offset_mhz": values["reset_pi_offset_mhz"],
        "post_reset_pi_offset_mhz": values["post_reset_pi_offset_mhz"],
        "reset_pi_freq_step_mhz": values["reset_pi_freq_step_mhz"],
        "error": "",
    }


def run_sweep(relax_values, reset_record, calibrate_point, checkpoint):
    rows = []
    for index, relax_us in enumerate(relax_values):
        started = time.time()
        started_iso = datetime.datetime.now().isoformat(timespec="seconds")
        print("\n" + "=" * 78)
        print(
            f"FEEDBACK RELAX {index + 1}/{len(relax_values)}: "
            f"{float(relax_us):g} us"
        )
        print("=" * 78, flush=True)
        point_record = copy.deepcopy(reset_record)
        try:
            drift = calibrate_point(float(relax_us), point_record)
            if drift is None:
                raise RuntimeError("drift-pi calibration returned no usable result")
            row = summarize_point(float(relax_us), drift)
        except KeyboardInterrupt:
            row = {
                "feedback_relax_us": float(relax_us),
                "status": "interrupted",
                "error": "KeyboardInterrupt",
            }
            row.update(
                elapsed_s=time.time() - started,
                started_at_iso=started_iso,
                finished_at_iso=datetime.datetime.now().isoformat(timespec="seconds"),
            )
            rows.append(row)
            checkpoint(rows)
            raise
        except Exception as exc:
            row = {
                "feedback_relax_us": float(relax_us),
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }
            row.update(
                elapsed_s=time.time() - started,
                started_at_iso=started_iso,
                finished_at_iso=datetime.datetime.now().isoformat(timespec="seconds"),
            )
            rows.append(row)
            checkpoint(rows)
            raise
        row.update(
            elapsed_s=time.time() - started,
            started_at_iso=started_iso,
            finished_at_iso=datetime.datetime.now().isoformat(timespec="seconds"),
        )
        rows.append(row)
        checkpoint(rows)
        print(
            f"relax {float(relax_us):7.1f} us | "
            f"P(e|no pi) {row['P_e_no_pi']:.3f} | "
            f"P(e|pi) {row['P_e_with_pi']:.3f} | "
            f"contrast/passive {row['contrast_fraction_of_passive']:.3f}",
            flush=True,
        )
    return rows


def choose_shortest_usable(
    rows,
    min_contrast_fraction=MIN_CONTRAST_FRACTION_OF_PASSIVE,
    max_p_e_no_pi=MAX_P_E_NO_PI,
):
    usable = [
        row
        for row in rows
        if row.get("status") == "ok"
        and math.isfinite(float(row.get("P_e_no_pi", float("nan"))))
        and math.isfinite(float(row.get("contrast_fraction_of_passive", float("nan"))))
        and float(row["P_e_no_pi"]) <= float(max_p_e_no_pi)
        and float(row["contrast_fraction_of_passive"]) >= float(min_contrast_fraction)
    ]
    if not usable:
        return None
    return min(usable, key=lambda row: float(row["feedback_relax_us"]))


def _output_paths():
    now = datetime.datetime.now()
    folder = os.path.join(outerFolder, QUBIT, f"{QUBIT}_{now:%Y_%m_%d}")
    os.makedirs(folder, exist_ok=True)
    stem = os.path.join(folder, f"{QUBIT}_{now:%H_%M_%S}_FeedbackRelaxSweep")
    return {
        "json": stem + ".json",
        "csv": stem + ".csv",
        "plot": stem + ".png",
    }


def _write_csv(path, rows):
    with open(path, "w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in CSV_FIELDS})


def _write_json_atomic(path, payload):
    temporary = path + ".partial"
    with open(temporary, "w") as stream:
        json.dump(payload, stream, indent=2, default=_json_default)
    os.replace(temporary, path)


def _save_plot(path, rows):
    good = [row for row in rows if row.get("status") == "ok"]
    if not good:
        return
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    x = [row["feedback_relax_us"] for row in good]
    fig, axes = plt.subplots(2, 1, figsize=(8.5, 8), constrained_layout=True)
    axes[0].plot(x, [row["P_e_no_pi"] for row in good], "o-", label="no pi")
    axes[0].plot(x, [row["P_e_with_pi"] for row in good], "o-", label="with pi")
    axes[0].set_xscale("log")
    axes[0].set_xlabel("Feedback relax between shots [us]")
    axes[0].set_ylabel("Measured excited probability")
    axes[0].legend()
    ax_ratio = axes[0].twinx()
    ax_ratio.plot(
        x,
        [row["contrast_fraction_of_passive"] for row in good],
        "s--",
        color="tab:green",
        label="contrast / passive",
    )
    ax_ratio.axhline(
        MIN_CONTRAST_FRACTION_OF_PASSIVE, color="tab:green", linestyle=":"
    )
    ax_ratio.set_ylabel("Contrast fraction of passive", color="tab:green")

    axes[1].plot(
        x, [row["reset_pi_offset_mhz"] for row in good], "o-", label="reset pi"
    )
    axes[1].plot(
        x,
        [row["post_reset_pi_offset_mhz"] for row in good],
        "o-",
        label="post-reset pi",
    )
    axes[1].plot(
        x,
        [row["reset_pi_freq_step_mhz"] for row in good],
        "o-",
        label="reset iteration step",
    )
    axes[1].set_xscale("log")
    axes[1].set_xlabel("Feedback relax between shots [us]")
    axes[1].set_ylabel("Calibrated frequency offset [MHz]")
    axes[1].legend()
    fig.suptitle(f"{QUBIT} feedback-reset spacing diagnostic")
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main():
    relax_values = validate_settings(
        FEEDBACK_RELAX_US,
        drift_shots=DRIFT_CAL_SHOTS,
        probe_shots=RESET_PROBE_SHOTS,
        reset_max_iters=RESET_MAX_ITERS,
    )
    cfg = dict(BaseConfig)
    cfg.update(
        {
            "relax_delay": float(PASSIVE_REFERENCE_RELAX_US),
            "reset_max_iters": int(RESET_MAX_ITERS),
            "reset_thermalization_us": float(RESET_THERMALIZATION_US),
        }
    )
    paths = _output_paths()
    settings = {
        "qubit": QUBIT,
        "feedback_relax_us": relax_values,
        "drift_cal_shots": int(DRIFT_CAL_SHOTS),
        "reset_probe_shots": int(RESET_PROBE_SHOTS),
        "passive_reference_relax_us": float(PASSIVE_REFERENCE_RELAX_US),
        "reset_max_iters": int(RESET_MAX_ITERS),
        "reset_thermalization_us": float(RESET_THERMALIZATION_US),
        "min_contrast_fraction_of_passive": float(
            MIN_CONTRAST_FRACTION_OF_PASSIVE
        ),
        "max_p_e_no_pi": float(MAX_P_E_NO_PI),
    }

    print("=" * 78)
    print(f"{QUBIT} FEEDBACK-RESET RELAX SWEEP")
    print(f"park gain: {cfg.get('ff_park_gain')}")
    print(f"relax values [us]: {relax_values}")
    print(f"reset iterations: {RESET_MAX_ITERS}")
    print(f"drift calibration shots/condition: {DRIFT_CAL_SHOTS}")
    print("No flux correction, gain, frequency, or pulse-amplitude setting is changed.")
    print(f"checkpoint JSON: {paths['json']}")
    print(f"checkpoint CSV:  {paths['csv']}")
    print("=" * 78, flush=True)

    soc, soccfg = makeProxy()
    print("\n[1/2] Acquiring a fresh rotated reset discriminator at long relax...")
    reset_record = active_reset.probe_reset_params(
        soc,
        soccfg,
        cfg,
        path=QUBIT,
        outer_folder=outerFolder,
        shots=int(RESET_PROBE_SHOTS),
        validate=True,
        reset_max_iters=int(RESET_MAX_ITERS),
        gate_policy="best_effort",
    )
    if not active_reset.rotated_probe_record(reset_record):
        raise RuntimeError(
            "The fresh probe did not produce a functional rotated feedback reset. "
            "No relax sweep was run."
        )

    payload = {
        "schema": "q3_feedback_relax_sweep_v1",
        "created_at_iso": datetime.datetime.now().isoformat(timespec="seconds"),
        "settings": settings,
        "base_config": cfg,
        "reset_record": reset_record,
        "results": [],
        "shortest_usable": None,
    }

    def checkpoint(rows):
        payload["results"] = copy.deepcopy(rows)
        _write_csv(paths["csv"], rows)
        _write_json_atomic(paths["json"], payload)

    checkpoint([])

    def calibrate_point(relax_us, point_record):
        return active_reset.calibrate_drift_pi(
            soc,
            soccfg,
            cfg,
            point_record,
            shots=int(DRIFT_CAL_SHOTS),
            passive_relax_us=float(PASSIVE_REFERENCE_RELAX_US),
            feedback_relax_us=float(relax_us),
            max_iters=int(RESET_MAX_ITERS),
            thermalization_us=float(RESET_THERMALIZATION_US),
            verbose=True,
        )

    print("\n[2/2] Re-optimizing the reset and post-reset pi at every relax value...")
    rows = run_sweep(relax_values, reset_record, calibrate_point, checkpoint)
    selected = choose_shortest_usable(rows)
    payload["shortest_usable"] = copy.deepcopy(selected)
    payload["completed_at_iso"] = datetime.datetime.now().isoformat(timespec="seconds")
    checkpoint(rows)
    _save_plot(paths["plot"], rows)

    print("\n" + "=" * 78)
    print("FINAL SUMMARY")
    print(
        " relax_us   P(e|no pi)   P(e|pi)   contrast/passive   "
        "reset_off   post_off   iter_step"
    )
    for row in rows:
        print(
            f" {row['feedback_relax_us']:8.1f}   {row['P_e_no_pi']:10.3f}   "
            f"{row['P_e_with_pi']:8.3f}   "
            f"{row['contrast_fraction_of_passive']:16.3f}   "
            f"{row['reset_pi_offset_mhz']:+9.2f}   "
            f"{row['post_reset_pi_offset_mhz']:+8.2f}   "
            f"{row['reset_pi_freq_step_mhz']:+9.2f}"
        )
    if selected is None:
        print(
            "\nNo spacing met the diagnostic heuristic: "
            f"P(e|no pi) <= {MAX_P_E_NO_PI:.2f} and contrast/passive >= "
            f"{MIN_CONTRAST_FRACTION_OF_PASSIVE:.2f}."
        )
    else:
        print(
            f"\nShortest spacing meeting the diagnostic heuristic: "
            f"{selected['feedback_relax_us']:.0f} us"
        )
    print(f"JSON: {paths['json']}")
    print(f"CSV:  {paths['csv']}")
    print(f"plot: {paths['plot']}")
    print("=" * 78)


if __name__ == "__main__":
    main()
