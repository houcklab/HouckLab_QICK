"""Every shipped template loads, resolves at every sweep point it would run, and compiles."""
from pathlib import Path

import pytest

from Bob.compiler.tlq_backend import compile_sequence
from Bob.config.snapshot import make_snapshot
from Bob.core.sequence import Sequence
from Bob.library import build_library

TEMPLATES = sorted((Path(build_library.__file__).parent / "templates").glob("*.json"))


def test_templates_are_current():
    for key, fn in build_library.TEMPLATES.items():
        on_disk = Sequence.load(Path(build_library.__file__).parent / "templates" / f"{key}.json").to_dict()
        fresh = fn().to_dict()
        # ids are random per build; compare structure

        def strip(d):
            return [{k: v for k, v in b.items() if k not in ("id", "segment")} for b in d["blocks"]]
        assert strip(on_disk) == strip(fresh), f"{key}.json is stale: run python -m Bob.library.build_library"


@pytest.mark.parametrize("path", TEMPLATES, ids=[p.stem for p in TEMPLATES])
def test_template_compiles_at_first_middle_last_point(path, station, calib):
    seq = Sequence.load(path)
    n = seq.settings.n_points()
    for k in sorted({0, n // 2, n - 1}):
        compiled, res, problems = compile_sequence(seq, station, calib, seq.settings.point(k), compensate=False)
        errors = [str(p) for p in problems if p.level == "error"]
        assert compiled is not None and not errors, (k, errors)
        assert compiled.n_samples % 16 == 0


def test_snapshot_has_every_point(station, calib):
    seq = Sequence.load(Path(build_library.__file__).parent / "templates" / "t1.json")
    snap = make_snapshot(seq, station, calib)
    assert len(snap["points"]) == seq.settings.n_points()
    assert snap["calibration"]["sha256"] == calib.sha256
