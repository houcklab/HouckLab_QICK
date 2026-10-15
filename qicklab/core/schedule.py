"""tProc timing: the clock cycle, the realised axis of a register-swept wait, and the
per-rep period of a compiled program (the ModifiedRamsey schedule ledger)."""

import numpy as np


def tproc_cycle_us(soccfg):
    """One tProc clock cycle in us, read from the board (1 / f_time; 1/430.08 MHz =
    0.0023251488 us on the lab board): docs/concepts/timing_and_units.md#clocks."""
    return soccfg.cycles2us(1)


def realised_wait_axis_us(soccfg, start, step, expts, segments=1):
    """Wait axis (us) of a register-swept wait as the tProc realises it.

    The program advances its wait register by ``us2cycles(step / segments)`` whole tProc
    cycles per point and plays ``segments`` equal waits, so point ``i`` waits
    ``segments * (us2cycles(start / segments) + i * us2cycles(step / segments))`` cycles,
    not ``start + i * step`` us. Fixed pulse / sync overhead is not included. A grid that
    is already whole cycles (e.g. a ``quantised_t2e_step`` step) is returned as
    ``start + i * step`` unchanged, not re-derived to within float rounding.
    docs/concepts/timing_and_units.md#register-swept-wait-axis
    """
    c0 = soccfg.us2cycles(start / segments)
    dc = soccfg.us2cycles(step / segments)
    realised = soccfg.cycles2us(segments * (c0 + dc * np.arange(expts)))
    nominal = start + np.arange(expts) * step
    if np.allclose(realised, nominal, rtol=1e-12, atol=1e-12):
        return nominal
    return realised


class RepPeriodMixin:
    """For an AveragerProgram whose only register-valued `sync` waits self.wait_cycles."""

    def scheduled_rep_period_cycles(self):
        """Per-rep period of the emitted schedule in tProc cycles: every synci immediate
        plus self.wait_cycles per register sync between LOOP_J and loopnz, active-reset
        overhead included (docs/experiments/modified_ramsey.md#timing-ledger)."""
        plist = self.prog_list
        start = next(i for i, x in enumerate(plist) if x.get("label") == "LOOP_J")
        end = next(i for i, x in enumerate(plist) if x["name"] == "loopnz")
        t = 0
        for inst in plist[start:end]:
            if inst["name"] == "synci":
                t += inst["args"][0]
            elif inst["name"] == "sync":
                t += self.wait_cycles
        return int(t)

    def scheduled_rep_period_us(self):
        f_time = float(self.soccfg["tprocs"][0]["f_time"])
        return self.scheduled_rep_period_cycles() / f_time
