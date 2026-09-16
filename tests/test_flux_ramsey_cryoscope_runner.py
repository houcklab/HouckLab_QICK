import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from fluxpred import cryoscope, schema
from fluxpred.core import probe_delays, probe_fits_constant_segment

RUNNERS = {
    "q3": "WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/FluxRamseyCryoscope.py",
    "q5": "LabCode/Control/Flux_Tunable/FluxRamseyCryoscope.py",
}
COORDINATES = {"q3": (-25146.0, -14750.0), "q5": (0.156232010522, 0.387741615)}
FLUX_FIT = {"q3": [19.0, 0.22, 60000.0, 0.0, 0.1, 0.0],
            "q5": [19.0, 0.22, 1.0, 0.0, 0.1, 0.0]}
Q3_PRODUCTION_FLUX_FIT = [
    6.0089036599253225,
    0.24978861537376948,
    46821.65898343736,
    -16500.00011106883,
    0.4052706711778531,
    -5.54146293201133e-05,
]


def load_runner():
    root = Path(__file__).resolve().parent.parent
    for device, relative in RUNNERS.items():
        path = root/relative
        if path.exists():
            spec = importlib.util.spec_from_file_location(f"{device}_cryoscope_runner", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return device, module
    raise RuntimeError("no FluxRamseyCryoscope runner found in this repository")


DEVICE, RUNNER = load_runner()
PARK, TARGET = COORDINATES[DEVICE]
PARAMS = FLUX_FIT[DEVICE]


PREFIX = {"q3": "Q3", "q5": "Q5"}[DEVICE]


PULSE_NS = 400.0
READOUT_SPAN_NS = 3000.0


def plan(environ=None):
    return RUNNER.plan(park=PARK, target=TARGET, flux_fit_params=PARAMS, pulse_ns=PULSE_NS,
                       readout_span_ns=READOUT_SPAN_NS,
                       environ={} if environ is None else environ)


def test_runner_device_matches_the_repository():
    assert RUNNER.DEVICE == DEVICE


def test_static_flux_model_is_exported_in_the_schema_key_order():
    document = RUNNER.flux_fit_dict(PARAMS)
    assert set(document) == {"EJmax", "Ec", "period_volts", "phase_offset_volts", "d",
                             "tilt_slope"}
    assert all(np.isfinite(value) for value in document.values())


def test_flux_fit_dict_accepts_five_or_six_elements():
    five = RUNNER.flux_fit_dict(PARAMS[:5])
    assert five["tilt_slope"] == 0.0


def test_sensitivity_is_nonzero_between_park_and_target():
    settings = plan()
    assert abs(settings["sensitivity_mhz_per_unit"]) > 100.0


def test_window_ladder_covers_the_requested_range():
    windows = cryoscope.plan_window_ladder(25.0, finest_ns=500.0, ratio=5.0)
    assert cryoscope.window_unambiguous_range_mhz(min(windows)) >= 25.0
    assert max(windows) == 500.0


def test_an_unreachable_excursion_is_refused_with_an_actionable_message():
    with pytest.raises(ValueError, match="reduce the identification amplitude"):
        cryoscope.plan_window_ladder(470.0, finest_ns=500.0, ratio=5.0, max_rungs=3)


def test_ladder_pruning_drops_a_redundant_rung_but_keeps_the_ends():
    assert cryoscope.prune_ladder([416.0, 500.0, 2000.0]) == [416.0, 2000.0]
    assert cryoscope.prune_ladder([100.0, 400.0, 1600.0, 6400.0]) == [100.0, 400.0, 1600.0, 6400.0]


def test_effective_window_is_center_to_center():
    assert cryoscope.effective_window_ns(500.0, 400.0) == 900.0
    assert cryoscope.idle_window_ns(900.0, 400.0) == 500.0


def test_an_effective_window_shorter_than_the_pulse_is_refused():
    with pytest.raises(ValueError, match="not reachable"):
        cryoscope.idle_window_ns(300.0, 400.0)


def test_played_idle_windows_are_the_effective_windows_minus_the_pulse():
    settings = plan()
    for effective, idle in zip(settings["effective_windows_ns"], settings["windows_ns"]):
        assert effective-idle == pytest.approx(PULSE_NS)


def test_first_emission_segment_always_covers_the_probe_span():
    settings = plan()
    assert settings["schedule_first_ns"] >= settings["probe_span_ns"]


def test_expected_excursion_fits_the_coarsest_rung():
    settings = plan()
    assert settings["expected_excursion_mhz"] <= settings["coarsest_range_mhz"]


def test_a_longer_pulse_lowers_the_permitted_amplitude():
    short = RUNNER.plan(park=PARK, target=TARGET, flux_fit_params=PARAMS, pulse_ns=40.0,
                        readout_span_ns=READOUT_SPAN_NS, environ={})
    long = RUNNER.plan(park=PARK, target=TARGET, flux_fit_params=PARAMS, pulse_ns=2000.0,
                       readout_span_ns=READOUT_SPAN_NS, environ={})
    assert long["amplitude_ceiling"] < short["amplitude_ceiling"]


def test_plan_refuses_an_amplitude_above_the_ceiling():
    ceiling = plan()["amplitude_ceiling"]
    with pytest.raises(ValueError, match="exceeds the"):
        plan({f"{PREFIX}_CRYO_AMPLITUDE": repr(ceiling*2.0)})


def test_a_longer_minimum_idle_lowers_the_permitted_amplitude():
    wide = plan({f"{PREFIX}_CRYO_MIN_IDLE_NS": "16"})["amplitude_ceiling"]
    narrow = plan({f"{PREFIX}_CRYO_MIN_IDLE_NS": "2000"})["amplitude_ceiling"]
    assert narrow < wide


def test_plan_accepts_an_explicit_window_ladder():
    settings = plan({f"{PREFIX}_CRYO_WINDOWS_NS": "2000,416"})
    assert settings["effective_windows_ns"] == (416.0, 2000.0)


def test_plan_refuses_an_effective_window_shorter_than_the_pulse():
    with pytest.raises(ValueError, match="shorter than"):
        plan({f"{PREFIX}_CRYO_WINDOWS_NS": "2000,100"})


def test_identification_interval_avoids_the_production_park():
    settings = plan()
    assert settings["production_park"] == PARK
    assert settings["park"] != PARK
    assert abs(settings["branch_sensitivity_mhz_per_unit"][0.0]) >= 50.0
    assert abs(settings["branch_sensitivity_mhz_per_unit"][1.0]) >= 50.0


def test_explicit_identification_interval_is_honoured():
    span = TARGET-PARK
    settings = plan({f"{PREFIX}_CRYO_PARK_V": repr(PARK+0.2*span),
                     f"{PREFIX}_CRYO_TARGET_V": repr(PARK+0.6*span)})
    assert settings["park"] == pytest.approx(PARK+0.2*span)
    assert settings["target"] == pytest.approx(PARK+0.6*span)


@pytest.mark.skipif(DEVICE != "q3", reason="q3 production-fit regression")
def test_real_q3_fit_automatically_moves_identification_away_from_the_sweet_spot():
    settings = RUNNER.plan(
        park=-25146.0,
        target=-14750.0,
        flux_fit_params=Q3_PRODUCTION_FLUX_FIT,
        pulse_ns=PULSE_NS,
        readout_span_ns=READOUT_SPAN_NS,
        environ={},
    )

    assert settings["identification_interval_mode"] == "auto_high_sensitivity"
    assert settings["park"] == pytest.approx(-23066.8)
    assert settings["target"] == pytest.approx(-18908.4)
    assert min(abs(value) for value in settings["branch_sensitivity_mhz_per_unit"].values()) >= 50.0


@pytest.mark.skipif(DEVICE != "q3", reason="q3 production-fit regression")
def test_explicit_low_sensitivity_q3_interval_is_still_rejected():
    with pytest.raises(ValueError, match="sweet spot"):
        RUNNER.plan(
            park=-25146.0,
            target=-14750.0,
            flux_fit_params=Q3_PRODUCTION_FLUX_FIT,
            pulse_ns=PULSE_NS,
            readout_span_ns=READOUT_SPAN_NS,
            environ={
                "Q3_CRYO_PARK_V": "-24106.4",
                "Q3_CRYO_TARGET_V": "-19948.0",
            },
        )


@pytest.mark.skipif(DEVICE != "q3", reason="q3 production-coordinate regression")
def test_acquisition_config_anchors_the_waveform_at_the_identification_park():
    base = {"ff_park_gain": -25146.0, "other": 7}
    settings = {"park": -23066.8, "flux_fit_params": Q3_PRODUCTION_FLUX_FIT}

    configured = RUNNER.acquisition_config(base, {"threshold": 1.0}, settings)

    assert configured["ff_park_gain"] == -25146.0
    assert configured["cryoscope_park_gain"] == -23066.8
    assert configured["flux_fit_params"] == Q3_PRODUCTION_FLUX_FIT
    assert configured["calib_params"] == {"threshold": 1.0}


def test_plan_reports_an_amplitude_within_its_ceiling():
    settings = plan()
    assert 0.0 < settings["amplitude"] <= settings["amplitude_ceiling"]+1e-12
    assert settings["static_flux_model"]["Ec"] == PARAMS[1]


def test_built_command_holds_every_probe_inside_one_constant_segment():
    settings = plan()
    command, schedule, _ = RUNNER.build_command(settings)
    span = 2.0*40.0+max(settings["windows_ns"])
    delays = probe_delays(command, schedule, span_ns=span,
                          inset_ns=settings["probe_inset_ns"],
                          max_points=settings["max_delays"])
    assert len(delays) >= 20
    for delay in delays:
        assert probe_fits_constant_segment(command, delay, span)
    assert float(command.edges_ns[-1]) == pytest.approx(
        settings["hold_ns"]+settings["recovery_ns"])


def test_residual_run_loads_a_model_in_the_production_coordinate(tmp_path):
    document = schema.build_model_document(
        device=DEVICE,
        park=PARK,
        scale=TARGET-PARK,
        taus_us=[8.0, 24.0, 64.0, 192.0],
        coefficients=[0.01, -0.01, 0.01, -0.01],
        source_files=["raw.csv"],
        source_sha256=["a" * 64],
    )
    model_path = tmp_path / "candidate.json"
    model_path.write_text(json.dumps(document))
    settings = plan({f"{PREFIX}_CRYO_BASE_MODEL_JSON": str(model_path)})

    command, _, model = RUNNER.build_command(settings)

    assert settings["park"] != settings["production_park"]
    assert command.values.size > 1
    assert np.any(np.abs(model.coefficients) > 0)


def test_delay_grid_straddles_the_return_edge_on_both_sides():
    settings = plan()
    command, schedule, _ = RUNNER.build_command(settings)
    delays = probe_delays(command, schedule, span_ns=2.0*40.0+max(settings["windows_ns"]),
                          inset_ns=settings["probe_inset_ns"],
                          max_points=settings["max_delays"])
    hold = settings["hold_ns"]
    assert np.count_nonzero(delays < hold) >= 8
    assert np.count_nonzero(delays > hold) >= 8
    after = delays[delays > hold]
    assert float(np.min(after)-hold) <= 20_000.0
