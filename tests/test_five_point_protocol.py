"""Hardware-free contracts for the matched five-point production scan."""

import importlib
import csv
import json
import sys
import types

import numpy as np
import pytest

PREFIX = "WorkingProjects.TLS_Spectroscopy.Client_modules"


def analysis():
    spec = importlib.util.find_spec(f"{PREFIX}.Experiments.five_point_t1")
    assert spec is not None, "matched five-point analysis is not implemented"
    return importlib.import_module(spec.name)


@pytest.mark.parametrize("delays", [[10, 50], [10, 50, 200, 300], [0, 50, 200],
                                   [10, np.nan, 200], [10, 200, 50], [10, 10, 200]])
def test_delay_validation_rejects_invalid_protocol_axes(delays):
    with pytest.raises(ValueError):
        analysis().validate_five_point_delays(delays)


def test_binomial_fit_recovers_lifetime_and_shot_scaled_uncertainty():
    module = analysis()
    survival = 0.1 + 0.8 * np.exp(-np.array([10, 50, 200]) / 80)
    fitted = module.estimate_five_point_t1([0.1], [0.9], survival, [10, 50, 200],
                                         shots_per_condition=180)
    precise = module.estimate_five_point_t1([0.1], [0.9], survival, [10, 50, 200],
                                          shots_per_condition=720)
    assert fitted["T1_5pt_us"][0] == pytest.approx(80, rel=1e-4)
    assert fitted["T1_5pt_valid_mask"].tolist() == [1]
    assert fitted["fit_deviance"][0] < 1e-6
    assert fitted["T1_5pt_err_us"][0] > 0
    assert precise["T1_5pt_err_us"][0] == pytest.approx(fitted["T1_5pt_err_us"][0] / 2)


def test_uninformative_or_nonphysical_populations_are_marked_invalid():
    fitted = analysis().estimate_five_point_t1([0.5, np.nan, -1], [0.51, 0.9, 0.9],
                                               [[0.5]*3]*3, [10, 50, 200],
                                               shots_per_condition=180)
    assert fitted["T1_5pt_valid_mask"].tolist() == [0, 0, 0]
    assert np.isnan(fitted["T1_5pt_us"]).all()


def test_bidirectional_reduction_reverses_odd_shots_and_weights_odd_budget():
    # Acquisition positions: forward [0, 1], reverse [1, 0], forward [0, 0].
    values = np.array([[[0, 1, 0], [1, 0, 0]]])
    result = analysis().reduce_bidirectional_condition_states(values, ["P0"])
    np.testing.assert_allclose(result["P0"], [0, 2/3])
    np.testing.assert_allclose(result["P0_scan_up"], [0, 0.5])
    np.testing.assert_allclose(result["P0_scan_down"], [0, 1])
    assert result["dc_scan_up_shots"] == 2
    assert result["dc_scan_down_shots"] == 1
    canonical = values.copy()
    canonical[:, :, 1] = values[:, ::-1, 1]
    same = analysis().reduce_bidirectional_condition_states(canonical, ["P0"], canonical_dc_axis=True)
    np.testing.assert_equal(same["P0"], result["P0"])


def program_type():
    module = importlib.import_module(f"{PREFIX}.active_reset_OPX.programs")
    assert hasattr(module, "OPXResetT15PointProgram"), "resident five-point program missing"
    return module, module.OPXResetT15PointProgram


