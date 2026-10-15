"""GS200 bring-up safety (hardware-free): output never stepped, wrong source refused, readback.

Scripted fake GS200; covers qicklab.hardware.yoko.enable_current_output_safely (TWPA),
open_charge_yoko (charge line) and ramp_to (+-10 V guard, level readback).
"""

import re

import pytest

from qicklab.hardware import yoko as Y


class ScriptedYoko:
    """GS200 stand-in: answers :OUTP?, :SOUR:FUNC?, :SOUR:RANG?, :SOUR:LEV? from its state."""

    def __init__(self, output=False, func="VOLT", rang=10.0, level=0.0, clip=None):
        self.output, self.func, self.rang, self.level = output, func, rang, level
        self.clip = clip  # None, or the max |level| the source actually applies
        self.log = []
        self.closed = False

    def write(self, cmd):
        self.log.append(f"W {cmd}")
        if m := re.fullmatch(r":SOUR:LEV (\S+)", cmd):
            v = float(m.group(1))
            self.level = v if self.clip is None else max(-self.clip, min(self.clip, v))
        elif m := re.fullmatch(r":OUTP (ON|OFF)", cmd):
            self.output = m.group(1) == "ON"
        elif m := re.fullmatch(r":SOUR:FUNC (\w+)", cmd):
            self.func = m.group(1)
        elif m := re.fullmatch(r":SOUR:RANG (\S+)", cmd):
            self.rang = float(m.group(1))

    def query(self, cmd):
        self.log.append(f"Q {cmd}")
        return {
            ":OUTP?": "1" if self.output else "0",
            ":SOUR:FUNC?": self.func,
            ":SOUR:RANG?": f"{self.rang:E}",
            ":SOUR:LEV?": f"{self.level:E}",
        }[cmd]

    def writes(self):
        return [entry[2:] for entry in self.log if entry.startswith("W ")]

    def close(self):
        self.closed = True


class RM:
    def __init__(self, dev):
        self.dev, self.opened = dev, []

    def open_resource(self, address):
        self.opened.append(address)
        return self.dev


# --- TWPA: enable_current_output_safely -------------------------------------------------------


def test_twpa_off_sets_level_zero_before_output_on():
    dev = ScriptedYoko(output=False, func="VOLT", rang=10.0, level=3.0)  # stale 3 V setpoint
    assert Y.enable_current_output_safely(dev, 1e-3) == 1e-3
    assert dev.writes() == [":SOUR:FUNC CURR", ":SOUR:RANG 0.001", ":SOUR:LEV 0", ":OUTP ON"]
    assert dev.level == 0.0 and dev.output and dev.func == "CURR"


def test_twpa_on_in_voltage_mode_refused_without_writes():
    dev = ScriptedYoko(output=True, func="VOLT", level=0.5)
    with pytest.raises(RuntimeError, match="VOLT"):
        Y.enable_current_output_safely(dev, 1e-3)
    assert dev.writes() == []


def test_twpa_on_in_current_mode_keeps_setpoint():
    dev = ScriptedYoko(output=True, func="CURR", rang=1e-3, level=11e-6)
    assert Y.enable_current_output_safely(dev, 1e-3) == 1e-3
    assert dev.writes() == [] and dev.level == 11e-6


def test_twpa_on_range_change_only_at_zero():
    dev = ScriptedYoko(output=True, func="CURR", rang=10e-3, level=0.0)
    assert Y.enable_current_output_safely(dev, 1e-3) == 1e-3
    assert dev.writes() == [":SOUR:RANG 0.001"]
    # nonzero level, larger active range: keep it, write nothing
    dev = ScriptedYoko(output=True, func="CURR", rang=10e-3, level=5e-6)
    assert Y.enable_current_output_safely(dev, 1e-3) == 10e-3
    assert dev.writes() == []
    # nonzero level, smaller active range than needed: refuse
    dev = ScriptedYoko(output=True, func="CURR", rang=1e-3, level=5e-6)
    with pytest.raises(RuntimeError, match="Ramp to 0"):
        Y.enable_current_output_safely(dev, 10e-3)
    assert dev.writes() == []


