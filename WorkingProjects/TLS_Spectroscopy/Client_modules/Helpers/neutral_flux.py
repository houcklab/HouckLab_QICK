"""Explicit entry point for new controller-neutral flux experiments only.

No existing runner or experiment imports this helper. Reset executes at park
before the caller starts a compiled, complete flux excursion. The caller owns
the causal history, sufficient recovery/park settling, the reset decision, and
the qubit/readout timeline. A boolean acknowledgment cannot establish that a
physical line or inverse filter has settled.
"""

import numpy as np

from fluxpred.qick import emit, validate_program_compatibility


def begin_schedule(plan, prog, *, channel, reset_completed_at_park):
    """Align once at the beginning and queue flux without consuming its horizon.

    Contract: the caller has finished active reset at the recorded park gain,
    included or bounded all preceding flux history in ``plan``, and verified the
    model's terminal residual. The plan includes its return correction and an
    explicit final park plateau. Active reset's variable duration is outside
    this fixed schedule; this function neither computes nor clears filter state.

    After this call, queue drive/readout at explicit offsets from the shared
    origin. Do not use ``sync_all`` before a drive/readout intended to overlap
    flux: that would advance to the *end* of the complete flux schedule.
    Synchronize all channels only after those operations are queued and before
    the next reset/shot. Check the complete QICK program's compiled instruction
    count; a plan's allowance alone is not a hardware compilation check.
    """
    if reset_completed_at_park is not True:
        raise ValueError("caller must acknowledge reset completed at park")
    configured_park = float(prog.cfg.get("ff_park_gain", np.nan))
    if not np.isfinite(configured_park) or configured_park != plan.park_gain:
        raise ValueError("program park gain does not match the compiled schedule")
    if not plan.segments or plan.segments[-1].gain != int(np.rint(plan.park_gain)):
        raise ValueError("a complete excursion must end with an explicit park plateau")
    validate_program_compatibility(plan, prog, channel=channel)
    prog.sync_all(0)
    emit(plan, prog, channel=channel)
