"""Contracts for measuring q3 fast-flux transfer with park Ramsey phase."""

import importlib
import json

import numpy as np
import pytest


MODULE = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.TLSFloquetTransferRamsey"


def experiment():
    return importlib.import_module(MODULE)


def test_plan_stays_at_park_and_covers_loss_sweep_frequencies():
    plan = experiment().plan()
    assert plan["bias"] == "q3 park"
    assert plan["reset_mode"] == "passive"
    assert plan["frequencies_mhz"] == [20.0, 30.0, 40.0]
    assert plan["amplitudes_dac"] == [600, 1000, 1400, 1700, 2000]
    assert plan["durations_us"] == [0.1, 0.2]
    assert plan["static_offsets_dac"] == [-700, 700]
    assert plan["ramsey_arms"] == ["g", "e", "i", "q"]
    assert plan["blocks"] == 2


def test_schedule_brackets_each_rate_and_duration_with_zero_ac():
    module = experiment()
    schedule = module.schedule(
        frequencies_mhz=(20.0, 40.0), amplitudes_dac=(600, 2000),
        durations_us=(0.1,), static_offsets_dac=(-700, 700))
    assert [row["name"] for row in schedule if row["block"] == 0] == [
        "b0_f20_t100_off_pre", "b0_f20_t100_a600", "b0_f20_t100_a2000",
        "b0_f20_t100_off_post", "b0_f40_t100_off_pre",
        "b0_f40_t100_a600", "b0_f40_t100_a2000",
        "b0_f40_t100_off_post", "b0_t100_static_m700",
        "b0_t100_static_p700"]
    assert [row["name"] for row in schedule if row["block"] == 1] == [
        "b1_t100_static_p700", "b1_t100_static_m700",
        "b1_f40_t100_off_post", "b1_f40_t100_a2000",
        "b1_f40_t100_a600", "b1_f40_t100_off_pre",
        "b1_f20_t100_off_post", "b1_f20_t100_a2000",
        "b1_f20_t100_a600", "b1_f20_t100_off_pre"]
    assert len({row["name"] for row in schedule}) == len(schedule)
    assert all(row["duration_us"] == .1 for row in schedule)


def test_park_waveform_has_integer_cycles_and_never_clips():
    module = experiment()
    for frequency, expected_cycles in ((20., 2), (30., 3), (40., 4)):
        wave, report = module.park_waveform(
            park_gain=-25146, amplitude_dac=2000, frequency_mhz=frequency,
            static_offset_dac=0, duration_us=.1,
            sample_rate_mhz=6881.28, fabric_rate_mhz=430.08,
            max_gain=32767)
        assert wave.dtype == np.int16
        assert wave.size == 688
        assert wave[0] == -25146
        assert report["cycles_per_waveform"] == expected_cycles
        assert report["actual_modulation_mhz"] == pytest.approx(frequency, abs=.02)
        assert wave.min() >= -27146
        assert wave.max() <= -23146
    static, report = module.park_waveform(
        park_gain=-25146, amplitude_dac=0, frequency_mhz=0,
        static_offset_dac=700, duration_us=.1,
        sample_rate_mhz=6881.28, fabric_rate_mhz=430.08,
        max_gain=32767)
    assert np.all(static == -24446)
    assert report["static_offset_dac"] == 700


def test_park_waveform_rejects_combined_ac_static_and_clipping():
    module = experiment()
    args = dict(park_gain=-25146, duration_us=.2,
                sample_rate_mhz=6881.28, fabric_rate_mhz=430.08,
                max_gain=32767)
    with pytest.raises(ValueError, match="exclusive"):
        module.park_waveform(**args, amplitude_dac=1000,
                             frequency_mhz=20, static_offset_dac=700)
    with pytest.raises(ValueError, match="DAC range"):
        module.park_waveform(**args, amplitude_dac=9000,
                             frequency_mhz=20, static_offset_dac=0)


