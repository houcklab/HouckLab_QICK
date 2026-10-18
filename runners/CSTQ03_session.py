"""CSTQ03 session runner: pick the qubits and bias in SESSION, list the steps in PLAN, run the file.

    python -m runners.CSTQ03_session              # on the fridge (RFSoC + charge yoko)
    python -m runners.CSTQ03_session --dry-run    # fake board: compile every program, keep nothing

Device numbers live in devices/CSTQ03.py. STEP holds every step of the legacy runner
runners/CSTQ03_BFC.py (deleted in phase 5b) with that runner's values (where they differ from
the library defaults), so PLAN = [STEP["t1"]] does what `RunT1 = True` did there; any recipe
keyword changes one step (R.t1(relax_delay=5000)).
Each step's effective parameters are printed before it runs. Guide: docs/running_a_session.md.
"""

import sys

from devices.CSTQ03 import DEVICE
from qicklab.core.session import Session, run
from qicklab.runs import groups as G
from qicklab.runs import recipes as R

# ── 1. SESSION: qubits, bias, the groups every step shares ──────────────────
SESSION = Session(
    DEVICE,
    qubit_readout=5,
    qubit_pulse=5,
    bias_v=0.000,  # [V] charge yoko, held for the whole session
    yoko_fixed=False,  # True: charge_sweep holds the bias and repeats in time
    # library groups except the runner's repetition counts
    coherence=G.coherence(repetitions=1000),
    echo=G.echo(repetitions=3000),
)

# ── 2. STEP: the legacy runner's steps, its values ──────────────────────────
_MODIFIED_RAMSEY = R.modified_ramsey(
    df=1,  # placeholder splitting [MHz]: CSTQ03 has no calibrated Qubit.parity
    f_ge=3754.5,  # Q2's centre, not a measured upper branch (devices/CSTQ03.py)
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
    # the probe frequency it finds is written into charge_dispersion_quasicw's dict (as before)
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
PLAN = [
    STEP["undriven_single_shot"],
]


if __name__ == "__main__":
    run(SESSION, PLAN, dry_run="--dry-run" in sys.argv[1:])