def test_resident_condition_order_matches_references_and_resets_every_record(monkeypatch):
    module, cls = program_type()
    prog = object.__new__(cls)
    prog.cfg = {"opx_t1_5pt_reference_hold_us": 2, "opx_t1_5pt_delays_us": [10, 50, 200],
                "opx_reset_scheme": "opx_unbounded", "qubit_ch": 1}
    prog.reset_page, prog.reset_regs = 0, {}
    prog.payload_calibration, prog.loop_calibration = object(), object()
    prog.reset_config = types.SimpleNamespace(inter_shot_delay_us=0)
    events = []
    prog._shot_park_callbacks = lambda: (lambda: None, lambda: None)
    prog._prepare_excited = lambda: events.append("pi")
    prog._wait_three_point_payload = lambda hold, flux: events.append((hold, flux))
    prog._measure_project = prog._set_reset_pulse = prog._wait_reset_ringdown = lambda: None
    prog.us2cycles = lambda x: x
    prog.sync_all = lambda x: None
    def emit(_prog, **kwargs):
        events.append(kwargs["label_prefix"])
        assert kwargs["reset_scheme"] == "opx_unbounded"
        kwargs["emit_payload"]()
        events.append("controller_reset")
    monkeypatch.setattr(module, "emit_payload_reset_shot", emit)
    prog._emit_t1_conditions({}, "POINT")
    assert events == ["POINT_P0", (2, True), "controller_reset",
                      "POINT_P1", "pi", (2, True), "controller_reset",
                      "POINT_PS0", "pi", (12, True), "controller_reset",
                      "POINT_PS1", "pi", (52, True), "controller_reset",
                      "POINT_PS2", "pi", (202, True), "controller_reset"]


def test_five_point_budget_and_lut_stream_size_preserve_three_point(monkeypatch):
    module, cls = program_type()
    def hardware_init(self, soccfg, cfg, *_args):
        self.cfg = cfg
    monkeypatch.setattr(module.OPXResetT1Program, "__init__", hardware_init)
    cfg = {"opx_t1_3pt_dc_gains": list(range(841)), "opx_t1_3pt_gain_lookup": True,
           "opx_t1_3pt_shots": 180, "opx_t1_5pt_delays_us": [10, 50, 200],
           "opx_t1_5pt_reference_hold_us": 2}
    board = {"tprocs": [{"dmem_size": 16384}]}
    prog = cls(board, cfg, None, None)
    assert prog.cfg["reps"] == 756900
    assert prog.cfg["opx_record_base"] == 848
    plan = module.resident_stream_plan(board, done_addr=1, record_base=848,
        record_words=prog.record_words, records_per_unit=prog._records_per_dc(),
        total_units=151380, records_per_shot=4205, total_shots=180)
    assert plan["bank_units"] == 776
    assert plan["bank_words"] == 7760
    assert plan["final_partial_units"] == 60
    assert 848 + 2*plan["bank_words"] == 16368
    with pytest.raises(ValueError, match="two complete"):
        module.resident_stream_plan({"tprocs": [{"dmem_size": 867}]}, done_addr=1,
            record_base=848, record_words=2, records_per_unit=5, total_units=151380,
            records_per_shot=4205, total_shots=180)
    three = module.OPXResetT13PointProgram(board, {**cfg, "opx_t1_3pt_wait_us": 100}, None, None)
    assert three.cfg["reps"] == 454140


def test_integration_canonicalizes_records_without_reordering_conditions(monkeypatch):
    module = importlib.import_module(f"{PREFIX}.active_reset_OPX.integration")
    assert hasattr(module, "acquire_t1_5pt_iq"), "five-point acquisition missing"
    class HardwareProgram:
        def __init__(self, board, cfg, *_args):
            self.cfg = cfg
            self._t1_ff_predistortion_mode = "stateful"
            self._t1_ff_predistortion_tail_us = 8.0
            self._t1_ff_predistortion_recovery_us = 25.0
            assert cfg["opx_resident_dmem_stream"] is True
        def us2cycles(self, *_args, **_kwargs):
            return 2
    monkeypatch.setattr(module, "OPXResetT15PointProgram", HardwareProgram)
    records = [types.SimpleNamespace(final_i=x*2, final_q=-x*2) for x in range(20)]
    def acquire(_soc, prog, _timeout, cfg, *, total_shots):
        assert total_shots == 2
        assert cfg["opx_t1_5pt_delays_us"] == [10, 50, 200]
        return records
    monkeypatch.setattr(module, "_run_program", acquire)
    i, q, telemetry = module.acquire_t1_5pt_iq(None, None,
        {"reset_mode": "passive", "read_length": 1, "ro_chs": [0]},
        dc_gains=[-100, -90], delays_us=[10, 50, 200], reference_hold_us=2,
        shots=2, reset_scheme="none")
    assert i.shape == (5, 2, 2)
    np.testing.assert_equal(i[0], [[0, 15], [5, 10]])
    np.testing.assert_equal(i[4], [[4, 19], [9, 14]])
    np.testing.assert_equal(q, -i)
    assert telemetry["records"] == 20
    assert telemetry["flux_predistortion_round_trip_mode"] == "stateful"
    assert telemetry["flux_predistortion_return_tail_us"] == 8.0
    assert telemetry["flux_predistortion_recovery_window_us"] == 25.0
    assert telemetry["flux_predistortion_tail_overlaps_payload_readout"] is True
    assert telemetry["p0_mode"] == "matched_frequency_resolved"
    assert telemetry["condition_names"] == ("P0", "P1", "Ps_10us", "Ps_50us", "Ps_200us")


