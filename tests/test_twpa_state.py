"""TWPA state provenance (hardware-free): bias readback, state log, gain_compare leaves the pump ON.

The SynthHD cannot be queried without switching the pump off, so every qicklab.twpa script
appends its end state to <TWPA_STATE_DIR>/twpa_state.jsonl, and pump_sweep / gain_compare store a
read-only TWPA bias readback in their npz. gain_compare leaves the pump ON at the ON point only
after a completed run (LEAVE_PUMP_ON, ``--off`` overrides); Ctrl-C or an error switches it off.
Fakes: SynthHD (``pywindfreak`` is an optional extra), YOKO, PNA-X and ``input()``.
"""

import importlib
import json
import math
import sys
import types

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402

from qicklab.hardware.yoko import TWPA_YOKO_ADDRESS  # noqa: E402
from qicklab.twpa import common  # noqa: E402

N_REP, N_SIG = 3, 11


class FakeYoko:
    """Stateful GS200: answers the queries the scripts send and applies setpoint writes."""

    def __init__(self, on=True, func="CURR", level=11e-6, rng=1e-3):
        self.on, self.func, self.level, self.rng = on, func, level, rng
        self.writes, self.closed = [], False
        self.fail_queries = False

    def query(self, cmd):
        if self.fail_queries:
            raise RuntimeError("VISA timeout")
        return {
            ":OUTP?": "1" if self.on else "0",
            ":SOUR:FUNC?": self.func,
            ":SOUR:LEV?": repr(self.level),
            ":SOUR:RANG?": repr(self.rng),
        }[cmd]

    def write(self, cmd):
        self.writes.append(cmd)
        key, _, val = cmd.partition(" ")
        if key == ":SOUR:LEV":
            self.level = float(val)
        elif key == ":OUTP":
            self.on = val == "ON"
        elif key == ":SOUR:FUNC":
            self.func = val
        elif key == ":SOUR:RANG":
            self.rng = float(val)

    def close(self):
        self.closed = True


class FakeChannel:
    def __init__(self):
        self.frequency, self.power, self.rf_enable = 0.0, -100.0, False


class FakeSynth:
    instances = []

    def __init__(self, port):
        self.channels = [FakeChannel(), FakeChannel()]  # connecting disables RF on both
        self.closed = False
        FakeSynth.instances.append(self)

    def __getitem__(self, i):
        return self.channels[i]

    def close(self):
        for ch in self.channels:
            ch.rf_enable = False
        self.closed = True


class FakePnax:
    timeout = 0

    def __init__(self):
        self.writes, self.closed = [], False

    def write(self, cmd):
        self.writes.append(cmd)

    def query(self, cmd):
        return "1"

    def close(self):
        self.closed = True


