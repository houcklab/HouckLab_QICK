"""Invariants of the phase-3 symbol map. Needs only the legacy tree (git), never qicklab/."""

import ast
import re
from collections import Counter, defaultdict

import pytest

from tests.refactor import equivalence as eq
from tests.refactor.symbol_map import FILE_PHASE, KINDS, LAYOUT_MODULES, PHASES, SYMBOLS

PROOF_AST = re.compile(r"proof: AST-identical to (\S+?)(?=[\s;(]|$)(?!.*except)")
AUDIT_CITATION = re.compile(r"\.(md|json)\b|audit")


@pytest.fixture(scope="module")
def legacy(legacy_root):
    return eq.Tree("legacy", legacy_root)


def _legacy_keys(tree):
    return Counter(
        (m, k)
        for m in tree.legacy_modules()
        for k in [eq.MODULE_KEY] + [k for k, _ in eq.statement_keys(tree.parse(m))]
    )


def test_every_legacy_file_is_covered(legacy):
    files = set(legacy.legacy_modules())
    assert len(files) == 52
    assert {e.old_module for e in SYMBOLS} == files
    assert set(FILE_PHASE) == files


def test_every_legacy_symbol_appears_exactly_once(legacy):
    expected = _legacy_keys(legacy)
    got = Counter((e.old_module, e.old_qualname) for e in SYMBOLS)
    missing = sorted(set(expected) - set(got))
    stale = sorted(set(got) - set(expected))
    dups = sorted(k for k, n in got.items() if n > 1)
    assert not missing, f"legacy statements without an entry: {missing[:20]}"
    assert not stale, f"entries for statements that do not exist: {stale[:20]}"
    assert not dups, f"statements with several entries: {dups[:20]}"


def test_columns_are_well_formed():
    for e in SYMBOLS:
        assert e.kind in KINDS, e
        assert e.phase in PHASES, e
        assert e.old_module.startswith(eq.LEGACY_PREFIX), e
        if e.kind == "deleted":
            assert e.phase == "3b" and AUDIT_CITATION.search(e.note), (
                f"deletion needs a citation: {e}"
            )
        if e.kind == "merged":
            assert "proof:" in e.note, f"merge needs a proof: {e}"
            if e.phase != "3b":
                assert PROOF_AST.search(e.note), f"a 3a merge must be AST-identical: {e}"
        if e.kind == "main_to_test":
            assert e.new_module.startswith("tests."), e
        if e.kind in ("moved", "renamed", "main_to_test"):
            assert e.phase == FILE_PHASE[e.old_module], e
        if e.kind == "renamed":
            assert e.new_name != e.old_qualname, e
        if e.kind == "moved" and e.old_qualname != eq.MODULE_KEY:
            assert e.new_name == e.old_qualname, f"a name change is kind=renamed: {e}"


@pytest.mark.parametrize("stage", ["3a", "final"])
def test_no_two_symbols_share_a_destination(stage):
    groups = defaultdict(list)
    for e in SYMBOLS:
        if e.old_qualname == eq.MODULE_KEY:
            continue  # module headers are rewritten, not moved
        dest = (e.new_module, e.new_name)
        if stage == "final":
            if e.kind == "deleted":
                continue
            dest = (e.final_module or e.new_module, e.final_name or e.new_name)
        groups[dest].append(e)
    for dest, group in groups.items():
        owners = [e for e in group if not (e.kind == "merged" and "proof:" in e.note)]
        assert len(owners) <= 1, (
            f"{dest} claimed by {[(e.old_module, e.old_qualname) for e in owners]}"
        )


def test_destinations_are_in_the_design_layout():
    for e in SYMBOLS:
        assert e.new_module in LAYOUT_MODULES, e
        if e.final_module:
            assert e.final_module in LAYOUT_MODULES, e


def test_ast_identical_merge_proofs_hold(legacy):
    """Every 'proof: AST-identical to X' is re-checked on the legacy tree."""
    chk = eq.Checker(SYMBOLS, legacy, legacy, FILE_PHASE)
    checked = 0
    for e in SYMBOLS:
        m = PROOF_AST.search(e.note) if e.kind == "merged" else None
        if not m:
            continue
        mod, _, name = m.group(1).rpartition(".")
        a = chk.old.normalized(e.old_module, e.old_qualname, rename_to="_")
        b = chk.old.normalized(f"{eq.LEGACY_PREFIX}.{mod}", name, rename_to="_")
        assert b is not None, f"proof target {m.group(1)} not found"
        assert ast.dump(a) == ast.dump(b), f"{e.old_module}:{e.old_qualname} != {m.group(1)}"
        checked += 1
    assert checked >= 8
