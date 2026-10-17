"""TWPA pump_sweep (hardware-free): per-row pump-OFF reference, gain ranking, per-row atomic save.

Fakes the SynthHD (``pywindfreak`` is an optional extra), the PNA-X and ``input()``; the
synthetic S21 has a linear drift in time plus a pump-dependent gain bump. The gain against the
row's pump-OFF trace must recover the injected optimum, where the raw ON |S21| is pulled by the
drift; the npz is written once per frequency row (plus once on an interrupted row), atomically,
and a failed write warns instead of aborting the sweep.
"""

import importlib
import json
import os
import sys
import types

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402

from qicklab.hardware.yoko import TWPA_YOKO_ADDRESS  # noqa: E402

N_F, N_P = 7, 5  # pump grid used by the tests (rows = pump frequency, columns = pump power)
I0, J0 = 2, 2  # injected optimum
G0 = 10.0  # peak gain (dB)
DRIFT_DB = 0.5  # baseline drift per PNA-X measurement (dB)
N_SIG = 21  # PNA-X points across the band (the committed PNAX_N_FREQ_POINTS)
SHAPE = 1.0 + 0.2 * np.cos(2 * np.pi * np.arange(N_SIG) / 20.0)  # gain ripple across the band


class FakeChannel:
    def __init__(self):
        self.frequency, self.power, self.rf_enable = 0.0, -100.0, False


class FakeSynth:
    instances = []

    def __init__(self, port):
        self.port = port
        self.channels = [FakeChannel(), FakeChannel()]  # connecting disables RF on both
        self.closed = False
        FakeSynth.instances.append(self)

    def __getitem__(self, i):
        return self.channels[i]

    def close(self):
        for ch in self.channels:
            ch.rf_enable = False
        self.closed = True


class FakeYoko:
    """TWPA bias source, read-only here: CURR mode, output on, 11 uA."""

    def __init__(self):
        self.writes, self.closed = [], False

    def query(self, cmd):
        return {":OUTP?": "1", ":SOUR:FUNC?": "CURR", ":SOUR:LEV?": "1.1e-05"}[cmd]

    def write(self, cmd):
        self.writes.append(cmd)

    def close(self):
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


