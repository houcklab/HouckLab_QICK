import argparse
import json
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import numpy as np

from fluxpred import measurement, offline, schema
from fluxpred.core import Filter
from fluxpred.fit import Trace, fit_inverse, fit_plant

TRANSMON_KEYS = ("EJmax", "Ec", "period_volts", "phase_offset_volts", "d")


def transmon_frequency(coordinate, model):
    x = np.asarray(coordinate, dtype=float)
    phase = np.pi*(x-float(model["phase_offset_volts"]))/float(model["period_volts"])
    ej = float(model["EJmax"])*np.sqrt(np.cos(phase)**2+float(model["d"])**2*np.sin(phase)**2)
    return np.sqrt(8.0*ej*float(model["Ec"]))-float(model["Ec"])+float(model.get("tilt_slope", 0.0))*x


def static_model_callable(document):
    model = document["analysis"]["nominal_phase_model"]
    missing = [key for key in TRANSMON_KEYS if key not in model]
    if missing:
        raise schema.SchemaError(
            f"the measurement's static flux model is missing {missing}; the measured frequency "
            f"cannot be converted to a flux coordinate")
    return lambda coordinate: transmon_frequency(coordinate, model)


def load_traces(summary_paths, *, device, root=None, verify_hashes=True):
    traces, documents, analyses, commands = [], [], [], []
    for path in summary_paths:
        document = measurement.read_summary(path, device=device, verify_hashes=verify_hashes,
                                            hash_root=root)
        raw_path = schema.resolve_against(document["files"]["raw_csv"]["path"], root)
        raw = measurement.read_raw_csv(raw_path)
        command = measurement.command_from_summary(document, root=root)
        ideal = ideal_amplitude(command, raw["delay_ns"], document)
        analysis = measurement.trace_from_summary(
            document, raw, frequency_of_coordinate=static_model_callable(document),
            probe_frequency_ghz=probe_frequency(document), ideal_amplitude=ideal)
        traces.append(measurement.identification_trace(document, analysis, command))
        documents.append(document)
        analyses.append(analysis)
        commands.append(command)
    return traces, documents, analyses, commands


def probe_frequency(document):
    model = document["analysis"]["nominal_phase_model"]
    if "probe_frequency_ghz" not in model:
        raise schema.SchemaError(
            "the measurement's static flux model must record probe_frequency_ghz")
    return float(model["probe_frequency_ghz"])


def ideal_amplitude(command, delays_ns, document):
    amplitude = float(document["sequence"]["normalized_amplitude"])
    hold_ns = float(command.edges_ns[-1])-float(document["sequence"]["recovery_ns"])
    return np.where(np.asarray(delays_ns, dtype=float) < hold_ns, amplitude, 0.0)


def fit(traces, *, banks_us, regularizations, folds, horizon_ns, sample_ns, max_l1,
        static_gain=True):
    banks = [np.asarray(bank, dtype=float)*1000.0 for bank in banks_us]
    chosen = offline.select_plant_bank(traces, banks, regularizations=regularizations, folds=folds,
                                       static_gain=static_gain)
    taus = chosen["taus_ns"]
    plant = fit_plant(traces, taus, regularization=chosen["regularization"], max_l1=max_l1,
                      static_gain=static_gain)
    inverse = fit_inverse([plant["coefficients"]], taus, regularization=chosen["regularization"],
                          horizon_ns=horizon_ns, sample_ns=sample_ns)
    return chosen, plant, inverse


def evaluate(model, plant, *, amplitude, hold_ns, recovery_ns, sample_ns, probe_ns):
    cancellation = offline.inverse_cancellation(
        model, plant, amplitude=amplitude, horizon_ns=hold_ns, sample_ns=sample_ns,
        probe_ns=probe_ns)
    round_trip = offline.simulate_round_trip(
        model, plant, amplitude=amplitude, hold_ns=hold_ns, recovery_ns=recovery_ns,
        sample_ns=sample_ns, probe_ns=probe_ns)
    return cancellation, round_trip


