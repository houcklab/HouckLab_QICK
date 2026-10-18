"""Session groups (qicklab.runs.groups) and step recipes (qicklab.runs.recipes).

Every recipe slot is checked against what its run_* reads: an AST scan of the run_* source
(following the dict into the qicklab helpers it is handed to), and the golden cfg_access where a
dict is merged into an experiment's cfg. The library defaults are checked against the frozen
runner (tests/regression/fixtures/cstq03_legacy_params.py), and every runner dispatch is
rebuilt as a Step whose arguments reproduce the runner's own dicts.
"""

import ast
import inspect
import json
import re
import textwrap
from functools import cache
from pathlib import Path

import pytest

from devices.CSTQ03 import DEVICE
from qicklab.core.config import rebuild_singleshot_config
from qicklab.core.context import build_context
from qicklab.core.device import ParityParams
from qicklab.core.session import GROUPS, Step
import qicklab.runs as runs
from qicklab.runs import groups as G
from qicklab.runs import recipes as R
from qicklab.runs.auto_coherence import AUTO_COHERENCE_PARAMS
from qicklab.runs.modified_ramsey import run_modified_ramsey_control
from qicklab.runs.single_shot import run_undriven_single_shot
from tests.regression.fixtures import cstq03_legacy_params as F

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "tests" / "regression" / "golden_cstq03.json"

CANONICAL = {  # design.md "Device / session layer": step -> regime
    "transmission_fit": "A",
    "transmission_sweep": "A",
    "constant_tone": "A",
    "constant_two_tone": "A",
    "two_tone_spec": "A",
    "spec_gain_length_sweep": "A",
    "trans_qubit_spec": "A",
    "chi_shift": "A",
    "amplitude_rabi": "A",
    "t1": "A",
    "t2_ramsey": "A",
    "t2_echo": "A",
    "t1_t2e": "A",
    "t1_t2r_t2e": "A",
    "interleaved_coherence": "A",
    "auto_coherence": "B",
    "single_shot": "B",
    "undriven_single_shot": "B",
    "t1_single_shot": "B",
    "readout_optimize": "B",
    "qubit_optimize": "B",
    "active_reset_verify": "A",
    "modified_ramsey": "A",
    "modified_ramsey_control": "A",
    "charge_dispersion_ramsey": "A",
    "charge_dispersion_quasicw": "A",
    "two_tone_charge_dispersion_quasicw": "A",
    "charge_sweep": "A",
    "charge_transmission_sweep": "A",
    "zero_span_parity": "B",
}

# keywords that are not legacy keys of a slot table: they carry another Step or a shared dict
SPECIAL_KEYWORDS = {
    "modified_ramsey_control": {"ramsey"},
    "interleaved_coherence": {"undriven"},
    "two_tone_charge_dispersion_quasicw": {"charge_dispersion"},
}
ZSP = "zero_span_params"


# AST scan: which keys does a run_* read from one of its dict arguments
class Reads:
    """{path: {key: {access kinds}}} read from one parameter; path () is the dict itself."""

    def __init__(self):
        self.keys = {}
        self.merged = {}  # path -> where the whole dict is merged or handed to non-qicklab code

    def add(self, path, key, kind):
        self.keys.setdefault(path, {}).setdefault(key, set()).add(kind)

    def at(self, path=()):
        return set(self.keys.get(path, {}))

    def kinds(self, path=()):
        return self.keys.get(path, {})


def _const_strings(node, fn, local_consts):
    """The str constants of a literal tuple/list, or of a name bound to one (locally/globally)."""
    if isinstance(node, (ast.Tuple, ast.List)):
        return [
            [x.value if isinstance(x, ast.Constant) else None for x in e.elts]
            if isinstance(e, ast.Tuple)
            else (e.value if isinstance(e, ast.Constant) else None)
            for e in node.elts
        ]
    if isinstance(node, ast.Name):
        if node.id in local_consts:
            return local_consts[node.id]
        value = fn.__globals__.get(node.id)
        if isinstance(value, (tuple, list)):
            return list(value)
    return None


def _loop_values(tree, fn):
    """name -> {str} for loop / comprehension targets iterating over constant tuples."""
    local_consts = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, (ast.Tuple, ast.List))
        ):
            local_consts[node.targets[0].id] = [
                e.value
                if isinstance(e, ast.Constant)
                else ([x.value if isinstance(x, ast.Constant) else None for x in e.elts])
                if isinstance(e, ast.Tuple)
                else None
                for e in node.value.elts
            ]
    values = {}
    loops = [n for n in ast.walk(tree) if isinstance(n, (ast.For, ast.comprehension))]
    for loop in loops:
        items = _const_strings(loop.iter, fn, local_consts)
        if items is None:
            continue
        target = loop.target
        if isinstance(target, ast.Name):
            values.setdefault(target.id, set()).update(i for i in items if isinstance(i, str))
        elif isinstance(target, ast.Tuple):
            for pos, elt in enumerate(target.elts):
                if isinstance(elt, ast.Name):
                    for item in items:
                        if isinstance(item, (list, tuple)) and pos < len(item):
                            if isinstance(item[pos], str):
                                values.setdefault(elt.id, set()).add(item[pos])
    return values


