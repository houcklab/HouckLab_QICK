"""Measurement-first diagnostic for the q3 resident five-point acquisition.

This runs a small production-path measurement, retains the full condition/DC/
shot IQ tensors, and reports the populations before the long scan or sync layer
is involved.  Passive reset is the default so record generation and decoding
can be isolated from feedback reset.
"""

import copy
import csv
import json
import os
import pickle
import sys
import time
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


from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.progress import (
    progress_counter,
)


def template_refit_plan(environ=None):
    """Return the offline full-line-template refit contract."""
    environ = os.environ if environ is None else environ
    source = environ.get("Q3_TEMPLATE_REFIT_PKL")
    if not source:
        raise ValueError("Q3_TEMPLATE_REFIT_PKL must name a saved raw step-response PKL.")
    return {
        "source_pkl": Path(source),
        "trace_tracking_mode": "image_template_causal",
        "trace_min_supported_fraction": float(
            environ.get("Q3_TEMPLATE_REFIT_MIN_SUPPORT", "0.8")
        ),
        "trace_polarity": environ.get("Q3_TEMPLATE_REFIT_POLARITY", "dark"),
    }


def run_template_refit(plan=None):
    """Refit an existing raw q3 map without contacting any measurement hardware."""
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mQubitFluxStepResponse import (
        QubitFluxStepResponse,
    )

    plan = template_refit_plan() if plan is None else dict(plan)
    source_pkl = Path(plan["source_pkl"])
    source_config = source_pkl.with_suffix(".json")
    if not source_pkl.is_file():
        raise FileNotFoundError(f"Saved raw step-response PKL not found: {source_pkl}")
    if not source_config.is_file():
        raise FileNotFoundError(f"Saved step-response config JSON not found: {source_config}")
    with source_pkl.open("rb") as handle:
        source = pickle.load(handle)
    with source_config.open("r") as handle:
        cfg = json.load(handle)
    required = ("IQ_mag", "IQ_phase", "f_vec", "t_vec", "flux_fit_params")
    missing = [name for name in required if name not in source]
    if missing:
        raise ValueError(f"Saved step-response PKL is missing: {missing}")

    qubit = str(source.get("qubit", "q3"))
    # A normal source is <RFSOC>/<q3>/<q3_date>/<file>; preserve that standard
    # output hierarchy for the refit products.
    outer_folder = source_pkl.parents[2]
    experiment = QubitFluxStepResponse(
        soc=None,
        soccfg=None,
        path=qubit,
        outerFolder=str(outer_folder),
        prefix=qubit,
        suffix="Qubit_Flux_Step_Response_TEMPLATE_CAUSAL_REFIT",
        cfg=cfg,
        element=qubit,
        f_vec=np.asarray(source["f_vec"], dtype=float),
        t_vec=np.asarray(source["t_vec"], dtype=float),
        dc_offset=float(source["dc_offset"]),
        baseline_dc_offset=float(source["baseline_dc_offset"]),
        shots=int(source.get("shots", cfg.get("reps", 1))),
        flux_fit_params=source["flux_fit_params"],
        flux_lookup_mode="fit",
        live_plot=False,
        fit_rise_decay_bump_dc_correction=True,
        fit_tail_fraction=float(source.get("fit_tail_fraction", 0.25)),
        piecewise_segment_edges_ns=source.get("piecewise_segment_edges_ns"),
        piecewise_regularization=float(source.get("piecewise_regularization", 0.02)),
        piecewise_final_weight=float(source.get("piecewise_final_weight", 0.0)),
        piecewise_min_multiplier=float(source.get("piecewise_min_multiplier", 0.5)),
        piecewise_max_multiplier=float(source.get("piecewise_max_multiplier", 1.5)),
        piecewise_correction_gain=float(source.get("piecewise_correction_gain", 1.0)),
        piecewise_desired_response=source.get("piecewise_desired_response", "unity"),
        piecewise_response_domain=source.get("piecewise_response_domain", "voltage"),
        # The trace extractor has already produced the robust causal model.
        # Invert that smooth trajectory directly; fitting a second transient
        # model here is redundant and can introduce a new local optimum.
        piecewise_response_model="measured",
        piecewise_fit_start_ns=source.get("piecewise_fit_start_ns"),
        piecewise_time_origin_ns=float(source.get("piecewise_time_origin_ns", 0.0)),
        baseline_rearm_time_ns=int(source.get("baseline_rearm_time_ns", 40_000)),
        trace_tracking_mode=plan["trace_tracking_mode"],
        trace_polarity=plan["trace_polarity"],
        trace_min_supported_fraction=float(plan["trace_min_supported_fraction"]),
    )
    experiment.data.update({
        "IQ_mag": np.asarray(source["IQ_mag"], dtype=float),
        "IQ_phase": np.asarray(source["IQ_phase"], dtype=float),
        "offline_refit_source_pkl": str(source_pkl),
    })
    print(f"[template refit] source={source_pkl}")
    print(
        "[template refit] extracting one full-line translation per delay, then "
        "fitting a smooth causal trajectory; no measurement hardware is used"
    )
    experiment._extract_trace_from_map(
        experiment.data["IQ_mag"],
        experiment.data["IQ_phase"],
    )
    supported = np.asarray(experiment.data["trace_supported"], dtype=bool)
    print(
        f"[template refit] support={supported.sum()}/{supported.size} "
        f"({supported.mean():.3f}); causal RMS="
        f"{experiment.data['trace_causal_model_rms_mhz']:.3f} MHz"
    )
    experiment._fit_rise_decay_bump_dc_correction_from_step_response()
    generated_correction = Path(
        experiment.data["rise_decay_bump_dc_compensation_json"]
    )
    candidate_correction = generated_correction.with_name(
        generated_correction.stem + "_CANDIDATE.json"
    )
    generated_correction.replace(candidate_correction)
    experiment.data["rise_decay_bump_dc_compensation_json"] = str(
        candidate_correction
    )
    experiment.finalize_analysis()
    experiment.pickle_data()
    experiment.save_config()
    correction = experiment.data["rise_decay_bump_dc_compensation_json"]
    print(f"TEMPLATE_REFIT_IMAGE={experiment.data['summary_image']}")
    print(f"TEMPLATE_REFIT_CORRECTION_JSON={correction}")
    print("[template refit] CANDIDATE ONLY: inspect the smooth overlay before running 3b")
    return correction


def fresh_step3a_plan(environ=None):
    """Return the high-SNR, correction-free q3 calibration contract."""
    environ = os.environ if environ is None else environ
    readout_after_park = str(
        environ.get("Q3_FRESH_3A_READOUT_AFTER_PARK", "off")
    ).strip().lower() in {"1", "true", "yes", "on"}
    delay_vector_us = np.concatenate([
        np.arange(0.5, 25.5, 0.5),
        np.arange(27.0, 61.0, 2.0),
        np.arange(65.0, 195.0, 10.0),
        np.asarray([197.0, 200.0]),
    ]).tolist()
    return {
        "shots": int(environ.get("Q3_FRESH_3A_SHOTS", "1000")),
        "spec_amp": int(environ.get("Q3_FRESH_3A_SPEC_AMP", "25000")),
        "frequency_window_mhz": [4000.0, 4100.0],
        "frequency_step_mhz": 0.5,
        "delay_vector_us": delay_vector_us,
        "apply_flux_tail_compensation": False,
        "compose_with_applied_flux_tail_compensation": False,
        "readout_after_park": readout_after_park,
        "trace_polarity": None if readout_after_park else "bright",
    }


def fresh_step3b_plan(environ=None):
    """Return the matched correction-ON validation contract for fresh q3 3a."""
    environ = os.environ if environ is None else environ
    plan = fresh_step3a_plan({
        "Q3_FRESH_3A_SHOTS": environ.get("Q3_FRESH_3B_SHOTS", "500"),
        "Q3_FRESH_3A_SPEC_AMP": environ.get("Q3_FRESH_3B_SPEC_AMP", "25000"),
        "Q3_FRESH_3A_READOUT_AFTER_PARK": "on",
    })
    plan.update({
        "apply_flux_tail_compensation": True,
        "compose_with_applied_flux_tail_compensation": False,
        "correction_json": environ.get("Q3_FRESH_3B_CORRECTION_JSON"),
    })
    return plan


def run_fresh_step3a(plan=None):
    """Run one absolute q3 step-response fit without an existing correction."""
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        TLSSpectroscopy as tls,
    )

    plan = fresh_step3a_plan() if plan is None else dict(plan)
    low_mhz, high_mhz = plan["frequency_window_mhz"]
    tls.P3_STEP_RESPONSE.update({
        "shots": int(plan["shots"]),
        "spec_amp": int(plan["spec_amp"]),
        "freq_step": float(plan["frequency_step_mhz"]),
        "auto_center_frequency_window": True,
        "auto_freq_absolute_min_mhz": float(low_mhz),
        "auto_freq_absolute_max_mhz": float(high_mhz),
        "t_vec_us": list(plan["delay_vector_us"]),
        "correction_fit_start_us": None,
        "correction_time_origin_us": 0.0,
        "baseline_rearm_us": 40.0,
        "piecewise_desired_response": "unity",
        "piecewise_response_model": "rise_decay_bump",
        "trace_tracking_mode": "image_template_causal",
        "readout_after_park": bool(plan["readout_after_park"]),
        "trace_polarity": plan["trace_polarity"],
        "trace_shoulder": "auto",
        "trace_max_jump_mhz": 4.0,
        "trace_smoothing_window_points": 7,
        "trace_smoothing_polyorder": 2,
        "trace_use_smoothed_frequency": True,
        "fit_residual_composition": False,
        "live_plot": True,
    })
    print(
        "[fresh 3a] q3 absolute calibration: correction OFF, composition OFF; "
        f"{plan['shots']} shots, {len(plan['delay_vector_us'])} delays, "
        f"{low_mhz / 1000:.3f}--{high_mhz / 1000:.3f} GHz; "
        f"readout={'PARK' if plan['readout_after_park'] else 'held flux'}"
    )
    tls._set_yoko_if_requested()
    soc, soccfg = tls.makeProxy()
    return tls.run_step3a_step_response_fit(tls.outerFolder, soc, soccfg)


def run_fresh_step3b(plan=None):
    """Validate the accepted absolute q3 correction on its calibration grid."""
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        TLSSpectroscopy as tls,
    )

    plan = fresh_step3b_plan() if plan is None else dict(plan)
    low_mhz, high_mhz = plan["frequency_window_mhz"]
    tls.P3_STEP_RESPONSE.update({
        "shots": int(plan["shots"]),
        "spec_amp": int(plan["spec_amp"]),
        "freq_step": float(plan["frequency_step_mhz"]),
        "auto_center_frequency_window": True,
        "auto_freq_absolute_min_mhz": float(low_mhz),
        "auto_freq_absolute_max_mhz": float(high_mhz),
        "t_vec_us": list(plan["delay_vector_us"]),
        "correction_fit_start_us": None,
        "correction_time_origin_us": 0.0,
        "baseline_rearm_us": 40.0,
        "piecewise_desired_response": "unity",
        "piecewise_response_model": "rise_decay_bump",
        "trace_tracking_mode": "image_v26",
        "readout_after_park": True,
        "trace_polarity": None,
        "trace_shoulder": "auto",
        "trace_max_jump_mhz": 4.0,
        "trace_smoothing_window_points": 7,
        "trace_smoothing_polyorder": 2,
        "trace_use_smoothed_frequency": True,
        "fit_residual_composition": False,
        "live_plot": True,
    })
    print(
        "[fresh 3b] q3 validation: correction ON, composition OFF; "
        f"{plan['shots']} shots, {len(plan['delay_vector_us'])} delays, "
        f"{low_mhz / 1000:.3f}--{high_mhz / 1000:.3f} GHz; readout=PARK"
    )
    tls._set_yoko_if_requested()
    soc, soccfg = tls.makeProxy()
    return tls.run_step3b_step_response_correct(
        tls.outerFolder,
        soc,
        soccfg,
        correction_json=plan.get("correction_json"),
    )


