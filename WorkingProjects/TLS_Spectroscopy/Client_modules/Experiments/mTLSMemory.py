import datetime

import numpy as np
from qick import AveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import discriminate_shots
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset, ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import acquire_with_retry, suppress_stdout
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import add_qubit_gaussian, set_readout_pulse


MEMORY_SEQUENCES = ("single", "double", "ground_double")


class TLSMemoryProgram(AveragerProgram):

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def _set_qubit_pulse(self, gain=None, waveform="qubit", freq_mhz=None):
        cfg = self.cfg
        self.set_pulse_registers(
            ch=cfg["qubit_ch"], style="arb",
            freq=self.freq2reg(
                float(cfg["qubit_pi_freq"] if freq_mhz is None else freq_mhz),
                gen_ch=cfg["qubit_ch"]),
            phase=self.deg2reg(0.0, gen_ch=cfg["qubit_ch"]),
            gain=int(cfg["qubit_pi_gain"] if gain is None else gain),
            waveform=waveform)

    def initialize(self):
        cfg = self.cfg
        cfg["reps"] = int(cfg["shots"])
        sequence = str(cfg.get("memory_sequence", "double")).lower()
        if sequence not in MEMORY_SEQUENCES:
            raise ValueError(f"memory_sequence must be one of {MEMORY_SEQUENCES}")
        if str(cfg.get("qubit_pulse_style", "arb")).lower() != "arb":
            raise ValueError("TLSMemoryProgram requires an arb qubit pulse")
        interaction_us = float(cfg.get("memory_interaction_us", 0.0))
        storage_us = float(cfg.get("memory_storage_us", 0.0))
        if not np.isfinite(interaction_us) or interaction_us < 0.0:
            raise ValueError("memory_interaction_us must be finite and non-negative")
        if not np.isfinite(storage_us) or storage_us < 0.0:
            raise ValueError("memory_storage_us must be finite and non-negative")
        self.memory_sequence = sequence
        self.memory_storage_us = storage_us
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
            add_qubit_gaussian(
                self, name="qubit_reset",
                sigma_us=float(cfg.get("reset_pi_sigma", cfg["sigma"])),
                drag_beta=float(cfg.get(
                    "reset_pi_drag_beta", cfg.get("qubit_drag_beta", 0.0))))
        self._set_qubit_pulse()
        set_readout_pulse(self, self._read_freq_reg)
        park_gain = float(cfg.get("ff_park_gain", 0) or 0)
        stepping = abs(float(cfg["ff_gain"]) - park_gain) > 0.0
        self.ff_settle_us = ff_pulse.flux_settle_us(cfg) if stepping else 0.0
        self.ff_park_segs = ff_pulse.build_park_hold(
            self, hold_us=ff_pulse.flux_settle_us(cfg))
        self.ff_segs = ff_pulse.build_ramp_hold_ramp(
            self, hold_us=interaction_us + self.ff_settle_us,
            ff_gain=float(cfg["ff_gain"]),
            dt_play_us=cfg.get("dt_pulseplay", 5.0),
            ramp_us=cfg.get("ff_ramp_length", ff_pulse.STATE_SAFE_RAMP_US),
            dt_def_us=cfg.get("dt_pulsedef", 0.002),
            compensation=ff_pulse.load_compensation(cfg),
            distortion_model=ff_pulse.make_distortion_model(self))
        self.excursion_total_us = (
            interaction_us + 2.0 * self.ff_settle_us
            + 2.0 * float(cfg.get("ff_ramp_length", ff_pulse.STATE_SAFE_RAMP_US))
            + 0.010)
        self.synci(200)

    def _play_excursion(self):
        cfg = self.cfg
        ff_pulse.play_ramp_up_hold(
            self, self.ff_segs, dt_play_us=cfg.get("dt_pulseplay", 5.0))
        self.sync_all(self.us2cycles(0.010))
        ff_pulse.play_ramp_down(self, self.ff_segs)
        self.sync_all(self.us2cycles(self.ff_settle_us))

    def _idle_excursion(self):
        self.sync_all(self.us2cycles(self.excursion_total_us))

    def body(self):
        cfg = self.cfg
        ff_pulse.play_park_up(self, self.ff_park_segs)
        if active_reset.uses_feedback(cfg):
            reset_read_gain = cfg.get("reset_read_pulse_gain")
            if reset_read_gain is not None:
                set_readout_pulse(self, self._read_freq_reg, gain=int(reset_read_gain))
            self._set_qubit_pulse(
                gain=int(cfg.get("reset_pi_gain", cfg["qubit_pi_gain"])),
                waveform="qubit_reset",
                freq_mhz=cfg.get("reset_pi_freq", cfg["qubit_pi_freq"]))
            active_reset.active_reset_block(
                self, ro_ch=cfg["ro_chs"][0],
                threshold_raw=cfg["reset_threshold_raw"],
                oper=cfg.get("reset_oper", "lower"),
                ground_below=cfg.get("reset_ground_below", True),
                max_iters=int(cfg.get("reset_max_iters", 3)))
            self._set_qubit_pulse()
            if reset_read_gain is not None:
                set_readout_pulse(self, self._read_freq_reg)
        if active_reset.heralds(cfg):
            self.measure(
                pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
                adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
                wait=True, syncdelay=self.us2cycles(cfg.get("herald_delay", 8.0)))
        if self.memory_sequence != "ground_double":
            self.pulse(ch=cfg["qubit_ch"])
            self.sync_all(self.us2cycles(0.010))
        self._play_excursion()
        self.sync_all(self.us2cycles(self.memory_storage_us))
        if self.memory_sequence in ("double", "ground_double"):
            self._play_excursion()
        else:
            self._idle_excursion()
        self.measure(
            pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
            adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
            wait=True, syncdelay=self.us2cycles(0.01))
        ff_pulse.play_park_down(self, self.ff_park_segs)
        self.sync_all(self.us2cycles(
            cfg.get("active_reset_post_measure_delay_us", 0.05)
            if active_reset.uses_feedback(cfg) else cfg["relax_delay"]))

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