@pytest.fixture
def ps(monkeypatch, tmp_path):
    fake = types.ModuleType("pywindfreak")
    fake.SynthHD = FakeSynth
    monkeypatch.setitem(sys.modules, "pywindfreak", fake)
    names = ("qicklab.hardware.synthhd", "qicklab.twpa.pump_sweep")
    for name in names:
        monkeypatch.delitem(sys.modules, name, raising=False)
    mod = importlib.import_module("qicklab.twpa.pump_sweep")
    FakeSynth.instances.clear()
    pnax, yoko = FakePnax(), FakeYoko()
    # The TWPA state log goes to tmp_path/state, never to the committed V:/ path.
    monkeypatch.setattr("qicklab.twpa.common.TWPA_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(mod, "N_FREQ_POINTS", N_F)
    monkeypatch.setattr(mod, "N_POWER_POINTS", N_P)
    monkeypatch.setattr(mod, "SAVE_DIR", str(tmp_path))
    rm = types.SimpleNamespace(open_resource=lambda a: yoko if a == TWPA_YOKO_ADDRESS else pnax)
    monkeypatch.setattr(mod.pyvisa, "ResourceManager", lambda: rm)
    monkeypatch.setattr("builtins.input", lambda *a: "yes")
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    mod._test_pnax = pnax
    mod._test_yoko = yoko
    yield mod
    plt.close("all")
    for name in names:
        sys.modules.pop(name, None)


def install_model(mod, monkeypatch, raise_at=None, exc=KeyboardInterrupt):
    """Synthetic PNA-X: S21(dB) = drift(call index) + [pump on] gain(i, j) * SHAPE(f).

    Raises ``exc`` on measurement call number ``raise_at``. Returns the measurement log: one
    (rf_on, i, j) per call."""
    freqs_Hz = np.linspace(mod.F_START_GHz, mod.F_STOP_GHz, N_F) * 1e9
    powers = np.linspace(mod.P_START_dBm, mod.P_STOP_dBm, N_P)
    log = []

    def gain(i, j):
        return G0 * np.exp(-(((i - I0) / 1.2) ** 2) - ((j - J0) / 1.2) ** 2)

    def measure(pnax, n_avg):
        k = len(log)
        if raise_at is not None and k == raise_at:
            raise exc("injected")
        ch = FakeSynth.instances[-1][mod.PUMP_CHANNELS[0]]
        i = int(np.argmin(np.abs(freqs_Hz - ch.frequency)))
        j = int(np.argmin(np.abs(powers - ch.power)))
        rf_on = any(FakeSynth.instances[-1][c].rf_enable for c in mod.PUMP_CHANNELS)
        log.append((rf_on, i, j))
        shape = SHAPE if mod.PNAX_MEAS_MODE == "BAND" else SHAPE[:1]
        db = -3.0 + DRIFT_DB * k + (gain(i, j) * shape if rf_on else 0.0 * shape)
        return 10 ** (db / 20.0) * np.exp(1j * 0.3)

    monkeypatch.setattr(mod, "measure_s21_band", measure)
    return log


def count_replaces(mod, monkeypatch, fail=None):
    """Record every rename of the temp file onto the npz; ``fail`` = "first" or "all" refuses it.

    Each record is (src, dst, pump RF on at that moment, PNA-X source already switched off)."""
    calls = []
    real = os.replace

    def replace(src, dst):
        rf_on = any(ch.rf_enable for ch in FakeSynth.instances[-1].channels)
        calls.append((src, dst, rf_on, "SOUR:POW1:MODE OFF" in mod._test_pnax.writes))
        if fail == "all" or (fail == "first" and len(calls) == 1):
            raise PermissionError("V:/ is briefly unreachable")
        return real(src, dst)

    monkeypatch.setattr(mod.os, "replace", replace)
    return calls


def load_npz(tmp_path):
    files = sorted(tmp_path.glob("*_pump_sweep.npz"))
    assert len(files) == 1
    assert not list(tmp_path.glob("*.tmp"))  # atomic: no temp file left behind
    # F46: each save (re)writes the provenance sidecar next to the npz
    assert (tmp_path / (files[0].stem + "_provenance.json")).is_file()
    with np.load(files[0]) as z:
        return {k: z[k] for k in z.files}


# --- helpers ---------------------------------------------------------------------------------


def test_gain_band_stats_and_best_point(ps):
    on = np.array([[2.0, 4.0, 8.0], [np.nan, np.nan, np.nan]])
    off = np.array([1.0, 1.0, 2.0])
    g = ps.gain_trace_dB(on, off)
    assert g[0] == pytest.approx(20 * np.log10([2.0, 4.0, 4.0]))
    g_mean, g_min, ripple = ps.gain_band_stats(g)
    assert g_mean[0] == pytest.approx(np.mean(20 * np.log10([2.0, 4.0, 4.0])))
    assert g_min[0] == pytest.approx(20 * np.log10(2.0))
    assert ripple[0] == pytest.approx(20 * np.log10(2.0))
    assert np.isnan(g_mean[1]) and np.isnan(g_min[1]) and np.isnan(ripple[1])

    fom = np.array([[1.0, 5.0], [9.0, np.nan]])
    assert ps.best_point(fom, np.array([[True, True], [False, True]])) == (0, 1)
    assert ps.best_point(fom, np.zeros((2, 2), bool)) is None


def test_save_npz_atomic_warns_on_oserror(ps, monkeypatch, tmp_path, capsys):
    path = str(tmp_path / "x.npz")
    assert ps.save_npz_atomic(path, a=np.arange(3))
    assert os.path.exists(path) and not os.path.exists(path + ".tmp")
    assert not os.path.exists(path + ".npz")  # no doubled extension

    def boom(src, dst):
        raise OSError("network drive gone")

    monkeypatch.setattr(ps.os, "replace", boom)
    assert ps.save_npz_atomic(path, a=np.arange(4)) is False
    out = capsys.readouterr().out
    # The rename failed after a complete temp write: the warning names the temp file, which is kept.
    assert "WARNING" in out and f"the newest data is complete in {path}.tmp" in out
    with np.load(path) as z:  # the previous good file is untouched
        assert z["a"].tolist() == [0, 1, 2]
    with open(path + ".tmp", "rb") as f, np.load(f) as z:
        assert z["a"].tolist() == [0, 1, 2, 3]

    # The temp write itself fails (directory gone): no temp file, the warning says so.
    bad = str(tmp_path / "missing_dir" / "y.npz")
    assert ps.save_npz_atomic(bad, a=np.arange(3)) is False
    assert f"{bad} keeps the last successful save" in capsys.readouterr().out
    assert not os.path.exists(bad + ".tmp")


# --- main() with fakes -------------------------------------------------------------------------


def test_gain_vs_row_off_reference_recovers_optimum_despite_drift(
    ps, monkeypatch, tmp_path, capsys
):
    log = install_model(ps, monkeypatch)
    saves = count_replaces(ps, monkeypatch)
    ps.main()
    out = capsys.readouterr().out
    d = load_npz(tmp_path)

    # One pump-RF-OFF reference at the start of every row, then the power sweep with RF on.
    assert len(log) == N_F * (N_P + 1)
    for i in range(N_F):
        row = log[i * (N_P + 1) : (i + 1) * (N_P + 1)]
        assert row[0] == (False, i, 0)
        assert [r[0] for r in row[1:]] == [True] * N_P
        assert [r[2] for r in row[1:]] == list(range(N_P))

    assert d["off_completed"].all() and d["completed"].all()
    assert d["s21_off"].shape == (N_F, N_SIG)
    assert d["gain_band_dB"].shape == (N_F, N_P)
    # band-mean gain == ON band-mean |S21| - the row's OFF band-mean |S21| (no NaNs here)
    np.testing.assert_allclose(d["gain_band_dB"], d["mean_band_dB"] - d["off_band_dB"][:, None])

    # Ranking on gain recovers the injected optimum; raw ON |S21| is dragged to the last row.
    i_g, j_g = np.unravel_index(np.nanargmax(d["gain_band_dB"]), (N_F, N_P))
    i_s, _ = np.unravel_index(np.nanargmax(d["mean_band_dB"]), (N_F, N_P))
    assert (i_g, j_g) == (I0, J0)
    assert i_s == N_F - 1

    # Band-min gain and ripple at the optimum (intra-row drift = (J0 + 1) calls since the OFF).
    offset = DRIFT_DB * (J0 + 1)
    assert d["gain_ripple_dB"][I0, J0] == pytest.approx(G0 * (SHAPE.max() - SHAPE.min()))
    assert d["gain_min_dB"][I0, J0] == pytest.approx(G0 * SHAPE.min() + offset)
    assert d["gain_band_dB"][I0, J0] == pytest.approx(G0 * SHAPE.mean() + offset)

    # Saved once per frequency row, never per point; nothing left unsaved for the finally path.
    assert len(saves) == N_F
    assert all(src.endswith(".npz.tmp") and dst.endswith(".npz") for src, dst, *_ in saves)

    assert "Best pump point for band-mean gain" in out
    assert "_pump_sweep.npz" in out and "NOT saved" not in out
    assert "band-min gain" in out and "ripple" in out
    assert f"f = {np.linspace(ps.F_START_GHz, ps.F_STOP_GHz, N_F)[I0]:.4f} GHz" in out
    ch = FakeSynth.instances[-1][ps.PUMP_CHANNELS[0]]
    assert ch.rf_enable is False and ps._test_pnax.closed


def test_interrupted_row_is_saved_in_finally(ps, monkeypatch, tmp_path):
    k = 3 * (N_P + 1) + 3  # row 3: OFF, j=0, j=1 measured, Ctrl-C during j=2
    install_model(ps, monkeypatch, raise_at=k)
    saves = count_replaces(ps, monkeypatch)
    ps.main()
    d = load_npz(tmp_path)
    assert len(saves) == 3 + 1  # rows 0-2 + the partial row on exit
    _, _, rf_on, pnax_off = saves[-1]
    assert not rf_on and pnax_off  # the exit save runs after pump RF and PNA-X source are off
    assert d["completed"][:3].all() and d["completed"][3].tolist() == [
        True,
        True,
        False,
        False,
        False,
    ]
    assert not d["completed"][4:].any()
    assert d["off_completed"].tolist() == [True] * 4 + [False] * (N_F - 4)
    assert np.isfinite(d["gain_band_dB"][3, :2]).all() and np.isnan(d["gain_band_dB"][3, 2:]).all()
    assert all(not ch.rf_enable for ch in FakeSynth.instances[-1].channels)


def test_error_mid_row_saves_partial_row_then_propagates(ps, monkeypatch, tmp_path, capsys):
    """A non-Ctrl-C error (e.g. a VISA timeout) saves the partial row in finally, then re-raises."""
    k = 3 * (N_P + 1) + 3  # row 3: OFF, j=0, j=1 measured, error during j=2
    install_model(ps, monkeypatch, raise_at=k, exc=RuntimeError)
    saves = count_replaces(ps, monkeypatch)
    with pytest.raises(RuntimeError, match="injected"):
        ps.main()
    d = load_npz(tmp_path)
    assert len(saves) == 3 + 1
    _, _, rf_on, pnax_off = saves[-1]
    assert not rf_on and pnax_off
    assert d["completed"][3].tolist() == [True, True, False, False, False]
    assert d["off_completed"].tolist() == [True] * 4 + [False] * (N_F - 4)
    assert np.isfinite(d["gain_band_dB"][3, :2]).all()
    assert all(not ch.rf_enable for ch in FakeSynth.instances[-1].channels)
    assert ps._test_pnax.closed
    assert "NOT saved" not in capsys.readouterr().out


def test_every_save_fails_reports_not_saved(ps, monkeypatch, tmp_path, capsys):
    """No false "Saved: <npz>" line: the run ends with a NOT-saved warning naming the temp file."""
    install_model(ps, monkeypatch)
    saves = count_replaces(ps, monkeypatch, fail="all")
    ps.main()
    out = capsys.readouterr().out
    assert len(saves) == N_F + 1  # every row, plus the retry on exit
    assert not list(tmp_path.glob("*_pump_sweep.npz"))
    (tmp,) = tmp_path.glob("*_pump_sweep.npz.tmp")
    assert f"data NOT saved: {str(tmp)[: -len('.tmp')]} was never written" in out
    assert f"the newest complete write is {tmp}" in out
    assert "Saved: " + str(tmp)[: -len(".tmp")] not in out
    with open(tmp, "rb") as f, np.load(f) as z:  # the temp file holds the full run
        assert z["completed"].all() and z["off_completed"].all()


def test_failed_save_warns_and_sweep_continues(ps, monkeypatch, tmp_path, capsys):
    install_model(ps, monkeypatch)
    saves = count_replaces(ps, monkeypatch, fail="first")
    ps.main()
    assert "WARNING: saving" in capsys.readouterr().out
    assert len(saves) == N_F  # row 0's failure is covered by row 1's save; no extra save
    d = load_npz(tmp_path)
    assert d["completed"].all()


def test_cw_mode_single_point_gain(ps, monkeypatch, tmp_path):
    monkeypatch.setattr(ps, "PNAX_MEAS_MODE", "CW")
    install_model(ps, monkeypatch)
    ps.main()
    d = load_npz(tmp_path)
    assert d["s21_off"].shape == (N_F, 1) and d["s21_band"].shape == (N_F, N_P, 1)
    np.testing.assert_allclose(d["gain_ripple_dB"], 0.0)
    assert np.unravel_index(np.nanargmax(d["gain_band_dB"]), (N_F, N_P)) == (I0, J0)


def test_bias_readback_in_npz_and_state_logged_with_pump_off(ps, monkeypatch, tmp_path):
    """F54: the npz carries a read-only TWPA bias readback; the end state goes to the state log."""
    install_model(ps, monkeypatch)
    ps.main()
    d = load_npz(tmp_path)
    assert d["bias_uA"] == pytest.approx(11.0) and int(d["yoko_output_on"]) == 1
    assert str(d["yoko_func"]) == "CURR" and d["yoko_level"] == pytest.approx(1.1e-5)
    assert ps._test_yoko.writes == [] and ps._test_yoko.closed  # read-only, closed again
    with open(tmp_path / "state" / "twpa_state.jsonl", encoding="utf-8") as f:
        (entry,) = [json.loads(line) for line in f]
    assert entry["script"] == "twpa_pump_sweep" and entry["outcome"] == "completed"
    assert entry["completed_points"] == N_F * N_P
    assert entry["bias"]["bias_uA"] == pytest.approx(11.0)
    assert [p["rf_enable"] for p in entry["pump"]] == [False] * len(ps.PUMP_CHANNELS)
    assert entry["pnax"]["n_avg"] == ps.PNAX_N_AVG and entry["data_file"].endswith(".npz")


def _broken_synth(port):
    raise OSError("could not open port 'COM5'")


@pytest.mark.parametrize("fault", ["connect", "bad_channel"])
def test_failed_synth_setup_is_logged(ps, monkeypatch, tmp_path, fault):
    """F54: the SynthHD connect sits inside the try, so a failure there still writes a log line.

    connect fails -> pump RF unknown (null); connected but a bad PUMP_CHANNELS index -> RF off
    (connect and close both disable it) and the port is closed."""
    install_model(ps, monkeypatch)
    if fault == "connect":
        monkeypatch.setattr(ps, "SynthHD", _broken_synth)
        expect_exc, expect_rf = OSError, None
    else:
        monkeypatch.setattr(ps, "PUMP_CHANNELS", [5])
        expect_exc, expect_rf = IndexError, False
    with pytest.raises(expect_exc):
        ps.main()
    with open(tmp_path / "state" / "twpa_state.jsonl", encoding="utf-8") as f:
        (entry,) = [json.loads(line) for line in f]
    assert entry["outcome"] == "error" and entry["completed_points"] == 0
    assert [p["rf_enable"] for p in entry["pump"]] == [expect_rf]
    assert ps._test_pnax.closed and "SOUR:POW1:MODE OFF" in ps._test_pnax.writes
    if fault == "bad_channel":
        assert FakeSynth.instances[-1].closed


@pytest.mark.parametrize(
    "faults, expect_rf",
    [(("disable",), False), (("close",), False), (("disable", "close"), None)],
)
def test_unconfirmed_pump_off_is_logged_unknown(
    ps, monkeypatch, tmp_path, capsys, faults, expect_rf
):
    """Ctrl-C with the pump ON: logged OFF only if the rf_enable=False writes or close()
    succeeded; if both fail the pump may still be ON, so the log says unknown (null)."""
    install_model(ps, monkeypatch, raise_at=2)  # row 0: OFF, j=0, Ctrl-C at j=1 (pump ON)
    armed = []
    inner = ps.measure_s21_band

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

    monkeypatch.setattr(ps, "measure_s21_band", measure)
    monkeypatch.setattr(FakeChannel, "__setattr__", setattr_)
    monkeypatch.setattr(FakeSynth, "close", close)
    ps.main()
    with open(tmp_path / "state" / "twpa_state.jsonl", encoding="utf-8") as f:
        (entry,) = [json.loads(line) for line in f]
    assert entry["outcome"] == "interrupted"
    assert [p["rf_enable"] for p in entry["pump"]] == [expect_rf] * len(ps.PUMP_CHANNELS)
    ch = FakeSynth.instances[-1][ps.PUMP_CHANNELS[0]]
    out = capsys.readouterr().out
    if expect_rf is None:
        assert ch.rf_enable is True  # still ON: logging "off" would be a false record
        assert "pump RF state unknown (it may still be ON)" in out
    else:
        assert ch.rf_enable is False and "state unknown" not in out
