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
from qicklab.core.session import Session, run
from qicklab.runs import groups as G
from qicklab.runs import recipes as R

# ── 1. SESSION: qubits, bias, the groups every step shares ──────────────────
SESSION = Session(
    DEVICE,
    qubit_readout=1,
    qubit_pulse=1,
    bias_v=0.000,  # [V] charge yoko, held for the whole session
    yoko_fixed=False,  # True: charge_sweep holds the bias and repeats in time
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
    "transmission_fit": R.transmission_fit(),
    "transmission_sweep": R.transmission_sweep(),
    "two_tone_spec": R.two_tone_spec(),
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
    "amplitude_rabi": R.amplitude_rabi(),
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
    "undriven_single_shot": _UNDRIVEN,
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
    STEP["transmission_fit"],
]


if __name__ == "__main__":
    run(SESSION, PLAN, dry_run="--dry-run" in sys.argv[1:])
