"""Thin runner wrapper for the ModifiedRamsey verification harness.

The checks themselves live in Experiments/verify_ModifiedRamsey.py so they can
also be run with no board attached (tier A):

    python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.verify_ModifiedRamsey
"""

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.verify_ModifiedRamsey import (
    run_board_suite,
    run_offline_suite,
)

__all__ = ["run_verify_modified_ramsey"]


def run_verify_modified_ramsey(ctx, VerifyModifiedRamsey_params):
    """Tier A + tier B verification of the ModifiedRamsey fix set.

    Runs the offline checks first (they need only ctx.soccfg, and a failure
    there means the on-board numbers cannot be interpreted), then the board
    checks. Needs no qubit signal, no calibration, and no YOKO.
    """
    params = dict(VerifyModifiedRamsey_params or {})

    if params.get("run_offline", True):
        offline = run_offline_suite(soccfg=ctx.soccfg)
        if not offline["passed"] and not params.get("force", False):
            print("[verify_MR] offline checks FAILED against the live soccfg -- "
                  "stopping before the board stages. Pass force=True to continue "
                  "anyway.")
            return {"offline": offline, "board": None}
    else:
        offline = None

    board = run_board_suite(ctx, params)
    return {"offline": offline, "board": board}
