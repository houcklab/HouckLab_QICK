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
    return float(np.sum(np.abs(_vector(state, "state"))))


def render(model, desired, *, initial_state=None, sample_ns=None, max_segments=100000):
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
        bounds = np.r_[np.arange(count)*dt, duration]
        for width in np.diff(bounds):
            factor = -np.expm1(-width/model.taus_ns)
            mean = r + np.sum((g-state)*model.taus_ns/width*factor)
            values.append(mean)
            edges.append(edges[-1]+width)
            state += (g-state)*factor
    return Command(edges, values), state


def compare_commands(a, b):
    if abs(a.edges_ns[-1]-b.edges_ns[-1]) > 1e-6:
        raise ValueError("comparison requires identical time horizons")
    edges = np.unique(np.r_[a.edges_ns, b.edges_ns])
    mid = (edges[1:]+edges[:-1])/2
    ia = np.minimum(np.searchsorted(a.edges_ns, mid, side="right")-1, len(a.values)-1)
    ib = np.minimum(np.searchsorted(b.edges_ns, mid, side="right")-1, len(b.values)-1)
    delta = a.values[ia] - b.values[ib]
    width = np.diff(edges)
    return {"max_abs": float(np.max(np.abs(delta))),
            "rms": float(np.sqrt(np.sum(width*delta**2)/np.sum(width))),
            "integrated_abs_ns": float(np.sum(width*np.abs(delta))),
            "signed_area_ns": float(np.sum(width*delta))}


def render_on_schedule(model, schedule, *, initial_state=None, max_segments=100000):
    entries = [(float(level), float(duration)) for level, duration in schedule]
    if not entries or any(not np.isfinite(d) or d <= 0 for _, d in entries):
        raise ValueError("schedule entries need positive finite durations")
    if type(max_segments) is not int or max_segments < 1:
        raise ValueError("invalid segment limit")
    if len(entries) > max_segments:
        raise ValueError("command segment budget exceeded")
    state = np.zeros(len(model.taus_ns)) if initial_state is None else _vector(initial_state, "state").copy()
    if state.shape != model.taus_ns.shape:
        raise ValueError("state dimension mismatch")
    edges, values = [0.0], []
    for level, width in entries:
        g = model.potential(level)
        factor = -np.expm1(-width/model.taus_ns)
        values.append(level + np.sum((g-state)*model.taus_ns/width*factor))
        edges.append(edges[-1]+width)
        state += (g-state)*factor
    return Command(edges, values), state


def geometric_schedule(level, total_ns, *, first_ns, growth=1.35, max_ns=None, quantum_ns=None):
    total_ns = float(total_ns)
    first_ns = float(first_ns)
    growth = float(growth)
    if not np.isfinite(total_ns) or total_ns <= 0:
        raise ValueError("total_ns must be positive and finite")
    if not np.isfinite(first_ns) or first_ns <= 0:
        raise ValueError("first_ns must be positive and finite")
    if not np.isfinite(growth) or growth < 1.0:
        raise ValueError("growth must be at least one")
    ceiling = total_ns if max_ns is None else float(max_ns)
    if not np.isfinite(ceiling) or ceiling <= 0:
        raise ValueError("max_ns must be positive and finite")
    if quantum_ns is not None:
        quantum_ns = float(quantum_ns)
        if not np.isfinite(quantum_ns) or quantum_ns <= 0:
            raise ValueError("quantum_ns must be positive and finite")
        if first_ns < quantum_ns:
            raise ValueError("first_ns is shorter than one emission quantum")
    widths, remaining, width = [], total_ns, first_ns
    while remaining > 0:
        step = min(width, ceiling, remaining)
        if quantum_ns is not None and remaining - step > 0:
            step = max(np.floor(step/quantum_ns)*quantum_ns, quantum_ns)
            if remaining - step < quantum_ns:
                step = remaining
        widths.append(step)
        remaining -= step
        width *= growth
    if quantum_ns is not None and len(widths) > 1 and widths[-1] < quantum_ns:
        widths[-2] += widths.pop()
    return [(float(level), float(w)) for w in widths]


