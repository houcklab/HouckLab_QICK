import datetime

import numpy as np
from qick import AveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import discriminate_shots
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset, ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import (
    acquire_with_retry, split_reps, suppress_stdout,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    add_qubit_gaussian, set_readout_pulse,
)


RAMSEY_ARMS = ("g", "e", "i", "q")


class RoundTripRamseyProgram(AveragerProgram):

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def _set_qubit_pulse(self, gain, phase_deg, waveform="qubit", freq_mhz=None):
        cfg = self.cfg
        frequency = cfg["qubit_pi_freq"] if freq_mhz is None else freq_mhz
        self.set_pulse_registers(
            ch=cfg["qubit_ch"], style="arb",
            freq=self.freq2reg(float(frequency),
                               gen_ch=cfg["qubit_ch"]),
            phase=self.deg2reg(float(phase_deg), gen_ch=cfg["qubit_ch"]),
            gain=int(gain), waveform=waveform)

    def _arm(self):
        arm = str(self.cfg.get("ramsey_arm", "g")).lower()
        if arm not in RAMSEY_ARMS:
            raise ValueError(f"ramsey_arm must be one of {RAMSEY_ARMS}, got {arm!r}")
        return arm

    def _set_arm_prep(self):
        cfg = self.cfg
        arm = self._arm()
        if arm == "e":
            gain = int(cfg["qubit_pi_gain"])
        elif arm in ("i", "q"):
            gain = int(cfg["qubit_pi2_gain"])
        else:
            gain = 0
        self._set_qubit_pulse(gain, 0.0)

    def initialize(self):
        cfg = self.cfg
        cfg["reps"] = int(cfg["shots"])
        if str(cfg.get("qubit_pulse_style", "arb")).lower() != "arb":
            raise ValueError("RoundTripRamseyProgram requires an arb qubit pulse")
        for key in ("qubit_pi_gain", "qubit_pi2_gain", "qubit_pi_freq"):
            if key not in cfg or not np.isfinite(float(cfg[key])):
                raise ValueError(f"{key} must be finite")
        if int(cfg["qubit_pi_gain"]) <= 0 or int(cfg["qubit_pi2_gain"]) <= 0:
            raise ValueError("qubit_pi_gain and qubit_pi2_gain must be positive")
        self._arm()
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg.get("mixer_freq", 0), ro_ch=cfg["ro_chs"][0])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])
        ff_pulse.declare_ff(self)
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ro_ch, freq=cfg["read_pulse_freq"],
                length=self.us2cycles(cfg["read_length"], ro_ch=cfg["ro_chs"][0]),
                gen_ch=cfg["res_ch"])
        self._read_freq_reg = self.freq2reg(
            cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])
        add_qubit_gaussian(self)
        if active_reset.uses_feedback(cfg):
            reset_read_freq = float(cfg.get(
                "reset_read_pulse_freq", cfg["read_pulse_freq"]))
            if not np.isclose(reset_read_freq, float(cfg["read_pulse_freq"]),
                              rtol=0.0, atol=1e-9):
                raise ValueError("feedback reset and scoring readout must share one ADC/DDC frequency")
            add_qubit_gaussian(
                self, name="qubit_reset",
                sigma_us=float(cfg.get("reset_pi_sigma", cfg["sigma"])),
                drag_beta=float(cfg.get(
                    "reset_pi_drag_beta", cfg.get("qubit_drag_beta", 0.0))))
        self._set_arm_prep()
        set_readout_pulse(self, self._read_freq_reg)
        hold_us = float(cfg.get("ramsey_flux_hold_us", 1.0))
        if not np.isfinite(hold_us) or hold_us < 0.0:
            raise ValueError("ramsey_flux_hold_us must be finite and non-negative")
        park_gain = float(cfg.get("ff_park_gain", 0) or 0)
        stepping = abs(float(cfg["ff_gain"]) - park_gain) > 0
        self.park_idle_only = bool(cfg.get("ramsey_park_idle_only", False))
        if self.park_idle_only and stepping:
            raise ValueError("ramsey_park_idle_only requires ff_gain == ff_park_gain")
        self.ramsey_echo = bool(cfg.get("ramsey_echo", False))
        segment_hold_us = hold_us / 2.0 if self.ramsey_echo else hold_us
        self.ramsey_idle_segment_us = segment_hold_us
        self.ff_settle_us = ff_pulse.flux_settle_us(cfg) if stepping else 0.0
        self.ff_segs = None if self.park_idle_only else ff_pulse.build_ramp_hold_ramp(
                self, hold_us=segment_hold_us + self.ff_settle_us,
                ff_gain=float(cfg["ff_gain"]),
                dt_play_us=cfg.get("dt_pulseplay", 5.0),
                ramp_us=cfg.get("ff_ramp_length", ff_pulse.STATE_SAFE_RAMP_US),
                dt_def_us=cfg.get("dt_pulsedef", 0.002),
                compensation=ff_pulse.load_compensation(cfg),
                distortion_model=ff_pulse.make_distortion_model(self))
        self.synci(200)

    def _play_excursion(self):
        cfg = self.cfg
        if self.ff_segs is None:
            echo = bool(self.__dict__.get(
                "ramsey_echo", cfg.get("ramsey_echo", False)))
            fallback = float(cfg.get("ramsey_flux_hold_us", 0.0)) / (2.0 if echo else 1.0)
            self.sync_all(self.us2cycles(self.__dict__.get(
                "ramsey_idle_segment_us", fallback)))
        else:
            ff_pulse.play_ramp_up_hold(
                self, self.ff_segs, dt_play_us=cfg.get("dt_pulseplay", 5.0))
            self.sync_all(self.us2cycles(0.010))
            ff_pulse.play_ramp_down(self, self.ff_segs)
            self.sync_all(self.us2cycles(ff_pulse.flux_settle_us(cfg)))

    def body(self):
        cfg = self.cfg
        arm = self._arm()
        if self.ff_segs is not None:
            ff_pulse.assert_park(self, self.ff_segs)
        if active_reset.uses_feedback(cfg):
            reset_read_gain = cfg.get("reset_read_pulse_gain")
            if reset_read_gain is not None:
                set_readout_pulse(
                    self, self._read_freq_reg, gain=int(reset_read_gain))
            self._set_qubit_pulse(
                int(cfg.get("reset_pi_gain", cfg["qubit_pi_gain"])), 0.0,
                "qubit_reset", cfg.get("reset_pi_freq", cfg["qubit_pi_freq"]))
            active_reset.active_reset_block(
                self, ro_ch=cfg["ro_chs"][0],
                threshold_raw=cfg["reset_threshold_raw"],
                oper=cfg.get("reset_oper", "lower"),
                ground_below=cfg.get("reset_ground_below", True),
                max_iters=int(cfg.get("reset_max_iters", 3)))
            self._set_arm_prep()
            if reset_read_gain is not None:
                set_readout_pulse(self, self._read_freq_reg)
        if active_reset.heralds(cfg):
            self.measure(
                pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                wait=True, syncdelay=self.us2cycles(cfg.get("herald_delay", 8.0)))
        if arm != "g":
            self.pulse(ch=cfg["qubit_ch"])
            self.sync_all(self.us2cycles(0.010))
        self._play_excursion()
        if bool(self.__dict__.get("ramsey_echo", cfg.get("ramsey_echo", False))):
            if arm in ("i", "q"):
                self._set_qubit_pulse(
                    int(cfg["qubit_pi_gain"]),
                    float(cfg.get("ramsey_echo_phase_deg", 0.0)))
                self.pulse(ch=cfg["qubit_ch"])
                self.sync_all(self.us2cycles(0.010))
            else:
                self.sync_all(self.us2cycles(4.0 * float(cfg["sigma"]) + 0.010))
            self._play_excursion()
        if arm in ("i", "q"):
            phase = 0.0 if arm == "i" else float(cfg.get("ramsey_q_phase_deg", 90.0))
            self._set_qubit_pulse(int(cfg["qubit_pi2_gain"]), phase)
            self.pulse(ch=cfg["qubit_ch"])
            self.sync_all(self.us2cycles(0.010))
        self.measure(
            pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
            adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
            wait=True, syncdelay=self.us2cycles(cfg["relax_delay"]))

    def acquire(self, soc, load_pulses=True, progress=False, **kw):
        n_reset = active_reset.active_reset_readouts(self.cfg)
        n_herald = int(active_reset.heralds(self.cfg))
        super().acquire(
            soc, load_pulses=load_pulses,
            readouts_per_experiment=1 + n_reset + n_herald, progress=progress)
        return self.collect_shots()

    def collect_shots(self):
        length = self.us2cycles(
            self.cfg["read_length"], ro_ch=self.cfg["ro_chs"][0])
        n_reset = active_reset.active_reset_readouts(self.cfg)
        n_herald = int(active_reset.heralds(self.cfg))
        reads = 1 + n_reset + n_herald
        shots_i = self.di_buf[0].reshape((self.cfg["reps"], reads)) / length
        shots_q = self.dq_buf[0].reshape((self.cfg["reps"], reads)) / length
        if n_herald:
            return (shots_i[:, n_reset], shots_q[:, n_reset],
                    shots_i[:, n_reset + 1], shots_q[:, n_reset + 1])
        empty = np.full(self.cfg["reps"], np.nan)
        return empty, empty.copy(), shots_i[:, n_reset], shots_q[:, n_reset]


