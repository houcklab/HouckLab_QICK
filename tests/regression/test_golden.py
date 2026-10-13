"""Golden-master check: every runner flag must still send the same thing.

Regenerates the capture in memory with DRIVER, once per synthetic board
variant, and compares it, (variant, run label) by (variant, run label), with
golden_cstq03.json. Floats compare with a relative tolerance of 1e-9;
``traceback`` entries are diagnostic only and ignored. The golden records the
QICK version it was captured with; any other installed version fails loudly.

  REGRESSION_UPDATE=1          rewrite the golden from the current code
  REGRESSION_LABELS=RunT1,...  capture/compare only these labels (faster)
  REGRESSION_VARIANTS=A        capture/compare only these board variants
"""

import importlib
import json
import math
import os
from pathlib import Path

import pytest
from qick import get_version

from tests.regression import capture as core

DRIVER = "tests.regression.driver_qicklab"  # pre-refactor: tests.regression.driver_legacy
GOLDEN = Path(__file__).with_name("golden_cstq03.json")
META = "__meta__"
IGNORED_KEYS = frozenset({"traceback"})
REL_TOL = 1e-9
MAX_DIFF_LINES = 40

UPDATE = os.environ.get("REGRESSION_UPDATE") == "1"
ONLY = sorted(filter(None, os.environ.get("REGRESSION_LABELS", "").split(",")))
VARIANTS = tuple(
    filter(None, os.environ.get("REGRESSION_VARIANTS", ",".join(core.VARIANTS)).split(","))
)
GOLDEN_DATA = json.loads(GOLDEN.read_text(encoding="utf-8")) if GOLDEN.exists() else {}
GOLDEN_META = GOLDEN_DATA.get(META, {})
CASES = [
    (variant, label)
    for variant in GOLDEN_META.get("variants", [])
    for label in sorted(GOLDEN_DATA.get(variant, {}))
]


def _check_qick_version():
    golden = GOLDEN_META.get("qick")
    if golden is not None and golden != get_version():
        pytest.fail(
            f"installed qick {get_version()} != qick {golden} the golden was captured with. "
            "Compiled binaries depend on the QICK version: install the pinned version "
            "(pyproject.toml) or regenerate the golden on the LEGACY code deliberately.",
            pytrace=False,
        )


@pytest.fixture(scope="module")  # module, not session: the teardown below must run before other test modules
def capture():
    if not UPDATE:
        _check_qick_version()
    unknown = set(VARIANTS) - set(core.VARIANTS)
    if unknown:
        pytest.fail(f"unknown REGRESSION_VARIANTS {sorted(unknown)}", pytrace=False)
    driver = importlib.import_module(DRIVER)
    result = core.capture_variants(driver.capture_all, ONLY or None, VARIANTS)
    if UPDATE:
        merged = result
        if ONLY or set(VARIANTS) != set(core.VARIANTS):
            merged = {**GOLDEN_DATA, META: result[META]}
            merged[META]["variants"] = sorted(set(GOLDEN_META.get("variants", [])) | set(VARIANTS))
            for variant in VARIANTS:
                base = GOLDEN_DATA.get(variant, {}) if ONLY else {}
                merged[variant] = {**base, **result[variant]}
        text = json.dumps(merged, indent=2, sort_keys=True, allow_nan=True)
        GOLDEN.write_text(text + "\n", encoding="utf-8")
    yield result
    # Undo every patch (savefig/show/pause/sleep no-ops, virtual clock, proxy
    # fakes, experiment instrumentation) so later test modules in the same
    # process see the real library again.
    core._ACTIVE.undo()


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


def test_golden_meta():
    if UPDATE:
        pytest.skip("golden rewritten")
    if not GOLDEN_DATA:
        pytest.fail(f"{GOLDEN.name} missing; generate it with REGRESSION_UPDATE=1")
    assert GOLDEN_META.get("variants") == list(core.VARIANTS)
    _check_qick_version()


def test_run_labels_match(capture):
    if UPDATE or ONLY:
        pytest.skip("golden rewritten" if UPDATE else "label subset requested")
    for variant in VARIANTS:
        assert sorted(capture[variant]) == sorted(GOLDEN_DATA.get(variant, {})), variant


@pytest.mark.parametrize(
    ("variant", "label"),
    CASES or [("-", "<no golden: run with REGRESSION_UPDATE=1>")],
    ids=[f"{v}-{lab}" for v, lab in CASES] or None,
)
def test_run_matches_golden(variant, label, capture):
    if UPDATE:
        pytest.skip("golden rewritten")
    if variant not in GOLDEN_DATA:
        pytest.fail(f"{GOLDEN.name} missing; generate it with REGRESSION_UPDATE=1")
    if ONLY and label not in ONLY:
        pytest.skip("not in REGRESSION_LABELS")
    if variant not in VARIANTS:
        pytest.skip("not in REGRESSION_VARIANTS")
    assert label in capture[variant], f"driver produced no run labelled {label!r} on {variant}"
    diffs = list(_diff(GOLDEN_DATA[variant][label], capture[variant][label], f"{variant}:{label}"))
    shown = "\n".join(diffs[:MAX_DIFF_LINES])
    more = f"\n... and {len(diffs) - MAX_DIFF_LINES} more" if len(diffs) > MAX_DIFF_LINES else ""
    assert not diffs, f"{len(diffs)} difference(s) from golden:\n{shown}{more}"
