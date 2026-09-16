import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

_directory = os.path.dirname(os.path.abspath(__file__))
while _directory != os.path.dirname(_directory):
    if os.path.isdir(os.path.join(_directory, "WorkingProjects")):
        if _directory not in sys.path:
            sys.path.insert(0, _directory)
        break
    _directory = os.path.dirname(_directory)
else:
    raise RuntimeError("Could not find the HouckLab_QICK repo root.")

from fluxpred import cryoscope, measurement, schema
from fluxpred.core import probe_delays, render_on_schedule
from fluxpred.validation import shot_schedule
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import (
    flux_fit as fx, fluxpred_command as fpc,
)

DEVICE = "q3"
DEFAULTS = {
    "hold_us": 200.0,
    "recovery_us": 600.0,
    "shots": 300,
    "rounds": 2,
    "finest_window_ns": 1000.0,
    "ladder_ratio": 2.5,
    "schedule_first_us": 0.0,
    "schedule_growth": 1.2,
    "schedule_max_us": 100.0,
    "probe_inset_ns": 16.0,
    "max_delays": 40,
    "amplitude_safety": 0.8,
    "min_idle_ns": 16.0,
    "assumed_overshoot": 0.20,
    "park_fraction": 0.10,
    "target_fraction": 0.50,
    "min_sensitivity_mhz_per_unit": 50.0,
    "emission_quantum_ns": 1000.0,
}


def _env_float(name, fallback, environ=None):
    environ = os.environ if environ is None else environ
    value = environ.get(name)
    return float(value) if value not in (None, "") else float(fallback)


def _env_int(name, fallback, environ=None):
    environ = os.environ if environ is None else environ
    value = environ.get(name)
    return int(value) if value not in (None, "") else int(fallback)


def flux_fit_dict(params):
    ej, ec, period, offset, d, tilt = fx._coerce_params(params)
    return {"EJmax": ej, "Ec": ec, "period_volts": period, "phase_offset_volts": offset,
            "d": d, "tilt_slope": tilt}


def sensitivity_mhz_per_unit(params, park, target):
    step = max(abs(target-park)*1e-5, 1e-6)
    midpoint = 0.5*(park+target)
    high = fx.estimate_fit_frequency_ghz(params, midpoint+step)
    low = fx.estimate_fit_frequency_ghz(params, midpoint-step)
    return (high-low)/(2.0*step)*1000.0*(target-park)


def _identification_interval(frequency, *, production_park, production_target,
                             minimum_sensitivity, environ):
    """Choose a measurable interval without changing the production coordinate.

    The plant is assumed linear, so it may be identified away from a sweet spot.
    Explicit voltage overrides remain strict; automatic movement is only used for
    the default fractional interval.
    """
    span = float(production_target)-float(production_park)
    park_fraction = _env_float(
        "Q3_CRYO_PARK_FRACTION", DEFAULTS["park_fraction"], environ)
    target_fraction = _env_float(
        "Q3_CRYO_TARGET_FRACTION", DEFAULTS["target_fraction"], environ)
    explicit = any(
        str(environ.get(name, "")).strip()
        for name in ("Q3_CRYO_PARK_V", "Q3_CRYO_TARGET_V")
    )

    def coordinates(start_fraction, stop_fraction):
        park = _env_float(
            "Q3_CRYO_PARK_V",
            float(production_park)+float(start_fraction)*span,
            environ,
        )
        target = _env_float(
            "Q3_CRYO_TARGET_V",
            float(production_park)+float(stop_fraction)*span,
            environ,
        )
        return park, target

    amplitudes = tuple(np.linspace(0.0, 1.0, 9))
    id_park, id_target = coordinates(park_fraction, target_fraction)
    if explicit:
        report = cryoscope.assert_branch_sensitivity(
            frequency, park=id_park, target=id_target,
            minimum_mhz_per_unit=minimum_sensitivity,
            amplitudes=amplitudes,
        )
        return id_park, id_target, report, "explicit"

    try:
        report = cryoscope.assert_branch_sensitivity(
            frequency, park=id_park, target=id_target,
            minimum_mhz_per_unit=minimum_sensitivity,
            amplitudes=amplitudes,
        )
        return id_park, id_target, report, "preferred"
    except ValueError as preferred_error:
        width = target_fraction-park_fraction
        if not 0.0 < width <= 1.0:
            raise ValueError(
                "Q3 cryoscope identification fractions must define a positive interval "
                "inside the calibrated production span"
            ) from preferred_error
        starts = np.arange(0.0, 1.0-width+1e-12, 0.05)
        starts = sorted(starts, key=lambda value: (abs(value-park_fraction), value))
        for start in starts:
            if abs(start-park_fraction) < 1e-12:
                continue
            candidate_park = float(production_park)+float(start)*span
            candidate_target = float(production_park)+float(start+width)*span
            try:
                report = cryoscope.assert_branch_sensitivity(
                    frequency, park=candidate_park, target=candidate_target,
                    minimum_mhz_per_unit=minimum_sensitivity,
                    amplitudes=amplitudes,
                )
            except ValueError:
                continue
            return candidate_park, candidate_target, report, "auto_high_sensitivity"
        raise ValueError(
            "no high-sensitivity q3 Ramsey identification interval exists inside the "
            "calibrated production span; inspect the P4 flux fit before measuring"
        ) from preferred_error


