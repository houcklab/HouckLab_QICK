"""Session runner of CSTQ03_nucell_fab2026_10 (neutrino cell, Oct 2026 fab), 2026-10-29 cooldown.

    python -m runners.CSTQ03_nucell_fab2026_10_session              # on the fridge
    python -m runners.CSTQ03_nucell_fab2026_10_session --dry-run    # fake board, keeps nothing

Device numbers: devices/CSTQ03_nucell_fab2026_10.py (carried over, not yet measured on this
sample). STEP holds every step with the 2026-10-01 CSTQ03 runner's values
(runners/archive/CSTQ03_2026_10_01_session.py); any recipe keyword changes one step
(R.t1(relax_delay=5000)). Before the first run: TWPA bring-up (docs/experiments/twpa.md).
Each step's effective parameters are printed before it runs. Guide: docs/running_a_session.md.
"""

import sys

from devices.CSTQ03_nucell_fab2026_10 import DEVICE
from qicklab.core.session import Session, run, run_qubit_loop
from qicklab.runs import groups as G
from qicklab.runs import recipes as R

# ── 1. SESSION: qubits, bias, the groups every step shares ──────────────────
SESSION = Session(
    DEVICE,
    qubit_readout=2,
    qubit_pulse=2,
    bias_v=0.000,  # [V] charge yoko, held for the whole session
    yoko_fixed=False,  # True: charge_sweep holds the bias and repeats in time
    # resonator sweep of transmission_fit / transmission_sweep, centred on the readout freq
    transmission=G.transmission(
        span=5,  # [MHz] half-span: sweeps readout freq +- span (inclusive)
        num_points=201,  # frequency points (step = 2 * span / (num_points - 1))
        reps=20,  # hardware averages per point
        rounds=20,  # software repeats of the sweep
    ),
    coherence=G.coherence(repetitions=1000),
    echo=G.echo(repetitions=3000),
)

# ── 2. STEP: every step, the 2026-10-01 runner's values ─────────────────────
_MODIFIED_RAMSEY = R.modified_ramsey(
    df=1,  # placeholder splitting [MHz]: no Qubit.parity calibrated on this sample
    f_ge=3754.5,  # 2026-10-01 CSTQ03 Q2 centre, not a measured upper branch
    num_cycles=1000,
    mapping_p_e_state0=0.1,
    mapping_p_e_state1=0.9,
    mapping_probabilities_calibrated=False,
)
_CHARGE_DISPERSION_QUASICW = R.charge_dispersion_quasicw(probe_freq=2306.567327)
_UNDRIVEN = R.undriven_single_shot(repeat=10000)