def load_experiments(monkeypatch):
    # QICK and the single-shot experiment require hardware-only dependencies.
    monkeypatch.setitem(sys.modules, "qick", types.SimpleNamespace(AveragerProgram=object))
    monkeypatch.setitem(sys.modules, f"{PREFIX}.Experiments.mSingleShot1Q",
                        types.SimpleNamespace(discriminate_shots=lambda i, q, cal: i))
    name = f"{PREFIX}.Experiments.mT1VsFlux"
    monkeypatch.delitem(sys.modules, name, raising=False)
    return importlib.import_module(name)


def test_runner_defaults_enforce_the_production_comparison_budget(monkeypatch):
    load_experiments(monkeypatch)
    spec = importlib.util.find_spec(f"{PREFIX}.Runners.FivePointApplesToApples")
    assert spec is not None, "production five-point runner missing"
    runner = importlib.import_module(spec.name)
    cfg = runner.P6_5PT_APPLES_TO_APPLES
    assert cfg["decay_delays_us"] == [10, 50, 200]
    assert cfg["shots_per_condition"] == 180
    assert cfg["reset_mode"] == "active"
    assert cfg["shots_per_condition"] * 5 == 900
    assert cfg["freq_min_ghz"] == 3.8
    assert cfg["freq_max_ghz"] == 4.3
    assert cfg["freq_step_mhz"] == 0.5
    assert cfg["dc_min"] == -20550
    assert cfg["dc_max"] == -11800
    assert cfg["sync_session"] == "q3_q5_5pt_apples_20260914_v1"
    assert cfg["sync_directory"] == "Z:/FluxTeam/Data/.qick_qua_sync"
    assert cfg["sync_slot_s"] == 300


def test_production_runner_installs_latest_q3_p4_calibration(monkeypatch):
    load_experiments(monkeypatch)
    runner = importlib.import_module(
        f"{PREFIX}.Runners.FivePointApplesToApples"
    )
    tls = types.SimpleNamespace(BaseConfig={})
    runner.install_scan_calibration(tls)
    assert tls.FLUX_FIT_PARAMS == [
        6.0089036599253225,
        0.24978861537376948,
        46821.65898343736,
        -16500.00011106883,
        0.4052706711778531,
        -5.54146293201133e-05,
    ]
    assert tls.BASELINE_DC_OFFSET == -25146
    assert tls.TARGET_DC_OFFSET == -14750
    assert tls.BaseConfig["dt_pulseplay"] == 0.5
    assert tls.BaseConfig["dt_pulsedef"] == 0.002


