"""
Device configuration for the FTTv02_SiOxJJ flux-tunable transmon (TLS spectroscopy).

Seeded from the QICK BFF_ACStark branch (WorkingProjects/QM_Team/qubit_measurements
Calib/initialize4Q.py) which drives the SAME board (nameserver 192.168.1.125).

QUA -> QICK frequency note
--------------------------
The QUA setup used an external analog LO (E8257D) + IQ mixer with a digital IF, so
each tone was f_physical = LO_freq + IF.  QICK synthesizes the whole tone digitally
on the RFSoC DAC, so here every ``*_freq`` key is an ABSOLUTE frequency in MHz and
the Nyquist zone (``nqz`` / ``qubit_nqz``) places it in band.  The external-LO
power / IQ-mixer-imbalance calibration from QUA is not needed and is dropped.

Everything marked ``# DEVICE`` is a hardware-specific number to (re)measure on your
cooldown -- treat the values here as reasonable starting points, not ground truth.
They are exactly the knobs the TLS pipeline (steps 1, 2, 5) is designed to find.
"""

# makeProxy is exposed here for runners; it is NOT called at import time.
from WorkingProjects.TLS_Spectroscopy.Client_modules.CoreLib.socProxy import makeProxy  # noqa: F401


# ---- fast-flux DAC channel map (matches BFF_ACStark FF_channel1 = Q1) ----
FF_CH_Q1 = 2   # DEVICE: RFSoC DAC generator wired to the qubit's fast-flux line

FF_Qubits = {
    # per-qubit fast-flux gen channel + cable/converter delay (us) for time alignment
    str(1): {'channel': FF_CH_Q1, 'delay_time': 0.017 + 0.0045},
}


BaseConfig = {
    # ---- channel map (fixed by wiring) ----
    "res_ch": 0,          # DAC generator: readout resonator drive
    "qubit_ch": 1,        # DAC generator: qubit drive
    "ff_ch": FF_CH_Q1,    # DAC generator: fast-flux line (the flux "step" pulse)
    "ro_chs": [0],        # ADC readout channel(s)
    "nqz": 2,             # Nyquist zone of the readout DAC (cavity ~ 6.9 GHz)
    "qubit_nqz": 1,       # Nyquist zone of the qubit DAC (f01 ~ 2-2.6 GHz -> zone 1)
    "ff_nqz": 1,          # Nyquist zone of the fast-flux DAC (baseband/DC-like)
    "mixer_freq": 0.0,    # MHz; 0 => direct digital synthesis (no digital up-mixer)
    "cavity_LO": 0,       # Hz; software base offset added back to displayed cavity freq

    # ---- averaging / timing ----
    "reps": 1000,         # hardware averages per point
    "relax_delay": 3000,  # us; wait between shots (>~ a few T1); QUA reset_time analog
    "adc_trig_offset": 1, # us; delay from readout pulse to ADC capture window   # DEVICE
    "res_phase": 0,

    # ---- readout pulse ----
    "read_pulse_style": "const",
    "read_length": 5.0,        # us; ADC integration window                      # DEVICE
    "read_pulse_gain": 10000,  # DAC units                                       # DEVICE
    "read_pulse_freq": 6902.15,# MHz absolute readout freq (QUA r_LO+r_IF)       # DEVICE

    # ---- qubit spectroscopy / drive defaults ----
    "qubit_pulse_style": "const",
    "qubit_freq": 2400.0,      # MHz absolute f01 (QUA q_LO+q_IF), updated per flux # DEVICE
    "qubit_gain": 5000,        # DAC units (spec/drive amplitude)                # DEVICE
    "qubit_length": 0.5,       # us; CW/saturation spec-pulse length (QUA cw_len)
    "sigma": 0.05,             # us; gaussian pi-pulse sigma (arb/flat_top styles)
    "flat_top_length": 0.30,   # us

    # ---- RF switch gating (from BFF config; harmless if no switch) ----
    "trig_buffer_start": 0.02, # us
    "trig_buffer_end": 0.02,   # us
    "trig_delay": 0.082,       # us
    "use_switch": False,

    # ---- IQ de-winding (cable phase vs freq); 0 disables ----
    "cavity_winding_freq": 0,
    "cavity_winding_offset": 0,

    # ---- fast-flux structures (consumed by the FF experiments) ----
    "FF_Qubits": FF_Qubits,
}


# ---- flux -> qubit-frequency model (asymmetric-SQUID transmon) --------------
# [EJmax(GHz), Ec(GHz), period(V), sweet-spot offset(V), asymmetry d, tilt(GHz/V)]
# These are the numbers step 2 (qubit-spec-vs-flux) fits and prints.  The values
# below are the QUA TLSSpectroscopy.py FLUX_FIT_PARAMS for FTTv02 q6 as a starting
# point -- re-fit per device/qubit.
FLUX_FIT_PARAMS = [19.50014965, 0.04005047978, 0.837913911,
                   0.1906228572, 0.1391267552, 0.0]

# Static-flux operating points (Yokogawa GS200 voltage, V).                     # DEVICE
BASELINE_DC_OFFSET = 0.19782   # park / sweet-spot bias
TARGET_DC_OFFSET = 0.35        # distortion-probe target for step 3

# Data root (Windows share on the lab PC).                                      # DEVICE
outerFolder = r"Z:\FluxTeam\Data\FTTv02_SiOxJJ_QICK"


# ---- optional Yokogawa DC flux source ---------------------------------------
# The static/DC flux bias is a Yokogawa GS200 over VISA.  Left commented so
# importing this module never touches hardware; construct it in a runner.
#
# import pyvisa as visa
# from WorkingProjects.TLS_Spectroscopy.Client_modules.PythonDrivers.YOKOGS200 import YOKOGS200
# YOKO_VISA = "USB0::0x0B21::0x0039::91S929899::0::INSTR"   # DEVICE
# def make_yoko():
#     yoko = YOKOGS200(YOKO_VISA, rm=visa.ResourceManager())
#     yoko.SetMode('voltage')
#     return yoko
