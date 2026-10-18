"""CSTQ03, 2026-10-01 BFC cooldown. History and measurements: docs/devices/CSTQ03.md.

Values as in runners/CSTQ03_BFC.py sections 1-2 on 2026-10-17. Inline notes undated in the
legacy runner are marked "runner, undated". No ParityParams are calibrated in this cooldown:
the runner's Modified Ramsey f_ge 3754.5 / df 1 is Q2's centre, not a measured upper branch.
"""

from qicklab.core.device import Device, Qubit, Readout, ReadoutWindow, Setup, TwpaSetup

DEVICE = Device(
    name="CSTQ03",
    cooldown="2026-10-01",
    data_root="V:/t1Team/Data/2026-10-01_BFC_cooldown/CSTQ03/RFSOC",
    cavity_min=True,  # resonator is a dip
    readout_window=ReadoutWindow(length_us=15, adc_offset_us=0.3),
    ss_window=ReadoutWindow(length_us=15, adc_offset_us=0.3),  # runner: "keep at 15"
    setup=Setup(
        rfsoc_host="192.168.0.103",
        rfsoc_port=8888,
        rfsoc_name="myqick",
        yoko_addr="GPIB1::9::INSTR",
        board_overrides={},  # BASE_CONFIG: nqz 2 (readout), qubit_nqz 1
        twpa=TwpaSetup(
            yoko_addr="GPIB1::12::INSTR",
            synth_port="COM5",
            pnax_addr="GPIB0::16::INSTR",
            pump=(10.7165, -5.5, 1),  # 2026-10 cooldown, ch1
            bias_ua=0,  # set_bias.py target; its note says "18 (10/7/26)"
        ),
    ),
    qubits={
        1: Qubit(
            freq=2763,
            gain=5000,
            pi2_gain=3975 // 2,  # 2026-10-17: = 1987, carried over from gain 3975; re-derive
            sigma=0.6,
            readout=Readout(freq=6791.2, gain=1000),
        ),
        2: Qubit(
            freq=3754.5,
            gain=3800,
            sigma=0.02,
            # runner, undated: readout coarse 4000, behaviour at 4500; readout length 5 us
            readout=Readout(freq=7452.9, gain=4500),
            notes="qubit, T1 found (runner, undated)",
        ),
        3: Qubit(
            freq=2512,
            gain=5000,
            pi2_gain=3975 // 2,  # 2026-10-17: = 1987, carried over from gain 3975; re-derive
            sigma=0.06,
            readout=Readout(freq=6916.2, gain=1000),  # runner, undated: gain 1200 before
        ),
        4: Qubit(
            freq=4117,
            gain=4900,
            sigma=0.02,
            readout=Readout(freq=7593, gain=4000),  # history: docs/devices/CSTQ03.md
        ),
        5: Qubit(
            freq=2651,
            gain=4200,
            sigma=0.08,
            readout=Readout(freq=7095.4, gain=1500),
            notes="alternative line 2756.685 MHz (runner, undated)",
        ),
        6: Qubit(
            freq=2955.6,  # runner, undated: prev 3056, 3238.7, 2965, 3921.5, 2963.5
            gain=4000,
            sigma=0.04,
            readout=Readout(freq=7285, gain=1500),  # runner, undated: prev gain 1400
        ),
    },
)
