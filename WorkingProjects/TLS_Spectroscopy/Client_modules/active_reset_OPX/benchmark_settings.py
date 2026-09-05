from dataclasses import dataclass


@dataclass(frozen=True)
class Q3BenchmarkSettings:
    feedback_syncdelay_us: float
    loop_recovery_us: float
    inter_shot_delay_us: float
    ground_confidence_fidelity: float
    qua_threshold_steps: int

    def opx_overrides(self):
        return {
            "opx_feedback_syncdelay_us": float(self.feedback_syncdelay_us),
            "opx_loop_recovery_us": float(self.loop_recovery_us),
            "opx_inter_shot_delay_us": float(self.inter_shot_delay_us),
        }

    def calibration_options(self):
        return {
            "ground_confidence_fidelity": float(self.ground_confidence_fidelity),
            "qua_threshold_steps": int(self.qua_threshold_steps),
        }


def q3_benchmark_settings():
    return Q3BenchmarkSettings(
        feedback_syncdelay_us=8.0,
        loop_recovery_us=25.0,
        inter_shot_delay_us=400.0,
        ground_confidence_fidelity=0.7,
        qua_threshold_steps=100,
    )


def build_t1_point_config(
    base_cfg,
    *,
    reset_scheme,
    inter_shot_delay_us,
    shots,
    delay_us,
    excursion_gain=None,
):
    cfg = dict(base_cfg)
    park_gain = float(cfg.get("ff_park_gain", 0) or 0)
    cfg.update({
        "shots": int(shots),
        "reps": int(shots),
        "ff_gain": park_gain if excursion_gain is None else float(excursion_gain),
        "ff_hold": float(delay_us),
        "t1_wait_us": float(delay_us),
        "do_ff": excursion_gain is not None,
        "do_pi": True,
        "opx_reset_scheme": str(reset_scheme),
        "opx_inter_shot_delay_us": float(inter_shot_delay_us),
    })
    return cfg
