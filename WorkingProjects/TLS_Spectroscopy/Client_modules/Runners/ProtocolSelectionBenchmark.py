"""Independent, temporary q3 protocol benchmark; importing never connects hardware.

Launch with ``python -m WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.ProtocolSelectionBenchmark``.
"""

from __future__ import annotations

from copy import deepcopy
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic
import traceback

from . import protocol_selection_benchmark as benchmark
from fluxpred import production as fluxpred_production


def runtime_settings(environ=None):
    environ = os.environ if environ is None else environ
    mode = str(environ.get("Q3_PROTOCOL_BENCHMARK_MODE", "full")).strip().lower()
    if mode not in {"full", "smoke", "five_point_ab"}:
        raise ValueError(
            "Q3_PROTOCOL_BENCHMARK_MODE must be full, smoke, or five_point_ab"
        )
    resume = str(environ.get("Q3_PROTOCOL_BENCHMARK_RESUME_MANIFEST", "")).strip()
    wait_for_return = str(
        environ.get("Q3_PROTOCOL_BENCHMARK_WAIT_FOR_RETURN", "0")
    ).strip().lower() in {"1", "true", "yes", "on"}
    return {
        "mode": mode,
        "resume_manifest": Path(resume) if resume else None,
        "overlap_payload_readout": not wait_for_return,
    }


def unity_timing_table(on):
    """Disable correction while retaining the exact stateful timing schedule."""
    off = fluxpred_production.timing_matched_unity(on)
    off["benchmark_predistortion_mode"] = "timing_matched_unity"
    off["source_model_sha256"] = on.get("model_sha256")
    return off


