from dataclasses import dataclass

import numpy as np

from .core import Command, Filter, render


def highpass_features(command, time_ns, taus_ns, *, probe_ns=0, freeze_probe=True):
    t, tau = np.asarray(time_ns, float), np.asarray(taus_ns, float)
    if t.ndim != 1 or tau.ndim != 1 or not len(tau) or np.any(~np.isfinite(t)) or np.any(~np.isfinite(tau)):
        raise ValueError("finite time and tau vectors required")
    if np.any(t < 0) or np.any(t >= command.edges_ns[-1]) or np.any(tau <= 0):
        raise ValueError("time outside command or invalid tau")
    if not np.isfinite(probe_ns) or probe_ns < 0:
        raise ValueError("probe_ns must be nonnegative")
    edges = command.edges_ns[:-1]
    jumps = np.diff(np.r_[0, command.values])
    delay = t[:, None]-edges[None, :]
    if probe_ns and not freeze_probe:
        if np.any(t+probe_ns > command.edges_ns[-1]):
            raise ValueError("continuous probe extends beyond command horizon")
        lo, hi = np.maximum(delay, 0), np.maximum(delay+probe_ns, 0)
        u = (hi-lo)@jumps/probe_ns
        features = np.stack([tj/probe_ns*((np.exp(-lo/tj)-np.exp(-hi/tj))@jumps) for tj in tau], axis=1)
        return u, features
    active = delay > 0 if probe_ns else delay >= 0
    active[:, 0] |= t == 0
    features = np.stack([np.sum(np.where(active, np.exp(-np.maximum(delay, 0)/tj)*jumps, 0), axis=1) for tj in tau], axis=1)
    if probe_ns:
        features *= tau/probe_ns*(-np.expm1(-probe_ns/tau))
    side = "left" if probe_ns else "right"
    u = command.values[np.maximum(np.searchsorted(command.edges_ns, t, side=side)-1, 0)]
    return u, features


def plant_response(command, time_ns, taus_ns, coefficients, *, probe_ns=0, freeze_probe=True):
    u, x = highpass_features(command, time_ns, taus_ns, probe_ns=probe_ns, freeze_probe=freeze_probe)
    a = np.asarray(coefficients, float)
    if a.shape != (x.shape[1],) or not np.all(np.isfinite(a)):
        raise ValueError("invalid plant coefficients")
    return u+x@a


@dataclass
class Trace:
    time_ns: np.ndarray
    response: np.ndarray
    command: Command
    support: np.ndarray
    probe_ns: float = 0.0

    def __post_init__(self):
        self.time_ns = np.array(self.time_ns, float)
        self.response = np.array(self.response, float)
        support = np.asarray(self.support)
        if np.any(~np.isin(support, [False, True])):
            raise ValueError("support must contain only boolean/0/1 values")
        self.support = np.array(support, bool)
        if self.time_ns.ndim != 1 or self.time_ns.shape != self.response.shape or self.support.shape != self.time_ns.shape:
            raise ValueError("trace arrays must be equal length vectors")
        if np.any(~np.isfinite(self.time_ns)) or np.any(np.diff(self.time_ns) <= 0):
            raise ValueError("trace times must be finite and increasing")
        if np.any(~np.isfinite(self.response[self.support])):
            raise ValueError("supported responses must be finite")


def fit_plant(traces, taus_ns, *, regularization=1e-4, max_l1=0.25):
    tau = np.asarray(taus_ns, float)
    if not np.isfinite(regularization) or regularization < 0 or not traces:
        raise ValueError("nonnegative regularization and traces required")
    Filter(tau, [1], [np.zeros(len(tau))], max_l1=max_l1)
    xx, yy, means, originals = [], [], [], []
    for trace in traces:
        valid = trace.support
        if np.count_nonzero(valid) < len(tau)+3:
            raise ValueError("insufficient supported samples")
        u, x = highpass_features(trace.command, trace.time_ns[valid], tau, probe_ns=trace.probe_ns)
        y = trace.response[valid]-u
        xm, ym = x.mean(axis=0), y.mean()
        xx.append((x-xm)/np.sqrt(len(y)))
        yy.append((y-ym)/np.sqrt(len(y)))
        means.append((xm, ym))
        originals.append((x, y))
    x, y = np.vstack(xx), np.concatenate(yy)
    if np.linalg.matrix_rank(x) < len(tau):
        raise ValueError("rank-deficient plant identification")
    a = np.linalg.lstsq(np.vstack([x, np.sqrt(regularization)*np.eye(len(tau))]),
                        np.r_[y, np.zeros(len(tau))], rcond=None)[0]
    if np.sum(np.abs(a)) > max_l1:
        raise ValueError("plant coefficient L1 bound exceeded; model unsupported")
    offsets = np.array([ym-xm@a for xm, ym in means])
    residuals = [y-x@a-offset for (x, y), offset in zip(originals, offsets)]
    return {"coefficients": a, "offsets": offsets,
            "rms": float(np.sqrt(np.mean(np.concatenate(residuals)**2))),
            "condition_number": float(np.linalg.cond(x)), "regularization": regularization}


def fit_inverse(plants, taus_ns, *, regularization=1e-4, horizon_ns=500000, sample_ns=4000, max_amplitude=1.0):
    tau = np.asarray(taus_ns, float)
    plants = np.asarray(plants, float)
    if plants.ndim != 2 or plants.shape[1] != len(tau) or not plants.shape[0] or np.any(~np.isfinite(plants)):
        raise ValueError("invalid plants")
    if not np.isfinite(regularization) or regularization < 0:
        raise ValueError("invalid inverse regularization")
    zero = Filter(tau, [1], [np.zeros(len(tau))])
    reference, _ = render(zero, [(1, horizon_ns)], sample_ns=sample_ns)
    t = (reference.edges_ns[1:]+reference.edges_ns[:-1])/2
    basis = []
    for j in range(len(tau)):
        c = np.zeros(len(tau)); c[j] = 1
        basis.append(render(Filter(tau, [1], [c], max_l1=1), [(1, horizon_ns)], sample_ns=sample_ns)[0])
    xx, yy = [], []
    for plant in plants:
        base = plant_response(reference, t, tau, plant)
        x = np.stack([plant_response(cmd, t, tau, plant)-base for cmd in basis], axis=1)
        xx.append(x/np.sqrt(len(t))); yy.append((1-base)/np.sqrt(len(t)))
    x, y = np.vstack(xx), np.concatenate(yy)
    c = np.linalg.lstsq(np.vstack([x, np.sqrt(regularization)*np.eye(len(tau))]), np.r_[y, np.zeros(len(tau))], rcond=None)[0]
    model = Filter(tau, [max_amplitude], [c])
    return {"model": model, "design_rms": float(np.sqrt(np.mean((x@c-y)**2)*len(t))),
            "regularization": regularization}


def interpolate_plant(amplitudes, coefficients, amplitude):
    knots, a = np.asarray(amplitudes, float), np.asarray(coefficients, float)
    if knots.ndim != 1 or not len(knots) or a.ndim != 2 or len(a) != len(knots) or np.any(np.diff(knots) <= 0):
        raise ValueError("invalid amplitude knots")
    if not np.all(np.isfinite(knots)) or not np.all(np.isfinite(a)) or not np.isfinite(amplitude):
        raise ValueError("nonfinite interpolation")
    return np.array([np.interp(amplitude, knots, column) for column in a.T]), bool(amplitude < knots[0] or amplitude > knots[-1])
