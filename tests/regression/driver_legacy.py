"""Replay every dispatch of the legacy runner CSTQ03_BFC.py with hardware mocked.

The runner's sections 1-2 (device parameters, flags, param dicts) are executed
verbatim. Section 3 (EXECUTE) is parsed, never run as a whole: for each
``if <Flag>: <body>`` in it, the driver runs the section's unconditional
statements that precede the ``if`` (build_context, and the
rebuild_singleshot_config regime switch for regime-B flags), then the body,
then the unconditional statements after it -- i.e. exactly what the runner does
with only that flag set, whatever the flag's current value. One extra variant
re-runs RunZeroSpanParity with every Validate_*/Build_* sub-flag on.

Usage:  python -m tests.regression.driver_legacy   (rewrites the golden file)
"""

import ast
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")

from tests.regression import capture  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CLIENT = "WorkingProjects.QM_Team.qubit_measurements.Client_modules"
RUNNER = REPO / "WorkingProjects/QM_Team/qubit_measurements/Client_modules/Runners/CSTQ03_BFC.py"
GOLDEN = Path(__file__).with_name("golden_cstq03.json")
EXECUTE_MARKER = "3. EXECUTE"
VALIDATE_VARIANT = ("RunZeroSpanParity", "RunZeroSpanParity[validate]", ("Validate_", "Build_"))


def install():
    import importlib

    import pyvisa

    importlib.import_module(f"{CLIENT}.Runners.runs")  # load every experiment module first
    experiment = importlib.import_module(f"{CLIENT}.CoreLib.Experiment")
    return capture.install_mocks(
        experiment.ExperimentClass,
        make_proxy_targets=[f"{CLIENT}.CoreLib.socProxy:makeProxy"],
        pyvisa_targets=[pyvisa],
    )


def plan():
    """Split the runner into (prefix code, [(label, statements, flag_prefixes)])."""
    lines = RUNNER.read_text(encoding="utf-8").splitlines(keepends=True)
    cut = next(i for i, line in enumerate(lines) if EXECUTE_MARKER in line)
    prefix = compile("".join(lines[:cut]), str(RUNNER), "exec")
    tree = ast.parse("".join(lines[cut:]))
    ast.increment_lineno(tree, cut)

    def is_dispatch(node):
        return isinstance(node, ast.If) and isinstance(node.test, ast.Name)

    body = tree.body
    runs = []
    for i, node in enumerate(body):
        if not is_dispatch(node):
            continue
        pre = [s for s in body[:i] if not is_dispatch(s)]
        post = [s for s in body[i + 1 :] if not is_dispatch(s)]
        stmts = pre + node.body + post
        runs.append((node.test.id, stmts, ()))
        flag, label, prefixes = VALIDATE_VARIANT
        if node.test.id == flag:
            runs.append((label, stmts, prefixes))
    return prefix, runs


def _redirect_data(ns, root):
    """Point every outerfoldername at the temp root, keeping its suffix."""
    old = ns.get("_QubitFolderRoot")
    for name, value in ns.items():
        if not (name.startswith("Qubit_Parameters") and isinstance(value, dict)):
            continue
        for q, params in value.items():
            folder = params.get("outerfoldername") if isinstance(params, dict) else None
            if isinstance(folder, str):
                params["outerfoldername"] = (
                    root + folder[len(old) :]
                    if old and folder.startswith(old)
                    else f"{root}/Q{q}//"
                )


def _traceback_tail(exc, n=4):
    frames = traceback.extract_tb(exc.__traceback__)[-n:]
    out = []
    for f in frames:
        try:
            path = Path(f.filename).resolve().relative_to(REPO).as_posix()
        except ValueError:
            path = Path(f.filename).name
        out.append(f"{path}:{f.lineno}:{f.name}")
    return out


def run_one(label, stmts, flag_prefixes, prefix_code):
    import matplotlib.pyplot as plt

    root = tempfile.mkdtemp(prefix="qicklab_regression_")
    capture.begin_run(label, root)
    code = compile(ast.Module(body=stmts, type_ignores=[]), str(RUNNER), "exec")
    verbose = bool(os.environ.get("REGRESSION_VERBOSE"))
    out_sink = sys.stdout if verbose else io.StringIO()
    err_sink = sys.stderr if verbose else io.StringIO()
    try:
        with contextlib.redirect_stdout(out_sink), contextlib.redirect_stderr(err_sink):
            ns = {"__name__": "__cstq03_replay__", "__file__": str(RUNNER)}
            exec(prefix_code, ns)
            _redirect_data(ns, root)
            ns.update({k: True for k in ns if k.startswith(flag_prefixes)} if flag_prefixes else {})
            exec(code, ns)
        outcome = {"status": "completed"}
    except capture.StopCapture:
        outcome = {"status": "stopped_at_budget"}
    except Exception as exc:
        outcome = {
            "status": "raised",
            "type": type(exc).__name__,
            "message": capture.normalize(str(exc))[:400],
            "traceback": _traceback_tail(exc),
        }
    result = capture.end_run()
    plt.close("all")
    plt.ioff()
    shutil.rmtree(root, ignore_errors=True)
    return {
        "outcome": outcome,
        "yoko_writes": result["yoko"],
        "experiments": result["experiments"],
        "hw_outside_experiments": result["hw_outside_experiments"],
    }


def capture_all(labels=None):
    """{run label: {outcome, yoko_writes, experiments, hw_outside_experiments}}."""
    install()
    prefix, runs = plan()
    out = {}
    for label, stmts, flag_prefixes in runs:
        if labels is not None and label not in labels:
            continue
        t0 = time.perf_counter()
        out[label] = run_one(label, stmts, flag_prefixes, prefix)
        status = out[label]["outcome"]["status"]
        n = len(out[label]["experiments"])
        print(
            f"[regression] {label:<34} {status:<18} {n:>3} exp  {time.perf_counter() - t0:6.1f}s",
            file=sys.stderr,
        )
    return json.loads(json.dumps(out, allow_nan=True))


def dump(result, path=GOLDEN):
    path.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    if sys.argv[1:]:  # named labels: dry run, golden untouched
        capture_all(sys.argv[1:])
    else:
        dump(capture_all())
        print(f"wrote {GOLDEN}", file=sys.stderr)
