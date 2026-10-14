"""Pin the schedule / readout-window numbers of the legacy tProc programs.

No hardware: every program is compiled against capture.FakeSocCfg, once per
synthetic board variant (A: gen fabric clock = tProc clock, readout i on tProc
input i; B: gen fabric 614.4 MHz != tProc 430.08 MHz, readout i on tProc input
i + 2). The integers below were obtained from the pre-refactor code; the
refactor (shared readout/reset/schedule helpers) must reproduce them exactly.
"""

import pytest

from tests.regression import capture


@pytest.fixture(scope="module")
def legacy():
    import importlib

    def get(module, name):
        return getattr(importlib.import_module(module), name)

    return {
        "BaseConfig": get("qicklab.hardware.board", "BaseConfig"),
        "MR": get("qicklab.experiments.modified_ramsey", "ModifiedRamseyProgram"),
        "US": get("qicklab.experiments.undriven_single_shot", "UndrivenSingleShotProgram"),
        "SS": get("qicklab.experiments.single_shot", "SingleShotProgram"),
        "ARV": get("qicklab.experiments.active_reset_verify", "ActiveResetVerifyProgram"),
        "T1": get("qicklab.experiments.t1", "T1Program"),
    }


def _cfg(base, **overrides):
    """A CSTQ03-like regime-A cfg: 15 us window, 0.3 us ADC offset, Q5 values."""
    cfg = dict(base)
    cfg.update(
        {
            "length": 15.3,
            "readout_length": 15.0,
            "adc_trig_offset": 0.3,
            "pulse_freq": 7095.4,
            "pulse_gain": 1500,
            "f_ge": 2651.0,
            "sigma": 0.08,
            "qubit_gain": 4200,
            "pi_gain": 4200,
            "pi2_gain": 2100,
            "flattop_length": None,
            "relax_delay": 300,
            "reps": 1000,
            "rounds": 1,
            "shots": 1000,
            "Pulse": True,
            "number_of_pulses": 1,
        }
    )
    cfg.update(overrides)
    return cfg


MR_PARAMS = {
    "df": 1.0,
    "mr_relax_delay": 500.0,
    "symmetric_ramsey": True,
    "max_drive_bandwidth_ratio": 1.4,
    "readout_threshold": 0.0,
    "reset_readout_relax_delay": 5.0,
    "post_reset_wait": 0.0,
}
T1_PARAMS = {"start": 0, "step": 5.0, "expts": 100}

# (use_active_reset, reset_cycles) -> scheduled rep period [tProc cycles]
MR_PERIOD = {
    "A": {(False, 1): 221996, (True, 1): 230865, (True, 2): 239734},
    "B": {(False, 1): 221993, (True, 1): 230860, (True, 2): 239727},
}
US_PERIOD = {"A": 135605, "B": 135604}
# readout_window_cycles[0], readout_tone_cycles, extension, adc_trig_offset_cycles
READOUT = {"A": (4608, 6581, 1, 129), "B": (4608, 9401, 1, 129)}
BINPROG_LEN = {
    "A": {"T1": 37, "MR_no_reset": 41, "MR_reset": 62},
    "B": {"T1": 39, "MR_no_reset": 41, "MR_reset": 61},
}
# tProc input channel of the active-reset `read` instruction. Both resolve the
# readout's tproc_ch through the shared ActiveResetMixin (ARV used to pass the
# readout index, so board B read input 0).
READ_INPUT = {"A": {"MR": 0, "ARV": 0}, "B": {"MR": 2, "ARV": 2}}
# int(end of the reset readout window) [tProc cycles]: the waiti immediate the
# pre-fix measure(wait=True) emitted before the reset `read`. 129 + 15 us * 430.08 MHz.
RESET_RO_END = {"A": 6580, "B": 6580}
# The reset-read waiti immediate: RESET_RO_END + us2cycles(0.5 us read-latency floor).
# Was 6580 (no stall past the window) before the read-latency fix.
RESET_READ_WAITI = {"A": 6795, "B": 6795}


@pytest.fixture(params=capture.VARIANTS)
def board(request):
    return request.param, capture.FakeSocCfg(request.param)


def _mr(legacy, soccfg, use_active_reset, reset_cycles=1):
    cfg = _cfg(
        legacy["BaseConfig"],
        **MR_PARAMS,
        use_active_reset=use_active_reset,
        reset_cycles=reset_cycles,
    )
    return legacy["MR"](soccfg, cfg)