def diagnostic_figure(path, *, analyses, traces, plant, model, cancellation, round_trip, taus_ns):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from fluxpred.fit import plant_response

    figure, axes = plt.subplots(3, 2, figsize=(14, 12))
    for index, analysis in enumerate(analyses):
        delays_us = np.asarray(analysis["delays_ns"], dtype=float)/1000.0
        support = np.asarray(analysis["support"], dtype=bool)
        for rung, window in enumerate(analysis["windows_ns"]):
            axes[0, 0].plot(delays_us, analysis["contrast"][rung], ".-",
                            label=f"trace {index} w={window:.0f}ns")
        axes[0, 1].plot(delays_us, analysis["resolved"]["resolved_phase_rad"], ".-",
                        label=f"trace {index} resolved")
        if np.any(~support):
            axes[0, 1].plot(delays_us[~support],
                            np.asarray(analysis["phases_rad"][-1])[~support], "rx",
                            label="masked" if index == 0 else None)
        axes[1, 0].plot(delays_us, analysis["residual_detuning_mhz"], ".-", label=f"trace {index}")
    for index, trace in enumerate(traces):
        support = np.asarray(trace.support, dtype=bool)
        predicted = ((1.0+plant.get("static_gain", 0.0))
                     * plant_response(trace.command, trace.time_ns, taus_ns,
                                      plant["coefficients"], probe_ns=trace.probe_ns)
                     + plant["offsets"][index])
        axes[1, 1].plot(trace.time_ns[support]/1000.0, trace.response[support], ".",
                        label=f"measured {index}")
        axes[1, 1].plot(trace.time_ns/1000.0, predicted, "-", label=f"plant fit {index}")
        axes[2, 0].plot(trace.time_ns[support]/1000.0,
                        (trace.response[support]-predicted[support])*1e3, ".",
                        label=f"residual {index} [1e-3]")
    axes[2, 0].axhline(0.0, color="k", linewidth=0.8)
    axes[2, 1].plot(np.asarray(round_trip["time_ns"])/1000.0, round_trip["response"],
                    label="round-trip forecast")
    axes[2, 1].plot(np.asarray(round_trip["time_ns"])/1000.0, round_trip["ideal"], "k--",
                    label="ideal")
    titles = ("X/Y contrast", "unwrapped phase [rad]", "residual detuning [MHz]",
              "unit-normalized amplitude", "plant fit residual [1e-3]", "return to park")
    for axis, title in zip(axes.ravel(), titles):
        axis.set_title(title)
        axis.set_xlabel("delay [us]")
        axis.grid(alpha=0.3)
        axis.legend(fontsize=7)
    figure.tight_layout()
    figure.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(figure)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, nargs="+", required=True)
    parser.add_argument("--device", required=True, choices=sorted(schema.DEVICES))
    parser.add_argument("--park", type=float, required=True)
    parser.add_argument("--scale", type=float, required=True)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--figure", type=Path)
    parser.add_argument("--banks-us", type=str, default="8,24,64,192;12,40,120,360")
    parser.add_argument("--regularizations", type=float, nargs="+",
                        default=list(offline.DEFAULT_REGULARIZATIONS))
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--max-l1", type=float, default=0.25)
    parser.add_argument("--emission-sample-ns", type=float, default=4000.0)
    parser.add_argument("--inverse-horizon-ns", type=float, default=1_000_000.0)
    parser.add_argument("--recovery-ns", type=float, default=1_600_000.0)
    parser.add_argument("--skip-hash-verification", action="store_true")
    parser.add_argument("--no-static-gain", action="store_true")
    parser.add_argument("--operator-note", default="")
    args = parser.parse_args(argv)

    banks_us = [[float(value) for value in bank.split(",")]
                for bank in args.banks_us.split(";") if bank.strip()]
    traces, documents, analyses, commands = load_traces(
        args.summary, device=args.device, root=args.root,
        verify_hashes=not args.skip_hash_verification)
    amplitude = float(documents[0]["sequence"]["normalized_amplitude"])
    hold_ns = float(commands[0].edges_ns[-1])-float(documents[0]["sequence"]["recovery_ns"])
    probe_ns = float(max(documents[0]["sequence"]["probe_windows_ns"]))

    chosen, plant, inverse = fit(
        traces, banks_us=banks_us, regularizations=tuple(args.regularizations), folds=args.folds,
        horizon_ns=args.inverse_horizon_ns, sample_ns=args.emission_sample_ns,
        max_l1=args.max_l1, static_gain=not args.no_static_gain)
    model = inverse["model"]
    cancellation, round_trip = evaluate(
        model, plant["coefficients"], amplitude=amplitude, hold_ns=hold_ns,
        recovery_ns=args.recovery_ns, sample_ns=args.emission_sample_ns, probe_ns=probe_ns)

    source_files, source_hashes = [], []
    for document in documents:
        for entry in document["files"].values():
            source_files.append(entry["path"])
            source_hashes.append(entry["sha256"])
    candidate = schema.build_model_document(
        device=args.device, park=args.park, scale=args.scale,
        taus_us=(chosen["taus_ns"]/1000.0).tolist(),
        coefficients=np.asarray(model.coefficients[0], dtype=float).tolist(),
        source_files=source_files, source_sha256=source_hashes,
        static_flux_model=documents[0]["analysis"]["nominal_phase_model"],
        fit_settings={"regularization": chosen["regularization"], "folds": int(args.folds),
                      "max_l1": float(args.max_l1),
                      "emission_sample_ns": float(args.emission_sample_ns),
                      "inverse_horizon_ns": float(args.inverse_horizon_ns),
                      "plant_coefficients": np.asarray(plant["coefficients"]).tolist(),
                      "plant_offsets": np.asarray(plant["offsets"]).tolist(),
                      "plant_rms": float(plant["rms"]),
                      "static_gain": float(plant.get("static_gain", 0.0)),
                      "static_gain_fitted": not args.no_static_gain,
                      "plant_condition_number": float(plant["condition_number"]),
                      "inverse_design_rms": float(inverse["design_rms"]),
                      "operator_note": str(args.operator_note)},
        cross_validation={"held_out_rms": chosen["held_out_rms"],
                          "best_held_out_rms": chosen["best_held_out_rms"],
                          "selected_taus_us": (chosen["taus_ns"]/1000.0).tolist(),
                          "table": chosen["table"],
                          "forecast_corrected_rms": float(cancellation["corrected_rms"]),
                          "forecast_uncorrected_rms": float(cancellation["uncorrected_rms"]),
                          "forecast_improvement": float(cancellation["improvement"]),
                          "round_trip_hold_error_rms": float(round_trip["hold_error_rms"]),
                          "round_trip_park_error_rms": float(round_trip["park_error_rms"]),
                          "round_trip_tail_bound": float(round_trip["tail_bound"]),
                          "supported_fraction": [float(a["supported_fraction"]) for a in analyses]},
        acceptance={"software": True, "scientific": False, "hardware": False},
        resolution_us=float(args.emission_sample_ns)/1000.0, max_l1=float(args.max_l1))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(candidate, indent=2, allow_nan=False)+"\n")
    figure_path = args.figure
    if figure_path is None:
        figure_path = args.out.with_name(args.out.stem+"_audit.png")
    diagnostic_figure(figure_path, analyses=analyses, traces=traces, plant=plant, model=model,
                      cancellation=cancellation, round_trip=round_trip,
                      taus_ns=chosen["taus_ns"])
    print(f"CANDIDATE_JSON={args.out}")
    print(f"DIAGNOSTIC_PNG={figure_path}")
    print(f"selected taus_us = {(chosen['taus_ns']/1000.0).tolist()}")
    print(f"regularization   = {chosen['regularization']:g}")
    print(f"held-out rms     = {chosen['held_out_rms']:.6g} (best {chosen['best_held_out_rms']:.6g})")
    print(f"plant            = {np.asarray(plant['coefficients']).tolist()}")
    print(f"static nuisance  = gain {plant.get('static_gain', 0.0):+.4f}, offsets "
          f"{np.round(np.asarray(plant['offsets']), 6).tolist()}")
    print(f"inverse          = {np.asarray(model.coefficients[0]).tolist()}  "
          f"L1={float(np.sum(np.abs(model.coefficients))):.4f}")
    print(f"forecast rms     = {cancellation['corrected_rms']:.6g} vs uncorrected "
          f"{cancellation['uncorrected_rms']:.6g} ({cancellation['improvement']:.1f}x)")
    print(f"round trip       = hold {round_trip['hold_error_rms']:.6g}, "
          f"park {round_trip['park_error_rms']:.6g}, tail {round_trip['tail_bound']:.3g}")
    print("acceptance.scientific=false until the exact production T1 lifecycle passes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
