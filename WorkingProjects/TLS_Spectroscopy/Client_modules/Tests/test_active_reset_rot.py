import numpy as np
import pytest

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset as ar
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset_rot as rot


def blobs(seed=0, ig=3726, qg=791, ie=4095, qe=-18944, sigma=2500, sigma_e=None,
          n=4000):
    rng = np.random.default_rng(seed)
    se = sigma if sigma_e is None else sigma_e
    return (rng.normal(ig, sigma, n), rng.normal(qg, sigma, n),
            rng.normal(ie, se, n), rng.normal(qe, se, n))


def realistic_blobs(seed=0, n=20000):
    """Overlap matched to the measured q4 readout: P(e|g)~0.07, P(g|e)~0.21.

    The excited blob is the wider one -- T1 decay during the 20 us readout drags a
    tail of |e> shots back toward |g>, which is why the two error rates differ.
    """
    return blobs(seed=seed, sigma=6800, sigma_e=9500, n=n)


def test_projection_angle_points_from_ground_to_excited():
    lg, ug, le, ue = blobs()
    theta = rot.projection_angle(lg, ug, le, ue)
    _, c, s = rot.fixed_point_coeffs(theta, np.max(np.abs(np.concatenate([lg, ug, le, ue]))))
    assert np.median(rot.project(le, ue, c, s)) > np.median(rot.project(lg, ug, c, s))


@pytest.mark.parametrize("theta", np.linspace(-np.pi, np.pi, 37))
@pytest.mark.parametrize("max_abs", [1e3, 2e4, 1e5, 1e6, 5e6])
def test_fixed_point_never_overflows_int32(theta, max_abs):
    shift, c, s = rot.fixed_point_coeffs(theta, max_abs)
    worst_term = max(abs(c), abs(s)) * max_abs
    assert worst_term <= rot.INT32_MAX, "a single mathi product overflows"
    ok, worst = rot.check_headroom(shift, theta, max_abs)
    assert ok, f"projection plus latch sink overflows: {worst:.3e}"
    assert worst <= rot.INT32_MAX


@pytest.mark.parametrize("theta", np.linspace(-np.pi, np.pi, 17))
def test_latch_sink_always_drives_below_any_in_range_threshold(theta):
    max_abs = 2e4
    shift, c, s = rot.fixed_point_coeffs(theta, max_abs)
    sink = rot.latch_offset(shift, theta, max_abs)
    worst_proj = rot.max_projection(shift, theta, max_abs)
    assert worst_proj + sink < -worst_proj, (
        "a latched shot must land below every reachable projection value, otherwise "
        "the latch can be escaped by a noisy read")


def test_fixed_point_matches_float_projection():
    lg, ug, le, ue = blobs()
    theta = rot.projection_angle(lg, ug, le, ue)
    max_abs = float(np.max(np.abs(np.concatenate([lg, ug, le, ue]))))
    shift, c, s = rot.fixed_point_coeffs(theta, max_abs)
    exact = np.cos(theta) * le + np.sin(theta) * ue
    fixed = rot.project(le, ue, c, s) / (2.0 ** shift)
    assert np.max(np.abs(exact - fixed)) < 1e-2 * np.std(exact)


def test_rotation_beats_the_best_single_quadrature_when_blobs_are_diagonal():
    lg, ug, le, ue = blobs(ig=0, qg=0, ie=10000, qe=10000, sigma=1500)
    rep = rot.separation_report(lg, ug, le, ue)
    assert rep["gain_vs_best_single"] > 1.3, rep
    assert rep["sep_rotated"] > rep["sep_lower"] and rep["sep_rotated"] > rep["sep_upper"]


def test_rotation_matches_single_quadrature_when_already_aligned():
    lg, ug, le, ue = blobs(ig=0, qg=0, ie=0, qe=20000, sigma=1500)
    rep = rot.separation_report(lg, ug, le, ue)
    assert 0.97 < rep["gain_vs_best_single"] < 1.03, rep


def test_choose_thresholds_orders_the_three_zones():
    lg, ug, le, ue = realistic_blobs()
    rep = rot.separation_report(lg, ug, le, ue)
    thr = rot.choose_thresholds(rep["proj_g"], rep["proj_e"])
    assert thr["ground_threshold"] <= thr["excite_threshold"]
    assert 0.0 <= thr["floor"] <= 1.0
    assert thr["p_latch_given_g"] > thr["p_latch_given_e"]


