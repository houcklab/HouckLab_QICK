"""The parameter registry (qicklab.core.params) against the code and the regression golden.

Runtime enforcement (design.md "Parameter registry (phase 6)"): (a) every cfg key the golden's
recording dict saw an experiment class read or write (both boards) is registered under the cfg
scope family with that class in read_by, and read_by lists exactly the recording classes;
every key of a saved cfg in the golden (experiments[].cfg) is registered, and the ones no class
reads (outside the UNRECORDED_CFG allowlist) are exactly RECORD_ONLY_CFG;
(b) every recipe keyword (and zero_span_parity dict key) and every session-group keyword is
registered under recipe:<step> / session:<group>; (c) every device-model field is registered
under device; (d) units are set on every entry; (e) nothing is registered that none of these
sources has, except the cited UNRECORDED_CFG allowlist. The golden's shape is pinned (both
boards, every label that ran an experiment records it), so a renamed field cannot leave these
checks with an empty source. Experiment classes no label builds (UNREACHED_CLASSES) are checked
against the AST instead. The AST scan of literal cfg subscripts under qicklab/experiments,
qicklab/analysis and qicklab/runs is a lint: it warns, it does not fail.
"""

import ast
import dataclasses
import inspect
import json
import re
import warnings
from collections import defaultdict
from functools import cache
from pathlib import Path

import pytest

from qicklab.core import device as D
from qicklab.core import params as P
from qicklab.core.session import GROUPS, Session
from qicklab.runs import STEPS
from qicklab.runs import groups as G
from qicklab.runs import recipes as R

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "tests" / "regression" / "golden_cstq03.json"
REGRESSION_README = REPO / "tests" / "regression" / "README.md"
EXPERIMENTS = REPO / "qicklab" / "experiments"
ANALYSIS = REPO / "qicklab" / "analysis"
RUNS = REPO / "qicklab" / "runs"
RUNS_MRC = REPO / "qicklab" / "runs" / "modified_ramsey.py"
# every dataclass qicklab.core.device defines, so a new one cannot go unchecked
DEVICE_CLASSES = tuple(
    sorted(
        (
            c
            for c in vars(D).values()
            if isinstance(c, type) and dataclasses.is_dataclass(c) and c.__module__ == D.__name__
        ),
        key=lambda c: c.__name__,
    )
)


@cache
def golden():
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def _labels():
    for variant in golden()["__meta__"]["variants"]:
        yield from golden()[variant].values()


@cache
def golden_access():
    """{cfg key: {class that read or wrote it}} over every label of both boards."""
    out = defaultdict(set)
    for label in _labels():
        for cls, access in label["cfg_access"].items():
            for key in (*access["read"], *access["written"]):
                out[key].add(cls)
    return dict(out)


def _cfg_keys_in(tree, is_cfg=None):
    """[(key, node)] for every literal cfg key in `tree` (see literal_cfg_keys)."""
    is_cfg = is_cfg or _is_cfg
    out = []
    for node in ast.walk(tree):
        key = None
        if isinstance(node, ast.Subscript) and is_cfg(node.value):
            key = _literal(node.slice)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("get", "setdefault", "pop")
            and is_cfg(node.func.value)
            and node.args
        ):
            key = _literal(node.args[0])
        elif (
            isinstance(node, ast.Compare)
            and any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops)
            and any(is_cfg(c) for c in node.comparators)
        ):
            key = _literal(node.left)
        if key is not None:
            out.append((key, node))
    return out


def _is_cfg(node):
    return (isinstance(node, ast.Name) and node.id == "cfg") or (
        isinstance(node, ast.Attribute) and node.attr == "cfg"
    )


def _is_run_cfg(node):
    """cfg, x.cfg, or a cfg dict the run functions build (zsp_cfg, mr_cfg, spec_cfg, ...)."""
    return _is_cfg(node) or (isinstance(node, ast.Name) and node.id.endswith("_cfg"))