def _readout(prog):
    return (
        prog.readout_window_cycles[0],
        prog.readout_tone_cycles,
        getattr(prog, "readout_tone_extension_cycles", None),
        prog.adc_trig_offset_cycles,
    )


def _reads(prog):
    return [inst["args"][0] for inst in prog.prog_list if inst["name"] == "read"]


@pytest.mark.parametrize(("use_active_reset", "reset_cycles"), [(False, 1), (True, 1), (True, 2)])
def test_modified_ramsey_rep_period(legacy, board, use_active_reset, reset_cycles):
    variant, soccfg = board
    prog = _mr(legacy, soccfg, use_active_reset, reset_cycles)
    assert (
        prog.scheduled_rep_period_cycles() == MR_PERIOD[variant][(use_active_reset, reset_cycles)]
    )


def test_undriven_rep_period(legacy, board):
    variant, soccfg = board
    prog = legacy["US"](soccfg, _cfg(legacy["BaseConfig"]))
    assert prog.scheduled_rep_period_cycles() == US_PERIOD[variant]


def test_undriven_rejects_register_sync(legacy, board):
    _, soccfg = board
    prog = legacy["US"](soccfg, _cfg(legacy["BaseConfig"]))
    end = next(i for i, inst in enumerate(prog.prog_list) if inst["name"] == "loopnz")
    prog.prog_list.insert(end, {"name": "sync", "args": (1, 3)})
    with pytest.raises(RuntimeError, match="register-based sync"):
        prog.scheduled_rep_period_cycles()


def test_readout_windows(legacy, board):
    variant, soccfg = board
    base = legacy["BaseConfig"]
    window, tone, extension, offset = READOUT[variant]
    progs = {
        "SS": legacy["SS"](soccfg, _cfg(base)),
        "MR": _mr(legacy, soccfg, True),
        "ARV": legacy["ARV"](
            soccfg, _cfg(base, use_active_reset=True, readout_threshold=0.0, prep_excited=True)
        ),
        "US": legacy["US"](soccfg, _cfg(base)),
    }
    for name, prog in progs.items():
        expected = (window, tone, None if name == "US" else extension, offset)
        assert _readout(prog) == expected, name


def test_gen_clock_changes_readout_tone(legacy):
    tones = {
        v: legacy["SS"](capture.FakeSocCfg(v), _cfg(legacy["BaseConfig"])).readout_tone_cycles
        for v in capture.VARIANTS
    }
    assert tones["A"] != tones["B"], tones


def test_binprog_length(legacy, board):
    variant, soccfg = board
    t1 = legacy["T1"](soccfg, _cfg(legacy["BaseConfig"], **T1_PARAMS))
    lengths = {
        "T1": len(t1.binprog),
        "MR_no_reset": len(_mr(legacy, soccfg, False).binprog),
        "MR_reset": len(_mr(legacy, soccfg, True).binprog),
    }
    assert lengths == BINPROG_LEN[variant]


def test_active_reset_read_channel_and_offset(legacy, board):
    variant, soccfg = board
    mr = _mr(legacy, soccfg, True)
    arv = legacy["ARV"](
        soccfg, _cfg(legacy["BaseConfig"], use_active_reset=True, readout_threshold=0.0)
    )
    assert set(_reads(mr)) == {READ_INPUT[variant]["MR"]}
    assert set(_reads(arv)) == {READ_INPUT[variant]["ARV"]}
    assert mr.cmp_offset == mr.readout_window_cycles[0] << 15
    assert arv.cmp_offset == arv.readout_window_cycles[0] << 15 == 4608 << 15


def _insts(prog, name, reg=None):
    return [
        inst["args"]
        for inst in prog.prog_list
        if inst["name"] == name and (reg is None or inst["args"][1] == reg)
    ]


