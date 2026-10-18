"""CSTQ03 "v2b nu cell" parameter set: archived, never imported by a session.

The table `Qubit_Parameters_v2b` that sat unused in the legacy runner (runners/CSTQ03_BFC.py,
deleted in phase 5b; frozen in tests/regression/fixtures/cstq03_legacy_runner.py.txt), as a
Device. `DEVICE.legacy_parameters()` reproduces that table byte for byte. Whether "v2b nu
cell" is an earlier cooldown of this chip or a sibling chip is not recorded, so `cooldown` is
the label "v2b", not a date. History and the notes per qubit: docs/devices/CSTQ03.md
("Archived: v2b "nu cell" parameter set"). Inline notes are the runner's, undated, including
the per-slot "currently working on N" (meaning unknown; docs/devices/CSTQ03.md, "Per-qubit
history").

Not recorded with the table, filled with what reproduces it or with the library defaults:
`data_root` (the runner's table shared the 2026-10-01 per-qubit folders with the current
table; where v2b data were saved is unknown), the readout windows, `cavity_min` and `setup`.
"""

from qicklab.core.device import Device, Qubit, Readout, Setup

DEVICE = Device(
    name="CSTQ03",
    cooldown="v2b",  # "v2b nu cell"; no date recorded
    data_root="V:/t1Team/Data/2026-10-01_BFC_cooldown/CSTQ03/RFSOC",  # as the runner's table
    setup=Setup(),  # not recorded: library defaults
    qubits={
        # currently working on 3
        1: Qubit(
            freq=1752,
            gain=5000,
            pi2_gain=3975 // 2,
            sigma=0.2,
            # readout gain 500 okay, 700 too much, 520 maybe too much, 530 too much
            readout=Readout(freq=6748, gain=2000),
        ),
        # currently working on 6
        2: Qubit(
            freq=4185.6,
            gain=2675,
            pi2_gain=2400 // 2,
            sigma=0.04,
            # readout coarsely tuned to 4000, seeing behavior at 4500
            readout=Readout(freq=7408.37, gain=3500),
            notes="qubit, T1 found",
        ),
        # currently working on 4
        3: Qubit(
            freq=2900,
            gain=5000,
            pi2_gain=3975 // 2,
            sigma=1,
            flattop_length=1,
            readout=Readout(freq=6870.8, gain=1500),  # readout gain 600 too much
            notes="qubit found 1719.8273",
        ),
        # currently working on (blank)
        4: Qubit(
            freq=4590,
            gain=2800,
            sigma=0.02,
            # readout history: 7288.48 at 1180; 400 good, 420 too much i think, 600 too much;
            # with directional coupler 1400 good, 1500 maybe too much
            readout=Readout(freq=7535.96, gain=2000),
            notes=(
                "qubit, 7468 was the previous pi pulse with sigma = 0.15, 5396 0.225 6435 "
                "2603.33 used for ramsey 7009 // 2"
            ),
        ),
        # currently working on 5
        5: Qubit(
            freq=2758.3,
            gain=4000,
            sigma=1,
            # readout 4500 with directional coupler, 1500 good without
            readout=Readout(freq=7050, gain=3000),
            notes="qubit, T1 found; alternative line 2756.685",
        ),
        # currently working on 2
        6: Qubit(
            freq=3258.1,
            gain=4600,
            pi2_gain=4750 // 2,
            sigma=0.1,
            readout=Readout(freq=7244.8, gain=2000),
            notes="cant find",
        ),
    },
)
