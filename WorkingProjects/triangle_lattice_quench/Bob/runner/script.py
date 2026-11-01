"""What an exported experiment script does: check, plot, or run on the RFSoC.

Exported scripts (runner/export.py) hold only their frozen inputs and call these functions,
so every script shares one tested copy of the logic.

    check()   compiles every sweep point; no hardware
    plot()    draws the flux waveforms and drives at one sweep point (matplotlib)
    run()     connects, acquires every point, saves each point as it is measured and plots it
              live; refuses until the station is marked as verified at the lab
              (station.json "hardware_verified"), unless overridden
    show_data()  plots a saved run
    run(simulate=True)  the whole run on the simulated board (runner/simulate.py): no RFSoC
"""
from __future__ import annotations

from typing import Optional

from ..compiler.tlq_backend import compile_sequence
from ..config.station import Station
from ..core.colors import qubit_color_hex
from .experiment import BobExperiment


def hardware_ready(station: Station) -> list:
    """Reasons the station is not yet trusted for real runs; empty when it is."""
    from ..hardware.compensation import Compensator
    reasons = []
    if not station.data.get("hardware_verified", False):
        reasons.append("station.json has hardware_verified = false: the first-lab-run checklist in "
                       "Bob/README.md has not been signed off")
    if not Compensator.from_station(station).available():
        reasons.append(f"IIR coefficient files are missing from library/stations/{station.name}/iir/, "
                       "so the flux would be uncompensated")
    return reasons


def check(seq, station, calib, out=print) -> bool:
    """Compile every sweep point and report. Returns True when all compile."""
    result = BobExperiment(seq, station, calib).dry_run()
    out(f"{seq.name}: {result['n_ok']} of {result['n']} sweep points compile.")
    bad = [p for p in result["points"] if not p["ok"]]
    for p in bad[:5]:
        out(f"  point {p['index']} {p['point']}: " + "; ".join(p["errors"]))
    if len(bad) > 5:
        out(f"  ... and {len(bad) - 5} more failing points")
    for reason in hardware_ready(station):
        out(f"Not ready for --run: {reason}.")
    return not bad


def plot(seq, station, calib, index: int = 0, show: bool = True):
    """Figure of the compiled flux (per channel) and drive pulses at sweep point ``index``."""
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    n_points = seq.settings.n_points()
    if not 0 <= index < n_points:
        raise ValueError(f"sweep point {index} is out of range (0 to {n_points - 1})")
    point = seq.settings.point(index)
    compiled, _, problems = compile_sequence(seq, station, calib, point)
    if compiled is None:
        raise RuntimeError("does not compile: " + "; ".join(str(p) for p in problems if p.level == "error"))
    t = compiled.time_axis_us()
    fig, (ax_ff, ax_dr) = plt.subplots(2, 1, sharex=True, figsize=(10, 6), height_ratios=[3, 1])
    for j in range(compiled.ff.shape[0]):
        ax_ff.plot(t, compiled.ff[j], lw=1.2, color=qubit_color_hex(j + 1), label=f"Q{j + 1}")
    for b, name in zip(compiled.segment_bounds, compiled.segment_names):
        x = b / compiled.samples_per_us
        ax_ff.axvline(x, color="0.7", lw=0.8, ls="--")
        ax_ff.text(x, ax_ff.get_ylim()[1], f" {name}", va="top", fontsize=8, color="0.35")
    for d in compiled.drives:
        xs = d.t_us + np.linspace(0, d.length_us, 200)
        mid, sig = d.t_us + d.length_us / 2, max(d.sigma_us, 1e-9)
        ax_dr.plot(xs, d.qubit + 0.4 * np.exp(-0.5 * ((xs - mid) / sig) ** 2), lw=1.2,
                   color=qubit_color_hex(d.qubit))
    ax_ff.set_ylabel("FF gain (DAC)")
    ax_ff.legend(ncol=8, fontsize=8, loc="lower center", bbox_to_anchor=(0.5, 1.0), frameon=False)
    ax_dr.set_ylabel("Drive (qubit)")
    ax_dr.set_xlabel("Time from start of FF body (µs)")
    label = ", ".join(f"{k} = {v:.4g}" for k, v in point.items())
    fig.suptitle(f"{seq.name}: sweep point {index}" + (f" ({label})" if label else ""), y=0.99)
    fig.tight_layout()
    if show:
        plt.show()
    return fig


def run(seq, station, calib, out_folder: Optional[str] = None, override: bool = False, out=print,
        live_plot: bool = True, show_plot: bool = True, connect=None, program_class=None,
        simulate: bool = False):
    """Connect to the station's RFSoC, acquire every point, save as it goes. Returns the .h5 path.

    The .h5 is created before the first point and each point is written as it is measured, so
    a crash or Ctrl+C keeps everything measured so far. The board's own config is saved next to
    it. With ``live_plot`` the figure is redrawn as points arrive and saved as a PNG.
    ``simulate`` runs on the simulated board (runner/simulate.py) instead: no RFSoC, made-up
    data, saved under <folder>/_simulated. ``connect`` and ``program_class`` replace the board
    in tests."""
    if simulate:
        from .simulate import SimulatedProgram, simulated_connect
        connect, program_class = connect or simulated_connect, program_class or SimulatedProgram
    else:
        reasons = hardware_ready(station)
        if reasons and not override:
            raise SystemExit("Refusing to run on hardware:\n  - " + "\n  - ".join(reasons) +
                             "\nComplete the checklist in Bob/README.md, or pass --i-know-it-is-unverified. "
                             "To try the run without the board, pass --simulate.")
    if not check(seq, station, calib, out=out):
        raise SystemExit("Some sweep points do not compile; fix them first.")
    from ..config.snapshot import make_snapshot
    from .save import RunWriter, board_config_text, check_board_config, run_folder_for
    if connect is None:
        from ..hardware.connection import connect_station as connect
    soc, soccfg = connect(station)
    board = None if simulate else board_config_text(soccfg)
    board_check = "simulated run: no board" if simulate else check_board_config(station, board)
    if not simulate:
        out(f"Board config: {board_check}.")
    exp = BobExperiment(seq, station, calib, soc, soccfg, program_class=program_class)
    writer = RunWriter(run_folder_for(seq, station, out_folder, simulate), seq,
                       make_snapshot(seq, station, calib, max_points=1), board_config=board,
                       board_check=board_check, simulated=simulate, station=station, calib=calib)
    out(f"Saving to {writer.path}" + ("  (simulated data)" if simulate else ""))
    exp.on_resolved(writer.write_resolved)
    exp.on_point(writer.write_point)
    figure = None
    if live_plot:
        from .live_plot import RunPlot, plot_layout
        figure = RunPlot(plot_layout(seq, simulated=simulate), show=show_plot)
        exp.on_point(figure.add_point)
    n = seq.settings.n_points()
    status = "complete"
    try:
        exp.run(progress=lambda k, total: out(f"  point {k} of {total}"), snapshot=False)
    except KeyboardInterrupt:
        status = f"stopped by Ctrl+C after {writer.points_done} of {n} points"
        out(status)
    except Exception as exc:
        status = f"failed after {writer.points_done} of {n} points: {exc}"
        raise
    finally:
        path = writer.close(status)
        if figure is not None:
            from .live_plot import png_path
            figure.save(png_path(path))
            if not show_plot:
                figure.plt.close(figure.fig)        # nothing will show it; free it
        out(f"Saved {path} ({status})")
    return path


def show_data(path, show: bool = True):
    """Plot a saved run (``--show-data``)."""
    from .live_plot import show_saved
    return show_saved(path, show=show)
