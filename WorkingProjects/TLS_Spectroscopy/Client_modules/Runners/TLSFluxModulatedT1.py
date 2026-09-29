"""Compare q3 loss with and without fast-flux modulation in each QICK shot.

The direct loss test showed that a 30-MHz waveform changes q3's loss, while
the carrier/sideband pilot did not resolve the modulation index. The original
mode compares 0, 800, and 1600 DAC AC flux at the freshly found loss
feature and a 14-MHz lower flank. Every logical hardware shot interleaves
short/long, modulation off/on, and park-prepared ground/excited visits. The
off visit uses the pinned static correction; the on visit adds a zero-mean
sinusoid to that same correction. Readout occurs after the full corrected
40-us return. This measures a candidate loss response, not TLS identity.

The ``--floquet-direct`` mode instead anchors the stronger 3.992-GHz
feature and applies a fully sampled, correction-matched AC waveform
after only the required 0.55-us arrival/settle. It compares 1.6- and
5.6-us AC-on/off visits in both program orders. This is a direct loss
test, not a calibrated J0-zero measurement.

The ``--floquet-frequency-sweep`` mode compares the same direct loss
measurement at 20, 30, and 40 MHz and four amplitudes. It tests whether the
response shifts with modulation frequency; without independent transfer
calibration, such a shift cannot by itself establish coherent Floquet physics.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid

import numpy as np

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.PulseFunctions import (
    ff_envelope_samples, ff_maxv,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
    TLSFluxModulationCalibration as calibration,
    TLSPumpProbeAdaptiveParkPump as adaptive,
    TLSPumpProbeLocalizer as localizer,
    TLSPumpProbeProtocolCheck as protocol,
    TLSPumpProbeResidentDrive as resident,
    TLSPumpProbeResidentProbe as probe,
    TLSPumpProbeShotAlternating as alternating,
    TLSPumpProbeWidePassiveScan as wide,
    TLSSwapHoldPilot as swap,
)


MODULATION_MHZ = 30.0
AMPLITUDES_DAC = (800, 1600)
HOLDS_US = (0.1, 6.0)
SHOTS = 4000
REFERENCE_SHOTS = 400
PRE_US = 20.0
PARK_RAMP_US = 1.0
RECORDS_PER_SHOT = 8
DIRECT_AMPLITUDES_DAC = (1000, 1600)
DIRECT_HOLDS_US = (1.6, 5.6)
DIRECT_PRE_US = 0.05
DIRECT_SHOTS = 6000
SWEEP_AMPLITUDES_DAC = (200, 400, 600, 800, 1000, 1200,
                        1400, 1600, 2000, 2400)
SWEEP_SHOTS = 4000
FREQUENCY_SWEEP_MHZ = (20.0, 30.0, 40.0)
FREQUENCY_SWEEP_AMPLITUDES_DAC = (600, 1000, 1400, 2000)
FREQUENCY_SWEEP_SHOTS = 4000
SCALING_PAIRS_MHZ_DAC = (
    (10.0, 500), (20.0, 1000), (30.0, 1500), (40.0, 2000),
    (50.0, 2500),
    (10.0, 1000), (30.0, 1000), (40.0, 1000), (50.0, 1000),
    (10.0, 2000), (20.0, 2000), (30.0, 2000), (50.0, 2000),
)
SCALING_SHOTS = 4000


def compensated_ac_waveform(*, segments, park_gain, target_gain,
                            amplitude_gain, modulation_mhz,
                            sample_rate_mhz, fabric_rate_mhz, cycles, max_gain):
    """Sample the pinned DC correction plus a sinusoid, without clipping."""
    lengths = np.asarray([float(duration) for _, duration in segments], dtype=float)
    levels = np.asarray([float(level) for level, _ in segments], dtype=float)
    if (lengths.size == 0 or not np.all(np.isfinite(lengths)) or
            not np.all(np.isfinite(levels)) or np.any(lengths <= 0)):
        raise ValueError("modulation hold needs finite positive correction segments")
    sine, report = calibration.modulation_waveform(
        sample_rate_mhz=sample_rate_mhz,
        fabric_rate_mhz=fabric_rate_mhz, cycles=cycles,
        baseline_gain=0.0, amplitude_gain=amplitude_gain,
        modulation_mhz=modulation_mhz, max_gain=max_gain)
    times_us = np.arange(len(sine), dtype=float) / float(sample_rate_mhz)
    if times_us[-1] > sum(lengths) + 1e-6:
        raise ValueError("correction segments do not cover the AC hold")
    segment_index = np.searchsorted(np.cumsum(lengths), times_us, side="right")
    segment_index = np.minimum(segment_index, len(levels)-1)
    baseline = float(park_gain) + levels[segment_index] * (
        float(target_gain) - float(park_gain))
    values = np.rint(baseline + sine.astype(float))
    if np.max(np.abs(values)) > min(float(max_gain), 32767.0):
        raise ValueError("AC waveform exceeds the fast-flux DAC range")
    waveform = values.astype(np.int16)
    report.update({"dc_level_count": int(len(levels)),
                   "dc_min": float(np.min(baseline)),
                   "dc_max": float(np.max(baseline)),
                   "waveform_min": int(waveform.min()),
                   "waveform_max": int(waveform.max())})
    return waveform, report


def conditions(flux_ghz, *, amplitude_dac, reverse=False,
               holds_us=HOLDS_US, pre_us=PRE_US):
    result = []
    for hold_label, hold_us in zip(("short", "long"), holds_us):
        for drive in ("off", "on"):
            for state in ("g", "e"):
                result.append({"name": f"{hold_label}_{drive}_{state}",
                               "flux_ghz": float(flux_ghz),
                               "drive_mhz": float(flux_ghz) * 1000.0,
                               "gain": 0, "preparation_state": state,
                               "reference_state": None,
                               "pre_drive_us": float(pre_us),
                               "post_drive_us": hold_us,
                               "modulation_amplitude_dac": (
                                   int(amplitude_dac) if drive == "on" else 0)})
    return list(reversed(result)) if reverse else result


def score_conditions(fractions):
    values = {name: float(value) for name, value in fractions.items()}
    score = {}
    for hold in ("short", "long"):
        for drive in ("off", "on"):
            score[f"{hold}_{drive}_contrast"] = (
                values[f"{hold}_{drive}_e"] - values[f"{hold}_{drive}_g"])
        score[f"{hold}_cold_modulation_change"] = (
            values[f"{hold}_on_g"] - values[f"{hold}_off_g"])
    score["modulation_survival_change"] = (
        score["long_on_contrast"] - score["short_on_contrast"] -
        score["long_off_contrast"] + score["short_off_contrast"])
    return score


def feature_specific_effect(feature, flank):
    return float(feature["modulation_survival_change"] -
                 flank["modulation_survival_change"])


def plan(*, focused=False, floquet_direct=False,
         floquet_amplitude_sweep=False, floquet_frequency_sweep=False,
         floquet_scaling_check=False):
    if sum((bool(focused), bool(floquet_direct),
            bool(floquet_amplitude_sweep), bool(floquet_frequency_sweep),
            bool(floquet_scaling_check))) > 1:
        raise ValueError("modulation experiment modes are exclusive")
    if floquet_scaling_check:
        return {"hardware_access": False, "reset_mode": "passive",
                "site": "fresh 3.992-GHz loss feature",
                "frequency_amplitude_pairs_mhz_dac": [list(pair) for pair in
                                                      SCALING_PAIRS_MHZ_DAC],
                "holds_us": list(DIRECT_HOLDS_US),
                "pre_target_hold_us": DIRECT_PRE_US,
                "park_ramp_us": PARK_RAMP_US,
                "conditions_per_shot": RECORDS_PER_SHOT,
                "programs": 2 * len(SCALING_PAIRS_MHZ_DAC),
                "shots_per_program": SCALING_SHOTS,
                "midpoint_feature_scout": True,
                "full_return_before_readout_us": 40.0,
                "raw_iq_saved": True,
                "measurement": "direct loss at equal A/f and fixed-amplitude controls",
                "interpretation": "compare response shapes; unknown line transfer prevents a J0 claim"}
    if floquet_frequency_sweep:
        return {"hardware_access": False, "reset_mode": "passive",
                "site": "fresh 3.992-GHz loss feature",
                "modulation_frequencies_mhz": list(FREQUENCY_SWEEP_MHZ),
                "modulation_amplitudes_dac": list(FREQUENCY_SWEEP_AMPLITUDES_DAC),
                "holds_us": list(DIRECT_HOLDS_US),
                "pre_target_hold_us": DIRECT_PRE_US,
                "park_ramp_us": PARK_RAMP_US,
                "conditions_per_shot": RECORDS_PER_SHOT,
                "programs": 2 * len(FREQUENCY_SWEEP_MHZ) *
                            len(FREQUENCY_SWEEP_AMPLITUDES_DAC),
                "shots_per_program": FREQUENCY_SWEEP_SHOTS,
                "midpoint_feature_scout": True,
                "full_return_before_readout_us": 40.0,
                "raw_iq_saved": True,
                "measurement": "feature loss versus AC frequency and amplitude; reversed order",
                "interpretation": "test frequency scaling; no transfer-calibrated J0 claim"}
    if floquet_amplitude_sweep:
        return {"hardware_access": False, "reset_mode": "passive",
                "site": "fresh 3.992-GHz loss feature",
                "modulation_frequency_mhz": MODULATION_MHZ,
                "modulation_amplitudes_dac": list(SWEEP_AMPLITUDES_DAC),
                "holds_us": list(DIRECT_HOLDS_US),
                "pre_target_hold_us": DIRECT_PRE_US,
                "park_ramp_us": PARK_RAMP_US,
                "conditions_per_shot": RECORDS_PER_SHOT,
                "programs": 2 * len(SWEEP_AMPLITUDES_DAC),
                "shots_per_program": SWEEP_SHOTS,
                "midpoint_feature_scout": True,
                "full_return_before_readout_us": 40.0,
                "raw_iq_saved": True,
                "measurement": "feature loss versus 30-MHz AC amplitude; forward/reverse order",
                "interpretation": "look for onset, plateau, or nonmonotonicity; no J0 claim"}
    if floquet_direct:
        return {"hardware_access": False, "reset_mode": "passive",
                "site": "fresh 3.992-GHz loss feature and clean upper flank",
                "modulation_frequency_mhz": MODULATION_MHZ,
                "modulation_amplitudes_dac": list(DIRECT_AMPLITUDES_DAC),
                "holds_us": list(DIRECT_HOLDS_US),
                "pre_target_hold_us": DIRECT_PRE_US,
                "park_ramp_us": PARK_RAMP_US,
                "conditions_per_shot": RECORDS_PER_SHOT,
                "programs": 8,
                "shots_per_program": DIRECT_SHOTS,
                "midpoint_feature_scout": True,
                "full_return_before_readout_us": 40.0,
                "raw_iq_saved": True,
                "measurement": "within-shot hot/cold loss with AC on/off at 1.6 and 5.6 us",
                "interpretation": "direct loss response; no calibrated J0 zero or TLS identity"}
    amplitudes = (1600,) if focused else AMPLITUDES_DAC
    return {"hardware_access": False, "reset_mode": "passive",
            "site": "fresh loss feature and 14-MHz lower flank",
            "modulation_frequency_mhz": MODULATION_MHZ,
            "modulation_amplitudes_dac": list(amplitudes),
            "holds_us": list(HOLDS_US),
            "pre_target_hold_us": PRE_US,
            "park_ramp_us": PARK_RAMP_US,
            "conditions_per_shot": RECORDS_PER_SHOT,
            "programs": 4 if focused else 8,
            "shots_per_program": 8000 if focused else SHOTS,
            "midpoint_feature_scout": bool(focused),
            "full_return_before_readout_us": 40.0,
            "raw_iq_saved": True,
            "measurement": "within-shot hot/cold survival, AC on/off, short/long",
            "note": __doc__}


def _target_segments(compensation, *, pre_us, hold_us, recovery_us):
    target, recovery = ff_pulse.compensation_round_trip_segments(
        compensation, pre_us + hold_us, recovery_us=recovery_us)
    before, during = ff_pulse.split_compensation_segments(target, pre_us)
    if not before or not during:
        raise ValueError("target correction does not cover the modulation hold")
    if sum(duration for _, duration in recovery) < recovery_us - 1e-6:
        raise ValueError("target correction does not cover the full return")
    return before, during, recovery


class ModulatedT1Program(alternating.ShotAlternatingResidentProgram):
    """Eight complete visits/readouts per shot, with one AC level per program."""

    def __init__(self, soccfg, condition_cfgs, payload_calibration, loop_calibration,
                 *, holds_us=HOLDS_US, pre_us=PRE_US,
                 allowed_amplitudes=AMPLITUDES_DAC,
                 modulation_mhz=MODULATION_MHZ):
        configs = [dict(cfg) for cfg in condition_cfgs]
        if len(configs) != RECORDS_PER_SHOT:
            raise ValueError("modulated T1 requires eight condition configurations")
        common = ("ff_gain", "ff_park_gain", "opx_resident_pre_us", "shots", "reps")
        if any(any(cfg[key] != configs[0][key] for key in common)
               for cfg in configs[1:]):
            raise ValueError("within-shot conditions must share flux, prehold, and shots")
        amplitudes = {int(cfg["opx_modulation_amplitude_dac"]) for cfg in configs}
        if amplitudes != {0, max(amplitudes)} or max(amplitudes) not in allowed_amplitudes:
            raise ValueError("each program needs AC-off and one declared AC-on level")
        observed = {(float(cfg["opx_resident_post_us"]),
                     int(cfg["opx_modulation_amplitude_dac"]),
                     cfg["opx_resident_preparation_state"]) for cfg in configs}
        expected = {(hold, amplitude, state) for hold in holds_us
                    for amplitude in amplitudes for state in ("g", "e")}
        if observed != expected:
            raise ValueError("conditions do not span both holds, AC states, and preparations")
        self.ac_amplitude_dac = max(amplitudes)
        self.modulation_mhz = float(modulation_mhz)
        if not np.isfinite(self.modulation_mhz) or self.modulation_mhz <= 0:
            raise ValueError("modulation frequency must be finite and positive")
        self.holds_us = tuple(float(hold) for hold in holds_us)
        self.pre_us = float(pre_us)
        self.logical_shots = int(configs[0]["shots"])
        self.condition_cfgs = configs
        run_cfg = dict(configs[0], reps=RECORDS_PER_SHOT * self.logical_shots)
        resident.ResidentDriveProgram.__init__(
            self, soccfg, run_cfg, payload_calibration, loop_calibration)

    def _declare_experiment(self):
        super()._declare_experiment()
        cfg = self.cfg
        generator = self.soccfg["gens"][int(cfg["ff_ch"])]
        self.ac_reports = {}
        self.ac_waveforms = {}
        for hold in self.holds_us:
            _, during, _ = _target_segments(
                self._t1_ff_compensation,
                pre_us=self.pre_us + self._t1_ff_settle_us,
                hold_us=hold,
                recovery_us=self._t1_ff_predistortion_recovery_us)
            cycles = int(self.us2cycles(hold, gen_ch=cfg["ff_ch"]))
            waveform, report = compensated_ac_waveform(
                segments=during,
                park_gain=cfg["ff_park_gain"], target_gain=cfg["ff_gain"],
                amplitude_gain=self.ac_amplitude_dac,
                modulation_mhz=self.modulation_mhz,
                sample_rate_mhz=generator["fs"],
                fabric_rate_mhz=generator["f_fabric"],
                cycles=cycles, max_gain=ff_maxv(self, scaled=True))
            self.ac_reports[str(hold)] = report
            self.ac_waveforms[str(hold)] = waveform
        park_samples = sum(
            length for channel, _, _, length in getattr(self, "_ff_ramp_cache", {})
            if channel == int(cfg["ff_ch"]))
        total_samples = park_samples + sum(len(x) for x in self.ac_waveforms.values())
        budget = ff_envelope_samples(self)
        if total_samples > budget:
            raise ValueError(f"AC flux and park envelopes need {total_samples} "
                             f"samples; generator has {budget}")
        self.ff_envelope_report = {"park_samples": park_samples,
                                   "ac_samples": total_samples - park_samples,
                                   "total_samples": total_samples,
                                   "capacity_samples": budget}
        for hold, waveform in self.ac_waveforms.items():
            name = "q3_ac_short" if float(hold) == self.holds_us[0] else "q3_ac_long"
            self.add_pulse(ch=cfg["ff_ch"], name=name, idata=waveform,
                           qdata=np.zeros_like(waveform))

    def _resident_excursion(self):
        cfg = self.cfg
        if self._t1_ff_compensation is None:
            raise ValueError("modulated T1 requires the pinned flux correction")
        park = float(cfg["ff_park_gain"])
        target = float(cfg["ff_gain"])
        hold = float(cfg["opx_resident_post_us"])
        before, during, recovery = _target_segments(
            self._t1_ff_compensation,
            pre_us=float(cfg["opx_resident_pre_us"]) + self._t1_ff_settle_us,
            hold_us=hold,
            recovery_us=self._t1_ff_predistortion_recovery_us)
        ff_pulse.play_relative_compensation_segments(self, park, target, before)
        if int(cfg["opx_modulation_amplitude_dac"]) == 0:
            ff_pulse.play_relative_compensation_segments(self, park, target, during)
        else:
            name = "q3_ac_short" if hold == self.holds_us[0] else "q3_ac_long"
            self.set_pulse_registers(
                ch=cfg["ff_ch"], freq=0, style="arb", phase=0,
                stdysel="last", gain=ff_maxv(self), waveform=name,
                outsel="input")
            self.pulse(ch=cfg["ff_ch"])
        self.sync_all(0)
        ff_pulse.play_relative_compensation_segments(self, park, target, recovery)
        ff_pulse.play_hard_step(self, park)
        self.sync_all(0)


def program_specs(center, *, amplitudes=AMPLITUDES_DAC, shots=SHOTS,
                  control_ghz=None, sites=("feature", "flank"),
                  holds_us=HOLDS_US, pre_us=PRE_US, frequencies_mhz=None,
                  settings=None):
    flank = (round(float(center) + resident.FLANK_OFFSET_GHZ, 3)
             if control_ghz is None else round(float(control_ghz), 3))
    specs = []
    if settings is not None and frequencies_mhz is not None:
        raise ValueError("explicit frequency-amplitude pairs exclude a frequency grid")
    frequencies = ((MODULATION_MHZ,) if frequencies_mhz is None else
                   tuple(float(value) for value in frequencies_mhz))
    pairs = (tuple((float(frequency), int(amplitude))
                   for frequency, amplitude in settings)
             if settings is not None else
             tuple((frequency, int(amplitude)) for amplitude in amplitudes
                   for frequency in frequencies))
    if (not pairs or len(set(pairs)) != len(pairs) or
            any(not np.isfinite(frequency) or frequency <= 0 or amplitude <= 0
                for frequency, amplitude in pairs)):
        raise ValueError("frequency sweep needs positive finite frequencies")
    for repeat in (0, 1):
        ordered_sites = tuple((site, float(center) if site == "feature" else flank)
                              for site in sites)
        ordered_pairs = pairs
        if repeat:
            ordered_sites = tuple(reversed(ordered_sites))
            ordered_pairs = tuple(reversed(pairs))
        for site, flux in ordered_sites:
            for frequency, amplitude in ordered_pairs:
                conds = conditions(flux, amplitude_dac=amplitude,
                                   reverse=bool(repeat), holds_us=holds_us,
                                   pre_us=pre_us)
                suffix = ("" if frequencies_mhz is None and settings is None else
                          f"_f{frequency:g}".replace(".", "p"))
                specs.append({"name": f"r{repeat}_{site}_a{amplitude}{suffix}",
                              "repeat": repeat, "site": site,
                              "flux_ghz": flux,
                              "amplitude_dac": amplitude,
                              "modulation_frequency_mhz": frequency,
                              "shots": int(shots),
                              "order": [c["name"] for c in conds],
                              "conditions": conds, "status": "pending"})
    return specs


def recenter_repeat(specs, *, center, repeat, control_ghz=None,
                    holds_us=HOLDS_US, pre_us=PRE_US):
    """Retarget an unacquired repeat after its own fresh loss scout."""
    flank = (round(float(center) + resident.FLANK_OFFSET_GHZ, 3)
             if control_ghz is None else round(float(control_ghz), 3))
    for entry in specs:
        if entry["repeat"] != repeat:
            continue
        if entry["status"] != "pending":
            raise ValueError("cannot retarget an acquired modulation program")
        flux = round(float(center), 3) if entry["site"] == "feature" else flank
        conds = conditions(flux, amplitude_dac=entry["amplitude_dac"],
                           reverse=bool(repeat), holds_us=holds_us,
                           pre_us=pre_us)
        entry["flux_ghz"] = flux
        entry["conditions"] = conds
        entry["order"] = [condition["name"] for condition in conds]


def block_stability(pre, mid, post):
    return {"r0": resident.feature_stable(pre, mid),
            "r1": resident.feature_stable(mid, post)}


def split_records(records, order, *, shots):
    records = list(records)
    expected = {x["name"] for x in conditions(4.136, amplitude_dac=AMPLITUDES_DAC[0])}
    if len(order) != RECORDS_PER_SHOT or set(order) != expected:
        raise ValueError("invalid eight-condition stream order")
    if len(records) != int(shots) * RECORDS_PER_SHOT:
        raise ValueError("incomplete eight-condition IQ stream")
    return {name: records[index::RECORDS_PER_SHOT]
            for index, name in enumerate(order)}


def _condition_configs(base, spec, dc_lookup):
    cfgs = []
    for cond in spec["conditions"]:
        arm = dict(cond, shots=spec["shots"])
        cfg = resident.arm_config(base, arm, dc_lookup)
        cfg["opx_modulation_amplitude_dac"] = cond["modulation_amplitude_dac"]
        cfgs.append(cfg)
    return cfgs


def _controls(scores):
    reports = {}
    for name, score in scores.items():
        site = "feature" if "_feature_" in name else "flank"
        short_floor = 0.08 if site == "feature" else 0.20
        long_floor = 0.03 if site == "feature" else 0.10
        reports[name] = {
            "usable": bool(
                min(score["short_off_contrast"], score["short_on_contrast"])
                >= short_floor and
                score["long_off_contrast"] >= long_floor and
                max(abs(score["short_cold_modulation_change"]),
                    abs(score["long_cold_modulation_change"])) <= 0.10),
            "short_hot_floor": short_floor, "long_off_hot_floor": long_floor}
    return {"programs": reports,
            "usable": all(x["usable"] for x in reports.values())}


def run(*, data_root=localizer.DATA_ROOT, correction_json=None,
        focused=False, floquet_direct=False, floquet_amplitude_sweep=False,
        floquet_frequency_sweep=False, floquet_scaling_check=False):
    if sum((bool(focused), bool(floquet_direct),
            bool(floquet_amplitude_sweep), bool(floquet_frequency_sweep),
            bool(floquet_scaling_check))) > 1:
        raise ValueError("modulation experiment modes are exclusive")
    anchored = (floquet_direct or floquet_amplitude_sweep or
                floquet_frequency_sweep or floquet_scaling_check)
    amplitudes = (tuple(sorted({amplitude for _, amplitude in
                                SCALING_PAIRS_MHZ_DAC})) if floquet_scaling_check else
                  FREQUENCY_SWEEP_AMPLITUDES_DAC if floquet_frequency_sweep else
                  SWEEP_AMPLITUDES_DAC if floquet_amplitude_sweep else
                  DIRECT_AMPLITUDES_DAC if floquet_direct else
                  (1600,) if focused else AMPLITUDES_DAC)
    frequencies = FREQUENCY_SWEEP_MHZ if floquet_frequency_sweep else None
    settings = SCALING_PAIRS_MHZ_DAC if floquet_scaling_check else None
    holds = DIRECT_HOLDS_US if anchored else HOLDS_US
    pre_us = DIRECT_PRE_US if anchored else PRE_US
    shots = (SCALING_SHOTS if floquet_scaling_check else
             FREQUENCY_SWEEP_SHOTS if floquet_frequency_sweep else
             SWEEP_SHOTS if floquet_amplitude_sweep else
             DIRECT_SHOTS if floquet_direct else 8000 if focused else SHOTS)
    midpoint = focused or anchored
    sites = (("feature",) if (floquet_amplitude_sweep or
                             floquet_frequency_sweep or floquet_scaling_check)
             else ("feature", "flank"))
    output_tag = ("TLS_Floquet_Scaling_Check" if floquet_scaling_check
                  else "TLS_Floquet_Frequency_Sweep" if floquet_frequency_sweep
                  else "TLS_Floquet_Amplitude_Sweep" if floquet_amplitude_sweep
                  else "TLS_Floquet_Direct_Loss" if floquet_direct
                  else "TLS_FluxModulated_T1")
    data_root = Path(data_root)
    correction = localizer.checked_correction(data_root, correction_json)
    scout = localizer.run(
        data_root=data_root, correction_json=correction,
        parameter_overrides={**(wide.parameters() if anchored else
                                adaptive.scout_parameters(phase="pre")),
                             "output_suffix": f"{output_tag}_Scout_pre"})
    selected = (swap.select_wide_candidate(
        swap.read_wide_scout(scout), preferred_center=3.992)
        if anchored else
        adaptive.select_loss_feature(adaptive.read_scout(scout)))
    center = round(float(selected["center_ghz"]), 3)
    flank = (round(float(selected["control_ghz"]), 3) if anchored
             else round(center + resident.FLANK_OFFSET_GHZ, 3))
    print(f"[mod-T1] feature={center:.3f} GHz; flank={flank:.3f} GHz",
          flush=True)

    with localizer.scan_environment(correction):
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import (
            FivePointApplesToApples as five, TLSSpectroscopy as tls,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ThreePointApplesToApples import (
            _integer_dc_grid,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.integration import (
            _block_timeout_s, _run_program, runtime_bundle,
        )
        from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.production import (
            ProductionResetSession,
        )

        if int(tls.BaseConfig["ff_park_gain"]) != -25146:
            raise RuntimeError("q3 park gain differs from verified configuration")
        tls.QUBIT, tls.SET_YOKO, tls.outerFolder = "q3", False, str(data_root)
        five.install_scan_calibration(tls)
        grid = np.asarray([center, flank], dtype=float)
        dc, realized = _integer_dc_grid(wide.parameters(), grid, tls)
        dc_lookup = {float(f): int(g) for f, g in zip(grid, dc)}
        compensation = tls._load_correction(str(correction), str(data_root))
        base = ProductionResetSession.passive().apply(tls.BaseConfig)
        five.apply_verified_feedback_timing(base)
        base.update({"apply_flux_tail_compensation": True,
                     "flux_tail_compensation": compensation,
                     "flux_fit_params": tls.FLUX_FIT_PARAMS,
                     "flux_settle_time_us": 0.5,
                     "flux_predistortion_return_prefix_us": 0.5,
                     "flux_predistortion_recovery_us": 40.0,
                     "flux_predistortion_overlap_payload_readout": False,
                     "flux_predistortion_round_trip_mode": "stateful",
                     "readout_thermalization_us": 10.0,
                     "ff_ramp_length": PARK_RAMP_US,
                     "qubit_pulse_style": "arb", "do_ff": True,
                     "opx_reset_scheme": "none",
                     "opx_resident_dmem_stream": True,
                     "opx_inter_shot_delay_us": 500.0})
        for hold in holds:
            _target_segments(compensation, pre_us=pre_us + 0.5,
                             hold_us=hold, recovery_us=40.0)
        session_id = (("q3_floquet_scaling_check_" if floquet_scaling_check
                       else "q3_floquet_frequency_sweep_" if floquet_frequency_sweep
                       else "q3_floquet_amplitude_sweep_" if floquet_amplitude_sweep
                       else "q3_floquet_direct_loss_" if floquet_direct else
                       "q3_flux_modulated_t1_") +
                      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                      "_" + uuid.uuid4().hex[:8])
        folder = data_root / "q3" / session_id
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / "manifest.json"
        refs = probe.reference_arms(center, phase="pre") + \
            probe.reference_arms(center, phase="post")
        for ref in refs:
            ref["shots"] = REFERENCE_SHOTS
            ref["status"] = "pending"
        manifest = {"schema": ("q3.floquet-scaling-check.v1"
                                if floquet_scaling_check else
                                "q3.floquet-frequency-sweep.v1"
                                if floquet_frequency_sweep else
                                "q3.floquet-amplitude-sweep.v1"
                                if floquet_amplitude_sweep else
                                "q3.floquet-direct-loss.v1" if floquet_direct
                                else "q3.flux-modulated-t1.v1"),
                    "status": "running", "session_id": session_id,
                    "code_commit": os.environ.get("Q3_CODE_COMMIT", "unknown"),
                    "correction_json": str(correction),
                    "correction_sha256": localizer.CORRECTION_SHA256,
                    "scout_csv": str(scout), "selected": selected,
                    "center_ghz": center, "flank_ghz": flank,
                    "dc_lookup": dc_lookup,
                    "realized_ghz": realized.tolist(),
                    "plan": plan(focused=focused, floquet_direct=floquet_direct,
                                 floquet_amplitude_sweep=floquet_amplitude_sweep,
                                 floquet_frequency_sweep=floquet_frequency_sweep,
                                 floquet_scaling_check=floquet_scaling_check),
                    "references": refs,
                    "programs": program_specs(
                        center, amplitudes=amplitudes, shots=shots,
                        control_ghz=flank if anchored else None,
                        sites=sites, holds_us=holds, pre_us=pre_us,
                        frequencies_mhz=frequencies, settings=settings)}
        protocol.checkpoint(path, manifest)
        print(f"[mod-T1] manifest={path}", flush=True)
        raw_refs = {}
        axis = None
        try:
            soc, soccfg = tls.makeProxy()
            bundle = runtime_bundle(base)
            programs = {}

            def compile_entry(entry):
                cfgs = _condition_configs(base, entry, dc_lookup)
                program = ModulatedT1Program(
                    soccfg, cfgs, bundle.payload, bundle.loop,
                    holds_us=holds, pre_us=pre_us,
                    allowed_amplitudes=amplitudes,
                    modulation_mhz=entry["modulation_frequency_mhz"])
                programs[entry["name"]] = program
                entry["waveform_reports"] = program.ac_reports
                entry["ff_envelope_report"] = program.ff_envelope_report
                for hold, samples in program.ac_waveforms.items():
                    wave_path = folder / f"{entry['name']}_waveform_{hold}.npz"
                    np.savez_compressed(wave_path, idata=samples)
                    entry.setdefault("waveform_npz", {})[hold] = str(wave_path)

            for entry in manifest["programs"]:
                if not midpoint or entry["repeat"] == 0:
                    compile_entry(entry)
            for ref in refs[:4] if midpoint else refs:
                resident.ResidentDriveProgram(
                    soccfg, resident.arm_config(base, ref, dc_lookup),
                    bundle.payload, bundle.loop)
            manifest["preflight_complete"] = not midpoint
            manifest["first_block_preflight_complete"] = True
            protocol.checkpoint(path, manifest)

            def acquire_ref(ref):
                nonlocal axis
                cfg = resident.arm_config(base, ref, dc_lookup)
                ref["status"] = "acquiring"
                protocol.checkpoint(path, manifest)
                program = resident.ResidentDriveProgram(
                    soccfg, cfg, bundle.payload, bundle.loop)
                records = _run_program(
                    soc, program, max(30.0, _block_timeout_s(cfg, REFERENCE_SHOTS)),
                    cfg, total_shots=REFERENCE_SHOTS)
                if len(records) != REFERENCE_SHOTS:
                    raise RuntimeError(f"{ref['name']}: incomplete reference IQ")
                raw_refs[ref["name"]] = records
                raw_path = folder / f"{ref['name']}.npz"
                np.savez_compressed(raw_path, i=[r.i for r in records],
                                    q=[r.q for r in records])
                ref["raw_npz"] = str(raw_path)
                if ref["name"] == "ref_e_pre":
                    axis = resident.fit_axis(
                        resident.record_iq(raw_refs["ref_g_pre"]),
                        resident.record_iq(records))
                    manifest["pre_readout_axis"] = axis
                    if not axis["valid"]:
                        raise RuntimeError("pre-run readout reference invalid")
                if axis is not None:
                    ref["excited_fraction_pre_axis"] = resident.classify(records, axis)
                ref["status"] = "complete"
                protocol.checkpoint(path, manifest)

            for ref in refs[:4]:
                print(f"[mod-T1] {ref['name']}", flush=True)
                acquire_ref(ref)
            for entry in manifest["programs"]:
                if midpoint and entry["repeat"] == 1 and "mid_selected" not in manifest:
                    mid_scout = localizer.run(
                        data_root=data_root, correction_json=correction,
                        parameter_overrides={**(wide.parameters() if anchored
                                                else adaptive.scout_parameters(phase="post")),
                                             "output_suffix": f"{output_tag}_Scout_mid"})
                    mid_selected = (swap.select_wide_candidate(
                        swap.read_wide_scout(mid_scout),
                        preferred_center=center,
                        preferred_control_offset=.014)
                        if anchored else
                        adaptive.select_loss_feature(adaptive.read_scout(mid_scout)))
                    mid_center = round(float(mid_selected["center_ghz"]), 3)
                    mid_flank = (round(float(mid_selected["control_ghz"]), 3)
                                 if anchored else
                                 round(mid_center + resident.FLANK_OFFSET_GHZ, 3))
                    recenter_repeat(manifest["programs"], center=mid_center,
                                    repeat=1,
                                    control_ghz=mid_flank if anchored else None,
                                    holds_us=holds, pre_us=pre_us)
                    mid_grid = np.asarray([mid_center, mid_flank], dtype=float)
                    mid_dc, mid_realized = _integer_dc_grid(
                        wide.parameters(), mid_grid, tls)
                    dc_lookup.update({float(f): int(g)
                                      for f, g in zip(mid_grid, mid_dc)})
                    manifest.update({"mid_scout_csv": str(mid_scout),
                                     "mid_selected": mid_selected,
                                     "mid_center_ghz": mid_center,
                                     "mid_flank_ghz": mid_flank,
                                     "mid_realized_ghz": mid_realized.tolist()})
                    for ref in refs[4:]:
                        ref["flux_ghz"] = mid_center
                        ref["drive_mhz"] = round(1000.0 * mid_center + 5.0, 3)
                        resident.ResidentDriveProgram(
                            soccfg, resident.arm_config(base, ref, dc_lookup),
                            bundle.payload, bundle.loop)
                    for future in manifest["programs"]:
                        if future["repeat"] == 1:
                            compile_entry(future)
                    manifest["preflight_complete"] = True
                    protocol.checkpoint(path, manifest)
                    print(f"[mod-T1] midpoint feature={mid_center:.3f} GHz; "
                          f"first block shift={1000*(mid_center-center):+.1f} MHz",
                          flush=True)
                print(f"[mod-T1] {entry['name']} {entry['shots']} x 8", flush=True)
                entry["status"] = "acquiring"
                protocol.checkpoint(path, manifest)
                records = _run_program(
                    soc, programs[entry["name"]],
                    max(30.0, RECORDS_PER_SHOT * _block_timeout_s(base, entry["shots"])),
                    base, total_shots=entry["shots"])
                split = split_records(records, entry["order"], shots=entry["shots"])
                for cond in entry["conditions"]:
                    subset = split[cond["name"]]
                    raw_path = folder / f"{entry['name']}_{cond['name']}.npz"
                    np.savez_compressed(raw_path, i=[r.i for r in subset],
                                        q=[r.q for r in subset])
                    cond["raw_npz"] = str(raw_path)
                    cond["excited_fraction_pre_axis"] = resident.classify(subset, axis)
                entry["status"] = "complete"
                protocol.checkpoint(path, manifest)
            for ref in refs[4:]:
                print(f"[mod-T1] {ref['name']}", flush=True)
                acquire_ref(ref)
            manifest["post_readout_score"] = resident.score_axis(
                axis, resident.record_iq(raw_refs["ref_g_post"]),
                resident.record_iq(raw_refs["ref_e_post"]))
            manifest["transfer_control"] = {
                phase: {"ground": resident.classify(
                            raw_refs[f"ref_transfer_g_{phase}"], axis),
                        "excited": resident.classify(
                            raw_refs[f"ref_transfer_e_{phase}"], axis)}
                for phase in ("pre", "post")}
            for item in manifest["transfer_control"].values():
                item["usable"] = resident.transfer_usable(item["ground"],
                                                           item["excited"])
            scores = {}
            for entry in manifest["programs"]:
                fractions = {c["name"]: c["excited_fraction_pre_axis"]
                             for c in entry["conditions"]}
                scores[entry["name"]] = score_conditions(fractions)
            manifest["program_scores"] = scores
            manifest["control_report"] = _controls(scores)
            effects = {}
            if floquet_frequency_sweep or floquet_scaling_check:
                for entry in manifest["programs"]:
                    effects[entry["name"]] = {
                        "modulation_frequency_mhz":
                            entry["modulation_frequency_mhz"],
                        "modulation_amplitude_dac": entry["amplitude_dac"],
                        "feature_modulation_survival_change":
                            scores[entry["name"]]["modulation_survival_change"]}
            else:
                for repeat in (0, 1):
                    for amplitude in amplitudes:
                        f = scores[f"r{repeat}_feature_a{amplitude}"]
                        if floquet_amplitude_sweep:
                            effects[f"r{repeat}_a{amplitude}"] = {
                                "feature_modulation_survival_change":
                                    f["modulation_survival_change"]}
                        else:
                            b = scores[f"r{repeat}_flank_a{amplitude}"]
                            effects[f"r{repeat}_a{amplitude}"] = {
                                "feature_modulation_survival_change":
                                    f["modulation_survival_change"],
                                "flank_modulation_survival_change":
                                    b["modulation_survival_change"],
                                "feature_specific_effect": feature_specific_effect(f, b)}
            manifest["effect_report"] = effects
            post_scout = localizer.run(
                data_root=data_root, correction_json=correction,
                parameter_overrides={**(wide.parameters() if anchored else
                                        adaptive.scout_parameters(phase="post")),
                                     "output_suffix": f"{output_tag}_Scout_post"})
            manifest["post_scout_csv"] = str(post_scout)
            try:
                manifest["post_selected"] = (swap.select_wide_candidate(
                    swap.read_wide_scout(post_scout),
                    preferred_center=(manifest["mid_center_ghz"]
                                      if midpoint else center),
                    preferred_control_offset=.014)
                    if anchored else
                    adaptive.select_loss_feature(adaptive.read_scout(post_scout)))
            except ValueError as exc:
                manifest["post_selection_error"] = str(exc)
            if midpoint and "post_selected" in manifest:
                manifest["block_stability"] = block_stability(
                    selected, manifest["mid_selected"], manifest["post_selected"])
                manifest["feature_stable"] = all(
                    manifest["block_stability"].values())
            else:
                manifest["feature_stable"] = (
                    resident.feature_stable(selected, manifest["post_selected"])
                    if "post_selected" in manifest else False)
            valid = (manifest["post_readout_score"]["valid"] and
                     all(x["usable"] for x in manifest["transfer_control"].values()) and
                     manifest["control_report"]["usable"] and
                     manifest["feature_stable"])
            manifest["status"] = "complete" if valid else "complete_controls_unstable"
            protocol.checkpoint(path, manifest)
            print(f"[mod-T1] {manifest['status']}: {path}", flush=True)
            return path
        except BaseException as exc:
            manifest["status"] = "failed"
            manifest["error"] = f"{type(exc).__name__}: {exc}"
            protocol.checkpoint(path, manifest)
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--focused", action="store_true",
                        help="1600-DAC repeat with a fresh midpoint feature scout")
    parser.add_argument("--floquet-direct", action="store_true",
                        help="short-predwell 1.6/5.6-us direct AC-on/off loss comparison")
    parser.add_argument("--floquet-amplitude-sweep", action="store_true",
                        help="repeat the direct 30-MHz loss test over ten AC amplitudes")
    parser.add_argument("--floquet-frequency-sweep", action="store_true",
                        help="compare the direct loss response at 20, 30, and 40 MHz")
    parser.add_argument("--floquet-scaling-check", action="store_true",
                        help="test equal A/f pairs against fixed-amplitude loss controls")
    parser.add_argument("--data-root", type=Path, default=localizer.DATA_ROOT)
    parser.add_argument("--correction-json", type=Path)
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(plan(focused=args.focused,
                              floquet_direct=args.floquet_direct,
                              floquet_amplitude_sweep=args.floquet_amplitude_sweep,
                              floquet_frequency_sweep=args.floquet_frequency_sweep,
                              floquet_scaling_check=args.floquet_scaling_check),
                         indent=2))
    else:
        run(data_root=args.data_root, correction_json=args.correction_json,
            focused=args.focused, floquet_direct=args.floquet_direct,
            floquet_amplitude_sweep=args.floquet_amplitude_sweep,
            floquet_frequency_sweep=args.floquet_frequency_sweep,
            floquet_scaling_check=args.floquet_scaling_check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
