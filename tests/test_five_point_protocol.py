"""Hardware-free contracts for the matched five-point production scan."""

import importlib
import ast
import csv
import json
import sys
import types
from pathlib import Path

import numpy as np
import pytest

PREFIX = "WorkingProjects.TLS_Spectroscopy.Client_modules"


def analysis():
    spec = importlib.util.find_spec(f"{PREFIX}.Experiments.five_point_t1")
    assert spec is not None, "matched five-point analysis is not implemented"
    return importlib.import_module(spec.name)


def diagnostic():
    spec = importlib.util.find_spec(f"{PREFIX}.Runners.Test")
    assert spec is not None, "measurement-first QICK diagnostic is missing"
    return importlib.import_module(spec.name)


def test_qick_measurement_diagnostic_selects_small_contiguous_frequency_slice():
    module = diagnostic()
    frequencies = np.linspace(4.3, 3.8, 1001)
    dc_values = np.arange(1001)

    selected_frequency, selected_dc, selected_indices = (
        module.select_diagnostic_slice(
            frequencies, dc_values, center_ghz=4.05, points=11,
        )
    )

    assert selected_frequency.shape == (11,)
    assert selected_dc.shape == (11,)
    assert selected_indices.tolist() == list(range(495, 506))
    assert selected_frequency[5] == pytest.approx(4.05)
    assert np.allclose(np.diff(selected_frequency), -0.0005)


def test_q3_fresh_step3a_plan_is_uncorrected_high_snr_and_early_time_resolved():
    plan = diagnostic().fresh_step3a_plan({})

    assert plan["shots"] == 1000
    assert plan["spec_amp"] == 25000
    assert plan["frequency_window_mhz"] == [4000.0, 4100.0]
    assert plan["frequency_step_mhz"] == pytest.approx(0.5)
    assert plan["apply_flux_tail_compensation"] is False
    assert plan["compose_with_applied_flux_tail_compensation"] is False
    assert plan["readout_after_park"] is False
    assert plan["trace_polarity"] == "bright"
    delays = np.asarray(plan["delay_vector_us"], dtype=float)
    np.testing.assert_allclose(delays[:50], np.arange(0.5, 25.5, 0.5))
    np.testing.assert_allclose(delays[50:67], np.arange(27.0, 61.0, 2.0))
    np.testing.assert_allclose(delays[67:80], np.arange(65.0, 195.0, 10.0))
    np.testing.assert_allclose(delays[-2:], [197.0, 200.0])
    assert len(delays) == 82
    assert np.all(np.diff(delays) > 0)


def test_q3_fresh_step3a_can_probe_at_park_readout_without_wrong_polarity():
    plan = diagnostic().fresh_step3a_plan({
        "Q3_FRESH_3A_READOUT_AFTER_PARK": "on",
    })

    assert plan["readout_after_park"] is True
    assert plan["trace_polarity"] is None


def test_q3_template_refit_is_offline_and_uses_smooth_full_line_tracker():
    source = Path("Z:/FluxTeam/Data/q3_saved_step_response.pkl")
    plan = diagnostic().template_refit_plan({
        "Q3_TEMPLATE_REFIT_PKL": str(source),
    })

    assert plan["source_pkl"] == source
    assert plan["trace_tracking_mode"] == "image_template_causal"
    assert plan["trace_min_supported_fraction"] == pytest.approx(0.8)
    assert plan["trace_polarity"] == "dark"


def test_q3_fresh_step3b_matches_the_accepted_at_park_calibration_grid():
    plan = diagnostic().fresh_step3b_plan({})

    assert plan["shots"] == 500
    assert plan["apply_flux_tail_compensation"] is True
    assert plan["compose_with_applied_flux_tail_compensation"] is False
    assert plan["readout_after_park"] is True
    assert plan["trace_polarity"] is None
    assert plan["frequency_window_mhz"] == [4000.0, 4100.0]
    assert plan["frequency_step_mhz"] == pytest.approx(0.5)
    assert plan["delay_vector_us"] == diagnostic().fresh_step3a_plan(
        {"Q3_FRESH_3A_READOUT_AFTER_PARK": "on"}
    )["delay_vector_us"]


def test_qick_measurement_diagnostic_bypasses_legacy_ss_streamer():
    path = Path(diagnostic().__file__)
    tree = ast.parse(path.read_text())
    main = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    attributes = {
        node.attr for node in ast.walk(main) if isinstance(node, ast.Attribute)
    }
    assert "run_step5_single_shot_cal" not in attributes


