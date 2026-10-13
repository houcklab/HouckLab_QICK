"""Golden-master check: every runner flag must still send the same thing.

Regenerates the capture in memory with DRIVER and compares it, run label by run
label, with golden_cstq03.json. Floats compare with a relative tolerance of
1e-9; ``traceback`` entries are diagnostic only and ignored.

  REGRESSION_UPDATE=1          rewrite the golden from the current code
  REGRESSION_LABELS=RunT1,...  capture/compare only these labels (faster)
"""

import importlib
import json
import math
import os
from pathlib import Path

import pytest

DRIVER = "tests.regression.driver_legacy"  # post-refactor: tests.regression.driver_qicklab
GOLDEN = Path(__file__).with_name("golden_cstq03.json")
IGNORED_KEYS = frozenset({"traceback"})
REL_TOL = 1e-9
MAX_DIFF_LINES = 40

UPDATE = os.environ.get("REGRESSION_UPDATE") == "1"
ONLY = sorted(filter(None, os.environ.get("REGRESSION_LABELS", "").split(",")))
GOLDEN_DATA = json.loads(GOLDEN.read_text(encoding="utf-8")) if GOLDEN.exists() else {}


@pytest.fixture(scope="session")
def capture():
    result = importlib.import_module(DRIVER).capture_all(ONLY or None)
    if UPDATE:
        merged = {**GOLDEN_DATA, **result} if ONLY else result
        text = json.dumps(merged, indent=2, sort_keys=True, allow_nan=True)
        GOLDEN.write_text(text + "\n", encoding="utf-8")
    return result


def _diff(expected, actual, path):
    """Yield one human-readable line per mismatch."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            if key in IGNORED_KEYS:
                continue
            if key not in actual:
                yield f"{path}.{key}: missing (golden={_short(expected[key])})"
            elif key not in expected:
                yield f"{path}.{key}: unexpected (actual={_short(actual[key])})"
            else:
                yield from _diff(expected[key], actual[key], f"{path}.{key}")
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            yield f"{path}: length {len(expected)} -> {len(actual)}"
        for i, (e, a) in enumerate(zip(expected, actual, strict=False)):
            yield from _diff(e, a, f"{path}[{i}]")
    elif isinstance(expected, float) and isinstance(actual, float):  # int vs float stays strict
        if not (
            math.isclose(expected, actual, rel_tol=REL_TOL, abs_tol=1e-12)
            or (math.isnan(expected) and math.isnan(actual))
        ):
            yield f"{path}: {expected!r} -> {actual!r}"
    elif expected != actual or type(expected) is not type(actual):
        yield f"{path}: {_short(expected)} -> {_short(actual)}"


def _short(x, n=120):
    text = json.dumps(x, sort_keys=True, allow_nan=True)
    return text if len(text) <= n else text[: n - 3] + "..."


def test_run_labels_match(capture):
    if UPDATE or ONLY:
        pytest.skip("golden rewritten" if UPDATE else "label subset requested")
    assert sorted(capture) == sorted(GOLDEN_DATA)


@pytest.mark.parametrize(
    "label", sorted(GOLDEN_DATA) or ["<no golden: run with REGRESSION_UPDATE=1>"]
)
def test_run_matches_golden(label, capture):
    if UPDATE:
        pytest.skip("golden rewritten")
    if label not in GOLDEN_DATA:
        pytest.fail(f"{GOLDEN.name} missing; generate it with REGRESSION_UPDATE=1")
    if ONLY and label not in ONLY:
        pytest.skip("not in REGRESSION_LABELS")
    assert label in capture, f"driver produced no run labelled {label!r}"
    diffs = list(_diff(GOLDEN_DATA[label], capture[label], label))
    shown = "\n".join(diffs[:MAX_DIFF_LINES])
    more = f"\n... and {len(diffs) - MAX_DIFF_LINES} more" if len(diffs) > MAX_DIFF_LINES else ""
    assert not diffs, f"{len(diffs)} difference(s) from golden:\n{shown}{more}"
