import ast
from pathlib import Path


RUNNER_DIR = Path(__file__).parents[2] / "Runners"
RUNNERS = (
    RUNNER_DIR / "GateCalibration.py",
    RUNNER_DIR / "SingleQubitCoherence.py",
    RUNNER_DIR / "TLSSpectroscopy.py",
)


def assigned_names(tree):
    names = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names.extend(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
    return names


def literal_dicts(tree):
    values = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                values[target.id] = ast.literal_eval(node.value)
    return values


def test_each_runner_exposes_only_one_reset_control():
    for path in RUNNERS:
        tree = ast.parse(path.read_text())
        controls = [
            name for name in assigned_names(tree)
            if name.startswith("RESET_")
        ]
        assert controls == ["RESET_MODE"], (path.name, controls)


def test_experiment_parameter_blocks_do_not_expose_reset_internals():
    forbidden = {
        "reset_threshold_raw",
        "reset_oper",
        "reset_ground_below",
        "reset_max_iters",
        "reset_probe_shots",
        "opx_reset_calibration",
        "opx_calibration_shots",
        "opx_inter_shot_delay_us",
        "opx_host_watchdog_s",
        "interleave_rounds",
    }
    for path in RUNNERS:
        tree = ast.parse(path.read_text())
        for name, values in literal_dicts(tree).items():
            if not name.startswith("P_") and not name.startswith("P6_"):
                continue
            assert forbidden.isdisjoint(values), (path.name, name, forbidden & values.keys())


def test_each_runner_loads_an_ignored_local_override_surface():
    for path in RUNNERS:
        source = path.read_text()
        assert "LOCAL_OVERRIDE_KEYS" in source, path.name
        assert "apply_local_overrides(globals(), __file__, LOCAL_OVERRIDE_KEYS)" in source, path.name