def test_qick_measurement_diagnostic_applies_requested_accumulator_read_delay():
    """A requested hardware-read delay must reach the tProc run config."""
    module = diagnostic()
    cfg = {"shots": 20}

    delay = module.apply_diagnostic_read_delay(
        cfg,
        {"Q3_DIAGNOSTIC_READ_DELAY_US": "10"},
    )

    assert delay == pytest.approx(10.0)
    assert cfg == {"shots": 20, "opx_read_delay_us": 10.0}


def test_qick_measurement_diagnostic_skips_exhaustive_dmem_reads_by_default():
    module = diagnostic()
    assert hasattr(module, "apply_diagnostic_dmem_verification")
    cfg = {}

    enabled = module.apply_diagnostic_dmem_verification(cfg, {})

    assert enabled is False
    assert cfg["opx_verify_dmem_reads"] is False


def test_qick_measurement_diagnostic_reports_resident_shot_progress(monkeypatch):
    module = diagnostic()
    assert hasattr(module, "make_shot_progress")
    calls = []
    monkeypatch.setattr(
        module,
        "progress_counter",
        lambda iteration, total, **kwargs: calls.append(
            (iteration, total, kwargs)
        ),
    )

    callback = module.make_shot_progress(start_time=123.0)
    callback(7, 180)

    assert calls == [(
        6,
        180,
        {"start_time": 123.0, "label": "five-point diagnostic"},
    )]


def test_qick_measurement_diagnostic_uses_matching_clock_domains_for_timers():
    module = diagnostic()
    assert hasattr(module, "start_diagnostic_timers")

    elapsed_start, progress_start = module.start_diagnostic_timers(
        monotonic_clock=lambda: 456.0,
        wall_clock=lambda: 1_789_000_000.0,
    )

    assert elapsed_start == 456.0
    assert progress_start == 1_789_000_000.0


def test_qick_causality_plan_is_one_combined_21_delay_dataset_per_mode():
    """The temporary A/B result must expose the full requested delay grid."""
    plan = diagnostic().predistortion_causality_plan({})

    assert plan == {
        "target_frequencies_ghz": [3.9, 4.05, 4.3],
        "delays_us": [
            0.5, 1.0, 2.0, 3.0, 4.0, 6.0, 8.0,
            10.0, 12.0, 16.0, 20.0, 25.0, 30.0,
            40.0, 50.0, 65.0, 80.0, 100.0, 125.0,
            160.0, 200.0,
        ],
        "shots": 300,
        "reset_mode": "active",
        "modes": ("on", "off"),
    }


def test_qick_causality_partitions_21_delays_into_hardware_safe_triplets():
    """Each resident program stays within the measured 16,384-word PMem limit."""
    module = diagnostic()
    delays = module.predistortion_causality_plan({})["delays_us"]

    chunks = module.partition_delay_triplets(delays)

    assert chunks == [
        (0.5, 1.0, 2.0),
        (3.0, 4.0, 6.0),
        (8.0, 10.0, 12.0),
        (16.0, 20.0, 25.0),
        (30.0, 40.0, 50.0),
        (65.0, 80.0, 100.0),
        (125.0, 160.0, 200.0),
    ]


def test_qick_causality_combines_chunk_references_and_all_survivals():
    """Chunking changes transport only; the saved result remains one delay scan."""
    module = diagnostic()

    def directional(p0, p1, delays, survival):
        result = {
            "P0": np.asarray([p0]),
            "P0_scan_up": np.asarray([p0 + 0.01]),
            "P0_scan_down": np.asarray([p0 - 0.01]),
            "P1": np.asarray([p1]),
            "P1_scan_up": np.asarray([p1 + 0.01]),
            "P1_scan_down": np.asarray([p1 - 0.01]),
        }
        for delay, value in zip(delays, survival):
            name = f"Ps_{delay:g}us"
            result[name] = np.asarray([value])
            result[f"{name}_scan_up"] = np.asarray([value + 0.01])
            result[f"{name}_scan_down"] = np.asarray([value - 0.01])
        return result

    chunks = [
        {
            "delays_us": (1.0, 2.0, 3.0),
            "directional": directional(0.1, 0.9, (1, 2, 3), (0.8, 0.7, 0.6)),
        },
        {
            "delays_us": (4.0, 5.0, 6.0),
            "directional": directional(0.2, 0.8, (4, 5, 6), (0.5, 0.4, 0.3)),
        },
    ]

    combined = module.combine_causality_chunks(
        chunks, delays_us=[1, 2, 3, 4, 5, 6]
    )

    np.testing.assert_allclose(combined["P0"], [0.15])
    np.testing.assert_allclose(combined["P1"], [0.85])
    np.testing.assert_allclose(combined["Ps_1us"], [0.8])
    np.testing.assert_allclose(combined["Ps_6us"], [0.3])
    assert list(combined)[:2] == ["P0", "P0_scan_up"]