def test_directional_uncertainty_diagnostics_and_provenance_reach_csv(monkeypatch, tmp_path):
    module = load_experiments(monkeypatch)
    assert hasattr(module, "T15PointVsFlux"), "five-point experiment missing"
    exp = object.__new__(module.T15PointVsFlux)
    exp.cfg = {"qua_shot_order": True}
    exp.soc = exp.soccfg = exp.calib_params = None
    exp.dc_vec = np.array([-100, -90])
    exp.decay_delays_us = np.array([10, 50, 200])
    exp.reference_hold_us, exp.shots = 2, 180
    exp.min_ref_contrast, exp.max_relative_error, exp.max_fit_t1_us = .05, 1, 3000
    exp.reset_mode, exp.element = "passive", "test"
    exp.acquisition_telemetry, exp.opx_reset_telemetry = [], []
    exp.data, exp.write_outputs = {}, False
    probabilities = [.1, .9, .806, .528, .166]
    states = np.array([[[int(s < p*180) for s in range(180)]]*2 for p in probabilities])
    telemetry = {"read_length_cycles": 2, "order": "shot_alternating_dc_P0_P1_Ps0_Ps1_Ps2"}
    monkeypatch.setattr(module, "acquire_t1_5pt_iq", lambda *a, **k: (states, states, telemetry))
    exp.acquire()
    spec = module.get_wall_clock_repeat_full_spec(exp)
    for direction in ("scan_up", "scan_down"):
        for key in ("T1_5pt_err_us", "T1_5pt_us_raw", "T1_5pt_fit_success", "T1_5pt_fit_deviance", "T1_5pt_valid_mask"):
            assert f"{key}_{direction}" in spec["scalar_columns"]
    assert "Ps_10us" in spec["scalar_columns"]


def test_series_appends_completed_rows_through_failure_and_overrun(monkeypatch, tmp_path):
    experiment_module = load_experiments(monkeypatch)
    runner = importlib.import_module(f"{PREFIX}.Runners.FivePointApplesToApples")
    monkeypatch.setattr(runner, "get_wall_clock_repeat_spec", lambda exp: {
        "metric_values": [.01], "metric_column_name": "inv_T1_5pt_per_us", "file_tag": "T1_5pt"})
    monkeypatch.setattr(runner, "get_wall_clock_repeat_full_spec", lambda exp: {})
    monkeypatch.setattr(runner, "save_wall_clock_repeat_full_outputs", experiment_module.save_wall_clock_repeat_full_outputs)
    compensation = {"source": "/calibration/generic_dc_compensation.json", "method": "rise_decay_bump_set_dc_offset_correction",
                    "metadata": {"qubit": "q3"}, "multipliers": [1.02, 1]}
    class Sync:
        enabled = True
        run = 0
        finished = []
        def corrected_clock(self):
            return 1000 + self.run * 300 + 350
        def wait_for_start(self, index, duration):
            self.run = index
            if index == 3:
                return None
            return {"sync_actual_start_epoch_s": 1000 + index * 300,
                    "sync_scheduled_end_epoch_s": 1300 + index * 300}
        def wait_for_end(self, index, **kwargs):
            self.finished.append((index, kwargs["status"]))
            return {"sync_slot_overrun_s": 50}
    def factory(metadata):
        def acquire(**kwargs):
            if metadata["wall_clock_run_index"] == 1:
                raise RuntimeError("scan failure")
        return types.SimpleNamespace(
            acquire=acquire, save_config=lambda: None, pname=str(tmp_path / "series.pkl"),
            dc_vec=[-100], data={"target_frequency_ghz": [4], "fit_frequency_ghz": [4],
                                "acquisition_order": "shot_alternating_dc_P0_P1_Ps0_Ps1_Ps2",
                                "flux_tail_compensation": compensation,
                                "correction_mode": "distortion-corrected",
                                "dc_scan_up_shots": 90, "dc_scan_down_shots": 90},
            CONDITION_NAMES=("P0", "P1", "Ps_10us", "Ps_50us", "Ps_200us"))
    sync = Sync()
    path = runner._run_series(factory, 2000, sync, lambda: None)
    with open(path, newline="") as file:
        rows = list(csv.DictReader(file))
    assert [row["wall_clock_run_index"] for row in rows] == ["0", "2"]
    assert sync.finished == [(0, "success"), (1, "failed"), (2, "success")]
    for row in rows:
        assert row["acquisition_order"] == "shot_alternating_dc_P0_P1_Ps0_Ps1_Ps2"
        assert row["acquisition_loop_order"] == "shot,frequency,condition"
        assert row["condition_order"] == "P0,P1,Ps_10us,Ps_50us,Ps_200us"
        assert row["reference_mode"] == "matched_frequency_resolved"
        assert float(row["correction_gain"]) == 1.0
        assert json.loads(row["condition_order_json"]) == ["P0", "P1", "Ps_10us", "Ps_50us", "Ps_200us"]
        assert json.loads(row["correction_provenance_json"]) == compensation
        assert float(row["sync_scan_duration_s"]) == 350
        assert float(row["sync_scan_overrun_s"]) == 50


