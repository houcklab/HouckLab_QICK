"""Per-shot accumulated I/Q extraction that survives the QICK buffer change.

Up to qick ~0.2.28x, ``AveragerProgram._process_accumulated`` handed back the
raw per-repetition accumulated stream, so ``prog.di_buf[ch]`` / ``prog.dq_buf[ch]``
were flat arrays of length ``reps * reads_per_shot`` (times ``expts`` for
RAveragerProgram) in raw accumulator units. Every single-shot experiment here
reshapes/strides those arrays.

From qick ~0.2.29x on (the BFG board runs 0.2.367), that method first calls
``_average_buf``, which averages over the reps axis and divides by the readout
length. ``di_buf`` therefore holds ONE length-normalized point per read per
channel, and the old reshape fails with e.g.

    ValueError: cannot reshape array of size 1 into shape (1,1000)

The raw stream still exists, as ``prog.acc_buf``: one array per readout channel
shaped ``(*loop_dims, reads_per_shot, 2)`` with the I/Q pair last, in raw
accumulator units (no length normalization, no IQ-offset removal) — i.e. exactly
what the old ``di_buf``/``dq_buf`` held, just not flattened.

``raw_shot_buffers`` flattens it back to the historical layout so call sites keep
their existing reshape/stride/normalization arithmetic unchanged.

Note on rounds: ``acc_buf`` is overwritten every round, so with ``rounds`` > 1 it
holds the last round only. That matches the old behaviour (``di_buf`` was also
re-derived per round), but single-shot programs should still force ``rounds`` = 1.
"""

import numpy as np


def raw_shot_buffers(prog):
    """Return ``(di_buf, dq_buf)`` in the pre-0.2.29x flat per-shot layout.

    Parameters
    ----------
    prog : qick AveragerProgram / RAveragerProgram
        A program on which ``acquire()`` has already been called.

    Returns
    -------
    (list of numpy.ndarray, list of numpy.ndarray)
        One flat float array per declared readout channel (declaration order,
        not absolute channel number), length ``prod(loop_dims) * reads_per_shot``,
        in raw accumulator units.
    """
    acc_buf = getattr(prog, "acc_buf", None)
    if not acc_buf:
        # qick <= ~0.2.28x (or a synthetic prog in a self-test): di_buf is
        # already the raw stream. Hand the containers back untouched so any
        # indexing convention the caller relies on still works.
        return prog.di_buf, prog.dq_buf

    di_buf = [np.asarray(d)[..., 0].ravel() for d in acc_buf]
    dq_buf = [np.asarray(d)[..., 1].ravel() for d in acc_buf]
    return di_buf, dq_buf