def test_qick_causality_normalizes_each_delay_with_its_local_chunk_references():
    """Repeated P0/P1 measurements remove drift between hardware chunks."""
    module = diagnostic()
    chunks = [
        {
            "delays_us": (1.0, 2.0, 3.0),
            "directional": {
                "P0": np.asarray([0.1]),
                "P1": np.asarray([0.9]),
                "Ps_1us": np.asarray([0.7]),
                "Ps_2us": np.asarray([0.7]),
                "Ps_3us": np.asarray([0.7]),
            },
        },
        {
            "delays_us": (4.0, 5.0, 6.0),
            "directional": {
                "P0": np.asarray([0.3]),
                "P1": np.asarray([0.7]),
                "Ps_4us": np.asarray([0.6]),
                "Ps_5us": np.asarray([0.6]),
                "Ps_6us": np.asarray([0.6]),
            },
        },
    ]

    summary = module.summarize_causality_chunks(
        chunks, delays_us=[1, 2, 3, 4, 5, 6], shots=300
    )

    np.testing.assert_allclose(summary["normalized"], [[0.75] * 6])
    np.testing.assert_allclose(summary["P0"], [0.2])
    np.testing.assert_allclose(summary["P1"], [0.8])


def test_qick_npoint_program_emits_all_21_delays_in_one_dc_visit():
    """A native audit point contains P0, P1, and every requested survival."""
    module = diagnostic()
    cls = module.make_npoint_program_class()
    delays = module.predistortion_causality_plan({})["delays_us"]
    program = object.__new__(cls)
    program.cfg = {
        "opx_t1_npoint_reference_hold_us": 2.0,
        "opx_t1_npoint_delays_us": delays,
    }
    emitted = []
    program._emit_tagged_condition = lambda *args: emitted.append(args)

    program._emit_t1_conditions({}, "POINT")

    assert program._records_per_dc() == 23
    assert len(emitted) == 23
    assert emitted[0] == ("POINT_P0", False, True, 2.0, 0)
    assert emitted[1] == ("POINT_P1", True, True, 2.0, 1)
    assert emitted[2] == ("POINT_PS0", True, True, 2.5, 2)
    assert emitted[-1] == ("POINT_PS20", True, True, 202.0, 22)


def test_qick_npoint_program_sizes_the_resident_stream_during_construction(monkeypatch):
    """The dynamic condition count must exist before the parent sizes DMem."""
    module = diagnostic()
    programs = importlib.import_module(
        f"{PREFIX}.active_reset_OPX.programs"
    )
    cls = module.make_npoint_program_class()
    monkeypatch.setattr(
        programs.OPXResetT1Program,
        "__init__",
        lambda self, _board, cfg, *_args: setattr(self, "cfg", cfg),
    )
    delays = module.predistortion_causality_plan({})["delays_us"]
    program = cls(
        {"tprocs": [{"dmem_size": 16384}]},
        {
            "opx_t1_3pt_dc_gains": [-100, -90, -80],
            "opx_t1_3pt_gain_lookup": True,
            "opx_t1_3pt_shots": 2,
            "opx_t1_npoint_delays_us": delays,
            "opx_t1_npoint_reference_hold_us": 2.0,
        },
        None,
        None,
    )

    assert program.cfg["reps"] == 2 * 3 * 23
    assert program._records_per_dc() == 23


