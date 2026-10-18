"""runners/CSTQ03_session.py hands every step the arguments runners/CSTQ03_BFC.py passes.

The legacy runner's sections 1-2 are executed (imports dropped) and every `if <Flag>: run_*`
of its section 3 is evaluated there. For every dispatch the session runner's STEP[<step>],
resolved against its SESSION, must produce:

* exactly what R.<step>(...) builds from the runner's own dicts (same keys, values, types and
  key order, as printed);
* every key of the runner's raw dicts with the runner's value and type (recursively into
  sub-dicts), except the runner keys with no recipe keyword, which must equal the pinned
  DEAD_KEYS allowlist (dead in the run_*; a key a user adds to a runner dict without a recipe
  keyword therefore fails here instead of silently never reaching the run).

The printed dicts are equivalent to the runner's, not textually equal: the dead keys are
dropped and the run_* defaults are written out. Delete this module with the legacy runner
(phase 5b): it skips itself at module level once runners/CSTQ03_BFC.py is gone.
"""

import ast
import importlib
from pathlib import Path

import pytest

from qicklab.core.session import GROUPS
from qicklab.runs import groups as G
from qicklab.runs import recipes as R
from tests.regression.fixtures import cstq03_legacy_params as F

REPO = Path(__file__).resolve().parents[1]
LEGACY = REPO / "runners" / "CSTQ03_BFC.py"
if not LEGACY.exists():
    pytest.skip("legacy runner deleted (5b)", allow_module_level=True)

runner = importlib.import_module("runners.CSTQ03_session")


def _legacy():
    """(namespace of sections 1-2, [(flag, [args after ctx])] of section 3)."""
    tree = ast.parse(LEGACY.read_text(encoding="utf-8"))
    cut = next(
        i
        for i, node in enumerate(tree.body)
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "ctx"
    )
    prefix = [n for n in tree.body[:cut] if not isinstance(n, (ast.Import, ast.ImportFrom))]
    ns = {}
    exec(compile(ast.Module(body=prefix, type_ignores=[]), str(LEGACY), "exec"), ns)

    def value(node):
        return eval(compile(ast.Expression(node), str(LEGACY), "eval"), {"__builtins__": {}}, ns)

    dispatches = []
    for node in tree.body[cut:]:
        if isinstance(node, ast.If) and isinstance(node.test, ast.Name):
            (stmt,) = node.body
            dispatches.append((node.test.id, [value(a) for a in stmt.value.args[1:]]))
    return ns, dispatches


NS, DISPATCHES = _legacy()


# Runner keys with no recipe keyword ({flag: {slot: sorted keys}}): dead in the run_*, which
# never reads them (the golden's cfg_access shows it). Any other dropped key fails the test.
DEAD_KEYS = {
    "RunModifiedRamsey_Control": {"ModifiedRamsey_Control_params": ["Gauss"]},
    "RunChargeDispersionQuasiCW": {"ChargeDispersion_params": ["lower_freq", "upper_freq"]},
    "RunChargeDispersionRamsey": {
        "ChargeDispersion_params": ["lower_freq", "probe_freq", "repetitions", "upper_freq"]
    },
}


def _expected_step(step, args):
    """(R.<step>(...) from the runner's own dicts, {slot: runner keys with no keyword})."""
    if step == "modified_ramsey_control":  # the live runner also passes ModifiedRamsey_params
        own, ramsey = args
        kw, own_ignored = F._kwargs(R.LEGACY_KEYS[step]["ModifiedRamsey_Control_params"], own)
        mr, mr_ignored = F._kwargs(
            R.LEGACY_KEYS["modified_ramsey"]["ModifiedRamsey_params"], ramsey
        )
        ignored = {
            "ModifiedRamsey_Control_params": own_ignored,
            "ModifiedRamsey_params": mr_ignored,
        }
        return R.modified_ramsey_control(**kw, ramsey=R.modified_ramsey(**mr)), ignored
    kwargs, ignored = F.recipe_kwargs(step, args)
    return R.STEPS[step](**kwargs), ignored


