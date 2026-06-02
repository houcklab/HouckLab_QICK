"""
twpa_flux_sweep_pnax.py — TWPA flux-period sweep with PNA-X S21 readback.

Purpose
  Verify the TWPA / DC bias path is alive by sweeping the bias current across
  the first flux period (0 → ~25 uA) at ≤ 300 nA/s and reading |S21| from the
  PNA-X at each step. Expected qualitative signature (datasheet):
    * Transmission enhancement near ~11 uA (operating point, impedance matched)
    * Strong suppression near ~25 uA (end of first flux period)
  Flat S21 vs current ⇒ the DC line is open / not delivering bias to the TWPA.

Safety
  * Pump generator (Holzworth HS9004A) MUST be OFF.
  * Ramp rate is enforced ≤ 300 nA/s by slow_ramp_to_current from twpa_set_bias.
  * On exit (success OR exception OR Ctrl-C) the bias is ramped back to 0.
  * This script overrides the 12 uA safety cap because the calibration sweep
    intentionally reaches the suppression at 25 uA. Do NOT use this for daily
    operation — use twpa_set_bias.py to set the operating point afterwards.

Wiring assumption
  YOKO in VOLTAGE mode → R_SERIES_OHMS (from twpa_set_bias) → TWPA bias port.
  PNA-X reads CW at PNAX_CW_FREQ_HZ, IF bandwidth PNAX_IF_BW_HZ.

Tested SCPI: Keysight PNA-X N52xx series. Other VNAs may need command tweaks
(see configure_pnax / measure_s21).
"""

import os
import sys
import time
import datetime as _dt

import numpy as np
import matplotlib.pyplot as plt
import pyvisa

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.twpa_set_bias import (
    TWPA_YOKO_ADDRESS,
    R_SERIES_OHMS,
    MAX_RATE_nA_per_s,
    pick_voltage_range,
    amp_to_volt,
    volt_to_amp,
    slow_ramp_to_current,
)


# ---------------------------------------------------------------------------
# User-set parameters
# ---------------------------------------------------------------------------
PNAX_ADDRESS         = "GPIB0::16::INSTR"   # TODO: PNA-X VISA address

# Bias sweep
I_START_uA           = -10.0
I_STOP_uA            = 10.0      # full first flux period — calibration only
N_BIAS_POINTS        = 51        # 51 points → 0.5 uA spacing across 0–25 uA
SETTLE_AFTER_RAMP_S  = 0.5       # post-ramp dwell before each PNA-X read

# PNA-X CW measurement
PNAX_CW_FREQ_HZ      = 7e9   # TODO: readout band — set near the cavity / chip transmission
PNAX_IF_BW_HZ        = 100.0
PNAX_POWER_dBm       = 0.0     # keep low: TWPA is unbiased much of the sweep
PNAX_N_AVG           = 4
PNAX_TIMEOUT_MS      = 30000

# Output
SAVE_DIR             = r"V:/t1Team/Data/2026-05-29_BFC_cooldown/TWPA_calibration"
RUN_TAG              = "first_period_sweep"


# ---------------------------------------------------------------------------
# PNA-X helpers (Keysight PNA-X SCPI)
# ---------------------------------------------------------------------------
def configure_pnax(pnax, cw_hz, if_bw_hz, power_dbm, n_avg, timeout_ms):
    pnax.timeout = timeout_ms
    pnax.write("*CLS")
    pnax.write("SYST:FPR")                                  # full preset
    pnax.write("CALC:PAR:DEL:ALL")
    pnax.write("CALC:PAR:DEF:EXT 'CH1_S21', 'S21'")
    pnax.write("CALC:PAR:SEL 'CH1_S21'")
    pnax.write("DISP:WIND1:STAT ON")
    pnax.write("DISP:WIND1:TRAC1:FEED 'CH1_S21'")
    pnax.write("CALC:FORM MLOG")
    pnax.write("SENS:SWE:TYPE CW")
    pnax.write(f"SENS:FREQ:CW {cw_hz:.6e}")
    pnax.write(f"SENS:BWID {if_bw_hz:.6e}")
    pnax.write(f"SOUR:POW1 {power_dbm:.2f}")
    pnax.write("SOUR:POW1:MODE ON")
    pnax.write(f"SENS:SWE:POIN {int(n_avg)}")
    pnax.write("SENS:AVER OFF")
    pnax.write("TRIG:SOUR IMM")
    pnax.write("SENS:SWE:MODE HOLD")
    pnax.query("*OPC?")


