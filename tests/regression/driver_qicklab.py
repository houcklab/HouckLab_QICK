"""Replay every dispatch of the frozen CSTQ03 runner with hardware mocked.

The runner is read from ``fixtures/cstq03_legacy_runner.py.txt``, a verbatim
copy of ``Runners/CSTQ03_BFC.py`` at commit 0f0a51f, never from the live file.
Its single ``from ... import *`` line is dropped; the exec namespace is seeded
with the names that star-import would bind from ``RUNS_PACKAGE`` instead, so a
post-refactor driver only changes that constant (and the patch targets).

Sections 1-2 (device parameters, flags, param dicts) are executed verbatim.
Section 3 (EXECUTE) is parsed, never run as a whole: for a set of flags, the
driver runs section 3's statements in source order, keeping every
unconditional statement (build_context, the rebuild_singleshot_config regime
switch, ctx.yoko.close()) and the bodies of the selected ``if <Flag>:`` blocks
only -- i.e. exactly what the runner does with only those flags set, whatever
their current values. Besides one run per flag there are:

* variant labels ``Flag[name]`` that apply a parameter override first
  (``OVERRIDES``), to reach code the file's own values never reach;
* multi-flag labels ``FlagA+FlagB`` (``MULTI``), for state carried from one
  dispatch to the next.

This is the post-refactor driver: identical to ``driver_legacy`` except for
the package constants (``RUNS_PACKAGE = "qicklab.runs"``, the experiment base
class from ``qicklab.core.experiment``, the proxy factory in
``qicklab.hardware.rfsoc`` under both its new name and its legacy alias), and
``input()`` raising EOFError during a replay (``_no_stdin``: the CW-tone steps
hold on it and must never block the capture). The fixture and the run labels
are unchanged, so the golden keys exactly as before.

Usage:  python -m tests.regression.driver_qicklab          (rewrites the golden)
        python -m tests.regression.driver_qicklab RunT1    (dry run, A and B)
"""

import ast
import builtins
import contextlib
import importlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")

from tests.regression import capture  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
RUNS_PACKAGE = "qicklab.runs"  # stands in for what the frozen runner star-imports
EXPERIMENT_MODULE = "qicklab.core.experiment"
FIXTURE = Path(__file__).with_name("fixtures") / "cstq03_legacy_runner.py.txt"
GOLDEN = Path(__file__).with_name("golden_cstq03.json")
EXECUTE_MARKER = "3. EXECUTE"
STAR_IMPORT = re.compile(r"^from\s+\S+\s+import\s+\*\s*$")


def _set(dict_name, **values):
    def apply(ns):
        ns[dict_name].update(values)

    apply.__doc__ = f"{dict_name}.update({values!r})"
    return apply


def _enable(*prefixes):
    def apply(ns):
        ns.update({k: True for k in list(ns) if k.startswith(prefixes)})

    apply.__doc__ = f"every flag starting with {prefixes} = True"
    return apply


def _all(*applies):
    def apply(ns):
        for a in applies:
            a(ns)

    apply.__doc__ = "; ".join(a.__doc__ for a in applies)
    return apply


# label -> (flags, override applied to the namespace before section 3)
OVERRIDES = {
    "RunZeroSpanParity[validate]": (("RunZeroSpanParity",), _enable("Validate_", "Build_")),
    # F05: the partner-significance gate rejects the harness's noise-only spectra, so the plain
    # labels now raise before SingleShot/ZSP; gate_off keeps the whole pipeline under the golden
    "RunZeroSpanParity[gate_off]": (
        ("RunZeroSpanParity",),
        _set("ZSP_ParitySpec_params", min_partner_snr=0),
    ),
    "RunZeroSpanParity[validate,gate_off]": (
        ("RunZeroSpanParity",),
        _all(_enable("Validate_", "Build_"), _set("ZSP_ParitySpec_params", min_partner_snr=0)),
    ),
    "Run2ToneChargeDispersionQuasiCW[gate_off]": (
        ("Run2ToneChargeDispersionQuasiCW",),
        _set("TwoToneChargeDispersion_params", min_partner_snr=0),
    ),
    "RunModifiedRamsey[no_reset]": (
        ("RunModifiedRamsey",),
        _set("ModifiedRamsey_params", use_active_reset=False),
    ),
    "RunModifiedRamsey_Control[verified]": (
        ("RunModifiedRamsey_Control",),
        _set("ModifiedRamsey_Control_params", sweet_spot_max_df_mhz=1e9),
    ),
    "RunAutoCoherence[fast]": (
        ("RunAutoCoherence",),
        _set(
            "AutoCoherence_override_params",
            auto_readout_opt=False,
            ss_gain_pts=3,
            T1_expts=5,
            T2_expts=5,
            T2E_expts=5,
        ),
    ),
    "RunT2E[rotation]": (("RunT2E",), _set("T2E_params", rotation_angle=0.3, min_max=[0.0, 1.0])),
    # session flag yoko_fixed = True: the charge sweep holds the bias and repeats in time (F28)
    "RunChargeSweep[yoko_fixed]": (("RunChargeSweep",), _enable("yoko_fixed")),
}
# label -> override. Flags run in runner order; the label is "+"-joined flags.
MULTI = {
    "RunTransmissionSweep+RunAmplitudeRabi": None,  # pulse_freq carried into Rabi
    # probe_freq leak; one search cycle so the second dispatch is reached at all
    "Run2ToneChargeDispersionQuasiCW+RunChargeDispersionQuasiCW": _set(
        "TwoToneChargeDispersion_params", num_cycles=1
    ),
    "RunActiveResetVerify+SingleShot": None,  # res_phase discarded by the rebuild
    "RunTransmissionSweep+Run2ToneSpec": None,
}