def test_unsynchronized_series_obeys_duration_without_sync_timestamps(monkeypatch):
    load_experiments(monkeypatch)
    runner = importlib.import_module(f"{PREFIX}.Runners.FivePointApplesToApples")
    class Sync:
        enabled = False
        calls = 0
        def corrected_clock(self):
            self.calls += 1
            return self.calls * 10
        def wait_for_start(self, *args):
            if self.calls == 0 and len(runs) >= 5:
                return None
            return {}
        def wait_for_end(self, *args, **kwargs):
            return {}
    sync = Sync()
    runs = []
    def factory(metadata):
        runs.append(metadata)
        raise RuntimeError("scan failure")
    assert runner._run_series(factory, 25, sync, lambda: None) is None
    assert 0 < len(runs) < 4


def test_complete_resident_loop_traverses_all_frequencies_each_shot(monkeypatch):
    """Execute emitted tProc loop control; only RF/stream I/O is simulated."""
    module, cls = program_type()
    prog = object.__new__(cls)
    prog.cfg = {"qubit_ch": 1, "ff_ch": 2, "opx_t1_3pt_shots": 3,
                "opx_t1_3pt_dc_gains": [-100, -90, -80], "opx_resident_dmem_stream": True,
                "opx_t1_5pt_reference_hold_us": 2, "opx_t1_5pt_delays_us": [10, 50, 200]}
    prog.soccfg = {"tprocs": [{"dmem_size": 16384}]}
    prog.done_addr, prog.record_base = 1, 32
    prog.reset_config = types.SimpleNamespace(hard_flux_steps=True)
    prog._t1_ff_compensation = None
    prog.ch_page = lambda ch: ch
    monkeypatch.setattr(module, "_declare_common", lambda p: None)
    prog._declare_experiment = prog._begin_park_lifecycle = prog._end_park_lifecycle = lambda: None
    code = []
    for name in ("regwi", "safe_regwi", "memwi", "mathi", "math", "bitwi", "condj", "loopnz", "label", "end"):
        setattr(prog, name, lambda *args, op=name: code.append((op, args)))
    prog._emit_three_point_payload = lambda label, pi, ff, hold: code.append(("record", (pi, ff, hold)))
    prog._stream_after_shot = lambda: code.append(("boundary", ()))
    prog._finish_stream = lambda: None
    monkeypatch.setattr(module, "initialize_resident_stream", lambda p, **kwargs: setattr(p, "stream_plan", kwargs["plan"]))
    prog.make_program()
    assert prog.stream_plan["records_per_shot"] == 15
    assert prog.stream_plan["records_per_unit"] == 5
    assert prog.stream_plan["total_units"] == 9
    labels = {args[0]: index for index, (op, args) in enumerate(code) if op == "label"}
    regs, memory, records, boundaries = {}, {}, [], []
    pc = 0
    for _ in range(1000):
        op, args = code[pc]
        pc += 1
        if op == "end":
            break
        if op in ("label",):
            continue
        if op in ("regwi", "safe_regwi"):
            page, reg, value = args
            regs[page, reg] = value
        elif op in ("mathi", "math", "bitwi"):
            page, dst, src, operation, rhs = args
            left = regs.get((page, src), 0)
            right = regs.get((page, rhs), 0) if op == "math" else rhs
            regs[page, dst] = {"+": lambda: left+right, "-": lambda: left-right, "&": lambda: left & right}[operation]()
        elif op == "condj":
            page, left, comparison, right, label = args
            assert comparison == "=="
            if regs.get((page, left), 0) == regs.get((page, right), 0):
                pc = labels[label]
        elif op == "loopnz":
            page, reg, label = args
            if regs[page, reg] > 0:
                regs[page, reg] -= 1
                pc = labels[label]
        elif op == "memwi":
            page, reg, address = args
            memory[address] = regs[page, reg]
        elif op == "record":
            records.append((regs[2, prog._t1_3pt_regs["dc_gain"]], *args))
        elif op == "boundary":
            boundaries.append(len(records))
        else:
            raise AssertionError(op)
    else:
        pytest.fail("resident shot loop did not finish")
    assert [row[0] for row in records[::5]] == [-100, -90, -80, -80, -90, -100, -100, -90, -80]
    assert records[:5] == [(-100, False, True, 2), (-100, True, True, 2),
                           (-100, True, True, 12), (-100, True, True, 52), (-100, True, True, 202)]
    assert boundaries == [5, 10, 15, 20, 25, 30, 35, 40, 45]
    assert memory[1] == 45


