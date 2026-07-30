import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    *[".."] * 4))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from WorkingProjects.TLS_Spectroscopy.Client_modules.Tests import reset_sim

reset_sim.install_stubs()

import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset as ar
from WorkingProjects.TLS_Spectroscopy.Client_modules.Tests.test_active_reset_rot import (
    MockProgram, interpret)

ROT = {"c_int": 100, "s_int": 0, "excite_threshold": 1000.0, "max_iters": 3}


def test_rot_reset_in_cfg_routes_to_the_rotated_block():
    prog = MockProgram(max_iters=3)
    prog.cfg["rot_reset"] = dict(ROT)
    ar.active_reset_block(prog, ro_ch=0, threshold_raw=5, oper="lower",
                          ground_below=False, max_iters=3, read_delay_us=None)
    opers = [op[1] for op in prog.asm if op[0] == "read"]
    assert opers.count("lower") == 3 and opers.count("upper") == 3
    assert any(op[0] == "mathi" for op in prog.asm)
    n, _ = interpret(prog.asm, [(50, 0)] * 3, 100, 0)
    assert n == 3


def test_without_rot_reset_fails_closed():
    prog = MockProgram(max_iters=3)
    with pytest.raises(RuntimeError, match=r"validated cfg\['rot_reset'\]"):
        ar.active_reset_block(prog, ro_ch=0, threshold_raw=5, oper="lower",
                              ground_below=False, max_iters=3, read_delay_us=None)


def test_diagnostics_can_explicitly_request_the_legacy_block():
    prog = MockProgram(max_iters=3)
    ar.active_reset_block(prog, ro_ch=0, threshold_raw=5, oper="lower",
                          ground_below=False, max_iters=3, read_delay_us=None,
                          allow_legacy=True)
    opers = [op[1] for op in prog.asm if op[0] == "read"]
    assert opers.count("lower") == 3 and opers.count("upper") == 0
    assert not any(op[0] == "mathi" for op in prog.asm)


def test_both_paths_emit_one_measure_per_iteration():
    for with_rot in (False, True):
        prog = MockProgram(max_iters=3)
        if with_rot:
            prog.cfg["rot_reset"] = dict(ROT)
        ar.active_reset_block(prog, ro_ch=0, threshold_raw=5, oper="lower",
                              ground_below=False, max_iters=3, read_delay_us=None,
                              allow_legacy=not with_rot)
        assert sum(1 for op in prog.asm if op[0] == "measure") == 3


def test_incomplete_rot_reset_fails_loudly_instead_of_running_legacy():
    prog = MockProgram(max_iters=3)
    prog.cfg["rot_reset"] = {"c_int": 100}
    with pytest.raises(ValueError, match="missing"):
        ar.active_reset_block(prog, ro_ch=0, threshold_raw=5, oper="lower",
                              ground_below=False, max_iters=3, read_delay_us=None)


def test_rot_reset_max_iters_overrides_the_call_site():
    prog = MockProgram(max_iters=3)
    prog.cfg["rot_reset"] = dict(ROT, max_iters=2)
    ar.active_reset_block(prog, ro_ch=0, threshold_raw=5, oper="lower",
                          ground_below=False, max_iters=3, read_delay_us=None)
    assert sum(1 for op in prog.asm if op[0] == "measure") == 2


def test_bench_patch_context_still_composes_with_native_dispatch():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import (
        mResetBench as bench)
    with bench.patched_production_reset():
        prog = MockProgram(max_iters=3)
        prog.cfg["rot_reset"] = dict(ROT)
        ar.active_reset_block(prog, ro_ch=0, threshold_raw=5, oper="lower",
                              ground_below=False, max_iters=3, read_delay_us=None)
        opers = [op[1] for op in prog.asm if op[0] == "read"]
        assert opers.count("upper") == 3