@dataclass
class PassPayload:
    rows: list
    metadata: dict


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _read_json(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def _cleanup(action):
    original = sys.exc_info()[1]
    try:
        action()
    except BaseException as exc:
        if original is None:
            raise
        detail = f"cleanup failed: {type(exc).__name__}: {exc}"
        if hasattr(original, "add_note"):
            original.add_note(detail)
        print(f"[benchmark] {detail}", file=sys.stderr, flush=True)


def _verify_calibration(manifest):
    calibration = manifest.get("calibration", {})
    path = calibration.get("path")
    if not path or calibration.get("sha256") != manifest.get("calibration_id"):
        raise ValueError("resume calibration provenance mismatch")
    if benchmark.sha256_file(path) != manifest["calibration_id"]:
        raise ValueError("resume calibration checksum mismatch")


def _read_pass_rows(path):
    """Decode the core CSV format for summaries when completed passes are resumed."""
    string_columns = {"pass_id", "protocol", "predistortion", "pass_started_at", "pass_ended_at"}
    boolean_columns = {"valid", "fit_success"}
    rows = []
    with Path(path).open(newline="", encoding="utf-8") as stream:
        for source in csv.DictReader(stream):
            row = {}
            for key, value in source.items():
                if key in string_columns:
                    row[key] = value
                elif key in boolean_columns:
                    row[key] = value == "True"
                elif key == "delays_us":
                    row[key] = json.loads(value) if value else []
                else:
                    row[key] = float(value) if value else float("nan")
            rows.append(row)
    return rows


def run_benchmark(*, backend, plan, output_dir, stem, resume_manifest=None, progress=True):
    """Calibrate once, acquire/checkpoint in canonical order, and close on every exit."""
    manifest_path = None
    active_pass = None
    try:
        benchmark.canonical_document(plan)
        if resume_manifest is not None:
            manifest_path = Path(resume_manifest).resolve()
            saved = _read_json(manifest_path)
            _verify_calibration(saved)
            # Validate artifacts and plan before permitting backend setup.
            benchmark.load_resume_manifest(
                manifest_path, plan, device=backend.device, controller=backend.controller,
                model_sha256=saved["model_provenance"]["sha256"],
                calibration_id=saved["calibration_id"],
            )
            backend.load_calibration(saved)
            manifest = benchmark.load_resume_manifest(
                manifest_path, plan, device=backend.device, controller=backend.controller,
                model_sha256=backend.model_provenance["sha256"], calibration_id=backend.calibration_id,
            )
            output_dir = manifest_path.parent
            stem = manifest["stem"]
        else:
            # The default NAS hierarchy becomes available after lazy setup.
            needs_calibration = output_dir is not None
            if output_dir is None:
                backend.calibrate()
                output_dir = backend.output_dir
            else:
                output_dir = Path(output_dir).resolve()
            manifest_path = output_dir / f"{stem}_manifest.json"
            if manifest_path.exists():
                raise FileExistsError(f"benchmark exists; explicitly resume {manifest_path}")
            if needs_calibration:
                backend.calibrate()
            manifest = benchmark.new_manifest(
                plan, device=backend.device, controller=backend.controller,
                code_commit=backend.code_commit, model_provenance=backend.model_provenance,
                calibration_id=backend.calibration_id,
            )
            manifest.update(stem=stem, created_at=_now_iso(), calibration=backend.calibration_provenance)
            benchmark.atomic_write_json(manifest_path, manifest)
        pending = benchmark.pending_passes(manifest, plan)
        manifest["status"] = "running"
        benchmark.atomic_write_json(manifest_path, manifest)
        suite_started = monotonic()
        for position, item in enumerate(pending):
            started_at = _now_iso()
            benchmark.record_pass_started(manifest_path, item.index, started_at=started_at)
            started = monotonic()
            durations = [entry["duration_s"] for entry in manifest["passes"] if entry["status"] == "complete"]
            eta = (sum(durations) / len(durations) * (len(pending) - position)) if durations else None
            eta_text = "unavailable" if eta is None else f"{eta / 60.0:.1f} min"
            print(f"[pass {item.index + 1:02d}/{len(plan.passes):02d}] {item.protocol} "
                  f"delays={list(item.delays_us)} us, {item.shots_per_condition} shots/condition, "
                  f"{item.shots_per_condition * item.condition_count} shots/frequency, "
                  f"{item.predistortion.upper()} | elapsed={(monotonic() - suite_started) / 60:.1f} min "
                  f"ETA={eta_text}", flush=True)
            raw_path, metadata_path = benchmark.artifact_paths(output_dir, stem, item)
            active_pass = item
            try:
                try:
                    payload = backend.acquire_pass(item, progress=progress)
                    ended_at = _now_iso()
                    for row in payload.rows:
                        row.update(pass_started_at=started_at, pass_ended_at=ended_at)
                    payload.metadata.update(pass_started_at=started_at, pass_ended_at=ended_at)
                    benchmark.write_pass_csv(raw_path, payload.rows)
                    benchmark.atomic_write_json(metadata_path, payload.metadata)
                finally:
                    _cleanup(backend.restore_park)
                manifest = benchmark.record_pass_complete(
                    manifest_path, item.index, raw_path=raw_path, metadata_path=metadata_path,
                    ended_at=ended_at, duration_s=monotonic() - started,
                )
            except BaseException as exc:
                benchmark.record_pass_failed(
                    manifest_path, item.index, error_type=type(exc).__name__, error_message=str(exc),
                    traceback_text=traceback.format_exc(), failed_at=_now_iso(),
                )
                raise
            active_pass = None
        summaries = []
        session = {**manifest, "passes": []}
        for entry in manifest["passes"]:
            rows = _read_pass_rows(entry["artifacts"]["raw_csv"]["path"])
            summaries.append(benchmark.summarize_pass(rows, duration_s=entry["duration_s"]))
            session["passes"].append({**entry, "rows": rows})
        summary_path = Path(output_dir) / f"{stem}_summary.csv"
        comparison_path = Path(output_dir) / f"{stem}_comparison.png"
        benchmark.write_summary_csv(summary_path, summaries)
        benchmark.render_comparison_figure(session, comparison_path)
        manifest.update(status="complete", ended_at=_now_iso(), summary_path=str(summary_path),
                        comparison_path=str(comparison_path))
        benchmark.atomic_write_json(manifest_path, manifest)
        for path in (manifest_path, summary_path, comparison_path):
            print(f"[benchmark] {path.resolve()}")
        return manifest
    except BaseException:
        # Per-pass cleanup ran above. Setup and aggregation failures also restore park.
        if active_pass is None:
            _cleanup(backend.restore_park)
        raise
    finally:
        _cleanup(backend.close)


class QickBenchmarkBackend:
    """Hardware setup is deferred until calibrate() or load_calibration()."""

    device = "q3"
    controller = "qick"

    def __init__(self, *, plan, environ=None):
        self.plan = plan
        self.environ = dict(os.environ if environ is None else environ)
        self.soc = None
        self.session = None

    def _setup(self):
        if self.soc is not None:
            raise RuntimeError("benchmark backend already initialized")
        benchmark.canonical_document(self.plan)
        self.hw = _load_hardware()
        tls, five = self.hw.tls, self.hw.five
        five.install_scan_calibration(tls)
        self.base = deepcopy(tls.BaseConfig)
        self.base["ff_park_gain"] = tls._baseline_dc_offset()
        self.code_commit = self.environ.get("Q3_CODE_COMMIT") or subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parent, text=True,
        ).strip()
        self.params = {
            "freq_min_ghz": self.plan.frequency_stop_ghz, "freq_max_ghz": self.plan.frequency_start_ghz,
            "freq_step_mhz": self.plan.frequency_step_mhz, "dc_min": -20550, "dc_max": -11800,
            "decay_delays_us": [40., 80., 120., 160., 200.], "reference_hold_us": 2.,
            "flux_settle_us": .5,
            "flux_predistortion_return_prefix_us": 24.,
            "flux_predistortion_recovery_us": 40.,
            "flux_predistortion_recovery_scale": .25,
        }
        selection_env = dict(self.environ)
        selection_env.setdefault("Q3_FLUXPRED_MODE", "neutral")
        self.neutral = five.resolve_neutral_selection(tls, environ=selection_env)
        if self.neutral["mode"] != "neutral":
            raise ValueError("benchmark requires Q3_FLUXPRED_MODE=neutral")
        self.tables = {"on": five.render_neutral_scan_compensation(self.neutral, self.params)}
        self.tables["off"] = unity_timing_table(self.tables["on"])
        self.model_provenance = self.hw.provenance(self.neutral, backend="qick", code_commit=self.code_commit)
        self.model_provenance["sha256"] = self.neutral["model_sha256"]
        self.target = self.hw.grid._target_frequency_grid_ghz(self.params)
        self.dc_vec, self.realized = self.hw.grid._integer_dc_grid(self.params, self.target, tls_module=tls)
        self.output_dir = (Path(tls.outerFolder) / tls.QUBIT / f"{tls.QUBIT}_{datetime.now():%Y_%m_%d}").resolve()
        tls._set_yoko_if_requested()
        self.soc, self.soccfg = tls.makeProxy()

    def _apply_session(self):
        wait_for_return = str(
            self.environ.get("Q3_PROTOCOL_BENCHMARK_WAIT_FOR_RETURN", "0")
        ).strip().lower() in {"1", "true", "yes", "on"}
        self.base.update({
            "ff_gain_vec": self.dc_vec, "flux_fit_params": self.hw.tls.FLUX_FIT_PARAMS,
            "qubit_pulse_style": "arb", "apply_flux_tail_compensation": True,
            "flux_predistortion_round_trip_mode": "stateful", "flux_predistortion_recovery_us": 40.,
            "flux_predistortion_return_prefix_us": 24.,
            "flux_settle_time_us": .5, "readout_thermalization_us": 10.,
            "opx_t1_3pt_gain_lookup": True, "opx_reverse_survival_order": False,
            "flux_predistortion_overlap_payload_readout": not wait_for_return,
        })
        self.base = self.session.apply(self.base)
        self.hw.five.apply_verified_feedback_timing(self.base)
        path = (Path(self.session.calibration_output) / "calibration.json").resolve()
        self.calibration_id = benchmark.sha256_file(path)
        self.calibration_provenance = {
            "path": str(path), "sha256": self.calibration_id,
            "method_frequency_mhz": self.session.method_frequency_mhz,
        }

    def calibrate(self):
        self._setup()
        self.session = self.hw.prepare_reset_session(
            self.plan.reset_mode, outer_folder=self.hw.tls.outerFolder, qubit=self.hw.tls.QUBIT,
            base_cfg=self.base, soc=self.soc, soccfg=self.soccfg, purpose="ProtocolSelectionBenchmark",
        )
        self._apply_session()

    def load_calibration(self, manifest):
        _verify_calibration(manifest)
        self._setup()
        if manifest["model_provenance"]["sha256"] != self.model_provenance["sha256"]:
            raise ValueError("resume model mismatch")
        calibration = manifest["calibration"]
        bundle = self.hw.load_calibration(calibration["path"])
        metadata = bundle.metadata
        if (metadata.get("qubit") != self.device
                or metadata.get("purpose") != "ProtocolSelectionBenchmark"
                or metadata.get("method_frequency_mhz") != calibration.get("method_frequency_mhz")):
            raise ValueError("resume calibration provenance mismatch")
        self.session = self.hw.ProductionResetSession.active(
            bundle.to_dict(), calibration["method_frequency_mhz"], Path(calibration["path"]).parent,
        )
        self._apply_session()
        if self.calibration_id != manifest["calibration_id"]:
            raise ValueError("resume calibration checksum mismatch")

    def acquire_pass(self, item, progress=True):
        if self.session is None:
            raise RuntimeError("benchmark must calibrate or load calibration before acquiring")
        table = deepcopy(self.tables[item.predistortion])
        cfg = deepcopy(self.base)
        cfg.update(shots=item.shots_per_condition, flux_tail_compensation=table)
        three_point = item.protocol.startswith("3pt")
        kwargs = dict(
            soc=self.soc, soccfg=self.soccfg, path=self.hw.tls.QUBIT, outerFolder=self.hw.tls.outerFolder,
            suffix=f"Protocol_Selection_Benchmark_{item.pass_id}", cfg=cfg, dc_vec=self.dc_vec,
            shots=item.shots_per_condition, calib_params=None, park_voltage=cfg["ff_park_gain"],
            reset_mode=cfg["reset_mode"], flux_tail_compensation=table, write_outputs=False,
            min_ref_contrast=.05,
        )
        if three_point:
            kwargs["Ts_ns"] = int(item.delays_us[0] * 1000)
            exp = self.hw.T13PointVsFlux(**kwargs)
        else:
            kwargs.update(decay_delays_us=item.delays_us, reference_hold_us=2., max_relative_error=.5,
                          max_fit_t1_us=3000.)
            exp = self.hw.T15PointVsFlux(**kwargs)
        exp.acquire(progress=progress)
        metadata = {
            "pass_index": item.index, "pass_id": item.pass_id, "protocol": item.protocol,
            "protocol_path": "three_point" if three_point else "n_point",
            "predistortion": item.predistortion, "delays_us": list(item.delays_us),
            "shots_per_condition": item.shots_per_condition, "condition_count": item.condition_count,
            "target_frequency_ghz": self.target, "fit_frequency_ghz": self.realized,
            "realized_frequency_ghz": self.realized, "flux_coordinate": self.dc_vec,
            "correction_mode": "neutral" if item.predistortion == "on" else "timing_matched_unity",
            "plan_fingerprint": benchmark.plan_fingerprint(self.plan),
            "model_provenance": self.model_provenance, "fluxpred_provenance": self.model_provenance,
            "calibration_id": self.calibration_id, "calibration": self.calibration_provenance,
            "code_commit": self.code_commit, "config": cfg,
            "flux_predistortion_recovery_scale": .25,
            "flux_predistortion_return_prefix_us": 24.,
        }
        exp.data.update(metadata)
        rows = benchmark.normalize_experiment_data(
            item, exp.data, target_frequency_ghz=self.target, realized_frequency_ghz=self.realized,
            flux_coordinate=self.dc_vec, requested_flux_coordinate=self.dc_vec, realized_flux_coordinate=self.dc_vec,
        )
        return PassPayload(rows, self.hw.json_safe(metadata))

    def restore_park(self):
        if self.soc is not None:
            streamer = getattr(self.soc, "streamer", None)
            if streamer is not None and streamer.readout_running():
                streamer.stop_readout()
            _restore_park(self.soc, self.soccfg, self.base)

    def close(self):
        if self.soc is not None:
            try:
                streamer = getattr(self.soc, "streamer", None)
                if streamer is not None and streamer.readout_running():
                    streamer.stop_readout()
            finally:
                release = getattr(self.soc, "_pyroRelease", None)
                if callable(release):
                    release()
                self.soc = None


