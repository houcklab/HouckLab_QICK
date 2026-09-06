from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .analysis import load_park_history_method_frequencies
from .benchmark_settings import q3_benchmark_settings
from .calibration import (
    acquire_calibration,
    per_shot_reference_config,
    save_calibration,
    save_raw_calibration,
    validate_confident_calibration,
)


CALIBRATION_SHOTS = 2000
CALIBRATION_RELAX_US = 1000.0
MIN_CONFIDENT_STATE_FRACTION = 0.2
HOST_WATCHDOG_S = 2.0
AUTOMATIC_RECALIBRATION_MIN = 30.0
PASSIVE_T1_RESET_US = 400.0


def normalize_reset_mode(mode):
    if isinstance(mode, bool):
        return "opx_unbounded" if mode else "passive"
    value = str("passive" if mode is None else mode).strip().lower()
    if value in ("active", "opx_unbounded"):
        return "opx_unbounded"
    if value in ("passive", "none"):
        return "passive"
    raise ValueError("reset mode must be 'active' or 'passive'")


def latest_park_history_result(outer_folder, qubit):
    paths = list(
        (Path(outer_folder) / str(qubit)).glob(
            f"{qubit}_*/{qubit}_*_active_reset_OPX_park_history_spectroscopy/result.json"
        )
    )
    if not paths:
        raise FileNotFoundError(
            f"no completed park-history spectroscopy result found for {qubit}"
        )
    return max(paths, key=lambda path: path.stat().st_mtime)


def build_calibration_config(base_cfg, method_frequency_mhz):
    cfg = dict(base_cfg)
    cfg.update(q3_benchmark_settings().opx_overrides())
    cfg.update({
        "qubit_pi_freq": float(method_frequency_mhz),
        "reset_pi_freq": float(method_frequency_mhz),
        "relax_delay": float(CALIBRATION_RELAX_US),
        "opx_unbounded_watchdog_s": float(HOST_WATCHDOG_S),
    })
    return per_shot_reference_config(cfg)


@dataclass(frozen=True)
class ProductionResetSession:
    runtime_mode: str
    calibration: dict | None = None
    method_frequency_mhz: float | None = None
    calibration_output: Path | None = None

    @classmethod
    def passive(cls):
        return cls("passive")

    @classmethod
    def active(cls, calibration, method_frequency_mhz, calibration_output=None):
        return cls(
            "opx_unbounded",
            dict(calibration),
            float(method_frequency_mhz),
            None if calibration_output is None else Path(calibration_output),
        )

    def apply(self, cfg):
        values = dict(cfg)
        values.update(q3_benchmark_settings().opx_overrides())
        values.update({
            "reset_mode": self.runtime_mode,
            "randomize_point_order": False,
            "shuffle_detuning": False,
            "remeasure_outliers": False,
            "qua_shot_order": True,
            "three_point_matched_refs": False,
        })
        if self.runtime_mode == "passive":
            values["opx_inter_shot_delay_us"] = float(
                values.get("relax_delay", PASSIVE_T1_RESET_US)
            )
            values.pop("opx_reset_calibration", None)
            return values
        if self.calibration is None or self.method_frequency_mhz is None:
            raise RuntimeError("active reset session is missing its automatic calibration")
        values.update({
            "opx_reset_calibration": dict(self.calibration),
            "opx_unbounded_watchdog_s": float(HOST_WATCHDOG_S),
            "opx_inter_shot_delay_us": float(
                q3_benchmark_settings().inter_shot_delay_us
            ),
            "qubit_pi_freq": float(self.method_frequency_mhz),
            "reset_pi_freq": float(self.method_frequency_mhz),
            "relax_delay": float(q3_benchmark_settings().inter_shot_delay_us),
        })
        return values


def prepare_reset_session(
    reset_mode,
    *,
    outer_folder,
    qubit,
    base_cfg,
    soc,
    soccfg,
    purpose,
    now=None,
):
    mode = normalize_reset_mode(reset_mode)
    if mode == "passive":
        return ProductionResetSession.passive()
    history_result = latest_park_history_result(outer_folder, qubit)
    frequencies = load_park_history_method_frequencies(history_result)
    frequency = float(frequencies["opx_unbounded"])
    cfg = build_calibration_config(base_cfg, frequency)
    created = datetime.now() if now is None else datetime.strptime(
        str(now), "%Y_%m_%d_%H_%M_%S"
    )
    output = (
        Path(outer_folder)
        / str(qubit)
        / f"{qubit}_{created:%Y_%m_%d}"
        / f"{qubit}_{created:%H_%M_%S}_active_reset_OPX_production_calibration"
    )
    output.mkdir(parents=True, exist_ok=False)
    bundle, raw = acquire_calibration(
        soc,
        soccfg,
        cfg,
        shots=int(CALIBRATION_SHOTS),
        **q3_benchmark_settings().calibration_options(),
        metadata={
            "qubit": str(qubit),
            "created": created.isoformat(),
            "purpose": str(purpose),
            "park_history_result": str(history_result),
            "method_frequency_mhz": frequency,
        },
    )
    save_calibration(output / "calibration.json", bundle)
    save_raw_calibration(output / "calibration_raw.npz", raw)
    validate_confident_calibration(
        bundle,
        min_confident_fraction=float(MIN_CONFIDENT_STATE_FRACTION),
    )
    return ProductionResetSession.active(bundle.to_dict(), frequency, output)
