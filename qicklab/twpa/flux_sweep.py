"""TWPA flux-period sweep (pump OFF): ramp the bias over +-25 uA at <= 300 nA/s, read PNA-X |S21|.

Reports the bias maximizing band-mean (or CW) |S21|; calibration only. Appends the end state (bias
readback after the ramp to 0) to the TWPA state log. See docs/experiments/twpa.md.
"""

import sys
import time

import matplotlib.pyplot as plt
import numpy as np
import pyvisa

from qicklab.hardware.pnax import band_mean_dB, measure_s21_band
from qicklab.hardware.yoko import enable_current_output_safely, pick_current_range, ramp_current
from qicklab.twpa.common import append_state, read_bias_state, timestamped_paths
from qicklab.twpa.set_bias import STEP_PERIOD_S, TWPA_YOKO_ADDRESS, MAX_RATE_nA_per_s

PNAX_ADDRESS = "GPIB0::16::INSTR"

I_START_uA = -25.0
I_STOP_uA = 25.0  # full first flux period — calibration only
N_BIAS_POINTS = 51
SETTLE_AFTER_RAMP_S = 0.5  # post-ramp dwell before each PNA-X read

# Figure of merit: "BAND" = mean |S21| over [PNAX_F_START_HZ, PNAX_F_STOP_HZ];
# "CW" = |S21| at PNAX_CW_FREQ_HZ (single tone, faster).
PNAX_MEAS_MODE = "BAND"
PNAX_CW_FREQ_HZ = 7.0e9  # CW tone (used only when PNAX_MEAS_MODE == "CW")
PNAX_F_START_HZ = 5e9
PNAX_F_STOP_HZ = 8e9
PNAX_N_FREQ_POINTS = 201  # points across the band (BAND mode only)
PNAX_IF_BW_HZ = 100.0
PNAX_POWER_dBm = -25.0  # keep low: TWPA is unbiased much of the sweep
PNAX_N_AVG = 4  # sweep-averaging count (1 = off)
PNAX_TIMEOUT_MS = 30000

SAVE_DIR = r"V:/t1Team/Data/2026-10-01_BFC_cooldown/TWPA_calibration"
RUN_TAG = "first_period_sweep"


def configure_pnax(
    pnax,
    meas_mode,
    f_start_hz,
    f_stop_hz,
    n_points,
    cw_freq_hz,
    if_bw_hz,
    power_dbm,
    n_avg,
    timeout_ms,
):
    pnax.timeout = timeout_ms
    pnax.write("*CLS")
    pnax.write("SYST:FPR")  # full preset
    pnax.write("CALC:PAR:DEL:ALL")
    pnax.write("CALC:PAR:DEF:EXT 'CH1_S21', 'S21'")
    pnax.write("CALC:PAR:SEL 'CH1_S21'")
    pnax.write("DISP:WIND1:STAT ON")
    pnax.write("DISP:WIND1:TRAC1:FEED 'CH1_S21'")
    pnax.write("CALC:FORM MLOG")
    if meas_mode == "CW":
        # Single-tone: zero-span CW sweep at one frequency, one point.
        pnax.write("SENS:SWE:TYPE CW")
        pnax.write(f"SENS:FREQ:CW {cw_freq_hz:.6e}")
        pnax.write("SENS:SWE:POIN 1")
    else:
        pnax.write("SENS:SWE:TYPE LIN")
        pnax.write(f"SENS:FREQ:STAR {f_start_hz:.6e}")
        pnax.write(f"SENS:FREQ:STOP {f_stop_hz:.6e}")
        pnax.write(f"SENS:SWE:POIN {int(n_points)}")
    pnax.write(f"SENS:BWID {if_bw_hz:.6e}")
    pnax.write(f"SOUR:POW1 {power_dbm:.2f}")
    pnax.write("SOUR:POW1:MODE ON")
    if n_avg and int(n_avg) > 1:
        pnax.write(f"SENS:AVER:COUN {int(n_avg)}")
        pnax.write("SENS:AVER ON")
        pnax.write("SENS:AVER:CLE")
    else:
        pnax.write("SENS:AVER OFF")
    pnax.write("TRIG:SOUR IMM")
    pnax.write("SENS:SWE:MODE HOLD")
    pnax.query("*OPC?")


