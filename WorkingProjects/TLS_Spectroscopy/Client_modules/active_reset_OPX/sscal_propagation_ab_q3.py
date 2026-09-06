from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


_source = Path(__file__).resolve()
for _parent in _source.parents:
    if (_parent / "WorkingProjects").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break
else:
    raise RuntimeError("Could not locate the HouckLab_QICK repository root")


from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import (
    json_safe,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.sscal_failure_diagnostic_q3 import (
    pair_metrics,
)


QUBIT = "q3"
SHOTS = 1000
PASSIVE_RESET_US = 1000.0
FORCED_FREQUENCY_MHZ = 4365.8920294330965
FORCED_GAIN_DAC = 15500
FORCED_SIGMA_US = 0.2
FIDELITY_THRESHOLD = 0.75
DRIFT_TOLERANCE = 0.15


def build_run_configs(
    base_config,
    *,
    forced_frequency_mhz,
    forced_gain_dac,
    forced_sigma_us,
    shots,
):
    common = {
        "shots": int(shots),
        "reps": int(shots),
        "repeats": 1,
        "relax_delay": float(PASSIVE_RESET_US),
        "opx_inter_shot_delay_us": float(PASSIVE_RESET_US),
        "single_shot_state_order": "ge",
        "reset_mode": "passive",
        "ff_gain": 0,
        "ff_hold_gain": 0,
        "readout_after_park": True,
        "qubit_pulse_style": "arb",
    }
    imported = dict(base_config)
    imported.update(common)
    forced = dict(imported)
    forced.update({
        "qubit_freq": float(forced_frequency_mhz),
        "qubit_pi_freq": float(forced_frequency_mhz),
        "qubit_gain": int(forced_gain_dac),
        "qubit_pi_gain": int(forced_gain_dac),
        "qubit_pi2_gain": int(round(int(forced_gain_dac) / 2.0)),
        "sigma": float(forced_sigma_us),
    })
    return imported, forced


def classify_ab(imported_before, forced, imported_after):
    before = float(imported_before)
    middle = float(forced)
    after = float(imported_after)
    if abs(before - after) >= DRIFT_TOLERANCE:
        return "state_changed_during_test"
    if min(before, after) >= FIDELITY_THRESHOLD:
        return "imported_configuration_now_works"
    if middle >= FIDELITY_THRESHOLD and max(before, after) < FIDELITY_THRESHOLD:
        return "configuration_not_propagated"
    if middle < FIDELITY_THRESHOLD:
        return "known_good_pulse_no_longer_good"
    return "marginal_configuration_difference"


def _output_dir(outer_folder):
    now = datetime.now()
    output = (
        Path(outer_folder)
        / QUBIT
        / f"{QUBIT}_{now:%Y_%m_%d}"
        / f"{QUBIT}_{now:%H_%M_%S}_SSCal_propagation_ABA"
    )
    output.mkdir(parents=True, exist_ok=False)
    return output


def _effective_config(cfg):
    keys = (
        "qubit_freq",
        "qubit_pi_freq",
        "qubit_gain",
        "qubit_pi_gain",
        "qubit_pi2_gain",
        "sigma",
        "read_pulse_freq",
        "read_pulse_gain",
        "read_length",
        "ff_gain",
        "ff_hold_gain",
        "ff_park_gain",
        "shots",
        "reps",
        "repeats",
        "relax_delay",
        "opx_inter_shot_delay_us",
        "single_shot_state_order",
        "reset_mode",
    )
    return {key: cfg.get(key) for key in keys}


def _run_pair(soc, soccfg, cfg, outer_folder):
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import SingleShot1Q
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import suppress_stdout

    run_cfg = dict(cfg)
    experiment = SingleShot1Q(
        soc=soc,
        soccfg=soccfg,
        path=QUBIT,
        outerFolder=outer_folder,
        suffix="SSCal_propagation_ABA_point",
        cfg=run_cfg,
        plot=False,
        save=False,
        repeats=1,
        min_F=0.0,
    )
    with suppress_stdout():
        experiment.acquire(progress=False, plotDisp=False)
    raw = {
        "ground_i": np.asarray(experiment.I_0, dtype=float),
        "ground_q": np.asarray(experiment.Q_0, dtype=float),
        "excited_i": np.asarray(experiment.I_1, dtype=float),
        "excited_q": np.asarray(experiment.Q_1, dtype=float),
    }
    metrics = pair_metrics(
        raw["ground_i"],
        raw["ground_q"],
        raw["excited_i"],
        raw["excited_q"],
    )
    return raw, metrics, _effective_config(experiment.cfg)


def _save_raw(path, runs):
    values = {}
    for name, run in runs.items():
        for key, array in run["raw"].items():
            values[f"{name}_{key}"] = np.asarray(array)
    np.savez_compressed(path, **values)


def _plot(path, runs, diagnosis):
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), constrained_layout=True)
    for axis, (name, run) in zip(axes, runs.items()):
        raw = run["raw"]
        axis.scatter(raw["ground_i"], raw["ground_q"], s=7, alpha=0.3, label="ground")
        axis.scatter(raw["excited_i"], raw["excited_q"], s=7, alpha=0.3, label="excited")
        axis.set_title(f"{name}\nF={run['metrics']['fidelity']:.4f}")
        axis.set_xlabel("I")
        axis.set_ylabel("Q")
        axis.legend()
    fig.suptitle(diagnosis)
    fig.savefig(path, dpi=170)
    plt.close(fig)