def test_ramsey_phase_uses_local_ground_excited_references():
    module = experiment()
    result = module.ramsey_signal({"g": .1, "e": .9,
                                   "i": .7, "q": .5})
    assert result["reference_contrast"] == pytest.approx(.8)
    assert result["coherence_real"] == pytest.approx(.5)
    assert result["coherence_imag"] == pytest.approx(0.0)
    assert result["phase_rad"] == pytest.approx(0.0)
    assert result["valid"] is True
    with pytest.raises(ValueError, match="contrast"):
        module.ramsey_signal({"g": .4, "e": .5, "i": .45, "q": .45})


def test_park_ramsey_program_plays_ac_and_restores_exact_park():
    module = experiment()

    class FakeBase:
        def __init__(self, cfg):
            self.cfg = cfg
            self.soccfg = {"gens": [{"fs": 6881.28, "f_fabric": 430.08,
                                      "maxv": 32767, "maxv_scale": 1.0,
                                      "maxlen": 65536}]}
            self.pulses = []
            self.events = []
            self.initialize()

        def initialize(self):
            self.events.append("base_initialized")

        def us2cycles(self, duration, **_kw):
            return round(duration * 430.08)

        def add_pulse(self, **kwargs):
            self.pulses.append(kwargs)

        def set_pulse_registers(self, **kwargs):
            self.events.append(("registers", kwargs))

        def pulse(self, **kwargs):
            self.events.append(("pulse", kwargs))

        def sync_all(self, cycles):
            self.events.append(("sync", cycles))

    klass = module.make_program_class(FakeBase)
    cfg = {"ff_ch": 0, "ff_park_gain": -25146,
           "ff_gain": -25146, "ff_ramp_length": 4.0,
           "ramsey_park_idle_only": True, "ramsey_echo": False,
           "ramsey_flux_hold_us": .2,
           "transfer_amplitude_dac": 1000,
           "transfer_frequency_mhz": 40.0,
           "transfer_static_offset_dac": 0}
    program = klass(cfg)
    assert program.events[0] == "base_initialized"
    assert program.waveform_report["cycles_per_waveform"] == 8
    assert len(program.pulses) == 1
    assert program.pulses[0]["idata"].size == 1376
    assert program.memory_report["total_samples"] < 65536
    program._play_excursion()
    registers = [event[1] for event in program.events
                 if isinstance(event, tuple) and event[0] == "registers"]
    assert registers[0]["waveform"] == "q3_park_transfer"
    assert registers[-1]["gain"] == -25146
    assert registers[-1]["style"] == "const"
    assert len([event for event in program.events
                if isinstance(event, tuple) and event[0] == "pulse"]) == 2


def test_compiled_memory_report_checkpoints_with_numpy_cycle_count():
    module = experiment()

    class NumpyCycleBase:
        def __init__(self, cfg):
            self.cfg = cfg
            self.soccfg = {"gens": [{"fs": 6881.28, "f_fabric": 430.08,
                                      "maxv": 32767, "maxv_scale": 1.0,
                                      "maxlen": 65536}]}
            self.initialize()

        def initialize(self):
            pass

        def us2cycles(self, duration, **_kwargs):
            return np.int64(round(duration * 430.08))

        def add_pulse(self, **_kwargs):
            pass

    cfg = {"ff_ch": 0, "ff_park_gain": -25146,
           "ff_gain": -25146, "ff_ramp_length": 4.0,
           "ramsey_park_idle_only": True, "ramsey_echo": False,
           "ramsey_flux_hold_us": .1,
           "transfer_amplitude_dac": 1000,
           "transfer_frequency_mhz": 20.0,
           "transfer_static_offset_dac": 0}
    program = module.make_program_class(NumpyCycleBase)(cfg)
    checkpoint = {"preflight": [{"memory_report": program.memory_report,
                                  "waveform_report": program.waveform_report}]}
    json.dumps(checkpoint)