def test_realistic_blobs_reproduce_the_measured_error_rates():
    lg, ug, le, ue = realistic_blobs()
    rep = rot.separation_report(lg, ug, le, ue)
    thr = rot.choose_thresholds(rep["proj_g"], rep["proj_e"])
    assert 0.02 < thr["p_e_given_g"] < 0.15, thr
    assert 0.10 < thr["p_g_given_e"] < 0.35, thr
    assert 0.02 < thr["floor"] < 0.25, thr


@pytest.mark.parametrize("peg,pge", [(0.073, 0.208), (0.02, 0.05), (0.198, 0.334)])
@pytest.mark.parametrize("iters", [1, 3, 5, 8])
def test_no_latch_chain_reduces_exactly_to_the_existing_two_zone_model(peg, pge, iters):
    b_g, b_e = peg, 1.0 - pge
    ref_e, ref_g = ar.predicted_residuals(peg, pge, 0.8, iters)
    assert rot.simulate_reset(0, b_g, 0, b_e, 0.8, iters, "e") == pytest.approx(ref_e, abs=1e-12)
    assert rot.simulate_reset(0, b_g, 0, b_e, 0.8, iters, "g") == pytest.approx(ref_g, abs=1e-12)


def test_three_zone_never_loses_to_two_zone():
    lg, ug, le, ue = realistic_blobs()
    rep = rot.separation_report(lg, ug, le, ue)
    two = rot.choose_thresholds(rep["proj_g"], rep["proj_e"], iters=3, three_zone=False)
    three = rot.choose_thresholds(rep["proj_g"], rep["proj_e"], iters=3, three_zone=True)
    assert three["predicted_worst"] <= two["predicted_worst"] + 1e-12


def test_latch_helps_the_ground_branch_at_a_matched_excite_threshold():
    """The optimizer minimises max(r_g, r_e) and may trade the |g> branch away, so the
    latch's own effect is only visible with the excite threshold held fixed."""
    lg, ug, le, ue = realistic_blobs()
    rep = rot.separation_report(lg, ug, le, ue)
    two = rot.choose_thresholds(rep["proj_g"], rep["proj_e"], iters=3, three_zone=False)
    thr = two["excite_threshold"]
    b_g = float(np.mean(rep["proj_g"] >= thr))
    b_e = float(np.mean(rep["proj_e"] >= thr))
    plain = rot.simulate_reset(0.0, b_g, 0.0, b_e, 0.8, 3, "g")
    ground_thr = float(np.quantile(rep["proj_g"], 0.5))
    a_g = float(np.mean(rep["proj_g"] < ground_thr))
    a_e = float(np.mean(rep["proj_e"] < ground_thr))
    latched = rot.simulate_reset(a_g, b_g, a_e, b_e, 0.8, 3, "g")
    assert latched < plain, (
        f"the latch exists to stop later iterations spuriously re-exciting a qubit that "
        f"already reached |g>: {latched:.5f} should beat {plain:.5f}")


def test_latch_gain_is_modest_because_the_excited_branch_dominates():
    """Guards the claim in ResetRotationDev: the latch is a small win, not a large one.

    The worst case is set by the |e> branch, which the latch cannot help -- so anyone
    reading a big improvement off hardware should suspect the measurement, not cheer.
    """
    lg, ug, le, ue = realistic_blobs()
    rep = rot.separation_report(lg, ug, le, ue)
    two = rot.choose_thresholds(rep["proj_g"], rep["proj_e"], iters=3, three_zone=False)
    three = rot.choose_thresholds(rep["proj_g"], rep["proj_e"], iters=3, three_zone=True)
    assert 1.0 <= two["predicted_worst"] / three["predicted_worst"] < 1.5


