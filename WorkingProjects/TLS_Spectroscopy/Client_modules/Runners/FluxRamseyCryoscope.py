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
    "finest_window_ns": 500.0,
    "ladder_ratio": 5.0,
    "schedule_first_us": 2.0,
    "schedule_growth": 1.35,
    "schedule_max_us": 100.0,
    "probe_inset_ns": 8.0,
    "max_delays": 34,
    "amplitude_safety": 0.8,
    "coarsest_window_ns": 20.0,
    "assumed_overshoot": 0.20,
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


def plan(*, park, target, flux_fit_params, environ=None):
    environ = os.environ if environ is None else environ
    if flux_fit_params is None:
        raise RuntimeError(
            "FLUX_FIT_PARAMS is required: the cryoscope converts measured detuning to a flux "
            "coordinate through the static model")
    park = float(park)
    target = float(target)
    params = flux_fit_params
    sensitivity = sensitivity_mhz_per_unit(params, park, target)
    finest = _env_float("Q3_CRYO_FINEST_WINDOW_NS", DEFAULTS["finest_window_ns"], environ)
    ratio = _env_float("Q3_CRYO_LADDER_RATIO", DEFAULTS["ladder_ratio"], environ)
    overshoot = _env_float("Q3_CRYO_ASSUMED_OVERSHOOT", DEFAULTS["assumed_overshoot"], environ)
    coarsest = _env_float("Q3_CRYO_COARSEST_WINDOW_NS", DEFAULTS["coarsest_window_ns"], environ)
    explicit = environ.get("Q3_CRYO_WINDOWS_NS", "").strip()
    if explicit:
        windows = tuple(sorted(float(value) for value in explicit.split(",")))
    else:
        windows = cryoscope.plan_window_ladder(
            cryoscope.window_unambiguous_range_mhz(coarsest), finest_ns=finest, ratio=ratio)
    ceiling = cryoscope.max_identification_amplitude(
        sensitivity_mhz_per_unit=sensitivity, overshoot=overshoot,
        coarsest_window_ns=min(windows), safety=DEFAULTS["amplitude_safety"])
    amplitude = _env_float("Q3_CRYO_AMPLITUDE", min(ceiling, 1.0), environ)
    if amplitude > ceiling+1e-12:
        raise RuntimeError(
            f"Q3_CRYO_AMPLITUDE={amplitude:g} exceeds the {ceiling:.4f} the {min(windows):g} ns "
            f"coarsest rung can unwrap for an assumed {overshoot:.0%} overshoot at "
            f"{sensitivity:.0f} MHz per unit amplitude; lower the amplitude, shorten the coarsest "
            f"window, or start from an existing correction")
    return {"park": park, "target": target, "flux_fit_params": params,
            "static_flux_model": flux_fit_dict(params),
            "sensitivity_mhz_per_unit": sensitivity, "windows_ns": windows,
            "amplitude": amplitude, "amplitude_ceiling": ceiling, "overshoot": overshoot,
            "hold_ns": _env_float("Q3_CRYO_HOLD_US", DEFAULTS["hold_us"], environ)*1000.0,
            "recovery_ns": _env_float("Q3_CRYO_RECOVERY_US", DEFAULTS["recovery_us"], environ)*1000.0,
            "shots": _env_int("Q3_CRYO_SHOTS", DEFAULTS["shots"], environ),
            "rounds": _env_int("Q3_CRYO_ROUNDS", DEFAULTS["rounds"], environ),
            "schedule_first_ns": _env_float("Q3_CRYO_SCHEDULE_FIRST_US",
                                            DEFAULTS["schedule_first_us"], environ)*1000.0,
            "schedule_growth": _env_float("Q3_CRYO_SCHEDULE_GROWTH", DEFAULTS["schedule_growth"], environ),
            "schedule_max_ns": _env_float("Q3_CRYO_SCHEDULE_MAX_US",
                                          DEFAULTS["schedule_max_us"], environ)*1000.0,
            "probe_inset_ns": _env_float("Q3_CRYO_PROBE_INSET_NS", DEFAULTS["probe_inset_ns"], environ),
            "max_delays": _env_int("Q3_CRYO_MAX_DELAYS", DEFAULTS["max_delays"], environ),
            "model_json": environ.get("Q3_CRYO_BASE_MODEL_JSON", "").strip(),
            "note": environ.get("Q3_CRYO_NOTE", "center identification").strip()}