def test_phase_report_uses_both_zero_ac_brackets_within_one_block():
    module = experiment()
    entries = module.schedule(frequencies_mhz=(20.,),
                              amplitudes_dac=(1000,), durations_us=(.1,),
                              static_offsets_dac=())
    phases = {"off_pre": 0.0, "a1000": .4, "off_post": .2}
    for entry in entries:
        phase = next(value for suffix, value in phases.items()
                     if entry["name"].endswith(suffix))
        entry["signal"] = {"coherence_real": float(np.cos(phase)),
                           "coherence_imag": float(np.sin(phase)),
                           "valid": True}
    report = module.phase_report(entries)
    assert report["b0_f20_t100_a1000"]["phase_relative_to_off_rad"] == \
        pytest.approx(.3, abs=.002)
    assert report["b1_f20_t100_a1000"]["phase_relative_to_off_rad"] == \
        pytest.approx(.3, abs=.002)
    assert report["b0_f20_t100_a1000"]["off_bracket_drift_rad"] == \
        pytest.approx(.2)


def test_acquisition_saves_four_park_ramsey_arms_and_scores_local_phase(tmp_path):
    module = experiment()
    entry = module.schedule(frequencies_mhz=(20.,), amplitudes_dac=(1000,),
                            durations_us=(.1,), static_offsets_dac=())[1]
    seen = []

    class FakeProgram:
        def __init__(self, _soccfg, cfg):
            self.cfg = cfg
            self.waveform_report = {"actual_modulation_mhz": 20.0}
            self.memory_report = {"total_samples": 56000}
            self.park_transfer_waveform = np.arange(8, dtype=np.int16)
            seen.append((cfg["ramsey_arm"], cfg["transfer_amplitude_dac"],
                         cfg["transfer_frequency_mhz"], cfg["ramsey_flux_hold_us"]))

    def acquire(program, _soc):
        ones = {"g": 1, "e": 9, "i": 7, "q": 5}[program.cfg["ramsey_arm"]]
        iq = np.array([1] * ones + [0] * (10 - ones), dtype=float)
        return np.full(10, np.nan), np.full(10, np.nan), iq, np.zeros(10)

    result = module.acquire_entry(
        entry, soc=None, soccfg=None, base_cfg={},
        program_class=FakeProgram, acquire=acquire,
        discriminate=lambda i, q, _cal: i > .5,
        calib_params={}, folder=tmp_path, shots=10)
    assert seen == [(arm, 1000, 20., .1) for arm in ("g", "e", "i", "q")]
    assert result["signal"]["coherence_real"] == pytest.approx(.5)
    assert result["signal"]["coherence_imag"] == pytest.approx(0.)
    assert set(result["arms"]) == {"g", "e", "i", "q"}
    assert all((tmp_path / f"{entry['name']}_{arm}.npz").exists()
               for arm in ("g", "e", "i", "q"))
    assert (tmp_path / f"{entry['name']}_waveform.npz").exists()


def test_low_contrast_entry_keeps_raw_iq_and_marks_phase_invalid(tmp_path):
    module = experiment()
    entry = module.schedule(frequencies_mhz=(20.,), amplitudes_dac=(600,),
                            durations_us=(.1,), static_offsets_dac=())[1]

    class FakeProgram:
        def __init__(self, _soccfg, cfg):
            self.cfg = cfg
            self.waveform_report = {"actual_modulation_mhz": 20.0}
            self.memory_report = {"total_samples": 56000}
            self.park_transfer_waveform = np.arange(8, dtype=np.int16)

    result = module.acquire_entry(
        entry, soc=None, soccfg=None, base_cfg={},
        program_class=FakeProgram,
        acquire=lambda _program, _soc: (np.full(10, np.nan),
                                        np.full(10, np.nan),
                                        np.zeros(10), np.zeros(10)),
        discriminate=lambda i, q, _cal: i > .5,
        calib_params={}, folder=tmp_path, shots=10)
    assert result["signal"]["valid"] is False
    assert "contrast" in result["signal"]["error"]
    assert all((tmp_path / f"{entry['name']}_{arm}.npz").exists()
               for arm in ("g", "e", "i", "q"))


