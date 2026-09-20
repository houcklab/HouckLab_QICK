"""Step-1 raw readout characterisation for q3.

This runner intentionally reports measured resonator centres, linewidth, and
qubit frequency only.  It does not calculate chi, Purcell, coupling, or an
anharmonicity.  Values that require a separate measurement are explicitly
written as null in the JSON artifact.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
from pathlib import Path

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_fit as fx
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import (
    readout_characterization as characterisation,
)


QUBIT = "q3"


def _bool(environ, key, default=False):
    return str(environ.get(key, str(int(default)))).strip().lower() in {
        "1", "true", "yes", "on",
    }


def runtime_settings(environ=None):
    env = os.environ if environ is None else environ
    target_gain = env.get("Q3_STEP1_TARGET_GAIN_DAC")
    return {
        "target_frequency_ghz": float(env.get("Q3_STEP1_TARGET_FREQUENCY_GHZ", "4.100")),
        "target_gain_dac": None if target_gain in (None, "") else int(target_gain),
        "readout_shots": int(env.get("Q3_STEP1_READOUT_SHOTS", "300")),
        "qubit_spec_shots": int(env.get("Q3_STEP1_QUBIT_SPEC_SHOTS", "300")),
        "qubit_spec_points": int(env.get("Q3_STEP1_QUBIT_SPEC_POINTS", "161")),
        "qubit_spec_span_mhz": float(env.get("Q3_STEP1_QUBIT_SPEC_SPAN_MHZ", "80")),
        "resonator_span_mhz": float(env.get("Q3_STEP1_RESONATOR_SPAN_MHZ", "4.0")),
        "resonator_step_mhz": float(env.get("Q3_STEP1_RESONATOR_STEP_MHZ", "0.05")),
        "readout_gain_dac": int(env.get("Q3_STEP1_READOUT_GAIN_DAC", "1880")),
        "relax_delay_us": float(env.get("Q3_STEP1_RELAX_DELAY_US", "100.0")),
        "fef_mode": "unmeasured",
        "plot": _bool(env, "Q3_STEP1_PLOT", False),
    }


def gain_for_frequency(*, flux_fit_params, frequency_ghz, lo=-25146, hi=-14750):
    """Invert q3's monotonic production branch without selecting another branch."""
    grid = np.linspace(float(lo), float(hi), 200_001)
    frequencies = fx.estimate_fit_frequency_ghz_array(flux_fit_params, grid)
    order = np.argsort(frequencies)
    requested = float(frequency_ghz)
    if requested < frequencies[order[0]] or requested > frequencies[order[-1]]:
        raise ValueError(
            f"target {requested:.6f} GHz is outside q3 production branch "
            f"{frequencies[order[0]]:.6f}..{frequencies[order[-1]]:.6f} GHz"
        )
    return int(round(np.interp(requested, frequencies[order], grid[order])))


def predicted_resonator_mhz(gain, params):
    f_bare, g, ejmax, ec, period, offset, d = [float(v) for v in params]
    phase = np.pi * (float(gain) - offset) / period
    ej = ejmax * np.sqrt(np.cos(phase) ** 2 + d ** 2 * np.sin(phase) ** 2)
    fq = 1e9 * (np.sqrt(8.0 * ej * ec) - ec)
    delta = f_bare - fq
    dressed = (0.5 * (f_bare + fq)
               + 0.5 * np.sign(delta) * np.sqrt(delta ** 2 + 4.0 * g ** 2))
    return float(dressed / 1e6)


def _axis(center_mhz, span_mhz, step_mhz):
    return np.arange(center_mhz - span_mhz, center_mhz + span_mhz + 0.5 * step_mhz,
                     step_mhz, dtype=float)


def _fit_trace(frequency_mhz, magnitude_dbm, fitter):
    fit, errors = fitter(frequency_mhz, magnitude_dbm)
    if fit is None:
        raise RuntimeError("resonator fit returned no result")
    result = {"centre_MHz": float(fit["fr"]), "fwhm_MHz": abs(float(fit["fwhm"])),
              "fit_errors": None if errors is None else {k: float(v) for k, v in errors.items()}}
    edge = min(abs(result["centre_MHz"] - float(np.min(frequency_mhz))),
               abs(result["centre_MHz"] - float(np.max(frequency_mhz))))
    result["edge_margin_MHz"] = edge
    result["inside_scan_window"] = bool(edge >= 2.0 * float(frequency_mhz[1] - frequency_mhz[0]))
    return result