def test_rotation_is_immune_to_readout_phase_while_one_quadrature_is_not():
    lg, ug, le, ue = realistic_blobs()
    worst_rot, worst_single = [], []
    for deg in (0, 15, 30, 45, 60, 75, 90):
        th = np.deg2rad(deg)
        c, s = np.cos(th), np.sin(th)
        lg2, ug2 = c * lg - s * ug, s * lg + c * ug
        le2, ue2 = c * le - s * ue, s * le + c * ue
        rep = rot.separation_report(lg2, ug2, le2, ue2)
        use_lower = rep["sep_lower"] >= rep["sep_upper"]
        g1, e1 = (lg2, le2) if use_lower else (ug2, ue2)
        if np.median(e1) < np.median(g1):
            g1, e1 = -g1, -e1
        worst_single.append(
            rot.choose_thresholds(g1, e1, iters=3, three_zone=False)["predicted_worst"])
        worst_rot.append(
            rot.choose_thresholds(rep["proj_g"], rep["proj_e"], iters=3)["predicted_worst"])
    assert max(worst_rot) - min(worst_rot) < 0.01, (
        f"the rotated scheme must not care about readout phase: {worst_rot}")
    assert max(worst_single) > 1.3 * min(worst_single), (
        f"the single-quadrature scheme should degrade badly near 45 deg: {worst_single}")


def test_fixed_point_coeffs_rejects_nonsense_scale():
    for bad in (0.0, -1.0, np.nan, np.inf):
        with pytest.raises(ValueError):
            rot.fixed_point_coeffs(0.3, bad)


def test_scratch_registers_are_distinct():
    regs = rot.scratch_registers()
    assert len(set(regs.values())) == len(regs)
    assert 0 not in regs.values()


class MockProgram:
    """Records the emitted tProc instruction stream so it can be interpreted."""

    pulse_registers = ("freq", "phase", "addr", "gain", "mode", "t")

    def __init__(self, max_iters=3):
        self.asm = []
        self.cfg = {"res_ch": 0, "qubit_ch": 1, "adc_trig_offset": 0.5,
                    "reset_thermalization_us": 2.0, "reset_max_iters": max_iters,
                    "reset_read_delay_us": None}
        self.soccfg = {"readouts": [{"tproc_ch": 0, "tproc_ctrl": 1}],
                       "gens": [{"tproc_ch": 1}]}
        self._adc_ts = [100]
        self._dac_ts = [100]

    def ch_page(self, ch):
        return 1

    def _ch_page_tproc(self, ch):
        return 1

    def _sreg_tproc(self, ch, name):
        return 21 + self.pulse_registers.index(name)

    def us2cycles(self, us, **kw):
        return int(round(float(us) * 100))

    def cycles2us(self, c):
        return float(c) / 100.0

    def _rec(self, *op):
        self.asm.append(op)

    def measure(self, **kw):
        self._rec("measure")

    def waiti(self, *a):
        self._rec("waiti", *a)

    def read(self, ch, page, oper, reg):
        self._rec("read", oper, reg)

    def mathi(self, page, dst, src, op, imm):
        self._rec("mathi", dst, src, op, int(imm))

    def math(self, page, dst, a, op, b):
        self._rec("math", dst, a, op, b)

    def regwi(self, page, reg, val, comment=""):
        self._rec("regwi", reg, int(val))

    def memwi(self, page, reg, addr):
        self._rec("memwi", reg, addr)

    def condj(self, page, a, op, b, label):
        self._rec("condj", a, op, b, label)

    def label(self, name):
        self._rec("label", name)

    def pulse(self, ch=None):
        self._rec("pulse")

    def sync_all(self, *a):
        self._rec("sync")


def interpret(asm, reads, c_int, s_int):
    """Run the recorded stream against a list of (lower, upper) reads per iteration.

    Returns (n_pi_fired, latched_after) so the control flow can be asserted.
    """
    regs = {}
    labels = {op[1]: i for i, op in enumerate(asm) if op[0] == "label"}
    pc, read_idx, n_pi = 0, 0, 0
    ops = {'+': lambda x, y: x + y, '*': lambda x, y: x * y,
           '-': lambda x, y: x - y}
    cmp_ = {'<': lambda x, y: x < y, '>': lambda x, y: x > y,
            '>=': lambda x, y: x >= y, '<=': lambda x, y: x <= y,
            '==': lambda x, y: x == y, '!=': lambda x, y: x != y}
    guard = 0
    while pc < len(asm):
        guard += 1
        assert guard < 10000, "runaway program"
        op = asm[pc]
        k = op[0]
        if k == "read":
            lo, up = reads[min(read_idx, len(reads) - 1)]
            regs[op[2]] = lo if op[1] == "lower" else up
            if op[1] == "upper":
                read_idx += 1
        elif k == "mathi":
            regs[op[1]] = ops[op[3]](regs.get(op[2], 0), op[4])
        elif k == "math":
            regs[op[1]] = ops[op[3]](regs.get(op[2], 0), regs.get(op[4], 0))
        elif k == "regwi":
            regs[op[1]] = op[2]
        elif k == "condj":
            if cmp_[op[2]](regs.get(op[1], 0), regs.get(op[3], 0)):
                pc = labels[op[4]]
        elif k == "pulse":
            n_pi += 1
        pc += 1
    return n_pi, regs


