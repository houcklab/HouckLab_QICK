"""Session state (`Context`) and the regime-A builder `build_context`.

Config model and carry-overs: docs/concepts/config_regimes.md, docs/architecture.md#carry-overs.
"""

from dataclasses import dataclass

import pyvisa

from qicklab.core import io
from qicklab.core.config import check_gain
from qicklab.hardware.board import BaseConfig, FF_Qubits
from qicklab.hardware.rfsoc import DEFAULT_TIMEOUT_S, makeProxy
from qicklab.hardware.yoko import open_charge_yoko, ramp_to


@dataclass
class Context:
    """Hardware handles, the persistent `config` and derived scalars of the selected qubits."""

    soc: object
    soccfg: object
    yoko: object
    config: dict
    outerFolder: str
    Qubit_Readout: int
    Qubit_Pulse: int
    Qubit_Parameters: dict
    start_voltage: float
    yoko_fixed: bool
    cavity_min: bool
    cavity_gain: float
    resonator_frequency_center: float
    qubit_gain: float
    pi2_gain: float
    qubit_frequency_center: float
    qubit_sigma: float
    qubit_flattop: object

    def working_config(self, *updates):
        """Return a shallow copy of `config` updated with `updates`, for transient knobs."""
        cfg = dict(self.config)
        for u in updates:
            if u:
                cfg.update(u)
        return cfg