def test_phase_check_schedule_repeats_analysis_phases_in_reversed_blocks():
    rows = experiment().phase_check_schedule()
    assert len(rows) == 32
    assert len({row["name"] for row in rows}) == 32
    assert [row["analysis_phase_deg"] for row in rows[:4]] == [0, 90, 180, 270]
    assert rows[0]["kind"] == "off"
    assert rows[4]["kind"] == "static"
    assert rows[8]["frequency_mhz"] == 20.0
    assert rows[12]["frequency_mhz"] == 40.0
    assert rows[16]["block"] == 1
    assert rows[16]["name"].endswith("f40_a1700_p270")
    assert all(row["duration_us"] == .1 for row in rows)


def test_phase_check_acquisition_forwards_second_pulse_phase(tmp_path):
    module = experiment()
    entry = module.phase_check_schedule()[2]
    seen = {}

    class FakeProgram:
        def __init__(self, _soccfg, cfg):
            seen[cfg["ramsey_arm"]] = cfg["ramsey_q_phase_deg"]
            self.cfg = cfg
            self.waveform_report = {}
            self.memory_report = {}
            self.park_transfer_waveform = np.arange(8, dtype=np.int16)

    def acquire(program, _soc):
        n = {"g": 1, "e": 9, "i": 5, "q": 5}[program.cfg["ramsey_arm"]]
        iq = np.r_[np.ones(n), np.zeros(10 - n)]
        return np.full(10, np.nan), np.full(10, np.nan), iq, np.zeros(10)

    module.acquire_entry(
        entry, soc=None, soccfg=None, base_cfg={},
        program_class=FakeProgram, acquire=acquire,
        discriminate=lambda i, q, _cal: i > .5,
        calib_params={}, folder=tmp_path, shots=10)
    assert seen == {"g": 180, "e": 180, "i": 180, "q": 180}


def test_phase_check_report_separates_phase_shift_from_flat_off_axis():
    module = experiment()
    rows = module.phase_check_schedule()
    for row in rows:
        phi = 0.0 if row["kind"] == "off" else .4
        theta = np.deg2rad(row["analysis_phase_deg"])
        q = .5 + .3 * np.cos(theta - phi)
        row["arms"] = {arm: {"excited_fraction": value}
                       for arm, value in (("g", .1), ("e", .9),
                                          ("i", .8), ("q", q))}
    report = module.phase_check_report(rows)
    assert report["valid"] is True
    assert report["blocks"]["b0"]["off"]["fringe_span"] == pytest.approx(.6)
    assert report["blocks"]["b0"]["f20_a1700"]["phase_relative_off_rad"] == \
        pytest.approx(.4)
    for row in rows:
        if row["kind"] == "off":
            row["arms"]["q"]["excited_fraction"] = .5
    assert module.phase_check_report(rows)["valid"] is False


