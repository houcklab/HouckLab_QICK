from dataclasses import dataclass


@dataclass(frozen=True)
class Q3BenchmarkSettings:
    feedback_syncdelay_us: float
    loop_recovery_us: float
    ground_confidence_fidelity: float
    qua_threshold_steps: int

    def opx_overrides(self):
        return {
            "opx_feedback_syncdelay_us": float(self.feedback_syncdelay_us),
            "opx_loop_recovery_us": float(self.loop_recovery_us),
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
        ground_confidence_fidelity=0.7,
        qua_threshold_steps=100,
    )