def install():
    import pyvisa

    importlib.import_module(RUNS_PACKAGE)  # load every experiment module first
    experiment = importlib.import_module(EXPERIMENT_MODULE)
    return capture.install_mocks(
        experiment.ExperimentClass,
        # install_mocks patches by attribute NAME + object identity, so the
        # legacy alias (makeProxy = make_proxy) needs its own target.
        make_proxy_targets=[
            "qicklab.hardware.rfsoc:make_proxy",
            "qicklab.hardware.rfsoc:makeProxy",
        ],
        pyvisa_targets=[pyvisa],
    )


def star_namespace(module):
    """The names ``from <module> import *`` binds."""
    names = getattr(module, "__all__", None)
    if names is None:
        names = [n for n in vars(module) if not n.startswith("_")]
    return {n: getattr(module, n) for n in names}


def plan():
    """Split the fixture into (prefix code, [(label, statements, override)])."""
    lines = FIXTURE.read_text(encoding="utf-8").splitlines(keepends=True)
    imports = [i for i, line in enumerate(lines) if STAR_IMPORT.match(line)]
    if len(imports) != 1:
        raise RuntimeError(f"expected one star import in {FIXTURE.name}, found {len(imports)}")
    lines[imports[0]] = "\n"  # keep line numbers
    cut = next(i for i, line in enumerate(lines) if EXECUTE_MARKER in line)
    prefix = compile("".join(lines[:cut]), str(FIXTURE), "exec")
    tree = ast.parse("".join(lines[cut:]))
    ast.increment_lineno(tree, cut)
    body = tree.body

    def is_dispatch(node):
        return isinstance(node, ast.If) and isinstance(node.test, ast.Name)

    flags = [node.test.id for node in body if is_dispatch(node)]

    def statements(selected):
        unknown = set(selected) - set(flags)
        if unknown:
            raise RuntimeError(f"no dispatch for {sorted(unknown)} in {FIXTURE.name}")
        out = []
        for node in body:
            if not is_dispatch(node):
                out.append(node)
            elif node.test.id in selected:
                out.extend(node.body)
        return out

    runs = []
    for flag in flags:
        runs.append((flag, statements((flag,)), None))
        for label, (selected, override) in OVERRIDES.items():
            if selected[0] == flag:
                runs.append((label, statements(selected), override))
    for label, override in MULTI.items():
        runs.append((label, statements(tuple(label.split("+"))), override))
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


@contextlib.contextmanager
def _patched(obj, name, value):
    saved = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, saved)


def _no_stdin(prompt=""):
    """input() during a replay: there is no operator, whatever the terminal.

    The CW-tone steps (run_constant_tone / run_constant_two_tone) hold their tones on input();
    raising EOFError puts them on their no-stdin path (stop the tones at once) under a tty,
    `pytest -s` or a pipe alike, instead of blocking behind the redirected, invisible prompt.
    """
    raise EOFError("no interactive stdin in the regression replay")


def run_one(label, stmts, override, prefix_code, runs_names):
    import matplotlib.pyplot as plt

    root = tempfile.mkdtemp(prefix="qicklab_regression_")
    capture.begin_run(label, root)
    code = compile(ast.Module(body=stmts, type_ignores=[]), str(FIXTURE), "exec")
    verbose = bool(os.environ.get("REGRESSION_VERBOSE"))
    out_sink = sys.stdout if verbose else io.StringIO()
    err_sink = sys.stderr if verbose else io.StringIO()
    try:
        with (
            contextlib.redirect_stdout(out_sink),
            contextlib.redirect_stderr(err_sink),
            _patched(builtins, "input", _no_stdin),
        ):
            ns = {"__name__": "__cstq03_replay__", "__file__": str(FIXTURE)}
            ns["__builtins__"] = builtins
            ns.update(runs_names)
            exec(prefix_code, ns)
            _redirect_data(ns, root)
            if override is not None:
                override(ns)
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
        "skipped": result["skipped"],
        "cfg_access": result["cfg_access"],
    }


def capture_all(labels=None):
    """{run label: {...}} on the currently selected board (capture.set_board)."""
    install()
    prefix, runs = plan()
    runs_names = star_namespace(importlib.import_module(RUNS_PACKAGE))
    out = {}
    for label, stmts, override in runs:
        if labels is not None and label not in labels:
            continue
        t0 = time.perf_counter()
        out[label] = run_one(label, stmts, override, prefix, runs_names)
        status = out[label]["outcome"]["status"]
        n = len(out[label]["experiments"])
        n_skip = sum(out[label]["skipped"].values())
        print(
            f"[regression] {capture.current_board()} {label:<58} {status:<18} "
            f"{n:>3} exp {n_skip:>4} skip {time.perf_counter() - t0:6.1f}s",
            file=sys.stderr,
        )
    return json.loads(json.dumps(out, allow_nan=True))


def dump(result, path=GOLDEN):
    path.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    if sys.argv[1:]:  # named labels: dry run, golden untouched
        capture.capture_variants(capture_all, sys.argv[1:])
    else:
        dump(capture.capture_variants(capture_all))
        print(f"wrote {GOLDEN}", file=sys.stderr)
