"""Owned causal inverse, independent of controller SDKs. All times are ns.

u = r + sum(g(r) - z), dz/dt = (g(r) - z)/tau.
The fixed, real negative poles guarantee BIBO stability. For one coefficient
row this is an LTI filter. Multiple rows define a parallel Hammerstein inverse
with a single, explicit interpolation rule, including transitions to park.
"""

from dataclasses import dataclass

import numpy as np

ALGORITHM = "stable_parallel_highpass_inverse_v1"


def _vector(value, name):
    a = np.array(value, dtype=float, copy=True)
    if a.ndim != 1 or not a.size or not np.all(np.isfinite(a)):
        raise ValueError(f"{name} must be a nonempty finite vector")
    a.setflags(write=False)
    return a


@dataclass(frozen=True)
class Command:
    edges_ns: np.ndarray
    values: np.ndarray

    def __post_init__(self):
        edges = _vector(self.edges_ns, "edges_ns")
        values = _vector(self.values, "values")
        if len(edges) != len(values)+1 or edges[0] != 0 or np.any(np.diff(edges) <= 0):
            raise ValueError("Command needs N+1 strictly increasing edges starting at zero")
        object.__setattr__(self, "edges_ns", edges)
        object.__setattr__(self, "values", values)

    def to_dict(self):
        return {"edges_ns": self.edges_ns.tolist(), "values": self.values.tolist()}


@dataclass(frozen=True)
class Filter:
    taus_ns: np.ndarray
    amplitudes: np.ndarray
    coefficients: np.ndarray
    resolution_ns: float = 4000.0
    max_l1: float = 0.25

    def __post_init__(self):
        tau = _vector(self.taus_ns, "taus_ns")
        amp = _vector(self.amplitudes, "amplitudes")
        c = np.array(self.coefficients, dtype=float, copy=True)
        if not np.isfinite(self.resolution_ns) or self.resolution_ns <= 0:
            raise ValueError("resolution_ns must be positive")
        if np.any(tau < 2*self.resolution_ns) or np.any(np.diff(tau) <= 0):
            raise ValueError("taus must increase and be >= twice the measurement resolution")
        if np.any(amp <= 0) or np.any(np.diff(amp) <= 0):
            raise ValueError("amplitudes must be positive and strictly increasing")
        if c.shape != (len(amp), len(tau)) or not np.all(np.isfinite(c)):
            raise ValueError("coefficients shape must be (amplitudes, taus), all finite")
        if not np.isfinite(self.max_l1) or not 0 < self.max_l1 <= 1:
            raise ValueError("max_l1 must be in (0,1]")
        if np.any(np.sum(np.abs(c), axis=1) > self.max_l1 + 1e-12):
            raise ValueError("coefficient L1 bound exceeded")
        c.setflags(write=False)
        object.__setattr__(self, "taus_ns", tau)
        object.__setattr__(self, "amplitudes", amp)
        object.__setattr__(self, "coefficients", c)

    def potential(self, amplitude):
        r = float(amplitude)
        if not np.isfinite(r) or r < 0 or r > self.amplitudes[-1]+1e-12:
            raise ValueError("desired amplitude outside calibrated [0, max] range")
        # Constant endpoint toward park; g(0)=0. No sign-reflection assumption.
        c = np.array([np.interp(r, self.amplitudes, column) for column in self.coefficients.T])
        return r*c

    def to_dict(self):
        return dict(schema_version=1, algorithm=ALGORITHM,
                    taus_ns=self.taus_ns.tolist(), amplitudes=self.amplitudes.tolist(),
                    coefficients=self.coefficients.tolist(), resolution_ns=float(self.resolution_ns),
                    max_l1=float(self.max_l1))

    @classmethod
    def from_dict(cls, doc):
        keys = {"schema_version", "algorithm", "taus_ns", "amplitudes", "coefficients", "resolution_ns", "max_l1"}
        if not isinstance(doc, dict) or set(doc) != keys or type(doc["schema_version"]) is not int:
            raise ValueError("invalid filter schema")
        if doc["schema_version"] != 1 or doc["algorithm"] != ALGORITHM:
            raise ValueError("unsupported filter schema or algorithm")
        return cls(**{key: doc[key] for key in keys - {"schema_version", "algorithm"}})


def tail_bound(state):
    """Bound |u| for all subsequent park times; no cancellation assumption."""
    return float(np.sum(np.abs(_vector(state, "state"))))


def render(model, desired, *, initial_state=None, sample_ns=None, max_segments=100000):
    """Exact state update with interval-average zero-order-hold commands.

    Desired is [(normalized_level, duration_ns), ...]. Carry the returned state
    into every subsequent call. An omitted state means a demonstrably settled
    park, never a new-shot/reset event. Finer sampling changes emission only.
    """
    dt = model.resolution_ns if sample_ns is None else float(sample_ns)
    if not np.isfinite(dt) or dt <= 0 or type(max_segments) is not int or max_segments < 1:
        raise ValueError("invalid sampling or segment limit")
    segments = [(float(r), float(d)) for r, d in desired]
    if not segments or any(not np.isfinite(d) or d <= 0 for _, d in segments):
        raise ValueError("desired segments need positive finite durations")
    if sum(np.ceil(d/dt) for _, d in segments) > max_segments:
        raise ValueError("command segment budget exceeded")
    state = np.zeros(len(model.taus_ns)) if initial_state is None else _vector(initial_state, "state").copy()
    if state.shape != model.taus_ns.shape:
        raise ValueError("state dimension mismatch")
    edges, values = [0.0], []
    for r, duration in segments:
        g = model.potential(r)
        count = int(np.ceil(duration/dt))
        # Last interval is exact; never extend a requested hold to a sample grid.
        bounds = np.r_[np.arange(count)*dt, duration]
        for width in np.diff(bounds):
            factor = -np.expm1(-width/model.taus_ns)
            mean = r + np.sum((g-state)*model.taus_ns/width*factor)
            values.append(mean)
            edges.append(edges[-1]+width)
            state += (g-state)*factor
    return Command(edges, values), state


def compare_commands(a, b):
    """Exact normalized command discrepancy on union of piecewise boundaries."""
    if abs(a.edges_ns[-1]-b.edges_ns[-1]) > 1e-6:
        raise ValueError("comparison requires identical time horizons")
    edges = np.unique(np.r_[a.edges_ns, b.edges_ns])
    mid = (edges[1:]+edges[:-1])/2
    # Extend the terminal value only across the accepted <=1e-6 ns numerical
    # endpoint discrepancy. Real hardware horizon differences are rejected.
    ia = np.minimum(np.searchsorted(a.edges_ns, mid, side="right")-1, len(a.values)-1)
    ib = np.minimum(np.searchsorted(b.edges_ns, mid, side="right")-1, len(b.values)-1)
    delta = a.values[ia] - b.values[ib]
    width = np.diff(edges)
    return {"max_abs": float(np.max(np.abs(delta))),
            "rms": float(np.sqrt(np.sum(width*delta**2)/np.sum(width))),
            "integrated_abs_ns": float(np.sum(width*np.abs(delta))),
            "signed_area_ns": float(np.sum(width*delta))}
