from datetime import datetime
import json
from pathlib import Path
import sys

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
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.analysis import (
    json_safe,
    load_park_history_method_frequencies,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.benchmark_settings import (
    q3_benchmark_settings,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.calibration import (
    acquire_calibration,
    per_shot_reference_config,
    save_calibration,
    save_raw_calibration,
    validate_confident_calibration,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
    acquire_tls_memory_iq,
    classify_payload_iq,
)


QUBIT = "q3"
CALIBRATION_SHOTS = 1000
SHOTS = 200
TARGET_GAIN = -20000
INTERACTION_US = 4.0
STORAGE_US = 12.0
SEQUENCES = ("single", "double", "ground_double")


def _latest_park_history_result():
    paths = list(
        (Path(outerFolder) / QUBIT).glob(
            f"{QUBIT}_*/{QUBIT}_*_active_reset_OPX_park_history_spectroscopy/result.json"
        )
    )
    if not paths:
        raise FileNotFoundError("no completed park-history spectroscopy result found")
    return max(paths, key=lambda path: path.stat().st_mtime)


def _output_dir():
    now = datetime.now()
    output = (
        Path(outerFolder)
        / QUBIT
        / f"{QUBIT}_{now:%Y_%m_%d}"
        / f"{QUBIT}_{now:%H_%M_%S}_active_reset_OPX_TLS_memory_smoke"
    )
    output.mkdir(parents=True, exist_ok=False)
    return output


def _write_json(path, values):
    Path(path).write_text(
        json.dumps(json_safe(values), indent=2, sort_keys=True) + "\n"
    )


def main():
    import qick

    if str(qick.__version__) != "0.2.133":
        raise RuntimeError(f"This test requires qick 0.2.133, found {qick.__version__}")
    output = _output_dir()
    print(f"output={output}")
    park_history_path = _latest_park_history_result()
    frequency = float(
        load_park_history_method_frequencies(park_history_path)["opx_unbounded"]
    )
    print(f"park_history_frequency_mhz={frequency:.6f}")
    soc, soccfg = makeProxy()
    settings = q3_benchmark_settings()
    cfg = dict(BaseConfig)
    cfg.update(settings.opx_overrides())
    cfg.update({
        "reset_mode": "opx_unbounded",
        "qubit_pi_freq": frequency,
        "reset_pi_freq": frequency,
        "ff_gain": int(TARGET_GAIN),
        "do_ff": True,
        "shots": int(SHOTS),
        "reps": int(SHOTS),
        "opx_max_reset_attempts": 8,
        "opx_read_delay_us": 2.0,
        "opx_reset_settle_us": 0.05,
        "opx_verification_delay_us": 0.25,
        "opx_record_base": 32,
        "opx_done_addr": 1,
        "opx_unbounded_watchdog_s": 2.0,
    })
    metadata = {
        "created": datetime.now().isoformat(),
        "qick_version": str(qick.__version__),
        "qubit": QUBIT,
        "park_history_result": str(park_history_path),
        "park_history_frequency_mhz": frequency,
        "target_gain": int(TARGET_GAIN),
        "interaction_us": float(INTERACTION_US),
        "storage_us": float(STORAGE_US),
        "sequences": list(SEQUENCES),
        "shots_per_sequence": int(SHOTS),
        "park_lifecycle": "persistent_hard_step",
        "payload_order": "shot_sequence",
        "reset_scheme": "opx_unbounded",
        "config": cfg,
    }
    _write_json(output / "run_metadata.json", metadata)
    calibration_cfg = per_shot_reference_config(cfg)
    bundle, raw = acquire_calibration(
        soc,
        soccfg,
        calibration_cfg,
        shots=int(CALIBRATION_SHOTS),
        **settings.calibration_options(),
        metadata=metadata,
    )
    save_calibration(output / "calibration.json", bundle)
    save_raw_calibration(output / "calibration_raw.npz", raw)
    validate_confident_calibration(bundle, min_confident_fraction=0.2)
    cfg["opx_reset_calibration"] = bundle.to_dict()
    try:
        i_values, q_values, telemetry = acquire_tls_memory_iq(
            soc,
            soccfg,
            cfg,
            sequences=SEQUENCES,
            interaction_us=INTERACTION_US,
            storage_us=STORAGE_US,
            ff_gain=TARGET_GAIN,
            shots=SHOTS,
        )
    finally:
        reset_gens = getattr(soc, "reset_gens", None)
        if callable(reset_gens):
            reset_gens()
    classified = classify_payload_iq(
        cfg,
        i_values,
        q_values,
        telemetry["read_length_cycles"],
    )
    probabilities = {
        sequence: float(np.mean(classified[index]))
        for index, sequence in enumerate(SEQUENCES)
    }
    assignment = {
        "P_g": float(bundle.payload.holdout["false_pi"]),
        "P_e": float(bundle.payload.holdout["excited_fire"]),
    }
    contrast = assignment["P_e"] - assignment["P_g"]
    corrected = {
        sequence: float((value - assignment["P_g"]) / contrast)
        for sequence, value in probabilities.items()
    }
    np.savez_compressed(
        output / "raw_iq.npz",
        sequences=np.asarray(SEQUENCES),
        i=i_values,
        q=q_values,
        classified=classified,
    )
    result = {
        "probabilities": probabilities,
        "corrected_populations": corrected,
        "assignment_reference": assignment,
        "telemetry": telemetry,
    }
    _write_json(output / "result.json", result)
    for sequence in SEQUENCES:
        print(
            f"{sequence} P_excited={probabilities[sequence]:.6f} "
            f"population_corrected={corrected[sequence]:.6f}"
        )


if __name__ == "__main__":
    main()
