"""Phase-3a equivalence gate. The ledger runs always; the old-vs-new check once qicklab/ exists.

Set REFACTOR_PHASE=3a-i or 3a-ii to require every entry of that phase to be in place.
"""

import os
import subprocess
import sys

import pytest

from tests.refactor import equivalence as eq
from tests.refactor.symbol_map import FILE_PHASE, SYMBOLS

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
def test_qicklab_is_equivalent_to_legacy():
    phase = os.environ.get("REFACTOR_PHASE")
    code, out = _run(*(["--phase", phase] if phase else []))
    assert code == 0, out


@pytest.mark.slow
def test_checker_self_test():
    """Identity mapping passes; a changed constant and an import-only re-binding both fail."""
    code, out = _run("--self-test")
    assert code == 0, out
    assert "[identity]" in out and "SELF-TEST: PASS" in out
