from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np

from .analysis import ReferenceAxis
from .classifier import ClassifierCalibration, fit_classifier


@dataclass(frozen=True)
class CalibrationBundle:
    schema_version: int
    payload: ClassifierCalibration
    loop: ClassifierCalibration
    reference_axis: ReferenceAxis
    metadata: dict

    def __post_init__(self):
        if int(self.schema_version) != 1:
            raise ValueError(f"unsupported OPX calibration schema {self.schema_version}")

    def to_dict(self):
        return {
            "schema_version": int(self.schema_version),
            "payload": self.payload.to_dict(),
            "loop": self.loop.to_dict(),
            "reference_axis": self.reference_axis.to_dict(),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, values):
        values = dict(values)
        return cls(
            schema_version=int(values["schema_version"]),
            payload=ClassifierCalibration.from_dict(values["payload"]),
            loop=ClassifierCalibration.from_dict(values["loop"]),
            reference_axis=ReferenceAxis.from_dict(values["reference_axis"]),
            metadata=dict(values.get("metadata", {})),
        )


def save_calibration(path, bundle):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle.to_dict(), indent=2, sort_keys=True) + "\n")
    return path


def load_calibration(path):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"OPX active-reset calibration not found: {path}. Run the calibration stage first."
        )
    try:
        values = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read OPX active-reset calibration {path}: {exc}") from exc
    return CalibrationBundle.from_dict(values)


def _config_digest(cfg):
    encoded = json.dumps(dict(cfg), sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _capture_context(soc, soccfg, cfg, *, context, shots):
    from .programs import TimingMatchedReferenceProgram

    output = {}
    for preparation, label in ((False, "ground"), (True, "excited")):
        run_cfg = dict(cfg)
        run_cfg.update({
            "shots": int(shots),
            "reps": int(shots),
            "prep_excited": bool(preparation),
            "opx_reference_context": str(context),
        })
        program = TimingMatchedReferenceProgram(soccfg, run_cfg)
        i_values, q_values = program.acquire(soc, load_pulses=True, progress=False)
        output[label] = {
            "i": np.asarray(i_values, dtype=np.int64),
            "q": np.asarray(q_values, dtype=np.int64),
        }
    return output


def acquire_calibration(
    soc,
    soccfg,
    cfg,
    *,
    shots=4000,
    false_ground_limit=0.01,
    false_pi_limit=0.01,
    metadata=None,
):
    shots = int(shots)
    if shots < 40:
        raise ValueError("calibration_shots must be at least 40")
    payload_raw = _capture_context(soc, soccfg, cfg, context="payload", shots=shots)
    loop_raw = _capture_context(soc, soccfg, cfg, context="loop", shots=shots)
    payload = fit_classifier(
        payload_raw["ground"]["i"], payload_raw["ground"]["q"],
        payload_raw["excited"]["i"], payload_raw["excited"]["q"],
        context="payload", false_ground_limit=false_ground_limit,
        false_pi_limit=false_pi_limit,
    )
    loop = fit_classifier(
        loop_raw["ground"]["i"], loop_raw["ground"]["q"],
        loop_raw["excited"]["i"], loop_raw["excited"]["q"],
        context="loop", false_ground_limit=false_ground_limit,
        false_pi_limit=false_pi_limit,
    )
    axis = ReferenceAxis.from_centers(
        np.mean(loop_raw["ground"]["i"]),
        np.mean(loop_raw["ground"]["q"]),
        np.mean(loop_raw["excited"]["i"]),
        np.mean(loop_raw["excited"]["q"]),
    )
    bundle_metadata = dict(metadata or {})
    bundle_metadata.update({
        "shots_per_state_per_context": shots,
        "config_sha256": _config_digest(cfg),
        "false_ground_limit": float(false_ground_limit),
        "false_pi_limit": float(false_pi_limit),
    })
    try:
        import qick
        bundle_metadata["qick_version"] = str(qick.__version__)
    except Exception:
        bundle_metadata["qick_version"] = "unavailable"
    return (
        CalibrationBundle(1, payload, loop, axis, bundle_metadata),
        {"payload": payload_raw, "loop": loop_raw},
    )


def save_raw_calibration(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        payload_ground_i=raw["payload"]["ground"]["i"],
        payload_ground_q=raw["payload"]["ground"]["q"],
        payload_excited_i=raw["payload"]["excited"]["i"],
        payload_excited_q=raw["payload"]["excited"]["q"],
        loop_ground_i=raw["loop"]["ground"]["i"],
        loop_ground_q=raw["loop"]["ground"]["q"],
        loop_excited_i=raw["loop"]["excited"]["i"],
        loop_excited_q=raw["loop"]["excited"]["q"],
    )
    return path
