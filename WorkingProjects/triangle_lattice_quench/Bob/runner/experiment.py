"""BobExperiment: sweep, compile, acquire, stream results, save.

One class for every experiment: sweep axes are data in the sequence, so there is no
subclass per sweep or plot. Each point's result goes to ``on_point`` listeners as soon as it
is measured (the run's file writer, the live plot, Desq), and plotting never runs inside
acquisition.

Status: the dry run is in use. The hardware loop below has not been run on the RFSoC yet;
Run stays off until the station is marked as verified at the lab (script.hardware_ready).
"""
from __future__ import annotations

from typing import Callable, Optional

import numpy as np

from ..compiler.tlq_backend import compile_sequence
from ..config.calibration import CalibrationStore
from ..config.problems import has_errors
from ..config.snapshot import make_snapshot
from ..config.station import Station
from ..core.sequence import Sequence
from .populations import populations


class BobExperiment:
    def __init__(self, seq: Sequence, station: Station, calib: CalibrationStore, soc=None, soccfg=None,
                 program_class=None):
        self.seq, self.station, self.calib = seq, station, calib
        self.soc, self.soccfg = soc, soccfg
        # the QICK program to build per point; BobProgram unless a test supplies a stand-in
        self.program_class = program_class
        self.listeners: list = []
        self.resolved_listeners: list = []
        self._stop = False

    def on_point(self, fn: Callable) -> None:
        """``fn(k, point, data)`` after sweep point k is measured."""
        self.listeners.append(fn)

    def on_resolved(self, fn: Callable) -> None:
        """``fn(k, resolved)`` with every resolved number of sweep point k, before it is measured."""
        self.resolved_listeners.append(fn)

    def stop(self) -> None:
        self._stop = True

    # ------------------------------------------------------------------ dry run
    def dry_run(self) -> dict:
        """Compile every sweep point without hardware. Returns a summary per point."""
        out = []
        for k, pt in self.seq.settings.iter_points():
            compiled, res, problems = compile_sequence(self.seq, self.station, self.calib, pt)
            out.append({"index": k, "point": pt, "ok": compiled is not None,
                        "samples": compiled.n_samples if compiled else None,
                        "errors": [str(p) for p in problems if p.level == "error"]})
        return {"points": out, "n_ok": sum(p["ok"] for p in out), "n": len(out)}

    # ------------------------------------------------------------------ run
    def run(self, progress: Optional[Callable] = None, snapshot: bool = True) -> dict:
        """Acquire every sweep point on the RFSoC. Returns arrays shaped (n_readouts, *sweep_shape):

        ``I``, ``Q`` (averaged), and for population modes ``population`` and, with a confusion
        matrix, ``population_corrected``; plus each sweep axis's values and a ``snapshot``.
        """
        if self.soc is None or self.soccfg is None:
            raise RuntimeError("not connected to an RFSoC")
        program_class = self.program_class
        if program_class is None:
            from ..hardware.bob_program import BobProgram
            program_class = BobProgram
        settings = self.seq.settings
        shape = [max(1, a.points) for a in settings.sweeps] or [1]
        results: dict = {}
        self._stop = False
        for k, pt in settings.iter_points():
            if self._stop:
                break
            compiled, res, problems = compile_sequence(self.seq, self.station, self.calib, pt)
            if compiled is None or has_errors(problems):
                raise RuntimeError(f"point {k} {pt} does not compile: " +
                                   "; ".join(str(p) for p in problems if p.level == "error"))
            for fn in self.resolved_listeners:
                fn(k, res)
            cfg = dict(compiled.qick_cfg)
            cfg["bob_point"] = {"index": k, "shape": shape, "values": pt}   # which sweep point; the board ignores it
            prog = program_class(self.soccfg, reps=cfg["reps"], final_delay=cfg["relax_delay"], cfg=cfg)
            point = self._acquire_point(prog, cfg)
            idx = np.unravel_index(k, shape)
            for key, vals in point.items():
                if key not in results:
                    results[key] = np.full((len(vals), *shape), np.nan)
                results[key][(slice(None), *idx)] = vals
            for fn in self.listeners:
                fn(k, pt, point)
            if progress:
                progress(k + 1, settings.n_points())
        for a in settings.sweeps:
            results[a.name] = a.values()
        if snapshot:
            results["snapshot"] = make_snapshot(self.seq, self.station, self.calib, max_points=200)
        return results

    @property
    def stopped(self) -> bool:
        return self._stop

    def _acquire_point(self, prog, cfg) -> dict:
        """One sweep point: {key: one value per readout channel}."""
        rounds = cfg.get("rounds", 1)
        if str(cfg.get("bob_measure_mode", "iq")).startswith("populations"):
            shots_i, shots_q = prog.acquire_shots(self.soc, rounds=rounds, progress=False)
            out = {"I": np.array([np.mean(x) for x in shots_i]), "Q": np.array([np.mean(x) for x in shots_q])}
            pops = populations(shots_i, shots_q, cfg)
            out["population"] = pops["population"]
            if cfg["bob_measure_mode"] == "populations_corrected" and "population_corrected" in pops:
                out["population_corrected"] = pops["population_corrected"]
            return out
        iq = prog.acquire(self.soc, rounds=rounds, progress=False)
        # acquire() returns one (triggers, 2) array per readout channel; Bob triggers once per shot
        iq = np.asarray([np.asarray(x)[..., 0, :] for x in iq])   # (n_ro, 2)
        return {"I": iq[:, 0], "Q": iq[:, 1]}
