"""Run a saved experiment again from its .h5 alone.

Every run's .h5 holds what is needed to repeat it (runner/save.py): the sequence, the station
as it was, the calibration it used, the IIR coefficient files and Bob's version. This module
rebuilds the experiment from those and checks it against the numbers saved for each point.

    python -m Bob.runner.rerun <run>_data.h5                   check that the saved inputs rebuild it
    python -m Bob.runner.rerun <run>_data.h5 --run             run it again on the RFSoC
    python -m Bob.runner.rerun <run>_data.h5 --run --simulate  ... or on the simulated board
    python -m Bob.runner.rerun <run>_data.h5 --sequence x.json write the sequence, to open it in Bob

Run from the folder that contains Bob/. A rerun uses the station as it was saved with the run,
including its hardware_verified flag and nameserver address.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np

from ..config.calibration import CalibrationStore
from ..config.resolver import Resolver
from ..config.station import Station
from ..core.sequence import Sequence
from .save import flatten_resolution


def _attrs_and_iir(path):
    import h5py
    with h5py.File(str(path), "r") as f:
        attrs = dict(f.attrs)
        iir = {name: np.asarray(ds[()]) for name, ds in f["iir"].items()} if "iir" in f else {}
        resolved = None
        if "resolved" in f:
            g = f["resolved"]
            resolved = {"constant": json.loads(g.attrs.get("constant", "{}")),
                        "varying": {ds.attrs["value"]: np.asarray(ds[()]) for ds in g.values()}}
    return attrs, iir, resolved


def inputs(path, workdir: Optional[str] = None):
    """(sequence, station, calibration) exactly as the run used them."""
    attrs, iir, _ = _attrs_and_iir(path)
    missing = [k for k in ("bob_sequence", "station", "calibration") if not attrs.get(k)]
    if missing:
        raise ValueError(f"{Path(path).name} was saved before Bob stored everything needed to rerun it "
                         f"(missing: {', '.join(missing)})")
    seq = Sequence.from_dict(json.loads(attrs["bob_sequence"]))
    folder = Path(workdir or tempfile.mkdtemp(prefix="bob_rerun_"))
    station_data = json.loads(attrs["station"])
    if iir:                                     # put the saved coefficient files where the station expects them
        iir_dir = folder / (station_data.get("compensation") or {}).get("iir_dir", "iir")
        iir_dir.mkdir(parents=True, exist_ok=True)
        for name, ab in iir.items():
            np.savetxt(iir_dir / name, ab)
    station = Station(station_data, folder=folder)
    calib = CalibrationStore(json.loads(attrs["calibration"]), path=attrs.get("calibration_path") or None,
                             sha256=attrs.get("calibration_sha256") or None)
    return seq, station, calib


def check(path) -> dict:
    """Rebuild every measured point from the saved inputs and compare it with the saved numbers.
    Returns {"points": n checked, "mismatches": [(point, value, saved, rebuilt), ...]}."""
    attrs, _, saved = _attrs_and_iir(path)
    seq, station, calib = inputs(path)
    if saved is None:
        raise ValueError(f"{Path(path).name} has no resolved values to compare with")
    n = int(attrs.get("points_done", seq.settings.n_points()))
    shape = tuple(max(1, a.points) for a in seq.settings.sweeps) or (1,)
    resolver = Resolver(station, calib)
    mismatches = []
    for k in range(n):
        flat = flatten_resolution(resolver.resolve(seq, seq.settings.point(k)))
        idx = np.unravel_index(k, shape)
        for key, value in flat.items():
            if key in saved["varying"]:
                want = saved["varying"][key][idx]
                same = np.allclose(np.asarray(value, float), want, rtol=1e-12, atol=0, equal_nan=True)
            else:
                want = saved["constant"].get(key, "<not saved>")
                same = value == want
            if not same:
                mismatches.append((k, key, want, value))
    return {"points": n, "mismatches": mismatches}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check or repeat a saved Bob run from its .h5.")
    parser.add_argument("file", help="the run's _data.h5")
    parser.add_argument("--run", action="store_true", help="run it again on the RFSoC")
    parser.add_argument("--simulate", action="store_true", help="with --run: on the simulated board")
    parser.add_argument("--out", help="with --run: folder to save under")
    parser.add_argument("--sequence", metavar="JSON", help="write the sequence to this file, to open in Bob")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    report = check(args.file)
    bad = report["mismatches"]
    print(f"{Path(args.file).name}: the saved inputs rebuild {report['points'] - len({m[0] for m in bad})} "
          f"of {report['points']} measured points exactly.")
    for k, key, want, got in bad[:10]:
        print(f"  point {k}, {key}: saved {want!r}, rebuilt {got!r}")
    if args.sequence:
        seq, _, _ = inputs(args.file)
        seq.save(args.sequence)
        print(f"Wrote {args.sequence}")
    if args.run:
        from . import script
        seq, station, calib = inputs(args.file)
        script.run(seq, station, calib, out_folder=args.out, simulate=args.simulate)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
