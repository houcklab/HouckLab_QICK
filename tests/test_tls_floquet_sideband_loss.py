"""Controls for the targeted q3 modulation-sideband loss scan."""

import importlib

import numpy as np
import pytest


def experiment():
    return importlib.import_module(
        "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners."
        "TLSFloquetSidebandLoss")


def test_sideband_schedule_resolves_both_first_sidebands_and_reverses_order():
    module = experiment()
    specs = module.program_specs(4.104, shots=10)
    expected_offsets = [-34, -32, -30, -28, -26, 0, 26, 28, 30, 32, 34]
    assert [x["offset_mhz"] for x in specs[:11]] == expected_offsets
    assert [x["offset_mhz"] for x in specs[11:]] == expected_offsets[::-1]
    assert [x["center_ghz"] for x in specs[:11]] == [
        round(4.104 + offset / 1000, 3) for offset in expected_offsets]
    assert all(len(x["conditions"]) == 8 for x in specs)
    for spec in specs:
        assert {(c["post_drive_us"], c["modulation_amplitude_dac"],
                 c["preparation_state"]) for c in spec["conditions"]} == {
            (hold, amplitude, state) for hold in (1.6, 5.6)
            for amplitude in (0, 1000) for state in ("g", "e")}


def test_sideband_schedule_recenters_only_pending_second_block():
    module = experiment()
    specs = module.program_specs(4.104, shots=10)
    module.recenter_repeat(specs, center=4.106, repeat=1)
    assert specs[0]["center_ghz"] == 4.070
    assert specs[11]["center_ghz"] == 4.140
    assert all(x["feature_ghz"] == 4.106 for x in specs[11:])
    specs[11]["status"] = "complete"
    with pytest.raises(ValueError, match="acquired"):
        module.recenter_repeat(specs, center=4.108, repeat=1)


def test_sideband_preflight_requires_quiet_windows_on_both_sides():
    module = experiment()
    rows = []
    for i in range(251):
        freq = round(3.8 + .002 * i, 3)
        p25 = .25 if abs(freq - 4.104) < .004 else .55
        rows.append({"target_frequency_ghz": str(freq), "P0": ".10",
                     "P1": ".65", "Ps_25us": str(p25),
                     "P0_scan_up": ".10", "P1_scan_up": ".65",
                     "Ps_25us_scan_up": str(p25), "P0_scan_down": ".10",
                     "P1_scan_down": ".65", "Ps_25us_scan_down": str(p25)})
    report = module.validate_sideband_windows(rows, 4.104)
    assert report["usable"] is True
    assert report["left_advantage"] > .4
    assert report["right_advantage"] > .4
    for row in rows:
        if abs(float(row["target_frequency_ghz"]) - 4.074) <= .0041:
            row["Ps_25us"] = ".26"
            row["Ps_25us_scan_up"] = ".26"
            row["Ps_25us_scan_down"] = ".26"
    assert module.validate_sideband_windows(rows, 4.104)["usable"] is False


def test_sideband_preflight_rejects_a_second_loss_even_when_it_is_shallower():
    module = experiment()
    rows = []
    for i in range(251):
        freq = round(3.8 + .002 * i, 3)
        p25 = .25 if abs(freq - 4.104) < .004 else .55
        if 4.070 <= freq <= 4.078:
            p25 = .40  # normalized survival .545: quieter than center, but lossy
        rows.append({"target_frequency_ghz": str(freq), "P0": ".10",
                     "P1": ".65", "Ps_25us": str(p25),
                     "P0_scan_up": ".10", "P1_scan_up": ".65",
                     "Ps_25us_scan_up": str(p25), "P0_scan_down": ".10",
                     "P1_scan_down": ".65", "Ps_25us_scan_down": str(p25)})
    assert module.validate_sideband_windows(rows, 4.104)["usable"] is False


def test_sideband_scan_rejects_edges_outside_the_wide_scout():
    module = experiment()
    with pytest.raises(ValueError, match="outside"):
        module.program_specs(3.820, shots=10)


def test_30_mhz_corrected_waveforms_use_whole_cycles_and_fit_memory(monkeypatch):
    module = experiment()
    modulated = module.modulated
    monkeypatch.setattr(
        modulated.alternating.ShotAlternatingResidentProgram,
        "_declare_experiment", lambda self: None)
    monkeypatch.setattr(modulated, "_target_segments",
                        lambda _correction, *, pre_us, hold_us, recovery_us:
                        ([(1., pre_us)], [(1., hold_us + .01)],
                         [(1., recovery_us)]))
    monkeypatch.setattr(modulated, "ff_maxv", lambda *_args, **_kw: 32767)
    monkeypatch.setattr(modulated, "ff_envelope_samples", lambda *_args: 65536)
    program = object.__new__(modulated.ModulatedT1Program)
    program.cfg = {"ff_ch": 0, "ff_gain": -16047,
                   "ff_park_gain": -25146}
    program.soccfg = {"gens": [{"fs": 6881.28, "f_fabric": 430.08}]}
    program.holds_us = module.HOLDS_US
    program.pre_us = module.PRE_US
    program.ac_amplitude_dac = module.AMPLITUDE_DAC
    program.modulation_mhz = module.MODULATION_MHZ
    program._t1_ff_compensation = object()
    program._t1_ff_settle_us = .5
    program._t1_ff_predistortion_recovery_us = 40.
    program._ff_ramp_cache = {}
    program.us2cycles = lambda hold, **_kw: round(hold * 430.08)
    program.add_pulse = lambda **_kw: None
    program._declare_experiment()
    assert [program.ac_reports[str(hold)]["cycles_per_waveform"]
            for hold in module.HOLDS_US] == [48, 168]
    assert program.ff_envelope_report["total_samples"] < 65536
    assert all(np.max(np.abs(samples)) < 32767
               for samples in program.ac_waveforms.values())