def _carries(got, raw, dead, where):
    """Every key of the runner dict `raw` (but `dead`) is in `got` with the same value and type."""
    for key, value in raw.items():
        if key in dead:
            continue
        assert key in got, f"{where}: runner key {key!r} does not reach the run"
        if isinstance(value, dict):
            assert isinstance(got[key], dict), f"{where}.{key}"
            _carries(got[key], value, (), f"{where}.{key}")
        else:
            assert got[key] == value, f"{where}.{key}"
            assert type(got[key]) is type(value), f"{where}.{key}"


def test_session_is_the_runner_selection():
    s = runner.SESSION
    assert (s.qubit_readout, s.qubit_pulse) == (NS["Qubit_Readout"], NS["Qubit_Pulse"])
    assert s.bias_v == NS["start_voltage"] and s.yoko_fixed is NS["yoko_fixed"]
    assert s.device.cavity_min is NS["cavity_min"]
    assert s.device.legacy_parameters() == NS["Qubit_Parameters"]


@pytest.mark.parametrize("legacy_name, group", list(F.GROUP_OF_DICT.items()))
def test_session_groups_are_the_runner_dicts(legacy_name, group):
    got = G.resolve(runner.SESSION.groups(), runner.SESSION.qubit())[group]
    want = dict(NS[legacy_name])
    if group == "coherence":  # a t2_ramsey / t1_t2r_t2e keyword here; the runs .get() it
        assert want.pop("f_virt_mhz") is None
    assert got == want
    assert {k: type(v) for k, v in got.items()} == {k: type(v) for k, v in want.items()}


def test_step_catalogue_has_every_canonical_step():
    assert set(runner.STEP) == set(R.STEPS)
    assert all(runner.STEP[name].name == name for name in runner.STEP)
    # in the legacy dispatch order, so a PLAN listed in STEP order runs as the runner did
    assert list(runner.STEP) == [F.STEP_OF_FLAG[flag] for flag, _ in DISPATCHES]
    assert all(any(step is s for s in runner.STEP.values()) for step in runner.PLAN)


def test_plan_is_the_runner_flags():
    on = [F.STEP_OF_FLAG[flag] for flag, _ in DISPATCHES if NS[flag]]
    assert [s.name for s in runner.PLAN] == on


@pytest.mark.parametrize(("flag", "args"), DISPATCHES, ids=[f for f, _ in DISPATCHES])
def test_step_arguments_are_the_runner_arguments(flag, args):
    step = F.STEP_OF_FLAG[flag]
    session = runner.SESSION
    got = runner.STEP[step].arguments(session.groups(), session.qubit())
    legacy_groups = {g: NS[d] for d, g in F.GROUP_OF_DICT.items()}
    expected, ignored = _expected_step(step, args)
    assert {slot: keys for slot, keys in ignored.items() if keys} == DEAD_KEYS.get(flag, {})
    want = expected.arguments(legacy_groups, session.qubit())
    needs = runner.STEP[step].needs
    raw = list(args) + [None] * (len(needs) - len(args))
    for slot, g, w, r in zip(needs, got, want, raw, strict=True):
        if step == "two_tone_charge_dispersion_quasicw" and slot == "ChargeDispersion_params":
            # output dict: the quasi-CW step's own, as the runner shares ChargeDispersion_params
            assert g is runner.STEP["charge_dispersion_quasicw"].params[slot]
            continue
        if slot in GROUPS and slot == "coherence":
            w = {k: v for k, v in w.items() if not (k == "f_virt_mhz" and v is None)}
        assert g == w, slot
        assert repr(g) == repr(w), slot  # same types and key order, as printed
        if isinstance(r, dict):  # the runner's raw dict itself, not only its translation
            dead = list(ignored.get(slot, ()))
            if slot == "coherence" and r.get("f_virt_mhz", 0) is None:
                dead.append("f_virt_mhz")  # the one group key allowed absent (the runs .get() it)
            _carries(g, r, dead, slot)


def test_dead_keys_allowlist_catches_a_new_runner_key():
    """A key added to a runner dict with no recipe keyword is reported, not silently dropped."""
    flag, args = next((f, a) for f, a in DISPATCHES if f == "RunAmplitudeRabi")
    args = [dict(a, not_a_recipe_keyword=1) if isinstance(a, dict) else a for a in args]
    _, ignored = _expected_step(F.STEP_OF_FLAG[flag], args)
    assert any("not_a_recipe_keyword" in keys for keys in ignored.values())
