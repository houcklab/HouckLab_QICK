import datetime

import numpy as np
from qick import AveragerProgram

from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mSingleShot1Q import discriminate_shots
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import active_reset, ff_pulse
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import acquire_with_retry, suppress_stdout
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import add_qubit_gaussian, set_readout_pulse


SATURATION_ARMS = ("no_pump", "pump")


class TLSSaturationProbeProgram(AveragerProgram):

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def _set_park_pi(self, waveform="qubit", gain=None, freq_mhz=None):
        cfg = self.cfg
        self.set_pulse_registers(
            ch=cfg["qubit_ch"], style="arb",
            freq=self.freq2reg(
                float(cfg["qubit_pi_freq"] if freq_mhz is None else freq_mhz),
                gen_ch=cfg["qubit_ch"]),
            phase=self.deg2reg(0.0, gen_ch=cfg["qubit_ch"]),
            gain=int(cfg["qubit_pi_gain"] if gain is None else gain),
            waveform=waveform)

    def _set_pump(self):
        cfg = self.cfg
        enabled = self.saturation_arm == "pump"
        self.set_pulse_registers(
            ch=cfg["qubit_ch"], style="const",
            freq=self.freq2reg(float(cfg["saturation_pump_freq_mhz"]),
                               gen_ch=cfg["qubit_ch"]),
            phase=self.deg2reg(0.0, gen_ch=cfg["qubit_ch"]),
            gain=int(cfg["saturation_pump_gain"] if enabled else 0),
            length=self.us2cycles(self.pump_tone_us, gen_ch=cfg["qubit_ch"]))

    def initialize(self):
        cfg = self.cfg
        cfg["reps"] = int(cfg["shots"])
        arm = str(cfg.get("saturation_arm", "no_pump")).lower()
        if arm not in SATURATION_ARMS:
            raise ValueError(f"saturation_arm must be one of {SATURATION_ARMS}")
        if not active_reset.uses_feedback(cfg):
            raise ValueError("TLSSaturationProbeProgram requires feedback reset")
        if not cfg.get("rot_reset"):
            raise ValueError("TLSSaturationProbeProgram requires rotated feedback reset")
        if str(cfg.get("qubit_pulse_style", "arb")).lower() != "arb":
            raise ValueError("TLSSaturationProbeProgram requires an arb park pi pulse")
        pump_us = float(cfg.get("saturation_pump_us", 0.0))
        probe_us = float(cfg.get("saturation_probe_us", 0.0))
        recovery_us = float(cfg.get("saturation_recovery_us", 0.0))
        if not np.isfinite([pump_us, probe_us, recovery_us]).all():
            raise ValueError("saturation durations must be finite")
        if pump_us <= 0.0 or probe_us < 0.0 or recovery_us < 0.0:
            raise ValueError("pump duration must be positive and other durations non-negative")
        pump_gain = int(cfg.get("saturation_pump_gain", 0))
        if pump_gain <= 0:
            raise ValueError("saturation_pump_gain must be positive")
        self.saturation_arm = arm
        self.recovery_us = recovery_us
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
        add_qubit_gaussian(
            self, name="qubit_reset",
            sigma_us=float(cfg.get("reset_pi_sigma", cfg["sigma"])),
            drag_beta=float(cfg.get(
                "reset_pi_drag_beta", cfg.get("qubit_drag_beta", 0.0))))
        self._set_park_pi()
        set_readout_pulse(self, self._read_freq_reg)
        park_gain = float(cfg.get("ff_park_gain", 0) or 0)
        stepping = abs(float(cfg["ff_gain"]) - park_gain) > 0.0
        self.ff_settle_us = ff_pulse.flux_settle_us(cfg) if stepping else 0.0
        self.ff_park_segs = ff_pulse.build_park_hold(
            self, hold_us=ff_pulse.flux_settle_us(cfg))
        common = {
            "ff_gain": float(cfg["ff_gain"]),
            "dt_play_us": cfg.get("dt_pulseplay", 5.0),
            "ramp_us": cfg.get("ff_ramp_length", ff_pulse.STATE_SAFE_RAMP_US),
            "dt_def_us": cfg.get("dt_pulsedef", 0.002),
            "compensation": ff_pulse.load_compensation(cfg),
            "distortion_model": ff_pulse.make_distortion_model(self),
        }
        self.pump_segs = ff_pulse.build_ramp_hold_ramp(
            self, hold_us=pump_us + self.ff_settle_us,
            name_prefix="saturation_pump", **common)
        self.probe_segs = ff_pulse.build_ramp_hold_ramp(
            self, hold_us=probe_us + self.ff_settle_us,
            name_prefix="saturation_probe", **common)
        self.pump_tone_us = (
            pump_us + self.ff_settle_us
            + float(cfg.get("ff_ramp_length", ff_pulse.STATE_SAFE_RAMP_US)))
        self.synci(200)

    def _pump_excursion(self):
        cfg = self.cfg
        self._set_pump()
        self.pulse(ch=cfg["qubit_ch"])
        ff_pulse.play_ramp_up_hold(
            self, self.pump_segs, dt_play_us=cfg.get("dt_pulseplay", 5.0))
        self.sync_all(self.us2cycles(0.010))
        ff_pulse.play_ramp_down(self, self.pump_segs)
        self.sync_all(self.us2cycles(self.ff_settle_us))

    def _reset_qubit(self):
        cfg = self.cfg
        reset_read_gain = cfg.get("reset_read_pulse_gain")
        if reset_read_gain is not None:
            set_readout_pulse(self, self._read_freq_reg, gain=int(reset_read_gain))
        self._set_park_pi(
            waveform="qubit_reset",
            gain=int(cfg.get("reset_pi_gain", cfg["qubit_pi_gain"])),
            freq_mhz=cfg.get("reset_pi_freq", cfg["qubit_pi_freq"]))
        active_reset.active_reset_block(
            self, ro_ch=cfg["ro_chs"][0],
            threshold_raw=cfg["reset_threshold_raw"],
            oper=cfg.get("reset_oper", "lower"),
            ground_below=cfg.get("reset_ground_below", True),
            max_iters=int(cfg.get("reset_max_iters", 3)),
            thermalization_us=float(cfg.get("saturation_reset_thermalization_us", 0.0)))
        self._set_park_pi()
        if reset_read_gain is not None:
            set_readout_pulse(self, self._read_freq_reg)

    def _probe_excursion(self):
        cfg = self.cfg
        self.pulse(ch=cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.010))
        ff_pulse.play_ramp_up_hold(
            self, self.probe_segs, dt_play_us=cfg.get("dt_pulseplay", 5.0))
        self.sync_all(self.us2cycles(0.010))
        ff_pulse.play_ramp_down(self, self.probe_segs)
        self.sync_all(self.us2cycles(self.ff_settle_us))

    def body(self):
        cfg = self.cfg
        ff_pulse.play_park_up(self, self.ff_park_segs)
        self._pump_excursion()
        self._reset_qubit()
        self.sync_all(self.us2cycles(self.recovery_us))
        self._probe_excursion()
        self.measure(
            pulse_ch=cfg["res_ch"], adcs=cfg["ro_chs"],
            adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
            wait=True, syncdelay=self.us2cycles(0.01))
        ff_pulse.play_park_down(self, self.ff_park_segs)
        self.sync_all(self.us2cycles(
            cfg.get("active_reset_post_measure_delay_us", 0.05)))

    def acquire(self, soc, load_pulses=True, progress=False, **kw):
        n_reset = active_reset.active_reset_readouts(self.cfg)
        super().acquire(
            soc, load_pulses=load_pulses,
            readouts_per_experiment=n_reset + 1, progress=progress)
        return self.collect_shots()

    def collect_shots(self):
        length = self.us2cycles(
            self.cfg["read_length"], ro_ch=self.cfg["ro_chs"][0])
        n_reset = active_reset.active_reset_readouts(self.cfg)
        reads = n_reset + 1
        shots_i = self.di_buf[0].reshape((self.cfg["reps"], reads)) / length
        shots_q = self.dq_buf[0].reshape((self.cfg["reps"], reads)) / length
        return shots_i[:, :n_reset], shots_q[:, :n_reset], shots_i[:, -1], shots_q[:, -1]


