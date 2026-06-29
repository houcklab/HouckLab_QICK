"""Standalone offline test of the 2D pi/2 phase calibration axis convention.

Goal: settle whether `SweepExperimentND` stores Z as (R, n_phase, n_samples) or
the transpose, and whether the GUI's imshow + fit_beamsplitter_offset path
displays/fits along the correct axis.

What it does
------------
1. Reproduces the exact SweepExperimentND iteration/storage convention with
   sweep_arrays = (y_points, x_points). y = phase, x = samples.
2. Stores a synthetic P_e(phi, t) = (1 - cos(phi) * sin(g*t)) / 2 -- the
   physical prediction from the William-Oliver writeup -- so we know
   *which axis should oscillate which way*.
3. Prints the resulting Z shape and a few cells with their expected values.
4. Runs the data through fit_beamsplitter_offset (as the real analyze does)
   and prints popt: the `w` parameter MUST be ~2*pi/360 rad/deg if the fit is
   sinusoid-ing the phase axis correctly.
5. Renders the 2D map with imshow + extent the same way the GUI does, saves
   to test_pi2phase_axes.png.

Run: python -m WorkingProjects.triangle_lattice_quench.Run_Experiments.verify_pi2phase_axes
(or just python verify_pi2phase_axes.py from this folder if the helper imports
fall back to a relative path -- see the import block below).
"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Make the project importable when running this file directly.
_HERE = Path(__file__).resolve().parent
_PROJ_ROOT = _HERE.parents[2]  # WorkingProjects/
if str(_PROJ_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJ_ROOT))

from WorkingProjects.triangle_lattice_quench.Helpers.Beamsplitter_Fit import (
    fit_beamsplitter_offset,
)


def main() -> int:
    # ---- 1. Set up the swept axes (same convention as MottQuenchPi2Phase2D) ----
    n_phase = 21    # phase axis (cosine should appear here)
    n_samples = 51  # samples axis (monotonic time)
    phases = np.linspace(0.0, 360.0, n_phase)
    samples = np.linspace(0.0, 8000.0, n_samples)

    # SweepExperimentND prepends keys/arrays: y_key first (after x_key), so
    # sweep_arrays = (y_points, x_points) = (phases, samples).
    sweep_arrays = (phases, samples)
    sweep_shape = tuple(len(a) for a in sweep_arrays)
    print(f"[1] sweep_arrays order = (y=phases [n={n_phase}], x=samples [n={n_samples}])")
    print(f"    sweep_shape       = {sweep_shape}  (expected ({n_phase}, {n_samples}))")

    # ---- 2. Synthetic ground truth P_e(phi, t) ----
    # P_e = (1 - cos(phi) * sin(g*t)) / 2 with g chosen so we see a few periods.
    g_per_sample = 2 * np.pi / 4000.0  # one swap period every 4000 samples

    def Pe(phi_deg: float, t_samples: float) -> float:
        return 0.5 * (1.0 - np.cos(np.deg2rad(phi_deg)) * np.sin(g_per_sample * t_samples))

    # ---- 3. Allocate Z exactly like SweepExperimentND.acquire() does ----
    R = 1  # one readout for the test
    data_shape = sweep_shape  # no inner QICK loops
    Z = np.full((R,) + data_shape, np.nan)

    # ---- 4. Iterate exactly like SweepExperimentND does ----
    index_iterator = itertools.product(*(range(len(a)) for a in sweep_arrays))
    value_iterator = itertools.product(*sweep_arrays)
    for sweep_indices, sweep_values in zip(index_iterator, value_iterator):
        # sweep_values = (y_val, x_val) = (phase, sample)
        i_y, i_x = sweep_indices
        phase_val, sample_val = sweep_values
        Z[0][i_y, i_x] = Pe(phase_val, sample_val)

    print(f"\n[2] Z shape (R, ...) = {Z.shape}")
    print(f"    Z[0] shape       = {Z[0].shape}  (rows = ???, cols = ???)")

    # Spot-check a few cells: if rows are phase, then Z[0][i, :] varies in
    # samples for a fixed phase. Z[0][:, j] varies in phase for a fixed sample.
    i_at_phi0 = int(np.argmin(np.abs(phases - 0.0)))
    i_at_phi90 = int(np.argmin(np.abs(phases - 90.0)))
    j_at_t0 = int(np.argmin(np.abs(samples - 0.0)))
    j_at_t1k = int(np.argmin(np.abs(samples - 1000.0)))

    print(f"\n[3] Spot checks (Z[0, i, j] vs Pe(phases[i], samples[j])):")
    for (i, j), label in [
        ((i_at_phi0, j_at_t0),  "phi=0, t=0"),
        ((i_at_phi0, j_at_t1k), "phi=0, t=1000"),
        ((i_at_phi90, j_at_t0),  "phi=90, t=0"),
        ((i_at_phi90, j_at_t1k), "phi=90, t=1000"),
    ]:
        actual = Z[0][i, j]
        expected = Pe(phases[i], samples[j])
        ok = "OK" if abs(actual - expected) < 1e-12 else "MISMATCH"
        print(f"    {label:14s}: Z[0,{i},{j}] = {actual:+.4f}  expected {expected:+.4f}  [{ok}]")

    # If rows = phase, the variation along row 0 (fixed phi=0) should be in samples
    # (a pure sin(g*t)/2 amplitude). The variation along column 0 (fixed t=0) should
    # be zero (sin(0)=0). Verify:
    var_along_row = float(np.max(Z[0][i_at_phi0, :]) - np.min(Z[0][i_at_phi0, :]))
    var_along_col = float(np.max(Z[0][:, j_at_t0]) - np.min(Z[0][:, j_at_t0]))
    print(f"\n[4] Variation diagnostics (with rows=phase, cols=samples expected):")
    print(f"    Z[0, phi=0_row, all samples].ptp() = {var_along_row:.4f}  "
          f"(should be ~1.0 if rows are phase: full sin(gt) sweep)")
    print(f"    Z[0, all phases, t=0_col].ptp()    = {var_along_col:.4f}  "
          f"(should be ~0.0 if cols are samples: sin(0)=0 -> flat in phase)")

    if var_along_row > 0.9 and var_along_col < 1e-6:
        layout = "rows=phase, cols=samples  (matches Z.shape = (R, n_phase, n_samples))"
    elif var_along_row < 1e-6 and var_along_col > 0.9:
        layout = "rows=samples, cols=phase  (TRANSPOSED -- Z.shape = (R, n_samples, n_phase))"
    else:
        layout = "ambiguous"
    print(f"    => layout: {layout}")

    # ---- 5. Run fit_beamsplitter_offset and check 'w' ----
    # The fit's signature is (Z [R, O, T], offsets, wait_times) and treats axis 1
    # of Z as the sinusoid (offset) axis. We pass offsets=phases.
    print(f"\n[5] Calling fit_beamsplitter_offset(Z, phases, samples)...")
    try:
        params = fit_beamsplitter_offset(Z, phases, samples)
        popt = np.asarray(params["popt"])
        r_squared = np.asarray(params["r_squared"])
        print(f"    popt[0]      = {popt[0]}  (A, w, phi, offset, gamma)")
        print(f"    r_squared[0] = {r_squared[0]:.4f}")
        w = float(popt[0][1])
        # If fit axis is degrees (phase), w should be ~2*pi/360 = 0.01745.
        expected_w_deg = 2 * np.pi / 360.0
        expected_w_samples = g_per_sample  # 2*pi/4000 = 0.001571
        diff_deg = abs(w - expected_w_deg) / expected_w_deg
        diff_samples = abs(w - expected_w_samples) / expected_w_samples
        print(f"\n    Fit-axis identification:")
        print(f"      expected w if fit is on PHASE  axis: {expected_w_deg:.6f} rad/deg")
        print(f"      expected w if fit is on SAMPLE axis: {expected_w_samples:.6f} rad/sample")
        print(f"      actual w from fit:                   {w:.6f}")
        if diff_deg < 0.2:
            print(f"      => fit IS sinusoid-ing the PHASE axis (good)")
        elif diff_samples < 0.5:
            print(f"      => fit is sinusoid-ing the SAMPLES axis (Z is transposed for the fit)")
        else:
            print(f"      => fit `w` matches neither axis cleanly; multi-start may have landed badly")
    except Exception as exc:
        print(f"    fit failed: {exc}")

    # ---- 6. Render the 2D map exactly like the GUI does ----
    print(f"\n[6] Rendering imshow with extent=[samples_l, samples_r, phases_b, phases_t]...")
    fig, ax = plt.subplots(figsize=(7, 4))
    mat = Z[0]  # shape per the code: (n_phase, n_samples) -- but we just verified
    extent = [samples[0], samples[-1], phases[0], phases[-1]]
    im = ax.imshow(mat, aspect="auto", origin="lower",
                   extent=extent, interpolation="none")
    ax.set_xlabel("samples (4.65/16 ns)")
    ax.set_ylabel("measurement pi/2 phase (deg)")
    ax.set_title(f"Synthetic P_e = (1 - cos(phi)*sin(g*t))/2  "
                 f"[g_per_sample = {g_per_sample:.5f}]")
    fig.colorbar(im, ax=ax, label="P_e")
    fig.tight_layout()
    out = _HERE / "test_pi2phase_axes.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"    saved -> {out}")
    print(f"\n    Inspect the PNG. Correct rendering shows:")
    print(f"      * a 'chevron' with vertical nodal lines at phi=90 deg and 270 deg,")
    print(f"      * horizontal nodal lines at t with sin(g*t)=0 (t=0, 2000, 4000, 6000, 8000 samples),")
    print(f"      * cosine fringes RUNNING ACROSS the Y (phase) axis,")
    print(f"      * monotonic sin(g*t) modulation along X (samples).")
    print(f"    If the cosine fringes run along X instead, the GUI render path has")
    print(f"    an axis bug (the data here is constructed to match expectations).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
