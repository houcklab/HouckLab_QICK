from dataclasses import asdict, dataclass
import math

from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.pulse_setup import (
    READOUT_THERMALIZATION_US,
)


MAX_RESET_ATTEMPTS = 32


@dataclass(frozen=True)
class OPXResetConfig:
    """Timing and memory settings for the isolated reset state machine."""

    max_reset_attempts: int = 8
    read_delay_us: float = 2.0
    feedback_syncdelay_us: float = 2.0
    loop_recovery_us: float = READOUT_THERMALIZATION_US
    reset_settle_us: float = 0.05
    verification_delay_us: float = 0.25
    inter_shot_delay_us: float = 400.0
    persistent_park: bool = False
    refresh_park_before_shot: bool = False
    hard_flux_steps: bool = False
    park_preroll_us: float = 0.0
    record_base: int = 32
    done_addr: int = 1
    poll_interval_s: float = 0.002
    timeout_margin: float = 3.0

    @classmethod
    def from_mapping(cls, values):
        values = values or {}
        aliases = {
            "max_reset_attempts": "opx_max_reset_attempts",
            "read_delay_us": "opx_read_delay_us",
            "feedback_syncdelay_us": "opx_feedback_syncdelay_us",
            "loop_recovery_us": "opx_loop_recovery_us",
            "reset_settle_us": "opx_reset_settle_us",
            "verification_delay_us": "opx_verification_delay_us",
            "inter_shot_delay_us": "opx_inter_shot_delay_us",
            "persistent_park": "opx_persistent_park",
            "refresh_park_before_shot": "opx_refresh_park_before_shot",
            "hard_flux_steps": "opx_hard_flux_steps",
            "park_preroll_us": "opx_park_preroll_us",
            "record_base": "opx_record_base",
            "done_addr": "opx_done_addr",
            "poll_interval_s": "opx_poll_interval_s",
            "timeout_margin": "opx_timeout_margin",
        }
        kwargs = {
            field: values[prefixed]
            for field, prefixed in aliases.items()
            if prefixed in values
        }
        if (
            "opx_loop_recovery_us" not in values
            and "readout_thermalization_us" in values
        ):
            kwargs["loop_recovery_us"] = values["readout_thermalization_us"]
        cfg = cls(**kwargs)
        cfg.validate()
        return cfg

    def validate(self):
        if not 1 <= int(self.max_reset_attempts) <= MAX_RESET_ATTEMPTS:
            raise ValueError(
                f"opx_max_reset_attempts must be in the range 1..{MAX_RESET_ATTEMPTS}"
            )
        for name in (
            "read_delay_us",
            "feedback_syncdelay_us",
            "loop_recovery_us",
            "reset_settle_us",
            "verification_delay_us",
            "inter_shot_delay_us",
            "park_preroll_us",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if int(self.record_base) < 2:
            raise ValueError("opx_record_base must be at least 2")
        if not isinstance(self.persistent_park, bool):
            raise ValueError("opx_persistent_park must be a boolean")
        if not isinstance(self.refresh_park_before_shot, bool):
            raise ValueError("opx_refresh_park_before_shot must be a boolean")
        if not isinstance(self.hard_flux_steps, bool):
            raise ValueError("opx_hard_flux_steps must be a boolean")
        if self.refresh_park_before_shot and not self.persistent_park:
            raise ValueError(
                "opx_refresh_park_before_shot requires opx_persistent_park"
            )
        if int(self.done_addr) < 0 or int(self.done_addr) == int(self.record_base):
            raise ValueError("opx_done_addr must be non-negative and outside the record base")
        if not math.isfinite(float(self.poll_interval_s)) or float(self.poll_interval_s) <= 0:
            raise ValueError("opx_poll_interval_s must be positive and finite")
        if not math.isfinite(float(self.timeout_margin)) or float(self.timeout_margin) < 1:
            raise ValueError("opx_timeout_margin must be at least 1")
        return self

    def to_dict(self):
        return asdict(self)
