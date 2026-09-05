from dataclasses import asdict, dataclass
from enum import Enum
import math

import numpy as np


INT32_MAX = 2**31 - 1
DEFAULT_HEADROOM = 4.0
DEFAULT_MAX_SHIFT = 20


class Zone(str, Enum):
    GROUND = "ground"
    AMBIGUOUS = "ambiguous"
    EXCITED = "excited"


@dataclass(frozen=True)
class ClassifierCalibration:
    schema_version: int
    context: str
    theta_rad: float
    shift: int
    c_int: int
    s_int: int
    ground_threshold: int
    excited_threshold: int
    max_abs_raw: int
    holdout: dict

    def __post_init__(self):
        if int(self.schema_version) != 1:
            raise ValueError(f"unsupported classifier schema {self.schema_version}")
        if int(self.ground_threshold) >= int(self.excited_threshold):
            raise ValueError("ground_threshold must be below excited_threshold")
        if not (int(self.c_int) or int(self.s_int)):
            raise ValueError("the projection coefficients cannot both be zero")

    def project(self, i_values, q_values):
        return (
            int(self.c_int) * np.asarray(i_values, dtype=np.int64)
            + int(self.s_int) * np.asarray(q_values, dtype=np.int64)
        )

    def assembly_plan(self):
        c_int, s_int = int(self.c_int), int(self.s_int)
        same_sign = (c_int >= 0) == (s_int >= 0)
        return {
            "c_abs": abs(c_int),
            "s_abs": abs(s_int),
            "combine_op": "+" if same_sign else "-",
            "excited_above": c_int >= 0,
        }

    def assembly_thresholds(self):
        sign = 1 if self.assembly_plan()["excited_above"] else -1
        return {
            "ground": sign * int(self.ground_threshold),
            "excited": sign * int(self.excited_threshold),
        }

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, values):
        return cls(**dict(values))


def classify(projected_value, calibration):
    value = int(projected_value)
    if value <= int(calibration.ground_threshold):
        return Zone.GROUND
    if value > int(calibration.excited_threshold):
        return Zone.EXCITED
    return Zone.AMBIGUOUS


def _fixed_point_coefficients(theta, max_abs_raw):
    max_abs = float(max_abs_raw)
    if not math.isfinite(max_abs) or max_abs <= 0:
        raise ValueError("raw calibration values must have a positive finite scale")
    gain = abs(math.cos(theta)) + abs(math.sin(theta))
    shift = int(math.floor(math.log2(INT32_MAX / (DEFAULT_HEADROOM * gain * max_abs))))
    shift = max(0, min(DEFAULT_MAX_SHIFT, shift))
    c_int = int(round(math.cos(theta) * 2**shift))
    s_int = int(round(math.sin(theta) * 2**shift))
    worst = max_abs * (abs(c_int) + abs(s_int))
    if worst > INT32_MAX:
        raise ValueError(f"fixed-point projection can overflow int32 ({worst:.3e})")
    if not (c_int or s_int):
        raise ValueError("fixed-point projection rounded both coefficients to zero")
    return shift, c_int, s_int


def _ground_threshold(excited_projection, false_ground_limit):
    excited = np.asarray(excited_projection, dtype=np.int64)
    candidates = np.concatenate(([int(np.min(excited)) - 1], np.unique(excited)))
    valid = [int(v) for v in candidates if np.mean(excited <= v) <= false_ground_limit]
    return max(valid)


def _excited_threshold(ground_projection, false_pi_limit):
    ground = np.asarray(ground_projection, dtype=np.int64)
    candidates = np.concatenate((np.unique(ground), [int(np.max(ground)) + 1]))
    valid = [int(v) for v in candidates if np.mean(ground > v) <= false_pi_limit]
    return min(valid)


def qua_thresholds(
    ground_projection,
    excited_projection,
    *,
    ground_confidence_fidelity=0.7,
    threshold_steps=100,
):
    ground = np.asarray(ground_projection, dtype=np.int64).ravel()
    excited = np.asarray(excited_projection, dtype=np.int64).ravel()
    if not ground.size or ground.size != excited.size:
        raise ValueError("QUA threshold arrays must have one matching nonzero length")
    confidence = float(ground_confidence_fidelity)
    if not math.isfinite(confidence) or not 0 <= confidence < 1:
        raise ValueError("ground confidence fidelity must be in [0, 1)")
    steps = int(threshold_steps)
    if steps < 2:
        raise ValueError("threshold steps must be at least 2")
    minimum = min(int(np.min(ground)), int(np.min(excited)))
    maximum = max(int(np.max(ground)), int(np.max(excited)))
    if minimum == maximum:
        raise ValueError("ground and excited projections coincide")
    candidates = np.linspace(minimum, maximum, steps)
    fidelities = np.asarray([
        1.0
        - 0.5 * float(np.mean(excited <= threshold))
        - 0.5 * float(np.mean(ground > threshold))
        for threshold in candidates
    ])
    confident = np.flatnonzero(fidelities > confidence)
    if not confident.size:
        confident = np.flatnonzero(fidelities > 0)
    ground_threshold = int(math.floor(candidates[int(confident[0])]))
    excited_threshold = int(math.floor(candidates[int(np.argmax(fidelities))]))
    if ground_threshold >= excited_threshold:
        ground_threshold = excited_threshold - 1
    return {
        "ground": ground_threshold,
        "excited": excited_threshold,
        "ground_fidelity": float(fidelities[int(confident[0])]),
        "peak_fidelity": float(np.max(fidelities)),
    }