def _literal(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


@cache
def literal_cfg_keys():
    """{key: {"file.py:line", ...}} for cfg["k"], self.cfg["k"], cfg.get / setdefault / pop("k")
    and "k" in cfg under qicklab/experiments and qicklab/analysis (the analysis functions take
    the experiment's cfg, e.g. classify_thermal_tail), and under qicklab/runs, where the cfg
    dicts the run functions build for the saved record (zsp_cfg, mr_cfg, ...) count too."""
    found = defaultdict(set)
    trees = {path: (tree, _is_cfg) for path, tree in _experiment_modules().items()}
    for folder, is_cfg in ((ANALYSIS, _is_cfg), (RUNS, _is_run_cfg)):
        for path in sorted(folder.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            trees[path] = (tree, is_cfg)
    for path, (tree, is_cfg) in trees.items():
        for key, node in _cfg_keys_in(tree, is_cfg):
            found[key].add(f"{path.name}:{node.lineno}")
    return dict(found)


@cache
def _experiment_modules():
    return {
        path: ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for path in sorted(EXPERIMENTS.glob("*.py"))
    }


@cache
def experiment_classes():
    """{class name: (file name, ClassDef)} for every top-level class under qicklab/experiments."""
    out = {}
    for path, tree in _experiment_modules().items():
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                assert node.name not in out, node.name
                out[node.name] = (path.name, node)
    return out


def _keys(scope):
    return {p.key for p in P.entries(scope=scope)}


@cache
def golden_saved():
    """{cfg key: {class whose saved cfg holds it}} over every label of both boards."""
    out = defaultdict(set)
    for label in _labels():
        for exp in label["experiments"]:
            for key in exp["cfg"]:
                out[key].add(exp["cls"])
    return dict(out)


# (a) the golden's recorded cfg access -------------------------------------------------------


def test_the_golden_sources_are_not_empty():
    """Both boards, and every label that built an experiment records its cfg access and its
    saved cfg, so tests (a) and the record-only check cannot pass on an empty source."""
    assert sorted(golden()["__meta__"]["variants"]) == ["A", "B"]
    for variant in golden()["__meta__"]["variants"]:
        labels = golden()[variant]
        assert labels, variant
        for name, label in labels.items():
            built = {exp["cls"] for exp in label["experiments"]}
            assert set(label["cfg_access"]) == built, (variant, name)
            for cls, access in label["cfg_access"].items():
                assert access["read"] or access["written"], (variant, name, cls)
            for exp in label["experiments"]:
                assert exp["cfg"], (variant, name, exp["cls"])
            if not built:
                assert label["outcome"]["status"] == "raised", (variant, name)
        assert sum(bool(label["experiments"]) for label in labels.values()) > len(labels) // 2
    assert golden_access() and golden_saved()


def test_every_recorded_cfg_key_is_registered_with_its_classes():
    problems = []
    for key, recorded in sorted(golden_access().items()):
        found = [p for p in P.cfg_entries(key) if (p.key, p.scope) not in P.UNRECORDED_CFG]
        if not found:
            problems.append(f"{key}: recorded by {sorted(recorded)}, not in PARAMS (scope cfg)")
            continue
        every = [cls for p in found for cls in p.read_by]
        twice = sorted({c for c in every if every.count(c) > 1})
        if twice:
            problems.append(f"{key}: {twice} in the read_by of more than one cfg entry")
        # classes no label builds are listed from the code (test_unreached_classes_*)
        listed = [cls for cls in every if cls not in P.UNREACHED_CLASSES]
        if set(listed) != recorded:
            problems.append(
                f"{key}: read_by {sorted(set(listed))} != recorded {sorted(recorded)} "
                f"(missing {sorted(recorded - set(listed))}, "
                f"extra {sorted(set(listed) - recorded)})"
            )
    assert not problems, "\n".join(problems)


def test_every_saved_cfg_key_is_registered():
    registered = {p.key for p in P.entries("cfg")}
    missing = {k: sorted(v) for k, v in golden_saved().items() if k not in registered}
    assert not missing, f"saved cfg keys not in PARAMS (scope cfg): {missing}"


def test_record_only_cfg_is_the_saved_keys_no_class_reads():
    allowlisted = {key for key, _ in P.UNRECORDED_CFG}
    assert not P.RECORD_ONLY_CFG & allowlisted
    unread = set(golden_saved()) - set(golden_access()) - allowlisted
    assert P.RECORD_ONLY_CFG == unread, (
        f"missing {sorted(unread - P.RECORD_ONLY_CFG)}, extra {sorted(P.RECORD_ONLY_CFG - unread)}"
    )
    for key in P.RECORD_ONLY_CFG:
        assert [p.scope for p in P.cfg_entries(key)] == ["cfg"], key


def test_unreached_classes_are_the_experiment_classes_no_label_builds():
    """Every ExperimentClass under qicklab/experiments is either recorded by the golden or
    listed in UNREACHED_CLASSES (with its file and program class); never both."""
    recorded = {cls for classes in golden_access().values() for cls in classes}
    classes = experiment_classes()
    experiment = {
        name
        for name, (_, node) in classes.items()
        if any(isinstance(b, ast.Name) and b.id == "ExperimentClass" for b in node.bases)
    }
    assert recorded <= experiment, sorted(recorded - experiment)
    assert not recorded & set(P.UNREACHED_CLASSES), sorted(recorded & set(P.UNREACHED_CLASSES))
    assert experiment == recorded | set(P.UNREACHED_CLASSES), (
        f"neither recorded nor UNREACHED_CLASSES: {sorted(experiment - recorded)}; "
        f"listed but not an ExperimentClass: {sorted(set(P.UNREACHED_CLASSES) - experiment)}"
    )
    for cls, (file, program, why) in P.UNREACHED_CLASSES.items():
        assert classes[cls][0] == file and classes[program][0] == file, (cls, program, file)
        assert why.strip(), cls


@pytest.mark.parametrize("cls", sorted(P.UNREACHED_CLASSES))
def test_unreached_classes_name_the_keys_they_read(cls):
    """Every literal cfg key of the class and its program is a cfg entry naming the class, in
    one meaning only."""
    _, program, _ = P.UNREACHED_CLASSES[cls]
    keys = {
        key for name in (cls, program) for key, _ in _cfg_keys_in(experiment_classes()[name][1])
    }
    named = [p for p in P.entries("cfg") if cls in p.read_by]
    listed = [p.key for p in named]
    assert keys <= set(listed), f"not listed: {sorted(keys - set(listed))}"
    assert len(listed) == len(set(listed)), sorted({k for k in listed if listed.count(k) > 1})
    assert len(listed) > len(keys) // 2


def test_unrecorded_cfg_allowlist_is_cited_and_true():
    recorded = golden_access()
    scan = literal_cfg_keys()
    problems = []
    for (key, scope), citation in sorted(P.UNRECORDED_CFG.items()):
        entry = P.PARAMS.get((key, scope))
        if entry is None or P.scope_family(scope) != "cfg":
            problems.append(f"{(key, scope)}: allowlisted but not a cfg entry of PARAMS")
            continue
        overlap = set(entry.read_by) & recorded.get(key, set())
        if overlap:
            problems.append(f"{(key, scope)}: the golden records it for {sorted(overlap)}")
        files = set(re.findall(r"(\w+\.py)", citation))
        seen = {loc.split(":")[0] for loc in scan.get(key, ())}
        if not files or not files <= seen:
            problems.append(
                f"{(key, scope)}: cites {sorted(files)}, the AST lint finds it in {sorted(seen)}"
            )
    assert not problems, "\n".join(problems)


# (b) recipes, groups, Session ---------------------------------------------------------------


def _zsp_dict_keys():
    return {
        f"{kw}.{key}"
        for legacy, kw in R._ZSP_KEYS
        if legacy in R.ZSP_SUBDICTS
        for key in R.ZSP_SUBDICTS[legacy]
    }


def test_step_functions_match_the_recipes():
    assert set(P.STEP_FUNCTIONS) == set(STEPS)
    for step, recipe in R._RECIPES.items():
        assert P.STEP_FUNCTIONS[step] == recipe.fn.__name__, step


@pytest.mark.parametrize("step", sorted(STEPS))
def test_every_recipe_keyword_is_registered(step):
    keywords = set(inspect.signature(STEPS[step]).parameters)
    expected = keywords | (_zsp_dict_keys() if step == "zero_span_parity" else set())
    registered = _keys(f"recipe:{step}")
    assert registered == expected, (
        f"missing {sorted(expected - registered)}, unused {sorted(registered - expected)}"
    )
    for p in P.entries(scope=f"recipe:{step}"):
        assert p.read_by == (P.STEP_FUNCTIONS[step],), p


def test_recipe_side_tables_name_registered_keywords():
    for table in (R.FROZEN_DIFFERENCES, R.LIBRARY_DEVICE_VALUES):
        for step, keywords in table.items():
            for kw in keywords:
                assert (kw, f"recipe:{step}") in P.PARAMS, (step, kw)


@pytest.mark.parametrize("group", sorted(G.BUILDERS))
def test_every_group_keyword_is_registered(group):
    keywords = set(inspect.signature(G.BUILDERS[group]).parameters)
    registered = _keys(f"session:{group}")
    assert registered == keywords, (
        f"missing {sorted(keywords - registered)}, unused {sorted(registered - keywords)}"
    )
    for kw in G.FROZEN_DIFFERENCES.get(group, {}):
        assert kw in registered, (group, kw)


def test_session_scopes_are_the_groups_and_the_session_fields():
    assert set(G.BUILDERS) == set(GROUPS)
    scopes = {p.scope for p in P.entries("session")}
    assert scopes == {"session"} | {f"session:{g}" for g in GROUPS}
    fields = {f.name for f in dataclasses.fields(Session)} - set(GROUPS)
    assert _keys("session") == fields


# (c) the device model -----------------------------------------------------------------------


def test_every_device_field_is_registered():
    expected = {
        f"{cls.__name__}.{f.name}" for cls in DEVICE_CLASSES for f in dataclasses.fields(cls)
    }
    registered = _keys("device")
    assert registered == expected, (
        f"missing {sorted(expected - registered)}, unused {sorted(registered - expected)}"
    )
    assert {p.scope for p in P.entries("device")} == {"device"}


# (d) entry hygiene --------------------------------------------------------------------------


def test_every_entry_has_units_meaning_and_layer():
    for (key, scope), p in P.PARAMS.items():
        assert (p.key, p.scope) == (key, scope)
        assert p.units and all(u.strip() in P.UNITS for u in p.units.split(",")), p
        assert p.meaning.strip(), p
        assert p.layer in P.LAYERS, p
        assert P.scope_family(scope) in P.SCOPE_FAMILIES, p
        assert isinstance(p.read_by, tuple), p


def test_code_facing_entries_name_their_readers():
    for p in P.PARAMS.values():
        if P.scope_family(p.scope) in ("cfg", "recipe") or p.scope.startswith("session:"):
            assert p.read_by, p


# (e) nothing unused; dead keys stay out; double meanings split -------------------------------


def test_no_cfg_entry_without_a_source():
    recorded, saved = golden_access(), golden_saved()
    for p in P.entries("cfg"):
        assert p.key in recorded or p.key in saved or (p.key, p.scope) in P.UNRECORDED_CFG, (
            f"{(p.key, p.scope)}: no golden record and not in UNRECORDED_CFG"
        )


def _dead_keys():
    text = REGRESSION_README.read_text(encoding="utf-8")
    section = text.split("## Allowed cfg diffs", 1)[1].split("\n## ", 1)[0]
    keys = set()
    for line in section.splitlines():
        if line.startswith("| `"):
            keys |= set(re.findall(r"`([^`]+)`", line.split("|")[1]))
    return keys


def test_dead_keys_stay_out():
    dead = _dead_keys()
    assert dead >= {"pulse_style", "start_ts_gain", "end_ts_gain", "ts_step"}
    assert not dead & {p.key for p in P.PARAMS.values()}


# A cfg key that means two things: {key: {scope: (units, classes that must read it there)}}.
# The scopes must be exactly the key's cfg-family scopes, so merging two meanings into one
# entry (or moving a class to the wrong meaning) fails; test (a) checks the rest of read_by.
DOUBLE_MEANINGS = {
    "qubit_gain": {
        "cfg": ("DAC units", {"QubitSpecSliceFF", "ConstantTwoTone"}),
        "cfg:single_shot": ("DAC units", {"SingleShotProgramFFMUX"}),
        "cfg:zero_span": ("DAC units", {"ZeroSpanParity"}),
        "cfg:rabi": ("DAC units", {"AmplitudeRabiFF_N"}),
    },
    "reps": {
        "cfg": ("shots", {"T1FF", "QubitSpecSliceFF", "AmplitudeRabiFF_N", "ChargeDispersion"}),
        "cfg:single_shot": ("shots", {"SingleShotProgramFFMUX", "T1_SS", "ModifiedRamsey"}),
    },
    "start": {
        "cfg": ("MHz", {"QubitSpecSliceFF"}),
        "cfg:gain_sweep": ("DAC units", {"AmplitudeRabiFF"}),
        "cfg:wait_sweep": ("us", {"T1FF", "T2R"}),
    },
    "step": {
        "cfg": ("MHz", {"QubitSpecSliceFF"}),
        "cfg:gain_sweep": ("DAC units", {"AmplitudeRabiFF"}),
        "cfg:wait_sweep": ("us", {"T1FF", "T2R"}),
    },
    "Qubit_number": {
        "cfg": ("index", {"T1FF"}),
        "cfg:rabi": ("index", {"AmplitudeRabiFF_N"}),
    },
    "f_ge": {
        "cfg": ("MHz", {"T1FF", "SingleShotProgramFFMUX"}),
        "cfg:modified_ramsey": ("MHz", {"ModifiedRamsey"}),
    },
}


@pytest.mark.parametrize("key", sorted(DOUBLE_MEANINGS))
def test_double_meaning_cfg_keys_split_by_class(key):
    wanted = DOUBLE_MEANINGS[key]
    found = {p.scope: p for p in P.cfg_entries(key)}
    assert set(found) == set(wanted), (key, sorted(found))
    for scope, (units, classes) in wanted.items():
        p = found[scope]
        assert p.units == units, (key, scope, p.units)
        assert classes <= set(p.read_by), (key, scope, sorted(classes - set(p.read_by)))
    readers = [set(p.read_by) for p in found.values()]
    for i, a in enumerate(readers):
        for b in readers[i + 1 :]:
            assert not a & b, (key, sorted(a & b))
    meanings = [p.meaning for p in found.values()]
    assert len(set(meanings)) == len(meanings), (key, meanings)


def test_mr_relax_delay_is_not_relax_delay():
    """The Modified Ramsey program waits mr_relax_delay; relax_delay is the other programs'."""
    for step in ("modified_ramsey", "modified_ramsey_control"):
        assert ("mr_relax_delay", f"recipe:{step}") in P.PARAMS, step
    assert ("relax_delay", "recipe:modified_ramsey") not in P.PARAMS
    assert "ModifiedRamsey" in P.PARAMS[("mr_relax_delay", "cfg")].read_by
    assert "ModifiedRamsey" not in {c for p in P.cfg_entries("relax_delay") for c in p.read_by}
    assert "relax_delay" in P.PARAMS[("mr_relax_delay", "recipe:modified_ramsey")].notes


def test_spec_steps_play_the_spec_gain_not_qubit_gain():
    """session:spec has two gains: qubit_gain (the regime-A base config) and gain (what the
    spectroscopy steps play); the steps inherit gain, and qubit_gain's notes say so."""
    assert "`gain`" in P.PARAMS[("qubit_gain", "session:spec")].notes
    for step in ("two_tone_spec", "trans_qubit_spec", "charge_sweep", "charge_dispersion_quasicw"):
        assert ("qubit_gain", f"recipe:{step}") not in P.PARAMS, step
        assert P.PARAMS[("gain", f"recipe:{step}")].notes == "None: the spec group's gain", step


def _mrc_sweet_params():
    """{find_sweet_spot key: legacy ModifiedRamsey_Control_params key} from the literal
    sweet_params_mrc dict of run_modified_ramsey_control."""
    tree = ast.parse(RUNS_MRC.read_text(encoding="utf-8"), filename=str(RUNS_MRC))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "sweet_params_mrc" for t in node.targets)
            and isinstance(node.value, ast.Dict)
        ):
            out = {}
            for k, v in zip(node.value.keys, node.value.values, strict=True):
                if isinstance(v, ast.Subscript):
                    out[_literal(k)] = _literal(v.slice)
                elif isinstance(v, ast.Call) and v.args:
                    out[_literal(k)] = _literal(v.args[0])
            return out
    raise AssertionError("sweet_params_mrc not found in qicklab/runs/modified_ramsey.py")