def test_ramp_current_starts_from_zero_after_enable(monkeypatch):
    monkeypatch.setattr(Y.time, "sleep", lambda s: None)
    dev = ScriptedYoko(output=False, func="CURR", rang=1e-3, level=20e-6)  # stale 20 uA
    Y.enable_current_output_safely(dev, 1e-3)
    Y.ramp_current(dev, 1e-6, 300e-9, dt=0.05)
    levels = [float(w.split()[1]) for w in dev.writes() if w.startswith(":SOUR:LEV ")]
    assert levels[0] == 0.0 and levels[-1] == pytest.approx(1e-6)
    assert max(abs(b - a) for a, b in zip(levels, levels[1:])) <= 300e-9 * 0.05 * (1 + 1e-9)


# --- charge line: open_charge_yoko ------------------------------------------------------------


def test_charge_off_sets_level_zero_before_output_on():
    dev = ScriptedYoko(output=False, func="CURR", rang=1e-3, level=2.0)
    dev_rang_after_volt = 10.0

    def write(cmd, _w=dev.write):
        _w(cmd)
        if cmd == ":SOUR:FUNC VOLT":
            dev.rang = dev_rang_after_volt  # range query applies to the active function

    dev.write = write
    rm = RM(dev)
    assert Y.open_charge_yoko(rm, "GPIB1::9::INSTR", 0.5) is dev
    assert dev.writes() == [":SOUR:FUNC VOLT", ":SOUR:LEV 0", ":OUTP ON"]
    assert dev.log.index("Q :SOUR:RANG?") > dev.log.index("W :SOUR:FUNC VOLT")


def test_charge_on_in_voltage_mode_leaves_level():
    dev = ScriptedYoko(output=True, func="VOLT", rang=10.0, level=0.3)
    Y.open_charge_yoko(RM(dev), "GPIB1::9::INSTR", 0.5)
    assert dev.writes() == [] and dev.level == 0.3


def test_charge_on_in_current_mode_refused_without_writes():
    dev = ScriptedYoko(output=True, func="CURR", rang=1e-3, level=11e-6)
    with pytest.raises(RuntimeError, match="current"):
        Y.open_charge_yoko(RM(dev), "GPIB1::9::INSTR", 0.0)
    assert dev.writes() == [] and dev.closed


@pytest.mark.parametrize(
    "addr",
    [
        "GPIB1::12::INSTR",
        " gpib1::12::instr ",
        "GPIB1::12",  # pyvisa opens these aliases as the same instrument
        "GPIB1::12::0::INSTR",
        "gpib1::12::0",
    ],
)
def test_charge_refuses_twpa_address(addr):
    # the TWPA source parked with its output OFF is the case the state check cannot catch
    rm = RM(ScriptedYoko(output=False, func="CURR"))
    with pytest.raises(ValueError, match="TWPA"):
        Y.open_charge_yoko(rm, addr, 0.0)
    assert rm.opened == []


@pytest.mark.parametrize("addr", ["GPIB1::9::INSTR", "GPIB0::12::INSTR", "GPIB1::120::INSTR"])
def test_charge_accepts_other_gpib_addresses(addr):
    rm = RM(ScriptedYoko(output=False))
    Y.open_charge_yoko(rm, addr, 0.0)
    assert rm.opened == [addr]


def test_charge_start_voltage_above_range_refused_before_output_on():
    dev = ScriptedYoko(output=False, func="VOLT", rang=1.0)
    with pytest.raises(ValueError, match="range"):
        Y.open_charge_yoko(RM(dev), "GPIB1::9::INSTR", 2.0)
    assert ":OUTP ON" not in dev.writes() and dev.closed
    Y.open_charge_yoko(RM(ScriptedYoko(output=False, rang=1.0)), "GPIB1::9::INSTR", 1.2)  # headroom


