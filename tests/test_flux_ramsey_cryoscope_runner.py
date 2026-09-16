import importlib.util
from pathlib import Path

import numpy as np
import pytest

from fluxpred import cryoscope
from fluxpred.core import probe_delays, probe_fits_constant_segment

RUNNERS = {
    "q3": "WorkingProjects/TLS_Spectroscopy/Client_modules/Runners/FluxRamseyCryoscope.py",
    "q5": "LabCode/Control/Flux_Tunable/FluxRamseyCryoscope.py",
}
COORDINATES = {"q3": (-25146.0, -14750.0), "q5": (0.156232010522, 0.387741615)}
FLUX_FIT = {"q3": [19.0, 0.22, 60000.0, 0.0, 0.1, 0.0],
            "q5": [19.0, 0.22, 1.0, 0.0, 0.1, 0.0]}


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


def plan(environ=None):
    return RUNNER.plan(park=PARK, target=TARGET, flux_fit_params=PARAMS,
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


def test_window_ladder_covers_the_coarsest_rung_range():
    windows = cryoscope.plan_window_ladder(
        cryoscope.window_unambiguous_range_mhz(20.0), finest_ns=500.0, ratio=5.0)
    assert windows == (20.0, 100.0, 500.0)
    assert cryoscope.window_unambiguous_range_mhz(windows[0]) >= 25.0


def test_an_unreachable_excursion_is_refused_with_an_actionable_message():
    with pytest.raises(ValueError, match="reduce the identification amplitude"):
        cryoscope.plan_window_ladder(470.0, finest_ns=500.0, ratio=5.0, max_rungs=3)


def test_amplitude_ceiling_shrinks_with_a_longer_coarsest_window():
    wide = cryoscope.max_identification_amplitude(
        sensitivity_mhz_per_unit=3000.0, overshoot=0.2, coarsest_window_ns=20.0)
    narrow = cryoscope.max_identification_amplitude(
        sensitivity_mhz_per_unit=3000.0, overshoot=0.2, coarsest_window_ns=100.0)
    assert narrow < wide


def test_plan_refuses_an_amplitude_above_the_ceiling():
    ceiling = plan()["amplitude_ceiling"]
    with pytest.raises(RuntimeError, match="exceeds the"):
        plan({f"{PREFIX}_CRYO_AMPLITUDE": repr(ceiling*2.0)})


def test_a_longer_coarsest_window_lowers_the_permitted_amplitude():
    wide = plan({f"{PREFIX}_CRYO_COARSEST_WINDOW_NS": "20"})["amplitude_ceiling"]
    narrow = plan({f"{PREFIX}_CRYO_COARSEST_WINDOW_NS": "100"})["amplitude_ceiling"]
    assert narrow < wide


def test_plan_accepts_an_explicit_window_ladder():
    settings = plan({f"{PREFIX}_CRYO_WINDOWS_NS": "500,100,20"})
    assert settings["windows_ns"] == (20.0, 100.0, 500.0)


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