def fit_classifier(
    ground_i,
    ground_q,
    excited_i,
    excited_q,
    *,
    context,
    false_ground_limit=0.01,
    false_pi_limit=0.01,
    ground_confidence_fidelity=None,
    qua_threshold_steps=100,
):
    arrays = [np.asarray(v, dtype=np.int64).ravel() for v in (
        ground_i, ground_q, excited_i, excited_q
    )]
    n = min(v.size for v in arrays)
    if n < 40:
        raise ValueError("classifier calibration needs at least 40 shots per state")
    arrays = [v[:n] for v in arrays]
    gi, gq, ei, eq = arrays
    if not 0 <= float(false_ground_limit) < 0.5:
        raise ValueError("false_ground_limit must be in [0, 0.5)")
    if not 0 <= float(false_pi_limit) < 0.5:
        raise ValueError("false_pi_limit must be in [0, 0.5)")

    train = np.arange(n) % 2 == 0
    holdout = ~train
    di = float(np.median(ei[train]) - np.median(gi[train]))
    dq = float(np.median(eq[train]) - np.median(gq[train]))
    if math.hypot(di, dq) <= 0:
        raise ValueError("ground and excited calibration centroids coincide")
    theta = math.atan2(dq, di)
    max_abs = int(np.max(np.abs(np.concatenate(arrays))))
    shift, c_int, s_int = _fixed_point_coefficients(theta, max_abs)

    project = lambda i, q: c_int * np.asarray(i, dtype=np.int64) + s_int * np.asarray(q, dtype=np.int64)
    pg_train = project(gi[train], gq[train])
    pe_train = project(ei[train], eq[train])
    if float(np.median(pe_train)) <= float(np.median(pg_train)):
        raise RuntimeError("internal error: fitted projection does not point toward excited")
    qua_metrics = {}
    if ground_confidence_fidelity is None:
        false_ground_boundary = _ground_threshold(pe_train, float(false_ground_limit))
        false_pi_boundary = _excited_threshold(pg_train, float(false_pi_limit))
        ground_threshold = min(false_ground_boundary, false_pi_boundary)
        excited_threshold = max(false_ground_boundary, false_pi_boundary)
        if ground_threshold == excited_threshold:
            ground_threshold -= 1
    else:
        thresholds = qua_thresholds(
            pg_train,
            pe_train,
            ground_confidence_fidelity=ground_confidence_fidelity,
            threshold_steps=qua_threshold_steps,
        )
        ground_threshold = int(thresholds["ground"])
        excited_threshold = int(thresholds["excited"])
        qua_metrics = {
            "ground_confidence_fidelity": float(ground_confidence_fidelity),
            "ground_threshold_fidelity": float(thresholds["ground_fidelity"]),
            "peak_fidelity": float(thresholds["peak_fidelity"]),
            "threshold_steps": int(qua_threshold_steps),
        }

    pg_hold = project(gi[holdout], gq[holdout])
    pe_hold = project(ei[holdout], eq[holdout])
    metrics = {
        "shots_per_state": int(np.count_nonzero(holdout)),
        "false_ground_accept": float(np.mean(pe_hold <= ground_threshold)),
        "false_pi": float(np.mean(pg_hold > excited_threshold)),
        "ground_accept": float(np.mean(pg_hold <= ground_threshold)),
        "excited_fire": float(np.mean(pe_hold > excited_threshold)),
        "ground_median": int(np.median(pg_hold)),
        "excited_median": int(np.median(pe_hold)),
        **qua_metrics,
    }
    return ClassifierCalibration(
        schema_version=1,
        context=str(context),
        theta_rad=float(theta),
        shift=int(shift),
        c_int=int(c_int),
        s_int=int(s_int),
        ground_threshold=int(ground_threshold),
        excited_threshold=int(excited_threshold),
        max_abs_raw=int(max_abs),
        holdout=metrics,
    )
