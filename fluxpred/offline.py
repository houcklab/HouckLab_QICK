import numpy as np

from .core import Command, render, tail_bound
from .fit import Trace, fit_plant, plant_response


def forecast(model, amplitude, plant, trace, *, sample_ns=None):
    new, _ = render(model, [(amplitude, trace.command.edges_ns[-1])], sample_ns=sample_ns)
    unit = Command(new.edges_ns, new.values/amplitude)
    before = plant_response(trace.command, trace.time_ns, model.taus_ns, plant, probe_ns=trace.probe_ns)
    after = plant_response(unit, trace.time_ns, model.taus_ns, plant, probe_ns=trace.probe_ns, freeze_probe=False)
    return trace.response+after-before


def blocked_plant_score(traces, taus_ns, *, regularization, folds=5):
    errors = []
    for fold in range(folds):
        training, masks = [], []
        for tr in traces:
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
    end = max(a.edges_ns[-1], b.edges_ns[-1])
    result = []
    for command in (a, b):
        if abs(command.values[-1]) > terminal_tolerance:
            raise ValueError("comparison requires exact terminal zero park")
        edges = command.edges_ns.copy(); edges[-1] = end
        result.append(Command(edges, command.values))
    return tuple(result)


CANDIDATE_BANKS_US = ((8.0, 24.0, 64.0, 192.0), (12.0, 40.0, 120.0, 360.0))
DEFAULT_REGULARIZATIONS = (1e-5, 1e-4, 1e-3, 1e-2)


def select_plant_bank(traces, banks_ns, *, regularizations=DEFAULT_REGULARIZATIONS, folds=5,
                      simpler_within=0.05):
    if not banks_ns:
        raise ValueError("at least one candidate pole bank is required")
    if not regularizations:
        raise ValueError("at least one regularization value is required")
    table = []
    for bank in banks_ns:
        taus = np.asarray(bank, float)
        for regularization in regularizations:
            try:
                score = blocked_plant_score(traces, taus, regularization=regularization, folds=folds)
            except (ValueError, np.linalg.LinAlgError) as error:
                table.append({"taus_ns": taus.tolist(), "regularization": float(regularization),
                              "held_out_rms": float("inf"), "order": int(taus.size),
                              "rejected": str(error)})
                continue
            table.append({"taus_ns": taus.tolist(), "regularization": float(regularization),
                          "held_out_rms": float(score), "order": int(taus.size), "rejected": None})
    usable = [row for row in table if row["rejected"] is None and np.isfinite(row["held_out_rms"])]
    if not usable:
        raise ValueError("no candidate pole bank produced a finite held-out score")
    best = min(usable, key=lambda row: row["held_out_rms"])
    threshold = best["held_out_rms"] * (1.0 + float(simpler_within))
    adequate = [row for row in usable if row["held_out_rms"] <= threshold]
    chosen = min(adequate, key=lambda row: (row["order"], row["held_out_rms"]))
    return {"taus_ns": np.asarray(chosen["taus_ns"], float),
            "regularization": chosen["regularization"],
            "held_out_rms": chosen["held_out_rms"],
            "best_held_out_rms": best["held_out_rms"],
            "simpler_within": float(simpler_within), "folds": int(folds), "table": table}


def simulate_round_trip(model, plant_coefficients, *, amplitude, hold_ns, recovery_ns,
                        initial_state=None, sample_ns=None, probe_ns=0, samples=2001):
    command, state = render(model, [(amplitude, float(hold_ns)), (0.0, float(recovery_ns))],
                            initial_state=initial_state, sample_ns=sample_ns)
    horizon = float(command.edges_ns[-1])
    time_ns = np.linspace(0.0, horizon, int(samples), endpoint=False)
    if probe_ns:
        time_ns = time_ns[time_ns + float(probe_ns) <= horizon]
    response = plant_response(command, time_ns, model.taus_ns, plant_coefficients, probe_ns=probe_ns)
    ideal = np.where(time_ns < float(hold_ns), float(amplitude), 0.0)
    during = time_ns < float(hold_ns)
    after = ~during
    return {"time_ns": time_ns, "command": command, "response": response, "ideal": ideal,
            "error": response - ideal, "state_after_recovery": state,
            "tail_bound": tail_bound(state),
            "hold_error_rms": float(np.sqrt(np.mean((response[during] - amplitude) ** 2)))
            if np.any(during) else float("nan"),
            "park_error_rms": float(np.sqrt(np.mean(response[after] ** 2)))
            if np.any(after) else float("nan"),
            "max_abs_error": float(np.max(np.abs(response - ideal)))}


def inverse_cancellation(model, plant_coefficients, *, amplitude, horizon_ns, sample_ns=None,
                         probe_ns=0, samples=2001, settle_fraction=0.5):
    command, _ = render(model, [(amplitude, float(horizon_ns))], sample_ns=sample_ns)
    time_ns = np.linspace(0.0, float(horizon_ns), int(samples), endpoint=False)
    if probe_ns:
        time_ns = time_ns[time_ns + float(probe_ns) <= float(horizon_ns)]
    corrected = plant_response(command, time_ns, model.taus_ns, plant_coefficients, probe_ns=probe_ns)
    uncorrected_command = Command([0.0, float(horizon_ns)], [float(amplitude)])
    uncorrected = plant_response(uncorrected_command, time_ns, model.taus_ns, plant_coefficients,
                                 probe_ns=probe_ns)
    late = time_ns >= float(settle_fraction) * float(horizon_ns)
    return {"time_ns": time_ns, "corrected": corrected, "uncorrected": uncorrected,
            "corrected_rms": float(np.sqrt(np.mean((corrected - amplitude) ** 2))),
            "uncorrected_rms": float(np.sqrt(np.mean((uncorrected - amplitude) ** 2))),
            "corrected_late_mean": float(np.mean(corrected[late])),
            "improvement": float(np.sqrt(np.mean((uncorrected - amplitude) ** 2))
                                 / max(np.sqrt(np.mean((corrected - amplitude) ** 2)), 1e-15))}