def build_context(
    Qubit_Parameters,
    Qubit_Readout,
    Qubit_Pulse,
    start_voltage,
    *,
    Transmission_params,
    Spec_relevant_params,
    tl,
    ts=None,  # accepted for the legacy call shape; its gain keys were read by nothing and are no longer merged
    charge_params,
    cavity_min=True,
    yoko_fixed=False,
    yoko_addr="GPIB1::9::INSTR",
    readout_length_us=15,
    adc_trig_offset_us=None,
    rfsoc_host="192.168.0.103",
    rfsoc_port=8888,
    rfsoc_name="myqick",
    rfsoc_timeout_s=DEFAULT_TIMEOUT_S,
    device=None,
):
    """Connect RFSoC + yoko, build the regime-A config and return a populated Context.

    Regime A and its window: docs/concepts/config_regimes.md, docs/concepts/readout_window.md.
    Raises ValueError before touching hardware if a selected gain is outside 0..32767.
    ``rfsoc_host``/``rfsoc_port``/``rfsoc_name``/``rfsoc_timeout_s`` go to ``make_proxy``
    (docs/hardware.md#rfsoc); ``rfsoc_timeout_s=None`` waits forever on a dead board.
    Registers the session record (``device``, data root, qubits, endpoints) that every later
    save attaches as provenance (docs/architecture.md#provenance).
    """
    readout_entry = Qubit_Parameters[str(Qubit_Readout)]["Readout"]
    qubit_entry = Qubit_Parameters[str(Qubit_Pulse)]["Qubit"]
    check_gain(f"Qubit_Parameters['{Qubit_Readout}']['Readout']['Gain']", readout_entry["Gain"])
    check_gain(f"Qubit_Parameters['{Qubit_Pulse}']['Qubit']['Gain']", qubit_entry["Gain"])
    check_gain(f"Qubit_Parameters['{Qubit_Pulse}']['Qubit']['pi2_Gain']", qubit_entry["pi2_Gain"])
    check_gain("Spec_relevant_params['qubit_gain']", Spec_relevant_params["qubit_gain"])

    soc, soccfg = makeProxy(
        host=rfsoc_host, port=rfsoc_port, name=rfsoc_name, timeout=rfsoc_timeout_s
    )

    outerFolder = Qubit_Parameters[str(Qubit_Readout)]["outerfoldername"]
    io.start_session(
        soccfg,
        device=device,
        data_root=outerFolder,
        qubit_readout=Qubit_Readout,
        qubit_pulse=Qubit_Pulse,
        rfsoc_host=rfsoc_host,
        rfsoc_port=rfsoc_port,
        rfsoc_name=rfsoc_name,
        rfsoc_timeout_s=rfsoc_timeout_s,
        yoko_addr=yoko_addr,
        start_voltage=start_voltage,
        yoko_fixed=yoko_fixed,
    )

    rm = pyvisa.ResourceManager()
    yoko = open_charge_yoko(rm, yoko_addr, start_voltage)
    ramp_to(yoko, start_voltage)

    cavity_gain = Qubit_Parameters[str(Qubit_Readout)]["Readout"]["Gain"]
    resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout)]["Readout"]["Frequency"]
    qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]["Qubit"]["Gain"]
    pi2_gain = Qubit_Parameters[str(Qubit_Pulse)]["Qubit"]["pi2_Gain"]
    qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]["Qubit"]["Frequency"]
    qubit_sigma = Qubit_Parameters[str(Qubit_Pulse)]["Qubit"]["sigma"]
    qubit_flattop = Qubit_Parameters[str(Qubit_Pulse)]["Qubit"]["flattop_length"]

    readout_length_us = float(readout_length_us)
    if readout_length_us <= 0:
        raise ValueError(
            f"readout_length_us must be positive, got {readout_length_us}. "
            f"Set it from the runner (Readout_Time)."
        )
    if adc_trig_offset_us is None:
        adc_trig_offset_us = BaseConfig["adc_trig_offset"]
    adc_trig_offset_us = float(adc_trig_offset_us)
    if adc_trig_offset_us < 0:
        raise ValueError(
            f"adc_trig_offset_us must be >= 0, got {adc_trig_offset_us}. "
            f"Set it from the runner (ADC_Offset)."
        )
    print(
        f"[readout window] integration {readout_length_us} us, "
        f"adc_trig_offset {adc_trig_offset_us} us, "
        f"resonator tone {adc_trig_offset_us + readout_length_us} us"
    )
    trans_config = {
        "reps": 1000,
        # tone starts at t=0, ADC at adc_trig_offset: covers both (docs/concepts/readout_window.md)
        "length": adc_trig_offset_us + readout_length_us,
        "readout_length": readout_length_us,
        "adc_trig_offset": adc_trig_offset_us,
        "pulse_gain": cavity_gain,  # [DAC units]
        "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
        "TransSpan": Transmission_params["span"],  # MHz, span is center +/- this
        "TransNumPoints": Transmission_params["num_points"],
        "cav_relax_delay": 30,
    }
    qubit_config = {
        "qubit_pulse_style": "const",
        "qubit_gain": Spec_relevant_params["qubit_gain"],
        "qubit_freq": qubit_frequency_center,
        "qubit_length": Spec_relevant_params["qubit_length"],
        "SpecSpan": Spec_relevant_params["SpecSpan"],  # MHz, span is center +/- this
        "SpecNumPoints": Spec_relevant_params["SpecNumPoints"],
        "current_voltage": start_voltage,
    }
    expt_cfg = {
        "step": 2 * qubit_config["SpecSpan"] / qubit_config["SpecNumPoints"],
        "start": qubit_config["qubit_freq"] - qubit_config["SpecSpan"],
        "expts": qubit_config["SpecNumPoints"],
    }

    UpdateConfig = trans_config | qubit_config | expt_cfg | tl | charge_params
    config = BaseConfig | UpdateConfig
    print(config)
    config["FF_Qubits"] = FF_Qubits
    config["cavity_min"] = cavity_min  # look for dip, not peak

    return Context(
        soc=soc,
        soccfg=soccfg,
        yoko=yoko,
        config=config,
        outerFolder=outerFolder,
        Qubit_Readout=Qubit_Readout,
        Qubit_Pulse=Qubit_Pulse,
        Qubit_Parameters=Qubit_Parameters,
        start_voltage=start_voltage,
        yoko_fixed=yoko_fixed,
        cavity_min=cavity_min,
        cavity_gain=cavity_gain,
        resonator_frequency_center=resonator_frequency_center,
        qubit_gain=qubit_gain,
        pi2_gain=pi2_gain,
        qubit_frequency_center=qubit_frequency_center,
        qubit_sigma=qubit_sigma,
        qubit_flattop=qubit_flattop,
    )