def select_diagnostic_slice(
    frequency_ghz,
    dc_values,
    *,
    center_ghz=4.05,
    points=11,
):
    frequency_ghz = np.asarray(frequency_ghz, dtype=float)
    dc_values = np.asarray(dc_values)
    points = int(points)
    if frequency_ghz.ndim != 1 or frequency_ghz.shape != dc_values.shape:
        raise ValueError("frequency and DC grids must be matching 1-D arrays")
    if points < 3 or points % 2 == 0 or points > frequency_ghz.size:
        raise ValueError("diagnostic points must be an odd integer within the grid")
    center = int(np.abs(frequency_ghz - float(center_ghz)).argmin())
    half = points // 2
    start = min(max(center - half, 0), frequency_ghz.size - points)
    indices = np.arange(start, start + points, dtype=int)
    return (
        frequency_ghz[indices].copy(),
        dc_values[indices].copy(),
        indices,
    )


def _median(values):
    values = np.asarray(values, dtype=float)
    finite = values[np.isfinite(values)]
    return float(np.median(finite)) if finite.size else float("nan")


def make_shot_progress(start_time):
    """Report resident-stream progress in completed shot sweeps."""
    return lambda done, total: progress_counter(
        done - 1,
        total,
        start_time=start_time,
        label="five-point diagnostic",
    )


def start_diagnostic_timers(
    *,
    monotonic_clock=time.monotonic,
    wall_clock=time.time,
):
    """Start elapsed and ETA timers in the clock domains they each require."""
    return float(monotonic_clock()), float(wall_clock())


def _json_default(value):
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _save_csv(path, columns):
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in zip(*columns.values()):
            writer.writerow(row)


def sequence_audit_requested(environ=None):
    """Select the temporary native many-delay A/B diagnostic."""
    environ = os.environ if environ is None else environ
    return str(environ.get("Q3_T1_SEQUENCE_AUDIT", "off")).strip().lower() in {
        "1", "true", "yes", "on",
    }


def return_readout_contract_requested(environ=None):
    """Select the temporary post-return preparation/readout diagnostic."""
    environ = os.environ if environ is None else environ
    return str(
        environ.get("Q3_RETURN_READOUT_CONTRACT", "off")
    ).strip().lower() in {"1", "true", "yes", "on"}


def return_readout_contract_plan(environ=None):
    """Cross correction ON/OFF with overlapping/waited return timing."""
    environ = os.environ if environ is None else environ
    frequencies = [
        float(value)
        for value in str(
            environ.get(
                "Q3_RETURN_CONTRACT_FREQUENCIES_GHZ",
                "4.050,4.060,4.070",
            )
        ).split(",")
    ]
    holds = [
        float(value)
        for value in str(
            environ.get("Q3_RETURN_CONTRACT_HOLDS_US", "2,42,82,202")
        ).split(",")
    ]
    shots = int(environ.get("Q3_RETURN_CONTRACT_SHOTS", "300"))
    reset_mode = str(
        environ.get("Q3_RETURN_CONTRACT_RESET_MODE", "active")
    ).strip().lower()
    if (
        not frequencies
        or not np.all(np.isfinite(frequencies))
        or len(set(frequencies)) != len(frequencies)
    ):
        raise ValueError(
            "Q3_RETURN_CONTRACT_FREQUENCIES_GHZ needs unique finite values"
        )
    if (
        len(holds) < 2
        or not np.all(np.isfinite(holds))
        or np.any(np.asarray(holds) < 0.01)
        or np.any(np.diff(holds) <= 0.0)
    ):
        raise ValueError(
            "Q3_RETURN_CONTRACT_HOLDS_US needs increasing positive values"
        )
    if shots < 2:
        raise ValueError("Q3_RETURN_CONTRACT_SHOTS must be at least two")
    if reset_mode not in ("active", "passive"):
        raise ValueError(
            "Q3_RETURN_CONTRACT_RESET_MODE must be active or passive"
        )
    return {
        "target_frequencies_ghz": frequencies,
        "hold_times_us": holds,
        "shots": shots,
        "reset_mode": reset_mode,
        "recovery_us": float(
            environ.get("Q3_RETURN_CONTRACT_RECOVERY_US", "40")
        ),
        "modes": (
            "on_overlap", "off_overlap", "on_waited", "off_waited",
        ),
        "min_contrast": float(
            environ.get("Q3_RETURN_CONTRACT_MIN_CONTRAST", "0.5")
        ),
        "max_population_span": float(
            environ.get("Q3_RETURN_CONTRACT_MAX_POPULATION_SPAN", "0.1")
        ),
        "max_directional_delta": float(
            environ.get("Q3_RETURN_CONTRACT_MAX_DIRECTIONAL_DELTA", "0.15")
        ),
    }


def unity_timing_table(compensation):
    """Keep every segment boundary while removing correction amplitude."""
    result = copy.deepcopy(compensation)
    result["multipliers"] = [1.0] * len(result["multipliers"])
    result["diagnostic_predistortion_mode"] = "timing_matched_unity"
    return result


def predistortion_causality_plan(environ=None):
    """Return the independent dense q3 predistortion A/B contract."""
    environ = os.environ if environ is None else environ
    frequencies = [
        float(value)
        for value in str(
            environ.get("Q3_CAUSALITY_FREQUENCIES_GHZ", "3.900,4.050,4.300")
        ).split(",")
    ]
    delay_points_text = str(
        environ.get("Q3_CAUSALITY_DELAY_POINTS", "")
    ).strip()
    if delay_points_text:
        delay_points = int(delay_points_text)
        if delay_points < 3:
            raise ValueError("Q3_CAUSALITY_DELAY_POINTS must be at least three")
        delay_min_us = float(environ.get("Q3_CAUSALITY_DELAY_MIN_US", "0.5"))
        delay_max_us = float(environ.get("Q3_CAUSALITY_DELAY_MAX_US", "500"))
        delays = np.linspace(delay_min_us, delay_max_us, delay_points).tolist()
    else:
        delays = [
            float(value)
            for value in str(
                environ.get(
                    "Q3_CAUSALITY_DELAYS_US",
                    "0.5,1,2,3,4,6,8,10,12,16,20,25,30,40,50,65,80,100,125,160,200",
                )
            ).split(",")
        ]
    shots = int(environ.get("Q3_CAUSALITY_SHOTS", "300"))
    recovery_us = float(environ.get("Q3_CAUSALITY_RECOVERY_US", "40"))
    reset_mode = str(
        environ.get("Q3_CAUSALITY_RESET_MODE", "active")
    ).strip().lower()
    overlap_value = str(
        environ.get("Q3_CAUSALITY_OVERLAP_READOUT", "on")
    ).strip().lower()
    modes = tuple(
        value.strip().lower()
        for value in str(
            environ.get("Q3_CAUSALITY_MODE_ORDER", "on,off")
        ).split(",")
    )
    if len(frequencies) < 1 or not np.all(np.isfinite(frequencies)):
        raise ValueError(
            "Q3_CAUSALITY_FREQUENCIES_GHZ needs at least one finite value"
        )
    if len(set(frequencies)) != len(frequencies):
        raise ValueError("Q3_CAUSALITY_FREQUENCIES_GHZ values must be unique")
    if (
        len(delays) < 3
        or not np.all(np.isfinite(delays))
        or np.any(np.asarray(delays) <= 0.0)
        or np.any(np.diff(delays) <= 0.0)
    ):
        raise ValueError(
            "Q3_CAUSALITY_DELAYS_US needs at least three positive increasing values"
        )
    if shots < 2:
        raise ValueError("Q3_CAUSALITY_SHOTS must be at least two")
    if not np.isfinite(recovery_us) or recovery_us <= 0.0:
        raise ValueError("Q3_CAUSALITY_RECOVERY_US must be finite and positive")
    if reset_mode not in ("active", "passive"):
        raise ValueError("Q3_CAUSALITY_RESET_MODE must be active or passive")
    if overlap_value not in ("on", "off"):
        raise ValueError("Q3_CAUSALITY_OVERLAP_READOUT must be on or off")
    if len(modes) != 2 or set(modes) != {"on", "off"}:
        raise ValueError(
            "Q3_CAUSALITY_MODE_ORDER must contain on and off exactly once"
        )
    return {
        "target_frequencies_ghz": frequencies,
        "delays_us": delays,
        "shots": shots,
        "recovery_us": recovery_us,
        "reset_mode": reset_mode,
        "overlap_payload_readout": overlap_value == "on",
        "modes": modes,
    }


def partition_delay_triplets(delays_us):
    """Split a dense audit grid into hardware-proven five-condition programs."""
    delays = np.asarray(delays_us, dtype=float).reshape(-1)
    if (
        delays.size == 0
        or not np.all(np.isfinite(delays))
        or np.any(delays <= 0.0)
        or np.any(np.diff(delays) <= 0.0)
    ):
        raise ValueError(
            "dense causality delays must be positive and increasing"
        )
    return [
        tuple(float(value) for value in delays[start:start + 3])
        for start in range(0, delays.size, 3)
    ]


def combine_causality_chunks(chunks, *, delays_us):
    """Merge chunked transport into one dense directional population result."""
    if not chunks:
        raise ValueError("at least one causality chunk is required")
    requested = tuple(float(value) for value in delays_us)
    observed = tuple(
        float(delay)
        for chunk in chunks
        for delay in chunk["delays_us"]
    )
    if observed != requested:
        raise ValueError(
            f"causality chunk delays {observed} do not match requested delays {requested}"
        )

    combined = {}
    for name in (
        "P0", "P0_scan_up", "P0_scan_down",
        "P1", "P1_scan_up", "P1_scan_down",
    ):
        values = [
            np.asarray(chunk["directional"][name], dtype=float)
            for chunk in chunks
        ]
        combined[name] = np.mean(np.stack(values, axis=0), axis=0)
    for chunk in chunks:
        for delay in chunk["delays_us"]:
            condition = f"Ps_{float(delay):g}us"
            for name in (
                condition,
                f"{condition}_scan_up",
                f"{condition}_scan_down",
            ):
                combined[name] = np.asarray(
                    chunk["directional"][name], dtype=float
                ).copy()
    combined["dc_scan_up_shots"] = int(
        sum(chunk["directional"].get("dc_scan_up_shots", 0) for chunk in chunks)
    )
    combined["dc_scan_down_shots"] = int(
        sum(chunk["directional"].get("dc_scan_down_shots", 0) for chunk in chunks)
    )
    return combined