def _callee(fn, call):
    func, glb = call.func, fn.__globals__
    if isinstance(func, ast.Name):
        obj = glb.get(func.id)
    elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        obj = getattr(glb.get(func.value.id), func.attr, None)
    else:
        return None
    obj = inspect.unwrap(obj) if callable(obj) else None
    if inspect.isfunction(obj) and (obj.__module__ or "").startswith("qicklab"):
        return obj
    return None


def scan(fn, pname, out=None, base=(), seen=None):
    """Reads of parameter `pname` of `fn`, following it into qicklab helpers it is passed to."""
    out = Reads() if out is None else out
    seen = set() if seen is None else seen
    if (fn, pname, base) in seen:
        return out
    seen.add((fn, pname, base))
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn))).body[0]
    loops = _loop_values(tree, fn)
    aliases = {pname: {base}}

    def paths(node):
        if isinstance(node, ast.Name):
            return aliases.get(node.id, set())
        if isinstance(node, ast.BoolOp):  # `x or {}`
            return set().union(*(paths(v) for v in node.values))
        if isinstance(node, ast.IfExp):
            return paths(node.body) | paths(node.orelse)
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            return {p + (node.slice.value,) for p in paths(node.value)}
        return set()

    def keys_of(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return {node.value}
        if isinstance(node, ast.Name) and node.id in loops:
            return loops[node.id]
        return {"<dynamic>"}

    for _ in range(3):  # aliases: name = <tracked expr>, to a fixpoint
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and paths(node.value):
                    aliases.setdefault(target.id, set()).update(paths(node.value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            for p in paths(node.value):
                kind = "write" if isinstance(node.ctx, (ast.Store, ast.Del)) else "[]"
                for k in keys_of(node.slice):
                    out.add(p, k, kind)
        elif isinstance(node, ast.Compare) and isinstance(node.ops[0], (ast.In, ast.NotIn)):
            for p in paths(node.comparators[0]):
                for k in keys_of(node.left):
                    out.add(p, k, "in")
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and paths(func.value) and node.args:
            if func.attr in ("get", "setdefault", "pop"):
                default = ast.unparse(node.args[1]) if len(node.args) > 1 else "None"
                for p in paths(func.value):
                    for k in keys_of(node.args[0]):
                        out.add(p, k, f"{func.attr}:{default}")
                continue
        args = [(i, a) for i, a in enumerate(node.args)] + [(k.arg, k.value) for k in node.keywords]
        for where, arg in args:
            for p in paths(arg):
                callee = _callee(fn, node)
                if callee is None or where is None:
                    out.merged.setdefault(p, set()).add(ast.unparse(func))
                    continue
                names = list(inspect.signature(callee).parameters)
                name = names[where] if isinstance(where, int) else where
                if isinstance(where, int) and where >= len(names):
                    continue
                scan(callee, name, out, p, seen)
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            for side in (node.left, node.right):
                for p in paths(side):
                    out.merged.setdefault(p, set()).add("|")
        elif isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values, strict=True):
                if k is None:
                    for p in paths(v):
                        out.merged.setdefault(p, set()).add("**")
    return out


@cache
def run_reads(step, slot):
    """Reads of the run_* parameter that slot `slot` of `step` fills."""
    s = R.STEPS[step]()
    names = list(inspect.signature(s.fn).parameters)[1:]
    return scan(s.fn, names[s.needs.index(slot)])


def _optional_default(fn, kinds):
    """The value the run uses when the key is absent (its .get / .setdefault default), or a
    marker when the key is read unconditionally or only tested for presence."""
    for kind in kinds:
        if kind.startswith(("get:", "setdefault:")):
            src = kind.split(":", 1)[1]
            try:
                return ast.literal_eval(src)
            except ValueError:
                if src in fn.__globals__:
                    return fn.__globals__[src]
                return _COMPUTED
    return _REQUIRED


_COMPUTED = object()  # a .get default computed at run time (ctx value, other keys)
_REQUIRED = object()


@cache
def golden():
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def golden_reads(label, cls):
    return set(golden()["A"][label]["cfg_access"][cls]["read"])


def _slot(step, name):
    return next(s for s in R._RECIPES[step].slots if s.name == name)


# the recipe set
def test_one_recipe_per_canonical_step():
    assert set(R.STEPS) == set(CANONICAL)
    for name, recipe in R.STEPS.items():
        step = recipe()
        assert isinstance(step, Step) and step.name == name
        assert step.regime == CANONICAL[name], name
        assert step.fn.__module__.startswith("qicklab.runs.") and step.fn.__name__.startswith(
            "run_"
        )


@pytest.mark.parametrize("fn", [*R.STEPS.values(), *G.BUILDERS.values()])
def test_keyword_only_documented_and_typo_raises(fn):
    params = inspect.signature(fn).parameters.values()
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params), fn.__name__
    assert all(p.name == p.name.lower() and p.name.isidentifier() for p in params)
    doc = inspect.getdoc(fn)
    assert doc and len(doc.splitlines()[0]) <= 100, fn.__name__
    if fn in R.STEPS.values():
        page = doc.split("docs/experiments/")[-1].split()[0].rstrip(".")
        assert (REPO / "docs" / "experiments" / page).is_file(), (fn.__name__, page)
    with pytest.raises(TypeError):
        fn(not_a_parameter=1)


def test_zero_span_subdict_typo_raises():
    with pytest.raises(TypeError, match="n_chunk"):
        R.zero_span_parity(strobe={"n_chunk": 3})
    step = R.zero_span_parity(strobe={"n_chunks": 3})
    assert step.params[ZSP]["ZSP_StrobeParams"]["n_chunks"] == 3
    assert R.ZSP_SUBDICTS["ZSP_StrobeParams"]["n_chunks"] == 60  # defaults untouched


_CALL = re.compile(r"\b([RG])\.([a-z0-9_]+)\(")
_KEYWORD = re.compile(r"(?:^|[,(\s])([A-Za-z_]\w*)\s*=(?!=)")


def test_doc_snippets_use_real_recipes_and_keywords():
    bad = []
    for page in sorted((REPO / "docs").rglob("*.md")):
        if page.relative_to(REPO / "docs").parts[0] == "dev":
            continue
        text = page.read_text(encoding="utf-8")
        for m in _CALL.finditer(text):
            fn = (R.STEPS if m[1] == "R" else vars(G)).get(m[2])
            where = f"{page.relative_to(REPO)}:{text.count(chr(10), 0, m.start()) + 1}"
            if not callable(fn):
                bad.append((where, f"{m[1]}.{m[2]}"))
                continue
            end, depth = m.end(), 1
            while end < len(text) and depth:
                depth += {"(": 1, ")": -1}.get(text[end], 0)
                end += 1
            given = set(_KEYWORD.findall(text[m.end() : end - 1]))
            bad += [
                (where, f"{m[1]}.{m[2]}({kw}=)")
                for kw in sorted(given - set(inspect.signature(fn).parameters))
            ]
    assert not bad


def test_legacy_tables_cover_every_keyword():
    for name, recipe in R.STEPS.items():
        kws = set(inspect.signature(recipe).parameters)
        table = {kw for slot in R.LEGACY_KEYS[name].values() for _, kw in slot}
        assert table | SPECIAL_KEYWORDS.get(name, set()) == kws, name
        assert set(R.FROZEN_DIFFERENCES.get(name, {})) <= kws, name
    for group, table in G.KEYS.items():
        assert {kw for _, kw in table} == set(inspect.signature(G.BUILDERS[group]).parameters)
        assert list(G.BUILDERS[group]()) == [legacy for legacy, _ in table]
        assert set(G.FROZEN_DIFFERENCES.get(group, {})) <= {kw for _, kw in table}


# keys == what the run_* reads
def _own_slots():
    for name in R.STEPS:
        for slot in R._RECIPES[name].slots:
            if slot.name not in GROUPS and not slot.scalar:
                yield name, slot.name


@pytest.mark.parametrize(("step", "slot"), list(_own_slots()))
def test_own_slot_keys_are_what_the_run_reads(step, slot):
    value = R.STEPS[step]().params[slot]
    if step == "interleaved_coherence" and slot == "US_params":
        # merged with {"Repeat": 1, "plotDisp": False} and handed to run_undriven_single_shot
        assert set(value) == scan(run_undriven_single_shot, "US_params").at()
        return
    if step == "modified_ramsey_control" and slot == "ModifiedRamsey_params":
        assert value is None  # legacy: the Ramsey uses MRC's own keys (ramsey= gives MR's)
        assert run_reads(step, slot).at() <= set(R.modified_ramsey().params[slot])
        return
    reads = run_reads(step, slot)
    if _slot(step, slot).output:  # written by the run, then read back
        assert value == {}
        assert all("write" in k for k in reads.kinds().values())
        return
    if step == "auto_coherence":  # merged over AUTO_COHERENCE_PARAMS
        assert () in reads.merged
        assert value == AUTO_COHERENCE_PARAMS
        return
    if step == "chi_shift":  # merged into the cfg ChiShift reads (golden cfg_access)
        assert reads.merged.get(()) == {"ctx.working_config"}
        assert set(value) <= golden_reads("RunChiShift", "ChiShift")
        return
    assert "<dynamic>" not in reads.at(), reads.kinds()
    assert set(value) == reads.at()


def test_zero_span_subdicts_are_what_the_run_reads():
    reads = run_reads("zero_span_parity", ZSP)
    params = R.zero_span_parity().params[ZSP]
    zsp_reads = golden_reads("RunZeroSpanParity[gate_off]", "ZeroSpanParity")
    experiment_src = (REPO / "qicklab" / "experiments" / "zero_span_parity.py").read_text()
    for legacy, sub in params.items():
        if legacy not in R.ZSP_SUBDICTS:
            continue
        if (legacy,) in reads.merged:  # **mode_params into the ZeroSpanParity cfg
            assert legacy in ("ZSP_StrobeParams", "ZSP_DecimatedParams")
            if legacy == "ZSP_StrobeParams":  # read by the class, n_chunks by the run
                assert set(sub) <= zsp_reads | reads.at((legacy,))
            else:  # decimated mode never runs in the golden: the class must name each key
                assert all(f'"{k}"' in experiment_src for k in sub), sub
            continue
        assert set(sub) == reads.at((legacy,)), legacy


# whole dicts merged into another dict or cfg instead of read key by key (scan() cannot see
# which keys survive): (step, slot, path) -> where their keys are checked
WHOLE_DICT_MERGES = {
    ("chi_shift", "ChiShift_params", ()): "the ChiShift cfg: test_own_slot_keys (golden)",
    ("interleaved_coherence", "US_params", ()): "US_params | forced: test_own_slot_keys",
    ("interleaved_coherence", "coherence", ()): "group | per-step: the coherence group test",
    ("interleaved_coherence", "echo", ()): "group | per-step: the echo group test",
    ("auto_coherence", "AutoCoherence_override_params", ()): "over AUTO_COHERENCE_PARAMS",
    ("zero_span_parity", ZSP, ("ZSP_StrobeParams",)): "the ZeroSpanParity cfg (golden)",
    ("zero_span_parity", ZSP, ("ZSP_DecimatedParams",)): "the ZeroSpanParity cfg (source)",
}


def test_whole_dict_merges_are_the_known_ones():
    found = set()
    for name in R.STEPS:
        for slot in R._RECIPES[name].slots:
            if slot.scalar:
                continue
            for path in run_reads(name, slot.name).merged:
                if path == () or (name == "zero_span_parity" and len(path) == 1):
                    found.add((name, slot.name, path))
    assert found == set(WHOLE_DICT_MERGES)


# runner keys an experiment reads although the recipe does not pass them: set elsewhere
READ_ELSEWHERE = {
    # the sweet-spot search spec plays Gauss=True itself (runs/auto_coherence.py spec_cfg)
    ("modified_ramsey_control", "Gauss"): (
        run_modified_ramsey_control,
        "ModifiedRamsey_Control_params",
    ),
}


def _nested_keys(d):
    out = set(d)
    for v in d.values():
        if isinstance(v, dict):
            out |= _nested_keys(v)
    return out


@pytest.mark.parametrize("label", sorted(json.loads(GOLDEN.read_text(encoding="utf-8"))["A"]))
def test_runner_keys_the_experiments_read_are_recipe_keys(label):
    """Golden cfg_access, independent of scan(): a key of a runner dict passed to the label's
    steps that an experiment class read must be passed by the recipe (own slot or group)."""
    record = golden()["A"][label]
    read = set().union(*(set(a["read"]) for a in record["cfg_access"].values()))
    ns = F.namespace()
    args_of = {flag: args for flag, _, args in F.dispatches(ns)}
    for flag in (part.split("[")[0] for part in label.split("+")):
        step = F.STEP_OF_FLAG[flag]
        s = R.STEPS[step]()
        runner, recipe = set(), set()
        args = list(args_of[flag]) + [None] * (len(s.needs) - len(args_of[flag]))
        for slot, value in zip(s.needs, args, strict=True):
            if slot in GROUPS:
                recipe |= set(G.BUILDERS[slot]())
                continue
            if isinstance(value, dict):
                runner |= _nested_keys(value)
            if isinstance(s.params[slot], dict):
                recipe |= _nested_keys(s.params[slot])
        if step == "modified_ramsey_control":  # ramsey= hands over the MR keys
            recipe |= set(R.modified_ramsey().params["ModifiedRamsey_params"])
        missing = (runner & read) - recipe
        for key in missing:
            fn, param = READ_ELSEWHERE.get((step, key), (None, None))
            assert fn is not None, (step, key)
            assert key not in scan(fn, param).at(), (step, key)  # the run never takes it


def _group_consumers():
    """group -> [(function, parameter)] that read it: the config builders and every step slot."""
    out = {g: [] for g in GROUPS}
    builder = {
        "Transmission_params": "transmission",
        "Spec_relevant_params": "spec",
        "tl": "tones",
        "charge_params": "charge",
    }
    for param, group in builder.items():
        out[group].append((build_context, param))
    out["single_shot"].append((rebuild_singleshot_config, "SS_params"))
    for name in R.STEPS:
        s = R.STEPS[name]()
        names = list(inspect.signature(s.fn).parameters)[1:]
        for i, slot in enumerate(s.needs):
            if slot in GROUPS:
                out[slot].append((s.fn, names[i]))
    return out


@pytest.mark.parametrize("group", GROUPS)
def test_group_keys_are_what_the_consumers_read(group):
    keys = set(G.BUILDERS[group]())
    overrides = {
        legacy
        for name in R.STEPS
        for slot, table in R.LEGACY_KEYS[name].items()
        if slot == group
        for legacy, _ in table
    }
    read, merged = set(), False
    for fn, param in _group_consumers()[group]:
        reads = scan(fn, param)
        assert "<dynamic>" not in reads.at(), (fn.__name__, reads.kinds())
        read |= reads.at()
        merged |= fn is build_context and () in reads.merged
    if merged:  # tl / charge_params are merged into the regime-A base cfg
        cfg = golden()["A"]["RunT1"]["experiments"][0]["cfg"]
        assert keys <= set(cfg)
        read |= keys
    assert keys <= read, f"{group}: keys nobody reads {sorted(keys - read)}"
    assert read - keys <= overrides, f"{group}: read but neither group key nor step override"
    for name in R.STEPS:  # a step override is a key the step's own run reads
        if group in R.LEGACY_KEYS[name]:
            mine = {legacy for legacy, _ in R.LEGACY_KEYS[name][group]}
            assert mine <= run_reads(name, group).at(), (name, mine - run_reads(name, group).at())


# library defaults vs the frozen runner
def _diff(fn, reads_kinds, lib, frozen, drop_none=frozenset()):
    """Legacy keys where lib and frozen make the run behave differently."""
    out = set()
    for key in set(lib) | set(frozen):
        kinds = reads_kinds.get(key, set())
        if not kinds:  # nobody reads it (frozen-only dead key)
            assert key not in lib, key
            continue
        if key in lib and key in frozen:
            if lib[key] != frozen[key]:
                out.add(key)
        elif key in lib:
            if not (
                (lib[key] is None and key in drop_none) or _same_as_absent(fn, kinds, lib[key])
            ):
                out.add(key)
        else:
            out.add(key)
    return out


def _same_as_absent(fn, kinds, value):
    default = _optional_default(fn, kinds)
    return default is not _REQUIRED and default is not _COMPUTED and default == value


@pytest.mark.parametrize("group", list(G.KEYS))
def test_group_defaults_are_the_runner_values_except_documented(group):
    legacy_name = {g: d for d, g in F.GROUP_OF_DICT.items()}[group]
    frozen = F.namespace()[legacy_name]
    lib = G.BUILDERS[group]()
    differ = {k for k in set(lib) | set(frozen) if lib.get(k, object()) != frozen.get(k)}
    documented = {
        dict((kw, legacy) for legacy, kw in G.KEYS[group])[kw]
        for kw in G.FROZEN_DIFFERENCES.get(group, {})
    }
    assert differ == documented


@pytest.mark.parametrize("legacy_name, group", list(F.GROUP_OF_DICT.items()))
def test_group_rebuilt_from_the_runner_dict_is_the_runner_dict(legacy_name, group):
    """The slice-d driver's contract: G.<group>(**group_kwargs(group, ns[dict])) == ns[dict]."""
    frozen = F.namespace()[legacy_name]
    kwargs, ignored = F.group_kwargs(group, frozen)
    assert ignored == []
    rebuilt = G.BUILDERS[group](**kwargs)
    assert rebuilt == frozen
    assert list(rebuilt) == list(frozen)
    assert rebuilt is not frozen


def _dispatch_steps():
    return [(flag, F.STEP_OF_FLAG[flag]) for flag, _, _ in F.dispatches()]


@pytest.mark.parametrize(("flag", "step"), _dispatch_steps())
def test_step_defaults_are_the_runner_values_except_documented(flag, step):
    ns = F.namespace()
    args = next(a for f, _, a in F.dispatches(ns) if f == flag)
    lib_step = R.STEPS[step]()
    documented = set()
    for table in R.LEGACY_KEYS[step].values():
        legacy_of = {kw: legacy for legacy, kw in table}
        documented |= {
            legacy_of[kw] for kw in R.FROZEN_DIFFERENCES.get(step, {}) if kw in legacy_of
        }
    differ = set()
    for i, slot in enumerate(lib_step.needs):
        if slot in GROUPS or i >= len(args) or args[i] is None:
            continue
        spec = _slot(step, slot)
        if spec.output:
            continue
        if step == "interleaved_coherence" and slot == "US_params":
            kinds = scan(run_undriven_single_shot, "US_params").kinds()
            forced = {"Repeat": 1, "plotDisp": False}  # the loop passes US_params | forced
            lib, frozen = lib_step.params[slot] | forced, args[i] | forced
            differ |= _diff(run_undriven_single_shot, kinds, lib, frozen, spec.drop_none)
            continue
        reads = run_reads(step, slot)
        lib, frozen = lib_step.params[slot], args[i]
        if step == "zero_span_parity":
            for legacy, sub in lib.items():
                if isinstance(sub, dict):
                    sub_kinds = reads.kinds((legacy,))
                    if (legacy,) in reads.merged:
                        sub_kinds = {k: {"[]"} for k in sub}
                    for k in _diff(lib_step.fn, sub_kinds, sub, frozen[legacy]):
                        differ.add(f"{legacy}.{k}")
                elif sub != frozen[legacy]:
                    differ.add(legacy)
            continue
        kinds = reads.kinds()
        if step in ("auto_coherence", "chi_shift"):  # merged: every key counts as read
            kinds = {k: {"[]"} for k in set(lib) | set(frozen)}
            if step == "auto_coherence":
                frozen = {**AUTO_COHERENCE_PARAMS, **frozen}
        differ |= _diff(lib_step.fn, kinds, lib, frozen, spec.drop_none)
    assert differ == documented, (sorted(differ - documented), sorted(documented - differ))


# every runner dispatch, as a Step, reproduces the runner's arguments
@pytest.mark.parametrize(("flag", "step"), _dispatch_steps())
def test_dispatch_rebuilt_as_step_passes_the_runner_dicts(flag, step):
    ns = F.namespace()
    args = next(a for f, _, a in F.dispatches(ns) if f == flag)
    kwargs, ignored = F.recipe_kwargs(step, args)
    s = R.STEPS[step](**kwargs)
    groups = {g: ns[d] for d, g in F.GROUP_OF_DICT.items()}
    actual = s.arguments(groups, DEVICE.qubits[ns["Qubit_Pulse"]])
    assert len(actual) == len(s.needs)
    padded = list(args) + [None] * (len(s.needs) - len(args))
    for slot, got, want in zip(s.needs, actual, padded, strict=True):
        if slot in GROUPS:
            assert got == want and got is not want, slot
        elif _slot(step, slot).output:
            assert got is want  # the run writes probe_freq into the runner's own dict
        elif step == "zero_span_parity":
            reads = run_reads(step, slot)
            assert set(got) == set(want)
            for legacy, sub in got.items():
                if not isinstance(sub, dict):
                    assert sub == want[legacy], legacy
                    continue
                for k in set(sub) | set(want[legacy]):
                    if k in want[legacy]:
                        assert sub[k] == want[legacy][k], (legacy, k)
                    else:
                        assert _same_as_absent(s.fn, reads.kinds((legacy,)).get(k, ()), sub[k])
        elif want is None or not isinstance(want, dict):
            assert got == want or (want is None and slot == "cw_params"), slot
        else:
            fn, kinds = s.fn, run_reads(step, slot).kinds()
            if step == "interleaved_coherence" and slot == "US_params":
                fn, kinds = (
                    run_undriven_single_shot,
                    scan(run_undriven_single_shot, "US_params").kinds(),
                )
            if step == "auto_coherence":  # the run merges it over AUTO_COHERENCE_PARAMS
                assert {**AUTO_COHERENCE_PARAMS, **got} == {**AUTO_COHERENCE_PARAMS, **want}
                continue
            if step == "chi_shift":  # merged into the cfg as it is
                assert got == want, slot
                continue
            for k in set(got) | set(want):
                if k in got and k in want:
                    assert got[k] == want[k], (slot, k)
                elif k in got:
                    assert _same_as_absent(fn, kinds.get(k, ()), got[k]), (slot, k, got[k])
                else:
                    assert k in ignored.get(slot, ()) and not kinds.get(k), (slot, k)


# resolution
Q5 = DEVICE.qubits[5]
PARITY = ParityParams(df_mhz=0.4, f_upper_mhz=2651.2, cd_max_mhz=0.6, cd_period_mv=4.0)
Q5P = DEVICE.with_qubit(5, parity=PARITY).qubits[5]


def test_symmetric_ramsey_without_f_upper_raises():
    with pytest.raises(ValueError, match="f_upper_mhz"):
        R.modified_ramsey(df=1).arguments({}, Q5)
    with pytest.raises(ValueError, match="f_upper_mhz"):
        R.modified_ramsey(df=1, symmetric_ramsey=True).arguments({}, None)
    (mr,) = R.modified_ramsey(df=1, symmetric_ramsey=False).arguments({}, Q5)
    assert "f_ge" not in mr  # standard scheme: the run drives the qubit centre
    (mr,) = R.modified_ramsey(df=1, f_ge=3754.5).arguments({}, Q5)
    assert mr["f_ge"] == 3754.5 and mr["df"] == 1


def test_parity_values_resolve_from_the_qubit():
    (mr,) = R.modified_ramsey().arguments({}, Q5P)
    assert (mr["f_ge"], mr["df"]) == (2651.2, 0.4)
    assert (mr["mapping_p_e_state0"], mr["mapping_p_e_state1"]) == (0.1, 0.9)
    assert mr["mapping_probabilities_calibrated"] is False
    with pytest.raises(ValueError, match="df"):
        R.modified_ramsey(f_ge=1.0).arguments({}, Q5)
    mrc, _ = R.modified_ramsey_control().arguments({}, Q5P)
    assert (mrc["cd_max_mhz"], mrc["cd_period_mv"]) == (0.6, 4.0)
    assert "use_active_reset" not in mrc  # None: the run's default
    with pytest.raises(ValueError, match="cd_max_mhz"):
        R.modified_ramsey_control().arguments({}, Q5)
    cd, _ = R.charge_dispersion_quasicw().arguments({"spec": G.spec()}, Q5P)
    assert cd["probe_freq"] == 2651.2
    with pytest.raises(ValueError, match="probe_freq"):
        R.charge_dispersion_quasicw().arguments({"spec": G.spec()}, Q5)
    _, cdr = R.charge_dispersion_ramsey().arguments({"coherence": G.coherence()}, Q5)
    assert "df" not in cdr  # the run raises KeyError('df'), as the runner did
    _, cdr = R.charge_dispersion_ramsey().arguments({"coherence": G.coherence()}, Q5P)
    assert cdr["df"] == 0.4
    (rabi,) = R.amplitude_rabi().arguments({}, Q5)
    assert rabi["qubit_freq"] == Q5.freq
    with pytest.raises(ValueError, match="qubit_freq"):
        R.amplitude_rabi().arguments({}, None)
    assert R.charge_sweep().arguments({"spec": G.spec()}, Q5P)[1] == 4.0
    assert R.charge_sweep().arguments({"spec": G.spec()}, Q5)[1] is None
    (zsp,) = R.zero_span_parity().arguments({}, Q5P)
    cached = zsp["ZSP_ParityFreqs_Cached"]
    assert (cached["lower_peak_MHz"], cached["higher_peak_MHz"]) == (2651.2 - 0.4, 2651.2)
    assert R.zero_span_parity().params[ZSP]["ZSP_ParityFreqs_Cached"]["lower_peak_MHz"] is None


def test_modified_ramsey_control_with_a_ramsey_step():
    ramsey = R.modified_ramsey(df=0.5)  # symmetric_ramsey=True, no f_ge, no parity on Q5
    mrc, mr = R.modified_ramsey_control(cd_max_mhz=0.6, cd_period_mv=4.0, ramsey=ramsey).arguments(
        {}, Q5
    )
    assert mr["df"] == 0.5 and "f_ge" not in mr and mr["symmetric_ramsey"] is True
    assert mr is not ramsey.params["ModifiedRamsey_params"]
    assert "f_ge" not in run_reads("modified_ramsey_control", "ModifiedRamsey_params").at()
    _, mr = R.modified_ramsey_control(ramsey=R.modified_ramsey()).arguments({}, Q5P)
    assert mr["df"] == 0.4 and "f_ge" not in mr
    assert (mr["mapping_p_e_state0"], mr["mapping_p_e_state1"]) == (0.1, 0.9)
    with pytest.raises(ValueError, match="df"):
        R.modified_ramsey_control(
            cd_max_mhz=0.6, cd_period_mv=4.0, ramsey=R.modified_ramsey()
        ).arguments({}, Q5)


def test_spec_gain_resolves_from_the_qubit():
    assert G.spec()["gain"] is None and Q5.spec_gain is None
    q750 = DEVICE.with_qubit(5, spec_gain=750).qubits[5]
    group = G.spec()
    assert G.resolve({"spec": group}, Q5)["spec"]["gain"] == 800  # library value
    groups = G.resolve({"spec": group, "coherence": G.coherence()}, q750)
    assert groups["spec"]["gain"] == 750 and group["gain"] is None  # input untouched
    assert groups["coherence"] == G.coherence()
    assert G.resolve({"spec": G.spec(gain=600)}, q750)["spec"]["gain"] == 600  # group wins
    (spec,) = R.two_tone_spec().arguments(groups, q750)
    assert spec["gain"] == 750 and spec["qubit_gain"] == 1000  # base-config gain unchanged
    (spec,) = R.two_tone_spec(gain=900).arguments(groups, q750)
    assert spec["gain"] == 900  # step wins


def test_steps_fill_the_groups_themselves():
    # a library G.spec() handed straight to a Step never reaches the run as gain=None
    q750 = DEVICE.with_qubit(5, spec_gain=750).qubits[5]
    library = {"spec": G.spec(), "coherence": G.coherence()}
    assert R.two_tone_spec().arguments(library, q750)[0]["gain"] == 750
    assert R.two_tone_spec().arguments(library, Q5)[0]["gain"] == 800
    assert R.two_tone_spec().arguments(library)[0]["gain"] == 800  # no qubit: library value
    assert R.two_tone_spec().arguments({"spec": G.spec(gain=600)}, q750)[0]["gain"] == 600
    assert R.two_tone_spec(gain=900).arguments(library, q750)[0]["gain"] == 900
    assert library["spec"]["gain"] is None  # the session's group is not written to
    qubit = DEVICE.with_qubit(5, parity=PARITY, spec_gain=750).qubits[5]
    for name, recipe in R.STEPS.items():
        step = recipe()
        assert step.fill_groups is G.resolve, name
        args = step.arguments({g: G.BUILDERS[g]() for g in GROUPS}, qubit)
        for slot, arg in zip(step.needs, args):
            if slot == "spec":
                assert arg["gain"] is not None, name


def test_steps_registry_is_exported_from_runs():
    assert runs.STEPS is R.STEPS and "STEPS" not in runs.__all__  # star namespace unchanged


# keywords design.md calls device-dependent that would need sign-off to stay concrete
DEVICE_LIKE = re.compile(r"^(ss_)?voltage_(min|max)$|^(spec_)?gain$")


def test_device_like_library_values_are_the_documented_ones():
    found = {}
    for name, recipe in R.STEPS.items():
        for kw, p in inspect.signature(recipe).parameters.items():
            if DEVICE_LIKE.match(kw) and p.default is not None:
                found.setdefault(name, set()).add(kw)
        if name == "zero_span_parity":
            for key, default in R.ZSP_SUBDICTS["ZSP_ParitySpec_params"].items():
                if DEVICE_LIKE.match(key) and default is not None:
                    found.setdefault(name, set()).add(f"parity_spec.{key}")
    assert found == {s: set(kws) for s, kws in R.LIBRARY_DEVICE_VALUES.items()}
    assert all(why for kws in R.LIBRARY_DEVICE_VALUES.values() for why in kws.values())
    text = (REPO / "docs" / "running_a_session.md").read_text(encoding="utf-8")
    assert "LIBRARY_DEVICE_VALUES" in text
    for step, kws in R.LIBRARY_DEVICE_VALUES.items():
        row = next(line for line in text.splitlines() if line.startswith(f"| `{step}` |"))
        for kw in kws:
            assert kw.split(".")[-1] in row, (step, kw)


def test_precedence_library_group_step():
    groups = {"coherence": G.coherence(relax_delay=3000)}
    (args,) = R.t1().arguments(groups)
    assert args["relax_delay"] == 3000 and args["repetitions"] == G.coherence()["repetitions"]
    (args,) = R.t1(relax_delay=5000).arguments(groups)
    assert args["relax_delay"] == 5000 and groups["coherence"]["relax_delay"] == 3000
    assert "plotDisp" not in args  # None: run_t1's own rule (plot when repetitions <= 1)
    (args,) = R.t1(plot_disp=False).arguments(groups)
    assert args["plotDisp"] is False
    coh, echo = R.t1_t2e(relax_delay=10, t2e_relax_delay=20).arguments(
        {"coherence": G.coherence(), "echo": G.echo()}
    )
    assert (coh["relax_delay"], echo["relax_delay"]) == (10, 20)


def test_optional_keys_left_out_when_none():
    (us,) = R.undriven_single_shot(shots=None, relax_delay=None).arguments({})
    assert "Shots" not in us and "relax_delay" not in us  # inherit the single-shot cfg
    (arv,) = R.active_reset_verify().arguments({})
    assert "reset_read_latency_us" not in arv
    (arv,) = R.active_reset_verify(reset_read_latency_us=0.7).arguments({})
    assert arv["reset_read_latency_us"] == 0.7


def test_shared_charge_dispersion_dict_and_fresh_groups():
    quasicw = R.charge_dispersion_quasicw(probe_freq=1.0)
    shared = quasicw.params["ChargeDispersion_params"]
    two_tone = R.two_tone_charge_dispersion_quasicw(charge_dispersion=shared)
    spec = G.spec()
    _, spec_arg, out = two_tone.arguments({"spec": spec})
    assert out is shared and spec_arg is not spec
    out["probe_freq"] = 2.0  # what the two-tone run does
    cd, _ = quasicw.arguments({"spec": spec})
    assert cd["probe_freq"] == 2.0  # the legacy probe_freq hand-over (docs: known issues)


def test_interleave_uses_the_given_undriven_step():
    step = R.interleaved_coherence(undriven=R.undriven_single_shot(shots=10, repeat=5))
    il, us, *_ = step.arguments({g: {} for g in GROUPS})
    assert il == {"cycles": 1, "UndrivenSingleShot": True, "T1": True, "T2R": True, "T2E": False}
    assert (us["Shots"], us["Repeat"]) == (10, 5)


def test_step_validates_regime_and_slots():
    with pytest.raises(ValueError, match="regime"):
        Step("x", print, "C")
    with pytest.raises(ValueError, match="own slots"):
        Step("x", print, "A", needs=("own",))
    with pytest.raises(KeyError, match="coherence"):
        R.t1().arguments({})


# the frozen parameter fixture
def test_frozen_runner_text_is_intact_and_namespaces_are_fresh():
    assert F.blob_sha1() == F.BLOB_SHA1
    a, b = F.namespace(), F.namespace()
    assert a["T1T2_params"] == b["T1T2_params"] and a["T1T2_params"] is not b["T1T2_params"]
    assert set(F.GROUP_OF_DICT) <= set(a)
    flags = [flag for flag, _, _ in F.dispatches(a)]
    assert flags == list(F.STEP_OF_FLAG) and len(flags) == len(set(flags))
    args, kwargs = F.build_context_call(a)
    assert args[0] is a["Qubit_Parameters"]
    for legacy, group in F.GROUP_OF_DICT.items():
        if legacy in kwargs:
            assert kwargs[legacy] is a[legacy], group
    assert a["Qubit_Parameters"] == DEVICE.legacy_parameters()
