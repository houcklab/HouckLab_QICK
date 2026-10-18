"""The frozen CSTQ03 runner's parameter values and dispatches, read from the frozen text.

Single source: `cstq03_legacy_runner.py.txt` (never edited, see README.md). `namespace()` execs
its sections 1-2 in a fresh sandbox on every call (several runs mutate their dicts), so nothing
here is a hand copy. `dispatches()` evaluates the arguments of every `if <Flag>: run_*(ctx, ...)`
of section 3 in such a namespace. `STEP_OF_FLAG`, `GROUP_OF_DICT`, `group_kwargs` and
`recipe_kwargs` translate them to the session API (qicklab.runs.groups / recipes).
"""

import ast
import hashlib
import re
from pathlib import Path

from qicklab.core.session import GROUPS
from qicklab.runs import groups as G
from qicklab.runs import recipes as R

FIXTURE = Path(__file__).with_name("cstq03_legacy_runner.py.txt")
BLOB_SHA1 = "94cc049016d9ffb7d27784fcfb5e4e2058f37775"  # git hash-object of FIXTURE
EXECUTE_MARKER = "3. EXECUTE"
_STAR_IMPORT = re.compile(r"^from\s+\S+\s+import\s+\*\s*$")

# legacy flag -> canonical step (docs/experiments/README.md#index)
STEP_OF_FLAG = {
    "Constant2Tone": "constant_two_tone",
    "ConstantTone": "constant_tone",
    "RunTransmissionSweep": "transmission_fit",
    "RunTransmissionSweeps": "transmission_sweep",
    "Run2ToneSpec": "two_tone_spec",
    "RunSpecGainLengthSweep": "spec_gain_length_sweep",
    "RunChiShift": "chi_shift",
    "Run2ToneChargeDispersionQuasiCW": "two_tone_charge_dispersion_quasicw",
    "RunModifiedRamsey": "modified_ramsey",
    "RunModifiedRamsey_Control": "modified_ramsey_control",
    "RunChargeDispersionQuasiCW": "charge_dispersion_quasicw",
    "RunChargeDispersionRamsey": "charge_dispersion_ramsey",
    "RunAmplitudeRabi": "amplitude_rabi",
    "RunT1": "t1",
    "RunT1T2E": "t1_t2e",
    "RunT1T2RT2E": "t1_t2r_t2e",
    "RunT2": "t2_ramsey",
    "RunT2E": "t2_echo",
    "RunTrans_QubitSpec": "trans_qubit_spec",
    "RunChargeSweep": "charge_sweep",
    "RunChargeTransmissionSweep": "charge_transmission_sweep",
    "RunActiveResetVerify": "active_reset_verify",
    "RunInterleavedCoherence": "interleaved_coherence",
    "SingleShot": "single_shot",
    "RunUndrivenSingleShot": "undriven_single_shot",
    "RunT1SS": "t1_single_shot",
    "SingleShot_ReadoutOptimize": "readout_optimize",
    "SingleShot_QubitOptimize": "qubit_optimize",
    "RunAutoCoherence": "auto_coherence",
    "RunZeroSpanParity": "zero_span_parity",
}

# runner dict -> session group (the dicts build_context / rebuild_singleshot_config read)
GROUP_OF_DICT = {
    "Transmission_params": "transmission",
    "Spec_relevant_params": "spec",
    "charge_params": "charge",
    "tl": "tones",
    "T1T2_params": "coherence",
    "T2E_params": "echo",
    "SS_params": "single_shot",
}


def blob_sha1():
    """`git hash-object` of the frozen runner text (BLOB_SHA1 while it is intact).

    CRLF is normalised to LF first, as git does under the repo's `* text=auto`.
    """
    data = FIXTURE.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _sections():
    lines = FIXTURE.read_text(encoding="utf-8").splitlines(keepends=True)
    cut = next(i for i, line in enumerate(lines) if EXECUTE_MARKER in line)
    prefix = "".join("\n" if _STAR_IMPORT.match(line) else line for line in lines[:cut])
    tree = ast.parse("".join(lines[cut:]))
    ast.increment_lineno(tree, cut)
    return prefix, tree


