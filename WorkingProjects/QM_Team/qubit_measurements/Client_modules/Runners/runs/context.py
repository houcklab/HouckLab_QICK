"""Shared runtime context for the CSTQ03 measurement runner.

`Context` bundles the state that the old CSTQ03_BFC.py script kept as module-level
globals (soc/soccfg/yoko, the persistent instrument `config`, the output folder, and
the derived per-qubit scalars). Every extracted measurement routine takes `(ctx, params)`.

Config model (see docs/superpowers/specs/2026-07-02-cstq03-runner-refactor-design.md §5):
  * `ctx.config` is the PERSISTENT instrument config. Only measured carry-overs
    `pulse_freq` (found cavity frequency) and `res_phase` (calibrated readout phase)
    are written back to it by routines.
  * Transient per-experiment knobs (reps, rounds, spans, sigma, per-scan gains, ...)
    go on a fresh local copy from `ctx.working_config(params)` and never leak.
"""

from dataclasses import dataclass

import pyvisa

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import *
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.socProxy import *
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import *


class NullYoko:
    """Stand-in for the YOKO GS200 when the charge line is not connected.

    Speaks just enough of the SCPI surface that `ramp_to()` and the `:SOUR:LEV?`
    reads scattered through the measurement routines keep working: it remembers a
    virtual level and reports it back. Experiments that never move the voltage
    (transmission, two-tone, Rabi, T1/T2/T2E, single-shot) therefore run unchanged.

    It deliberately REFUSES to fake a voltage change. Charge-sweep / charge-parity
    routines derive their physics from stepping the yoko; silently pretending the
    step happened would produce plausible-looking but meaningless data, so any
    attempt to move off the starting level raises instead.
    """

    def __init__(self, level=0.0):
        self._level = float(level)
        print(f"[NullYoko] No yoko in use - virtual level pinned at {self._level} V. "
              f"Voltage-stepping experiments (charge sweep / charge dispersion / "
              f"modified Ramsey) will raise if run.")

    def write(self, cmd):
        cmd = str(cmd).strip()
        upper = cmd.upper()
        if upper.startswith(":SOUR:LEV"):
            target = float(cmd.split()[-1])
            if abs(target - self._level) > 1e-12:
                raise RuntimeError(
                    f"NullYoko: refusing to fake a voltage change "
                    f"({self._level} V -> {target} V). This experiment needs a real "
                    f"charge line. Connect/power the YOKO and rebuild the context with "
                    f"use_yoko=True (see UseYoko in the runner)."
                )
        # :SOUR:FUNC VOLT, :OUTP ON, etc. are no-ops.

    def query(self, cmd):
        upper = str(cmd).strip().upper()
        if upper.startswith(":SOUR:LEV"):
            # %.12g, not %.6f: ramp_to() reads the level back and writes it
            # again, and write() refuses a move larger than 1e-12. Rounding the
            # read-back to 6 decimals would make that echo look like a real
            # voltage change for any start_voltage with finer resolution.
            return f"{self._level:.12g}"
        if upper.startswith("*IDN"):
            return "NullYoko,virtual,0,0"
        return "0"

    def close(self):
        pass


@dataclass
class Context:
    # hardware handles
    soc: object
    soccfg: object
    yoko: object
    # False when `yoko` is a NullYoko stub (no charge line this session)
    has_yoko: bool
    # persistent instrument config (mutated only for the pulse_freq / res_phase carry-overs)
    config: dict
    outerFolder: str
    # active qubit selection
    Qubit_Readout: int
    Qubit_Pulse: int
    Qubit_Parameters: dict
    # session-wide flags/values
    start_voltage: float
    yoko_fixed: bool
    cavity_min: bool
    # derived scalars for the selected qubit(s)
    cavity_gain: float
    resonator_frequency_center: float
    qubit_gain: float
    pi2_gain: float
    qubit_frequency_center: float
    qubit_sigma: float
    qubit_flattop: object

    def working_config(self, *updates):
        """Return a fresh shallow copy of the persistent config, updated with the
        given dict(s). Use this for transient per-experiment knobs so they never
        leak into later measurements."""
        cfg = dict(self.config)
        for u in updates:
            if u:
                cfg.update(u)
        return cfg


