"""Reusable numerical diagnostics. Never imports a controller or opens hardware."""

import numpy as np

from .core import Command, render
from .fit import Trace, fit_plant, plant_response


def forecast(model, amplitude, plant, trace, *, sample_ns=None):
    """Transport a held-out measured residual through a model command change.

    y_new = y_measured + P(u_new-u_measured). This retains all measured model
    discrepancy/noise. It is a conditional forecast, not a new measurement or
    evidence that the discrepancy will survive the changed command unchanged.
    """
    new, _ = render(model, [(amplitude, trace.command.edges_ns[-1])], sample_ns=sample_ns)
    unit = Command(new.edges_ns, new.values/amplitude)
    before = plant_response(trace.command, trace.time_ns, model.taus_ns, plant, probe_ns=trace.probe_ns)
    after = plant_response(unit, trace.time_ns, model.taus_ns, plant, probe_ns=trace.probe_ns, freeze_probe=False)
    return trace.response+after-before


def blocked_plant_score(traces, taus_ns, *, regularization, folds=5):
    """Contiguous time-block prediction; nuisance offsets fitted on train only."""
    errors = []
    for fold in range(folds):
        training, masks = [], []
        for tr in traces:
            # Blocks span the full trace, including unsupported positions.
            block = np.minimum(np.arange(len(tr.time_ns))*folds//len(tr.time_ns), folds-1)
            test = (block == fold) & tr.support
            train = (block != fold) & tr.support
            masks.append(test)
            training.append(Trace(tr.time_ns, tr.response, tr.command, train, tr.probe_ns))
        fit = fit_plant(training, taus_ns, regularization=regularization)
        for tr, test, offset in zip(traces, masks, fit['offsets']):
            predicted = plant_response(tr.command, tr.time_ns, taus_ns, fit['coefficients'], probe_ns=tr.probe_ns)+offset
            errors.extend((predicted[test]-tr.response[test]).tolist())
    if not errors:
        raise ValueError("no held-out supported samples")
    return float(np.sqrt(np.mean(np.square(errors))))


def common_horizon(a, b, *, terminal_tolerance=0):
    """Compare quantized horizons by extending only an explicit zero park."""
    end = max(a.edges_ns[-1], b.edges_ns[-1])
    result = []
    for command in (a, b):
        if abs(command.values[-1]) > terminal_tolerance:
            raise ValueError("comparison requires exact terminal zero park")
        edges = command.edges_ns.copy(); edges[-1] = end
        result.append(Command(edges, command.values))
    return tuple(result)
