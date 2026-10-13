"""Phase-3a equivalence gate. The ledger runs always; the old-vs-new check once qicklab/ exists.

CURRENT_PHASE is the phase the tree is in (bumped by the refactor commits: 3a-i -> 3a-ii ->
3b -> 3b-done); REFACTOR_PHASE overrides it. In 3a-* every entry of that phase must be in
place (AST + bindings) and later phases are skipped. In "3b" bodies change on purpose, so only
the structural check runs (every moved/merged symbol present, nothing bound twice); a 3b
deletion that has not happened yet ("should be deleted") is reported but allowed, one area at
a time. "3b-done" makes those pending deletions failures too.
"""

import json
import os
import subprocess
import sys

import pytest

from tests.refactor import equivalence as eq
from tests.refactor.symbol_map import FILE_PHASE, SYMBOLS

CURRENT_PHASE = "3b"
HAS_QICKLAB = (eq.REPO / "qicklab").is_dir()


def _run(*args):
    proc = subprocess.run(
        [sys.executable, "-m", "tests.refactor.equivalence", *args],
        cwd=eq.REPO,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    return proc.returncode, proc.stdout + proc.stderr


def test_ledger_accounts_for_every_legacy_statement(legacy_root):
    chk = eq.Checker(SYMBOLS, eq.Tree("legacy", legacy_root), eq.Tree("new", eq.REPO), FILE_PHASE)
    fails = [f for f in chk.run(ledger_only=True) if f.status == "FAIL"]
    assert not fails, "\n".join(f"{f.where}: {f.detail}" for f in fails)


@pytest.mark.skipif(not HAS_QICKLAB, reason="phase 3a not reached: qicklab/ does not exist yet")
def test_qicklab_is_equivalent_to_legacy(tmp_path):
    phase = os.environ.get("REFACTOR_PHASE", CURRENT_PHASE)
    cli_phase = "3b" if phase == "3b-done" else phase
    out_json = tmp_path / "findings.json"
    code, out = _run(*(["--phase", cli_phase] if cli_phase else []), "--json", str(out_json))
    findings = json.loads(out_json.read_text(encoding="utf-8"))
    pending = [
        f
        for f in findings
        if f["status"] == "FAIL"
        and f["check"] == "structure"
        and f["detail"] == "should be deleted"
    ]
    fails = [f for f in findings if f["status"] == "FAIL" and (phase != "3b" or f not in pending)]
    if phase == "3b" and pending:
        print(f"{len(pending)} 3b deletions still pending (allowed while CURRENT_PHASE == '3b')")
    assert not fails, out
    assert (code == 0) == (not [f for f in findings if f["status"] == "FAIL"])


@pytest.mark.slow
def test_checker_self_test():
    """Identity mapping passes; a changed constant and an import-only re-binding both fail.

    Runs against a copy of the legacy worktree, so it stays valid while the legacy files
    leave the working tree during 3a.
    """
    code, out = _run("--self-test")
    assert code == 0, out
    assert "[identity]" in out and "SELF-TEST: PASS" in out