def test_phase_check_cli_plan_is_short_and_requires_no_hardware(capsys):
    module = experiment()
    assert module.main(["--plan", "--phase-check"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["mode"] == "phase_axis_check"
    assert printed["programs"] == 32
    assert printed["shots_per_arm"] == 200


def test_pulse_gain_schedule_reverses_order_and_keeps_zero_ac():
    rows = experiment().pulse_gain_schedule(gains=(2000, 4000))
    assert [(r["block"], r["pi2_gain"], r["analysis_phase_deg"])
            for r in rows] == [
                (0, 2000, 0), (0, 2000, 180),
                (0, 4000, 0), (0, 4000, 180),
                (1, 4000, 180), (1, 4000, 0),
                (1, 2000, 180), (1, 2000, 0)]
    assert all(r["amplitude_dac"] == 0 and r["static_offset_dac"] == 0
               and r["duration_us"] == .1 for r in rows)
    assert len({r["name"] for r in rows}) == len(rows)


def test_pulse_gain_report_requires_reproduced_phase_contrast():
    module = experiment()
    rows = module.pulse_gain_schedule(gains=(2000, 4000))
    for row in rows:
        gain = row["pi2_gain"]
        phase = row["analysis_phase_deg"]
        q = ({2000: {.0: .62, 180: .27},
              4000: {.0: .78, 180: .16}}[gain][phase])
        i = {2000: .62, 4000: .78}[gain]
        row["arms"] = {arm: {"excited_fraction": value}
                       for arm, value in (("g", .10), ("e", .85),
                                          ("i", i), ("q", q))}
    report = module.pulse_gain_report(rows)
    assert report["valid"] is True
    assert report["selected_pi2_gain"] == 4000
    assert report["gains"]["4000"]["minimum_phase_contrast"] == \
        pytest.approx(.62)
    for row in rows:
        if row["block"] == 1 and row["pi2_gain"] == 4000:
            row["arms"]["q"]["excited_fraction"] = .5
    assert module.pulse_gain_report(rows)["selected_pi2_gain"] == 2000
    for row in rows:
        if row["block"] == 1 and row["pi2_gain"] == 2000:
            row["arms"]["q"]["excited_fraction"] = .5
    assert module.pulse_gain_report(rows)["valid"] is False


def test_pulse_gain_report_rejects_program_drift_that_mimics_phase_axis():
    module = experiment()
    rows = module.pulse_gain_schedule(gains=(4000,))
    for row in rows:
        phase = row["analysis_phase_deg"]
        row["arms"] = {arm: {"excited_fraction": value}
                       for arm, value in (("g", .1), ("e", .85),
                                          ("i", .8 if phase == 0 else .3),
                                          ("q", .8 if phase == 0 else .3))}
    assert module.pulse_gain_report(rows)["valid"] is False


def test_pulse_gain_acquisition_overrides_only_pi2_gain(tmp_path):
    module = experiment()
    entry = module.pulse_gain_schedule(gains=(4000,))[0]
    seen = []

    class FakeProgram:
        def __init__(self, _soccfg, cfg):
            self.cfg = cfg
            self.waveform_report = {}
            self.memory_report = {}
            self.park_transfer_waveform = np.arange(8, dtype=np.int16)
            seen.append((cfg["qubit_pi_gain"], cfg["qubit_pi2_gain"],
                         cfg["ramsey_q_phase_deg"]))

    def acquire(program, _soc):
        n = {"g": 1, "e": 9, "i": 5, "q": 8}[program.cfg["ramsey_arm"]]
        iq = np.r_[np.ones(n), np.zeros(10 - n)]
        return np.full(10, np.nan), np.full(10, np.nan), iq, np.zeros(10)

    module.acquire_entry(
        entry, soc=None, soccfg=None,
        base_cfg={"qubit_pi_gain": 13500, "qubit_pi2_gain": 6750},
        program_class=FakeProgram, acquire=acquire,
        discriminate=lambda i, q, _cal: i > .5,
        calib_params={}, folder=tmp_path, shots=10)
    assert seen == [(13500, 4000, 0)] * 4


def test_pulse_gain_check_cli_plan_is_hardware_free(capsys):
    module = experiment()
    assert module.main(["--plan", "--pulse-gain-check"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["mode"] == "pulse_gain_check"
    assert printed["bias"] == "q3 park"
    assert printed["programs"] == 4 * len(printed["pi2_gains"])


def test_transfer_plan_accepts_selected_pi2_gain_and_rejects_bad_values(capsys):
    module = experiment()
    assert module.main(["--plan", "--phase-check", "--pi2-gain", "4000"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["qubit_pi2_gain"] == 4000
    with pytest.raises(ValueError, match="pi/2 gain"):
        module.plan(pi2_gain=0)
    with pytest.raises(ValueError, match="gain check"):
        module.plan(pulse_gain_check=True, pi2_gain=4000)
