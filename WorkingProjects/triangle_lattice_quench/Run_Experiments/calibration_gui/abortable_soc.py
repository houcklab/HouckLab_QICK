"""Lets the Auto-Calibration Stop button interrupt a running acquisition on the RFSoC.

QICK's acquire() is one blocking call: it starts the tProc, then loops on
``soc.poll_data()`` until every shot is back. Nothing outside can break into it, and the
soc is a Pyro proxy whose calls from different threads queue behind one connection lock,
so a call from the Stop button would wait behind a ``poll_data`` that can block for
seconds. The abort is therefore cooperative and runs on the WORKER thread, which owns the
connection: this wrapper stands in for the soc during a run, bounds how long each poll may
block, and once the stop flag is up it stops the board and unwinds the acquire.

Observed on this board: killing the Python process (Stop in PyCharm) stops the outputs at
once, even for a 100-million-rep program that would otherwise run for hours. So something
already stops the processor when the client goes away. The mechanism is not known (nothing in
QICK's client code or its stock Pyro server does it); Stop here does the same deliberately.
"""

POLL_TIMEOUT_S = 0.25      # longest one poll_data() may block, so Stop is seen at least this often

# Stop the tProc itself on abort? True (the default) halts the processor at once, which a
# multi-hour program needs; the price is that the compensating (negative) fast-flux pulse of
# the one shot in flight may be skipped, which is negligible next to the alternative. False
# only ends the PC-side wait and the board's data-collection loop and lets the board finish the
# sequence it is playing (if a new run starts first, QICK's config_all() stops the tProc
# before loading the new program).
STOP_TPROC_ON_ABORT = True


class AcquisitionAborted(BaseException):
    """Raised inside acquire() to unwind it. A BaseException on purpose: the stages and
    experiments contain broad ``except Exception`` blocks that would swallow anything else
    and carry on running."""


class AbortableSoc:
    """Delegates everything to the real soc, but checks ``should_abort()`` whenever QICK's
    acquire loop comes back to Python."""

    def __init__(self, soc, should_abort):
        self._soc = soc
        self._should_abort = should_abort
        self.interrupt_errors: list[str] = []      # board-side stop calls that failed, for the log
        self.tproc_stopped = False                 # did we stop the processor (see STOP_TPROC_ON_ABORT)

    def __getattr__(self, name):                   # only reached for names not defined here
        if name in ("_soc", "_should_abort"):      # not set yet (copy/unpickle): avoid recursion
            raise AttributeError(name)
        return getattr(self._soc, name)

    def _check(self) -> None:
        if self._should_abort():
            self._interrupt()
            raise AcquisitionAborted()

    def _interrupt(self) -> None:
        """End the board-side readout loop and, if STOP_TPROC_ON_ABORT, stop the processor.

        ``streamer.stop_readout()`` only sets the streamer's stop flag (its ``finally`` then
        restores the internal start source); the pulse sequence is untouched. ``stop_tproc(
        lazy=True)`` is a single control-register write on tProc v2 (not a reset) and does
        nothing on v1, where stopping would mean a reset and program reload. Neither failing
        may stop the unwind, so errors are recorded, not raised."""
        calls = [("stop_readout", lambda: self._soc.streamer.stop_readout())]
        if STOP_TPROC_ON_ABORT:
            calls.insert(0, ("stop_tproc", lambda: self._soc.stop_tproc(lazy=True)))
        for what, call in calls:
            try:
                call()
                self.tproc_stopped = self.tproc_stopped or what == "stop_tproc"
            except Exception as exc:
                self.interrupt_errors.append(f"{what}: {exc!r}")

    def poll_data(self, totaltime=0.1, timeout=None):
        self._check()
        timeout = POLL_TIMEOUT_S if timeout is None else min(timeout, POLL_TIMEOUT_S)
        data = self._soc.poll_data(totaltime=totaltime, timeout=timeout)
        self._check()                              # a stop that arrived mid-poll drops its data
        return data

    def get_tproc_counter(self, *args, **kwargs):  # the decimated / run_rounds loops poll this
        self._check()
        return self._soc.get_tproc_counter(*args, **kwargs)
