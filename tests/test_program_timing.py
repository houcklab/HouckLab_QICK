"""Pin the schedule / readout-window numbers of the legacy tProc programs.

No hardware: every program is compiled against capture.FakeSocCfg, once per
synthetic board variant (A: gen fabric clock = tProc clock, readout i on tProc
input i; B: gen fabric 614.4 MHz != tProc 430.08 MHz, readout i on tProc input
i + 2). The integers below were obtained from the pre-refactor code; the
refactor (shared readout/reset/schedule helpers) must reproduce them exactly.
The regime-A and zero-span pins at the end were set by the readout-window fix
(each records the value it replaced).
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


# (readout_tone_cycles, extension) when cfg['length'] = 16 us exceeds offset + window: the
# requested tone already covers the ADC window, so it is played unextended.
LONG_TONE = {"A": (6881, 0), "B": (9830, 0)}
ARV_EXTRA = {"use_active_reset": True, "readout_threshold": 0.0, "prep_excited": True}


@pytest.mark.parametrize("overrides", [{}, {"ro_chs": [0, 1]}, {"length": 16.0}])
def test_readout_windows(legacy, board, overrides):
    """SS, MR, ARV and US share core.readout.cover_readout_window, so the window, tone and
    extension agree. US now stores the extension too (it did not when it kept its own copy)."""
    variant, soccfg = board
    base = legacy["BaseConfig"]
    window, tone, extension, offset = READOUT[variant]
    if "length" in overrides:
        tone, extension = LONG_TONE[variant]
    progs = {
        "SS": legacy["SS"](soccfg, _cfg(base, **overrides)),
        "ARV": legacy["ARV"](soccfg, _cfg(base, **ARV_EXTRA, **overrides)),
        "US": legacy["US"](soccfg, _cfg(base, **overrides)),
    }
    if not overrides:
        progs["MR"] = _mr(legacy, soccfg, True)
    ro_chs = overrides.get("ro_chs", [0])
    for name, prog in progs.items():
        assert _readout(prog) == (window, tone, extension, offset), name
        assert prog.readout_window_cycles == dict.fromkeys(ro_chs, window), name
        assert {ch: ro["length"] for ch, ro in prog.ro_chs.items()} == dict.fromkeys(
            ro_chs, window
        ), name
        assert prog._gen_mgrs[prog.cfg["res_ch"]].next_pulse["length"] == tone, name


@pytest.mark.parametrize("name", ["SS", "ARV", "US"])
def test_single_shot_family_uses_shared_window(legacy, board, monkeypatch, name):
    """The single-shot family calls core.readout.cover_readout_window (no private copy), so
    the active-reset threshold transfers between the calibration and its consumers."""
    import importlib

    _, soccfg = board
    cls = legacy[name]
    module = importlib.import_module(cls.__module__)
    real = module.cover_readout_window
    calls = []

    def spy(prog, cfg):
        calls.append(prog)
        return real(prog, cfg)

    monkeypatch.setattr(module, "cover_readout_window", spy)
    extra = ARV_EXTRA if name == "ARV" else {}
    prog = cls(soccfg, _cfg(legacy["BaseConfig"], **extra))
    assert calls == [prog]


# Stored per-channel windows that differ from each other and from us2cycles(readout_length),
# so dividing by channel 0's window everywhere, or by a recomputed us2cycles, fails.
FAKE_WINDOWS = {0: 1000, 1: 250}


@pytest.mark.parametrize("name", ["SS", "US"])
def test_single_shot_normalises_by_declared_window(legacy, board, name):
    """collect_shots divides each ro_ch's raw sums by that channel's stored
    readout_window_cycles[ch]."""
    import numpy as np

    _, soccfg = board
    prog = legacy[name](soccfg, _cfg(legacy["BaseConfig"], ro_chs=[0, 1], shots=4))
    assert all(prog.ro_chs[ch]["length"] not in FAKE_WINDOWS.values() for ch in (0, 1))
    prog.readout_window_cycles = dict(FAKE_WINDOWS)
    prog.di_buf = [np.full(4, FAKE_WINDOWS[ch] * 3.0) for ch in (0, 1)]
    prog.dq_buf = [np.full(4, FAKE_WINDOWS[ch] * -1.0) for ch in (0, 1)]
    i, q = prog.collect_shots()
    for ch in (0, 1):
        assert i[ch].shape == (1, 4) and np.all(i[ch] == 3.0) and np.all(q[ch] == -1.0)


def test_active_reset_verify_normalises_by_declared_window(legacy, board):
    """ARV's collect_shots picks verification read k of each rep out of the
    reads_per_rep-interleaved stream and divides by the stored readout_window_cycles[ro_ch]."""
    import numpy as np

    _, soccfg = board
    reps = 3
    prog = legacy["ARV"](
        soccfg, _cfg(legacy["BaseConfig"], use_active_reset=False, reps=reps, n_verify_reads=2)
    )
    assert prog.ro_chs[0]["length"] != FAKE_WINDOWS[0]
    prog.readout_window_cycles = {0: FAKE_WINDOWS[0]}
    # acquire() sets the layout before collect_shots; mirror it without hardware
    prog.reads_per_rep = rpr = prog.reset_cycles + prog.n_verify_reads
    assert prog.n_verify_reads == 2
    # read slot s of rep r carries value 10*r + s (in per-sample units)
    per_sample = np.array([[10.0 * r + s for s in range(rpr)] for r in range(reps)]).ravel()
    prog.di_buf = [per_sample * FAKE_WINDOWS[0]]
    prog.dq_buf = [-per_sample * FAKE_WINDOWS[0]]
    vi, vq = prog.collect_shots()
    expected = np.array([[10.0 * r + prog.reset_cycles + k for r in range(reps)] for k in range(2)])
    assert vi.shape == (2, reps)
    assert np.array_equal(vi, expected) and np.array_equal(vq, -expected)


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


T2E_PARAMS = {"start": 0, "step": 2 * 0.00232515 * 35, "expts": 121}


@pytest.mark.parametrize("n", [0, 2, 4, -1])
def test_t2e_rejects_even_or_zero_pi_pulses(n):
    """n + 1 equal waits refocus a static detuning only for odd n (docs/experiments/t2_echo.md)."""
    from qicklab.experiments.t2_echo import T2EProgram
    from qicklab.hardware.board import BaseConfig

    cfg = _cfg(BaseConfig, **T2E_PARAMS, num_pi_pulses=n)
    with pytest.raises(ValueError, match="num_pi_pulses = -?\\d+: must be odd"):
        T2EProgram(capture.FakeSocCfg("A"), cfg)


@pytest.mark.parametrize("n", [1, 3])
def test_t2e_accepts_odd_pi_pulses(board, n):
    """Odd n compiles, with one register-timed wait per gap (n + 1 waits)."""
    from qicklab.experiments.t2_echo import T2EProgram
    from qicklab.hardware.board import BaseConfig

    _, soccfg = board
    cfg = _cfg(BaseConfig, **T2E_PARAMS, num_pi_pulses=n)
    prog = T2EProgram(soccfg, cfg)
    assert len(_insts(prog, "sync")) == n + 1


# --- Regime-A programs: readout window on the readout clock, tone covers it -------------
# Before the fix every program below declared us2cycles(readout_length) tProc cycles as
# the window (6451 readout samples = 21.0 us for a 15 us window), played a 6580-cycle tone
# converted on the tProc clock (10.71 us on board B), and its measure() waiti ran to
# int(129 + 6451 * 1.4) = 9160 tProc cycles, ~6 us after the tone ended.
REGIME_A_EXTRA = {
    "start": 0,
    "step": 1,
    "expts": 3,
    "cav_relax_delay": 10,
    "qubit_length": 50.0,
    "Gauss": False,
    "res_phase": 0,
    "mixer_freq": 0,
    "trig_buffer_start": 0.05,
    "trig_buffer_end": 0.05,
    "trig_delay": 0.0,
    "pulse_01": True,
    "qubit_freq": 2651.0,
    "phase_step": 0,
    "num_pi_pulses": 1,
    "df": 1.0,
    "variable_wait": 1.0,
}
REGIME_A = {
    "CavitySpecFF": ("qicklab.experiments.transmission", "CavitySpecFFProg"),
    "QubitSpecSliceFF": ("qicklab.experiments.qubit_spec", "QubitSpecSliceFFProg"),
    "AmplitudeRabiFF": ("qicklab.experiments.rabi", "AmplitudeRabiFFProg"),
    "AmplitudeRabiPoint": ("qicklab.experiments.rabi", "AmplitudeRabiPointProg"),
    "Chi": ("qicklab.experiments.chi_shift", "ChiProgram"),
    "T1": ("qicklab.experiments.t1", "T1Program"),
    "T2R": ("qicklab.experiments.t2_ramsey", "T2RProgram"),
    "T2E": ("qicklab.experiments.t2_echo", "T2EProgram"),
    "ChargeDispersion": ("qicklab.experiments.charge_dispersion", "ChargeDispersionProgram"),
    "ChargeDispersionQuasiCW": (
        "qicklab.experiments.charge_dispersion",
        "ChargeDispersionQuasiCWProg",
    ),
    "T1SS": ("qicklab.experiments.t1_single_shot", "T1SingleShotProgram"),
}
# Programs that declare ADC 0 and 1 whatever ro_chs is; the rest declare ro_chs = [0].
TWO_ADC = {"QubitSpecSliceFF", "AmplitudeRabiFF", "AmplitudeRabiPoint", "ChargeDispersionQuasiCW"}
# int(end of the ADC window) [tProc cycles] = the measure(wait=True) waiti immediate:
# int(129 + 4608 * 430.08 / 307.2) = int(6580.2). Was 9160.
ADC_END_WAITI = {"A": 6580, "B": 6580}
# Const qubit drive of QubitSpecSliceFF / ChargeDispersionQuasiCW for qubit_length = 50 us,
# in generator cycles (50 * f_fabric). Was 21504 (tProc clock) on both boards.
SPEC_DRIVE = {"A": 21504, "B": 30720}
# ConstantTone, length 15.3 us, generator cycles. Was 6580 on both boards.
CONSTANT_TONE = {"A": 6580, "B": 9400}


def _program(name, soccfg, **overrides):
    import importlib

    from qicklab.hardware.board import BaseConfig

    module, cls = REGIME_A[name]
    cfg = _cfg(BaseConfig, **REGIME_A_EXTRA)
    cfg.update(overrides)
    return getattr(importlib.import_module(module), cls)(soccfg, cfg)


@pytest.mark.parametrize("name", sorted(REGIME_A))
def test_regime_a_readout_window(board, name):
    variant, soccfg = board
    prog = _program(name, soccfg)
    window, tone, extension, offset = READOUT[variant]
    declared = [0, 1] if name in TWO_ADC else [0]
    assert {ch: ro["length"] for ch, ro in prog.ro_chs.items()} == dict.fromkeys(
        declared, round(15.0 * 307.2)
    )
    assert _readout(prog) == (window, tone, extension, offset)
    # The resonator const pulse plays the covering tone, in generator cycles.
    res_ch = prog.cfg["res_ch"]
    assert prog._gen_mgrs[res_ch].next_pulse["length"] == prog.readout_tone_cycles
    f_time = soccfg["tprocs"][0]["f_time"]
    f_fabric = soccfg["gens"][res_ch]["f_fabric"]
    adc_end = offset + window * f_time / soccfg["readouts"][0]["f_output"]
    assert int(adc_end) == ADC_END_WAITI[variant]
    assert [w[1] for w in _insts(prog, "waiti")] == [ADC_END_WAITI[variant]]
    # The tone outlasts the ADC window by less than one generator cycle.
    tone_end = tone * f_time / f_fabric
    assert 0 <= tone_end - adc_end < f_time / f_fabric


def test_regime_a_rejects_short_tone(board):
    _, soccfg = board
    with pytest.raises(ValueError, match="must cover"):
        _program("T1", soccfg, length=15.0)


@pytest.mark.parametrize("name", ["QubitSpecSliceFF", "ChargeDispersionQuasiCW"])
def test_const_spec_drive_on_generator_clock(board, name):
    variant, soccfg = board
    prog = _program(name, soccfg)
    qubit_ch = prog.cfg["qubit_ch"]
    cycles = prog._gen_mgrs[qubit_ch].next_pulse["length"]
    assert cycles == SPEC_DRIVE[variant]
    assert cycles / soccfg["gens"][qubit_ch]["f_fabric"] == pytest.approx(50.0, abs=1e-3)


def test_constant_tone_on_generator_clock(board):
    from qicklab.experiments.cw_tones import ConstantTone
    from qicklab.hardware.board import BaseConfig

    variant, soccfg = board
    prog = ConstantTone(soccfg, _cfg(BaseConfig, mixer_freq=0))
    assert prog._gen_mgrs[prog.cfg["res_ch"]].next_pulse["length"] == CONSTANT_TONE[variant]


# CW tones: one periodic const pulse per gen at t = 0, then end (F69). Mode word =
# (stdysel zero | periodic | outsel dds = 0b01101) << 16 | period [gen cycles]. Was the oneshot
# word 0b01001 << 16 | period (A: 596404 / 654782, B: 599224 / 655359), replayed reps times by
# an AveragerProgram loop with a sync_all per rep. The periods are unchanged: ConstantTone
# CONSTANT_TONE, ConstantTwoToneProg min(us2cycles(151 us, gen), 65535) = 64942 (A), 65535 (B).
CW_MODE = {
    "A": {"ConstantTone": {0: 858548}, "ConstantTwoToneProg": {0: 916910, 1: 916910}},
    "B": {"ConstantTone": {0: 861368}, "ConstantTwoToneProg": {0: 917503, 1: 917503}},
}


@pytest.mark.parametrize("name", ["ConstantTone", "ConstantTwoToneProg"])
def test_cw_tones_are_one_periodic_program(board, name):
    import qicklab.experiments.cw_tones as cw
    from qicklab.hardware.board import BaseConfig

    variant, soccfg = board
    cfg = _cfg(BaseConfig, mixer_freq=0, tone_length=151, qubit_freq=2651.0)
    before = dict(cfg)
    prog = getattr(cw, name)(soccfg, cfg)
    assert cfg == before  # the caller's cfg is not touched (ConstantTone wrote reps/rounds)
    names = [inst["name"] for inst in prog.prog_list]
    assert names[-1] == "end" and names.count("end") == 1
    assert not {"loopnz", "synci", "sync", "memwi", "waiti", "label"} & set(names)
    modes = {}
    for ch, want in CW_MODE[variant][name].items():
        pulse = prog._gen_mgrs[ch].next_pulse
        page, mode_reg = pulse["rp"], pulse["regs"][0][4]
        (mode,) = [a[2] for a in _insts(prog, "regwi") if tuple(a[:2]) == (page, mode_reg)]
        modes[ch] = mode
        assert (mode >> 16) & 0b00100  # periodic
        assert not (mode >> 16) & 0b10000  # phrst = 0: phase-continuous
        _, t_reg = prog._gen_regmap[(ch, "t")]
        assert [a[2] for a in _insts(prog, "regwi") if tuple(a[:2]) == (page, t_reg)] == [0]
    assert modes == CW_MODE[variant][name]
    assert len(_insts(prog, "set")) == len(CW_MODE[variant][name])


# Resonator freq register of both CW programs = CavitySpecFF's for pulse_freq 7095.4 MHz: the
# resonator gen is declared with ro_ch = ro_chs[0] and freq2reg rounds to the readout's
# frequency grid (F69). ConstantTwoToneProg passed no ro_ch before: 133643508 on board A
# (B's grid is already common to gen and readout, so B's integer is unchanged).
RES_FREQ_REG = {"A": 133643509, "B": 775006890}


@pytest.mark.parametrize("name", ["ConstantTone", "ConstantTwoToneProg"])
def test_cw_res_tone_declared_like_cavity_spec(board, name):
    import qicklab.experiments.cw_tones as cw
    from qicklab.hardware.board import BaseConfig

    variant, soccfg = board

    def res_freq(prog):
        ch = prog.cfg["res_ch"]
        assert prog.gen_chs[ch]["ro_ch"] == prog.cfg["ro_chs"][0]
        page, reg = prog._gen_regmap[(ch, "freq")]
        return [a[2] for a in _insts(prog, "regwi") if tuple(a[:2]) == (page, reg)]

    cfg = _cfg(BaseConfig, mixer_freq=0, tone_length=151, qubit_freq=2651.0)
    spec = _program("CavitySpecFF", soccfg)
    assert spec.cfg["pulse_freq"] == cfg["pulse_freq"]
    assert res_freq(getattr(cw, name)(soccfg, cfg)) == res_freq(spec) == [RES_FREQ_REG[variant]]


def test_t1_ss_normalises_by_declared_window(board):
    """T1_SS divides each shot by the window it declares (4608 samples), so its shots are in
    SingleShotProgram's per-sample units. The pre-fix program declared 6451 samples but
    divided by 4608, leaving its IQ 1.4x too large for the single_shot threshold."""
    import numpy as np

    _, soccfg = board
    prog = _program("T1SS", soccfg, reps=4)
    ch = prog.cfg["ro_chs"][0]
    declared = prog.ro_chs[ch]["length"]
    assert declared == 4608
    assert prog.readout_window_cycles[ch] == declared
    # FakeSoc / the ADC: the raw sum of a constant per-sample value v over the window.
    prog.di_buf = [np.full(4, declared * 3.0)]
    prog.dq_buf = [np.full(4, declared * -1.0)]
    i, q = prog.collect_shots()
    assert i.shape == (1, 4) and np.all(i == 3.0) and np.all(q == -1.0)


def test_t1_ss_plays_pi_gain(board):
    """T1SingleShotProgram's pi pulse plays cfg['pi_gain'] (run_t1_ss writes ctx.qubit_gain, the
    gain its single_shot calibration uses), not cfg['qubit_gain'] (the spec gain in regime A).
    Was qubit_gain; the harness cfg has both at 4200, so no other pin moves."""
    _, soccfg = board
    prog = _program("T1SS", soccfg, qubit_gain=900, pi_gain=4100)
    pulse = prog._gen_mgrs[prog.cfg["qubit_ch"]].next_pulse
    page, gain_reg = pulse["rp"], pulse["regs"][0][3]  # arb regs: freq, phase, addr, gain, mode
    gains = [args[2] for args in _insts(prog, "regwi") if tuple(args[:2]) == (page, gain_reg)]
    assert gains == [4100]


# --- Zero span: read_length on the readout clock ------------------------------------------
def _zsp_cfg(adc_trig_offset, read_length, sample_period_us=None, capture_length_us=None):
    from qicklab.hardware.board import BaseConfig

    cfg = dict(BaseConfig)
    cfg.update(
        {
            "mixer_freq": 0.0,
            "read_pulse_freq": 7095.4,
            "parity_drive_freq": 1000.0,
            "qubit_gain": 1000,
            "pulse_gain": 1500,
            "res_phase": 0,
            "adc_trig_offset": adc_trig_offset,
            "read_length": read_length,
            "start_src": "internal",
        }
    )
    if sample_period_us is not None:
        cfg.update(mode="strobe", sample_period_us=sample_period_us, reps_per_chunk=100, reps=100)
    else:
        cfg.update(mode="decimated", capture_length_us=capture_length_us, reps=1, soft_avgs=1)
    return cfg


def _last_synci(prog):
    return _insts(prog, "synci")[-1][0]


# (adc_trig_offset, read_length, sample_period_us): the rule-1 floor (offset + read + 1.0)
# exactly. The old window (4300 tProc-cycle count read as samples) made the first one
# 'waiti 0, 6236; synci 6236' = 14.50 us per rep instead of 11.5.
@pytest.mark.parametrize(("offset", "read", "sp"), [(0.5, 10.0, 11.5), (0.488, 5.0, 6.488)])
def test_zero_span_strobe_period_is_sample_period(board, offset, read, sp):
    from qicklab.experiments.zero_span_parity import ZeroSpanParityProgStrobe, _validate_cfg

    _, soccfg = board
    cfg = _zsp_cfg(offset, read, sample_period_us=sp)
    _validate_cfg(cfg, soccfg)
    prog = ZeroSpanParityProgStrobe(soccfg, cfg)
    assert prog.ro_chs[0]["length"] == round(read * 307.2)
    assert _last_synci(prog) == prog.rep_period_cycles == soccfg.us2cycles(sp)


def test_zero_span_default_strobe(board):
    """CSTQ03 default (0.488 / 5 / 20 us): window 1536 readout samples (was 2150); the
    period is the tone's, 20 us, to within board B's < 1 tProc cycle generator rounding."""
    from qicklab.experiments.zero_span_parity import ZeroSpanParityProgStrobe

    variant, soccfg = board
    prog = ZeroSpanParityProgStrobe(soccfg, _zsp_cfg(0.488, 5.0, sample_period_us=20.0))
    assert prog.ro_chs[0]["length"] == 1536
    assert soccfg.us2cycles(20.0) == 8602
    assert _last_synci(prog) == {"A": 8602, "B": 8601}[variant]


def test_zero_span_strobe_normalises_by_declared_window(board):
    """_acquire_strobe divides the raw sums by the window the program declares (1536 samples
    for 5 us), so strobe I/Q are in the single-shot separator's per-sample units. Before the
    fix the program declared 2150 samples and _acquire_strobe divided by 1536 (I/Q 1.4x)."""
    import numpy as np

    from qicklab.experiments.zero_span_parity import ZeroSpanParity, ZeroSpanParityProgStrobe

    _, soccfg = board
    cfg = _zsp_cfg(0.488, 5.0, sample_period_us=20.0)
    prog = ZeroSpanParityProgStrobe(soccfg, cfg)
    declared = prog.ro_chs[cfg["ro_chs"][0]]["length"]
    assert declared == 1536

    class _Stub:
        _acquire_strobe = ZeroSpanParity._acquire_strobe

        def __init__(self):
            self.cfg, self.soccfg, self.soc, self.prog = cfg, soccfg, None, prog

    n = cfg["reps"]
    prog.di_buf = [np.full(n, declared * 3.0)]
    prog.dq_buf = [np.full(n, declared * -1.0)]
    prog.acquire = lambda *_a, **_k: None
    out = _Stub()._acquire_strobe(progress=False)
    assert out["ro_norm_cycles"] == declared
    assert np.allclose(out["I"], 3.0) and np.allclose(out["Q"], -1.0)


def test_zero_span_strobe_rejects_readout_bound_period(board):
    """Below the rule-1 floor (program built without _validate_cfg) the ADC window, not the
    tones, would set the rep period: the program refuses to compile."""
    from qicklab.experiments.zero_span_parity import ZeroSpanParityProgStrobe

    _, soccfg = board
    with pytest.raises(RuntimeError, match="compiled strobe rep period"):
        ZeroSpanParityProgStrobe(soccfg, _zsp_cfg(0.5, 10.0, sample_period_us=9.0))


def test_zero_span_decimated_buffer_rule_matches_declaration(board):
    """Rule 5's estimate round(read_length * f_output) is the declared buffer length."""
    from qicklab.experiments.zero_span_parity import ZeroSpanParityProgDecimated, _validate_cfg

    _, soccfg = board
    ok = _zsp_cfg(0.488, 3.2, capture_length_us=4.0)
    _validate_cfg(ok, soccfg)
    prog = ZeroSpanParityProgDecimated(soccfg, ok)
    assert prog.ro_chs[0]["length"] == 983 <= soccfg["readouts"][0]["buf_maxlen"]
    with pytest.raises(RuntimeError, match="rule 5"):
        _validate_cfg(_zsp_cfg(0.488, 3.4, capture_length_us=4.0), soccfg)