def build_command(settings, *, quantum_ns=1000.0):
    model = None
    if settings["model_json"]:
        model, _ = schema.load_model(
            settings["model_json"], device=DEVICE, park=settings["park"],
            scale=settings["target"]-settings["park"], diagnostic_override=True)
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
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as tls

    settings = plan(park=tls._baseline_dc_offset(), target=tls.TARGET_DC_OFFSET,
                    flux_fit_params=tls.FLUX_FIT_PARAMS)
    tls._set_yoko_if_requested()
    soc, soccfg = tls.makeProxy()
    clock_ns = fpc.fabric_clock_ns(soccfg, tls.BaseConfig["ff_ch"])
    quantum_ns = max(1000.0, 8.0*clock_ns)
    command, schedule, _ = build_command(settings, quantum_ns=quantum_ns)
    x90_ns = 4.0*float(tls.BaseConfig["sigma"])*1000.0
    span = 2.0*x90_ns+max(settings["windows_ns"])
    delays = probe_delays(command, schedule, span_ns=span,
                          inset_ns=settings["probe_inset_ns"],
                          max_points=settings["max_delays"])
    probe_ghz = fx.estimate_fit_frequency_ghz(
        settings["flux_fit_params"],
        settings["park"]+settings["amplitude"]*(settings["target"]-settings["park"]))

    print(f"[ramsey] device={DEVICE} park={settings['park']:+.1f} target={settings['target']:+.1f} "
          f"DAC_gain  amplitude={settings['amplitude']:.4f} (ceiling {settings['amplitude_ceiling']:.4f})")
    print(f"[ramsey] windows={list(settings['windows_ns'])} ns  delays={len(delays)}  "
          f"shots={settings['shots']}  probe={probe_ghz:.6f} GHz")
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
        hold_ns=settings["hold_ns"], recovery_ns=settings["recovery_ns"], save=True)
    data = experiment.acquire(progress=True)

    labels = ("g", "e")+measurement.quadrature_labels(len(settings["windows_ns"]))
    populations = {name: np.array([record["populations"][name] for record in data["records"]])
                   for name in labels}
    keeps = {name: np.array([record["keep_fraction"][name] for record in data["records"]])
             for name in labels}
    base = Path(experiment.dname)
    raw_path = measurement.write_raw_csv(
        base.with_name(base.name+"_raw.csv"), delays_ns=delays, populations=populations,
        keep_fractions=keeps, window_count=len(settings["windows_ns"]))
    command_path = measurement.write_command_json(
        base.with_name(base.name+"_command.json"), command)
    static = flux_fit_dict(settings["flux_fit_params"])
    static["probe_frequency_ghz"] = float(probe_ghz)
    raw = measurement.read_raw_csv(raw_path)
    ideal = np.where(delays < settings["hold_ns"], settings["amplitude"], 0.0)
    analysis = measurement.analyze(
        delays_ns=raw["delay_ns"], p_ground=raw["p_g"], p_excited=raw["p_e"],
        quadratures=measurement.quadratures_from_raw(raw, len(settings["windows_ns"])),
        windows_ns=settings["windows_ns"], probe_frequency_ghz=probe_ghz,
        frequency_of_coordinate=lambda coordinate: fx.estimate_fit_frequency_ghz_array(
            settings["flux_fit_params"], coordinate),
        park=settings["park"], target=settings["target"], shots=settings["shots"],
        ideal_amplitude=ideal)
    document = measurement.build_summary(
        device=DEVICE, park=settings["park"], scale=settings["target"]-settings["park"],
        park_coordinate=settings["park"], target_coordinate=settings["target"],
        normalized_amplitude=settings["amplitude"], delays_ns=delays,
        windows_ns=settings["windows_ns"], shots=settings["shots"], rounds=settings["rounds"],
        recovery_ns=settings["recovery_ns"], command=command, trace=analysis,
        static_flux_model=static,
        differentiator={"method": "fixed_window", "window_ns": float(max(settings["windows_ns"]))},
        timestamp=datetime.now().isoformat(timespec="seconds"),
        controller_commit=os.environ.get("Q3_CODE_COMMIT", "unknown"),
        code_commit=os.environ.get("Q3_CODE_COMMIT", "unknown"),
        operator_note=settings["note"],
        files={"raw_csv": measurement.describe_file(raw_path),
               "command_json": measurement.describe_file(command_path)})
    summary_path = measurement.write_summary(
        base.with_name(base.name+"_summary.json"), document)

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
