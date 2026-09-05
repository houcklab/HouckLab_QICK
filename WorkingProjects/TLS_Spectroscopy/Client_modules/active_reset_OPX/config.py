from dataclasses import asdict, dataclass
import math


MAX_RESET_ATTEMPTS = 32


@dataclass(frozen=True)
class OPXResetConfig:
    """Timing and memory settings for the isolated reset state machine."""

    max_reset_attempts: int = 8
    read_delay_us: float = 2.0
    feedback_syncdelay_us: float = 2.0
    loop_recovery_us: float = 0.0
    reset_settle_us: float = 0.05
    verification_delay_us: float = 0.25
    inter_shot_delay_us: float = 400.0
    persistent_park: bool = False
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
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if int(self.record_base) < 2:
            raise ValueError("opx_record_base must be at least 2")
        if not isinstance(self.persistent_park, bool):
            raise ValueError("opx_persistent_park must be a boolean")
        if int(self.done_addr) < 0 or int(self.done_addr) == int(self.record_base):
            raise ValueError("opx_done_addr must be non-negative and outside the record base")
        if not math.isfinite(float(self.poll_interval_s)) or float(self.poll_interval_s) <= 0:
            raise ValueError("opx_poll_interval_s must be positive and finite")
        if not math.isfinite(float(self.timeout_margin)) or float(self.timeout_margin) < 1:
            raise ValueError("opx_timeout_margin must be at least 1")
        return self

    def to_dict(self):
        return asdict(self)
