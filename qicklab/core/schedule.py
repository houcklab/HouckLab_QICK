"""Per-rep period of a compiled tProc program (the ModifiedRamsey schedule ledger)."""


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
