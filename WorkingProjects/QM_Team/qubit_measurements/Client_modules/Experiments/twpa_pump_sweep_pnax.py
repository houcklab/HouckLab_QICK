"""
twpa_pump_sweep_pnax.py — TWPA pump (freq, power) sweep with PNA-X S21 readback.

Purpose
  With the DC bias already parked at its operating point (set via twpa_set_bias.py),
  sweep the TWPA pump RF over a 2-D grid of (frequency, power) and record |S21|
  vs the signal path at PNAX_CW_FREQ_HZ. The output is a 2-D map showing where
  the TWPA actually adds gain — i.e. the right pump frequency and pump power for
  the chosen signal band.

Pump source
  Two SignalCore SC5510A signal generators, controlled remotely over Pyro5 via
  sc5510a_client.py. The devices listed in PUMP_DEVICE_IDS are driven IDENTICALLY:
  at every sweep point each listed device carries the same frequency and power.
  (If you later want offset/independent control, add fixed offsets near where
  the devices are programmed inside the loop.)

  This is a two-machine setup. The SC5510A devices are physically connected to a
  *server PC* running the Pyro name server + instrument server (see the sc5510a-py
  repo). This script is the *client*: set SC5510A_SERVER_HOST below to the server
  PC's LAN IP and PUMP_DEVICE_IDS to the two device ids you want to drive.

  To find the device ids: from the client, with the server running, do
      import sc5510a_client as sc
      print(sc.list_instruments())
  which prints names like 'SC5510A#10002D35' — the trailing id is the device id.

Safety
  * DC bias should already be at the operating point before running this. The
    script does NOT touch the YOKO. Verify in twpa_set_bias.py / on the panel.
  * PUMP_POWER_MAX_dBm enforces a hard ceiling on the swept power axis.
  * On exit (success / exception / Ctrl-C) the pump devices are RF-disabled.
  * PNA-X output stays low — the TWPA may be under-pumped at the start of the
    sweep, so the signal must not saturate the line.
"""

import os
import sys
import time
import datetime as _dt

import numpy as np
import matplotlib.pyplot as plt
import pyvisa

# sc5510a_client lives in the shared PythonDrivers directory (one level up).
_DRIVERS_DIR = os.path.join(os.path.dirname(__file__), "..", "PythonDrivers")
if os.path.normpath(_DRIVERS_DIR) not in sys.path:
    sys.path.insert(0, os.path.normpath(_DRIVERS_DIR))
import sc5510a_client as sc


# ---------------------------------------------------------------------------
# User-set parameters
# ---------------------------------------------------------------------------
# --- Pump source (two SignalCore SC5510A, driven identically over Pyro5) ----
SC5510A_SERVER_HOST = "192.168.0.102"   # server PC LAN IP running the Pyro name server
PUMP_DEVICE_IDS     = ["10002D34", "10002D35"]  # TODO: the two SC5510A device ids (see sc.list_instruments())

# Frequency sweep (applied to BOTH devices identically)
F_START_GHz         = 11
F_STOP_GHz          = 14
N_FREQ_POINTS       = 61                 # 25 MHz spacing across 12.0–13.5 GHz (centered on ~12.7 GHz)

# Power sweep (applied to BOTH devices identically)
P_START_dBm         = -30.0
P_STOP_dBm          = 0.0
N_POWER_POINTS      = 31                 # 0.5 dB spacing across -25 → 0 dBm
PUMP_POWER_MAX_dBm  = 0.0                # hard ceiling — script refuses P > this

# Sweep timing
SETTLE_AFTER_FREQ_S  = 0.20              # PLL lock + thermal settle
SETTLE_AFTER_POWER_S = 0.05              # power-only update settle

# --- PNA-X CW measurement of the signal path -------------------------------
PNAX_ADDRESS         = "GPIB0::16::INSTR"
PNAX_CW_FREQ_HZ      = 7.000e9           # TODO: signal frequency where you want to see TWPA gain
PNAX_IF_BW_HZ        = 100.0
PNAX_POWER_dBm       = -60.0             # keep low — the TWPA may be under-pumped at start
PNAX_N_AVG           = 50
PNAX_TIMEOUT_MS      = 30000

