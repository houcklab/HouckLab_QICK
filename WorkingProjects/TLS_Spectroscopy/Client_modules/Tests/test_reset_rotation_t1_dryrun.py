import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DRYRUN = os.path.join(HERE, "dryrun_reset_rotation_t1.py")
REPO = os.path.abspath(os.path.join(HERE, *[".."] * 4))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from WorkingProjects.TLS_Spectroscopy.Client_modules.Tests import reset_sim

reset_sim.install_stubs()

from WorkingProjects.TLS_Spectroscopy.Client_modules.Tests.test_active_reset_rot import (
    MockProgram)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset as ar
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import mResetBench as bench


@pytest.fixture(scope="module", params=[7, 3])
def out(request):
    env = dict(os.environ, PYTHONPATH=REPO, RESET_SIM_SEED=str(request.param))
    p = subprocess.run([sys.executable, DRYRUN], capture_output=True, text=True,
                       env=env, timeout=900)
    assert p.returncode == 0, (f"seed {request.param}: exit {p.returncode}\n"
                               f"{p.stdout[-3000:]}\n{p.stderr[-3000:]}")
    assert "DRY RUN COMPLETED WITHOUT ERROR" in p.stdout
    return p.stdout


def test_no_register_collision_ever_occurred(out):
    assert "collision" not in out
    assert "REGISTER PRESSURE FAILURE" not in out


def test_per_dc_mean_t1_is_near_the_simulated_truth_in_both_arms(out):
    rows = re.findall(r"legacy T1 =\s+([\d.]+) \+/-\s+[\d.]+ us \| "
                      r"rot T1 =\s+([\d.]+)", out)
    assert len(rows) == 3, f"expected one analysis row per dc point, got {rows}"
    for leg, rot in rows:
        for arm, v in (("legacy", float(leg)), ("rot", float(rot))):
            assert 60.0 < v < 260.0, (
                f"{arm} mean T1 = {v} us is outside 60..260 us; the simulated truth "
                f"is 150 us and the 3-point window reads it slightly low, so a value "
                f"out here means the estimator or the reset chain is broken")


def test_all_four_replacement_criteria_pass(out):
    assert out.count("[PASS]") == 4, out[out.find("VERDICT"):][:1500]
    assert "[FAIL]" not in out
    for marker in ("every 3-point fit valid", "no systematic T1 shift",
                   "reset floor no worse than legacy", "rotated block built and ran"):
        assert re.search(r"\[PASS\][^\n]*" + re.escape(marker), out), marker
    assert "Part B passes." in out


def test_enough_interleaved_pass_rows_were_printed(out):
    rows = re.findall(r"pass \d+/\d+\s+(legacy|rot)\s+dc\s+\d+", out)
    assert len(rows) >= 4, rows
    assert "legacy" in rows and "rot" in rows


def test_every_fit_was_valid_and_contrast_was_healthy(out):
    m = re.search(r"(\d+)/(\d+) valid estimates", out)
    assert m and m.group(1) == m.group(2)
    for c in re.findall(r"contrast (\d\.\d+)", out):
        assert float(c) > 0.4


def _spy(calls):
    def spy(prog, **kw):
        calls.append((prog, kw))
    return spy


def test_dispatcher_routes_a_legacy_cfg_to_the_original_block(monkeypatch):
    calls = []
    monkeypatch.setattr(ar, "active_reset_block", _spy(calls))
    prog = MockProgram()
    assert "rot_reset" not in prog.cfg
    with bench.patched_production_reset():
        ar.active_reset_block(prog, ro_ch=0, threshold_raw=5, oper="lower",
                              ground_below=False, max_iters=3)
    assert len(calls) == 1
    assert calls[0][0] is prog
    assert calls[0][1] == {"ro_ch": 0, "threshold_raw": 5, "oper": "lower",
                           "ground_below": False, "max_iters": 3}
    assert not prog.asm
    ar.active_reset_block(prog, ro_ch=0, threshold_raw=5, oper="lower",
                          ground_below=False, max_iters=3)
    assert len(calls) == 2, "exiting the context must restore the patched original"


def test_dispatcher_routes_a_rot_reset_cfg_to_the_rotated_block(monkeypatch):
    calls = []
    monkeypatch.setattr(ar, "active_reset_block", _spy(calls))
    prog = MockProgram()
    prog.cfg["rot_reset"] = dict(c_int=100, s_int=0, excite_threshold=1000,
                                 max_iters=3)
    with bench.patched_production_reset():
        ar.active_reset_block(prog, ro_ch=0, threshold_raw=5, oper="lower",
                              ground_below=False, max_iters=3)
    assert not calls, "the legacy block must NOT run when cfg['rot_reset'] is set"
    opers = [op[1] for op in prog.asm if op[0] == "read"]
    assert opers.count("lower") == 3 and opers.count("upper") == 3, opers
    assert sum(1 for op in prog.asm if op[0] == "measure") == 3
    assert sum(1 for op in prog.asm if op[0] == "pulse") == 3