def slice_command(command, start_ns, stop_ns):
    start_ns, stop_ns = float(start_ns), float(stop_ns)
    horizon = float(command.edges_ns[-1])
    if not np.isfinite(start_ns) or not np.isfinite(stop_ns) or stop_ns <= start_ns:
        raise ValueError("slice needs a positive finite interval")
    if start_ns < -1e-9 or stop_ns > horizon+1e-9:
        raise ValueError("slice interval lies outside the command horizon")
    start_ns = max(start_ns, 0.0)
    stop_ns = min(stop_ns, horizon)
    interior = command.edges_ns[(command.edges_ns > start_ns+1e-9) & (command.edges_ns < stop_ns-1e-9)]
    edges = np.r_[start_ns, interior, stop_ns]
    mid = (edges[1:]+edges[:-1])/2
    index = np.minimum(np.searchsorted(command.edges_ns, mid, side="right")-1, len(command.values)-1)
    return Command(edges-start_ns, command.values[index])


def split_command(command, boundaries_ns):
    bounds = np.unique(np.r_[0.0, np.asarray(boundaries_ns, dtype=float), command.edges_ns[-1]])
    if np.any(bounds < -1e-9) or np.any(bounds > command.edges_ns[-1]+1e-9):
        raise ValueError("split boundaries lie outside the command horizon")
    return [slice_command(command, low, high) for low, high in zip(bounds[:-1], bounds[1:])]


def schedule_start_times(schedule):
    widths = np.asarray([float(duration) for _, duration in schedule], dtype=float)
    if widths.ndim != 1 or not widths.size or np.any(widths <= 0) or not np.all(np.isfinite(widths)):
        raise ValueError("schedule needs positive finite durations")
    return np.r_[0.0, np.cumsum(widths)[:-1]]


def constant_span(command, time_ns):
    time_ns = float(time_ns)
    edges = np.asarray(command.edges_ns, dtype=float)
    values = np.asarray(command.values, dtype=float)
    if not np.isfinite(time_ns) or time_ns < 0 or time_ns >= edges[-1]:
        raise ValueError("time lies outside the command horizon")
    index = int(np.searchsorted(edges, time_ns, side="right"))-1
    index = min(max(index, 0), values.size-1)
    low = index
    while low > 0 and values[low-1] == values[index]:
        low -= 1
    high = index
    while high < values.size-1 and values[high+1] == values[index]:
        high += 1
    return float(edges[low]), float(edges[high+1]), float(values[index])


def probe_fits_constant_segment(command, start_ns, span_ns):
    try:
        low, high, _ = constant_span(command, start_ns)
    except ValueError:
        return False
    return bool(start_ns >= low-1e-9 and float(start_ns)+float(span_ns) <= high+1e-9)


def probe_delays(command, schedule, *, span_ns, inset_ns=4.0, max_points=None, skip_first=0):
    span_ns = float(span_ns)
    inset_ns = float(inset_ns)
    if not np.isfinite(span_ns) or span_ns <= 0:
        raise ValueError("span_ns must be positive and finite")
    if not np.isfinite(inset_ns) or inset_ns < 0:
        raise ValueError("inset_ns must be nonnegative and finite")
    starts = schedule_start_times(schedule)
    usable = [float(value)+inset_ns for value in starts
              if probe_fits_constant_segment(command, float(value)+inset_ns, span_ns)]
    usable = usable[int(skip_first):]
    if not usable:
        raise ValueError(
            f"no emission segment is long enough to hold a {span_ns:g} ns probe inset by "
            f"{inset_ns:g} ns; increase the schedule's first segment or shorten the probe window")
    if max_points is not None and len(usable) > int(max_points):
        index = np.unique(np.rint(np.linspace(0, len(usable)-1, int(max_points))).astype(int))
        usable = [usable[position] for position in index]
    return np.asarray(usable, dtype=float)
