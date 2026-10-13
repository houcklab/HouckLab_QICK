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
# tProc input channel of the active-reset `read` instruction. MR resolves the
# readout's tproc_ch; ARV passes the readout index (known legacy bug, pinned).
READ_INPUT = {"A": {"MR": 0, "ARV": 0}, "B": {"MR": 2, "ARV": 0}}


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
    assert arv.cmp_offset == 1 << 24