def plan(*, park, target, flux_fit_params, pulse_ns, readout_span_ns, environ=None):
    environ = os.environ if environ is None else environ
    if flux_fit_params is None:
        raise RuntimeError(
            "FLUX_FIT_PARAMS is required: the cryoscope converts measured detuning to a flux "
            "coordinate through the static model")
    model = flux_fit_dict(flux_fit_params)
    frequency = lambda coordinate: fx.estimate_fit_frequency_ghz_array(flux_fit_params, coordinate)
    explicit = environ.get("Q3_CRYO_WINDOWS_NS", "").strip()
    requested_windows = ([float(value) for value in explicit.split(",")] if explicit else None)
    requested_amplitude = environ.get("Q3_CRYO_AMPLITUDE", "").strip()
    production_park = float(park)
    production_target = float(target)
    minimum_sensitivity = _env_float(
        "Q3_CRYO_MIN_SENSITIVITY", DEFAULTS["min_sensitivity_mhz_per_unit"], environ)
    id_park, id_target, sensitivity, interval_mode = _identification_interval(
        frequency,
        production_park=production_park,
        production_target=production_target,
        minimum_sensitivity=minimum_sensitivity,
        environ=environ,
    )
    probe = cryoscope.plan_probe(
        frequency, park=id_park, target=id_target, pulse_ns=float(pulse_ns),
        readout_span_ns=float(readout_span_ns),
        min_idle_ns=_env_float("Q3_CRYO_MIN_IDLE_NS", DEFAULTS["min_idle_ns"], environ),
        finest_effective_ns=_env_float("Q3_CRYO_FINEST_WINDOW_NS",
                                       DEFAULTS["finest_window_ns"], environ),
        ratio=_env_float("Q3_CRYO_LADDER_RATIO", DEFAULTS["ladder_ratio"], environ),
        overshoot=_env_float("Q3_CRYO_ASSUMED_OVERSHOOT", DEFAULTS["assumed_overshoot"], environ),
        inset_ns=_env_float("Q3_CRYO_PROBE_INSET_NS", DEFAULTS["probe_inset_ns"], environ),
        requested_amplitude=float(requested_amplitude) if requested_amplitude else None,
        requested_effective_windows_ns=requested_windows,
        emission_quantum_ns=DEFAULTS["emission_quantum_ns"],
        requested_first_ns=_env_float("Q3_CRYO_SCHEDULE_FIRST_US",
                                      DEFAULTS["schedule_first_us"], environ)*1000.0)
    settings = {"park": id_park, "target": id_target,
                "production_park": production_park, "production_target": production_target,
                "identification_interval_mode": interval_mode,
                "branch_sensitivity_mhz_per_unit": sensitivity, "flux_fit_params": flux_fit_params,
                "static_flux_model": model,
                "sensitivity_mhz_per_unit": sensitivity_mhz_per_unit(
                    flux_fit_params, float(park), float(target)),
                "windows_ns": probe["idle_windows_ns"],
                "effective_windows_ns": probe["effective_windows_ns"],
                "hold_ns": _env_float("Q3_CRYO_HOLD_US", DEFAULTS["hold_us"], environ)*1000.0,
                "recovery_ns": _env_float("Q3_CRYO_RECOVERY_US", DEFAULTS["recovery_us"], environ)*1000.0,
                "shots": _env_int("Q3_CRYO_SHOTS", DEFAULTS["shots"], environ),
                "rounds": _env_int("Q3_CRYO_ROUNDS", DEFAULTS["rounds"], environ),
                "schedule_growth": _env_float("Q3_CRYO_SCHEDULE_GROWTH",
                                              DEFAULTS["schedule_growth"], environ),
                "schedule_max_ns": _env_float("Q3_CRYO_SCHEDULE_MAX_US",
                                              DEFAULTS["schedule_max_us"], environ)*1000.0,
                "max_delays": _env_int("Q3_CRYO_MAX_DELAYS", DEFAULTS["max_delays"], environ),
                "model_json": environ.get("Q3_CRYO_BASE_MODEL_JSON", "").strip(),
                "note": environ.get("Q3_CRYO_NOTE", "center identification").strip()}
    settings.update(probe)
    settings["probe_inset_ns"] = probe["inset_ns"]
    return settings


