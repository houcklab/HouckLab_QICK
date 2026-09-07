import csv
import sys
import types

import pytest


qick = sys.modules.get("qick")
if qick is None:
    qick = types.ModuleType("qick")
    qick.AveragerProgram = type("AveragerProgram", (), {})
    qick.RAveragerProgram = type("RAveragerProgram", (), {})
    sys.modules["qick"] = qick

from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mT1VsFlux import (
    _append_csv_rows,
)


def test_wall_clock_csv_append_keeps_one_header_and_all_completed_rows(tmp_path):
    path = tmp_path / "wall_clock.csv"
    fieldnames = ["run", "value"]

    _append_csv_rows(path, fieldnames, [{"run": 0, "value": 1.5}])
    _append_csv_rows(path, fieldnames, [{"run": 1, "value": 2.5}])

    with path.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))
    assert rows == [
        {"run": "0", "value": "1.5"},
        {"run": "1", "value": "2.5"},
    ]
    assert path.read_text(encoding="utf-8").count("run,value") == 1
    assert not (tmp_path / "wall_clock.csv.lock").exists()


def test_wall_clock_csv_append_rejects_schema_changes(tmp_path):
    path = tmp_path / "wall_clock.csv"
    _append_csv_rows(path, ["run"], [{"run": 0}])

    with pytest.raises(ValueError, match="header"):
        _append_csv_rows(path, ["different"], [{"different": 1}])

    assert not (tmp_path / "wall_clock.csv.lock").exists()