def measure_s21_complex(pnax):
    """Trigger one CW sweep and return mean complex S21 across the points."""
    pnax.write("SENS:SWE:MODE SING")
    pnax.query("*OPC?")
    raw = pnax.query("CALC:DATA? SDATA")
    vals = np.fromstring(raw, sep=',')
    if vals.size < 2 or vals.size % 2 != 0:
        raise RuntimeError(f"Unexpected SDATA payload from PNA-X: {vals.size} values")
    s21 = vals[0::2] + 1j * vals[1::2]
    return np.mean(s21)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    # Validate range
    if I_STOP_uA > 25.0 or I_START_uA < -25.0:
        raise ValueError("Bias sweep must stay within ±25 uA (first flux period).")
    if MAX_RATE_nA_per_s > 300.0:
        raise ValueError("MAX_RATE_nA_per_s > 300 nA/s violates the TWPA datasheet ceiling.")

    bias_uA = np.linspace(I_START_uA, I_STOP_uA, N_BIAS_POINTS)
    max_abs_V = abs(amp_to_volt(max(abs(bias_uA[0]), abs(bias_uA[-1])) * 1e-6))
    range_V = pick_voltage_range(max_abs_V)

    # Pre-flight summary
    print("=" * 72)
    print("TWPA FLUX SWEEP + PNA-X S21")
    print(f"  YOKO            : {TWPA_YOKO_ADDRESS}    R_series = {R_SERIES_OHMS:.4g} Ω")
    print(f"  PNA-X           : {PNAX_ADDRESS}")
    print(f"  bias points     : {N_BIAS_POINTS} from {I_START_uA:+.3f} → {I_STOP_uA:+.3f} uA "
          f"(Δ = {(I_STOP_uA-I_START_uA)/(N_BIAS_POINTS-1):.3f} uA)")
    print(f"  YOKO V range    : {range_V:g} V (auto)")
    print(f"  max ramp rate   : {MAX_RATE_nA_per_s:.0f} nA/s")
    print(f"  PNA-X CW        : {PNAX_CW_FREQ_HZ/1e9:.6f} GHz   IF BW = {PNAX_IF_BW_HZ:g} Hz   "
          f"P = {PNAX_POWER_dBm:.1f} dBm   N_avg = {PNAX_N_AVG}")
    print(f"  save dir        : {SAVE_DIR}")
    print()
    print("CONFIRM:")
    print("  [ ] TWPA pump generator (Holzworth HS9004A) RF output is OFF.")
    print("  [ ] PNA-X RF output safe at {:+.1f} dBm into the line.".format(PNAX_POWER_dBm))
    print("  [ ] R_SERIES_OHMS and addresses match the physical wiring.")
    print("=" * 72)
    ans = input("Type 'yes' to proceed: ").strip().lower()
    if ans not in ("y", "yes"):
        print("[twpa_flux_sweep] Aborted by user.")
        sys.exit(0)

    os.makedirs(SAVE_DIR, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.join(SAVE_DIR, f"{stamp}_{RUN_TAG}")
    npz_path = base + ".npz"
    png_path = base + ".png"

    rm = pyvisa.ResourceManager()
    yoko = rm.open_resource(TWPA_YOKO_ADDRESS)
    pnax = rm.open_resource(PNAX_ADDRESS)

    s21_complex = np.full(N_BIAS_POINTS, np.nan + 1j * np.nan, dtype=complex)
    t0 = time.time()

    try:
        # YOKO setup
        yoko.write(":SOUR:FUNC VOLT")
        yoko.write(f":SOUR:RANG {range_V:g}")
        yoko.write(":OUTP ON")

        # PNA-X setup
        configure_pnax(pnax, PNAX_CW_FREQ_HZ, PNAX_IF_BW_HZ,
                       PNAX_POWER_dBm, PNAX_N_AVG, PNAX_TIMEOUT_MS)

        max_rate_A = MAX_RATE_nA_per_s * 1e-9
        for k, I_uA in enumerate(bias_uA):
            slow_ramp_to_current(yoko, I_uA * 1e-6, max_rate_A)
            time.sleep(SETTLE_AFTER_RAMP_S)
            s21 = measure_s21_complex(pnax)
            s21_complex[k] = s21
            elapsed = time.time() - t0
            print(f"  [{k+1:>3d}/{N_BIAS_POINTS}] I={I_uA:+7.3f} uA  "
                  f"|S21|={20*np.log10(np.abs(s21)):+7.2f} dB  "
                  f"∠S21={np.degrees(np.angle(s21)):+7.2f}°  "
                  f"t={elapsed:6.1f}s")

            # Incremental save so a crash near the end keeps the partial dataset.
            np.savez(npz_path,
                     bias_uA=bias_uA,
                     s21_complex=s21_complex,
                     pnax_cw_hz=PNAX_CW_FREQ_HZ,
                     pnax_if_bw_hz=PNAX_IF_BW_HZ,
                     pnax_power_dbm=PNAX_POWER_dBm,
                     r_series_ohms=R_SERIES_OHMS,
                     completed_index=k)

    except KeyboardInterrupt:
        print("\n[twpa_flux_sweep] Ctrl-C — ramping bias back to 0 uA before exit.")
    finally:
        try:
            slow_ramp_to_current(yoko, 0.0, MAX_RATE_nA_per_s * 1e-9)
        except Exception as e:
            print(f"[twpa_flux_sweep] WARNING: failed to ramp bias to 0: {e}")
        try:
            pnax.write("SOUR:POW1:MODE OFF")
        except Exception:
            pass
        yoko.close()
        pnax.close()

    # ---------------- Plot ----------------
    s21_dB = 20.0 * np.log10(np.abs(s21_complex))
    s21_phase_deg = np.degrees(np.unwrap(np.angle(s21_complex)))

    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(7, 6))
    ax1.plot(bias_uA, s21_dB, '-o', ms=3)
    ax1.set_ylabel("|S21|  (dB)")
    ax1.grid(True, alpha=0.3)
    ax1.set_title(f"TWPA flux sweep — {PNAX_CW_FREQ_HZ/1e9:.4f} GHz CW")
    ax1.axvline(11.0, ls='--', alpha=0.4, label="nominal op. pt. (11 uA)")
    ax1.axvline(25.0, ls=':', alpha=0.4, label="period end (25 uA)")
    ax1.legend(loc="best", fontsize=8)

    ax2.plot(bias_uA, s21_phase_deg, '-o', ms=3, color='C1')
    ax2.set_ylabel("∠S21  (deg, unwrapped)")
    ax2.set_xlabel("Bias current  (uA)")
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(png_path, dpi=140)
    print(f"[twpa_flux_sweep] Saved: {npz_path}")
    print(f"[twpa_flux_sweep] Saved: {png_path}")

    # ---------------- Alive-check summary ----------------
    finite = np.isfinite(s21_dB)
    if finite.sum() >= 3:
        spread = float(np.nanmax(s21_dB[finite]) - np.nanmin(s21_dB[finite]))
        print(f"[twpa_flux_sweep] |S21| spread across sweep: {spread:.2f} dB")
        if spread < 0.5:
            print("  ⚠ Spread < 0.5 dB → DC bias path may be open or TWPA not flux-responsive.")
        else:
            print("  ✓ Bias-dependent transmission observed — DC path appears alive.")


if __name__ == "__main__":
    main()
