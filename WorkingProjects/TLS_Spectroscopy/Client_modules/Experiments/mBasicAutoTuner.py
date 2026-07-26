"""A deliberately simple, measurement-first single-qubit auto tuner.

This module automates the tune-up that has worked manually in this repository:

    resonator -> wide qubit spectrum -> provisional IQ Rabi
    -> bootstrap readout grid -> canonical single-shot control selection
    -> error-amplified SS control -> joint readout/control/duration refinement

The implementation is intentionally independent of :mod:`mAutoTuner`.  Early
averaged-IQ experiments are *seeds*, never verdicts.  The optimization objective is
the exact paired ground/excited ``SingleShotProgram`` used by
``TLSSpectroscopy.py`` step 5.  In the report-only duration portfolio, the pure
fidelity winner remains untouched by leakage or coherent-control screening.  A
second, explicitly labelled balanced recommendation is selected only among
statistically noninferior pulses after constant-area duration partners, deterministic
gain zooms, leakage, and repeated-pulse behavior have all been measured.  A weak
starting point never prevents the search, and an optional-stage failure never erases
the best directly measured candidate.

After spectroscopy and coherent Rabi locate physical frequency basins, the tuner uses
a structured joint search over readout duration/gain and Gaussian duration/pi gain.
Every duration pair receives measurements; multi-fidelity elimination and a local
Matérn trust-region surrogate refine several basins without allowing a noisy early
winner to erase the rest.  Final selection is based only on fresh held-out replays.
A Pareto replay minimizes X180-plus-readout latency only inside a predeclared fidelity
noninferiority bound; low-fidelity speedups are never part of the feasible set.
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import io
import json
import math
import os
import pickle
import sys
import time
import warnings
from contextlib import redirect_stdout
from statistics import NormalDist

import matplotlib.pyplot as plt
import h5py
import numpy as np
from scipy.optimize import OptimizeWarning, curve_fit
from scipy.signal import find_peaks, savgol_filter
from scipy.stats import t as student_t
from qick import AveragerProgram, RAveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import (
    ExperimentClass, NpEncoder,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mRabiChevronSS import (
    RabiSSProgram,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import (
    SingleShotProgram,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset, ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    add_qubit_gaussian, explicit_flat_top_fields, readout_drive_length_us,
    pulse_fingerprint, set_readout_pulse,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.ss_helpers import (
    find_blob_median, find_threshold,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.basic_joint_optimizer import (
    CandidateArchive,
    PulseCandidate,
    duration_stratified_shortlist,
    fidelity_evidence,
    latency_pareto_frontier,
    propose_trust_region_candidates,
    select_shortest_noninferior,
    unique_candidate_rows,
    validate_structured_coverage,
)


BASIC_AUTOTUNER_REVISION = "gain-only-search-v14"


BASIC_DEFAULTS = {
    "random_seed": 271828,
    # A normal console transcript is not enough to debug hardware-path failures.
    # Production runs therefore stream every raw single-shot/control IQ acquisition
    # into one self-contained HDF5 bundle and embed the complete final Python data
    # archive at save time.  Tests stay lightweight unless force_without_hardware is
    # explicitly enabled.
    "diagnostics": {
        "enabled": True,
        "force_without_hardware": False,
        "compression": "gzip",
        "compression_level": 4,
        "flush_every_records": 8,
    },
    # Optional explicit pickle from an interrupted run of this exact revision.  Only
    # complete coarse cells with the same physical input contract are reused;
    # medium/final candidates are freshly replayed in the current drift epoch.
    "resume_checkpoint": None,
    "max_consecutive_point_failures": 5,
    # ``concise`` keeps the operator informed at human-scale stage boundaries while
    # retaining every technical message in data['report'].  Set to ``detailed`` only
    # when debugging an acquisition problem.
    "console": {"verbosity": "concise"},
    "calibration_drift": {
        "max_angle_degrees": 25.0,
        "max_independent_fidelity_change": 0.08,
        "max_fixed_discriminator_fidelity_loss": 0.08,
        "max_midpoint_shift_fraction": 0.25,
    },
    "reset": {
        # Direct-control stages use fresh tProc feedback once a usable readout/pi tuple
        # exists.  Readout-coordinate maps deliberately revert to passive reset because
        # their changing integration length/frequency/gain invalidates one raw feedback
        # threshold; the winner is re-probed immediately afterward.
        "enabled": True, "probe_shots": 2000, "max_iters": 3,
        "min_activation_fidelity": 0.75,
        "min_raw_assignment_fidelity": 0.80,
        "min_passive_relax_t1_multiple": 5.0,
        "assumed_qubit_t1_us": None,
        "res_phase_calibration": {
            "enabled": True, "phase_step_deg": 15.0,
            "sweep_shots": 800, "check_shots": 3000,
            "relax_delay_us": 500.0,
        },
        # Clear residual measurement photons before every calibrated control pulse.
        # Kept explicit in the saved reset record even though the shared primitive
        # also fails safe to this value for non-tuner callers.
        "thermalization_us": 25.0,
        "post_measure_delay_us": 0.05,
        # The reset drive gain/control are frozen.  A raw threshold is calibrated and
        # cached for every ADC integration length/readout frequency used by the joint
        # search, so changing the scoring gain no longer disables feedback reset.
        "profile_shots": 650,
        "profile_min_raw_fidelity": 0.72,
        "profile_validate": True,
        # The residual-population reset probe is necessary but not authoritative:
        # a threshold/path error can pass that probe while destroying the actual
        # TLS step-5 g/e clouds.  Every profile must therefore reproduce the same
        # complete pulse tuple against passive preparation before it is allowed to
        # affect an optimizer score.
        "exact_qualification_shots": 650,
        "exact_qualification_blocks": 2,
        "exact_min_feedback_fidelity": 0.70,
        "exact_max_fidelity_loss": 0.030,
        "exact_max_block_loss": 0.080,
        "exact_min_separation_ratio": 0.70,
        # A large, statistically resolved passive-to-feedback collapse is a path
        # mismatch, not a profile-specific fluctuation.  Disable feedback for the
        # remainder of the run instead of repeatedly poisoning later durations.
        "exact_catastrophic_loss": 0.10,
    },
    "baseline": {"shots": 800, "blocks": 2},
    "resonator": {
        "enabled": True, "span_mhz": 4.0, "points": 61, "shots": 120,
        "polarity": "dip", "wide_span_mhz": 12.0, "wide_points": 101,
        "min_contrast_snr": 5.0, "always_wide": True,
        # Prefer a device-independent prior around initialize.py.  Absolute bounds
        # remain an explicit override for characterized-device studies.  The outer
        # scan is padded only to fit a line exactly at the +/-radius limit; candidates
        # in that padding are never accepted.
        "search_min_mhz": None, "search_max_mhz": None,
        "search_radius_mhz": 100.0,
        "search_expansion_radii_mhz": [5.0, 25.0, 100.0],
        "search_edge_padding_mhz": 2.0,
        "search_step_mhz": 0.20,
        # Four MHz leaves enough off-resonant baseline around the measured
        # ~0.34-MHz-wide q4 notch.  A 1.2-MHz confirmation let the quadratic
        # background absorb a real modest-depth notch and reject it as low SNR.
        "confirmation_span_mhz": 4.0, "confirmation_points": 81,
        "confirmation_shots": 120,
        "edge_guard_points": 2, "min_relative_contrast": 0.002,
        "min_feature_width_mhz": 0.04, "max_feature_width_mhz": 2.0,
        # A broad readout scan may contain several real resonators or package modes.
        # Preserve and independently confirm several notches; qubit spectroscopy then
        # selects the physically useful resonator/qubit branch.
        "max_candidates": 8,
        "min_candidate_separation_mhz": 1.0,
        "max_confirmation_width_ratio": 2.5,
        "max_confirmation_shift_mhz": 0.25,
        # Averaged discovery must not inherit a deliberately bad/zero input readout.
        # The input gain is also tried if the safe gain does not survive an independent
        # confirmation scan.  This bootstrap is never written without direct SS
        # optimization and a final exact-tuple replay.
        "discovery_gain": 5000, "discovery_length_us": 10.0,
    },
    "spectroscopy": {
        "enabled": True, "local_span_mhz": 20.0, "local_points": 81,
        "wide_span_mhz": 80.0, "wide_points": 121, "gain": 7000,
        "pulse_length_us": 2.0, "shots": 80, "max_candidates": 8,
        "min_feature_snr": 3.0, "always_wide": True,
        # Search the complete configurable prior around initialize.py.  Unlike the
        # resonator search this is intentionally not stopped at the first feature: a
        # nearby TLS must not hide a farther qubit inside the authorized window.
        # Absolute bounds remain available as an explicit override.
        "search_min_mhz": None, "search_max_mhz": None,
        "search_radius_mhz": 100.0,
        "search_edge_padding_mhz": 10.0,
        "search_step_mhz": 2.0, "coarse_candidates": 8,
        # Overlapping broad lines need not make two local maxima: the weaker qubit
        # can be only a shoulder on a stronger TLS.  Add a capped set of separated,
        # high-residual shoulder proposals before the ordinary opposed confirmations.
        "coarse_shoulder_fraction": 0.18,
        "coarse_shoulder_separation_steps": 1.25,
        "coarse_min_shoulder_candidates": 2,
        # The high-power hardware line can be several MHz wide.  A narrow 6-MHz
        # confirmation lets the smooth-baseline model absorb that line and reject a
        # real transition, so retain the proven 20-MHz local spectroscopy window.
        "confirmation_span_mhz": 20.0, "confirmation_points": 81,
        "confirmation_shots": 60, "max_repeat_error_mhz": 0.60,
        "confirmation_min_feature_snr": 4.0,
        "confirmation_min_fit_r2": 0.25,
        "confirmation_max_linewidth_mhz": 8.0,
        "coarse_capture_mhz": 2.0,
        "confirmation_neighbor_mask_mhz": 1.5,
        "confirmation_neighbor_radius_mhz": 8.0,
        # Every independently confirmed notch may be evaluated through the expensive
        # opposed spectroscopy confirmation.  The cap matches resonator.max_candidates
        # and exists only to bound pathological package-mode forests.
        "max_resonator_branches": 8,
        # Once two branches both show spectroscopy/Rabi, compare their complete rough
        # physical tuples with the actual step-5 single-shot objective before choosing
        # which readout neighborhood receives the expensive joint optimization.
        "branch_ss_shots": 250, "branch_ss_blocks": 2,
        # A physical single-line fit is preferred, but spectroscopy is a basin
        # generator rather than the final control verdict.  Two fresh opposed scans
        # with a strong, correlated complex response may provisionally seed Rabi when
        # overlapping lines make every one-line linewidth fit hit its bound.
        "confirmation_allow_provisional_seed": True,
        "confirmation_provisional_min_snr": 4.0,
        "confirmation_provisional_min_complex_correlation": 0.50,
        "edge_guard_points": 2,
    },
    "iq_rabi": {
        "enabled": True, "local_span_mhz": 4.0,
        "freq_points_per_candidate": 5, "gain_min": 0, "gain_max": 30000,
        "gain_points": 31, "shots": 60, "min_r2": 0.55,
        "witness_min_snr": 5.0, "witness_min_relative_contrast": 0.10,
        "fine_gain_points": 41, "shortlist": 4,
    },
    "rough_single_shot": {
        # A small direct-SS chevron is run independently in every retained spectral
        # basin before any basin is discarded.  This is the automated counterpart of
        # the manual SS Rabi-chevron step and protects a weak true qubit from a strong
        # but irrelevant TLS ridge or a poor averaged-IQ fit.
        "coarse_shots": 140, "freq_span_mhz": 2.0, "freq_points": 3,
        "gain_fraction": 0.35, "gain_points": 5,
        "shots": 700, "blocks": 2,
    },
    "parity_chevron": {
        "enabled": True, "freq_span_mhz": 1.5, "freq_points": 9,
        "gain_fraction": 0.22, "gain_points": 9, "pulse_counts": [3, 4, 5],
        "shots": 100, "confirm_shots": 600, "confirm_blocks": 2,
        "min_contrast_sigma": 5.0, "min_depth_correctness": 0.55,
        "min_consistent_depth_fraction": 0.67,
        # Qualify every independently coherent Rabi basin before the expensive joint
        # optimizer.  A one-pulse SS maximum is not allowed to create a transition,
        # but a rough pulse is not required to pass the *final* pulse-quality audit
        # before the optimizer has had a chance to tune its gain and duration.
        "max_control_branches": 6,
        "branch_compare_shots": 900, "branch_compare_blocks": 3,
        "max_rabi_frequency_shift_mhz": 2.0,
        "qualified_basin_radius_mhz": 2.0,
        # A branch comparison made with a collapsed discriminator must not erase a
        # strong passive bootstrap/Rabi basin over a millipercent coin-flip tie.
        "minimum_informative_branch_fidelity_lcb": 0.60,
        "minimum_informative_branch_separation_sigma": 0.75,
        # Early readout is only a bootstrap discriminator.  It may have much lower
        # contrast than the later optimized readout, but must still resolve enough
        # population to test odd/even action rather than confuse readout quality with
        # transition coherence.
        "fallback_minimum_binary_contrast": 0.12,
        # This high-statistics rough audit runs only for the few coherent-Rabi
        # branches.  Passing it can resolve two competing transitions; failing it is
        # now provisional evidence and cannot block gain/duration optimization.
        "prequalification_shot_multiplier": 8,
    },
    "fine_frequency": {
        # Repeated (+Xpi,-Xpi) pseudoidentity pairs amplify coherent detuning without
        # assuming that half of the X180 DAC code is a calibrated X90.
        "enabled": True, "span_mhz": 1.0, "points": 17, "pairs": 5,
        "shots": 220, "calibration_shots": 500,
        "confirm_shots": 700, "confirm_blocks": 2,
        "min_contrast_sigma": 5.0,
    },
    "amplified_error": {
        # The QUA ``ALE_tune_1Q.py`` file actually runs amplified AMPLITUDE error
        # (AAE), not leakage.  This is its X180 analogue: multi-depth odd/even parity
        # jointly refines frequency and gain.  Several depths suppress the aliases
        # that make a single repeated-pulse count unsafe.
        "enabled": True, "freq_span_mhz": 0.5, "freq_points": 3,
        "gain_fraction": 0.08, "gain_points": 11,
        "pulse_counts": [5, 6, 7, 9, 10, 11, 13, 14, 15],
        "shots": 80, "calibration_shots": 500,
        "confirm_shots": 700, "confirm_blocks": 2,
        "min_contrast_sigma": 5.0, "min_depth_correctness": 0.55,
        "min_consistent_depth_fraction": 0.67,
    },
    "leakage": {
        # The basic workflow defaults to a practical fixed-Gaussian screen: compare
        # independently tuned duration/power candidates and reject reproducible
        # third-cloud growth, then independently replay the winner.  It deliberately
        # does not search DRAG waveforms and does not rename an IQ-cloud anomaly P(f).
        # Strict identity+shelving qutrit response inversion remains opt-in because an
        # old anharmonicity prior is not enough to prove a usable present-day e-f
        # calibration.  Set this to ``auto`` to activate it when that metadata exists;
        # otherwise retain the explicitly labelled operational third-cloud screen.
        "enabled": False, "operational_enabled": True,
        "required_for_write": True,
        # Legacy repeated-return settings remain available for detailed diagnostics,
        # but AAE already performs the correct multi-depth coherent-error refinement.
        # They are off in the basic screen because return error is not a leakage
        # measurement and custom DRAG uploads made this stage needlessly fragile.
        "operational_repeated_return_enabled": False,
        "operational_depths": [1, 2, 3, 4, 6, 8],
        "operational_shots": 220, "operational_reference_shots": 500,
        # Retry a fresh before/after discriminator bracket when drift, rather than
        # leakage, is the only reason an otherwise safe waveform was invalid.
        "operational_drift_retries": 2,
        "operational_verify_shots": 650, "operational_verify_blocks": 3,
        "operational_max_even_return_error": 0.12,
        "operational_max_odd_inversion_error": 0.12,
        "operational_min_binary_contrast": 0.45,
        "operational_tune_drag": False,
        "operational_beta_span": 0.08, "operational_beta_points": 7,
        "operational_max_beta_span": 0.16,
        "operational_max_extensions": 2,
        # Six slots cover every default duration instead of allowing several nearby
        # beta values from one duration to crowd out the duration/power comparison.
        "operational_max_candidate_waveforms": 6,
        "operational_selection_shots": 900,
        "operational_selection_blocks": 3,
        "operational_selection_shortlist": 6,
        # Candidates inside this joint uncertainty/margin band are treated as tied;
        # the longer, lower-power Gaussian wins that tie.
        "operational_fidelity_tie_margin": 0.003,
        "operational_max_tie_fidelity_loss": 0.010,
        # The legacy tail-excess metric can cancel when a readout-induced third cloud
        # appears in *both* prepared states.  A deterministic 2-D Gaussian-mixture
        # model therefore compares two versus three resolved IQ populations.  A
        # supported third population may be small, but it may not exceed either the
        # combined or single-preparation bounds below.
        "third_cluster_min_bic_improvement": 20.0,
        "third_cluster_min_separation_sigma": 3.5,
        "max_third_cluster_fraction": 0.05,
        "max_single_state_third_cluster_fraction": 0.08,
        "anharmonicity_prior_mhz": None,
        "ef_span_mhz": 100.0, "ef_points": 101,
        "ef_narrow_span_mhz": 6.0, "ef_narrow_points": 61,
        "ef_spec_gain": 7000, "ef_spec_shots": 300,
        "ef_min_feature_snr": 4.0, "ef_max_repeat_error_mhz": 1.5,
        # Keep several peaks from each opposed scan and associate the same physical
        # feature across the two passes.  Comparing only each pass's strongest peak
        # falsely rejects a real e-f line whenever a different weak feature swaps rank.
        "ef_feature_candidates": 8,
        # A separately calibrated long/narrow-bandwidth Gaussian prepares the qutrit
        # response references.  Using the candidate pulse to define "pure e" would
        # absorb its own leakage into the response matrix and make one-pulse P(f)
        # circularly zero by construction.
        "reference_sigma_us": 0.50,
        "reference_gain_max": 30000, "reference_gain_points": 41,
        "reference_rabi_shots": 300, "reference_min_rabi_r2": 0.55,
        "reference_min_contrast": 0.20,
        "reference_max_return_fraction": 0.35,
        "ef_gain_max": 30000, "ef_gain_points": 41,
        "ef_rabi_shots": 300, "ef_min_rabi_r2": 0.55,
        "ef_min_rabi_contrast": 0.15, "ef_max_return_fraction": 0.40,
        # beta is peak derivative-Q / peak Gaussian-I.  Both signs must be searched
        # because the physical sign depends on the mixer/cabling convention.
        "beta_span": 0.08, "beta_points": 7,
        "max_beta_span": 0.20, "max_extensions": 2,
        # Include a direct one-pulse witness and repeated-pulse leakage amplifiers.
        "depths": [1, 2, 4, 8], "gap_phases": [0.0, 0.5],
        "shots": 250, "reference_shots": 400,
        # Leakage maps screen feasibility; a separate round-robin held-out replay
        # selects fidelity so the largest of many noisy beta estimates cannot win.
        "selection_fidelity_shots": 900,
        "selection_fidelity_blocks": 3, "selection_shortlist": 5,
        "verify_shots": 800, "verify_blocks": 3,
        "familywise_alpha": 0.05, "confidence_sigma": 1.96,
        "max_response_condition": 40.0,
        "min_identity_selectivity": 0.45,
        "min_shelving_selectivity": 0.45,
        # Hard constraints.  Fidelity is maximized only inside this feasible set.
        "max_single_p2": 0.02, "max_amplified_p2": 0.03,
        "max_third_blob_excess": 0.05,
        "max_candidate_waveforms": 3,
    },
    "readout": {
        "enabled": True, "freq_span_mhz": 2.0, "freq_points": 11,
        "gain_min": 1000, "gain_max": 10000, "gain_points": 11,
        "shots": 140, "shortlist": 3, "confirm_shots": 600,
        "confirm_blocks": 2,
        "max_tie_fidelity_loss": 0.010,
        "local_freq_span_mhz": 0.8, "local_freq_points": 5,
        "local_gain_fraction": 0.25, "local_gain_points": 5,
    },
    "readout_length": {
        "enabled": True,
        # Dense timing coverage near the useful short-readout boundary prevents a
        # coarse 8->14 us jump from masquerading as the shortest acceptable result.
        # Very short points are measured, not forbidden; the fidelity constraint is
        # what rejects a 1-us/60% readout.
        "values_us": [float(value) for value in range(1, 21)],
        "min_us": 1.0, "max_us": 20.0,
        "freq_span_mhz": 0.8, "freq_points": 3,
        # A separate broad power axis is measured at every length.  Reusing one
        # +/-25% neighborhood biases the comparison because short integrations can
        # need several times the drive of long integrations.
        "gain_min": 1000, "gain_max": 10000, "gain_points": 7,
        "shots": 160, "shortlist": 3, "confirm_shots": 700,
        "confirm_blocks": 2,
        # Global top-K can fill every held-out slot with variants of the starting
        # length.  Confirm two coarse frequency/gain cells at every tested length.
        "confirm_per_length": 2,
    },
    "qubit": {
        "enabled": True, "freq_span_mhz": 3.0, "freq_points": 11,
        "gain_fraction": 0.50, "gain_points": 11, "shots": 140,
        "shortlist": 3, "confirm_shots": 700, "confirm_blocks": 2,
        "local_freq_span_mhz": 0.8, "local_freq_points": 7,
        "local_gain_fraction": 0.22, "local_gain_points": 7,
    },
    "pulse_duration": {
        # The physical Gaussian gate length is 4*sigma.  Every sigma gets its own
        # local frequency/gain retune; comparing sigma at one fixed gain is invalid.
        "enabled": True,
        "sigma_values_us": [0.05, 0.10, 0.15, 0.25, 0.35, 0.50],
        "freq_span_mhz": 1.0, "freq_points": 3,
        "gain_fraction": 0.28, "gain_points": 5, "shots": 160,
        "shortlist": 3, "confirm_shots": 700, "confirm_blocks": 2,
        "confirm_per_sigma": 2,
    },
    "joint_search": {
        # This replaces greedy readout-length/qubit-gain/pulse-duration coordinate
        # descent.  Every duration pair receives a broad joint readout/pi-gain sweep.
        "enabled": True,
        "read_lengths_us": [float(value) for value in range(1, 21)],
        "sigma_values_us": [0.05, 0.10, 0.15, 0.25, 0.35, 0.50],
        "read_gain_min": 1000, "read_gain_max": 10000,
        # Ten points give an input-independent 1000-DAC backbone (including 5000)
        # across the normal 1k--10k operating range.  The current in-range gain is
        # added separately, so it cannot displace any of these powers.
        "read_gain_points": 10,
        # The fast QICK sweep includes gain zero as the shared ground reference and
        # uniformly spans past the rough Rabi pi estimate for this duration.
        "qubit_gain_points_including_ground": 15,
        "qubit_gain_max_scale": 1.85,
        "qubit_gain_hard_max": 32767,
        "coarse_shots": 56,
        "medium_per_duration_pair": 1,
        "medium_global_count": 24,
        "medium_max_candidates": 110,
        "medium_shots": 260, "medium_blocks": 2,
        # A small Matérn trust-region surrogate refines gains/frequencies around
        # several measured basins; it never selects an unmeasured candidate.
        "trust_regions": 6, "trust_proposals": 36,
        "trust_pool_size": 3000,
        "trust_read_frequency_radius_mhz": 0.40,
        "trust_qubit_frequency_radius_mhz": 0.70,
        # Quantization keeps the surrogate from requesting dozens of nearly identical
        # reset discriminator profiles.  All proposed points remain real measurements;
        # this only chooses a reusable local hardware lattice for their frequencies.
        "trust_read_frequency_points": 5,
        "trust_qubit_frequency_points": 7,
        "trust_read_gain_fraction": 0.30,
        "trust_qubit_gain_fraction": 0.30,
        "trust_shots": 420, "trust_blocks": 2,
        "closure_iterations": 2,
        "closure_frequency_radius_scale": 0.55,
        "closure_gain_radius_scale": 0.60,
        # A runtime-limited search must not become a short-duration search merely
        # because those cells happened to be shuffled first.  The first gain pass is
        # mandatory and covers every read-length/sigma pair before any pair receives
        # a second readout power.  Three mandatory passes exercise the centre and both
        # interior quartiles; later passes retain the same round-robin rule.
        "minimum_duration_coverage_passes": 3,
        # Reserve distinct tails for held-out duration-stratified comparison and for
        # frequency/AAE closure.  Without these reservations the coarse map can consume
        # the entire soft budget, leaving its winner unconfirmed and uncorrected.
        "reserve_medium_minutes": 6.0,
        "reserve_control_refinement_minutes": 7.0,
        # The operator never discovers an hour-long fallback after launch.  This is a
        # soft acquisition budget: completed measurements remain reportable and final
        # confirmation receives a reserved tail budget.
        "runtime_budget_minutes": 30.0,
        "reserve_final_minutes": 5.0,
    },
    "duration_portfolio": {
        # Manual-selection mode: produce one independently screened calibration for
        # every integer readout duration and never write initialize.py.  Discovery,
        # averaged Rabi, and AAE are shared; the full readout/control tuple is then
        # remeasured and safety-audited separately at each duration.
        "enabled": True,
        "manual_selection_only": True,
        "read_lengths_us": [float(value) for value in range(1, 21)],
        # Cross several measured readout basins with several AAE/Rabi control basins,
        # then add a small fixed-duration trust-region refinement.  Every duration
        # receives the same number of attempted candidates.
        "native_seeds_per_length": 3,
        "readout_seeds_per_length": 2,
        "control_seed_count": 3,
        # The stochastic proposals remain useful for discovering a different local
        # basin, but they are no longer accepted as evidence that either DAC gain is
        # locally optimal.  A deterministic axial challenge and a two-dimensional
        # zoom below are mandatory around the measured winner.
        "local_proposals_per_length": 4,
        "local_read_frequency_radius_mhz": 0.30,
        "local_qubit_frequency_radius_mhz": 0.50,
        "local_read_gain_fraction": 0.22,
        "local_qubit_gain_fraction": 0.22,
        "refine_shots": 260,
        "refine_blocks": 2,
        "deterministic_gain_refinement": True,
        # Round one independently challenges readout and X180 gain, avoiding the
        # combinatorial cost of a broad Cartesian grid while proving that neither
        # coarse-lattice coordinate was simply inherited.  Round two is a full 3x3
        # local interaction check around the newly measured winner.
        "gain_axis_read_fraction": 0.15,
        "gain_axis_read_points": 5,
        "gain_axis_qubit_fraction": 0.08,
        "gain_axis_qubit_points": 5,
        "gain_zoom_read_fraction": 0.04,
        "gain_zoom_read_points": 3,
        "gain_zoom_qubit_fraction": 0.025,
        "gain_zoom_qubit_points": 3,
        "gain_zoom_max_rounds": 3,
        "gain_minimum_read_step_dac": 100,
        "gain_minimum_qubit_step_dac": 100,
        "gain_refine_shots": 300,
        "gain_refine_blocks": 2,
        "gain_zoom_shots": 420,
        "gain_zoom_blocks": 2,
        # For a Gaussian X180, gain*sigma is the ideal two-level pulse area.  Test
        # exact half/double-duration partners, including sigma values (such as 0.30
        # us) which are absent from the original coarse duration list.  Each partner
        # receives its own local amplitude challenge; area scaling is only a seed.
        "constant_area_sigma_factors": [],
        "constant_area_qubit_fraction": 0.08,
        "constant_area_qubit_points": 5,
        "constant_area_sigma_min_us": 0.05,
        "constant_area_sigma_max_us": 0.50,
        "pulse_family_aae_enabled": False,
        # Selection is deliberately one-dimensional: maximize independently replayed
        # single-shot fidelity at the fixed readout duration.  Leakage and coherent
        # control are measured afterward on that exact winner and reported as separate
        # facts; neither can replace it with a lower-fidelity tuple.  Keep the strongest
        # historical same-duration tuple in the expensive replay cohort so a winner
        # already observed earlier in this run cannot silently disappear.
        "historical_champions_per_length": 1,
        "confirm_candidates_per_length": 5,
        "pulse_family_champions_per_length": 3,
        "screen_shots": 220,
        "screen_reference_shots": 500,
        "screen_drift_retries": 2,
        "confirm_shots": 900,
        "confirm_blocks": 3,
        "require_control_audit": True,
        # The fidelity winner is still reported exactly as requested.  Separately,
        # screen a few held-out pulse-family alternatives and recommend a longer,
        # lower-drive candidate only when its paired fidelity loss is statistically
        # bounded.  This is a Pareto report, not leakage-based replacement of the
        # maximum-fidelity row.
        "balanced_row_enabled": False,
        "balanced_screen_candidates_per_length": 0,
        "balanced_max_fidelity_loss": 0.010,
        "balanced_confidence_sigma": 1.96,
        "balanced_control_attempts": 2,
    },
    "latency": {
        # Latency is a secondary, epsilon-constrained objective.  First establish
        # the best held-out fidelity; then minimize the physical X180+readout chain
        # only among candidates which independently prove that their fidelity loss
        # is at most one absolute percentage point.  A fidelity/time ratio is not
        # used because it rewards unusably short, low-fidelity measurements.
        "enabled": True,
        "max_fidelity_loss": 0.005,
        "minimum_mean_fidelity": 0.90,
        "minimum_lcb_fidelity": 0.88,
        # Reporting has a second, explicitly non-writing Pareto option.  It answers
        # "what is the fastest still-useful chain?" even when no faster arm can meet
        # the much stricter 0.5-point noninferiority certificate above.  Mean/LCB
        # floors exclude seductive 1-us/60%-fidelity points, while the five-point
        # loss cap keeps the option anchored to the measured device ceiling.
        "practical_max_mean_fidelity_loss": 0.05,
        "practical_minimum_mean_fidelity": 0.85,
        "practical_minimum_lcb_fidelity": 0.82,
        "familywise_alpha": 0.05,
        "confidence_sigma": 1.96,
        # A cheap joint cross of the already retuned representative at each readout
        # length and each Gaussian duration discovers interactions without reopening
        # the full six-dimensional frequency/gain/length Cartesian product.
        "coarse_shots": 160,
        "max_point_attempts": 2,
        "screening_sigma": 3.0,
        "screening_slack": 0.020,
        # Retained for saved-parameter compatibility.  The timing stage no longer
        # truncates a statistically plausible joint timing set to this top-K value;
        # doing so can hide the actual short plateau.
        "shortlist": 8,
        "confirm_shots": 1500,
        # Eight randomized round-robin blocks support paired noninferiority estimates;
        # three blocks are too fragile for a sub-percentage-point decision.
        "confirm_blocks": 8,
        "max_confirmation_attempts": 2,
        # If a promising faster tuple is unresolved rather than demonstrably worse,
        # collect another complete interleaved batch instead of declaring failure at
        # the first noisy boundary decision.  The same shortlist is replayed so every
        # comparison remains block-paired to one common reference.
        "adaptive_confirmation_rounds": 2,
        "adaptive_ucb_slack": 0.010,
        # A fast histogram can be an incoherent saturation/alias.  Audit qualified
        # latency contenders in increasing-time order and fall through to the next
        # one instead of letting the final control check merely abort the run.
        "control_screen_enabled": True,
        "max_block_spread": 0.08,
        "max_reference_drift": 0.04,
        # The independent final replay may not spend a second, larger fidelity
        # allowance after the timing comparison already spent epsilon.  A timing
        # certificate is invalidated when the exact replay falls by more than the
        # original noninferiority budget.
        "max_final_fidelity_drop": 0.010,
        # Preserve every default readout-length arm in the bounded joint cross.
        "max_readout_candidates": 20,
        "max_control_candidates": 6,
        "min_read_length_us": 1.0,
        "max_read_length_us": 20.0,
        # The primary/safety searches remain free to use slower controls.  The joint
        # latency stage spans the full existing Gaussian search envelope.
        "min_sigma_us": 0.05,
        "max_sigma_us": 1.00,
    },
    "coordinate_descent_repeat": True,
    "control_verify": {
        # The final single-shot histogram is not, by itself, proof of a coherent
        # X180: a saturated transition can also produce two well-separated clouds.
        # Audit the exact selected frequency/gain/sigma/DRAG tuple with alternating
        # odd/even repeated pulses before it can be written.
        "enabled": True, "pulse_counts": [1, 2, 3, 4, 5, 6],
        "shots": 320, "calibration_shots": 500, "blocks": 2,
        "minimum_binary_contrast": 0.30,
        "max_even_return_error_ucb": 0.25,
        "max_odd_inversion_error_ucb": 0.25,
        "familywise_alpha": 0.05, "confidence_sigma": 1.96,
    },
    "final": {
        "top_candidates": 3, "shots": 1200, "blocks": 3,
        "confidence_sigma": 1.96, "max_block_spread": 0.08,
        # A statistically stable coin-flip classifier is still not a calibration.
        # This gates writes only; the best measured tuple is always retained/reported.
        "minimum_write_fidelity_lcb": 0.60,
        # A saturation line plus a stable histogram does not prove coherent X180
        # control.  Write authorization requires a repeated-pulse/Rabi witness bound
        # to the exact selected frequency, gain, duration, and DRAG tuple.
        # Exact tuples whose confirmation batch was incomplete are audited regardless
        # of raw-score rank, so later coarse outliers cannot erase a real Rabi basin.
        "max_unconfirmed_contenders": 16,
    },
}


def configure_readout_length_mode(params, current_read_length_us,
                                   scan_1_to_20_us=True):
    """Return an isolated parameter tree for broad or fixed readout-length tuning.

    Four independent policies contain a readout-duration axis. Changing only the
    final portfolio would still let the joint search, legacy length refinement, or
    latency guard measure other durations. Keep those axes identical so fixed mode
    means exactly what it says: optimize every other candidate coordinate while every
    scored readout uses the value loaded from ``initialize.py``.
    """
    configured = copy.deepcopy(params)
    if bool(scan_1_to_20_us):
        lengths = [float(value) for value in range(1, 21)]
        mode = "1_to_20_us"
    else:
        try:
            current = float(current_read_length_us)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(
                "fixed readout-length mode needs a numeric initialize.py "
                "read_length")
        if not math.isfinite(current) or current <= 0.0:
            raise ValueError(
                "fixed readout-length mode needs a positive finite initialize.py "
                "read_length")
        lengths = [current]
        mode = "fixed_initialize_read_length"

    configured["joint_search"]["read_lengths_us"] = list(lengths)
    configured["duration_portfolio"]["read_lengths_us"] = list(lengths)
    configured["duration_portfolio"]["readout_length_mode"] = mode
    configured["duration_portfolio"][
        "configured_initialize_read_length_us"] = float(current_read_length_us)
    configured["readout_length"].update({
        "values_us": list(lengths),
        "min_us": float(min(lengths)),
        "max_us": float(max(lengths)),
    })
    configured["latency"]["max_read_length_us"] = float(max(lengths))
    return configured


def configure_gain_only_search(params, sigma_us):
    configured = copy.deepcopy(params)
    try:
        sigma = float(sigma_us)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("gain-only search needs a numeric initialize.py sigma")
    if not math.isfinite(sigma) or sigma <= 0.0:
        raise ValueError(
            "gain-only search needs a positive finite initialize.py sigma")
    configured["joint_search"]["sigma_values_us"] = [sigma]
    configured["pulse_duration"]["enabled"] = False
    configured["latency"]["min_sigma_us"] = sigma
    configured["latency"]["max_sigma_us"] = sigma
    configured["duration_portfolio"].update({
        "qubit_sigma_us": sigma,
        "search_axes": "read_pulse_gain_and_qubit_pi_gain",
        "constant_area_sigma_factors": [],
        "pulse_family_aae_enabled": False,
        "pulse_family_champions_per_length": 1,
        "balanced_screen_candidates_per_length": 0,
        "balanced_row_enabled": False,
    })
    return configured


TUNED_KEYS = (
    "read_pulse_freq", "read_pulse_gain", "read_length",
    "qubit_freq", "qubit_pi_freq", "qubit_pi_gain", "sigma",
    "qubit_drag_beta",
)


# Human-scale console milestones.  Internal calibration-graph nodes which merely
# re-probe a threshold or repeat a refinement stay in the saved report without
# flooding the terminal.
_CONCISE_STAGE_START = {
    "baseline": "Checking the starting calibration...",
    "resonator": "Finding the resonator...",
    "spectroscopy": "Finding the qubit transition...",
    "iq_rabi": "Finding a rough pi pulse...",
    "readout_grid": "Optimizing the initial readout...",
    "reset_after_bootstrap": "Setting up active reset...",
    "rough_ss": "Refining the pi pulse with single-shot measurements...",
    "parity_chevron": "Qualifying the qubit transition with repeated pulses...",
    "pre_expensive_gate": "Locking the resonator and qubit transition...",
    "joint_search": "Searching readout and pi-pulse power/length together...",
    "multi_aae": "Reducing amplified amplitude error across the best pulses...",
    "joint_closure_1": "Rechecking the coupled parameters after AAE...",
    "joint_closure_2": "Finishing the coupled parameter refinement...",
    "readout_after_control": "Refining readout frequency and power...",
    "readout_length": "Optimizing readout length...",
    "qubit_grid": "Optimizing qubit frequency and amplitude...",
    "pulse_duration": "Optimizing pi-pulse duration...",
    "latency": "Finding the shortest high-fidelity pulse and readout...",
    "readout_repeat": "Cross-checking the readout...",
    "qubit_repeat": "Cross-checking the pi pulse...",
    "amplified_error": "Reducing amplified amplitude error...",
    "final": "Comparing the best measured calibrations...",
    "duration_portfolio": (
        "Building the 1-20 us fidelity/leakage calibration table..."),
    "operational_leakage": "Screening pulse duration and power...",
    "operational_leakage_verify": "Verifying the pulse-safety checks...",
    "leakage": "Optimizing under the leakage constraint...",
    "qubit_post_leakage": "Rechecking the pi pulse after safety screening...",
    "readout_post_leakage": "Rechecking the readout after safety screening...",
    "leakage_verify": "Verifying leakage independently...",
    "final_safe": "Running the final screened validation...",
    "final_feedback": "Running the final active-reset validation...",
    "final_control_verify": "Verifying coherent action of the selected pi pulse...",
}


def _qubit_gain_sweep_supported(soccfg, gen_ch):
    """Whether ``sreg(ch, 'gain')`` is a real standalone amplitude register.

    Interpolated generators pack amplitude into another register.  Incrementing the
    nominal gain register can then compile while leaving the physical pulse amplitude
    fixed, so unknown/packed generators use slower point-by-point compiled pulses.
    """
    try:
        generator = soccfg["gens"][int(gen_ch)]
        gtype = str(generator.get("type", "")).lower()
    except Exception:
        return None
    if not gtype:
        return None
    return bool(gtype.startswith("axis_signal_gen_v"))


def _deep_merge(base, update):
    out = copy.deepcopy(base)
    for key, value in (update or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _robust_scale(x):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if not x.size:
        return np.nan
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


def _binomial_variance_jeffreys(k, n):
    """Posterior variance that remains finite after observing zero events."""
    n = max(int(n), 1)
    a, b = float(k) + 0.5, float(n - k) + 0.5
    return float(a * b / ((a + b) ** 2 * (a + b + 1.0)))


def _simultaneous_z(comparisons, alpha=0.05, floor=1.96):
    """Two-sided Bonferroni confidence multiplier for a screened family."""
    count = max(int(comparisons), 1)
    alpha = float(np.clip(alpha, 1e-9, 0.5))
    return float(max(float(floor), NormalDist().inv_cdf(
        1.0 - alpha / (2.0 * count))))


def _third_blob_diagnostics(c0, c1, theta, scale_factor, sigma_cut=4.0):
    """Find population far from both robust g/e blobs without calling it leakage.

    This catches a separated third cloud even when it lies on the ``excited`` side of
    the binary threshold and therefore leaves step-5 fidelity deceptively high.  The
    excess excited-preparation tail is the useful control diagnostic; common tails in
    both preparations are more likely readout/amplifier pathology.  This remains an
    operational anomaly metric, not P(f); strict mode can measure P(f) separately by
    shelving response inversion.
    """
    rotation = np.exp(-1j * float(theta))
    g = rotation * np.asarray(c0, dtype=complex)
    e = rotation * np.asarray(c1, dtype=complex)
    # Apply the discriminator sign only to x.  Euclidean distances are sign invariant,
    # but keeping the same orientation makes saved centres directly interpretable.
    xg, xe = float(scale_factor) * g.real, float(scale_factor) * e.real
    yg, ye = g.imag, e.imag
    cg = np.array([np.median(xg), np.median(yg)], dtype=float)
    ce = np.array([np.median(xe), np.median(ye)], dtype=float)
    separation = float(np.linalg.norm(ce - cg))

    def radius(x, y):
        # A small separation-relative floor prevents a mathematically zero orthogonal
        # MAD from classifying harmless ADC quantization as a third state.
        return max(0.5 * (_robust_scale(x) + _robust_scale(y)),
                   0.01 * separation, 1e-12)

    sg, se = radius(xg, yg), radius(xe, ye)

    def flags(x, y):
        points = np.column_stack([x, y])
        d2 = np.minimum(
            np.sum((points - cg) ** 2, axis=1) / (sg * sg),
            np.sum((points - ce) ** 2, axis=1) / (se * se),
        )
        return d2 > float(sigma_cut) ** 2

    fg, fe = flags(xg, yg), flags(xe, ye)
    kg, ke = int(np.count_nonzero(fg)), int(np.count_nonzero(fe))
    ng, ne = max(int(fg.size), 1), max(int(fe.size), 1)
    pg, pe = float(kg / ng), float(ke / ne)
    pg_se = math.sqrt(_binomial_variance_jeffreys(kg, ng))
    pe_se = math.sqrt(_binomial_variance_jeffreys(ke, ne))
    excess = max(0.0, pe - pg)
    excess_se = math.sqrt(pe_se ** 2 + pg_se ** 2)
    return {
        "outlier_frac": float((kg + ke) / (ng + ne)),
        "ground_outlier_frac": pg,
        "excited_outlier_frac": pe,
        "ground_outlier_ucb_95": float(min(pg + 1.96 * pg_se, 1.0)),
        "excited_outlier_ucb_95": float(min(pe + 1.96 * pe_se, 1.0)),
        "third_blob_excess": excess,
        "third_blob_excess_se": float(excess_se),
        "third_blob_excess_ucb_95": float(excess + 1.96 * excess_se),
        "outlier_sigma_cut": float(sigma_cut),
    }


def _third_cluster_diagnostics(c0, c1):
    """Detect a resolved third IQ population without assuming which state it is.

    The ordinary binary discriminator is intentionally blind to structure orthogonal
    to its threshold.  Here a full-covariance two-component GMM is compared with a
    three-component model using BIC.  The two components most associated with the
    ground- and excited-preparation records are treated as the intended binary pair;
    the remaining component is the non-binary population.  This catches the failure
    visible in an SS-cal plot even when that extra cloud occurs equally in both
    preparations and the old ``P_outlier(e)-P_outlier(g)`` statistic cancels to zero.
    """
    unavailable = {
        "third_cluster_guard_available": False,
        "third_cluster_supported": False,
        "third_cluster_detected": False,
        "third_cluster_fraction": np.nan,
        "third_cluster_fraction_ucb_95": np.nan,
        "third_cluster_ground_fraction": np.nan,
        "third_cluster_excited_fraction": np.nan,
        "third_cluster_single_state_fraction": np.nan,
        "third_cluster_single_state_fraction_ucb_95": np.nan,
        "third_cluster_bic_improvement": np.nan,
        "third_cluster_min_separation_sigma": np.nan,
        "third_cluster_binary_axis_projection": np.nan,
        "third_cluster_perpendicular_ratio": np.nan,
        "third_cluster_size_ratio": np.nan,
    }
    try:
        from sklearn.mixture import GaussianMixture
    except Exception:
        return unavailable
    ground = np.column_stack((np.real(c0), np.imag(c0))).astype(float)
    excited = np.column_stack((np.real(c1), np.imag(c1))).astype(float)
    if ground.shape[0] < 50 or excited.shape[0] < 50:
        return unavailable
    points = np.vstack((ground, excited))
    finite = np.all(np.isfinite(points), axis=1)
    if np.count_nonzero(finite) < 100:
        return unavailable
    # step5_metrics has already paired and finite-filtered c0/c1, so this is normally
    # all true.  Keep the split explicit to avoid silently mixing labels if a caller
    # invokes the helper directly.
    if not np.all(finite):
        return unavailable
    centre = np.median(points, axis=0)
    scale = np.asarray([
        max(_robust_scale(points[:, axis]), np.std(points[:, axis]) * 0.05, 1e-9)
        for axis in range(2)], dtype=float)
    normalized = (points - centre) / scale
    try:
        models = []
        for components in (2, 3):
            model = GaussianMixture(
                n_components=components, covariance_type="full",
                reg_covar=1e-3, n_init=4, max_iter=300, tol=1e-4,
                random_state=1729,
            ).fit(normalized)
            if not bool(model.converged_):
                return unavailable
            models.append(model)
        two, three = models
        bic_improvement = float(two.bic(normalized) - three.bic(normalized))
        responsibility = np.asarray(three.predict_proba(normalized), dtype=float)
        n_ground = ground.shape[0]
        n_excited = excited.shape[0]
        ground_mass = np.mean(responsibility[:n_ground], axis=0)
        excited_mass = np.mean(responsibility[n_ground:], axis=0)
        pairs = [(g_index, e_index)
                 for g_index in range(3) for e_index in range(3)
                 if g_index != e_index]
        canonical_ground, canonical_excited = max(
            pairs, key=lambda pair: (
                float(ground_mass[pair[0]] + excited_mass[pair[1]]),
                float(ground_mass[pair[0]]), float(excited_mass[pair[1]])))
        anomalous = next(index for index in range(3)
                         if index not in (canonical_ground, canonical_excited))
        third_ground = float(ground_mass[anomalous])
        third_excited = float(excited_mass[anomalous])
        third_total = float(
            (n_ground * third_ground + n_excited * third_excited)
            / max(n_ground + n_excited, 1))
        third_total_se = math.sqrt(_binomial_variance_jeffreys(
            int(round(third_total * (n_ground + n_excited))),
            n_ground + n_excited))
        third_ground_se = math.sqrt(_binomial_variance_jeffreys(
            int(round(third_ground * n_ground)), n_ground))
        third_excited_se = math.sqrt(_binomial_variance_jeffreys(
            int(round(third_excited * n_excited)), n_excited))
        third_total_ucb = float(min(
            third_total + 1.96 * third_total_se, 1.0))
        third_single_state_ucb = float(max(
            min(third_ground + 1.96 * third_ground_se, 1.0),
            min(third_excited + 1.96 * third_excited_se, 1.0)))
        separations = []
        for canonical in (canonical_ground, canonical_excited):
            delta = three.means_[anomalous] - three.means_[canonical]
            covariance = 0.5 * (
                three.covariances_[anomalous] + three.covariances_[canonical])
            distance2 = float(delta @ np.linalg.pinv(covariance) @ delta)
            separations.append(math.sqrt(max(distance2, 0.0)))
        minimum_separation = float(min(separations))
        transform = np.diag(scale)
        means_raw = three.means_ * scale[None, :] + centre[None, :]
        covariances_raw = np.asarray([
            transform @ covariance @ transform
            for covariance in three.covariances_])
        binary_axis = (means_raw[canonical_excited]
                       - means_raw[canonical_ground])
        axis_norm2 = float(binary_axis @ binary_axis)
        offset = means_raw[anomalous] - means_raw[canonical_ground]
        projection = float(offset @ binary_axis / max(axis_norm2, 1e-18))
        perpendicular = offset - projection * binary_axis
        perpendicular_ratio = float(
            np.linalg.norm(perpendicular)
            / max(math.sqrt(axis_norm2), 1e-9))
        anomalous_size = float(np.trace(covariances_raw[anomalous]))
        canonical_size = float(max(
            np.trace(covariances_raw[canonical_ground]),
            np.trace(covariances_raw[canonical_excited]), 1e-18))
        size_ratio = float(anomalous_size / canonical_size)
    except Exception:
        return unavailable
    topology_distinct = bool(
        projection < -0.15 or projection > 1.15
        or perpendicular_ratio >= 0.20
        # A compact population between the two intended states is also physical,
        # but a compact component close to either endpoint is usually just a GMM
        # splitting one skewed/non-Gaussian binary cloud.  Requiring an interior
        # location prevents that ordinary model mismatch from being called leakage.
        or (size_ratio <= 2.0 and 0.20 <= projection <= 0.80))
    supported = bool(
        np.all(np.isfinite([
            bic_improvement, minimum_separation, third_total,
            third_ground, third_excited, projection,
            perpendicular_ratio, size_ratio]))
        and bic_improvement >= 20.0 and minimum_separation >= 3.5
        and topology_distinct)
    return {
        "third_cluster_guard_available": True,
        "third_cluster_supported": supported,
        "third_cluster_detected": supported,
        "third_cluster_fraction": third_total,
        "third_cluster_fraction_ucb_95": third_total_ucb,
        "third_cluster_ground_fraction": third_ground,
        "third_cluster_excited_fraction": third_excited,
        "third_cluster_single_state_fraction": float(
            max(third_ground, third_excited)),
        "third_cluster_single_state_fraction_ucb_95": (
            third_single_state_ucb),
        "third_cluster_bic_improvement": bic_improvement,
        "third_cluster_min_separation_sigma": minimum_separation,
        "third_cluster_binary_axis_projection": projection,
        "third_cluster_perpendicular_ratio": perpendicular_ratio,
        "third_cluster_size_ratio": size_ratio,
    }


def ground_fraction_with_discriminator(i, q, metrics):
    """Ground-labelled fraction and Jeffreys uncertainty for a fixed g/e axis."""
    labels = discriminate_with_metrics(i, q, metrics)
    n = int(labels.size)
    if n < 10:
        return np.nan, np.inf
    k = int(np.count_nonzero(labels == 0))
    return float(k / n), float(math.sqrt(_binomial_variance_jeffreys(k, n)))


def solve_shelved_qutrit_population(calibration, target_identity, target_shelved,
                                    max_condition=40.0):
    """Estimate P(g/e/f) from calibrated identity and f-selective shelving.

    Each calibration column is ``(p_g identity, se, p_g shelved, se)``.  The
    shelving sequence e-f pi followed by g-e pi maps f to g while mapping g/e away
    from g.  Together with ordinary binary readout and normalization this gives a
    measured 3x3 response matrix.  Ill-conditioned and nonphysical inversions fail
    closed instead of fabricating a small leakage value.
    """
    try:
        columns = [calibration[name] for name in ("g", "e", "f")]
        matrix = np.array([
            [float(column[0]) for column in columns],
            [float(column[2]) for column in columns],
            [1.0, 1.0, 1.0],
        ], dtype=float)
        matrix_se = np.array([
            [float(column[1]) for column in columns],
            [float(column[3]) for column in columns],
            [0.0, 0.0, 0.0],
        ], dtype=float)
        observed = np.array([
            float(target_identity[0]), float(target_shelved[0]), 1.0],
            dtype=float)
        observed_se = np.array([
            float(target_identity[1]), float(target_shelved[1]), 0.0],
            dtype=float)
        condition = float(np.linalg.cond(matrix))
        inverse = np.linalg.inv(matrix)
        raw = inverse @ observed
    except Exception:
        return {"ok": False, "population": np.full(3, np.nan),
                "population_se": np.full(3, np.inf), "condition": np.inf,
                "p2": np.nan, "p2_se": np.inf}
    covariance = inverse @ np.diag(observed_se ** 2) @ inverse.T
    # d(A^-1 b)/dA_rc = -A^-1[:, r] p[c].
    for row in range(2):
        for column in range(3):
            gradient = -inverse[:, row] * raw[column]
            covariance += np.outer(gradient, gradient) * matrix_se[row, column] ** 2
    population_se = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    physical = np.clip(raw, 0.0, None)
    if float(np.sum(physical)) > 0:
        physical /= float(np.sum(physical))
    matrix_ok = bool(np.isfinite(condition) and condition <= float(max_condition))
    physical_ok = bool(
        np.all(raw >= -3.0 * population_se)
        and np.all(raw <= 1.0 + 3.0 * population_se))
    return {
        "ok": bool(matrix_ok and physical_ok
                   and np.all(np.isfinite(population_se))),
        "population": physical, "population_raw": raw,
        "population_se": population_se,
        "p2": float(physical[2]), "p2_raw": float(raw[2]),
        "p2_se": float(population_se[2]), "condition": condition,
        "response_matrix": matrix, "response_matrix_se": matrix_se,
        "matrix_ok": matrix_ok, "physical_ok": physical_ok,
    }


def _candidate_key(candidate):
    return (
        round(float(candidate["read_pulse_freq"]), 9),
        int(round(candidate["read_pulse_gain"])),
        round(float(candidate["read_length"]), 9),
        round(float(candidate["qubit_pi_freq"]), 9),
        int(round(candidate["qubit_pi_gain"])),
        round(float(candidate["sigma"]), 9),
        round(float(candidate.get("qubit_drag_beta", 0.0)), 9),
    )


def _control_key(candidate):
    """Hardware-relevant identity of one physical X180 waveform."""
    return (
        round(float(candidate["qubit_pi_freq"]), 9),
        int(round(candidate["qubit_pi_gain"])),
        round(float(candidate["sigma"]), 9),
        round(float(candidate.get("qubit_drag_beta", 0.0)), 9),
    )


def _candidate_from_cfg(cfg):
    # Do not use ``dict.get(key, cfg[other])`` here: Python evaluates the default
    # expression eagerly, so a perfectly valid config containing only
    # ``qubit_pi_freq`` would still raise KeyError while constructing its fallback.
    qf = float(cfg["qubit_pi_freq"] if "qubit_pi_freq" in cfg
               else cfg["qubit_freq"])
    return {
        "read_pulse_freq": float(cfg["read_pulse_freq"]),
        "read_pulse_gain": int(round(cfg["read_pulse_gain"])),
        "read_length": float(cfg["read_length"]),
        "qubit_freq": qf,
        "qubit_pi_freq": qf,
        "qubit_pi_gain": int(round(cfg["qubit_pi_gain"])),
        "sigma": float(cfg["sigma"]),
        # Starts as part of physical identity; the direct leakage stage may optimize it.
        "qubit_drag_beta": float(cfg.get("qubit_drag_beta", 0.0) or 0.0),
    }


def _with_candidate(candidate, **changes):
    out = dict(candidate)
    out.update(changes)
    if "qubit_pi_freq" in changes and "qubit_freq" not in changes:
        out["qubit_freq"] = float(changes["qubit_pi_freq"])
    if "qubit_freq" in changes and "qubit_pi_freq" not in changes:
        out["qubit_pi_freq"] = float(changes["qubit_freq"])
    out["read_pulse_gain"] = int(round(out["read_pulse_gain"]))
    out["qubit_pi_gain"] = int(round(out["qubit_pi_gain"]))
    return out


def _unique_candidates(candidates):
    out, seen = [], set()
    for candidate in candidates:
        key = _candidate_key(candidate)
        if key not in seen:
            seen.add(key)
            out.append(dict(candidate))
    return out


def duration_balanced_joint_jobs(read_lengths, sigmas, read_gains, rng):
    """Return a gain-pass-major joint-grid schedule.

    Every prefix ending at a complete read-gain pass contains every physical
    read-length/sigma stratum exactly once.  This property makes a partial,
    runtime-limited acquisition interpretable: a short readout cannot win simply
    because random job order never reached the longer integrations.

    Readout powers are visited in a space-filling order (centre, quartiles, bounds,
    then farthest unsampled value) so the first few complete passes are useful even
    when passive reset prevents acquisition of the full power lattice.
    """
    lengths = np.asarray(read_lengths, dtype=float)
    pulse_sigmas = np.asarray(sigmas, dtype=float)
    gains = np.asarray(sorted(set(int(round(value)) for value in read_gains)),
                       dtype=int)
    if not lengths.size or not pulse_sigmas.size or not gains.size:
        return []

    chosen = []
    unused = set(range(gains.size))
    span = max(float(gains[-1] - gains[0]), 1.0)
    # Resolve the central operating regime before testing the compression/no-signal
    # bounds.  Ties deliberately select the lower DAC value.
    for fraction in (0.50, 0.25, 0.75, 0.0, 1.0):
        if not unused:
            break
        target = float(gains[0]) + fraction * span
        index = min(unused, key=lambda raw: (
            abs(float(gains[raw]) - target), int(gains[raw])))
        chosen.append(index)
        unused.remove(index)
    while unused:
        # Maximin completion distributes later passes between already sampled powers
        # instead of walking monotonically through DAC gain.
        index = max(unused, key=lambda raw: (
            min(abs(float(gains[raw]) - float(gains[prior]))
                for prior in chosen),
            -int(gains[raw])))
        chosen.append(index)
        unused.remove(index)

    strata = [(float(length), float(sigma))
              for length in lengths for sigma in pulse_sigmas]
    jobs = []
    for pass_index, gain_index in enumerate(chosen):
        order = np.asarray(rng.permutation(len(strata)), dtype=int)
        for raw in order:
            read_length, sigma = strata[int(raw)]
            jobs.append((read_length, sigma, int(gains[gain_index]),
                         int(pass_index)))
    return jobs


def step5_metrics(ig, qg, ie, qe, analyze_multimodality=False):
    """Reproduce TLS step-5 fidelity and return its operational discriminator.

    This intentionally uses ``find_blob_median`` and the same 100-threshold
    ``find_threshold`` sweep as :class:`SingleShot1Q`.  Consequently a manual step-5
    result such as 0.9165 is reported on the same scale here (balanced assignment
    fidelity), rather than the older visibility convention ``2*F-1``.
    """
    ig, qg = np.asarray(ig, dtype=float), np.asarray(qg, dtype=float)
    ie, qe = np.asarray(ie, dtype=float), np.asarray(qe, dtype=float)
    n = min(ig.size, qg.size, ie.size, qe.size)
    if n < 20:
        raise ValueError("at least 20 paired ground/excited shots are required")
    ig, qg, ie, qe = ig[:n], qg[:n], ie[:n], qe[:n]
    good = np.isfinite(ig) & np.isfinite(qg) & np.isfinite(ie) & np.isfinite(qe)
    ig, qg, ie, qe = ig[good], qg[good], ie[good], qe[good]
    n = ig.size
    if n < 20:
        raise ValueError("too few finite paired ground/excited shots")

    c0, c1 = ig + 1j * qg, ie + 1j * qe
    center_g = complex(find_blob_median(c0))
    center_e = complex(find_blob_median(c1))
    theta = float(np.angle(center_e - center_g))
    xg = np.real(np.exp(-1j * theta) * c0)
    xe = np.real(np.exp(-1j * theta) * c1)
    thresholds, fidelities = find_threshold(xg.astype(complex), xe.astype(complex))
    k = int(np.nanargmax(fidelities))
    threshold = float(thresholds[k])
    fidelity = float(fidelities[k])

    factor = 1.0
    if float(np.mean(xg)) > threshold:
        factor = -1.0
        xg, xe, threshold = -xg, -xe, -threshold
    p_e_given_g = float(np.mean(xg > threshold))
    p_g_given_e = float(np.mean(xe < threshold))
    confusion = np.array([
        [1.0 - p_e_given_g, p_g_given_e],
        [p_e_given_g, 1.0 - p_g_given_e],
    ])
    # The manual TLS step-5 number above deliberately fits and scores the IQ axis and
    # threshold on the same shots so it remains directly comparable with the lab's
    # historical calibration output.  That resubstitution estimate is slightly
    # optimistic, however, and candidate-dependent optimism is unacceptable when a
    # sub-percentage-point latency decision is being certified.  Build an additional
    # deterministic two-fold cross-fit estimate: each discriminator is trained on one
    # interleaved half and scored only on shots it did not see.  Timing selection uses
    # this held-out metric while the ordinary ``fidelity`` field remains step-5 exact.
    crossfit_ground_errors = 0
    crossfit_excited_errors = 0
    crossfit_ground_total = 0
    crossfit_excited_total = 0
    crossfit_fold_fidelities = []
    indices = np.arange(n, dtype=int)
    for heldout_parity in (0, 1):
        heldout = (indices % 2) == heldout_parity
        training = ~heldout
        train_g, train_e = c0[training], c1[training]
        test_g, test_e = c0[heldout], c1[heldout]
        fold_center_g = complex(find_blob_median(train_g))
        fold_center_e = complex(find_blob_median(train_e))
        fold_theta = float(np.angle(fold_center_e - fold_center_g))
        fold_ground = np.real(np.exp(-1j * fold_theta) * train_g)
        fold_excited = np.real(np.exp(-1j * fold_theta) * train_e)
        fold_thresholds, fold_fidelities = find_threshold(
            fold_ground.astype(complex), fold_excited.astype(complex))
        fold_threshold = float(
            fold_thresholds[int(np.nanargmax(fold_fidelities))])
        fold_factor = (-1.0 if float(np.mean(fold_ground)) > fold_threshold
                       else 1.0)
        fixed = {
            "read_theta": fold_theta,
            "scale_factor": fold_factor,
            "threshold": fold_factor * fold_threshold,
        }
        predicted_ground = discriminate_with_metrics(
            test_g.real, test_g.imag, fixed)
        predicted_excited = discriminate_with_metrics(
            test_e.real, test_e.imag, fixed)
        ground_errors = int(np.count_nonzero(predicted_ground > 0))
        excited_errors = int(np.count_nonzero(predicted_excited < 1))
        ground_total = int(predicted_ground.size)
        excited_total = int(predicted_excited.size)
        crossfit_ground_errors += ground_errors
        crossfit_excited_errors += excited_errors
        crossfit_ground_total += ground_total
        crossfit_excited_total += excited_total
        crossfit_fold_fidelities.append(float(
            1.0 - 0.5 * (
                ground_errors / max(ground_total, 1)
                + excited_errors / max(excited_total, 1))))
    crossfit_p_e_given_g = float(
        crossfit_ground_errors / max(crossfit_ground_total, 1))
    crossfit_p_g_given_e = float(
        crossfit_excited_errors / max(crossfit_excited_total, 1))
    crossfit_fidelity = float(
        1.0 - 0.5 * (crossfit_p_e_given_g + crossfit_p_g_given_e))
    crossfit_variance = float(0.25 * (
        _binomial_variance_jeffreys(
            crossfit_ground_errors, crossfit_ground_total)
        + _binomial_variance_jeffreys(
            crossfit_excited_errors, crossfit_excited_total)))
    crossfit_fidelity_se = float(math.sqrt(max(crossfit_variance, 0.0)))
    crossfit_confusion = np.array([
        [1.0 - crossfit_p_e_given_g, crossfit_p_g_given_e],
        [crossfit_p_e_given_g, 1.0 - crossfit_p_g_given_e],
    ])
    # The exact helper's finite threshold grid defines fidelity.  The confusion matrix
    # is retained for directional errors and uncertainty and should agree to O(1/n).
    var = (p_e_given_g * (1.0 - p_e_given_g)
           + p_g_given_e * (1.0 - p_g_given_e)) / (4.0 * n)
    # Jeffreys-scale floor avoids claiming zero uncertainty after observing zero errors.
    fidelity_se = float(math.sqrt(max(var, 0.25 / (n + 1.0) ** 2)))
    sg = max(_robust_scale(xg), 1e-12)
    se = max(_robust_scale(xe), 1e-12)
    sep_sigma = float(abs(np.median(xe) - np.median(xg)) / (0.5 * (sg + se)))
    anomaly = _third_blob_diagnostics(c0, c1, theta, factor)
    cluster = (_third_cluster_diagnostics(c0, c1)
               if bool(analyze_multimodality) else {
                   "third_cluster_guard_available": False,
                   "third_cluster_supported": False,
                   "third_cluster_detected": False,
                   "third_cluster_fraction": np.nan,
                   "third_cluster_fraction_ucb_95": np.nan,
                   "third_cluster_ground_fraction": np.nan,
                   "third_cluster_excited_fraction": np.nan,
                   "third_cluster_single_state_fraction": np.nan,
                   "third_cluster_single_state_fraction_ucb_95": np.nan,
                   "third_cluster_bic_improvement": np.nan,
                   "third_cluster_min_separation_sigma": np.nan,
                   "third_cluster_binary_axis_projection": np.nan,
                   "third_cluster_perpendicular_ratio": np.nan,
                   "third_cluster_size_ratio": np.nan,
               })
    return {
        "fidelity": fidelity,
        "fidelity_se": fidelity_se,
        "fidelity_lcb_95": float(fidelity - 1.96 * fidelity_se),
        "crossfit_fidelity": crossfit_fidelity,
        "crossfit_fidelity_se": crossfit_fidelity_se,
        "crossfit_fidelity_lcb_95": float(
            crossfit_fidelity - 1.96 * crossfit_fidelity_se),
        "crossfit_p_e_given_g": crossfit_p_e_given_g,
        "crossfit_p_g_given_e": crossfit_p_g_given_e,
        "crossfit_confusion": crossfit_confusion,
        "crossfit_fold_fidelities": np.asarray(
            crossfit_fold_fidelities, dtype=float),
        "threshold_selection_optimism": float(
            fidelity - crossfit_fidelity),
        "visibility": float(2.0 * fidelity - 1.0),
        "p_e_given_g": p_e_given_g,
        "p_g_given_e": p_g_given_e,
        "confusion": confusion,
        "read_theta": theta,
        "scale_factor": factor,
        "threshold": threshold,
        "sep_sigma": sep_sigma,
        "shots_per_state": int(n),
        "ground_center_i": float(center_g.real),
        "ground_center_q": float(center_g.imag),
        "excited_center_i": float(center_e.real),
        "excited_center_q": float(center_e.imag),
        "projected_ground_center": float(
            factor * np.real(np.exp(-1j * theta) * center_g)),
        "projected_excited_center": float(
            factor * np.real(np.exp(-1j * theta) * center_e)),
        **anomaly,
        **cluster,
    }


def discriminate_with_metrics(i, q, metrics):
    c = np.asarray(i, dtype=float) + 1j * np.asarray(q, dtype=float)
    x = float(metrics["scale_factor"]) * np.real(
        np.exp(-1j * float(metrics["read_theta"])) * c)
    return (x > float(metrics["threshold"])).astype(np.int8)


def fit_anchored_rabi(gains, signal):
    """Fit a damped Rabi cosine whose phase is anchored by the zero-gain point."""
    x, y = np.asarray(gains, dtype=float), np.asarray(signal, dtype=float)
    good = np.isfinite(x) & np.isfinite(y)
    x, y = x[good], y[good]
    if x.size < 9 or np.ptp(x) <= 0:
        return {"ok": False, "pi_gain": np.nan, "r2": -np.inf,
                "contrast": 0.0, "yfit": np.full_like(y, np.nan)}
    order = np.argsort(x)
    x, y = x[order], y[order]
    x = x - x[0]
    span = float(np.ptp(x))
    step = float(np.median(np.diff(np.unique(x))))

    def model(g, offset, amp, pi_gain, decay):
        return offset + amp * np.exp(-g / decay) * np.cos(np.pi * g / pi_gain)

    # FFT plus geometric seeds make the first physical period identifiable even when
    # the high-gain oscillations are strongly damped.
    centred = y - np.mean(y)
    fft = np.fft.rfft(centred * np.hanning(x.size))
    ff = np.fft.rfftfreq(x.size, d=max(step, 1e-9))
    if ff.size > 1:
        fft_pi = 0.5 / max(float(ff[1 + np.argmax(np.abs(fft[1:]))]), 1e-12)
    else:
        fft_pi = span / 3.0
    seeds = [fft_pi, span / 8.0, span / 6.0, span / 4.0,
             span / 3.0, span / 2.0, 0.75 * span]
    best = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", OptimizeWarning)
        for p0 in seeds:
            if not np.isfinite(p0):
                continue
            try:
                popt, pcov = curve_fit(
                    model, x, y,
                    p0=[float(np.mean(y)), float(y[0] - np.mean(y)),
                        float(np.clip(p0, 0.6 * step, span)), 3.0 * span],
                    # pi_gain below one gain step is a discrete-time alias of a much
                    # slower Rabi oscillation, not a resolvable first inversion.
                    bounds=([-np.inf, -np.inf, 1.05 * step, 0.20 * span],
                            [np.inf, np.inf, 1.25 * span, 1e5 * span]),
                    maxfev=30000,
                )
                yf = model(x, *popt)
                sse = float(np.sum((y - yf) ** 2))
                if best is None or sse < best[0]:
                    best = (sse, popt, pcov, yf)
            except Exception:
                pass
    if best is None:
        return {"ok": False, "pi_gain": np.nan, "r2": -np.inf,
                "contrast": float(np.ptp(y)), "yfit": np.full_like(y, np.nan)}
    sse, popt, pcov, yf = best
    total = float(np.sum((y - np.mean(y)) ** 2)) + 1e-15
    r2 = float(1.0 - sse / total)
    offset, amp, pi_gain, decay = [float(v) for v in popt]
    try:
        pi_err = float(math.sqrt(max(float(pcov[2, 2]), 0.0)))
    except Exception:
        pi_err = np.inf
    ok = bool(np.isfinite(pi_gain) and 1.05 * step <= pi_gain <= span
              and r2 > 0.45 and abs(amp) > 0)
    return {
        "ok": ok, "pi_gain": pi_gain, "pi_gain_err": pi_err,
        "period": 2.0 * pi_gain, "r2": r2,
        "contrast": float(2.0 * abs(amp)), "decay_gain": decay,
        "offset": offset, "amplitude": amp, "x": x, "y": y, "yfit": yf,
    }


def analyze_iq_chevron(freqs, gains, i_map, q_map, min_r2=0.55):
    """Find a coherent Rabi ridge after removing each row's common IQ offset.

    This is the key correction to the existing TLS/QM chevrons: absolute ``I**2+Q**2``
    is dominated by the readout baseline and has no reason to identify a pi pulse.
    """
    freqs, gains = np.asarray(freqs, float), np.asarray(gains, float)
    z = np.asarray(i_map, float) + 1j * np.asarray(q_map, float)
    if z.shape != (freqs.size, gains.size):
        raise ValueError("IQ chevron shape does not match its axes")
    rows = []
    for row, freq in zip(z, freqs):
        d = row - row[0]
        xy = np.column_stack([d.real, d.imag])
        xy -= np.nanmean(xy, axis=0)
        try:
            _, _, vh = np.linalg.svd(np.nan_to_num(xy), full_matrices=False)
            axis = vh[0]
        except Exception:
            axis = np.array([1.0, 0.0])
        projection = d.real * axis[0] + d.imag * axis[1]
        fit = fit_anchored_rabi(gains, projection)
        residual = projection - np.asarray(fit.get("yfit", projection))
        noise = max(_robust_scale(residual), 1e-12)
        snr = float(np.ptp(projection) / noise)
        score = float(max(fit.get("r2", -1.0), -1.0) * math.log1p(max(snr, 0.0)))
        rows.append({"frequency": float(freq), "projection": projection,
                     "fit": fit, "snr": snr, "raw_score": score,
                     "contrast_observed": float(np.ptp(projection))})
    max_contrast = max(max(row["contrast_observed"] for row in rows), 1e-15)
    for row in rows:
        # A vanishing but perfectly sinusoidal numerical/noise trace can have an
        # excellent scale-free r2.  The physical ridge must also carry a substantial
        # fraction of the largest drive-induced displacement in the map.
        relative = float(row["contrast_observed"] / max_contrast)
        row["relative_contrast"] = relative
        row["score"] = float(row["raw_score"] * relative)
    valid = [row for row in rows
             if row["fit"].get("ok") and row["fit"].get("r2", -1) >= min_r2]
    pool = valid if valid else rows
    best = max(pool, key=lambda row: row["score"])
    return {"ok": bool(valid), "best": best, "rows": rows}


def _declare_common(program, include_qubit=True):
    cfg = program.cfg
    program.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                        mixer_freq=cfg.get("mixer_freq", 0),
                        ro_ch=cfg["ro_chs"][0])
    if include_qubit:
        program.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
    # ``ff_park_gain`` is an environmental operating point, never an optimization
    # coordinate.  Declare its generator even when the configured value is zero so
    # every uploaded program can clear a stale nonzero latched FF output.
    ff_pulse.declare_static_park(program)
    for ro_ch in cfg["ro_chs"]:
        program.declare_readout(
            ch=ro_ch, freq=cfg["read_pulse_freq"],
            length=program.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
            gen_ch=cfg["res_ch"],
        )
    set_readout_pulse(program)


def _replay_static_flux(program):
    """Hold the input configuration's FF park value for this complete repetition."""
    ff_pulse.play_static_park(
        program, settle_us=program.cfg.get("ff_park_settle_us", 0.05))


class BasicTransmissionProgram(AveragerProgram):
    """Static-operating-point readout using the canonical step-5 pulse."""

    def initialize(self):
        self.cfg.setdefault("reps", int(self.cfg.get("shots", 300)))
        _declare_common(self, include_qubit=False)
        self.synci(200)

    def body(self):
        cfg = self.cfg
        _replay_static_flux(self)
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))


class BasicSpecProgram(RAveragerProgram):
    """Hardware frequency sweep of a constant saturation-spectroscopy pulse."""

    def initialize(self):
        cfg = self.cfg
        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")
        _declare_common(self, include_qubit=True)
        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])
        # Encode the magnitude and select +/- explicitly.  Passing a negative MHz
        # value through freq2reg may produce a wrapped unsigned word too large for a
        # tProc immediate; subtraction keeps reversed confirmation sweeps portable.
        self.f_step = self.freq2reg(
            abs(float(cfg["step"])), gen_ch=cfg["qubit_ch"])
        self.f_step_operation = "+" if float(cfg["step"]) >= 0 else "-"
        self.set_pulse_registers(
            ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0,
            gain=int(cfg["spec_gain"]),
            length=self.us2cycles(cfg["spec_len_us"], gen_ch=cfg["qubit_ch"]),
        )
        self.synci(200)

    def body(self):
        cfg = self.cfg
        _replay_static_flux(self)
        self.pulse(ch=cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.02))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))

    def update(self):
        self.mathi(
            self.q_rp, self.r_freq, self.r_freq,
            self.f_step_operation, self.f_step)


class BasicRabiProgram(RAveragerProgram):
    """Hardware gain sweep of the canonical 4-sigma Gaussian pulse."""

    def initialize(self):
        cfg = self.cfg
        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")
        _declare_common(self, include_qubit=True)
        add_qubit_gaussian(self)
        if str(cfg.get("reset_mode", "passive")).strip().lower() == "feedback":
            add_qubit_gaussian(
                self, name="qubit_reset",
                sigma_us=float(cfg.get("reset_pi_sigma", cfg["sigma"])),
                drag_beta=float(cfg.get(
                    "reset_pi_drag_beta", cfg.get("qubit_drag_beta", 0.0))))
        self.set_pulse_registers(
            ch=cfg["qubit_ch"], style="arb",
            freq=self.freq2reg(float(cfg["drive_freq"]), gen_ch=cfg["qubit_ch"]),
            phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]),
            gain=int(cfg["start"]), waveform="qubit",
        )
        self.synci(200)

    def body(self):
        cfg = self.cfg
        _replay_static_flux(self)
        self.pulse(ch=cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.01))
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, "+", int(self.cfg["step"]))


class BasicSequenceProgram(AveragerProgram):
    """Generic canonical Gaussian sequence followed by one per-shot readout.

    Legacy callers supply ``sequence_phases_deg`` and one gain/frequency.  Leakage
    calibration supplies ``sequence_ops`` containing ``('pulse', gain, phase)`` for
    the candidate g-e DRAG waveform and ``('pulse_at', gain, phase, frequency,
    'reference')`` for independently calibrated long g-e/e-f reference pulses.
    """

    def initialize(self):
        cfg = self.cfg
        cfg["reps"] = int(cfg.get("shots", cfg.get("reps", 200)))
        _declare_common(self, include_qubit=True)
        add_qubit_gaussian(self)
        if str(cfg.get("reset_mode", "passive")).strip().lower() == "feedback":
            # The reset pulse is deliberately frozen to the independently validated
            # control tuple while the candidate waveform is varied.  Declare both
            # waveforms: referencing an undeclared ``qubit_reset`` happens to escape
            # the virtual backend but fails during a real QICK program upload.
            add_qubit_gaussian(
                self, name="qubit_reset",
                sigma_us=float(cfg.get("reset_pi_sigma", cfg["sigma"])),
                drag_beta=float(cfg.get(
                    "reset_pi_drag_beta", cfg.get("qubit_drag_beta", 0.0))))
        if any(op[0] == "pulse_at" and len(op) > 4
               and str(op[4]) == "gaussian"
               for op in cfg.get("sequence_ops", [])):
            # Shelving uses the same duration/clock but no DRAG quadrature; its gain is
            # calibrated independently for every candidate duration.
            add_qubit_gaussian(self, name="qubit_ef", drag_beta=0.0)
        if any(op[0] == "pulse_at" and len(op) > 4
               and str(op[4]) == "reference"
               for op in cfg.get("sequence_ops", [])):
            add_qubit_gaussian(
                self, name="qubit_ref",
                sigma_us=float(cfg["leakage_reference_sigma_us"]),
                drag_beta=0.0)
        self.synci(200)

    def body(self):
        cfg = self.cfg
        _replay_static_flux(self)
        qch = cfg["qubit_ch"]
        feedback = str(cfg.get("reset_mode", "passive")).strip().lower() == "feedback"
        if feedback:
            reset_read_freq = float(cfg.get(
                "reset_read_pulse_freq", cfg["read_pulse_freq"]))
            if not np.isclose(
                    reset_read_freq, float(cfg["read_pulse_freq"]),
                    rtol=0.0, atol=1e-9):
                raise ValueError(
                    "feedback reset profile does not match this sequence "
                    "program's ADC/DDC frequency")
            set_readout_pulse(
                self, gain=int(cfg.get(
                    "reset_read_pulse_gain", cfg["read_pulse_gain"])))
            # This program may later switch among candidate g-e and reference e-f
            # waveforms.  Install the candidate X180 explicitly for reset first; every
            # sequence operation below then installs its own complete pulse registers.
            self.set_pulse_registers(
                ch=qch, style="arb",
                freq=self.freq2reg(float(cfg.get(
                    "reset_pi_freq", cfg["drive_freq"])), gen_ch=qch),
                phase=self.deg2reg(0, gen_ch=qch),
                gain=int(cfg.get("reset_pi_gain", cfg["qubit_pi_gain"])),
                waveform="qubit_reset")
            active_reset.active_reset_block(
                self, ro_ch=cfg["ro_chs"][0],
                threshold_raw=cfg["reset_threshold_raw"],
                oper=cfg.get("reset_oper", "lower"),
                ground_below=cfg.get("reset_ground_below", True),
                max_iters=int(cfg.get("reset_max_iters", 3)),
                reg_val=25, reg_thr=26)
            set_readout_pulse(self)
        gap = self.us2cycles(float(cfg.get("seq_gap_us", 0.01)))
        if "sequence_ops" in cfg:
            operations = list(cfg["sequence_ops"])
        else:
            operations = [
                ("pulse", int(cfg["sequence_gain"]), float(phase))
                for phase in cfg["sequence_phases_deg"]
            ]
        last_registers = None
        for operation in operations:
            if operation[0] == "pulse":
                gain, phase = int(operation[1]), float(operation[2])
                frequency = float(cfg["drive_freq"])
                waveform = "qubit"
            elif operation[0] == "pulse_at":
                gain, phase = int(operation[1]), float(operation[2])
                frequency = float(operation[3])
                family = str(operation[4]) if len(operation) > 4 else "qubit"
                if family not in ("qubit", "gaussian", "reference"):
                    raise ValueError("unknown pulse_at waveform %r" % family)
                waveform = ({"gaussian": "qubit_ef", "reference": "qubit_ref"}
                            .get(family, "qubit"))
            elif operation[0] == "delay":
                self.sync_all(self.us2cycles(float(operation[1])))
                continue
            else:
                raise ValueError("unknown sequence operation %r" % (operation,))
            registers = (gain, phase, frequency, waveform)
            if registers != last_registers:
                self.set_pulse_registers(
                    ch=qch, style="arb",
                    freq=self.freq2reg(frequency, gen_ch=qch),
                    phase=self.deg2reg(phase, gen_ch=qch),
                    gain=gain, waveform=waveform)
                last_registers = registers
            self.pulse(ch=qch)
            if gap > 0:
                self.sync_all(gap)
        self.measure(pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                     wait=True, syncdelay=self.us2cycles(
                         cfg.get("active_reset_post_measure_delay_us", 0.05)
                         if feedback else cfg["relax_delay"]))

    def acquire(self, soc, load_pulses=True, progress=False, **kw):
        n_reset = active_reset.active_reset_readouts(self.cfg)
        return super().acquire(
            soc, load_pulses=load_pulses,
            readouts_per_experiment=1 + n_reset, progress=progress, **kw)


def _curve_from_qick(value, n):
    arr = np.asarray(value, dtype=float).squeeze()
    if arr.ndim == 0:
        arr = np.repeat(float(arr), int(n))
    arr = arr.reshape(-1)
    if arr.size < n:
        raise RuntimeError("QICK returned %d points, expected %d" % (arr.size, n))
    return arr[:n]


def _mean_from_qick(value):
    arr = np.asarray(value, dtype=float)
    if not arr.size:
        raise RuntimeError("QICK returned an empty acquisition")
    return float(np.mean(arr))


def _shots_from_program(program, cfg):
    length = program.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0])
    n = int(cfg["reps"])
    n_reset = active_reset.active_reset_readouts(cfg)
    reads = 1 + n_reset
    di, dq = getattr(program, "di_buf", None), getattr(program, "dq_buf", None)
    if di is not None and dq is not None:
        shot_i = np.asarray(di, dtype=float)[0].reshape((n, reads))[:, n_reset]
        shot_q = np.asarray(dq, dtype=float)[0].reshape((n, reads))[:, n_reset]
        return shot_i / length, shot_q / length
    get_raw = getattr(program, "get_raw", None)
    if callable(get_raw):
        raw = np.asarray(get_raw(), dtype=float).reshape(-1, 2)
        raw = raw.reshape((n, reads, 2))[:, n_reset, :]
        return raw[:, 0] / length, raw[:, 1] / length
    raise RuntimeError("QICK exposes neither di_buf/dq_buf nor get_raw per-shot data")


def load_basic_autotuner_diagnostic(path, load_raw=False):
    """Load a self-contained diagnostic bundle produced by :class:`BasicAutoTuner`.

    ``load_raw=False`` returns the complete run archive and a light record manifest.
    Set it true only when per-shot IQ arrays are needed; hardware bundles can be large.
    """
    with h5py.File(os.fspath(path), "r") as handle:
        if "snapshot/run_data_pickle" not in handle:
            raise ValueError("diagnostic bundle has no complete run snapshot")
        payload = np.asarray(
            handle["snapshot/run_data_pickle"], dtype=np.uint8).tobytes()
        run_data = pickle.loads(payload)
        records = []
        raw_group = handle.get("raw_records")
        if raw_group is not None:
            for name in sorted(raw_group):
                group = raw_group[name]
                row = {
                    "record_index": int(name),
                    "kind": str(group.attrs.get("kind", "unknown")),
                    "timestamp_unix": float(group.attrs.get(
                        "timestamp_unix", np.nan)),
                    "candidate": json.loads(group.attrs.get(
                        "candidate_json", "{}")),
                    "pulse_signature": json.loads(group.attrs.get(
                        "pulse_signature_json", "null")),
                    "reset_runtime": json.loads(group.attrs.get(
                        "reset_runtime_json", "{}")),
                    "metadata": json.loads(group.attrs.get(
                        "metadata_json", "{}")),
                    "datasets": {
                        key: {"shape": tuple(group[key].shape),
                              "dtype": str(group[key].dtype)}
                        for key in group.keys()},
                }
                if load_raw:
                    row["raw"] = {
                        key: np.asarray(group[key]) for key in group.keys()}
                records.append(row)
        return {
            "run_data": run_data,
            "raw_records": records,
            "format_version": int(handle.attrs.get("format_version", 0)),
            "autotuner_revision": str(handle.attrs.get(
                "autotuner_revision", "unknown")),
            "complete": bool(handle.attrs.get("complete", False)),
            "source_sha256": str(handle.attrs.get(
                "source_sha256", "unavailable")),
            "write_failures": json.loads(handle.attrs.get(
                "write_failures_json", "[]")),
        }


class BasicAutoTuner(ExperimentClass):
    """Streamlined autotuner built around direct TLS step-5 fidelity.

    Hardware methods beginning with ``_acquire_`` are deliberately narrow injection
    boundaries.  The test suite replaces them with a virtual device; production uses
    the exact QICK programs in this module and ``mSingleShot1Q``.
    """

    def __init__(self, soc=None, soccfg=None, path="", outerFolder="", prefix="data",
                 suffix="Basic_Auto_Tune", cfg=None, meta_dict=None, params=None, **kw):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
                         prefix=prefix, suffix=suffix, cfg=copy.deepcopy(cfg),
                         meta_dict=meta_dict, **kw)
        if cfg is None:
            raise ValueError("BasicAutoTuner requires a configuration dictionary")
        self.input_cfg = copy.deepcopy(cfg)
        self.params = _deep_merge(BASIC_DEFAULTS, params)
        self.rng = np.random.default_rng(int(self.params["random_seed"]))
        self.initial = _candidate_from_cfg(self.input_cfg)
        self.working = dict(self.initial)
        self._archive = []
        self._joint_archive = CandidateArchive(self._archive)
        self._joint_rows = []
        self._confirmed = []
        self._unconfirmed_contenders = []
        self._maps = {}
        self._stages = []
        self._report = []
        self._key_evidence = {key: [] for key in TUNED_KEYS}
        self._resonator_seed = float(self.initial["read_pulse_freq"])
        self._discovery_readout = dict(self.initial)
        self._resonator_candidates = []
        self._resonator_branch_records = []
        self._spec_candidate_rows = []
        self._spectroscopy_branch_attempts = []
        # An input frequency is a value to replay, not evidence that a transition
        # exists there.  Spectroscopy populates this list only with measured,
        # independently reproduced features (unless spectroscopy is explicitly off).
        self._spec_candidates_mhz = []
        self._discovery_guard_active = False
        self._discovery_status = {
            "resonator": False,
            "spectroscopy": False,
        }
        self._control_witnesses = []
        self._final_control_verified_key = None
        self._rabi_candidates = []
        self._rough_control_candidates = []
        self._qualified_control_candidates = []
        self._qualified_transition_frequency = None
        self._qualified_transition_frequencies = []
        self._qualified_control_key = None
        self._bootstrap_control_candidate = None
        self._portfolio_aae_candidates = []
        self._interrupted = False
        self._final_replay_completed = False
        self._final_replay_kind = None
        self._fast_gain_sweep = None
        self._leakage_active = self._leakage_enabled()
        self._operational_leakage_active = bool(
            self.params["leakage"].get("operational_enabled", True))
        self._duration_portfolio_active = bool(
            self.params["duration_portfolio"].get("enabled", True))
        self._leakage_selected_candidate = None
        self._leakage_ef_calibration = None
        self._leakage_verified_candidate_key = None
        self._latency_reference_key = None
        self._confirmation_cohort_serial = 0
        self._reset_runtime = {"reset_mode": "passive"}
        self._last_compiled_reset_runtime = {"reset_mode": "passive"}
        self._reset_readout_key = None
        self._reset_profiles = {}
        self._reset_fixed_readout_gain = None
        self._reset_fixed_control = None
        self._feedback_profiles_suspended = False
        self._reset_unavailable = False
        self._feedback_disqualified = False
        self._res_phase_calibrated = False
        self._thermalization = {"verified": False}
        self._run_started_monotonic = None
        self._joint_search_started_monotonic = None
        self._final_replays = []
        self._analyze_multimodality = False
        diagnostic_settings = self.params["diagnostics"]
        self.diagnostic_fname = self.dname + "_diagnostics.h5"
        self._diagnostic_active = bool(
            diagnostic_settings.get("enabled", True)
            and (self.soc is not None or diagnostic_settings.get(
                "force_without_hardware", False)))
        self._diagnostic_h5 = None
        self._diagnostic_record_count = 0
        self._diagnostic_write_failures = []
        self.data = {
            "revision": BASIC_AUTOTUNER_REVISION,
            "autotuner_revision": BASIC_AUTOTUNER_REVISION,
            "pulse_program": "TLS step-5 SingleShotProgram with fixed-reset profiles",
            "initial_pulse_signature": self._pulse_signature(self.initial),
            "fidelity_definition": "TLS step-5 balanced assignment fidelity",
            "selection_objective": (
                "at every requested readout duration, report the "
                "locally gain-converged full tuple maximizing one common interleaved "
                "held-out fidelity LCB; also report a constant-area, lower-drive "
                "balanced alternative only when paired noninferiority, leakage, and "
                "coherent-control measurements support it; manual selection only"
                if self._duration_portfolio_active else
                "minimize measured X180-plus-readout latency among candidates within "
                "a familywise held-out noninferiority bound of the best TLS step-5 "
                "fidelity, subject to direct shelving P(f) and third-cloud "
                "upper-confidence constraints"
                if self._leakage_active else
                "minimize measured X180-plus-readout latency among candidates within "
                "a familywise held-out noninferiority bound of the best TLS step-5 "
                "fidelity, then require independently verified fixed-Gaussian "
                "duration/power candidates without a resolved third IQ population"),
            "initial": dict(self.initial),
            "working": dict(self.working),
            "best_found": None,
            "candidate_archive": self._archive,
            "confirmed_candidates": self._confirmed,
            "unconfirmed_contenders": self._unconfirmed_contenders,
            "maps": self._maps,
            "joint_search": {
                "enabled": bool(self.params["joint_search"].get("enabled", True)),
                "status": "not_run", "coarse_rows": [],
                "medium_rows": [], "trust_rows": [], "closure_rounds": [],
            },
            "final_replay_history": self._final_replays,
            "stages": self._stages,
            "report": self._report,
            "discovery": self._discovery_status,
            "control_witnesses": self._control_witnesses,
            "control_branch_qualification": {
                "status": "not_run", "qualified": False,
                "frequency_qualified": False,
                "selected_control_verified": False,
                "selected": None, "branches": [],
                "expensive_search_allowed": False,
            },
            "confirmation_failures": [],
            "latency_optimization": {
                "enabled": bool(
                    not self._duration_portfolio_active
                    and self.params["latency"].get("enabled", True)),
                "objective": "readout generator duration plus four-sigma X180",
                "requested_objective": "read_length plus four-sigma X180",
                "status": "not_run",
            },
            "duration_portfolio": {
                "enabled": bool(self._duration_portfolio_active),
                "manual_selection_only": bool(
                    self.params["duration_portfolio"].get(
                        "manual_selection_only", True)),
                "readout_length_mode": self.params["duration_portfolio"].get(
                    "readout_length_mode", "custom"),
                "configured_initialize_read_length_us": self.params[
                    "duration_portfolio"].get(
                        "configured_initialize_read_length_us"),
                "read_lengths_us": list(
                    self.params["duration_portfolio"].get(
                        "read_lengths_us", [])),
                "entries": [], "status": "not_run",
                "automatic_write_allowed": False,
            },
            "diagnostic_bundle": {
                "enabled": bool(self._diagnostic_active),
                "path": self.diagnostic_fname,
                "format_version": 1,
                "raw_record_count": 0,
                "complete": False,
                "write_failures": self._diagnostic_write_failures,
            },
            "key_evidence": self._key_evidence,
            "eligible_tuned": {},
            "tuned": {},
            "outcome": "not_started",
            "success": False,
            "leakage": {
                "active": bool(
                    self._leakage_active or self._operational_leakage_active),
                "strict_direct_active": bool(self._leakage_active),
                "operational_active": bool(self._operational_leakage_active),
                "required_for_write": bool(
                    (self._leakage_active or self._operational_leakage_active)
                    and self.params["leakage"].get("required_for_write", True)),
                "measurement": (
                    "identity+shelving qutrit response inversion"
                    if self._leakage_active else
                    "fixed-Gaussian duration/power 2-D third-population screen"),
                "direct_p2_measured": False,
                "third_blob_guard": True,
                "third_cluster_guard": True,
                "optimized": False, "verified": False,
                "failure": None,
            },
            "fast_flux_operating_point": {
                "mode": "static_park",
                "configured": bool(ff_pulse.static_park_configured(self.input_cfg)),
                "ff_ch": self.input_cfg.get("ff_ch"),
                "ff_park_gain": int(self.input_cfg.get("ff_park_gain", 0) or 0),
                "tuned": False,
            },
            "reset": {
                "requested": bool(self.params["reset"].get("enabled", True)),
                "mode": "passive", "fresh": False,
                "authority": "exact_same_tuple_passive_feedback_step5_ab",
                "feedback_disqualified": False,
                "readout_key": None, "events": [],
                "fallback_relax_delay_us": float(
                    self.input_cfg.get("relax_delay", np.nan)),
            },
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._load_resume_checkpoint()

    # ------------------------------------------------------------------ invariants
    def _load_resume_checkpoint(self):
        path = self.params.get("resume_checkpoint")
        if path in (None, ""):
            return
        path = os.path.abspath(os.path.expanduser(str(path)))
        with open(path, "rb") as stream:
            previous = pickle.load(stream)
        if not isinstance(previous, dict):
            raise ValueError("resume checkpoint is not an autotuner result dictionary")
        if previous.get("revision") != BASIC_AUTOTUNER_REVISION:
            raise ValueError("resume checkpoint revision %r does not match %r"
                             % (previous.get("revision"),
                                BASIC_AUTOTUNER_REVISION))
        old_initial = previous.get("initial")
        if (not isinstance(old_initial, dict)
                or _candidate_key(old_initial) != _candidate_key(self.initial)):
            raise ValueError("resume checkpoint belongs to a different input tuple")
        old_flux = previous.get("fast_flux_operating_point", {})
        if (not isinstance(old_flux, dict)
                or int(old_flux.get("ff_park_gain", 0) or 0)
                != int(self.input_cfg.get("ff_park_gain", 0) or 0)
                or old_flux.get("ff_ch") != self.input_cfg.get("ff_ch")):
            raise ValueError("resume checkpoint belongs to a different fast-flux context")
        archived = previous.get("candidate_archive", [])
        confirmed = previous.get("confirmed_candidates", [])
        self._archive.extend(copy.deepcopy(
            archived if isinstance(archived, list) else []))
        self._confirmed.extend(copy.deepcopy(
            confirmed if isinstance(confirmed, list) else []))
        old_joint = previous.get("joint_search", {})
        if isinstance(old_joint, dict):
            self.data["joint_search"]["resumed_coarse_rows"] = copy.deepcopy(
                old_joint.get("coarse_rows", []))
        self.data["resume"] = {
            "checkpoint": path,
            "archived_measurements": len(self._archive),
            "confirmed_candidates": len(self._confirmed),
            "policy": "reuse complete coarse cells; freshly replay later stages",
        }

    @staticmethod
    def _reset_readout_signature(candidate):
        return (
            round(float(candidate["read_pulse_freq"]), 9),
            int(round(candidate["read_pulse_gain"])),
            round(float(candidate["read_length"]), 9),
        )

    @staticmethod
    def _reset_profile_signature(candidate):
        """ADC/DDC coordinates that bind one fixed-gain reset threshold."""
        return (
            round(float(candidate["read_pulse_freq"]), 9),
            round(float(candidate["read_length"]), 9),
        )

    def _pulse_signature(self, candidate):
        cfg = copy.deepcopy(self.input_cfg)
        cfg.update({key: candidate[key] for key in (
            "read_pulse_freq", "read_pulse_gain", "read_length",
            "qubit_freq", "qubit_pi_freq", "qubit_pi_gain", "sigma")})
        cfg["qubit_drag_beta"] = float(candidate.get("qubit_drag_beta", 0.0))
        cfg["qubit_gain"] = int(round(candidate["qubit_pi_gain"]))
        cfg["qubit_pulse_style"] = "arb"
        cfg["use_switch"] = False
        cfg["switch_triggered"] = False
        encoded = json.dumps(
            pulse_fingerprint(cfg), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _deactivate_feedback(self, reason=None):
        was_feedback = self._reset_runtime.get("reset_mode") == "feedback"
        self._feedback_profiles_suspended = True
        self._reset_runtime = {"reset_mode": "passive"}
        self.data["reset"].update({"mode": "passive", "fresh": False})
        if reason is not None:
            event = {"mode": "passive", "reason": str(reason),
                     "readout_key": list(self._reset_readout_signature(self.working))}
            self.data["reset"]["events"].append(event)
            if was_feedback:
                self._log("reset", "OK", "%s; using passive reset for this map"
                          % reason)

    def _working_confirmation_fidelity(self):
        rows = [row for row in self._confirmed
                if _candidate_key(row) == _candidate_key(self.working)]
        return max((float(row.get("fidelity", -np.inf)) for row in rows),
                   default=-np.inf)

    def _capture_reset_probe_diagnostic(self, raw, record, candidate, reason):
        """Move raw reset-threshold distributions into the run bundle."""
        if not isinstance(raw, dict):
            return
        record = record if isinstance(record, dict) else {}
        recommended = record.get("recommended", {})
        if not isinstance(recommended, dict):
            recommended = {}
        arrays = {}
        for state in ("ground", "excited"):
            state_rows = raw.get(state, {})
            if not isinstance(state_rows, dict):
                continue
            for quadrature in ("lower", "upper"):
                if quadrature in state_rows:
                    arrays["%s_%s" % (state, quadrature)] = state_rows[quadrature]
        if arrays:
            self._record_raw_diagnostic(
                "active_reset_probe", candidate, arrays,
                {"reason": str(reason),
                 "threshold_raw": recommended.get("threshold_raw"),
                 "oper": recommended.get("oper"),
                 "ground_below": recommended.get("ground_below"),
                 "raw_assignment_fidelity": record.get(
                     "raw_assignment_fidelity"),
                 "validation": record.get("validation")})

    def _qualify_feedback_runtime(self, candidate, runtime, reason):
        """Require exact step-5 equivalence before feedback can score a tuple.

        The reset probe observes residual reset-readout outcomes.  It does not prove
        that the complete ground/excited preparation and scoring path is unchanged.
        This randomized passive/feedback A/B replay is therefore the authority for
        every threshold profile used by the tuner.
        """
        settings = self.params["reset"]
        shots = max(int(settings.get("exact_qualification_shots", 650)), 1)
        blocks = max(int(settings.get("exact_qualification_blocks", 2)), 1)
        profile_key = self._reset_profile_signature(candidate)
        runtime = copy.deepcopy(runtime)
        runtime["reset_profile_key"] = profile_key
        self._reset_profiles[profile_key] = copy.deepcopy(runtime)
        previous_runtime = copy.deepcopy(self._reset_runtime)
        previous_suspended = bool(self._feedback_profiles_suspended)
        passive_rows, feedback_rows, failures = [], [], []
        try:
            # Reverse acquisition order every block so slow drift cannot be assigned
            # systematically to one reset mode.  GE/EG also alternates by block.
            for block in range(blocks):
                modes = ("passive", "feedback") if block % 2 == 0 else (
                    "feedback", "passive")
                for mode in modes:
                    self._reset_runtime = copy.deepcopy(runtime)
                    self._feedback_profiles_suspended = mode == "passive"
                    try:
                        row = self._measure_candidate(
                            candidate, shots,
                            "feedback exact A/B %s block %d after %s" % (
                                mode, block + 1, reason),
                            state_order="ge" if block % 2 == 0 else "eg",
                            archive=False)
                    except KeyboardInterrupt:
                        raise
                    except Exception as exc:
                        failures.append({
                            "mode": mode, "block": int(block + 1),
                            "error": "%s: %s" % (type(exc).__name__, exc),
                        })
                    else:
                        (passive_rows if mode == "passive" else
                         feedback_rows).append(row)
        finally:
            self._reset_runtime = previous_runtime
            self._feedback_profiles_suspended = previous_suspended

        passive = (self._aggregate(candidate, passive_rows,
                                   "feedback exact A/B passive")
                   if passive_rows else None)
        feedback = (self._aggregate(candidate, feedback_rows,
                                    "feedback exact A/B feedback")
                    if feedback_rows else None)
        complete = bool(
            not failures and len(passive_rows) == blocks
            and len(feedback_rows) == blocks)
        passive_fidelity = float(
            passive.get("fidelity", np.nan) if passive else np.nan)
        feedback_fidelity = float(
            feedback.get("fidelity", np.nan) if feedback else np.nan)
        passive_se = float(
            passive.get("fidelity_se", np.inf) if passive else np.inf)
        feedback_se = float(
            feedback.get("fidelity_se", np.inf) if feedback else np.inf)
        difference_se = float(np.hypot(passive_se, feedback_se))
        loss = passive_fidelity - feedback_fidelity
        loss_ucb = float(loss + 1.96 * difference_se)
        loss_lcb = float(loss - 1.96 * difference_se)
        paired_losses = [
            float(passive_rows[index]["fidelity"]
                  - feedback_rows[index]["fidelity"])
            for index in range(min(len(passive_rows), len(feedback_rows)))]
        worst_block_loss = float(max(paired_losses, default=np.inf))
        passive_sep = float(passive.get("sep_sigma", np.nan)
                            if passive else np.nan)
        feedback_sep = float(feedback.get("sep_sigma", np.nan)
                             if feedback else np.nan)
        separation_ratio = float(
            feedback_sep / passive_sep
            if np.isfinite(passive_sep) and passive_sep > 1e-9 else np.nan)
        feedback_lcb = float(feedback_fidelity - 1.96 * feedback_se)
        passed = bool(
            complete
            and np.all(np.isfinite([
                feedback_lcb, loss_ucb, worst_block_loss, separation_ratio]))
            and feedback_lcb >= float(settings.get(
                "exact_min_feedback_fidelity", 0.70))
            and loss_ucb <= float(settings.get(
                "exact_max_fidelity_loss", 0.030))
            and worst_block_loss <= float(settings.get(
                "exact_max_block_loss", 0.080))
            and separation_ratio >= float(settings.get(
                "exact_min_separation_ratio", 0.70)))
        catastrophic = bool(
            complete
            and np.isfinite(loss_lcb)
            and np.isfinite(passive_fidelity)
            and passive_fidelity >= float(settings.get(
                "exact_min_feedback_fidelity", 0.70))
            and loss_lcb >= float(settings.get(
                "exact_catastrophic_loss", 0.10)))
        qualification = {
            "reason": str(reason), "profile_key": list(profile_key),
            "candidate": {key: candidate[key] for key in self.initial},
            "shots_per_block": shots, "requested_blocks": blocks,
            "complete": complete, "passed": passed,
            "catastrophic_path_mismatch": catastrophic,
            "passive": copy.deepcopy(passive),
            "feedback": copy.deepcopy(feedback),
            "fidelity_loss": loss, "fidelity_loss_se": difference_se,
            "fidelity_loss_lcb_95": loss_lcb,
            "fidelity_loss_ucb_95": loss_ucb,
            "worst_paired_block_loss": worst_block_loss,
            "separation_ratio": separation_ratio,
            "failures": failures,
        }
        self.data["reset"].setdefault(
            "exact_step5_qualifications", []).append(qualification)
        if passed:
            self._reset_runtime = copy.deepcopy(runtime)
            self._feedback_profiles_suspended = False
            self._reset_profiles[profile_key] = copy.deepcopy(runtime)
            return True

        self._reset_profiles.pop(profile_key, None)
        self._reset_runtime = {"reset_mode": "passive"}
        self._feedback_profiles_suspended = True
        self.data["reset"].setdefault("failed_profiles", []).append({
            "profile_key": list(profile_key), "reason": str(reason),
            "failure": "exact step-5 passive/feedback equivalence failed",
            "qualification": copy.deepcopy(qualification),
        })
        if catastrophic:
            self._feedback_disqualified = True
            self._reset_profiles.clear()
            self.data["reset"]["feedback_disqualified"] = True
            self.data["reset"]["feedback_disqualification_reason"] = (
                "exact same-tuple feedback replay degraded fidelity by %.3f "
                "(95%% lower bound %.3f)" % (loss, loss_lcb))
        return False

    def _calibrate_reset_phase(self, reason):
        settings = self.params["reset"].get("res_phase_calibration", {})
        if not isinstance(settings, dict) or not bool(settings.get("enabled", True)):
            return None
        if self._res_phase_calibrated:
            return None
        self._res_phase_calibrated = True
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.reset_phase import (
            calibrate_res_phase,
        )
        previous = float(self.input_cfg.get("res_phase", 0.0))
        probe_cfg = self._cfg_for(self.working, reset_mode="passive")
        record = {
            "attempted": True, "reason": str(reason),
            "res_phase_before_deg": previous,
            "candidate": {key: self.working[key] for key in self.initial},
            "writes_initialize_py": False,
        }
        try:
            def run_calibration():
                return calibrate_res_phase(
                    self.soc, self.soccfg, probe_cfg, self.path,
                    self.outerFolder, apply_config=False,
                    sweep_shots=int(settings.get("sweep_shots", 800)),
                    check_shots=int(settings.get("check_shots", 3000)),
                    phase_step_deg=float(settings.get("phase_step_deg", 15.0)),
                    relax_delay_us=float(settings.get("relax_delay_us", 500.0)))

            if self._detailed_console():
                best = run_calibration()
            else:
                with redirect_stdout(io.StringIO()):
                    best = run_calibration()
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            record.update({
                "applied": False,
                "failure": "%s: %s" % (type(exc).__name__, exc)})
            self.data["reset"]["res_phase_calibration"] = record
            self._log("reset", "WARN",
                      "readout-phase alignment failed before %s (%s: %s); keeping "
                      "the configured res_phase" % (reason, type(exc).__name__, exc))
            return None
        try:
            best = float(best)
        except (TypeError, ValueError):
            best = float("nan")
        if not np.isfinite(best):
            record.update({
                "applied": False,
                "failure": "no aligned readout phase was returned"})
            self.data["reset"]["res_phase_calibration"] = record
            self._log("reset", "WARN",
                      "readout-phase alignment produced no usable angle before %s; "
                      "keeping the configured res_phase" % reason)
            return None
        self.input_cfg["res_phase"] = best
        record.update({
            "applied": True, "res_phase_deg": best,
            "res_phase_shift_deg": float(best - previous),
            "aligned_pulse_signature": self._pulse_signature(self.working),
        })
        self.data["reset"]["res_phase_calibration"] = record
        self._log(
            "reset", "OK",
            "aligned the readout phase for tProc discrimination: res_phase "
            "%.1f -> %.1f deg (run-scoped; initialize.py untouched, step-5 "
            "fidelity is invariant to this rotation)" % (previous, best))
        return best

    def _try_activate_feedback(self, reason):
        """Freshly calibrate feedback for the exact current readout/control tuple."""
        settings = self.params["reset"]
        if (not bool(settings.get("enabled", True)) or self._reset_unavailable
                or self._feedback_disqualified):
            return False
        if self.soccfg is None or not active_reset.active_reset_supported(
                self.soccfg, self.input_cfg["ro_chs"][0]):
            self._reset_unavailable = True
            self.data["reset"]["events"].append({
                "mode": "passive", "reason": "feedback path unavailable"})
            return False
        self._calibrate_reset_phase(reason)
        # A weak starting tuple must never gate either tuning or the attempt to make
        # tuning faster.  The end-to-end reset probe below is the authority: if the
        # rough pulse/readout cannot support reset it rejects the profile safely, but
        # a low assignment-fidelity estimate by itself is not a reason to give up.
        fidelity = self._working_confirmation_fidelity()
        minimum = float(settings.get("min_activation_fidelity", 0.75))
        if not np.isfinite(fidelity) or fidelity < minimum:
            self._log(
                "reset", "WARN",
                "probing feedback after %s despite weak current F %.3f; the fresh "
                "end-to-end reset validation will decide" % (reason, fidelity))
        probe_cfg = self._cfg_for(self.working, reset_mode="passive")
        try:
            def run_probe():
                return active_reset.probe_reset_params(
                    self.soc, self.soccfg, probe_cfg, path=self.path,
                    outer_folder=self.outerFolder,
                    shots=int(settings.get("probe_shots", 2000)), validate=True,
                    min_raw_fidelity=float(
                        settings.get("min_raw_assignment_fidelity", 0.80)),
                    diagnostic_callback=lambda raw, data:
                        self._capture_reset_probe_diagnostic(
                            raw, data, self.working, reason))

            if self._detailed_console():
                rec = run_probe()
            else:
                # The complete raw-IQ/threshold/residual diagnostics remain in the
                # probe artifact and returned reset record.  They are useful for
                # debugging, but not useful as routine operator console output.
                with redirect_stdout(io.StringIO()):
                    rec = run_probe()
        except Exception as exc:
            rec = None
            self._log("reset", "WARN", "feedback probe failed after %s (%s: %s)"
                      % (reason, type(exc).__name__, exc))
        if rec is None:
            self._deactivate_feedback(
                "fresh feedback validation failed after %s" % reason)
            return False
        self._reset_fixed_readout_gain = int(self.working["read_pulse_gain"])
        self._reset_fixed_control = {
            "qubit_pi_freq": float(self.working["qubit_pi_freq"]),
            "qubit_pi_gain": int(self.working["qubit_pi_gain"]),
            "sigma": float(self.working["sigma"]),
            "qubit_drag_beta": float(
                self.working.get("qubit_drag_beta", 0.0)),
        }
        profile_key = self._reset_profile_signature(self.working)
        self._reset_runtime = {
            "reset_mode": "feedback",
            "reset_profile_key": profile_key,
            "reset_threshold_raw": int(rec["threshold_raw"]),
            "reset_oper": str(rec.get("oper", "lower")),
            "reset_ground_below": bool(rec.get("ground_below", True)),
            "reset_max_iters": int(settings.get("max_iters", 3)),
            "reset_thermalization_us": float(
                settings.get("thermalization_us", 25.0)),
            "active_reset_post_measure_delay_us": float(
                settings.get("post_measure_delay_us", 0.05)),
            "reset_read_pulse_freq": float(self.working["read_pulse_freq"]),
            "reset_read_pulse_gain": int(self._reset_fixed_readout_gain),
            # Freeze the validated correction pulse while candidate pulse parameters
            # are swept.  Otherwise a deliberately bad candidate would also become
            # its own reset pulse and be unfairly penalized by a different initial
            # state rather than by its gate action.
            "reset_pi_freq": float(self.working["qubit_pi_freq"]),
            "reset_pi_gain": int(self.working["qubit_pi_gain"]),
            "reset_pi_sigma": float(self.working["sigma"]),
            "reset_pi_drag_beta": float(
                self.working.get("qubit_drag_beta", 0.0)),
        }
        self._reset_profiles[profile_key] = copy.deepcopy(self._reset_runtime)
        self._feedback_profiles_suspended = False
        if not self._qualify_feedback_runtime(
                self.working, self._reset_runtime, reason):
            self._deactivate_feedback(
                "exact passive/feedback step-5 qualification failed after %s"
                % reason)
            return False
        self._reset_readout_key = self._reset_readout_signature(self.working)
        event = {
            "mode": "feedback", "reason": str(reason),
            "readout_key": list(self._reset_readout_key),
            "threshold_raw": int(rec["threshold_raw"]),
            "oper": str(rec.get("oper", "lower")),
            "ground_below": bool(rec.get("ground_below", True)),
            "validation": rec.get("validation"),
            "raw_assignment_fidelity": rec.get("raw_assignment_fidelity"),
            "raw_assignment_errors": rec.get("raw_assignment_errors"),
            "thermalization_us": float(settings.get("thermalization_us", 25.0)),
        }
        self.data["reset"]["events"].append(event)
        self.data["reset"].update({
            "mode": "feedback", "fresh": True,
            "readout_key": list(self._reset_readout_key),
            "threshold_raw": int(rec["threshold_raw"]),
            "oper": str(rec.get("oper", "lower")),
            "ground_below": bool(rec.get("ground_below", True)),
            "validation": rec.get("validation"),
            "raw_assignment_fidelity": rec.get("raw_assignment_fidelity"),
            "raw_assignment_errors": rec.get("raw_assignment_errors"),
            "thermalization_us": float(settings.get("thermalization_us", 25.0)),
        })
        self._log(
            "reset", "OK",
            "fresh end-to-end feedback reset enabled after %s (threshold %d, %s, "
            "%d passes)" % (reason, int(rec["threshold_raw"]),
                             rec.get("oper", "lower"),
                             int(settings.get("max_iters", 3))))
        return True

    def _ensure_reset_profile(self, candidate, reason):
        """Cache feedback discrimination for one frequency/integration pair.

        The reset readout drive gain and correction X180 are frozen from the bootstrap
        calibration.  Only the ADC/DDC frequency and integration length change, so a
        profile is reusable across every scoring readout gain in that duration group.
        """
        settings = self.params["reset"]
        key = self._reset_profile_signature(candidate)
        if (not bool(settings.get("enabled", True))
                or self._reset_unavailable or self._feedback_disqualified):
            return False
        if key in self._reset_profiles:
            self._reset_runtime = copy.deepcopy(self._reset_profiles[key])
            self._feedback_profiles_suspended = False
            return True
        if (self.soccfg is None or not active_reset.active_reset_supported(
                    self.soccfg, self.input_cfg["ro_chs"][0])):
            return False
        if self._reset_fixed_readout_gain is None or self._reset_fixed_control is None:
            # This normally happens only if the bootstrap feedback activation failed.
            # A profile cannot safely be invented from an unvalidated candidate.
            return False
        probe_candidate = _with_candidate(
            candidate,
            read_pulse_gain=int(self._reset_fixed_readout_gain),
            qubit_pi_freq=float(self._reset_fixed_control["qubit_pi_freq"]),
            qubit_pi_gain=int(self._reset_fixed_control["qubit_pi_gain"]),
            sigma=float(self._reset_fixed_control["sigma"]),
            qubit_drag_beta=float(
                self._reset_fixed_control.get("qubit_drag_beta", 0.0)),
        )
        probe_cfg = self._cfg_for(probe_candidate, reset_mode="passive")
        try:
            def run_probe():
                return active_reset.probe_reset_params(
                    self.soc, self.soccfg, probe_cfg, path=self.path,
                    outer_folder=self.outerFolder,
                    shots=int(settings.get("profile_shots", 650)),
                    validate=bool(settings.get("profile_validate", True)),
                    min_raw_fidelity=float(settings.get(
                        "profile_min_raw_fidelity", 0.72)),
                    diagnostic_callback=lambda raw, data:
                        self._capture_reset_probe_diagnostic(
                            raw, data, probe_candidate, reason))

            if self._detailed_console():
                rec = run_probe()
            else:
                with redirect_stdout(io.StringIO()):
                    rec = run_probe()
        except Exception as exc:
            rec = None
            self._log("reset", "WARN", "reset profile %.6f MHz/%.1f us failed "
                      "after %s (%s: %s)" % (
                          key[0], key[1], reason, type(exc).__name__, exc))
        if rec is None:
            self.data["reset"].setdefault("failed_profiles", []).append({
                "profile_key": list(key), "reason": str(reason)})
            return False
        runtime = {
            "reset_mode": "feedback",
            "reset_profile_key": key,
            "reset_threshold_raw": int(rec["threshold_raw"]),
            "reset_oper": str(rec.get("oper", "lower")),
            "reset_ground_below": bool(rec.get("ground_below", True)),
            "reset_max_iters": int(settings.get("max_iters", 3)),
            "reset_thermalization_us": float(
                settings.get("thermalization_us", 25.0)),
            "active_reset_post_measure_delay_us": float(
                settings.get("post_measure_delay_us", 0.05)),
            "reset_read_pulse_freq": float(candidate["read_pulse_freq"]),
            "reset_read_pulse_gain": int(self._reset_fixed_readout_gain),
            "reset_pi_freq": float(self._reset_fixed_control["qubit_pi_freq"]),
            "reset_pi_gain": int(self._reset_fixed_control["qubit_pi_gain"]),
            "reset_pi_sigma": float(self._reset_fixed_control["sigma"]),
            "reset_pi_drag_beta": float(
                self._reset_fixed_control.get("qubit_drag_beta", 0.0)),
        }
        self._reset_profiles[key] = copy.deepcopy(runtime)
        self._reset_runtime = copy.deepcopy(runtime)
        self._feedback_profiles_suspended = False
        if not self._qualify_feedback_runtime(probe_candidate, runtime, reason):
            return False
        event = {
            "mode": "feedback_profile", "reason": str(reason),
            "profile_key": list(key),
            "fixed_readout_gain": int(self._reset_fixed_readout_gain),
            "threshold_raw": int(rec["threshold_raw"]),
            "raw_assignment_fidelity": rec.get("raw_assignment_fidelity"),
            "validation": rec.get("validation"),
        }
        self.data["reset"]["events"].append(event)
        self.data["reset"].update({
            "mode": "feedback", "fresh": True,
            "profile_count": len(self._reset_profiles),
            "active_profile_key": list(key),
            "fixed_readout_gain": int(self._reset_fixed_readout_gain),
        })
        return True

    def _leakage_enabled(self):
        """Whether the device configuration identifies a transmon e-f target."""
        settings = self.params["leakage"]
        mode = settings.get("enabled", "auto")
        if not (isinstance(mode, str) and mode.lower() == "auto"):
            return bool(mode)

        def finite(value):
            try:
                return bool(np.isfinite(float(value)))
            except (TypeError, ValueError, OverflowError):
                return False

        return bool(
            finite(self.input_cfg.get("qubit_ef_freq"))
            or finite(self.input_cfg.get("qubit_anharmonicity_mhz"))
            or finite(settings.get("anharmonicity_prior_mhz")))

    def _preflight(self):
        cfg = self.input_cfg
        required = (
            "res_ch", "qubit_ch", "ro_chs", "nqz", "qubit_nqz",
            "read_pulse_freq", "read_pulse_gain", "read_length",
            "qubit_pi_gain", "sigma", "adc_trig_offset", "relax_delay",
        )
        missing = [key for key in required if key not in cfg]
        if "qubit_pi_freq" not in cfg and "qubit_freq" not in cfg:
            missing.append("qubit_pi_freq (or qubit_freq)")
        if missing:
            raise ValueError("missing BasicAutoTuner config keys: %s" % ", ".join(missing))
        if int(cfg["res_ch"]) == int(cfg["qubit_ch"]):
            raise ValueError(
                "res_ch and qubit_ch are both %d; their pulse registers would collide"
                % int(cfg["res_ch"]))
        if len(cfg["ro_chs"]) != 1:
            raise ValueError(
                "basic tuner v1 requires exactly one readout channel; got %r"
                % (cfg["ro_chs"],))
        if str(cfg.get("qubit_pulse_style", "arb")).lower() != "arb":
            raise ValueError("basic tuner requires the canonical arb Gaussian pulse")
        if explicit_flat_top_fields(cfg):
            raise ValueError("basic tuner does not mix flat-top and 4-sigma Gaussian paths")
        if str(cfg.get("read_pulse_style", "const")).lower() != "const":
            raise ValueError("basic tuner requires the canonical constant readout pulse")
        if bool(cfg.get("use_switch", False)) or bool(
                cfg.get("switch_triggered", False)):
            raise ValueError("basic tuner v1 reproduces the step-5 switch-off pulse path")
        park_gain = int(cfg.get("ff_park_gain", 0) or 0)
        if park_gain != 0 and cfg.get("ff_ch", None) is None:
            raise ValueError(
                "nonzero ff_park_gain requires ff_ch so the operating point can be "
                "replayed on every acquisition")
        if cfg.get("ff_ch", None) is not None:
            ff_ch = int(cfg["ff_ch"])
            if ff_ch in (int(cfg["res_ch"]), int(cfg["qubit_ch"])):
                raise ValueError(
                    "ff_ch must be distinct from res_ch and qubit_ch; got %d" % ff_ch)
            try:
                ff_max = int(self.soccfg["gens"][ff_ch]["maxv"])
            except Exception:
                ff_max = None
            if ff_max is not None and abs(park_gain) > ff_max:
                raise ValueError(
                    "ff_park_gain %d exceeds fast-flux generator range +/- %d"
                    % (park_gain, ff_max))
        # A dynamic park->hold excursion is a different experiment timing path.  The
        # The basic tuner faithfully replays a *static* park value, but it must not
        # silently mix static stages with a pulsed-flux control stage.  Frequency
        # discovery coverage is a separate, explicitly configured relative prior or
        # absolute device envelope.
        if int(cfg.get("ff_hold_gain", 0) or 0) != 0:
            raise ValueError(
                "basic tuner calibrates the static ff_park_gain operating point; "
                "ff_hold_gain requests a dynamic flux excursion")
        for row in (cfg.get("FF_Qubits", {}) or {}).values():
            if not hasattr(row, "get"):
                continue
            for key in ("Gain_Readout", "Gain_Expt", "Gain_Pulse"):
                if int(row.get(key, 0) or 0) != 0:
                    raise ValueError(
                        "basic tuner supports static ff_park_gain, not legacy dynamic "
                        "FF_Qubits Gain_Readout/Gain_Expt/Gain_Pulse sequences")
        if float(cfg["sigma"]) <= 0 or float(cfg["read_length"]) <= 0:
            raise ValueError("sigma and read_length must be positive")
        relax_delay = float(cfg["relax_delay"])
        settings = self.params["reset"]
        multiple = float(settings.get("min_passive_relax_t1_multiple", 5.0))
        raw_t1 = cfg.get("qubit_t1_us", settings.get("assumed_qubit_t1_us"))
        try:
            t1 = float(raw_t1) if raw_t1 is not None else float("nan")
        except (TypeError, ValueError):
            t1 = float("nan")
        thermalization = {
            "passive_relax_delay_us": relax_delay,
            "qubit_t1_us": t1 if np.isfinite(t1) else None,
            "required_multiple_of_t1": multiple,
            "verified": False,
        }
        if np.isfinite(t1) and t1 > 0.0:
            required = multiple * t1
            thermalization.update({
                "required_relax_delay_us": required,
                "relax_delay_in_t1": float(relax_delay / t1),
                "verified": bool(relax_delay >= required - 1e-9),
            })
            if relax_delay < required - 1e-9:
                raise ValueError(
                    "relax_delay %.0f us is only %.1f x the configured qubit_t1_us "
                    "%.0f us; passive preparation needs at least %.1f x T1 (%.0f us) "
                    "or every ground-state measurement starts partly excited"
                    % (relax_delay, relax_delay / t1, t1, multiple, required))
        else:
            self._log(
                "preflight", "OK",
                "no qubit_t1_us is configured, so the %.0f us passive relaxation "
                "delay is an unverified thermalization assumption; a delay shorter "
                "than about %.0fx T1 corrupts every ground-state preparation"
                % (relax_delay, multiple))
        self._thermalization = thermalization
        self.data["thermalization"] = dict(thermalization)
        self._fast_gain_sweep = _qubit_gain_sweep_supported(
            self.soccfg, cfg["qubit_ch"])
        if self.soccfg is not None and self._fast_gain_sweep is not True:
            self._log(
                "preflight", "WARN",
                "qubit generator does not advertise a standalone gain register; "
                "using slower point-by-point compiled pulses so amplitude really changes")
        if ff_pulse.static_park_configured(cfg):
            self._log(
                "fast_flux", "OK",
                "holding configured ff_park_gain %d DAC on channel %s throughout; "
                "flux is fixed context, not a searched or writable parameter"
                % (park_gain, cfg.get("ff_ch")))

    def _cfg_for(self, candidate=None, **extra):
        c = self.working if candidate is None else candidate
        cfg = copy.deepcopy(self.input_cfg)
        cfg.update({key: c[key] for key in (
            "read_pulse_freq", "read_pulse_gain", "read_length",
            "qubit_freq", "qubit_pi_freq", "qubit_pi_gain", "sigma",
        )})
        cfg["qubit_drag_beta"] = float(c.get(
            "qubit_drag_beta", self.input_cfg.get("qubit_drag_beta", 0.0)) or 0.0)
        # This key is the RAverager register step used by SingleShotProgram.  Omitting
        # it was the exact kind of pulse-path mismatch that made older automatic runs
        # disagree with a 91.65% manual step-5 run.
        cfg["qubit_gain"] = int(round(c["qubit_pi_gain"]))
        cfg["qubit_pulse_style"] = "arb"
        profile_key = self._reset_profile_signature(c)
        reset = ({"reset_mode": "passive"}
                 if self._feedback_profiles_suspended else
                 dict(self._reset_profiles.get(profile_key, self._reset_runtime)))
        # The reset *drive* gain/control are frozen, so candidate readout gain can vary
        # without changing state preparation.  Frequency and ADC integration length
        # still bind the raw threshold and therefore require an exact cached profile.
        if (reset.get("reset_mode") == "feedback"
                and tuple(reset.get("reset_profile_key", ())) != profile_key):
            reset = {"reset_mode": "passive"}
        cfg.update(reset)
        # Per-shot buffers and requested shot counts must have one unambiguous meaning;
        # inherited software averaging would otherwise make seeds and direct SS use
        # different effective sample sets.
        cfg["rounds"] = 1
        cfg["soft_avgs"] = 1
        cfg["use_switch"] = False
        cfg["switch_triggered"] = False
        cfg.update(extra)
        # Diagnostics must describe the reset mode compiled into this acquisition,
        # not the tuner's global desired mode.  In particular an unmatched profile
        # deliberately compiles passive even while another feedback profile is live.
        reset_keys = {
            key for key in cfg
            if str(key).startswith("reset_")
        }
        reset_keys.add("reset_mode")
        if "active_reset_post_measure_delay_us" in cfg:
            reset_keys.add("active_reset_post_measure_delay_us")
        self._last_compiled_reset_runtime = {
            key: copy.deepcopy(cfg[key]) for key in reset_keys if key in cfg}
        self._last_compiled_reset_runtime.setdefault("reset_mode", "passive")
        return cfg

    def _detailed_console(self):
        console = self.params.get("console", {})
        if not isinstance(console, dict):
            return str(console).strip().lower() in ("detailed", "verbose", "debug")
        return str(console.get("verbosity", "concise")).strip().lower() in (
            "detailed", "verbose", "debug")

    @staticmethod
    def _candidate_console_text(candidate):
        if not isinstance(candidate, dict):
            return None
        try:
            text = ("read %.6f MHz / %d DAC / %.1f us; pi %.6f MHz / %d DAC / "
                    "%.1f ns"
                    % (float(candidate["read_pulse_freq"]),
                       int(round(candidate["read_pulse_gain"])),
                       float(candidate["read_length"]),
                       float(candidate["qubit_pi_freq"]),
                       int(round(candidate["qubit_pi_gain"])),
                       4000.0 * float(candidate["sigma"])))
            if np.isfinite(float(candidate.get("fidelity", np.nan))):
                text += "; F=%.3f" % float(candidate["fidelity"])
            return text
        except (KeyError, TypeError, ValueError):
            return None

    def _concise_stage_done(self, name, result):
        if name == "baseline":
            fidelity = (float(result.get("fidelity", np.nan))
                        if isinstance(result, dict) else np.nan)
            print("  Starting fidelity: %s" % (
                "%.3f" % fidelity if np.isfinite(fidelity) else "measured"))
        elif name == "resonator" and result is not None:
            candidates = np.asarray(self._maps.get("resonator", {}).get(
                "candidate_frequencies_mhz", [result]), dtype=float)
            if candidates.size > 1:
                print("  Resonator candidates found near %s MHz."
                      % ", ".join("%.6f" % value for value in candidates))
            else:
                print("  Resonator found near %.6f MHz." % float(result))
        elif name == "spectroscopy" and result:
            values = ", ".join("%.4f" % float(value) for value in result)
            if len(self._resonator_candidates) > 1:
                print("  Resonator/qubit branch selected: %.6f MHz readout; "
                      "qubit candidate%s near %s MHz."
                      % (self._resonator_seed,
                         "s" if len(result) != 1 else "", values))
            else:
                print("  Qubit candidate%s found near %s MHz."
                      % ("s" if len(result) != 1 else "", values))
        elif name == "iq_rabi":
            print("  Rough pi pulse: %.6f MHz at %d DAC."
                  % (self.working["qubit_pi_freq"],
                     int(round(self.working["qubit_pi_gain"]))))
        elif name == "reset_after_bootstrap":
            if bool(result):
                print("  Active reset is ready.")
            elif self._feedback_disqualified:
                print("  Active reset did not preserve the calibration; using passive "
                      "relaxation.")
            else:
                print("  Active reset was unavailable; using passive relaxation.")
        elif name in ("leakage", "operational_leakage"):
            safe = bool((self.data.get("leakage", {}) or {}).get(
                "selection_safe", False))
            print("  Fixed-Gaussian pulse passed the initial safety screen." if safe else
                  "  No pulse passed every leakage-sensitive check; automatic writes "
                  "are blocked.")
        elif name == "operational_leakage_verify":
            print("  Pulse-safety checks passed." if bool(result) else
                  "  Pulse-safety checks failed; automatic writes are blocked.")
        elif name == "leakage_verify":
            print("  Leakage verification passed." if bool(result) else
                  "  Leakage verification failed; automatic writes are blocked.")
        elif name in ("readout_grid", "readout_after_control", "readout_length",
                      "readout_repeat", "readout_post_leakage"):
            print("  Readout selected: %.6f MHz / %d DAC / %.1f us."
                  % (self.working["read_pulse_freq"],
                     int(round(self.working["read_pulse_gain"])),
                     self.working["read_length"]))
        elif name in ("rough_ss", "qubit_grid", "pulse_duration", "qubit_repeat",
                      "qubit_post_leakage"):
            print("  Pi pulse selected: %.6f MHz / %d DAC / %.1f ns."
                  % (self.working["qubit_pi_freq"],
                     int(round(self.working["qubit_pi_gain"])),
                     4000.0 * self.working["sigma"]))
        elif name == "parity_chevron":
            qualified = self.data.get("control_branch_qualification", {})
            branches = qualified.get("branches", []) if isinstance(
                qualified, dict) else []
            count = sum(str(row.get("status", "")).startswith(
                        "frequency_qualified") for row in branches)
            verified = bool(qualified.get("selected_control_verified", False))
            print("  Qubit transition frequency qualified near %.6f MHz (%d coherent "
                  "branch%s); rough repeated-pulse control %s."
                  % (self.working["qubit_pi_freq"], count,
                     "" if count == 1 else "es",
                     "verified" if verified else
                     "is provisional until final candidate audits"))
        elif name == "pre_expensive_gate":
            print("  Resonator and qubit transition are locked; starting the full "
                  "parameter search.")
        elif name == "amplified_error":
            print("  Repeated-pulse refinement complete.")
        elif name == "joint_search":
            coverage = self.data.get("joint_search", {}).get("coverage", {})
            print("  Joint search selected read %.1f us / %d DAC and X180 %.1f ns / "
                  "%d DAC%s."
                  % (self.working["read_length"],
                     int(round(self.working["read_pulse_gain"])),
                     4000.0 * self.working["sigma"],
                     int(round(self.working["qubit_pi_gain"])),
                     " with complete duration coverage"
                     if coverage.get("complete", False) else
                     " from the completed measurements"))
        elif name == "duration_portfolio":
            portfolio = self.data.get("duration_portfolio", {})
            entries = portfolio.get("entries", []) if isinstance(
                portfolio, dict) else []
            measured = sum(isinstance(row.get("selected"), dict)
                           for row in entries if isinstance(row, dict))
            print("  Portfolio complete: %d/%d fidelity-first rows measured; "
                  "leakage and coherent control are reported separately."
                  % (measured, len(entries)))
        elif name == "multi_aae":
            print("  AAE-refined pi pulse: %.6f MHz / %d DAC / %.1f ns."
                  % (self.working["qubit_pi_freq"],
                     int(round(self.working["qubit_pi_gain"])),
                     4000.0 * self.working["sigma"]))
        elif name.startswith("joint_closure_"):
            print("  Coupled refinement selected read %.1f us and X180 %.1f ns."
                  % (self.working["read_length"],
                     4000.0 * self.working["sigma"]))
        elif name == "latency":
            timing = self.data.get("latency_optimization", {})
            saved = float(timing.get("latency_saved_us", 0.0))
            loss = float(timing.get(
                "pre_safety_selected_fidelity_loss", 0.0))
            if str(timing.get("status", "")).startswith("retained_reference"):
                print("  No faster candidate proved the fidelity requirement; "
                      "keeping the best-fidelity reference.")
            else:
                print("  Shortest qualified chain: %.1f ns X180 + %.1f us readout "
                      "(saved %.2f us, measured dF %+.3f)."
                      % (4000.0 * self.working["sigma"],
                         self.working["read_length"], saved, -loss))
        elif name in ("final", "final_safe", "final_feedback"):
            text = self._candidate_console_text(result)
            print("  Validation complete%s." % ((": " + text) if text else ""))
        elif name == "final_control_verify":
            print("  Selected pi pulse passed the repeated-pulse check.")
        else:
            print("  Done.")

    def _log(self, stage, level, message):
        level = str(level).upper()
        row = {"stage": str(stage), "level": level, "message": str(message),
               "time": datetime.datetime.now().strftime("%H:%M:%S")}
        self._report.append(row)
        if self._detailed_console():
            print("  [%-16s] %-4s %s" % (str(stage)[:16], level, message))

    def _run_stage(self, name, function):
        row = {"name": name, "status": "running", "error": None}
        self._stages.append(row)
        concise_message = None if self._detailed_console() else _CONCISE_STAGE_START.get(name)
        if concise_message:
            print("  " + concise_message)
        try:
            result = function()
            row["status"] = "ok"
            if concise_message:
                self._concise_stage_done(name, result)
            return result
        except KeyboardInterrupt:
            row["status"] = "interrupted"
            self._interrupted = True
            raise
        except Exception as exc:
            row["status"] = "warning"
            row["error"] = "%s: %s" % (type(exc).__name__, exc)
            self._log(name, "WARN", "%s -- continuing with the best measured tuple"
                      % row["error"])
            if not self._detailed_console():
                label = concise_message or (str(name).replace("_", " ").capitalize() + "...")
                if name in ("operational_leakage", "operational_leakage_verify",
                            "leakage", "leakage_verify"):
                    print("  Warning: %s could not be completed (%s); retaining the "
                          "best completed fidelity replay."
                          % (label.rstrip("."), row["error"]))
                else:
                    print("  Warning: %s could not be completed; continuing with the "
                          "best measurement so far." % label.rstrip("."))
            return None
        finally:
            self.data["working"] = dict(self.working)
            # A long hardware run must survive a client crash or operator interrupt.
            # The pickle is the lossless checkpoint; HDF5/PNG are finalized by runner.
            try:
                self._checkpoint()
            except Exception as exc:
                self._log(name, "WARN", "checkpoint failed: %s" % exc)
                if not self._detailed_console():
                    print("  Warning: the intermediate checkpoint could not be saved.")

    # ------------------------------------------------------- raw diagnostic bundle
    def _diagnostic_file(self):
        """Open the append-only raw-acquisition bundle lazily."""
        if not self._diagnostic_active:
            return None
        if self._diagnostic_h5 is None:
            handle = h5py.File(self.diagnostic_fname, "a")
            handle.attrs["format"] = "BasicAutoTuner diagnostic bundle"
            handle.attrs["format_version"] = 1
            handle.attrs["autotuner_revision"] = BASIC_AUTOTUNER_REVISION
            handle.attrs["python_version"] = sys.version
            handle.require_group("raw_records")
            self._diagnostic_h5 = handle
        return self._diagnostic_h5

    def _diagnostic_failure(self, phase, exc):
        failure = {
            "phase": str(phase),
            "error": "%s: %s" % (type(exc).__name__, exc),
            "record_index": int(self._diagnostic_record_count),
        }
        self._diagnostic_write_failures.append(failure)
        bundle = self.data.get("diagnostic_bundle")
        if isinstance(bundle, dict):
            bundle["complete"] = False

    def _record_raw_diagnostic(self, kind, candidate, arrays, metadata=None):
        """Stream one raw IQ acquisition with its exact physical tuple.

        Diagnostic I/O is deliberately non-authoritative: a disk failure is recorded
        but never changes or aborts the calibration measurement itself.
        """
        if not self._diagnostic_active:
            return None
        index = int(self._diagnostic_record_count)
        self._diagnostic_record_count += 1
        try:
            handle = self._diagnostic_file()
            records = handle["raw_records"]
            name = "%08d" % index
            if name in records:
                del records[name]
            group = records.create_group(name)
            candidate_payload = ({key: candidate.get(key)
                                  for key in self.initial if key in candidate}
                                 if isinstance(candidate, dict) else {})
            group.attrs["kind"] = str(kind)
            group.attrs["timestamp_unix"] = float(time.time())
            group.attrs["candidate_json"] = json.dumps(
                candidate_payload, cls=NpEncoder, sort_keys=True)
            group.attrs["pulse_signature_json"] = json.dumps(
                self._pulse_signature(candidate_payload)
                if candidate_payload else None,
                cls=NpEncoder, sort_keys=True)
            group.attrs["reset_runtime_json"] = json.dumps(
                self._last_compiled_reset_runtime,
                cls=NpEncoder, sort_keys=True)
            group.attrs["reset_runtime_source"] = "compiled_acquisition_cfg"
            group.attrs["metadata_json"] = json.dumps(
                {} if metadata is None else metadata,
                cls=NpEncoder, sort_keys=True)
            settings = self.params["diagnostics"]
            compression = settings.get("compression", "gzip")
            compression = None if not compression else str(compression)
            compression_options = (
                int(settings.get("compression_level", 4))
                if compression == "gzip" else None)
            for key, value in dict(arrays).items():
                array = np.asarray(value)
                if not (np.issubdtype(array.dtype, np.number)
                        or array.dtype == bool):
                    continue
                options = {}
                if array.size > 1 and compression is not None:
                    options.update({
                        "compression": compression,
                        "shuffle": True,
                    })
                    if compression_options is not None:
                        options["compression_opts"] = compression_options
                if np.issubdtype(array.dtype, np.complexfloating):
                    group.create_dataset(str(key) + "_real", data=array.real,
                                         **options)
                    group.create_dataset(str(key) + "_imag", data=array.imag,
                                         **options)
                else:
                    group.create_dataset(str(key), data=array, **options)
            bundle = self.data.get("diagnostic_bundle")
            if isinstance(bundle, dict):
                bundle["raw_record_count"] = int(self._diagnostic_record_count)
            flush_every = max(int(settings.get("flush_every_records", 8)), 1)
            if self._diagnostic_record_count % flush_every == 0:
                handle.flush()
            return index
        except Exception as exc:
            self._diagnostic_failure("raw_%s" % kind, exc)
            return None

    @staticmethod
    def _replace_diagnostic_bytes(handle, path, payload):
        if path in handle:
            del handle[path]
        parent, _, name = path.rpartition("/")
        group = handle.require_group(parent) if parent else handle
        raw = np.frombuffer(bytes(payload), dtype=np.uint8)
        group.create_dataset(name, data=raw, compression="gzip",
                             compression_opts=4, shuffle=True)

    def _finalize_diagnostic_bundle(self, data):
        """Embed the complete run archive beside streamed raw IQ in one HDF5."""
        if not self._diagnostic_active:
            return False
        bundle = data.setdefault("diagnostic_bundle", {})
        bundle.update({
            "enabled": True,
            "path": self.diagnostic_fname,
            "format_version": 1,
            "raw_record_count": int(self._diagnostic_record_count),
            "complete": False,
            "write_failures": self._diagnostic_write_failures,
        })
        try:
            handle = self._diagnostic_file()
            source_hash = None
            try:
                with open(__file__, "rb") as stream:
                    source_hash = hashlib.sha256(stream.read()).hexdigest()
            except Exception:
                pass
            bundle.update({
                "complete": not bool(self._diagnostic_write_failures),
                "source_sha256": source_hash,
            })
            snapshot = pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
            self._replace_diagnostic_bytes(
                handle, "snapshot/run_data_pickle", snapshot)
            self._replace_diagnostic_bytes(
                handle, "snapshot/summary_json", json.dumps(
                    self._jsonable_summary(data), cls=NpEncoder,
                    sort_keys=True).encode("utf-8"))
            self._replace_diagnostic_bytes(
                handle, "snapshot/params_json", json.dumps(
                    self.params, cls=NpEncoder, sort_keys=True).encode("utf-8"))
            self._replace_diagnostic_bytes(
                handle, "snapshot/input_config_json", json.dumps(
                    self.input_cfg, cls=NpEncoder,
                    sort_keys=True).encode("utf-8"))
            try:
                soccfg_text = json.dumps(
                    self.soccfg, cls=NpEncoder, sort_keys=True)
            except Exception:
                soccfg_text = repr(self.soccfg)
            self._replace_diagnostic_bytes(
                handle, "snapshot/soccfg_text", soccfg_text.encode("utf-8"))
            handle.attrs["raw_record_count"] = int(
                self._diagnostic_record_count)
            handle.attrs["complete"] = bool(bundle["complete"])
            handle.attrs["source_sha256"] = source_hash or "unavailable"
            handle.attrs["write_failures_json"] = json.dumps(
                self._diagnostic_write_failures, cls=NpEncoder)
            handle.flush()
            handle.close()
            self._diagnostic_h5 = None
            return True
        except Exception as exc:
            self._diagnostic_failure("finalize", exc)
            try:
                if self._diagnostic_h5 is not None:
                    self._diagnostic_h5.flush()
                    self._diagnostic_h5.close()
            except Exception:
                pass
            self._diagnostic_h5 = None
            return False

    # ---------------------------------------------------------- production backends
    def _acquire_transmission(self, freqs_mhz, candidate, shots):
        freqs = np.asarray(freqs_mhz, dtype=float)
        z = np.full(freqs.size, np.nan + 1j * np.nan)
        order = self.rng.permutation(freqs.size)
        for index in order:
            cfg = self._cfg_for(candidate, read_pulse_freq=float(freqs[index]),
                                shots=int(shots), reps=int(shots))
            program = BasicTransmissionProgram(self.soccfg, cfg)
            avgi, avgq = program.acquire(
                self.soc, load_pulses=True, progress=False)
            z[index] = _mean_from_qick(avgi) + 1j * _mean_from_qick(avgq)
        return z

    def _acquire_spectroscopy(self, freqs_mhz, candidate, shots, gain,
                              pulse_length_us):
        freqs = np.asarray(freqs_mhz, dtype=float)
        if freqs.size < 2:
            raise ValueError("spectroscopy needs at least two frequencies")
        step = float(freqs[1] - freqs[0])
        cfg = self._cfg_for(
            candidate, start=float(freqs[0]), step=step, expts=int(freqs.size),
            reps=int(shots), shots=int(shots), spec_gain=int(round(gain)),
            spec_len_us=float(pulse_length_us),
        )
        program = BasicSpecProgram(self.soccfg, cfg)
        _x, avgi, avgq = program.acquire(
            self.soc, load_pulses=True, progress=False)
        return (_curve_from_qick(avgi, freqs.size)
                + 1j * _curve_from_qick(avgq, freqs.size))

    def _acquire_iq_chevron(self, freqs_mhz, gains, candidate, shots):
        freqs, gains = np.asarray(freqs_mhz, float), np.asarray(gains, int)
        if gains.size < 2:
            raise ValueError("Rabi gain sweep needs at least two gains")
        steps = np.diff(gains)
        if not np.all(steps == steps[0]):
            raise ValueError("hardware Rabi sweep requires equally spaced integer gains")
        i_map = np.full((freqs.size, gains.size), np.nan)
        q_map = np.full_like(i_map, np.nan)
        if self._fast_gain_sweep is True:
            for row, freq in enumerate(freqs):
                cfg = self._cfg_for(
                    candidate, drive_freq=float(freq), start=int(gains[0]),
                    step=int(steps[0]), expts=int(gains.size), reps=int(shots),
                    shots=int(shots),
                )
                program = BasicRabiProgram(self.soccfg, cfg)
                _x, avgi, avgq = program.acquire(
                    self.soc, load_pulses=True, progress=False)
                i_map[row] = _curve_from_qick(avgi, gains.size)
                q_map[row] = _curve_from_qick(avgq, gains.size)
            return i_map, q_map

        # Packed/unknown generator: compile every amplitude into the pulse registers.
        # This costs uploads but cannot silently produce a flat fake gain sweep.
        jobs = [(fi, gi) for fi in range(freqs.size) for gi in range(gains.size)]
        for job_index in self.rng.permutation(len(jobs)):
            fi, gi = jobs[int(job_index)]
            cfg = self._cfg_for(
                candidate, drive_freq=float(freqs[fi]), start=int(gains[gi]),
                step=0, expts=1, reps=int(shots), shots=int(shots),
            )
            program = BasicRabiProgram(self.soccfg, cfg)
            _x, avgi, avgq = program.acquire(
                self.soc, load_pulses=True, progress=False)
            i_map[fi, gi] = _curve_from_qick(avgi, 1)[0]
            q_map[fi, gi] = _curve_from_qick(avgq, 1)[0]
        return i_map, q_map

    def _acquire_ss_pair(self, candidate, shots, state_order="ge"):
        # This is the production TLS step-5 program, not a lookalike sequence program.
        if self._fast_gain_sweep is not True:
            # SingleShotProgram obtains g/e by sweeping the qubit gain register.  On a
            # packed generator, two fixed compiled programs are the only safe physical
            # equivalent.  Return arrays in canonical [ground, excited] order.
            acquired = {}
            states = ("ground", "excited") if state_order == "ge" \
                else ("excited", "ground")
            for state in states:
                cfg = self._cfg_for(
                    candidate, drive_freq=float(candidate["qubit_pi_freq"]),
                    sequence_gain=(0 if state == "ground"
                                   else int(candidate["qubit_pi_gain"])),
                    # Match SingleShotProgram's gain-zero ground arm exactly: it still
                    # emits the zero-amplitude waveform and the same 10 ns post-pulse gap.
                    sequence_phases_deg=[0.0], shots=int(shots), reps=int(shots),
                )
                program = BasicSequenceProgram(self.soccfg, cfg)
                program.acquire(self.soc, load_pulses=True, progress=False)
                acquired[state] = _shots_from_program(program, cfg)
            return (acquired["ground"][0], acquired["ground"][1],
                    acquired["excited"][0], acquired["excited"][1])

        cfg = self._cfg_for(
            candidate, qubit_gain=int(candidate["qubit_pi_gain"]),
            qubit_pi_gain=int(candidate["qubit_pi_gain"]),
            qubit_pi_freq=float(candidate["qubit_pi_freq"]),
            shots=int(shots), repeats=1,
            single_shot_state_order=str(state_order),
        )
        program = SingleShotProgram(self.soccfg, cfg)
        shot_i, shot_q = program.acquire(
            self.soc, load_pulses=True, progress=False)
        shot_i, shot_q = np.asarray(shot_i, float), np.asarray(shot_q, float)
        if shot_i.ndim != 2 or shot_q.ndim != 2 \
                or shot_i.shape[0] < 2 or shot_q.shape[0] < 2:
            raise RuntimeError("SingleShotProgram did not return [ground, excited] shots")
        return shot_i[0], shot_q[0], shot_i[1], shot_q[1]

    def _acquire_joint_gain_sweep(self, base_candidate, gains, shots, label,
                                  epoch=0):
        """Measure a complete pi-gain line with one shared ground cloud."""
        gains = np.asarray(gains, dtype=int)
        if (gains.ndim != 1 or gains.size < 3 or gains[0] != 0
                or np.any(np.diff(gains) <= 0)
                or not np.all(np.diff(gains) == np.diff(gains)[0])):
            raise ValueError("joint pi-gain sweep must be a uniform increasing axis "
                             "beginning at zero")
        if self.soccfg is None or self._fast_gain_sweep is not True:
            rows = []
            for index, gain in enumerate(gains[1:]):
                candidate = _with_candidate(
                    base_candidate, qubit_pi_gain=int(gain))
                row = self._measure_candidate(
                    candidate, int(shots), "%s gain %d" % (label, int(gain)),
                    state_order="ge" if index % 2 == 0 else "eg",
                    archive=False)
                row.update({
                    "evidence_level": "coarse_direct_proposal",
                    "evidence_tier": 1,
                })
                rows.append(self._joint_archive.append(
                    row, stage="joint_coarse", fidelity_level="coarse",
                    epoch=int(epoch)))
            return rows

        cfg = self._cfg_for(
            base_candidate,
            rabi_drive_freq=float(base_candidate["qubit_pi_freq"]),
            n_pulses=1, amp_start=int(gains[0]),
            amp_step=int(gains[1] - gains[0]), amp_expts=int(gains.size),
            shots=int(shots), reps=int(shots), ff_hold_gain=0)
        shot_i, shot_q = RabiSSProgram(self.soccfg, cfg).acquire(
            self.soc, load_pulses=True, progress=False)
        shot_i, shot_q = np.asarray(shot_i), np.asarray(shot_q)
        if shot_i.shape[0] != gains.size or shot_q.shape[0] != gains.size:
            raise RuntimeError("QICK joint gain sweep returned the wrong number of "
                               "gain experiments")
        self._record_raw_diagnostic(
            "joint_gain_sweep", base_candidate,
            {"shot_i": shot_i, "shot_q": shot_q},
            {"label": str(label), "gains_dac": gains,
             "shots": int(shots), "epoch": int(epoch)})
        rows = []
        for index, gain in enumerate(gains[1:], start=1):
            candidate = _with_candidate(
                base_candidate, qubit_pi_gain=int(gain))
            metrics = step5_metrics(
                shot_i[0], shot_q[0], shot_i[index], shot_q[index])
            row = dict(candidate)
            row.update({key: value for key, value in metrics.items()
                        if key != "confusion"})
            row.update({
                "confusion": np.asarray(metrics["confusion"]),
                "label": "%s gain %d" % (label, int(gain)),
                "state_order": "shared-ground-gain-sweep",
                "evidence_level": "shared_ground_proposal",
                "evidence_tier": 0,
                "measurement_index": len(self._archive),
                "pulse_signature": self._pulse_signature(candidate),
            })
            rows.append(self._joint_archive.append(
                row, stage="joint_coarse", fidelity_level="coarse",
                epoch=int(epoch)))
        return rows

    def _runtime_minutes(self):
        if self._run_started_monotonic is None:
            return 0.0
        return float((time.monotonic() - self._run_started_monotonic) / 60.0)

    def _joint_runtime_minutes(self):
        if self._joint_search_started_monotonic is None:
            return 0.0
        return float(
            (time.monotonic() - self._joint_search_started_monotonic) / 60.0)

    def _joint_budget_allows(self, reserve_final=True,
                             additional_reserve_minutes=0.0):
        settings = self.params["joint_search"]
        budget = float(settings.get("runtime_budget_minutes", 30.0))
        reserve = (float(settings.get("reserve_final_minutes", 5.0))
                   if reserve_final else 0.0)
        reserve += max(float(additional_reserve_minutes), 0.0)
        # Discovery, resonator backtracking, and bootstrap Rabi can legitimately be
        # slow.  Charging those stages against the joint optimizer used to leave a
        # passive-reset run with only a random fragment of its duration grid.  This
        # budget begins at the joint map itself.
        return self._joint_runtime_minutes() < max(budget - reserve, 0.0)

    @staticmethod
    def _joint_rank(row):
        mean, se, lcb = fidelity_evidence(row)
        return (lcb, mean, -se,
                -PulseCandidate.from_mapping(row).chain_latency_us())

    @staticmethod
    def _evidence_tier(row):
        """Cross-stage authority of one fidelity estimate.

        Shared-ground low-shot sweeps are excellent proposal generators, but their
        many correlated comparisons cannot outrank a fresh paired, multi-block
        replay merely because one of them observed a perfect finite sample.
        """
        try:
            explicit = int(row.get("evidence_tier"))
        except (AttributeError, TypeError, ValueError, OverflowError):
            explicit = None
        if explicit is not None:
            return int(np.clip(explicit, 0, 3))
        if not isinstance(row, dict):
            return 0
        state_order = str(row.get("state_order", "")).lower()
        level = str(row.get("evidence_level", "")).lower()
        if "shared-ground" in state_order or "shared_ground" in level:
            return 0
        blocks = int(row.get(
            "completed_confirmation_blocks",
            row.get("confirmation_blocks", 0)) or 0)
        if (bool(row.get("confirmation_complete", False))
                and bool(row.get("confirmation_batch_complete", True))
                and blocks >= 2):
            return 3
        if blocks >= 2:
            return 2
        if state_order in ("ge", "eg") or level == "paired_single_shot":
            return 1
        return 0

    @classmethod
    def _authoritative_rank(cls, row):
        return (cls._evidence_tier(row),) + tuple(cls._joint_rank(row))

    def _joint_anchor_probe(self, candidate, shots, label, previous=None):
        row = self._measure_candidate(candidate, int(shots), label)
        if previous is None:
            return row, False
        before = fidelity_evidence(previous)[0]
        after = fidelity_evidence(row)[0]
        limit = float(self.params["calibration_drift"].get(
            "max_independent_fidelity_change", 0.08))
        return row, bool(np.isfinite(before) and np.isfinite(after)
                         and abs(after - before) > limit)

    def _acquire_sequence(self, candidate, sequence_ops, shots, seq_gap_us=None):
        """Acquire raw shots for an arbitrary g-e/e-f shelving sequence."""
        extra = {
            "drive_freq": float(candidate["qubit_pi_freq"]),
            "sequence_ops": list(sequence_ops),
            "shots": int(shots), "reps": int(shots),
            "leakage_reference_sigma_us": max(
                float(self.params["leakage"]["reference_sigma_us"]),
                float(candidate["sigma"])),
        }
        if seq_gap_us is not None:
            extra["seq_gap_us"] = float(seq_gap_us)
        cfg = self._cfg_for(candidate, **extra)
        program = BasicSequenceProgram(self.soccfg, cfg)
        program.acquire(self.soc, load_pulses=True, progress=False)
        shot_i, shot_q = _shots_from_program(program, cfg)
        self._record_raw_diagnostic(
            "sequence", candidate, {"shot_i": shot_i, "shot_q": shot_q},
            {"sequence_ops": list(sequence_ops), "shots": int(shots),
             "seq_gap_us": seq_gap_us})
        return shot_i, shot_q

    def _acquire_parity_chevron(self, freqs_mhz, gains, candidate, shots,
                                pulse_counts, calibration):
        """Return a joint odd/even parity score, using a fixed fresh discriminator."""
        freqs, gains = np.asarray(freqs_mhz, float), np.asarray(gains, int)
        if gains.size < 2 or not np.all(np.diff(gains) == np.diff(gains)[0]):
            raise ValueError("parity chevron requires an equally spaced gain axis")
        populations = np.full((len(pulse_counts), freqs.size, gains.size), np.nan)
        if self._fast_gain_sweep is not True:
            jobs = [(ci, fi, gi) for ci in range(len(pulse_counts))
                    for fi in range(freqs.size) for gi in range(gains.size)]
            for job_index in self.rng.permutation(len(jobs)):
                ci, fi, gi = jobs[int(job_index)]
                cfg = self._cfg_for(
                    candidate, drive_freq=float(freqs[fi]),
                    sequence_gain=int(gains[gi]),
                    sequence_phases_deg=[0.0] * int(pulse_counts[ci]),
                    shots=int(shots), reps=int(shots),
                )
                program = BasicSequenceProgram(self.soccfg, cfg)
                program.acquire(self.soc, load_pulses=True, progress=False)
                shot_i, shot_q = _shots_from_program(program, cfg)
                exact = _with_candidate(
                    candidate, qubit_pi_freq=float(freqs[fi]),
                    qubit_pi_gain=int(gains[gi]))
                self._record_raw_diagnostic(
                    "parity_chevron_point", exact,
                    {"shot_i": shot_i, "shot_q": shot_q},
                    {"pulse_count": int(pulse_counts[ci]),
                     "shots": int(shots)})
                populations[ci, fi, gi] = float(np.mean(
                    discriminate_with_metrics(shot_i, shot_q, calibration)))
            targets = np.asarray(
                [1.0 if int(n) % 2 else 0.0 for n in pulse_counts])
            correctness = np.where(targets[:, None, None] > 0.5,
                                   populations, 1.0 - populations)
            return np.mean(correctness, axis=0), populations

        jobs = [(count_index, freq_index)
                for count_index in range(len(pulse_counts))
                for freq_index in range(freqs.size)]
        for job_number, job_index in enumerate(self.rng.permutation(len(jobs))):
            count_index, freq_index = jobs[int(job_index)]
            count, freq = pulse_counts[count_index], freqs[freq_index]
            run_gains = gains if job_number % 2 == 0 else gains[::-1]
            cfg = self._cfg_for(
                candidate, rabi_drive_freq=float(freq), n_pulses=int(count),
                amp_start=int(run_gains[0]),
                amp_step=int(np.diff(run_gains)[0]),
                amp_expts=int(gains.size), shots=int(shots), reps=int(shots),
                ff_hold_gain=0,
            )
            program = RabiSSProgram(self.soccfg, cfg)
            shot_i, shot_q = program.acquire(
                self.soc, load_pulses=True, progress=False)
            shot_i, shot_q = np.asarray(shot_i), np.asarray(shot_q)
            exact = _with_candidate(candidate, qubit_pi_freq=float(freq))
            self._record_raw_diagnostic(
                "parity_chevron_gain_line", exact,
                {"shot_i": shot_i, "shot_q": shot_q},
                {"pulse_count": int(count), "gains_dac": run_gains,
                 "shots": int(shots)})
            row = np.empty(gains.size, dtype=float)
            for gain_index in range(gains.size):
                row[gain_index] = float(
                    np.mean(discriminate_with_metrics(
                        shot_i[gain_index], shot_q[gain_index], calibration)))
            populations[count_index, freq_index] = (
                row if job_number % 2 == 0 else row[::-1])
        targets = np.asarray([1.0 if int(n) % 2 else 0.0 for n in pulse_counts])
        correctness = np.where(targets[:, None, None] > 0.5,
                               populations, 1.0 - populations)
        return np.mean(correctness, axis=0), populations

    def _acquire_inverse_pair_scan(self, freqs_mhz, candidate, shots, pairs,
                                   calibration):
        freqs = np.asarray(freqs_mhz, dtype=float)
        populations = np.full(freqs.size, np.nan)
        phases = [phase for _ in range(int(pairs)) for phase in (0.0, 180.0)]
        for index in self.rng.permutation(freqs.size):
            cfg = self._cfg_for(
                candidate, drive_freq=float(freqs[index]),
                sequence_gain=int(candidate["qubit_pi_gain"]),
                sequence_phases_deg=phases, shots=int(shots), reps=int(shots),
            )
            program = BasicSequenceProgram(self.soccfg, cfg)
            program.acquire(self.soc, load_pulses=True, progress=False)
            shot_i, shot_q = _shots_from_program(program, cfg)
            exact = _with_candidate(
                candidate, qubit_pi_freq=float(freqs[index]))
            self._record_raw_diagnostic(
                "inverse_pair_scan", exact,
                {"shot_i": shot_i, "shot_q": shot_q},
                {"pair_count": int(pairs), "shots": int(shots),
                 "phases_deg": phases})
            populations[index] = float(np.mean(
                discriminate_with_metrics(shot_i, shot_q, calibration)))
        return populations

    # ----------------------------------------------------------- direct SS objective
    def _measure_candidate(self, candidate, shots, label, state_order="ge",
                           archive=True, reference_discriminator=None):
        ig, qg, ie, qe = self._acquire_ss_pair(
            dict(candidate), int(shots), state_order=state_order)
        self._record_raw_diagnostic(
            "single_shot_pair", candidate,
            {"ground_i": ig, "ground_q": qg,
             "excited_i": ie, "excited_q": qe},
            {"label": str(label), "shots": int(shots),
             "state_order": str(state_order),
             "analyze_multimodality": bool(self._analyze_multimodality)})
        metrics = step5_metrics(
            ig, qg, ie, qe,
            analyze_multimodality=bool(self._analyze_multimodality))
        row = dict(candidate)
        row.update({key: value for key, value in metrics.items()
                    if key != "confusion"})
        row["confusion"] = np.asarray(metrics["confusion"])
        if reference_discriminator is not None:
            ground_state = discriminate_with_metrics(
                ig, qg, reference_discriminator)
            excited_state = discriminate_with_metrics(
                ie, qe, reference_discriminator)
            p_e_given_g = float(np.mean(ground_state > 0))
            p_g_given_e = float(np.mean(excited_state < 1))
            row.update({
                "reference_fidelity": float(
                    1.0 - 0.5 * (p_e_given_g + p_g_given_e)),
                "reference_p_e_given_g": p_e_given_g,
                "reference_p_g_given_e": p_g_given_e,
            })
        row["label"] = str(label)
        row["state_order"] = str(state_order)
        row["evidence_level"] = "paired_single_shot"
        row["evidence_tier"] = 1
        row["measurement_index"] = len(self._archive)
        row["pulse_signature"] = self._pulse_signature(candidate)
        if archive:
            self._archive.append(row)
        return row

    @staticmethod
    def _aggregate(candidate, measurements, label):
        if not measurements:
            raise ValueError("cannot aggregate zero measurements")
        fids = np.asarray([row["fidelity"] for row in measurements], dtype=float)
        shot_ses = np.asarray([row["fidelity_se"] for row in measurements], dtype=float)
        mean = float(np.mean(fids))
        if fids.size > 1:
            between = float(np.std(fids, ddof=1) / np.sqrt(fids.size))
        else:
            between = 0.0
        within = float(np.sqrt(np.sum(shot_ses ** 2)) / fids.size)
        se = float(max(between, within))
        out = dict(candidate)
        out.update({
            "fidelity": mean, "fidelity_se": se,
            "fidelity_lcb_95": float(mean - 1.96 * se),
            "evidence_level": "multi_block_replay",
            "evidence_tier": 2,
            "confirmation_blocks": int(fids.size),
            "block_fidelities": fids,
            "block_fidelity_ses": shot_ses,
            "block_spread": float(np.ptp(fids)) if fids.size else np.inf,
            "label": str(label),
            "measurement_indices": [int(row["measurement_index"])
                                    for row in measurements],
            "sep_sigma": float(np.mean([row["sep_sigma"] for row in measurements])),
            # Multiple blocks are a family of fresh anomaly checks.  Preserve the
            # worst upper bound so a transient third cloud cannot be averaged away.
            "third_blob_excess_ucb": float(max(
                row.get("third_blob_excess_ucb_95", np.inf)
                for row in measurements)),
            "ground_outlier_ucb_95": float(max(
                row.get("ground_outlier_ucb_95", np.inf)
                for row in measurements)),
            "excited_outlier_ucb_95": float(max(
                row.get("excited_outlier_ucb_95", np.inf)
                for row in measurements)),
        })
        cluster_available = bool(all(
            row.get("third_cluster_guard_available", False)
            for row in measurements))
        supported_clusters = [
            row for row in measurements
            if row.get("third_cluster_supported", False)]
        out.update({
            "third_cluster_guard_available": cluster_available,
            "third_cluster_supported": bool(supported_clusters),
            "third_cluster_detected": bool(any(
                row.get("third_cluster_detected", False)
                for row in measurements)),
            "third_cluster_fraction": float(max((
                row.get("third_cluster_fraction", 0.0)
                for row in supported_clusters), default=0.0)),
            "third_cluster_fraction_ucb_95": float(max((
                row.get("third_cluster_fraction_ucb_95", 0.0)
                for row in supported_clusters), default=0.0)),
            "third_cluster_single_state_fraction": float(max((
                row.get("third_cluster_single_state_fraction", 0.0)
                for row in supported_clusters), default=0.0)),
            "third_cluster_single_state_fraction_ucb_95": float(max((
                row.get("third_cluster_single_state_fraction_ucb_95", 0.0)
                for row in supported_clusters), default=0.0)),
            "third_cluster_bic_improvement": float(max((
                row.get("third_cluster_bic_improvement", -np.inf)
                for row in measurements), default=-np.inf)),
            "third_cluster_min_separation_sigma": float(min((
                row.get("third_cluster_min_separation_sigma", np.inf)
                for row in supported_clusters), default=np.inf)),
        })
        crossfit_fids = np.asarray([
            row.get("crossfit_fidelity", np.nan) for row in measurements],
            dtype=float)
        crossfit_shot_ses = np.asarray([
            row.get("crossfit_fidelity_se", np.nan) for row in measurements],
            dtype=float)
        if (crossfit_fids.size == fids.size
                and np.all(np.isfinite(crossfit_fids))
                and np.all(np.isfinite(crossfit_shot_ses))
                and np.all(crossfit_shot_ses >= 0.0)):
            crossfit_mean = float(np.mean(crossfit_fids))
            crossfit_between = (float(np.std(crossfit_fids, ddof=1)
                                      / np.sqrt(crossfit_fids.size))
                                if crossfit_fids.size > 1 else 0.0)
            crossfit_within = float(
                np.sqrt(np.sum(crossfit_shot_ses ** 2))
                / crossfit_fids.size)
            crossfit_se = float(max(crossfit_between, crossfit_within))
            out.update({
                "crossfit_fidelity": crossfit_mean,
                "crossfit_fidelity_se": crossfit_se,
                "crossfit_fidelity_lcb_95": float(
                    crossfit_mean - 1.96 * crossfit_se),
                "block_crossfit_fidelities": crossfit_fids,
                "block_crossfit_fidelity_ses": crossfit_shot_ses,
                "crossfit_block_spread": float(np.ptp(crossfit_fids)),
                "fidelity_estimator_for_latency": "two_fold_crossfit",
            })
        return out

    def _confirm_candidates(self, candidates, shots, blocks, label,
                            add_to_history=True):
        candidates = _unique_candidates(candidates)
        if not candidates:
            raise ValueError("cannot confirm an empty candidate list")
        requested_blocks = max(int(blocks), 1)
        buckets = [[] for _ in candidates]
        pairing_buckets = [[] for _ in candidates]
        failures = []
        self._confirmation_cohort_serial += 1
        cohort = "%s::%d" % (str(label), self._confirmation_cohort_serial)
        # Round-robin, randomized candidate order prevents one candidate from owning a
        # uniquely favorable drift window.  GE/EG order alternates between blocks.  A
        # transient failure is isolated to that candidate/block: successful contenders
        # remain available to this stage and to the final replay.
        for block in range(requested_blocks):
            for index in self.rng.permutation(len(candidates)):
                try:
                    row = self._measure_candidate(
                        candidates[index], shots,
                        "%s block %d" % (label, block + 1),
                        state_order="ge" if block % 2 == 0 else "eg")
                    buckets[index].append(row)
                    pairing_buckets[index].append(
                        "%s::block-%d" % (cohort, block + 1))
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    failure = {
                        "label": str(label), "candidate_index": int(index),
                        "block": int(block + 1),
                        "error": "%s: %s" % (type(exc).__name__, exc),
                    }
                    failures.append(failure)
                    self.data["confirmation_failures"].append(failure)
        batch_complete = bool(
            not failures and all(len(rows) == requested_blocks for rows in buckets))
        aggregates = []
        for candidate, rows, pairing_ids in zip(
                candidates, buckets, pairing_buckets):
            key = _candidate_key(candidate)
            existing = next((entry for entry in self._unconfirmed_contenders
                             if _candidate_key(entry["candidate"]) == key), None)
            if not batch_complete:
                entry = {
                    "candidate": {name: candidate[name] for name in self.initial},
                    "missing_blocks": int(requested_blocks - len(rows)),
                    "completed_blocks": int(len(rows)),
                    "scheduled_blocks": int(requested_blocks),
                    "batch_incomplete": True,
                    "label": str(label),
                    "order": int(len(self.data["confirmation_failures"])),
                }
                if existing is None:
                    self._unconfirmed_contenders.append(entry)
                elif entry["missing_blocks"] >= existing["missing_blocks"]:
                    existing.update(entry)
            elif existing is not None:
                self._unconfirmed_contenders.remove(existing)
            if not rows:
                continue
            aggregate = self._aggregate(candidate, rows, label)
            aggregate.update({
                "scheduled_confirmation_blocks": requested_blocks,
                "completed_confirmation_blocks": len(rows),
                "missing_confirmation_blocks": requested_blocks - len(rows),
                "confirmation_complete": bool(len(rows) == requested_blocks),
                "confirmation_batch_complete": batch_complete,
                "confirmation_failure_count": len(failures),
                # These opaque ids are equal only for candidates acquired in the
                # same randomized round-robin block.  Sequential frontier batches
                # can therefore be pooled without falsely pairing unrelated drift
                # windows merely because both happen to contain eight blocks.
                "block_pairing_ids": list(pairing_ids),
                "evidence_level": (
                    "held_out_complete_multi_block" if batch_complete else
                    "incomplete_multi_block"),
                "evidence_tier": 3 if (
                    batch_complete and len(rows) >= 2) else 2,
            })
            aggregates.append(aggregate)
        limit = max(int(self.params["final"].get(
            "max_unconfirmed_contenders", 16)), 1)
        # Fully failed tuples sort ahead of partially measured ones.  Preserve earlier
        # discovery order within a priority class so a later storm of backend faults
        # cannot continually evict the first unresolved spectral basins.
        self._unconfirmed_contenders[:] = sorted(
            self._unconfirmed_contenders,
            key=lambda entry: (-int(entry["missing_blocks"]), int(entry["order"])),
        )[:limit]
        if failures:
            self._log(
                "confirmation", "WARN",
                "%s retained %d/%d successful candidate-block measurements; "
                "the batch remains usable for best-effort reporting but is not "
                "calibration evidence"
                % (label, sum(len(rows) for rows in buckets),
                   len(candidates) * requested_blocks))
        if not aggregates:
            raise RuntimeError("%s completed no confirmation measurements" % label)
        if add_to_history:
            self._confirmed.extend(aggregates)
        return aggregates

    @staticmethod
    def _confirmation_batch_complete(aggregates):
        return bool(aggregates and all(
            row.get("confirmation_batch_complete", False) for row in aggregates))

    @staticmethod
    def _best_aggregate(rows):
        if not rows:
            return None
        return max(rows, key=lambda row: (
            float(row.get("fidelity_lcb_95", -np.inf)),
            float(row.get("fidelity", -np.inf)),
            -float(row.get("read_length", np.inf)),
        ))

    @staticmethod
    def _latency_fidelity_evidence(row):
        """Return the held-out fidelity evidence used only for timing decisions.

        New hardware rows carry a two-fold cross-fit estimate which removes the
        candidate-dependent optimism from fitting the IQ discriminator on its scoring
        shots.  Legacy/synthetic rows fall back to their ordinary fidelity fields so
        saved data and deterministic unit tests remain readable.
        """
        if not isinstance(row, dict):
            row = {}
        try:
            use_crossfit = bool(
                np.isfinite(float(row.get("crossfit_fidelity", np.nan)))
                and np.isfinite(float(row.get(
                    "crossfit_fidelity_se", np.nan))))
        except (TypeError, ValueError, OverflowError):
            use_crossfit = False
        prefix = "crossfit_" if use_crossfit else ""
        block_prefix = "block_crossfit_" if use_crossfit else "block_"
        try:
            block_fidelities = np.asarray(row.get(
                block_prefix + "fidelities", []), dtype=float)
            block_fidelity_ses = np.asarray(row.get(
                block_prefix + "fidelity_ses", []), dtype=float)
        except (TypeError, ValueError, OverflowError):
            block_fidelities = np.asarray([], dtype=float)
            block_fidelity_ses = np.asarray([], dtype=float)
        raw_pairing_ids = row.get("block_pairing_ids", [])
        block_pairing_ids = (
            tuple(str(value) for value in raw_pairing_ids)
            if isinstance(raw_pairing_ids, (list, tuple, np.ndarray)) else ())
        def numeric(name, default):
            try:
                return float(row.get(prefix + name, default))
            except (TypeError, ValueError, OverflowError):
                return float(default)
        return {
            "fidelity": numeric("fidelity", np.nan),
            "fidelity_se": numeric("fidelity_se", np.inf),
            "fidelity_lcb_95": numeric("fidelity_lcb_95", np.nan),
            "block_fidelities": block_fidelities,
            "block_fidelity_ses": block_fidelity_ses,
            "block_pairing_ids": block_pairing_ids,
            "estimator": ("two_fold_crossfit" if use_crossfit
                          else "legacy_resubstitution"),
        }

    @staticmethod
    def _candidate_latency_us(candidate):
        """Physical X180-plus-readout latency used by the secondary objective.

        Saved hardware rows may carry ``readout_drive_length_us`` (integration plus
        ADC offset/guard, and any explicit longer generator request).  Synthetic and
        legacy rows fall back to the requested integration length.  The Gaussian
        control envelope is exactly four sigma on this canonical pulse path.
        """
        try:
            sigma = float(candidate["sigma"])
            readout = float(candidate.get(
                "readout_drive_length_us", candidate["read_length"]))
        except (KeyError, TypeError, ValueError, OverflowError):
            return np.inf
        if (not np.all(np.isfinite([sigma, readout]))
                or sigma <= 0.0 or readout <= 0.0):
            return np.inf
        return float(readout + 4.0 * sigma)

    @staticmethod
    def _latency_noninferiority(reference, candidate, max_loss,
                                confidence_z=1.96):
        """Conservative upper bound on fidelity sacrificed by ``candidate``.

        When both rows expose per-block shot uncertainties, the randomized
        round-robin blocks are paired to remove common drift.  Otherwise the method
        falls back to the independent aggregate uncertainties.  In both cases a wide
        error bar makes qualification *harder*, never easier.
        """
        result = {
            "eligible": False, "reason": None, "mean_loss": np.inf,
            "loss_se": np.inf, "loss_ucb": np.inf,
            "confidence_z": float(confidence_z), "method": "invalid",
        }
        if not np.isfinite(BasicAutoTuner._candidate_latency_us(candidate)):
            result["reason"] = "invalid latency coordinates"
            return result
        try:
            ref_evidence = BasicAutoTuner._latency_fidelity_evidence(reference)
            candidate_evidence = BasicAutoTuner._latency_fidelity_evidence(
                candidate)
            ref_mean = float(ref_evidence["fidelity"])
            candidate_mean = float(candidate_evidence["fidelity"])
            ref_se = float(ref_evidence["fidelity_se"])
            candidate_se = float(candidate_evidence["fidelity_se"])
            loss_limit = float(max_loss)
            z = float(confidence_z)
        except (KeyError, TypeError, ValueError, OverflowError):
            result["reason"] = "missing fidelity evidence"
            return result
        if (not np.all(np.isfinite(
                [ref_mean, candidate_mean, ref_se, candidate_se, loss_limit, z]))
                or ref_se < 0.0 or candidate_se < 0.0
                or loss_limit < 0.0 or z < 0.0):
            result["reason"] = "invalid fidelity evidence"
            return result

        try:
            same_tuple = _candidate_key(reference) == _candidate_key(candidate)
        except Exception:
            same_tuple = False
        mean_loss = float(ref_mean - candidate_mean)
        if same_tuple:
            loss_se = 0.0
            method = "reference_identity"
        else:
            ref_blocks = ref_evidence["block_fidelities"]
            candidate_blocks = candidate_evidence["block_fidelities"]
            ref_block_ses = ref_evidence["block_fidelity_ses"]
            candidate_block_ses = candidate_evidence["block_fidelity_ses"]
            ref_ids = tuple(ref_evidence.get("block_pairing_ids", ()))
            candidate_ids = tuple(candidate_evidence.get(
                "block_pairing_ids", ()))
            ids_present = bool(ref_ids or candidate_ids)
            paired = False
            if (ids_present and len(ref_ids) == ref_blocks.size
                    and len(candidate_ids) == candidate_blocks.size
                    and len(set(ref_ids)) == len(ref_ids)
                    and len(set(candidate_ids)) == len(candidate_ids)):
                ref_index = {value: index for index, value in enumerate(ref_ids)}
                candidate_index = {
                    value: index for index, value in enumerate(candidate_ids)}
                shared = [value for value in ref_ids if value in candidate_index]
                if len(shared) >= 2:
                    ref_positions = [ref_index[value] for value in shared]
                    candidate_positions = [candidate_index[value]
                                           for value in shared]
                    ref_blocks = ref_blocks[ref_positions]
                    candidate_blocks = candidate_blocks[candidate_positions]
                    ref_block_ses = ref_block_ses[ref_positions]
                    candidate_block_ses = candidate_block_ses[candidate_positions]
                    paired = True
            elif not ids_present:
                # Backward-compatible path for saved/synthetic rows predating
                # explicit acquisition-cohort ids.
                paired = bool(ref_blocks.size == candidate_blocks.size)
            paired = bool(
                paired
                and ref_blocks.ndim == candidate_blocks.ndim == 1
                and ref_block_ses.ndim == candidate_block_ses.ndim == 1
                and ref_blocks.size >= 2
                and ref_blocks.size == candidate_blocks.size
                and ref_blocks.size == ref_block_ses.size
                and ref_blocks.size == candidate_block_ses.size
                and np.all(np.isfinite(np.r_[
                    ref_blocks, candidate_blocks,
                    ref_block_ses, candidate_block_ses]))
                and np.all(ref_block_ses >= 0.0)
                and np.all(candidate_block_ses >= 0.0))
            if paired:
                differences = ref_blocks - candidate_blocks
                between = float(
                    np.std(differences, ddof=1) / math.sqrt(differences.size))
                # Propagate the uncertainty of the *mean* paired loss.  Variances
                # add across independent blocks and division by B happens after the
                # square root: sqrt(sum(var_i)) / B.  Dividing the summed variance by
                # B before the root would return a typical single-block error bar and
                # make even equal-fidelity candidates practically impossible to
                # certify.
                within = float(math.sqrt(np.sum(
                    ref_block_ses ** 2 + candidate_block_ses ** 2))
                    / differences.size)
                loss_se = float(max(between, within))
                mean_loss = float(np.mean(differences))
                method = "paired_round_robin_blocks"
            else:
                loss_se = float(math.hypot(ref_se, candidate_se))
                method = "independent_aggregate"
        loss_ucb = float(mean_loss + z * loss_se)
        eligible = bool(np.isfinite(loss_ucb) and loss_ucb <= loss_limit)
        result.update({
            "eligible": eligible, "mean_loss": mean_loss,
            "loss_se": loss_se, "loss_ucb": loss_ucb, "method": method,
            "fidelity_estimator": candidate_evidence["estimator"],
            "reason": ("fidelity-loss upper bound is within budget" if eligible
                       else "fidelity-loss upper bound exceeds budget"),
        })
        return result

    @staticmethod
    def _select_latency_constrained(rows, reference, settings):
        """Shortest complete candidate which proves fidelity noninferiority.

        This is intentionally lexicographic: hard fidelity/statistical constraints
        first, latency second.  No weighted fidelity/time score can trade a large
        fidelity collapse for an impressive-looking short duration.
        """
        settings = dict(settings or {})
        max_loss = float(settings.get("max_fidelity_loss", 0.010))
        minimum_mean = float(settings.get("minimum_mean_fidelity", 0.90))
        minimum_lcb = float(settings.get("minimum_lcb_fidelity", 0.88))
        confidence_z = float(settings.get("confidence_sigma", 1.96))
        required_blocks = max(int(settings.get("required_blocks", 0)), 0)
        maximum_spread = float(settings.get("max_block_spread", np.inf))
        simultaneous_references = settings.get("simultaneous_reference_rows")
        if not isinstance(simultaneous_references, (list, tuple)):
            simultaneous_references = [reference]
        diagnostics, eligible = [], []
        for row in rows:
            latency = BasicAutoTuner._candidate_latency_us(row)
            pairwise = []
            for comparison_reference in simultaneous_references:
                comparison = BasicAutoTuner._latency_noninferiority(
                    comparison_reference, row, max_loss=max_loss,
                    confidence_z=confidence_z)
                comparison["reference_key"] = (
                    list(_candidate_key(comparison_reference))
                    if np.isfinite(BasicAutoTuner._candidate_latency_us(
                        comparison_reference)) else None)
                pairwise.append(comparison)
            result = (max(pairwise, key=lambda item: float(
                item.get("loss_ucb", np.inf))) if pairwise else {
                    "eligible": False, "reason": "no fidelity references",
                    "mean_loss": np.inf, "loss_se": np.inf,
                    "loss_ucb": np.inf, "confidence_z": confidence_z,
                    "method": "invalid", "reference_key": None,
                })
            # Simultaneous intervals cover every possible higher-fidelity arm.  A
            # candidate is within epsilon of the unknown best only when *all* those
            # pairwise upper bounds pass; comparing solely with the observed winner
            # can accept an under-sampled arm that may actually be better.
            result = dict(result)
            result["eligible"] = bool(
                pairwise and all(item.get("eligible", False) for item in pairwise))
            result["reason"] = (
                "all simultaneous fidelity-loss bounds are within budget"
                if result["eligible"] else
                "at least one simultaneous fidelity-loss bound exceeds budget")
            result["worst_case_reference_key"] = result.pop(
                "reference_key", None)
            result["pairwise_loss_bounds"] = [{
                "reference_key": item.get("reference_key"),
                "mean_loss": item.get("mean_loss"),
                "loss_se": item.get("loss_se"),
                "loss_ucb": item.get("loss_ucb"),
                "method": item.get("method"),
                "eligible": item.get("eligible"),
            } for item in pairwise]
            reasons = [] if result["eligible"] else [result["reason"]]
            try:
                evidence = BasicAutoTuner._latency_fidelity_evidence(row)
                mean = float(evidence["fidelity"])
                lcb = float(evidence["fidelity_lcb_95"])
                simultaneous_lcb = float(mean - confidence_z * float(
                    evidence["fidelity_se"]))
                blocks = int(row.get("confirmation_blocks", 0))
                spread = float(row.get(
                    "crossfit_block_spread",
                    row.get("block_spread", np.inf)))
            except (TypeError, ValueError, OverflowError):
                mean, lcb, simultaneous_lcb = np.nan, np.nan, np.nan
                blocks, spread = 0, np.inf
            if not np.isfinite(latency):
                reasons.append("invalid latency coordinates")
            if not np.isfinite(mean) or mean < minimum_mean:
                reasons.append("mean fidelity is below the absolute floor")
            if (not np.isfinite(simultaneous_lcb)
                    or simultaneous_lcb < minimum_lcb):
                reasons.append(
                    "simultaneous fidelity lower bound is below the absolute floor")
            if required_blocks and blocks < required_blocks:
                reasons.append("confirmation block count is incomplete")
            if not np.isfinite(spread) or spread > maximum_spread:
                reasons.append("confirmation block spread is unstable")
            if row.get("confirmation_batch_complete") is False:
                reasons.append("confirmation batch is incomplete")
            accepted = not reasons
            diagnostic = dict(result)
            diagnostic.update({
                "candidate_key": (list(_candidate_key(row))
                                  if np.isfinite(latency) else None),
                "latency_us": latency,
                "integration_chain_us": (
                    float(row.get("read_length", np.inf))
                    + 4.0 * float(row.get("sigma", np.inf))
                    if np.isfinite(latency) else np.inf),
                "fidelity": mean, "fidelity_lcb_95": lcb,
                "fidelity_lcb_simultaneous": simultaneous_lcb,
                "step5_resubstitution_fidelity": float(
                    row.get("fidelity", np.nan)),
                "fidelity_estimator": evidence.get("estimator"),
                "accepted": bool(accepted),
                "reason": "; ".join(dict.fromkeys(reasons))
                if reasons else "qualified",
            })
            diagnostics.append(diagnostic)
            if accepted:
                eligible.append(row)
        if not eligible:
            return reference, diagnostics

        def deterministic_key(row):
            try:
                identity = _candidate_key(row)
            except Exception:
                identity = (np.inf,) * 7
            evidence = BasicAutoTuner._latency_fidelity_evidence(row)
            return (
                BasicAutoTuner._candidate_latency_us(row),
                float(row.get("third_blob_excess_ucb", np.inf)),
                float(row.get("read_pulse_gain", np.inf)) ** 2
                * float(row.get("read_length", np.inf)),
                -float(evidence.get("fidelity_lcb_95", -np.inf)),
                -float(evidence.get("fidelity", -np.inf)),
                identity,
            )

        return min(eligible, key=deterministic_key), diagnostics

    @staticmethod
    def _latency_frontier_candidates(rows, max_per_read_length=1,
                                     max_per_sigma=1, limit=8,
                                     nondominated=True,
                                     uncertainty_sigma=3.0):
        """Preserve the measured latency/fidelity frontier before fresh replay.

        Fidelity-only top-K truncation loses every fast basin when several variants
        of one slow tuple score slightly higher.  This helper retains the best row per
        timing coordinate and then the nondominated latency/fidelity frontier.
        """
        valid_by_key = {}
        for row in rows:
            if not np.isfinite(BasicAutoTuner._candidate_latency_us(row)):
                continue
            try:
                key = _candidate_key(row)
                timing = BasicAutoTuner._latency_fidelity_evidence(row)
                evidence = (
                    float(timing.get("fidelity_lcb_95", -np.inf)),
                    float(timing.get("fidelity", -np.inf)),
                    -float(timing.get("fidelity_se", np.inf)),
                )
            except Exception:
                continue
            incumbent = valid_by_key.get(key)
            if incumbent is None:
                valid_by_key[key] = row
            else:
                old_timing = BasicAutoTuner._latency_fidelity_evidence(incumbent)
                old = (
                    float(old_timing.get("fidelity_lcb_95", -np.inf)),
                    float(old_timing.get("fidelity", -np.inf)),
                    -float(old_timing.get("fidelity_se", np.inf)),
                )
                if evidence > old:
                    valid_by_key[key] = row
        unique = list(valid_by_key.values())
        if not unique:
            return []

        def evidence_key(row):
            timing = BasicAutoTuner._latency_fidelity_evidence(row)
            return (
                float(timing.get("fidelity_lcb_95", -np.inf)),
                float(timing.get("fidelity", -np.inf)),
                -float(timing.get("fidelity_se", np.inf)),
                tuple(-value if isinstance(value, (int, float)) else value
                      for value in _candidate_key(row)),
            )

        if not nondominated:
            # Keep every control whose coarse uncertainty interval overlaps the best
            # interval at the same readout length, and symmetrically every readout
            # tied at the same pulse duration.  Marginal top-1 pruning can omit the
            # true shortest *joint* corner (for example 8 us/.10 when 8 us/.25 and
            # 20 us/.10 happen to win their separate noisy marginals).
            z = max(float(uncertainty_sigma), 0.0)
            retained = {}
            for coordinate in ("read_length", "sigma"):
                groups = {}
                for row in unique:
                    groups.setdefault(
                        round(float(row[coordinate]), 9), []).append(row)
                for group in groups.values():
                    intervals = []
                    for row in group:
                        timing = BasicAutoTuner._latency_fidelity_evidence(row)
                        mean = float(timing.get("fidelity", -np.inf))
                        se = float(timing.get("fidelity_se", np.inf))
                        if not np.all(np.isfinite([mean, se])) or se < 0.0:
                            continue
                        intervals.append((row, mean - z * se, mean + z * se))
                    if not intervals:
                        continue
                    best_lcb = max(item[1] for item in intervals)
                    for row, _lcb, ucb in intervals:
                        if ucb >= best_lcb - 1e-12:
                            retained[_candidate_key(row)] = row
            best = max(unique, key=evidence_key)
            fastest = min(unique, key=lambda row: (
                BasicAutoTuner._candidate_latency_us(row),
                -float(BasicAutoTuner._latency_fidelity_evidence(row).get(
                    "fidelity_lcb_95", -np.inf)),
                _candidate_key(row)))
            retained[_candidate_key(best)] = best
            retained[_candidate_key(fastest)] = fastest
            ordered = sorted(retained.values(), key=lambda row: (
                BasicAutoTuner._candidate_latency_us(row),
                -float(BasicAutoTuner._latency_fidelity_evidence(row).get(
                    "fidelity_lcb_95", -np.inf)),
                _candidate_key(row)))
            limit = max(int(limit), 1)
            return [dict(row) for row in ordered[:limit]]

        retained = {}
        for coordinate, count in (("read_length", max_per_read_length),
                                  ("sigma", max_per_sigma)):
            groups = {}
            for row in unique:
                groups.setdefault(round(float(row[coordinate]), 9), []).append(row)
            for group in groups.values():
                ranked = sorted(group, key=evidence_key, reverse=True)
                for row in ranked[:max(int(count), 1)]:
                    retained[_candidate_key(row)] = row
        best = max(unique, key=evidence_key)
        fastest = min(unique, key=lambda row: (
            BasicAutoTuner._candidate_latency_us(row),
            -float(BasicAutoTuner._latency_fidelity_evidence(row).get(
                "fidelity_lcb_95", -np.inf)),
            _candidate_key(row)))
        retained[_candidate_key(best)] = best
        retained[_candidate_key(fastest)] = fastest

        ordered = sorted(retained.values(), key=lambda row: (
            BasicAutoTuner._candidate_latency_us(row),
            -float(BasicAutoTuner._latency_fidelity_evidence(row).get(
                "fidelity_lcb_95", -np.inf)),
            _candidate_key(row)))
        frontier, best_lcb_so_far = [], -np.inf
        for row in ordered:
            lcb = float(BasicAutoTuner._latency_fidelity_evidence(row).get(
                "fidelity_lcb_95", -np.inf))
            if not frontier or lcb > best_lcb_so_far + 1e-12:
                frontier.append(row)
                best_lcb_so_far = max(best_lcb_so_far, lcb)
        if not any(_candidate_key(row) == _candidate_key(best)
                   for row in frontier):
            frontier.append(best)
        frontier = sorted(_unique_candidates(frontier), key=lambda row: (
            BasicAutoTuner._candidate_latency_us(row),
            -float(BasicAutoTuner._latency_fidelity_evidence(row).get(
                "fidelity_lcb_95", -np.inf)),
            _candidate_key(row)))

        limit = max(int(limit), 1)
        if len(frontier) <= limit:
            return [dict(row) for row in frontier]
        if limit == 1:
            return [dict(best)]
        # The preceding uncertainty screen already removed obviously poor fast arms.
        # Densely retain the *earliest* surviving frontier points, because an evenly
        # spaced sample can skip the 8/10/12-us boundary and incorrectly call 14 us the
        # shortest acceptable readout.  Force the best-fidelity anchor as the final
        # slot so the epsilon comparison still uses the strongest observed basin.
        best_index = next(index for index, row in enumerate(frontier)
                          if _candidate_key(row) == _candidate_key(best))
        indices = set(range(min(limit - 1, len(frontier))))
        indices.add(best_index)
        for index in range(len(frontier)):
            if len(indices) >= limit:
                break
            indices.add(index)
        return [dict(frontier[index]) for index in sorted(indices)]

    def _annotate_candidate_latency(self, candidate):
        """Attach requested and hardware-realized latency to a saved candidate."""
        row = dict(candidate)
        try:
            cfg = copy.deepcopy(self.input_cfg)
            cfg.update({key: row[key] for key in self.initial})
            generator_length = float(readout_drive_length_us(cfg))
            requested = float(row["read_length"]) + 4.0 * float(row["sigma"])
            physical = generator_length + 4.0 * float(row["sigma"])
        except Exception:
            generator_length = requested = physical = np.inf
        row.update({
            "readout_drive_length_us": generator_length,
            "integration_chain_us": requested,
            "latency_us": physical,
            "latency_metric": "readout_generator_plus_4sigma_x180",
        })
        return row

    @staticmethod
    def _timing_component_subset(rows, coordinate, reference_value, limit):
        """One high-evidence representative per timing value, diversely bounded."""
        grouped = {}
        for row in rows:
            try:
                value = round(float(row[coordinate]), 9)
                timing = BasicAutoTuner._latency_fidelity_evidence(row)
                evidence = (
                    int(row.get("confirmation_blocks", 0)),
                    float(timing.get("fidelity_lcb_95", -np.inf)),
                    float(timing.get("fidelity", -np.inf)),
                    -float(timing.get("fidelity_se", np.inf)),
                )
                _candidate_key(row)
            except Exception:
                continue
            incumbent = grouped.get(value)
            if incumbent is None:
                grouped[value] = row
            else:
                old_timing = BasicAutoTuner._latency_fidelity_evidence(incumbent)
                old = (
                    int(incumbent.get("confirmation_blocks", 0)),
                    float(old_timing.get("fidelity_lcb_95", -np.inf)),
                    float(old_timing.get("fidelity", -np.inf)),
                    -float(old_timing.get("fidelity_se", np.inf)),
                )
                if evidence > old:
                    grouped[value] = row
        ordered = [grouped[value] for value in sorted(grouped)]
        limit = max(int(limit), 1)
        if len(ordered) <= limit:
            return ordered
        best = max(ordered, key=lambda row: (
            float(BasicAutoTuner._latency_fidelity_evidence(row).get(
                "fidelity_lcb_95", -np.inf)),
            float(BasicAutoTuner._latency_fidelity_evidence(row).get(
                "fidelity", -np.inf))))
        reference = min(ordered, key=lambda row: abs(
            float(row[coordinate]) - float(reference_value)))
        if limit == 1:
            return [best]
        if limit == 2:
            pair = [ordered[0], best]
            if pair[0] is pair[1]:
                pair[1] = reference if reference is not pair[0] else ordered[-1]
            return pair
        best_index = next(index for index, row in enumerate(ordered)
                          if row is best)
        reference_index = next(index for index, row in enumerate(ordered)
                               if row is reference)
        chosen = {0, best_index, reference_index}
        for index in np.rint(np.linspace(
                0, len(ordered) - 1, limit)).astype(int):
            chosen.add(int(index))
        while len(chosen) > limit:
            protected = {0, best_index, reference_index}
            removable = [index for index in sorted(chosen)
                         if index not in protected]
            if not removable:
                break
            chosen.remove(removable[len(removable) // 2])
        while len(chosen) < limit:
            missing = [index for index in range(len(ordered))
                       if index not in chosen]
            chosen.add(missing[0])
        return [ordered[index] for index in sorted(chosen)]

    def _latency_joint_candidate_pool(self, reference, control_rows=None):
        """Cross retuned timing representatives without reopening every coordinate."""
        p = self.params["latency"]
        reference_physical = {key: reference[key] for key in self.initial}
        rows = (list(self._confirmed) + list(self._archive)
                + list(self.data.get("final_candidates", [])) + [reference])
        readout_physical = []
        for row in rows:
            if not all(key in row for key in self.initial):
                continue
            try:
                read_length = float(row["read_length"])
            except Exception:
                continue
            if (not np.isfinite(read_length)
                    or not float(p["min_read_length_us"]) <= read_length
                    <= float(p["max_read_length_us"])):
                continue
            readout_physical.append(row)
        requested_controls = (rows if control_rows is None else
                              list(control_rows) + [reference])
        control_physical = []
        for row in requested_controls:
            if not all(key in row for key in self.initial):
                continue
            try:
                sigma = float(row["sigma"])
            except Exception:
                continue
            if (not np.isfinite(sigma)
                    or not float(p["min_sigma_us"]) <= sigma
                    <= float(p["max_sigma_us"])):
                continue
            control_physical.append(row)
        if not readout_physical or not control_physical:
            return [self._annotate_candidate_latency(reference_physical)]
        readout_rows = self._timing_component_subset(
            readout_physical, "read_length", reference["read_length"],
            p["max_readout_candidates"])
        selected_controls = self._timing_component_subset(
            control_physical, "sigma", reference["sigma"],
            p["max_control_candidates"])
        candidates = []
        for readout in readout_rows:
            for control in selected_controls:
                candidate = dict(reference_physical)
                for key in ("read_pulse_freq", "read_pulse_gain", "read_length"):
                    candidate[key] = readout[key]
                for key in ("qubit_freq", "qubit_pi_freq", "qubit_pi_gain",
                            "sigma", "qubit_drag_beta"):
                    candidate[key] = control[key]
                candidate["qubit_freq"] = float(candidate["qubit_pi_freq"])
                candidates.append(self._annotate_candidate_latency(candidate))
        candidates.append(self._annotate_candidate_latency(reference_physical))
        # Do not truncate at the seed's latency.  A slower cross-coordinate tuple may
        # establish a materially higher safe-fidelity reference; omitting it would
        # spend the epsilon budget relative to a degraded anchor.  The bounded
        # representative cross (rather than the full Cartesian search) controls cost.
        return _unique_candidates(candidates)

    def _latency_family_settings(self, comparisons, required_blocks=None):
        settings = copy.deepcopy(self.params["latency"])
        count = max(int(comparisons), 1)
        alpha = float(np.clip(
            settings.get("familywise_alpha", 0.05), 1e-9, 0.5))
        # One-sided Bonferroni bound: every fast contender must independently prove
        # that its loss is below epsilon.  Multiplicity is paid in the confidence
        # multiplier, not hidden in an optimistic winner selection.
        normal_quantile = float(NormalDist().inv_cdf(1.0 - alpha / count))
        degrees_of_freedom = (max(int(required_blocks) - 1, 1)
                              if required_blocks is not None else None)
        # The paired loss SE includes block-to-block drift estimated from a small
        # number of randomized rounds.  Treating that variance as known and applying a
        # normal quantile is anti-conservative (especially for the default eight
        # blocks), so use the finite-sample Student-t tail for every timing contrast.
        # This is conservative when known per-shot noise dominates and exact when the
        # between-block term controls the standard error.
        finite_sample_quantile = (
            float(student_t.ppf(1.0 - alpha / count,
                                degrees_of_freedom))
            if degrees_of_freedom is not None else normal_quantile)
        settings["confidence_sigma"] = float(max(
            float(settings.get("confidence_sigma", 1.96)),
            normal_quantile, finite_sample_quantile))
        settings["familywise_comparison_count"] = int(count)
        settings["familywise_distribution"] = (
            "student_t" if degrees_of_freedom is not None else "normal")
        settings["familywise_degrees_of_freedom"] = degrees_of_freedom
        if required_blocks is not None:
            settings["required_blocks"] = int(required_blocks)
        return settings

    @staticmethod
    def _combine_latency_confirmation_rounds(rounds, label):
        """Pool complete confirmation batches while preserving true drift pairing.

        Adaptive batches normally contain the same tuples, while sequential frontier
        promotion intentionally introduces new tuples.  Opaque per-block cohort ids
        let both cases share one combiner without pretending that unrelated blocks
        acquired at different times were paired.
        """
        if not rounds:
            return []
        expected = {
            _candidate_key(row) for batch in rounds for row in batch}
        if not expected:
            return []
        combined = []
        for key in sorted(expected):
            pieces = [row for batch in rounds for row in batch
                      if _candidate_key(row) == key]
            block_fidelities = np.concatenate([
                np.asarray(row.get("block_fidelities", []), dtype=float)
                for row in pieces])
            block_ses = np.concatenate([
                np.asarray(row.get("block_fidelity_ses", []), dtype=float)
                for row in pieces])
            if (block_fidelities.size < 1
                    or block_fidelities.size != block_ses.size
                    or not np.all(np.isfinite(np.r_[block_fidelities, block_ses]))
                    or np.any(block_ses < 0.0)):
                raise RuntimeError(
                    "adaptive latency batch has invalid per-block fidelity evidence")
            count = int(block_fidelities.size)
            between = (float(np.std(block_fidelities, ddof=1)
                             / math.sqrt(count)) if count > 1 else 0.0)
            within = float(math.sqrt(np.sum(block_ses ** 2)) / count)
            fidelity = float(np.mean(block_fidelities))
            row = dict(pieces[-1])
            row.update({
                "fidelity": fidelity,
                "fidelity_se": float(max(between, within)),
                "fidelity_lcb_95": float(
                    fidelity - 1.96 * max(between, within)),
                "confirmation_blocks": count,
                "block_fidelities": block_fidelities,
                "block_fidelity_ses": block_ses,
                "block_spread": float(np.ptp(block_fidelities)),
                "scheduled_confirmation_blocks": count,
                "completed_confirmation_blocks": count,
                "missing_confirmation_blocks": 0,
                "confirmation_complete": True,
                "confirmation_batch_complete": True,
                "confirmation_failure_count": 0,
                "label": str(label),
                "measurement_indices": [
                    int(index) for piece in pieces
                    for index in piece.get("measurement_indices", [])],
                "third_blob_excess_ucb": float(max(
                    piece.get("third_blob_excess_ucb", np.inf)
                    for piece in pieces)),
            })
            pairing_parts = [
                list(piece.get("block_pairing_ids", [])) for piece in pieces]
            if (all(len(values) for values in pairing_parts)
                    and sum(len(values) for values in pairing_parts) == count):
                pairing_ids = [value for values in pairing_parts for value in values]
                if len(set(pairing_ids)) != len(pairing_ids):
                    raise RuntimeError(
                        "latency batches reused an acquisition pairing id")
                row["block_pairing_ids"] = pairing_ids
            else:
                row.pop("block_pairing_ids", None)
            crossfit_blocks = [np.asarray(piece.get(
                "block_crossfit_fidelities", []), dtype=float)
                for piece in pieces]
            crossfit_ses = [np.asarray(piece.get(
                "block_crossfit_fidelity_ses", []), dtype=float)
                for piece in pieces]
            if (all(values.size for values in crossfit_blocks)
                    and all(values.size for values in crossfit_ses)):
                crossfit_blocks = np.concatenate(crossfit_blocks)
                crossfit_ses = np.concatenate(crossfit_ses)
                if (crossfit_blocks.size != count
                        or crossfit_ses.size != count
                        or not np.all(np.isfinite(np.r_[
                            crossfit_blocks, crossfit_ses]))
                        or np.any(crossfit_ses < 0.0)):
                    raise RuntimeError(
                        "adaptive latency batch has invalid cross-fit evidence")
                crossfit_between = (float(np.std(
                    crossfit_blocks, ddof=1) / math.sqrt(count))
                    if count > 1 else 0.0)
                crossfit_within = float(
                    math.sqrt(np.sum(crossfit_ses ** 2)) / count)
                crossfit_se = float(max(crossfit_between, crossfit_within))
                crossfit_fidelity = float(np.mean(crossfit_blocks))
                row.update({
                    "crossfit_fidelity": crossfit_fidelity,
                    "crossfit_fidelity_se": crossfit_se,
                    "crossfit_fidelity_lcb_95": float(
                        crossfit_fidelity - 1.96 * crossfit_se),
                    "block_crossfit_fidelities": crossfit_blocks,
                    "block_crossfit_fidelity_ses": crossfit_ses,
                    "crossfit_block_spread": float(np.ptp(crossfit_blocks)),
                    "fidelity_estimator_for_latency": "two_fold_crossfit",
                })
            combined.append(row)
        return combined

    @staticmethod
    def _latency_has_ambiguous_faster_candidate(
            diagnostics, reference, selected, settings):
        """Whether more shots could resolve a physically faster viable contender."""
        target_latency = BasicAutoTuner._candidate_latency_us(selected)
        if not np.isfinite(target_latency):
            target_latency = BasicAutoTuner._candidate_latency_us(reference)
        max_loss = float(settings.get("max_fidelity_loss", 0.010))
        slack = float(settings.get("adaptive_ucb_slack", 0.010))
        mean_floor = float(settings.get("minimum_mean_fidelity", 0.90))
        lcb_floor = float(settings.get("minimum_lcb_fidelity", 0.88))
        for row in diagnostics:
            if row.get("accepted", False):
                continue
            latency = float(row.get("latency_us", np.inf))
            if not np.isfinite(latency) or latency >= target_latency - 1e-12:
                continue
            # Only spend additional hardware time when the point estimate and lower
            # confidence side are still compatible with the declared fidelity set.
            mean_loss = float(row.get("mean_loss", np.inf))
            loss_se = float(row.get("loss_se", np.inf))
            loss_lcb = mean_loss - float(row.get(
                "confidence_z", settings.get("confidence_sigma", 1.96))) * loss_se
            if (np.isfinite(loss_lcb) and loss_lcb <= max_loss
                    and float(row.get("loss_ucb", np.inf))
                    <= max_loss + slack
                    and float(row.get("fidelity", -np.inf)) >= mean_floor
                    and float(row.get("fidelity_lcb_95", -np.inf))
                    >= lcb_floor - slack):
                return True
        return False

    def _stage_latency_selection(self, reference, control_rows=None,
                                 reference_kind="unconstrained"):
        """Jointly minimize X180+readout time inside a fidelity-loss certificate."""
        p = self.params["latency"]
        if not p.get("enabled", True):
            self.data["latency_optimization"].update({
                "status": "disabled", "selected": copy.deepcopy(reference),
            })
            return reference
        if reference is None:
            raise RuntimeError("latency optimization has no best-fidelity reference")
        reference = self._annotate_candidate_latency(reference)
        self._latency_reference_key = _candidate_key(reference)
        self._deactivate_feedback("joint latency comparison")
        pool = self._latency_joint_candidate_pool(
            reference, control_rows=control_rows)
        if not pool:
            raise RuntimeError("latency candidate pool is empty")

        coarse_rows, failures = [], []
        for order, raw in enumerate(self.rng.permutation(len(pool))):
            candidate = pool[int(raw)]
            last_error = None
            for attempt in range(max(int(p.get("max_point_attempts", 2)), 1)):
                try:
                    row = self._measure_candidate(
                        candidate, int(p["coarse_shots"]),
                        "latency joint coarse attempt %d" % (attempt + 1),
                        state_order="ge" if order % 2 == 0 else "eg")
                    coarse_rows.append(self._annotate_candidate_latency(row))
                    last_error = None
                    break
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    last_error = exc
            if last_error is not None:
                failures.append({
                    "candidate_key": list(_candidate_key(candidate)),
                    "attempts": max(int(p.get("max_point_attempts", 2)), 1),
                    "error": "%s: %s" % (
                        type(last_error).__name__, last_error),
                })
        coverage = float(len(coarse_rows) / max(len(pool), 1))
        self._maps["latency"] = {
            "candidate_count": len(pool), "coarse_rows": coarse_rows,
            "failures": failures, "coverage": coverage,
            "search_complete": False, "selection_confirmed": False,
        }
        if coverage < 1.0 - 1e-12:
            raise RuntimeError(
                "joint latency screen completed only %.1f%% of candidates after "
                "retries; retaining the best-fidelity reference because a missing "
                "fast point prevents a shortest-chain claim" % (100.0 * coverage))

        reference_timing = self._latency_fidelity_evidence(reference)
        reference_floor = (
            float(reference_timing["fidelity"])
            - float(p["max_fidelity_loss"])
            - float(p["screening_slack"]))
        plausible = [row for row in coarse_rows
                     if (float(self._latency_fidelity_evidence(row).get(
                         "fidelity", -np.inf))
                         + float(p["screening_sigma"])
                         * float(self._latency_fidelity_evidence(row).get(
                             "fidelity_se", np.inf)))
                     >= reference_floor]
        # Confirm every uncertainty-plausible one-per-coordinate timing
        # representative in one randomized, interleaved held-out cohort.
        # Truncating to the first batch is not a shortest-chain search: several noisy
        # 1--10 us arms can occupy every slot, fail the held-out epsilon test, and hide
        # a valid 12--16 us plateau.  Coarse nondominance is not enough either: a noisy
        # 10-us estimate can superficially dominate the true 12-us boundary.  Splitting
        # arms across independent cohorts is also invalid because common drift is absent
        # from either arm's
        # within-batch error bar.  One cohort lets every pair use the same block-level
        # drift subtraction.  This representative set remains far smaller than the joint
        # Cartesian grid: only one representative per timing coordinate and only
        # uncertainty-plausible rows survive.
        frontier = self._latency_frontier_candidates(
            plausible, max_per_read_length=1, max_per_sigma=1,
            limit=max(len(plausible), 1), nondominated=False,
            uncertainty_sigma=float(p["screening_sigma"]))
        reference_candidate = self._annotate_candidate_latency(
            {key: reference[key] for key in self.initial})
        reference_key = _candidate_key(reference_candidate)
        frontier = [row for row in frontier
                    if _candidate_key(row) != reference_key]
        shortlist = _unique_candidates(frontier + [reference_candidate])
        confirmation_rounds = []
        confirmation_errors = []
        attempted, complete = [], False
        batch_errors = []
        for attempt_index in range(max(int(p.get(
                "max_confirmation_attempts", 2)), 1)):
            try:
                attempted = self._confirm_candidates(
                    shortlist, int(p["confirm_shots"]),
                    int(p["confirm_blocks"]),
                    "final exact latency Pareto replay frontier batch 1 attempt %d"
                    % (attempt_index + 1), add_to_history=True)
                attempted = [self._annotate_candidate_latency(row)
                             for row in attempted]
                complete = self._confirmation_batch_complete(attempted)
                if complete:
                    break
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                message = "%s: %s" % (type(exc).__name__, exc)
                batch_errors.append(message)
                confirmation_errors.append(message)
        frontier_batch_records = [{
            "batch": 1,
            "mode": "single_interleaved_frontier_cohort",
            "candidate_keys": [list(_candidate_key(row)) for row in shortlist],
            "candidate_count": len(shortlist),
            "complete": bool(complete),
            "errors": batch_errors,
        }]
        if complete:
            confirmation_rounds.append(attempted)
        confirmations = (
            self._combine_latency_confirmation_rounds(
                confirmation_rounds, "final exact latency frontier replay")
            if confirmation_rounds else [])
        self._maps["latency"].update({
            "shortlist": shortlist, "confirmations": confirmations,
            "frontier": frontier,
            "frontier_confirmation_batches": frontier_batch_records,
            "confirmation_attempt_errors": confirmation_errors,
            "selection_confirmation_complete": bool(complete),
            "search_complete": bool(complete),
            "selection_confirmed": bool(complete),
        })
        if not complete:
            raise RuntimeError(
                "latency frontier replay did not complete every randomized block")
        seed_reference_key = self._latency_reference_key
        fresh_seed = next((row for row in confirmations
                           if _candidate_key(row) == seed_reference_key), None)
        if fresh_seed is None:
            raise RuntimeError("fidelity-reference seed was not replayed")
        reference_drift = float(
            self._latency_fidelity_evidence(fresh_seed)["fidelity"]
            - reference_timing["fidelity"])
        if abs(reference_drift) > float(p["max_reference_drift"]):
            raise RuntimeError(
                "fidelity-reference seed drifted by %+.3f during latency replay"
                % reference_drift)

        # The caller supplies a strong seed, not an immutable reference.  The joint
        # cross can discover a higher-fidelity readout/control combination, including
        # one slower than that seed.  Anchor the epsilon budget once, to the best fresh
        # held-out aggregate in the complete comparison, so losses cannot compose over
        # multiple coordinate stages.
        adaptive_records = []
        anchor_safety_audits = []
        anchor_control_audits = []
        safety_qualified_keys = set()
        control_qualified_keys = set()
        infeasible_keys = set()
        safety_required = bool(
            self._leakage_active or self._operational_leakage_active)
        if self._leakage_verified_candidate_key is not None:
            safety_qualified_keys.add(tuple(self._leakage_verified_candidate_key))

        def candidate_is_qualified(key):
            return bool(
                key in control_qualified_keys
                and (not safety_required or key in safety_qualified_keys))

        def qualify_candidate(row, role):
            """Lazily prove that a decision-relevant arm is physically feasible."""
            key = _candidate_key(row)
            if key in infeasible_keys:
                return False
            if key not in control_qualified_keys:
                try:
                    audit = self._stage_final_control_verify(row)
                    control_ok = bool(audit.get("verified", False))
                    failure = None
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    audit, control_ok = None, False
                    failure = "%s: %s" % (type(exc).__name__, exc)
                anchor_control_audits.append({
                    "candidate_key": list(key), "role": str(role),
                    "passed": control_ok, "failure": failure,
                    "audit": copy.deepcopy(audit),
                })
                # Selection screening is evidence for the feasible set, not the fresh
                # exact witness which authorizes a later initialize.py write.
                self._final_control_verified_key = None
                if control_ok:
                    control_qualified_keys.add(key)
                else:
                    infeasible_keys.add(key)
                    return False
            if not safety_required:
                return True
            if key not in safety_qualified_keys:
                self.working = {name: row[name] for name in self.initial}
                try:
                    if self._leakage_active:
                        safe = bool(self._stage_leakage_verify(
                            allow_fallback=False))
                    else:
                        safe = bool(self._stage_operational_leakage_verify(
                            allow_fallback=False))
                    failure = (None if safe else self.data.get(
                        "leakage", {}).get("failure"))
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    safe = False
                    failure = "%s: %s" % (type(exc).__name__, exc)
                timing = self._latency_fidelity_evidence(row)
                anchor_safety_audits.append({
                    "candidate_key": list(key), "role": str(role),
                    "fidelity": float(row.get("fidelity", np.nan)),
                    "timing_fidelity": float(timing.get(
                        "fidelity", np.nan)),
                    "passed": safe, "failure": failure,
                })
                if safe:
                    safety_qualified_keys.add(key)
                else:
                    infeasible_keys.add(key)
                    return False
            return True

        def qualified_reference(rows):
            ranked_rows = sorted(rows, key=lambda row: (
                float(self._latency_fidelity_evidence(row).get(
                    "fidelity_lcb_95", -np.inf)),
                float(self._latency_fidelity_evidence(row).get(
                    "fidelity", -np.inf))), reverse=True)
            for row in ranked_rows:
                key = _candidate_key(row)
                if key in infeasible_keys:
                    continue
                if qualify_candidate(row, "fidelity_reference"):
                    return row
            return None

        selected = fresh_reference = None
        diagnostics, family_settings = [], None
        maximum_adaptive = max(int(p.get(
            "adaptive_confirmation_rounds", 0)), 0)
        for adaptive_round in range(maximum_adaptive + 1):
            # Recompute whenever an audit removes an infeasible arm.  Importantly,
            # this audits not only the observed best anchor but also any arm which is
            # the binding simultaneous reference for a rejected faster candidate.  An
            # unsafe third cloud or incoherent saturated drive therefore cannot veto
            # every genuinely feasible speedup merely because its histogram looked
            # excellent.
            while True:
                decision_rows = [
                    row for row in confirmations
                    if _candidate_key(row) not in infeasible_keys]
                fresh_reference = qualified_reference(decision_rows)
                if fresh_reference is None:
                    raise RuntimeError(
                        "no held-out latency reference passed coherent pulse-safety "
                        "qualification")
                decision_rows = [
                    row for row in confirmations
                    if _candidate_key(row) not in infeasible_keys]
                self._latency_reference_key = _candidate_key(fresh_reference)
                required_blocks = min(int(row.get("confirmation_blocks", 0))
                                      for row in decision_rows)
                # The best-fidelity anchor is selected from this same held-out batch.
                # Cover both directions of every pair, not merely K-1 fixed-reference
                # contrasts, and spend alpha across every permitted adaptive look.
                candidate_count = len(confirmations)
                family_settings = self._latency_family_settings(
                    max(candidate_count * (candidate_count - 1)
                        * (maximum_adaptive + 1), 1),
                    required_blocks)
                decision_settings = dict(family_settings)
                decision_settings["simultaneous_reference_rows"] = decision_rows
                selected, diagnostics = self._select_latency_constrained(
                    decision_rows, fresh_reference, decision_settings)
                if not qualify_candidate(selected, "latency_selection"):
                    continue

                reference_latency = self._candidate_latency_us(fresh_reference)
                rows_by_key = {_candidate_key(row): row for row in decision_rows}
                removed_binding_reference = False
                for diagnostic in sorted(diagnostics, key=lambda row: (
                        float(row.get("latency_us", np.inf)),
                        tuple(row.get("candidate_key") or ()))):
                    # Prove why every faster-than-reference rejected arm is out of
                    # bounds.  This also keeps a later coherent-fallback selection
                    # honest if a fresh control replay rejects the initial winner.
                    if (diagnostic.get("accepted", False)
                            or float(diagnostic.get("latency_us", np.inf))
                            >= reference_latency - 1e-12
                            or float(diagnostic.get("loss_ucb", np.inf))
                            <= float(p["max_fidelity_loss"])):
                        continue
                    blocker_key = tuple(
                        diagnostic.get("worst_case_reference_key") or ())
                    blocker = rows_by_key.get(blocker_key)
                    if (not blocker_key or blocker is None
                            or candidate_is_qualified(blocker_key)):
                        continue
                    if not qualify_candidate(blocker, "binding_reference"):
                        removed_binding_reference = True
                        break
                if removed_binding_reference:
                    continue
                break
            ambiguous = self._latency_has_ambiguous_faster_candidate(
                diagnostics, fresh_reference, selected, decision_settings)
            if not ambiguous or adaptive_round >= maximum_adaptive:
                break
            try:
                extra = self._confirm_candidates(
                    shortlist, int(p["confirm_shots"]),
                    int(p["confirm_blocks"]),
                    "adaptive exact latency replay round %d"
                    % (adaptive_round + 1), add_to_history=True)
                extra = [self._annotate_candidate_latency(row) for row in extra]
                extra_complete = self._confirmation_batch_complete(extra)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                adaptive_records.append({
                    "round": adaptive_round + 1, "complete": False,
                    "error": "%s: %s" % (type(exc).__name__, exc),
                })
                break
            adaptive_records.append({
                "round": adaptive_round + 1,
                "complete": bool(extra_complete),
                "candidate_count": len(extra),
            })
            if not extra_complete:
                # The original complete batch remains valid evidence.  An optional
                # precision extension may fail without erasing that result.
                break
            confirmation_rounds.append(extra)
            confirmations = self._combine_latency_confirmation_rounds(
                confirmation_rounds, "final exact adaptive latency replay")

        if selected is None or fresh_reference is None or family_settings is None:
            raise RuntimeError("latency selection did not produce a candidate")
        self._maps["latency"].update({
            "confirmations": confirmations,
            "confirmation_rounds": confirmation_rounds,
            "adaptive_confirmation": adaptive_records,
            "adaptive_rounds_completed": sum(
                bool(row.get("complete", False)) for row in adaptive_records),
            "anchor_safety_audits": anchor_safety_audits,
            "anchor_control_audits": anchor_control_audits,
            "infeasible_reference_keys": [
                list(key) for key in sorted(infeasible_keys)],
            # Legacy alias retained for old result readers.  The broader name above is
            # accurate because either coherence or leakage can remove an arm.
            "safety_rejected_anchor_keys": [
                list(key) for key in sorted(infeasible_keys)],
            "control_qualified_candidate_keys": [
                list(key) for key in sorted(control_qualified_keys)],
            "safety_qualified_candidate_keys": [
                list(key) for key in sorted(safety_qualified_keys)],
        })
        selected = self._annotate_candidate_latency(selected)
        selected_key = _candidate_key(selected)
        accepted_selected = any(
            bool(row.get("accepted", False))
            and tuple(row.get("candidate_key") or ()) == selected_key
            for row in diagnostics)
        reference_latency = self._candidate_latency_us(fresh_reference)
        selected_latency = self._candidate_latency_us(selected)
        qualified_speedup = bool(
            accepted_selected
            and selected_key != self._latency_reference_key
            and selected_latency < reference_latency - 1e-12)
        if not qualified_speedup:
            selected = self._annotate_candidate_latency(fresh_reference)
            selected_key = self._latency_reference_key
            selected_latency = reference_latency
        selected_is_accepted = any(
            bool(row.get("accepted", False))
            and tuple(row.get("candidate_key") or ()) == selected_key
            for row in diagnostics)
        any_qualified_nonreference = any(
            bool(row.get("accepted", False))
            and tuple(row.get("candidate_key") or ())
            != self._latency_reference_key
            for row in diagnostics)
        status = (
            "selected" if qualified_speedup else
            ("retained_reference_timing_uncertain"
             if not selected_is_accepted else
             ("retained_reference_no_qualified_speedup"
             if any_qualified_nonreference else
             "retained_reference_no_qualified_candidate")))
        self._adopt(selected, "latency")
        self.data["latency_optimization"].update({
            "status": status,
            "reference_kind": str(reference_kind),
            "reference": copy.deepcopy(fresh_reference),
            "reference_seed": copy.deepcopy(fresh_seed),
            "selected": copy.deepcopy(selected),
            "certified_selected": copy.deepcopy(selected),
            "certified_selected_key": list(selected_key),
            "latency_certificate_valid": bool(selected_is_accepted),
            "pre_safety_selected": copy.deepcopy(selected),
            "diagnostics": diagnostics,
            "familywise_confidence_sigma": family_settings["confidence_sigma"],
            "familywise_comparison_count": int(
                family_settings["familywise_comparison_count"]),
            "familywise_distribution": family_settings.get(
                "familywise_distribution"),
            "familywise_degrees_of_freedom": family_settings.get(
                "familywise_degrees_of_freedom"),
            "max_fidelity_loss": float(p["max_fidelity_loss"]),
            "reference_drift": reference_drift,
            "adaptive_confirmation": adaptive_records,
            "anchor_safety_audits": anchor_safety_audits,
            "anchor_control_audits": anchor_control_audits,
            "infeasible_reference_keys": [
                list(key) for key in sorted(infeasible_keys)],
            "safety_rejected_anchor_keys": [
                list(key) for key in sorted(infeasible_keys)],
            "control_qualified_candidate_keys": [
                list(key) for key in sorted(control_qualified_keys)],
            "safety_qualified_candidate_keys": [
                list(key) for key in sorted(safety_qualified_keys)],
            "confirmation_blocks": int(selected.get(
                "confirmation_blocks", p["confirm_blocks"])),
            "reference_latency_us": reference_latency,
            "selected_latency_us": selected_latency,
            "pre_safety_selected_latency_us": selected_latency,
            "integration_chain_us": float(selected["integration_chain_us"]),
            "latency_saved_us": float(reference_latency - selected_latency),
            "latency_reduction_fraction": float(
                max(reference_latency - selected_latency, 0.0)
                / max(reference_latency, 1e-12)),
            "pre_safety_selected_fidelity_loss": float(
                self._latency_fidelity_evidence(fresh_reference)["fidelity"]
                - self._latency_fidelity_evidence(selected)["fidelity"]),
            "qualified_candidate_found": bool(any_qualified_nonreference),
            "qualified_speedup": bool(qualified_speedup),
        })
        self.data["final_candidates"] = confirmations
        self._final_replay_completed = True
        self._final_replay_kind = "latency_unconstrained"
        self.data["final_confirmation_complete"] = True
        return selected

    def _stage_latency_control_screen(self, verify_safety=False):
        """Choose the first latency-qualified tuple passing control and safety audits."""
        record = self.data.get("latency_optimization", {})
        status_before_screen = str(record.get("status", ""))
        if (not self.params["latency"].get("control_screen_enabled", True)
                or not (status_before_screen == "selected"
                        or status_before_screen.startswith(
                            "retained_reference"))):
            return record.get("selected")
        confirmations = list(self._maps.get("latency", {}).get(
            "confirmations", []))
        accepted_keys = {
            tuple(row.get("candidate_key") or ())
            for row in record.get("diagnostics", [])
            if row.get("accepted", False)
        }
        reference = record.get("reference")
        if not isinstance(reference, dict):
            raise RuntimeError("latency control screen has no reference tuple")
        reference_key = _candidate_key(reference)
        reference_latency = self._candidate_latency_us(reference)
        contenders = [row for row in confirmations
                      if _candidate_key(row) in accepted_keys
                      and _candidate_key(row) != reference_key
                      and self._candidate_latency_us(row)
                      < reference_latency - 1e-12]
        contenders = sorted(contenders, key=lambda row: (
            self._candidate_latency_us(row),
            -float(self._latency_fidelity_evidence(row).get(
                "fidelity_lcb_95", -np.inf)),
            _candidate_key(row)))
        # The best-fidelity reference is the conservative last fallback, but it must
        # pass the same coherence audit rather than being adopted silently.
        contenders.append(reference)
        failures, chosen, chosen_audit = [], None, None
        for candidate in contenders:
            try:
                audit = self._stage_final_control_verify(candidate)
                if verify_safety:
                    self.working = {
                        key: candidate[key] for key in self.initial}
                    if self._leakage_active:
                        safe = self._stage_leakage_verify(
                            allow_fallback=False)
                    elif self._operational_leakage_active:
                        safe = self._stage_operational_leakage_verify(
                            allow_fallback=False)
                    else:
                        safe = True
                    if not safe:
                        raise RuntimeError(
                            "the exact latency tuple failed its pulse-safety audit")
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                failures.append({
                    "candidate_key": list(_candidate_key(candidate)),
                    "latency_us": self._candidate_latency_us(candidate),
                    "error": "%s: %s" % (type(exc).__name__, exc),
                })
                continue
            chosen = candidate
            chosen_audit = copy.deepcopy(audit)
            break
        if chosen is None:
            record.update({
                "status": "failed_no_coherent_latency_candidate",
                "control_screen_failures": failures,
                "control_screen_passed": False,
                "latency_certificate_valid": False,
                "qualified_speedup": False,
            })
            self._maps["latency_control_screen"] = {
                "failures": failures, "selected_candidate_key": None,
                "selected_latency_us": np.inf, "audit": None,
                "selection_confirmed": False, "search_complete": True,
            }
            self._final_control_verified_key = None
            raise RuntimeError(
                "no latency-qualified tuple, including the fidelity reference, "
                "passed the coherent odd/even pulse audit")
        chosen_key = _candidate_key(chosen)
        chosen_accepted = chosen_key in accepted_keys
        prior_certificate_valid = bool(record.get(
            "latency_certificate_valid", False))
        certificate_valid = bool(prior_certificate_valid and chosen_accepted)
        if chosen_key == reference_key:
            if not chosen_accepted:
                # Coherence does not resolve an uncertain fidelity comparison.  Keep
                # this as an explicit pure-fidelity fallback and never resurrect a
                # timing certificate from tuple identity alone.
                record["status"] = "retained_reference_timing_uncertain"
            elif status_before_screen == "selected" or failures:
                record["status"] = "retained_reference_control_fallback"
        elif failures:
            record["status"] = "selected_control_recovery"
        chosen = self._annotate_candidate_latency(chosen)
        self._adopt(chosen, "latency_control_screen")
        chosen_latency = self._candidate_latency_us(chosen)
        chosen_speedup = bool(
            certificate_valid and chosen_key != reference_key
            and chosen_latency < reference_latency - 1e-12)
        reference_timing = self._latency_fidelity_evidence(reference)
        chosen_timing = self._latency_fidelity_evidence(chosen)
        record.update({
            "selected": copy.deepcopy(chosen),
            "certified_selected": copy.deepcopy(chosen),
            "certified_selected_key": list(chosen_key),
            "latency_certificate_valid": certificate_valid,
            "pre_safety_selected": copy.deepcopy(chosen),
            "selected_latency_us": chosen_latency,
            "pre_safety_selected_latency_us": chosen_latency,
            "latency_saved_us": max(reference_latency - chosen_latency, 0.0),
            "latency_reduction_fraction": (
                max(reference_latency - chosen_latency, 0.0)
                / max(reference_latency, 1e-12)),
            "pre_safety_selected_fidelity_loss": float(
                reference_timing["fidelity"] - chosen_timing["fidelity"]),
            "control_screen_failures": failures,
            "control_screen_passed": bool(chosen_audit is not None),
            "control_screen_audit": chosen_audit,
            "control_screen_included_safety": bool(verify_safety),
            "qualified_speedup": chosen_speedup,
        })
        self._maps["latency_control_screen"] = {
            "failures": failures,
            "selected_candidate_key": list(_candidate_key(chosen)),
            "selected_latency_us": chosen_latency,
            "audit": chosen_audit,
            "safety_audited": bool(verify_safety),
            "selection_confirmed": bool(chosen_audit is not None),
            "search_complete": bool(chosen_audit is not None),
        }
        # This screening witness guides fallback but cannot be borrowed by the final
        # write certificate.  The exact post-safety final tuple is audited again.
        self._final_control_verified_key = None
        return chosen

    @staticmethod
    def _noninferior_seed(aggregates, seed, incumbent, margin=0.005):
        by_key = {_candidate_key(row): row for row in aggregates}
        seed_row = by_key.get(_candidate_key(seed))
        incumbent_row = by_key.get(_candidate_key(incumbent))
        if seed_row is None:
            return BasicAutoTuner._best_aggregate(aggregates)
        if incumbent_row is None:
            return seed_row
        floor = (float(incumbent_row["fidelity"])
                 - 1.96 * float(incumbent_row["fidelity_se"]) - float(margin))
        if float(seed_row["fidelity_lcb_95"]) >= floor:
            return seed_row
        return BasicAutoTuner._best_aggregate(aggregates)

    @staticmethod
    def _prefer_lower_readout_exposure(aggregates, margin=0.003,
                                       max_mean_loss=0.010):
        """Prefer lower readout gain-squared x duration inside a fidelity tie."""
        if not aggregates:
            return None
        best = BasicAutoTuner._best_aggregate(aggregates)
        tied = []
        for row in aggregates:
            uncertainty = 1.96 * math.hypot(
                float(best.get("fidelity_se", np.inf)),
                float(row.get("fidelity_se", np.inf)))
            loss = float(best["fidelity"]) - float(row["fidelity"])
            if (loss <= uncertainty + float(margin)
                    and loss <= float(max_mean_loss)):
                tied.append(row)
        return min(tied or [best], key=lambda row: (
            float(row.get("read_pulse_gain", np.inf)) ** 2
            * float(row.get("read_length", np.inf)),
            float(row.get("read_length", np.inf)),
            -float(row.get("fidelity_lcb_95", -np.inf))))

    @staticmethod
    def _calibration_drift(before, after):
        angle = float(np.angle(np.exp(1j * (
            float(after["read_theta"]) - float(before["read_theta"])))))
        theta = float(before["read_theta"])
        factor = float(before["scale_factor"])

        def project(row, state):
            center = complex(float(row["%s_center_i" % state]),
                             float(row["%s_center_q" % state]))
            return float(factor * np.real(np.exp(-1j * theta) * center))

        pre_g = project(before, "ground")
        pre_e = project(before, "excited")
        post_g = project(after, "ground")
        post_e = project(after, "excited")
        separation = max(abs(pre_e - pre_g), 1e-12)
        midpoint_shift_fraction = abs(
            0.5 * (post_g + post_e) - 0.5 * (pre_g + pre_e)) / separation
        reference_fidelity = float(after.get("reference_fidelity", np.nan))
        return {
            "angle_degrees": float(abs(np.degrees(angle))),
            "fidelity_change": float(after["fidelity"] - before["fidelity"]),
            "fixed_discriminator_fidelity": reference_fidelity,
            "fixed_discriminator_fidelity_loss": float(
                before["fidelity"] - reference_fidelity),
            "midpoint_shift_fraction": float(midpoint_shift_fraction),
            "separation_change_fraction": float(
                ((post_e - post_g) - (pre_e - pre_g)) / separation),
        }

    def _calibration_is_stable(self, drift):
        limits = self.params["calibration_drift"]
        return bool(
            np.isfinite(drift["fixed_discriminator_fidelity"])
            and float(drift["angle_degrees"])
            <= float(limits["max_angle_degrees"])
            and abs(float(drift["fidelity_change"]))
            <= float(limits["max_independent_fidelity_change"])
            and float(drift["fixed_discriminator_fidelity_loss"])
            <= float(limits["max_fixed_discriminator_fidelity_loss"])
            and float(drift["midpoint_shift_fraction"])
            <= float(limits["max_midpoint_shift_fraction"]))

    def _require_stable_calibration(self, drift, stage):
        if not self._calibration_is_stable(drift):
            raise RuntimeError(
                "%s discriminator drifted during its map (angle %.1f deg, "
                "independent dF %+.3f, fixed-discriminator loss %+.3f, "
                "midpoint shift %.2f separation)"
                % (stage, drift["angle_degrees"], drift["fidelity_change"],
                   drift["fixed_discriminator_fidelity_loss"],
                   drift["midpoint_shift_fraction"]))

    def _adopt(self, aggregate, stage):
        if aggregate is None:
            return
        self.working = {key: aggregate[key] for key in self.initial}
        self._log(stage, "OK",
                  "selected read %.6f/%d/%.1fus | pi %.6f @ %d / %.1fns; "
                  "step-5 F=%.4f +/- %.4f"
                  % (self.working["read_pulse_freq"],
                     self.working["read_pulse_gain"], self.working["read_length"],
                     self.working["qubit_pi_freq"], self.working["qubit_pi_gain"],
                     4000.0 * self.working["sigma"], aggregate["fidelity"],
                     aggregate["fidelity_se"]))

    def _record_key_evidence(self, keys, stage, complete):
        for key in keys:
            self._key_evidence[key].append({
                "value": self.working[key], "stage": str(stage),
                "complete": bool(complete),
            })

    def _record_control_witness(self, stage, frequency_mhz, kind,
                                candidate=None, **metrics):
        """Archive coherent evidence, optionally bound to one exact waveform."""
        try:
            frequency = float(frequency_mhz)
        except (TypeError, ValueError, OverflowError):
            return
        if not np.isfinite(frequency):
            return
        row = {
            "stage": str(stage), "kind": str(kind),
            "frequency_mhz": frequency,
        }
        if candidate is not None:
            try:
                control = {
                    "qubit_pi_freq": float(candidate["qubit_pi_freq"]),
                    "qubit_pi_gain": int(round(candidate["qubit_pi_gain"])),
                    "sigma": float(candidate["sigma"]),
                    "qubit_drag_beta": float(candidate.get(
                        "qubit_drag_beta", 0.0)),
                }
                row["control_tuple"] = control
                row["control_key"] = _control_key(control)
            except (KeyError, TypeError, ValueError, OverflowError):
                # Incomplete diagnostic witnesses remain useful in the saved report,
                # but cannot authorize a write because they have no control key.
                pass
        row.update(metrics)
        self._control_witnesses.append(row)

    def _key_has_evidence(self, key, value):
        for row in reversed(self._key_evidence.get(key, [])):
            measured = row.get("value")
            try:
                matches = (int(measured) == int(value) if key.endswith("gain")
                           else math.isclose(float(measured), float(value),
                                             rel_tol=0.0, abs_tol=1e-9))
            except Exception:
                matches = measured == value
            if matches:
                return bool(row.get("complete", False))
        return False

    @staticmethod
    def _tuned_values_match(key, first, second):
        """Compare two persisted calibration values without gain truncation leaks."""
        try:
            if key.endswith("gain"):
                return int(round(float(first))) == int(round(float(second)))
            return math.isclose(float(first), float(second),
                                rel_tol=0.0, abs_tol=1e-9)
        except (TypeError, ValueError, OverflowError):
            return first == second

    def _input_tuned_value(self, key):
        """Return the value that would remain if the runner did not write ``key``."""
        return self.input_cfg.get(key, self.initial[key])

    # --------------------------------------------------------------- map utilities
    @staticmethod
    def _integer_axis(start, stop, points, lower=0, upper=32767):
        start = int(np.clip(round(start), lower, upper))
        stop = int(np.clip(round(stop), lower, upper))
        if stop < start:
            start, stop = stop, start
        points = max(int(points), 2)
        step = max(int(round((stop - start) / float(points - 1))), 1)
        axis = start + step * np.arange(points, dtype=int)
        axis = axis[(axis <= upper) & (axis <= stop)]
        if axis.size < 2:
            axis = np.array([max(lower, start - 1), min(upper, start + 1)], dtype=int)
        return axis

    @staticmethod
    def _float_axis(center, span, points, include=()):
        axis = np.linspace(float(center) - float(span) / 2.0,
                           float(center) + float(span) / 2.0, int(points))
        for value in include:
            if np.isfinite(value):
                axis[int(np.argmin(np.abs(axis - float(value))))] = float(value)
        return np.sort(np.unique(axis))

    @staticmethod
    def _bounded_axis(start, stop, nominal_step):
        """Return one uniform, inclusive axis for an authorized absolute band."""
        start, stop, nominal_step = map(float, (start, stop, nominal_step))
        if not np.all(np.isfinite([start, stop, nominal_step])):
            raise ValueError("frequency-search bounds must be finite")
        if stop <= start or nominal_step <= 0:
            raise ValueError("frequency-search bounds/step are invalid")
        intervals = max(int(round((stop - start) / nominal_step)), 1)
        return np.linspace(start, stop, intervals + 1, dtype=float)

    def _frequency_discovery_plan(self, center, settings, adaptive=False):
        """Build absolute or seed-relative search axes and acceptance bounds.

        Relative scans include a small outer padding so a transition exactly at the
        authorized +/-radius limit is an interior, fittable feature.  The acceptance
        bounds remain unpadded, so the padding cannot silently enlarge the prior.
        """
        center = float(center)
        search_min = settings.get("search_min_mhz")
        search_max = settings.get("search_max_mhz")
        absolute = search_min is not None or search_max is not None
        if absolute:
            if search_min is None or search_max is None:
                raise ValueError(
                    "search_min_mhz and search_max_mhz must be set together")
            allowed_min, allowed_max = float(search_min), float(search_max)
            axes = [self._bounded_axis(
                allowed_min, allowed_max, settings["search_step_mhz"])]
            return {
                "axes": axes,
                "acceptance_bounds": [(allowed_min, allowed_max)],
                "allowed_min_mhz": allowed_min,
                "allowed_max_mhz": allowed_max,
                "mode": "absolute",
                "configured_envelope": True,
            }

        radius = settings.get("search_radius_mhz")
        if radius is None:
            axis = self._float_axis(
                center, settings["wide_span_mhz"], settings["wide_points"])
            return {
                "axes": [axis],
                "acceptance_bounds": [(float(axis[0]), float(axis[-1]))],
                "allowed_min_mhz": float(axis[0]),
                "allowed_max_mhz": float(axis[-1]),
                "mode": "legacy_local",
                "configured_envelope": False,
            }

        radius = float(radius)
        padding = float(settings.get("search_edge_padding_mhz", 0.0))
        if (not np.all(np.isfinite([center, radius, padding]))
                or radius <= 0 or padding < 0):
            raise ValueError("relative frequency-search radius/padding is invalid")
        radii = [radius]
        if adaptive:
            requested = settings.get("search_expansion_radii_mhz", [radius])
            if not isinstance(requested, (list, tuple, np.ndarray)):
                raise ValueError("search_expansion_radii_mhz must be a sequence")
            radii = sorted(set(
                float(value) for value in requested
                if np.isfinite(float(value)) and 0 < float(value) <= radius))
            if not radii or not math.isclose(
                    radii[-1], radius, rel_tol=0.0, abs_tol=1e-12):
                radii.append(radius)
        axes, acceptance = [], []
        for current_radius in radii:
            scan_radius = current_radius + padding
            axes.append(self._bounded_axis(
                center - scan_radius, center + scan_radius,
                settings["search_step_mhz"]))
            acceptance.append((
                center - current_radius, center + current_radius))
        return {
            "axes": axes,
            "acceptance_bounds": acceptance,
            "allowed_min_mhz": center - radius,
            "allowed_max_mhz": center + radius,
            "mode": "relative_prior",
            "configured_envelope": True,
            "center_mhz": center,
            "radius_mhz": radius,
            "padding_mhz": padding,
        }

    @staticmethod
    def _contained_centered_axis(center, span, points, lower=None, upper=None):
        """Build a centered axis, shifted inward to remain inside optional bounds."""
        center, span = float(center), float(span)
        points = max(int(points), 3)
        if points % 2 == 0:
            points += 1
        if not np.all(np.isfinite([center, span])) or span <= 0:
            raise ValueError("confirmation center/span are invalid")
        if lower is not None or upper is not None:
            if lower is None or upper is None:
                raise ValueError("both confirmation bounds are required")
            lower, upper = float(lower), float(upper)
            if upper <= lower or span > upper - lower + 1e-12:
                raise ValueError("confirmation span exceeds the authorized band")
            center = float(np.clip(
                center, lower + span / 2.0, upper - span / 2.0))
        return np.linspace(center - span / 2.0, center + span / 2.0, points)

    @staticmethod
    def _gain_axis(start, stop, points, include=()):
        axis = np.rint(np.linspace(float(start), float(stop), int(points))).astype(int)
        axis = np.clip(axis, 0, 32767)
        for value in include:
            if np.isfinite(value):
                axis[int(np.argmin(np.abs(axis - int(round(value)))))] = int(
                    np.clip(round(value), 0, 32767))
        return np.sort(np.unique(axis))

    def _direct_grid(self, stage, candidates, shape, axes, shots, shortlist,
                     confirm_shots, confirm_blocks, coverage_values=None,
                     coverage_per_value=1, primary_fidelity_only=False):
        candidates = [dict(candidate) for candidate in candidates]
        if int(np.prod(shape)) != len(candidates):
            raise ValueError("candidate list does not match grid shape")
        if coverage_values is not None and len(coverage_values) != len(candidates):
            raise ValueError("coverage values do not match the direct grid")
        score = np.full(len(candidates), np.nan)
        score_se = np.full(len(candidates), np.nan)
        third_blob_ucb = np.full(len(candidates), np.nan)
        order = self.rng.permutation(len(candidates))
        failures = 0
        consecutive_failures = 0
        aborted = False
        cache = {}
        self._log(stage, "OK", "%d-point direct step-5 grid (%d shots/state)"
                  % (len(candidates), int(shots)))
        progress_step = max(len(candidates) // 10, 1)
        for count, index in enumerate(order):
            key = _candidate_key(candidates[index])
            if key in cache:
                score[index], score_se[index], third_blob_ucb[index] = cache[key]
                consecutive_failures = 0
                continue
            try:
                measured = self._measure_candidate(
                    candidates[index], int(shots), "%s coarse" % stage,
                    state_order="ge" if count % 2 == 0 else "eg")
                score[index] = measured["fidelity"]
                score_se[index] = measured["fidelity_se"]
                third_blob_ucb[index] = measured["third_blob_excess_ucb_95"]
                cache[key] = (
                    score[index], score_se[index], third_blob_ucb[index])
                consecutive_failures = 0
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                failures += 1
                consecutive_failures += 1
                self._log(stage, "WARN", "grid point %d/%d failed (%s: %s)"
                          % (count + 1, len(candidates), type(exc).__name__, exc))
                if consecutive_failures >= int(self.params.get(
                        "max_consecutive_point_failures", 5)):
                    self._log(stage, "WARN",
                              "%d consecutive backend failures; stopping this grid"
                              % consecutive_failures)
                    aborted = True
                    break
            if (self._detailed_console()
                    and ((count + 1) % progress_step == 0
                         or count + 1 == len(candidates))):
                print("      %s progress: %d/%d" % (stage, count + 1, len(candidates)))
        if not np.any(np.isfinite(score)):
            raise RuntimeError("every direct single-shot grid point failed")
        coverage = float(np.count_nonzero(np.isfinite(score)) / max(len(score), 1))
        selection_usable = bool(not aborted and coverage >= 0.80)
        # A partially measured map may still nominate useful candidates for fresh
        # confirmation, but it is never complete evidence for an automatic write.
        search_complete = bool(not aborted and coverage >= 1.0 - 1e-12)
        self._maps[stage] = {
            "axes": {key: np.asarray(value) for key, value in axes.items()},
            "fidelity": score.reshape(shape),
            "fidelity_se": score_se.reshape(shape),
            "third_blob_excess_ucb": third_blob_ucb.reshape(shape),
            "failed_points": int(failures),
            "coverage": coverage, "aborted": bool(aborted),
            "selection_coverage_usable": selection_usable,
            "search_complete": search_complete, "selection_confirmed": False,
        }
        if not selection_usable:
            raise RuntimeError(
                "%s grid incomplete (%.1f%% finite coverage); partial points archived"
                % (stage, 100.0 * coverage))
        if not search_complete:
            self._log(
                stage, "WARN",
                "%.1f%% map coverage is enough to confirm/report candidates, but only "
                "100%% coverage counts as independent coordinate-search evidence; "
                "a stable exact final tuple replay can still authorize the winner"
                % (100.0 * coverage))
        finite = np.flatnonzero(np.isfinite(score))
        guarded = finite
        # The ordinary optimizer must remain a pure fidelity search.  Only strict
        # direct-P(f) mode may constrain this ranking.  The default operational guard
        # compares the resulting duration/power family afterwards and reports the
        # unconstrained replay separately, so a failed guard cannot silently erase the
        # best pulse the hardware actually measured.
        if self._leakage_active:
            threshold = float(self.params["leakage"]["max_third_blob_excess"])
            safe = finite[np.isfinite(third_blob_ucb[finite])
                          & (third_blob_ucb[finite] <= threshold)]
            if safe.size:
                guarded = safe
        ranked = guarded[np.argsort(score[guarded])[::-1]]
        selected_indices = [int(index) for index in
                            ranked[:max(int(shortlist), 1)]]
        covered_groups = {}
        if coverage_values is not None:
            # Global top-K is not timing coverage: all K points can be noisy variants
            # of one duration, while the input duration is guaranteed a separate
            # incumbent slot.  That makes the answer depend on the starting length.
            # Reserve held-out contenders independently at every physical duration.
            for index in guarded:
                try:
                    group = round(float(coverage_values[int(index)]), 9)
                except (TypeError, ValueError, OverflowError):
                    group = str(coverage_values[int(index)])
                covered_groups.setdefault(group, []).append(int(index))
            per_value = max(int(coverage_per_value), 1)
            for group in sorted(covered_groups, key=str):
                group_ranked = sorted(
                    covered_groups[group], key=lambda index: (
                        float(score[index]), -float(score_se[index])),
                    reverse=True)
                selected_indices.extend(group_ranked[:per_value])
        selected_indices = list(dict.fromkeys(selected_indices))
        selected = [candidates[index] for index in selected_indices]
        # The current incumbent is freshly remeasured beside the grid winners.  Thus a
        # noisy maximum can never silently replace a genuinely better manual tuple.
        incumbent = dict(self.working)
        selected.append(incumbent)
        confirmed = self._confirm_candidates(
            selected, int(confirm_shots), int(confirm_blocks), "%s confirm" % stage)
        confirmation_complete = self._confirmation_batch_complete(confirmed)
        self._maps[stage]["selection_confirmation_complete"] = bool(
            confirmation_complete)
        self._maps[stage]["coverage_confirmation"] = {
            "enabled": bool(coverage_values is not None),
            "groups": [value for value in sorted(covered_groups, key=str)],
            "per_group": (max(int(coverage_per_value), 1)
                          if coverage_values is not None else 0),
            "selected_candidate_keys": [
                list(_candidate_key(candidates[index]))
                for index in selected_indices],
        }
        if not confirmation_complete:
            self._maps[stage]["search_complete"] = False
        guarded_confirmed = list(confirmed)
        if self._leakage_active:
            threshold = float(self.params["leakage"]["max_third_blob_excess"])
            safe_confirmed = [row for row in confirmed
                              if float(row.get(
                                  "third_blob_excess_ucb", np.inf)) <= threshold]
            if safe_confirmed:
                guarded_confirmed = safe_confirmed
        direct_best = self._best_aggregate(guarded_confirmed)
        # When held-out evidence cannot distinguish the incumbent from the apparent
        # winner, keep the incumbent.  This prevents a flat bootstrap map from turning
        # a coherent Rabi/readout seed into an arbitrary noise-selected tuple.
        if primary_fidelity_only:
            # Gate/readout latency is a secondary epsilon-constrained objective.  The
            # primary calibration must first preserve the maximum held-out fidelity;
            # otherwise the timing preference is spent twice and can hide a longer,
            # materially better readout solely because the input happened to be short.
            best = direct_best
        elif str(stage).startswith("readout"):
            best = self._prefer_lower_readout_exposure(
                guarded_confirmed, margin=0.003,
                max_mean_loss=self.params["readout"].get(
                    "max_tie_fidelity_loss", 0.010))
        else:
            best = self._noninferior_seed(
                guarded_confirmed, incumbent, direct_best, margin=0.003)
        self._adopt(best, stage)
        self._maps[stage]["selection_confirmed"] = True
        return best

    @staticmethod
    def _smooth_trace(values):
        values = np.asarray(values, dtype=float)
        n = values.size
        if n < 5:
            return values.copy()
        # Keep the kernel deliberately short.  A 15-point kernel erased a narrow
        # resonator in coarse scans and moved the apparent dip by multiple linewidths.
        window = 5
        return savgol_filter(values, window_length=window, polyorder=2, mode="interp")

    @staticmethod
    def _parabolic_vertex(x, y, index):
        if index <= 0 or index >= len(x) - 1:
            return float(x[index])
        xx = np.asarray(x[index - 1:index + 2], float)
        yy = np.asarray(y[index - 1:index + 2], float)
        try:
            a, b, _ = np.polyfit(xx, yy, 2)
            vertex = -b / (2.0 * a)
            if a != 0 and xx[0] <= vertex <= xx[-1]:
                return float(vertex)
        except Exception:
            pass
        return float(x[index])

    @classmethod
    def _resonator_feature(cls, freqs, response, polarity="dip",
                           edge_guard_points=2, min_snr=3.0,
                           min_relative_contrast=0.002,
                           min_feature_width_mhz=0.04,
                           max_feature_width_mhz=2.0):
        """Find a detrended, interior resonator feature without accepting a slope.

        A raw magnitude argmin is not a resonator detector: on a scan that misses the
        device, cable slope or the remote tail of a notch necessarily puts the argmin
        at an edge.  This routine iteratively fits the smooth background, scores only
        the residual feature, and keeps boundary/contrast checks explicit so callers
        can archive a rejected scan without calling it a found resonator.
        """
        freqs = np.asarray(freqs, dtype=float)
        response = np.asarray(response, dtype=complex)
        if freqs.ndim != 1 or response.shape != freqs.shape or freqs.size < 9:
            raise ValueError("invalid resonator trace")
        magnitude = np.abs(response)
        finite = np.isfinite(freqs) & np.isfinite(magnitude)
        if np.count_nonzero(finite) < max(9, int(math.ceil(0.9 * freqs.size))):
            raise ValueError("resonator trace has insufficient finite coverage")
        span = float(freqs[-1] - freqs[0])
        if not np.isfinite(span) or span <= 0:
            raise ValueError("resonator frequency axis is invalid")
        x = 2.0 * (freqs - freqs[0]) / span - 1.0
        mask = finite.copy()
        baseline = np.full(freqs.size, np.nan, dtype=float)
        sign = -1.0 if str(polarity).strip().lower() == "peak" else 1.0
        # For a dip, signed = baseline - magnitude; for a peak the sign reverses.
        for _ in range(5):
            degree = min(2, int(np.count_nonzero(mask)) - 1)
            if degree < 1:
                break
            coefficients = np.polyfit(x[mask], magnitude[mask], degree)
            baseline = np.polyval(coefficients, x)
            signed = sign * (baseline - magnitude)
            centre = float(np.nanmedian(signed[mask]))
            scale = max(
                _robust_scale(signed[mask]),
                np.finfo(float).eps * max(
                    float(np.nanmedian(np.abs(magnitude[mask]))), 1.0),
            )
            # Remove a positive feature from the next background fit while retaining
            # ordinary negative residuals and slow baseline structure.
            next_mask = finite & (signed <= centre + 2.5 * scale)
            if (np.count_nonzero(next_mask) < max(7, freqs.size // 2)
                    or np.array_equal(next_mask, mask)):
                break
            mask = next_mask
        if not np.all(np.isfinite(baseline[finite])):
            raise ValueError("resonator background fit failed")
        feature = sign * (baseline - magnitude)
        smoothed_feature = cls._smooth_trace(feature)
        smoothed_magnitude = cls._smooth_trace(magnitude)
        guard = int(np.clip(
            int(edge_guard_points), 1, max((freqs.size - 3) // 2, 1)))
        searchable = np.arange(guard, freqs.size - guard, dtype=int)
        searchable = searchable[np.isfinite(smoothed_feature[searchable])]
        if searchable.size < 3:
            raise ValueError("resonator trace has no searchable interior")
        index = int(searchable[int(np.nanargmax(smoothed_feature[searchable]))])
        exclusion = max(2, freqs.size // 30)
        background_indices = searchable[np.abs(searchable - index) > exclusion]
        if background_indices.size < 3:
            background_indices = searchable[searchable != index]
        floor = float(np.nanmedian(smoothed_feature[background_indices]))
        numerical_floor = np.finfo(float).eps * max(
            float(np.nanmedian(np.abs(magnitude[background_indices]))), 1.0)
        noise = max(
            _robust_scale(smoothed_feature[background_indices] - floor),
            numerical_floor,
        )
        height = float(smoothed_feature[index] - floor)
        snr = float(height / noise)
        relative = float(height / max(
            float(np.nanmedian(np.abs(magnitude[background_indices]))), 1e-15))
        profile = smoothed_feature - floor
        half_height = 0.5 * height
        left = index
        while left > 0 and profile[left] > half_height:
            left -= 1
        right = index
        while right < freqs.size - 1 and profile[right] > half_height:
            right += 1
        two_sided = bool(left > 0 and right < freqs.size - 1
                         and left < index < right)
        feature_width = (float(freqs[right] - freqs[left])
                         if two_sided else np.inf)
        at_boundary = bool(
            index <= guard or index >= freqs.size - 1 - guard)
        seed = cls._parabolic_vertex(freqs, smoothed_feature, index)
        valid = bool(
            np.all(finite)
            and not at_boundary
            and np.isfinite(snr) and snr >= float(min_snr)
            and np.isfinite(relative)
            and relative >= float(min_relative_contrast)
            and two_sided
            and feature_width >= float(min_feature_width_mhz)
            and feature_width <= float(max_feature_width_mhz))
        reasons = []
        if not np.all(finite):
            reasons.append("incomplete trace")
        if at_boundary:
            reasons.append("feature is at the search boundary")
        if not np.isfinite(snr) or snr < float(min_snr):
            reasons.append("contrast SNR %.2f is below %.2f" % (snr, min_snr))
        if (not np.isfinite(relative)
                or relative < float(min_relative_contrast)):
            reasons.append("relative contrast %.4g is below %.4g"
                           % (relative, min_relative_contrast))
        if not two_sided:
            reasons.append("feature has no two-sided half-height crossings")
        elif (feature_width < float(min_feature_width_mhz)
              or feature_width > float(max_feature_width_mhz)):
            reasons.append("feature width %.4f MHz is outside %.4f..%.4f MHz"
                           % (feature_width, min_feature_width_mhz,
                              max_feature_width_mhz))
        return {
            "frequency_mhz": float(seed), "index": index,
            "valid": valid, "failure": "; ".join(reasons),
            "at_boundary": at_boundary, "contrast_snr": snr,
            "relative_contrast": relative, "feature_height": height,
            "feature_width_mhz": feature_width,
            "magnitude": magnitude, "smoothed_magnitude": smoothed_magnitude,
            "baseline_magnitude": baseline, "feature": feature,
            "smoothed_feature": smoothed_feature,
        }

    @classmethod
    def _resonator_features(cls, freqs, response, polarity="dip",
                            edge_guard_points=2, min_snr=3.0,
                            min_relative_contrast=0.002,
                            min_feature_width_mhz=0.04,
                            max_feature_width_mhz=2.0,
                            max_candidates=8,
                            min_candidate_separation_mhz=1.0):
        """Return several validated notches from one detrended transmission trace.

        ``_resonator_feature`` intentionally returns the strongest feature for legacy
        callers.  Discovery cannot use that as an identity decision: another resonator
        or package mode may be deeper than the resonator coupled to the target qubit.
        This method reuses the same robust background fit, finds separated local
        maxima in its signed residual, and evaluates every candidate against a common
        noise floor before any downstream branch is discarded.
        """
        strongest = cls._resonator_feature(
            freqs, response, polarity=polarity,
            edge_guard_points=edge_guard_points, min_snr=min_snr,
            min_relative_contrast=min_relative_contrast,
            min_feature_width_mhz=min_feature_width_mhz,
            max_feature_width_mhz=max_feature_width_mhz)
        freqs = np.asarray(freqs, dtype=float)
        profile = np.asarray(strongest["smoothed_feature"], dtype=float)
        magnitude = np.asarray(strongest["magnitude"], dtype=float)
        guard = int(np.clip(
            int(edge_guard_points), 1, max((freqs.size - 3) // 2, 1)))
        step = abs(float(np.median(np.diff(freqs))))
        separation_points = max(int(round(
            float(min_candidate_separation_mhz) / max(step, 1e-15))), 1)
        interior = np.arange(guard, freqs.size - guard, dtype=int)
        finite_interior = interior[np.isfinite(profile[interior])]
        if finite_interior.size < 3:
            return []
        local, _properties = find_peaks(
            profile[finite_interior], distance=separation_points)
        indices = finite_interior[np.asarray(local, dtype=int)]
        indices = np.unique(np.append(indices, int(strongest["index"]))).astype(int)
        indices = indices[np.argsort(profile[indices])[::-1]]
        # Estimate the common background after masking the strongest separated peaks.
        # This prevents a deep distractor from being counted as noise against a weaker
        # but still reproducible target resonator.
        mask_indices = indices[:max(3 * int(max_candidates), int(max_candidates), 1)]
        exclusion_points = max(
            separation_points // 2,
            int(math.ceil(float(max_feature_width_mhz) / max(step, 1e-15))),
            2)
        background_mask = np.ones(freqs.size, dtype=bool)
        background_mask[:guard] = False
        background_mask[freqs.size - guard:] = False
        for index in mask_indices:
            lo = max(int(index) - exclusion_points, 0)
            hi = min(int(index) + exclusion_points + 1, freqs.size)
            background_mask[lo:hi] = False
        background = profile[background_mask & np.isfinite(profile)]
        if background.size < max(7, freqs.size // 10):
            cutoff = float(np.nanpercentile(profile[finite_interior], 70.0))
            background = profile[
                finite_interior[profile[finite_interior] <= cutoff]]
        floor = float(np.nanmedian(background))
        numerical_floor = np.finfo(float).eps * max(
            float(np.nanmedian(np.abs(magnitude[np.isfinite(magnitude)]))), 1.0)
        noise = max(_robust_scale(background - floor), numerical_floor)
        reference_magnitude = max(
            float(np.nanmedian(np.abs(magnitude[np.isfinite(magnitude)]))), 1e-15)
        candidates = []
        for index in indices:
            index = int(index)
            height = float(profile[index] - floor)
            snr = float(height / noise)
            relative = float(height / reference_magnitude)
            half_height = floor + 0.5 * height
            left = index
            while left > 0 and profile[left] > half_height:
                left -= 1
            right = index
            while right < freqs.size - 1 and profile[right] > half_height:
                right += 1
            two_sided = bool(left > 0 and right < freqs.size - 1
                             and left < index < right)
            width = (float(freqs[right] - freqs[left])
                     if two_sided else np.inf)
            at_boundary = bool(
                index <= guard or index >= freqs.size - 1 - guard)
            valid = bool(
                not at_boundary and np.isfinite(snr) and snr >= float(min_snr)
                and np.isfinite(relative)
                and relative >= float(min_relative_contrast)
                and two_sided
                and float(min_feature_width_mhz) <= width
                <= float(max_feature_width_mhz))
            if not valid:
                continue
            row = dict(strongest)
            row.update({
                "frequency_mhz": cls._parabolic_vertex(freqs, profile, index),
                "index": index, "valid": True, "failure": "",
                "at_boundary": at_boundary, "contrast_snr": snr,
                "relative_contrast": relative, "feature_height": height,
                "feature_width_mhz": width,
            })
            candidates.append(row)
            if len(candidates) >= max(int(max_candidates), 1):
                break
        return candidates

    @staticmethod
    def _significant_spectral_rows(freqs, features, min_snr,
                                   edge_guard_points=2):
        """Return only measured, significant, non-boundary spectral peaks."""
        freqs = np.asarray(freqs, dtype=float)
        guard = int(np.clip(
            int(edge_guard_points), 1, max((freqs.size - 3) // 2, 1)))
        rows = []
        for position, index in enumerate(features.get("candidate_indices", [])):
            index = int(index)
            if index <= guard or index >= freqs.size - 1 - guard:
                continue
            try:
                snr = float(features["snr_trace"][index])
            except (IndexError, KeyError, TypeError, ValueError):
                continue
            if not np.isfinite(snr) or snr < float(min_snr):
                continue
            rows.append({
                "frequency": float(freqs[index]), "index": index,
                "score": snr, "rank": int(position),
            })
        return rows

    @staticmethod
    def _spectral_shoulder_rows(freqs, features, existing_rows, min_snr,
                                maximum_rows, relative_floor=0.18,
                                separation_steps=1.25,
                                edge_guard_points=2):
        """Add separated high-residual bins that need not be local maxima.

        Two power-broadened transitions a few MHz apart can merge into one maximum,
        so ``find_peaks`` alone systematically drops the weaker line.  These are only
        *proposals*: every added shoulder still has to survive two opposed, fresh,
        high-resolution scans and the physical complex-line fit.  The global cap keeps
        the confirmation workload identical to the configured candidate budget.
        """
        freqs = np.asarray(freqs, dtype=float)
        snr_trace = np.asarray(features.get("snr_trace", []), dtype=float)
        if freqs.ndim != 1 or snr_trace.shape != freqs.shape or freqs.size < 5:
            return []
        guard = int(np.clip(
            int(edge_guard_points), 1, max((freqs.size - 3) // 2, 1)))
        interior = np.arange(guard + 1, freqs.size - 1 - guard, dtype=int)
        finite = interior[np.isfinite(snr_trace[interior])]
        if not finite.size:
            return []
        strongest = float(np.max(snr_trace[finite]))
        threshold = max(float(min_snr), float(relative_floor) * strongest)
        step = abs(float(np.median(np.diff(freqs))))
        separation = max(float(separation_steps) * step, step)
        selected = [dict(row) for row in existing_rows]
        additions = []
        for index in finite[np.argsort(snr_trace[finite])[::-1]]:
            score = float(snr_trace[index])
            if score < threshold:
                break
            if len(additions) >= max(int(maximum_rows), 1):
                break
            frequency = float(freqs[index])
            if any(abs(frequency - float(row["frequency"])) <= separation
                   for row in selected):
                continue
            row = {
                "frequency": frequency, "index": int(index),
                "score": score, "rank": len(selected),
                "proposal_kind": "shoulder",
            }
            selected.append(row)
            additions.append(row)
        return additions

    @staticmethod
    def _retain_spectral_proposal_mix(rows, maximum_rows,
                                      minimum_shoulders=2):
        """Cap discovery work without letting ordinary peaks crowd every shoulder."""
        ranked = sorted(rows, key=lambda row: float(row["score"]), reverse=True)
        limit = max(int(maximum_rows), 1)
        shoulder_limit = int(np.clip(int(minimum_shoulders), 0, limit))
        chosen = [row for row in ranked
                  if row.get("proposal_kind") == "shoulder"][:shoulder_limit]
        for row in ranked:
            if len(chosen) >= limit:
                break
            if row not in chosen:
                chosen.append(row)
        return sorted(chosen, key=lambda row: float(row["score"]), reverse=True)

    @staticmethod
    def _opposed_provisional_spectral_seed(freqs, passes, pass_features,
                                           center_hint_mhz, capture_mhz,
                                           min_snr=4.0,
                                           min_complex_correlation=0.5):
        """Nonparametric, two-pass basin evidence for an overlapped line.

        This deliberately returns the independently discovered coarse hint rather
        than pretending a shoulder has a trustworthy one-line center.  The following
        Rabi map supplies the coherent frequency estimate; final exact repeated-pulse
        validation remains mandatory for any write.
        """
        freqs = np.asarray(freqs, dtype=float)
        traces = np.asarray(passes, dtype=complex)
        if (freqs.ndim != 1 or traces.shape != (2, freqs.size)
                or len(pass_features) != 2):
            return {"valid": False, "failure": "opposed traces are incomplete"}
        capture = float(capture_mhz)
        basin = np.flatnonzero(
            np.abs(freqs - float(center_hint_mhz)) <= capture)
        if basin.size < 5:
            return {"valid": False, "failure": "provisional basin is too small"}
        step = abs(float(np.median(np.diff(freqs))))
        offset = freqs - float(center_hint_mhz)
        half_span = float(np.max(np.abs(offset)))
        flank = np.flatnonzero(
            np.abs(offset) >= max(capture + 2.0 * step, 0.65 * half_span))
        if flank.size < 8:
            return {"valid": False,
                    "failure": "provisional scan has too little far-off baseline"}
        design = np.column_stack((np.ones(flank.size), offset[flank]))
        pass_snr = []
        residuals = []
        for trace, features in zip(traces, pass_features):
            del features
            coefficients_real = np.linalg.lstsq(
                design, trace.real[flank], rcond=None)[0]
            coefficients_imag = np.linalg.lstsq(
                design, trace.imag[flank], rcond=None)[0]
            full_design = np.column_stack((np.ones(freqs.size), offset))
            baseline = ((full_design @ coefficients_real)
                        + 1j * (full_design @ coefficients_imag))
            residual = np.asarray(trace - baseline, complex)
            noise = max(_robust_scale(np.concatenate((
                residual.real[flank], residual.imag[flank]))), 1e-15)
            pass_snr.append(float(np.max(np.abs(residual[basin])) / noise))
            residuals.append(np.asarray(residual[basin], complex))
        norm = float(np.linalg.norm(residuals[0]) * np.linalg.norm(residuals[1]))
        correlation = (float(abs(np.vdot(residuals[0], residuals[1])) / norm)
                       if norm > 1e-15 else 0.0)
        valid = bool(
            np.all(np.isfinite(pass_snr))
            and min(pass_snr) >= float(min_snr)
            and np.isfinite(correlation)
            and correlation >= float(min_complex_correlation))
        failures = []
        if not np.all(np.isfinite(pass_snr)) or min(pass_snr) < float(min_snr):
            failures.append("opposed point SNR is below threshold")
        if (not np.isfinite(correlation)
                or correlation < float(min_complex_correlation)):
            failures.append("opposed complex response is not correlated")
        return {
            "valid": valid, "failure": "; ".join(failures),
            "frequency_mhz": float(center_hint_mhz),
            "pass_snr": tuple(pass_snr),
            "complex_correlation": correlation,
        }

    @staticmethod
    def _spectral_features(freqs, response, max_candidates=3):
        freqs = np.asarray(freqs, float)
        z = np.asarray(response, complex)
        n = freqs.size
        if n < 9 or z.size != n:
            raise ValueError("invalid spectroscopy trace")
        # A wide Savitzky-Golay curve models slow gain/phase drift.  Spectral lines are
        # ranked by complex distance from that local baseline, independent of whether
        # they appear as a dip, peak, or phase rotation.
        window = min(n if n % 2 else n - 1, max(11, 2 * (n // 8) + 1))
        if window % 2 == 0:
            window -= 1
        if window < 7:
            baseline = np.linspace(z[0], z[-1], n)
        else:
            baseline = (savgol_filter(z.real, window, 2, mode="interp")
                        + 1j * savgol_filter(z.imag, window, 2, mode="interp"))
        residual = np.abs(z - baseline)
        noise = max(_robust_scale(residual), 1e-15)
        floor = float(np.median(residual))
        snr_trace = (residual - floor) / noise
        distance = max(1, n // 40)
        peaks, properties = find_peaks(snr_trace, distance=distance, prominence=1.0)
        if not peaks.size:
            peaks = np.array([int(np.nanargmax(snr_trace))])
            prominences = snr_trace[peaks]
        else:
            prominences = properties.get("prominences", snr_trace[peaks])
        order = peaks[np.argsort(prominences)[::-1]]
        chosen = [int(index) for index in order[:max(int(max_candidates), 1)]]
        return {
            "candidates_mhz": [float(freqs[index]) for index in chosen],
            "candidate_indices": chosen,
            "best_snr": float(np.nanmax(snr_trace)),
            "residual": residual,
            "snr_trace": snr_trace,
            "baseline": baseline,
        }

    @staticmethod
    def _fit_complex_spectral_line(freqs, response, center_hint_mhz,
                                   capture_mhz, min_snr=4.0, min_r2=0.25,
                                   max_linewidth_mhz=8.0,
                                   excluded_centers_mhz=(),
                                   exclusion_half_width_mhz=1.5):
        """Fit physical spectroscopy line hypotheses on a complex background.

        Peak-bin matching is unstable for the several-MHz-wide, power-broadened line
        observed on this device.  A joint I/Q fit uses the whole local profile and
        provides a center uncertainty, linewidth, and background-model improvement.
        Saturation spectroscopy can appear either as a symmetric excited-population
        Lorentzian along one IQ direction or as a dispersive complex pole, depending
        on the pulse/readout regime.  Both equal-parameter hypotheses are fitted; the
        lower-residual one is retained instead of baking one virtual-device line shape
        into the hardware acceptance test.
        The fit is a confirmation/centering primitive only; coherent Rabi and direct
        single-shot measurements still decide whether the line is controllable.
        """
        freqs = np.asarray(freqs, dtype=float)
        response = np.asarray(response, dtype=complex)
        acquired_finite = np.isfinite(freqs) & np.isfinite(response.real) \
            & np.isfinite(response.imag)
        if (freqs.ndim != 1 or response.shape != freqs.shape
                or np.count_nonzero(acquired_finite)
                < max(15, int(0.9 * freqs.size))):
            return {"valid": False, "failure": "incomplete complex line trace"}
        finite = acquired_finite.copy()
        exclusion_half_width = max(float(exclusion_half_width_mhz), 0.0)
        if exclusion_half_width > 0:
            for excluded_center in excluded_centers_mhz:
                try:
                    excluded_center = float(excluded_center)
                except (TypeError, ValueError, OverflowError):
                    continue
                if not np.isfinite(excluded_center):
                    continue
                target_distance = np.abs(freqs - float(center_hint_mhz))
                neighbor_distance = np.abs(freqs - excluded_center)
                # Assign each measured point to its nearest independently detected
                # coarse line (a one-dimensional Voronoi mask).  Merely deleting the
                # neighbor's central bins leaves its broad tails to drag a one-line
                # fit several MHz; the nearest-basin mask retains the target-facing
                # half profile and lets the neighbor tail enter only as smooth
                # background.  Remove the neighbor core as an additional guard.
                finite &= target_distance <= neighbor_distance
                finite &= ~(
                    (neighbor_distance <= exclusion_half_width)
                    & (target_distance > 0.5 * exclusion_half_width))
        if np.count_nonzero(finite) < 15:
            return {"valid": False,
                    "failure": "too few points remain after neighbor masking"}
        x = freqs[finite] - float(center_hint_mhz)
        z = response[finite]
        if x.size < 2 or not np.all(np.diff(x) > 0):
            return {"valid": False, "failure": "line-fit axis is not increasing"}
        capture = float(capture_mhz)
        step = abs(float(np.median(np.diff(x))))
        if not np.isfinite(capture) or capture <= step:
            return {"valid": False, "failure": "line-fit capture range is invalid"}
        design = np.column_stack((np.ones(x.size), x))
        baseline_real = np.linalg.lstsq(design, z.real, rcond=None)[0]
        baseline_imag = np.linalg.lstsq(design, z.imag, rcond=None)[0]
        baseline = (design @ baseline_real) + 1j * (design @ baseline_imag)
        residual = z - baseline
        capture_indices = np.flatnonzero(np.abs(x) <= capture)
        if capture_indices.size < 3:
            return {"valid": False, "failure": "line-fit capture has too few points"}
        strongest = int(capture_indices[
            int(np.nanargmax(np.abs(residual[capture_indices])))])

        def packed_model(kind):
            def model(axis, c0r, c0i, c1r, c1i, ar, ai,
                      center_offset, linewidth):
                normalized = 2.0 * (axis - center_offset) / linewidth
                if kind == "population_lorentzian":
                    profile = 1.0 / (1.0 + normalized * normalized)
                elif kind == "complex_pole":
                    profile = 1.0 / (1.0 + 1j * normalized)
                else:  # pragma: no cover - closed internal model set
                    raise ValueError("unknown spectroscopy line model")
                line = (ar + 1j * ai) * profile
                value = ((c0r + 1j * c0i)
                         + (c1r + 1j * c1i) * axis + line)
                return np.concatenate((value.real, value.imag))
            return model

        target = np.concatenate((z.real, z.imag))
        linewidth_min = max(0.5 * step, 0.02)
        linewidth_max = min(
            float(freqs[finite][-1] - freqs[finite][0]),
            float(max_linewidth_mhz))
        if linewidth_max <= linewidth_min:
            return {"valid": False, "failure": "line-fit linewidth bounds are invalid"}
        lower = np.asarray(
            [-np.inf] * 6 + [-capture, linewidth_min], dtype=float)
        upper = np.asarray(
            [np.inf] * 6 + [capture, linewidth_max], dtype=float)
        center_guesses = [float(x[strongest]), 0.0]
        linewidth_guesses = [
            max(2.0 * step, 0.2), 0.5, 1.0, 2.0, 4.0,
            min(0.8 * linewidth_max, 6.0),
        ]
        best = None
        for model_kind in ("population_lorentzian", "complex_pole"):
            model = packed_model(model_kind)
            for center_guess in center_guesses:
                center_guess = float(np.clip(
                    center_guess, -0.98 * capture, 0.98 * capture))
                for linewidth_guess in linewidth_guesses:
                    linewidth_guess = float(np.clip(
                        linewidth_guess, 1.01 * linewidth_min,
                        0.99 * linewidth_max))
                    normalized = (2.0 * (x[strongest] - center_guess)
                                  / linewidth_guess)
                    profile = (
                        1.0 / (1.0 + normalized * normalized)
                        if model_kind == "population_lorentzian"
                        else 1.0 / (1.0 + 1j * normalized))
                    amplitude = residual[strongest] / profile
                    guess = np.asarray([
                        baseline_real[0], baseline_imag[0],
                        baseline_real[1], baseline_imag[1],
                        amplitude.real, amplitude.imag,
                        center_guess, linewidth_guess,
                    ], dtype=float)
                    try:
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore", OptimizeWarning)
                            fitted, covariance = curve_fit(
                                model, x, target, p0=guess,
                                bounds=(lower, upper), maxfev=20000)
                        fit_target = model(x, *fitted)
                        rss = float(np.sum((target - fit_target) ** 2))
                        if np.isfinite(rss) and (best is None or rss < best[0]):
                            best = (rss, fitted, covariance, fit_target,
                                    model_kind)
                    except (RuntimeError, ValueError, FloatingPointError,
                            np.linalg.LinAlgError):
                        continue
        if best is None:
            return {"valid": False, "failure": "complex line fit did not converge"}
        rss, fitted, covariance, fit_target, model_kind = best
        baseline_target = np.concatenate((baseline.real, baseline.imag))
        baseline_rss = float(np.sum((target - baseline_target) ** 2))
        r2 = float(1.0 - rss / max(baseline_rss, 1e-30))
        dof = max(2 * x.size - fitted.size, 1)
        noise = math.sqrt(max(rss, 0.0) / dof)
        amplitude = float(math.hypot(fitted[4], fitted[5]))
        snr = float(amplitude / max(noise, 1e-15))
        center = float(center_hint_mhz + fitted[6])
        linewidth = float(fitted[7])
        try:
            center_se = float(math.sqrt(max(float(covariance[6, 6]), 0.0)))
        except (IndexError, TypeError, ValueError):
            center_se = np.inf
        bound_margin = max(step, 0.05 * capture)
        interior = bool(abs(float(fitted[6])) <= capture - bound_margin)
        linewidth_interior = bool(
            linewidth > 1.02 * linewidth_min
            and linewidth < 0.98 * linewidth_max)
        valid = bool(
            interior and linewidth_interior
            and np.isfinite(center_se)
            and np.isfinite(snr) and snr >= float(min_snr)
            and np.isfinite(r2) and r2 >= float(min_r2))
        failures = []
        if not interior:
            failures.append("fit center reached the capture boundary")
        if not linewidth_interior:
            failures.append("fit linewidth reached a bound")
        if not np.isfinite(center_se):
            failures.append("fit center uncertainty is nonfinite")
        if not np.isfinite(snr) or snr < float(min_snr):
            failures.append("line SNR %.2f is below %.2f" % (snr, min_snr))
        if not np.isfinite(r2) or r2 < float(min_r2):
            failures.append("line fit r2 %.3f is below %.3f" % (r2, min_r2))
        fitted_complex = (
            fit_target[:x.size] + 1j * fit_target[x.size:])
        return {
            "valid": valid, "failure": "; ".join(failures),
            "frequency_mhz": center, "frequency_se_mhz": center_se,
            "linewidth_mhz": linewidth, "snr": snr, "r2": r2,
            "amplitude": amplitude, "model": model_kind,
            "fit_response": fitted_complex,
            "residual_response": z - fitted_complex,
        }

    @staticmethod
    def _reproduced_spectral_seed(freqs, combined, individual, max_error_mhz,
                                  min_combined_snr):
        """Associate one significant spectral feature across two opposed passes.

        A scan can contain several real or weak spurious features.  Requiring the
        *strongest* feature in pass one to also be strongest in pass two is not a
        reproducibility test: harmless rank swapping then looks like a disappearing
        line.  Match all retained local peaks, require a close pair and significant
        combined evidence, and choose the pair with the strongest weaker pass.
        """
        freqs = np.asarray(freqs, dtype=float)
        if freqs.size == 0 or len(individual) != 2:
            raise RuntimeError("opposed spectroscopy passes are incomplete")
        maximum_error = float(max_error_mhz)
        minimum_combined = float(min_combined_snr)
        minimum_individual = max(1.5, minimum_combined)
        matches = []
        for left_position, left_frequency in enumerate(
                individual[0].get("candidates_mhz", [])):
            left_indices = individual[0].get("candidate_indices", [])
            if left_position >= len(left_indices):
                continue
            left_index = int(left_indices[left_position])
            left_snr = float(individual[0]["snr_trace"][left_index])
            for right_position, right_frequency in enumerate(
                    individual[1].get("candidates_mhz", [])):
                right_indices = individual[1].get("candidate_indices", [])
                if right_position >= len(right_indices):
                    continue
                separation = abs(float(left_frequency) - float(right_frequency))
                if separation > maximum_error:
                    continue
                right_index = int(right_indices[right_position])
                right_snr = float(individual[1]["snr_trace"][right_index])
                centre = 0.5 * (float(left_frequency) + float(right_frequency))
                combined_index = int(np.argmin(np.abs(freqs - centre)))
                combined_snr = float(combined["snr_trace"][combined_index])
                if (not np.all(np.isfinite(
                        [left_snr, right_snr, combined_snr]))
                        or min(left_snr, right_snr) < minimum_individual
                        or combined_snr < minimum_combined):
                    continue
                matches.append({
                    "frequency_mhz": float(centre),
                    "pass_centres_mhz": (
                        float(left_frequency), float(right_frequency)),
                    "pass_snr": (left_snr, right_snr),
                    "combined_snr": combined_snr,
                    "separation_mhz": float(separation),
                })
        if not matches:
            raise RuntimeError(
                "no significant spectral feature reproduced in opposed passes")
        return max(matches, key=lambda row: (
            min(row["pass_snr"]), row["combined_snr"],
            -row["separation_mhz"]))

    def _inverse_pair_map(self, stage, incumbent, params, center_frequency):
        """Acquire one drift-bracketed inverse-pair frequency map.

        The returned ``data_complete`` flag is deliberately stricter than merely
        finding a finite minimum.  A map with one missing point may still nominate a
        candidate for direct replay, but it cannot provide independent coordinate-
        search evidence.  A later stable exact replay of the complete tuple remains
        sufficient for an atomic update.
        """
        calibration_row = self._measure_candidate(
            incumbent, params["calibration_shots"],
            "%s discriminator" % stage)
        calibration = {key: calibration_row[key] for key in
                       ("read_theta", "scale_factor", "threshold")}
        freqs = self._float_axis(
            center_frequency, params["span_mhz"], params["points"],
            include=[center_frequency, incumbent["qubit_pi_freq"]])
        populations = self._acquire_inverse_pair_scan(
            freqs, incumbent, params["shots"], params["pairs"], calibration)
        post_calibration = self._measure_candidate(
            incumbent, params["calibration_shots"],
            "%s discriminator post" % stage,
            reference_discriminator=calibration)
        drift = self._calibration_drift(calibration_row, post_calibration)
        drift_stable = self._calibration_is_stable(drift)
        finite = np.isfinite(populations)
        coverage = float(np.count_nonzero(finite) / max(populations.size, 1))
        self._maps[stage] = {
            "axes": {"qubit_frequency_mhz": freqs},
            "residual_excited_population": populations,
            "pairs": int(params["pairs"]),
            "calibration_drift": drift,
            "calibration_stable": drift_stable,
            "coverage": coverage,
            "data_complete": bool(np.all(finite)),
            "search_complete": False,
            "selection_confirmed": False,
        }
        self._require_stable_calibration(drift, stage)
        if not np.any(finite):
            raise RuntimeError("inverse-pair frequency scan returned no finite data")
        # Searching many frequencies turns an ordinary largest/smallest binomial
        # fluctuation into an apparently structured range.  A 3-sigma pointwise rule
        # is therefore not a valid post-selection information test.  Use the measured
        # two-point uncertainty with a conservative 5-sigma default before allowing
        # the inverse-pair minimum to move or authorize the drive frequency.
        low_index = int(np.nanargmin(populations))
        high_index = int(np.nanargmax(populations))
        shot_count = max(int(params["shots"]), 1)
        point_variance = populations * (1.0 - populations) / shot_count
        point_variance = np.maximum(
            point_variance, 0.25 / float(shot_count + 1) ** 2)
        contrast = float(populations[high_index] - populations[low_index])
        contrast_se = float(math.hypot(
            math.sqrt(float(point_variance[low_index])),
            math.sqrt(float(point_variance[high_index]))))
        contrast_sigma = contrast / max(contrast_se, 1e-12)
        informative = bool(
            np.all(finite) and np.isfinite(contrast_sigma)
            and contrast_sigma >= float(params.get("min_contrast_sigma", 5.0)))
        self._maps[stage].update({
            "map_contrast": contrast,
            "map_contrast_se": contrast_se,
            "map_contrast_sigma": contrast_sigma,
            "information_complete": informative,
        })
        if not informative:
            self._maps[stage]["search_complete"] = False
            raise RuntimeError(
                "inverse-pair frequency response has insufficient post-selection "
                "information (contrast %.2f sigma, require %.2f)"
                % (contrast_sigma,
                   float(params.get("min_contrast_sigma", 5.0))))
        index = low_index
        frequency = self._parabolic_vertex(freqs, populations, index)
        seed = _with_candidate(incumbent, qubit_pi_freq=float(frequency))
        self._record_control_witness(
            stage, frequency, "inverse_pair_pseudoidentity",
            candidate=seed,
            contrast_sigma=float(contrast_sigma),
            pairs=int(params["pairs"]),
        )
        return {
            "stage": stage, "frequencies": freqs,
            "populations": populations, "index": index, "seed": seed,
            "data_complete": bool(np.all(finite)),
        }

    def _parity_map(self, stage, incumbent, params, center_frequency,
                    center_gain, calibration_shots, discriminator_label):
        """Acquire one drift-bracketed odd/even parity map."""
        calibration_row = self._measure_candidate(
            incumbent, int(calibration_shots),
            "%s discriminator" % discriminator_label)
        calibration = {key: calibration_row[key] for key in
                       ("read_theta", "scale_factor", "threshold")}
        freqs = self._float_axis(
            center_frequency, params["freq_span_mhz"], params["freq_points"],
            include=[center_frequency, incumbent["qubit_pi_freq"]])
        fraction = float(params["gain_fraction"])
        gains = self._integer_axis(
            float(center_gain) * (1.0 - fraction),
            float(center_gain) * (1.0 + fraction), params["gain_points"])
        score, populations = self._acquire_parity_chevron(
            freqs, gains, incumbent, params["shots"], params["pulse_counts"],
            calibration)
        post_calibration = self._measure_candidate(
            incumbent, int(calibration_shots),
            "%s discriminator post" % discriminator_label,
            reference_discriminator=calibration)
        drift = self._calibration_drift(calibration_row, post_calibration)
        drift_stable = self._calibration_is_stable(drift)
        finite = np.isfinite(score)
        coverage = float(np.count_nonzero(finite) / max(score.size, 1))
        self._maps[stage] = {
            "axes": {"qubit_frequency_mhz": freqs,
                     "qubit_gain_dac": gains,
                     "pulse_count": np.asarray(params["pulse_counts"], int)},
            "parity_score": score, "excited_populations": populations,
            "calibration_drift": drift,
            "calibration_stable": drift_stable,
            "coverage": coverage,
            "data_complete": bool(np.all(finite)),
            "search_complete": False,
            "selection_confirmed": False,
        }
        self._require_stable_calibration(drift, discriminator_label)
        if not np.any(finite):
            raise RuntimeError("%s returned no finite parity score" % stage)
        index = np.unravel_index(int(np.nanargmax(score)), score.shape)
        # A flat repeated-pulse surface contains no amplitude/frequency information.
        # Its numerical argmax is merely the largest shot-noise fluctuation, and the
        # direct one-pulse replay is intentionally too insensitive to reject a small
        # coherent miscalibration.  Require both a multiple-comparison-resistant map
        # contrast and agreement across the independently amplified pulse depths before
        # the raw optimum may move the control tuple or become write evidence.
        targets = np.asarray(
            [1.0 if int(count) % 2 else 0.0
             for count in params["pulse_counts"]], dtype=float)
        correctness = np.where(
            targets[:, None, None] > 0.5, populations, 1.0 - populations)
        depth_count = max(correctness.shape[0], 1)
        shot_count = max(int(params["shots"]), 1)
        depth_variance = correctness * (1.0 - correctness) / shot_count
        # Avoid zero nominal uncertainty when finite shots happen to observe no errors.
        depth_variance = np.maximum(
            depth_variance, 0.25 / float(shot_count + 1) ** 2)
        cell_se = np.sqrt(np.nansum(depth_variance, axis=0)) / depth_count
        low_index = np.unravel_index(int(np.nanargmin(score)), score.shape)
        contrast = float(score[index] - score[low_index])
        contrast_se = float(math.hypot(
            float(cell_se[index]), float(cell_se[low_index])))
        contrast_sigma = contrast / max(contrast_se, 1e-12)
        winning_depths = np.asarray(correctness[(slice(None),) + index], float)
        depth_median = float(np.nanmedian(winning_depths))
        depth_consistent_fraction = float(np.mean(winning_depths > 0.5))
        informative = bool(
            np.isfinite(contrast_sigma)
            and contrast_sigma >= float(params.get("min_contrast_sigma", 5.0))
            and depth_median >= float(params.get("min_depth_correctness", 0.55))
            and depth_consistent_fraction >= float(params.get(
                "min_consistent_depth_fraction", 0.67)))
        self._maps[stage].update({
            "map_contrast": contrast,
            "map_contrast_se": contrast_se,
            "map_contrast_sigma": contrast_sigma,
            "winning_depth_correctness": winning_depths,
            "winning_depth_median": depth_median,
            "winning_depth_consistent_fraction": depth_consistent_fraction,
            "information_complete": informative,
        })
        if not informative:
            self._maps[stage]["search_complete"] = False
            raise RuntimeError(
                "%s has insufficient repeated-pulse information "
                "(contrast %.2f sigma, median depth correctness %.3f, "
                "consistent depths %.0f%%)"
                % (stage, contrast_sigma, depth_median,
                   100.0 * depth_consistent_fraction))
        seed = _with_candidate(
            incumbent, qubit_pi_freq=float(freqs[index[0]]),
            qubit_pi_gain=int(gains[index[1]]))
        self._record_control_witness(
            stage, seed["qubit_pi_freq"], "odd_even_repeated_pulses",
            candidate=seed,
            contrast_sigma=float(contrast_sigma),
            depth_median=float(depth_median),
            consistent_depth_fraction=float(depth_consistent_fraction),
        )
        return {
            "stage": stage, "frequencies": freqs, "gains": gains,
            "score": score, "populations": populations,
            "index": index, "seed": seed,
            "data_complete": bool(np.all(finite)),
        }

    def _quantize_joint_proposals(self, proposals, center,
                                  read_radius, qubit_radius):
        """Project surrogate proposals onto a small reusable frequency lattice."""
        p = self.params["joint_search"]
        read_axis = np.linspace(
            float(center["read_pulse_freq"]) - float(read_radius),
            float(center["read_pulse_freq"]) + float(read_radius),
            max(int(p.get("trust_read_frequency_points", 5)), 1))
        qubit_axis = np.linspace(
            float(center["qubit_pi_freq"]) - float(qubit_radius),
            float(center["qubit_pi_freq"]) + float(qubit_radius),
            max(int(p.get("trust_qubit_frequency_points", 7)), 1))
        projected = []
        for raw in proposals:
            candidate = _with_candidate(
                raw,
                read_pulse_freq=float(read_axis[int(np.argmin(
                    np.abs(read_axis - float(raw["read_pulse_freq"]))))]),
                qubit_pi_freq=float(qubit_axis[int(np.argmin(
                    np.abs(qubit_axis - float(raw["qubit_pi_freq"]))))]),
            )
            projected.append(candidate)
        return _unique_candidates(projected)

    # --------------------------------------------------------------------- stages
    def _stage_joint_search(self):
        """Structured four-dimensional search plus held-out local refinement."""
        p = self.params["joint_search"]
        if not p.get("enabled", True):
            self.data["joint_search"]["status"] = "disabled"
            return None
        if (self._discovery_guard_active
                and (self._qualified_transition_frequency is None
                     or not self._candidate_in_qualified_transition(self.working))):
            raise RuntimeError(
                "joint search cannot start without a repeated-pulse-qualified "
                "transition")
        self._joint_search_started_monotonic = time.monotonic()
        base = dict(self.working)
        read_lengths = np.asarray(sorted(set(
            float(value) for value in p["read_lengths_us"]
            if np.isfinite(float(value)) and float(value) > 0.0)), dtype=float)
        sigmas = np.asarray(sorted(set(
            float(value) for value in p["sigma_values_us"]
            if np.isfinite(float(value)) and float(value) > 0.0)), dtype=float)
        if not read_lengths.size or not sigmas.size:
            raise ValueError("joint search needs positive readout and pulse durations")
        read_gains = self._gain_axis(
            p["read_gain_min"], p["read_gain_max"], p["read_gain_points"])
        # Preserve every member of the input-independent broad backbone.  A useful
        # in-range starting gain is one additional measurement, never a replacement
        # which can silently delete a better power from the grid.
        base_read_gain = int(round(base["read_pulse_gain"]))
        if (int(p["read_gain_min"]) <= base_read_gain
                <= int(p["read_gain_max"])):
            read_gains = np.sort(np.unique(np.append(
                read_gains, base_read_gain))).astype(int)
        gain_points = max(int(p["qubit_gain_points_including_ground"]), 5)
        jobs = duration_balanced_joint_jobs(
            read_lengths, sigmas, read_gains, self.rng)
        strata_per_pass = int(read_lengths.size * sigmas.size)
        minimum_passes = min(
            max(int(p.get("minimum_duration_coverage_passes", 1)), 1),
            int(read_gains.size))
        mandatory_passes_requested = int(minimum_passes)
        mandatory_passes_granted = int(minimum_passes)
        mandatory_jobs = int(minimum_passes * strata_per_pass)
        coarse_tail_reserve = (
            float(p.get("reserve_medium_minutes", 6.0))
            + float(p.get("reserve_control_refinement_minutes", 7.0)))
        pass_started_monotonic = time.monotonic()
        pass_minutes = []
        coarse_rows, failures = [], []
        resumed_rows = list(self.data["joint_search"].get(
            "resumed_coarse_rows", []))
        resumed_cells = 0
        epoch = 0
        anchor, _ = self._joint_anchor_probe(
            base, max(int(p["coarse_shots"]), 80),
            "joint-search anchor epoch 0")
        anchor_interval = max(strata_per_pass, 1)
        completed_jobs = 0
        for serial, job in enumerate(jobs):
            if serial and serial % strata_per_pass == 0:
                boundary = time.monotonic()
                pass_minutes.append(
                    float((boundary - pass_started_monotonic) / 60.0))
                pass_started_monotonic = boundary
                completed_passes = int(serial // strata_per_pass)
                if (completed_passes < mandatory_passes_granted
                        and not self._joint_budget_allows(
                            reserve_final=True,
                            additional_reserve_minutes=(
                                coarse_tail_reserve
                                + float(np.mean(pass_minutes))))):
                    mandatory_passes_granted = completed_passes
                    mandatory_jobs = int(completed_passes * strata_per_pass)
                    self._log(
                        "joint_search", "WARN",
                        "measured %.1f min per duration-coverage pass; granting %d "
                        "of %d mandatory readout-power passes so the held-out "
                        "medium/trust refinement keeps its reserved budget"
                        % (float(np.mean(pass_minutes)), completed_passes,
                           mandatory_passes_requested))
            # Complete the mandatory duration-balanced pass even if a slow backend
            # crosses the soft estimate while that pass is in flight.  Only later
            # readout-power passes are optional.
            if (serial >= mandatory_jobs
                    and not self._joint_budget_allows(
                        reserve_final=True,
                        additional_reserve_minutes=coarse_tail_reserve)):
                break
            read_length, sigma, read_gain, _gain_pass = job
            candidate = _with_candidate(
                base, read_length=read_length, read_pulse_gain=read_gain,
                sigma=sigma)
            self._ensure_reset_profile(
                candidate, "joint search %.1f us" % read_length)
            expected_pi = (float(base["qubit_pi_gain"])
                           * float(base["sigma"]) / sigma)
            maximum = int(np.clip(round(
                float(p["qubit_gain_max_scale"]) * expected_pi),
                gain_points - 1, int(p["qubit_gain_hard_max"])))
            step = max(int(round(maximum / float(gain_points - 1))), 1)
            gains = step * np.arange(gain_points, dtype=int)
            gains = gains[gains <= int(p["qubit_gain_hard_max"])]
            if gains.size < 3:
                failures.append({"job": job[:3],
                                 "error": "gain axis collapsed"})
                completed_jobs += 1
                continue
            prior = [row for row in resumed_rows
                     if np.isclose(float(row.get("read_length", np.nan)), read_length)
                     and np.isclose(float(row.get("sigma", np.nan)), sigma)
                     and int(round(float(row.get("read_pulse_gain", -1)))) == read_gain
                     and np.isclose(float(row.get("read_pulse_freq", np.nan)),
                                    float(candidate["read_pulse_freq"]), atol=1e-9)
                     and np.isclose(float(row.get("qubit_pi_freq", np.nan)),
                                    float(candidate["qubit_pi_freq"]), atol=1e-9)]
            prior_gains = {int(round(float(row.get("qubit_pi_gain", -1))))
                           for row in prior}
            if set(int(value) for value in gains[1:]).issubset(prior_gains):
                coarse_rows.extend([
                    row for row in prior
                    if int(round(float(row["qubit_pi_gain"]))) in set(gains[1:])])
                resumed_cells += 1
                completed_jobs += 1
                continue
            try:
                coarse_rows.extend(self._acquire_joint_gain_sweep(
                    candidate, gains, int(p["coarse_shots"]),
                    "joint coarse L%.1f S%.3f R%d" % (
                        read_length, sigma, read_gain), epoch=epoch))
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                failures.append({
                    "job": job[:3],
                    "error": "%s: %s" % (type(exc).__name__, exc),
                })
            completed_jobs += 1
            if ((serial + 1) % anchor_interval == 0
                    and self._joint_budget_allows(
                        reserve_final=True,
                        additional_reserve_minutes=coarse_tail_reserve)):
                new_anchor, drifted = self._joint_anchor_probe(
                    base, max(int(p["coarse_shots"]), 80),
                    "joint-search anchor check", previous=anchor)
                if drifted:
                    epoch += 1
                anchor = new_anchor
        coverage = validate_structured_coverage(
            coarse_rows, read_lengths, sigmas)
        record = self.data["joint_search"]
        record.update({
            "status": "coarse_complete" if coverage["complete"] else "coarse_partial",
            "coarse_rows": coarse_rows,
            "coarse_row_count": len(coarse_rows),
            "coarse_failures": failures,
            "resumed_coarse_cells": int(resumed_cells),
            "coverage": coverage,
            "read_lengths_us": read_lengths,
            "sigma_values_us": sigmas,
            "read_gains_dac": read_gains,
            "read_gain_pass_order_dac": np.asarray([
                jobs[index * strata_per_pass][2]
                for index in range(len(read_gains))], dtype=int),
            "mandatory_duration_passes": int(mandatory_passes_granted),
            "mandatory_duration_passes_requested": int(
                mandatory_passes_requested),
            "mandatory_coverage_reduced_for_budget": bool(
                mandatory_passes_granted < mandatory_passes_requested),
            "coarse_pass_minutes": list(pass_minutes),
            "coarse_cells_attempted": int(completed_jobs),
            "coarse_gain_passes_completed": int(
                completed_jobs // max(strata_per_pass, 1)),
            "drift_epochs": int(epoch + 1),
            "runtime_minutes_after_coarse": self._joint_runtime_minutes(),
        })
        if not coarse_rows:
            raise RuntimeError("joint search completed no coarse measurements")

        medium_seeds = duration_stratified_shortlist(
            coarse_rows,
            per_stratum=int(p["medium_per_duration_pair"]),
            global_count=int(p["medium_global_count"]),
            maximum=int(p["medium_max_candidates"]),
        )
        medium_candidates = [
            PulseCandidate.from_mapping(row).as_dict() for row in medium_seeds]
        control_reserve = float(p.get(
            "reserve_control_refinement_minutes", 7.0))
        if self._joint_budget_allows(
                reserve_final=True,
                additional_reserve_minutes=control_reserve):
            medium_rows = self._confirm_candidates(
                medium_candidates + [base], int(p["medium_shots"]),
                int(p["medium_blocks"]), "joint medium held-out",
                add_to_history=True)
        else:
            medium_rows = []
        record["medium_rows"] = medium_rows
        record["medium_candidate_count"] = len(medium_candidates)
        candidate_pool = list(medium_rows) or list(coarse_rows)

        read_radius = float(p["trust_read_frequency_radius_mhz"])
        qubit_radius = float(p["trust_qubit_frequency_radius_mhz"])
        limits = {
            "read_pulse_freq": (
                float(base["read_pulse_freq"]) - read_radius,
                float(base["read_pulse_freq"]) + read_radius),
            "read_pulse_gain": (
                int(p["read_gain_min"]), int(p["read_gain_max"])),
            "read_length": (float(read_lengths[0]), float(read_lengths[-1])),
            "qubit_pi_freq": (
                float(base["qubit_pi_freq"]) - qubit_radius,
                float(base["qubit_pi_freq"]) + qubit_radius),
            "qubit_pi_gain": (1, int(p["qubit_gain_hard_max"])),
            "sigma": (float(sigmas[0]), float(sigmas[-1])),
        }
        proposals = propose_trust_region_candidates(
            coarse_rows + list(medium_rows), rng=self.rng,
            count=int(p["trust_proposals"]), proposal_limits=limits,
            read_frequency_radius_mhz=read_radius,
            qubit_frequency_radius_mhz=qubit_radius,
            read_gain_fraction=float(p["trust_read_gain_fraction"]),
            qubit_gain_fraction=float(p["trust_qubit_gain_fraction"]),
            trust_regions=int(p["trust_regions"]),
            pool_size=int(p["trust_pool_size"]),
        )
        proposals = self._quantize_joint_proposals(
            proposals, base, read_radius, qubit_radius)
        proposals = self._qualified_transition_rows(proposals)
        for candidate in proposals:
            if self._joint_budget_allows(
                    reserve_final=True,
                    additional_reserve_minutes=control_reserve):
                self._ensure_reset_profile(candidate, "joint trust-region proposal")
        if (proposals and self._joint_budget_allows(
                reserve_final=True,
                additional_reserve_minutes=control_reserve)):
            trust_rows = self._confirm_candidates(
                proposals, int(p["trust_shots"]), int(p["trust_blocks"]),
                "joint trust-region held-out", add_to_history=True)
        else:
            trust_rows = []
        record.update({
            "trust_proposals": proposals,
            "trust_rows": trust_rows,
            "runtime_minutes_after_search": self._joint_runtime_minutes(),
        })
        candidate_pool.extend(trust_rows)
        best = max(candidate_pool, key=self._joint_rank)
        self._adopt(best, "joint_search")
        record["selected"] = copy.deepcopy(best)
        record["status"] = (
            "complete" if coverage["complete"] and medium_rows else
            "partial_with_candidate")
        duration_best = np.full((read_lengths.size, sigmas.size), np.nan)
        for row in coarse_rows:
            li = int(np.argmin(np.abs(read_lengths - float(row["read_length"]))))
            si = int(np.argmin(np.abs(sigmas - float(row["sigma"]))))
            score = fidelity_evidence(row)[0]
            if (not np.isfinite(duration_best[li, si])
                    or score > duration_best[li, si]):
                duration_best[li, si] = score
        self._maps["joint_search"] = {
            "axes": {"read_length_us": read_lengths, "sigma_us": sigmas},
            "duration_best_fidelity": duration_best,
            "search_complete": bool(coverage["complete"] and medium_rows),
            "selection_confirmed": bool(medium_rows),
            "coverage": coverage,
            "coarse_candidate_count": len(coarse_rows),
            "medium_candidate_count": len(medium_rows),
            "trust_candidate_count": len(trust_rows),
        }
        self._record_key_evidence(
            TUNED_KEYS, "joint_search",
            bool(coverage["complete"] and medium_rows))
        self._joint_rows = list(coarse_rows) + list(medium_rows) + list(trust_rows)
        return best

    def _stage_multi_candidate_aae(self):
        """Run frequency/AAE closure from several measured control basins."""
        p = self.params["joint_search"]
        pool = sorted(
            self._qualified_transition_rows(self._confirmed),
            key=self._joint_rank, reverse=True)
        seeds, seen_controls = [], set()
        for row in pool:
            key = _control_key(row)
            if key in seen_controls:
                continue
            seen_controls.add(key)
            seeds.append({name: row[name] for name in self.initial})
            if len(seeds) >= max(int(p.get("trust_regions", 6)) // 2, 2):
                break
        if not seeds:
            seeds = [dict(self.working)]
        refined, original = [], dict(self.working)
        for index, seed in enumerate(seeds):
            if not self._joint_budget_allows(reserve_final=True):
                break
            self.working = dict(seed)
            self._ensure_reset_profile(
                self.working, "AAE control basin %d" % (index + 1))
            try:
                self._stage_fine_frequency(
                    "joint_aae_frequency_%d" % (index + 1))
                self._stage_amplified_error()
                if self._candidate_in_qualified_transition(self.working):
                    refined.append(dict(self.working))
                else:
                    self._log(
                        "multi_aae", "WARN",
                        "control basin %d refinement left the qualified transition; "
                        "discarding it" % (index + 1))
                    self.working = dict(seed)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                self._log("multi_aae", "WARN", "control basin %d failed (%s: %s)"
                          % (index + 1, type(exc).__name__, exc))
        self.working = dict(original)
        candidates = _unique_candidates(refined + seeds + [original])
        if not candidates:
            self.working = original
            return None
        confirmed = self._confirm_candidates(
            candidates, int(self.params["amplified_error"]["confirm_shots"]),
            int(self.params["amplified_error"]["confirm_blocks"]),
            "multi-basin AAE exact replay", add_to_history=True)
        best = max(confirmed, key=self._joint_rank)
        self._adopt(best, "multi_aae")
        self.data["joint_search"]["aae_candidates"] = confirmed
        return best

    def _stage_joint_closure(self, iteration):
        """Reopen a small coupled neighborhood after AAE changes the control."""
        p = self.params["joint_search"]
        source = self._qualified_transition_rows(
            list(self._joint_rows) + list(self._confirmed))
        if not source or not self._joint_budget_allows(reserve_final=True):
            return None
        scale = float(p.get("closure_frequency_radius_scale", 0.55))
        gain_scale = float(p.get("closure_gain_radius_scale", 0.60))
        base = (dict(self.working)
                if self._candidate_in_qualified_transition(self.working)
                else dict(max(source, key=self._joint_rank)))
        read_radius = scale * float(p["trust_read_frequency_radius_mhz"])
        qubit_radius = scale * float(p["trust_qubit_frequency_radius_mhz"])
        qualified_radius = float(self.params["parity_chevron"].get(
            "qualified_basin_radius_mhz", 2.0))
        qualified_center = self._qualified_transition_frequency
        qualified_lower = (-np.inf if qualified_center is None else
                           float(qualified_center) - qualified_radius)
        qualified_upper = (np.inf if qualified_center is None else
                           float(qualified_center) + qualified_radius)
        limits = {
            "read_pulse_freq": (base["read_pulse_freq"] - read_radius,
                                base["read_pulse_freq"] + read_radius),
            "read_pulse_gain": (int(p["read_gain_min"]),
                                int(p["read_gain_max"])),
            "read_length": (min(p["read_lengths_us"]),
                            max(p["read_lengths_us"])),
            "qubit_pi_freq": (
                max(base["qubit_pi_freq"] - qubit_radius,
                    qualified_lower),
                min(base["qubit_pi_freq"] + qubit_radius,
                    qualified_upper)),
            "qubit_pi_gain": (1, int(p["qubit_gain_hard_max"])),
            "sigma": (min(p["sigma_values_us"]), max(p["sigma_values_us"])),
        }
        proposals = propose_trust_region_candidates(
            source, rng=self.rng,
            count=max(int(p["trust_proposals"]) // 2, 8),
            proposal_limits=limits,
            read_frequency_radius_mhz=read_radius,
            qubit_frequency_radius_mhz=qubit_radius,
            read_gain_fraction=gain_scale * float(p["trust_read_gain_fraction"]),
            qubit_gain_fraction=gain_scale * float(p["trust_qubit_gain_fraction"]),
            trust_regions=max(int(p["trust_regions"]) // 2, 2),
            pool_size=max(int(p["trust_pool_size"]) // 2, 1000),
        )
        proposals = self._quantize_joint_proposals(
            proposals, base, read_radius, qubit_radius)
        proposals = self._qualified_transition_rows(proposals)
        for candidate in proposals:
            self._ensure_reset_profile(
                candidate, "joint closure %d" % int(iteration))
        if not proposals:
            return None
        confirmed = self._confirm_candidates(
            proposals + [base], int(p["trust_shots"]),
            int(p["trust_blocks"]),
            "joint closure %d held-out" % int(iteration),
            add_to_history=True)
        direct = max(confirmed, key=self._joint_rank)
        best = self._noninferior_seed(confirmed, base, direct, margin=0.003)
        self._adopt(best, "joint_closure_%d" % int(iteration))
        self.data["joint_search"]["closure_rounds"].append({
            "iteration": int(iteration), "proposals": proposals,
            "confirmations": confirmed, "selected": copy.deepcopy(best),
        })
        self._joint_rows.extend(confirmed)
        return best

    def _stage_baseline(self):
        p = self.params["baseline"]
        rows = self._confirm_candidates(
            [self.initial], p["shots"], p["blocks"], "exact input tuple")
        best = rows[0]
        self._adopt(best, "baseline")
        self._log("baseline", "OK",
                  "exact step-5 replay measured; low fidelity does not gate the search")
        return best

    def _stage_resonator(self):
        """Confirm every credible notch before spectroscopy chooses a branch."""
        p = self.params["resonator"]
        if not p.get("enabled", True):
            self._log("resonator", "SKIP", "disabled")
            return None
        plan = self._frequency_discovery_plan(
            self.initial["read_pulse_freq"], p, adaptive=True)
        # Discovery must inspect the complete authorized envelope.  Stopping after a
        # valid feature in an inner shell is exactly how a stronger unrelated notch
        # hid the target resonator in the previous implementation.
        coarse_axis = np.asarray(plan["axes"][-1], dtype=float)
        accept_min, accept_max = map(float, plan["acceptance_bounds"][-1])
        bounded = bool(plan["configured_envelope"])
        safe = _with_candidate(
            self.working,
            read_pulse_gain=int(np.clip(round(p.get(
                "discovery_gain", self.working["read_pulse_gain"])), 1, 32767)),
            read_length=max(float(p.get(
                "discovery_length_us", self.working["read_length"])), 0.1),
        )
        # A deliberately bad input gain is only a fallback.  Once the known-safe
        # discovery pulse reveals confirmed candidates, repeating a 200-MHz scan at
        # the bad input power adds time without improving branch identity.
        trial_candidates = _unique_candidates([safe, self.working])
        confirmation_points = max(int(p.get("confirmation_points", 81)), 9)
        confirmation_span = float(p.get("confirmation_span_mhz", 4.0))
        shift_limit = float(p.get("max_confirmation_shift_mhz", 0.25))
        width_ratio_limit = float(p.get(
            "max_confirmation_width_ratio", 2.5))
        trials, confirmed = [], []
        for trial_index, trial in enumerate(trial_candidates):
            try:
                response = self._acquire_transmission(
                    coarse_axis, trial, int(p["shots"]))
                features = self._resonator_features(
                    coarse_axis, response,
                    polarity=p.get("polarity", "dip"),
                    edge_guard_points=p.get("edge_guard_points", 2),
                    min_snr=p.get("min_contrast_snr", 3.0),
                    min_relative_contrast=p.get(
                        "min_relative_contrast", 0.002),
                    min_feature_width_mhz=p.get(
                        "min_feature_width_mhz", 0.04),
                    max_feature_width_mhz=p.get(
                        "max_feature_width_mhz", 2.0),
                    max_candidates=p.get("max_candidates", 8),
                    min_candidate_separation_mhz=p.get(
                        "min_candidate_separation_mhz", 1.0))
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                trials.append({
                    "candidate": dict(trial), "axis": coarse_axis,
                    "acceptance_bounds_mhz": (accept_min, accept_max),
                    "response": None, "feature": None,
                    "confirmation_axis": None,
                    "confirmation_response": None,
                    "confirmation_feature": None,
                    "confirmation_shift_mhz": np.inf,
                    "confirmation_width_ratio": np.inf,
                    "confirmation_valid": False,
                    "error": "%s: %s" % (type(exc).__name__, exc),
                    "trial_index": int(trial_index),
                })
                continue
            if not features:
                trials.append({
                    "candidate": dict(trial), "axis": coarse_axis,
                    "acceptance_bounds_mhz": (accept_min, accept_max),
                    "response": np.asarray(response, complex), "feature": None,
                    "confirmation_axis": None,
                    "confirmation_response": None,
                    "confirmation_feature": None,
                    "confirmation_shift_mhz": np.inf,
                    "confirmation_width_ratio": np.inf,
                    "confirmation_valid": False,
                    "error": "no valid interior notch", "trial_index": int(trial_index),
                })
            for coarse_feature in features:
                coarse_seed = float(coarse_feature["frequency_mhz"])
                row = {
                    "candidate": dict(trial), "axis": coarse_axis,
                    "acceptance_bounds_mhz": (accept_min, accept_max),
                    "response": np.asarray(response, complex),
                    "feature": coarse_feature,
                    "confirmation_axis": None,
                    "confirmation_response": None,
                    "confirmation_feature": None,
                    "confirmation_shift_mhz": np.inf,
                    "confirmation_width_ratio": np.inf,
                    "confirmation_valid": False, "error": None,
                    "trial_index": int(trial_index),
                }
                if not accept_min <= coarse_seed <= accept_max:
                    row["error"] = "candidate lies only in scan padding"
                    trials.append(row)
                    continue
                try:
                    confirmation_axis = self._contained_centered_axis(
                        coarse_seed, confirmation_span, confirmation_points,
                        lower=float(coarse_axis[0]) if bounded else None,
                        upper=float(coarse_axis[-1]) if bounded else None)
                    confirmation_response = self._acquire_transmission(
                        confirmation_axis, trial,
                        int(p.get("confirmation_shots", p["shots"])))
                    local_features = self._resonator_features(
                        confirmation_axis, confirmation_response,
                        polarity=p.get("polarity", "dip"),
                        edge_guard_points=p.get("edge_guard_points", 2),
                        min_snr=p.get("min_contrast_snr", 3.0),
                        min_relative_contrast=p.get(
                            "min_relative_contrast", 0.002),
                        min_feature_width_mhz=p.get(
                            "min_feature_width_mhz", 0.04),
                        max_feature_width_mhz=p.get(
                            "max_feature_width_mhz", 2.0),
                        max_candidates=3,
                        min_candidate_separation_mhz=p.get(
                            "min_candidate_separation_mhz", 1.0))
                    if not local_features:
                        raise RuntimeError("local confirmation found no valid notch")
                    confirmation_feature = min(
                        local_features,
                        key=lambda item: abs(
                            float(item["frequency_mhz"]) - coarse_seed))
                    confirmed_seed = float(
                        confirmation_feature["frequency_mhz"])
                    shift = abs(confirmed_seed - coarse_seed)
                    coarse_width = float(coarse_feature["feature_width_mhz"])
                    confirmation_width = float(
                        confirmation_feature["feature_width_mhz"])
                    width_ratio = max(coarse_width, confirmation_width) / max(
                        min(coarse_width, confirmation_width), 1e-15)
                    valid = bool(
                        accept_min <= confirmed_seed <= accept_max
                        and shift <= shift_limit
                        and width_ratio <= width_ratio_limit + 1e-9)
                    row.update({
                        "confirmation_axis": confirmation_axis,
                        "confirmation_response": np.asarray(
                            confirmation_response, complex),
                        "confirmation_feature": confirmation_feature,
                        "confirmation_shift_mhz": float(shift),
                        "confirmation_width_ratio": float(width_ratio),
                        "confirmation_valid": valid,
                    })
                    if not valid:
                        row["error"] = (
                            "coarse/local notch identity changed "
                            "(shift %.3f MHz, width ratio %.2fx)"
                            % (shift, width_ratio))
                    else:
                        confirmed.append(row)
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    row["error"] = "%s: %s" % (type(exc).__name__, exc)
                trials.append(row)
            if confirmed:
                break

        # Deduplicate the same notch proposed in neighboring coarse bins or powers.
        confirmed.sort(key=lambda row: (
            float(row["confirmation_feature"]["contrast_snr"]),
            float(row["confirmation_feature"]["relative_contrast"])),
            reverse=True)
        retained = []
        merge_tolerance = max(
            float(p.get("max_confirmation_shift_mhz", 0.25)) * 2.0,
            0.5 * float(p.get("min_candidate_separation_mhz", 1.0)))
        for row in confirmed:
            frequency = float(row["confirmation_feature"]["frequency_mhz"])
            if any(abs(frequency - float(old["confirmation_feature"][
                    "frequency_mhz"])) <= merge_tolerance for old in retained):
                continue
            retained.append(row)
            if len(retained) >= max(int(p.get("max_candidates", 8)), 1):
                break
        if not retained:
            failures = [row.get("error") for row in trials if row.get("error")]
            reason = "; ".join(failures) or "all resonator acquisitions failed"
            self._maps["resonator"] = {
                "axes": {"read_frequency_mhz": coarse_axis,
                         "confirmation_frequency_mhz": np.empty((0,), float)},
                "search_complete": False, "selection_confirmed": False,
                "used_global_scan": bool(bounded), "used_wide_scan": True,
                "search_mode": plan["mode"],
                "allowed_min_mhz": float(plan["allowed_min_mhz"]),
                "allowed_max_mhz": float(plan["allowed_max_mhz"]),
                "candidate_frequencies_mhz": np.empty((0,), float),
                "trial_valid": np.asarray([
                    row["confirmation_valid"] for row in trials], dtype=bool),
                "trial_confirmation_valid": np.asarray([
                    row["confirmation_valid"] for row in trials], dtype=bool),
                "trial_gain_dac": np.asarray([
                    row["candidate"]["read_pulse_gain"] for row in trials],
                    dtype=int),
                "trial_length_us": np.asarray([
                    row["candidate"]["read_length"] for row in trials],
                    dtype=float),
                "search_attempt_scan_bounds_mhz": np.asarray([
                    [float(coarse_axis[0]), float(coarse_axis[-1])]
                    for _row in trials], dtype=float).reshape((-1, 2)),
                "search_attempt_acceptance_bounds_mhz": np.asarray([
                    [accept_min, accept_max] for _row in trials],
                    dtype=float).reshape((-1, 2)),
                "failure": reason,
            }
            raise RuntimeError(
                "no independently reproduced resonator feature in %.3f..%.3f MHz (%s)"
                % (plan["allowed_min_mhz"], plan["allowed_max_mhz"], reason))

        # This is only a provisional branch for backward-compatible plotting.  Every
        # retained branch is passed to spectroscopy below, which is the first identity
        # decision allowed to set selection_confirmed when several notches exist.
        provisional = min(
            retained,
            key=lambda row: abs(float(row["confirmation_feature"][
                "frequency_mhz"]) - float(self.initial["read_pulse_freq"])))
        feature = provisional["feature"]
        confirmation = provisional["confirmation_feature"]
        seed = float(confirmation["frequency_mhz"])
        self._resonator_candidates = [
            _with_candidate(
                row["candidate"], read_pulse_freq=float(
                    row["confirmation_feature"]["frequency_mhz"]))
            for row in retained]
        self._resonator_branch_records = retained
        self._resonator_seed = seed
        self._discovery_readout = _with_candidate(
            provisional["candidate"], read_pulse_freq=seed)
        self._discovery_status["resonator"] = True
        self._maps["resonator"] = {
            "axes": {
                "read_frequency_mhz": coarse_axis,
                "confirmation_frequency_mhz": np.asarray([
                    row["confirmation_axis"] for row in retained], dtype=float),
            },
            "magnitude": feature["magnitude"],
            "smoothed_magnitude": feature["smoothed_magnitude"],
            "baseline_magnitude": feature["baseline_magnitude"],
            "feature": feature["smoothed_feature"],
            "complex_response": provisional["response"],
            "contrast_snr": float(feature["contrast_snr"]),
            "relative_contrast": float(feature["relative_contrast"]),
            "feature_width_mhz": float(feature["feature_width_mhz"]),
            "candidate_at_boundary": bool(feature["at_boundary"]),
            "confirmation_magnitude": confirmation["magnitude"],
            "confirmation_feature": confirmation["smoothed_feature"],
            "confirmation_complex_response": provisional[
                "confirmation_response"],
            "confirmation_contrast_snr": float(
                confirmation["contrast_snr"]),
            "confirmation_relative_contrast": float(
                confirmation["relative_contrast"]),
            "confirmation_width_mhz": float(
                confirmation["feature_width_mhz"]),
            "confirmation_at_boundary": bool(confirmation["at_boundary"]),
            "confirmation_shift_mhz": float(
                provisional["confirmation_shift_mhz"]),
            "confirmation_width_ratio": float(
                provisional["confirmation_width_ratio"]),
            "candidate_frequencies_mhz": np.asarray([
                row["confirmation_feature"]["frequency_mhz"]
                for row in retained], dtype=float),
            "candidate_contrast_snr": np.asarray([
                row["confirmation_feature"]["contrast_snr"]
                for row in retained], dtype=float),
            "candidate_relative_contrast": np.asarray([
                row["confirmation_feature"]["relative_contrast"]
                for row in retained], dtype=float),
            "selected_frequency_mhz": seed,
            "provisional_selection": bool(len(retained) > 1),
            "search_complete": True,
            "selection_confirmed": bool(len(retained) == 1),
            "used_global_scan": bool(bounded), "used_wide_scan": True,
            "search_mode": plan["mode"],
            "allowed_min_mhz": float(plan["allowed_min_mhz"]),
            "allowed_max_mhz": float(plan["allowed_max_mhz"]),
            "search_attempt_scan_bounds_mhz": np.asarray([
                [float(coarse_axis[0]), float(coarse_axis[-1])]
                for _row in trials], dtype=float).reshape((-1, 2)),
            "search_attempt_acceptance_bounds_mhz": np.asarray([
                [accept_min, accept_max] for _row in trials],
                dtype=float).reshape((-1, 2)),
            "bootstrap_gain_dac": int(provisional["candidate"][
                "read_pulse_gain"]),
            "bootstrap_length_us": float(provisional["candidate"][
                "read_length"]),
            "trial_gain_dac": np.asarray([
                row["candidate"]["read_pulse_gain"] for row in trials], dtype=int),
            "trial_length_us": np.asarray([
                row["candidate"]["read_length"] for row in trials], dtype=float),
            "trial_contrast_snr": np.asarray([
                row["feature"]["contrast_snr"]
                if row.get("feature") is not None else np.nan
                for row in trials], dtype=float),
            "trial_relative_contrast": np.asarray([
                row["feature"]["relative_contrast"]
                if row.get("feature") is not None else np.nan
                for row in trials], dtype=float),
            "trial_feature_width_mhz": np.asarray([
                row["feature"]["feature_width_mhz"]
                if row.get("feature") is not None else np.nan
                for row in trials], dtype=float),
            "trial_confirmation_valid": np.asarray([
                row["confirmation_valid"] for row in trials], dtype=bool),
            "trial_valid": np.asarray([
                row["confirmation_valid"] for row in trials], dtype=bool),
            "trial_confirmation_shift_mhz": np.asarray([
                row["confirmation_shift_mhz"] for row in trials], dtype=float),
            "trial_confirmation_width_ratio": np.asarray([
                row["confirmation_width_ratio"] for row in trials], dtype=float),
        }
        self._log(
            "resonator", "OK",
            "confirmed resonator candidates %s; spectroscopy will select the branch"
            % ", ".join("%.6f" % float(candidate["read_pulse_freq"])
                        for candidate in self._resonator_candidates))
        return seed

    def _stage_spectroscopy(self):
        """Evaluate confirmed resonator branches and backtrack failed ones."""
        p = self.params["spectroscopy"]
        branches = _unique_candidates(
            self._resonator_candidates or [self._discovery_readout])
        if not p.get("enabled", True) or len(branches) <= 1:
            result = self._stage_spectroscopy_single(
                branches[0] if branches else self._discovery_readout,
                map_name="spectroscopy")
            if result and branches:
                selected = dict(branches[0])
                self._discovery_readout = selected
                self._resonator_seed = float(selected["read_pulse_freq"])
                self._maps.get("resonator", {})["selection_confirmed"] = True
                self._maps.get("resonator", {})[
                    "selected_frequency_mhz"] = self._resonator_seed
                self._spec_candidate_rows = [
                    {"frequency": float(value), "readout": dict(selected)}
                    for value in result]
            return result

        maximum = max(int(p.get("max_resonator_branches", len(branches))), 1)
        # The resonator stage has already capped and independently confirmed this list.
        # Never discard a confirmed branch merely because its notch is shallower; the
        # cap exists only to make a deliberately pathological many-mode scan explicit.
        branches = branches[:maximum]
        attempts = []
        original_readout = dict(self._discovery_readout)
        for index, branch in enumerate(branches):
            map_name = "spectroscopy_resonator_branch_%d" % index
            try:
                values = self._stage_spectroscopy_single(
                    branch, map_name=map_name)
                branch_map = copy.deepcopy(self._maps[map_name])
                scores = np.asarray(
                    branch_map.get("candidate_scores", []), dtype=float)
                physical = np.asarray(
                    branch_map.get("candidate_physical_fit_valid", []),
                    dtype=bool)
                finite_scores = scores[np.isfinite(scores)]
                rank = (
                    bool(np.any(physical)),
                    float(np.max(finite_scores)) if finite_scores.size else -np.inf,
                    int(len(values)),
                )
                attempts.append({
                    "index": int(index), "readout": dict(branch),
                    "status": "confirmed", "candidates": list(values),
                    "rank": rank, "map_name": map_name, "map": branch_map,
                })
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                attempts.append({
                    "index": int(index), "readout": dict(branch),
                    "status": "rejected", "candidates": [],
                    "rank": (False, -np.inf, 0), "map_name": map_name,
                    "map": copy.deepcopy(self._maps.get(map_name, {})),
                    "error": "%s: %s" % (type(exc).__name__, exc),
                })
        viable = [row for row in attempts if row["status"] == "confirmed"]
        self._spectroscopy_branch_attempts = copy.deepcopy(viable)
        if not viable:
            self._discovery_readout = original_readout
            self._spec_candidates_mhz = []
            self._discovery_status["spectroscopy"] = False
            self._maps["spectroscopy"] = {
                "search_complete": False, "selection_confirmed": False,
                "resonator_branch_frequencies_mhz": np.asarray([
                    row["readout"]["read_pulse_freq"] for row in attempts],
                    dtype=float),
                "resonator_branch_valid": np.zeros(len(attempts), dtype=bool),
                "resonator_branch_errors": [
                    row.get("error", "") for row in attempts],
                "failure": "no confirmed resonator branch produced a reproducible "
                           "qubit spectrum",
            }
            self._maps.get("resonator", {})["selection_confirmed"] = False
            raise RuntimeError(
                "none of %d confirmed resonator branches produced a reproducible "
                "qubit transition" % len(attempts))
        chosen = max(viable, key=lambda row: row["rank"])
        selected_readout = dict(chosen["readout"])
        self._discovery_readout = selected_readout
        self._resonator_seed = float(selected_readout["read_pulse_freq"])
        self._spec_candidates_mhz = [
            float(value) for value in chosen["candidates"]]
        self._spec_candidate_rows = [
            {"frequency": float(value), "readout": dict(selected_readout)}
            for value in self._spec_candidates_mhz]
        self._discovery_status["spectroscopy"] = True
        selected_map = copy.deepcopy(chosen["map"])
        selected_map.update({
            "resonator_branch_frequencies_mhz": np.asarray([
                row["readout"]["read_pulse_freq"] for row in attempts],
                dtype=float),
            "resonator_branch_valid": np.asarray([
                row["status"] == "confirmed" for row in attempts], dtype=bool),
            "resonator_branch_best_scores": np.asarray([
                row["rank"][1] for row in attempts], dtype=float),
            "resonator_branch_errors": [
                row.get("error", "") for row in attempts],
            "selected_resonator_branch_mhz": self._resonator_seed,
            "branch_backtracking_complete": True,
            "search_complete": True, "selection_confirmed": True,
        })
        self._maps["spectroscopy"] = selected_map
        resonator_map = self._maps.get("resonator", {})
        selected_record = next((
            row for row in self._resonator_branch_records
            if np.isclose(float(row["confirmation_feature"]["frequency_mhz"]),
                          self._resonator_seed, rtol=0.0, atol=1e-6)
        ), None)
        if selected_record is not None:
            coarse_feature = selected_record["feature"]
            confirmed_feature = selected_record["confirmation_feature"]
            resonator_map.update({
                "magnitude": coarse_feature["magnitude"],
                "smoothed_magnitude": coarse_feature["smoothed_magnitude"],
                "baseline_magnitude": coarse_feature["baseline_magnitude"],
                "feature": coarse_feature["smoothed_feature"],
                "complex_response": selected_record["response"],
                "contrast_snr": float(coarse_feature["contrast_snr"]),
                "relative_contrast": float(
                    coarse_feature["relative_contrast"]),
                "feature_width_mhz": float(
                    coarse_feature["feature_width_mhz"]),
                "confirmation_magnitude": confirmed_feature["magnitude"],
                "confirmation_feature": confirmed_feature["smoothed_feature"],
                "confirmation_complex_response": selected_record[
                    "confirmation_response"],
                "confirmation_contrast_snr": float(
                    confirmed_feature["contrast_snr"]),
                "confirmation_relative_contrast": float(
                    confirmed_feature["relative_contrast"]),
                "confirmation_width_mhz": float(
                    confirmed_feature["feature_width_mhz"]),
                "confirmation_shift_mhz": float(
                    selected_record["confirmation_shift_mhz"]),
                "confirmation_width_ratio": float(
                    selected_record["confirmation_width_ratio"]),
                "bootstrap_gain_dac": int(selected_record["candidate"][
                    "read_pulse_gain"]),
                "bootstrap_length_us": float(selected_record["candidate"][
                    "read_length"]),
            })
        branch_resolved = len(viable) == 1
        resonator_map.update({
            "selection_confirmed": bool(branch_resolved),
            "selected_frequency_mhz": self._resonator_seed,
            "selected_by": (
                "unique reproduced qubit spectroscopy branch"
                if branch_resolved else
                "provisional best spectroscopy branch; coherent Rabi pending"),
            "branch_backtracking_complete": True,
        })
        self._log(
            "spectroscopy", "OK",
            "selected resonator %.6f MHz after testing %d confirmed branches; "
            "retained qubit seeds %s"
            % (self._resonator_seed, len(attempts),
               ", ".join("%.4f" % value
                         for value in self._spec_candidates_mhz)))
        return self._spec_candidates_mhz

    def _stage_spectroscopy_single(self, seed_candidate=None,
                                   map_name="spectroscopy"):
        p = self.params["spectroscopy"]
        if not p.get("enabled", True):
            self._spec_candidates_mhz = [float(self.initial["qubit_pi_freq"])]
            self._log("spectroscopy", "SKIP", "disabled")
            return None
        self._spec_candidates_mhz = []
        # Temporarily read near the resonator response seed to maximize spectroscopy
        # contrast.  This does not adopt the seed as the optimized SS readout.
        seed_candidate = dict(
            self._discovery_readout if seed_candidate is None else seed_candidate)
        plan = self._frequency_discovery_plan(
            self.initial["qubit_pi_freq"], p, adaptive=False)
        coarse_freqs = plan["axes"][-1]
        search_min = float(coarse_freqs[0])
        search_max = float(coarse_freqs[-1])
        allowed_min = float(plan["allowed_min_mhz"])
        allowed_max = float(plan["allowed_max_mhz"])
        bounded = bool(plan["configured_envelope"])
        retained_coarse_count = max(
            int(p.get("coarse_candidates", 8)), int(p["max_candidates"]), 1)
        # Scan padding may contain real but unauthorized lines.  Inspect extra peaks
        # before filtering so those padding-only lines cannot consume every retained
        # in-prior candidate slot.
        scan_candidate_count = max(
            3 * retained_coarse_count, retained_coarse_count + 4)

        def coarse_scan(axis, source):
            response = self._acquire_spectroscopy(
                axis, seed_candidate, p["shots"], p["gain"],
                p["pulse_length_us"])
            features = self._spectral_features(
                axis, response, max_candidates=scan_candidate_count)
            rows = self._significant_spectral_rows(
                axis, features, p["min_feature_snr"],
                p.get("edge_guard_points", 2))
            for row in rows:
                row["proposal_kind"] = "peak"
            rows.extend(self._spectral_shoulder_rows(
                axis, features, rows, p["min_feature_snr"],
                scan_candidate_count,
                relative_floor=p.get("coarse_shoulder_fraction", 0.18),
                separation_steps=p.get(
                    "coarse_shoulder_separation_steps", 1.25),
                edge_guard_points=p.get("edge_guard_points", 2)))
            rows = [row for row in rows
                    if allowed_min <= float(row["frequency"]) <= allowed_max]
            rows = self._retain_spectral_proposal_mix(
                rows, retained_coarse_count,
                p.get("coarse_min_shoulder_candidates", 2))
            for row in rows:
                row["source"] = source
            return np.asarray(response, complex), features, rows

        coarse_z, coarse_features, primary_rows = coarse_scan(
            coarse_freqs, "primary")
        # One isolated flux row has no neighboring-row continuity.  A second grid
        # offset by half a coarse step prevents a sub-MHz transition midway between
        # the 2-MHz primary samples from disappearing entirely.
        if bounded and coarse_freqs.size >= 2:
            staggered_freqs = 0.5 * (coarse_freqs[:-1] + coarse_freqs[1:])
            staggered_z, staggered_features, staggered_rows = coarse_scan(
                staggered_freqs, "half_step")
        else:
            staggered_freqs = np.empty((0,), dtype=float)
            staggered_z = np.empty((0,), dtype=complex)
            staggered_features = {
                "residual": np.empty((0,), dtype=float),
                "snr_trace": np.empty((0,), dtype=float),
            }
            staggered_rows = []
        merged_rows = sorted(
            primary_rows + staggered_rows,
            key=lambda row: row["score"], reverse=True)
        coarse_step = abs(float(np.median(np.diff(coarse_freqs))))
        deduplicated_rows = []
        for row in merged_rows:
            if any(abs(row["frequency"] - old["frequency"])
                   <= 0.6 * coarse_step for old in deduplicated_rows):
                continue
            deduplicated_rows.append(row)
        coarse_rows = self._retain_spectral_proposal_mix(
            deduplicated_rows, retained_coarse_count,
            p.get("coarse_min_shoulder_candidates", 2))

        confirmation_points = max(int(p.get("confirmation_points", 41)), 9)
        if confirmation_points % 2 == 0:
            confirmation_points += 1
        confirmation_span = float(p.get("confirmation_span_mhz", 6.0))
        confirmation_shots = int(p.get("confirmation_shots", p["shots"]))
        repeat_error = float(p.get("max_repeat_error_mhz", 0.60))
        confirmation_min_snr = float(p.get(
            "confirmation_min_feature_snr", 4.0))
        confirmation_min_r2 = float(p.get(
            "confirmation_min_fit_r2", 0.25))
        confirmation_max_linewidth = float(p.get(
            "confirmation_max_linewidth_mhz", 8.0))
        coarse_capture = float(p.get(
            "coarse_capture_mhz",
            1.5 * abs(float(np.median(np.diff(coarse_freqs))))))
        neighbor_mask = float(p.get(
            "confirmation_neighbor_mask_mhz", 1.5))
        neighbor_radius = float(p.get(
            "confirmation_neighbor_radius_mhz", 8.0))
        confirmation_axes = []
        confirmation_response = []
        confirmation_snr = []
        confirmation_valid = []
        confirmation_fit_centers = []
        confirmation_fit_center_se = []
        confirmation_fit_linewidth = []
        confirmation_fit_snr = []
        confirmation_fit_r2 = []
        validation_errors = []
        reproduced = []
        for coarse in coarse_rows:
            neighbor_centers = [
                float(other["frequency"]) for other in coarse_rows
                # A shoulder is a hypothesis about a hidden second line.  It may use
                # a reproduced peak as an exclusion anchor when fitted, but must not
                # carve points out of that peak's own fit before it is validated.
                if other.get("proposal_kind", "peak") == "peak"
                if abs(float(other["frequency"]) - float(coarse["frequency"]))
                > 0.6 * coarse_step
                and abs(float(other["frequency"])
                        - float(coarse["frequency"])) <= neighbor_radius
            ]
            axis = self._contained_centered_axis(
                coarse["frequency"], confirmation_span, confirmation_points,
                lower=search_min if bounded else None,
                upper=search_max if bounded else None)
            confirmation_axes.append(axis)
            try:
                passes = np.empty((2, axis.size), dtype=complex)
                pass_features = []
                passes[0] = self._acquire_spectroscopy(
                    axis, seed_candidate, confirmation_shots, p["gain"],
                    p["pulse_length_us"])
                # Acquire the second scan from high to low, then realign it.  A
                # sweep-time drift now moves in the opposite frequency direction and
                # cannot masquerade as a stationary line in both passes.
                reverse_response = self._acquire_spectroscopy(
                    axis[::-1], seed_candidate, confirmation_shots, p["gain"],
                    p["pulse_length_us"])
                passes[1] = np.asarray(reverse_response, complex)[::-1]
                for pass_index in range(2):
                    pass_features.append(self._spectral_features(
                        axis, passes[pass_index],
                        max_candidates=retained_coarse_count))
                combined_z = np.mean(passes, axis=0)
                combined = self._spectral_features(
                    axis, combined_z, max_candidates=retained_coarse_count)
                def fit_trace(trace):
                    fitted = self._fit_complex_spectral_line(
                        axis, trace, coarse["frequency"], coarse_capture,
                        min_snr=confirmation_min_snr,
                        min_r2=confirmation_min_r2,
                        max_linewidth_mhz=confirmation_max_linewidth,
                        excluded_centers_mhz=neighbor_centers,
                        exclusion_half_width_mhz=neighbor_mask)
                    # Raw coarse proposals are not yet established neighboring lines.
                    # If their Voronoi masks break a real target fit, retry without
                    # those unverified exclusions before falling back to a provisional
                    # opposed-response seed.
                    if not fitted.get("valid", False) and neighbor_centers:
                        unmasked = self._fit_complex_spectral_line(
                            axis, trace, coarse["frequency"], coarse_capture,
                            min_snr=confirmation_min_snr,
                            min_r2=confirmation_min_r2,
                            max_linewidth_mhz=confirmation_max_linewidth)
                        if unmasked.get("valid", False):
                            unmasked["neighbor_mask_retry"] = True
                            return unmasked
                    return fitted

                fits = [fit_trace(trace)
                        for trace in (passes[0], passes[1], combined_z)]
                fits_valid = all(fit.get("valid", False) for fit in fits)
                fit_failure = "; ".join(
                    fit.get("failure", "invalid complex line fit")
                    for fit in fits if not fit.get("valid", False))
                provisional = None
                if not fits_valid and p.get(
                        "confirmation_allow_provisional_seed", True):
                    provisional = self._opposed_provisional_spectral_seed(
                        axis, passes, pass_features, coarse["frequency"],
                        coarse_capture,
                        min_snr=p.get(
                            "confirmation_provisional_min_snr", 4.0),
                        min_complex_correlation=p.get(
                            "confirmation_provisional_min_complex_correlation",
                            0.50))
                if not fits_valid and not (
                        provisional and provisional.get("valid", False)):
                    provisional_failure = (
                        provisional.get("failure", "provisional seed disabled")
                        if provisional is not None else "provisional seed disabled")
                    raise RuntimeError(
                        "%s; provisional opposed response failed: %s"
                        % (fit_failure, provisional_failure))
                if fits_valid:
                    separation = abs(
                        float(fits[0]["frequency_mhz"])
                        - float(fits[1]["frequency_mhz"]))
                    uncertainty_limit = 3.0 * math.hypot(
                        float(fits[0]["frequency_se_mhz"]),
                        float(fits[1]["frequency_se_mhz"]))
                    allowed_separation = max(repeat_error, uncertainty_limit)
                    if separation > allowed_separation:
                        raise RuntimeError(
                            "opposed fitted centres differ by %.3f MHz (limit %.3f)"
                            % (separation, allowed_separation))
                    pass_variances = np.maximum(np.square([
                        float(fits[0]["frequency_se_mhz"]),
                        float(fits[1]["frequency_se_mhz"]),
                    ]), 1e-12)
                    pass_weights = 1.0 / pass_variances
                    refined = float(np.average([
                        float(fits[0]["frequency_mhz"]),
                        float(fits[1]["frequency_mhz"]),
                    ], weights=pass_weights))
                    refined_se = float(math.sqrt(1.0 / np.sum(pass_weights)))
                    combined_separation = abs(
                        float(fits[2]["frequency_mhz"]) - refined)
                    combined_limit = max(
                        repeat_error,
                        3.0 * math.hypot(
                            refined_se, float(fits[2]["frequency_se_mhz"])))
                    if combined_separation > combined_limit:
                        raise RuntimeError(
                            "combined fitted centre differs from the opposed-pass "
                            "estimate by %.3f MHz (limit %.3f)"
                            % (combined_separation, combined_limit))
                    if abs(refined - float(coarse["frequency"])) > coarse_capture:
                        raise RuntimeError(
                            "confirmed center escaped its coarse capture basin")
                    row = {
                        "frequency": refined,
                        "score": float(min(fits[0]["snr"], fits[1]["snr"])),
                        "combined_snr": float(fits[2]["snr"]),
                        "pass_snr": (float(fits[0]["snr"]),
                                     float(fits[1]["snr"])),
                        "pass_centres_mhz": (
                            float(fits[0]["frequency_mhz"]),
                            float(fits[1]["frequency_mhz"])),
                        "separation_mhz": float(separation),
                        "combined_separation_mhz": float(combined_separation),
                        "physical_fit_valid": True,
                    }
                else:
                    refined = float(provisional["frequency_mhz"])
                    combined_index = int(np.argmin(np.abs(axis - refined)))
                    row = {
                        "frequency": refined,
                        "score": float(min(provisional["pass_snr"])),
                        "combined_snr": float(
                            combined["snr_trace"][combined_index]),
                        "pass_snr": tuple(provisional["pass_snr"]),
                        "pass_centres_mhz": (refined, refined),
                        "separation_mhz": 0.0,
                        "combined_separation_mhz": np.nan,
                        "physical_fit_valid": False,
                        "provisional_complex_correlation": float(
                            provisional["complex_correlation"]),
                    }
                if not allowed_min <= refined <= allowed_max:
                    raise RuntimeError(
                        "confirmed center lies only in fit padding outside the "
                        "authorized +/-radius prior")
                row.update({
                    "coarse_frequency": float(coarse["frequency"]),
                    "coarse_score": float(coarse["score"]),
                    "proposal_kind": coarse.get("proposal_kind", "peak"),
                    "source": coarse.get("source"),
                })
                reproduced.append(row)
                confirmation_response.append(passes)
                confirmation_snr.append(np.vstack([
                    pass_features[0]["snr_trace"],
                    pass_features[1]["snr_trace"],
                    combined["snr_trace"],
                ]))
                confirmation_valid.append(True)
                if fits_valid:
                    confirmation_fit_centers.append([
                        fit["frequency_mhz"] for fit in fits])
                    confirmation_fit_center_se.append([
                        fit["frequency_se_mhz"] for fit in fits])
                    confirmation_fit_linewidth.append([
                        fit["linewidth_mhz"] for fit in fits])
                    confirmation_fit_snr.append([fit["snr"] for fit in fits])
                    confirmation_fit_r2.append([fit["r2"] for fit in fits])
                    validation_errors.append("")
                else:
                    confirmation_fit_centers.append([np.nan] * 3)
                    confirmation_fit_center_se.append([np.nan] * 3)
                    confirmation_fit_linewidth.append([np.nan] * 3)
                    confirmation_fit_snr.append([np.nan] * 3)
                    confirmation_fit_r2.append([np.nan] * 3)
                    validation_errors.append(
                        "physical fit rejected (%s); retained only as an opposed "
                        "response seed for coherent Rabi" % fit_failure)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                confirmation_response.append(np.full(
                    (2, axis.size), np.nan + 1j * np.nan))
                confirmation_snr.append(np.full((3, axis.size), np.nan))
                confirmation_valid.append(False)
                confirmation_fit_centers.append([np.nan] * 3)
                confirmation_fit_center_se.append([np.nan] * 3)
                confirmation_fit_linewidth.append([np.nan] * 3)
                confirmation_fit_snr.append([np.nan] * 3)
                confirmation_fit_r2.append([np.nan] * 3)
                validation_errors.append("%s: %s" % (type(exc).__name__, exc))

        reproduced.sort(key=lambda row: (
            row["score"], row["combined_snr"], row["coarse_score"]),
                        reverse=True)
        retained_rows = []
        tolerance = max(repeat_error, 0.6 * coarse_step)
        for row in reproduced:
            if any(abs(row["frequency"] - old["frequency"]) <= tolerance
                   for old in retained_rows):
                continue
            retained_rows.append(row)
            if len(retained_rows) >= max(int(p["max_candidates"]), 1):
                break

        self._maps[map_name] = {
            "axes": {
                "qubit_frequency_mhz": coarse_freqs,
                "staggered_qubit_frequency_mhz": staggered_freqs,
                "confirmation_frequency_mhz": (
                    np.asarray(confirmation_axes, dtype=float)
                    if confirmation_axes else
                    np.empty((0, confirmation_points), dtype=float)),
            },
            "complex_response": coarse_z,
            "feature_residual": coarse_features["residual"],
            "feature_snr": coarse_features["snr_trace"],
            "staggered_complex_response": staggered_z,
            "staggered_feature_residual": staggered_features["residual"],
            "staggered_feature_snr": staggered_features["snr_trace"],
            "used_global_scan": bool(bounded), "used_wide_scan": True,
            "search_mode": plan["mode"],
            "allowed_min_mhz": allowed_min,
            "allowed_max_mhz": allowed_max,
            "scan_min_mhz": float(coarse_freqs[0]),
            "scan_max_mhz": float(coarse_freqs[-1]),
            "coarse_candidate_frequencies_mhz": np.asarray([
                row["frequency"] for row in coarse_rows], dtype=float),
            "coarse_candidate_scores": np.asarray([
                row["score"] for row in coarse_rows], dtype=float),
            "coarse_candidate_kinds": [
                row.get("proposal_kind", "peak") for row in coarse_rows],
            "confirmation_complex_response": (
                np.asarray(confirmation_response, dtype=complex)
                if confirmation_response else
                np.empty((0, 2, confirmation_points), dtype=complex)),
            "confirmation_feature_snr": (
                np.asarray(confirmation_snr, dtype=float)
                if confirmation_snr else
                np.empty((0, 3, confirmation_points), dtype=float)),
            "confirmation_valid": np.asarray(confirmation_valid, dtype=bool),
            "confirmation_fit_centers_mhz": np.asarray(
                confirmation_fit_centers, dtype=float).reshape((-1, 3)),
            "confirmation_fit_center_se_mhz": np.asarray(
                confirmation_fit_center_se, dtype=float).reshape((-1, 3)),
            "confirmation_fit_linewidth_mhz": np.asarray(
                confirmation_fit_linewidth, dtype=float).reshape((-1, 3)),
            "confirmation_fit_snr": np.asarray(
                confirmation_fit_snr, dtype=float).reshape((-1, 3)),
            "confirmation_fit_r2": np.asarray(
                confirmation_fit_r2, dtype=float).reshape((-1, 3)),
            "candidate_frequencies_mhz": np.asarray([
                row["frequency"] for row in retained_rows], dtype=float),
            "candidate_scores": np.asarray([
                row["score"] for row in retained_rows], dtype=float),
            "candidate_physical_fit_valid": np.asarray([
                row.get("physical_fit_valid", False)
                for row in retained_rows], dtype=bool),
            "search_complete": bool(retained_rows),
            "selection_confirmed": bool(retained_rows),
            "validation_errors": validation_errors,
        }
        if not coarse_rows:
            self._maps[map_name]["failure"] = (
                "no significant interior coarse feature")
            raise RuntimeError(
                "no %.1f-sigma qubit feature in %.3f..%.3f MHz"
                % (p["min_feature_snr"], allowed_min, allowed_max))
        if not retained_rows:
            self._maps[map_name]["failure"] = (
                "no coarse feature survived opposed fitted confirmations")
            raise RuntimeError(
                "none of %d coarse qubit features reproduced independently"
                % len(coarse_rows))
        self._spec_candidates_mhz = [
            float(row["frequency"]) for row in retained_rows]
        self._discovery_status["spectroscopy"] = True
        self._log("spectroscopy", "OK",
                  "retained reproduced spectral seeds %s; coherent Rabi/direct SS "
                  "choose among them"
                  % ", ".join("%.4f" % f for f in self._spec_candidates_mhz))
        return self._spec_candidates_mhz

    def _stage_iq_rabi(self):
        """Use coherent Rabi to resolve branches that both passed spectroscopy."""
        branches = list(self._spectroscopy_branch_attempts)
        if len(branches) <= 1:
            return self._stage_iq_rabi_single()
        attempts = []
        original = {
            "working": dict(self.working),
            "readout": dict(self._discovery_readout),
            "resonator_seed": float(self._resonator_seed),
            "spec": list(self._spec_candidates_mhz),
            "rabi_candidates": copy.deepcopy(self._rabi_candidates),
        }
        for index, branch in enumerate(branches):
            self._maps.pop("iq_rabi", None)
            self._maps.pop("rough_amplitude_rabi", None)
            self._discovery_readout = dict(branch["readout"])
            self._resonator_seed = float(
                self._discovery_readout["read_pulse_freq"])
            self._spec_candidates_mhz = [
                float(value) for value in branch["candidates"]]
            self._rabi_candidates = []
            try:
                result = self._stage_iq_rabi_single()
                iq_map = copy.deepcopy(self._maps.get("iq_rabi", {}))
                amplitude_map = copy.deepcopy(
                    self._maps.get("rough_amplitude_rabi", {}))
                scores = np.asarray(iq_map.get("row_scores", []), dtype=float)
                r2 = np.asarray(iq_map.get("row_r2", []), dtype=float)
                finite_scores = scores[np.isfinite(scores)]
                finite_r2 = r2[np.isfinite(r2)]
                coherent = bool(iq_map.get("coherent_witness", False))
                branch_ss = None
                if coherent:
                    try:
                        branch_ss = self._confirm_candidates(
                            [self.working],
                            int(self.params["spectroscopy"].get(
                                "branch_ss_shots", 250)),
                            int(self.params["spectroscopy"].get(
                                "branch_ss_blocks", 2)),
                            "resonator branch %d rough step-5 replay" % index,
                            add_to_history=True)[0]
                    except KeyboardInterrupt:
                        raise
                    except Exception as exc:
                        self._log(
                            "iq_rabi", "WARN",
                            "rough direct-SS branch %d comparison failed (%s: %s)"
                            % (index, type(exc).__name__, exc))
                branch_lcb = (fidelity_evidence(branch_ss)[2]
                              if branch_ss is not None else -np.inf)
                attempts.append({
                    "index": int(index), "readout": dict(branch["readout"]),
                    "spec_candidates": list(branch["candidates"]),
                    "status": "coherent" if coherent else "provisional",
                    "rank": (
                        coherent,
                        float(branch_lcb),
                        float(np.max(finite_scores))
                        if finite_scores.size else -np.inf,
                        float(np.max(finite_r2)) if finite_r2.size else -np.inf,
                    ),
                    "working": dict(self.working),
                    "rabi_candidates": copy.deepcopy(self._rabi_candidates),
                    "result": copy.deepcopy(result),
                    "branch_single_shot": copy.deepcopy(branch_ss),
                    "spectroscopy_map": copy.deepcopy(branch["map"]),
                    "iq_map": iq_map, "amplitude_map": amplitude_map,
                })
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                attempts.append({
                    "index": int(index), "readout": dict(branch["readout"]),
                    "spec_candidates": list(branch["candidates"]),
                    "status": "rejected",
                    "rank": (False, -np.inf, -np.inf, -np.inf),
                    "error": "%s: %s" % (type(exc).__name__, exc),
                })
            finally:
                if "iq_rabi" in self._maps:
                    self._maps["iq_rabi_resonator_branch_%d" % index] = (
                        copy.deepcopy(self._maps["iq_rabi"]))
                if "rough_amplitude_rabi" in self._maps:
                    self._maps[
                        "rough_amplitude_rabi_resonator_branch_%d" % index] = (
                            copy.deepcopy(self._maps["rough_amplitude_rabi"]))
        coherent = [row for row in attempts if row["status"] == "coherent"]
        if not coherent:
            self.working = original["working"]
            self._discovery_readout = original["readout"]
            self._resonator_seed = original["resonator_seed"]
            self._spec_candidates_mhz = original["spec"]
            self._rabi_candidates = original["rabi_candidates"]
            self._maps.get("resonator", {})["selection_confirmed"] = False
            raise RuntimeError(
                "multiple resonator branches passed spectroscopy but none produced "
                "a coherent Rabi witness")
        chosen = max(coherent, key=lambda row: row["rank"])
        self.working = dict(chosen["working"])
        self._discovery_readout = dict(chosen["readout"])
        self._resonator_seed = float(
            self._discovery_readout["read_pulse_freq"])
        self._spec_candidates_mhz = list(chosen["spec_candidates"])
        self._rabi_candidates = copy.deepcopy(chosen["rabi_candidates"])
        self._maps["iq_rabi"] = copy.deepcopy(chosen["iq_map"])
        self._maps["rough_amplitude_rabi"] = copy.deepcopy(
            chosen["amplitude_map"])
        spectroscopy_audit = {
            key: copy.deepcopy(value)
            for key, value in self._maps.get("spectroscopy", {}).items()
            if key.startswith("resonator_branch_")
            or key in ("branch_backtracking_complete",)
        }
        self._maps["spectroscopy"] = copy.deepcopy(
            chosen["spectroscopy_map"])
        self._maps["spectroscopy"].update(spectroscopy_audit)
        self._maps["spectroscopy"].update({
            "selected_resonator_branch_mhz": self._resonator_seed,
            "search_complete": True, "selection_confirmed": True,
        })
        self._maps["iq_rabi"].update({
            "resonator_branch_frequencies_mhz": np.asarray([
                row["readout"]["read_pulse_freq"] for row in attempts],
                dtype=float),
            "resonator_branch_coherent": np.asarray([
                row["status"] == "coherent" for row in attempts], dtype=bool),
            "resonator_branch_scores": np.asarray([
                row["rank"][2] for row in attempts], dtype=float),
            "resonator_branch_step5_lcb": np.asarray([
                row["rank"][1] for row in attempts], dtype=float),
            "selected_resonator_branch_mhz": self._resonator_seed,
            "branch_selection_confirmed": True,
        })
        self._maps.get("resonator", {}).update({
            "selection_confirmed": True,
            "selected_frequency_mhz": self._resonator_seed,
            "selected_by": "coherent Rabi after opposed spectroscopy",
        })
        selected_record = next((
            row for row in self._resonator_branch_records
            if np.isclose(float(row["confirmation_feature"]["frequency_mhz"]),
                          self._resonator_seed, rtol=0.0, atol=1e-6)
        ), None)
        if selected_record is not None:
            coarse_feature = selected_record["feature"]
            confirmed_feature = selected_record["confirmation_feature"]
            self._maps["resonator"].update({
                "magnitude": coarse_feature["magnitude"],
                "smoothed_magnitude": coarse_feature["smoothed_magnitude"],
                "baseline_magnitude": coarse_feature["baseline_magnitude"],
                "feature": coarse_feature["smoothed_feature"],
                "complex_response": selected_record["response"],
                "contrast_snr": float(coarse_feature["contrast_snr"]),
                "relative_contrast": float(
                    coarse_feature["relative_contrast"]),
                "feature_width_mhz": float(
                    coarse_feature["feature_width_mhz"]),
                "confirmation_magnitude": confirmed_feature["magnitude"],
                "confirmation_feature": confirmed_feature["smoothed_feature"],
                "confirmation_complex_response": selected_record[
                    "confirmation_response"],
                "confirmation_contrast_snr": float(
                    confirmed_feature["contrast_snr"]),
                "confirmation_relative_contrast": float(
                    confirmed_feature["relative_contrast"]),
                "confirmation_width_mhz": float(
                    confirmed_feature["feature_width_mhz"]),
                "confirmation_shift_mhz": float(
                    selected_record["confirmation_shift_mhz"]),
                "confirmation_width_ratio": float(
                    selected_record["confirmation_width_ratio"]),
            })
        self._log(
            "iq_rabi", "OK",
            "coherent Rabi selected resonator %.6f MHz after %d spectroscopy branches"
            % (self._resonator_seed, len(attempts)))
        return self.working

    def _stage_iq_rabi_single(self):
        p = self.params["iq_rabi"]
        if not p.get("enabled", True):
            self._log("iq_rabi", "SKIP", "disabled")
            return None
        if not self._spec_candidates_mhz:
            raise RuntimeError(
                "no validated spectroscopy candidates are available for Rabi")
        # Resonator spectroscopy already established a better readout-frequency seed.
        # Use it for the cheap averaged-IQ maps and carry it into the rough direct-SS
        # candidates; otherwise a bad input readout can erase the Rabi we need in order
        # to escape that same bad starting tuple.
        rabi_base = dict(self._discovery_readout)
        local_freqs = []
        for center in self._spec_candidates_mhz:
            local_freqs.extend(self._float_axis(
                center, p["local_span_mhz"], p["freq_points_per_candidate"],
                include=[center]))
        # Register resolution makes sub-Hz distinctions irrelevant here.
        freqs = np.asarray(sorted(set(round(float(f), 6) for f in local_freqs)))
        gains = self._integer_axis(
            p["gain_min"], p["gain_max"], p["gain_points"])
        i_map, q_map = self._acquire_iq_chevron(
            freqs, gains, rabi_base, p["shots"])
        analysis = analyze_iq_chevron(
            freqs, gains, i_map, q_map, min_r2=p["min_r2"])
        coherent_rows = [
            row for row in analysis["rows"]
            if bool(row["fit"].get("ok", False))
            and float(row["fit"].get("r2", -np.inf)) >= float(p["min_r2"])
            and np.isfinite(float(row["fit"].get("pi_gain", np.nan)))
            and float(row.get("snr", -np.inf))
            >= float(p.get("witness_min_snr", 5.0))
            and float(row.get("relative_contrast", 0.0))
            >= float(p.get("witness_min_relative_contrast", 0.10))
        ]
        if not coherent_rows:
            self._maps["iq_rabi"] = {
                "axes": {"qubit_frequency_mhz": freqs,
                         "qubit_gain_dac": gains},
                "I": i_map, "Q": q_map,
                "row_scores": np.asarray([
                    row["score"] for row in analysis["rows"]]),
                "row_r2": np.asarray([
                    row["fit"].get("r2", np.nan)
                    for row in analysis["rows"]]),
                "row_pi_gain": np.asarray([
                    row["fit"].get("pi_gain", np.nan)
                    for row in analysis["rows"]]),
                "coherent_witness": False,
                "coherent_witness_frequencies_mhz": np.asarray([], dtype=float),
                "search_complete": False, "selection_confirmed": False,
                "failure": "no spectral basin produced a coherent Rabi witness",
            }
            raise RuntimeError(
                "none of the reproduced spectral features produced a coherent Rabi "
                "witness; refusing to nominate a qubit transition")
        # A large non-oscillatory excursion can have a high generic chevron score.
        # It may be useful spectroscopy, but it is not an X180 seed.  From this point
        # onward only rows satisfying the explicit coherent-witness requirements exist.
        best = max(coherent_rows, key=lambda row: float(row["score"]))
        rough_freq = float(best["frequency"])
        rough_gain = float(best["fit"].get("pi_gain", np.nan))
        if not np.isfinite(rough_gain):
            # Still return a physical first-response lobe if a heavily damped trace did
            # not satisfy the coherent fit.  Direct SS confirmation remains sovereign.
            projection = np.asarray(best["projection"])
            rough_gain = float(gains[int(np.nanargmax(np.abs(projection - projection[0])))])
        rough_gain = int(np.clip(round(rough_gain), 1, 32767))
        self._maps["iq_rabi"] = {
            "axes": {"qubit_frequency_mhz": freqs, "qubit_gain_dac": gains},
            "I": i_map, "Q": q_map,
            "row_scores": np.asarray([row["score"] for row in analysis["rows"]]),
            "row_r2": np.asarray([row["fit"].get("r2", np.nan)
                                  for row in analysis["rows"]]),
            "row_pi_gain": np.asarray([row["fit"].get("pi_gain", np.nan)
                                       for row in analysis["rows"]]),
            "coherent_witness": bool(coherent_rows),
            "coherent_witness_frequencies_mhz": np.asarray([
                row["frequency"] for row in coherent_rows], dtype=float),
        }
        for row in coherent_rows:
            witness_candidate = _with_candidate(
                rabi_base,
                qubit_pi_freq=float(row["frequency"]),
                qubit_pi_gain=int(np.clip(round(
                    row["fit"].get("pi_gain", np.nan)), 1, 32767)))
            self._record_control_witness(
                "iq_rabi", row["frequency"], "averaged_iq_rabi",
                candidate=witness_candidate,
                r2=float(row["fit"].get("r2", np.nan)),
                snr=float(row.get("snr", np.nan)),
                relative_contrast=float(row.get(
                    "relative_contrast", np.nan)),
                pi_gain=float(row["fit"].get("pi_gain", np.nan)),
            )

        ranked_rows = sorted(coherent_rows, key=lambda row: row["score"],
                             reverse=True)
        rabi_candidates = []
        selected_rows = []
        # Preserve at least one *actually coherent* candidate from every spectral basin.
        # Spectroscopy-only basins are deliberately omitted.  Without
        # this non-maximum suppression, four adjacent samples around one strong TLS can
        # crowd the configured-prior/qubit basin out of the direct-SS shortlist.
        spectral_centers = np.asarray(self._spec_candidates_mhz, dtype=float)
        for center_index, center in enumerate(spectral_centers):
            # Use disjoint nearest-centre (Voronoi) assignment.  Overlapping +/- local
            # windows must not let several nearby spectral seeds all select the same
            # strong Rabi row and silently erase a weaker basin.
            basin = [
                row for row in ranked_rows
                if int(np.argmin(np.abs(
                    spectral_centers - float(row["frequency"])))) == center_index
            ]
            if basin:
                selected_rows.append(basin[0])
        selected_rows.extend(ranked_rows)
        seen_frequencies = set()
        rabi_capacity = max(
            int(p.get("shortlist", 4)), len(self._spec_candidates_mhz))
        for row in selected_rows:
            fkey = round(float(row["frequency"]), 6)
            if fkey in seen_frequencies:
                continue
            seen_frequencies.add(fkey)
            gain = row["fit"].get("pi_gain", np.nan)
            if not np.isfinite(gain):
                projection = np.asarray(row["projection"])
                gain = gains[int(np.nanargmax(np.abs(projection - projection[0])))]
            rabi_candidates.append(_with_candidate(
                rabi_base, qubit_pi_freq=float(row["frequency"]),
                qubit_pi_gain=int(np.clip(round(gain), 1, 32767))))
            if len(_unique_candidates(rabi_candidates)) >= rabi_capacity:
                break

        fine_stop = min(32767, max(int(round(2.4 * rough_gain)), rough_gain + 4))
        fine_gains = self._integer_axis(0, fine_stop, p["fine_gain_points"])
        fi, fq = self._acquire_iq_chevron(
            np.asarray([rough_freq]), fine_gains, rabi_base, p["shots"])
        fine = analyze_iq_chevron(
            np.asarray([rough_freq]), fine_gains, fi, fq,
            min_r2=max(0.45, 0.8 * float(p["min_r2"])))
        fine_gain = fine["best"]["fit"].get("pi_gain", np.nan)
        if np.isfinite(fine_gain):
            rough_gain = int(np.clip(round(fine_gain), 1, 32767))
        self._maps["rough_amplitude_rabi"] = {
            "axes": {"qubit_frequency_mhz": np.asarray([rough_freq]),
                     "qubit_gain_dac": fine_gains},
            "I": fi, "Q": fq,
            "projection": np.asarray(fine["best"]["projection"])[None, :],
            "fit": np.asarray(fine["best"]["fit"].get("yfit", []))[None, :],
        }
        self.working = _with_candidate(
            rabi_base, qubit_pi_freq=rough_freq, qubit_pi_gain=rough_gain)
        # Refinement replaces the coarse representative of its own basin; it must not
        # consume an extra shortlist slot and evict the weaker fourth basin (which may
        # be the intended qubit behind stronger TLS lines).
        rabi_candidates = _unique_candidates(rabi_candidates)
        if rabi_candidates:
            replace_index = int(np.argmin([
                abs(float(candidate["qubit_pi_freq"]) - rough_freq)
                for candidate in rabi_candidates
            ]))
            rabi_candidates[replace_index] = dict(self.working)
        else:
            rabi_candidates = [dict(self.working)]
        self._rabi_candidates = _unique_candidates(rabi_candidates)[:rabi_capacity]
        if not self._rabi_candidates:
            raise RuntimeError("coherent Rabi analysis produced no physical candidate")
        coherent_centers = sorted(set(
            int(np.argmin(np.abs(spectral_centers - float(row["frequency"]))))
            for row in coherent_rows))
        self._maps["iq_rabi"].update({
            "coherent_spectral_basin_indices": np.asarray(
                coherent_centers, dtype=int),
            "rejected_spectral_basin_indices": np.asarray([
                index for index in range(len(spectral_centers))
                if index not in coherent_centers], dtype=int),
            "candidate_frequencies_mhz": np.asarray([
                candidate["qubit_pi_freq"]
                for candidate in self._rabi_candidates], dtype=float),
            "search_complete": True, "selection_confirmed": True,
        })
        self._log("iq_rabi", "OK" if analysis["ok"] else "WARN",
                  "common-mode-subtracted Rabi seed %.6f MHz @ %d DAC (r2 %.3f)"
                  % (rough_freq, rough_gain, best["fit"].get("r2", np.nan)))
        return self.working

    def _stage_rough_single_shot(self):
        p = self.params["rough_single_shot"]
        incumbent = dict(self.working)
        seeds = list(self._rabi_candidates) or [incumbent]
        frequency_offsets = np.linspace(
            -float(p["freq_span_mhz"]) / 2.0,
            float(p["freq_span_mhz"]) / 2.0, int(p["freq_points"]))
        gain_scales = np.linspace(
            1.0 - float(p["gain_fraction"]),
            1.0 + float(p["gain_fraction"]), int(p["gain_points"]))
        actual_gains = np.empty((len(seeds), len(gain_scales)), dtype=int)
        candidates = []
        for basin_index, seed in enumerate(seeds):
            actual_gains[basin_index] = np.clip(
                np.rint(float(seed["qubit_pi_gain"]) * gain_scales),
                1, 32767).astype(int)
            for offset in frequency_offsets:
                for gain in actual_gains[basin_index]:
                    # Candidates discovered before readout optimization are always
                    # grafted onto the current read tuple.
                    candidates.append(_with_candidate(
                        incumbent, sigma=float(seed["sigma"]),
                        qubit_pi_freq=float(seed["qubit_pi_freq"] + offset),
                        qubit_pi_gain=int(gain)))

        shape = (len(seeds), len(frequency_offsets), len(gain_scales))
        score = np.full(int(np.prod(shape)), np.nan)
        score_se = np.full_like(score, np.nan)
        order = self.rng.permutation(len(candidates))
        cache = {}
        failures = 0
        consecutive_failures = 0
        aborted = False
        self._log(
            "rough_ss", "OK",
            "%d-basin direct-SS Rabi chevron (%d points, %d shots/state)"
            % (len(seeds), len(candidates), int(p["coarse_shots"])))
        progress_step = max(len(candidates) // 10, 1)
        for count, index in enumerate(order):
            key = _candidate_key(candidates[index])
            if key in cache:
                score[index], score_se[index] = cache[key]
                consecutive_failures = 0
                continue
            try:
                measured = self._measure_candidate(
                    candidates[index], int(p["coarse_shots"]),
                    "rough_ss chevron coarse",
                    state_order="ge" if count % 2 == 0 else "eg")
                score[index] = measured["fidelity"]
                score_se[index] = measured["fidelity_se"]
                cache[key] = (score[index], score_se[index])
                consecutive_failures = 0
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                failures += 1
                consecutive_failures += 1
                self._log(
                    "rough_ss", "WARN", "chevron point %d/%d failed (%s: %s)"
                    % (count + 1, len(candidates), type(exc).__name__, exc))
                if consecutive_failures >= int(self.params.get(
                        "max_consecutive_point_failures", 5)):
                    aborted = True
                    self._log("rough_ss", "WARN",
                              "backend failure circuit breaker stopped the SS chevron")
                    break
            if (self._detailed_console()
                    and ((count + 1) % progress_step == 0
                         or count + 1 == len(candidates))):
                print("      rough_ss chevron progress: %d/%d"
                      % (count + 1, len(candidates)))

        score_map = score.reshape(shape)
        coverage = float(np.count_nonzero(np.isfinite(score)) / max(score.size, 1))
        self._maps["rough_ss_chevron"] = {
            "axes": {
                "basin_seed_frequency_mhz": np.asarray(
                    [seed["qubit_pi_freq"] for seed in seeds], dtype=float),
                "frequency_offset_mhz": frequency_offsets,
                "gain_scale": gain_scales,
            },
            "actual_gain_dac": actual_gains,
            "fidelity": score_map,
            "fidelity_se": score_se.reshape(shape),
            "coverage": coverage,
            "failed_points": int(failures),
            "aborted": bool(aborted),
            "search_complete": bool(not aborted and coverage >= 1.0 - 1e-12),
            "selection_confirmed": False,
        }
        basin_winners = []
        for basin_index, seed in enumerate(seeds):
            flat = score_map[basin_index].reshape(-1)
            finite = np.flatnonzero(np.isfinite(flat))
            if finite.size:
                local_index = int(finite[np.argmax(flat[finite])])
                global_index = (basin_index * len(frequency_offsets)
                                * len(gain_scales) + local_index)
                basin_winners.append(candidates[global_index])
            else:
                basin_winners.append(_with_candidate(
                    incumbent, sigma=float(seed["sigma"]),
                    qubit_pi_freq=float(seed["qubit_pi_freq"]),
                    qubit_pi_gain=int(seed["qubit_pi_gain"])))
        if not basin_winners:
            raise RuntimeError("no Rabi basin is available for direct SS confirmation")
        # The arbitrary input tuple is a diagnostic baseline, not a transition
        # candidate.  Every tuple admitted here descends from a coherent Rabi witness.
        admitted = _unique_candidates(basin_winners + [incumbent])
        confirmed = self._confirm_candidates(
            admitted,
            p["shots"], p["blocks"],
            "rough pulse exact step-5")
        confirmation_complete = self._confirmation_batch_complete(confirmed)
        self._maps["rough_ss_chevron"]["selection_confirmed"] = True
        self._maps["rough_ss_chevron"]["selection_confirmation_complete"] = bool(
            confirmation_complete)
        if not confirmation_complete:
            self._maps["rough_ss_chevron"]["search_complete"] = False
        admitted_keys = {_candidate_key(row) for row in admitted}
        self._rough_control_candidates = sorted([
            copy.deepcopy(row) for row in confirmed
            if _candidate_key(row) in admitted_keys
            and bool(row.get("confirmation_complete", False))
        ], key=self._joint_rank, reverse=True)
        self._maps["rough_ss_chevron"].update({
            "admitted_candidate_keys": [
                list(_candidate_key(row)) for row in admitted],
            "confirmed_coherent_candidates": copy.deepcopy(
                self._rough_control_candidates),
            "coherent_only": True,
        })
        if not self._rough_control_candidates:
            raise RuntimeError(
                "no coherent-Rabi-derived control candidate completed its held-out "
                "single-shot replay")
        direct_best = self._best_aggregate(confirmed)
        best = self._noninferior_seed(
            confirmed, incumbent, direct_best, margin=0.005)
        self._adopt(best, "rough_ss")
        return best

    def _parity_refine_branch(self, incumbent, stage, label):
        """Refine one coherent-Rabi branch without selecting it globally."""
        p = self.params["parity_chevron"]
        calibration_shots = max(int(p["shots"]), 300)
        initial = self._parity_map(
            stage, incumbent, p,
            incumbent["qubit_pi_freq"], incumbent["qubit_pi_gain"],
            calibration_shots, label)
        index = initial["index"]
        initial_edge = bool(
            index[0] in (0, initial["frequencies"].size - 1)
            or index[1] in (0, initial["gains"].size - 1))
        self._maps[stage]["initial_edge_winner"] = initial_edge
        seeds, preferred, maps = [initial["seed"]], initial["seed"], [initial]
        final_edge, expansion_ok = initial_edge, False
        edge_stage = stage + "_edge"
        if initial_edge:
            self._maps[stage]["search_complete"] = False
            try:
                expanded = self._parity_map(
                    edge_stage, incumbent, p,
                    initial["seed"]["qubit_pi_freq"],
                    initial["seed"]["qubit_pi_gain"], calibration_shots,
                    label + " expansion")
                expanded_index = expanded["index"]
                final_edge = bool(
                    expanded_index[0] in (0, expanded["frequencies"].size - 1)
                    or expanded_index[1] in (0, expanded["gains"].size - 1))
                self._maps[edge_stage]["edge_winner"] = final_edge
                self._maps[edge_stage]["search_complete"] = bool(
                    expanded["data_complete"] and not final_edge)
                seeds.insert(0, expanded["seed"])
                preferred = expanded["seed"]
                maps.append(expanded)
                expansion_ok = True
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                self._maps[stage]["expansion_failure"] = "%s: %s" % (
                    type(exc).__name__, exc)
        confirmed = self._confirm_candidates(
            seeds + [incumbent], p["confirm_shots"], p["confirm_blocks"],
            label + " direct step-5", add_to_history=True)
        confirmation_complete = self._confirmation_batch_complete(confirmed)
        best = self._noninferior_seed(confirmed, preferred, incumbent)
        for mapping in maps:
            self._maps[mapping["stage"]]["selection_confirmed"] = bool(
                confirmation_complete)
            self._maps[mapping["stage"]][
                "selection_confirmation_complete"] = bool(confirmation_complete)
            if not confirmation_complete:
                self._maps[mapping["stage"]]["search_complete"] = False
        complete = bool(
            confirmation_complete and initial["data_complete"]
            and (not initial_edge
                 or (expansion_ok and maps[-1]["data_complete"] and not final_edge)))
        self._maps[stage].update({
            "expanded": initial_edge,
            "edge_winner": bool(initial_edge and final_edge),
            "search_complete": complete,
        })
        if not complete:
            raise RuntimeError(
                "the repeated-pulse map was incomplete or remained boundary-limited")
        return {
            "candidate": best, "confirmed": confirmed,
            "stage": stage, "edge_stage": edge_stage if initial_edge else None,
            "map": copy.deepcopy(self._maps[stage]),
        }

    def _stage_parity_chevron(self):
        """Select a coherent transition; keep rough pulse quality provisional.

        Resonator/opposed spectroscopy plus a resolved averaged-IQ Rabi establish a
        workable transition frequency.  The parity map and exact odd/even audit add
        useful branch-selection evidence, but at this point gain and duration are
        deliberately still rough.  Requiring them to pass the final pulse certificate
        here would make the optimizer demand an already tuned pi pulse before it is
        allowed to tune one.
        """
        p = self.params["parity_chevron"]
        self._qualified_control_candidates = []
        self._qualified_transition_frequency = None
        self._qualified_transition_frequencies = []
        self._qualified_control_key = None
        self._final_control_verified_key = None
        source = list(self._rough_control_candidates)
        # Isolated map/calibration helpers are used directly by deterministic unit
        # tests and notebooks.  Production ``acquire`` activates the discovery guard
        # and may never manufacture this fallback.
        if not source and not self._discovery_guard_active:
            source = [dict(self.working)]
        if not source:
            raise RuntimeError(
                "no held-out coherent-Rabi control branch is available for "
                "transition selection")
        branches, seen = [], set()
        for row in sorted(source, key=self._authoritative_rank, reverse=True):
            frequency = round(float(row["qubit_pi_freq"]), 6)
            # Adjacent SS samples within one Rabi linewidth are one branch, not
            # separate opportunities to crowd a physically distinct transition out.
            if any(abs(frequency - existing) <= 0.5 for existing in seen):
                continue
            seen.add(frequency)
            branches.append(copy.deepcopy(row))
            if len(branches) >= max(int(p.get("max_control_branches", 6)), 1):
                break
        records, admitted = [], []
        original = dict(self.working)
        for index, seed in enumerate(branches, 1):
            stage = "parity_chevron" if index == 1 else (
                "parity_chevron_basin_%d" % index)
            record = {
                "branch": index, "seed": copy.deepcopy(seed),
                "rabi_frequency_mhz": float(seed["qubit_pi_freq"]),
                "status": "frequency_qualified_control_provisional",
                "candidate": None, "control_verified": False,
                "parity_failure": None, "control_failure": None,
                "qualification_kind": None,
            }
            candidates = [seed]
            if p.get("enabled", True):
                try:
                    refined = self._parity_refine_branch(
                        seed, stage, "transition branch %d parity" % index)
                    record["parity"] = copy.deepcopy(refined)
                    candidates = sorted(
                        refined["confirmed"], key=self._joint_rank, reverse=True)
                    preferred_key = _candidate_key(refined["candidate"])
                    candidates.sort(
                        key=lambda row: _candidate_key(row) == preferred_key,
                        reverse=True)
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    record["parity_failure"] = "%s: %s" % (
                        type(exc).__name__, exc)
            else:
                record["parity_failure"] = "repeated-pulse refinement is disabled"
            maximum_shift = float(p.get("max_rabi_frequency_shift_mhz", 2.0))
            candidates = [
                contender for contender in candidates
                if abs(float(contender["qubit_pi_freq"])
                       - float(seed["qubit_pi_freq"])) <= maximum_shift]
            if not candidates:
                candidates = [seed]
            provisional = copy.deepcopy(candidates[0])
            verified_candidate = None
            verified_audit = None
            for contender in candidates:
                try:
                    audit = self._stage_final_control_verify(
                        contender,
                        minimum_binary_contrast=float(p.get(
                            "fallback_minimum_binary_contrast", 0.12)),
                        shot_multiplier=max(int(p.get(
                            "prequalification_shot_multiplier", 4)), 1))
                    if not bool(audit.get("verified", False)):
                        raise RuntimeError("exact odd/even audit returned unverified")
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    record["control_failure"] = "%s: %s" % (
                        type(exc).__name__, exc)
                    failed_audit = self._maps.get("final_control_verify")
                    if isinstance(failed_audit, dict):
                        record["control_audit_attempt"] = copy.deepcopy(
                            failed_audit)
                    continue
                verified_candidate = copy.deepcopy(contender)
                verified_audit = copy.deepcopy(audit)
                break
            candidate = (verified_candidate if verified_candidate is not None
                         else provisional)
            if verified_candidate is not None:
                kind = ("rabi_plus_parity_plus_exact_odd_even"
                        if record.get("parity_failure") is None else
                        "coherent_rabi_plus_exact_odd_even")
                record.update({
                    "status": "frequency_qualified_control_verified",
                    "control_verified": True,
                    "control_audit": verified_audit,
                    "control_failure": None,
                })
            elif record.get("parity_failure") is None:
                kind = "coherent_rabi_plus_parity_control_provisional"
            else:
                kind = "coherent_rabi_plus_heldout_ss_control_provisional"
            candidate = copy.deepcopy(candidate)
            candidate.update({
                "transition_qualification_kind": kind,
                "transition_rabi_seed_mhz": float(seed["qubit_pi_freq"]),
                "transition_control_verified": bool(
                    verified_candidate is not None),
                "transition_control_audit": copy.deepcopy(verified_audit),
            })
            record.update({
                "candidate": copy.deepcopy(candidate),
                "qualification_kind": kind,
            })
            admitted.append(candidate)
            records.append(record)

        if not admitted:
            self.working = original
            self.data["control_branch_qualification"] = {
                "status": "failed", "qualified": False,
                "frequency_qualified": False,
                "selected_control_verified": False,
                "selected": None, "branches": records,
                "expensive_search_allowed": False,
                "failure": "no held-out coherent-Rabi transition was selectable",
            }
            self._maps["control_branch_qualification"] = {
                "branch_seed_frequency_mhz": np.asarray([
                    row["rabi_frequency_mhz"] for row in records], dtype=float),
                "branch_qualified": np.zeros(len(records), dtype=bool),
                "search_complete": True, "selection_confirmed": False,
            }
            raise RuntimeError(
                "no coherent-Rabi branch remained after transition selection; "
                "refusing to start the expensive joint search")

        # If any rough branch already passed the exact control audit, do not let a
        # higher one-pulse score from an unverified branch displace it.  When none pass,
        # all branches remain workable coherent-Rabi frequencies and pulse quality is
        # explicitly deferred to the optimizer and per-row final audits.
        verified = [row for row in admitted
                    if bool(row.get("transition_control_verified", False))]
        selection_pool = verified or admitted
        comparison_failure = None
        try:
            comparison = self._confirm_candidates(
                [{key: row[key] for key in self.initial}
                 for row in selection_pool],
                int(p.get("branch_compare_shots", 900)),
                int(p.get("branch_compare_blocks", 3)),
                "coherent transition branch comparison", add_to_history=True)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            comparison = []
            comparison_failure = "%s: %s" % (type(exc).__name__, exc)
        comparison_complete = bool(
            comparison and self._confirmation_batch_complete(comparison))
        informative_comparison = [
            row for row in comparison
            if (float(row.get("fidelity_lcb_95", -np.inf))
                >= float(p.get(
                    "minimum_informative_branch_fidelity_lcb", 0.60))
                and float(row.get("sep_sigma", -np.inf))
                >= float(p.get(
                    "minimum_informative_branch_separation_sigma", 0.75)))]
        if informative_comparison:
            selected = max(informative_comparison,
                           key=self._authoritative_rank)
            selection_reason = "informative held-out branch comparison"
        elif verified:
            selected = max(verified, key=self._authoritative_rank)
            selection_reason = "exact odd/even verified branch fallback"
        else:
            bootstrap = self._bootstrap_control_candidate
            admitted_frequencies = [
                float(row["qubit_pi_freq"]) for row in admitted]
            radius = float(p.get("qualified_basin_radius_mhz", 2.0))
            if (isinstance(bootstrap, dict)
                    and all(key in bootstrap for key in self.initial)
                    and any(abs(float(bootstrap["qubit_pi_freq"]) - frequency)
                            <= radius for frequency in admitted_frequencies)):
                selected = copy.deepcopy(bootstrap)
                selection_reason = (
                    "passive bootstrap retained because branch comparison had "
                    "no informative contrast")
            else:
                selected = max(selection_pool, key=self._authoritative_rank)
                selection_reason = (
                    "strongest coherent-Rabi seed retained because branch "
                    "comparison had no informative contrast")
        selected_key = _control_key(selected)
        exact_selected_record = next((
            row for row in records
            if isinstance(row.get("candidate"), dict)
            and _control_key(row["candidate"]) == selected_key), None)
        selected_record = exact_selected_record or min(
            records, key=lambda row: abs(
                float(row["candidate"]["qubit_pi_freq"])
                - float(selected["qubit_pi_freq"])))
        selected_verified = bool(
            exact_selected_record is not None
            and selected_record.get("control_verified", False))
        selected_audit = copy.deepcopy(selected_record.get("control_audit"))
        protected_candidates = []
        if isinstance(self._bootstrap_control_candidate, dict):
            protected_candidates.append(self._bootstrap_control_candidate)
        protected_candidates.extend(comparison)
        protected_candidates.extend(admitted)
        self._qualified_control_candidates = copy.deepcopy(
            _unique_candidates(protected_candidates))
        self._qualified_transition_frequencies = sorted(set(
            round(float(row["qubit_pi_freq"]), 9) for row in admitted))
        self._qualified_transition_frequency = float(selected["qubit_pi_freq"])
        self._qualified_control_key = selected_key
        self._final_control_verified_key = (
            selected_key if selected_verified else None)
        self.working = {key: selected[key] for key in self.initial}
        if selected_verified and isinstance(selected_audit, dict):
            self._maps["final_control_verify"] = selected_audit
        else:
            self._maps.pop("final_control_verify", None)
        selected_stage = selected_record.get("parity", {}).get("stage")
        if selected_stage and selected_stage in self._maps:
            selected_map = copy.deepcopy(self._maps[selected_stage])
            selected_edge = selected_record.get("parity", {}).get("edge_stage")
            selected_map.update({
                "branch_records": copy.deepcopy(records),
                "selected_branch": int(selected_record["branch"]),
                "selected_frequency_mhz": self._qualified_transition_frequency,
                "branch_selection_confirmed": bool(informative_comparison),
                "branch_selection_reason": selection_reason,
            })
            self._maps["parity_chevron"] = selected_map
            if selected_edge and selected_edge in self._maps:
                self._maps["parity_chevron_edge"] = copy.deepcopy(
                    self._maps[selected_edge])
        self._maps["control_branch_qualification"] = {
            "branch_seed_frequency_mhz": np.asarray([
                row["rabi_frequency_mhz"] for row in records], dtype=float),
            "branch_qualified": np.asarray([
                row["status"].startswith("frequency_qualified")
                for row in records], dtype=bool),
            "branch_control_verified": np.asarray([
                bool(row.get("control_verified", False))
                for row in records], dtype=bool),
            "qualified_frequency_mhz": np.asarray([
                row["qubit_pi_freq"] for row in admitted], dtype=float),
            "selected_frequency_mhz": self._qualified_transition_frequency,
            "selected_control_verified": selected_verified,
            "branch_comparison_complete": comparison_complete,
            "branch_comparison_informative": bool(informative_comparison),
            "selection_reason": selection_reason,
            "search_complete": True, "selection_confirmed": True,
        }
        self.data["control_branch_qualification"] = {
            "status": ("frequency_qualified_control_verified"
                       if selected_verified else
                       "frequency_qualified_control_provisional"),
            "qualified": True, "frequency_qualified": True,
            "selected_control_verified": selected_verified,
            "selected": copy.deepcopy(selected), "branches": records,
            "comparison": copy.deepcopy(comparison),
            "comparison_complete": comparison_complete,
            "comparison_failure": comparison_failure,
            "comparison_informative": bool(informative_comparison),
            "qualified_frequencies_mhz": list(
                self._qualified_transition_frequencies),
            "selection_reason": selection_reason,
            "expensive_search_allowed": True,
        }
        self._adopt(selected, "parity_chevron")
        self._record_key_evidence(
            ("qubit_freq", "qubit_pi_freq"),
            "control_branch_qualification", True)
        return selected

    def _candidate_in_qualified_transition(self, candidate):
        """Whether a candidate remains in the pre-qualified transition basin."""
        centers = list(self._qualified_transition_frequencies)
        if not centers and self._qualified_transition_frequency is not None:
            centers = [float(self._qualified_transition_frequency)]
        if not centers:
            return True
        try:
            frequency = float(candidate["qubit_pi_freq"])
        except (KeyError, TypeError, ValueError, OverflowError):
            return False
        radius = float(self.params["parity_chevron"].get(
            "qualified_basin_radius_mhz", 2.0))
        return bool(np.isfinite(frequency) and any(
            abs(frequency - float(center)) <= radius for center in centers))

    def _qualified_transition_rows(self, rows):
        """Remove measurements from spectral branches rejected before joint search."""
        return [row for row in rows
                if isinstance(row, dict)
                and self._candidate_in_qualified_transition(row)]

    def _stage_pre_expensive_gate(self):
        """Require frequency identity, not a pre-optimized pulse, before joint search."""
        resonator = self._maps.get("resonator", {})
        spectroscopy = self._maps.get("spectroscopy", {})
        rabi = self._maps.get("iq_rabi", {})
        qualification = self.data.get("control_branch_qualification", {})
        failures = []
        if not (self._discovery_status.get("resonator", False)
                and bool(resonator.get("search_complete", False))
                and bool(resonator.get("selection_confirmed", False))):
            failures.append("resonator discovery/confirmation is incomplete")
        if not (self._discovery_status.get("spectroscopy", False)
                and bool(spectroscopy.get("search_complete", False))
                and bool(spectroscopy.get("selection_confirmed", False))):
            failures.append("opposed qubit spectroscopy is incomplete")
        if not (bool(rabi.get("coherent_witness", False))
                and bool(rabi.get("selection_confirmed", False))):
            failures.append("no confirmed coherent Rabi witness exists")
        if not (isinstance(qualification, dict)
                and bool(qualification.get("frequency_qualified", False))
                and isinstance(qualification.get("selected"), dict)
                and self._qualified_control_key is not None):
            failures.append("no coherent-Rabi-qualified transition was selected")
        selected = qualification.get("selected") if isinstance(
            qualification, dict) else None
        if isinstance(selected, dict):
            if _control_key(selected) != self._qualified_control_key:
                failures.append("qualified transition key is internally inconsistent")
            coherent_frequencies = np.asarray(
                rabi.get("coherent_witness_frequencies_mhz", []), dtype=float)
            maximum_shift = float(self.params["parity_chevron"].get(
                "max_rabi_frequency_shift_mhz", 2.0))
            if (not coherent_frequencies.size
                    or np.min(np.abs(coherent_frequencies
                                     - float(selected["qubit_pi_freq"])))
                    > maximum_shift):
                failures.append(
                    "selected transition is not connected to a coherent Rabi line")
        passed = not failures
        gate = {
            "passed": passed, "failures": failures,
            "resonator_frequency_mhz": float(self._resonator_seed),
            "qubit_frequency_mhz": (
                float(self._qualified_transition_frequency)
                if self._qualified_transition_frequency is not None else np.nan),
            "control_key": list(self._qualified_control_key or ()),
            "rough_control_verified": bool(
                qualification.get("selected_control_verified", False))
            if isinstance(qualification, dict) else False,
            "rough_control_status": qualification.get("status")
            if isinstance(qualification, dict) else None,
            "qualification_basis": (
                "confirmed_resonator_plus_opposed_spectroscopy_plus_coherent_rabi"),
            "search_complete": passed, "selection_confirmed": passed,
        }
        self._maps["pre_expensive_gate"] = gate
        self.data["pre_expensive_gate"] = copy.deepcopy(gate)
        if not passed:
            self.data["control_branch_qualification"][
                "expensive_search_allowed"] = False
            raise RuntimeError(
                "pre-expensive calibration gate failed: %s" % "; ".join(failures))
        self.data["control_branch_qualification"][
            "expensive_search_allowed"] = True
        return copy.deepcopy(selected)

    def _stage_fine_frequency(self, stage="fine_frequency"):
        p = self.params["fine_frequency"]
        if not p.get("enabled", True):
            self._log(stage, "SKIP", "disabled")
            return None
        incumbent = dict(self.working)
        initial = self._inverse_pair_map(
            stage, incumbent, p, incumbent["qubit_pi_freq"])
        initial_edge = initial["index"] in (
            0, initial["frequencies"].size - 1)
        self._maps[stage]["initial_edge_winner"] = bool(initial_edge)
        seeds = [initial["seed"]]
        preferred = initial["seed"]
        maps = [initial]
        final_edge = bool(initial_edge)
        expansion_ok = False
        if initial_edge:
            self._maps[stage]["search_complete"] = False
            self._log(
                stage, "WARN",
                "inverse-pair minimum is on a boundary; running one centered/outward "
                "frequency expansion before deciding")
            try:
                expanded = self._inverse_pair_map(
                    stage + "_edge", incumbent, p,
                    initial["seed"]["qubit_pi_freq"])
                final_edge = expanded["index"] in (
                    0, expanded["frequencies"].size - 1)
                self._maps[expanded["stage"]]["edge_winner"] = bool(final_edge)
                self._maps[expanded["stage"]]["search_complete"] = bool(
                    expanded["data_complete"] and not final_edge)
                seeds.insert(0, expanded["seed"])
                preferred = expanded["seed"]
                maps.append(expanded)
                expansion_ok = True
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                final_edge = True
                self._maps[stage]["expansion_failure"] = \
                    "%s: %s" % (type(exc).__name__, exc)
                self._log(
                    stage, "WARN",
                    "boundary expansion failed (%s: %s); directly confirming the "
                    "best measured edge point and incumbent anyway"
                    % (type(exc).__name__, exc))
        confirmed = self._confirm_candidates(
            seeds + [incumbent], p["confirm_shots"], p["confirm_blocks"],
            "%s direct replay" % stage)
        confirmation_complete = self._confirmation_batch_complete(confirmed)
        chosen = self._noninferior_seed(confirmed, preferred, incumbent)
        self._adopt(chosen, stage)
        for mapping in maps:
            self._maps[mapping["stage"]]["selection_confirmed"] = True
            self._maps[mapping["stage"]]["selection_confirmation_complete"] = bool(
                confirmation_complete)
            if not confirmation_complete:
                self._maps[mapping["stage"]]["search_complete"] = False
        complete = bool(
            confirmation_complete and initial["data_complete"]
            and (not initial_edge
                 or (expansion_ok and maps[-1]["data_complete"] and not final_edge)))
        self._maps[stage]["expanded"] = bool(initial_edge)
        self._maps[stage]["edge_winner"] = bool(initial_edge and final_edge)
        self._maps[stage]["search_complete"] = complete
        self._record_key_evidence(
            ("qubit_freq", "qubit_pi_freq"), stage, complete)
        if initial_edge and not final_edge and complete:
            self._log(stage, "OK",
                      "expanded inverse-pair minimum is interior; frequency search "
                      "is complete")
        elif initial_edge:
            self._log(stage, "WARN",
                      "expanded inverse-pair minimum remains boundary-limited or "
                      "incomplete; best candidate retained for the exact final tuple "
                      "replay")
        elif not complete:
            self._log(stage, "WARN",
                      "inverse-pair map was incomplete; confirmed candidate retained "
                      "without independent coordinate-search evidence")
        return chosen

    def _stage_amplified_error(self):
        p = self.params["amplified_error"]
        if not p.get("enabled", True):
            self._log("amplified_error", "SKIP", "disabled")
            return None
        self._log(
            "amplified_error", "OK",
            "QUA-style amplified amplitude error (AAE) refinement for X180: "
            "joint multi-depth parity across frequency and gain")
        incumbent = dict(self.working)
        initial = self._parity_map(
            "amplified_error", incumbent, p,
            incumbent["qubit_pi_freq"], incumbent["qubit_pi_gain"],
            p["calibration_shots"], "amplified error")
        index = initial["index"]
        initial_edge = (index[0] in (0, initial["frequencies"].size - 1)
                        or index[1] in (0, initial["gains"].size - 1))
        self._maps["amplified_error"]["initial_edge_winner"] = bool(initial_edge)
        self._maps["amplified_error"].update({
            "calibration_kind": "amplified_amplitude_error_x180",
            "qua_analogue": "ALE_tune_1Q.py / m_amplified_amplitude_error.AAE",
            "leakage_measurement": False,
        })
        seeds = [initial["seed"]]
        preferred = initial["seed"]
        maps = [initial]
        final_edge = bool(initial_edge)
        expansion_ok = False
        if initial_edge:
            self._maps["amplified_error"]["search_complete"] = False
            self._log(
                "amplified_error", "WARN",
                "raw variable-depth optimum is on a boundary; running one centered/"
                "outward frequency/gain expansion before deciding")
            try:
                expanded = self._parity_map(
                    "amplified_error_edge", incumbent, p,
                    initial["seed"]["qubit_pi_freq"],
                    initial["seed"]["qubit_pi_gain"],
                    p["calibration_shots"], "amplified error expansion")
                expanded_index = expanded["index"]
                final_edge = bool(
                    expanded_index[0] in (0, expanded["frequencies"].size - 1)
                    or expanded_index[1] in (0, expanded["gains"].size - 1))
                self._maps["amplified_error_edge"]["edge_winner"] = final_edge
                self._maps["amplified_error_edge"].update({
                    "calibration_kind": "amplified_amplitude_error_x180",
                    "qua_analogue": (
                        "ALE_tune_1Q.py / m_amplified_amplitude_error.AAE"),
                    "leakage_measurement": False,
                })
                self._maps["amplified_error_edge"]["search_complete"] = bool(
                    expanded["data_complete"] and not final_edge)
                seeds.insert(0, expanded["seed"])
                preferred = expanded["seed"]
                maps.append(expanded)
                expansion_ok = True
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                final_edge = True
                self._maps["amplified_error"]["expansion_failure"] = \
                    "%s: %s" % (type(exc).__name__, exc)
                self._log(
                    "amplified_error", "WARN",
                    "boundary expansion failed (%s: %s); directly confirming the "
                    "best measured edge point and incumbent anyway"
                    % (type(exc).__name__, exc))
        confirmed = self._confirm_candidates(
            seeds + [incumbent], p["confirm_shots"], p["confirm_blocks"],
            "amplified-error direct replay")
        confirmation_complete = self._confirmation_batch_complete(confirmed)
        chosen = self._noninferior_seed(confirmed, preferred, incumbent)
        self._adopt(chosen, "amplified_error")
        for mapping in maps:
            self._maps[mapping["stage"]]["selection_confirmed"] = True
            self._maps[mapping["stage"]]["selection_confirmation_complete"] = bool(
                confirmation_complete)
            if not confirmation_complete:
                self._maps[mapping["stage"]]["search_complete"] = False
        complete = bool(
            confirmation_complete and initial["data_complete"]
            and (not initial_edge
                 or (expansion_ok and maps[-1]["data_complete"] and not final_edge)))
        self._maps["amplified_error"]["expanded"] = bool(initial_edge)
        self._maps["amplified_error"]["edge_winner"] = bool(
            initial_edge and final_edge)
        self._maps["amplified_error"]["search_complete"] = complete
        self._record_key_evidence(
            ("qubit_freq", "qubit_pi_freq", "qubit_pi_gain"),
            "amplified_error", complete)
        if initial_edge and not final_edge and complete:
            self._log("amplified_error", "OK",
                      "expanded variable-depth optimum is interior; amplified control "
                      "search is complete")
        elif initial_edge:
            self._log("amplified_error", "WARN",
                      "expanded variable-depth optimum remains boundary-limited or "
                      "incomplete; best candidate retained for the exact final tuple "
                      "replay")
        elif not complete:
            self._log("amplified_error", "WARN",
                      "variable-depth map was incomplete; confirmed candidate retained "
                      "without independent coordinate-search evidence")
        return chosen

    def _stage_readout_grid(self, stage="readout_grid", local=False,
                            record_evidence=True, prior_complete=True):
        p = self.params["readout"]
        if not p.get("enabled", True):
            self._log(stage, "SKIP", "disabled")
            return None
        if local:
            center_freq = float(self.working["read_pulse_freq"])
            span = p["local_freq_span_mhz"]
            nfreq = p["local_freq_points"]
            center_gain = int(self.working["read_pulse_gain"])
            fraction = float(p["local_gain_fraction"])
            gains = self._gain_axis(
                center_gain * (1.0 - fraction), center_gain * (1.0 + fraction),
                p["local_gain_points"], include=[center_gain])
        else:
            incumbent = float(self.working["read_pulse_freq"])
            seed = float(self._resonator_seed)
            center_freq = 0.5 * (incumbent + seed)
            span = max(float(p["freq_span_mhz"]),
                       abs(incumbent - seed) + 0.5 * float(p["freq_span_mhz"]))
            nfreq = p["freq_points"]
            gains = self._gain_axis(
                p["gain_min"], p["gain_max"], p["gain_points"],
                include=[self.working["read_pulse_gain"]])
        freqs = self._float_axis(
            center_freq, span, nfreq,
            include=[self.working["read_pulse_freq"], self._resonator_seed])
        candidates = [
            _with_candidate(self.working, read_pulse_freq=float(freq),
                            read_pulse_gain=int(gain))
            for freq in freqs for gain in gains
        ]
        result = self._direct_grid(
            stage, candidates, (freqs.size, gains.size),
            {"read_frequency_mhz": freqs, "read_gain_dac": gains},
            p["shots"], p["shortlist"], p["confirm_shots"],
            p["confirm_blocks"])
        coverage_complete = bool(
            prior_complete and self._maps[stage].get("search_complete", False))
        at_edge = (np.isclose(self.working["read_pulse_freq"], freqs[0])
                   or np.isclose(self.working["read_pulse_freq"], freqs[-1])
                   or int(self.working["read_pulse_gain"]) in
                   (int(gains[0]), int(gains[-1])))
        self._maps[stage]["edge_winner"] = bool(at_edge)
        self._maps[stage]["eligibility_evidence_enabled"] = bool(record_evidence)
        if at_edge:
            self._maps[stage]["search_complete"] = False
            if record_evidence:
                self._record_key_evidence(
                    ("read_pulse_freq", "read_pulse_gain"), stage, False)
        if at_edge and not stage.endswith("_edge"):
            self._log(stage, "WARN",
                      "confirmed winner is on a grid edge; expanding once around it")
            return self._stage_readout_grid(
                stage + "_edge", local=True, record_evidence=record_evidence,
                prior_complete=coverage_complete)
        if at_edge:
            self._log(stage, "WARN",
                      "winner remains on the expanded edge; result retained but this "
                      "readout map is not independent coordinate-search evidence")
        elif record_evidence:
            self._record_key_evidence(
                ("read_pulse_freq", "read_pulse_gain"), stage,
                coverage_complete)
            if not coverage_complete:
                self._log(stage, "WARN",
                          "winner confirmed, but incomplete upstream/map coverage makes "
                          "the exact final tuple replay responsible for write safety")
        return result

    def _stage_readout_length(self):
        p = self.params["readout_length"]
        if not p.get("enabled", True):
            self._log("readout_length", "SKIP", "disabled")
            return None
        values = sorted(set(float(v) for v in p["values_us"]
                            if np.isfinite(v) and float(v) > 0)
                        | {float(self.working["read_length"])})
        center_frequency = float(self.working["read_pulse_freq"])
        frequency_offsets = np.linspace(
            -float(p["freq_span_mhz"]) / 2.0,
            float(p["freq_span_mhz"]) / 2.0, int(p["freq_points"]))
        actual_gains = self._gain_axis(
            p.get("gain_min", self.params["readout"]["gain_min"]),
            p.get("gain_max", self.params["readout"]["gain_max"]),
            p["gain_points"], include=[self.working["read_pulse_gain"]])
        candidates = [
            _with_candidate(
                self.working, read_length=value,
                read_pulse_freq=float(center_frequency + offset),
                read_pulse_gain=int(gain))
            for value in values for offset in frequency_offsets for gain in actual_gains
        ]
        result = self._direct_grid(
            "readout_length", candidates,
            (len(values), len(frequency_offsets), len(actual_gains)),
            {"read_length_us": np.asarray(values),
             "frequency_offset_mhz": frequency_offsets,
             "read_gain_dac": actual_gains}, p["shots"], p["shortlist"],
            p["confirm_shots"], p["confirm_blocks"],
            coverage_values=[row["read_length"] for row in candidates],
            coverage_per_value=p.get("confirm_per_length", 2),
            primary_fidelity_only=True)
        initial_coverage_complete = bool(
            self._maps["readout_length"].get("search_complete", False))
        self._maps["readout_length"]["actual_gain_dac"] = actual_gains
        selected_length = float(self.working["read_length"])
        length_edge = (np.isclose(selected_length, values[0])
                       or np.isclose(selected_length, values[-1]))
        frequency_edge = (
            np.isclose(self.working["read_pulse_freq"],
                       center_frequency + frequency_offsets[0])
            or np.isclose(self.working["read_pulse_freq"],
                          center_frequency + frequency_offsets[-1]))
        gain_edge = int(self.working["read_pulse_gain"]) in (
            int(actual_gains[0]), int(actual_gains[-1]))
        at_edge = bool(length_edge or frequency_edge or gain_edge)
        self._maps["readout_length"]["edge_winner"] = bool(at_edge)
        self._maps["readout_length"]["edge_dimensions"] = {
            "read_length": bool(length_edge),
            "read_pulse_freq": bool(frequency_edge),
            "read_pulse_gain": bool(gain_edge),
        }
        if at_edge:
            self._maps["readout_length"]["search_complete"] = False
            extension = (max(float(p["min_us"]), 0.5 * selected_length)
                         if np.isclose(selected_length, values[0])
                         else min(float(p["max_us"]), 1.5 * selected_length))
            self._record_key_evidence(
                ("read_pulse_freq", "read_pulse_gain", "read_length"),
                "readout_length", False)
            if length_edge and not np.isclose(extension, selected_length):
                self._log("readout_length", "WARN",
                          "length winner is on an edge; testing %.1f us once" % extension)
                incumbent = dict(self.working)
                edge_lengths = np.asarray([selected_length, extension], dtype=float)
                edge_gains = self._gain_axis(
                    p.get("gain_min", self.params["readout"]["gain_min"]),
                    p.get("gain_max", self.params["readout"]["gain_max"]),
                    p["gain_points"], include=[incumbent["read_pulse_gain"]])
                edge_candidates = [
                    _with_candidate(
                        incumbent, read_length=float(length),
                        read_pulse_freq=float(incumbent["read_pulse_freq"] + offset),
                        read_pulse_gain=int(gain))
                    for length in edge_lengths for offset in frequency_offsets
                    for gain in edge_gains
                ]
                result = self._direct_grid(
                    "readout_length_edge", edge_candidates,
                    (2, len(frequency_offsets), len(edge_gains)),
                    {"read_length_us": edge_lengths,
                     "frequency_offset_mhz": frequency_offsets,
                     "read_gain_dac": edge_gains}, p["shots"], p["shortlist"],
                    p["confirm_shots"], p["confirm_blocks"],
                    coverage_values=[row["read_length"]
                                     for row in edge_candidates],
                    coverage_per_value=p.get("confirm_per_length", 2),
                    primary_fidelity_only=True)
                extension_coverage_complete = bool(
                    self._maps["readout_length_edge"].get(
                        "search_complete", False))
                self._maps["readout_length_edge"]["actual_gain_dac"] = edge_gains
                extension_won = np.isclose(float(self.working["read_length"]), extension)
                edge_frequency_limited = (
                    np.isclose(self.working["read_pulse_freq"],
                               incumbent["read_pulse_freq"] + frequency_offsets[0])
                    or np.isclose(self.working["read_pulse_freq"],
                                  incumbent["read_pulse_freq"] + frequency_offsets[-1]))
                edge_gain_limited = int(self.working["read_pulse_gain"]) in (
                    int(edge_gains[0]), int(edge_gains[-1]))
                unresolved = bool(
                    extension_won or edge_frequency_limited or edge_gain_limited)
                self._maps["readout_length_edge"]["edge_winner"] = unresolved
                self._maps["readout_length_edge"]["edge_dimensions"] = {
                    "read_length": bool(extension_won),
                    "read_pulse_freq": bool(edge_frequency_limited),
                    "read_pulse_gain": bool(edge_gain_limited),
                }
                extension_complete = bool(
                    initial_coverage_complete and extension_coverage_complete
                    and not unresolved)
                self._maps["readout_length_edge"]["search_complete"] = \
                    extension_complete
                self._record_key_evidence(
                    ("read_pulse_freq", "read_pulse_gain", "read_length"),
                    "readout_length_edge", extension_complete)
                if unresolved:
                    self._log("readout_length_edge", "WARN",
                              "expanded joint search remains boundary-limited in %s; "
                              "retained for the exact final tuple replay"
                              % ", ".join(key for key, value in
                                          self._maps["readout_length_edge"]
                                          ["edge_dimensions"].items() if value))
            elif at_edge:
                self._log(
                    "readout_length", "WARN",
                    "joint length search is boundary-limited in %s; retained and a "
                    "local readout refinement will follow, but this length comparison "
                    "is not write evidence"
                    % ", ".join(key for key, value in
                                self._maps["readout_length"]["edge_dimensions"].items()
                                if value))
        else:
            self._record_key_evidence(
                ("read_pulse_freq", "read_pulse_gain", "read_length"),
                "readout_length", initial_coverage_complete)
            if not initial_coverage_complete:
                self._log(
                    "readout_length", "WARN",
                    "winner confirmed, but incomplete map coverage makes the joint "
                    "length result report-only")
        # Every length was compared after its own local f/g retune.  One final fine
        # pass around the winning three-dimensional cell removes coarse-grid error.
        if self.params["readout"].get("enabled", True):
            self._stage_readout_grid("readout_after_length", local=True)
        return result

    def _stage_qubit_grid(self, stage="qubit_grid", local=False,
                          prior_complete=True):
        p = self.params["qubit"]
        if not p.get("enabled", True):
            self._log(stage, "SKIP", "disabled")
            return None
        if local:
            span, nfreq = p["local_freq_span_mhz"], p["local_freq_points"]
            fraction, ngain = p["local_gain_fraction"], p["local_gain_points"]
        else:
            span, nfreq = p["freq_span_mhz"], p["freq_points"]
            fraction, ngain = p["gain_fraction"], p["gain_points"]
        center_freq = float(self.working["qubit_pi_freq"])
        center_gain = int(self.working["qubit_pi_gain"])
        freqs = self._float_axis(center_freq, span, nfreq, include=[center_freq])
        gains = self._gain_axis(
            center_gain * (1.0 - float(fraction)),
            center_gain * (1.0 + float(fraction)), ngain, include=[center_gain])
        candidates = [
            _with_candidate(self.working, qubit_pi_freq=float(freq),
                            qubit_pi_gain=int(gain))
            for freq in freqs for gain in gains
        ]
        result = self._direct_grid(
            stage, candidates, (freqs.size, gains.size),
            {"qubit_frequency_mhz": freqs, "qubit_gain_dac": gains},
            p["shots"], p["shortlist"], p["confirm_shots"],
            p["confirm_blocks"])
        coverage_complete = bool(
            prior_complete and self._maps[stage].get("search_complete", False))
        at_edge = (np.isclose(self.working["qubit_pi_freq"], freqs[0])
                   or np.isclose(self.working["qubit_pi_freq"], freqs[-1])
                   or int(self.working["qubit_pi_gain"]) in
                   (int(gains[0]), int(gains[-1])))
        self._maps[stage]["edge_winner"] = bool(at_edge)
        if at_edge:
            self._maps[stage]["search_complete"] = False
            self._record_key_evidence(
                ("qubit_freq", "qubit_pi_freq", "qubit_pi_gain"), stage, False)
        if at_edge and not stage.endswith("_edge"):
            self._log(stage, "WARN",
                      "confirmed winner is on a grid edge; expanding once around it")
            return self._stage_qubit_grid(
                stage + "_edge", local=True,
                prior_complete=coverage_complete)
        if at_edge:
            self._log(stage, "WARN",
                      "winner remains on the expanded edge; result retained but this "
                      "control map is not independent coordinate-search evidence")
        else:
            self._record_key_evidence(
                ("qubit_freq", "qubit_pi_freq", "qubit_pi_gain"), stage,
                coverage_complete)
            if not coverage_complete:
                self._log(stage, "WARN",
                          "winner confirmed, but incomplete upstream/map coverage makes "
                          "the exact final tuple replay responsible for write safety")
        return result

    def _stage_pulse_duration(self):
        p = self.params["pulse_duration"]
        if not p.get("enabled", True):
            self._log("pulse_duration", "SKIP", "disabled")
            return None
        sigma_values = sorted(set(float(v) for v in p["sigma_values_us"]
                                  if np.isfinite(v) and float(v) > 0)
                              | {float(self.working["sigma"])})
        frequency_offsets = np.linspace(
            -float(p["freq_span_mhz"]) / 2.0,
            float(p["freq_span_mhz"]) / 2.0, int(p["freq_points"]))
        gain_scales = np.linspace(
            1.0 - float(p["gain_fraction"]),
            1.0 + float(p["gain_fraction"]), int(p["gain_points"]))
        old_sigma = float(self.working["sigma"])
        old_gain = float(self.working["qubit_pi_gain"])
        old_frequency = float(self.working["qubit_pi_freq"])
        candidates = []
        actual_gains = np.empty((len(sigma_values), len(gain_scales)), dtype=int)
        for si, sigma in enumerate(sigma_values):
            # Gaussian rotation area is approximately gain*sigma.  The area scaling is
            # only a center; every duration then gets a real local gain/frequency grid.
            predicted_gain = old_gain * old_sigma / sigma
            for gi, scale in enumerate(gain_scales):
                actual_gains[si, gi] = int(np.clip(
                    round(predicted_gain * scale), 1, 32767))
            for offset in frequency_offsets:
                for gain in actual_gains[si]:
                    candidates.append(_with_candidate(
                        self.working, sigma=float(sigma),
                        qubit_pi_freq=float(old_frequency + offset),
                        qubit_pi_gain=int(gain)))
        result = self._direct_grid(
            "pulse_duration", candidates,
            (len(sigma_values), len(frequency_offsets), len(gain_scales)),
            {"sigma_us": np.asarray(sigma_values),
             "frequency_offset_mhz": frequency_offsets,
             "gain_scale": gain_scales},
            p["shots"], p["shortlist"], p["confirm_shots"],
            p["confirm_blocks"],
            coverage_values=[row["sigma"] for row in candidates],
            coverage_per_value=p.get("confirm_per_sigma", 2),
            primary_fidelity_only=True)
        initial_coverage_complete = bool(
            self._maps["pulse_duration"].get("search_complete", False))
        self._maps["pulse_duration"]["actual_gain_dac"] = actual_gains
        selected_sigma = float(self.working["sigma"])
        selected_sigma_index = int(np.argmin(
            np.abs(np.asarray(sigma_values, dtype=float) - selected_sigma)))
        sigma_edge = (np.isclose(selected_sigma, sigma_values[0])
                      or np.isclose(selected_sigma, sigma_values[-1]))
        frequency_edge = (
            np.isclose(self.working["qubit_pi_freq"],
                       old_frequency + frequency_offsets[0])
            or np.isclose(self.working["qubit_pi_freq"],
                          old_frequency + frequency_offsets[-1]))
        selected_gain_axis = actual_gains[selected_sigma_index]
        gain_edge = int(self.working["qubit_pi_gain"]) in (
            int(selected_gain_axis[0]), int(selected_gain_axis[-1]))
        at_edge = bool(sigma_edge or frequency_edge or gain_edge)
        self._maps["pulse_duration"]["edge_winner"] = bool(at_edge)
        self._maps["pulse_duration"]["edge_dimensions"] = {
            "sigma": bool(sigma_edge),
            "qubit_pi_freq": bool(frequency_edge),
            "qubit_pi_gain": bool(gain_edge),
        }
        if at_edge:
            self._maps["pulse_duration"]["search_complete"] = False
            self._record_key_evidence(
                ("qubit_freq", "qubit_pi_freq", "qubit_pi_gain", "sigma"),
                "pulse_duration", False)
            if np.isclose(selected_sigma, sigma_values[0]):
                extension = max(0.025, 0.5 * selected_sigma)
            else:
                extension = min(1.0, 1.5 * selected_sigma)
            if sigma_edge and not np.isclose(extension, selected_sigma):
                self._log("pulse_duration", "WARN",
                          "duration winner is on an edge; testing %.1f ns once"
                          % (4000.0 * extension))
                incumbent = dict(self.working)
                extension_sigmas = np.asarray([selected_sigma, extension], dtype=float)
                edge_candidates = []
                edge_gains = np.empty((2, len(gain_scales)), dtype=int)
                for si, sigma in enumerate(extension_sigmas):
                    predicted = (float(incumbent["qubit_pi_gain"])
                                 * selected_sigma / sigma)
                    edge_gains[si] = np.clip(
                        np.rint(predicted * gain_scales), 1, 32767).astype(int)
                    for offset in frequency_offsets:
                        for gain in edge_gains[si]:
                            edge_candidates.append(_with_candidate(
                                incumbent, sigma=float(sigma),
                                qubit_pi_freq=float(
                                    incumbent["qubit_pi_freq"] + offset),
                                qubit_pi_gain=int(gain)))
                edge_result = self._direct_grid(
                    "pulse_duration_edge", edge_candidates,
                    (2, len(frequency_offsets), len(gain_scales)),
                    {"sigma_us": extension_sigmas,
                     "frequency_offset_mhz": frequency_offsets,
                     "gain_scale": gain_scales},
                    p["shots"], p["shortlist"], p["confirm_shots"],
                    p["confirm_blocks"],
                    coverage_values=[row["sigma"] for row in edge_candidates],
                    coverage_per_value=p.get("confirm_per_sigma", 2),
                    primary_fidelity_only=True)
                extension_coverage_complete = bool(
                    self._maps["pulse_duration_edge"].get(
                        "search_complete", False))
                self._maps["pulse_duration_edge"]["actual_gain_dac"] = edge_gains
                extension_won = np.isclose(float(self.working["sigma"]), extension)
                selected_edge_sigma = int(np.argmin(np.abs(
                    extension_sigmas - float(self.working["sigma"]))))
                edge_frequency_limited = (
                    np.isclose(self.working["qubit_pi_freq"],
                               incumbent["qubit_pi_freq"] + frequency_offsets[0])
                    or np.isclose(self.working["qubit_pi_freq"],
                                  incumbent["qubit_pi_freq"] + frequency_offsets[-1]))
                edge_gain_limited = int(self.working["qubit_pi_gain"]) in (
                    int(edge_gains[selected_edge_sigma, 0]),
                    int(edge_gains[selected_edge_sigma, -1]))
                unresolved = bool(
                    extension_won or edge_frequency_limited or edge_gain_limited)
                self._maps["pulse_duration_edge"]["edge_winner"] = unresolved
                self._maps["pulse_duration_edge"]["edge_dimensions"] = {
                    "sigma": bool(extension_won),
                    "qubit_pi_freq": bool(edge_frequency_limited),
                    "qubit_pi_gain": bool(edge_gain_limited),
                }
                extension_complete = bool(
                    initial_coverage_complete and extension_coverage_complete
                    and not unresolved)
                self._maps["pulse_duration_edge"]["search_complete"] = \
                    extension_complete
                self._record_key_evidence(
                    ("qubit_freq", "qubit_pi_freq", "qubit_pi_gain", "sigma"),
                    "pulse_duration_edge", extension_complete)
                if unresolved:
                    self._log("pulse_duration_edge", "WARN",
                              "expanded joint duration search remains boundary-limited "
                              "in %s; candidate is retained for exact final tuple replay"
                              % ", ".join(key for key, value in
                                          self._maps["pulse_duration_edge"]
                                          ["edge_dimensions"].items() if value))
                return edge_result
            self._log(
                "pulse_duration", "WARN",
                "joint duration search is boundary-limited in %s; candidate is retained "
                "but this duration comparison is not write evidence"
                % ", ".join(key for key, value in
                            self._maps["pulse_duration"]["edge_dimensions"].items()
                            if value))
        else:
            self._record_key_evidence(
                ("qubit_freq", "qubit_pi_freq", "qubit_pi_gain", "sigma"),
                "pulse_duration", initial_coverage_complete)
            if not initial_coverage_complete:
                self._log(
                    "pulse_duration", "WARN",
                    "winner confirmed, but incomplete map coverage makes the joint "
                    "duration map non-authoritative until exact final tuple replay")
        return result

    # ----------------------------------------- fixed-readout-duration manual portfolio
    def _portfolio_source_rows(self):
        """Every measured complete tuple which can seed a fixed-length search."""
        rows = []
        sources = (
            [self._bootstrap_control_candidate]
            if isinstance(self._bootstrap_control_candidate, dict) else [],
            self._portfolio_aae_candidates,
            self._qualified_control_candidates,
            self.data.get("final_candidates", []),
            self.data.get("joint_search", {}).get("aae_candidates", []),
            self._joint_rows, self._confirmed, self._archive,
        )
        for source in sources:
            if not isinstance(source, (list, tuple)):
                continue
            for row in source:
                if (isinstance(row, dict)
                        and all(key in row for key in self.initial)
                        and np.isfinite(float(row.get("fidelity", np.nan)))):
                    rows.append(row)
        return self._qualified_transition_rows(rows)

    def _portfolio_control_seeds(self, rows, count):
        """Select control waveforms without promoting coarse correlated outliers."""
        count = max(int(count), 1)
        eligible = [
            row for row in rows
            if isinstance(row, dict)
            and all(key in row for key in self.initial)
            and self._candidate_in_qualified_transition(row)]
        # Once held-out multi-block controls exist, shared-ground proposal rows have
        # fulfilled their purpose.  They may still train the local surrogate, but may
        # not consume the few protected control slots at every readout duration.
        if any(self._evidence_tier(row) >= 2 for row in eligible):
            eligible = [row for row in eligible
                        if self._evidence_tier(row) >= 2]
        ordered = sorted(eligible, key=self._authoritative_rank, reverse=True)
        selected, seen = [], set()

        def add(row):
            if not isinstance(row, dict) or not all(
                    key in row for key in self.initial):
                return
            key = _control_key(row)
            if key not in seen:
                seen.add(key)
                selected.append(row)

        # The passive bootstrap is the last known control before feedback or later
        # branch-selection machinery can alter state preparation.  Give that exact
        # waveform one protected slot whenever it has real fidelity evidence.
        bootstrap = self._bootstrap_control_candidate
        if (isinstance(bootstrap, dict)
                and np.isfinite(float(bootstrap.get("fidelity", np.nan)))
                and self._candidate_in_qualified_transition(bootstrap)):
            add(bootstrap)
        for row in ordered:
            add(row)
            if len(selected) >= count:
                break
        return selected[:count]

    def _portfolio_candidates_for_length(self, read_length, source_rows):
        """Build an equally budgeted full-tuple refinement set for one duration."""
        p = self.params["duration_portfolio"]
        length = float(read_length)
        local = [row for row in source_rows
                 if np.isclose(float(row.get("read_length", np.nan)), length,
                               rtol=0.0, atol=1e-9)]
        local = sorted(local, key=self._authoritative_rank, reverse=True)
        if not local:
            return [], {
                "source_rows": 0, "native_seed_count": 0,
                "cross_seed_count": 0, "proposal_count": 0,
                "failure": "the structured joint search measured no tuple at this "
                           "readout duration",
            }

        native = _unique_candidates([
            {key: row[key] for key in self.initial}
            for row in local[:max(int(p["native_seeds_per_length"]), 1)]
        ])

        readouts, seen_readouts = [], set()

        def add_readout(row):
            if not isinstance(row, dict) or not all(
                    key in row for key in self.initial):
                return
            key = (round(float(row["read_pulse_freq"]), 9),
                   int(round(row["read_pulse_gain"])))
            if key not in seen_readouts:
                seen_readouts.add(key)
                readouts.append(row)

        # As with the control waveform, replay the passive bootstrap readout at every
        # duration.  One noisy 56-shot power cell must not prevent the known working
        # resonator/gain neighborhood from receiving equal-budget confirmation.
        if isinstance(self._bootstrap_control_candidate, dict):
            add_readout(self._bootstrap_control_candidate)
        for row in local:
            add_readout(row)
            if len(readouts) >= max(int(p["readout_seeds_per_length"]), 1):
                break
        readouts = readouts[:max(int(p["readout_seeds_per_length"]), 1)]

        # AAE and coherent-Rabi calibration are properties of the control waveform,
        # not of integration time.  Cross their best measured control basins with
        # each length's best readout basins, then remeasure the complete physical
        # tuples so no fidelity or safety evidence is borrowed across durations.
        control_source = []
        if isinstance(self._bootstrap_control_candidate, dict):
            control_source.append(self._bootstrap_control_candidate)
        control_source.extend(self._portfolio_aae_candidates)
        control_source.extend(self._qualified_control_candidates)
        aae = self.data.get("joint_search", {}).get("aae_candidates", [])
        if isinstance(aae, list):
            control_source.extend(aae)
        control_source.extend(source_rows)
        controls = self._portfolio_control_seeds(
            control_source, int(p["control_seed_count"]))

        crossed = []
        for readout in readouts:
            for control in controls:
                crossed.append(_with_candidate(
                    readout, read_length=length,
                    qubit_pi_freq=float(control["qubit_pi_freq"]),
                    qubit_pi_gain=int(control["qubit_pi_gain"]),
                    sigma=float(control["sigma"]),
                    qubit_drag_beta=float(control.get(
                        "qubit_drag_beta", 0.0))))

        training = local
        center = native[0]
        read_radius = float(p["local_read_frequency_radius_mhz"])
        qubit_radius = float(p["local_qubit_frequency_radius_mhz"])
        proposal_count = max(int(p["local_proposals_per_length"]), 0)
        proposals = []
        if proposal_count:
            limits = {
                "read_pulse_freq": (
                    float(center["read_pulse_freq"]) - read_radius,
                    float(center["read_pulse_freq"]) + read_radius),
                "read_pulse_gain": (
                    int(self.params["joint_search"]["read_gain_min"]),
                    int(self.params["joint_search"]["read_gain_max"])),
                "read_length": (length, length),
                "qubit_pi_freq": (
                    float(center["qubit_pi_freq"]) - qubit_radius,
                    float(center["qubit_pi_freq"]) + qubit_radius),
                "qubit_pi_gain": (
                    1, int(self.params["joint_search"]["qubit_gain_hard_max"])),
                "sigma": (
                    min(self.params["joint_search"]["sigma_values_us"]),
                    max(self.params["joint_search"]["sigma_values_us"])),
            }
            try:
                proposals = propose_trust_region_candidates(
                    training, rng=self.rng, count=proposal_count,
                    proposal_limits=limits,
                    read_frequency_radius_mhz=read_radius,
                    qubit_frequency_radius_mhz=qubit_radius,
                    read_gain_fraction=float(p["local_read_gain_fraction"]),
                    qubit_gain_fraction=float(p["local_qubit_gain_fraction"]),
                    trust_regions=min(
                        max(int(self.params["joint_search"]["trust_regions"]), 1),
                        max(len(native), 1)),
                    pool_size=max(
                        int(self.params["joint_search"]["trust_pool_size"]),
                        300),
                )
                proposals = self._quantize_joint_proposals(
                    proposals, center, read_radius, qubit_radius)
                proposals = [_with_candidate(row, read_length=length)
                             for row in proposals[:proposal_count]]
                proposals = self._qualified_transition_rows(proposals)
            except Exception as exc:
                proposals = []
                proposal_failure = "%s: %s" % (type(exc).__name__, exc)
            else:
                proposal_failure = None
        else:
            proposal_failure = None

        candidates = self._qualified_transition_rows(
            _unique_candidates(native + crossed + proposals))
        # Fill duplicate-collapsed sets from measured local rows.  The target is the
        # same at every duration, preserving equal opportunity under runtime limits.
        target = max(
            int(p["native_seeds_per_length"])
            + int(p["readout_seeds_per_length"]) * int(p["control_seed_count"])
            + proposal_count, 1)
        for row in local:
            if len(candidates) >= target:
                break
            candidates = _unique_candidates(candidates + [
                {key: row[key] for key in self.initial}])
        candidates = self._qualified_transition_rows(candidates)[:target]
        held_out = [row for row in local if self._evidence_tier(row) >= 2]
        return candidates, {
            "source_rows": len(local),
            "native_seed_count": len(native),
            "cross_seed_count": len(_unique_candidates(crossed)),
            "proposal_count": len(proposals),
            "target_candidate_count": target,
            "proposal_failure": proposal_failure,
            "source_max_evidence_tier": int(max(
                (self._evidence_tier(row) for row in local), default=0)),
            "source_held_out_row_count": len(held_out),
            "readout_seeded_from_proposals_only": bool(not held_out),
        }

    @staticmethod
    def _portfolio_centered_gain_axis(center, fraction, points, minimum_step,
                                      lower, upper):
        """Return an odd, deterministic DAC axis containing ``center`` exactly.

        Fractional grids alone collapse at low gain, while a fixed absolute grid is
        unnecessarily coarse at high gain.  The larger of the two spacings is used;
        clipping is explicit and the physical incumbent is always retained.
        """
        center = int(np.clip(round(center), int(lower), int(upper)))
        points = max(int(points), 3)
        if points % 2 == 0:
            points += 1
        half = points // 2
        step = max(
            int(round(abs(float(center) * float(fraction)) / max(half, 1))),
            max(int(minimum_step), 1),
        )
        values = center + step * np.arange(-half, half + 1, dtype=int)
        values = np.clip(values, int(lower), int(upper))
        return np.sort(np.unique(np.r_[values, center])).astype(int)

    def _portfolio_deterministic_gain_candidates(self, rows, length):
        """Challenge a coarse winner and its constant-area duration partners.

        Readout and X180 gains are first varied on separate axes.  Half/double sigma
        partners use inverse gain scaling only as an initial pulse-area prediction;
        every partner then receives its own measured qubit-gain axis.
        """
        p = self.params["duration_portfolio"]
        ranked = sorted(
            [row for row in rows if isinstance(row, dict)],
            key=self._authoritative_rank, reverse=True)
        if not ranked:
            return [], {"enabled": True, "failure": "no measured center"}
        center = {key: ranked[0][key] for key in self.initial}
        center = _with_candidate(center, read_length=float(length))
        read_axis = self._portfolio_centered_gain_axis(
            center["read_pulse_gain"], p["gain_axis_read_fraction"],
            p["gain_axis_read_points"], p["gain_minimum_read_step_dac"],
            self.params["joint_search"]["read_gain_min"],
            self.params["joint_search"]["read_gain_max"])
        qubit_axis = self._portfolio_centered_gain_axis(
            center["qubit_pi_gain"], p["gain_axis_qubit_fraction"],
            p["gain_axis_qubit_points"], p["gain_minimum_qubit_step_dac"],
            1, self.params["joint_search"]["qubit_gain_hard_max"])
        candidates = [
            _with_candidate(center, read_pulse_gain=int(gain))
            for gain in read_axis
        ]
        candidates.extend(
            _with_candidate(center, qubit_pi_gain=int(gain))
            for gain in qubit_axis)

        candidates = self._qualified_transition_rows(
            _unique_candidates(candidates))
        return candidates, {
            "enabled": True,
            "reference_candidate_key": list(_candidate_key(center)),
            "read_gain_axis_dac": read_axis,
            "qubit_gain_axis_dac": qubit_axis,
            "candidate_count": len(candidates),
        }

    def _portfolio_gain_zoom_candidates(self, center, length):
        """Full local 2-D interaction grid around a freshly measured winner."""
        p = self.params["duration_portfolio"]
        physical = {key: center[key] for key in self.initial}
        physical = _with_candidate(physical, read_length=float(length))
        read_axis = self._portfolio_centered_gain_axis(
            physical["read_pulse_gain"], p["gain_zoom_read_fraction"],
            p["gain_zoom_read_points"], p["gain_minimum_read_step_dac"],
            self.params["joint_search"]["read_gain_min"],
            self.params["joint_search"]["read_gain_max"])
        qubit_axis = self._portfolio_centered_gain_axis(
            physical["qubit_pi_gain"], p["gain_zoom_qubit_fraction"],
            p["gain_zoom_qubit_points"], p["gain_minimum_qubit_step_dac"],
            1, self.params["joint_search"]["qubit_gain_hard_max"])
        candidates = [
            _with_candidate(
                physical, read_pulse_gain=int(read_gain),
                qubit_pi_gain=int(qubit_gain))
            for read_gain in read_axis for qubit_gain in qubit_axis
        ]
        candidates = self._qualified_transition_rows(
            _unique_candidates(candidates))
        return candidates, {
            "reference_candidate_key": list(_candidate_key(physical)),
            "read_gain_axis_dac": read_axis,
            "qubit_gain_axis_dac": qubit_axis,
            "candidate_count": len(candidates),
        }

    def _portfolio_balance_diagnostic(self, reference, candidate):
        """Paired noninferiority certificate for an optional balanced pulse."""
        p = self.params["duration_portfolio"]
        return self._latency_noninferiority(
            reference, candidate,
            float(p.get("balanced_max_fidelity_loss", 0.010)),
            confidence_z=float(p.get("balanced_confidence_sigma", 1.96)))

    def _portfolio_screening_shortlist(self, exact_rows, selected):
        """Retain the fidelity winner plus distinct measured pulse durations."""
        p = self.params["duration_portfolio"]
        limit = max(int(p.get(
            "balanced_screen_candidates_per_length", 3)), 1)
        ordered = sorted(
            exact_rows, key=self._authoritative_rank, reverse=True)
        chosen = []

        def add(row):
            if (isinstance(row, dict)
                    and not any(_candidate_key(row) == _candidate_key(old)
                                for old in chosen)):
                chosen.append(row)

        add(selected)
        family_best = {}
        for row in ordered:
            sigma = round(float(row["sigma"]), 9)
            family_best.setdefault(sigma, row)
        # First retain the best independently replayed alternatives.  Then force the
        # longest measured family into the small screen cohort when space remains, so
        # a lower-drive constant-area challenge cannot vanish solely due to shot noise.
        for row in sorted(
                family_best.values(), key=self._authoritative_rank, reverse=True):
            add(row)
            if len(chosen) >= limit:
                break
        longest = max(family_best.values(), key=lambda row: (
            float(row["sigma"]), -int(row["qubit_pi_gain"])))
        if not any(_candidate_key(longest) == _candidate_key(row)
                   for row in chosen):
            if len(chosen) >= limit:
                chosen[-1] = longest
            else:
                add(longest)
        return _unique_candidates(chosen)[:limit]

    def _portfolio_balanced_order(self, rows, reference):
        """Rank noninferior screened rows by safety, drive stress, then fidelity."""
        eligible = []
        for raw in rows:
            row = dict(raw)
            diagnostic = self._portfolio_balance_diagnostic(reference, row)
            row["balanced_noninferiority"] = diagnostic
            if bool(diagnostic.get("eligible", False)):
                eligible.append(row)

        def rank(row):
            status = str(row.get(
                "portfolio_safety_status", "INCONCLUSIVE")).upper()
            status_rank = {"SAFE": 2, "INCONCLUSIVE": 1, "UNSAFE": 0}.get(
                status, 0)
            risk = float(row.get("portfolio_leakage_risk_ucb", np.inf))
            if not np.isfinite(risk):
                risk = np.inf
            return (
                status_rank,
                -risk,
                float(row.get("sigma", 0.0)),
                -int(row.get("qubit_pi_gain", 32767)),
                float(row.get("fidelity_lcb_95", -np.inf)),
            )
        return sorted(eligible, key=rank, reverse=True)

    def _portfolio_screen_candidate(self, candidate, length, rank):
        """Apply the active direct or operational safety test to one exact tuple."""
        p = self.params["duration_portfolio"]
        label = "portfolio %.0f us candidate %d" % (float(length), int(rank))
        if self._leakage_active:
            calibration = self._calibrate_ef_transition(candidate)
            row = self._measure_leakage_candidate(
                candidate, calibration,
                max(int(p["screen_shots"]),
                    int(self.params["leakage"]["shots"])),
                max(int(p["screen_reference_shots"]),
                    int(self.params["leakage"]["reference_shots"])),
                label)
            row["portfolio_safe"] = bool(row.get("leakage_safe", False))
            row["portfolio_safety_kind"] = "direct_shelving_p_f_and_2d_iq"
            return row
        if not self._operational_leakage_active:
            raise RuntimeError(
                "neither direct P(f) nor operational 2-D IQ safety is enabled")
        attempts = 1 + max(int(p.get("screen_drift_retries", 2)), 0)
        row = None
        for attempt in range(attempts):
            row = self._measure_operational_leakage_candidate(
                candidate, int(p["screen_shots"]),
                int(p["screen_reference_shots"]),
                "%s bracket %d" % (label, attempt + 1))
            row["portfolio_screen_attempt"] = int(attempt + 1)
            if (row.get("valid", False)
                    or row.get("failure")
                    != "the bracketing discriminator drifted"):
                break
        row["portfolio_safe"] = bool(row.get("operational_safe", False))
        row["portfolio_safety_kind"] = "resolved_2d_iq_population"
        return row

    def _portfolio_confirmation_status(self, screening, confirmation):
        """Classify exact-tuple safety without conflating failure and leakage."""
        p = self.params["leakage"]
        if not bool(screening.get("valid", False)):
            return "INCONCLUSIVE"
        if not bool(screening.get("portfolio_safe", False)):
            return "UNSAFE"
        if not bool(confirmation.get("confirmation_complete", False)):
            return "INCONCLUSIVE"
        supported = bool(confirmation.get("third_cluster_supported", False))
        if not bool(confirmation.get("third_cluster_guard_available", False)):
            return "INCONCLUSIVE"
        values = [float(confirmation.get("third_blob_excess_ucb", np.nan))]
        if not np.all(np.isfinite(values)):
            return "INCONCLUSIVE"
        if values[0] > float(p["max_third_blob_excess"]):
            return "UNSAFE"
        if supported:
            fraction = float(confirmation.get(
                "third_cluster_fraction_ucb_95", np.nan))
            single = float(confirmation.get(
                "third_cluster_single_state_fraction_ucb_95", np.nan))
            if not np.all(np.isfinite([fraction, single])):
                return "INCONCLUSIVE"
            if (fraction > float(p["max_third_cluster_fraction"])
                    or single > float(
                        p["max_single_state_third_cluster_fraction"])):
                return "UNSAFE"
        return "SAFE"

    def _portfolio_merge_evidence(self, screening, confirmation=None):
        """Attach worst-case exact-tuple safety evidence to held-out fidelity."""
        row = dict(confirmation if isinstance(confirmation, dict) else screening)
        rows = [screening]
        if isinstance(confirmation, dict):
            rows.append(confirmation)

        def worst(key, default=np.inf):
            values = [float(item.get(key, default)) for item in rows]
            finite = [value for value in values if np.isfinite(value)]
            return float(max(finite)) if finite else float(default)

        row.update({
            "third_blob_excess_ucb": worst("third_blob_excess_ucb"),
            # A supported third component in either the screening bracket or the
            # held-out replay is physical evidence and must remain in the objective;
            # a later inconclusive GMM fit cannot erase it.
            "third_cluster_supported": any(bool(item.get(
                "third_cluster_supported", False)) for item in rows),
            "third_cluster_guard_available": all(bool(item.get(
                "third_cluster_guard_available", False)) for item in rows),
            "third_cluster_fraction": worst(
                "third_cluster_fraction", default=0.0),
            "third_cluster_fraction_ucb_95": worst(
                "third_cluster_fraction_ucb_95", default=0.0),
            "third_cluster_single_state_fraction": worst(
                "third_cluster_single_state_fraction", default=0.0),
            "third_cluster_single_state_fraction_ucb_95": worst(
                "third_cluster_single_state_fraction_ucb_95", default=0.0),
            "single_p2_ucb": worst("single_p2_ucb"),
            "amplified_p2_ucb": worst("amplified_p2_ucb"),
            "portfolio_safety_kind": screening.get(
                "portfolio_safety_kind"),
            "screening": copy.deepcopy(screening),
            "held_out_confirmation": copy.deepcopy(confirmation),
        })
        return row

    def _portfolio_objective(self, row):
        """Return the sole portfolio selection objective: held-out fidelity LCB."""
        fidelity_lcb = float(row.get("fidelity_lcb_95", np.nan))
        if not np.isfinite(fidelity_lcb):
            fidelity = float(row.get("fidelity", np.nan))
            fidelity_se = float(row.get("fidelity_se", np.nan))
            if not np.isfinite(fidelity):
                return -np.inf
            fidelity_lcb = fidelity - (1.96 * fidelity_se
                                       if np.isfinite(fidelity_se) else 0.0)
        return float(fidelity_lcb)

    def _annotate_portfolio_objective(self, row):
        """Attach leakage reporting fields without changing fidelity ranking."""
        row = dict(row)
        risks = []
        blob = float(row.get("third_blob_excess_ucb", np.nan))
        if np.isfinite(blob):
            risks.append(max(blob, 0.0))
        if bool(row.get("third_cluster_supported", False)):
            for key in ("third_cluster_fraction_ucb_95",
                        "third_cluster_single_state_fraction_ucb_95"):
                value = float(row.get(key, np.nan))
                if np.isfinite(value):
                    risks.append(max(value, 0.0))
        if self._leakage_active:
            direct = float(row.get("single_p2_ucb", np.nan))
            if np.isfinite(direct):
                risks.append(max(direct, 0.0))
        row["portfolio_leakage_risk_ucb"] = (
            float(max(risks)) if risks else np.nan)
        row["portfolio_selection_fidelity_lcb"] = self._portfolio_objective(row)
        return row

    def _portfolio_rank(self, row):
        """Deterministic fidelity-only rank; leakage never affects selection."""
        return tuple(self._joint_rank(row))

    def _portfolio_fidelity_shortlist(self, refined, source_rows, length, limit):
        """Choose expensive replays by fidelity while protecting prior winners.

        The first member is the best tuple from the fresh equal-budget refinement.
        The strongest historical same-duration tuple(s) are mandatory even when a
        noisy low-shot refinement temporarily ranks them lower.  Remaining slots are
        filled by fresh fidelity rank.  Leakage fields are deliberately never read.
        """
        refined = sorted(
            list(refined), key=self._authoritative_rank, reverse=True)
        historical = sorted((
            row for row in source_rows
            if isinstance(row, dict)
            and np.isclose(float(row.get("read_length", np.nan)), float(length),
                           rtol=0.0, atol=1e-9)
        ), key=self._authoritative_rank, reverse=True)
        historical_count = max(int(self.params["duration_portfolio"].get(
            "historical_champions_per_length", 1)), 0)
        chosen = []

        def add(row):
            if not isinstance(row, dict) or not all(
                    key in row for key in self.initial):
                return
            candidate = {key: row[key] for key in self.initial}
            if not any(_candidate_key(candidate) == _candidate_key(existing)
                       for existing in chosen):
                chosen.append(candidate)

        if refined:
            add(refined[0])
        for row in historical[:historical_count]:
            add(row)
        # Retain independently measured champions from several pulse-duration
        # families.  Without this protected diversity the exact replay can contain
        # five gain variants of one short/high-power pulse and never test the longer
        # constant-area alternative that the local stage was created to evaluate.
        family_count = max(int(self.params["duration_portfolio"].get(
            "pulse_family_champions_per_length", 1)), 1)
        family_best = {}
        for row in refined:
            sigma = round(float(row["sigma"]), 9)
            if sigma not in family_best:
                family_best[sigma] = row
        family_champions = sorted(
            family_best.values(), key=self._authoritative_rank, reverse=True)
        for row in family_champions[:family_count]:
            add(row)
        target = max(int(limit), len(chosen), 1)
        for row in refined:
            add(row)
            if len(chosen) >= target:
                break
        return chosen[:target]

    def _portfolio_control_audit(self, candidate, length):
        """Run and retain an odd/even coherence audit without selecting a config."""
        previous_key = self._final_control_verified_key
        previous_map = copy.deepcopy(self._maps.get("final_control_verify"))
        try:
            audit = self._stage_final_control_verify(candidate)
            return copy.deepcopy(audit), None
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            audit = copy.deepcopy(self._maps.get("final_control_verify"))
            return audit, "%s: %s" % (type(exc).__name__, exc)
        finally:
            self._final_control_verified_key = previous_key
            if previous_map is None:
                self._maps.pop("final_control_verify", None)
            else:
                self._maps["final_control_verify"] = previous_map

    def _stage_duration_portfolio(self):
        """Return the held-out fidelity winner at every requested readout duration.

        A deterministic gain/pulse-area challenge follows the broad search.  Exact
        finalists from *all* readout lengths are then replayed in one randomized
        round-robin cohort, so a 1-us row and a 20-us row do not own different drift
        windows.  Leakage and odd/even control never replace the pure-fidelity winner;
        they may only produce a separately labelled noninferior recommendation.
        """
        if not self._duration_portfolio_active:
            return None
        p = self.params["duration_portfolio"]
        lengths = sorted(set(
            float(value) for value in p.get("read_lengths_us", [])
            if np.isfinite(float(value)) and float(value) > 0.0))
        if not lengths:
            raise ValueError("duration portfolio needs positive read lengths")
        source_rows = self._portfolio_source_rows()
        entries, all_failures, control_audits = [], [], []
        plans = {}
        expected_refine_candidates = None

        # Phase 1: discover and locally converge each duration.  Every local cohort
        # contains its center as a repeated reference and is randomized by
        # _confirm_candidates, preventing a monotonic gain scan from becoming a time
        # scan.  The high-stat final comparison is interleaved across durations below.
        for length in lengths:
            entry = {
                "read_length_us": float(length), "status": "INCONCLUSIVE",
                "leakage_status": "INCONCLUSIVE", "control_status": "NOT_RUN",
                "balanced_status": "NOT_RUN", "selected": None,
                "balanced": None, "search": {}, "screened_candidates": [],
                "failures": [],
            }
            try:
                candidates, search = self._portfolio_candidates_for_length(
                    length, source_rows)
                entry["search"] = search
                if expected_refine_candidates is None and candidates:
                    expected_refine_candidates = len(candidates)
                if not candidates:
                    raise RuntimeError(search.get(
                        "failure", "no candidate seeds were available"))
                for candidate in candidates:
                    self._ensure_reset_profile(
                        candidate, "portfolio %.0f us refinement" % length)
                refined = self._confirm_candidates(
                    candidates, int(p["refine_shots"]),
                    int(p["refine_blocks"]),
                    "portfolio %.0f us equal-budget refinement" % length,
                    add_to_history=True)
                entry["search"].update({
                    "candidate_count": len(candidates),
                    "refined_candidate_count": len(refined),
                    "refinement_complete": bool(
                        len(refined) == len(candidates)
                        and all(row.get("confirmation_complete", False)
                                for row in refined)),
                })
                ranked = sorted(refined, key=self._joint_rank, reverse=True)
                if not ranked:
                    raise RuntimeError("fixed-duration refinement returned no rows")

                local_rows = []
                zoom_rows = []
                if bool(p.get("deterministic_gain_refinement", True)):
                    gain_candidates, gain_record = \
                        self._portfolio_deterministic_gain_candidates(
                            ranked, length)
                    entry["search"]["deterministic_gain_refinement"] = gain_record
                    for candidate in gain_candidates:
                        self._ensure_reset_profile(
                            candidate,
                            "portfolio %.0f us deterministic gain refinement"
                            % length)
                    if gain_candidates:
                        try:
                            local_rows = self._confirm_candidates(
                                gain_candidates, int(p["gain_refine_shots"]),
                                int(p["gain_refine_blocks"]),
                                "portfolio %.0f us deterministic gain and "
                                "constant-area refinement" % length,
                                add_to_history=True)
                        except KeyboardInterrupt:
                            raise
                        except Exception as exc:
                            failure = {
                                "phase": "deterministic_gain_refinement",
                                "error": "%s: %s" % (type(exc).__name__, exc),
                            }
                            entry["failures"].append(failure)
                            all_failures.append(dict(
                                failure, read_length_us=length))
                    first_pool = ranked + local_rows
                    if first_pool:
                        zoom_center = max(
                            first_pool, key=self._portfolio_rank)
                        zoom_records = []
                        locally_converged = False
                        for zoom_round in range(max(int(p.get(
                                "gain_zoom_max_rounds", 3)), 1)):
                            zoom_candidates, zoom_record = \
                                self._portfolio_gain_zoom_candidates(
                                    zoom_center, length)
                            for candidate in zoom_candidates:
                                self._ensure_reset_profile(
                                    candidate,
                                    "portfolio %.0f us deterministic gain zoom"
                                    % length)
                            round_rows = []
                            if zoom_candidates:
                                try:
                                    round_rows = self._confirm_candidates(
                                        zoom_candidates,
                                        int(p["gain_zoom_shots"]),
                                        int(p["gain_zoom_blocks"]),
                                        "portfolio %.0f us deterministic 2-D gain "
                                        "zoom round %d" % (
                                            length, zoom_round + 1),
                                        add_to_history=True)
                                except KeyboardInterrupt:
                                    raise
                                except Exception as exc:
                                    failure = {
                                        "phase": "deterministic_gain_zoom",
                                        "round": int(zoom_round + 1),
                                        "error": "%s: %s" % (
                                            type(exc).__name__, exc),
                                    }
                                    entry["failures"].append(failure)
                                    all_failures.append(dict(
                                        failure, read_length_us=length))
                                    zoom_record.update({
                                        "round": int(zoom_round + 1),
                                        "complete": False,
                                        "failure": failure["error"],
                                    })
                                    zoom_records.append(zoom_record)
                                    break
                            zoom_rows.extend(round_rows)
                            if not round_rows:
                                zoom_record.update({
                                    "round": int(zoom_round + 1),
                                    "complete": False,
                                })
                                zoom_records.append(zoom_record)
                                break
                            winner = max(round_rows, key=self._portfolio_rank)
                            read_axis = np.asarray(
                                zoom_record["read_gain_axis_dac"], dtype=int)
                            qubit_axis = np.asarray(
                                zoom_record["qubit_gain_axis_dac"], dtype=int)
                            read_edge = bool(
                                read_axis.size > 1
                                and int(winner["read_pulse_gain"]) in (
                                    int(read_axis[0]), int(read_axis[-1])))
                            qubit_edge = bool(
                                qubit_axis.size > 1
                                and int(winner["qubit_pi_gain"]) in (
                                    int(qubit_axis[0]), int(qubit_axis[-1])))
                            locally_converged = bool(
                                not read_edge and not qubit_edge)
                            zoom_record.update({
                                "round": int(zoom_round + 1),
                                "complete": True,
                                "winner_candidate_key": list(
                                    _candidate_key(winner)),
                                "read_gain_edge": read_edge,
                                "qubit_gain_edge": qubit_edge,
                                "locally_converged": locally_converged,
                            })
                            zoom_records.append(zoom_record)
                            zoom_center = winner
                            if locally_converged:
                                break
                        entry["search"]["deterministic_gain_zoom"] = {
                            "rounds": zoom_records,
                            "locally_converged": locally_converged,
                            "round_count": len(zoom_records),
                            "final_center_candidate_key": list(
                                _candidate_key(zoom_center)),
                        }
                else:
                    entry["search"]["deterministic_gain_refinement"] = {
                        "enabled": False}

                refined_pool = sorted(
                    ranked + local_rows + zoom_rows,
                    key=self._authoritative_rank, reverse=True)
                entry["search"].update({
                    "gain_refined_candidate_count": len(local_rows),
                    "gain_zoom_candidate_count": len(zoom_rows),
                    "gain_reference_replayed": bool(local_rows or zoom_rows),
                })

                # Successive halving is based only on held-out fidelity.  Force the
                # strongest historical same-duration tuple into this expensive cohort
                # so a previously observed winner (for example the 19 us joint-search
                # incumbent) is always independently replayed rather than forgotten.
                exact_candidates = self._portfolio_fidelity_shortlist(
                    refined_pool, source_rows, length,
                    max(int(p.get("confirm_candidates_per_length", 5)), 1))
                for candidate in exact_candidates:
                    self._ensure_reset_profile(
                        candidate, "portfolio %.0f us fidelity replay" % length)
                plans[length] = {
                    "entry": entry,
                    "ranked_fallback": refined_pool or ranked,
                    "exact_candidates": exact_candidates,
                }
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                failure = {"phase": "duration", "error": "%s: %s" % (
                    type(exc).__name__, exc)}
                entry["failures"].append(failure)
                all_failures.append(dict(failure, read_length_us=length))
            entries.append(entry)

        # Phase 2: one common held-out cohort across all durations.  The block pairing
        # ids now have the same acquisition epoch for every row, allowing real paired
        # noninferiority tests and preventing the old sequential 99-minute table from
        # confusing temporal drift with readout-duration dependence.
        all_exact_candidates = _unique_candidates([
            candidate for plan in plans.values()
            for candidate in plan["exact_candidates"]])
        all_exact_rows = []
        if all_exact_candidates:
            try:
                all_exact_rows = self._confirm_candidates_with_multimodality(
                    all_exact_candidates, int(p["confirm_shots"]),
                    int(p["confirm_blocks"]),
                    "portfolio duration-interleaved exact fidelity replay",
                    add_to_history=True)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                failure = {
                    "phase": "duration_interleaved_fidelity_confirmation",
                    "error": "%s: %s" % (type(exc).__name__, exc),
                }
                all_failures.append(failure)
                for plan in plans.values():
                    plan["entry"]["failures"].append(copy.deepcopy(failure))

        # Phase 3: independently report fidelity and the optional balanced pulse.
        # Screening several exact finalists is intentional: leakage cannot influence
        # the pure winner, but it must be measured before recommending a longer pulse.
        for length in lengths:
            plan = plans.get(length)
            if plan is None:
                continue
            entry = plan["entry"]
            try:
                exact_candidates = plan["exact_candidates"]
                exact_keys = {_candidate_key(row) for row in exact_candidates}
                exact_rows = [
                    row for row in all_exact_rows
                    if _candidate_key(row) in exact_keys]
                complete_exact = [
                    row for row in exact_rows
                    if row.get("confirmation_complete", False)]
                fallback = plan["ranked_fallback"]
                fidelity_pool = complete_exact or exact_rows or fallback
                selected = copy.deepcopy(max(
                    fidelity_pool, key=self._portfolio_rank))
                selected["portfolio_fidelity_selection_basis"] = (
                    "complete_duration_interleaved_exact_replay"
                    if complete_exact else
                    "partial_duration_interleaved_exact_replay"
                    if exact_rows else "gain_refinement_fallback")

                local_history = sorted((
                    row for row in source_rows
                    if np.isclose(float(row.get("read_length", np.nan)), length,
                                  rtol=0.0, atol=1e-9)
                ), key=self._joint_rank, reverse=True)
                historical_best = local_history[0] if local_history else None
                historical_key = (_candidate_key(historical_best)
                                  if historical_best is not None else None)
                replayed_keys = {_candidate_key(row) for row in exact_candidates}
                entry["search"].update({
                    "exact_fidelity_candidate_count": len(exact_candidates),
                    "exact_fidelity_row_count": len(exact_rows),
                    "exact_fidelity_confirmation_complete": bool(
                        complete_exact
                        and len(complete_exact) == len(exact_candidates)),
                    "duration_interleaved_exact_replay": True,
                    "historical_best_candidate_key": (
                        list(historical_key) if historical_key is not None else None),
                    "historical_best_fidelity": (
                        float(historical_best.get("fidelity", np.nan))
                        if historical_best is not None else np.nan),
                    "historical_best_replayed": bool(
                        historical_key is not None
                        and historical_key in replayed_keys),
                    "selected_candidate_key": list(_candidate_key(selected)),
                })

                screen_source = complete_exact or exact_rows or [selected]
                screen_targets = self._portfolio_screening_shortlist(
                    screen_source, selected)
                screened_rows, raw_screenings = [], []
                for rank, target in enumerate(screen_targets, start=1):
                    row = copy.deepcopy(target)
                    leakage_status = "INCONCLUSIVE"
                    try:
                        screening = self._portfolio_screen_candidate(
                            target, length, rank)
                        raw_screenings.append(copy.deepcopy(screening))
                        row = self._portfolio_merge_evidence(screening, target)
                        leakage_status = self._portfolio_confirmation_status(
                            screening, target)
                        row["portfolio_safety_kind"] = screening.get(
                            "portfolio_safety_kind")
                    except KeyboardInterrupt:
                        raise
                    except Exception as exc:
                        failure = {
                            "phase": "leakage_measurement",
                            "candidate_key": list(_candidate_key(target)),
                            "error": "%s: %s" % (type(exc).__name__, exc),
                        }
                        entry["failures"].append(failure)
                        all_failures.append(dict(
                            failure, read_length_us=length))
                        row.update({
                            "portfolio_safety_kind": "unavailable",
                            "third_blob_excess_ucb": np.nan,
                            "third_cluster_fraction": np.nan,
                            "third_cluster_fraction_ucb_95": np.nan,
                            "third_cluster_single_state_fraction": np.nan,
                            "third_cluster_single_state_fraction_ucb_95": np.nan,
                            "single_p2_ucb": np.nan,
                            "amplified_p2_ucb": np.nan,
                        })
                    row["portfolio_safety_status"] = leakage_status
                    row["portfolio_safe"] = bool(leakage_status == "SAFE")
                    screened_rows.append(
                        self._annotate_portfolio_objective(row))
                entry["screened_candidates"] = raw_screenings
                selected = next((
                    row for row in screened_rows
                    if _candidate_key(row) == _candidate_key(selected)),
                    self._annotate_portfolio_objective(selected))
                leakage_status = str(selected.get(
                    "portfolio_safety_status", "INCONCLUSIVE"))

                require_control = bool(p.get("require_control_audit", True))
                audit_cache = {}

                def audit_candidate(candidate):
                    key = _candidate_key(candidate)
                    if key in audit_cache:
                        return audit_cache[key]
                    if require_control:
                        audit, error = self._portfolio_control_audit(
                            candidate, length)
                    else:
                        audit, error = None, None
                    record = {
                        "read_length_us": length,
                        "candidate_key": list(key),
                        "verified": bool(not require_control or error is None),
                        "error": error, "audit": audit,
                    }
                    audit_cache[key] = record
                    control_audits.append(copy.deepcopy(record))
                    return record

                selected_audit = audit_candidate(selected)
                selected["control_verified"] = bool(
                    selected_audit["verified"] if require_control else False)
                selected["control_audit"] = selected_audit["audit"]
                selected["control_failure"] = selected_audit["error"]
                control_status = (
                    "NOT_REQUIRED" if not require_control else
                    "VERIFIED" if selected_audit["verified"] else "FAILED")

                balanced_enabled = bool(p.get("balanced_row_enabled", False))
                balanced_order = (
                    self._portfolio_balanced_order(screened_rows, selected)
                    if balanced_enabled else [])
                balanced = None
                balanced_record = None
                attempts = max(int(p.get(
                    "balanced_control_attempts", 2)), 1)
                for candidate in balanced_order[:attempts]:
                    record = audit_candidate(candidate)
                    if balanced is None:
                        balanced = copy.deepcopy(candidate)
                        balanced_record = record
                    if not require_control or record["verified"]:
                        balanced = copy.deepcopy(candidate)
                        balanced_record = record
                        break
                if balanced is None and balanced_enabled:
                    balanced = copy.deepcopy(selected)
                    balanced_record = selected_audit
                    balanced["balanced_noninferiority"] = \
                        self._portfolio_balance_diagnostic(selected, selected)
                if balanced is None:
                    entry.update({
                        "status": ("UNSAFE" if leakage_status == "UNSAFE" else
                                   "SAFE" if (leakage_status == "SAFE"
                                              and control_status in (
                                                  "VERIFIED", "NOT_REQUIRED"))
                                   else "INCONCLUSIVE"),
                        "leakage_status": leakage_status,
                        "control_status": control_status,
                        "selected": copy.deepcopy(selected),
                        "balanced_status": "NOT_RUN", "balanced": None,
                        "evaluated_exact_candidates": copy.deepcopy(screened_rows),
                    })
                    continue
                balanced["control_verified"] = bool(
                    balanced_record["verified"] if require_control else False)
                balanced["control_audit"] = balanced_record["audit"]
                balanced["control_failure"] = balanced_record["error"]
                balanced["balanced_is_fidelity_winner"] = bool(
                    _candidate_key(balanced) == _candidate_key(selected))
                balanced_control_status = (
                    "NOT_REQUIRED" if not require_control else
                    "VERIFIED" if balanced_record["verified"] else "FAILED")
                balanced_leakage_status = str(balanced.get(
                    "portfolio_safety_status", "INCONCLUSIVE"))
                balanced_status = (
                    "UNSAFE" if balanced_leakage_status == "UNSAFE" else
                    "SAFE" if (
                        balanced_leakage_status == "SAFE"
                        and balanced_control_status in (
                            "VERIFIED", "NOT_REQUIRED")) else "INCONCLUSIVE")

                overall_status = (
                    "UNSAFE" if leakage_status == "UNSAFE" else
                    "SAFE" if (leakage_status == "SAFE"
                               and control_status in (
                                   "VERIFIED", "NOT_REQUIRED"))
                    else "INCONCLUSIVE")
                entry.update({
                    "status": overall_status,
                    "leakage_status": leakage_status,
                    "control_status": control_status,
                    "selected": copy.deepcopy(selected),
                    "balanced_status": balanced_status,
                    "balanced_leakage_status": balanced_leakage_status,
                    "balanced_control_status": balanced_control_status,
                    "balanced": copy.deepcopy(balanced),
                    "evaluated_exact_candidates": copy.deepcopy(screened_rows),
                })
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                failure = {"phase": "duration_reporting", "error": "%s: %s" % (
                    type(exc).__name__, exc)}
                entry["failures"].append(failure)
                all_failures.append(dict(failure, read_length_us=length))

        safe_entries = [entry for entry in entries
                        if entry.get("status") == "SAFE"
                        and isinstance(entry.get("selected"), dict)]
        reportable_entries = [entry for entry in entries
                              if isinstance(entry.get("selected"), dict)]
        balanced_entries = [entry for entry in entries
                            if isinstance(entry.get("balanced"), dict)]
        best_safe_entry = (max(
            safe_entries,
            key=lambda entry: self._portfolio_rank(entry["selected"]))
            if safe_entries else None)
        best_entry = (max(
            reportable_entries,
            key=lambda entry: self._portfolio_rank(entry["selected"]))
            if reportable_entries else None)
        requested = len(lengths)
        complete_lengths = sum(isinstance(entry.get("selected"), dict)
                               for entry in entries)
        equal_budget = bool(
            expected_refine_candidates is not None
            and all((not entry.get("search", {}).get("candidate_count"))
                    or int(entry["search"]["candidate_count"])
                    == int(expected_refine_candidates)
                    for entry in entries))
        portfolio = {
            "enabled": True, "manual_selection_only": True,
            "automatic_write_allowed": False,
            "readout_length_mode": p.get("readout_length_mode", "custom"),
            "configured_initialize_read_length_us": p.get(
                "configured_initialize_read_length_us"),
            "selection_objective": "held_out_fidelity_lcb_95_only",
            "leakage_affects_selection": False,
            "control_audit_affects_selection": False,
            "balanced_selection_objective": (
                "among paired-noninferior exact replays, prefer verified/safe lower-"
                "leakage longer lower-drive pulses; never replace fidelity winner"),
            "balanced_max_fidelity_loss": float(p.get(
                "balanced_max_fidelity_loss", 0.010)),
            "duration_interleaved_exact_replay": True,
            "read_lengths_us": lengths, "entries": entries,
            "requested_length_count": requested,
            "reportable_length_count": complete_lengths,
            "balanced_reportable_length_count": len(balanced_entries),
            "safe_length_count": len(safe_entries),
            "unsafe_length_count": sum(
                entry.get("status") == "UNSAFE" for entry in entries),
            "inconclusive_length_count": sum(
                entry.get("status") == "INCONCLUSIVE" for entry in entries),
            "equal_refinement_budget": equal_budget,
            "expected_refine_candidates_per_length": expected_refine_candidates,
            "control_audits": control_audits,
            "failures": all_failures,
            "best_safe_entry": copy.deepcopy(best_safe_entry),
            "status": ("complete" if complete_lengths == requested
                       else "partial"),
        }
        self.data["duration_portfolio"] = portfolio
        self._maps["duration_portfolio"] = {
            "read_length_us": np.asarray(lengths, dtype=float),
            "fidelity": np.asarray([
                float((entry.get("selected") or {}).get("fidelity", np.nan))
                for entry in entries]),
            "fidelity_se": np.asarray([
                float((entry.get("selected") or {}).get("fidelity_se", np.nan))
                for entry in entries]),
            "balanced_fidelity": np.asarray([
                float((entry.get("balanced") or {}).get("fidelity", np.nan))
                for entry in entries]),
            "balanced_sigma_us": np.asarray([
                float((entry.get("balanced") or {}).get("sigma", np.nan))
                for entry in entries]),
            "balanced_qubit_gain_dac": np.asarray([
                float((entry.get("balanced") or {}).get(
                    "qubit_pi_gain", np.nan)) for entry in entries]),
            "third_population_ucb_95": np.asarray([
                float((entry.get("selected") or {}).get(
                    "third_cluster_fraction_ucb_95", np.nan))
                for entry in entries]),
            "single_p2_ucb": np.asarray([
                float((entry.get("selected") or {}).get("single_p2_ucb", np.nan))
                for entry in entries]),
            "status_code": np.asarray([
                {"SAFE": 1, "UNSAFE": -1}.get(entry.get("status"), 0)
                for entry in entries], dtype=int),
            "search_complete": bool(complete_lengths == requested),
            "selection_confirmed": bool(
                complete_lengths == requested
                and all((entry.get("selected") or {}).get(
                    "portfolio_fidelity_selection_basis")
                        == "complete_duration_interleaved_exact_replay"
                        for entry in entries)),
            "equal_refinement_budget": equal_budget,
        }
        self.data["leakage"].update({
            "portfolio_screened": True,
            "portfolio_safe_length_count": len(safe_entries),
            # There is intentionally no single selected write tuple in this mode.
            "verified": False, "required_for_write": False,
            "final_replay_complete": False,
        })
        self._final_control_verified_key = None
        self._leakage_verified_candidate_key = None
        if best_entry is None:
            raise RuntimeError(
                "the duration portfolio completed no reportable parameter set")
        best = copy.deepcopy(best_entry["selected"])
        self.working = {key: best[key] for key in self.initial}
        return best

    # ----------------------------------------------- practical operational leakage screen
    def _measure_candidate_with_multimodality(self, candidate, shots, label,
                                               **kwargs):
        previous = bool(self._analyze_multimodality)
        self._analyze_multimodality = True
        try:
            return self._measure_candidate(candidate, shots, label, **kwargs)
        finally:
            self._analyze_multimodality = previous

    def _confirm_candidates_with_multimodality(self, candidates, shots, blocks,
                                                label, **kwargs):
        previous = bool(self._analyze_multimodality)
        self._analyze_multimodality = True
        try:
            return self._confirm_candidates(
                candidates, shots, blocks, label, **kwargs)
        finally:
            self._analyze_multimodality = previous

    def _acquire_repeated_populations(self, candidate, pulse_counts, shots,
                                      calibration):
        """Measure exact-candidate odd/even repeated-pulse populations."""
        counts = [int(value) for value in pulse_counts]
        populations = np.full(len(counts), np.nan, dtype=float)
        for raw in self.rng.permutation(len(counts)):
            index = int(raw)
            cfg = self._cfg_for(
                candidate, drive_freq=float(candidate["qubit_pi_freq"]),
                sequence_gain=int(candidate["qubit_pi_gain"]),
                sequence_phases_deg=[0.0] * counts[index],
                shots=int(shots), reps=int(shots),
            )
            program = BasicSequenceProgram(self.soccfg, cfg)
            program.acquire(self.soc, load_pulses=True, progress=False)
            shot_i, shot_q = _shots_from_program(program, cfg)
            self._record_raw_diagnostic(
                "repeated_control", candidate,
                {"shot_i": shot_i, "shot_q": shot_q},
                {"pulse_count": int(counts[index]), "shots": int(shots)})
            populations[index] = float(np.mean(
                discriminate_with_metrics(shot_i, shot_q, calibration)))
        return populations

    def _stage_final_control_verify(self, final,
                                    minimum_binary_contrast=None,
                                    shot_multiplier=1):
        """Certify coherent odd/even action of the exact selected X180 tuple.

        The step-5 objective establishes readout assignment and state-preparation
        separation, but an incoherently saturated drive can pass that test.  This
        final audit repeats the *unchanged* frequency/gain/sigma/DRAG waveform at
        several depths.  Only an exact-tuple witness emitted here (or an earlier
        exact-tuple parity witness) may authorize an automatic configuration write.
        """
        p = self.params["control_verify"]
        contrast_floor = float(
            p["minimum_binary_contrast"] if minimum_binary_contrast is None
            else minimum_binary_contrast)
        self._final_control_verified_key = None
        if not p.get("enabled", True):
            raise RuntimeError(
                "exact selected-pulse coherent verification is disabled")
        if not isinstance(final, dict):
            raise RuntimeError("there is no final candidate to verify coherently")
        candidate = {key: final[key] for key in self.initial}
        counts = np.asarray(sorted(set(
            int(value) for value in p.get("pulse_counts", [])
            if int(value) > 0)), dtype=int)
        if (counts.size < 4 or not np.any(counts % 2 == 0)
                or not np.any(counts % 2 == 1)):
            raise ValueError(
                "final control verification requires at least four positive odd/even "
                "pulse depths")
        multiplier = max(int(shot_multiplier), 1)
        shots = max(int(p["shots"]) * multiplier, 1)
        reference_shots = max(int(p["calibration_shots"]) * multiplier, 1)
        blocks = max(int(p["blocks"]), 1)
        familywise_z = _simultaneous_z(
            int(counts.size * blocks), p.get("familywise_alpha", 0.05),
            p.get("confidence_sigma", 1.96))
        block_rows = []
        for block in range(blocks):
            before = self._measure_candidate(
                candidate, reference_shots,
                "final control discriminator %d" % (block + 1),
                archive=False)
            calibration = {key: before[key] for key in
                           ("read_theta", "scale_factor", "threshold")}
            populations = np.asarray(self._acquire_repeated_populations(
                candidate, counts, shots, calibration), dtype=float)
            after = self._measure_candidate(
                candidate, reference_shots,
                "final control discriminator post %d" % (block + 1),
                archive=False, reference_discriminator=calibration)
            drift = self._calibration_drift(before, after)
            drift_stable = self._calibration_is_stable(drift)
            p_e_ground = float(before["p_e_given_g"])
            p_e_excited = float(1.0 - before["p_g_given_e"])
            contrast = float(p_e_excited - p_e_ground)
            contrast_valid = bool(
                np.isfinite(contrast)
                and contrast >= contrast_floor)
            if contrast_valid and populations.shape == counts.shape:
                normalized = (populations - p_e_ground) / contrast
                sequence_variance = np.asarray([
                    _binomial_variance_jeffreys(
                        int(np.clip(round(value * shots), 0, shots)), shots)
                    for value in populations
                ], dtype=float)
                ground_variance = _binomial_variance_jeffreys(
                    int(np.clip(round(p_e_ground * reference_shots),
                                0, reference_shots)), reference_shots)
                excited_variance = _binomial_variance_jeffreys(
                    int(np.clip(round(p_e_excited * reference_shots),
                                0, reference_shots)), reference_shots)
                gradient_ground = (normalized - 1.0) / contrast
                gradient_excited = -normalized / contrast
                normalized_se = np.sqrt(np.maximum(
                    sequence_variance / contrast ** 2
                    + gradient_ground ** 2 * ground_variance
                    + gradient_excited ** 2 * excited_variance,
                    0.0))
            else:
                normalized = np.full(counts.shape, np.nan, dtype=float)
                normalized_se = np.full(counts.shape, np.inf, dtype=float)
            targets = (counts % 2).astype(float)
            errors = np.abs(normalized - targets)
            error_ucb = errors + familywise_z * normalized_se
            even = counts % 2 == 0
            odd = ~even
            worst_even = (float(np.max(error_ucb[even]))
                          if np.all(np.isfinite(error_ucb[even])) else np.inf)
            worst_odd = (float(np.max(error_ucb[odd]))
                         if np.all(np.isfinite(error_ucb[odd])) else np.inf)
            valid = bool(
                drift_stable and contrast_valid
                and populations.shape == counts.shape
                and np.all(np.isfinite(populations))
                and np.all(np.isfinite(error_ucb)))
            passed = bool(
                valid
                and worst_even <= float(p["max_even_return_error_ucb"])
                and worst_odd <= float(p["max_odd_inversion_error_ucb"]))
            block_rows.append({
                "block": int(block), "populations": populations,
                "normalized_populations": normalized,
                "normalized_population_se": normalized_se,
                "target_populations": targets,
                "error_ucb": error_ucb,
                "worst_even_return_error_ucb": worst_even,
                "worst_odd_inversion_error_ucb": worst_odd,
                "binary_contrast": contrast,
                "calibration_drift": drift,
                "calibration_stable": bool(drift_stable),
                "valid": bool(valid), "passed": bool(passed),
            })
        verified = bool(len(block_rows) == blocks
                        and all(row["passed"] for row in block_rows))
        worst_even = float(max(
            row["worst_even_return_error_ucb"] for row in block_rows))
        worst_odd = float(max(
            row["worst_odd_inversion_error_ucb"] for row in block_rows))
        self._maps["final_control_verify"] = {
            "pulse_counts": counts,
            "candidate": dict(candidate),
            "control_key": _control_key(candidate),
            "blocks": block_rows,
            "familywise_z": float(familywise_z),
            "verified": bool(verified),
            "search_complete": bool(verified),
            "selection_confirmed": bool(verified),
        }
        if not verified:
            raise RuntimeError(
                "the exact selected pulse failed odd/even coherence "
                "(return/inversion UCB %.3f/%.3f; limits %.3f/%.3f)"
                % (worst_even, worst_odd,
                   float(p["max_even_return_error_ucb"]),
                   float(p["max_odd_inversion_error_ucb"])))
        self._record_control_witness(
            "final_control_verify", candidate["qubit_pi_freq"],
            "exact_odd_even_repeated_pulses", candidate=candidate,
            blocks=int(blocks), pulse_counts=counts.tolist(),
            worst_even_return_error_ucb=worst_even,
            worst_odd_inversion_error_ucb=worst_odd,
            familywise_z=float(familywise_z), exact_tuple=True)
        self._final_control_verified_key = _control_key(candidate)
        return self._maps["final_control_verify"]

    def _measure_operational_leakage_candidate(self, candidate, shots,
                                               reference_shots, label):
        """Screen one fixed Gaussian for a reproducible non-binary IQ cloud.

        The default basic screen brackets the candidate with two fresh TLS step-5
        measurements and uses the worse third-cloud upper bound.  Optional repeated
        returns remain available as a diagnostic, but are disabled by default: AAE is
        the correct coherent amplitude-error experiment, and a return error is not a
        direct leakage population measurement.
        """
        p = self.params["leakage"]
        candidate = dict(candidate)
        before = self._measure_candidate_with_multimodality(
            candidate, int(reference_shots), "%s discriminator" % label)
        calibration = {key: before[key] for key in
                       ("read_theta", "scale_factor", "threshold")}
        repeated_enabled = bool(p.get(
            "operational_repeated_return_enabled", False))
        depths = ([int(value) for value in p["operational_depths"]
                   if int(value) > 0] if repeated_enabled else [])
        if repeated_enabled and (
                not depths or not any(value % 2 == 0 for value in depths)
                or not any(value % 2 == 1 for value in depths)):
            raise RuntimeError(
                "operational repeated-return depths require positive odd and even "
                "counts")
        populations = (np.asarray(self._acquire_repeated_populations(
            candidate, depths, int(shots), calibration), dtype=float)
            if repeated_enabled else np.asarray([], dtype=float))
        after = self._measure_candidate_with_multimodality(
            candidate, int(reference_shots), "%s discriminator post" % label,
            reference_discriminator=calibration)
        drift = self._calibration_drift(before, after)
        drift_stable = self._calibration_is_stable(drift)

        p_e_ground = float(before["p_e_given_g"])
        p_e_excited = float(1.0 - before["p_g_given_e"])
        contrast = float(p_e_excited - p_e_ground)
        finite_contrast = bool(
            np.isfinite(contrast)
            and contrast >= float(p["operational_min_binary_contrast"]))
        if repeated_enabled and finite_contrast:
            normalized = (populations - p_e_ground) / contrast
            n = max(int(shots), 1)
            sequence_variance = np.asarray([
                _binomial_variance_jeffreys(
                    int(np.clip(round(value * n), 0, n)), n)
                for value in populations
            ], dtype=float)
            reference_n = max(int(before.get("shots_per_state", reference_shots)), 1)
            ground_variance = _binomial_variance_jeffreys(
                int(np.clip(round(p_e_ground * reference_n), 0, reference_n)),
                reference_n)
            excited_variance = _binomial_variance_jeffreys(
                int(np.clip(round(p_e_excited * reference_n), 0, reference_n)),
                reference_n)
            gradient_ground = (normalized - 1.0) / contrast
            gradient_excited = -normalized / contrast
            normalized_se = np.sqrt(np.maximum(
                sequence_variance / contrast ** 2
                + gradient_ground ** 2 * ground_variance
                + gradient_excited ** 2 * excited_variance,
                0.0))
        elif repeated_enabled:
            normalized = np.full(len(depths), np.nan)
            normalized_se = np.full(len(depths), np.inf)
        else:
            normalized = np.asarray([], dtype=float)
            normalized_se = np.asarray([], dtype=float)
        targets = np.asarray([value % 2 for value in depths], dtype=float)
        errors = np.abs(normalized - targets)
        z = (_simultaneous_z(
            len(depths), p.get("familywise_alpha", 0.05),
            p.get("confidence_sigma", 1.96)) if repeated_enabled else np.nan)
        error_ucb = (errors + z * normalized_se if repeated_enabled
                     else np.asarray([], dtype=float))
        even = np.asarray([value % 2 == 0 for value in depths], dtype=bool)
        odd = ~even
        even_values = error_ucb[even]
        odd_values = error_ucb[odd]
        worst_even = (float(np.max(even_values[np.isfinite(even_values)]))
                      if np.any(np.isfinite(even_values)) else np.nan)
        worst_odd = (float(np.max(odd_values[np.isfinite(odd_values)]))
                     if np.any(np.isfinite(odd_values)) else np.nan)
        third_before = float(before["third_blob_excess_ucb_95"])
        third_after = float(after["third_blob_excess_ucb_95"])
        third_blob = float(max(third_before, third_after))

        def cluster_guard(row):
            available = bool(row.get("third_cluster_guard_available", False))
            bic = float(row.get("third_cluster_bic_improvement", np.nan))
            separation = float(row.get(
                "third_cluster_min_separation_sigma", np.nan))
            supported = bool(
                available and bool(row.get("third_cluster_supported", False))
                and np.all(np.isfinite([bic, separation]))
                and bic >= float(p["third_cluster_min_bic_improvement"])
                and separation >= float(
                    p["third_cluster_min_separation_sigma"]))
            fraction = (float(row.get("third_cluster_fraction", np.nan))
                        if supported else 0.0)
            fraction_ucb = (float(row.get(
                "third_cluster_fraction_ucb_95", np.nan))
                if supported else 0.0)
            single_state = (float(row.get(
                "third_cluster_single_state_fraction", np.nan))
                            if supported else 0.0)
            single_state_ucb = (float(row.get(
                "third_cluster_single_state_fraction_ucb_95", np.nan))
                if supported else 0.0)
            valid_guard = bool(
                available and np.all(np.isfinite([
                    fraction, fraction_ucb, single_state,
                    single_state_ucb])))
            safe_guard = bool(
                valid_guard
                and fraction_ucb <= float(p["max_third_cluster_fraction"])
                and single_state_ucb <= float(
                    p["max_single_state_third_cluster_fraction"]))
            return {
                "available": available, "supported": supported,
                "valid": valid_guard, "safe": safe_guard,
                "fraction": fraction, "fraction_ucb_95": fraction_ucb,
                "single_state_fraction": single_state,
                "single_state_fraction_ucb_95": single_state_ucb,
                "bic_improvement": bic, "separation_sigma": separation,
            }

        cluster_before = cluster_guard(before)
        cluster_after = cluster_guard(after)
        cluster_valid = bool(cluster_before["valid"] and cluster_after["valid"])
        third_cluster_fraction = float(max(
            cluster_before["fraction"], cluster_after["fraction"]))
        third_cluster_fraction_ucb = float(max(
            cluster_before["fraction_ucb_95"],
            cluster_after["fraction_ucb_95"]))
        third_cluster_single_state = float(max(
            cluster_before["single_state_fraction"],
            cluster_after["single_state_fraction"]))
        third_cluster_single_state_ucb = float(max(
            cluster_before["single_state_fraction_ucb_95"],
            cluster_after["single_state_fraction_ucb_95"]))
        cluster_safe = bool(cluster_before["safe"] and cluster_after["safe"])
        fids = np.asarray([before["fidelity"], after["fidelity"]], dtype=float)
        shot_ses = np.asarray(
            [before["fidelity_se"], after["fidelity_se"]], dtype=float)
        fidelity = float(np.mean(fids))
        fidelity_se = float(max(
            np.std(fids, ddof=1) / math.sqrt(2.0),
            np.sqrt(np.sum(shot_ses ** 2)) / 2.0))
        repeated_valid = bool(
            not repeated_enabled
            or (finite_contrast and np.all(np.isfinite(populations))
                and np.all(np.isfinite(error_ucb))))
        repeated_safe = bool(
            not repeated_enabled
            or (worst_even <= float(p["operational_max_even_return_error"])
                and worst_odd <= float(p["operational_max_odd_inversion_error"])))
        valid = bool(
            np.isfinite(fidelity) and np.isfinite(fidelity_se)
            and drift_stable and repeated_valid
            and np.isfinite(third_blob) and cluster_valid)
        safe = bool(
            valid and repeated_safe and cluster_safe
            and third_blob <= float(p["max_third_blob_excess"]))
        failure = None
        if not valid:
            if not drift_stable:
                failure = "the bracketing discriminator drifted"
            elif not repeated_valid:
                failure = "the optional repeated-return diagnostic was invalid"
            elif not cluster_valid:
                failure = "the three-cloud IQ safety model was unavailable or invalid"
            else:
                failure = "the bracketing single-shot audit was invalid"
        elif not repeated_safe:
            failure = "the optional repeated-return diagnostic exceeded its limit"
        elif not cluster_safe:
            failure = (
                "resolved third IQ population 95%% UCB %.1f%% overall / %.1f%% "
                "in one preparation exceeded %.1f%% / %.1f%%"
                % (100.0 * third_cluster_fraction_ucb,
                   100.0 * third_cluster_single_state_ucb,
                   100.0 * float(p["max_third_cluster_fraction"]),
                   100.0 * float(
                       p["max_single_state_third_cluster_fraction"])))
        elif third_blob > float(p["max_third_blob_excess"]):
            failure = ("third-cloud excess UCB %.4f exceeded %.4f"
                       % (third_blob, float(p["max_third_blob_excess"])))
        row = dict(candidate)
        row.update({
            "fidelity": fidelity,
            "fidelity_se": fidelity_se,
            "fidelity_lcb_95": float(fidelity - 1.96 * fidelity_se),
            "third_blob_excess_ucb": third_blob,
            "third_blob_excess_ucb_before": third_before,
            "third_blob_excess_ucb_after": third_after,
            "third_cluster_guard_available": cluster_valid,
            "third_cluster_supported": bool(
                cluster_before["supported"] or cluster_after["supported"]),
            "third_cluster_detected": bool(not cluster_safe),
            "third_cluster_fraction": third_cluster_fraction,
            "third_cluster_fraction_ucb_95": third_cluster_fraction_ucb,
            "third_cluster_single_state_fraction": third_cluster_single_state,
            "third_cluster_single_state_fraction_ucb_95": (
                third_cluster_single_state_ucb),
            "third_cluster_before": cluster_before,
            "third_cluster_after": cluster_after,
            "depths": np.asarray(depths, dtype=int),
            "observed_excited_fraction": populations,
            "normalized_excited_population": normalized,
            "normalized_population_se": normalized_se,
            "target_population": targets,
            "depth_error": errors, "depth_error_ucb": error_ucb,
            "max_even_return_error_ucb": worst_even,
            "max_odd_inversion_error_ucb": worst_odd,
            "binary_contrast": contrast,
            "repeated_return_enabled": repeated_enabled,
            "calibration_drift": drift,
            "calibration_stable": drift_stable,
            "valid": valid, "operational_safe": safe,
            "leakage_safe": safe,
            "label": str(label),
            "failure": failure,
        })
        return row

    @staticmethod
    def _prefer_longer_noninferior(aggregates, margin=0.003,
                                   max_mean_loss=0.010):
        """Among statistically tied fidelities, prefer longer/lower-power control."""
        if not aggregates:
            return None
        best = BasicAutoTuner._best_aggregate(aggregates)
        tied = []
        for row in aggregates:
            uncertainty = 1.96 * math.hypot(
                float(best.get("fidelity_se", np.inf)),
                float(row.get("fidelity_se", np.inf)))
            loss = float(best["fidelity"]) - float(row["fidelity"])
            if (loss <= uncertainty + float(margin)
                    and loss <= float(max_mean_loss)):
                tied.append(row)
        return max(tied or [best], key=lambda row: (
            float(row.get("sigma", 0.0)),
            -abs(float(row.get("qubit_pi_gain", np.inf))),
            -float(row.get("max_even_return_error_ucb", np.inf)),
            -float(row.get("max_odd_inversion_error_ucb", np.inf)),
            -float(row.get("third_blob_excess_ucb", np.inf)),
            float(row.get("fidelity_lcb_95", -np.inf))))

    @staticmethod
    def _duration_covered_shortlist(rows, limit):
        """Keep the best safe row per duration before filling by fidelity."""
        ranked = sorted(rows, key=lambda row: (
            float(row.get("fidelity_lcb_95", -np.inf)),
            float(row.get("fidelity", -np.inf))), reverse=True)
        limit = max(int(limit), 1)
        by_duration = {}
        for row in ranked:
            by_duration.setdefault(round(float(row["sigma"]), 9), row)
        shortlist = list(by_duration.values())[:limit]
        for row in ranked:
            if len(shortlist) >= limit:
                break
            if not any(_candidate_key(existing) == _candidate_key(row)
                       for existing in shortlist):
                shortlist.append(row)
        return shortlist

    def _operational_waveform_pool(self):
        """One measured fixed-Gaussian control candidate per available duration."""
        limit = max(int(self.params["leakage"].get(
            "operational_max_candidate_waveforms", 6)), 1)
        fixed_beta = float(self.working.get("qubit_drag_beta", 0.0))

        def physical(row):
            candidate = dict(self.working)
            for key in ("qubit_freq", "qubit_pi_freq", "qubit_pi_gain", "sigma"):
                candidate[key] = row[key]
            # The basic screen compares duration and power; it never introduces a new
            # waveform family.  Strict direct-P(f) mode owns any explicit DRAG search.
            candidate["qubit_drag_beta"] = fixed_beta
            return candidate

        def control_key(candidate):
            return (
                round(float(candidate["qubit_pi_freq"]), 7),
                int(round(candidate["qubit_pi_gain"])),
                round(float(candidate["sigma"]), 9),
                round(float(candidate.get("qubit_drag_beta", 0.0)), 9),
            )

        rows = self._qualified_transition_rows(
            list(self.data.get("final_candidates", []))
            + list(self._confirmed) + list(self._archive))
        ranked = sorted(
            (row for row in rows if all(key in row for key in self.initial)),
            key=lambda row: (
                float(row.get("fidelity_lcb_95", -np.inf)),
                float(row.get("fidelity", -np.inf))), reverse=True)
        by_duration = {}
        for row in ranked:
            by_duration.setdefault(round(float(row["sigma"]), 9), row)

        pool = ([dict(self.working)]
                if self._candidate_in_qualified_transition(self.working) else [])
        if not pool:
            qualified = self._qualified_transition_rows(ranked)
            if not qualified:
                raise RuntimeError(
                    "no qualified-transition waveform is available for safety "
                    "screening")
            pool = [physical(qualified[0])]
        seen = {control_key(pool[0])}
        duration_rows = [by_duration[key] for key in sorted(by_duration)]
        slots = max(limit - 1, 0)
        if len(duration_rows) > slots > 0:
            # Span the full measured duration range.  The current winner is already
            # retained separately and confirmation rejects any noisy coarse seed.
            indices = np.unique(np.rint(np.linspace(
                0, len(duration_rows) - 1, slots)).astype(int))
            duration_rows = [duration_rows[int(index)] for index in indices]
        for row in duration_rows + ranked:
            if len(pool) >= limit:
                break
            candidate = physical(row)
            key = control_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            pool.append(candidate)
        return pool

    def _stage_operational_leakage(self):
        """Select fixed-waveform Gaussian duration/power inside the operational set."""
        if not self._operational_leakage_active:
            return None
        p = self.params["leakage"]
        attempts = []
        safe_rows = []
        tune_drag = bool(p.get("operational_tune_drag", False))
        for waveform_index, waveform in enumerate(self._operational_waveform_pool()):
            incumbent_beta = float(waveform.get("qubit_drag_beta", 0.0))
            rows = []
            failures = []
            measured = set()
            consecutive_failures = 0
            abort_waveform = False
            extensions = (max(int(p["operational_max_extensions"]), 1)
                          if tune_drag else 1)
            for extension in range(extensions):
                span = min(
                    float(p["operational_beta_span"]) * (1.7 ** extension),
                    float(p["operational_max_beta_span"]))
                betas = (np.unique(np.round(np.r_[
                    np.linspace(
                        incumbent_beta - span, incumbent_beta + span,
                        max(int(p["operational_beta_points"]), 5)),
                    0.0, incumbent_beta,
                ], 8)) if tune_drag else np.asarray([incumbent_beta], dtype=float))
                for raw in self.rng.permutation(betas.size):
                    beta = float(betas[int(raw)])
                    if beta in measured:
                        continue
                    measured.add(beta)
                    candidate = _with_candidate(
                        waveform, qubit_drag_beta=beta)
                    try:
                        drift_attempts = 1 + max(int(p.get(
                            "operational_drift_retries", 2)), 0)
                        row = None
                        for drift_attempt in range(drift_attempts):
                            row = self._measure_operational_leakage_candidate(
                                candidate, int(p["operational_shots"]),
                                int(p["operational_reference_shots"]),
                                "operational waveform %d beta %+.5f bracket %d"
                                % (waveform_index + 1, beta,
                                   drift_attempt + 1))
                            row["bracket_attempt"] = int(drift_attempt + 1)
                            row["bracket_attempts_allowed"] = int(drift_attempts)
                            rows.append(row)
                            if (row.get("valid", False)
                                    or row.get("failure")
                                    != "the bracketing discriminator drifted"):
                                break
                    except KeyboardInterrupt:
                        raise
                    except Exception as exc:
                        consecutive_failures += 1
                        failures.append({
                            "qubit_drag_beta": beta,
                            "error": "%s: %s" % (type(exc).__name__, exc),
                        })
                        self._log(
                            "operational_leakage", "WARN",
                            "waveform %d beta %+.5f failed (%s: %s)"
                            % (waveform_index + 1, beta,
                               type(exc).__name__, exc))
                        if consecutive_failures >= int(
                                self.params["max_consecutive_point_failures"]):
                            abort_waveform = True
                            break
                        continue
                    consecutive_failures = 0
                if abort_waveform:
                    break
                safe_now = [row for row in rows if row["operational_safe"]]
                if tune_drag and safe_now:
                    best_safe = max(safe_now, key=lambda row: (
                        float(row["fidelity_lcb_95"]),
                        -float(row["max_even_return_error_ucb"]),
                        -float(row["max_odd_inversion_error_ucb"])))
                    measured_betas = np.asarray([
                        row["qubit_drag_beta"] for row in rows], dtype=float)
                    if (float(best_safe["qubit_drag_beta"])
                            > float(np.min(measured_betas)) + 1e-9
                            and float(best_safe["qubit_drag_beta"])
                            < float(np.max(measured_betas)) - 1e-9):
                        break
            attempts.append({
                "candidate": dict(waveform), "rows": rows,
                "failures": failures, "aborted": bool(abort_waveform),
            })
            safe_rows.extend(row for row in rows if row["operational_safe"])
        if not safe_rows:
            completed = [row for attempt in attempts for row in attempt["rows"]]
            failures = [failure for attempt in attempts
                        for failure in attempt["failures"]]
            if completed:
                best_attempt = min(
                    completed,
                    key=lambda row: float(row.get(
                        "third_blob_excess_ucb", np.inf)))
                failure = (
                    "no fixed-Gaussian duration/power candidate passed: best "
                    "third-cloud excess UCB %.4f (limit %.4f)%s"
                    % (float(best_attempt.get(
                        "third_blob_excess_ucb", np.inf)),
                       float(p["max_third_blob_excess"]),
                       ("; %s" % best_attempt["failure"])
                       if best_attempt.get("failure") else ""))
            elif failures:
                failure = (
                    "the fixed-Gaussian duration/power screen completed no candidate; "
                    "first acquisition failure: %s" % failures[0]["error"])
                best_attempt = None
            else:
                failure = "the fixed-Gaussian duration/power pool was empty"
                best_attempt = None
            self.data["leakage"].update({
                "attempts": attempts, "optimized": False,
                "selection_safe": False, "verified": False,
                "best_screened_attempt": best_attempt,
                "best_third_blob_excess_ucb": (
                    float(best_attempt["third_blob_excess_ucb"])
                    if best_attempt is not None else np.inf),
                "failure": failure,
            })
            raise RuntimeError(failure)

        # Reserve duration coverage before filling by score.  This keeps the
        # longer/lower-power alternatives in the held-out comparison even when several
        # frequency/gain variants of one duration scored well earlier.
        shortlist = self._duration_covered_shortlist(
            safe_rows, p["operational_selection_shortlist"])
        confirmations = self._confirm_candidates_with_multimodality(
            shortlist, int(p["operational_selection_shots"]),
            int(p["operational_selection_blocks"]),
            "held-out operationally safe fidelity selection",
            add_to_history=True)
        screened_by_key = {_candidate_key(row): row for row in shortlist}
        for confirmation in confirmations:
            screened_row = screened_by_key.get(_candidate_key(confirmation), {})
            confirmation["screening_third_blob_excess_ucb"] = float(
                screened_row.get("third_blob_excess_ucb", np.inf))
            confirmation["screening_max_even_return_error_ucb"] = float(
                screened_row.get("max_even_return_error_ucb", np.nan))
            confirmation["screening_max_odd_inversion_error_ucb"] = float(
                screened_row.get("max_odd_inversion_error_ucb", np.nan))
            cluster_available = bool(confirmation.get(
                "third_cluster_guard_available", False))
            cluster_fraction_ucb = float(confirmation.get(
                "third_cluster_fraction_ucb_95", np.inf))
            cluster_single_state_ucb = float(confirmation.get(
                "third_cluster_single_state_fraction_ucb_95", np.inf))
            confirmation["operational_safe"] = bool(
                screened_row.get("operational_safe", False)
                and cluster_available
                and cluster_fraction_ucb <= float(
                    p["max_third_cluster_fraction"])
                and cluster_single_state_ucb <= float(
                    p["max_single_state_third_cluster_fraction"])
                and float(confirmation.get("third_blob_excess_ucb", np.inf))
                <= float(p["max_third_blob_excess"]))
        complete = self._confirmation_batch_complete(confirmations)
        safe_confirmations = [row for row in confirmations
                              if row.get("operational_safe", False)]
        if not safe_confirmations:
            best_confirmation = min(
                confirmations,
                key=lambda row: float(row.get(
                    "third_blob_excess_ucb", np.inf)))
            failure = (
                "held-out duration/power confirmation reproduced no safe candidate; "
                "best third-cloud excess UCB %.4f (limit %.4f)"
                % (float(best_confirmation.get(
                    "third_blob_excess_ucb", np.inf)),
                   float(p["max_third_blob_excess"])))
            self.data["leakage"].update({
                "attempts": attempts,
                "selection_confirmations": confirmations,
                "selection_confirmation_complete": bool(complete),
                "optimized": False, "selection_safe": False,
                "verified": False, "failure": failure,
            })
            raise RuntimeError(failure)
        # This stage establishes the highest-fidelity *safe* reference.  The later
        # joint latency replay then minimizes readout+control time across every safe
        # duration; choosing a timing compromise here would bias that reference.
        selected_confirmation = (
            self._best_aggregate(safe_confirmations)
            if self.params["latency"].get("enabled", True) else
            self._prefer_longer_noninferior(
                safe_confirmations, p["operational_fidelity_tie_margin"],
                p["operational_max_tie_fidelity_loss"]))
        if selected_confirmation is None:
            raise RuntimeError("operational safe shortlist produced no confirmation")
        screened = next(
            row for row in shortlist
            if _candidate_key(row) == _candidate_key(selected_confirmation))
        chosen = dict(screened)
        chosen.update({
            "screening_fidelity": float(screened["fidelity"]),
            "screening_fidelity_se": float(screened["fidelity_se"]),
            "fidelity": float(selected_confirmation["fidelity"]),
            "fidelity_se": float(selected_confirmation["fidelity_se"]),
            "fidelity_lcb_95": float(selected_confirmation["fidelity_lcb_95"]),
            "confirmation_blocks": int(
                selected_confirmation["confirmation_blocks"]),
            "block_fidelities": selected_confirmation["block_fidelities"],
            "block_spread": float(selected_confirmation["block_spread"]),
            "third_blob_excess_ucb": float(max(
                screened["third_blob_excess_ucb"],
                selected_confirmation["third_blob_excess_ucb"])),
            "third_cluster_guard_available": bool(
                screened.get("third_cluster_guard_available", False)
                and selected_confirmation.get(
                    "third_cluster_guard_available", False)),
            "third_cluster_supported": bool(
                screened.get("third_cluster_supported", False)
                or selected_confirmation.get("third_cluster_supported", False)),
            "third_cluster_fraction": float(max(
                screened.get("third_cluster_fraction", 0.0),
                selected_confirmation.get("third_cluster_fraction", 0.0))),
            "third_cluster_fraction_ucb_95": float(max(
                screened.get("third_cluster_fraction_ucb_95", 0.0),
                selected_confirmation.get(
                    "third_cluster_fraction_ucb_95", 0.0))),
            "third_cluster_single_state_fraction": float(max(
                screened.get("third_cluster_single_state_fraction", 0.0),
                selected_confirmation.get(
                    "third_cluster_single_state_fraction", 0.0))),
            "third_cluster_single_state_fraction_ucb_95": float(max(
                screened.get(
                    "third_cluster_single_state_fraction_ucb_95", 0.0),
                selected_confirmation.get(
                    "third_cluster_single_state_fraction_ucb_95", 0.0))),
            "selection_confirmation_complete": bool(complete),
        })
        self._leakage_selected_candidate = {
            key: chosen[key] for key in self.initial}
        self._adopt(chosen, "operational_leakage")
        self.data["leakage"].update({
            "attempts": attempts, "chosen": chosen,
            "optimized": True, "selection_safe": True,
            "screening_kind": "fixed_gaussian_duration_power",
            "drag_tuned": bool(tune_drag),
            "selection_confirmations": confirmations,
            "selection_confirmation_complete": bool(complete),
            "verified": False, "failure": None,
        })
        return chosen

    def _stage_operational_leakage_verify(self, allow_fallback=True):
        """Independently repeat every operational guard on the exact final tuple."""
        if not self._operational_leakage_active:
            return None
        p = self.params["leakage"]
        self._leakage_verified_candidate_key = None

        def verify(candidate, tag):
            rows, failures = [], []
            requested = max(int(p["operational_verify_blocks"]), 1)
            for block in range(requested):
                try:
                    rows.append(self._measure_operational_leakage_candidate(
                        candidate, int(p["operational_verify_shots"]),
                        int(p["operational_verify_shots"]),
                        "%s block %d" % (tag, block + 1)))
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    failures.append({
                        "block": block + 1,
                        "error": "%s: %s" % (type(exc).__name__, exc),
                    })
            passed = bool(
                len(rows) == requested and not failures
                and all(row.get("operational_safe", False) for row in rows))
            return rows, failures, passed

        candidate = dict(self.working)
        rows, failures, passed = verify(candidate, "operational verification")
        used_fallback = False
        if (allow_fallback and not passed
                and self._leakage_selected_candidate is not None
                and _control_key(candidate)
                != _control_key(self._leakage_selected_candidate)):
            # Keep the freshly optimized readout and restore only the known-safe
            # control waveform.  The ensuing full operational audit validates this
            # exact crossed tuple, including its readout-dependent third-cloud guard.
            candidate = dict(candidate)
            for key in ("qubit_freq", "qubit_pi_freq", "qubit_pi_gain", "sigma",
                        "qubit_drag_beta"):
                candidate[key] = self._leakage_selected_candidate[key]
            rows, failures, passed = verify(
                candidate, "operational safe-seed fallback")
            used_fallback = True
            if passed:
                self.working = dict(candidate)
        worst_even = max((float(row.get(
            "max_even_return_error_ucb", np.inf)) for row in rows), default=np.inf)
        worst_odd = max((float(row.get(
            "max_odd_inversion_error_ucb", np.inf)) for row in rows), default=np.inf)
        worst_blob = max((float(row.get(
            "third_blob_excess_ucb", np.inf)) for row in rows), default=np.inf)
        worst_cluster = max((float(row.get(
            "third_cluster_fraction", np.inf)) for row in rows), default=np.inf)
        worst_cluster_ucb = max((float(row.get(
            "third_cluster_fraction_ucb_95", np.inf))
                                 for row in rows), default=np.inf)
        worst_cluster_single_state = max((float(row.get(
            "third_cluster_single_state_fraction", np.inf))
                                          for row in rows), default=np.inf)
        worst_cluster_single_state_ucb = max((float(row.get(
            "third_cluster_single_state_fraction_ucb_95", np.inf))
                                              for row in rows), default=np.inf)
        if passed:
            failure_reason = None
        elif failures:
            failure_reason = (
                "fixed-Gaussian verification acquisition failed: %s"
                % failures[0]["error"])
        elif rows:
            failed_rows = [row for row in rows
                           if not row.get("operational_safe", False)]
            failure_reason = (
                failed_rows[0].get("failure")
                if failed_rows and failed_rows[0].get("failure") else
                "fresh fixed-Gaussian third-cloud verification failed")
        else:
            failure_reason = "fixed-Gaussian verification completed no blocks"
        self.data["leakage"].update({
            "verification": rows, "verified": bool(passed),
            "verification_failures": failures,
            "operational_verified": bool(passed),
            "verified_candidate_key": (
                list(_candidate_key(candidate)) if passed else None),
            "used_safe_seed_fallback": bool(used_fallback),
            "worst_even_return_error_ucb": worst_even,
            "worst_odd_inversion_error_ucb": worst_odd,
            "worst_third_blob_excess_ucb": worst_blob,
            "worst_third_cluster_fraction": worst_cluster,
            "worst_third_cluster_fraction_ucb_95": worst_cluster_ucb,
            "worst_third_cluster_single_state_fraction": (
                worst_cluster_single_state),
            "worst_third_cluster_single_state_fraction_ucb_95": (
                worst_cluster_single_state_ucb),
            "failure": failure_reason,
        })
        if passed:
            self._leakage_verified_candidate_key = _candidate_key(candidate)
        return bool(passed)

    # ------------------------------------------------------- direct leakage constraint
    @staticmethod
    def _ef_pulse(gain, frequency, phase=0.0):
        return ("pulse_at", int(round(gain)), float(phase),
                float(frequency), "reference")

    @staticmethod
    def _reference_pulse(gain, frequency, phase=0.0):
        return ("pulse_at", int(round(gain)), float(phase),
                float(frequency), "reference")

    @staticmethod
    def _ge_pulse(candidate, phase=0.0):
        return ("pulse", int(round(candidate["qubit_pi_gain"])), float(phase))

    def _sequence_mean(self, candidate, sequence, shots, seq_gap_us=None):
        i, q = self._acquire_sequence(
            candidate, sequence, int(shots), seq_gap_us=seq_gap_us)
        i, q = np.asarray(i, dtype=float), np.asarray(q, dtype=float)
        n = min(i.size, q.size)
        if n < 10:
            raise RuntimeError("sequence acquisition returned fewer than 10 shots")
        i, q = i[:n], q[:n]
        return {
            "i": float(np.mean(i)), "q": float(np.mean(q)),
            "se_i": float(np.std(i, ddof=1) / math.sqrt(n)),
            "se_q": float(np.std(q, ddof=1) / math.sqrt(n)),
            "shots": int(n),
        }

    def _population_with_local_refs(self, candidate, sequence, shots,
                                    excited_sequence=None):
        """Project one sequence between immediately adjacent g/e IQ references."""
        ground = self._sequence_mean(candidate, [], shots)
        if excited_sequence is None:
            excited_sequence = [self._ge_pulse(candidate)]
        excited = self._sequence_mean(
            candidate, excited_sequence, shots)
        measured = self._sequence_mean(candidate, sequence, shots)
        delta = np.array([
            excited["i"] - ground["i"], excited["q"] - ground["q"]],
            dtype=float)
        target = np.array([
            measured["i"] - ground["i"], measured["q"] - ground["q"]],
            dtype=float)
        denominator = float(np.dot(delta, delta))
        if not np.isfinite(denominator) or denominator <= 0:
            return np.nan, np.inf
        population = float(np.dot(target, delta) / denominator)
        gradient_m = delta / denominator
        gradient_e = target / denominator - 2.0 * population * delta / denominator
        gradient_g = -gradient_m - gradient_e
        sigma_m = np.array([measured["se_i"], measured["se_q"]])
        sigma_e = np.array([excited["se_i"], excited["se_q"]])
        sigma_g = np.array([ground["se_i"], ground["se_q"]])
        variance = float(
            np.sum((gradient_m * sigma_m) ** 2)
            + np.sum((gradient_e * sigma_e) ** 2)
            + np.sum((gradient_g * sigma_g) ** 2))
        return population, float(math.sqrt(max(variance, 0.0)))

    def _interleaved_sequence_fractions(self, candidate, sequences, metrics, shots):
        """Measure every labelled sequence in four randomized drift-balanced blocks."""
        labels = list(sequences)
        each = max(10, int(math.ceil(float(shots) / 4.0)))
        acquired = {label: [[], []] for label in labels}
        schedule = labels * 4
        for raw in self.rng.permutation(len(schedule)):
            label = schedule[int(raw)]
            i, q = self._acquire_sequence(
                candidate, sequences[label], each)
            acquired[label][0].append(np.asarray(i, dtype=float))
            acquired[label][1].append(np.asarray(q, dtype=float))
        return {
            label: ground_fraction_with_discriminator(
                np.concatenate(acquired[label][0]),
                np.concatenate(acquired[label][1]), metrics)
            for label in labels
        }

    def _audit_reference_ge_gain(self, candidate, gain, shots, total_span):
        """Directly verify that one reference pulse inverts and two return."""
        harmonic = []
        for count in (0, 1, 2):
            sequence = ([self._reference_pulse(
                0, candidate["qubit_pi_freq"])] if count == 0 else
                [self._reference_pulse(
                    gain, candidate["qubit_pi_freq"])] * count)
            harmonic.append(self._sequence_mean(
                candidate, sequence, int(shots)))
        z = np.asarray([complex(row["i"], row["q"]) for row in harmonic])
        baseline = 0.5 * (z[0] + z[2])
        contrast = float(abs(z[1] - baseline))
        return_error = float(abs(z[2] - z[0]))
        noise = float(3.0 * math.sqrt(sum(
            row["se_i"] ** 2 + row["se_q"] ** 2 for row in harmonic)))
        p = self.params["leakage"]
        allowance = float(p["reference_max_return_fraction"]) * contrast + noise
        normalized_contrast = contrast / max(float(total_span), 1e-12)
        passed = bool(
            normalized_contrast >= float(p["reference_min_contrast"])
            and return_error <= allowance)
        return {
            "gain": int(round(gain)), "harmonic": harmonic,
            "contrast": contrast, "return_error": return_error,
            "return_allowance": allowance,
            "normalized_contrast": normalized_contrast,
            "passed": passed,
        }

    def _calibrate_reference_ge(self, candidate):
        """Calibrate a long narrow-bandwidth g-e pulse for independent qutrit SPAM."""
        p = self.params["leakage"]
        gains = self._integer_axis(
            0, int(p["reference_gain_max"]), int(p["reference_gain_points"]),
            lower=0, upper=32767)
        response = np.full(gains.size, np.nan + 1j * np.nan, dtype=complex)
        errors = np.full((gains.size, 2), np.inf, dtype=float)
        for raw in self.rng.permutation(gains.size):
            index = int(raw)
            sequence = [self._reference_pulse(
                gains[index], candidate["qubit_pi_freq"])]
            measured = self._sequence_mean(
                candidate, sequence, int(p["reference_rabi_shots"]))
            response[index] = complex(measured["i"], measured["q"])
            errors[index] = measured["se_i"], measured["se_q"]
        displacement = response - response[0]
        xy = np.column_stack([displacement.real, displacement.imag])
        xy -= np.mean(xy, axis=0)
        try:
            _u, _s, vh = np.linalg.svd(xy, full_matrices=False)
            direction = vh[0]
        except Exception:
            direction = np.array([1.0, 0.0])
        projection = displacement.real * direction[0] + displacement.imag * direction[1]
        rabi = fit_anchored_rabi(gains, projection)
        if (not rabi.get("ok")
                or float(rabi.get("r2", -np.inf))
                < float(p["reference_min_rabi_r2"])
                or not np.isfinite(rabi.get("pi_gain", np.nan))):
            raise RuntimeError(
                "long reference g-e pulse did not produce a coherent Rabi")
        gain = int(round(rabi["pi_gain"]))
        if gain <= 0 or gain >= int(p["reference_gain_max"]):
            raise RuntimeError("long reference g-e pi gain is outside its range")
        total_span = max(float(np.ptp(response.real)), float(np.ptp(response.imag)),
                         1e-12)
        audits = [self._audit_reference_ge_gain(
            candidate, gain, int(p["reference_rabi_shots"]), total_span)]
        if not audits[0]["passed"]:
            # A damped multi-period fit can lock to 3pi or another alias even with a
            # good global r2.  The physical requirement is simpler and stronger:
            # one pulse must invert and two identical pulses must return.  On audit
            # failure, directly test a small set of observed response maxima plus a
            # local neighborhood of the fit and select the lowest passing gain.
            displacement_size = np.abs(response - response[0])
            peaks, _properties = find_peaks(displacement_size)
            ranked_peaks = sorted(
                (int(index) for index in peaks if int(gains[index]) > 0),
                key=lambda index: float(displacement_size[index]), reverse=True)[:6]
            local = np.clip(np.rint(float(gain) * np.linspace(0.65, 1.35, 9)),
                            1, int(p["reference_gain_max"]) - 1).astype(int)
            rescue_gains = [int(gains[index]) for index in ranked_peaks]
            rescue_gains.extend(int(value) for value in local)
            rescue_gains = sorted(set(rescue_gains) - {int(gain)})
            for rescue_gain in rescue_gains:
                audits.append(self._audit_reference_ge_gain(
                    candidate, rescue_gain, int(p["reference_rabi_shots"]),
                    total_span))
            passing = [row for row in audits if row["passed"]]
            if passing:
                selected = min(passing, key=lambda row: row["gain"])
                gain = int(selected["gain"])
            else:
                selected = audits[0]
        else:
            selected = audits[0]
        if not selected["passed"]:
            raise RuntimeError(
                "long reference g-e 0/pi/2pi audit failed "
                "(relative contrast %.3f, return %.4g > %.4g)"
                % (selected["normalized_contrast"], selected["return_error"],
                   selected["return_allowance"]))
        return {
            "ge_reference_gain": gain,
            "reference_sigma_us": max(
                float(p["reference_sigma_us"]), float(candidate["sigma"])),
            "gains": gains, "response": response, "response_se": errors,
            "projection": projection, "rabi": rabi,
            "harmonic": selected["harmonic"],
            "harmonic_contrast": selected["contrast"],
            "harmonic_return_error": selected["return_error"],
            "harmonic_audits": audits,
            "harmonic_rescue_used": bool(gain != int(round(rabi["pi_gain"]))),
        }

    def _calibrate_ef_transition(self, candidate):
        """Find and coherently verify e-f with a g-e/e-f/g-e shelving witness."""
        p = self.params["leakage"]
        ge_reference = self._calibrate_reference_ge(candidate)
        ge = self._reference_pulse(
            ge_reference["ge_reference_gain"], candidate["qubit_pi_freq"])
        try:
            configured = float(self.input_cfg.get("qubit_ef_freq", np.nan))
        except (TypeError, ValueError):
            configured = np.nan
        alpha_prior = p.get("anharmonicity_prior_mhz")
        if alpha_prior is None:
            alpha_prior = self.input_cfg.get("qubit_anharmonicity_mhz", np.nan)
        try:
            alpha_prior = float(alpha_prior)
        except (TypeError, ValueError):
            alpha_prior = np.nan
        centre = (configured if np.isfinite(configured)
                  else float(candidate["qubit_pi_freq"]) + alpha_prior)
        if not np.isfinite(centre):
            raise RuntimeError(
                "direct leakage requires qubit_ef_freq or qubit_anharmonicity_mhz")
        def scan(grid):
            grid = np.asarray(grid, dtype=float)
            passes = np.full((2, grid.size), np.nan + 1j * np.nan, dtype=complex)
            orders = (range(grid.size), range(grid.size - 1, -1, -1))
            for pass_index, order in enumerate(orders):
                for index in order:
                    seq = [ge, self._ef_pulse(
                        p["ef_spec_gain"], grid[index]), ge]
                    measured = self._sequence_mean(
                        candidate, seq, int(p["ef_spec_shots"]))
                    passes[pass_index, index] = complex(
                        measured["i"], measured["q"])
            average = np.mean(passes, axis=0)
            retained = max(int(p.get("ef_feature_candidates", 8)), 3)
            combined = self._spectral_features(
                grid, average, max_candidates=retained)
            individual = [self._spectral_features(
                grid, passes[index], max_candidates=retained)
                for index in range(2)]
            return average, passes, combined, individual

        broad_frequencies = self._float_axis(
            centre, p["ef_span_mhz"], p["ef_points"], include=[centre])
        broad, broad_passes, broad_features, broad_individual = scan(
            broad_frequencies)
        if float(broad_features["best_snr"]) < float(p["ef_min_feature_snr"]):
            raise RuntimeError(
                "e-f shelving scan found no %.1f-sigma feature in %.1f +/- %.1f MHz"
                % (p["ef_min_feature_snr"], centre, p["ef_span_mhz"] / 2.0))
        try:
            broad_match = self._reproduced_spectral_seed(
                broad_frequencies, broad_features, broad_individual,
                p["ef_max_repeat_error_mhz"], p["ef_min_feature_snr"])
        except RuntimeError as exc:
            raise RuntimeError(
                "e-f broad-scan feature did not reproduce in opposed passes") from exc
        broad_seed = float(broad_match["frequency_mhz"])

        narrow_frequencies = self._float_axis(
            broad_seed, p["ef_narrow_span_mhz"], p["ef_narrow_points"],
            include=[broad_seed])
        narrow, narrow_passes, narrow_features, narrow_individual = scan(
            narrow_frequencies)
        try:
            narrow_match = self._reproduced_spectral_seed(
                narrow_frequencies, narrow_features, narrow_individual,
                p["ef_max_repeat_error_mhz"], p["ef_min_feature_snr"])
        except RuntimeError as exc:
            raise RuntimeError(
                "e-f shelving feature did not reproduce in the narrow confirmation"
                ) from exc
        ef_frequency = float(narrow_match["frequency_mhz"])
        if abs(ef_frequency - broad_seed) > float(p["ef_max_repeat_error_mhz"]):
            raise RuntimeError(
                "e-f shelving feature did not reproduce in the narrow confirmation")
        alpha = ef_frequency - float(candidate["qubit_pi_freq"])
        if alpha >= -5.0:
            raise RuntimeError(
                "candidate e-f line %.4f MHz gives non-transmon anharmonicity %.3f MHz"
                % (ef_frequency, alpha))

        gains = self._integer_axis(
            0, int(p["ef_gain_max"]), int(p["ef_gain_points"]),
            lower=0, upper=32767)
        populations = np.full(gains.size, np.nan)
        population_se = np.full(gains.size, np.inf)
        for raw in self.rng.permutation(gains.size):
            index = int(raw)
            sequence = [ge, self._ef_pulse(
                gains[index], ef_frequency), ge]
            populations[index], population_se[index] = \
                self._population_with_local_refs(
                    candidate, sequence, int(p["ef_rabi_shots"]),
                    excited_sequence=[ge])
        rabi = fit_anchored_rabi(gains, populations)
        if (not rabi.get("ok")
                or float(rabi.get("r2", -np.inf)) < float(p["ef_min_rabi_r2"])
                or not np.isfinite(rabi.get("pi_gain", np.nan))):
            raise RuntimeError("e-f candidate did not produce a coherent Rabi")
        ef_gain = int(round(rabi["pi_gain"]))
        if ef_gain <= 0 or ef_gain >= int(p["ef_gain_max"]):
            raise RuntimeError("e-f pi gain lies outside the authorized range")

        harmonic = []
        for count in (0, 1, 2):
            ef_sequence = ([self._ef_pulse(0, ef_frequency)] if count == 0
                           else [self._ef_pulse(
                               ef_gain, ef_frequency)] * count)
            sequence = [ge] + ef_sequence + [ge]
            harmonic.append(self._population_with_local_refs(
                candidate, sequence, int(p["ef_rabi_shots"]),
                excited_sequence=[ge]))
        baseline = 0.5 * (harmonic[0][0] + harmonic[2][0])
        contrast = abs(harmonic[1][0] - baseline)
        return_error = abs(harmonic[2][0] - harmonic[0][0])
        return_allowance = (
            float(p["ef_max_return_fraction"]) * contrast
            + 3.0 * math.hypot(harmonic[0][1], harmonic[2][1]))
        if (not np.isfinite(contrast)
                or contrast < float(p["ef_min_rabi_contrast"])
                or return_error > return_allowance):
            raise RuntimeError(
                "e-f 0/pi/2pi audit failed (contrast %.3f, return %.3f > %.3f)"
                % (contrast, return_error, return_allowance))
        calibration = {
            "ef_frequency": ef_frequency, "ef_gain": ef_gain,
            "anharmonicity_mhz": alpha,
            "ge_reference": ge_reference,
            "ge_reference_gain": ge_reference["ge_reference_gain"],
            "reference_sigma_us": ge_reference["reference_sigma_us"],
            "broad_frequencies_mhz": broad_frequencies,
            "broad_response": broad, "broad_passes": broad_passes,
            "broad_features": broad_features, "broad_match": broad_match,
            "narrow_frequencies_mhz": narrow_frequencies,
            "narrow_response": narrow, "narrow_passes": narrow_passes,
            "narrow_features": narrow_features, "narrow_match": narrow_match,
            "rabi_gains": gains, "rabi_population": populations,
            "rabi_population_se": population_se, "rabi": rabi,
            "harmonic": harmonic, "harmonic_contrast": float(contrast),
            "harmonic_return_error": float(return_error),
        }
        self._log(
            "leakage", "OK",
            "shelving-calibrated e-f %.4f MHz (anharmonicity %.3f MHz), "
            "e-f pi %d DAC" % (ef_frequency, alpha, ef_gain))
        return calibration

    def _leakage_response_calibration(self, candidate, ef_calibration, shots):
        """Measure the identity/shelving response matrix for prepared g/e/f."""
        p = self.params["leakage"]
        ig, qg, ie, qe = self._acquire_ss_pair(candidate, int(shots))
        self._record_raw_diagnostic(
            "leakage_response_reference", candidate,
            {"ground_i": ig, "ground_q": qg,
             "excited_i": ie, "excited_q": qe},
            {"shots": int(shots), "state_order": "ge"})
        metrics = step5_metrics(ig, qg, ie, qe)
        ge = self._reference_pulse(
            ef_calibration["ge_reference_gain"],
            candidate["qubit_pi_freq"])
        ef = self._ef_pulse(
            ef_calibration["ef_gain"], ef_calibration["ef_frequency"])
        preparation = {"g": [], "e": [ge], "f": [ge, ef]}
        sequences = {}
        for state in ("g", "e", "f"):
            sequences[(state, "identity")] = list(preparation[state])
            sequences[(state, "shelved")] = list(preparation[state]) + [ef, ge]
        fractions = self._interleaved_sequence_fractions(
            candidate, sequences, metrics, int(shots))
        calibration = {
            state: (
                fractions[(state, "identity")][0],
                fractions[(state, "identity")][1],
                fractions[(state, "shelved")][0],
                fractions[(state, "shelved")][1],
            ) for state in ("g", "e", "f")
        }
        condition_probe = solve_shelved_qutrit_population(
            calibration,
            (calibration["g"][0], calibration["g"][1]),
            (calibration["g"][2], calibration["g"][3]),
            p["max_response_condition"])
        identity_selectivity = float(
            calibration["g"][0]
            - max(calibration["e"][0], calibration["f"][0]))
        shelving_selectivity = float(
            calibration["f"][2]
            - max(calibration["g"][2], calibration["e"][2]))
        ok = bool(
            condition_probe.get("matrix_ok", False)
            and identity_selectivity >= float(p["min_identity_selectivity"])
            and shelving_selectivity >= float(p["min_shelving_selectivity"]))
        return {
            "ok": ok, "metrics": metrics, "calibration": calibration,
            "condition": float(condition_probe.get("condition", np.inf)),
            "response_matrix": condition_probe.get("response_matrix"),
            "response_matrix_se": condition_probe.get("response_matrix_se"),
            "identity_selectivity": identity_selectivity,
            "shelving_selectivity": shelving_selectivity,
            "reason": None if ok else "ill-conditioned or nonselective shelving",
        }

    def _leakage_target_population(self, candidate, sequence, response,
                                   ef_calibration, shots, seq_gap_us):
        """Interleave target identity/shelving shots and invert P(g/e/f)."""
        ge = self._reference_pulse(
            ef_calibration["ge_reference_gain"],
            candidate["qubit_pi_freq"])
        ef = self._ef_pulse(
            ef_calibration["ef_gain"], ef_calibration["ef_frequency"])
        sequences = {
            "identity": list(sequence),
            "shelved": list(sequence) + [ef, ge],
        }
        # Preserve the selected gap in both target arms.  The appended shelving pulses
        # use the same short gap, matching the response calibration convention.
        metrics = response["metrics"]
        labels = list(sequences)
        each = max(10, int(math.ceil(float(shots) / 4.0)))
        acquired = {label: [[], []] for label in labels}
        schedule = labels * 4
        for raw in self.rng.permutation(len(schedule)):
            label = schedule[int(raw)]
            i, q = self._acquire_sequence(
                candidate, sequences[label], each, seq_gap_us=seq_gap_us)
            acquired[label][0].append(np.asarray(i, dtype=float))
            acquired[label][1].append(np.asarray(q, dtype=float))
        fractions = {
            label: ground_fraction_with_discriminator(
                np.concatenate(acquired[label][0]),
                np.concatenate(acquired[label][1]), metrics)
            for label in labels
        }
        solved = solve_shelved_qutrit_population(
            response["calibration"], fractions["identity"], fractions["shelved"],
            self.params["leakage"]["max_response_condition"])
        solved["ground_fractions"] = fractions
        return solved

    def _measure_leakage_candidate(self, candidate, ef_calibration, shots,
                                   reference_shots, label):
        """Measure step-5 fidelity, third-cloud excess, and direct/amplified P(f)."""
        p = self.params["leakage"]
        candidate = dict(candidate)
        direct = self._measure_candidate_with_multimodality(
            candidate, int(reference_shots), "%s direct step-5" % label)
        response = self._leakage_response_calibration(
            candidate, ef_calibration, int(reference_shots))
        row = dict(candidate)
        row.update({
            "fidelity": float(direct["fidelity"]),
            "fidelity_se": float(direct["fidelity_se"]),
            "fidelity_lcb_95": float(direct["fidelity_lcb_95"]),
            "third_blob_excess": float(direct["third_blob_excess"]),
            "third_blob_excess_se": float(direct["third_blob_excess_se"]),
            "third_blob_excess_ucb": float(direct["third_blob_excess_ucb_95"]),
            "ground_outlier_frac": float(direct["ground_outlier_frac"]),
            "excited_outlier_frac": float(direct["excited_outlier_frac"]),
            "third_cluster_guard_available": bool(direct.get(
                "third_cluster_guard_available", False)),
            "third_cluster_supported": bool(direct.get(
                "third_cluster_supported", False)),
            "third_cluster_fraction": float(direct.get(
                "third_cluster_fraction", np.nan)),
            "third_cluster_fraction_ucb_95": float(direct.get(
                "third_cluster_fraction_ucb_95", np.nan)),
            "third_cluster_single_state_fraction": float(direct.get(
                "third_cluster_single_state_fraction", np.nan)),
            "third_cluster_single_state_fraction_ucb_95": float(direct.get(
                "third_cluster_single_state_fraction_ucb_95", np.nan)),
            "response": response, "witnesses": [], "label": str(label),
        })
        if not response.get("ok", False):
            row.update(valid=False, leakage_safe=False,
                       single_p2_ucb=np.inf, amplified_p2_ucb=np.inf,
                       failure=response.get("reason"))
            return row
        depths = [int(value) for value in p["depths"]]
        phases = [float(value) for value in p["gap_phases"]]
        z = _simultaneous_z(
            len(depths) * len(phases), p.get("familywise_alpha", 0.05),
            p.get("confidence_sigma", 1.96))
        alpha = float(ef_calibration["anharmonicity_mhz"])
        base_gap = float(self.input_cfg.get("seq_gap_us", 0.01))
        period_us = 1.0 / max(abs(alpha), 1e-12)
        for depth in depths:
            for phase in phases:
                gap = base_gap + phase * period_us
                sequence = [self._ge_pulse(candidate)] * depth
                solved = self._leakage_target_population(
                    candidate, sequence, response, ef_calibration,
                    int(shots), gap)
                solved.update({
                    "depth": int(depth), "gap_phase": float(phase),
                    "gap_us": float(gap),
                })
                row["witnesses"].append(solved)
        if not row["witnesses"] or not all(
                witness.get("ok", False) for witness in row["witnesses"]):
            row.update(valid=False, leakage_safe=False,
                       single_p2_ucb=np.inf, amplified_p2_ucb=np.inf,
                       failure="one or more qutrit inversions failed")
            return row
        for witness in row["witnesses"]:
            witness["p2_ucb"] = float(np.clip(
                witness["p2"] + z * witness["p2_se"], 0.0, 1.0))
        direct_witnesses = [w for w in row["witnesses"] if w["depth"] == 1]
        amplified_witnesses = [w for w in row["witnesses"] if w["depth"] > 1]
        single_ucb = max((w["p2_ucb"] for w in direct_witnesses), default=np.inf)
        amplified_ucb = max(
            (w["p2_ucb"] for w in amplified_witnesses), default=single_ucb)
        finite = bool(
            np.isfinite(row["fidelity"]) and np.isfinite(row["fidelity_se"])
            and np.isfinite(single_ucb) and np.isfinite(amplified_ucb)
            and row["third_cluster_guard_available"]
            and np.isfinite(row["third_cluster_fraction_ucb_95"])
            and np.isfinite(
                row["third_cluster_single_state_fraction_ucb_95"]))
        safe = bool(
            finite
            and single_ucb <= float(p["max_single_p2"])
            and amplified_ucb <= float(p["max_amplified_p2"])
            and row["third_blob_excess_ucb"]
            <= float(p["max_third_blob_excess"])
            and (not row["third_cluster_supported"]
                 or (row["third_cluster_fraction_ucb_95"]
                     <= float(p["max_third_cluster_fraction"])
                     and row[
                         "third_cluster_single_state_fraction_ucb_95"]
                     <= float(
                         p["max_single_state_third_cluster_fraction"]))))
        row.update({
            "valid": finite, "leakage_safe": safe,
            "single_p2_ucb": float(single_ucb),
            "amplified_p2_ucb": float(amplified_ucb),
            "confidence_sigma": float(z), "failure": None,
        })
        return row

    def _leakage_waveform_pool(self, limit=None):
        """High-fidelity distinct control waveforms, including longer fallbacks."""
        if limit is None:
            limit = self.params["leakage"]["max_candidate_waveforms"]
        limit = max(int(limit), 1)

        def physical(row):
            # Compare control waveforms under one fixed readout/reset calibration.
            # Pulling each historical row's old readout tuple would mix raw feedback
            # thresholds and make duration look better or worse because of SPAM drift.
            candidate = dict(self.working)
            for key in ("qubit_freq", "qubit_pi_freq", "qubit_pi_gain", "sigma",
                        "qubit_drag_beta"):
                candidate[key] = row[key]
            return candidate

        def control_key(row):
            return (
                round(float(row["qubit_pi_freq"]), 7),
                int(round(row["qubit_pi_gain"])),
                round(float(row["sigma"]), 9),
            )

        pool = ([dict(self.working)]
                if self._candidate_in_qualified_transition(self.working) else [])
        if not pool:
            raise RuntimeError(
                "no qualified-transition waveform is available for direct leakage "
                "screening")
        seen = {control_key(self.working)}
        rows = self._qualified_transition_rows(
            list(self.data.get("final_candidates", [])) + list(self._confirmed))
        ranked = sorted(rows, key=lambda row: (
            float(row.get("fidelity_lcb_95", -np.inf)),
            float(row.get("fidelity", -np.inf))), reverse=True)
        # First preserve the best candidate at every longer duration.  Leakage rises
        # rapidly for short/high-amplitude pulses, so a pure global-fidelity shortlist
        # can otherwise omit the most important recovery direction.
        current_sigma = float(self.working["sigma"])
        by_sigma = {}
        for row in ranked:
            if not all(key in row for key in self.initial):
                continue
            sigma = round(float(row["sigma"]), 9)
            by_sigma.setdefault(sigma, row)
        longer = [row for sigma, row in sorted(by_sigma.items())
                  if sigma > current_sigma + 1e-10]
        slots = max(limit - 1, 0)
        if len(longer) > slots > 0:
            indices = np.unique(np.rint(np.linspace(
                0, len(longer) - 1, slots)).astype(int))
            longer = [longer[int(index)] for index in indices]
        for row in longer + ranked:
            if len(pool) >= limit:
                break
            if not all(key in row for key in self.initial):
                continue
            candidate = physical(row)
            key = control_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            pool.append(candidate)
        return pool

    def _stage_leakage(self):
        """Choose the highest-fidelity waveform satisfying direct leakage bounds."""
        if not self._leakage_active:
            self._log("leakage", "SKIP",
                      "no e-f frequency/anharmonicity prior; direct P(f) inactive")
            return None
        p = self.params["leakage"]
        attempts = []
        for waveform_index, waveform in enumerate(self._leakage_waveform_pool()):
            try:
                ef_calibration = self._calibrate_ef_transition(waveform)
            except Exception as exc:
                attempts.append({
                    "candidate": dict(waveform), "ef_calibration": None,
                    "rows": [], "chosen": None,
                    "failure": "%s: %s" % (type(exc).__name__, exc),
                })
                self._log(
                    "leakage", "WARN",
                    "waveform %d e-f calibration failed (%s: %s)"
                    % (waveform_index + 1, type(exc).__name__, exc))
                continue
            incumbent_beta = float(waveform.get("qubit_drag_beta", 0.0))
            rows = []

            def measure(beta, suffix):
                candidate = _with_candidate(
                    waveform, qubit_drag_beta=float(beta))
                row = self._measure_leakage_candidate(
                    candidate, ef_calibration, int(p["shots"]),
                    int(p["reference_shots"]),
                    "leakage waveform %d %s" % (waveform_index + 1, suffix))
                rows.append(row)
                self._log(
                    "leakage", "OK" if row.get("leakage_safe") else "WARN",
                    "waveform %d beta %+.5f -> F %.4f +/- %.4f, "
                    "P(f) UCB one/amplified %s/%s, third-cloud excess UCB %.4f%s"
                    % (waveform_index + 1, beta,
                       row.get("fidelity", np.nan),
                       row.get("fidelity_se", np.inf),
                       ("%.4f" % row["single_p2_ucb"])
                       if np.isfinite(row.get("single_p2_ucb", np.inf)) else "FAILED",
                       ("%.4f" % row["amplified_p2_ucb"])
                       if np.isfinite(row.get("amplified_p2_ucb", np.inf)) else "FAILED",
                       row.get("third_blob_excess_ucb", np.inf),
                       " [SAFE]" if row.get("leakage_safe") else ""))
                return row

            incumbent = measure(incumbent_beta, "incumbent")
            # Safety is a constraint, not the optimization objective.  Even a safe
            # incumbent has not established the best fidelity over beta, so always run
            # the first two-sided DRAG map.  Further span extensions are needed only
            # while no safe point exists or the best safe point remains on a boundary.
            measured = {round(incumbent_beta, 8)}
            for extension in range(max(int(p["max_extensions"]), 1)):
                span = min(float(p["beta_span"]) * (1.7 ** extension),
                           float(p["max_beta_span"]))
                values = list(np.linspace(
                    incumbent_beta - span, incumbent_beta + span,
                    max(int(p["beta_points"]), 5)))
                values.extend((0.0, incumbent_beta))
                values = np.unique(np.round(values, 8))
                for raw in self.rng.permutation(values.size):
                    beta = float(values[int(raw)])
                    if round(beta, 8) in measured:
                        continue
                    measured.add(round(beta, 8))
                    measure(beta, "scan %d" % (extension + 1))
                safe_now = [row for row in rows if row.get("leakage_safe")]
                if safe_now:
                    best_safe = max(safe_now, key=lambda row: (
                        float(row["fidelity_lcb_95"]),
                        -float(row["single_p2_ucb"]),
                        -float(row["amplified_p2_ucb"])))
                    beta_values = np.asarray([row["qubit_drag_beta"]
                                              for row in rows], dtype=float)
                    if (best_safe["qubit_drag_beta"]
                            > np.min(beta_values) + 1e-9
                            and best_safe["qubit_drag_beta"]
                            < np.max(beta_values) - 1e-9):
                        break
            safe_rows = [row for row in rows if row.get("leakage_safe")]
            if safe_rows:
                chosen = max(safe_rows, key=lambda row: (
                    float(row["fidelity_lcb_95"]),
                    -float(row["single_p2_ucb"]),
                    -float(row["amplified_p2_ucb"])))
            else:
                valid_rows = [row for row in rows if row.get("valid")]
                if valid_rows:
                    def violation(row):
                        return max(
                            float(row["single_p2_ucb"]) / float(p["max_single_p2"]),
                            float(row["amplified_p2_ucb"])
                            / float(p["max_amplified_p2"]),
                            float(row["third_blob_excess_ucb"])
                            / float(p["max_third_blob_excess"]),
                        )
                    chosen = min(valid_rows, key=lambda row: (
                        violation(row), -float(row["fidelity_lcb_95"])))
                else:
                    chosen = None
            attempts.append({
                "candidate": dict(waveform),
                "ef_calibration": ef_calibration,
                "rows": rows, "chosen": chosen, "failure": None,
            })
        feasible = [attempt for attempt in attempts
                    if isinstance(attempt.get("chosen"), dict)
                    and attempt["chosen"].get("leakage_safe", False)]
        if feasible:
            selected_attempt = max(feasible, key=lambda attempt: (
                float(attempt["chosen"]["fidelity_lcb_95"]),
                -float(attempt["chosen"]["single_p2_ucb"]),
                -float(attempt["chosen"]["amplified_p2_ucb"])))
        else:
            measured = [attempt for attempt in attempts
                        if attempt.get("chosen") is not None]
            if not measured:
                self.data["leakage"].update({
                    "attempts": attempts, "optimized": False,
                    "verified": False,
                    "failure": "no waveform produced a valid direct leakage estimate",
                })
                raise RuntimeError(self.data["leakage"]["failure"])
            selected_attempt = min(measured, key=lambda attempt: (
                max(
                    float(attempt["chosen"].get("single_p2_ucb", np.inf))
                    / float(p["max_single_p2"]),
                    float(attempt["chosen"].get("amplified_p2_ucb", np.inf))
                    / float(p["max_amplified_p2"]),
                    float(attempt["chosen"].get(
                        "third_blob_excess_ucb", np.inf))
                    / float(p["max_third_blob_excess"])),
                -float(attempt["chosen"].get("fidelity_lcb_95", -np.inf))))
        chosen = selected_attempt["chosen"]

        # Beta/duration screening compares many noisy fidelities.  Replaying the top
        # safe physical tuples in randomized round-robin blocks removes that winner's
        # curse and prevents slow drift from favoring whichever waveform ran first.
        # Direct leakage is independently re-audited after all subsequent refinements.
        safe_pairs = [
            (attempt, row) for attempt in attempts for row in attempt.get("rows", [])
            if row.get("leakage_safe", False)
        ]
        selection_confirmations = []
        selection_complete = False
        if safe_pairs:
            ranked_pairs = sorted(safe_pairs, key=lambda pair: (
                float(pair[1].get("fidelity_lcb_95", -np.inf)),
                float(pair[1].get("fidelity", -np.inf))), reverse=True)
            covered_rows = self._duration_covered_shortlist(
                [row for _attempt, row in ranked_pairs],
                max(int(p["selection_shortlist"]), 1))
            selected_pairs = [
                next(pair for pair in ranked_pairs
                     if _candidate_key(pair[1]) == _candidate_key(row))
                for row in covered_rows
            ]
            try:
                selection_confirmations = self._confirm_candidates(
                    [row for _attempt, row in selected_pairs],
                    int(p["selection_fidelity_shots"]),
                    int(p["selection_fidelity_blocks"]),
                    "held-out leakage-feasible fidelity selection",
                    add_to_history=True)
                selection_complete = self._confirmation_batch_complete(
                    selection_confirmations)
                confirmed = self._best_aggregate(selection_confirmations)
                if confirmed is not None:
                    key = _candidate_key(confirmed)
                    pair = next((pair for pair in selected_pairs
                                 if _candidate_key(pair[1]) == key), None)
                    if pair is not None:
                        selected_attempt, screened = pair
                        chosen = dict(screened)
                        chosen.update({
                            "screening_fidelity": float(screened["fidelity"]),
                            "screening_fidelity_se": float(screened["fidelity_se"]),
                            "fidelity": float(confirmed["fidelity"]),
                            "fidelity_se": float(confirmed["fidelity_se"]),
                            "fidelity_lcb_95": float(confirmed["fidelity_lcb_95"]),
                            "confirmation_blocks": int(
                                confirmed["confirmation_blocks"]),
                            "block_fidelities": confirmed["block_fidelities"],
                            "block_spread": float(confirmed["block_spread"]),
                            "selection_confirmation_complete": bool(
                                selection_complete),
                        })
                        selected_attempt["chosen"] = chosen
            except Exception as exc:
                self._log(
                    "leakage", "WARN",
                    "held-out feasible-fidelity comparison failed (%s: %s); "
                    "retaining the best screened safe tuple for later final replay"
                    % (type(exc).__name__, exc))
        self._leakage_selected_candidate = {
            key: chosen[key] for key in self.initial}
        self._leakage_ef_calibration = selected_attempt["ef_calibration"]
        self._adopt(chosen, "leakage")
        self.data["leakage"].update({
            "attempts": attempts, "chosen": chosen,
            "ef_calibration": self._leakage_ef_calibration,
            "direct_p2_measured": True,
            "selection_confirmations": selection_confirmations,
            "selection_confirmation_complete": bool(selection_complete),
            "optimized": True, "verified": False,
            "selection_safe": bool(chosen.get("leakage_safe", False)),
            "failure": (None if chosen.get("leakage_safe") else
                        "no measured waveform met every leakage constraint"),
        })
        if chosen.get("leakage_safe"):
            self._log(
                "leakage", "OK",
                "leakage-constrained winner retains F %.4f with one-pulse/amplified "
                "P(f) UCB %.4f/%.4f and third-cloud excess UCB %.4f"
                % (chosen["fidelity"], chosen["single_p2_ucb"],
                   chosen["amplified_p2_ucb"], chosen["third_blob_excess_ucb"]))
        else:
            self._log(
                "leakage", "WARN",
                "no waveform passed every leakage bound; retaining the least-violating "
                "measured candidate for reporting, but automatic writes are blocked")
        return chosen

    def _stage_leakage_verify(self, allow_fallback=True):
        """Fresh independent leakage blocks after all post-DRAG control refinements."""
        if not self._leakage_active:
            return None
        p = self.params["leakage"]
        self._leakage_verified_candidate_key = None

        def verify(candidate, tag):
            # Every duration/frequency control family gets its own long g-e and e-f
            # shelving calibration.  Reusing the calibration from whichever waveform
            # won the earlier screen can mislabel e/f preparation for another latency
            # contender and is not a valid direct P(f) certificate.
            calibration = self._calibrate_ef_transition(candidate)
            rows = []
            for block in range(max(int(p["verify_blocks"]), 1)):
                rows.append(self._measure_leakage_candidate(
                    candidate, calibration,
                    int(p["verify_shots"]), int(p["verify_shots"]),
                    "%s block %d" % (tag, block + 1)))
            passed = bool(
                len(rows) == max(int(p["verify_blocks"]), 1)
                and all(row.get("valid") and row.get("leakage_safe")
                        for row in rows))
            return rows, passed, calibration

        candidate = dict(self.working)
        verification_errors = []
        calibration = None
        try:
            rows, passed, calibration = verify(
                candidate, "leakage verification")
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            rows, passed = [], False
            verification_errors.append(
                "%s: %s" % (type(exc).__name__, exc))
        used_fallback = False
        if (allow_fallback and not passed
                and self._leakage_selected_candidate is not None
                and _control_key(candidate)
                != _control_key(self._leakage_selected_candidate)):
            self._log(
                "leakage_verify", "WARN",
                "post-leakage coherent refinement violated the leakage constraint; "
                "restoring and independently replaying the measured safe seed")
            candidate = dict(candidate)
            for key in ("qubit_freq", "qubit_pi_freq", "qubit_pi_gain", "sigma",
                        "qubit_drag_beta"):
                candidate[key] = self._leakage_selected_candidate[key]
            try:
                rows, passed, calibration = verify(
                    candidate, "leakage safe-seed fallback")
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                rows, passed, calibration = [], False, None
                verification_errors.append(
                    "%s: %s" % (type(exc).__name__, exc))
            used_fallback = True
            if passed:
                self.working = dict(candidate)
        worst_single = max(
            (float(row.get("single_p2_ucb", np.inf)) for row in rows),
            default=np.inf)
        worst_amplified = max(
            (float(row.get("amplified_p2_ucb", np.inf)) for row in rows),
            default=np.inf)
        worst_blob = max(
            (float(row.get("third_blob_excess_ucb", np.inf)) for row in rows),
            default=np.inf)
        self.data["leakage"].update({
            "verification": rows, "verified": bool(passed),
            "direct_verified": bool(passed),
            "direct_p2_measured": True,
            "verified_candidate_key": (
                list(_candidate_key(candidate)) if passed else None),
            "used_safe_seed_fallback": bool(used_fallback),
            "verification_errors": verification_errors,
            "worst_single_p2_ucb": worst_single,
            "worst_amplified_p2_ucb": worst_amplified,
            "worst_third_blob_excess_ucb": worst_blob,
            "failure": (None if passed else
                        ("fresh leakage calibration/verification failed: %s"
                         % verification_errors[-1]
                         if verification_errors else
                         "fresh leakage verification exceeded a hard constraint")),
        })
        if passed:
            self._leakage_verified_candidate_key = _candidate_key(candidate)
            self._leakage_ef_calibration = calibration
        self._log(
            "leakage_verify", "OK" if passed else "WARN",
            "%d fresh blocks: worst P(f) UCB one/amplified %s/%s, "
            "third-cloud excess UCB %s -- %s"
            % (len(rows),
               "%.4f" % worst_single if np.isfinite(worst_single) else "FAILED",
               "%.4f" % worst_amplified
               if np.isfinite(worst_amplified) else "FAILED",
               "%.4f" % worst_blob if np.isfinite(worst_blob) else "FAILED",
               "PASS" if passed else "WRITE BLOCKED"))
        return bool(passed)

    def _stage_final_constrained(self):
        """Exact step-5 replay of only the leakage-screened physical tuple."""
        return self._stage_final_current_tuple(
            "final exact leakage-screened step-5 replay",
            "leakage_constrained", "final_safe")

    def _stage_final_feedback(self):
        """Exact replay after a fresh active-reset threshold/loop validation."""
        return self._stage_final_current_tuple(
            "final exact feedback-reset step-5 replay",
            "feedback_validated", "final_feedback")

    def _safety_screened_control_rows(self):
        """Control tuples which actually passed the active safety screen."""
        leakage = self.data.get("leakage", {})
        rows = []
        for attempt in leakage.get("attempts", []) if isinstance(leakage, dict) else []:
            if not isinstance(attempt, dict):
                continue
            for row in attempt.get("rows", []):
                if not isinstance(row, dict):
                    continue
                safe = (row.get("leakage_safe", False)
                        if self._leakage_active else
                        row.get("operational_safe", False))
                if safe:
                    rows.append(row)
        chosen = leakage.get("chosen") if isinstance(leakage, dict) else None
        if isinstance(chosen, dict):
            rows.append(chosen)
        if (self._leakage_verified_candidate_key is not None
                and _candidate_key(self.working)
                == self._leakage_verified_candidate_key):
            rows.append(dict(self.working))
        return [row for row in rows
                if all(key in row for key in self.initial)]

    def _stage_safe_latency_reference(self):
        """Replay the best screened control under the latest readout coordinates."""
        chosen = self.data.get("leakage", {}).get("chosen")
        if not isinstance(chosen, dict):
            raise RuntimeError("latency optimization has no safety-screened control")
        candidate = dict(self.working)
        working_is_verified = bool(
            self._leakage_verified_candidate_key is not None
            and _candidate_key(self.working)
            == self._leakage_verified_candidate_key)
        if not working_is_verified:
            for key in ("qubit_freq", "qubit_pi_freq", "qubit_pi_gain", "sigma",
                        "qubit_drag_beta"):
                candidate[key] = chosen[key]
        candidate["qubit_freq"] = float(candidate["qubit_pi_freq"])
        self.working = candidate
        return self._stage_final_current_tuple(
            "final exact pre-latency safety-seed replay",
            "safety_reference_unverified", "latency_reference")

    def _stage_final_current_tuple(self, label, replay_kind, log_stage):
        # Fail closed: an exception in this replay must not leave the completion flag
        # or provenance from the earlier unconstrained final comparison in force.
        self._final_replay_completed = False
        self._final_replay_kind = None
        p = self.params["final"]
        candidate = dict(self.working)
        finals = self._confirm_candidates(
            [candidate], p["shots"], p["blocks"], label,
            add_to_history=True)
        best = self._best_aggregate(finals)
        self._adopt(best, log_stage)
        self.data["final_candidates"] = finals
        self._final_replay_completed = self._confirmation_batch_complete(finals)
        self._final_replay_kind = (
            str(replay_kind) if self._final_replay_completed else None)
        self.data["final_confirmation_complete"] = bool(
            self._final_replay_completed)
        self._remember_final_replays(
            finals, replay_kind, self._final_replay_completed)
        return best

    def _remember_final_replays(self, rows, replay_kind, batch_complete):
        """Keep immutable evidence for both optimization objectives.

        Safety and timing stages are allowed to replace ``working``.  They must not
        erase a longer, higher-fidelity exact replay, nor may a later short replay be
        mislabeled as the overall optimum.  Each final batch is therefore retained
        independently and classified only from its own completion/spread evidence.
        """
        for source in rows or []:
            row = copy.deepcopy(source)
            stable = bool(
                batch_complete
                and bool(row.get("confirmation_complete", True))
                and int(row.get("confirmation_blocks", 0))
                >= int(self.params["final"]["blocks"])
                and float(row.get("block_spread", np.inf))
                <= float(self.params["final"]["max_block_spread"]))
            row.update({
                "final_replay_kind": str(replay_kind),
                "final_replay_batch_complete": bool(batch_complete),
                "final_replay_stable": stable,
            })
            self._final_replays.append(row)

    def _replay_candidate_is_stable(self, candidate):
        """Whether a final-stage aggregate is complete enough to replace an earlier one."""
        if not isinstance(candidate, dict) or not self._final_replay_completed:
            return False
        return bool(
            int(candidate.get("confirmation_blocks", 0))
            >= int(self.params["final"]["blocks"])
            and float(candidate.get("block_spread", np.inf))
            <= float(self.params["final"]["max_block_spread"]))

    @staticmethod
    def _timing_recovery_rank(candidate):
        """Held-out rank used when two fresh exact final replays compete."""
        evidence = BasicAutoTuner._latency_fidelity_evidence(candidate)
        try:
            lcb = float(evidence["fidelity_lcb_95"])
            mean = float(evidence["fidelity"])
        except (KeyError, TypeError, ValueError, OverflowError):
            lcb = mean = -np.inf
        if not np.isfinite(lcb):
            lcb = -np.inf
        if not np.isfinite(mean):
            mean = -np.inf
        return (lcb, mean)

    def _recover_timing_reference_after_failed_final(self, final):
        """Replay the fidelity reference when a late fast-tuple replay collapses.

        The latency certificate is a secondary objective; it must never turn a usable
        best-fidelity calibration into an abort merely because the independent final
        replay no longer supports the speedup.  Recovery is deliberately expensive
        only on this exceptional path: restore the fresh best-fidelity reference,
        repeat the applicable safety audit, and acquire a new exact final replay.  A
        failed recovery leaves the original final evidence intact and write-blocked.
        """
        record = self.data.get("latency_optimization", {})
        if not isinstance(final, dict) or not isinstance(record, dict):
            return final
        status = str(record.get("status", ""))
        certificate_active = bool(
            record.get("latency_certificate_valid", False)
            and (status in ("selected", "selected_control_recovery")
                 or (status.startswith("retained_reference")
                     and status != "retained_reference_timing_uncertain")))
        certified = record.get("certified_selected")
        if not certificate_active or not isinstance(certified, dict):
            return final
        original_final_stable = bool(
            self._final_replay_completed
            and int(final.get("confirmation_blocks", 0))
            >= int(self.params["final"]["blocks"])
            and float(final.get("block_spread", np.inf))
            <= float(self.params["final"]["max_block_spread"]))
        final_timing = self._latency_fidelity_evidence(final)
        certified_timing = self._latency_fidelity_evidence(certified)
        original_rank = self._timing_recovery_rank(final)
        maximum_drop = float(min(
            max(float(self.params["latency"].get(
                "max_final_fidelity_drop", 0.010)), 0.0),
            max(float(self.params["latency"].get(
                "max_fidelity_loss", 0.010)), 0.0)))
        guard = bool(
            _candidate_key(final) == _candidate_key(certified)
            and float(final_timing["fidelity"])
            >= float(self.params["latency"].get(
                "minimum_mean_fidelity", 0.90))
            and float(final_timing["fidelity_lcb_95"])
            >= float(self.params["latency"].get(
                "minimum_lcb_fidelity", 0.88))
            and float(final_timing["fidelity"])
            >= float(certified_timing["fidelity"]) - maximum_drop)
        record["late_final_guard_probe"] = {
            "passed": bool(guard),
            "candidate_key": list(_candidate_key(final)),
            "certified_candidate_key": list(_candidate_key(certified)),
            "final_timing_fidelity": float(final_timing["fidelity"]),
            "certified_timing_fidelity": float(certified_timing["fidelity"]),
            "maximum_drop": maximum_drop,
            "estimator": final_timing["estimator"],
        }
        if guard:
            return final
        reference = record.get("reference")
        if (isinstance(reference, dict)
                and _candidate_key(reference) == _candidate_key(final)
                and original_final_stable):
            # A retained-reference timing certificate has no second tuple to replay.
            # Its fresh exact replay is still valid ordinary-fidelity evidence even
            # when drift makes the original one-point timing claim stale.  Demote the
            # secondary certificate instead of turning that usable calibration into
            # an artificial abort.
            record.update({
                "status_before_reference_recovery": status,
                "status": "failed_final_timing_guard_retained_exact_final",
                "selected": copy.deepcopy(final),
                "latency_certificate_valid": False,
                "qualified_speedup": False,
                "latency_saved_us": 0.0,
                "latency_reduction_fraction": 0.0,
                "reference_recovery": {
                    "attempted": False, "passed": False, "adopted": False,
                    "original_stable": True,
                    "selected_candidate_key": list(_candidate_key(final)),
                    "original_final": copy.deepcopy(final),
                    "recovered_reference": None,
                    "original_rank": list(original_rank),
                    "recovered_rank": None,
                    "comparison_estimator": (
                        "%s_lcb_then_mean" % final_timing["estimator"]),
                    "reason": (
                        "the certified tuple already is the fidelity reference; "
                        "the fresh stable exact replay was retained under the "
                        "ordinary fidelity policy"),
                },
            })
            return final
        if not isinstance(reference, dict):
            record["reference_recovery"] = {
                "attempted": False, "passed": False, "adopted": False,
                "original_stable": bool(original_final_stable),
                "original_final": copy.deepcopy(final),
                "original_rank": list(original_rank),
                "failure": "no distinct best-fidelity reference is available",
            }
            return final

        snapshot = {
            "working": copy.deepcopy(self.working),
            "final_candidates": copy.deepcopy(
                self.data.get("final_candidates", [])),
            "final_replay_completed": self._final_replay_completed,
            "final_replay_kind": self._final_replay_kind,
            "final_confirmation_complete": self.data.get(
                "final_confirmation_complete", False),
            "leakage": copy.deepcopy(self.data.get("leakage", {})),
            "leakage_verified_key": self._leakage_verified_candidate_key,
            "leakage_ef_calibration": copy.deepcopy(
                self._leakage_ef_calibration),
            "reset_runtime": copy.deepcopy(self._reset_runtime),
            "reset": copy.deepcopy(self.data.get("reset", {})),
        }
        try:
            self.working = {key: reference[key] for key in self.initial}
            self._deactivate_feedback("late best-fidelity reference recovery")
            if self._leakage_active:
                if not self._stage_leakage_verify(allow_fallback=False):
                    raise RuntimeError(
                        "the best-fidelity reference failed fresh direct leakage "
                        "verification")
                recovered = self._stage_final_constrained()
            elif self._operational_leakage_active:
                if not self._stage_operational_leakage_verify(
                        allow_fallback=False):
                    raise RuntimeError(
                        "the best-fidelity reference failed fresh pulse-safety "
                        "verification")
                recovered = self._stage_final_constrained()
            else:
                recovered = self._stage_final_current_tuple(
                    "final exact best-fidelity timing fallback replay",
                    "unconstrained", "final_timing_reference")
            if not self._replay_candidate_is_stable(recovered):
                raise RuntimeError(
                    "the best-fidelity reference replay was incomplete or unstable")
            if self._leakage_active or self._operational_leakage_active:
                # A prior unstable constrained replay may have set this false.  The
                # fresh recovered constrained replay is now the exact write witness.
                self.data["leakage"]["final_replay_complete"] = True
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            self.working = snapshot["working"]
            self.data["final_candidates"] = snapshot["final_candidates"]
            self._final_replay_completed = snapshot["final_replay_completed"]
            self._final_replay_kind = snapshot["final_replay_kind"]
            self.data["final_confirmation_complete"] = snapshot[
                "final_confirmation_complete"]
            self.data["leakage"] = snapshot["leakage"]
            self._leakage_verified_candidate_key = snapshot[
                "leakage_verified_key"]
            self._leakage_ef_calibration = snapshot["leakage_ef_calibration"]
            self._reset_runtime = snapshot["reset_runtime"]
            self.data["reset"] = snapshot["reset"]
            record["reference_recovery"] = {
                "attempted": True, "passed": False, "adopted": False,
                "original_stable": bool(original_final_stable),
                "original_final": copy.deepcopy(final),
                "recovered_reference": None,
                "original_rank": list(original_rank),
                "recovered_rank": None,
                "failure": "%s: %s" % (type(exc).__name__, exc),
            }
            return final

        recovered_timing = self._latency_fidelity_evidence(recovered)
        recovered_rank = self._timing_recovery_rank(recovered)
        comparison_estimator = (
            "two_fold_crossfit_lcb_then_mean"
            if (final_timing["estimator"] == "two_fold_crossfit"
                and recovered_timing["estimator"] == "two_fold_crossfit") else
            "legacy_resubstitution_lcb_then_mean")
        keep_original = bool(
            original_final_stable
            and (original_rank > recovered_rank
                 or (original_rank == recovered_rank
                     and self._candidate_latency_us(final)
                     <= self._candidate_latency_us(recovered))))
        if keep_original:
            # The reference acquisition itself succeeded, but primary-fidelity
            # evidence says it is worse than the already-stable exact final.  Restore
            # every final/safety state field and keep the better tuple as an ordinary,
            # explicitly uncertified calibration.
            self.working = snapshot["working"]
            self.data["final_candidates"] = snapshot["final_candidates"]
            self._final_replay_completed = snapshot["final_replay_completed"]
            self._final_replay_kind = snapshot["final_replay_kind"]
            self.data["final_confirmation_complete"] = snapshot[
                "final_confirmation_complete"]
            self.data["leakage"] = snapshot["leakage"]
            self._leakage_verified_candidate_key = snapshot[
                "leakage_verified_key"]
            self._leakage_ef_calibration = snapshot["leakage_ef_calibration"]
            self._reset_runtime = snapshot["reset_runtime"]
            self.data["reset"] = snapshot["reset"]
            record.update({
                "status_before_reference_recovery": status,
                "status": "failed_final_timing_guard_retained_exact_final",
                "selected": copy.deepcopy(final),
                "latency_certificate_valid": False,
                "qualified_speedup": False,
                "latency_saved_us": 0.0,
                "latency_reduction_fraction": 0.0,
                "reference_recovery": {
                    "attempted": True, "passed": True, "adopted": False,
                    "original_stable": True,
                    "selected_candidate_key": list(_candidate_key(final)),
                    "original_final": copy.deepcopy(final),
                    "recovered_reference": copy.deepcopy(recovered),
                    "original_rank": list(original_rank),
                    "recovered_rank": list(recovered_rank),
                    "comparison_estimator": comparison_estimator,
                    "reason": (
                        "the recovered fidelity reference ranked below the already-"
                        "stable exact final replay"),
                },
            })
            return final

        record.update({
            "status_before_reference_recovery": status,
            "status": "failed_final_timing_guard_retained_fidelity_reference",
            "selected": copy.deepcopy(recovered),
            "latency_certificate_valid": False,
            "qualified_speedup": False,
            "latency_saved_us": 0.0,
            "latency_reduction_fraction": 0.0,
            "reference_recovery": {
                "attempted": True, "passed": True, "adopted": True,
                "original_stable": bool(original_final_stable),
                "selected_candidate_key": list(_candidate_key(recovered)),
                "original_final": copy.deepcopy(final),
                "recovered_reference": copy.deepcopy(recovered),
                "original_rank": list(original_rank),
                "recovered_rank": list(recovered_rank),
                "comparison_estimator": comparison_estimator,
                "reason": (
                    "the recovered fidelity reference outranked the failed timing "
                    "tuple" if original_final_stable else
                    "the recovered fidelity reference was the only stable exact "
                    "final replay"),
            },
        })
        return recovered

    def _current_best_for_partial_run(self):
        pool = list(self._confirmed)
        if self._archive:
            # Completed individual measurements are real evidence even when an
            # interrupt prevented their surrounding grid/confirmation from finishing.
            # They are explicitly labeled unconfirmed and can never become eligible.
            observed = max(self._archive, key=lambda row: (
                float(row.get("fidelity_lcb_95", -np.inf)),
                float(row.get("fidelity", -np.inf))))
            pool.append(self._aggregate(
                observed, [observed], "partial best direct measurement (unconfirmed)"))
        return self._best_aggregate(pool)

    def _stage_final(self):
        self._final_replay_completed = False
        self._final_replay_kind = None
        p = self.params["final"]
        ranked = sorted(
            self._qualified_transition_rows(self._confirmed),
            key=lambda row: (float(row.get("fidelity_lcb_95", -np.inf)),
                             float(row.get("fidelity", -np.inf))), reverse=True)
        raw_ranked = sorted(
            self._qualified_transition_rows(self._archive),
            key=lambda row: (float(row.get("fidelity_lcb_95", -np.inf)),
                             float(row.get("fidelity", -np.inf))), reverse=True)

        def physical_candidate(row):
            return {key: row[key] for key in self.initial}

        # A contender whose confirmation blocks all suffered transient faults is still
        # present in the raw archive.  Re-introduce the top raw measurements here; a
        # false coarse maximum is harmless because this final replay is fresh and held
        # out, while omitting it could permanently lose the correct Rabi basin.
        candidates = [physical_candidate(row)
                      for row in ranked[:int(p["top_candidates"])]]
        candidates.extend(
            dict(entry["candidate"])
            for entry in self._unconfirmed_contenders
            if isinstance(entry.get("candidate"), dict)
            and self._candidate_in_qualified_transition(entry["candidate"]))
        candidates.extend(physical_candidate(row)
                          for row in raw_ranked[:int(p["top_candidates"])])
        if self._candidate_in_qualified_transition(self.working):
            candidates.append(dict(self.working))
        if self._candidate_in_qualified_transition(self.initial):
            candidates.append(dict(self.initial))
        candidates = _unique_candidates(candidates)
        if not candidates:
            raise RuntimeError("no measured candidate is available for final replay")
        finals = self._confirm_candidates(
            candidates, p["shots"], p["blocks"], "final exact step-5 replay",
            add_to_history=True)
        # All final records have identical shots and block count, so comparing their
        # lower confidence bounds is fair and resistant to a one-block fluctuation.
        # Protect the final fine-frequency/AAE tuple when its one-pulse score is
        # statistically noninferior: a one-pulse histogram is insensitive to the small
        # coherent errors that those amplified sequences were designed to expose.
        selection_finals = list(finals)
        if self._leakage_active:
            threshold = float(self.params["leakage"]["max_third_blob_excess"])
            safe_finals = [row for row in finals
                           if float(row.get(
                               "third_blob_excess_ucb", np.inf)) <= threshold]
            if safe_finals:
                selection_finals = safe_finals
        direct_best = self._best_aggregate(selection_finals)
        # The latency stage owns the one declared fidelity tradeoff.  Starting it
        # from a merely noninferior control seed would silently spend an additional
        # margin before the timing comparison even begins.
        best = (direct_best if self.params["latency"].get("enabled", True)
                else self._noninferior_seed(
                    selection_finals, self.working, direct_best, margin=0.003))
        self._adopt(best, "final")
        self.data["final_candidates"] = finals
        self._final_replay_completed = self._confirmation_batch_complete(finals)
        self._final_replay_kind = (
            "unconstrained" if self._final_replay_completed else None)
        self.data["final_confirmation_complete"] = bool(
            self._final_replay_completed)
        self._remember_final_replays(
            finals, "unconstrained", self._final_replay_completed)
        return best

    def _estimate_default_measurement_repetitions(self):
        """Conservative workload estimate used only for the upfront operator ETA."""
        p = self.params
        total = 0
        total += 2 * int(p["baseline"]["shots"]) * int(p["baseline"]["blocks"])
        if p["resonator"].get("enabled", True):
            resonator = p["resonator"]
            coarse_points = sum(
                axis.size for axis in self._frequency_discovery_plan(
                    self.initial["read_pulse_freq"], resonator,
                    adaptive=True)["axes"])
            # The safe bootstrap and a distinct input readout can both be required
            # when the first gain fails its fresh confirmation.
            total += 2 * int(resonator["shots"]) * int(coarse_points)
            total += (2 * max(int(resonator.get("max_candidates", 8)), 1)
                      * int(resonator.get(
                          "confirmation_shots", resonator["shots"]))
                      * int(resonator.get("confirmation_points", 81)))
        if p["spectroscopy"].get("enabled", True):
            spectroscopy = p["spectroscopy"]
            coarse_points = self._frequency_discovery_plan(
                self.initial["qubit_pi_freq"], spectroscopy,
                adaptive=False)["axes"][-1].size
            # Primary grid plus the half-step-staggered grid.
            coarse_points = 2 * int(coarse_points) - 1
            total += int(spectroscopy["shots"]) * int(coarse_points)
            candidate_count = max(
                int(spectroscopy.get("coarse_candidates", 8)),
                int(spectroscopy.get("max_candidates", 8)), 1)
            total += (2 * candidate_count
                      * int(spectroscopy.get("confirmation_points", 41))
                      * int(spectroscopy.get(
                          "confirmation_shots", spectroscopy["shots"])))
        if p["iq_rabi"].get("enabled", True):
            basins = max(int(p["spectroscopy"].get("max_candidates", 3)), 1)
            total += int(p["iq_rabi"]["shots"]) * (
                basins * int(p["iq_rabi"]["freq_points_per_candidate"])
                * int(p["iq_rabi"]["gain_points"])
                + int(p["iq_rabi"]["fine_gain_points"]))
        r = p["rough_single_shot"]
        rabi_capacity = max(
            int(p["iq_rabi"].get("shortlist", 4)),
            1 + int(p["spectroscopy"].get("max_candidates", 3)))
        total += (2 * rabi_capacity * int(r["freq_points"])
                  * int(r["gain_points"]) * int(r["coarse_shots"]))
        total += (2 * int(r["shots"]) * int(r["blocks"])
                  * (rabi_capacity + 2))
        for _ in range(2):
            f = p["fine_frequency"]
            if f.get("enabled", True):
                total += 2 * int(f["calibration_shots"])
                total += int(f["points"]) * int(f["shots"])
                total += 4 * int(f["confirm_shots"]) * int(f["confirm_blocks"])
        parity = p["parity_chevron"]
        if parity.get("enabled", True):
            total += 2 * max(int(parity["shots"]), 300)
            total += (len(parity["pulse_counts"]) * int(parity["freq_points"])
                      * int(parity["gain_points"]) * int(parity["shots"]))
            total += 4 * int(parity["confirm_shots"]) * int(parity["confirm_blocks"])
        readout = p["readout"]
        if readout.get("enabled", True):
            total += (2 * int(readout["freq_points"]) * int(readout["gain_points"])
                      * int(readout["shots"]))
            total += (2 * (int(readout["shortlist"]) + 1)
                      * int(readout["confirm_shots"]) * int(readout["confirm_blocks"]))
        qubit = p["qubit"]
        joint = p["joint_search"]
        if joint.get("enabled", True):
            joint_lengths = len(set(
                float(value) for value in joint["read_lengths_us"]
                if np.isfinite(float(value)) and float(value) > 0.0))
            joint_sigmas = len(set(
                float(value) for value in joint["sigma_values_us"]
                if np.isfinite(float(value)) and float(value) > 0.0))
            strata = max(joint_lengths * joint_sigmas, 1)
            gain_passes = min(
                max(int(joint.get("minimum_duration_coverage_passes", 1)), 1),
                max(int(joint["read_gain_points"]), 1))
            gain_points = max(
                int(joint["qubit_gain_points_including_ground"]), 5)
            total += (strata * gain_passes * gain_points
                      * int(joint["coarse_shots"]))
            total += (2 * (int(joint["medium_max_candidates"]) + 1)
                      * int(joint["medium_shots"]) * int(joint["medium_blocks"]))
            total += (2 * int(joint["trust_proposals"])
                      * int(joint["trust_shots"]) * int(joint["trust_blocks"]))
            closure_rounds = max(int(joint.get("closure_iterations", 2)), 0)
            total += (closure_rounds * 2
                      * (max(int(joint["trust_proposals"]) // 2, 8) + 1)
                      * int(joint["trust_shots"]) * int(joint["trust_blocks"]))
        amplified = p["amplified_error"]
        if amplified.get("enabled", True):
            total += 2 * int(amplified["calibration_shots"])
            total += (len(amplified["pulse_counts"])
                      * int(amplified["freq_points"])
                      * int(amplified["gain_points"]) * int(amplified["shots"]))
            total += 4 * int(amplified["confirm_shots"]) * int(amplified["confirm_blocks"])
        if self._duration_portfolio_active:
            portfolio = p["duration_portfolio"]
            length_count = len(set(float(value) for value in portfolio.get(
                "read_lengths_us", [])
                if np.isfinite(float(value)) and float(value) > 0.0))
            candidate_count = max(
                int(portfolio["native_seeds_per_length"])
                + int(portfolio["readout_seeds_per_length"])
                * int(portfolio["control_seed_count"])
                + int(portfolio["local_proposals_per_length"]), 1)
            total += (2 * length_count * candidate_count
                      * int(portfolio["refine_shots"])
                      * int(portfolio["refine_blocks"]))
            if (bool(portfolio.get("pulse_family_aae_enabled", True))
                    and amplified.get("enabled", True)):
                family_count = len(portfolio.get(
                    "constant_area_sigma_factors", (0.5, 2.0)))
                aae_point = (
                    2 * int(amplified["calibration_shots"])
                    + len(amplified["pulse_counts"])
                    * int(amplified["freq_points"])
                    * int(amplified["gain_points"])
                    * int(amplified["shots"])
                    + 4 * int(amplified["confirm_shots"])
                    * int(amplified["confirm_blocks"]))
                total += family_count * aae_point
                total += (2 * (family_count + 1)
                          * int(amplified["confirm_shots"])
                          * int(amplified["confirm_blocks"]))
            if bool(portfolio.get("deterministic_gain_refinement", True)):
                gain_candidates = (
                    int(portfolio["gain_axis_read_points"])
                    + int(portfolio["gain_axis_qubit_points"]) - 1
                    + len(portfolio.get(
                        "constant_area_sigma_factors", (0.5, 2.0)))
                    * int(portfolio["constant_area_qubit_points"]))
                zoom_candidates = (
                    int(portfolio["gain_zoom_read_points"])
                    * int(portfolio["gain_zoom_qubit_points"])
                    * max(int(portfolio.get("gain_zoom_max_rounds", 3)), 1))
                total += (2 * length_count * gain_candidates
                          * int(portfolio["gain_refine_shots"])
                          * int(portfolio["gain_refine_blocks"]))
                total += (2 * length_count * zoom_candidates
                          * int(portfolio["gain_zoom_shots"])
                          * int(portfolio["gain_zoom_blocks"]))
            # Several exact pulse families are screened so the optional balanced
            # recommendation has measured leakage evidence.  The fidelity winner is
            # still selected before, and independently of, these acquisitions.
            screen_count = max(int(portfolio.get(
                "balanced_screen_candidates_per_length", 3)), 1)
            if self._leakage_active:
                leak = p["leakage"]
                calibration_point = (
                    2 * (int(leak["ef_points"])
                         + int(leak["ef_narrow_points"]))
                    * int(leak["ef_spec_shots"])
                    + (int(leak["reference_gain_points"]) + 3)
                    * int(leak["reference_rabi_shots"])
                    + 3 * (int(leak["ef_gain_points"]) + 3)
                    * int(leak["ef_rabi_shots"]))
                screen_point = (
                    4 * 6 * int(math.ceil(
                        float(portfolio["screen_reference_shots"]) / 4.0))
                    + 2 * int(portfolio["screen_reference_shots"])
                    + 8 * len(leak["depths"]) * len(leak["gap_phases"])
                    * int(math.ceil(
                        float(portfolio["screen_shots"]) / 4.0)))
                total += (length_count * screen_count
                          * (calibration_point + screen_point))
            else:
                leak = p["leakage"]
                drift_attempts = 1 + max(int(portfolio.get(
                    "screen_drift_retries", 2)), 0)
                screen_point = (
                    4 * int(portfolio["screen_reference_shots"])
                    + (len(leak["operational_depths"])
                       * int(portfolio["screen_shots"])
                       if bool(leak.get(
                           "operational_repeated_return_enabled", False)) else 0))
                total += (length_count * screen_count * screen_point
                          * drift_attempts)
            confirm_count = min(
                candidate_count + (gain_candidates + zoom_candidates
                                   if bool(portfolio.get(
                                       "deterministic_gain_refinement", True))
                                   else 0),
                max(int(portfolio.get(
                    "confirm_candidates_per_length", 5)),
                    int(portfolio.get(
                        "historical_champions_per_length", 1))
                    + int(portfolio.get(
                        "pulse_family_champions_per_length", 3)) + 1, 1))
            total += (2 * length_count * confirm_count
                      * int(portfolio["confirm_shots"])
                      * int(portfolio["confirm_blocks"]))
        elif self._leakage_active:
            leak = p["leakage"]
            # Nominal constrained search: independently calibrate g-e/e-f and run a
            # complete initial beta map for every retained duration.  Boundary span
            # extensions and recovery after transient backend faults remain extra.
            waveform_count = max(int(leak["max_candidate_waveforms"]), 1)
            calibration_point = (
                2 * (int(leak["ef_points"]) + int(leak["ef_narrow_points"]))
                * int(leak["ef_spec_shots"])
                + (int(leak["reference_gain_points"]) + 3)
                * int(leak["reference_rabi_shots"])
                + 3 * (int(leak["ef_gain_points"]) + 3)
                * int(leak["ef_rabi_shots"]))
            per_point = (4 * 6 * int(math.ceil(
                float(leak["reference_shots"]) / 4.0))
                         + 2 * int(leak["reference_shots"])
                         + 8 * len(leak["depths"]) * len(leak["gap_phases"])
                         * int(math.ceil(float(leak["shots"]) / 4.0)))
            beta_points = max(int(leak["beta_points"]), 5) + 1
            total += waveform_count * (
                calibration_point + beta_points * per_point)
            total += (2 * int(leak["selection_shortlist"])
                      * int(leak["selection_fidelity_shots"])
                      * int(leak["selection_fidelity_blocks"]))
            verify_point = (4 * 6 * int(math.ceil(
                float(leak["verify_shots"]) / 4.0))
                            + 2 * int(leak["verify_shots"])
                            + 8 * len(leak["depths"]) * len(leak["gap_phases"])
                            * int(math.ceil(float(leak["verify_shots"]) / 4.0)))
            total += int(leak["verify_blocks"]) * verify_point
            # Final direct-P(f) verification recalibrates g-e/e-f for the exact
            # latency-selected waveform; reserve a second calibration for the safe-
            # seed fallback path.
            total += 2 * calibration_point
            # Re-close coordinates after DRAG/duration selection, then replay the
            # exact safe tuple.  These are real planned stages, not optimistic extras.
            total += (2 * int(qubit["local_freq_points"])
                      * int(qubit["local_gain_points"]) * int(qubit["shots"]))
            total += (2 * (int(qubit["shortlist"]) + 1)
                      * int(qubit["confirm_shots"]) * int(qubit["confirm_blocks"]))
            total += 2 * int(f["calibration_shots"])
            total += int(f["points"]) * int(f["shots"])
            total += 4 * int(f["confirm_shots"]) * int(f["confirm_blocks"])
            total += 2 * int(amplified["calibration_shots"])
            total += (len(amplified["pulse_counts"])
                      * int(amplified["freq_points"])
                      * int(amplified["gain_points"])
                      * int(amplified["shots"]))
            total += (4 * int(amplified["confirm_shots"])
                      * int(amplified["confirm_blocks"]))
            total += (2 * int(readout["local_freq_points"])
                      * int(readout["local_gain_points"])
                      * int(readout["shots"]))
            total += (2 * (int(readout["shortlist"]) + 1)
                      * int(readout["confirm_shots"])
                      * int(readout["confirm_blocks"]))
        elif self._operational_leakage_active:
            leak = p["leakage"]
            waveform_count = max(int(
                leak["operational_max_candidate_waveforms"]), 1)
            beta_points = (max(int(leak["operational_beta_points"]), 5) + 1
                           if bool(leak.get("operational_tune_drag", False)) else 1)
            screen_point = (
                4 * int(leak["operational_reference_shots"])
                + (len(leak["operational_depths"])
                   * int(leak["operational_shots"])
                   if bool(leak.get(
                       "operational_repeated_return_enabled", False)) else 0))
            # A discriminator-drift retry repeats the whole before/after bracket.
            # Budget the configured worst case so this ETA does not hide the new
            # robustness work behind an optimistic one-attempt estimate.
            drift_attempts = 1 + max(int(leak.get(
                "operational_drift_retries", 2)), 0)
            total += (waveform_count * beta_points * screen_point
                      * drift_attempts)
            total += (2 * int(leak["operational_selection_shortlist"])
                      * int(leak["operational_selection_shots"])
                      * int(leak["operational_selection_blocks"]))
            verify_point = (
                4 * int(leak["operational_verify_shots"])
                + (len(leak["operational_depths"])
                   * int(leak["operational_verify_shots"])
                   if bool(leak.get(
                       "operational_repeated_return_enabled", False)) else 0))
            total += int(leak["operational_verify_blocks"]) * verify_point
            # Same local closure used by strict mode after control-waveform selection.
            total += (2 * int(qubit["local_freq_points"])
                      * int(qubit["local_gain_points"]) * int(qubit["shots"]))
            total += (2 * (int(qubit["shortlist"]) + 1)
                      * int(qubit["confirm_shots"]) * int(qubit["confirm_blocks"]))
            total += 2 * int(f["calibration_shots"])
            total += int(f["points"]) * int(f["shots"])
            total += 4 * int(f["confirm_shots"]) * int(f["confirm_blocks"])
            total += 2 * int(amplified["calibration_shots"])
            total += (len(amplified["pulse_counts"])
                      * int(amplified["freq_points"])
                      * int(amplified["gain_points"])
                      * int(amplified["shots"]))
            total += (4 * int(amplified["confirm_shots"])
                      * int(amplified["confirm_blocks"]))
            total += (2 * int(readout["local_freq_points"])
                      * int(readout["local_gain_points"]) * int(readout["shots"]))
            total += (2 * (int(readout["shortlist"]) + 1)
                      * int(readout["confirm_shots"])
                      * int(readout["confirm_blocks"]))
        final = p["final"]
        # Normal final replay: top confirmed + top raw + working + input.  Explicit
        # recovery-queue candidates are added only after actual confirmation faults.
        total += (2 * (2 * int(final["top_candidates"]) + 2)
                  * int(final["shots"]) * int(final["blocks"]))
        latency = p["latency"]
        if latency.get("enabled", True) and not self._duration_portfolio_active:
            joint_points = (int(latency["max_readout_candidates"])
                            * int(latency["max_control_candidates"]))
            total += (2 * joint_points * int(latency["coarse_shots"])
                      * int(latency.get("max_point_attempts", 2)))
            total += (2 * (int(latency["shortlist"]) + 1)
                      * int(latency["confirm_shots"])
                      * int(latency["confirm_blocks"])
                      * (int(latency.get("max_confirmation_attempts", 2))
                         + int(latency.get(
                             "adaptive_confirmation_rounds", 0))))
        if ((self._leakage_active or self._operational_leakage_active)
                and not self._duration_portfolio_active):
            total += 2 * int(final["shots"]) * int(final["blocks"])
        control_verify = p["control_verify"]
        if control_verify.get("enabled", True):
            if self._duration_portfolio_active:
                portfolio = p["duration_portfolio"]
                # Audit the pure-fidelity winner and, when different, a small number
                # of noninferior balanced alternatives.  This remains report-only.
                control_audits = (
                    len(portfolio.get("read_lengths_us", []))
                    * max(int(portfolio.get(
                        "balanced_control_attempts", 2)), 1))
            else:
                control_audits = (1 + int(p["latency"].get("shortlist", 0))
                                  if p["latency"].get("enabled", True) else 1)
            total += control_audits * int(control_verify["blocks"]) * (
                4 * int(control_verify["calibration_shots"])
                + len(control_verify["pulse_counts"])
                * int(control_verify["shots"]))
        return int(total)

    def _complete_acquire(self, final, plotDisp=False):
        """Finalize and persist either a full run or an intentional early stop."""
        if final is None:
            final = self._current_best_for_partial_run()
        self._finalize(final)
        try:
            self._checkpoint()
        except Exception as exc:
            self._log("save", "WARN", "pickle save failed: %s" % exc)
        try:
            self.save_plot(plotDisp=plotDisp)
        except Exception as exc:
            self._log("plot", "WARN", "summary plot failed: %s" % exc)
        return {"config": copy.deepcopy(self.input_cfg), "data": self.data}

    # --------------------------------------------------------------- orchestration
    def acquire(self, progress=False, debug=False, plotDisp=False):
        del progress, debug
        self._run_started_monotonic = time.monotonic()
        # Direct unit users may call individual analysis/finalization helpers, but a
        # production acquire must never authorize writes after critical discovery
        # failed and later local grids merely optimized shot noise.
        self._discovery_guard_active = True
        self._final_control_verified_key = None
        self._preflight()
        repetitions = self._estimate_default_measurement_repetitions()
        relax_delay_us = float(self.input_cfg.get("relax_delay", np.nan))
        passive_hours = float(repetitions * relax_delay_us / 1e6 / 3600.0)
        self.data["planned_repetitions"] = int(repetitions)
        self.data["planned_passive_idle_hours"] = passive_hours
        if not self._detailed_console():
            print("  Planned workload: about %.1fM single-shot repetitions."
                  % (repetitions / 1e6))
            print("  Repetition delay alone is about %.1f h at the configured "
                  "%.0f us passive relaxation; qualified active reset removes "
                  "most of it." % (passive_hours, relax_delay_us))
            if self._duration_portfolio_active:
                lengths = self.params["duration_portfolio"].get(
                    "read_lengths_us", [])
                print("  Readout durations requested: %d (%s)."
                      % (len(lengths),
                         self.params["duration_portfolio"].get(
                             "readout_length_mode", "custom")))
        if self._detailed_console():
            print("=" * 78)
            print("BASIC AUTO TUNER  %s" % self.path)
            print("  revision %s; exact TLS step-5 objective with direct P(f) constraint"
                  % BASIC_AUTOTUNER_REVISION)
            print("  start: read %.6f/%d/%.1fus | pi %.6f @ %d / %.1fns | DRAG %+.5f"
                  % (self.initial["read_pulse_freq"], self.initial["read_pulse_gain"],
                     self.initial["read_length"], self.initial["qubit_pi_freq"],
                     self.initial["qubit_pi_gain"], 4000.0 * self.initial["sigma"],
                     self.initial["qubit_drag_beta"]))
            if self._leakage_active:
                leakage = self.params["leakage"]
                print("  leakage limits: P(f) UCB one/amplified %.3f/%.3f; "
                      "third-cloud excess %.3f"
                      % (leakage["max_single_p2"], leakage["max_amplified_p2"],
                         leakage["max_third_blob_excess"]))
            print("  worst-case all-passive delay: %.1f min over about %.0fk repetitions"
                  % (passive_hours * 60.0, repetitions / 1000.0))
            print("=" * 78)

        try:
            self._run_stage("baseline", self._stage_baseline)
            self._run_stage("resonator", self._stage_resonator)
            self._run_stage("spectroscopy", self._stage_spectroscopy)
            self._run_stage("iq_rabi", self._stage_iq_rabi)
            # Break the control/readout chicken-and-egg loop: coherent averaged Rabi is
            # a provisional preparation, then a broad direct-SS readout search makes the
            # later exact comparison among all Rabi basins meaningful.  This bootstrap
            # map is deliberately not write evidence; readout is re-optimized after the
            # direct/amplified control choice.
            bootstrap = self._run_stage(
                "readout_grid", lambda: self._stage_readout_grid(
                    "readout_grid", local=False, record_evidence=False))
            if isinstance(bootstrap, dict):
                # Preserve the exact passive-preparation tuple and its held-out
                # evidence.  It is crossed into every later duration even if a
                # failed feedback profile makes a subsequent branch comparison
                # temporarily look like coin flips.
                self._bootstrap_control_candidate = copy.deepcopy(bootstrap)
                self.data["bootstrap_control_candidate"] = copy.deepcopy(
                    bootstrap)
            self._run_stage("reset_after_bootstrap", lambda:
                            self._try_activate_feedback("bootstrap readout"))
            self._run_stage("rough_ss", self._stage_rough_single_shot)
            self._run_stage("parity_chevron", self._stage_parity_chevron)
            gate = self._run_stage(
                "pre_expensive_gate", self._stage_pre_expensive_gate)
            if gate is None:
                self.data["expensive_search_skipped"] = True
                self.data["expensive_search_skip_reason"] = (
                    "resonator/qubit transition qualification did not pass")
                self._log(
                    "run", "WARN",
                    "stopping before joint optimization because the resonator and "
                    "qubit transition were not both independently qualified")
                return self._complete_acquire(
                    self._current_best_for_partial_run(), plotDisp=plotDisp)
            # The bootstrap probe may legitimately fail when the preliminary pulse is
            # weak.  Retry with the now-confirmed coherent pulse before the expensive
            # joint map; failure still falls back to passive relaxation and never
            # aborts or narrows the search.
            self._run_stage("reset_before_joint", lambda:
                            self._try_activate_feedback("rough coherent pulse"))
            self._run_stage("joint_search", self._stage_joint_search)
            self._run_stage("multi_aae", self._stage_multi_candidate_aae)
            for iteration in range(1, max(int(self.params["joint_search"].get(
                    "closure_iterations", 2)), 0) + 1):
                self._run_stage(
                    "joint_closure_%d" % iteration,
                    lambda iteration=iteration: self._stage_joint_closure(iteration))
                # A coupled one-pulse refinement can expose a small coherent residual.
                # Re-close it before the next/final comparison without reopening a
                # one-way coordinate-descent chain.
                if (iteration < int(self.params["joint_search"].get(
                        "closure_iterations", 2))
                        and self._joint_budget_allows(reserve_final=True)):
                    self._run_stage(
                        "multi_aae_closure_%d" % iteration,
                        self._stage_multi_candidate_aae)
            # The ordinary final map first identifies the best empirical waveforms.
            # The default basic path then compares fixed-waveform duration/power
            # candidates for reproducible third-cloud growth.  Optional strict mode
            # replaces that screen with direct shelving P(f).  Either path re-closes
            # local coordinates and independently verifies the exact tuple before the
            # only replay allowed to authorize a write.
            # Candidate-rich final comparison can now use its cached fixed-gain reset
            # profile per frequency/integration pair.  Scoring gain is independent and
            # therefore no longer forces an all-passive multi-readout replay.
            final = self._run_stage("final", self._stage_final)
            ordinary_final = copy.deepcopy(final) if final is not None else None
            ordinary_replay_completed = bool(self._final_replay_completed)
            ordinary_replay_kind = self._final_replay_kind
            ordinary_final_candidates = copy.deepcopy(
                self.data.get("final_candidates", []))

            def restore_ordinary_final(reason):
                if ordinary_final is None:
                    return None
                attempted = self.data.get("final_candidates")
                if attempted is not None:
                    self.data["rejected_late_final_candidates"] = copy.deepcopy(
                        attempted)
                self.data["final_candidates"] = copy.deepcopy(
                    ordinary_final_candidates)
                self._final_replay_completed = ordinary_replay_completed
                self._final_replay_kind = ordinary_replay_kind
                self.data["final_confirmation_complete"] = bool(
                    ordinary_replay_completed)
                self.working = {
                    key: ordinary_final[key] for key in self.initial}
                self._log(
                    "final", "WARN",
                    "%s; retaining the earlier stable unconstrained fidelity replay"
                    % reason)
                return copy.deepcopy(ordinary_final)

            if final is not None:
                # Preserve the pure-fidelity answer before any independent safety
                # or latency selection.  A shorter/screened pulse may later become the
                # writable result, but the operator must always see the tradeoff.
                self.data["best_fidelity_replay"] = copy.deepcopy(final)
                self.data["best_fidelity_replay_complete"] = bool(
                    self._final_replay_completed)
                # With a safety constraint, the joint timing decision must wait until
                # the feasible control durations are known.  Otherwise an unsafe fast
                # pulse can drag readout length short and hide the true shortest safe
                # combination.  Unconstrained runs can optimize immediately.
                if (not self._duration_portfolio_active
                        and not (self._leakage_active
                                 or self._operational_leakage_active)):
                    latency_result = self._run_stage(
                        "latency", lambda: self._stage_latency_selection(
                            final, reference_kind="unconstrained"))
                    if latency_result is not None:
                        screened = self._run_stage(
                            "latency_control_screen",
                            self._stage_latency_control_screen)
                        final = screened if screened is not None else latency_result
                    elif self.params["latency"].get("enabled", True):
                        self.data["latency_optimization"].update({
                            "status": "failed_retained_fidelity_reference",
                            "selected": copy.deepcopy(final),
                        })
            reset_ready = self._run_stage(
                "reset_before_verification", lambda:
                self._try_activate_feedback("best-fidelity winner"))
            if self._duration_portfolio_active:
                portfolio_best = self._run_stage(
                    "duration_portfolio", self._stage_duration_portfolio)
                if portfolio_best is not None:
                    final = portfolio_best
            elif self._leakage_active:
                # Direct qutrit programs may load candidate, g-e reference, and e-f
                # waveforms together.  Passive reset avoids adding a frozen reset
                # waveform to that memory footprint and also compares durations fairly.
                self._deactivate_feedback("direct leakage waveform comparison")
                leakage_result = self._run_stage(
                    "leakage", self._stage_leakage)
                leakage_verified = False
                if leakage_result is None:
                    leakage_stage = self._stages[-1]
                    self.data["leakage"].update({
                        "optimized": False, "verified": False,
                        "failure": (leakage_stage.get("error")
                                    or "direct leakage stage produced no result"),
                    })
                else:
                    self._run_stage(
                        "frequency_post_leakage", lambda: self._stage_fine_frequency(
                            "frequency_post_leakage"))
                    self._run_stage(
                        "aae_post_leakage", self._stage_amplified_error)
                    self._run_stage(
                        "joint_post_leakage", lambda: self._stage_joint_closure(
                            int(self.params["joint_search"].get(
                                "closure_iterations", 2)) + 1))
                    if self.params["latency"].get("enabled", True):
                        # Post-screen frequency/gain/AAE closure is useful only after
                        # the refined exact tuple proves safety.  This first audit also
                        # refreshes the matching e-f shelving calibration in strict
                        # mode.  A second audit below certifies the eventual joint
                        # timing winner.
                        self._deactivate_feedback(
                            "pre-latency direct leakage verification")
                        preverified = bool(self._run_stage(
                            "leakage_verify_before_latency",
                            self._stage_leakage_verify))
                        if preverified:
                            safe_controls = self._safety_screened_control_rows()
                            safe_reference = self._run_stage(
                                "latency_reference",
                                self._stage_safe_latency_reference)
                            if safe_reference is not None:
                                latency_result = self._run_stage(
                                    "latency", lambda: self._stage_latency_selection(
                                        safe_reference, control_rows=safe_controls,
                                        reference_kind="direct_leakage_verified"))
                                if latency_result is not None:
                                    screened = self._run_stage(
                                        "latency_control_screen",
                                        lambda: self._stage_latency_control_screen(
                                            verify_safety=True))
                                    final = (screened if screened is not None
                                             else latency_result)
                                else:
                                    self.data["latency_optimization"].update({
                                        "status": "failed_retained_safe_reference",
                                        "selected": copy.deepcopy(safe_reference),
                                    })
                        else:
                            self.data["latency_optimization"].update({
                                "status": "not_run_no_verified_safe_control",
                            })
                    self._deactivate_feedback("direct leakage verification")
                    leakage_verified = bool(self._run_stage(
                        "leakage_verify", self._stage_leakage_verify))
                # A leakage-constrained replay is meaningful only for the exact tuple
                # that passed the independent qutrit audit.  Previously this replay
                # ran even when all e-f calibrations had failed, allowing a late noisy
                # measurement to overwrite a much better validated unconstrained
                # result.  Keep that best real measurement for reporting while still
                # failing closed on every config write.
                if leakage_verified:
                    self._run_stage(
                        "reset_after_post_readout", lambda:
                        self._try_activate_feedback(
                            "latency-selected leakage-safe tuple"))
                    constrained = self._run_stage(
                        "final_safe", self._stage_final_constrained)
                    if self._replay_candidate_is_stable(constrained):
                        final = constrained
                        self.data["leakage"]["final_replay_complete"] = True
                    else:
                        failure = (
                            "the direct leakage audit passed, but its final exact "
                            "step-5 replay was incomplete or unstable")
                        self.data["leakage"].update({
                            "final_replay_complete": False,
                            "failure": failure,
                        })
                        final = restore_ordinary_final(failure)
            elif self._operational_leakage_active:
                operational_result = self._run_stage(
                    "operational_leakage", self._stage_operational_leakage)
                operational_verified = False
                if operational_result is None:
                    operational_stage = self._stages[-1]
                    self.data["leakage"].update({
                        "optimized": False, "verified": False,
                        "failure": (operational_stage.get("error")
                                    or "operational screen produced no result"),
                    })
                else:
                    self._run_stage(
                        "frequency_post_leakage", lambda: self._stage_fine_frequency(
                            "frequency_post_leakage"))
                    self._run_stage(
                        "aae_post_leakage", self._stage_amplified_error)
                    self._run_stage(
                        "joint_post_leakage", lambda: self._stage_joint_closure(
                            int(self.params["joint_search"].get(
                                "closure_iterations", 2)) + 1))
                    if self.params["latency"].get("enabled", True):
                        self._deactivate_feedback(
                            "pre-latency operational safety verification")
                        preverified = bool(self._run_stage(
                            "operational_leakage_verify_before_latency",
                            self._stage_operational_leakage_verify))
                        if preverified:
                            safe_controls = self._safety_screened_control_rows()
                            safe_reference = self._run_stage(
                                "latency_reference",
                                self._stage_safe_latency_reference)
                            if safe_reference is not None:
                                latency_result = self._run_stage(
                                    "latency", lambda: self._stage_latency_selection(
                                        safe_reference, control_rows=safe_controls,
                                        reference_kind="operationally_verified"))
                                if latency_result is not None:
                                    screened = self._run_stage(
                                        "latency_control_screen",
                                        lambda: self._stage_latency_control_screen(
                                            verify_safety=True))
                                    final = (screened if screened is not None
                                             else latency_result)
                                else:
                                    self.data["latency_optimization"].update({
                                        "status": "failed_retained_safe_reference",
                                        "selected": copy.deepcopy(safe_reference),
                                    })
                        else:
                            self.data["latency_optimization"].update({
                                "status": "not_run_no_verified_safe_control",
                            })
                    self._deactivate_feedback("operational safety verification")
                    operational_verified = bool(self._run_stage(
                        "operational_leakage_verify",
                        self._stage_operational_leakage_verify))
                if operational_verified:
                    self._run_stage(
                        "reset_after_post_readout", lambda:
                        self._try_activate_feedback(
                            "latency-selected operationally safe tuple"))
                    constrained = self._run_stage(
                        "final_safe", self._stage_final_constrained)
                    if self._replay_candidate_is_stable(constrained):
                        final = constrained
                        self.data["leakage"]["final_replay_complete"] = True
                    else:
                        failure = (
                            "the pulse-safety screen passed, but its final exact "
                            "step-5 replay was incomplete or unstable")
                        self.data["leakage"].update({
                            "final_replay_complete": False,
                            "failure": failure,
                        })
                        final = restore_ordinary_final(failure)
            elif reset_ready:
                feedback_final = self._run_stage(
                    "final_feedback", self._stage_final_feedback)
                if self._replay_candidate_is_stable(feedback_final):
                    final = feedback_final
                else:
                    final = restore_ordinary_final(
                        "the final active-reset replay was incomplete or unstable")
            if final is not None and not self._duration_portfolio_active:
                recovered = self._run_stage(
                    "timing_reference_recovery",
                    lambda: self._recover_timing_reference_after_failed_final(
                        final))
                if recovered is not None:
                    final = recovered
                self._run_stage(
                    "final_control_verify",
                    lambda: self._stage_final_control_verify(final))
        except KeyboardInterrupt:
            self._interrupted = True
            final = None
            self._log("run", "WARN", "operator interrupted; retaining completed measurements")

        return self._complete_acquire(final, plotDisp=plotDisp)

    def _finalize_duration_portfolio(self, final):
        """Finalize a report-only portfolio without manufacturing a write winner."""
        portfolio = self.data.get("duration_portfolio", {})
        entries = (portfolio.get("entries", [])
                   if isinstance(portfolio, dict) else [])
        if bool(self.data.get("expensive_search_skipped", False)) and not entries:
            candidate = copy.deepcopy(final) if isinstance(final, dict) else None
            tuned = ({key: candidate[key] for key in TUNED_KEYS}
                     if isinstance(candidate, dict)
                     and all(key in candidate for key in TUNED_KEYS) else {})
            self.data.update({
                "outcome": "transition_qualification_failed",
                "success": False,
                "failure": self.data.get(
                    "expensive_search_skip_reason",
                    "resonator/qubit qualification failed before joint search"),
                "best_found": candidate,
                "best_overall_candidate": candidate,
                "best_safe_candidate": None,
                "best_fidelity_replay": candidate,
                "best_fidelity_replay_complete": False,
                "tuned": tuned, "eligible_tuned": {},
                "final_stable": False, "fidelity_replay_stable": False,
                "manual_selection_required": False,
                "automatic_config_write_allowed": False,
            })
            if isinstance(portfolio, dict):
                portfolio.update({
                    "status": "not_run_transition_unqualified",
                    "automatic_write_allowed": False,
                })
            return
        reportable = [entry for entry in entries
                      if isinstance(entry, dict)
                      and isinstance(entry.get("selected"), dict)]
        safe = [entry for entry in reportable
                if str(entry.get("status", "")).upper() == "SAFE"]
        balanced_reportable = [
            entry for entry in reportable
            if isinstance(entry.get("balanced"), dict)]
        best_overall_entry = (max(
            reportable,
            key=lambda entry: self._portfolio_rank(entry["selected"]))
            if reportable else None)
        best_safe_entry = (max(
            safe, key=lambda entry: self._portfolio_rank(entry["selected"]))
            if safe else None)
        best_balanced_entry = (max(
            balanced_reportable,
            key=lambda entry: self._portfolio_rank(entry["balanced"]))
            if balanced_reportable else None)
        # Report reference follows the same fidelity-only objective as every row.
        # Safety remains available separately as best_safe_candidate and can never
        # replace the best-fidelity tuple in report-only portfolio mode.
        selected_entry = best_overall_entry
        candidate = (copy.deepcopy(selected_entry["selected"])
                     if selected_entry is not None else
                     (copy.deepcopy(final) if isinstance(final, dict) else None))
        if candidate is None:
            self.data.update({
                "outcome": "duration_portfolio_no_measurement",
                "success": False,
                "failure": "the duration portfolio produced no reportable tuple",
                "best_found": None, "tuned": {}, "eligible_tuned": {},
                "final_stable": False, "fidelity_replay_stable": False,
                "manual_selection_required": True,
            })
            return
        for key in ("block_fidelities", "block_fidelity_ses",
                    "block_crossfit_fidelities", "block_crossfit_fidelity_ses"):
            if isinstance(candidate.get(key), np.ndarray):
                candidate[key] = candidate[key].tolist()
        candidate["gate_length_ns"] = 4000.0 * float(candidate["sigma"])
        candidate["portfolio_status"] = (
            selected_entry.get("status") if selected_entry else "INCONCLUSIVE")
        candidate["label"] = "duration portfolio report-only reference"
        tuned = {key: candidate[key] for key in TUNED_KEYS}
        requested = int(portfolio.get("requested_length_count", len(entries)) or 0)
        reportable_count = int(portfolio.get(
            "reportable_length_count", len(reportable)) or 0)
        complete = bool(requested > 0 and reportable_count == requested)
        replay_stable = bool(
            int(candidate.get("confirmation_blocks", 0))
            >= int(self.params["duration_portfolio"]["confirm_blocks"])
            and bool(candidate.get("confirmation_complete", False)))
        self.data.update({
            "best_found": candidate,
            "best_overall_candidate": copy.deepcopy(
                best_overall_entry["selected"]
                if best_overall_entry is not None else candidate),
            "best_safe_candidate": copy.deepcopy(
                best_safe_entry["selected"]
                if best_safe_entry is not None else None),
            "best_balanced_candidate": copy.deepcopy(
                best_balanced_entry["balanced"]
                if best_balanced_entry is not None else None),
            "best_fidelity_replay": copy.deepcopy(
                best_overall_entry["selected"]
                if best_overall_entry is not None else candidate),
            "best_fidelity_replay_complete": bool(best_overall_entry is not None),
            "shortest_high_fidelity_candidate": None,
            "shortest_high_fidelity_status": "replaced_by_manual_duration_portfolio",
            "tuned": tuned,
            "eligible_tuned": {},
            "manual_selection_required": True,
            "automatic_config_write_allowed": False,
            "fidelity_replay_stable": replay_stable,
            # Deliberately false: there is no operator-selected portfolio row yet.
            "final_stable": False,
            "success": complete,
            "outcome": ("duration_portfolio_complete" if complete
                        else "duration_portfolio_partial"),
            "failure": (None if complete else
                        "%d of %d requested readout durations produced a reportable "
                        "tuple" % (reportable_count, requested)),
            "leakage_required_for_write": False,
            "leakage_verified": False,
            "write_fidelity_gate": {
                "passed": False,
                "reason": "manual duration-portfolio selection is required",
                "measured_lcb": float(candidate.get(
                    "fidelity_lcb_95", np.nan)),
                "minimum_lcb": float(self.params["final"].get(
                    "minimum_write_fidelity_lcb", 0.60)),
            },
            "control_validation": {
                "required_for_write": False,
                "verified_for_write": False,
                "reason": "portfolio mode never authorizes an automatic write",
                "portfolio_control_audits": copy.deepcopy(
                    portfolio.get("control_audits", [])),
            },
            "eligibility": {
                "atomic_tuple_safe": False,
                "manual_selection_required": True,
                "automatic_write_allowed": False,
                "changed_keys": [], "write_needed": False,
                "discovery_verified": bool(
                    self._discovery_status.get("resonator", False)
                    and self._discovery_status.get("spectroscopy", False)),
                "write_fidelity_qualified": False,
                "control_verified": False,
                "leakage_required": False,
                "leakage_verified": False,
                "leakage_tuple_match": False,
                "final_replay_kind": "manual_duration_portfolio",
            },
        })
        self.data["working"] = {key: candidate[key] for key in self.initial}
        self.working = dict(self.data["working"])
        self._log(
            "result", "OK",
            "duration portfolio reports %d/%d lengths (%d SAFE); initialize.py "
            "remains untouched pending manual selection"
            % (reportable_count, requested, len(safe)))

    def _run_health(self):
        concerns = []
        failed_stages = [
            {"name": str(row.get("name")), "status": str(row.get("status")),
             "error": row.get("error")}
            for row in self._stages
            if str(row.get("status", "")) != "ok"
        ]
        for row in failed_stages:
            if row["status"] == "warning":
                concerns.append(
                    "stage '%s' did not complete: %s"
                    % (row["name"], row["error"]))

        reset = self.data.get("reset", {})
        reset = reset if isinstance(reset, dict) else {}
        reset_mode = str(reset.get("mode", "passive"))
        relax_delay = float(self.input_cfg.get("relax_delay", np.nan))
        if reset_mode != "feedback":
            concerns.append(
                "every acquisition paid the %.0f us passive relaxation delay; "
                "feedback reset was not active at the end of the run"
                % relax_delay)
        if bool(reset.get("feedback_disqualified", False)):
            concerns.append(
                "feedback reset was disqualified by the exact passive/feedback "
                "A/B and stayed off for the rest of the run")
        if not bool(self._thermalization.get("verified", False)):
            concerns.append(
                "the %.0f us passive relaxation delay was never checked against a "
                "measured T1; set qubit_t1_us so preflight can enforce the %.1fx "
                "margin, because a short delay silently corrupts every "
                "ground-state preparation"
                % (relax_delay, float(self.params["reset"].get(
                    "min_passive_relax_t1_multiple", 5.0))))

        joint = self.data.get("joint_search", {})
        joint = joint if isinstance(joint, dict) else {}
        coverage = joint.get("coverage", {})
        coverage = coverage if isinstance(coverage, dict) else {}
        joint_health = {
            "status": joint.get("status"),
            "coverage_complete": bool(coverage.get("complete", False)),
            "measured_strata": coverage.get("measured_strata"),
            "expected_strata": coverage.get("expected_strata"),
            "mandatory_duration_passes_requested": joint.get(
                "mandatory_duration_passes_requested"),
            "mandatory_duration_passes": joint.get("mandatory_duration_passes"),
            "mandatory_coverage_reduced_for_budget": bool(joint.get(
                "mandatory_coverage_reduced_for_budget", False)),
            "gain_passes_completed": joint.get("coarse_gain_passes_completed"),
            "medium_row_count": len(joint.get("medium_rows", []) or []),
            "trust_row_count": len(joint.get("trust_rows", []) or []),
            "runtime_minutes": joint.get("runtime_minutes_after_search"),
        }
        if joint.get("enabled", True) and joint.get("status") not in (
                "disabled", "not_run"):
            if not joint_health["coverage_complete"]:
                concerns.append(
                    "the joint search measured %s of %s duration strata; its "
                    "winner rests on partial coverage"
                    % (coverage.get("measured_strata"),
                       coverage.get("expected_strata")))
            if joint_health["mandatory_coverage_reduced_for_budget"]:
                concerns.append(
                    "the joint search granted %s of %s mandatory readout-power "
                    "passes to protect its reserved refinement budget"
                    % (joint_health["mandatory_duration_passes"],
                       joint_health["mandatory_duration_passes_requested"]))
            if not joint_health["medium_row_count"]:
                concerns.append(
                    "the joint search ran out of budget before its held-out "
                    "medium replay; downstream stages were seeded from coarse "
                    "shared-ground rows only")
            if not joint_health["trust_row_count"]:
                concerns.append(
                    "the joint search ran out of budget before its trust-region "
                    "refinement")

        portfolio = self.data.get("duration_portfolio", {})
        portfolio = portfolio if isinstance(portfolio, dict) else {}
        entries = portfolio.get("entries", []) if portfolio.get(
            "enabled", False) else []
        basis_counts, degraded_lengths, unconverged_lengths = {}, [], []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            selected = entry.get("selected")
            basis = (str(selected.get("portfolio_fidelity_selection_basis",
                                      "unknown"))
                     if isinstance(selected, dict) else "no_reportable_tuple")
            basis_counts[basis] = basis_counts.get(basis, 0) + 1
            search = entry.get("search", {})
            if not isinstance(search, dict):
                continue
            if bool(search.get("readout_seeded_from_proposals_only", False)):
                degraded_lengths.append(float(entry.get("read_length_us", np.nan)))
            zoom = search.get("deterministic_gain_zoom", {})
            if (isinstance(zoom, dict)
                    and not bool(zoom.get("locally_converged", False))):
                unconverged_lengths.append(
                    float(entry.get("read_length_us", np.nan)))
        portfolio_health = {
            "enabled": bool(portfolio.get("enabled", False)),
            "readout_length_mode": portfolio.get("readout_length_mode"),
            "requested_length_count": portfolio.get("requested_length_count"),
            "reportable_length_count": portfolio.get("reportable_length_count"),
            "equal_refinement_budget": portfolio.get("equal_refinement_budget"),
            "selection_basis_counts": basis_counts,
            "lengths_seeded_without_held_out_readout": degraded_lengths,
            "lengths_without_local_gain_convergence": unconverged_lengths,
            "failure_count": len(portfolio.get("failures", []) or []),
        }
        if portfolio_health["enabled"]:
            fallback = int(basis_counts.get("gain_refinement_fallback", 0))
            partial = int(basis_counts.get(
                "partial_duration_interleaved_exact_replay", 0))
            missing = int(basis_counts.get("no_reportable_tuple", 0))
            if fallback or partial:
                concerns.append(
                    "%d readout length(s) were decided without a complete "
                    "interleaved exact replay (%d partial, %d fallback)"
                    % (fallback + partial, partial, fallback))
            if missing:
                concerns.append(
                    "%d readout length(s) produced no reportable tuple" % missing)
            if degraded_lengths:
                concerns.append(
                    "%d readout length(s) had no held-out readout basin to seed "
                    "from and used coarse proposals only" % len(degraded_lengths))
            if unconverged_lengths:
                concerns.append(
                    "%d readout length(s) ended the gain zoom on an axis edge, so "
                    "their gains are not locally converged"
                    % len(unconverged_lengths))

        discovery = {
            "resonator": bool(self._discovery_status.get("resonator", False)),
            "spectroscopy": bool(
                self._discovery_status.get("spectroscopy", False)),
        }
        if not discovery["resonator"]:
            concerns.append("resonator discovery was not independently confirmed")
        if not discovery["spectroscopy"]:
            concerns.append("qubit spectroscopy was not independently confirmed")
        if self._interrupted:
            concerns.append("the operator interrupted the run")

        return {
            "degraded": bool(concerns),
            "concerns": concerns,
            "warned_stages": failed_stages,
            "reset": {
                "mode": reset_mode,
                "feedback_disqualified": bool(
                    reset.get("feedback_disqualified", False)),
                "profile_count": reset.get("profile_count"),
                "fallback_relax_delay_us": relax_delay,
                "res_phase_calibration": reset.get("res_phase_calibration"),
                "thermalization": dict(self._thermalization),
            },
            "discovery": discovery,
            "joint_search": joint_health,
            "duration_portfolio": portfolio_health,
            "runtime_minutes": self._runtime_minutes(),
            "estimated_repetitions": int(
                self.data.get("planned_repetitions", 0) or 0),
        }

    def _finalize(self, final):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.data["time"] = now
        self.data["working"] = dict(self.working)
        self.data["candidate_count"] = len(self._archive)
        self.data["interrupted"] = bool(self._interrupted)
        self.data["run_health"] = self._run_health()
        if self._archive:
            observed = max(self._archive, key=lambda row: float(
                row.get("fidelity", -np.inf)))
            self.data["best_observed_single_block"] = {
                key: observed[key] for key in (
                    "read_pulse_freq", "read_pulse_gain", "read_length",
                    "qubit_pi_freq", "qubit_pi_gain", "sigma",
                    "qubit_drag_beta", "fidelity",
                    "fidelity_se", "fidelity_lcb_95", "label", "measurement_index")
            }
        if final is None:
            self.data.update({
                "outcome": "no_measurement", "success": False,
                "failure": "no direct single-shot candidate was completed",
                "best_found": None, "tuned": {}, "eligible_tuned": {},
            })
            return
        # Discovery qualification is a hard phase boundary.  A baseline or bootstrap
        # histogram remains useful diagnostic evidence, but it is not a partially
        # successful tune and must never be dressed up as a final/portfolio result.
        if bool(self.data.get("expensive_search_skipped", False)):
            candidate = copy.deepcopy(final)
            tuned = ({key: candidate[key] for key in TUNED_KEYS}
                     if all(key in candidate for key in TUNED_KEYS) else {})
            self.data.update({
                "outcome": "transition_qualification_failed",
                "success": False,
                "failure": self.data.get(
                    "expensive_search_skip_reason",
                    "resonator/qubit qualification failed before joint search"),
                "best_found": candidate,
                "best_overall_candidate": candidate,
                "best_safe_candidate": None,
                "best_fidelity_replay": candidate,
                "best_fidelity_replay_complete": False,
                "tuned": tuned, "eligible_tuned": {},
                "final_stable": False, "fidelity_replay_stable": False,
                "manual_selection_required": False,
                "automatic_config_write_allowed": False,
            })
            portfolio = self.data.get("duration_portfolio")
            if isinstance(portfolio, dict):
                portfolio.update({
                    "status": "not_run_transition_unqualified",
                    "automatic_write_allowed": False,
                })
            return
        if self._duration_portfolio_active:
            self._finalize_duration_portfolio(final)
            return
        best = self._annotate_candidate_latency(final)
        stable_replays = [
            self._annotate_candidate_latency(row)
            for row in self._final_replays
            if bool(row.get("final_replay_stable", False))
            and all(key in row for key in self.initial)
        ]
        # ``best_found`` remains the exact tuple selected by safety/timing/write
        # policy.  The fidelity objective is an independent immutable answer: the
        # strongest stable exact replay from *any* final batch, including a later
        # screened batch which happens to outperform the earlier unconstrained one.
        if stable_replays:
            best_overall = max(stable_replays, key=self._joint_rank)
        else:
            prior = self.data.get("best_fidelity_replay")
            best_overall = self._annotate_candidate_latency(
                prior if isinstance(prior, dict) else best)
        self.data["best_overall_candidate"] = copy.deepcopy(best_overall)
        self.data["best_fidelity_replay"] = copy.deepcopy(best_overall)
        self.data["best_fidelity_replay_complete"] = bool(stable_replays)
        measured_pool = [row for row in self._confirmed
                         if all(key in row for key in self.initial)]
        if measured_pool:
            frontier = latency_pareto_frontier(measured_pool)
            fidelity_reference = max(measured_pool, key=self._joint_rank)
            fast_advisory, fast_diagnostics = select_shortest_noninferior(
                measured_pool, fidelity_reference,
                max_loss=float(self.params["latency"].get(
                    "max_fidelity_loss", 0.005)),
                confidence_z=float(self.params["latency"].get(
                    "confidence_sigma", 1.96)),
                minimum_mean=float(self.params["latency"].get(
                    "minimum_mean_fidelity", 0.90)),
                minimum_lcb=float(self.params["latency"].get(
                    "minimum_lcb_fidelity", 0.88)),
            )
            self.data["joint_search"].update({
                "best_measured_reference": copy.deepcopy(fidelity_reference),
                "latency_pareto_frontier": copy.deepcopy(frontier),
                # Advisory only: the existing randomized familywise latency stage is
                # the certificate allowed to influence a write.
                "shortest_noninferior_advisory": copy.deepcopy(fast_advisory),
                "shortest_noninferior_diagnostics": fast_diagnostics,
            })
        # Convert arrays to ordinary lists only in the compact top-level result; full
        # numpy evidence remains in confirmed_candidates and the pickle.
        for array_key in (
                "block_fidelities", "block_fidelity_ses",
                "block_crossfit_fidelities",
                "block_crossfit_fidelity_ses"):
            if isinstance(best.get(array_key), np.ndarray):
                best[array_key] = best[array_key].tolist()
        best["gate_length_ns"] = 4000.0 * float(best["sigma"])
        self.data["best_found"] = best
        latency_record = self.data.get("latency_optimization", {})
        latency_final_guard = True
        if isinstance(latency_record, dict):
            final_latency = float(self._candidate_latency_us(best))
            certified_key = tuple(latency_record.get(
                "certified_selected_key") or ())
            final_key = _candidate_key(best)
            latency_enabled = bool(latency_record.get("enabled", False))
            status_before_final = str(latency_record.get("status", "not_run"))
            certifying_status = bool(
                status_before_final in ("selected", "selected_control_recovery")
                or (status_before_final.startswith("retained_reference")
                    and status_before_final
                    != "retained_reference_timing_uncertain"))
            timing_certificate_active = bool(
                latency_enabled and certifying_status
                and latency_record.get("latency_certificate_valid", False))
            minimum_mean = float(self.params["latency"].get(
                "minimum_mean_fidelity", 0.90))
            minimum_lcb = float(self.params["latency"].get(
                "minimum_lcb_fidelity", 0.88))
            certified_selected = latency_record.get("certified_selected", {})
            final_timing = self._latency_fidelity_evidence(best)
            certified_timing = self._latency_fidelity_evidence(
                certified_selected if isinstance(certified_selected, dict)
                else best)
            certified_fidelity = float(certified_timing["fidelity"])
            maximum_drop = float(min(
                max(float(self.params["latency"].get(
                    "max_final_fidelity_drop", 0.010)), 0.0),
                max(float(self.params["latency"].get(
                    "max_fidelity_loss", 0.010)), 0.0)))
            latency_final_guard = bool(
                not timing_certificate_active
                or (float(final_timing["fidelity"]) >= minimum_mean
                    and float(final_timing["fidelity_lcb_95"]) >= minimum_lcb
                    and float(final_timing["fidelity"])
                    >= certified_fidelity - maximum_drop))
            certificate_matches = bool(
                timing_certificate_active and certified_key
                and final_key == certified_key
                and latency_final_guard)
            latency_record.update({
                "final_selected": copy.deepcopy(best),
                "final_selected_latency_us": final_latency,
                "final_selected_integration_chain_us": float(
                    best.get("integration_chain_us", np.inf)),
                "final_selected_read_length_us": float(best["read_length"]),
                "final_selected_x180_us": 4.0 * float(best["sigma"]),
                "certificate_matches_final_tuple": certificate_matches,
                "final_fidelity_guard_passed": latency_final_guard,
                "timing_certificate_was_active": timing_certificate_active,
                "final_timing_fidelity": float(final_timing["fidelity"]),
                "final_timing_fidelity_lcb_95": float(
                    final_timing["fidelity_lcb_95"]),
                "final_timing_fidelity_estimator": final_timing["estimator"],
                "final_fidelity_drop_from_certificate": float(
                    certified_fidelity - float(final_timing["fidelity"])),
                "max_final_fidelity_drop": maximum_drop,
            })
            if certificate_matches:
                latency_record.update({
                    "selected": copy.deepcopy(best),
                    "selected_latency_us": final_latency,
                    "latency_certificate_valid": True,
                })
            elif timing_certificate_active:
                previous_status = str(latency_record.get("status", "not_run"))
                latency_record.update({
                    "status": (
                        "invalidated_final_fidelity_guard"
                        if final_key == certified_key else
                        "invalidated_final_tuple_changed"),
                    "status_before_invalidation": previous_status,
                    "latency_certificate_valid": False,
                    "qualified_speedup": False,
                    "latency_saved_us": 0.0,
                    "latency_reduction_fraction": 0.0,
                })
            else:
                # A failed/not-run/uncertain timing stage is a pure-fidelity fallback.
                # It remains subject to the ordinary exact-final, safety, discovery,
                # and write-LCB gates below, but timing-only .90/.88 floors are N/A.
                latency_record.update({
                    "latency_certificate_valid": False,
                    "qualified_speedup": False,
                    "latency_saved_us": 0.0,
                    "latency_reduction_fraction": 0.0,
                })
            reference_latency = float(latency_record.get(
                "reference_latency_us", np.inf))
            if np.all(np.isfinite([reference_latency, final_latency])):
                raw_saved = float(reference_latency - final_latency)
                latency_record.update({
                    "final_latency_delta_us": float(
                        final_latency - reference_latency),
                    "final_observed_latency_saved_us": float(
                        max(raw_saved, 0.0)),
                })
                if certificate_matches:
                    latency_record.update({
                        "latency_saved_us": float(max(raw_saved, 0.0)),
                        "latency_reduction_fraction": float(
                            max(raw_saved, 0.0)
                            / max(reference_latency, 1e-12)),
                    })

        # Report the two requested optimization answers separately.  Prefer the
        # randomized paired/familywise timing certificate when it survived the exact
        # final guard.  Otherwise provide a clearly labeled advisory from completed
        # held-out confirmations; it is useful evidence but cannot authorize a
        # configuration write or claim a proven speedup.
        safety_active = bool(
            self._leakage_active or self._operational_leakage_active)
        verified_safety_key = (
            tuple(self._leakage_verified_candidate_key)
            if self._leakage_verified_candidate_key is not None else None)
        certified_short = None
        if (isinstance(latency_record, dict)
                and bool(latency_record.get("latency_certificate_valid", False))
                and bool(latency_record.get("qualified_speedup", False))):
            candidate = latency_record.get("certified_selected")
            if (isinstance(candidate, dict)
                    and (not safety_active
                         or (verified_safety_key is not None
                             and _candidate_key(candidate)
                             == verified_safety_key))):
                certified_short = self._annotate_candidate_latency(candidate)
        advisory_pool = list(stable_replays)
        advisory_pool.extend(
            self._annotate_candidate_latency(row) for row in self._confirmed
            if all(key in row for key in self.initial)
            and bool(row.get("confirmation_complete", True))
            and int(row.get("confirmation_blocks", 0)) >= 2)
        advisory_pool = unique_candidate_rows(advisory_pool)
        if safety_active:
            # A fast tuple is not a usable leakage-safe answer merely because another
            # duration passed.  Only the exact readout/control tuple independently
            # verified by the active safety path may be called the short candidate.
            advisory_pool = [
                row for row in advisory_pool
                if verified_safety_key is not None
                and _candidate_key(row) == verified_safety_key]
        shortest_diagnostics = []
        if certified_short is not None:
            shortest = certified_short
            shortest_status = "familywise_paired_noninferiority_certified"
        elif advisory_pool:
            strict_shortest, shortest_diagnostics = select_shortest_noninferior(
                advisory_pool, best_overall,
                max_loss=float(self.params["latency"].get(
                    "max_fidelity_loss", 0.005)),
                confidence_z=float(self.params["latency"].get(
                    "confidence_sigma", 1.96)),
                minimum_mean=float(self.params["latency"].get(
                    "minimum_mean_fidelity", 0.90)),
                minimum_lcb=float(self.params["latency"].get(
                    "minimum_lcb_fidelity", 0.88)),
            )
            strict_shortest = self._annotate_candidate_latency(strict_shortest)
            self.data["shortest_strict_noninferior_candidate"] = copy.deepcopy(
                strict_shortest)
            if _candidate_key(strict_shortest) != _candidate_key(best_overall):
                shortest = strict_shortest
                shortest_status = (
                    "independent_noninferiority_advisory_not_familywise_certified")
            else:
                best_mean = fidelity_evidence(best_overall)[0]
                maximum_mean_loss = float(self.params["latency"].get(
                    "practical_max_mean_fidelity_loss", 0.05))
                minimum_mean = float(self.params["latency"].get(
                    "practical_minimum_mean_fidelity", 0.85))
                minimum_lcb = float(self.params["latency"].get(
                    "practical_minimum_lcb_fidelity", 0.82))
                practical = []
                for row in advisory_pool:
                    mean, _se, lcb = fidelity_evidence(row)
                    if (np.all(np.isfinite([mean, lcb, best_mean]))
                            and mean >= minimum_mean
                            and lcb >= minimum_lcb
                            and best_mean - mean <= maximum_mean_loss):
                        practical.append(row)
                if practical:
                    shortest = min(practical, key=lambda row: (
                        self._candidate_latency_us(row),
                        -fidelity_evidence(row)[2],
                        -fidelity_evidence(row)[0]))
                    shortest = self._annotate_candidate_latency(shortest)
                else:
                    shortest = copy.deepcopy(best_overall)
                shortest_status = (
                    "same_as_best_overall_no_faster_high_fidelity_option"
                    if _candidate_key(shortest) == _candidate_key(best_overall)
                    else "practical_pareto_advisory_not_write_eligible")
        elif safety_active:
            shortest = None
            shortest_status = "no_short_candidate_passed_exact_tuple_safety"
        else:
            shortest = copy.deepcopy(best_overall)
            shortest_status = "best_effort_no_complete_final_replay_set"
        for candidate in (best_overall, shortest):
            if not isinstance(candidate, dict):
                continue
            candidate["safety_screen_required"] = safety_active
            candidate["safety_screen_verified_for_exact_tuple"] = bool(
                not safety_active
                or (verified_safety_key is not None
                    and _candidate_key(candidate) == verified_safety_key))
        self.data["best_overall_candidate"] = copy.deepcopy(best_overall)
        self.data["best_fidelity_replay"] = copy.deepcopy(best_overall)
        self.data["shortest_high_fidelity_candidate"] = copy.deepcopy(shortest)
        self.data["shortest_high_fidelity_status"] = shortest_status
        self.data["shortest_high_fidelity_diagnostics"] = shortest_diagnostics
        tuned = {key: best[key] for key in TUNED_KEYS}
        self.data["tuned"] = tuned
        is_final = str(best.get("label", "")).startswith("final exact")
        leakage_required = bool(
            self.data["leakage"].get("active", False)
            and self.data["leakage"].get("required_for_write", True))
        leakage_verified = bool(self.data["leakage"].get("verified", False))
        leakage_tuple_match = bool(
            not leakage_required
            or (leakage_verified
                and self._leakage_verified_candidate_key is not None
                and _candidate_key(best) == self._leakage_verified_candidate_key
                and self._final_replay_kind == "leakage_constrained"))
        self.data["leakage_required_for_write"] = leakage_required
        self.data["leakage_verified"] = leakage_verified
        fidelity_replay_stable = bool(
            is_final and self._final_replay_completed and not self._interrupted
            and int(best.get("confirmation_blocks", 0))
            >= int(self.params["final"]["blocks"])
            and float(best.get("block_spread", np.inf))
            <= float(self.params["final"]["max_block_spread"]))
        required_discovery = []
        if self._discovery_guard_active:
            if self.params["resonator"].get("enabled", True):
                required_discovery.append("resonator")
            if self.params["spectroscopy"].get("enabled", True):
                required_discovery.append("spectroscopy")
        missing_discovery = [
            name for name in required_discovery
            if not bool(self._discovery_status.get(name, False))]
        discovery_verified = not missing_discovery
        minimum_write_lcb = float(self.params["final"].get(
            "minimum_write_fidelity_lcb", 0.60))
        measured_lcb = float(best.get("fidelity_lcb_95", -np.inf))
        fidelity_write_qualified = bool(
            not self._discovery_guard_active
            or (np.isfinite(measured_lcb)
                and measured_lcb >= minimum_write_lcb))
        selected_control_key = _control_key(best)
        matching_control_witnesses = [
            row for row in self._control_witnesses
            if tuple(row.get("control_key", ())) == selected_control_key
        ]
        control_required = bool(self._discovery_guard_active)
        control_verified = bool(
            not control_required
            or self._final_control_verified_key == selected_control_key)
        self._discovery_status.update({
            "guard_active": bool(self._discovery_guard_active),
            "required_for_write": list(required_discovery),
            "missing_for_write": list(missing_discovery),
            "verified_for_write": bool(discovery_verified),
        })
        stable = bool(
            fidelity_replay_stable and leakage_tuple_match
            and discovery_verified and fidelity_write_qualified
            and control_verified and latency_final_guard)
        self.data["fidelity_replay_stable"] = fidelity_replay_stable
        self.data["final_stable"] = stable
        self.data["write_fidelity_gate"] = {
            "minimum_lcb": minimum_write_lcb,
            "measured_lcb": measured_lcb,
            "passed": bool(fidelity_write_qualified),
        }
        self.data["control_validation"] = {
            "required_for_write": bool(control_required),
            "verified_for_write": bool(control_verified),
            "selected_control_tuple": {
                "qubit_pi_freq": float(best["qubit_pi_freq"]),
                "qubit_pi_gain": int(round(best["qubit_pi_gain"])),
                "sigma": float(best["sigma"]),
                "qubit_drag_beta": float(best.get("qubit_drag_beta", 0.0)),
            },
            "selected_control_key": selected_control_key,
            "fresh_exact_audit_key": self._final_control_verified_key,
            "matching_witnesses": copy.deepcopy(matching_control_witnesses),
            "all_witnesses": copy.deepcopy(self._control_witnesses),
        }
        if fidelity_replay_stable and not discovery_verified:
            self._log(
                "eligibility", "WARN",
                "stable final replay is reportable but critical discovery failed: %s; "
                "automatic writes are blocked"
                % ", ".join(missing_discovery))
        if fidelity_replay_stable and not fidelity_write_qualified:
            self._log(
                "eligibility", "WARN",
                "stable final replay has fidelity LCB %.3f below the %.3f write "
                "floor; coin-flip discrimination cannot become a calibration"
                % (measured_lcb, minimum_write_lcb))
        if fidelity_replay_stable and not control_verified:
            self._log(
                "eligibility", "WARN",
                "stable final replay has no coherent Rabi/repeated-pulse witness "
                "for its exact frequency/gain/sigma/DRAG tuple; a saturation "
                "response is not proof of an X180 pulse, so automatic writes are "
                "blocked")
        evidence = {
            key: self._key_has_evidence(key, tuned[key]) for key in TUNED_KEYS
        }
        changed = [
            key for key in TUNED_KEYS
            if not self._tuned_values_match(
                key, tuned[key], self._input_tuned_value(key))
        ]
        missing_evidence = [key for key in changed if not evidence[key]]
        eligible = {}
        if stable and changed:
            # The stable final replay plus its exact-waveform coherence audit is the
            # strongest relevant write evidence: every changed coordinate below was
            # jointly exercised as one physical tuple.  Requiring a second, per-axis
            # provenance record can incorrectly reject a real winner that entered the
            # final pool through basin recovery or a cross-coordinate comparison.  We
            # therefore write the changed members of this jointly replayed tuple as an
            # atomic unit.  Earlier search evidence remains useful diagnostic metadata,
            # but it is not a veto over the later full-tuple experiment.
            eligible = {key: tuned[key] for key in changed}
            if missing_evidence:
                self._log(
                    "eligibility", "OK",
                    "stable exact final replay authorizes the complete measured "
                    "tuple; separate coordinate-search provenance is absent for %s"
                    % ", ".join(missing_evidence))
        self.data["eligibility"] = {
            "stable_final_replay": bool(stable),
            "changed_keys": list(changed),
            "exact_value_evidence": evidence,
            "missing_evidence": list(missing_evidence),
            "search_provenance_complete": bool(not missing_evidence),
            "eligibility_basis": (
                "stable_exact_full_tuple_replay_and_control_audit"
                if stable and control_required
                else ("stable_exact_full_tuple_replay" if stable else None)),
            "atomic_tuple_safe": bool(stable),
            "leakage_required": bool(leakage_required),
            "leakage_verified": bool(leakage_verified),
            "leakage_tuple_match": bool(leakage_tuple_match),
            "discovery_verified": bool(discovery_verified),
            "missing_discovery": list(missing_discovery),
            "minimum_write_fidelity_lcb": minimum_write_lcb,
            "write_fidelity_lcb": measured_lcb,
            "write_fidelity_qualified": bool(fidelity_write_qualified),
            "control_required": bool(control_required),
            "control_verified": bool(control_verified),
            "latency_final_fidelity_guard": bool(latency_final_guard),
            "final_replay_kind": self._final_replay_kind,
            "write_needed": bool(changed),
        }
        self.data["eligible_tuned"] = eligible
        self.data["success"] = True
        warned = [row for row in self._stages if row.get("status") == "warning"]
        report_warnings = [row.get("message") for row in self._report
                           if row.get("level") == "WARN"]
        self.data["warnings"] = ([row.get("error") for row in warned]
                                 + report_warnings)
        if self._interrupted:
            self.data["outcome"] = "interrupted_with_candidate"
        elif is_final:
            self.data["outcome"] = ("completed_with_warnings"
                                    if warned or report_warnings
                                    else "completed")
        else:
            self.data["outcome"] = "partial_with_candidate"
        self.data["failure"] = None
        self._log("result", "OK",
                  "best measured step-5 F=%.4f +/- %.4f%s"
                  % (best["fidelity"], best["fidelity_se"],
                     " (full measured tuple is write-eligible after stable final "
                     "replay and exact control audit)"
                     if eligible
                     else " (reported, not write-eligible)"))

    # ---------------------------------------------------------------- persistence
    def _checkpoint(self, data=None):
        """Atomically replace the lossless pickle checkpoint on the same volume."""
        payload = self.data if data is None else data
        temporary = self.pname + ".tmp"
        with open(temporary, "wb") as stream:
            pickle.dump(payload, stream, protocol=pickle.HIGHEST_PROTOCOL)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.pname)

    @staticmethod
    def _jsonable_summary(data):
        keys = (
            "revision", "fidelity_definition", "initial", "working", "best_found",
            "best_fidelity_replay", "best_fidelity_replay_complete",
            "best_overall_candidate", "best_safe_candidate",
            "best_balanced_candidate",
            "shortest_high_fidelity_candidate",
            "shortest_high_fidelity_status",
            "selection_objective",
            "tuned", "eligible_tuned", "eligibility", "outcome", "success", "failure",
            "candidate_count", "interrupted", "final_stable", "time", "stages",
            "fidelity_replay_stable",
            "discovery", "write_fidelity_gate", "control_validation",
            "control_witnesses",
            "report", "confirmation_failures", "final_confirmation_complete",
            "unconfirmed_contenders", "leakage_required_for_write",
            "leakage_verified", "reset", "manual_selection_required",
            "automatic_config_write_allowed",
            "control_branch_qualification", "pre_expensive_gate",
            "expensive_search_skipped", "expensive_search_skip_reason",
            "diagnostic_bundle", "run_health", "planned_repetitions",
            "planned_passive_idle_hours",
        )
        summary = {key: data.get(key) for key in keys if key in data}
        portfolio = data.get("duration_portfolio", {})
        if isinstance(portfolio, dict) and portfolio.get("enabled", False):
            compact_portfolio = {key: portfolio.get(key) for key in (
                "enabled", "manual_selection_only", "automatic_write_allowed",
                "readout_length_mode", "configured_initialize_read_length_us",
                "status", "read_lengths_us", "requested_length_count",
                "reportable_length_count", "balanced_reportable_length_count",
                "safe_length_count",
                "unsafe_length_count", "inconclusive_length_count",
                "equal_refinement_budget",
                "expected_refine_candidates_per_length",
                "selection_objective", "leakage_affects_selection",
                "control_audit_affects_selection", "balanced_selection_objective",
                "balanced_max_fidelity_loss",
                "duration_interleaved_exact_replay",
            ) if key in portfolio}
            compact_entries = []
            for entry in portfolio.get("entries", []):
                if not isinstance(entry, dict):
                    continue
                selected = entry.get("selected")
                row = {key: entry.get(key) for key in (
                    "read_length_us", "status", "leakage_status",
                    "control_status", "balanced_status",
                    "balanced_leakage_status", "balanced_control_status")}
                if isinstance(selected, dict):
                    row["selected"] = {key: selected.get(key) for key in (
                        *TUNED_KEYS, "fidelity", "fidelity_se",
                        "fidelity_lcb_95", "third_blob_excess_ucb",
                        "third_cluster_fraction",
                        "third_cluster_fraction_ucb_95",
                        "third_cluster_single_state_fraction",
                        "third_cluster_single_state_fraction_ucb_95",
                        "single_p2_ucb", "amplified_p2_ucb",
                        "portfolio_leakage_risk_ucb",
                        "portfolio_selection_fidelity_lcb",
                        "control_verified", "portfolio_safety_kind",
                    ) if key in selected}
                balanced = entry.get("balanced")
                if isinstance(balanced, dict):
                    row["balanced"] = {key: balanced.get(key) for key in (
                        *TUNED_KEYS, "fidelity", "fidelity_se",
                        "fidelity_lcb_95", "third_blob_excess_ucb",
                        "third_cluster_fraction",
                        "third_cluster_fraction_ucb_95",
                        "third_cluster_single_state_fraction",
                        "third_cluster_single_state_fraction_ucb_95",
                        "single_p2_ucb", "amplified_p2_ucb",
                        "portfolio_leakage_risk_ucb",
                        "portfolio_selection_fidelity_lcb",
                        "control_verified", "portfolio_safety_kind",
                        "balanced_noninferiority",
                        "balanced_is_fidelity_winner",
                    ) if key in balanced}
                compact_entries.append(row)
            compact_portfolio["entries"] = compact_entries
            summary["duration_portfolio"] = compact_portfolio
        joint = data.get("joint_search", {})
        if isinstance(joint, dict):
            compact_joint = {key: joint.get(key) for key in (
                "enabled", "status", "coarse_row_count",
                "medium_candidate_count", "drift_epochs",
                "runtime_minutes_after_coarse", "runtime_minutes_after_search",
            ) if key in joint}
            coverage = joint.get("coverage")
            if isinstance(coverage, dict):
                compact_joint["coverage"] = copy.deepcopy(coverage)
            candidate_keys = TUNED_KEYS + (
                "fidelity", "fidelity_se", "fidelity_lcb_95",
                "crossfit_fidelity", "crossfit_fidelity_se",
                "crossfit_fidelity_lcb_95", "confirmation_blocks",
                "chain_latency_us",
            )
            for name in ("selected", "best_measured_reference",
                         "shortest_noninferior_advisory"):
                candidate = joint.get(name)
                if isinstance(candidate, dict):
                    compact_joint[name] = {
                        key: candidate.get(key) for key in candidate_keys
                        if key in candidate
                    }
            compact_joint["pareto_point_count"] = len(
                joint.get("latency_pareto_frontier", []))
            summary["joint_search"] = compact_joint
        latency = data.get("latency_optimization", {})
        if isinstance(latency, dict):
            scalar_keys = (
                "enabled", "objective", "requested_objective", "status",
                "status_before_invalidation", "reference_kind",
                "max_fidelity_loss", "familywise_confidence_sigma",
                "familywise_comparison_count", "familywise_distribution",
                "familywise_degrees_of_freedom", "confirmation_blocks",
                "reference_drift", "reference_latency_us",
                "selected_latency_us", "integration_chain_us",
                "latency_saved_us", "latency_reduction_fraction",
                "pre_safety_selected_fidelity_loss",
                "qualified_candidate_found", "qualified_speedup",
                "control_screen_passed", "latency_certificate_valid",
                "certificate_matches_final_tuple",
                "timing_certificate_was_active", "final_fidelity_guard_passed",
                "final_timing_fidelity", "final_timing_fidelity_lcb_95",
                "final_timing_fidelity_estimator",
                "final_fidelity_drop_from_certificate",
                "max_final_fidelity_drop",
                "adaptive_rounds_completed", "final_selected_latency_us",
                "final_selected_integration_chain_us",
            )
            compact = {
                key: latency.get(key) for key in scalar_keys if key in latency
            }
            candidate_keys = TUNED_KEYS + (
                "fidelity", "fidelity_se", "fidelity_lcb_95",
                "crossfit_fidelity", "crossfit_fidelity_se",
                "crossfit_fidelity_lcb_95",
                "confirmation_blocks", "latency_us", "integration_chain_us",
            )
            for name in ("reference", "certified_selected", "final_selected"):
                candidate = latency.get(name)
                if isinstance(candidate, dict):
                    compact[name] = {
                        key: candidate.get(key) for key in candidate_keys
                        if key in candidate
                    }
            selected_key = tuple(latency.get("certified_selected_key") or ())
            diagnostic = next((row for row in latency.get("diagnostics", [])
                               if tuple(row.get("candidate_key") or ())
                               == selected_key), None)
            if isinstance(diagnostic, dict):
                compact["certificate"] = {
                    key: diagnostic.get(key) for key in (
                        "mean_loss", "loss_se", "loss_ucb", "confidence_z",
                        "method", "accepted", "reason") if key in diagnostic
                }
            summary["latency_optimization"] = compact
        leakage = data.get("leakage", {})
        if isinstance(leakage, dict):
            scalar_keys = (
                "active", "strict_direct_active", "operational_active",
                "required_for_write", "measurement", "direct_p2_measured",
                "third_blob_guard", "third_cluster_guard",
                "optimized", "verified", "selection_safe", "failure",
                "screening_kind", "drag_tuned", "best_third_blob_excess_ucb",
                "final_replay_complete",
                "used_safe_seed_fallback", "worst_single_p2_ucb",
                "worst_amplified_p2_ucb", "worst_third_blob_excess_ucb",
                "worst_third_cluster_fraction",
                "worst_third_cluster_fraction_ucb_95",
                "worst_third_cluster_single_state_fraction",
                "worst_third_cluster_single_state_fraction_ucb_95",
                "worst_even_return_error_ucb",
                "worst_odd_inversion_error_ucb",
            )
            summary["leakage"] = {
                key: leakage.get(key) for key in scalar_keys if key in leakage
            }
            chosen = leakage.get("chosen")
            if isinstance(chosen, dict):
                summary["leakage"]["chosen"] = {
                    key: chosen.get(key) for key in (
                        "qubit_pi_freq", "qubit_pi_gain", "sigma",
                        "qubit_drag_beta", "fidelity", "fidelity_se",
                        "single_p2_ucb", "amplified_p2_ucb",
                        "max_even_return_error_ucb",
                        "max_odd_inversion_error_ucb",
                        "third_blob_excess_ucb", "third_cluster_fraction",
                        "third_cluster_fraction_ucb_95",
                        "third_cluster_single_state_fraction",
                        "third_cluster_single_state_fraction_ucb_95", "leakage_safe",
                        "operational_safe")
                    if key in chosen
                }
        return summary

    def save_data(self, data=None):
        """Save compact numeric maps to HDF5; the complete nested archive is in pickle."""
        if data is None:
            data = self.data
        print("Saving %s" % self.fname)
        # Finalize the self-contained bundle first.  Even if the compact summary H5
        # later encounters a network-drive or serialization fault, the raw evidence
        # and complete Python archive survive in the file the operator will send back.
        if self._diagnostic_active:
            if self._finalize_diagnostic_bundle(data):
                print("Diagnostic bundle: %s" % self.diagnostic_fname)
            else:
                print("Warning: diagnostic bundle was incomplete: %s"
                      % self.diagnostic_fname)
        with self.datafile() as h5:
            h5.attrs["summary"] = json.dumps(self._jsonable_summary(data), cls=NpEncoder)
            h5.attrs["params"] = json.dumps(self.params, cls=NpEncoder)
            h5.attrs["input_config"] = json.dumps(self.input_cfg, cls=NpEncoder)
            for stage, mapping in (data.get("maps", {}) or {}).items():
                if not isinstance(mapping, dict):
                    continue
                prefix = "maps/%s" % str(stage).replace("/", "_")
                axes = mapping.get("axes", {})
                if isinstance(axes, dict):
                    for key, value in axes.items():
                        try:
                            arr = np.asarray(value)
                            if np.issubdtype(arr.dtype, np.number):
                                h5.add("%s/axis_%s" % (prefix, key), arr)
                        except Exception:
                            pass
                for key, value in mapping.items():
                    if key == "axes" or isinstance(value, (dict, str, bytes)):
                        continue
                    try:
                        arr = np.asarray(value)
                        if np.issubdtype(arr.dtype, np.complexfloating):
                            h5.add("%s/%s_real" % (prefix, key), arr.real)
                            h5.add("%s/%s_imag" % (prefix, key), arr.imag)
                        elif np.issubdtype(arr.dtype, np.number) or arr.dtype == bool:
                            h5.add("%s/%s" % (prefix, key), arr)
                    except Exception:
                        pass
            # Compact archive columns make the direct measurements inspectable without
            # loading Python pickle objects.
            if self._archive:
                columns = {
                    "fidelity": [row.get("fidelity", np.nan) for row in self._archive],
                    "fidelity_se": [row.get("fidelity_se", np.nan) for row in self._archive],
                    "read_frequency_mhz": [row["read_pulse_freq"] for row in self._archive],
                    "read_gain_dac": [row["read_pulse_gain"] for row in self._archive],
                    "read_length_us": [row["read_length"] for row in self._archive],
                    "qubit_frequency_mhz": [row["qubit_pi_freq"] for row in self._archive],
                    "qubit_gain_dac": [row["qubit_pi_gain"] for row in self._archive],
                    "sigma_us": [row["sigma"] for row in self._archive],
                    "drag_beta": [row.get("qubit_drag_beta", 0.0)
                                  for row in self._archive],
                    "third_blob_excess_ucb": [
                        row.get("third_blob_excess_ucb_95", np.nan)
                        for row in self._archive],
                    "third_cluster_fraction": [
                        row.get("third_cluster_fraction", np.nan)
                        for row in self._archive],
                    "third_cluster_fraction_ucb_95": [
                        row.get("third_cluster_fraction_ucb_95", np.nan)
                        for row in self._archive],
                }
                for key, value in columns.items():
                    h5.add("candidate_archive/%s" % key, np.asarray(value))
            leakage_rows = (data.get("leakage", {}) or {}).get("verification", [])
            if leakage_rows:
                for key in ("single_p2_ucb", "amplified_p2_ucb",
                            "max_even_return_error_ucb",
                            "max_odd_inversion_error_ucb",
                            "third_blob_excess_ucb", "third_cluster_fraction",
                            "third_cluster_fraction_ucb_95",
                            "third_cluster_single_state_fraction",
                            "third_cluster_single_state_fraction_ucb_95",
                            "fidelity"):
                    h5.add(
                        "leakage_verification/%s" % key,
                        np.asarray([row.get(key, np.nan) for row in leakage_rows],
                                   dtype=float))
        try:
            self._checkpoint(data)
        except Exception as exc:
            self._log("save", "WARN", "pickle save failed: %s" % exc)

    def save_plot(self, plotDisp=False):
        """Write one compact summary: direct fidelity history and the key search maps."""
        fig, axes = plt.subplots(2, 3, figsize=(15, 8.5), constrained_layout=True)
        axes = axes.ravel()
        if self._archive:
            fids = np.asarray([row.get("fidelity", np.nan) for row in self._archive])
            axes[0].plot(np.arange(fids.size), fids, ".", ms=3, alpha=0.65)
            if self.data.get("best_found"):
                axes[0].axhline(self.data["best_found"]["fidelity"], color="tab:red",
                                lw=1.2, label="selected final")
                axes[0].legend(fontsize=8)
            axes[0].set_ylim(0.45, 1.01)
            axes[0].set_xlabel("direct step-5 measurement")
            axes[0].set_ylabel("balanced assignment fidelity")
            axes[0].set_title("All directly measured candidates")
        else:
            axes[0].text(0.5, 0.5, "no direct SS data", ha="center", va="center")

        preferred = [
            ("iq_rabi", "row_r2"),
            ("parity_chevron", "parity_score"),
            ("joint_search", "duration_best_fidelity"),
            ("readout_grid", "fidelity"),
            ("amplified_error", "parity_score"),
        ]
        for axis, (stage, field) in zip(axes[1:], preferred):
            mapping = self._maps.get(stage, {})
            value = mapping.get(field)
            if value is None:
                axis.text(0.5, 0.5, "%s not available" % stage,
                          ha="center", va="center")
                axis.set_axis_off()
                continue
            arr = np.asarray(value, dtype=float)
            while arr.ndim > 2:
                arr = np.nanmax(arr, axis=0)
            if arr.ndim == 1:
                axis.plot(arr, "o-")
            else:
                image = axis.imshow(arr, origin="lower", aspect="auto",
                                    interpolation="nearest")
                fig.colorbar(image, ax=axis, shrink=0.8)
            axis.set_title("%s: %s" % (stage.replace("_", " "), field))
        leakage = self.data.get("leakage", {})
        portfolio = self.data.get("duration_portfolio", {})
        portfolio_entries = (portfolio.get("entries", [])
                             if isinstance(portfolio, dict) else [])
        if portfolio_entries:
            axis = axes[-1]
            axis.clear()
            lengths = np.asarray([
                entry.get("read_length_us", np.nan)
                for entry in portfolio_entries], dtype=float)
            fidelity = np.asarray([
                (entry.get("selected") or {}).get("fidelity", np.nan)
                for entry in portfolio_entries], dtype=float)
            fidelity_se = np.asarray([
                (entry.get("selected") or {}).get("fidelity_se", np.nan)
                for entry in portfolio_entries], dtype=float)
            third_ucb = np.asarray([
                (entry.get("selected") or {}).get(
                    "third_cluster_fraction_ucb_95", np.nan)
                for entry in portfolio_entries], dtype=float)
            colors = [{"SAFE": "tab:green", "UNSAFE": "tab:red"}.get(
                str(entry.get("status", "")).upper(), "tab:gray")
                for entry in portfolio_entries]
            axis.errorbar(lengths, fidelity, yerr=fidelity_se, color="0.35",
                          lw=1.0, marker="", capsize=2)
            axis.scatter(lengths, fidelity, c=colors, s=28, zorder=3)
            axis.set_ylim(0.45, 1.01)
            axis.set_xlabel("readout length (us)")
            axis.set_ylabel("held-out fidelity")
            leakage_axis = axis.twinx()
            leakage_axis.plot(lengths, third_ucb, "o--", color="tab:purple",
                              ms=3, lw=1.0, label="third-population UCB")
            leakage_axis.axhline(float(self.params["leakage"]
                                      ["max_third_cluster_fraction"]),
                                 color="tab:purple", ls=":", lw=1.0)
            leakage_axis.set_ylabel("third-population 95% UCB")
            axis.set_title("1-20 us manual-selection portfolio")
        elif isinstance(leakage, dict) and leakage.get("active", False):
            axis = axes[-1]
            axis.clear()
            rows = []
            for attempt in leakage.get("attempts", []):
                rows.extend(attempt.get("rows", []))
            rows = [row for row in rows
                    if np.isfinite(row.get("qubit_drag_beta", np.nan))]
            if rows:
                beta = np.asarray([row["qubit_drag_beta"] for row in rows])
                if leakage.get("strict_direct_active", False):
                    one = np.asarray([
                        row.get("single_p2_ucb", np.nan) for row in rows])
                    amplified = np.asarray([
                        row.get("amplified_p2_ucb", np.nan) for row in rows])
                    axis.plot(beta, one, "o", ms=4, label="one-pulse P(f) UCB")
                    axis.plot(beta, amplified, "s", ms=4,
                              label="amplified P(f) UCB")
                    axis.axhline(float(self.params["leakage"]["max_single_p2"]),
                                 color="tab:blue", ls="--", lw=1)
                    axis.axhline(float(
                        self.params["leakage"]["max_amplified_p2"]),
                        color="tab:orange", ls="--", lw=1)
                    axis.set_ylabel("population upper bound")
                    axis.set_title("direct shelving leakage constraint")
                else:
                    even = np.asarray([row.get(
                        "max_even_return_error_ucb", np.nan) for row in rows])
                    odd = np.asarray([row.get(
                        "max_odd_inversion_error_ucb", np.nan) for row in rows])
                    axis.plot(beta, even, "o", ms=4,
                              label="even return-error UCB")
                    axis.plot(beta, odd, "s", ms=4,
                              label="odd inversion-error UCB")
                    axis.axhline(float(self.params["leakage"]
                                       ["operational_max_even_return_error"]),
                                 color="tab:blue", ls="--", lw=1)
                    axis.axhline(float(self.params["leakage"]
                                       ["operational_max_odd_inversion_error"]),
                                 color="tab:orange", ls="--", lw=1)
                    axis.set_ylabel("normalized error upper bound")
                    axis.set_title("operational leakage-sensitive screen")
                axis.set_xlabel("DRAG beta")
                axis.legend(fontsize=7)
            else:
                axis.text(0.5, 0.5, "leakage-screen data unavailable",
                          ha="center", va="center")
        best = self.data.get("best_found")
        if best:
            if portfolio_entries:
                leakage_label = "manual 1-20 us portfolio"
            elif leakage.get("active", False):
                leakage_label = (
                    "verified" if leakage.get("verified", False)
                    else "not verified")
            else:
                leakage_label = "inactive"
            title = ("Basic auto tune %s | F=%.4f +/- %.4f | read %.6f/%d/%.1fus | "
                     "pi %.6f @ %d, %.1fns, DRAG %+.5f | leakage %s"
                     % (self.path, best["fidelity"], best["fidelity_se"],
                        best["read_pulse_freq"], best["read_pulse_gain"],
                        best["read_length"], best["qubit_pi_freq"],
                        best["qubit_pi_gain"], 4000.0 * best["sigma"],
                        best.get("qubit_drag_beta", 0.0),
                        leakage_label))
        else:
            title = "Basic auto tune %s | no completed direct SS candidate" % self.path
        fig.suptitle(title)
        fig.savefig(self.iname, dpi=160)
        if plotDisp:
            plt.show(block=False)
            plt.pause(0.1)
        else:
            plt.close(fig)