STEP = {
    # regime A: transmission, spectroscopy, coherence, charge parity
    "constant_two_tone": R.constant_two_tone(),
    "constant_tone": R.constant_tone(),
    # span / num_points: SESSION transmission group (shared with transmission_sweep);
    # a dip passing the carry-over gate replaces the readout freq for the later steps
    "transmission_fit": R.transmission_fit(
        reps=None,  # hardware averages (None: the transmission group's)
        rounds=None,  # software repeats (None: the transmission group's)
    ),
    "transmission_sweep": R.transmission_sweep(),
    # centred on DEVICE.qubits[qubit_pulse].freq (edit the device file to move the window)
    "two_tone_spec": R.two_tone_spec(
        gain=1500,  # [DAC] drive gain played (spec group default; Qubit.spec_gain if set)
        qubit_length=5,  # [us] const drive length (gauss=False)
        gauss=False,  # True: Gaussian of sigma [us], 4 sigma long, instead of const
        spec_span=10,  # [MHz] half-width: sweeps freq +- spec_span (wide first search)
        spec_num_points=501,  # 0.2 MHz step at span 50
        reps=20,  # hardware averages per point
        rounds=10,  # software repeats of the sweep
        relax_delay=2500,  # [us] between shots
        min_sep_mhz=0.2,  # [MHz] smallest separation accepted as a parity doublet
        fit_window_mhz=0.5,  # [MHz] Lorentzian fit half-window per peak
        prominent_ratio=0.1,  # second peak >= this fraction of the first
    ),
    "spec_gain_length_sweep": R.spec_gain_length_sweep(),
    "chi_shift": R.chi_shift(),
    # the probe frequency it finds is written into charge_dispersion_quasicw's dict
    "two_tone_charge_dispersion_quasicw": R.two_tone_charge_dispersion_quasicw(
        num_cycles=1000,
        charge_dispersion=_CHARGE_DISPERSION_QUASICW.params["ChargeDispersion_params"],
    ),
    "modified_ramsey": _MODIFIED_RAMSEY,
    "modified_ramsey_control": R.modified_ramsey_control(
        num_cycles=1000, cd_max_mhz=0.682, cd_period_mv=4.37, ramsey=_MODIFIED_RAMSEY
    ),
    "charge_dispersion_quasicw": _CHARGE_DISPERSION_QUASICW,
    "charge_dispersion_ramsey": R.charge_dispersion_ramsey(),  # needs df: raises KeyError('df')
    # pulse shape from the device: Gaussian of DEVICE.qubits[qubit_pulse].sigma [us], 4 sigma long
    # (flattop_length set: software sweep AmplitudeRabiFF_N, flattop_relax_delay applies)
    "amplitude_rabi": R.amplitude_rabi(
        qubit_freq=None,  # [MHz] drive frequency (None: DEVICE.qubits[qubit_pulse].freq)
        max_gain=30000,  # [DAC] top of the gain sweep from 0 (<= 32767)
        number_of_steps=401,  # gain points (step = int(max_gain / number_of_steps))
        reps=20,  # hardware averages per point
        rounds=20,  # software repeats of the sweep
        relax_delay=3000,  # [us] between shots
        fit=True,  # cosine fit, pi gain = period / 2 (copy into Qubit(gain=...))
        flattop_relax_delay=8000,  # [us] relax_delay used only with a flat-top qubit pulse
    ),
    "t1": R.t1(),
    "t1_t2e": R.t1_t2e(),
    "t1_t2r_t2e": R.t1_t2r_t2e(),
    "t2_ramsey": R.t2_ramsey(),
    "t2_echo": R.t2_echo(),
    "trans_qubit_spec": R.trans_qubit_spec(),
    "charge_sweep": R.charge_sweep(),
    "charge_transmission_sweep": R.charge_transmission_sweep(
        voltage_start=0, voltage_end=0.05, voltage_step=0.005
    ),
    "active_reset_verify": R.active_reset_verify(),
    "interleaved_coherence": R.interleaved_coherence(cycles=10000, undriven=_UNDRIVEN),
    # regime B: single-shot family (the config switch happens automatically)
    "single_shot": R.single_shot(),
    # drive off: readout-only IQ cloud + telegraph time series (readout from DEVICE / ss_window);
    # its own recipe, not _UNDRIVEN (repeat=10000, interleaved_coherence's)
    "undriven_single_shot": R.undriven_single_shot(
        shots=1_000_000,  # single shots per pass (~5 min at relax_delay 300)
        relax_delay=20,  # [us] after each shot; sets the sampling period (None: single_shot group's)
        relax_delay_sweep=(10, 20, 30, 40, 50, 60, 70, 80, 90, 100),  # [us] e.g. (20, 50, 100, 300): one acquisition each per pass
        min_separation_sigma=2.0,  # blob separation [combined sigma] to call two blobs
        average_shots=1,  # consecutive shots averaged per time-series point (1 = off)
        bin_sizes=(1, 2, 4, 8, 16, 32, 64),  # [shots] rate-vs-averaging sweep
        charge_sweep=True,  # True: one acquisition per bias of the voltage grid below
        voltage_start=0.0,  # [V] np.arange(start, end, step), end excluded
        voltage_end=0.02,  # [V]
        voltage_step=0.001,  # [V]
        charge_settle_s=1.0,  # [s] wait after each bias ramp
        repeat=1,  # passes per qubit visit; the qubit loop (section 4) does the repeating
        plot_disp=False,  # no window: the loop runs unattended
    ),
    "t1_single_shot": R.t1_single_shot(repetitions=3000),
    "readout_optimize": R.readout_optimize(),
    "qubit_optimize": R.qubit_optimize(),
    "auto_coherence": R.auto_coherence(
        skip_sweet_spot_search=True,
        calibrate_qubit_freq=False,
        ss_gain_span_frac=0.6,
        ss_gain_pts=100,
        t1_step=5,
        t1_repetitions=3,
        t2_expts=401,
        t2_repetitions=3,
        t2e_max_us=500,
        t2e_repetitions=3,
    ),
    "zero_span_parity": R.zero_span_parity(analysis={"classifier_method": "apriori_gmm"}),
}

# ── 3. PLAN: what to run, in order (repeats allowed) ────────────────────────
# Bring-up of a new sample, one stage at a time (paste the measured values into the device file):
#   transmission_fit -> two_tone_spec -> amplitude_rabi -> t1 -> t2_ramsey -> t2_echo
#   -> single_shot / readout_optimize
PLAN = [
    # STEP["transmission_fit"],
    # STEP["two_tone_spec"],
    # STEP["amplitude_rabi"],
    # STEP["t1"],
    STEP["undriven_single_shot"],
]


# ── 4. QUBIT LOOP (optional): the whole PLAN on each qubit in turn, round after round ──
# Set LOOP_QUBITS to e.g. (1, 2, 3, 4): PLAN runs on Q1 (readout = pulse = Q1), then Q2, ...,
# then the round starts again. SESSION.qubit_readout / qubit_pulse are then ignored. In a looped
# undriven_single_shot use repeat=1 (the loop repeats) and plot_disp=False.
LOOP_QUBITS = (1, 2, 3, 4, 5, 6)  # None: plain run(SESSION, PLAN)
LOOP_CYCLES = 1_000_000  # rounds over LOOP_QUBITS; None = until Ctrl-C


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv[1:]
    if LOOP_QUBITS:
        run_qubit_loop(SESSION, PLAN, LOOP_QUBITS, cycles=LOOP_CYCLES, dry_run=dry)
    else:
        run(SESSION, PLAN, dry_run=dry)
