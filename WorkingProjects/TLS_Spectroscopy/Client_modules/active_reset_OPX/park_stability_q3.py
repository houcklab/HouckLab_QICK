"""Standalone q3 prerequisite test for OPX-equivalent flux parking.

This runner deliberately exercises a continuously played channel-3 hold only
inside each shot, then ramps back to zero.  It does not enable active reset and
does not leave the flux line parked after a run or an interrupted acquisition.
"""

from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np


_root = Path(__file__).resolve()
for parent in _root.parents:
    if (parent / "WorkingProjects").is_dir():
        if str(parent) not in sys.path:
            sys.path.insert(0, str(parent))
        _repo_root = parent
        break
else:
    raise RuntimeError("Could not locate the HouckLab_QICK repository root")


from WorkingProjects.TLS_Spectroscopy.Client_modules.Calib.initialize import (
    BaseConfig,
    outerFolder,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.TLS_Spectroscopy.Client_modules.active_reset_OPX.park_stability import (
    build_frequency_axis_mhz,
    build_park_probe_config,
    summarize_park_trace,
)


# ---------------------------------------------------------------------------
# User-editable settings
# ---------------------------------------------------------------------------

QUBIT = "q3"

# None means inherit the current calibrated value from Calib/initialize.py.
PARK_GAIN = None
CENTER_FREQUENCY_MHZ = None

# The earlier +32000 test drifted by about 0.09 MHz/us.  A +/-25 MHz map keeps
# that entire trajectory visible over the active-reset window instead of
# falsely reporting a flat trace after the resonance leaves the sweep.
FREQUENCY_HALF_SPAN_MHZ = 25.0
FREQUENCY_STEP_MHZ = 0.5
DELAY_US = (0.5, 2.0, 5.0, 10.0, 20.0, 40.0, 60.0, 80.0, 120.0, 160.0)

SHOTS = 100
INTERLEAVE_ROUNDS = 4
SPECTROSCOPY_GAIN = 15000
SPECTROSCOPY_LENGTH_US = 0.5
PASSIVE_RESET_US = 400.0

# This 120 us window conservatively covers the eight-attempt OPX-style loop
# with the current 5 us readout and 2 us decision/feedback delays.
ACTIVE_RESET_WINDOW_US = 120.0
MAX_ALLOWED_DRIFT_MHZ = 0.5
EDGE_GUARD_MHZ = 1.0


def main():
    park_gain = int(BaseConfig["ff_park_gain"] if PARK_GAIN is None else PARK_GAIN)
    center_mhz = float(
        BaseConfig.get("qubit_pi_freq", BaseConfig["qubit_freq"])
        if CENTER_FREQUENCY_MHZ is None
        else CENTER_FREQUENCY_MHZ
    )
    delay_us = np.asarray(DELAY_US, dtype=float)
    if delay_us.size < 3 or not np.all(np.isfinite(delay_us)) or np.any(delay_us <= 0):
        raise ValueError("DELAY_US must contain at least three positive finite delays")
    if np.any(np.diff(delay_us) <= 0):
        raise ValueError("DELAY_US must be strictly increasing")
    if int(INTERLEAVE_ROUNDS) <= 0 or int(INTERLEAVE_ROUNDS) > int(SHOTS):
        raise ValueError("INTERLEAVE_ROUNDS must be in the range 1..SHOTS")

    frequency_mhz = build_frequency_axis_mhz(
        center_mhz, FREQUENCY_HALF_SPAN_MHZ, FREQUENCY_STEP_MHZ
    )
    cfg = build_park_probe_config(
        BaseConfig,
        park_gain=park_gain,
        frequency_axis_mhz=frequency_mhz,
        shots=SHOTS,
        spectroscopy_gain=SPECTROSCOPY_GAIN,
        spectroscopy_length_us=SPECTROSCOPY_LENGTH_US,
        passive_reset_us=PASSIVE_RESET_US,
    )
    cfg["interleave_rounds"] = int(INTERLEAVE_ROUNDS)

    now = datetime.now()
    output_dir = (
        Path(outerFolder)
        / QUBIT
        / f"{QUBIT}_{now:%Y_%m_%d}"
        / f"{QUBIT}_{now:%H_%M_%S}_active_reset_OPX_park_stability"
    )
    output_dir.mkdir(parents=True, exist_ok=False)

    try:
        source_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=_repo_root, text=True
        ).strip()
    except Exception:
        source_commit = "unknown"

    metadata = {
        "purpose": "OPX-style active-reset park prerequisite",
        "created": now.isoformat(),
        "source_commit": source_commit,
        "qubit": QUBIT,
        "park_gain_dac": park_gain,
        "center_frequency_mhz": center_mhz,
        "frequency_half_span_mhz": float(FREQUENCY_HALF_SPAN_MHZ),
        "frequency_step_mhz": float(FREQUENCY_STEP_MHZ),
        "delay_us": delay_us.tolist(),
        "shots_per_point": int(SHOTS),
        "interleave_rounds": int(INTERLEAVE_ROUNDS),
        "active_reset_window_us": float(ACTIVE_RESET_WINDOW_US),
        "max_allowed_drift_mhz": float(MAX_ALLOWED_DRIFT_MHZ),
        "flux_tail_compensation_applied": False,
        "park_between_shots": False,
        "readout_while_parked": True,
        "effective_config": cfg,
    }
    (output_dir / "run_metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n"
    )

    print("\nOPX park prerequisite | q3")
    print(f"Output: {output_dir}")
    print(f"Channel 3 target: {park_gain:+d} DAC")
    print(
        f"Qubit sweep: {frequency_mhz[0]:.3f} to {frequency_mhz[-1]:.3f} MHz "
        f"in {frequency_mhz[1] - frequency_mhz[0]:.3f} MHz steps"
    )
    print(
        f"Criterion: |f(t)-f({delay_us[0]:g} us)| <= {MAX_ALLOWED_DRIFT_MHZ:g} MHz "
        f"through {ACTIVE_RESET_WINDOW_US:g} us"
    )
    print("Safety mode: ramp to park and back to zero every shot; no correction.\n")

    import qick

    if str(qick.__version__) != "0.2.133":
        raise RuntimeError(
            f"This test is validated for qick 0.2.133, found {qick.__version__}"
        )

    import matplotlib

    matplotlib.use("Agg", force=True)
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments.mQubitFluxStepResponse import (
        FFStepResponseSpecProgram,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.acquisition import (
        interleaved_average,
        suppress_stdout,
    )
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers.trace_extraction import (
        extract_trace_from_map,
    )

    soc, soccfg = makeProxy()
    assembly_saved = False

    def run_point(index, reps):
        nonlocal assembly_saved
        run_cfg = dict(cfg)
        run_cfg["ff_hold"] = float(delay_us[index])
        run_cfg["reps"] = int(reps)
        with suppress_stdout():
            program = FFStepResponseSpecProgram(soccfg, run_cfg)
        if not assembly_saved:
            assembly = program.asm()
            (output_dir / "park_probe.asm").write_text(assembly)
            binary = np.asarray(program.compile(), dtype=np.uint64)
            (output_dir / "park_probe.asm.sha256").write_text(
                hashlib.sha256(binary.tobytes()).hexdigest() + "\n"
            )
            assembly_saved = True
        with suppress_stdout():
            _x, avgi, avgq = program.acquire(
                soc, load_pulses=True, progress=False
            )
        return np.asarray(avgi[0][0]) + 1j * np.asarray(avgq[0][0])

    def progress(done, total):
        print(f"  acquisition program {done}/{total}", end="\r", flush=True)

    def save_partial(round_index, running):
        np.savez_compressed(
            output_dir / "park_stability_partial.npz",
            complex_iq=np.asarray(running).T,
            frequency_mhz=frequency_mhz,
            delay_us=delay_us,
            completed_rounds=int(round_index) + 1,
        )

    mean_iq = interleaved_average(
        run_point,
        len(delay_us),
        int(SHOTS),
        rounds=int(INTERLEAVE_ROUNDS),
        live=save_partial,
        progress=progress,
    ).T
    print()

    magnitude_db = 20.0 * np.log10(np.abs(mean_iq) + 1e-12)
    phase_rad = np.angle(mean_iq)
    trace = extract_trace_from_map(
        magnitude_db,
        frequency_mhz / 1e3,
        delay_us * 1e3,
        center_mhz / 1e3,
        center_mhz / 1e3,
        float(FREQUENCY_HALF_SPAN_MHZ) / 1e3,
        trace_tracking_mode="ridge",
        trace_polarity="auto",
        trace_max_jump_mhz=8.0,
        trace_local_fit_half_window_mhz=8.0,
        trace_smoothing_window_points=7,
        trace_smoothing_polyorder=2,
        trace_use_smoothed_frequency=False,
    )
    extracted_frequency_mhz = np.asarray(trace["selected_frequency_ghz"]) * 1e3
    supported = np.asarray(trace["supported"], dtype=bool)
    summary = summarize_park_trace(
        delay_us=delay_us,
        frequency_mhz=extracted_frequency_mhz,
        supported=supported,
        sweep_min_mhz=float(frequency_mhz[0]),
        sweep_max_mhz=float(frequency_mhz[-1]),
        active_reset_window_us=ACTIVE_RESET_WINDOW_US,
        max_allowed_drift_mhz=MAX_ALLOWED_DRIFT_MHZ,
        edge_guard_mhz=max(float(EDGE_GUARD_MHZ), 2.0 * float(FREQUENCY_STEP_MHZ)),
    )
    summary.update({
        "park_gain_dac": park_gain,
        "trace_polarity": trace.get("polarity"),
        "frequency_sweep_mhz": [float(frequency_mhz[0]), float(frequency_mhz[-1])],
    })

    np.savez_compressed(
        output_dir / "park_stability_raw.npz",
        complex_iq=mean_iq,
        magnitude_db=magnitude_db,
        phase_rad=phase_rad,
        frequency_mhz=frequency_mhz,
        delay_us=delay_us,
        extracted_frequency_mhz=extracted_frequency_mhz,
        extracted_fwhm_hz=np.asarray(trace["extracted_fwhm_hz"], dtype=float),
        supported=supported,
    )
    raw_rows = np.column_stack((
        np.broadcast_to(delay_us[None, :], magnitude_db.shape).ravel(),
        np.broadcast_to(frequency_mhz[:, None], magnitude_db.shape).ravel(),
        magnitude_db.ravel(),
        phase_rad.ravel(),
    ))
    np.savetxt(
        output_dir / "park_stability_raw.csv",
        raw_rows,
        delimiter=",",
        header="delay_us,probe_frequency_mhz,magnitude_db,phase_rad",
        comments="",
    )
    first_supported = np.flatnonzero(supported & np.isfinite(extracted_frequency_mhz))
    reference = (
        float(extracted_frequency_mhz[first_supported[0]])
        if first_supported.size
        else float("nan")
    )
    trace_rows = np.column_stack((
        delay_us,
        extracted_frequency_mhz,
        extracted_frequency_mhz - reference,
        np.asarray(trace["extracted_fwhm_hz"], dtype=float) / 1e6,
        supported.astype(int),
    ))
    np.savetxt(
        output_dir / "park_stability_trace.csv",
        trace_rows,
        delimiter=",",
        header="delay_us,qubit_frequency_mhz,frequency_minus_first_mhz,fwhm_mhz,trace_supported",
        comments="",
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )

    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 1, figsize=(9, 11), constrained_layout=True)
    magnitude_plot = axes[0].pcolormesh(
        delay_us, frequency_mhz, magnitude_db, shading="auto"
    )
    fig.colorbar(magnitude_plot, ax=axes[0], label="Magnitude [dB]")
    axes[0].plot(delay_us, extracted_frequency_mhz, "w.-", lw=1.0, label="extracted")
    axes[0].set(ylabel="Probe frequency [MHz]", title="Qubit spectroscopy while channel 3 is held")
    axes[0].legend(loc="best")

    phase_plot = axes[1].pcolormesh(
        delay_us, frequency_mhz, phase_rad, shading="auto"
    )
    fig.colorbar(phase_plot, ax=axes[1], label="Phase [rad]")
    axes[1].plot(delay_us, extracted_frequency_mhz, "w.-", lw=1.0)
    axes[1].set(ylabel="Probe frequency [MHz]", title="Raw phase")

    axes[2].plot(delay_us, extracted_frequency_mhz - reference, "o-")
    axes[2].axhspan(
        -float(MAX_ALLOWED_DRIFT_MHZ),
        float(MAX_ALLOWED_DRIFT_MHZ),
        color="tab:green",
        alpha=0.15,
        label="allowed reset-window drift",
    )
    axes[2].axvline(float(ACTIVE_RESET_WINDOW_US), color="tab:red", ls="--", label="reset window")
    axes[2].set(
        xlabel="Time at park [us]",
        ylabel="Frequency - first point [MHz]",
        title=f"Park result: {summary['status']}",
    )
    axes[2].grid(alpha=0.25)
    axes[2].legend(loc="best")
    fig.suptitle(f"q3 park stability at channel-3 gain {park_gain:+d} DAC")
    fig.savefig(output_dir / "park_stability.png", dpi=180)
    plt.close(fig)

    print(f"Result: {summary['status']}")
    if summary["max_abs_drift_mhz"] is not None:
        print(
            f"Max |drift| through {ACTIVE_RESET_WINDOW_US:g} us: "
            f"{summary['max_abs_drift_mhz']:.4f} MHz"
        )
        print(
            f"Linear slope: {summary['frequency_slope_khz_per_us']:+.3f} kHz/us"
        )
    if summary["status"] == "inconclusive_sweep_edge":
        print("The resonance reached a sweep boundary; widen or recenter the frequency sweep.")
    elif summary["status"] == "inconclusive_insufficient_trace":
        print("Too few reliable resonance points were extracted; inspect the raw map.")
    elif summary["status"] == "fail":
        print("Do not resume active-reset tuning: the nonzero park is moving during the loop.")
    else:
        print("The within-shot park passed this prerequisite; active-reset debugging can resume.")
    print(f"\nSend back the entire output folder: {output_dir}")


if __name__ == "__main__":
    main()