class RoundTripRamsey(ExperimentClass):

    def __init__(self, *args, ff_gain=None, flux_hold_us=1.0, shots=250,
                 rounds=5, calib_params=None, min_reference_contrast=0.05,
                 assignment_reference=None, save=False, **kw):
        cfg = dict(kw.get("cfg") or {})
        if ff_gain is None:
            ff_gain = cfg.get("ff_gain")
        if ff_gain is None:
            raise ValueError("ff_gain is required")
        if calib_params is None:
            calib_params = cfg.get("calib_params")
        if calib_params is None:
            raise ValueError("calib_params is required")
        if assignment_reference is None:
            assignment_reference = cfg.get("assignment_reference")
        if assignment_reference is None:
            raise ValueError("assignment_reference is required")
        if "P_g" not in assignment_reference or "P_e" not in assignment_reference:
            raise ValueError("assignment_reference must contain P_g and P_e")
        cfg["ff_gain"] = float(ff_gain)
        cfg["ramsey_flux_hold_us"] = float(flux_hold_us)
        cfg["shots"] = int(shots)
        cfg["reps"] = int(shots)
        kw["cfg"] = cfg
        super().__init__(*args, **kw)
        self.ff_gain = float(ff_gain)
        self.flux_hold_us = float(flux_hold_us)
        self.shots = int(shots)
        self.rounds = max(1, min(int(rounds), self.shots))
        self.calib_params = dict(calib_params)
        self.assignment_reference = {
            "P_g": float(assignment_reference["P_g"]),
            "P_e": float(assignment_reference["P_e"]),
        }
        self.min_reference_contrast = float(min_reference_contrast)
        self.save = bool(save)

    def acquire(self, progress=False, plotDisp=False):
        pieces = {arm: {name: [] for name in ("herald_i", "herald_q", "i", "q")}
                  for arm in RAMSEY_ARMS}
        orders = (
            ("g", "e", "i", "q"),
            ("q", "i", "e", "g"),
            ("e", "g", "q", "i"),
            ("i", "q", "g", "e"),
        )
        visit_orders = []
        for round_index, reps in enumerate(split_reps(self.shots, self.rounds)):
            if reps <= 0:
                continue
            order = orders[round_index % len(orders)]
            visit_orders.append(order)
            for arm in order:
                cfg = dict(self.cfg)
                cfg["ramsey_arm"] = arm
                cfg["shots"] = cfg["reps"] = int(reps)
                with suppress_stdout():
                    prog = RoundTripRamseyProgram(self.soccfg, cfg)
                    hi, hq, i, q = acquire_with_retry(
                        prog, self.soc, load_pulses=True, progress=False)
                pieces[arm]["herald_i"].append(np.asarray(hi, dtype=float))
                pieces[arm]["herald_q"].append(np.asarray(hq, dtype=float))
                pieces[arm]["i"].append(np.asarray(i, dtype=float))
                pieces[arm]["q"].append(np.asarray(q, dtype=float))
        self.raw = {
            arm: {name: np.concatenate(parts) for name, parts in values.items()}
            for arm, values in pieces.items()
        }
        probabilities = {}
        keep_fraction = {}
        for arm in RAMSEY_ARMS:
            values = self.raw[arm]
            final = discriminate_shots(values["i"], values["q"], self.calib_params)
            if active_reset.heralds(self.cfg):
                keep = active_reset.herald_keep(
                    values["herald_i"], values["herald_q"], self.calib_params)
            else:
                keep = np.ones(final.size, dtype=bool)
            probabilities[arm] = float(np.mean(final[keep])) if np.any(keep) else np.nan
            keep_fraction[arm] = float(np.mean(keep))
        contrast = probabilities["e"] - probabilities["g"]
        local_valid = bool(
            np.isfinite(contrast) and contrast >= self.min_reference_contrast)
        assignment_g = self.assignment_reference["P_g"]
        assignment_e = self.assignment_reference["P_e"]
        assignment_contrast = assignment_e - assignment_g
        valid = bool(np.isfinite(assignment_contrast)
                     and assignment_contrast >= self.min_reference_contrast)
        if valid:
            corrected = {
                arm: (probabilities[arm] - assignment_g) / assignment_contrast
                for arm in RAMSEY_ARMS
            }
            ramsey_i = 2.0 * corrected["i"] - 1.0
            ramsey_q = 2.0 * corrected["q"] - 1.0
            magnitude = float(np.hypot(ramsey_i, ramsey_q))
            phase = float(np.arctan2(ramsey_q, ramsey_i))
        else:
            corrected = {arm: np.nan for arm in RAMSEY_ARMS}
            ramsey_i = ramsey_q = magnitude = phase = np.nan
        self.metrics = {
            "P_g": probabilities["g"],
            "P_e": probabilities["e"],
            "P_i": probabilities["i"],
            "P_q": probabilities["q"],
            "reference_contrast": contrast,
            "local_reference_valid": float(local_valid),
            "assignment_P_g": assignment_g,
            "assignment_P_e": assignment_e,
            "assignment_contrast": assignment_contrast,
            "population_g": corrected["g"],
            "population_e": corrected["e"],
            "ramsey_i": ramsey_i,
            "ramsey_q": ramsey_q,
            "coherence_magnitude": magnitude,
            "coherence_phase_rad": phase,
            "valid": float(valid),
        }
        for arm in RAMSEY_ARMS:
            self.metrics[f"keep_fraction_{arm}"] = keep_fraction[arm]
        self.data = {
            "meta_dict": dict(self.cfg),
            "ff_gain": self.ff_gain,
            "flux_hold_us": self.flux_hold_us,
            "shots_per_arm": self.shots,
            "rounds": self.rounds,
            "arm_visit_orders": visit_orders,
            "calib_params": dict(self.calib_params),
            "assignment_reference": dict(self.assignment_reference),
            "metrics": dict(self.metrics),
            "raw": self.raw,
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if self.save:
            self.pickle_data()
        return self.data