def test_active_reset_verify_offset_is_sign_safe(legacy, board):
    """ARV's comparison offset must exceed the largest |raw I| (ro_norm * 2^15); the old
    fixed 2^24 did not for a 15 us window, so negative-I shots wrapped."""
    _, soccfg = board
    arv = legacy["ARV"](
        soccfg, _cfg(legacy["BaseConfig"], use_active_reset=True, readout_threshold=-4000.0)
    )
    ro_norm = arv.readout_window_cycles[0]
    raw_threshold = round(-4000.0 * ro_norm)
    assert arv.cmp_offset >= ro_norm * 2**15
    assert _insts(arv, "regwi", arv.r_thresh) == [(arv.q_rp, 5, raw_threshold + arv.cmp_offset)]
    assert raw_threshold + arv.cmp_offset > 0
    assert _insts(arv, "mathi", arv.r_read) == [(arv.q_rp, 4, 4, "+", arv.cmp_offset)]


@pytest.mark.parametrize("force_pi", [False, True])
def test_active_reset_verify_uses_shared_reset(legacy, board, force_pi):
    """ARV runs the mixin's reset block; reset_force_pi only drops the condj."""
    _, soccfg = board
    arv = legacy["ARV"](
        soccfg,
        _cfg(
            legacy["BaseConfig"],
            use_active_reset=True,
            readout_threshold=0.0,
            reset_cycles=2,
            reset_force_pi=force_pi,
        ),
    )
    labels = [inst["label"] for inst in arv.prog_list if "label" in inst]
    assert {"RESET_DONE_0", "RESET_DONE_1"} <= set(labels)
    assert not any(lab.startswith("VRESET") for lab in labels)
    expected = [] if force_pi else [(1, 4, "<", 5, "RESET_DONE_%d" % i) for i in range(2)]
    assert _insts(arv, "condj") == expected
    assert len(_reads(arv)) == 2
    assert len(_insts(_mr(legacy, soccfg, True), "condj")) == 1


def test_reset_threshold_above_2_30_uses_safe_regwi(legacy):
    """A ~104 us window with a large positive threshold puts raw_threshold + cmp_offset
    above 2^30, which a plain regwi immediate cannot load: it must go through
    safe_regwi (regwi imm>>2, bitwi <<2, + imm%4) and reconstruct exactly."""
    arv = legacy["ARV"](
        capture.FakeSocCfg("A"),
        _cfg(
            legacy["BaseConfig"],
            length=104.3,
            readout_length=104.0,
            use_active_reset=True,
            readout_threshold=1000.0,
        ),
    )
    target = round(1000.0 * arv.readout_window_cycles[0]) + arv.cmp_offset
    assert arv.cmp_offset < 2**30 <= target
    writes = [
        inst
        for inst in arv.prog_list
        if inst["name"] in ("regwi", "bitwi", "mathi") and inst["args"][1] == arv.r_thresh
    ]
    assert writes[0]["name"] == "regwi" and abs(writes[0]["args"][2]) < 2**30
    assert writes[1]["name"] == "bitwi" and writes[1]["args"][3:] == ("<<", 2)
    value = writes[0]["args"][2] << 2
    if len(writes) > 2:
        assert writes[2]["name"] == "mathi" and writes[2]["args"][3] == "+"
        value += writes[2]["args"][4]
    assert value == target


def _reset_read_stalls(prog):
    """(waiti immediates, instruction names) between each reset ADC trigger and its `read`."""
    insts = prog.prog_list
    out = []
    for i, inst in enumerate(insts):
        if inst["name"] != "read":
            continue
        trig = max(j for j in range(i) if insts[j]["name"] == "seti")  # ADC trigger
        names = [x["name"] for x in insts[trig + 1 : i]]
        waits = [x["args"][1] for x in insts[trig + 1 : i] if x["name"] == "waiti"]
        out.append((waits, names))
    return out


def _arv(legacy, soccfg, **overrides):
    cfg = dict(use_active_reset=True, readout_threshold=0.0, reset_readout_relax_delay=5.0)
    cfg.update(overrides)
    return legacy["ARV"](soccfg, _cfg(legacy["BaseConfig"], **cfg))


def test_active_reset_read_waits_for_latency(legacy, board):
    """The reset `read` must not run until the current readout's accumulated I has
    reached the tProc input: a waiti to >= window end + 0.5 us sits before the synci
    (so the stall does not move the reference time or the corrective pi)."""
    from qicklab.core.active_reset import MIN_RESET_READ_SETTLE_US

    variant, soccfg = board
    floor = soccfg.us2cycles(MIN_RESET_READ_SETTLE_US)
    assert MIN_RESET_READ_SETTLE_US == 0.5
    progs = [_mr(legacy, soccfg, True, 2), _arv(legacy, soccfg, reset_cycles=2)]
    for prog in progs:
        stalls = _reset_read_stalls(prog)
        assert len(stalls) == 2
        for waits, names in stalls:
            assert waits == [RESET_READ_WAITI[variant]]
            assert waits[0] >= RESET_RO_END[variant] + floor
            # waiti, then the synci that schedules the pi, then straight to `read`.
            assert names[-2:] == ["waiti", "synci"]