def test_qick_npoint_acquisition_decodes_23_conditions_without_batching(monkeypatch):
    """The host decoder must retain all conditions and canonical scan direction."""
    module = diagnostic()
    integration = importlib.import_module(
        f"{PREFIX}.active_reset_OPX.integration"
    )
    delays = module.predistortion_causality_plan({})["delays_us"]

    class HardwareProgram:
        def __init__(self, board, cfg, *_args):
            self.cfg = cfg
            self._t1_ff_predistortion_mode = "stateful"
            self._t1_ff_predistortion_tail_us = 39.5
            self._t1_ff_predistortion_recovery_us = 40.0

        def us2cycles(self, *_args, **_kwargs):
            return 2

    records = [
        types.SimpleNamespace(
            final_i=value * 2,
            final_q=-value * 2,
            condition_tag=value % 23,
        )
        for value in range(2 * 2 * 23)
    ]

    def acquire(_soc, program, _timeout, cfg, *, total_shots, progress=None):
        assert isinstance(program, HardwareProgram)
        assert total_shots == 2
        assert cfg["opx_t1_npoint_delays_us"] == delays
        return records

    monkeypatch.setattr(integration, "_run_program", acquire)
    i_values, q_values, telemetry = module.acquire_t1_npoint_iq(
        None,
        None,
        {
            "reset_mode": "passive",
            "read_length": 1,
            "ro_chs": [0],
            "opx_diagnostic_condition_tags": True,
        },
        dc_gains=[-100, -90],
        delays_us=delays,
        reference_hold_us=2.0,
        shots=2,
        reset_scheme="none",
        program_class=HardwareProgram,
    )

    assert i_values.shape == (23, 2, 2)
    np.testing.assert_equal(i_values[0], [[0, 69], [23, 46]])
    np.testing.assert_equal(i_values[-1], [[22, 91], [45, 68]])
    np.testing.assert_equal(q_values, -i_values)
    assert telemetry["records_per_dc"] == 23
    assert telemetry["condition_names"][0:2] == ("P0", "P1")
    assert telemetry["condition_names"][-1] == "Ps_200us"
    assert telemetry["condition_tag_mismatches"] == 0
    assert telemetry["flux_predistortion_round_trip_mode"] == "stateful"


def test_qick_dense_summary_normalizes_every_delay_against_matched_references():
    """The comparison uses each mode's measured P0/P1 rather than raw Ps."""
    module = diagnostic()
    summary = module.summarize_dense_populations(
        [[0.1, 0.9, 0.9, 0.5, 0.1]],
        delays_us=[1.0, 2.0, 3.0],
        shots=100,
    )

    np.testing.assert_allclose(summary["normalized"], [[1.0, 0.5, 0.0]])
    assert summary["normalized_sigma"].shape == (1, 3)
    assert np.all(np.isfinite(summary["normalized_sigma"]))


def test_qick_sequence_audit_dispatches_before_the_small_diagnostic(monkeypatch):
    """The explicit audit flag must run only the native many-delay hardware test."""
    module = diagnostic()
    calls = []
    monkeypatch.setenv("Q3_T1_SEQUENCE_AUDIT", "on")
    monkeypatch.setattr(
        module,
        "run_predistortion_causality",
        lambda: calls.append("native-21-delay"),
    )

    module.main()

    assert calls == ["native-21-delay"]


def test_feedback_read_uses_qick_wait_all_sequence_when_requested():
    """The diagnostic timing mode must follow QICK's documented feedback order."""
    programs = importlib.import_module(
        f"{PREFIX}.active_reset_OPX.programs"
    )

    class Program:
        soccfg = {"readouts": [{"tproc_ch": 4}]}

        def __init__(self):
            self.calls = []

        def us2cycles(self, value):
            return int(round(100 * float(value)))

        def measure(self, **kwargs):
            self.calls.append(("measure", kwargs))

        def wait_all(self, cycles):
            self.calls.append(("wait_all", int(cycles)))

        def sync_all(self, cycles):
            self.calls.append(("sync_all", int(cycles)))

        def waiti(self, *args):
            self.calls.append(("waiti", args))

        def read(self, *args):
            self.calls.append(("read", args))

    program = Program()
    programs.emit_measure_and_read_feedback(
        program,
        cfg={
            "res_ch": 2,
            "ro_chs": [0],
            "adc_trig_offset": 0.25,
            "opx_feedback_read_timing": "official_wait_all",
        },
        read_delay_us=10.0,
        page=1,
        i_register=6,
        q_register=7,
    )

    assert program.calls == [
        (
            "measure",
            {
                "pulse_ch": 2,
                "adcs": [0],
                "adc_trig_offset": 25,
                "wait": False,
                "syncdelay": None,
            },
        ),
        ("wait_all", 1000),
        ("read", (4, 1, "lower", 6)),
        ("read", (4, 1, "upper", 7)),
    ]


