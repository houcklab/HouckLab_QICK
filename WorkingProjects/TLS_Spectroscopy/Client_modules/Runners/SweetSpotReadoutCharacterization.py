from __future__ import annotations

import csv
import datetime as dt
import json
import os
from pathlib import Path

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import (
    readout_characterization as characterisation,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ReadoutCharacterization import (
    _axis, _bool, _fit_trace, predicted_resonator_mhz,
)

QUBIT = "q3"


def runtime_settings(environ=None):
    env = os.environ if environ is None else environ
    offsets = str(env.get("Q3_STEP1B_BIAS_OFFSETS_DAC", "-800,-400,0,400,800"))
    return {
        "sweet_spot_gain_dac": int(env.get("Q3_STEP1B_SWEET_SPOT_GAIN_DAC", "-25146")),
        "bias_offsets_dac": [int(round(float(v))) for v in offsets.replace(",", " ").split()],
        "qubit_spec_gain_dac": int(env.get("Q3_STEP1B_QUBIT_SPEC_GAIN_DAC", "2000")),
        "qubit_spec_length_us": float(env.get("Q3_STEP1B_QUBIT_SPEC_LENGTH_US", "4.0")),
        "qubit_spec_points": int(env.get("Q3_STEP1B_QUBIT_SPEC_POINTS", "321")),
        "qubit_spec_span_mhz": float(env.get("Q3_STEP1B_QUBIT_SPEC_SPAN_MHZ", "15")),
        "qubit_spec_shots": int(env.get("Q3_STEP1B_QUBIT_SPEC_SHOTS", "3000")),
        "sweep_shots": int(env.get("Q3_STEP1B_SWEEP_SHOTS", "800")),
        "ef_mode": str(env.get("Q3_STEP1B_EF_MODE", "two_photon")).strip().lower(),
        "ef_low_offset_mhz": float(env.get("Q3_STEP1B_EF_LOW_OFFSET_MHZ", "400")),
        "ef_high_offset_mhz": float(env.get("Q3_STEP1B_EF_HIGH_OFFSET_MHZ", "40")),
        "ef_points": int(env.get("Q3_STEP1B_EF_POINTS", "361")),
        "ef_gain_dac": int(env.get("Q3_STEP1B_EF_GAIN_DAC", "20000")),
        "ef_length_us": float(env.get("Q3_STEP1B_EF_LENGTH_US", "4.0")),
        "ef_shots": int(env.get("Q3_STEP1B_EF_SHOTS", "3000")),
        "rabi_amp_min": int(env.get("Q3_STEP1B_RABI_AMP_MIN", "500")),
        "rabi_amp_max": int(env.get("Q3_STEP1B_RABI_AMP_MAX", "30000")),
        "rabi_amp_points": int(env.get("Q3_STEP1B_RABI_AMP_POINTS", "41")),
        "rabi_sigma_us": float(env.get("Q3_STEP1B_RABI_SIGMA_US", "0.2")),
        "rabi_shots": int(env.get("Q3_STEP1B_RABI_SHOTS", "400")),
        "readout_gain_dac": int(env.get("Q3_STEP1B_READOUT_GAIN_DAC", "472")),
        "readout_shots": int(env.get("Q3_STEP1B_READOUT_SHOTS", "300")),
        "resonator_span_mhz": float(env.get("Q3_STEP1B_RESONATOR_SPAN_MHZ", "4.0")),
        "resonator_step_mhz": float(env.get("Q3_STEP1B_RESONATOR_STEP_MHZ", "0.05")),
        "relax_delay_us": float(env.get("Q3_STEP1B_RELAX_DELAY_US", "500.0")),
        "spec_relax_delay_us": float(env.get("Q3_STEP1B_SPEC_RELAX_DELAY_US", "150.0")),
        "plot": _bool(env, "Q3_STEP1B_PLOT", False),
    }


def ef_candidate_peaks(freq_mhz, magnitude, fq_mhz, max_peaks=4):
    f = np.asarray(freq_mhz, dtype=float)
    y = np.asarray(magnitude, dtype=float)
    good = np.isfinite(f) & np.isfinite(y)
    f, y = f[good], y[good]
    if f.size < 9:
        return []
    width = max(5, f.size // 40)
    kernel = np.ones(width) / width
    baseline = np.convolve(y, kernel, mode="same")
    excess = y - baseline
    noise = float(np.std(np.diff(excess)) / np.sqrt(2.0))
    out = []
    work = excess.copy()
    work[:width] = -np.inf
    work[-width:] = -np.inf
    for _ in range(int(max_peaks)):
        k = int(np.nanargmax(work))
        prominence = float(work[k])
        if noise <= 0 or prominence < 4.0 * noise:
            break
        out.append({
            "frequency_MHz": float(f[k]),
            "offset_from_fq_MHz": float(f[k] - float(fq_mhz)),
            "prominence": prominence,
            "prominence_sigma": prominence / noise,
        })
        mask = np.abs(f - f[k]) < 8.0
        work[mask] = -np.inf
    return out


def select_two_photon(candidates, low_mhz=-200.0, high_mhz=-60.0):
    inside = [c for c in candidates
              if low_mhz <= c["offset_from_fq_MHz"] <= high_mhz]
    if len(inside) != 1:
        return None, inside
    return inside[0], inside


def _write_outputs(*, outer_folder, settings, report, rows, source_experiments):
    now = dt.datetime.now()
    data_dir = Path(outer_folder) / QUBIT / f"{QUBIT}_{now:%Y_%m_%d}"
    data_dir.mkdir(parents=True, exist_ok=True)
    stem = data_dir / f"{QUBIT}_{now:%H_%M_%S}_Step1b_SweetSpot_Readout"
    payload = {
        QUBIT + "_AlOx": report,
        "run_settings": settings,
        "raw_trace_csv": str(stem.with_name(stem.name + "_raw_traces.csv")),
        "source_experiments": source_experiments,
    }
    json_path = stem.with_suffix(".json")
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=float))
    csv_path = stem.with_name(stem.name + "_raw_traces.csv")
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["scan", "state", "bias_dac", "x", "x_units", "y", "y_units"])
        writer.writeheader()
        writer.writerows(rows)
    return json_path, csv_path