def sanity_dump(cfg, tag=""):
    keys = ["pulse_freq","qubit_freq","SpecSpan","SpecNumPoints","step","start",
            "qubit_pulse_style","qubit_length","qubit_gain","pulse_gain",
            "readout_length","cavity_min"]
    print(f"\n--- Sanity {tag} ---")
    for k in keys:
        if k in cfg: print(f"{k:>18}: {cfg[k]}")
    # If BaseConfig stores LOs/IFs/NCOs, print them too:
    for k in ["cavity_LO","qubit_LO","cavity_IF","qubit_IF","read_lo","drive_lo"]:
        if k in cfg: print(f"{k:>18}: {cfg[k]}")
    print("-------------------\n")


def rebuild_singleshot_config(ctx, SS_params):
    """Switch ctx.config into the single-shot regime.

    Reproduces the unconditional top-level `config` rebuild the original script
    performed AFTER the RunActiveResetVerify block (old CSTQ03_BFC.py lines
    2834-2835 + 2990-3016). The original ran a second `config = BaseConfig |
    UpdateConfig` here so every block below it (SingleShot, T1SS, readout/qubit
    optimize, AutoCoherence, ZeroSpanParity) executed under this config, not the
    one used by the transmission/spec/Ramsey/coherence blocks above. The client
    calls this once, at that same point in the run order.
    """
    qubit_gains = [ctx.Qubit_Parameters[str(Q_R)]['Qubit']['Gain'] for Q_R in SS_params["Qubit_Pulse"]]
    qubit_frequency_centers = [ctx.Qubit_Parameters[str(Q_R)]['Qubit']['Frequency'] for Q_R in SS_params["Qubit_Pulse"]]

    UpdateConfig = {
        ###### cavity
        # "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
        "read_pulse_style": "const", # --Fixed
        # The resonator tone starts at t=0; ADC integration starts ADC_Offset
        # later, so the tone must cover offset + the full integration window.
        "length": SS_params["ADC_Offset"] + SS_params["Readout_Time"],
        "readout_length": SS_params["Readout_Time"], # us (ADC integration window)
        "adc_trig_offset": SS_params["ADC_Offset"],
        "pi2_SS" : SS_params["pi2_SS"],

        # "pulse_gain": cavity_gain, # [DAC units]
        "pulse_gain": ctx.cavity_gain,  # [DAC units]
        "pulse_freq": ctx.resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
        ##### qubit spec parameters
        "qubit_pulse_style": "arb",
        "sigma": ctx.qubit_sigma,  ### units us, define a 20ns sigma
        "qubit_gain": ctx.qubit_gain,
        "f_ge": ctx.qubit_frequency_center,
        "qubit_gains": qubit_gains,
        "f_ges": qubit_frequency_centers,
        ##### define shots
        "shots": SS_params["Shots"], ### this gets turned into "reps"
        "relax_delay": SS_params['relax_delay'],  # us
        "flattop_length": ctx.qubit_flattop
    }

    config = BaseConfig | UpdateConfig
    config["FF_Qubits"] = FF_Qubits
    config['Read_Indeces'] = ctx.Qubit_Readout
    ctx.config = config


