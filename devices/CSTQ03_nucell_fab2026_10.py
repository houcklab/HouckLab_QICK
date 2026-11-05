"""CSTQ03 in a neutrino cell, October 2026 fab; 2026-10-29 BFC cooldown.

Shares the fridge with devices/CSTQ03_qcage_fab2026_09.py. Naming: docs/adding_a_device.md.
Every qubit value is carried over from the 2026-10-01 cooldown's CSTQ03
(devices/archive/CSTQ03_2026_10_01.py) as a starting point for a different sample: re-measure
before trusting any of them (transmission -> spectroscopy -> Rabi -> T1/T2/T2E).
TODO before the first RFSoC run: confirm this sample's charge-line yoko address and which
RFSoC DAC/ADC lines its readout and drive use (Setup.yoko_addr, board_overrides).
"""

from qicklab.core.device import Device, Qubit, Readout, ReadoutWindow, Setup, TwpaSetup

DEVICE = Device(
    name="CSTQ03_nucell_fab2026_10",
    chip="CSTQ03",
    package="nucell",
    fab="2026-10",
    cooldown="2026-10-29",
    data_root="V:/t1Team/Data/2026-10-29_BFC_cooldown/CSTQ03_nucell_fab2026_10/RFSOC",
    cavity_min=True,  # resonator is a dip (2026-10-01 CSTQ03); check on the first transmission
    readout_window=ReadoutWindow(length_us=15, adc_offset_us=0.3),
    ss_window=ReadoutWindow(length_us=15, adc_offset_us=0.3),
    setup=Setup(
        rfsoc_host="192.168.0.103",
        rfsoc_port=8888,
        rfsoc_name="myqick",
        yoko_addr="GPIB1::9::INSTR",  # 2026-10-01 charge line; confirm for this sample
        board_overrides={},  # BASE_CONFIG: nqz 2 (readout), qubit_nqz 1
        twpa=TwpaSetup(
            yoko_addr="GPIB1::12::INSTR",
            synth_port="COM5",
            pnax_addr="GPIB0::16::INSTR",
            pump=(10.7070, -1, 0),  # 2026-10-01 point; recalibrate (docs/experiments/twpa.md)
            bias_ua=13,  # set after this cooldown's flux_sweep
        ),
    ),
    # 2026-10-29: all values below are the 2026-10-01 CSTQ03 ones, not measured on this sample
    qubits={
        1: Qubit(
            freq=2763,
            gain=5000,
            sigma=0.6,
            readout=Readout(freq=6791.2, gain=1000),
        ),
        2: Qubit(
            freq=3754.5,
            gain=3800,
            sigma=0.02,
            readout=Readout(freq=7452.9, gain=4500),
        ),
        3: Qubit(
            freq=2512,
            gain=5000,
            sigma=0.06,
            readout=Readout(freq=6916.2, gain=1000),
        ),
        4: Qubit(
            freq=4117,
            gain=4900,
            sigma=0.02,
            readout=Readout(freq=7593, gain=4000),
        ),
        5: Qubit(
            freq=2651,
            gain=4200,
            sigma=0.08,
            readout=Readout(freq=7095.4, gain=1500),
        ),
        6: Qubit(
            freq=2955.6,
            gain=4000,
            sigma=0.04,
            readout=Readout(freq=7285, gain=1500),
        ),
    },
)