def main():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib import initialize
    from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import ProductionResetSession

    output = _output_dir(initialize.outerFolder)
    source_path = Path(initialize.__file__).resolve()
    base = ProductionResetSession.passive().apply(dict(initialize.BaseConfig))
    imported, forced = build_run_configs(
        base,
        forced_frequency_mhz=FORCED_FREQUENCY_MHZ,
        forced_gain_dac=FORCED_GAIN_DAC,
        forced_sigma_us=FORCED_SIGMA_US,
        shots=SHOTS,
    )
    audit = {
        "python_executable": sys.executable,
        "initialize_path": str(source_path),
        "initialize_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "imported": _effective_config(imported),
        "forced": _effective_config(forced),
    }
    (output / "run_metadata.json").write_text(
        json.dumps(json_safe(audit), indent=2, sort_keys=True) + "\n"
    )
    print(f"output={output}")
    print("imported_config=" + json.dumps(json_safe(audit["imported"]), sort_keys=True))
    print("forced_config=" + json.dumps(json_safe(audit["forced"]), sort_keys=True))
    soc, soccfg = makeProxy()
    runs = {}
    sequence = (
        ("imported_before", imported),
        ("forced_known_good", forced),
        ("imported_after", imported),
    )
    for name, cfg in sequence:
        print(f"stage={name}")
        raw, metrics, effective = _run_pair(
            soc,
            soccfg,
            cfg,
            initialize.outerFolder,
        )
        runs[name] = {
            "raw": raw,
            "metrics": metrics,
            "effective_config": effective,
        }
    diagnosis = classify_ab(
        runs["imported_before"]["metrics"]["fidelity"],
        runs["forced_known_good"]["metrics"]["fidelity"],
        runs["imported_after"]["metrics"]["fidelity"],
    )
    result = {
        "diagnosis": diagnosis,
        "audit": audit,
        "runs": {
            name: {
                "metrics": run["metrics"],
                "effective_config": run["effective_config"],
            }
            for name, run in runs.items()
        },
    }
    (output / "result.json").write_text(
        json.dumps(json_safe(result), indent=2, sort_keys=True) + "\n"
    )
    _save_raw(output / "raw_iq.npz", runs)
    _plot(output / "comparison.png", runs, diagnosis)
    print(f"diagnosis={diagnosis}")
    for name, run in runs.items():
        print(f"{name}_fidelity={run['metrics']['fidelity']:.4f}")
    print(f"output={output}")


if __name__ == "__main__":
    main()
