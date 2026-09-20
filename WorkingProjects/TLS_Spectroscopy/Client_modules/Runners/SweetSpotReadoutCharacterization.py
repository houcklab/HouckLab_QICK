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

QUBIT = "q3"


def _bool(environ, key, default=False):
    return str(environ.get(key, str(int(default)))).strip().lower() in {
        "1", "true", "yes", "on",
    }


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
        "qubit_spec_centre_mhz": float(env.get("Q3_STEP1B_QUBIT_SPEC_CENTRE_MHZ", "4367.5")),
        "qubit_spec_shots": int(env.get("Q3_STEP1B_QUBIT_SPEC_SHOTS", "3000")),
        "sweep_shots": int(env.get("Q3_STEP1B_SWEEP_SHOTS", "800")),
        "ef_mode": str(env.get("Q3_STEP1B_EF_MODE", "two_photon")).strip().lower(),
        "ef_gains_dac": [int(round(float(v))) for v in
                         str(env.get("Q3_STEP1B_EF_GAINS_DAC", "15000,20000,25000")
                             ).replace(",", " ").split()],
        "ef_centre_mhz": float(env.get("Q3_STEP1B_EF_CENTRE_MHZ", "4278.3")),
        "ef_halfspan_mhz": float(env.get("Q3_STEP1B_EF_HALFSPAN_MHZ", "25.0")),
        "ef_step_mhz": float(env.get("Q3_STEP1B_EF_STEP_MHZ", "0.2")),
        "ef_length_us": float(env.get("Q3_STEP1B_EF_LENGTH_US", "4.0")),
        "ef_shots": int(env.get("Q3_STEP1B_EF_SHOTS", "3000")),
        "rabi_amp_min": int(env.get("Q3_STEP1B_RABI_AMP_MIN", "2000")),
        "rabi_amp_max": int(env.get("Q3_STEP1B_RABI_AMP_MAX", "28000")),
        "rabi_amp_points": int(env.get("Q3_STEP1B_RABI_AMP_POINTS", "41")),
        "rabi_sigma_us": float(env.get("Q3_STEP1B_RABI_SIGMA_US", "0.2")),
        "rabi_shots": int(env.get("Q3_STEP1B_RABI_SHOTS", "500")),
        "ss_cal_shots": int(env.get("Q3_STEP1B_SS_CAL_SHOTS", "1000")),
        "readout_gain_dac": int(env.get("Q3_STEP1B_READOUT_GAIN_DAC", "472")),
        "readout_shots": int(env.get("Q3_STEP1B_READOUT_SHOTS", "1000")),
        "resonator_centre_mhz": float(env.get("Q3_STEP1B_RESONATOR_CENTRE_MHZ", "6933.3")),
        "resonator_span_mhz": float(env.get("Q3_STEP1B_RESONATOR_SPAN_MHZ", "4.0")),
        "resonator_points": int(env.get("Q3_STEP1B_RESONATOR_POINTS", "161")),
        "resonator_length_us": (None if str(env.get("Q3_STEP1B_RESONATOR_LENGTH_US", "")).strip() == ""
                                else float(env["Q3_STEP1B_RESONATOR_LENGTH_US"])),
        "spec_relax_delay_us": float(env.get("Q3_STEP1B_SPEC_RELAX_DELAY_US", "150.0")),
        "relax_delay_us": float(env.get("Q3_STEP1B_RELAX_DELAY_US", "500.0")),
        "ef_only": _bool(env, "Q3_STEP1B_EF_ONLY", False),
        "skip_sweep": _bool(env, "Q3_STEP1B_SKIP_SWEEP", False),
        "fq_override_mhz": (None if not str(env.get("Q3_STEP1B_FQ_MHZ", "")).strip()
                            else float(env["Q3_STEP1B_FQ_MHZ"])),
    }


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
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import outerFolder
    from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import fit_functions as fits
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import GateCalibration as gcal

    settings = runtime_settings()
    gcal.LIVE_PLOTS = False
    centre_gain = int(settings["sweet_spot_gain_dac"])
    biases = [centre_gain + d for d in settings["bias_offsets_dac"]]

    print("")
    print("=========== q3 Step 1b: sweet-spot readout characterisation ===========")
    print("  every scan runs through GateCalibration's own run_qubit_spec /")
    print("  run_transmission / run_rabi_chevron_iq; no separate config path")
    print(f"  nominal sweet spot   : {centre_gain:+d} DAC")
    print(f"  sweet-spot biases    : {biases}")
    print(f"  qubit spectroscopy   : const {settings['qubit_spec_gain_dac']} DAC, "
          f"{settings['qubit_spec_length_us']:g} us, {settings['qubit_spec_points']} pts")
    print(f"  readout gain         : {settings['readout_gain_dac']} DAC")
    print("  raw frequencies only: no chi, no g, no anharmonicity, no Purcell")
    print("=======================================================================")
    print("")

    soc, soccfg = makeProxy()
    source_experiments = {}
    trace_rows = []
    baseline_park = int(gcal.BaseConfig["ff_park_gain"])

    def set_bias(gain_dac):
        gcal.BaseConfig["ff_park_gain"] = int(gain_dac)

    def record(label, bias, x, y, x_units, y_units, state="g"):
        for a, b in zip(x, y):
            trace_rows.append({"scan": label, "state": state, "bias_dac": int(bias),
                               "x": float(a), "x_units": x_units,
                               "y": float(b), "y_units": y_units})

    def qubit_spec(label, *, bias, centre_mhz, span_mhz, points, shots, gain_dac, length_us):
        set_bias(bias)
        gcal.P_QUBIT_SPEC.update({
            "run": True, "readout_gain": int(settings["readout_gain_dac"]),
            "shots": int(shots),
            "freq_start_mhz": float(centre_mhz) - 0.5 * float(span_mhz),
            "freq_stop_mhz": float(centre_mhz) + 0.5 * float(span_mhz),
            "freq_points": int(points), "spec_gain": int(gain_dac),
            "spec_length_us": float(length_us),
            "relax_delay_us": float(settings["spec_relax_delay_us"]),
        })
        exp = gcal.run_qubit_spec(outerFolder, soc, soccfg)
        source_experiments[label] = {"pickle": exp.pname, "png": exp.iname}
        d = exp.data
        record(label, bias, d["fpts"], d["magnitude"], "MHz", "abs_IQ")
        return (float(d["qubit_freq_mhz"]), np.asarray(d["fpts"], float),
                np.asarray(d["magnitude"], float))

    def transmission(label, *, bias, gain, prepare_excited=False, pi_freq=None, pi_gain=None):
        set_bias(bias)
        gcal.P_TRANSMISSION.update({
            "run": True, "shots": int(settings["readout_shots"]),
            "freq_start_mhz": settings["resonator_centre_mhz"] - settings["resonator_span_mhz"],
            "freq_stop_mhz": settings["resonator_centre_mhz"] + settings["resonator_span_mhz"],
            "freq_points": int(settings["resonator_points"]),
            "spec_amp": int(gain),
            "spec_len_us": (None if settings["resonator_length_us"] is None
                            else float(settings["resonator_length_us"])),
            "relax_delay_us": float(settings["relax_delay_us"]),
            "prepare_excited": bool(prepare_excited),
            "qubit_pi_freq_mhz": None if pi_freq is None else float(pi_freq),
            "qubit_pi_gain": None if pi_gain is None else int(round(pi_gain)),
        })
        exp = gcal.run_transmission(outerFolder, soc, soccfg)
        source_experiments[label] = {"pickle": exp.pname, "png": exp.iname}
        d = exp.data
        f = np.asarray(d["f_vec"], float)
        m = np.asarray(d["IQ_magnitude_dBm"], float)
        record(label, bias, f, m, "MHz", "dBm", state="e" if prepare_excited else "g")
        fit, errors = fits.fit_resonator_dip(f, m)
        if fit is None:
            raise RuntimeError(f"{label}: resonator fit returned no result")
        return {"centre_MHz": float(fit["fr"]), "fwhm_MHz": abs(float(fit["fwhm"])),
                "fit_errors": None if errors is None else {k: float(v) for k, v in errors.items()},
                "inside_scan_window": bool(f.min() < fit["fr"] < f.max())}

    def two_photon_series(fq_mhz, bias):
        npts = int(round(2.0 * settings["ef_halfspan_mhz"] / settings["ef_step_mhz"])) + 1
        rows = []
        for gain in settings["ef_gains_dac"]:
            _, f2, m2 = qubit_spec(
                f"ef_two_photon_{gain}", bias=bias, centre_mhz=settings["ef_centre_mhz"],
                span_mhz=2.0 * settings["ef_halfspan_mhz"], points=npts,
                shots=settings["ef_shots"], gain_dac=gain,
                length_us=settings["ef_length_us"])
            fit = characterisation.fit_dip_in_window(
                f2, m2, expected_mhz=settings["ef_centre_mhz"], max_offset_mhz=6.0)
            ok = bool(fit and fit["snr"] is not None and fit["snr"] >= 4.0
                      and fit["inside_window"]
                      and fit["hwhm_MHz"] > 2.0 * settings["ef_step_mhz"])
            rows.append((gain, fit["centre_MHz"] if ok else None,
                         fit["snr"] if fit else None, fit["hwhm_MHz"] if fit else None))
            print(f"[step1b] gain {gain:6d}: two-photon "
                  + ("not detected" if not ok else
                     f"{fit['centre_MHz']:9.3f} MHz  HWHM {fit['hwhm_MHz']:.2f}  "
                     f"SNR {fit['snr']:.1f}"))
        tp = characterisation.extrapolate_zero_power(
            [g for g, c, _, _ in rows if c is not None],
            [c for _, c, _, _ in rows if c is not None])
        derived = characterisation.two_photon_anharmonicity(fq_mhz, tp["zero_power_MHz"])
        return rows, tp, derived

    try:
        if settings["ef_only"]:
            if settings["fq_override_mhz"] is None:
                raise ValueError("Q3_STEP1B_EF_ONLY requires Q3_STEP1B_FQ_MHZ")
            fq_mhz = float(settings["fq_override_mhz"])
            rows, tp, derived = two_photon_series(fq_mhz, centre_gain)
            payload = {
                "mode": "ef_only", "bias_dac": int(centre_gain), "f_q_GHz": fq_mhz / 1e3,
                "two_photon_vs_power": [{"gain_DAC": g, "centre_MHz": c, "snr": s_,
                                         "hwhm_MHz": w} for g, c, s_, w in rows],
                "two_photon_zero_power": tp,
                "f_two_photon_02_GHz": (None if tp["zero_power_MHz"] is None
                                        else tp["zero_power_MHz"] / 1e3),
                "f_ef_GHz": derived["f_ef_GHz"],
                "anharmonicity_MHz": derived["anharmonicity_MHz"],
                "fef_mode": ("two_photon" if derived["f_ef_GHz"] is not None
                             else "two_photon_inconclusive"),
            }
            if derived["anharmonicity_MHz"] is not None:
                print(f"[step1b] f_ef = {derived['f_ef_GHz']:.6f} GHz, "
                      f"anharmonicity {derived['anharmonicity_MHz']:+.2f} MHz")
            json_path, csv_path = _write_outputs(
                outer_folder=outerFolder, settings=settings, report=payload,
                rows=trace_rows, source_experiments=source_experiments)
            print(f"STEP1B_EF_JSON={json_path}")
            print(f"RAW_TRACE_CSV={csv_path}")
            return payload

        evidence = []
        if settings["skip_sweep"]:
            if settings["fq_override_mhz"] is None:
                raise ValueError("Q3_STEP1B_SKIP_SWEEP requires Q3_STEP1B_FQ_MHZ")
            print(f"[step1b] sweet-spot sweep skipped; using f_q "
                  f"{settings['fq_override_mhz']:.4f} MHz at {centre_gain:+d} DAC")
            biases = []
        for bias in biases:
            label = f"sweet_spot_scan_{bias:+d}"
            try:
                fq, _, _ = qubit_spec(
                    label, bias=bias, centre_mhz=settings["qubit_spec_centre_mhz"],
                    span_mhz=settings["qubit_spec_span_mhz"],
                    points=settings["qubit_spec_points"], shots=settings["sweep_shots"],
                    gain_dac=settings["qubit_spec_gain_dac"],
                    length_us=settings["qubit_spec_length_us"])
                evidence.append({"bias": int(bias), "f_q_GHz": round(fq / 1e3, 9)})
                print(f"[step1b] bias {bias:+d} DAC -> f_q {fq / 1e3:.6f} GHz")
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
                print(f"[step1b] centre is NOT the extremum; continuing at {working_gain:+d} DAC")

        if settings["skip_sweep"]:
            working_gain = centre_gain
            fq_mhz = float(settings["fq_override_mhz"])
            check = {"is_extremum": None, "reason": "sweep skipped by Q3_STEP1B_SKIP_SWEEP"}
            evidence = [{"bias": int(centre_gain), "f_q_GHz": fq_mhz / 1e3,
                         "note": "supplied via Q3_STEP1B_FQ_MHZ, not measured in this run"}]
        else:
            fq_mhz, _, _ = qubit_spec(
                "qubit_spec", bias=working_gain, centre_mhz=settings["qubit_spec_centre_mhz"],
                span_mhz=settings["qubit_spec_span_mhz"],
                points=settings["qubit_spec_points"],
                shots=settings["qubit_spec_shots"],
                gain_dac=settings["qubit_spec_gain_dac"],
                length_us=settings["qubit_spec_length_us"])
        print(f"[step1b] f_q = {fq_mhz / 1e3:.6f} GHz")

        f_ef_ghz = two_photon_ghz = ef_candidates = ef_power_series = None
        fef_mode = "unmeasured"
        if settings["ef_mode"] == "two_photon":
            rows, tp, derived = two_photon_series(fq_mhz, working_gain)
            ef_power_series = {
                "f_q_low_power_MHz": float(fq_mhz),
                "f_q_low_power_drive_DAC": int(settings["qubit_spec_gain_dac"]),
                "two_photon_vs_power": [{"gain_DAC": g, "centre_MHz": c, "snr": s_,
                                         "hwhm_MHz": w} for g, c, s_, w in rows],
                "two_photon_zero_power": tp,
                "anharmonicity_MHz": derived["anharmonicity_MHz"],
            }
            ef_candidates = [{"frequency_MHz": c, "offset_from_fq_MHz": c - fq_mhz,
                              "snr": s_, "gain_DAC": g}
                             for g, c, s_, _ in rows if c is not None]
            if derived["anharmonicity_MHz"] is not None \
                    and -400.0 < derived["anharmonicity_MHz"] < -100.0:
                two_photon_ghz = tp["zero_power_MHz"] / 1e3
                f_ef_ghz = derived["f_ef_GHz"]
                fef_mode = "two_photon"
                print(f"[step1b] f_ef = {f_ef_ghz:.6f} GHz, "
                      f"anharmonicity {derived['anharmonicity_MHz']:+.2f} MHz")
            else:
                fef_mode = "two_photon_inconclusive"
                print("[step1b] two-photon series gave no usable anharmonicity; f_ef stays null")

        set_bias(working_gain)
        gcal.BaseConfig["qubit_pi_freq"] = float(fq_mhz)
        gcal.P_SS_CAL.update({"run": True, "shots": int(settings["ss_cal_shots"])})
        calib_params = gcal.run_ss_cal(outerFolder, soc, soccfg)
        gcal.P_RABI_CHEVRON_SS.update({"run": True, "shots": int(settings["rabi_shots"])})
        rabi = gcal.run_rabi_chevron_ss(outerFolder, soc, soccfg, calib_params)
        source_experiments["rabi_amplitude"] = {"pickle": rabi.pname, "png": rabi.iname}
        gains = np.asarray(rabi.data["gain_vec"], float)
        detunings = np.asarray(rabi.data["detuning_vec_mhz"], float)
        pop = np.asarray(rabi.data["ss_data"], float)
        row = int(np.argmin(np.abs(detunings))) if pop.ndim == 2 else 0
        response = pop[row] if pop.ndim == 2 else pop
        print(f"[step1b] Rabi chevron {pop.shape}, using the row at "
              f"{detunings[row]:+.3f} MHz detuning")
        record("rabi_amplitude", working_gain, gains, response, "DAC", "excited_population")
        try:
            pi_calibration = characterisation.fit_rabi_amplitude(gains, response)
            pi_calibration["method"] = (
                f"GateCalibration run_ss_cal then run_rabi_chevron_ss, single detuning at "
                f"{fq_mhz:.4f} MHz, X180, {settings['rabi_shots']} shots; cosine fit to the "
                "discriminated excited population")
        except Exception as exc:
            pi_calibration = {"rabi_pi_amplitude": None, "error": str(exc)}
        pi_calibration["best_gain_argmax_DAC"] = float(rabi.data.get("best_gain", np.nan))
        pi_calibration["single_shot_calib_params"] = {
            k: float(v) for k, v in dict(calib_params).items()
            if isinstance(v, (int, float, np.floating))}
        pi_amp = pi_calibration.get("rabi_pi_amplitude")
        if pi_amp is None or not pi_calibration.get("inside_swept_range", False):
            pi_amp = float(rabi.data.get("best_gain", gcal.BaseConfig["qubit_pi_gain"]))
            pi_calibration["fallback_used"] = True
        pi_calibration["amplitude_used_for_excited_trace"] = float(pi_amp)
        print(f"[step1b] pi amplitude = {pi_amp:.0f} DAC "
              f"(configured {gcal.BaseConfig['qubit_pi_gain']})")

        low_gain = max(1, int(round(settings["readout_gain_dac"] * 10.0 ** (-6.0 / 20.0))))
        ground = transmission("resonator_ground", bias=working_gain,
                              gain=settings["readout_gain_dac"])
        lower = transmission("resonator_ground_minus_6dB", bias=working_gain, gain=low_gain)
        excited = transmission("resonator_excited", bias=working_gain,
                               gain=settings["readout_gain_dac"], prepare_excited=True,
                               pi_freq=fq_mhz, pi_gain=pi_amp)

        notes = [
            "Every scan ran through GateCalibration's run_qubit_spec, run_transmission and "
            "run_rabi_chevron_iq, so the flux/park lifecycle and acquisition path match the "
            "standard gate-calibration measurements.",
            "dc_bias_V is null: q3 flux is calibrated in FF DAC gain with no validated "
            "DAC-to-volts conversion in this repository.",
            "readout_power_dBm and readout_attenuation_dB are null: the source-chain "
            "calibration is not in this repository.",
            "kappa_external/internal are null: the dip fit does not separate them.",
        ]
        if fef_mode == "two_photon":
            notes.append(
                "f_ef_GHz is not a direct e-to-f measurement. It comes from the two-photon "
                "0-2 drive frequency extrapolated to zero drive power, via the exact relation "
                "f_ef = 2*f_two_photon - f_q, with f_q from the low-power scan.")
        elif fef_mode == "two_photon_inconclusive":
            notes.append("The two-photon 0-2 series gave no usable line; f_ef_GHz is null.")
        if not check.get("is_extremum", False):
            notes.append(f"The nominal sweet spot {centre_gain:+d} DAC did not test as the "
                         f"extremum; items 1-7 were taken at {working_gain:+d} DAC.")
        if pi_calibration.get("fallback_used"):
            notes.append("The Rabi fit did not place the pi amplitude inside the swept range; "
                         "the argmax gain was used for the excited-state trace.")

        base_report = characterisation.step1_report(
            fr_ground_mhz=ground["centre_MHz"], fr_excited_mhz=excited["centre_MHz"],
            kappa_total_mhz=ground["fwhm_MHz"], fq_mhz=fq_mhz,
            dc_coordinate=working_gain, readout_gain_dac=settings["readout_gain_dac"],
            lower_power_gain_dac=low_gain, fr_lower_power_mhz=lower["centre_MHz"],
            source="q3 Step-1b sweet-spot measurement", notes=" ".join(notes))
        report = characterisation.step1b_report(
            base_report=base_report, f_ef_ghz=f_ef_ghz, fef_mode=fef_mode,
            sweet_spot_evidence=evidence, sweet_spot_check=check,
            pi_calibration=pi_calibration, two_photon_ghz=two_photon_ghz,
            ef_candidates=ef_candidates)
        report["ef_power_series"] = ef_power_series
        report["resonator_fit_ground"] = ground
        report["resonator_fit_excited"] = excited
        report["resonator_fit_ground_minus_6dB"] = lower

        json_path, csv_path = _write_outputs(
            outer_folder=outerFolder,
            settings={**settings, "working_gain_dac": int(working_gain)},
            report=report, rows=trace_rows, source_experiments=source_experiments)
        shift = 1e3 * (report["f_r_excited_GHz"] - report["f_r_ground_GHz"])
        print("")
        print("[step1b] RESULTS")
        print(json.dumps({QUBIT + "_AlOx": report}, indent=2, sort_keys=True, default=float))
        print(f"[step1b] f_r_excited - f_r_ground = {shift:+.6f} MHz")
        print(f"STEP1B_JSON={json_path}")
        print(f"RAW_TRACE_CSV={csv_path}")
        return report
    finally:
        gcal.BaseConfig["ff_park_gain"] = baseline_park


if __name__ == "__main__":
    main()