def read_log(state_dir):
    with open(state_dir / common.TWPA_STATE_FILE, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Fake instruments; the state log goes to tmp_path/state, data to tmp_path/data."""
    fake = types.ModuleType("pywindfreak")
    fake.SynthHD = FakeSynth
    monkeypatch.setitem(sys.modules, "pywindfreak", fake)
    FakeSynth.instances.clear()
    state_dir = tmp_path / "state"
    monkeypatch.setattr(common, "TWPA_STATE_DIR", str(state_dir))
    yoko, pnax = FakeYoko(), FakePnax()
    rm = types.SimpleNamespace(
        open_resource=lambda a: yoko if a == TWPA_YOKO_ADDRESS else pnax,
    )
    monkeypatch.setattr("pyvisa.ResourceManager", lambda: rm)
    monkeypatch.setattr("builtins.input", lambda *a: "yes")
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr(sys, "argv", ["prog"])
    names = (
        "qicklab.hardware.synthhd",
        "qicklab.twpa.gain_compare",
        "qicklab.twpa.set_pump",
        "qicklab.twpa.set_bias",
        "qicklab.twpa.flux_sweep",
    )
    for name in names:
        monkeypatch.delitem(sys.modules, name, raising=False)
    yield types.SimpleNamespace(
        yoko=yoko, pnax=pnax, state_dir=state_dir, data_dir=tmp_path / "data"
    )
    plt.close("all")
    for name in names:
        sys.modules.pop(name, None)


# --- helpers ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "on, func, expect",
    [(True, "CURR", 11.0), (False, "CURR", math.nan), (True, "VOLT", math.nan)],
)
def test_read_bias_state_is_read_only_and_needs_curr_and_output_on(on, func, expect):
    yoko = FakeYoko(on=on, func=func, level=11e-6)
    b = common.read_bias_state(yoko)
    assert yoko.writes == []
    assert b["yoko_output_on"] is on and b["yoko_func"] == func
    assert b["yoko_level"] == pytest.approx(11e-6)  # the raw setpoint is kept either way
    if math.isnan(expect):
        assert math.isnan(b["bias_uA"])
    else:
        assert b["bias_uA"] == pytest.approx(expect)


def test_query_bias_never_raises_and_closes(capsys):
    def boom(a):
        raise OSError("GPIB1 gone")

    b = common.query_bias(types.SimpleNamespace(open_resource=boom), tag="t")
    assert math.isnan(b["bias_uA"]) and b["yoko_output_on"] is None
    assert "WARNING" in capsys.readouterr().out

    yoko = FakeYoko()
    yoko.fail_queries = True
    b = common.query_bias(types.SimpleNamespace(open_resource=lambda a: yoko), tag="t")
    assert math.isnan(b["bias_uA"]) and yoko.closed and yoko.writes == []

    f = common.bias_npz_fields(b)
    assert math.isnan(f["bias_uA"]) and math.isnan(f["yoko_level"])
    assert f["yoko_output_on"] == -1 and f["yoko_func"] == "unknown"
    f = common.bias_npz_fields(common.read_bias_state(FakeYoko()))
    assert f == {
        "bias_uA": pytest.approx(11.0),
        "yoko_output_on": 1,
        "yoko_func": "CURR",
        "yoko_level": pytest.approx(11e-6),
    }


def test_append_state_writes_strict_json_lines_and_never_raises(tmp_path, capsys):
    common.append_state("a", state_dir=str(tmp_path), bias={"bias_uA": math.nan}, x=np.float64(2))
    common.append_state("b", state_dir=str(tmp_path), pump=None)
    log = read_log(tmp_path)
    assert [e["script"] for e in log] == ["a", "b"]
    assert log[0]["bias"]["bias_uA"] is None and log[0]["x"] == 2.0  # NaN -> null
    assert {"time", "unix_time"} <= set(log[0])

    blocker = tmp_path / "file"
    blocker.write_text("")
    assert common.append_state("c", state_dir=str(blocker)) is None  # a file, not a dir
    assert "WARNING: could not append" in capsys.readouterr().out


def test_state_log_is_sandboxed_in_every_test():
    """tests/conftest.py redirects TWPA_STATE_DIR for every test, so no test (test_yoko_safety
    runs set_bias / flux_sweep main()) can append a made-up line to the lab's real state log."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(common))
    (committed,) = [
        n.value.value
        for n in tree.body
        if isinstance(n, ast.Assign) and [t.id for t in n.targets] == ["TWPA_STATE_DIR"]
    ]
    assert common.TWPA_STATE_DIR != committed


# --- gain_compare ------------------------------------------------------------------------------


def load_gc(env, monkeypatch, raise_at=None, exc=KeyboardInterrupt):
    mod = importlib.import_module("qicklab.twpa.gain_compare")
    monkeypatch.setattr(mod, "SAVE_DIR", str(env.data_dir))
    monkeypatch.setattr(mod, "N_REPEATS", N_REP)
    monkeypatch.setattr(mod, "N_SIGNAL_POINTS", N_SIG)
    calls = []

    def measure(pnax, n_points):
        if raise_at is not None and len(calls) == raise_at:
            raise exc("injected")
        on = FakeSynth.instances[-1][mod.PUMP_CHANNELS[0]].rf_enable
        calls.append(on)
        return np.full(n_points, 10 ** ((15.0 if on else 0.0) / 20.0), dtype=complex)

    monkeypatch.setattr(mod, "measure_s21_trace", measure)
    return mod, calls


def npz(env):
    (f,) = env.data_dir.glob("*_gain_on_vs_off.npz")
    with np.load(f) as z:
        return {k: z[k] for k in z.files}


def test_gain_compare_completed_run_leaves_pump_on_and_logs_it(env, monkeypatch, capsys):
    mod, calls = load_gc(env, monkeypatch)
    mod.main()
    synth = FakeSynth.instances[-1]
    ch = synth[mod.PUMP_CHANNELS[0]]
    assert calls == [False, True] * N_REP
    assert ch.rf_enable is True and not synth.closed  # port left open: close() kills RF
    assert ch.frequency == pytest.approx(mod.PUMP_ON_FREQ_GHz * 1e9)
    assert ch.power == pytest.approx(mod.PUMP_ON_POWER_dBm)
    assert env.pnax.closed and "SOUR:POW1:MODE OFF" in env.pnax.writes
    assert env.yoko.writes == [] and env.yoko.closed  # bias read-only

    d = npz(env)
    assert d["bias_uA"] == pytest.approx(11.0) and int(d["yoko_output_on"]) == 1
    assert str(d["yoko_func"]) == "CURR" and int(d["completed_repeats"]) == N_REP

    (entry,) = read_log(env.state_dir)
    assert entry["script"] == "twpa_gain_compare" and entry["outcome"] == "completed"
    assert entry["completed_repeats"] == N_REP
    assert entry["bias"]["bias_uA"] == pytest.approx(11.0)
    assert entry["pump"] == [
        {
            "channel": mod.PUMP_CHANNELS[0],
            "freq_hz": pytest.approx(mod.PUMP_ON_FREQ_GHz * 1e9),
            "power_dbm": mod.PUMP_ON_POWER_dBm,
            "rf_enable": True,
        }
    ]
    assert entry["pnax"]["power_dbm"] == mod.PNAX_POWER_dBm
    assert entry["data_file"].endswith("_gain_on_vs_off.npz")
    assert "Pump left ON" in capsys.readouterr().out


@pytest.mark.parametrize(
    "exc, outcome", [(KeyboardInterrupt, "interrupted"), (RuntimeError, "error")]
)
def test_gain_compare_aborted_run_switches_pump_off(env, monkeypatch, exc, outcome):
    mod, _ = load_gc(env, monkeypatch, raise_at=3, exc=exc)  # repeat 1 OFF done, ON trace fails
    if exc is KeyboardInterrupt:
        mod.main()
    else:
        with pytest.raises(RuntimeError, match="injected"):
            mod.main()
    synth = FakeSynth.instances[-1]
    assert synth.closed and not any(ch.rf_enable for ch in synth.channels)
    (entry,) = read_log(env.state_dir)
    assert entry["outcome"] == outcome and entry["completed_repeats"] == 1
    assert entry["pump"][0]["rf_enable"] is False
    assert int(npz(env)["completed_repeats"]) == 1


@pytest.mark.parametrize("how", ["--off", "constant"])
def test_gain_compare_off_override(env, monkeypatch, how):
    mod, _ = load_gc(env, monkeypatch)
    if how == "--off":
        monkeypatch.setattr(sys, "argv", ["prog", "--off"])
    else:
        monkeypatch.setattr(mod, "LEAVE_PUMP_ON", False)
    mod.main()
    synth = FakeSynth.instances[-1]
    assert synth.closed and not any(ch.rf_enable for ch in synth.channels)
    assert read_log(env.state_dir)[0]["pump"][0]["rf_enable"] is False


def test_gain_compare_failed_reenable_falls_back_to_off(env, monkeypatch, capsys):
    mod, _ = load_gc(env, monkeypatch)
    real = mod.set_pump_channels
    n = []

    def flaky(*a, **k):
        n.append(1)
        if len(n) == N_REP + 2:  # park + one ON per repeat, then the final re-enable
            raise RuntimeError("serial write failed")
        return real(*a, **k)

    monkeypatch.setattr(mod, "set_pump_channels", flaky)
    mod.main()
    synth = FakeSynth.instances[-1]
    assert synth.closed and not any(ch.rf_enable for ch in synth.channels)
    assert "failed to re-enable" in capsys.readouterr().out
    entry = read_log(env.state_dir)[0]
    assert entry["outcome"] == "completed" and entry["pump"][0]["rf_enable"] is False


def arm_rf_faults(mod, monkeypatch, measure_attr, faults):
    """From the injected Ctrl-C on (the pump is ON then), make the listed exits fail.

    "disable": every ``rf_enable = False`` write raises; "close": ``SynthHD.close()`` raises
    without touching the channels."""
    armed = []
    inner = getattr(mod, measure_attr)

    def measure(*a, **k):
        try:
            return inner(*a, **k)
        except KeyboardInterrupt:
            armed.append(True)
            raise

    def setattr_(self, name, value):
        if armed and "disable" in faults and name == "rf_enable" and value is False:
            raise OSError("serial write failed")
        object.__setattr__(self, name, value)

    def close(self):
        if armed and "close" in faults:
            raise OSError("serial port vanished")
        for ch in self.channels:
            object.__setattr__(ch, "rf_enable", False)
        self.closed = True

    monkeypatch.setattr(mod, measure_attr, measure)
    monkeypatch.setattr(FakeChannel, "__setattr__", setattr_)
    monkeypatch.setattr(FakeSynth, "close", close)


@pytest.mark.parametrize(
    "faults, expect_rf",
    [(("disable",), False), (("close",), False), (("disable", "close"), None)],
)
def test_gain_compare_unconfirmed_pump_off_is_logged_unknown(
    env, monkeypatch, capsys, faults, expect_rf
):
    """Ctrl-C with the pump ON: it is logged OFF only if the rf_enable=False writes or close()
    succeeded; if both fail the pump may still be ON, so the log says unknown (null)."""
    mod, _ = load_gc(env, monkeypatch, raise_at=3)  # Ctrl-C on repeat 2's ON trace: pump ON
    arm_rf_faults(mod, monkeypatch, "measure_s21_trace", faults)
    mod.main()
    synth = FakeSynth.instances[-1]
    (entry,) = read_log(env.state_dir)
    assert entry["outcome"] == "interrupted"
    assert entry["pump"][0]["rf_enable"] is expect_rf
    out = capsys.readouterr().out
    assert env.pnax.closed
    if expect_rf is None:
        assert synth[mod.PUMP_CHANNELS[0]].rf_enable is True  # still ON: "off" would be false
        assert "pump RF state unknown (it may still be ON)" in out
        assert "Pump RF disabled." not in out
    else:
        assert synth[mod.PUMP_CHANNELS[0]].rf_enable is False
        assert "Pump RF disabled." in out and "state unknown" not in out


# --- set_pump / set_bias / flux_sweep ------------------------------------------------------------


def test_set_pump_on_flag_overrides_disable_default_and_logs(env, monkeypatch):
    mod = importlib.import_module("qicklab.twpa.set_pump")
    assert mod.DISABLE_PUMP is True  # the committed default turns the pump off
    mod.main()
    assert FakeSynth.instances[-1].closed
    assert read_log(env.state_dir)[-1]["action"] == "pump_off"

    monkeypatch.setattr(sys, "argv", ["prog", "--on"])
    mod.main()
    synth = FakeSynth.instances[-1]
    (idx, (f_ghz, p_dbm)), *_ = mod.PUMP_SETTINGS.items()
    assert synth[idx].rf_enable is True and not synth.closed
    entry = read_log(env.state_dir)[-1]
    assert entry["action"] == "pump_on" and entry["script"] == "twpa_set_pump"
    assert entry["pump"][0] == {
        "channel": idx,
        "freq_hz": pytest.approx(f_ghz * 1e9),
        "power_dbm": p_dbm,
        "rf_enable": True,
    }
    assert entry["bias"]["bias_uA"] == pytest.approx(11.0) and env.yoko.writes == []

    monkeypatch.setattr(sys, "argv", ["prog", "--on", "--off"])
    with pytest.raises(ValueError, match="not both"):
        mod.main()


def test_set_bias_logs_readback_after_ramp(env, monkeypatch):
    env.yoko.on, env.yoko.level = False, 0.0
    mod = importlib.import_module("qicklab.twpa.set_bias")
    monkeypatch.setattr(mod, "TARGET_CURRENT_uA", 2.0)
    mod.main()
    (entry,) = read_log(env.state_dir)
    assert entry["script"] == "twpa_set_bias" and entry["outcome"] == "completed"
    assert entry["target_uA"] == 2.0 and entry["bias"]["bias_uA"] == pytest.approx(2.0)
    assert entry["bias"]["yoko_output_on"] is True and entry["pump"] is None


def test_flux_sweep_logs_bias_after_ramp_to_zero(env, monkeypatch):
    env.yoko.on, env.yoko.level = False, 0.0
    mod = importlib.import_module("qicklab.twpa.flux_sweep")
    monkeypatch.setattr(mod, "SAVE_DIR", str(env.data_dir))
    monkeypatch.setattr(mod, "I_START_uA", -1.0)
    monkeypatch.setattr(mod, "I_STOP_uA", 1.0)
    monkeypatch.setattr(mod, "N_BIAS_POINTS", 3)
    monkeypatch.setattr(
        mod, "measure_s21_band", lambda pnax, n_avg: np.ones(mod.PNAX_N_FREQ_POINTS, complex)
    )
    mod.main()
    (entry,) = read_log(env.state_dir)
    assert entry["script"] == "twpa_flux_sweep" and entry["outcome"] == "completed"
    assert entry["completed_points"] == 3
    assert entry["bias"]["bias_uA"] == pytest.approx(0.0)  # ramped back to 0 on exit
    assert entry["pnax"]["n_points"] == mod.PNAX_N_FREQ_POINTS


# --- failures after the pump scripts start touching the SynthHD ------------------------------------


def _broken_synth(port):
    raise OSError("could not open port 'COM5'")


@pytest.mark.parametrize("fault", ["connect", "bad_channel"])
def test_gain_compare_failed_synth_setup_is_logged(env, monkeypatch, capsys, fault):
    mod, _ = load_gc(env, monkeypatch)
    if fault == "connect":
        monkeypatch.setattr(mod, "SynthHD", _broken_synth)
        expect_exc, expect_rf = OSError, None  # unknown: the connect itself failed
    else:
        monkeypatch.setattr(mod, "PUMP_CHANNELS", [5])
        expect_exc, expect_rf = IndexError, False  # connected: connect + close disable RF
    with pytest.raises(expect_exc):
        mod.main()
    (entry,) = read_log(env.state_dir)
    assert entry["outcome"] == "error" and entry["completed_repeats"] == 0
    assert [p["rf_enable"] for p in entry["pump"]] == [expect_rf]
    assert env.pnax.closed
    if fault == "connect":
        assert "pump RF state unknown" in capsys.readouterr().out
    else:
        assert FakeSynth.instances[-1].closed


def test_set_pump_failed_connect_is_logged_unknown(env, monkeypatch):
    mod = importlib.import_module("qicklab.twpa.set_pump")
    monkeypatch.setattr(mod, "SynthHD", _broken_synth)
    for argv, action in ((["prog"], "pump_off"), (["prog", "--on"], "pump_on")):
        monkeypatch.setattr(sys, "argv", argv)
        with pytest.raises(OSError):
            mod.main()
        entry = read_log(env.state_dir)[-1]
        assert entry["action"] == action and entry["outcome"] == "error"
        assert [p["rf_enable"] for p in entry["pump"]] == [None] * len(mod.PUMP_SETTINGS)
        assert entry["bias"]["bias_uA"] == pytest.approx(11.0)
    assert len(read_log(env.state_dir)) == 2


def test_set_pump_off_path_close_error_still_logs_off(env, monkeypatch):
    mod = importlib.import_module("qicklab.twpa.set_pump")
    real_close = FakeSynth.close

    def bad_close(self):
        real_close(self)  # RF is off on both channels...
        raise OSError("serial port vanished")  # ...but the close call fails

    monkeypatch.setattr(FakeSynth, "close", bad_close, raising=True)
    with pytest.raises(OSError):
        mod.main()
    entry = read_log(env.state_dir)[-1]
    assert entry["action"] == "pump_off" and entry["outcome"] == "error"
    assert [p["rf_enable"] for p in entry["pump"]] == [False] * len(mod.PUMP_SETTINGS)


def test_set_pump_on_interrupted_while_programming_logs_unknown(env, monkeypatch):
    """Ctrl-C before every channel is programmed: the pump state is unknown, never 'ON'."""
    mod = importlib.import_module("qicklab.twpa.set_pump")
    monkeypatch.setattr(sys, "argv", ["prog", "--on"])

    def interrupted(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(mod, "set_pump_channels", interrupted)
    with pytest.raises(KeyboardInterrupt):
        mod.main()
    (entry,) = read_log(env.state_dir)
    assert entry["action"] == "pump_on" and entry["outcome"] == "interrupted"
    assert [p["rf_enable"] for p in entry["pump"]] == [None] * len(mod.PUMP_SETTINGS)


def test_set_pump_on_interrupted_after_parking_logs_on(env, monkeypatch):
    """Ctrl-C after the pump is parked (during the readback printout): it is ON, and logged ON."""
    mod = importlib.import_module("qicklab.twpa.set_pump")
    monkeypatch.setattr(sys, "argv", ["prog", "--on"])

    def print_(*a, **k):
        if a and "Pump enabled" in str(a[0]):
            raise KeyboardInterrupt

    monkeypatch.setattr(mod, "print", print_, raising=False)  # shadows the builtin in the module
    with pytest.raises(KeyboardInterrupt):
        mod.main()
    synth = FakeSynth.instances[-1]
    (idx, _), *_ = mod.PUMP_SETTINGS.items()
    assert synth[idx].rf_enable is True and not synth.closed
    (entry,) = read_log(env.state_dir)
    assert entry["outcome"] == "interrupted" and entry["pump"][0]["rf_enable"] is True