# --- Output ----------------------------------------------------------------
SAVE_DIR             = r"V:/t1Team/Data/2026-05-29_BFC_cooldown/TWPA_calibration"
RUN_TAG              = "pump_sweep"


# ---------------------------------------------------------------------------
# PNA-X helpers (Keysight PNA-X SCPI) — mirror twpa_flux_sweep_pnax.py
# ---------------------------------------------------------------------------
def configure_pnax(pnax, cw_hz, if_bw_hz, power_dbm, n_avg, timeout_ms):
    pnax.timeout = timeout_ms
    pnax.write("*CLS")
    pnax.write("SYST:FPR")
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
# SC5510A pump helpers
# ---------------------------------------------------------------------------
def set_pump_devices(devices, freq_hz, power_dbm, rf_enable):
    """Program every pump device identically (freq, power, RF on/off)."""
    for dev in devices:
        dev.frequency = float(freq_hz)
        dev.power = float(power_dbm)
        dev.output = bool(rf_enable)


def disable_pump_devices(devices):
    for dev in devices:
        try:
            dev.output = False
        except Exception as e:
            print(f"[twpa_pump_sweep] WARNING: failed to disable a device: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    # --- Validate -----------------------------------------------------------
    if max(P_START_dBm, P_STOP_dBm) > PUMP_POWER_MAX_dBm:
        raise ValueError(
            f"Power sweep reaches {max(P_START_dBm, P_STOP_dBm):+.2f} dBm, above "
            f"PUMP_POWER_MAX_dBm = {PUMP_POWER_MAX_dBm:+.2f} dBm."
        )
    if F_START_GHz <= 0 or F_STOP_GHz <= 0:
        raise ValueError("Pump frequencies must be > 0.")
    if any("TODO" in str(d) for d in PUMP_DEVICE_IDS):
        raise ValueError(
            "PUMP_DEVICE_IDS still contains placeholders — fill in the two SC5510A "
            "device ids (run sc5510a_client.list_instruments() to discover them)."
        )

    freqs_GHz   = np.linspace(F_START_GHz, F_STOP_GHz, N_FREQ_POINTS)
    powers_dBm  = np.linspace(P_START_dBm, P_STOP_dBm, N_POWER_POINTS)
    freqs_Hz    = freqs_GHz * 1e9

    n_total     = N_FREQ_POINTS * N_POWER_POINTS
    s21_complex = np.full((N_FREQ_POINTS, N_POWER_POINTS),
                          np.nan + 1j * np.nan, dtype=complex)
    completed   = np.zeros((N_FREQ_POINTS, N_POWER_POINTS), dtype=bool)

    # --- Pre-flight ---------------------------------------------------------
    print("=" * 72)
    print("TWPA PUMP (FREQ, POWER) SWEEP + PNA-X S21")
    print(f"  SC5510A server  : {SC5510A_SERVER_HOST}    devices = {PUMP_DEVICE_IDS}")
    print(f"  PNA-X           : {PNAX_ADDRESS}")
    print(f"  freq grid       : {N_FREQ_POINTS} pts  {F_START_GHz:.4f} → {F_STOP_GHz:.4f} GHz "
          f"(Δ = {(F_STOP_GHz-F_START_GHz)/(N_FREQ_POINTS-1)*1e3:.2f} MHz)")
    print(f"  power grid      : {N_POWER_POINTS} pts  {P_START_dBm:+.2f} → {P_STOP_dBm:+.2f} dBm "
          f"(Δ = {(P_STOP_dBm-P_START_dBm)/(N_POWER_POINTS-1):.2f} dB)")
    print(f"  power ceiling   : {PUMP_POWER_MAX_dBm:+.2f} dBm")
    print(f"  scheme          : {PUMP_DEVICE_IDS} driven identically")
    print(f"  PNA-X CW        : {PNAX_CW_FREQ_HZ/1e9:.6f} GHz   IF BW = {PNAX_IF_BW_HZ:g} Hz   "
          f"P = {PNAX_POWER_dBm:+.1f} dBm   N_avg = {PNAX_N_AVG}")
    print(f"  total points    : {n_total}  (est. ≥ "
          f"{n_total*(SETTLE_AFTER_POWER_S+0.2):.1f} s wall-clock minimum)")
    print(f"  save dir        : {SAVE_DIR}")
    print()
    print("CONFIRM:")
    print("  [ ] DC bias is already at its operating point (twpa_set_bias.py).")
    print("  [ ] The two SC5510A are wired to the pump line(s), nothing else is driving them.")
    print("  [ ] PNA-X RF output safe at {:+.1f} dBm into the line at this bias.".format(PNAX_POWER_dBm))
    print("=" * 72)
    ans = input("Type 'yes' to proceed: ").strip().lower()
    if ans not in ("y", "yes"):
        print("[twpa_pump_sweep] Aborted by user.")
        sys.exit(0)

    os.makedirs(SAVE_DIR, exist_ok=True)
    stamp    = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    base     = os.path.join(SAVE_DIR, f"{stamp}_{RUN_TAG}")
    npz_path = base + ".npz"
    png_path = base + ".png"

    rm    = pyvisa.ResourceManager()
    pnax  = rm.open_resource(PNAX_ADDRESS)

    # Connect to the two SC5510A pump devices over Pyro5.
    pump_devices = [sc.connect(dev_id, host=SC5510A_SERVER_HOST) for dev_id in PUMP_DEVICE_IDS]

    t0 = time.time()
    try:
        # --- Pump source setup ---------------------------------------------
        # The server-side driver locks each SC5510A to its external reference at
        # init; warn (don't abort) if a device reports its ext ref undetected.
        for dev_id, dev in zip(PUMP_DEVICE_IDS, pump_devices):
            if not dev.clocked:
                print(f"[twpa_pump_sweep] WARNING: SC5510A {dev_id} reports external "
                      f"reference NOT detected — check the 10 MHz ref cabling.")

        # Start each device disabled at the sweep's lowest power / first freq
        set_pump_devices(pump_devices, freqs_Hz[0], powers_dBm[0], rf_enable=False)

        # --- PNA-X setup ---------------------------------------------------
        configure_pnax(pnax, PNAX_CW_FREQ_HZ, PNAX_IF_BW_HZ,
                       PNAX_POWER_dBm, PNAX_N_AVG, PNAX_TIMEOUT_MS)

        # --- 2-D sweep: outer = freq (slow PLL retune), inner = power -----
        for i, f_Hz in enumerate(freqs_Hz):
            # Re-tune frequency at the inner-loop start power, then enable RF.
            set_pump_devices(pump_devices, f_Hz, powers_dBm[0], rf_enable=True)
            time.sleep(SETTLE_AFTER_FREQ_S)

            for j, p_dBm in enumerate(powers_dBm):
                # Update power on all pump devices; frequency unchanged.
                for dev in pump_devices:
                    dev.power = float(p_dBm)
                time.sleep(SETTLE_AFTER_POWER_S)

                s21 = measure_s21_complex(pnax)
                s21_complex[i, j] = s21
                completed[i, j]   = True

                elapsed = time.time() - t0
                n_done = int(completed.sum())
                print(f"  [{n_done:>4d}/{n_total}] f={f_Hz/1e9:7.4f} GHz  "
                      f"P={p_dBm:+6.2f} dBm  "
                      f"|S21|={20*np.log10(np.abs(s21)):+7.2f} dB  "
                      f"∠S21={np.degrees(np.angle(s21)):+7.2f}°  "
                      f"t={elapsed:6.1f}s")

                # Incremental save so a crash mid-sweep keeps the partial map.
                np.savez(npz_path,
                         freqs_GHz=freqs_GHz,
                         powers_dBm=powers_dBm,
                         s21_complex=s21_complex,
                         completed=completed,
                         pnax_cw_hz=PNAX_CW_FREQ_HZ,
                         pnax_if_bw_hz=PNAX_IF_BW_HZ,
                         pnax_power_dbm=PNAX_POWER_dBm,
                         pump_power_max_dbm=PUMP_POWER_MAX_dBm,
                         pump_device_ids=np.array(PUMP_DEVICE_IDS),
                         scheme="identical_devices")

    except KeyboardInterrupt:
        print("\n[twpa_pump_sweep] Ctrl-C — disabling pump RF before exit.")
    finally:
        try:
            disable_pump_devices(pump_devices)
        except Exception as e:
            print(f"[twpa_pump_sweep] WARNING: failed to disable pumps cleanly: {e}")
        try:
            pnax.write("SOUR:POW1:MODE OFF")
        except Exception:
            pass
        pnax.close()

    # ---------------- Plot ----------------
    s21_dB        = 20.0 * np.log10(np.abs(s21_complex))
    s21_phase_deg = np.degrees(np.angle(s21_complex))

    # Δ|S21| relative to the lowest-power row at the same frequency.
    # Strips out the static chain loss so the actual pump-induced gain
    # variation shows up clearly on its own colormap.
    ref_col   = s21_dB[:, 0]
    delta_dB  = s21_dB - ref_col[:, None]

    # pcolormesh with shading='nearest' centers each cell on its (f, P)
    # coordinate — no off-by-half-cell misalignment vs sweep points.
    PP, FF = np.meshgrid(powers_dBm, freqs_GHz)

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16, 6))

    pm1 = ax1.pcolormesh(PP, FF, s21_dB, shading='nearest', cmap='viridis')
    ax1.set_xlabel("Pump power  (dBm, pump devices)")
    ax1.set_ylabel("Pump frequency  (GHz, pump devices)")
    ax1.set_title(f"|S21|  (dB)  @ {PNAX_CW_FREQ_HZ/1e9:.4f} GHz signal")
    fig.colorbar(pm1, ax=ax1, label="|S21|  (dB)")

    # Symmetric colormap centered on 0 dB so + (gain) and − (loss/saturation)
    # are distinguishable at a glance.
    vmax = float(np.nanmax(np.abs(delta_dB))) if np.isfinite(delta_dB).any() else 1.0
    pm2 = ax2.pcolormesh(PP, FF, delta_dB, shading='nearest',
                         cmap='RdBu_r', vmin=-vmax, vmax=+vmax)
    ax2.set_xlabel("Pump power  (dBm, pump devices)")
    ax2.set_ylabel("Pump frequency  (GHz, pump devices)")
    ax2.set_title(f"Δ|S21|  vs P={powers_dBm[0]:+.1f} dBm row  (dB)")
    fig.colorbar(pm2, ax=ax2, label="Δ|S21|  (dB)")

    pm3 = ax3.pcolormesh(PP, FF, s21_phase_deg, shading='nearest', cmap='twilight')
    ax3.set_xlabel("Pump power  (dBm, pump devices)")
    ax3.set_ylabel("Pump frequency  (GHz, pump devices)")
    ax3.set_title("∠S21  (deg)")
    fig.colorbar(pm3, ax=ax3, label="∠S21  (deg)")

    fig.tight_layout()
    fig.savefig(png_path, dpi=140)
    print(f"[twpa_pump_sweep] Saved: {npz_path}")
    print(f"[twpa_pump_sweep] Saved: {png_path}")

    # ---------------- Summary ----------------
    finite = np.isfinite(s21_dB) & completed
    if finite.sum() >= 3:
        # Compare to the lowest-power row at the same freq → crude gain proxy.
        # (For a true gain measurement, run an unpumped reference sweep first.)
        ref_col      = np.where(np.isfinite(s21_dB[:, 0]), s21_dB[:, 0], np.nan)
        delta_dB     = s21_dB - ref_col[:, None]
        delta_dB[~finite] = np.nan
        k_flat       = np.nanargmax(delta_dB)
        i_max, j_max = np.unravel_index(k_flat, delta_dB.shape)
        print("[twpa_pump_sweep] Best Δ|S21| vs lowest-power row at same freq:")
        print(f"  f = {freqs_GHz[i_max]:.4f} GHz   P = {powers_dBm[j_max]:+.2f} dBm   "
              f"Δ|S21| = {delta_dB[i_max, j_max]:+.2f} dB   "
              f"(|S21| = {s21_dB[i_max, j_max]:+.2f} dB)")


if __name__ == "__main__":
    main()