def test_feedback_read_can_flush_one_accumulator_event_before_tproc_read():
    programs = importlib.import_module(
        f"{PREFIX}.active_reset_OPX.programs"
    )

    class Program:
        soccfg = {"readouts": [{"tproc_ch": 4}]}

        def __init__(self):
            self.calls = []

        def us2cycles(self, value):
            return int(round(100 * float(value)))

        def measure(self, **kwargs):
            self.calls.append(("measure", kwargs))

        def wait_all(self, cycles):
            self.calls.append(("wait_all", int(cycles)))

        def sync_all(self, cycles):
            self.calls.append(("sync_all", int(cycles)))

        def read(self, *args):
            self.calls.append(("read", args))

    program = Program()
    programs.emit_measure_and_read_feedback(
        program,
        cfg={
            "res_ch": 2,
            "ro_chs": [0],
            "adc_trig_offset": 0.25,
            "opx_feedback_read_timing": "official_wait_all",
            "opx_feedback_flush_measurement": True,
        },
        read_delay_us=10.0,
        page=1,
        i_register=6,
        q_register=7,
    )

    assert [name for name, _ in program.calls] == [
        "measure", "wait_all", "sync_all", "measure", "wait_all", "read", "read"
    ]
    assert program.calls[2] == ("sync_all", 100)


def test_feedback_read_can_flush_with_adc_trigger_without_second_readout_pulse():
    programs = importlib.import_module(
        f"{PREFIX}.active_reset_OPX.programs"
    )

    class Program:
        soccfg = {"readouts": [{"tproc_ch": 4}]}

        def __init__(self):
            self.calls = []

        def us2cycles(self, value):
            return int(round(100 * float(value)))

        def measure(self, **kwargs):
            self.calls.append(("measure", kwargs))

        def trigger(self, **kwargs):
            self.calls.append(("trigger", kwargs))

        def wait_all(self, cycles):
            self.calls.append(("wait_all", int(cycles)))

        def sync_all(self, cycles):
            self.calls.append(("sync_all", int(cycles)))

        def read(self, *args):
            self.calls.append(("read", args))

    program = Program()
    programs.emit_measure_and_read_feedback(
        program,
        cfg={
            "res_ch": 2,
            "ro_chs": [0],
            "adc_trig_offset": 0.25,
            "opx_feedback_read_timing": "official_wait_all",
            "opx_feedback_flush_mode": "adc_only",
        },
        read_delay_us=10.0,
        page=1,
        i_register=6,
        q_register=7,
    )

    assert [name for name, _ in program.calls] == [
        "measure", "wait_all", "sync_all", "trigger", "wait_all", "read", "read"
    ]
    assert program.calls[3] == (
        "trigger", {"adcs": [0], "adc_trig_offset": 25}
    )


def test_feedback_read_can_synchronize_all_timelines_before_original_measurement():
    programs = importlib.import_module(
        f"{PREFIX}.active_reset_OPX.programs"
    )

    class Program:
        soccfg = {"readouts": [{"tproc_ch": 4}]}

        def __init__(self):
            self.calls = []

        def us2cycles(self, value):
            return int(round(100 * float(value)))

        def measure(self, **kwargs):
            self.calls.append(("measure", kwargs))

        def wait_all(self, cycles):
            self.calls.append(("wait_all", int(cycles)))

        def sync_all(self, cycles):
            self.calls.append(("sync_all", int(cycles)))

        def read(self, *args):
            self.calls.append(("read", args))

    program = Program()
    programs.emit_measure_and_read_feedback(
        program,
        cfg={
            "res_ch": 2,
            "ro_chs": [0],
            "adc_trig_offset": 0.25,
            "opx_feedback_read_timing": "official_wait_all",
            "opx_feedback_pre_measure_sync": True,
        },
        read_delay_us=10.0,
        page=1,
        i_register=6,
        q_register=7,
    )

    assert [name for name, _ in program.calls] == [
        "sync_all", "measure", "wait_all", "read", "read"
    ]
    assert program.calls[0] == ("sync_all", 0)


def test_qick_diagnostic_selects_official_feedback_timing_by_default():
    module = diagnostic()
    cfg = {}

    mode = module.apply_diagnostic_feedback_timing(cfg, {})

    assert mode == "official_wait_all"
    assert cfg["opx_feedback_read_timing"] == "official_wait_all"


