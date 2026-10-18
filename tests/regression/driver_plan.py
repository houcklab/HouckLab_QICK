"""Replay every golden label through the session API: Session(devices.CSTQ03) + a PLAN of recipes.

The second driver of the golden (the first, ``driver_qicklab``, replays the frozen runner text
through the legacy call shapes and is the only one that writes the golden). Per label:

* the frozen runner's sections 1-2 are executed in a fresh namespace
  (``fixtures/cstq03_legacy_params.namespace()``) and the label's override from
  ``driver_qicklab.OVERRIDES`` / ``MULTI`` is applied to it, exactly as the legacy driver does;
* the session is ``Session(DEVICE with data_root = the temp root, Qubit_Readout, Qubit_Pulse,
  start_voltage, yoko_fixed, <every group rebuilt from its runner dict with G.<group>(...)>)``;
* the PLAN has one ``R.<step>(...)`` per selected flag, in runner order, whose keywords are the
  runner's dispatch dicts translated by ``recipe_kwargs`` (the frozen values passed explicitly;
  library defaults play no part);
* it is replayed in the legacy shape, not with ``run()``: ``ctx = connect(session)``,
  ``run_step(ctx, step)`` for each step, then ``ctx.yoko.close()`` on success only. ``run()``
  closes the yoko in a ``finally``; the legacy runner does not, so a label that raises or
  stops at the capture budget has no trailing yoko CLOSE in the golden.

The one cross-step dict the runner shares by identity is reproduced in the PLAN the way a
user would write it: ``two_tone_charge_dispersion_quasicw(charge_dispersion=...)`` receives
the later ``charge_dispersion_quasicw`` step's own ``ChargeDispersion_params`` dict, so the
probe frequency the search chooses reaches the quasi-CW step (the ``+`` label's leak).

Usage:  python -m tests.regression.driver_plan RunT1    (dry run on A and B, golden untouched)
"""

import builtins
import contextlib
import dataclasses
import io
import json
import os
import shutil
import sys
import tempfile
import time
import warnings

os.environ.setdefault("MPLBACKEND", "Agg")

from devices.CSTQ03 import DEVICE  # noqa: E402
from qicklab.core.session import GROUPS, Session, connect, run_step  # noqa: E402
from qicklab.runs import groups as G  # noqa: E402
from qicklab.runs import recipes as R  # noqa: E402
from tests.regression import capture  # noqa: E402
from tests.regression import driver_qicklab as legacy  # noqa: E402
from tests.regression.fixtures import cstq03_legacy_params as F  # noqa: E402

GOLDEN = legacy.GOLDEN


def install():
    """The legacy driver's mocks (every qicklab module, session layer included, is loaded first)."""
    return legacy.install()


def labels():
    """[(label, flags in runner order, override)] in the legacy driver's label order."""
    flags = [flag for flag, _, _ in F.dispatches()]
    out = []
    for flag in flags:
        out.append((flag, (flag,), None))
        for label, (selected, override) in legacy.OVERRIDES.items():
            if selected[0] == flag:
                out.append((label, selected, override))
    for label, override in legacy.MULTI.items():
        selected = tuple(label.split("+"))
        out.append((label, tuple(f for f in flags if f in selected), override))
    return out


def _groups(ns):
    """{group: G.<group>(...)} rebuilt from the runner's dicts (no runner key may be dropped)."""
    out = {}
    for legacy_name, group in F.GROUP_OF_DICT.items():
        kwargs, ignored = F.group_kwargs(group, ns[legacy_name])
        if ignored:
            raise ValueError(f"{legacy_name}: keys {ignored} have no G.{group}() keyword")
        out[group] = G.BUILDERS[group](**kwargs)
    return out


def _step_kwargs(ns, flags):
    """[(step, kwargs, runner args)] of the selected dispatches; an override's keys must survive."""
    baseline = {flag: F.recipe_kwargs(F.STEP_OF_FLAG[flag], a)[1] for flag, _, a in F.dispatches()}
    out = []
    for flag, _, args in F.dispatches(ns):
        if flag not in flags:
            continue
        step = F.STEP_OF_FLAG[flag]
        kwargs, ignored = F.recipe_kwargs(step, args)
        if ignored != baseline[flag]:
            raise ValueError(f"{flag}: override keys {ignored} have no R.{step}() keyword")
        out.append((step, kwargs, args))
    return out