def make_npoint_program_class():
    """Build the temporary resident P0/P1/N-delay QICK program class."""
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.programs import (
        OPXResetT13PointProgram,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.records import (
        CONDITION_TAGGED_PAYLOAD_RECORD_WORDS,
        decode_condition_tagged_payload_records,
    )

    class OPXResetT1NPointProgram(OPXResetT13PointProgram):
        """One resident program containing P0, P1, and every requested delay."""

        def __init__(self, soccfg, cfg, payload_calibration, loop_calibration):
            run_cfg = dict(cfg)
            if bool(run_cfg.get("opx_diagnostic_condition_tags", False)):
                self.record_words = CONDITION_TAGGED_PAYLOAD_RECORD_WORDS
                self.decode_dmem_records = decode_condition_tagged_payload_records
            delays = np.asarray(
                run_cfg.get("opx_t1_npoint_delays_us", ()), dtype=float
            ).reshape(-1)
            if (
                delays.size < 3
                or not np.all(np.isfinite(delays))
                or np.any(delays <= 0.0)
                or np.any(np.diff(delays) <= 0.0)
            ):
                raise ValueError(
                    "opx_t1_npoint_delays_us must contain at least three "
                    "positive increasing delays"
                )
            reference_hold_us = float(
                run_cfg.get("opx_t1_npoint_reference_hold_us", 0.0)
            )
            if not np.isfinite(reference_hold_us) or reference_hold_us < 0.01:
                raise ValueError(
                    "opx_t1_npoint_reference_hold_us must be at least 0.01 us"
                )
            run_cfg.update({
                "opx_t1_npoint_delays_us": delays.tolist(),
                "opx_t1_npoint_reference_hold_us": reference_hold_us,
                "opx_t1_3pt_wait_us": reference_hold_us + float(delays[-1]),
            })
            custom_holds = run_cfg.get("opx_t1_condition_holds_us")
            custom_flags = run_cfg.get("opx_t1_condition_excitation_flags")
            if custom_holds is not None or custom_flags is not None:
                holds = np.asarray(custom_holds, dtype=float).reshape(-1)
                flags = np.asarray(custom_flags, dtype=int).reshape(-1)
                if (
                    holds.size < 2 or holds.size != flags.size
                    or not np.all(np.isfinite(holds)) or np.any(holds < 0.01)
                    or np.any((flags != 0) & (flags != 1))
                ):
                    raise ValueError(
                        "custom return/readout conditions need matched finite "
                        "positive holds and zero/one excitation flags"
                    )
                run_cfg["opx_t1_condition_holds_us"] = holds.tolist()
                run_cfg["opx_t1_condition_excitation_flags"] = flags.tolist()
                self._npoint_records_per_dc = int(holds.size)
            else:
                self._npoint_records_per_dc = 2 + int(delays.size)
            super().__init__(
                soccfg,
                run_cfg,
                payload_calibration,
                loop_calibration,
            )

        def _records_per_dc(self):
            if hasattr(self, "_npoint_records_per_dc"):
                return int(self._npoint_records_per_dc)
            return 2 + len(self.cfg["opx_t1_npoint_delays_us"])

        def _set_p0_reference_flag(self, controls, label_prefix):
            # The audit measures frequency-resolved P0 on every shot.
            return None

        def _emit_t1_conditions(self, controls, label_prefix):
            custom_holds = self.cfg.get("opx_t1_condition_holds_us")
            if custom_holds is not None:
                flags = self.cfg["opx_t1_condition_excitation_flags"]
                for index, (hold, flag) in enumerate(zip(custom_holds, flags)):
                    self._emit_tagged_condition(
                        f"{label_prefix}_C{index}", bool(flag), True,
                        float(hold), index,
                    )
                return
            reference = float(self.cfg["opx_t1_npoint_reference_hold_us"])
            self._emit_tagged_condition(
                f"{label_prefix}_P0", False, True, reference, 0
            )
            self._emit_tagged_condition(
                f"{label_prefix}_P1", True, True, reference, 1
            )
            for index, delay in enumerate(self.cfg["opx_t1_npoint_delays_us"]):
                self._emit_tagged_condition(
                    f"{label_prefix}_PS{index}",
                    True,
                    True,
                    reference + float(delay),
                    index + 2,
                )

        def _emit_tagged_condition(self, label, do_pi, do_ff, hold_us, tag):
            self._emit_three_point_payload(label, do_pi, do_ff, hold_us)
            if not bool(self.cfg.get("opx_diagnostic_condition_tags", False)):
                return
            self.regwi(self.reset_page, self.reset_regs["q"], int(tag))
            self.memw(
                self.reset_page,
                self.reset_regs["q"],
                self.reset_regs["address"],
            )
            self.mathi(
                self.reset_page,
                self.reset_regs["address"],
                self.reset_regs["address"],
                "+",
                1,
            )

    return OPXResetT1NPointProgram


def acquire_t1_npoint_iq(
    soc,
    soccfg,
    cfg,
    *,
    dc_gains,
    delays_us,
    reference_hold_us,
    shots,
    reset_scheme="opx_unbounded",
    progress=None,
    program_class=None,
    condition_holds_us=None,
    condition_excitation_flags=None,
    condition_names=None,
    prepare_excited_after_return=False,
):
    """Acquire P0, P1, and N survival delays in one resident QICK program."""
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX import (
        integration,
    )

    bundle = integration.runtime_bundle(cfg)
    gains = np.asarray(dc_gains, dtype=float).reshape(-1)
    if gains.size == 0 or not np.all(np.isfinite(gains)):
        raise ValueError("at least one finite N-point DC gain is required")
    rounded = np.rint(gains).astype(np.int64)
    if not np.allclose(gains, rounded, rtol=0.0, atol=1e-9):
        raise ValueError("N-point DC gains must be integer DAC values")
    delays = np.asarray(delays_us, dtype=float).reshape(-1)
    if (
        delays.size < 3
        or not np.all(np.isfinite(delays))
        or np.any(delays <= 0.0)
        or np.any(np.diff(delays) <= 0.0)
    ):
        raise ValueError(
            "N-point delays must contain at least three positive increasing values"
        )
    reference_hold_us = float(reference_hold_us)
    if not np.isfinite(reference_hold_us) or reference_hold_us < 0.01:
        raise ValueError("N-point reference hold must be at least 0.01 us")
    total_shots = int(shots)
    if float(shots) != total_shots or total_shots < 2:
        raise ValueError("N-point shots must be an integer of at least two")
    reset_scheme = str(reset_scheme).strip().lower()
    if reset_scheme not in ("opx_unbounded", "none"):
        raise ValueError("reset_scheme must be 'opx_unbounded' or 'none'")

    custom_conditions = condition_holds_us is not None
    if custom_conditions:
        holds = np.asarray(condition_holds_us, dtype=float).reshape(-1)
        flags = np.asarray(condition_excitation_flags, dtype=int).reshape(-1)
        if (
            holds.size < 2 or holds.size != flags.size
            or not np.all(np.isfinite(holds)) or np.any(holds < 0.01)
            or np.any((flags != 0) & (flags != 1))
        ):
            raise ValueError(
                "custom conditions need matched finite positive holds and "
                "zero/one excitation flags"
            )
        names = tuple(
            str(value) for value in (
                condition_names
                if condition_names is not None
                else tuple(f"condition_{index}" for index in range(holds.size))
            )
        )
        if len(names) != holds.size:
            raise ValueError("condition_names must match custom conditions")
        records_per_dc = int(holds.size)
    else:
        holds = None
        flags = None
        names = (
            "P0", "P1", *(f"Ps_{delay:g}us" for delay in delays)
        )
        records_per_dc = 2 + int(delays.size)
    records_per_shot = int(rounded.size) * records_per_dc
    run_cfg = dict(cfg)
    run_cfg.update({
        "opx_reset_scheme": reset_scheme,
        "opx_t1_3pt_shots": total_shots,
        "opx_t1_3pt_dc_gains": rounded.tolist(),
        "opx_t1_npoint_delays_us": delays.tolist(),
        "opx_t1_npoint_reference_hold_us": reference_hold_us,
        "ff_hold": reference_hold_us + float(delays[-1]),
        "t1_wait_us": reference_hold_us + float(delays[-1]),
        "opx_resident_dmem_stream": True,
        "opx_t1_prepare_excited_after_return": bool(
            prepare_excited_after_return
        ),
    })
    if custom_conditions:
        run_cfg.update({
            "opx_t1_condition_holds_us": holds.tolist(),
            "opx_t1_condition_excitation_flags": flags.tolist(),
            "ff_hold": float(np.max(holds)),
            "t1_wait_us": float(np.max(holds)),
        })
    program_type = make_npoint_program_class() if program_class is None else program_class
    program = program_type(soccfg, run_cfg, bundle.payload, bundle.loop)
    block = integration._run_program(
        soc,
        program,
        integration._block_timeout_s(
            run_cfg, total_shots * records_per_shot
        ),
        run_cfg,
        total_shots=total_shots,
        progress=progress,
    )
    i_records = np.asarray(
        [record.final_i for record in block], dtype=float
    ).reshape(total_shots, rounded.size, records_per_dc)
    q_records = np.asarray(
        [record.final_q for record in block], dtype=float
    ).reshape(total_shots, rounded.size, records_per_dc)
    condition_tags = None
    if block and all(hasattr(record, "condition_tag") for record in block):
        condition_tags = np.asarray(
            [record.condition_tag for record in block], dtype=int
        ).reshape(total_shots, rounded.size, records_per_dc)
    i_records[1::2] = i_records[1::2, ::-1]
    q_records[1::2] = q_records[1::2, ::-1]
    if condition_tags is not None:
        condition_tags[1::2] = condition_tags[1::2, ::-1]
    i_values = i_records.transpose(2, 1, 0)
    q_values = q_records.transpose(2, 1, 0)
    tag_telemetry = {}
    if condition_tags is not None:
        decoded_tags = condition_tags.transpose(2, 1, 0)
        expected_tags = np.arange(records_per_dc, dtype=int)[:, None, None]
        mismatches = int(np.count_nonzero(decoded_tags != expected_tags))
        tag_telemetry = {
            "condition_tag_mismatches": mismatches,
            "condition_tags_match_decoded_conditions": bool(mismatches == 0),
        }
    read_cycles = program.us2cycles(
        cfg["read_length"], ro_ch=cfg["ro_chs"][0]
    )
    return i_values / int(read_cycles), q_values / int(read_cycles), {
        "shots_per_condition": total_shots,
        "dc_points": int(rounded.size),
        "records": int(len(block)),
        "records_per_dc": records_per_dc,
        "blocks": 1,
        "resident_stream": True,
        "native_many_delay_program": True,
        "order": "shot_alternating_dc_P0_P1_Ps_all_delays",
        "condition_names": names,
        "dc_scan_order": "alternating_bidirectional",
        "dc_scan_up_shots": int((total_shots + 1) // 2),
        "dc_scan_down_shots": int(total_shots // 2),
        "p0_mode": "matched_frequency_resolved",
        "reference_hold_us": reference_hold_us,
        "decay_delays_us": tuple(float(value) for value in delays),
        "condition_holds_us": (
            tuple(float(value) for value in holds)
            if custom_conditions else None
        ),
        "prepare_excited_after_return": bool(
            prepare_excited_after_return
        ),
        "read_length_cycles": int(read_cycles),
        **tag_telemetry,
        "dmem_read_verification": getattr(
            program,
            "dmem_read_verification",
            {"enabled": False},
        ),
        **integration.flux_predistortion_telemetry(program),
    }


def summarize_return_readout_states(
    states,
    *,
    hold_times_us,
    min_contrast,
    max_population_span,
    max_directional_delta,
):
    """Summarize paired P0/P1 references prepared only after flux return."""
    states = np.asarray(states, dtype=float)
    holds = np.asarray(hold_times_us, dtype=float)
    if states.ndim != 3 or states.shape[0] != 2 * holds.size:
        raise ValueError("return/readout states need P0/P1 for every hold")
    if states.shape[2] < 2:
        raise ValueError("return/readout states need at least two shots")
    combined = np.mean(states, axis=2).T
    up = np.mean(states[:, :, 0::2], axis=2).T
    down = np.mean(states[:, :, 1::2], axis=2).T
    p0 = combined[:, 0::2]
    p1 = combined[:, 1::2]
    contrast = p1 - p0
    p0_span = np.ptp(p0, axis=1)
    p1_span = np.ptp(p1, axis=1)
    directional = np.maximum(
        np.max(np.abs(up[:, 0::2] - down[:, 0::2]), axis=1),
        np.max(np.abs(up[:, 1::2] - down[:, 1::2]), axis=1),
    )
    failures = []
    for index in range(combined.shape[0]):
        reasons = []
        if float(np.min(contrast[index])) < float(min_contrast):
            reasons.append("low P1-P0 contrast")
        if float(max(p0_span[index], p1_span[index])) > float(max_population_span):
            reasons.append("hold-dependent park mapping")
        if float(directional[index]) > float(max_directional_delta):
            reasons.append("scan-direction dependence")
        failures.append(reasons)
    return {
        "combined": combined,
        "up": up,
        "down": down,
        "P0": p0,
        "P1": p1,
        "contrast": contrast,
        "P0_span": p0_span,
        "P1_span": p1_span,
        "max_directional_delta": directional,
        "failures": failures,
        "passed": not any(failures),
    }


def save_return_readout_contract_outputs(
    output_base,
    *,
    plan,
    target_frequency_ghz,
    realized_frequency_ghz,
    dc_vec,
    mode_results,
    correction_source,
):
    """Persist shot-level IQ plus concise return/readout comparison products."""
    npz_path = Path(str(output_base) + "_raw_iq.npz")
    csv_path = Path(str(output_base) + "_raw_iq.csv")
    json_path = Path(str(output_base) + "_summary.json")
    png_path = Path(str(output_base) + "_comparison.png")
    archive = {}
    for mode, result in mode_results.items():
        archive[f"{mode}_I"] = result["I"]
        archive[f"{mode}_Q"] = result["Q"]
        archive[f"{mode}_states"] = result["states"]
    archive.update({
        "target_frequency_ghz": np.asarray(target_frequency_ghz),
        "realized_frequency_ghz": np.asarray(realized_frequency_ghz),
        "dc_offset_dac": np.asarray(dc_vec),
        "hold_times_us": np.asarray(plan["hold_times_us"]),
    })
    np.savez_compressed(npz_path, **archive)

    fields = [
        "mode", "target_frequency_ghz", "realized_frequency_ghz",
        "dc_offset_dac", "hold_us", "prepared_state", "shot",
        "scan_direction", "I", "Q", "classified_excited",
    ]
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for mode in plan["modes"]:
            result = mode_results[mode]
            for hold_index, hold in enumerate(plan["hold_times_us"]):
                for state_offset, state_name in enumerate(("P0", "P1_after_return")):
                    condition = 2 * hold_index + state_offset
                    for frequency_index, frequency in enumerate(target_frequency_ghz):
                        for shot in range(plan["shots"]):
                            writer.writerow({
                                "mode": mode,
                                "target_frequency_ghz": frequency,
                                "realized_frequency_ghz": realized_frequency_ghz[frequency_index],
                                "dc_offset_dac": dc_vec[frequency_index],
                                "hold_us": hold,
                                "prepared_state": state_name,
                                "shot": shot,
                                "scan_direction": "up" if shot % 2 == 0 else "down",
                                "I": result["I"][condition, frequency_index, shot],
                                "Q": result["Q"][condition, frequency_index, shot],
                                "classified_excited": int(
                                    result["states"][condition, frequency_index, shot]
                                ),
                            })

    payload = {
        "plan": plan,
        "correction_source": correction_source,
        "raw_iq_npz": str(npz_path),
        "raw_iq_csv": str(csv_path),
        "overall_passed": bool(all(
            result["summary"]["passed"] for result in mode_results.values()
        )),
        "modes": {},
    }
    for mode, result in mode_results.items():
        summary = result["summary"]
        payload["modes"][mode] = {
            "passed": bool(summary["passed"]),
            "P0": summary["P0"].tolist(),
            "P1_after_return": summary["P1"].tolist(),
            "contrast": summary["contrast"].tolist(),
            "P0_span": summary["P0_span"].tolist(),
            "P1_span": summary["P1_span"].tolist(),
            "max_directional_delta": summary["max_directional_delta"].tolist(),
            "failures": summary["failures"],
            "telemetry": result["telemetry"],
        }
    with json_path.open("w") as handle:
        json.dump(payload, handle, indent=2, default=_json_default)

    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(
        len(target_frequency_ghz), 1,
        figsize=(8.5, 3.2 * len(target_frequency_ghz)),
        squeeze=False,
        constrained_layout=True,
    )
    colors = {
        "on_overlap": "#2457a6", "off_overlap": "#d97706",
        "on_waited": "#3b9e77", "off_waited": "#cc79a7",
    }
    holds = np.asarray(plan["hold_times_us"], dtype=float)
    for frequency_index, frequency in enumerate(target_frequency_ghz):
        axis = axes[frequency_index, 0]
        for mode in plan["modes"]:
            summary = mode_results[mode]["summary"]
            axis.plot(
                holds, summary["P0"][frequency_index], "o--",
                color=colors[mode], alpha=0.65, label=f"{mode} P0",
            )
            axis.plot(
                holds, summary["P1"][frequency_index], "o-",
                color=colors[mode], label=f"{mode} P1 after return",
            )
        axis.set_title(
            f"{frequency:.3f} GHz target: park mapping versus target hold"
        )
        axis.set_xlabel("Target hold [us]")
        axis.set_ylabel("P(excited) at park readout")
        axis.set_ylim(-0.05, 1.05)
        axis.grid(alpha=0.2)
        axis.legend(frameon=False, ncol=2, fontsize=8)
    fig.suptitle(
        "q3 return/readout contract: state prepared after flux return"
    )
    fig.savefig(png_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return npz_path, csv_path, json_path, png_path


def run_return_readout_contract():
    """Run the timing-matched four-way return/readout diagnostic on q3."""
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        FivePointApplesToApples as runner,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        TLSSpectroscopy as tls,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ThreePointApplesToApples import (
        _integer_dc_grid,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.acquisition import (
        dmem_words_from_soccfg,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
        classify_payload_iq,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
        PASSIVE_T1_RESET_US,
        ProductionResetSession,
        prepare_reset_session,
    )
    from fluxpred import production as fluxpred_production

    plan = return_readout_contract_plan()
    model_path = str(
        os.environ.get("Q3_RETURN_CONTRACT_NEUTRAL_MODEL_JSON", "")
    ).strip()
    if not model_path:
        raise ValueError(
            "Q3_RETURN_CONTRACT_NEUTRAL_MODEL_JSON must name the accepted "
            "controller-neutral q3 model"
        )
    runner.install_scan_calibration(tls)
    tls._set_yoko_if_requested()
    soc, soccfg = tls.makeProxy()
    if bool(soc.streamer.readout_running()):
        raise RuntimeError(
            "QICK streamer is already running. Stop the other QICK "
            "acquisition before launching this isolated test."
        )
    dmem_roundtrip = verify_dmem_roundtrip(
        soc, dmem_words=dmem_words_from_soccfg(soccfg)
    )
    print(
        "[transport] DMem sentinel PASS: bulk DMA and direct AXI agree at "
        f"address {dmem_roundtrip['address']}"
    )
    params = dict(runner.P6_5PT_APPLES_TO_APPLES)
    target_frequency_ghz = np.asarray(
        plan["target_frequencies_ghz"], dtype=float
    )
    dc_vec, realized_frequency_ghz = _integer_dc_grid(
        params, target_frequency_ghz
    )
    choice = fluxpred_production.selection(
        "q3",
        park=float(tls._baseline_dc_offset()),
        scale=float(tls.TARGET_DC_OFFSET) - float(tls._baseline_dc_offset()),
        environ={
            "Q3_FLUXPRED_MODE": "neutral",
            "Q3_FLUXPRED_MODEL_JSON": model_path,
            "Q3_FLUXPRED_DIAGNOSTIC_OVERRIDE": "1",
        },
        amplitude_range=(0.0, 1.0),
    )
    for line in fluxpred_production.describe(choice):
        print(line)
    compensation = fluxpred_production.neutral_step_table(
        choice,
        max_hold_ns=1000.0 * (
            float(params["flux_settle_us"]) + max(plan["hold_times_us"])
        ),
        recovery_ns=1000.0 * float(plan["recovery_us"]),
        schedule_first_ns=4_000.0,
        schedule_growth=1.2,
        schedule_max_ns=100_000.0,
        quantum_ns=1_000.0,
    )
    unity = unity_timing_table(compensation)
    print(
        "[return contract] q3 four-way test: correction ON/OFF x "
        "overlap/waited; OFF retains the exact segmented timing schedule"
    )
    print(
        "[return contract] the qubit remains in |g> throughout the flux "
        "excursion; P1 is prepared only after the selected return timing"
    )
    print("[return contract] acquiring one shared DMem-native classifier")
    classifier_session = prepare_reset_session(
        "active",
        outer_folder=tls.outerFolder,
        qubit=tls.QUBIT,
        base_cfg=tls.BaseConfig,
        soc=soc,
        soccfg=soccfg,
        purpose="PredistortionReturnReadoutContract",
    )
    common_cfg = dict(tls.BaseConfig)
    common_cfg.update({
        "shots": int(plan["shots"]),
        "ff_gain_vec": dc_vec,
        "flux_fit_params": tls.FLUX_FIT_PARAMS,
        "relax_delay": PASSIVE_T1_RESET_US,
        "qubit_pulse_style": "arb",
        "flux_settle_time_us": float(params["flux_settle_us"]),
        "readout_thermalization_us": float(params["readout_thermalization_us"]),
        "opx_t1_3pt_gain_lookup": True,
        "opx_diagnostic_condition_tags": True,
        "opx_verify_dmem_reads": False,
        "flux_predistortion_recovery_us": float(plan["recovery_us"]),
    })
    runner.apply_verified_feedback_timing(common_cfg)
    if plan["reset_mode"] == "active":
        common_cfg = classifier_session.apply(common_cfg)
        reset_scheme = "opx_unbounded"
    else:
        common_cfg = ProductionResetSession.passive().apply(common_cfg)
        common_cfg["opx_reset_calibration"] = dict(
            classifier_session.calibration
        )
        reset_scheme = "none"

    holds = list(plan["hold_times_us"])
    hold_chunks = [holds[start:start + 2] for start in range(0, len(holds), 2)]
    mode_chunks = {mode: [] for mode in plan["modes"]}
    total = len(hold_chunks) * len(plan["modes"])
    acquisition_index = 0
    for chunk_index, chunk_holds in enumerate(hold_chunks):
        mode_order = (
            plan["modes"] if chunk_index % 2 == 0
            else tuple(reversed(plan["modes"]))
        )
        condition_holds = [
            hold for hold in chunk_holds for _state in (0, 1)
        ]
        excitation_flags = [
            state for _hold in chunk_holds for state in (0, 1)
        ]
        condition_names = tuple(
            name
            for hold in chunk_holds
            for name in (
                f"P0_hold_{hold:g}us",
                f"P1_after_return_hold_{hold:g}us",
            )
        )
        for mode in mode_order:
            acquisition_index += 1
            cfg = dict(common_cfg)
            cfg.update({
                "apply_flux_tail_compensation": True,
                "flux_tail_compensation": (
                    compensation if mode.startswith("on") else unity
                ),
                "flux_predistortion_overlap_payload_readout": mode.endswith(
                    "_overlap"
                ),
            })
            print(
                f"[{mode} {acquisition_index}/{total}] holds={chunk_holds} us; "
                f"{plan['shots']} shots x {len(dc_vec)} targets x "
                f"{len(condition_names)} conditions"
            )
            progress_started = time.time()
            i_values, q_values, telemetry = acquire_t1_npoint_iq(
                soc,
                soccfg,
                cfg,
                dc_gains=dc_vec,
                delays_us=(10.0, 50.0, 200.0),
                reference_hold_us=2.0,
                shots=plan["shots"],
                reset_scheme=reset_scheme,
                condition_holds_us=condition_holds,
                condition_excitation_flags=excitation_flags,
                condition_names=condition_names,
                prepare_excited_after_return=True,
                progress=lambda done, count, _mode=mode: progress_counter(
                    done - 1,
                    count,
                    start_time=progress_started,
                    label=f"q3 return {_mode}",
                ),
            )
            states = classify_payload_iq(
                cfg, i_values, q_values, telemetry["read_length_cycles"]
            )
            if telemetry.get("condition_tag_mismatches", 0) != 0:
                raise RuntimeError(
                    f"{mode} condition tags do not match decoded records"
                )
            mode_chunks[mode].append({
                "chunk_index": chunk_index,
                "I": i_values,
                "Q": q_values,
                "states": states,
                "telemetry": telemetry,
            })

    mode_results = {}
    for mode in plan["modes"]:
        chunks = sorted(mode_chunks[mode], key=lambda item: item["chunk_index"])
        i_values = np.concatenate([item["I"] for item in chunks], axis=0)
        q_values = np.concatenate([item["Q"] for item in chunks], axis=0)
        states = np.concatenate([item["states"] for item in chunks], axis=0)
        summary = summarize_return_readout_states(
            states,
            hold_times_us=holds,
            min_contrast=plan["min_contrast"],
            max_population_span=plan["max_population_span"],
            max_directional_delta=plan["max_directional_delta"],
        )
        mode_results[mode] = {
            "I": i_values,
            "Q": q_values,
            "states": states,
            "summary": summary,
            "telemetry": [item["telemetry"] for item in chunks],
        }

    now = datetime.now()
    output_dir = Path(tls.outerFolder) / tls.QUBIT / f"{tls.QUBIT}_{now:%Y_%m_%d}"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_base = output_dir / (
        f"{tls.QUBIT}_{now:%H_%M_%S}_Predistortion_Return_Readout_Contract"
    )
    outputs = save_return_readout_contract_outputs(
        output_base,
        plan=plan,
        target_frequency_ghz=target_frequency_ghz,
        realized_frequency_ghz=realized_frequency_ghz,
        dc_vec=dc_vec,
        mode_results=mode_results,
        correction_source=model_path,
    )
    for mode in plan["modes"]:
        summary = mode_results[mode]["summary"]
        for frequency_index, frequency in enumerate(target_frequency_ghz):
            failures = summary["failures"][frequency_index]
            print(
                f"[result] {mode} {frequency:.3f} GHz: "
                f"min contrast={np.min(summary['contrast'][frequency_index]):.3f}; "
                f"P0 span={summary['P0_span'][frequency_index]:.3f}; "
                f"P1 span={summary['P1_span'][frequency_index]:.3f}; "
                f"direction delta={summary['max_directional_delta'][frequency_index]:.3f}; "
                + ("PASS" if not failures else "FAIL: " + ", ".join(failures))
            )
    print(f"RAW_IQ_NPZ={outputs[0]}")
    print(f"RAW_IQ_CSV={outputs[1]}")
    print(f"SUMMARY_JSON={outputs[2]}")
    print(f"COMPARISON_PNG={outputs[3]}")


def summarize_dense_populations(matrix, *, delays_us, shots):
    """Normalize every survival point against its mode-matched P0/P1."""
    matrix = np.asarray(matrix, dtype=float)
    delays = np.asarray(delays_us, dtype=float)
    shots = int(shots)
    expected_columns = 2 + len(delays)
    if matrix.ndim != 2 or matrix.shape[1] != expected_columns:
        raise ValueError(
            f"dense population matrix needs {expected_columns} columns"
        )
    if shots < 2:
        raise ValueError("dense population summary needs at least two shots")
    p0 = matrix[:, 0]
    p1 = matrix[:, 1]
    survival = matrix[:, 2:]
    contrast = p1 - p0
    with np.errstate(divide="ignore", invalid="ignore"):
        normalized = (survival - p0[:, None]) / contrast[:, None]
        variance_p0 = p0 * (1.0 - p0) / shots
        variance_p1 = p1 * (1.0 - p1) / shots
        variance_ps = survival * (1.0 - survival) / shots
        derivative_ps = 1.0 / contrast[:, None]
        derivative_p0 = (survival - p1[:, None]) / contrast[:, None] ** 2
        derivative_p1 = -(survival - p0[:, None]) / contrast[:, None] ** 2
        normalized_variance = (
            derivative_ps ** 2 * variance_ps
            + derivative_p0 ** 2 * variance_p0[:, None]
            + derivative_p1 ** 2 * variance_p1[:, None]
        )
    return {
        "delays_us": delays,
        "P0": p0,
        "P1": p1,
        "survival": survival,
        "normalized": normalized,
        "normalized_sigma": np.sqrt(normalized_variance),
    }


def summarize_causality_chunks(chunks, *, delays_us, shots):
    """Normalize each chunk with its contemporaneous P0/P1 references."""
    requested = tuple(float(value) for value in delays_us)
    observed = tuple(
        float(delay)
        for chunk in chunks
        for delay in chunk["delays_us"]
    )
    if observed != requested:
        raise ValueError(
            f"causality chunk delays {observed} do not match requested delays {requested}"
        )
    chunk_summaries = []
    for chunk in chunks:
        names = (
            "P0", "P1",
            *(f"Ps_{float(delay):g}us" for delay in chunk["delays_us"]),
        )
        matrix = np.column_stack(
            [chunk["directional"][name] for name in names]
        )
        chunk_summaries.append(
            summarize_dense_populations(
                matrix,
                delays_us=chunk["delays_us"],
                shots=shots,
            )
        )
    return {
        "delays_us": np.asarray(requested, dtype=float),
        "P0": np.mean(
            np.stack([summary["P0"] for summary in chunk_summaries]), axis=0
        ),
        "P1": np.mean(
            np.stack([summary["P1"] for summary in chunk_summaries]), axis=0
        ),
        "survival": np.concatenate(
            [summary["survival"] for summary in chunk_summaries], axis=1
        ),
        "normalized": np.concatenate(
            [summary["normalized"] for summary in chunk_summaries], axis=1
        ),
        "normalized_sigma": np.concatenate(
            [summary["normalized_sigma"] for summary in chunk_summaries], axis=1
        ),
    }


def save_predistortion_causality_outputs(
    output_base,
    *,
    plan,
    target_frequency_ghz,
    realized_frequency_ghz,
    dc_vec,
    mode_results,
    correction_source,
    readout_contract,
):
    """Save raw IQ, directional populations, propagated errors, and A/B plot."""
    output_base = Path(output_base)
    raw_iq_path = Path(str(output_base) + "_raw_iq.npz")
    csv_path = Path(str(output_base) + "_raw_populations.csv")
    json_path = Path(str(output_base) + "_summary.json")
    png_path = Path(str(output_base) + "_comparison.png")

    raw_payload = {
        "target_frequency_ghz": np.asarray(target_frequency_ghz, dtype=float),
        "realized_frequency_ghz": np.asarray(realized_frequency_ghz, dtype=float),
        "dc_offset_dac": np.asarray(dc_vec, dtype=int),
        "delays_us": np.asarray(plan["delays_us"], dtype=float),
        "condition_names": np.asarray(mode_results["on"]["condition_names"]),
    }
    for mode in plan["modes"]:
        for chunk_index, chunk in enumerate(mode_results[mode]["chunks"]):
            prefix = f"{mode}_chunk_{chunk_index}"
            raw_payload[f"delays_{prefix}"] = np.asarray(
                chunk["delays_us"], dtype=float
            )
            raw_payload[f"I_{prefix}"] = np.asarray(chunk["I"], dtype=float)
            raw_payload[f"Q_{prefix}"] = np.asarray(chunk["Q"], dtype=float)
            raw_payload[f"states_{prefix}"] = np.asarray(
                chunk["states"], dtype=float
            )
    np.savez_compressed(raw_iq_path, **raw_payload)

    fields = [
        "mode", "target_frequency_ghz", "realized_frequency_ghz",
        "dc_offset_dac", "condition", "delay_us", "population",
        "population_scan_up", "population_scan_down",
        "normalized_survival", "normalized_survival_sigma",
        "shots", "reset_mode", "correction_source",
    ]
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for mode in plan["modes"]:
            result = mode_results[mode]
            summary = result["summary"]
            directional = result["directional"]
            for frequency_index, frequency in enumerate(target_frequency_ghz):
                for condition in ("P0", "P1"):
                    writer.writerow({
                        "mode": mode,
                        "target_frequency_ghz": frequency,
                        "realized_frequency_ghz": realized_frequency_ghz[frequency_index],
                        "dc_offset_dac": dc_vec[frequency_index],
                        "condition": condition,
                        "delay_us": "",
                        "population": directional[condition][frequency_index],
                        "population_scan_up": directional[f"{condition}_scan_up"][frequency_index],
                        "population_scan_down": directional[f"{condition}_scan_down"][frequency_index],
                        "normalized_survival": "",
                        "normalized_survival_sigma": "",
                        "shots": plan["shots"],
                        "reset_mode": plan["reset_mode"],
                        "correction_source": correction_source if mode == "on" else "",
                    })
                for delay_index, delay in enumerate(plan["delays_us"]):
                    condition = f"Ps_{delay:g}us"
                    writer.writerow({
                        "mode": mode,
                        "target_frequency_ghz": frequency,
                        "realized_frequency_ghz": realized_frequency_ghz[frequency_index],
                        "dc_offset_dac": dc_vec[frequency_index],
                        "condition": condition,
                        "delay_us": delay,
                        "population": directional[condition][frequency_index],
                        "population_scan_up": directional[f"{condition}_scan_up"][frequency_index],
                        "population_scan_down": directional[f"{condition}_scan_down"][frequency_index],
                        "normalized_survival": summary["normalized"][frequency_index, delay_index],
                        "normalized_survival_sigma": summary["normalized_sigma"][frequency_index, delay_index],
                        "shots": plan["shots"],
                        "reset_mode": plan["reset_mode"],
                        "correction_source": correction_source if mode == "on" else "",
                    })

    metrics = {
        "plan": plan,
        "correction_source": correction_source,
        "readout_contract": readout_contract,
        "raw_iq_npz": str(raw_iq_path),
        "frequencies": {},
        "telemetry": {
            mode: mode_results[mode]["telemetry"] for mode in plan["modes"]
        },
    }
    for frequency_index, frequency in enumerate(target_frequency_ghz):
        key = f"{frequency:.6f}GHz"
        metrics["frequencies"][key] = {}
        for mode in plan["modes"]:
            summary = mode_results[mode]["summary"]
            normalized = summary["normalized"][frequency_index]
            upward = np.diff(normalized)
            metrics["frequencies"][key][mode] = {
                "P0": float(summary["P0"][frequency_index]),
                "P1": float(summary["P1"][frequency_index]),
                "reference_contrast": float(
                    summary["P1"][frequency_index]
                    - summary["P0"][frequency_index]
                ),
                "largest_upward_step": float(max(0.0, np.nanmax(upward))),
                "normalized_survival": normalized.tolist(),
                "normalized_survival_sigma": summary[
                    "normalized_sigma"
                ][frequency_index].tolist(),
            }
        on = mode_results["on"]["summary"]
        off = mode_results["off"]["summary"]
        delta = on["normalized"][frequency_index] - off["normalized"][frequency_index]
        sigma = np.sqrt(
            on["normalized_sigma"][frequency_index] ** 2
            + off["normalized_sigma"][frequency_index] ** 2
        )
        with np.errstate(divide="ignore", invalid="ignore"):
            z_score = delta / sigma
        metrics["frequencies"][key]["on_minus_off_normalized"] = delta.tolist()
        metrics["frequencies"][key]["on_minus_off_z"] = z_score.tolist()
        metrics["frequencies"][key]["on_minus_off_max_abs_z"] = float(
            np.nanmax(np.abs(z_score))
        )
    with json_path.open("w") as handle:
        json.dump(metrics, handle, indent=2, default=_json_default)

    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(
        len(target_frequency_ghz),
        2,
        figsize=(11.0, 3.2 * len(target_frequency_ghz)),
        squeeze=False,
        constrained_layout=True,
    )
    colors = {"on": "#2457a6", "off": "#d97706"}
    delays = np.asarray(plan["delays_us"], dtype=float)
    for frequency_index, frequency in enumerate(target_frequency_ghz):
        raw_ax, normalized_ax = axes[frequency_index]
        for mode in plan["modes"]:
            summary = mode_results[mode]["summary"]
            survival = summary["survival"][frequency_index]
            raw_sigma = np.sqrt(
                survival * (1.0 - survival) / plan["shots"]
            )
            raw_ax.errorbar(
                delays,
                survival,
                yerr=raw_sigma,
                marker="o",
                ms=3.5,
                lw=1.0,
                capsize=2,
                color=colors[mode],
                label=mode,
            )
            raw_ax.axhline(
                summary["P0"][frequency_index],
                color=colors[mode],
                lw=0.8,
                ls=":",
                alpha=0.75,
            )
            raw_ax.axhline(
                summary["P1"][frequency_index],
                color=colors[mode],
                lw=0.8,
                ls="--",
                alpha=0.75,
            )
            normalized_ax.errorbar(
                delays,
                summary["normalized"][frequency_index],
                yerr=summary["normalized_sigma"][frequency_index],
                marker="o",
                ms=3.5,
                lw=1.0,
                capsize=2,
                color=colors[mode],
                label=mode,
            )
        raw_ax.set_title(f"{frequency:.3f} GHz: raw P(excited)")
        normalized_ax.set_title(f"{frequency:.3f} GHz: normalized survival")
        raw_ax.set_ylabel("P(excited)")
        normalized_ax.set_ylabel("(Ps - P0) / (P1 - P0)")
        for axis in (raw_ax, normalized_ax):
            axis.set_xlabel("Delay [us]")
            axis.spines["top"].set_visible(False)
            axis.spines["right"].set_visible(False)
            axis.legend(frameon=False)
    fig.suptitle(
        f"q3 {len(delays)}-delay predistortion test: "
        "PMem-safe chunks, correction on/off"
    )
    fig.savefig(png_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return raw_iq_path, csv_path, json_path, png_path


def run_predistortion_causality():
    """Run one dense q3 ON/OFF audit using PMem-safe resident chunks."""
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.five_point_t1 import (
        reduce_bidirectional_condition_states,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        FivePointApplesToApples as runner,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        TLSSpectroscopy as tls,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ThreePointApplesToApples import (
        _integer_dc_grid,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.acquisition import (
        dmem_words_from_soccfg,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
        acquire_t1_5pt_iq,
        classify_payload_iq,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
        PASSIVE_T1_RESET_US,
        ProductionResetSession,
        prepare_reset_session,
    )

    plan = predistortion_causality_plan()
    neutral_model_path = str(
        os.environ.get("Q3_CAUSALITY_NEUTRAL_MODEL_JSON", "")
    ).strip() or None
    correction_override = str(
        os.environ.get("Q3_CAUSALITY_CORRECTION_JSON", "")
    ).strip() or None
    if neutral_model_path is not None and correction_override is not None:
        raise ValueError(
            "Set only one of Q3_CAUSALITY_NEUTRAL_MODEL_JSON and "
            "Q3_CAUSALITY_CORRECTION_JSON"
        )
    if neutral_model_path is None and correction_override is None:
        raise ValueError(
            "Set Q3_CAUSALITY_NEUTRAL_MODEL_JSON for the controller-neutral "
            "A/B test, or Q3_CAUSALITY_CORRECTION_JSON for a legacy comparison"
        )

    runner.install_scan_calibration(tls)
    tls._set_yoko_if_requested()
    soc, soccfg = tls.makeProxy()
    if bool(soc.streamer.readout_running()):
        raise RuntimeError(
            "QICK streamer is already running. Stop the other QICK acquisition "
            "before launching this isolated test."
        )
    dmem_roundtrip = verify_dmem_roundtrip(
        soc,
        dmem_words=dmem_words_from_soccfg(soccfg),
    )
    print(
        "[transport] DMem sentinel PASS: bulk DMA and direct AXI agree at "
        f"address {dmem_roundtrip['address']}"
    )

    params = dict(runner.P6_5PT_APPLES_TO_APPLES)
    target_frequency_ghz = np.asarray(
        plan["target_frequencies_ghz"], dtype=float
    )
    dc_vec, realized_frequency_ghz = _integer_dc_grid(
        params, target_frequency_ghz
    )
    if neutral_model_path is not None:
        from fluxpred import production as fluxpred_production

        neutral_choice = fluxpred_production.selection(
            "q3",
            park=float(tls._baseline_dc_offset()),
            scale=float(tls.TARGET_DC_OFFSET) - float(tls._baseline_dc_offset()),
            environ={
                "Q3_FLUXPRED_MODE": "neutral",
                "Q3_FLUXPRED_MODEL_JSON": neutral_model_path,
                "Q3_FLUXPRED_DIAGNOSTIC_OVERRIDE": "1",
            },
            amplitude_range=(0.0, 1.0),
        )
        for line in fluxpred_production.describe(neutral_choice):
            print(line)
        max_hold_ns = 1000.0 * (
            float(params["flux_settle_us"])
            + max(
                float(params["reference_hold_us"]),
                *[float(value) for value in plan["delays_us"]],
            )
        )
        compensation = fluxpred_production.neutral_step_table(
            neutral_choice,
            max_hold_ns=max_hold_ns,
            recovery_ns=1000.0 * float(plan["recovery_us"]),
            schedule_first_ns=4_000.0,
            schedule_growth=1.2,
            schedule_max_ns=100_000.0,
            quantum_ns=1_000.0,
        )
        correction_label = neutral_model_path
    else:
        compensation, _correction_mode = tls._resolve_step6_correction(
            params, correction_override, tls.outerFolder
        )
        correction_label = correction_override
    delay_chunks = partition_delay_triplets(plan["delays_us"])
    print(
        "[causality] q3 A/B: "
        f"{len(target_frequency_ghz)} frequencies x "
        f"{len(plan['delays_us'])} delays x {plan['shots']} shots; "
        f"reset={plan['reset_mode']}; recovery={plan['recovery_us']:g} us; "
        f"overlap-readout={plan['overlap_payload_readout']}; "
        "no handshake"
    )
    print(
        f"[causality] the {len(plan['delays_us'])}-delay dataset will be assembled from "
        f"{len(delay_chunks)} hardware-safe three-delay resident programs per mode"
    )
    print(f"[causality] ON uses {correction_label}")
    print("[causality] OFF uses no flux-tail correction")
    print("[causality] acquiring one shared DMem-native classifier calibration")
    classifier_session = prepare_reset_session(
        "active",
        outer_folder=tls.outerFolder,
        qubit=tls.QUBIT,
        base_cfg=tls.BaseConfig,
        soc=soc,
        soccfg=soccfg,
        purpose=f"Predistortion{len(plan['delays_us'])}PointTemporaryTest",
    )
    print(
        "[causality] classifier calibration saved: "
        f"{classifier_session.calibration_output}"
    )

    common_cfg = dict(tls.BaseConfig)
    common_cfg.update({
        "shots": int(plan["shots"]),
        "ff_gain_vec": dc_vec,
        "flux_fit_params": tls.FLUX_FIT_PARAMS,
        "relax_delay": PASSIVE_T1_RESET_US,
        "qubit_pulse_style": "arb",
        "flux_settle_time_us": float(params["flux_settle_us"]),
        "readout_thermalization_us": float(params["readout_thermalization_us"]),
        "opx_t1_3pt_gain_lookup": True,
        "opx_diagnostic_condition_tags": True,
        "opx_verify_dmem_reads": False,
        "flux_predistortion_recovery_us": float(plan["recovery_us"]),
        "flux_predistortion_overlap_payload_readout": bool(
            plan["overlap_payload_readout"]
        ),
    })
    runner.apply_verified_feedback_timing(common_cfg)
    if plan["reset_mode"] == "active":
        common_cfg = classifier_session.apply(common_cfg)
        reset_scheme = "opx_unbounded"
    else:
        common_cfg = ProductionResetSession.passive().apply(common_cfg)
        common_cfg["opx_reset_calibration"] = dict(
            classifier_session.calibration
        )
        reset_scheme = "none"

    condition_names = (
        "P0", "P1", *(f"Ps_{delay:g}us" for delay in plan["delays_us"])
    )
    mode_chunks = {mode: [] for mode in plan["modes"]}
    total_acquisitions = len(delay_chunks) * len(plan["modes"])
    acquisition_index = 0
    for chunk_index, delays in enumerate(delay_chunks):
        # Reverse mode order on alternating chunks so slow drift cannot always
        # favor the same correction state.
        mode_order = (
            tuple(plan["modes"])
            if chunk_index % 2 == 0
            else tuple(reversed(plan["modes"]))
        )
        for mode in mode_order:
            acquisition_index += 1
            cfg = dict(common_cfg)
            cfg.update({
                "apply_flux_tail_compensation": mode == "on",
                "flux_tail_compensation": compensation if mode == "on" else None,
            })
            chunk_names = (
                "P0", "P1", *(f"Ps_{delay:g}us" for delay in delays)
            )
            records = plan["shots"] * len(dc_vec) * len(chunk_names)
            print(
                f"[{mode} chunk {chunk_index + 1}/{len(delay_chunks)}; "
                f"acquisition {acquisition_index}/{total_acquisitions}] "
                f"delays={list(delays)} us; {records} records"
            )
            elapsed_started = time.monotonic()
            progress_started = time.time()
            i_values, q_values, telemetry = acquire_t1_5pt_iq(
                soc,
                soccfg,
                cfg,
                dc_gains=dc_vec,
                delays_us=delays,
                reference_hold_us=float(params["reference_hold_us"]),
                shots=plan["shots"],
                reset_scheme=reset_scheme,
                progress=lambda done, total, _mode=mode, _chunk=chunk_index: progress_counter(
                    done - 1,
                    total,
                    start_time=progress_started,
                    label=f"q3 {_mode} chunk {_chunk + 1}/{len(delay_chunks)}",
                ),
            )
            states = classify_payload_iq(
                cfg, i_values, q_values, telemetry["read_length_cycles"]
            )
            chunk_condition_names = tuple(telemetry["condition_names"])
            if chunk_condition_names != chunk_names:
                raise RuntimeError(
                    f"{mode} chunk {chunk_index + 1} condition axis mismatch: "
                    f"{chunk_condition_names} != {chunk_names}"
                )
            if telemetry.get("condition_tag_mismatches", 0) != 0:
                raise RuntimeError(
                    f"{mode} chunk {chunk_index + 1} condition tags do not "
                    "match the decoded condition axis"
                )
            directional = reduce_bidirectional_condition_states(
                states, chunk_names, canonical_dc_axis=True
            )
            mode_chunks[mode].append({
                "chunk_index": chunk_index,
                "delays_us": delays,
                "I": i_values,
                "Q": q_values,
                "states": states,
                "condition_names": chunk_names,
                "directional": directional,
                "telemetry": telemetry,
            })
            print(
                f"[{mode} chunk {chunk_index + 1}] complete in "
                f"{time.monotonic() - elapsed_started:.2f} s; "
                f"condition-tag mismatches={telemetry.get('condition_tag_mismatches')}"
            )

    mode_results = {}
    for mode in plan["modes"]:
        chunks = sorted(mode_chunks[mode], key=lambda item: item["chunk_index"])
        directional = combine_causality_chunks(
            chunks, delays_us=plan["delays_us"]
        )
        summary = summarize_causality_chunks(
            chunks,
            delays_us=plan["delays_us"],
            shots=plan["shots"],
        )
        mode_results[mode] = {
            "chunks": chunks,
            "condition_names": condition_names,
            "directional": directional,
            "summary": summary,
            "telemetry": [chunk["telemetry"] for chunk in chunks],
        }
        print(
            f"[{mode}] assembled all {len(plan['delays_us'])} delays; "
            f"median P1-P0={_median(summary['P1'] - summary['P0']):.4f}"
        )

    now = datetime.now()
    output_dir = (
        Path(tls.outerFolder) / tls.QUBIT / f"{tls.QUBIT}_{now:%Y_%m_%d}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_base = output_dir / (
        f"{tls.QUBIT}_{now:%H_%M_%S}_Predistortion_"
        f"{len(plan['delays_us'])}pt_Temporary_Test"
    )
    outputs = save_predistortion_causality_outputs(
        output_base,
        plan=plan,
        target_frequency_ghz=target_frequency_ghz,
        realized_frequency_ghz=realized_frequency_ghz,
        dc_vec=dc_vec,
        mode_results=mode_results,
        correction_source=correction_label,
        readout_contract={
            "readout_location": "park",
            "park_gain_dac": common_cfg.get(
                "ff_park_gain", tls._baseline_dc_offset()
            ),
            "accumulator_read_delay_us": common_cfg.get("opx_read_delay_us"),
            "feedback_read_timing": common_cfg.get("opx_feedback_read_timing"),
            "pre_measure_sync": common_cfg.get(
                "opx_feedback_pre_measure_sync"
            ),
            "flux_predistortion_recovery_us": float(plan["recovery_us"]),
            "flux_predistortion_tail_overlaps_payload_readout": bool(
                plan["overlap_payload_readout"]
            ),
            "correction_method": str(compensation.get("method", "legacy_piecewise")),
            "correction_model_sha256": str(compensation.get("model_sha256", "")),
            "correction_segment_edges_ns": list(
                compensation.get("segment_edges_ns", [])
            ),
            "correction_multipliers": list(compensation.get("multipliers", [])),
            "sequence_implementation": (
                "seven temporary OPXResetT15PointProgram chunks; shared classifier; "
                "P0/P1 repeated per chunk; no T1 fit"
            ),
        },
    )
    for frequency_index, frequency in enumerate(target_frequency_ghz):
        on = mode_results["on"]["summary"]["normalized"][frequency_index]
        off = mode_results["off"]["summary"]["normalized"][frequency_index]
        print(
            f"[result] {frequency:.3f} GHz: largest upward normalized step "
            f"on={max(0.0, np.nanmax(np.diff(on))):.3f}, "
            f"off={max(0.0, np.nanmax(np.diff(off))):.3f}"
        )
    print(f"RAW_IQ_NPZ={outputs[0]}")
    print(f"RAW_CSV={outputs[1]}")
    print(f"SUMMARY_JSON={outputs[2]}")
    print(f"COMPARISON_PNG={outputs[3]}")


def apply_diagnostic_read_delay(cfg, environ=None):
    """Apply the requested ADC-accumulator settling delay to a diagnostic run."""
    environ = os.environ if environ is None else environ
    read_delay_us = float(environ.get("Q3_DIAGNOSTIC_READ_DELAY_US", "2.0"))
    if not np.isfinite(read_delay_us) or read_delay_us < 0.0:
        raise ValueError(
            "Q3_DIAGNOSTIC_READ_DELAY_US must be finite and non-negative"
        )
    cfg["opx_read_delay_us"] = read_delay_us
    return read_delay_us


def apply_diagnostic_dmem_verification(cfg, environ=None):
    """Keep exhaustive per-word DMem checks opt-in for small transport tests."""
    environ = os.environ if environ is None else environ
    value = environ.get(
        "Q3_DIAGNOSTIC_VERIFY_DMEM_READS", "off"
    ).strip().lower()
    if value not in ("on", "off"):
        raise ValueError("Q3_DIAGNOSTIC_VERIFY_DMEM_READS must be on or off")
    enabled = value == "on"
    cfg["opx_verify_dmem_reads"] = enabled
    return enabled


def apply_diagnostic_feedback_timing(cfg, environ=None):
    """Select the accumulator handoff sequence for this isolated test."""
    environ = os.environ if environ is None else environ
    mode = environ.get(
        "Q3_DIAGNOSTIC_FEEDBACK_TIMING", "official_wait_all"
    ).strip().lower()
    if mode not in ("official_wait_all", "legacy_absolute_wait"):
        raise ValueError(
            "Q3_DIAGNOSTIC_FEEDBACK_TIMING must be official_wait_all or "
            "legacy_absolute_wait"
        )
    cfg["opx_feedback_read_timing"] = mode
    return mode


def apply_diagnostic_feedback_flush(cfg, environ=None):
    """Enable a second readout event solely to locate accumulator latency."""
    environ = os.environ if environ is None else environ
    value = environ.get("Q3_DIAGNOSTIC_FEEDBACK_FLUSH", "off").strip().lower()
    value = {"on": "readout"}.get(value, value)
    if value not in ("off", "readout", "adc_only"):
        raise ValueError(
            "Q3_DIAGNOSTIC_FEEDBACK_FLUSH must be off, readout, or adc_only"
        )
    cfg["opx_feedback_flush_mode"] = value
    return value


def apply_diagnostic_pre_measure_sync(cfg, environ=None):
    """Align all scheduled channels before the original payload readout."""
    environ = os.environ if environ is None else environ
    value = environ.get(
        "Q3_DIAGNOSTIC_PRE_MEASURE_SYNC", "off"
    ).strip().lower()
    if value not in ("on", "off"):
        raise ValueError("Q3_DIAGNOSTIC_PRE_MEASURE_SYNC must be on or off")
    enabled = value == "on"
    cfg["opx_feedback_pre_measure_sync"] = enabled
    return enabled


def verify_dmem_roundtrip(soc, *, dmem_words, scratch_words=8):
    """Cross-check server bulk DMA against direct tProc AXI access."""
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.acquisition import (
        _read_words,
        _single_read,
        _single_write,
        _write_words,
    )

    dmem_words = int(dmem_words)
    scratch_words = int(scratch_words)
    if scratch_words < 2 or dmem_words <= scratch_words:
        raise ValueError("DMem scratch region must fit at the end of data memory")
    address = dmem_words - scratch_words
    tproc = soc.tproc

    def direct_read():
        return np.asarray(
            [_single_read(tproc, address + offset) for offset in range(scratch_words)],
            dtype=np.uint32,
        )

    def bulk_read():
        return np.asarray(
            _read_words(soc, address, scratch_words, tproc=tproc),
            dtype=np.uint32,
        )

    original = direct_read()
    pattern_a = np.asarray(
        [
            (0x13579BDF + 0x1020304 * index) & 0xFFFFFFFF
            for index in range(scratch_words)
        ],
        dtype=np.uint32,
    )
    pattern_b = np.bitwise_xor(pattern_a, np.uint32(0xA5A5A5A5))
    report = {"address": address, "words": scratch_words}
    try:
        _write_words(soc, address, pattern_a, tproc=tproc)
        report["bulk_write_bulk_read_matches"] = bool(
            np.array_equal(bulk_read(), pattern_a)
        )
        report["bulk_write_direct_read_matches"] = bool(
            np.array_equal(direct_read(), pattern_a)
        )
        for offset, value in enumerate(pattern_b):
            _single_write(tproc, address + offset, int(value))
        report["direct_write_bulk_read_matches"] = bool(
            np.array_equal(bulk_read(), pattern_b)
        )
        report["direct_write_direct_read_matches"] = bool(
            np.array_equal(direct_read(), pattern_b)
        )
    finally:
        for offset, value in enumerate(original):
            _single_write(tproc, address + offset, int(value))
    failures = [
        name for name, passed in report.items()
        if name.endswith("_matches") and not passed
    ]
    if failures:
        raise RuntimeError(
            "DMem round-trip mismatch at the bulk/direct boundary: "
            + ", ".join(failures)
        )
    return report


def main():
    if return_readout_contract_requested():
        os.environ["MPLBACKEND"] = "Agg"
        run_return_readout_contract()
        return
    if sequence_audit_requested():
        run_predistortion_causality()
        return
    if os.environ.get("Q3_TEMPLATE_REFIT_PKL"):
        run_template_refit()
        return
    if os.environ.get("Q3_FRESH_3B", "0").strip().lower() in {
        "1", "true", "yes", "on",
    }:
        correction_json = run_fresh_step3b()
        print(f"FRESH_3B_CORRECTION_JSON={correction_json}")
        return
    if os.environ.get("Q3_FRESH_3A", "0").strip().lower() in {
        "1", "true", "yes", "on",
    }:
        correction_json = run_fresh_step3a()
        print(f"FRESH_3A_CORRECTION_JSON={correction_json}")
        return

    reset_mode = os.environ.get(
        "Q3_DIAGNOSTIC_RESET_MODE", "passive"
    ).strip().lower()
    if reset_mode not in ("passive", "active"):
        raise ValueError("Q3_DIAGNOSTIC_RESET_MODE must be passive or active")
    shots = int(os.environ.get("Q3_DIAGNOSTIC_SHOTS", "60"))
    points = int(os.environ.get("Q3_DIAGNOSTIC_POINTS", "11"))
    center_ghz = float(os.environ.get("Q3_DIAGNOSTIC_CENTER_GHZ", "4.05"))
    if shots < 2:
        raise ValueError("Q3_DIAGNOSTIC_SHOTS must be at least two")

    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.five_point_t1 import (
        estimate_five_point_t1,
        reduce_bidirectional_condition_states,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        FivePointApplesToApples as runner,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
        TLSSpectroscopy as tls,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ThreePointApplesToApples import (
        _integer_dc_grid,
        _target_frequency_grid_ghz,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
        acquire_t1_5pt_iq,
        classify_payload_iq,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
        PASSIVE_T1_RESET_US,
        ProductionResetSession,
        prepare_reset_session,
    )

    runner.install_scan_calibration(tls)
    tls._set_yoko_if_requested()
    soc, soccfg = tls.makeProxy()
    if bool(soc.streamer.readout_running()):
        raise RuntimeError(
            "QICK streamer is already running. Stop the other QICK acquisition "
            "before launching this isolated diagnostic."
        )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.acquisition import (
        dmem_words_from_soccfg,
    )
    dmem_roundtrip = verify_dmem_roundtrip(
        soc,
        dmem_words=dmem_words_from_soccfg(soccfg),
    )
    print(
        "[transport] DMem sentinel PASS: bulk DMA and direct AXI agree for "
        f"both write paths at address {dmem_roundtrip['address']} "
        f"({dmem_roundtrip['words']} words)"
    )

    params = dict(runner.P6_5PT_APPLES_TO_APPLES)
    full_target = _target_frequency_grid_ghz(params)
    full_dc, full_realized = _integer_dc_grid(params, full_target)
    target, dc_vec, indices = select_diagnostic_slice(
        full_target, full_dc, center_ghz=center_ghz, points=points
    )
    realized = np.asarray(full_realized)[indices]
    compensation, correction_mode = tls._resolve_step6_correction(
        params, None, tls.outerFolder
    )

    print(
        "[diagnostic] acquiring the DMem-native IQ classifier; the five-point "
        f"scan itself will use {reset_mode} reset"
    )
    classifier_session = prepare_reset_session(
        "active",
        outer_folder=tls.outerFolder,
        qubit=tls.QUBIT,
        base_cfg=tls.BaseConfig,
        soc=soc,
        soccfg=soccfg,
        purpose="FivePointMeasurementDiagnosticClassifier",
    )
    print(
        "[diagnostic] DMem-native classifier calibration saved: "
        f"{classifier_session.calibration_output}"
    )

    cfg = dict(tls.BaseConfig)
    cfg.update({
        "shots": shots,
        "ff_gain_vec": dc_vec,
        "apply_flux_tail_compensation": True,
        "flux_tail_compensation": compensation,
        "flux_fit_params": tls.FLUX_FIT_PARAMS,
        "relax_delay": PASSIVE_T1_RESET_US,
        "qubit_pulse_style": "arb",
        "flux_settle_time_us": float(params["flux_settle_us"]),
        "readout_thermalization_us": float(
            params["readout_thermalization_us"]
        ),
        "opx_t1_3pt_gain_lookup": True,
        "opx_diagnostic_condition_tags": True,
    })
    verify_dmem_reads = apply_diagnostic_dmem_verification(cfg)
    read_delay_us = apply_diagnostic_read_delay(cfg)
    feedback_timing = apply_diagnostic_feedback_timing(cfg)
    feedback_flush = apply_diagnostic_feedback_flush(cfg)
    pre_measure_sync = apply_diagnostic_pre_measure_sync(cfg)
    if reset_mode == "active":
        cfg = classifier_session.apply(cfg)
    else:
        cfg = ProductionResetSession.passive().apply(cfg)
        # Preserve the DMem-native payload classifier while leaving the scan's
        # between-record reset behavior strictly passive.
        cfg["opx_reset_calibration"] = dict(classifier_session.calibration)
    park_gain = cfg.get("ff_park_gain", tls._baseline_dc_offset())
    condition_names = (
        "P0",
        "P1",
        *(f"Ps_{delay:g}us" for delay in params["decay_delays_us"]),
    )
    reset_scheme = "opx_unbounded" if reset_mode == "active" else "none"

    print(
        "[diagnostic] small real measurement: "
        f"{shots} shots x {len(dc_vec)} frequencies x 5 conditions; "
        f"{target[0]:.4f}..{target[-1]:.4f} GHz; "
        f"reset={reset_mode}; predistortion={correction_mode}; "
        f"accumulator_read_delay={read_delay_us:g} us; "
        f"feedback_timing={feedback_timing}; feedback_flush={feedback_flush}"
        f"; pre_measure_sync={pre_measure_sync}; "
        f"exhaustive_dmem_verify={verify_dmem_reads}"
    )
    print(
        f"[diagnostic] expecting {shots * len(dc_vec) * 5} resident records; "
        "acquiring now"
    )
    started, progress_started = start_diagnostic_timers()
    i_values, q_values, telemetry = acquire_t1_5pt_iq(
        soc,
        soccfg,
        cfg,
        dc_gains=dc_vec,
        delays_us=params["decay_delays_us"],
        reference_hold_us=float(params["reference_hold_us"]),
        shots=shots,
        reset_scheme=reset_scheme,
        progress=make_shot_progress(progress_started),
    )
    elapsed = time.monotonic() - started
    states = classify_payload_iq(
        cfg, i_values, q_values, telemetry["read_length_cycles"]
    )
    directional = reduce_bidirectional_condition_states(
        states, condition_names, canonical_dc_axis=True
    )
    survival = np.column_stack(
        [directional[name] for name in condition_names[2:]]
    )
    estimate = estimate_five_point_t1(
        directional["P0"],
        directional["P1"],
        survival,
        params["decay_delays_us"],
        shots_per_condition=shots,
        min_ref_contrast=float(params["min_ref_contrast"]),
        max_relative_error=float(params["max_relative_error"]),
        max_t1_us=float(params["max_fit_t1_us"]),
    )

    print(
        f"[measurement] completed in {elapsed:.2f} s; "
        f"IQ shape={i_values.shape}; states shape={states.shape}"
    )
    dmem_verification = telemetry.get("dmem_read_verification", {})
    print(
        "[transport] resident-bank verification: "
        f"bulk_matches_direct={dmem_verification.get('bulk_matches_direct')}, "
        f"banks={dmem_verification.get('banks_compared')}, "
        f"words={dmem_verification.get('words_compared')}"
    )
    print(
        "[ordering] FPGA condition tags: "
        f"mismatches={telemetry.get('condition_tag_mismatches')}; "
        "zero means the tProc emission order and host decode agree"
    )
    print(
        "[populations] medians: "
        + ", ".join(
            f"{name}={_median(directional[name]):.4f}"
            for name in condition_names
        )
    )
    contrast = np.asarray(directional["P1"]) - np.asarray(directional["P0"])
    valid = np.asarray(estimate["T1_5pt_valid_mask"], dtype=bool)
    print(
        f"[quality] median P1-P0={_median(contrast):.4f}; "
        f"valid T1={int(valid.sum())}/{valid.size} "
        f"({100.0 * valid.mean():.1f}%)"
    )
    print(
        "[direction-check] median P1-P0: "
        f"up={_median(np.asarray(directional['P1_scan_up']) - np.asarray(directional['P0_scan_up'])):.4f}, "
        f"down={_median(np.asarray(directional['P1_scan_down']) - np.asarray(directional['P0_scan_down'])):.4f}"
    )
    print(
        "[iq-check] median I by decoded condition: "
        + ", ".join(
            f"{name}={_median(i_values[index]):.7g}"
            for index, name in enumerate(condition_names)
        )
    )
    print("[record-offset-check] median P1-P0 under cyclic condition shifts:")
    shift_contrasts = {}
    for shift in range(len(condition_names)):
        shifted = reduce_bidirectional_condition_states(
            np.roll(states, shift, axis=0),
            condition_names,
            canonical_dc_axis=True,
        )
        shift_contrasts[shift] = _median(
            np.asarray(shifted["P1"]) - np.asarray(shifted["P0"])
        )
        print(f"  shift={shift:+d}: {shift_contrasts[shift]:+.4f}")

    now = datetime.now()
    output_dir = (
        Path(tls.outerFolder)
        / tls.QUBIT
        / f"{tls.QUBIT}_{now:%Y_%m_%d}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = output_dir / f"{tls.QUBIT}_{now:%H_%M_%S}_5pt_measurement_diagnostic"
    npz_path = Path(str(stem) + "_raw_iq.npz")
    csv_path = Path(str(stem) + "_populations.csv")
    json_path = Path(str(stem) + "_summary.json")
    np.savez_compressed(
        npz_path,
        I=i_values,
        Q=q_values,
        states=states,
        condition_names=np.asarray(condition_names),
        target_frequency_ghz=target,
        realized_frequency_ghz=realized,
        dc_offset_dac=dc_vec,
    )
    columns = {
        "target_frequency_ghz": target,
        "realized_frequency_ghz": realized,
        "dc_offset_dac": dc_vec,
    }
    for name in condition_names:
        columns[name] = np.asarray(directional[name])
        columns[f"{name}_scan_up"] = np.asarray(
            directional[f"{name}_scan_up"]
        )
        columns[f"{name}_scan_down"] = np.asarray(
            directional[f"{name}_scan_down"]
        )
    for name in (
        "ref_contrast_5pt",
        "T1_5pt_us_raw",
        "T1_5pt_us",
        "T1_5pt_err_us",
        "T1_5pt_valid_mask",
    ):
        columns[name] = np.asarray(estimate[name])
    _save_csv(csv_path, columns)
    summary = {
        "created": now.isoformat(),
        "reset_mode": reset_mode,
        "shots_per_condition": shots,
        "frequency_points": int(len(dc_vec)),
        "condition_names": condition_names,
        "median_populations": {
            name: _median(directional[name]) for name in condition_names
        },
        "median_reference_contrast": _median(contrast),
        "valid_t1_points": int(valid.sum()),
        "total_t1_points": int(valid.size),
        "condition_shift_reference_contrasts": shift_contrasts,
        "telemetry": telemetry,
        "dmem_roundtrip": dmem_roundtrip,
        "classifier_calibration": str(classifier_session.calibration_output),
        "accumulator_read_delay_us": read_delay_us,
        "feedback_read_timing": feedback_timing,
        "feedback_flush_mode": feedback_flush,
        "pre_measure_sync": pre_measure_sync,
        "correction_mode": correction_mode,
        "raw_iq_npz": str(npz_path),
        "populations_csv": str(csv_path),
        "park_gain": park_gain,
    }
    with open(json_path, "w") as handle:
        json.dump(summary, handle, indent=2, default=_json_default)
    print(f"RAW_IQ_NPZ={npz_path}")
    print(f"DIAGNOSTIC_CSV={csv_path}")
    print(f"SUMMARY_JSON={json_path}")
    if _median(contrast) <= 0.05:
        print(
            "[diagnostic] FAIL: P1 is not above P0 with usable contrast before "
            "the five-point fitter. Inspect the condition-shift table and raw IQ."
        )
    else:
        print("[diagnostic] PASS: measured P1 is above P0 with usable contrast")


if __name__ == "__main__":
    main()
