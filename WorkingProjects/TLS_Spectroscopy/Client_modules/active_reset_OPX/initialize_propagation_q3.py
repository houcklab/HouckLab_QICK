import ast
from datetime import datetime
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys


_source = Path(__file__).resolve()
for _parent in _source.parents:
    if (_parent / "WorkingProjects").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break
else:
    raise RuntimeError("Could not locate the HouckLab_QICK repository root")


MODULE_NAME = "WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize"
QUBIT = "q3"
CONFIG_KEYS = (
    "qubit_freq",
    "qubit_pi_freq",
    "qubit_gain",
    "qubit_pi_gain",
    "qubit_pi2_gain",
    "sigma",
    "read_pulse_freq",
    "read_pulse_gain",
    "read_length",
    "ff_park_gain",
)


def extract_literal_config(path, keys):
    tree = ast.parse(Path(path).read_text())
    config_node = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "BaseConfig"
            for target in node.targets
        )
    )
    entries = {
        ast.literal_eval(key_node): value_node
        for key_node, value_node in zip(config_node.keys, config_node.values)
    }
    return {key: ast.literal_eval(entries[key]) for key in keys}


def diagnose_layers(source_values, imported_values, runner_values):
    source = dict(source_values)
    imported = dict(imported_values)
    runner = dict(runner_values)
    if source != imported:
        return "source_import_mismatch"
    expected_runner = dict(imported)
    if "qubit_pi_gain" in expected_runner:
        expected_runner["qubit_gain"] = expected_runner["qubit_pi_gain"]
    if runner != expected_runner:
        return "runner_override_mismatch"
    if source.get("qubit_gain") != source.get("qubit_pi_gain"):
        return "qubit_pi_gain_controls_sscal"
    return "propagation_ok"


def _file_record(path):
    if path is None:
        return None
    value = Path(path).resolve()
    if not value.exists():
        return {"path": str(value), "exists": False}
    stat = value.stat()
    return {
        "path": str(value),
        "exists": True,
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "sha256": hashlib.sha256(value.read_bytes()).hexdigest(),
    }


def _output_dir(outer_folder):
    now = datetime.now()
    output = (
        Path(outer_folder)
        / QUBIT
        / f"{QUBIT}_{now:%Y_%m_%d}"
        / f"{QUBIT}_{now:%H_%M_%S}_initialize_propagation"
    )
    output.mkdir(parents=True, exist_ok=False)
    return output


def main():
    spec = importlib.util.find_spec(MODULE_NAME)
    if spec is None or spec.origin is None:
        raise RuntimeError(f"Could not locate {MODULE_NAME}")
    source_path = Path(spec.origin).resolve()
    source_values = extract_literal_config(source_path, CONFIG_KEYS)
    initialize = importlib.import_module(MODULE_NAME)
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import GateCalibration

    imported_values = {key: initialize.BaseConfig[key] for key in CONFIG_KEYS}
    gate_import_values = {key: GateCalibration.BaseConfig[key] for key in CONFIG_KEYS}
    runner_cfg = GateCalibration._base_cfg(GateCalibration.P_SS_CAL, active=False)
    runner_cfg["qubit_gain"] = int(runner_cfg["qubit_pi_gain"])
    runner_values = {key: runner_cfg[key] for key in CONFIG_KEYS}
    diagnosis = diagnose_layers(source_values, imported_values, runner_values)
    result = {
        "diagnosis": diagnosis,
        "python_executable": sys.executable,
        "source": _file_record(source_path),
        "bytecode_cache": _file_record(getattr(initialize, "__cached__", None)),
        "module_file": str(Path(initialize.__file__).resolve()),
        "gate_uses_same_base_config_object": bool(
            GateCalibration.BaseConfig is initialize.BaseConfig
        ),
        "source_values": source_values,
        "imported_values": imported_values,
        "gate_import_values": gate_import_values,
        "sscal_runner_values": runner_values,
        "sscal_actual_gain_dac": int(runner_cfg["qubit_gain"]),
        "sscal_actual_frequency_mhz": float(runner_cfg["qubit_pi_freq"]),
        "sscal_actual_sigma_us": float(runner_cfg["sigma"]),
    }
    output = _output_dir(initialize.outerFolder)
    (output / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"output={output}")


if __name__ == "__main__":
    main()