# --- T2R virtual detuning (F29) ---------------------------------------------------------
# The r_phase2 (register 4) mathi immediate in update(): phase_step =
# deg2reg(360 * f_virt * dt, gen_ch=qubit_ch) with the default f_virt = 5 fringes over the
# realised window (capped at 1/8 turn per step), 0.1 us step. Was 0 for every expts
# (deg2reg(0, gen_ch=2)). The same on both boards (32-bit phase, tProc-clock step).
T2R_PHASE_STEP = {5: 2**29, 100: 214748365, 201: 106839982, 401: 53553208}


@pytest.mark.parametrize("expts", sorted(T2R_PHASE_STEP))
def test_t2r_virtual_detuning_phase_step(board, expts):
    from qicklab.experiments.t2_ramsey import ramsey_virtual_detuning
    from qicklab.hardware.board import BaseConfig

    _, soccfg = board
    cfg = _cfg(BaseConfig, **REGIME_A_EXTRA)
    cfg.update(step=0.1, expts=expts)
    detuning = ramsey_virtual_detuning(soccfg, cfg, None)
    assert detuning["phase_step"] == T2R_PHASE_STEP[expts]
    prog = _program("T2R", soccfg, step=0.1, expts=expts, **detuning)
    assert [args[4] for args in _insts(prog, "mathi", reg=4)] == [T2R_PHASE_STEP[expts]]
    assert [args[4] for args in _insts(prog, "mathi", reg=3)] == [43]  # wait step, cycles