def namespace():
    """Fresh {name: value} of the runner's sections 1-2 (device parameters, flags, dicts)."""
    prefix, _ = _sections()
    ns = {"__builtins__": __builtins__}
    exec(compile(prefix, str(FIXTURE), "exec"), ns)
    return {k: v for k, v in ns.items() if not k.startswith("__")}


def _eval(node, ns):
    return eval(compile(ast.Expression(node), str(FIXTURE), "eval"), {"__builtins__": {}}, ns)


def dispatches(ns=None):
    """[(flag, run_* name, [positional args after ctx])] of section 3, in source order.

    The args are evaluated in `ns` (default: a fresh namespace()), so they are the very dict
    objects of that namespace, as the runner passes them.
    """
    ns = namespace() if ns is None else ns
    _, tree = _sections()
    out = []
    for node in tree.body:
        if isinstance(node, ast.If) and isinstance(node.test, ast.Name):
            (stmt,) = node.body
            call = stmt.value
            out.append((node.test.id, call.func.id, [_eval(a, ns) for a in call.args[1:]]))
    return out


def build_context_call(ns=None):
    """(args, kwargs) the runner passes build_context, evaluated in `ns`."""
    ns = namespace() if ns is None else ns
    _, tree = _sections()
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
            if getattr(call.func, "id", None) == "build_context":
                args = [_eval(a, ns) for a in call.args]
                return args, {k.arg: _eval(k.value, ns) for k in call.keywords}
    raise LookupError("no build_context call in section 3")


def _kwargs(table, legacy):
    """(keywords, legacy keys with no keyword) of one legacy dict through a (legacy, kw) table."""
    kw_of = dict(table)
    kwargs = {kw_of[k]: v for k, v in legacy.items() if k in kw_of}
    return kwargs, sorted(k for k in legacy if k not in kw_of)


def group_kwargs(group, legacy):
    """(G.<group> keywords, ignored legacy keys) reproducing the runner dict `legacy`."""
    return _kwargs(G.KEYS[group], legacy)


def recipe_kwargs(step, args):
    """(R.<step> keywords, {slot: ignored legacy keys}) reproducing one dispatch's own dicts.

    Group slots are not converted (they come from the session groups); a trailing slot the
    runner leaves out is None, the run_* default. The output slot of
    two_tone_charge_dispersion_quasicw is passed as `charge_dispersion` (the runner's dict);
    interleaved_coherence's US_params becomes `undriven=R.undriven_single_shot(...)`.
    """
    recipe = R.STEPS[step]
    needs = recipe().needs
    tables = R.LEGACY_KEYS[step]
    kwargs, ignored = {}, {}
    if len(args) > len(needs):
        raise ValueError(f"{step}: {len(args)} arguments for the slots {needs}")
    args = list(args) + [None] * (len(needs) - len(args))  # the run_* defaults: None
    for slot, value in zip(needs, args, strict=True):
        if slot in GROUPS or (value is None and slot != "cd_period_mv"):
            continue
        if step == "two_tone_charge_dispersion_quasicw" and slot == "ChargeDispersion_params":
            kwargs["charge_dispersion"] = value
        elif step == "interleaved_coherence" and slot == "US_params":
            us, ignored[slot] = _kwargs(R.LEGACY_KEYS["undriven_single_shot"]["US_params"], value)
            kwargs["undriven"] = R.undriven_single_shot(**us)
        elif step == "modified_ramsey_control" and slot == "ModifiedRamsey_params":
            if value is not None:
                raise ValueError("the runner never passes ModifiedRamsey_params to MRC")
        elif slot == "cd_period_mv":
            kwargs["cd_period_mv"] = value
        else:
            k, ignored[slot] = _kwargs(tables[slot], value)
            kwargs.update(k)
    return kwargs, ignored