def main():
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import (
        BaseConfig, outerFolder,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mQubitSpec import QubitSpec
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mTransmission import (
        Transmission,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mRabiChevronIQ import (
        RabiChevronIQ,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import fit_functions as fits
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import flux_fit as fx
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as tls

    settings = runtime_settings()
    centre_gain = int(settings["sweet_spot_gain_dac"])
    biases = [centre_gain + d for d in settings["bias_offsets_dac"]]
    predicted_q_mhz = 1e3 * fx.estimate_fit_frequency_ghz(tls.FLUX_FIT_PARAMS, centre_gain)
    low_gain = max(1, int(round(settings["readout_gain_dac"] * 10.0 ** (-6.0 / 20.0))))

    print("")
    print("=========== q3 Step 1b: sweet-spot readout characterisation ===========")
    print(f"  nominal sweet spot   : {centre_gain:+d} DAC  (model f_q {predicted_q_mhz/1e3:.6f} GHz)")
    print(f"  sweet-spot biases    : {biases}")
    print(f"  qubit spectroscopy   : const {settings['qubit_spec_gain_dac']} DAC, "
          f"{settings['qubit_spec_length_us']:g} us, {settings['qubit_spec_points']} pts over "
          f"{settings['qubit_spec_span_mhz']:g} MHz")
    print(f"  readout gain         : {settings['readout_gain_dac']} DAC, -6 dB = {low_gain}")
    print(f"  relax delay          : {settings['spec_relax_delay_us']:g} us for spectroscopy, "
          f"{settings['relax_delay_us']:g} us for Rabi and the resonator traces")
    print(f"  e-f mode             : {settings['ef_mode']}")
    print("  raw frequencies only: no chi, no g, no anharmonicity, no Purcell")
    print("=======================================================================")
    print("")

    soc, soccfg = makeProxy()
    source_experiments = {}
    trace_rows = []

    def base_cfg(gain_dac):
        cfg = dict(BaseConfig)
        cfg.update({
            "ff_park_gain": int(gain_dac), "ff_hold_gain": 0,
            "shots": int(settings["readout_shots"]), "reps": int(settings["readout_shots"]),
            "relax_delay": float(settings["relax_delay_us"]), "qua_shot_order": False,
        })
        return cfg

    def qubit_spec(label, *, bias_dac, centre_mhz, span_mhz, points, shots,
                   gain_dac, length_us, read_freq_mhz):
        cfg = base_cfg(bias_dac)
        cfg.update({
            "shots": int(shots), "reps": int(shots),
            "relax_delay": float(settings["spec_relax_delay_us"]),
            "read_pulse_gain": int(settings["readout_gain_dac"]),
            "read_pulse_freq": float(read_freq_mhz),
            "qubit_freq_start": float(centre_mhz) - 0.5 * float(span_mhz),
            "qubit_freq_stop": float(centre_mhz) + 0.5 * float(span_mhz),
            "qubit_freq_expts": int(points),
            "qubit_pulse_style": "const",
            "qubit_gain": int(gain_dac),
            "qubit_length": float(length_us),
        })
        exp = QubitSpec(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                        suffix=f"Step1b_{label}", cfg=cfg, save=True)
        result = exp.acquire(progress=True, plotDisp=settings["plot"])
        source_experiments[label] = {"pickle": exp.pname, "png": exp.iname}
        data = result["data"]
        for f, m in zip(data["fpts"], data["magnitude"]):
            trace_rows.append({"scan": label, "state": "g", "bias_dac": int(bias_dac),
                               "x": float(f), "x_units": "MHz",
                               "y": float(m), "y_units": "magnitude"})
        return float(data["qubit_freq_mhz"]), np.asarray(data["fpts"], dtype=float), \
            np.asarray(data["magnitude"], dtype=float)

    resonator_axis_seed = _axis(predicted_resonator_mhz(centre_gain, tls.RESONATOR_FIT_PARAMS),
                                settings["resonator_span_mhz"], settings["resonator_step_mhz"])

    evidence = []
    for bias in biases:
        label = f"sweet_spot_scan_{bias:+d}"
        centre = 1e3 * fx.estimate_fit_frequency_ghz(tls.FLUX_FIT_PARAMS, bias)
        try:
            fq_mhz, _, _ = qubit_spec(
                label, bias_dac=bias, centre_mhz=centre,
                span_mhz=settings["qubit_spec_span_mhz"],
                points=settings["qubit_spec_points"], shots=settings["sweep_shots"],
                gain_dac=settings["qubit_spec_gain_dac"],
                length_us=settings["qubit_spec_length_us"],
                read_freq_mhz=float(np.median(resonator_axis_seed)))
            evidence.append({"bias": int(bias), "f_q_GHz": round(fq_mhz / 1e3, 9)})
            print(f"[step1b] bias {bias:+d} DAC -> f_q {fq_mhz/1e3:.6f} GHz")
        except Exception as exc:
            evidence.append({"bias": int(bias), "f_q_GHz": None, "error": str(exc)})
            print(f"[step1b] bias {bias:+d} DAC FAILED: {exc}")

    check = characterisation.sweet_spot_verdict(evidence, centre_gain)
    print(f"[step1b] sweet-spot check: {check['reason']}")
    working_gain = centre_gain
    if not check.get("is_extremum", False):
        observed = check.get("extremum_bias_observed")
        if observed is not None and np.isfinite(observed):
            working_gain = int(observed)
            print(f"[step1b] centre is NOT the extremum; continuing at observed "
                  f"extremum {working_gain:+d} DAC")

    predicted_r_mhz = predicted_resonator_mhz(working_gain, tls.RESONATOR_FIT_PARAMS)
    resonator_axis = _axis(predicted_r_mhz, settings["resonator_span_mhz"],
                           settings["resonator_step_mhz"])

    fq_mhz, _, _ = qubit_spec(
        "qubit_spec", bias_dac=working_gain, centre_mhz=predicted_q_mhz,
        span_mhz=settings["qubit_spec_span_mhz"], points=settings["qubit_spec_points"],
        shots=settings["qubit_spec_shots"], gain_dac=settings["qubit_spec_gain_dac"],
        length_us=settings["qubit_spec_length_us"], read_freq_mhz=float(predicted_r_mhz))
    print(f"[step1b] f_q = {fq_mhz/1e3:.6f} GHz")

    f_ef_ghz = None
    two_photon_ghz = None
    ef_candidates = None
    fef_mode = "unmeasured"
    if settings["ef_mode"] == "two_photon":
        lo = fq_mhz - settings["ef_low_offset_mhz"]
        hi = fq_mhz - settings["ef_high_offset_mhz"]
        _, ef_f, ef_mag = qubit_spec(
            "ef_two_photon", bias_dac=working_gain, centre_mhz=0.5 * (lo + hi),
            span_mhz=(hi - lo), points=settings["ef_points"], shots=settings["ef_shots"],
            gain_dac=settings["ef_gain_dac"], length_us=settings["ef_length_us"],
            read_freq_mhz=float(predicted_r_mhz))
        ef_candidates = ef_candidate_peaks(ef_f, ef_mag, fq_mhz)
        chosen, inside = select_two_photon(ef_candidates)
        if chosen is not None:
            two_photon_ghz = chosen["frequency_MHz"] / 1e3
            f_ef_ghz = (2.0 * chosen["frequency_MHz"] - fq_mhz) / 1e3
            fef_mode = "two_photon"
            print(f"[step1b] two-photon 0-2 at {chosen['frequency_MHz']/1e3:.6f} GHz "
                  f"({chosen['offset_from_fq_MHz']:+.1f} MHz, "
                  f"{chosen['prominence_sigma']:.1f} sigma) -> f_ef "
                  f"{f_ef_ghz:.6f} GHz")
        else:
            fef_mode = "two_photon_inconclusive"
            print(f"[step1b] two-photon scan did not yield a unique candidate in "
                  f"-200..-60 MHz; found {len(inside)}. f_ef stays null.")

    rabi_cfg = base_cfg(working_gain)
    rabi_cfg.update({
        "shots": int(settings["rabi_shots"]), "reps": int(settings["rabi_shots"]),
        "read_pulse_gain": int(settings["readout_gain_dac"]),
        "read_pulse_freq": float(predicted_r_mhz),
        "qubit_pi_freq": float(fq_mhz), "qubit_freq": float(fq_mhz),
        "rabi_drive_freq": float(fq_mhz),
        "amp_start": int(settings["rabi_amp_min"]), "amp_stop": int(settings["rabi_amp_max"]),
        "amp_expts": int(settings["rabi_amp_points"]),
        "freq_span": 0.0, "freq_points": 1,
        "qubit_pulse_style": "arb", "sigma": float(settings["rabi_sigma_us"]),
        "relax_delay": float(settings["relax_delay_us"]),
        "qua_passive_pre_point_delay_us": float(settings["relax_delay_us"]),
    })
    rabi = RabiChevronIQ(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                         suffix="Step1b_Rabi_Amplitude", cfg=rabi_cfg,
                         num_pi_pulses=1, pulse_type="X180", live_plot=settings["plot"])
    rabi_result = rabi.acquire(progress=True, plotDisp=settings["plot"])
    source_experiments["rabi_amplitude"] = {"pickle": rabi.pname, "png": rabi.iname}
    rabi_data = rabi_result["data"]
    gains = np.asarray(rabi_data["gain_vec"], dtype=float)
    iq = np.sqrt(np.asarray(rabi_data["I"], dtype=float) ** 2
                 + np.asarray(rabi_data["Q"], dtype=float) ** 2)
    response = iq[0] if iq.ndim == 2 else iq
    for g, v in zip(gains, response):
        trace_rows.append({"scan": "rabi_amplitude", "state": "g", "bias_dac": int(working_gain),
                           "x": float(g), "x_units": "DAC", "y": float(v),
                           "y_units": "abs_IQ"})
    try:
        pi_calibration = characterisation.fit_rabi_amplitude(gains, response)
        pi_calibration["method"] = (
            f"RabiChevronIQ amplitude sweep at fixed drive {fq_mhz:.4f} MHz, "
            f"X180 gaussian sigma {settings['rabi_sigma_us']:g} us, "
            f"{settings['rabi_shots']} shots; cosine fit to |IQ| vs gain")
        pi_calibration["best_gain_argmax_DAC"] = float(rabi_data.get("best_gain", np.nan))
    except Exception as exc:
        pi_calibration = {"rabi_pi_amplitude": None, "error": str(exc),
                          "best_gain_argmax_DAC": float(rabi_data.get("best_gain", np.nan)),
                          "method": "fit failed; argmax reported instead"}
    pi_amp = pi_calibration.get("rabi_pi_amplitude")
    if pi_amp is None or not pi_calibration.get("inside_swept_range", False):
        pi_amp = float(rabi_data.get("best_gain", BaseConfig["qubit_pi_gain"]))
        pi_calibration["fallback_used"] = True
    pi_calibration["amplitude_used_for_excited_trace"] = float(pi_amp)
    print(f"[step1b] pi amplitude = {pi_amp:.0f} DAC "
          f"(argmax {rabi_data.get('best_gain')}, "
          f"contrast {pi_calibration.get('rabi_fit_contrast')})")

    def transmission(scan, *, gain, prepare_excited=False):
        cfg = base_cfg(working_gain)
        cfg["read_pulse_gain"] = int(gain)
        cfg["read_pulse_freq"] = float(predicted_r_mhz)
        cfg["prepare_excited"] = bool(prepare_excited)
        if prepare_excited:
            cfg["qubit_pi_freq"] = float(fq_mhz)
            cfg["qubit_pi_gain"] = int(round(pi_amp))
            cfg["excited_pi_to_readout_us"] = 0.05
        exp = Transmission(soc=soc, soccfg=soccfg, path=QUBIT, outerFolder=outerFolder,
                           suffix=f"Step1b_{scan}", cfg=cfg, f_vec=resonator_axis,
                           plot=settings["plot"], save=True)
        result = exp.acquire(progress=True, plotDisp=settings["plot"])
        data = result["data"]
        source_experiments[scan] = {"pickle": exp.pname, "png": exp.iname}
        for f, m in zip(data["f_vec"], data["IQ_magnitude_dBm"]):
            trace_rows.append({"scan": scan, "state": "e" if prepare_excited else "g",
                               "bias_dac": int(working_gain), "x": float(f), "x_units": "MHz",
                               "y": float(m), "y_units": "dBm"})
        return _fit_trace(data["f_vec"], data["IQ_magnitude_dBm"], fits.fit_resonator_dip)

    ground = transmission("resonator_ground", gain=settings["readout_gain_dac"])
    lower = transmission("resonator_ground_minus_6dB", gain=low_gain)
    excited = transmission("resonator_excited", gain=settings["readout_gain_dac"],
                           prepare_excited=True)

    notes_parts = [
        "Step 1b: every item taken at one fixed sweet-spot flux bias; the flux was changed "
        "only for the sweet-spot confirmation sweep, which ran first.",
        "dc_bias_V is null because q3 flux is calibrated in FF DAC gain with no validated "
        "DAC-to-volts conversion in this repository.",
        "readout_power_dBm and readout_attenuation_dB are null because the source-chain "
        "calibration is not in this repository.",
        "kappa_external/internal are null: the dip fit does not separate them.",
    ]
    if fef_mode == "two_photon":
        notes_parts.append(
            "f_ef_GHz was not measured by direct e-to-f spectroscopy. It is computed from the "
            "measured two-photon 0-2 drive frequency via the exact relation "
            "f_ef = 2*f_two_photon - f_q. The measured two-photon frequency is reported "
            "separately as f_two_photon_02_GHz.")
    elif fef_mode == "two_photon_inconclusive":
        notes_parts.append(
            "The two-photon 0-2 scan did not produce a unique candidate peak in the expected "
            "-200..-60 MHz window; f_ef_GHz is null and all detected candidates are listed in "
            "ef_candidate_peaks.")
    if not check.get("is_extremum", False):
        notes_parts.append(
            f"The nominal sweet spot {centre_gain:+d} DAC did not test as the extremum; "
            f"items 1-7 were taken at {working_gain:+d} DAC instead.")
    if pi_calibration.get("fallback_used"):
        notes_parts.append(
            "The Rabi cosine fit did not place the pi amplitude inside the swept range; the "
            "argmax gain was used for the excited-state trace and is reported as "
            "amplitude_used_for_excited_trace.")
    notes_parts.append(
        f"Fit windows inside scan: ground={ground['inside_scan_window']}, "
        f"lower_power={lower['inside_scan_window']}, excited={excited['inside_scan_window']}.")

    base_report = characterisation.step1_report(
        fr_ground_mhz=ground["centre_MHz"], fr_excited_mhz=excited["centre_MHz"],
        kappa_total_mhz=ground["fwhm_MHz"], fq_mhz=fq_mhz,
        dc_coordinate=working_gain, readout_gain_dac=settings["readout_gain_dac"],
        lower_power_gain_dac=low_gain, fr_lower_power_mhz=lower["centre_MHz"],
        source="q3 Step-1b sweet-spot measurement", notes=" ".join(notes_parts),
    )
    report = characterisation.step1b_report(
        base_report=base_report, f_ef_ghz=f_ef_ghz, fef_mode=fef_mode,
        sweet_spot_evidence=evidence, sweet_spot_check=check,
        pi_calibration=pi_calibration, two_photon_ghz=two_photon_ghz,
        ef_candidates=ef_candidates,
    )
    report["resonator_fit_ground"] = ground
    report["resonator_fit_excited"] = excited
    report["resonator_fit_ground_minus_6dB"] = lower

    json_path, csv_path = _write_outputs(
        outer_folder=outerFolder,
        settings={**settings, "working_gain_dac": int(working_gain),
                  "predicted_fq_GHz": float(predicted_q_mhz / 1e3),
                  "predicted_fr_MHz": float(predicted_r_mhz)},
        report=report, rows=trace_rows, source_experiments=source_experiments)

    shift = 1e3 * (report["f_r_excited_GHz"] - report["f_r_ground_GHz"])
    print("")
    print("[step1b] RESULTS")
    print(json.dumps({QUBIT + "_AlOx": report}, indent=2, sort_keys=True, default=float))
    print(f"[step1b] f_r_excited - f_r_ground = {shift:+.6f} MHz "
          f"(band point gave +0.0097 MHz, park gave -0.4712 MHz)")
    if report["f_q_GHz"] > 6.0:
        print("[step1b] NOTE: sweet-spot f_q is above 6 GHz; tell the analysis team, the "
              "simple dispersive expression may not apply.")
    print(f"STEP1B_JSON={json_path}")
    print(f"RAW_TRACE_CSV={csv_path}")
    return report


if __name__ == "__main__":
    main()