def test_mrc_search_keywords_are_the_sweet_spot_walk():
    """modified_ramsey_control's search keywords fill auto_coherence's find_sweet_spot slots:
    each has that slot's units, and the ss_* ones cite it (MRC df is the Strategy-A trigger,
    not two_tone_charge_dispersion_quasicw's accepted separation)."""
    legacy_to_kw = dict(R._MRC_OWN)
    mapping = _mrc_sweet_params()
    assert {"ss_search_df_trigger", "ss_accept_sep", "ss_dV"} <= set(mapping)
    for slot, legacy in sorted(mapping.items()):
        kw = legacy_to_kw[legacy]
        ac_kw = slot if (slot, "recipe:auto_coherence") in P.PARAMS else slot.lower()
        ac = P.PARAMS[(ac_kw, "recipe:auto_coherence")]
        mrc = P.PARAMS[(kw, "recipe:modified_ramsey_control")]
        assert mrc.units == ac.units, (kw, mrc.units, ac_kw, ac.units)
        if slot.startswith("ss_"):
            assert f"auto_coherence {ac_kw}" in mrc.notes, (kw, mrc.notes)
    mrc_df = P.PARAMS[("df", "recipe:modified_ramsey_control")]
    assert mrc_df.meaning != P.PARAMS[("df", "recipe:two_tone_charge_dispersion_quasicw")].meaning
    assert "trigger" in mrc_df.meaning


# lint ---------------------------------------------------------------------------------------


def test_literal_cfg_subscripts_lint():
    """Report (warn, never fail) literal cfg keys of the scanned modules missing from PARAMS."""
    registered = {p.key for p in P.entries("cfg")}
    missing = {k: v for k, v in literal_cfg_keys().items() if k not in registered}
    if missing:
        report = "\n".join(f"  {k}: {', '.join(sorted(v)[:3])}" for k, v in sorted(missing.items()))
        warnings.warn(
            "literal cfg keys under qicklab/experiments, qicklab/analysis, qicklab/runs not in "
            f"PARAMS:\n{report}",
            stacklevel=1,
        )