@pytest.mark.parametrize("output", [False, True])
def test_charge_30V_range_refused_before_output_on(output):
    # 1 mV resolution on the 30 V range would trip ramp_to's 1e-4 V read-back on sub-mV points
    dev = ScriptedYoko(output=output, func="VOLT", rang=30.0)
    with pytest.raises(ValueError, match="10 V range"):
        Y.open_charge_yoko(RM(dev), "GPIB1::9::INSTR", 0.0)
    assert ":OUTP ON" not in dev.writes() and ":SOUR:LEV 0" not in dev.writes() and dev.closed
    Y.open_charge_yoko(RM(ScriptedYoko(output=False, rang=10.0)), "GPIB1::9::INSTR", 0.0)


# --- ramp_to ----------------------------------------------------------------------------------


@pytest.mark.parametrize("target", [10.5, -10.5, -50.0])
def test_ramp_to_rejects_beyond_10V_both_signs(target):
    dev = ScriptedYoko(output=True)
    # message text is quoted in docs/troubleshooting.md: keep the two in sync
    with pytest.raises(ValueError, match="exceeds the 10 V charge-line limit"):
        Y.ramp_to(dev, target)
    assert dev.log == []


def test_ramp_to_reads_back_and_lands(monkeypatch):
    monkeypatch.setattr(Y.time, "sleep", lambda s: None)
    dev = ScriptedYoko(output=True, level=0.0)
    Y.ramp_to(dev, -0.0035)
    assert dev.log[-2:] == ["W :SOUR:LEV -0.0035", "Q :SOUR:LEV?"]
    assert dev.level == -0.0035


def test_ramp_to_readback_mismatch_raises(monkeypatch):
    monkeypatch.setattr(Y.time, "sleep", lambda s: None)
    dev = ScriptedYoko(output=True, level=0.0, clip=1.2)  # 1 V range clips at 1.2 V
    with pytest.raises(RuntimeError, match="clipped"):
        Y.ramp_to(dev, 1.25, step=0.05)


# --- the scripts call the helper before any ramp ---------------------------------------------


def _patch_script(monkeypatch, module, dev):
    monkeypatch.setattr("builtins.input", lambda *a: "yes")
    monkeypatch.setattr(Y.time, "sleep", lambda s: None)
    monkeypatch.setattr(module.pyvisa, "ResourceManager", lambda: RM(dev))


def test_set_bias_main_zeroes_level_before_output_on(monkeypatch):
    from qicklab.twpa import set_bias

    monkeypatch.setattr(set_bias, "TARGET_CURRENT_uA", 0.5)
    dev = ScriptedYoko(output=False, func="VOLT", rang=10.0, level=2.0)  # stale 2 V
    _patch_script(monkeypatch, set_bias, dev)
    set_bias.main()
    w = dev.writes()
    assert w[:4] == [":SOUR:FUNC CURR", ":SOUR:RANG 0.001", ":SOUR:LEV 0", ":OUTP ON"]
    assert dev.level == pytest.approx(0.5e-6) and dev.closed


def test_flux_sweep_refused_source_is_not_ramped_in_finally(monkeypatch, tmp_path):
    from qicklab.twpa import flux_sweep

    dev = ScriptedYoko(output=True, func="VOLT", rang=10.0, level=1.0)  # biasing in voltage mode
    _patch_script(monkeypatch, flux_sweep, dev)
    monkeypatch.setattr(flux_sweep, "SAVE_DIR", str(tmp_path))
    ramps = []
    monkeypatch.setattr(flux_sweep, "ramp_current", lambda *a, **k: ramps.append(a))
    with pytest.raises(RuntimeError, match="VOLT"):
        flux_sweep.main()
    assert ramps == []  # finally must not "ramp to 0 A" a source that is in voltage mode
    # the same fake answers the PNA-X open too; no level was written to the yoko
    assert not any(w.startswith(":SOUR:") or w.startswith(":OUTP") for w in dev.writes())
    assert dev.level == 1.0