def main():
    if I_STOP_uA > 25.0 or I_START_uA < -25.0:
        raise ValueError("Bias sweep must stay within ±25 uA (first flux period).")
    if MAX_RATE_nA_per_s > 300.0:
        raise ValueError("MAX_RATE_nA_per_s > 300 nA/s violates the TWPA datasheet ceiling.")
    if PNAX_MEAS_MODE not in ("BAND", "CW"):
        raise ValueError("PNAX_MEAS_MODE must be 'BAND' or 'CW'.")
    if PNAX_MEAS_MODE == "BAND" and PNAX_F_STOP_HZ <= PNAX_F_START_HZ:
        raise ValueError("PNAX_F_STOP_HZ must be greater than PNAX_F_START_HZ.")
    if PNAX_MEAS_MODE == "CW" and PNAX_CW_FREQ_HZ <= 0:
        raise ValueError("PNAX_CW_FREQ_HZ must be > 0.")

    bias_uA = np.linspace(I_START_uA, I_STOP_uA, N_BIAS_POINTS)
    cw_mode = PNAX_MEAS_MODE == "CW"
    if cw_mode:
        n_freq = 1
        pnax_freq_hz = np.array([PNAX_CW_FREQ_HZ])
    else:
        n_freq = PNAX_N_FREQ_POINTS
        pnax_freq_hz = np.linspace(PNAX_F_START_HZ, PNAX_F_STOP_HZ, PNAX_N_FREQ_POINTS)
    max_abs_A = max(abs(bias_uA[0]), abs(bias_uA[-1])) * 1e-6
    range_A = pick_current_range(max_abs_A)

    band_GHz = (PNAX_F_START_HZ / 1e9, PNAX_F_STOP_HZ / 1e9)
    if cw_mode:
        fom_desc = f"|S21| (dB) at {PNAX_CW_FREQ_HZ / 1e9:.4f} GHz CW tone"
    else:
        fom_desc = "mean |S21| (dB) across the band"

    print("=" * 72)
    print("TWPA FLUX SWEEP + PNA-X banded S21  (YOKO current-source mode)")
    print(f"  YOKO            : {TWPA_YOKO_ADDRESS}")
    print(f"  PNA-X           : {PNAX_ADDRESS}")
    print(
        f"  bias points     : {N_BIAS_POINTS} from {I_START_uA:+.3f} → {I_STOP_uA:+.3f} uA "
        f"(Δ = {(I_STOP_uA - I_START_uA) / (N_BIAS_POINTS - 1):.3f} uA)"
    )
    print(f"  YOKO I range    : {range_A * 1e3:g} mA (auto)")
    print(f"  max ramp rate   : {MAX_RATE_nA_per_s:.0f} nA/s")
    if cw_mode:
        print(
            f"  PNA-X mode      : CW @ {PNAX_CW_FREQ_HZ / 1e9:.6f} GHz   "
            f"IF BW = {PNAX_IF_BW_HZ:g} Hz   "
            f"P = {PNAX_POWER_dBm:.1f} dBm   N_avg = {PNAX_N_AVG}"
        )
    else:
        print(
            f"  PNA-X band      : {band_GHz[0]:.6f} → {band_GHz[1]:.6f} GHz   "
            f"{PNAX_N_FREQ_POINTS} pts   IF BW = {PNAX_IF_BW_HZ:g} Hz   "
            f"P = {PNAX_POWER_dBm:.1f} dBm   N_avg = {PNAX_N_AVG}"
        )
    print(f"  figure of merit : {fom_desc}")
    print(f"  save dir        : {SAVE_DIR}")
    print()
    print("CONFIRM:")
    print("  [ ] TWPA pump generator (Holzworth HS9004A) RF output is OFF.")
    print(f"  [ ] PNA-X RF output safe at {PNAX_POWER_dBm:+.1f} dBm into the line.")
    print("  [ ] YOKO and PNA-X addresses match the physical wiring; YOKO is")
    print("      wired to source current directly into the TWPA bias line.")
    print("=" * 72)
    ans = input("Type 'yes' to proceed: ").strip().lower()
    if ans not in ("y", "yes"):
        print("[twpa_flux_sweep] Aborted by user.")
        sys.exit(0)

    npz_path, png_path = timestamped_paths(SAVE_DIR, RUN_TAG)

    rm = pyvisa.ResourceManager()
    yoko = rm.open_resource(TWPA_YOKO_ADDRESS)
    pnax = rm.open_resource(PNAX_ADDRESS)

    s21_band = np.full((N_BIAS_POINTS, n_freq), np.nan + 1j * np.nan, dtype=complex)
    mean_band_dB = np.full(N_BIAS_POINTS, np.nan)
    t0 = time.time()
    bias_enabled = False  # finally ramps to 0 only once the YOKO is known to be in current mode
    outcome = "error"  # -> "completed" after the last point, "interrupted" on Ctrl-C
    k_done = 0

    try:
        range_A = enable_current_output_safely(yoko, range_A)
        bias_enabled = True

        configure_pnax(
            pnax,
            PNAX_MEAS_MODE,
            PNAX_F_START_HZ,
            PNAX_F_STOP_HZ,
            PNAX_N_FREQ_POINTS,
            PNAX_CW_FREQ_HZ,
            PNAX_IF_BW_HZ,
            PNAX_POWER_dBm,
            PNAX_N_AVG,
            PNAX_TIMEOUT_MS,
        )

        max_rate_A = MAX_RATE_nA_per_s * 1e-9
        for k, I_uA in enumerate(bias_uA):
            ramp_current(yoko, I_uA * 1e-6, max_rate_A, dt=STEP_PERIOD_S)
            time.sleep(SETTLE_AFTER_RAMP_S)
            trace = measure_s21_band(pnax, PNAX_N_AVG)
            s21_band[k] = trace
            mean_band_dB[k] = band_mean_dB(trace)
            elapsed = time.time() - t0
            print(
                f"  [{k + 1:>3d}/{N_BIAS_POINTS}] I={I_uA:+7.3f} uA  "
                f"mean|S21|={mean_band_dB[k]:+7.2f} dB  "
                f"t={elapsed:6.1f}s"
            )

            # Incremental save so a crash near the end keeps the partial dataset.
            np.savez(
                npz_path,
                bias_uA=bias_uA,
                pnax_freq_hz=pnax_freq_hz,
                s21_band=s21_band,
                mean_band_dB=mean_band_dB,
                meas_mode=PNAX_MEAS_MODE,
                pnax_cw_freq_hz=PNAX_CW_FREQ_HZ,
                pnax_f_start_hz=PNAX_F_START_HZ,
                pnax_f_stop_hz=PNAX_F_STOP_HZ,
                pnax_if_bw_hz=PNAX_IF_BW_HZ,
                pnax_power_dbm=PNAX_POWER_dBm,
                yoko_curr_range_a=range_A,
                completed_index=k,
            )
            k_done = k + 1
        outcome = "completed"

    except KeyboardInterrupt:
        outcome = "interrupted"
        print("\n[twpa_flux_sweep] Ctrl-C — ramping bias back to 0 uA before exit.")
    finally:
        try:
            if bias_enabled:
                ramp_current(yoko, 0.0, MAX_RATE_nA_per_s * 1e-9, dt=STEP_PERIOD_S)
        except Exception as e:
            print(f"[twpa_flux_sweep] WARNING: failed to ramp bias to 0: {e}")
        try:
            pnax.write("SOUR:POW1:MODE OFF")
        except Exception:
            pass
        try:
            bias = read_bias_state(yoko)  # read-only, after the ramp back to 0
        except Exception as e:
            print(f"[twpa_flux_sweep] WARNING: TWPA bias readback failed: {e}")
            bias = None
        append_state(
            "twpa_flux_sweep",
            action="flux_sweep",
            outcome=outcome,
            data_file=npz_path,
            completed_points=k_done,
            bias=bias,
            pump=None,  # not touched by this script (pump must be OFF)
            pnax={
                "address": PNAX_ADDRESS,
                "meas_mode": PNAX_MEAS_MODE,
                "cw_freq_hz": PNAX_CW_FREQ_HZ,
                "f_start_hz": PNAX_F_START_HZ,
                "f_stop_hz": PNAX_F_STOP_HZ,
                "n_points": PNAX_N_FREQ_POINTS,
                "if_bw_hz": PNAX_IF_BW_HZ,
                "power_dbm": PNAX_POWER_dBm,
                "n_avg": PNAX_N_AVG,
            },
        )
        yoko.close()
        pnax.close()

    s21_band_dB = 20.0 * np.log10(np.abs(s21_band))
    freq_GHz = pnax_freq_hz / 1e9

    if cw_mode:
        fig, ax1 = plt.subplots(1, 1, figsize=(7, 4))
        fom_ylabel = f"|S21| @ {PNAX_CW_FREQ_HZ / 1e9:.4f} GHz  (dB)"
        fom_title = "TWPA flux sweep — CW transmission vs bias"
    else:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 7))
        fom_ylabel = f"mean |S21| over\n{band_GHz[0]:.3f}–{band_GHz[1]:.3f} GHz  (dB)"
        fom_title = "TWPA flux sweep — mean band transmission vs bias"

    ax1.plot(bias_uA, mean_band_dB, "-o", ms=3)
    ax1.set_ylabel(fom_ylabel)
    ax1.set_xlabel("Bias current  (uA)")
    ax1.grid(True, alpha=0.3)
    ax1.set_title(fom_title)
    ax1.axvline(11.0, ls="--", alpha=0.4, label="nominal op. pt. (11 uA)")
    ax1.axvline(25.0, ls=":", alpha=0.4, label="period end (25 uA)")
    if np.isfinite(mean_band_dB).any():
        k_best = int(np.nanargmax(mean_band_dB))
        ax1.axvline(
            bias_uA[k_best], color="C3", alpha=0.7, label=f"best bias ({bias_uA[k_best]:.2f} uA)"
        )
    ax1.legend(loc="best", fontsize=8)

    # Bottom: full band response vs bias (BAND mode only — CW has a single tone).
    if not cw_mode:
        BB, FF = np.meshgrid(bias_uA, freq_GHz)
        pm = ax2.pcolormesh(BB, FF, s21_band_dB.T, shading="nearest", cmap="viridis")
        ax2.set_xlabel("Bias current  (uA)")
        ax2.set_ylabel("Frequency  (GHz)")
        ax2.set_title("|S21|  (dB)  vs (bias, frequency)")
        fig.colorbar(pm, ax=ax2, label="|S21|  (dB)")

    fig.tight_layout()
    fig.savefig(png_path, dpi=140)
    print(f"[twpa_flux_sweep] Saved: {npz_path}")
    print(f"[twpa_flux_sweep] Saved: {png_path}")

    finite = np.isfinite(mean_band_dB)
    if finite.sum() >= 3:
        spread = float(np.nanmax(mean_band_dB[finite]) - np.nanmin(mean_band_dB[finite]))
        k_best = int(np.nanargmax(mean_band_dB))
        where = (
            f"at {PNAX_CW_FREQ_HZ / 1e9:.4f} GHz CW"
            if cw_mode
            else f"over {band_GHz[0]:.3f}–{band_GHz[1]:.3f} GHz"
        )
        print(f"[twpa_flux_sweep] |S21| spread across sweep: {spread:.2f} dB")
        print(f"[twpa_flux_sweep] Best bias for transmission:")
        print(f"  I = {bias_uA[k_best]:+.3f} uA   |S21| = {mean_band_dB[k_best]:+.2f} dB {where}")
        if spread < 0.5:
            print("  ⚠ Spread < 0.5 dB → DC bias path may be open or TWPA not flux-responsive.")
        else:
            print("  ✓ Bias-dependent transmission observed — DC path appears alive.")


if __name__ == "__main__":
    main()