def build_context(Qubit_Parameters, Qubit_Readout, Qubit_Pulse, start_voltage, *,
                  Transmission_params, Spec_relevant_params, tl, ts, charge_params,
                  cavity_min=True, yoko_fixed=False, yoko_addr='GPIB1::9::INSTR',
                  use_yoko=True, readout_length_us=15, adc_trig_offset_us=None):
    """Connect to the RFSoC + yoko, assemble the instrument config, and derive the
    per-qubit scalars — the setup boilerplate that used to sit at the top of the
    CSTQ03_BFC.py script — returning a populated Context.

    The keyword param dicts (Transmission_params, Spec_relevant_params, tl, ts,
    charge_params) are the client's tuning dicts; they feed the initial config
    assembly exactly as the original script did.

    `readout_length_us` / `adc_trig_offset_us` set the readout window for every
    experiment that runs under this config, i.e. everything BEFORE the client's
    `rebuild_singleshot_config()` call: transmission, two-tone, chi shift, Rabi,
    T1/T2/T2E, charge dispersion, ModifiedRamsey, ActiveResetVerify. The
    single-shot regime takes its window from SS_params["Readout_Time"] /
    SS_params["ADC_Offset"] instead. `adc_trig_offset_us=None` keeps
    BaseConfig["adc_trig_offset"]; the default readout_length_us=15 preserves the
    value this function hardcoded before it was exposed to the runner.
    """
    soc, soccfg = makeProxy()

    outerFolder = Qubit_Parameters[str(Qubit_Readout)]['outerfoldername']

    # yoko current source
    if use_yoko:
        rm = pyvisa.ResourceManager()
        yoko = rm.open_resource(yoko_addr)
        yoko.write(":SOUR:FUNC VOLT")
        yoko.write(":OUTP ON")
        ramp_to(yoko, start_voltage)
    else:
        # No charge line this session: virtual level starts at start_voltage so the
        # setup ramp below is a no-op rather than a refused move.
        yoko = NullYoko(start_voltage)

    # derived scalars for the selected readout/pulse qubit
    cavity_gain = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Gain']
    resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Frequency']
    qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain']
    pi2_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['pi2_Gain']
    qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency']
    qubit_sigma = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['sigma']
    qubit_flattop = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['flattop_length']

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
    print(f"[readout window] integration {readout_length_us} us, "
          f"adc_trig_offset {adc_trig_offset_us} us, "
          f"resonator tone {adc_trig_offset_us + readout_length_us} us")
    trans_config = {
        "reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
        "pulse_style": "const",  # --Fixed
        # "length" is the resonator tone duration; "readout_length" is the ADC
        # integration window. Since the ADC starts after adc_trig_offset, the tone
        # must last through offset + window rather than merely equal the window.
        "length": adc_trig_offset_us + readout_length_us,
        "readout_length": readout_length_us,
        # written explicitly (not left to BaseConfig) so a runner-side
        # adc_trig_offset_us override actually reaches the programs
        "adc_trig_offset": adc_trig_offset_us,
        "pulse_gain": cavity_gain,  # [DAC units]
        "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
        "TransSpan": Transmission_params['span'],  ### 0.75 MHz, span will be center+/- this parameter
        "TransNumPoints": Transmission_params['num_points'],  ### number of points in the transmission frequecny
        "cav_relax_delay": 30
    }
    qubit_config = {
        "qubit_pulse_style": "const",
        "qubit_gain": Spec_relevant_params["qubit_gain"],
        "qubit_freq": qubit_frequency_center,
        "qubit_length": Spec_relevant_params["qubit_length"],  # 20, 100 # 10 was the best for Q4
        "SpecSpan": Spec_relevant_params["SpecSpan"],  ### MHz, span will be center+/- this parameter
        "SpecNumPoints": Spec_relevant_params["SpecNumPoints"],  ### number of points in the transmission frequecny
        "current_voltage": start_voltage
    }
    expt_cfg = {
        "step": 2 * qubit_config["SpecSpan"] / qubit_config["SpecNumPoints"],
        "start": qubit_config["qubit_freq"] - qubit_config["SpecSpan"],
        "expts": qubit_config["SpecNumPoints"]
    }

    UpdateConfig = trans_config | qubit_config | expt_cfg | tl | ts | charge_params
    config = BaseConfig | UpdateConfig  ### note that UpdateConfig will overwrite elements in BaseConfig
    print(config)
    config["FF_Qubits"] = FF_Qubits
    config["cavity_min"] = cavity_min  # look for dip, not peak

    return Context(
        soc=soc, soccfg=soccfg, yoko=yoko, has_yoko=use_yoko,
        config=config, outerFolder=outerFolder,
        Qubit_Readout=Qubit_Readout, Qubit_Pulse=Qubit_Pulse,
        Qubit_Parameters=Qubit_Parameters,
        start_voltage=start_voltage, yoko_fixed=yoko_fixed, cavity_min=cavity_min,
        cavity_gain=cavity_gain, resonator_frequency_center=resonator_frequency_center,
        qubit_gain=qubit_gain, pi2_gain=pi2_gain,
        qubit_frequency_center=qubit_frequency_center,
        qubit_sigma=qubit_sigma, qubit_flattop=qubit_flattop,
    )