@pytest.mark.parametrize("shots", [180.5, 0, np.nan])
def test_binomial_fit_rejects_noninteger_or_invalid_trial_budget(shots):
    with pytest.raises(ValueError, match="shots_per_condition"):
        analysis().estimate_five_point_t1([.1], [.9], [.8, .5, .2], [10, 50, 200], shots_per_condition=shots)


def test_integration_rejects_fractional_shots_before_hardware(monkeypatch):
    module = importlib.import_module(f"{PREFIX}.active_reset_OPX.integration")
    with pytest.raises(ValueError, match="integer"):
        module.acquire_t1_5pt_iq(None, None, {"reset_mode": "passive"}, dc_gains=[-100],
                                delays_us=[10, 50, 200], reference_hold_us=2, shots=180.5)


def test_common_provenance_preserves_an_explicit_zero_correction_gain():
    result = analysis().five_point_output_metadata({"flux_tail_compensation": {
        "correction_gain": 0., "multipliers": [1.], "segment_edges_ns": [0.],
    }}, ("P0", "P1", "Ps_10us", "Ps_50us", "Ps_200us"))
    assert result["correction_gain"] == 0.


@pytest.mark.parametrize("shots", [180.5, 0, 1, np.nan, np.inf])
@pytest.mark.parametrize("positional", [False, True])
def test_public_constructor_rejects_invalid_shots_before_base_setup(monkeypatch, shots, positional):
    module = load_experiments(monkeypatch)
    def unexpected_base(*args, **kwargs):
        pytest.fail("invalid shot budget reached base setup")
    monkeypatch.setattr(module._T1VsFluxBase, "__init__", unexpected_base)
    args = (None, None, "", "", "data", "data", {}, None, [-100], shots) if positional else ()
    kwargs = {} if positional else {"shots": shots}
    with pytest.raises(ValueError, match="integer of at least two"):
        module.T15PointVsFlux(*args, decay_delays_us=[10, 50, 200], **kwargs)


def test_synchronized_overrun_uses_slower_completion_and_keeps_series_alive(monkeypatch, tmp_path):
    module = importlib.import_module(f"{PREFIX}.CoreLib.global_slot_sync")
    sync = module.GlobalSlotSynchronizer(enabled=True, role="follower", session="q3_q5_5pt_apples_v1",
                                         directory=tmp_path, slot_s=300, boundary_guard_s=5)
    sync.first_start_epoch_s = sync.current_start_epoch_s = 1000
    sync.ntp = {"offset_s": 0, "offset_span_s": 0}
    sync.token = "test:123"
    monkeypatch.setattr(sync, "corrected_clock", lambda: 1350)
    monkeypatch.setattr(sync, "refresh_ntp_if_due", lambda: None)
    monkeypatch.setattr(module, "_await_completion", lambda *args: {"status": "success", "finish_epoch_s": 1700})
    result = sync.wait_for_end(0)
    assert result["sync_slot_overrun_s"] == 50
    assert result["sync_next_start_epoch_s"] == 1900
    assert sync.has_slot(1, 2000)