def _load_hardware():
    """Keep QICK/Pyro and instrument initialization behind the execution boundary."""
    from types import SimpleNamespace
    from . import TLSSpectroscopy as tls
    from . import FivePointApplesToApples as five
    from . import ThreePointApplesToApples as grid
    from ..Experiments.mT1VsFlux import T13PointVsFlux, T15PointVsFlux
    from ..active_reset_OPX.production import prepare_reset_session, ProductionResetSession
    from ..active_reset_OPX.calibration import load_calibration
    from ..active_reset_OPX.analysis import json_safe
    from fluxpred.production import provenance
    return SimpleNamespace(tls=tls, five=five, grid=grid, T13PointVsFlux=T13PointVsFlux,
        T15PointVsFlux=T15PointVsFlux, prepare_reset_session=prepare_reset_session,
        ProductionResetSession=ProductionResetSession, load_calibration=load_calibration,
        json_safe=json_safe, provenance=provenance)


def _restore_park(soc, soccfg, cfg):
    from qick import AveragerProgram
    from ..Helpers import ff_pulse

    class ParkProgram(AveragerProgram):
        def initialize(self):
            ff_pulse.declare_ff(self)
            self.synci(200)

        def body(self):
            ff_pulse.play_hard_step(self, self.cfg["ff_park_gain"])
            self.sync_all(self.us2cycles(40.0))

    # No readout acquisition: run a single constant pulse with stdysel='last'.
    program = ParkProgram(soccfg, {**cfg, "reps": 1})
    program.config_all(soc, load_pulses=True, start_src="internal", debug=False)
    soc.tproc.start()


def main():
    settings = runtime_settings()
    plan = {
        "full": benchmark.full_plan,
        "smoke": benchmark.smoke_plan,
        "five_point_ab": benchmark.five_point_ab_plan,
    }[settings["mode"]]()
    backend = QickBenchmarkBackend(plan=plan)
    return run_benchmark(backend=backend, plan=plan, output_dir=None,
                         stem=benchmark.session_stem("q3", plan), resume_manifest=settings["resume_manifest"])


if __name__ == "__main__":
    main()
