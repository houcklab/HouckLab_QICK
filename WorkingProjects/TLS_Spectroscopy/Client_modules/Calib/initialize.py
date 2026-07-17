"""
Device configuration for FTTv02_SiOxJJ **qubit 4** (TLS spectroscopy, all-fast-flux).

Values confirmed 2026-07 against the measurement PC's working setup:
  - socProxy nameserver 192.168.1.107 (board: ZCU216, 7x axis_signal_gen_v4,
    2 readouts; tProc program memory 8192 words)
  - SingleShot_FF runner, Device 3: FTTv02_SiOxJJ (3.0 nm), Qubit_Parameters["4"]
  - flux line physically wired to the DAC 3_230 P/N differential pigtails (JHC4),
    which print(soccfg) maps to GENERATOR CHANNEL 3  ->  ff_ch = 3

QUA -> QICK frequency note
--------------------------
QICK synthesizes tones digitally: every ``*_freq`` here is an ABSOLUTE MHz and the
Nyquist zone (``nqz``/``qubit_nqz``) places it (same convention as the working
initialize4Q.py: readout 7248.95 MHz with nqz=2 on this board).

Flux model (all-fast-flux, QUA-style — no Yokogawa)
---------------------------------------------------
ALL flux control is the ff_ch DAC on the DC-coupled P/N line:
  - ``ff_park_gain``  : static park level (DAC units), held between sequences via
                        stdysel='last' (0 = native zero-applied-flux point).
  - ``ff_gain``       : the flux TARGET of a step/hold, in DAC units.
The flux->frequency model (FLUX_FIT_PARAMS) is therefore fit with ff_gain DAC
units as the flux axis — run step 4 (mQubitLongTimeSpecVsFlux) to measure and fit
it; do NOT reuse volt-based params from the QUA repo.
"""

# makeProxy is exposed here for runners; it is NOT called at import time.
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy  # noqa: F401


# ---- fast-flux channel map (from print(soccfg) + physical wiring) ----
FF_CH = 3   # generator 3 = DAC tile 2 ch 3 = 3_230 on JHC4 (the P/N flux pigtail)

FF_Qubits = {
    # qubit-4 flux line; delay_time (us) = cable/converter skew, 0 until measured
    str(4): {'channel': FF_CH, 'delay_time': 0.0},
}


BaseConfig = {
    # ---- channel map (matches the working initialize4Q.py + soccfg) ----
    "res_ch": 0,          # DAC gen 0 (0_230, JHC3): readout drive
    "qubit_ch": 1,        # DAC gen 1 (1_230, JHC4): qubit drive
    "ff_ch": FF_CH,       # DAC gen 3 (3_230, JHC4): fast-flux line
    "ro_chs": [0],        # ADC readout 0 (0_226, JHC7)
    "nqz": 2,             # readout DAC Nyquist zone (7248.95 MHz, as in initialize4Q)
    "qubit_nqz": 1,       # qubit DAC zone (2557 MHz < fs/2 = 3440 MHz)
    "ff_nqz": 1,          # fast flux is baseband/DC-like
    "mixer_freq": 0.0,    # direct digital synthesis
    "cavity_LO": 0,

    # ---- averaging / timing (from the working SingleShot_FF config) ----
    "reps": 1000,
    "relax_delay": 3000,       # us (runner steps override where needed, e.g. T1: 5000)
    "adc_trig_offset": 0.5,    # us (single-shot value; averaged trans scripts used 1)
    "res_phase": 0,

    # ---- readout pulse (Qubit_Parameters["4"]["Readout"]) ----
    "read_pulse_style": "const",
    "read_length": 20.0,       # us (SS_params Readout_Time; readout maxlen allows ~53 us)
    "read_pulse_gain": 4300,   # DAC units
    "read_pulse_freq": 7248.95,# MHz absolute

    # ---- qubit drive (Qubit_Parameters["4"]["Qubit"]) ----
    "qubit_pulse_style": "arb",
    "qubit_freq": 2557.25,     # MHz; spec center (pi-pulse freq: 2557.37)
    "qubit_pi_freq": 2557.37,  # MHz; use for pi pulses (steps 5, 6)
    "qubit_pi_gain": 12850,    # DAC units (pi); pi/2: 6000
    "qubit_pi2_gain": 6000,
    "qubit_gain": 7000,        # spec/saturation drive gain (Spec_relevant_params)
    "qubit_length": 0.5,       # us; short const spec probe for FF steps 3/4
    "sigma": 0.125,            # us; gaussian pi-pulse sigma
    "flat_top_length": 0.30,   # us (unused while style='arb')

    # ---- fast flux ----
    "ff_park_gain": 0,         # DAC units; static park level (0 = native flux point)
    "FF_Qubits": FF_Qubits,

    # ---- RF switch gating (present in BaseConfig for compatibility; unused) ----
    "trig_buffer_start": 0.02,
    "trig_buffer_end": 0.02,
    "trig_delay": 0.082,
    "use_switch": False,

    # ---- IQ de-winding (0 disables; matches working config) ----
    "cavity_winding_freq": 0,
    "cavity_winding_offset": 0,
}


# ---- flux -> qubit-frequency model (ff_gain DAC units as the flux axis) --------
# None until measured: run step 4 (mQubitLongTimeSpecVsFlux) with fit_flux=True; it
# prints a paste-ready FLUX_FIT_PARAMS = [EJmax(GHz), Ec(GHz), period(DAC),
# offset(DAC), d, tilt] with the flux axis in ff_gain DAC units.  (The QUA repo's
# volt-based params for q6 do NOT transfer.)
FLUX_FIT_PARAMS = None

# Fast-flux operating points for the step-response calibration (DAC units).
FF_PARK_GAIN = 0            # park/baseline level (= BaseConfig ff_park_gain)
FF_STEP_TARGET_GAIN = 8000  # step-3 distortion-probe target; pick from step 4's map

# Data root on the measurement PC (per-qubit subfolder appended via path='q4').
outerFolder = "Z:/FluxTeam/Data/FTT02_SiOxJJ_2026_06_25/RFSOC"


# ---- optional Yokogawa (NOT used in the all-FF workflow) ----------------------
# Kept only for the optional Yoko-swept steps 1-2 (resonator/spec vs DC flux).
# import pyvisa as visa
# from WorkingProjects.TLS_Spectroscopy.Client_modules.PythonDrivers.YOKOGS200 import YOKOGS200
# def make_yoko(visa_address):
#     yoko = YOKOGS200(visa_address, rm=visa.ResourceManager())
#     yoko.SetMode('voltage')
#     return yoko