@pytest.mark.parametrize("latency", [0.0, 0.2])
def test_reset_read_latency_is_floored(legacy, board, latency):
    """A cfg latency below the floor is clamped up, never down."""
    variant, soccfg = board
    for prog in (
        legacy["MR"](
            soccfg,
            _cfg(
                legacy["BaseConfig"],
                **MR_PARAMS,
                use_active_reset=True,
                reset_read_latency_us=latency,
            ),
        ),
        _arv(legacy, soccfg, reset_read_latency_us=latency),
    ):
        assert prog.reset_read_latency_us == 0.5
        assert [w for w, _ in _reset_read_stalls(prog)] == [[RESET_READ_WAITI[variant]]]


def test_reset_read_latency_above_floor(legacy, board):
    variant, soccfg = board
    prog = _arv(legacy, soccfg, reset_read_latency_us=1.0)
    assert _reset_read_stalls(prog)[0][0] == [RESET_RO_END[variant] + soccfg.us2cycles(1.0)]
    # Longer stall, same schedule: waiti never advances the reference time.
    mr = legacy["MR"](
        soccfg,
        _cfg(legacy["BaseConfig"], **MR_PARAMS, use_active_reset=True, reset_read_latency_us=1.0),
    )
    assert mr.scheduled_rep_period_cycles() == MR_PERIOD[variant][(True, 1)]


# (0.5, 0.501): same tProc cycle count (215) for both, so the stall would end 1 cycle
# before the pi with `read` + ~12 setup instructions still to run. (None, 0.65): 64-cycle
# gap, under the 86-cycle (0.2 us) setup margin.
@pytest.mark.parametrize(
    ("latency", "relax"),
    [(0.5, 0.5), (None, 0.3), (5.0, 5.0), (None, 0.501), (None, 0.65), (1.0, 1.1)],
)
def test_reset_read_latency_must_end_before_pi(legacy, latency, relax):
    """The guard is in tProc cycles and leaves RESET_PI_SETUP_MARGIN_US for the read and
    the corrective pi's register setup."""
    soccfg = capture.FakeSocCfg("A")
    extra = {} if latency is None else {"reset_read_latency_us": latency}
    with pytest.raises(ValueError, match="reset_readout_relax_delay"):
        _arv(legacy, soccfg, reset_readout_relax_delay=relax, **extra)
    params = dict(MR_PARAMS, reset_readout_relax_delay=relax, **extra)
    with pytest.raises(ValueError, match="reset_readout_relax_delay"):
        legacy["MR"](soccfg, _cfg(legacy["BaseConfig"], **params, use_active_reset=True))


@pytest.mark.parametrize("variant", capture.VARIANTS)
def test_reset_read_latency_margin_boundary(legacy, variant):
    """relax - latency == the setup margin in cycles is accepted, and the corrective pi is
    then scheduled at least that margin after the stall ends."""
    from qicklab.core.active_reset import MIN_RESET_READ_SETTLE_US, RESET_PI_SETUP_MARGIN_US

    soccfg = capture.FakeSocCfg(variant)
    assert RESET_PI_SETUP_MARGIN_US == 0.2
    relax = MIN_RESET_READ_SETTLE_US + RESET_PI_SETUP_MARGIN_US  # 0.7 us
    assert soccfg.us2cycles(relax) - soccfg.us2cycles(MIN_RESET_READ_SETTLE_US) == (
        soccfg.us2cycles(RESET_PI_SETUP_MARGIN_US)
    )
    prog = _arv(legacy, soccfg, reset_readout_relax_delay=relax)
    insts = prog.prog_list
    i = next(k for k, x in enumerate(insts) if x["name"] == "read")
    assert [x["name"] for x in insts[i - 2 : i]] == ["waiti", "synci"]
    stall_end, pi_time = insts[i - 2]["args"][1], insts[i - 1]["args"][0]
    assert pi_time - stall_end >= soccfg.us2cycles(RESET_PI_SETUP_MARGIN_US)
