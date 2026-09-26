import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


MODULE = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSPumpProbeProtocolCheck"


def check():
    assert importlib.util.find_spec(MODULE) is not None, "protocol-check runner is missing"
    return importlib.import_module(MODULE)


def test_plan_brackets_short_sequence_with_shared_25us_measurement():
    check()
    result = subprocess.run([sys.executable, "-m", MODULE, "--plan"],
                            cwd=Path(__file__).resolve().parents[1],
                            text=True, capture_output=True, check=True)
    plan = json.loads(result.stdout)
    assert plan["hardware_access"] is False
    assert plan["frequency_count"] == 91
    assert plan["frequency_range_ghz"] == [4.080, 4.125]
    assert plan["reset_calibrations"] == 1
    delays = [a["delays_us"] for a in plan["arms"]]
    assert delays == [[25.0, 60.0, 100.0], [4.0, 8.0, 25.0], [25.0, 60.0, 100.0]]
    assert all(len(d) == 3 and 25.0 in d for d in delays)


def test_arm_execution_checkpoints_each_result_and_stops_on_failure(tmp_path):
    module = check()
    path = tmp_path / "manifest.json"
    manifest = {"status": "running", "arms": [dict(a, status="pending") for a in module.arms()]}
    calls = []

    def acquire(arm):
        calls.append(arm["name"])
        if len(calls) == 2:
            saved = json.loads(path.read_text())
            assert saved["arms"][0]["status"] == "complete"
            assert saved["arms"][0]["full_csv"] == "first.csv"
            assert saved["arms"][1]["status"] == "acquiring"
            raise RuntimeError("readout failed")
        return "first.csv"

    with pytest.raises(RuntimeError, match="readout failed"):
        module.collect_arms(manifest, path, acquire)
    saved = json.loads(path.read_text())
    assert len(calls) == 2
    assert saved["status"] == "failed"
    assert [a["status"] for a in saved["arms"]] == ["complete", "failed", "pending"]
    assert "readout failed" in saved["arms"][1]["error"]


def test_successful_execution_saves_distinct_outputs_in_planned_order(tmp_path):
    module = check()
    path = tmp_path / "manifest.json"
    manifest = {"status": "running", "arms": [dict(a, status="pending") for a in module.arms()]}
    module.collect_arms(manifest, path, lambda arm: f"{arm['name']}.csv")
    saved = json.loads(path.read_text())
    assert saved["status"] == "complete"
    assert len({a["full_csv"] for a in saved["arms"]}) == 3
    assert all(a["status"] == "complete" for a in saved["arms"])