def _write_outputs(*, outer_folder, settings, report, rows, source_experiments):
    now = dt.datetime.now()
    data_dir = Path(outer_folder) / QUBIT / f"{QUBIT}_{now:%Y_%m_%d}"
    data_dir.mkdir(parents=True, exist_ok=True)
    stem = data_dir / f"{QUBIT}_{now:%H_%M_%S}_Step1_Readout_Characterisation"
    payload = {
        QUBIT + "_AlOx": report,
        "run_settings": settings,
        "raw_trace_csv": str(stem.with_name(stem.name + "_raw_traces.csv")),
        "source_experiments": source_experiments,
    }
    json_path = stem.with_suffix(".json")
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    csv_path = stem.with_name(stem.name + "_raw_traces.csv")
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["scan", "state", "frequency_MHz", "magnitude_dB"])
        writer.writeheader()
        writer.writerows(rows)
    return json_path, csv_path


def main():
    # Hardware imports live here so the settings and pure helpers remain offline-testable.
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import BaseConfig, outerFolder
    from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mQubitSpec import QubitSpec
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mTransmission import Transmission
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import fit_functions as fits
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as tls

    settings = runtime_settings()
    target_gain = (settings["target_gain_dac"] if settings["target_gain_dac"] is not None
                   else gain_for_frequency(flux_fit_params=tls.FLUX_FIT_PARAMS,
                                           frequency_ghz=settings["target_frequency_ghz"]))
    predicted_q_mhz = 1e3 * fx.estimate_fit_frequency_ghz(tls.FLUX_FIT_PARAMS, target_gain)
    predicted_r_mhz = predicted_resonator_mhz(target_gain, tls.RESONATOR_FIT_PARAMS)
    low_gain = max(1, int(round(settings["readout_gain_dac"] * 10.0 ** (-6.0 / 20.0))))
    resonator_axis = _axis(predicted_r_mhz, settings["resonator_span_mhz"],
                           settings["resonator_step_mhz"])

    print("[step1] q3 readout characterisation: raw quantities only")
    print(f"[step1] target predicted f_q={predicted_q_mhz / 1e3:.6f} GHz; "
          f"ff gain={target_gain:+d} DAC; predicted f_r={predicted_r_mhz:.4f} MHz")
    print(f"[step1] resonator scans: {resonator_axis[0]:.3f}..{resonator_axis[-1]:.3f} MHz "
          f"({len(resonator_axis)} points), gains {settings['readout_gain_dac']} and {low_gain} (-6 dB)")
    print("[step1] f_ef, source dBm/attenuation, and internal/external kappa are intentionally null: "
          "they are not directly measured by this runner.")

    soc, soccfg = makeProxy()
    base = dict(BaseConfig)
    base.update({
        "ff_park_gain": int(target_gain), "ff_hold_gain": 0,
        "shots": int(settings["readout_shots"]), "reps": int(settings["readout_shots"]),
        "relax_delay": float(settings["relax_delay_us"]), "qua_shot_order": False,
        "read_pulse_freq": float(predicted_r_mhz),
    })
    source_experiments = {}
    trace_rows = []

    def transmission(scan, *, gain, prepare_excited=False, qubit_pi_freq=None):
        cfg = dict(base)
        cfg["read_pulse_gain"] = int(gain)
        cfg["prepare_excited"] = bool(prepare_excited)
        if prepare_excited:
            cfg["qubit_pi_freq"] = float(qubit_pi_freq)
            cfg["qubit_pi_gain"] = int(BaseConfig["qubit_pi_gain"])
            cfg["excited_pi_to_readout_us"] = 0.05
        exp = Transmission(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                           suffix=f"Step1_{scan}", cfg=cfg, f_vec=resonator_axis,
                           plot=settings["plot"], save=True)
        result = exp.acquire(progress=True, plotDisp=settings["plot"])
        data = result["data"]
        source_experiments[scan] = {"pickle": exp.pname, "png": exp.iname}
        trace_rows.extend({"scan": scan,
                           "state": "e" if prepare_excited else "g",
                           "frequency_MHz": float(f), "magnitude_dB": float(m)}
                          for f, m in zip(data["f_vec"], data["IQ_magnitude_dBm"]))
        return _fit_trace(data["f_vec"], data["IQ_magnitude_dBm"], fits.fit_resonator_dip)

    ground = transmission("resonator_ground", gain=settings["readout_gain_dac"])
    lower = transmission("resonator_ground_minus_6dB", gain=low_gain)

    spec_cfg = dict(base)
    spec_cfg.update({
        "shots": int(settings["qubit_spec_shots"]), "reps": int(settings["qubit_spec_shots"]),
        "read_pulse_freq": float(ground["centre_MHz"]),
        "qubit_freq_start": predicted_q_mhz - 0.5 * settings["qubit_spec_span_mhz"],
        "qubit_freq_stop": predicted_q_mhz + 0.5 * settings["qubit_spec_span_mhz"],
        "qubit_freq_expts": int(settings["qubit_spec_points"]),
        "qubit_gain": int(BaseConfig.get("qubit_gain", 25_000)),
    })
    spec = QubitSpec(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                     suffix="Step1_Qubit_Spec", cfg=spec_cfg, save=True)
    spec_result = spec.acquire(progress=True, plotDisp=settings["plot"])
    measured_q_mhz = float(spec_result["data"]["qubit_freq_mhz"])
    source_experiments["qubit_spec"] = {"pickle": spec.pname, "png": spec.iname}
    for f, m in zip(spec_result["data"]["fpts"], spec_result["data"]["magnitude"]):
        trace_rows.append({"scan": "qubit_spec", "state": "g", "frequency_MHz": float(f),
                           "magnitude_dB": float(20.0 * np.log10(float(m) + 1e-12))})

    excited = transmission("resonator_excited", gain=settings["readout_gain_dac"],
                           prepare_excited=True, qubit_pi_freq=measured_q_mhz)
    notes = (
        "dc_bias_V is null because q3 production flux is calibrated in FF DAC gain and no "
        "validated DAC-to-volts conversion is present. readout_power_dBm and attenuation are "
        "null because the source-chain calibration is not in this repository. f_ef is null "
        "because no direct e-to-f or two-photon experiment was run. The excited-state trace "
        "uses the configured Gaussian pi amplitude at the directly measured target f_q; its "
        "amplitude has not been separately re-calibrated at this flux point. "
        f"Fit windows: ground={ground['inside_scan_window']}, lower_power={lower['inside_scan_window']}, "
        f"excited={excited['inside_scan_window']}."
    )
    report = characterisation.step1_report(
        fr_ground_mhz=ground["centre_MHz"], fr_excited_mhz=excited["centre_MHz"],
        kappa_total_mhz=ground["fwhm_MHz"], fq_mhz=measured_q_mhz,
        dc_coordinate=target_gain, readout_gain_dac=settings["readout_gain_dac"],
        lower_power_gain_dac=low_gain, fr_lower_power_mhz=lower["centre_MHz"],
        source="new q3 Step-1 measurement", notes=notes,
    )
    report["resonator_fit_ground"] = ground
    report["resonator_fit_excited"] = excited
    report["resonator_fit_ground_minus_6dB"] = lower
    json_path, csv_path = _write_outputs(outer_folder=outerFolder, settings={
        **settings, "target_gain_dac_resolved": int(target_gain),
        "predicted_target_fq_GHz": float(predicted_q_mhz / 1e3),
        "predicted_target_fr_MHz": float(predicted_r_mhz),
    }, report=report, rows=trace_rows, source_experiments=source_experiments)
    print("[step1] RESULTS")
    print(json.dumps({QUBIT + "_AlOx": report}, indent=2))
    print(f"STEP1_JSON={json_path}")
    print(f"RAW_TRACE_CSV={csv_path}")
    return report


if __name__ == "__main__":
    main()