class TLSMemory(ExperimentClass):

    def __init__(self, *args, ff_gain=None, interaction_us=0.0, storage_us=0.0,
                 sequence="double", shots=400, calib_params=None,
                 assignment_reference=None, **kw):
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
        sequence = str(sequence).lower()
        if sequence not in MEMORY_SEQUENCES:
            raise ValueError(f"sequence must be one of {MEMORY_SEQUENCES}")
        cfg.update({
            "ff_gain": float(ff_gain),
            "memory_interaction_us": float(interaction_us),
            "memory_storage_us": float(storage_us),
            "memory_sequence": sequence,
            "shots": int(shots),
            "reps": int(shots),
        })
        kw["cfg"] = cfg
        super().__init__(*args, **kw)
        self.ff_gain = float(ff_gain)
        self.interaction_us = float(interaction_us)
        self.storage_us = float(storage_us)
        self.sequence = sequence
        self.shots = int(shots)
        self.calib_params = dict(calib_params)
        self.assignment_reference = {
            "P_g": float(assignment_reference["P_g"]),
            "P_e": float(assignment_reference["P_e"]),
        }

    def acquire(self, progress=False, plotDisp=False):
        with suppress_stdout():
            prog = TLSMemoryProgram(self.soccfg, dict(self.cfg))
            hi, hq, i, q = acquire_with_retry(
                prog, self.soc, load_pulses=True, progress=False)
        final = discriminate_shots(i, q, self.calib_params)
        if active_reset.heralds(self.cfg):
            keep = active_reset.herald_keep(hi, hq, self.calib_params)
        else:
            keep = np.ones(final.size, dtype=bool)
        probability = float(np.mean(final[keep])) if np.any(keep) else np.nan
        contrast = self.assignment_reference["P_e"] - self.assignment_reference["P_g"]
        corrected = ((probability - self.assignment_reference["P_g"]) / contrast
                     if np.isfinite(contrast) and contrast > 0.0 else np.nan)
        self.raw = {"herald_i": hi, "herald_q": hq, "i": i, "q": q}
        self.metrics = {
            "P_excited": probability,
            "population_corrected": float(corrected),
            "keep_fraction": float(np.mean(keep)),
        }
        self.data = {
            "meta_dict": dict(self.cfg),
            "ff_gain": self.ff_gain,
            "interaction_us": self.interaction_us,
            "storage_us": self.storage_us,
            "sequence": self.sequence,
            "shots": self.shots,
            "calib_params": dict(self.calib_params),
            "assignment_reference": dict(self.assignment_reference),
            "metrics": dict(self.metrics),
            "raw": dict(self.raw),
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        return self.data
