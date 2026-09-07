from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path

import numpy as np


def json_safe(value):
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


@dataclass(frozen=True)
class ReferenceAxis:
    ground_i: float
    ground_q: float
    delta_i: float
    delta_q: float
    denominator: float

    @classmethod
    def from_centers(cls, ground_i, ground_q, excited_i, excited_q):
        di = float(excited_i) - float(ground_i)
        dq = float(excited_q) - float(ground_q)
        denominator = di * di + dq * dq
        if not math.isfinite(denominator) or denominator <= 0:
            raise ValueError("ground and excited reference centers coincide")
        return cls(float(ground_i), float(ground_q), di, dq, denominator)

    def population(self, i_values, q_values):
        i_values = np.asarray(i_values, dtype=float)
        q_values = np.asarray(q_values, dtype=float)
        return (
            (i_values - self.ground_i) * self.delta_i
            + (q_values - self.ground_q) * self.delta_q
        ) / self.denominator

    def mean_population(self, i_values, q_values):
        values = self.population(i_values, q_values)
        return float(np.mean(values)) if values.size else float("nan")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, values):
        return cls(**dict(values))


def load_park_history_method_frequencies(path):
    values = json.loads(Path(path).read_text())
    fits = dict(values.get("fits", {}))
    groups = {
        "opx_unbounded": (
            "history_1_recovery_10",
            "history_750_recovery_10",
        ),
        "passive": (
            "history_1_recovery_1000",
            "history_750_recovery_1000",
        ),
    }
    output = {}
    for method, names in groups.items():
        centers = []
        for name in names:
            if name not in fits:
                raise ValueError(f"park-history spectroscopy is missing {name}")
            fit = dict(fits[name])
            center = float(fit.get("center_mhz", float("nan")))
            error = float(fit.get("center_err_mhz", float("nan")))
            contrast = float(fit.get("contrast", float("nan")))
            if bool(fit.get("boundary_peak", True)):
                raise ValueError(f"park-history peak {name} lies at a sweep boundary")
            if not np.isfinite(center) or not np.isfinite(error) or error > 0.25:
                raise ValueError(f"park-history peak {name} has an unreliable center")
            if not np.isfinite(contrast) or contrast < 0.25:
                raise ValueError(f"park-history peak {name} has insufficient contrast")
            centers.append(center)
        output[method] = float(np.mean(centers))
    return output