def test_qick_measurement_diagnostic_roundtrips_bulk_and_direct_dmem():
    module = diagnostic()

    class TProc:
        def __init__(self, words):
            self.words = list(words)

        def single_read(self, address):
            return self.words[int(address)]

        def single_write(self, address, value):
            self.words[int(address)] = int(value) & 0xFFFFFFFF

    class Soc:
        def __init__(self):
            self.tproc = TProc(range(64))

        def read_qick_dmem(self, address, length):
            return self.tproc.words[int(address):int(address) + int(length)]

        def write_qick_dmem(self, address, values):
            start = int(address)
            for offset, value in enumerate(values):
                self.tproc.words[start + offset] = int(value) & 0xFFFFFFFF
            return len(values)

    soc = Soc()
    before = list(soc.tproc.words)

    report = module.verify_dmem_roundtrip(soc, dmem_words=64, scratch_words=8)

    assert report["bulk_write_bulk_read_matches"] is True
    assert report["bulk_write_direct_read_matches"] is True
    assert report["direct_write_bulk_read_matches"] is True
    assert report["direct_write_direct_read_matches"] is True
    assert soc.tproc.words == before


def test_condition_tagged_payload_decoder_preserves_iq_and_tag_order():
    records = importlib.import_module(
        f"{PREFIX}.active_reset_OPX.records"
    )

    decoded = records.decode_condition_tagged_payload_records(
        [11, 12, 0, 21, 22, 1, 31, 32, 2],
        expected_records=3,
    )

    assert [record.final_i for record in decoded] == [11, 21, 31]
    assert [record.final_q for record in decoded] == [12, 22, 32]
    assert [record.condition_tag for record in decoded] == [0, 1, 2]


def test_dmem_read_verification_rejects_a_shifted_bulk_bank():
    acquisition = importlib.import_module(
        f"{PREFIX}.active_reset_OPX.acquisition"
    )

    class TProc:
        def __init__(self, words):
            self.words = list(words)

        def single_read(self, address):
            return self.words[int(address)]

    tproc = TProc([101, 102, 103, 104, 105])
    assert acquisition.verify_dmem_read_match(
        tproc,
        address=1,
        bulk_words=[102, 103, 104],
    ) == 3
    with pytest.raises(RuntimeError, match="first mismatch at DMem address 1"):
        acquisition.verify_dmem_read_match(
            tproc,
            address=1,
            bulk_words=[103, 104, 102],
        )


def test_integration_forwards_the_dmem_verification_switch(monkeypatch):
    integration = importlib.import_module(
        f"{PREFIX}.active_reset_OPX.integration"
    )
    observed = {}
    program = types.SimpleNamespace(stream_plan={})

    def run_stream(*args, **kwargs):
        observed.update(kwargs)
        return []

    monkeypatch.setattr(integration, "run_dmem_stream", run_stream)
    integration._run_program(
        object(),
        program,
        3.0,
        {"opx_verify_dmem_reads": True},
        total_shots=2,
    )

    assert observed["verify_dmem_reads"] is True


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