def build_command(settings, *, quantum_ns=1000.0):
    model = None
    if settings["model_json"]:
        model, _ = schema.load_model(
            settings["model_json"], device=DEVICE,
            park=settings["production_park"],
            scale=settings["production_target"]-settings["production_park"],
            diagnostic_override=True)
    if model is None:
        model = fpc.identity_model(resolution_ns=max(quantum_ns, 1000.0))
    schedule = shot_schedule(
        amplitude=settings["amplitude"], hold_ns=settings["hold_ns"],
        recovery_ns=settings["recovery_ns"], first_ns=settings["schedule_first_ns"],
        growth=settings["schedule_growth"], max_ns=settings["schedule_max_ns"],
        quantum_ns=quantum_ns)
    command, _ = render_on_schedule(model, schedule)
    return command, schedule, model


def main():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mFluxRamseyCryoscope import (
        FluxRamseyCryoscope,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        FivePointApplesToApples as production_runner,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as tls

    production_runner.install_scan_calibration(tls)
    tls._set_yoko_if_requested()
    soc, soccfg = tls.makeProxy()
    clock_ns = fpc.fabric_clock_ns(soccfg, tls.BaseConfig["ff_ch"])
    x90_ns = fpc.qubit_pulse_ns(soccfg, channel=tls.BaseConfig["qubit_ch"],
                                sigma_us=float(tls.BaseConfig["sigma"]))
    x90_ns = fpc.round_up_to_clock(x90_ns, clock_ns)
    readout_span_ns = (float(tls.BaseConfig["read_length"])
                       + float(tls.BaseConfig.get("adc_trig_offset", 0.0))
                       + float(tls.BaseConfig.get("cryoscope_readout_margin_us", 1.0)))*1000.0
    settings = plan(park=tls._baseline_dc_offset(), target=tls.TARGET_DC_OFFSET,
                    flux_fit_params=tls.FLUX_FIT_PARAMS, pulse_ns=x90_ns,
                    readout_span_ns=readout_span_ns)
    quantum_ns = max(DEFAULTS["emission_quantum_ns"], 8.0*clock_ns)
    command, schedule, _ = build_command(settings, quantum_ns=quantum_ns)
    span = settings["probe_span_ns"]
    print(f"[ramsey] probe span {span/1000.0:.2f} us "
          f"(inset {settings['probe_inset_ns']:.0f} ns + 2 x {x90_ns:.0f} ns pulse + "
          f"{max(settings['windows_ns']):.0f} ns idle + {readout_span_ns/1000.0:.2f} us readout); "
          f"first emission segment {settings['schedule_first_ns']/1000.0:.1f} us")
    delays = probe_delays(command, schedule, span_ns=span,
                          inset_ns=settings["probe_inset_ns"],
                          max_points=settings["max_delays"])
    ideal = np.where(delays < settings["hold_ns"], settings["amplitude"], 0.0)
    probe_ghz = cryoscope.probe_frequencies(
        ideal,
        lambda coordinate: fx.estimate_fit_frequency_ghz_array(
            settings["flux_fit_params"], coordinate),
        park=settings["park"], target=settings["target"])

    print(f"[ramsey] device={DEVICE} park={settings['park']:+.1f} target={settings['target']:+.1f} "
          f"DAC_gain  amplitude={settings['amplitude']:.4f} (ceiling {settings['amplitude_ceiling']:.4f})")
    print(f"[ramsey] identification interval={settings['identification_interval_mode']} "
          f"sensitivity={min(abs(value) for value in settings['branch_sensitivity_mhz_per_unit'].values()):.1f}.."
          f"{max(abs(value) for value in settings['branch_sensitivity_mhz_per_unit'].values()):.1f} "
          "MHz per normalized unit")
    print(f"[ramsey] effective windows={[round(v) for v in settings['effective_windows_ns']]} ns "
          f"(idle {[round(v) for v in settings['windows_ns']]} ns), resolving "
          f"+-{settings['coarsest_range_mhz']:.3f} MHz down to "
          f"+-{settings['finest_range_mhz']:.3f} MHz; expected excursion "
          f"{settings['expected_excursion_mhz']:.3f} MHz")
    print(f"[ramsey] delays={len(delays)}  "
          f"shots={settings['shots']}  probe={float(probe_ghz.min()):.6f}.."
          f"{float(probe_ghz.max()):.6f} GHz")
    print(f"[ramsey] flux timeline {float(command.edges_ns[-1])/1000.0:.1f} us in "
          f"{len(schedule)} emissions, fabric clock {clock_ns:.4f} ns")
    acquisitions = len(delays)*(2+2*len(settings["windows_ns"]))
    per_shot_s = (float(command.edges_ns[-1])/1e9)+float(tls.BaseConfig.get("relax_delay", 500))/1e6
    print(f"[ramsey] {acquisitions} acquisitions x {settings['shots']} shots, "
          f"expect roughly {acquisitions*settings['shots']*per_shot_s/60.0:.1f} min of sequence time")

    calib_params = tls.run_step5_single_shot_cal(tls.outerFolder, soc, soccfg)
    cfg = dict(tls.BaseConfig)
    cfg["calib_params"] = calib_params
    cfg["flux_fit_params"] = settings["flux_fit_params"]
    experiment = FluxRamseyCryoscope(
        soc=soc, soccfg=soccfg, path=tls.QUBIT, outerFolder=tls.outerFolder,
        suffix="Flux_Ramsey_Cryoscope", cfg=cfg, command=command, delays_ns=delays,
        windows_ns=settings["windows_ns"], probe_freq_ghz=probe_ghz,
        scale_gain=settings["target"]-settings["park"], shots=settings["shots"],
        rounds=settings["rounds"], calib_params=calib_params, pulse_ns=x90_ns,
        hold_ns=settings["hold_ns"], recovery_ns=settings["recovery_ns"],
        readout_span_ns=readout_span_ns, save=True)
    data = experiment.acquire(progress=True)
    print(f"PICKLE={getattr(experiment, 'pname', getattr(experiment, 'fname', None))}")

    labels = ("g", "e")+measurement.quadrature_labels(len(settings["windows_ns"]))
    populations = {name: np.array([record["populations"][name] for record in data["records"]])
                   for name in labels}
    keeps = {name: np.array([record["keep_fraction"][name] for record in data["records"]])
             for name in labels}
    base = Path(experiment.fname).with_suffix("")
    static = flux_fit_dict(settings["flux_fit_params"])
    static["probe_frequency_ghz"] = float(probe_ghz[0])
    artifacts = measurement.write_measurement_artifacts(
        base, device=DEVICE, park=settings["production_park"],
        scale=settings["production_target"]-settings["production_park"],
        park_coordinate=settings["park"],
        target_coordinate=settings["target"], amplitude=settings["amplitude"],
        delays_ns=delays, effective_windows_ns=settings["effective_windows_ns"],
        idle_windows_ns=settings["windows_ns"], pulse_ns=x90_ns, shots=settings["shots"],
        rounds=settings["rounds"], recovery_ns=settings["recovery_ns"],
        hold_ns=settings["hold_ns"], command=command, populations=populations,
        keep_fractions=keeps, probe_frequency_ghz=probe_ghz, static_flux_model=static,
        frequency_of_coordinate=lambda coordinate: fx.estimate_fit_frequency_ghz_array(
            settings["flux_fit_params"], coordinate),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        code_commit=os.environ.get("Q3_CODE_COMMIT", "unknown"),
        operator_note=settings["note"])
    analysis = artifacts["analysis"]
    raw_path = artifacts["raw_csv"]
    command_path = artifacts["command_json"]
    summary_path = artifacts["summary_json"]

    print(f"[ramsey] supported fraction {analysis['supported_fraction']:.3f}, "
          f"{analysis['resolved']['ambiguous_count']} ambiguous branch point(s)")
    print(f"[ramsey] residual detuning span "
          f"{np.nanmin(analysis['residual_detuning_mhz']):+.3f} .. "
          f"{np.nanmax(analysis['residual_detuning_mhz']):+.3f} MHz")
    print(f"RAW_CSV={raw_path}")
    print(f"COMMAND_JSON={command_path}")
    print(f"SUMMARY_JSON={summary_path}")
    return summary_path


if __name__ == "__main__":
    main()