def build(max_iters=3, three_zone=True, use_latch=True, excite=1000, ground=-1000,
          sink=-10 ** 9, c_int=100, s_int=0):
    prog = MockProgram(max_iters=max_iters)
    rot.active_reset_rot_block(
        prog, ro_ch=0, c_int=c_int, s_int=s_int, excite_threshold=excite,
        ground_threshold=ground if three_zone else None,
        latch_sink=sink if use_latch else None, max_iters=max_iters,
        three_zone=three_zone, use_latch=use_latch, read_delay_us=None)
    return prog.asm


def test_asm_three_zone_fires_pi_only_when_confidently_excited():
    asm = build()
    # projection = 100 * lower; excite at 1000, ground at -1000
    n, _ = interpret(asm, [(50, 0)] * 3, 100, 0)      # +5000 -> excited every round
    assert n == 3
    n, _ = interpret(asm, [(0, 0)] * 3, 100, 0)       # 0 -> ambiguous, never fires
    assert n == 0
    n, _ = interpret(asm, [(-50, 0)] * 3, 100, 0)     # -5000 -> confidently ground
    assert n == 0


def test_asm_latch_stops_later_spurious_excitation():
    """Confident ground on round 1, then two noisy reads that would fire the pi."""
    asm = build(use_latch=True)
    n, _ = interpret(asm, [(-50, 0), (50, 0), (50, 0)], 100, 0)
    assert n == 0, "latched shot must never fire the pi again"


def test_asm_without_latch_the_spurious_pi_does_fire():
    asm = build(three_zone=True, use_latch=False)
    n, _ = interpret(asm, [(-50, 0), (50, 0), (50, 0)], 100, 0)
    assert n == 2, "without the latch the two noisy reads each fire -- this is the bug"


def test_asm_two_zone_matches_a_plain_threshold():
    asm = build(three_zone=False, use_latch=False)
    n, _ = interpret(asm, [(50, 0), (-50, 0), (50, 0)], 100, 0)
    assert n == 2


def test_asm_emits_one_measure_per_iteration_regardless_of_branch():
    """qick allocates the readout buffer for a FIXED trigger count per program, so a
    conditionally-skipped measurement would corrupt every shot, not just that one."""
    for iters in (1, 3, 5):
        asm = build(max_iters=iters)
        assert sum(1 for op in asm if op[0] == "measure") == iters


def test_asm_uses_both_accumulator_halves():
    asm = build()
    opers = [op[1] for op in asm if op[0] == "read"]
    assert opers.count("lower") == 3 and opers.count("upper") == 3


def test_asm_rejects_register_collision_with_pulse_registers():
    prog = MockProgram()
    with pytest.raises(ValueError):
        rot.active_reset_rot_block(
            prog, ro_ch=0, c_int=1, s_int=0, excite_threshold=10, ground_threshold=0,
            latch_sink=-10 ** 9, regs={"reg_i": 21, "reg_q": 2, "reg_ground": 3,
                                       "reg_excite": 4, "reg_latch": 5},
            read_delay_us=None)


def test_block_rejects_latch_without_three_zones():
    prog = MockProgram()
    with pytest.raises(ValueError, match="three_zone"):
        rot.active_reset_rot_block(prog, ro_ch=0, c_int=1, s_int=0, excite_threshold=10,
                                   three_zone=False, use_latch=True, read_delay_us=None)


def test_block_rejects_inverted_zone_order():
    prog = MockProgram()
    with pytest.raises(ValueError, match="ground_threshold"):
        rot.active_reset_rot_block(prog, ro_ch=0, c_int=1, s_int=0, excite_threshold=10,
                                   ground_threshold=99, latch_sink=-10 ** 9,
                                   read_delay_us=None)