def test_five_point_diagnostic_writes_condition_tag_after_each_iq_record():
    _module, cls = program_type()
    prog = object.__new__(cls)
    prog.cfg = {
        "opx_t1_5pt_reference_hold_us": 2,
        "opx_t1_5pt_delays_us": [10, 50, 200],
        "opx_diagnostic_condition_tags": True,
    }
    prog.reset_page = 0
    prog.reset_regs = {"q": 7, "address": 8}
    events = []
    prog._emit_three_point_payload = lambda label, pi, ff, hold: events.append(
        ("payload", label, pi, ff, hold)
    )
    prog.regwi = lambda page, reg, value, *args: events.append(
        ("tag", page, reg, value)
    )
    prog.memw = lambda page, reg, address: events.append(
        ("memw", page, reg, address)
    )
    prog.mathi = lambda page, dst, src, op, value: events.append(
        ("advance", page, dst, src, op, value)
    )

    prog._emit_t1_conditions({}, "POINT")

    assert [event[3] for event in events if event[0] == "tag"] == [0, 1, 2, 3, 4]
    assert len([event for event in events if event[0] == "memw"]) == 5
    assert len([event for event in events if event[0] == "advance"]) == 5


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
    records = [
        types.SimpleNamespace(
            final_i=x * 2,
            final_q=-x * 2,
            condition_tag=x % 5,
        )
        for x in range(20)
    ]
    shot_progress = object()
    def acquire(_soc, prog, _timeout, cfg, *, total_shots, progress=None):
        assert total_shots == 2
        assert cfg["opx_t1_5pt_delays_us"] == [10, 50, 200]
        assert progress is shot_progress
        return records
    monkeypatch.setattr(module, "_run_program", acquire)
    i, q, telemetry = module.acquire_t1_5pt_iq(None, None,
        {
            "reset_mode": "passive",
            "read_length": 1,
            "ro_chs": [0],
            "opx_diagnostic_condition_tags": True,
        },
        dc_gains=[-100, -90], delays_us=[10, 50, 200], reference_hold_us=2,
        shots=2, reset_scheme="none", progress=shot_progress)
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
    assert telemetry["condition_tag_mismatches"] == 0
    assert telemetry["condition_tags_match_decoded_conditions"] is True


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
    assert cfg["freq_min_ghz"] == 3.9
    assert cfg["freq_max_ghz"] == 4.3
    assert cfg["freq_step_mhz"] == 0.5
    assert round(
        (cfg["freq_max_ghz"] - cfg["freq_min_ghz"])
        * 1000.0 / cfg["freq_step_mhz"]
    ) + 1 == 801
    assert cfg["dc_min"] == -20550
    assert cfg["dc_max"] == -11800
    assert cfg["sync_session"] == "q3_q5_5pt_apples_20260914_v1"
    assert cfg["sync_directory"] == "Z:/FluxTeam/Data/.qick_qua_sync"
    assert cfg["sync_slot_s"] == 150


def test_production_runner_applies_hardware_verified_feedback_timing(monkeypatch):
    """The seven-day scan must use the timing sequence that passed on q3."""
    load_experiments(monkeypatch)
    runner = importlib.import_module(
        f"{PREFIX}.Runners.FivePointApplesToApples"
    )
    assert hasattr(runner, "apply_verified_feedback_timing")
    cfg = {"unrelated": "preserved"}

    returned = runner.apply_verified_feedback_timing(cfg)

    assert returned is cfg
    assert cfg == {
        "unrelated": "preserved",
        "opx_feedback_read_timing": "official_wait_all",
        "opx_feedback_pre_measure_sync": True,
        "opx_feedback_flush_mode": "off",
        "opx_read_delay_us": 10.0,
    }


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


def test_explicit_q3_correction_path_is_forwarded_exactly_to_resolver(monkeypatch):
    load_experiments(monkeypatch)
    runner = importlib.import_module(
        f"{PREFIX}.Runners.FivePointApplesToApples"
    )
    requested = (
        "Z:/FluxTeam/Data/FTT02_AlOxJJ_2026_08_28/RFSOC/q3/"
        "q3_2026_09_15/validated_CANDIDATE.json"
    )
    calls = []

    override, compensation, mode = runner.resolve_production_correction(
        {"apply_flux_tail_compensation": True},
        lambda path: calls.append(path) or ({"source": path}, "distortion-corrected"),
        {"Q3_5PT_CORRECTION_JSON": f"  {requested}  "},
    )

    assert override == requested
    assert calls == [requested]
    assert compensation == {"source": requested}
    assert mode == "distortion-corrected"


def test_blank_q3_correction_override_preserves_automatic_discovery(monkeypatch):
    load_experiments(monkeypatch)
    runner = importlib.import_module(
        f"{PREFIX}.Runners.FivePointApplesToApples"
    )
    calls = []

    override, compensation, mode = runner.resolve_production_correction(
        {"apply_flux_tail_compensation": True},
        lambda path: calls.append(path) or ({"source": "auto.json"}, "distortion-corrected"),
        {"Q3_5PT_CORRECTION_JSON": "   "},
    )

    assert override is None
    assert calls == [None]
    assert compensation == {"source": "auto.json"}
    assert mode == "distortion-corrected"


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
    forwarded = {}
    def acquire(*args, **kwargs):
        forwarded["progress"] = kwargs.get("progress")
        return states, states, telemetry
    monkeypatch.setattr(module, "acquire_t1_5pt_iq", acquire)
    exp.acquire(progress=True)
    assert callable(forwarded["progress"])
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