class TLSSaturationProbe(ExperimentClass):

    def __init__(self, *args, ff_gain=None, target_freq_mhz=None, pump_gain=None,
                 pump_us=10.0, probe_us=5.0, recovery_us=0.0,
                 arm="no_pump", shots=400, calib_params=None,
                 assignment_reference=None, **kw):
        cfg = dict(kw.get("cfg") or {})
        if ff_gain is None:
            ff_gain = cfg.get("ff_gain")
        if target_freq_mhz is None:
            target_freq_mhz = cfg.get("saturation_pump_freq_mhz")
        if pump_gain is None:
            pump_gain = cfg.get("saturation_pump_gain")
        if ff_gain is None or target_freq_mhz is None or pump_gain is None:
            raise ValueError("ff_gain, target_freq_mhz, and pump_gain are required")
        if calib_params is None:
            calib_params = cfg.get("calib_params")
        if calib_params is None:
            raise ValueError("calib_params is required")
        if assignment_reference is None:
            assignment_reference = cfg.get("assignment_reference")
        if assignment_reference is None:
            raise ValueError("assignment_reference is required")
        arm = str(arm).lower()
        if arm not in SATURATION_ARMS:
            raise ValueError(f"arm must be one of {SATURATION_ARMS}")
        cfg.update({
            "ff_gain": float(ff_gain),
            "saturation_pump_freq_mhz": float(target_freq_mhz),
            "saturation_pump_gain": int(pump_gain),
            "saturation_pump_us": float(pump_us),
            "saturation_probe_us": float(probe_us),
            "saturation_recovery_us": float(recovery_us),
            "saturation_arm": arm,
            "shots": int(shots),
            "reps": int(shots),
        })
        kw["cfg"] = cfg
        super().__init__(*args, **kw)
        self.ff_gain = float(ff_gain)
        self.target_freq_mhz = float(target_freq_mhz)
        self.pump_gain = int(pump_gain)
        self.pump_us = float(pump_us)
        self.probe_us = float(probe_us)
        self.recovery_us = float(recovery_us)
        self.arm = arm
        self.shots = int(shots)
        self.calib_params = dict(calib_params)
        self.assignment_reference = {
            "P_g": float(assignment_reference["P_g"]),
            "P_e": float(assignment_reference["P_e"]),
        }

    def acquire(self, progress=False, plotDisp=False):
        with suppress_stdout():
            prog = TLSSaturationProbeProgram(self.soccfg, dict(self.cfg))
            reset_i, reset_q, i, q = acquire_with_retry(
                prog, self.soc, load_pulses=True, progress=False)
        final = discriminate_shots(i, q, self.calib_params)
        probability = float(np.mean(final))
        contrast = self.assignment_reference["P_e"] - self.assignment_reference["P_g"]
        corrected = ((probability - self.assignment_reference["P_g"]) / contrast
                     if np.isfinite(contrast) and contrast > 0.0 else np.nan)
        reset_last = (discriminate_shots(reset_i[:, -1], reset_q[:, -1], self.calib_params)
                      if reset_i.shape[1] else np.asarray([], dtype=float))
        self.raw = {"reset_i": reset_i, "reset_q": reset_q, "i": i, "q": q}
        self.metrics = {
            "P_excited": probability,
            "population_corrected": float(corrected),
            "reset_last_P_excited": (float(np.mean(reset_last))
                                       if reset_last.size else np.nan),
        }
        self.data = {
            "meta_dict": dict(self.cfg),
            "ff_gain": self.ff_gain,
            "target_freq_mhz": self.target_freq_mhz,
            "pump_gain": self.pump_gain,
            "pump_us": self.pump_us,
            "probe_us": self.probe_us,
            "recovery_us": self.recovery_us,
            "arm": self.arm,
            "shots": self.shots,
            "calib_params": dict(self.calib_params),
            "assignment_reference": dict(self.assignment_reference),
            "metrics": dict(self.metrics),
            "raw": dict(self.raw),
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        return self.data