def build(ns, flags, data_root):
    """(Session, PLAN) of one label from the (overridden) runner namespace `ns`."""
    window = (ns["Readout_Time"], ns["ADC_Offset"])
    if DEVICE.legacy_parameters() != ns["Qubit_Parameters"] or window != (
        DEVICE.readout_window.length_us,
        DEVICE.readout_window.adc_offset_us,
    ):
        raise ValueError(
            "devices/CSTQ03.py no longer carries the frozen runner's qubit values / window: "
            "driver_plan replays the golden with them (give it a frozen Device instead)"
        )
    device = dataclasses.replace(DEVICE, data_root=data_root)
    session = Session(
        device,
        ns["Qubit_Readout"],
        ns["Qubit_Pulse"],
        ns["start_voltage"],
        yoko_fixed=ns["yoko_fixed"],
        **_groups(ns),
    )
    selected = _step_kwargs(ns, flags)
    steps = [None] * len(selected)
    own_dicts = {}  # id(runner dict) -> the later step's own copy of it
    for i in reversed(range(len(selected))):
        step, kwargs, args = selected[i]
        shared = kwargs.get("charge_dispersion")
        if shared is not None and id(shared) in own_dicts:
            kwargs = {**kwargs, "charge_dispersion": own_dicts[id(shared)]}
        steps[i] = R.STEPS[step](**kwargs)
        for slot, value in zip(steps[i].needs, args, strict=False):
            if slot not in GROUPS and isinstance(value, dict):
                own_dicts[id(value)] = steps[i].params[slot]
    return session, steps


def run_one(label, flags, override):
    import matplotlib.pyplot as plt

    root = tempfile.mkdtemp(prefix="qicklab_regression_")
    capture.begin_run(label, root)
    verbose = bool(os.environ.get("REGRESSION_VERBOSE"))
    out_sink = sys.stdout if verbose else io.StringIO()
    err_sink = sys.stderr if verbose else io.StringIO()
    try:
        with (
            contextlib.redirect_stdout(out_sink),
            contextlib.redirect_stderr(err_sink),
            legacy._patched(builtins, "input", legacy._no_stdin),
            warnings.catch_warnings(),
        ):
            # connect()'s Device.validate warnings (Nyquist images of the CSTQ03 set): known,
            # printed by every label, not part of what the golden compares
            warnings.filterwarnings("ignore", message=f"{DEVICE.name}: ", category=UserWarning)
            ns = F.namespace()
            if override is not None:
                override(ns)
            session, plan = build(ns, flags, root)
            ctx = connect(session)
            for step in plan:
                run_step(ctx, step)
            ctx.yoko.close()  # the legacy runner's last line: reached on success only
        outcome = {"status": "completed"}
    except capture.StopCapture:
        outcome = {"status": "stopped_at_budget"}
    except Exception as exc:
        outcome = {
            "status": "raised",
            "type": type(exc).__name__,
            "message": capture.normalize(str(exc))[:400],
            "traceback": legacy._traceback_tail(exc),
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


def capture_all(labels_wanted=None):
    """{run label: {...}} on the currently selected board (capture.set_board)."""
    install()
    out = {}
    for label, flags, override in labels():
        if labels_wanted is not None and label not in labels_wanted:
            continue
        t0 = time.perf_counter()
        out[label] = run_one(label, flags, override)
        status = out[label]["outcome"]["status"]
        n = len(out[label]["experiments"])
        n_skip = sum(out[label]["skipped"].values())
        print(
            f"[regression:plan] {capture.current_board()} {label:<53} {status:<18} "
            f"{n:>3} exp {n_skip:>4} skip {time.perf_counter() - t0:6.1f}s",
            file=sys.stderr,
        )
    return json.loads(json.dumps(out, allow_nan=True))


if __name__ == "__main__":
    if not sys.argv[1:]:
        sys.exit("usage: python -m tests.regression.driver_plan <label> [...] (never writes)")
    capture.capture_variants(capture_all, sys.argv[1:])
