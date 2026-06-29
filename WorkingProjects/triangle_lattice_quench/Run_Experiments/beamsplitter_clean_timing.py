'''Beamsplitter "clean timing" calibration + execution script.

Runs a multi-qubit fast-flux (FF) beamsplitter pulse where every qubit's
FF channel arrives at the beamsplitter setpoint simultaneously.  "Clean
timing" refers to the per-qubit `t_offset[j]` array that compensates
physical channel-to-channel skew on the FF lines so that, despite
different cable delays / DAC start times, all eight FF channels align
in time at the BS pulse.

Sequence each shot:
    init pi-pulses (FF held at Gain_Pulse)
        ↓
    compensated ramp (Gain_Pulse → Gain_Expt over `ramp_time` samples)
        ↓
    BS window (per qubit j, in samples of 4.65/16 ns):
        t_offset[j]          @ Gain_Expt         (alignment pad)
        intermediate_jump_samples[j]
                             @ intermediate_jump_gains[j]   (double-jump only)
        bs_samples[j]        @ Gain_BS           (the swap)
        readout_pad          @ Gain_Readout      (settle before readout)
        ↓
    MUX readout

`bs_samples` defaults to `pad_bs` from the JSON dynamics entry; per-qubit
extra "holding" samples at Gain_BS for qubits that don't reach a swap
partner during the swap window (keeps FF timing aligned across the row).

Double-jump vs single-jump:
    `intermediate_jump_gains[j] == None`  →  no intermediate jump on qubit j.
    Otherwise the FF parks at `intermediate_jump_gains[j]` for
    `intermediate_jump_samples[j]` samples before stepping to Gain_BS.
    BSClean.init_sweep_vars patches `None` slots to Gain_BS and zeros their
    intermediate_jump_samples so the math degenerates cleanly.

File layout:
    1. Hardware setup + base cfg construction (build_config + characterize_readout).
    2. `double_jump_base`: shared parameters used by every variant below.
    3. Per-sweep blocks — each is a `Sweep_<Foo> = bool` flag plus the
       parameter dict it would feed into the corresponding experiment class:
          - BeamsplitterOffset:   scan FF arrival timing of one qubit.
          - BeamsplitterGain:     scan one qubit's BS gain.
          - IntermediateSamples:  scan intermediate-jump duration.
          - IntermediateGain:     scan intermediate-jump gain.
          - DoubleJump1D:         1D BS-time trace (no extra sweep axis).
          - DoubleJump_CurrentCorrelations:
                                  1D BS-time trace + current-correlation
                                  analysis on two readout pairs.
       Each sweep has a Python-side variant (default) and a `_tprocSweep`
       variant that runs the sweep loop on the QICK tProc — same physics,
       much faster for many points but more rigid configuration.
    4. Dispatch block at the bottom runs whichever flags are True.

    - Joshua 11/29/25
'''

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
# BS experiment classes: Python-side outer-loop sweeps over BS parameters.
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.mBSDoubleJump_CleanTiming import \
    BSClean_Correlations, BSClean_offset, BSClean_BSGain, BSClean_ISamples, BSClean_IGain, BSClean1D
# tProc-side sweep equivalents (faster, less flexible).
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.mRampCurrentCalibrationR_SSMUX import \
    RampBeamsplitterOffsetR, RampBeamsplitterGainR, RampDoubleJumpGainR, RampDoubleJumpIntermediateSamplesR

# from WorkingProjects.triangle_lattice_quench.Flux_Files.Initialize_Qubit_Information import model_mapping
# print(1000 * model_mapping['Q2_bare'].freq(0))  # model's upper sweetspot freq, MHz
#19 rungs total

from WorkingProjects.triangle_lattice_quench.build_config import build_config
from Calibrate_muxed_readouts import characterize_readout
from WorkingProjects.triangle_lattice_quench.MUXInitialize import outerFolder
from WorkingProjects.triangle_lattice_quench.socProxy import makeProxy
soc, soccfg = makeProxy()

# ---------------------------------------------------------------------------
# Qubit selection + JSON resolver
# ---------------------------------------------------------------------------
# Qubit_Readout — qubits that are MUX-read out (one entry per ADC slot).
# Qubit_Pulse   — drive entries (drive_groups[<dg>].entries) that fire init
#                 pi-pulses, in order. Each label resolves to a freq/gain/
#                 sigma triple in JSON; the program plays them sequentially.
# Ramp_State    — key in ramp_groups; defines Gain_RampInit / Gain_Expt
#                 (FF endpoints of the cubic-compensated ramp segment).
# Dynamics_Point — key in dynamics_groups; defines Gain_BS / Gain_Dynamics
#                 (BS-window FF) plus t_offset / ij_samples / ij_gains /
#                 pad_bs / exact_t_bs, all promoted to cfg by build_config.
Qubit_Readout = [3,4,5,6,7,8]
Qubit_Pulse = ['4_4Q_readout', '8_4Q_readout', '5_4Q_readout']
Ramp_State = "5Q_highest_6_low"
Dynamics_Point = "resonant"

# Q — single-qubit target for the "swept_qubit" knob in every per-qubit
# sweep dict below (BS offset / BS gain / intermediate sweeps focus on
# Q while the other qubits run at their fixed cfg values).
Q = 1

config = build_config(Qubit_Readout=Qubit_Readout, Qubit_Pulse=Qubit_Pulse,
                      Ramp_State=Ramp_State, Dynamics_Point=Dynamics_Point)
# Characterize each readout in this MUX configuration to get fresh
# angle / threshold / confusion_matrix lists; merged into cfg so the
# experiment's population correction matches today's readout state.
# config |= characterize_readout(Qubit_Readout, soc=soc, soccfg=soccfg)

# ---------------------------------------------------------------------------
# Shared experiment parameters (used by every variant below)
# ---------------------------------------------------------------------------
# t_offset[j], ij_samples[j], ij_gains[j], pad_bs[j] all come from the
# Dynamics_Point JSON entry (build_config promotes them). Defaults below
# kick in only when the entry is missing one of those keys.
double_jump_base = {'reps': 400, 'ramp_time': 1000,
                    't_offset':
                    # [0] * 8,
                    # [22, 24, 13, 24, 8, 8, 9, 0],
                        config.get('t_offset', [0]*8),
                    'relax_delay': 180,
                    'start': 0, 'step': 8, 'expts': 71,
                    'intermediate_jump_samples': config.get('ij_samples',[None]*8),
                    'intermediate_jump_gains':   config.get('ij_gains',[None]*8),
                    'bs_samples': config.get('pad_bs',[0]*8),
                    }
print(double_jump_base['intermediate_jump_gains'])
print(double_jump_base['intermediate_jump_samples'])
# 'pad_bs' accounts for the intermediate jump samples where a qubit does not get to swap with its partner

# ---------------------------------------------------------------------------
# Sweep 1: per-qubit Beamsplitter timing offset
# ---------------------------------------------------------------------------
# Scan `t_offset[Q-1]` (one qubit's FF-channel timing) around its current
# value to find the t_offset that maximises swap fidelity. "Good" offsets
# observed on this device historically:
# "good" offsets = [22, 24, 13, 24, 8, 8, 9, 0]
Sweep_BeamsplitterOffset = False
Sweep_BeamsplitterOffset_tprocSweep = False
sweep_bs_offset_dict = {'swept_qubit': Q, 'reps': 2000, 'offsetStep': 1,
                        # During an offset sweep we want a single-jump BS
                        # (no double-jump confound), so kill intermediate
                        # jumps and pad_bs for every qubit.
                        'intermediate_jump_samples': [0]*8,
                        'bs_samples':[0]*8,

                        'offsetStart': config['t_offset'][Q-1]-2*15,
                        'offsetStop': config['t_offset'][Q-1]+2*15,
                        'start': 0, 'step': 4, 'expts': 162}

# sweep_bs_offset_dict = {'swept_qubit': Q, 'reps': 1600, 'offsetStep': 1,
#                         'intermediate_jump_samples': [0] * 8,
#                         'bs_samples': [0] * 8,
#
#                         'offsetStart': Qubit_Parameters[beamsplitter_point]['t_offset'][Q - 1] - 30,
#                         'offsetStop': Qubit_Parameters[beamsplitter_point]['t_offset'][Q - 1] + 30,
#                         'start': 0, 'step': 1, 'expts': 71}

# ---------------------------------------------------------------------------
# Sweep 2: per-qubit Beamsplitter gain
# ---------------------------------------------------------------------------
# Scan `FF_Qubits[Q]['Gain_BS']` to find the gain that drives the cleanest
# π/2 swap (or whatever angle the experiment is targeting). Other qubits
# stay at their cfg Gain_BS.
Sweep_BeamsplitterGain = False
Sweep_BeamsplitterGain_tprocSweep = False
sweep_bs_gain_dict = {'swept_qubit': Q, 'gainNumPoints': 11,
                      # 't_offset':[0,0,0,0,0,3,0,0],
                      # 't_offset': [2, 1, 6, 6, 8, -1, 1, -2],
                      # 'intermediate_jump_samples': [0] * 8,
                      # 'bs_samples': [0] * 8,
                            'gainStart':  config['FF_Qubits'][str(Q)]['Gain_BS'] - 1000,
                            'gainStop': config['FF_Qubits'][str(Q)]['Gain_BS'] + 1000,
                      'start':40}


# ---------------------------------------------------------------------------
# Sweep 3: intermediate-jump duration (double-jump calibration)
# ---------------------------------------------------------------------------
# Scan `intermediate_jump_samples[Q-1]` — how long qubit Q parks at the
# intermediate FF setpoint before jumping to Gain_BS. Only meaningful
# when `intermediate_jump_gains[Q-1]` is set (i.e. this qubit is in the
# double-jump branch).
Sweep_IntermediateSamples = False
Sweep_IntermediateSamples_tprocSweep = False
sweep_intermediate_samples_dict = {'swept_qubit': Q, 'samples_step': 1,
                                   'samples_start': 0, 'samples_stop': 6,}


# ---------------------------------------------------------------------------
# Sweep 4: intermediate-jump gain
# ---------------------------------------------------------------------------
# Scan `intermediate_jump_gains[Q-1]` around its current value. If
# IJGains[Q-1] is None (single-jump qubit), the `IJGains[Q-1] - 15000`
# arithmetic raises and the bare except leaves
# `double_jump_intermediate_gain_dict` undefined — enabling
# `Sweep_IntermediateGain` in that state will NameError downstream.
Sweep_IntermediateGain = False
Sweep_IntermediateGain_tprocSweep = False
IJGains = double_jump_base['intermediate_jump_gains']
print(IJGains[Q-1])
try:
    double_jump_intermediate_gain_dict = {'swept_qubit': Q, 'reps': 2000,
                        'gainStart': IJGains[Q-1] - 15000,
                        'gainStop':  IJGains[Q-1] + 15000,
                         'gainNumPoints': 11}
except:
    pass

# ---------------------------------------------------------------------------
# 1D run: full BS-time trace (no extra sweep axis)
# ---------------------------------------------------------------------------
# DoubleJump1D            : just plot population vs BS time.
# DoubleJump_CurrentCorrelations : same trace, plus current-correlation
#                                 analysis on two readout pairs (see
#                                 readout_pair_1 / readout_pair_2). Needs
#                                 MUX size >= 4.
#
# SinglePoint mode: instead of scanning BS time, hold each qubit at its
# own `exact_t_bs` (from the JSON dynamics entry) for a high-statistics
# single-point measurement — useful once timings are calibrated and you
# want a clean shot count at the operating point.
DoubleJump1D = False
DoubleJump_CurrentCorrelations = False
# Time trace or single point
# SinglePoint = (Q == 3) or (Q == 6)
SinglePoint = False

if not SinglePoint:
    # Standard 1D scan: BS time from 0 to (start + step * expts - 1) samples.
    double_jump_1d_dict = {'reps': 50_000,
                            'start': 0, 'step': 8, 'expts': 1000,
                           'readout_pair_1': [int(s) for s in '34'],
                           'readout_pair_2': [int(s) for s in '34'],
                        }
elif SinglePoint:
    # Single-point operating mode: per-qubit `exact_t_bs` (with pad_bs)
    # becomes the BS window; `expts=1` runs just that one point with very
    # high reps for tight statistics.
    double_jump_1d_dict = {'reps': 4_000_000,
                           'start': Q, 'step': 1, 'expts': 1,
                           'readout_pair_1': [int(s) for s in '12'],
                           'readout_pair_2': [int(s) for s in '12'],
                           'bs_samples': np.array(config['exact_t_bs']) + config.get('pad_bs',[0]*8),
                           'exact_t_bs': config['exact_t_bs']}

# This ends the working section of the file.
#----------------------------------------

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
# Note: the per-sweep blocks below reference `beamsplitter_point` and
# `rung` in their f-string prefixes — those variables are not currently
# defined in this file (likely left over from an earlier version). The
# DoubleJump1D and DoubleJump_CurrentCorrelations blocks don't reference
# them, so they're the only safe paths to enable as-is. Flipping any
# Sweep_* flag will NameError until those tags are restored.
config = config | double_jump_base

if Sweep_BeamsplitterOffset:
    BSClean_offset(path="BSClean_offset", outerFolder=outerFolder, prefix = f'{beamsplitter_point}_{rung}',
                          cfg=config | sweep_bs_offset_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)

if Sweep_BeamsplitterOffset_tprocSweep:
    RampBeamsplitterOffsetR(path="RampBeamsplitterOffsetR", outerFolder=outerFolder, prefix = f'{beamsplitter_point}_{rung}',
                            cfg=config | sweep_bs_offset_dict, soc=soc, soccfg=soccfg).acquire_display_save(
        plotDisp=True, block=False)


if Sweep_BeamsplitterGain:
    BSClean_BSGain(path="BSClean_BSGain", outerFolder=outerFolder, prefix = f'{beamsplitter_point}_{rung}',
                          cfg=config | sweep_bs_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)
if Sweep_BeamsplitterGain_tprocSweep:
    RampBeamsplitterGainR(path="RampBeamsplitterGainR", outerFolder=outerFolder, prefix = f'{beamsplitter_point}_{rung}',
                            cfg=config | sweep_bs_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(
        plotDisp=True, block=False)

if Sweep_IntermediateSamples:
    BSClean_ISamples(path="BSClean_ISamples", outerFolder=outerFolder, prefix = f'{beamsplitter_point}_{rung}',
                          cfg=config | double_jump_base | sweep_intermediate_samples_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)
if Sweep_IntermediateSamples_tprocSweep:
    RampDoubleJumpIntermediateSamplesR(path="RampDoubleJumpIntermediateLength", outerFolder=outerFolder,
                                       cfg=config | double_jump_base | sweep_intermediate_samples_dict, soc=soc,
                                       soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)

if Sweep_IntermediateGain:
    BSClean_IGain(path="BSClean_IGain", outerFolder=outerFolder, prefix = f'{beamsplitter_point}_{rung}',
                        cfg=config | double_jump_base | double_jump_intermediate_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)
if Sweep_IntermediateGain_tprocSweep:
    RampDoubleJumpGainR(path="RampDoubleJumpGainR", outerFolder=outerFolder,
                        cfg=config | double_jump_base | double_jump_intermediate_gain_dict, soc=soc,
                        soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)

if DoubleJump1D:
    print("conf_mat type:", type(config.get('confusion_matrix')))
    print("conf_mat len:", len(config.get('confusion_matrix', [])))
    BSClean1D(path="BSClean", outerFolder=outerFolder,
                      cfg=config | double_jump_base | double_jump_1d_dict, soc=soc, soccfg=soccfg,).acquire_display_save(plotDisp=True, block=False)

if DoubleJump_CurrentCorrelations:
    print("conf_mat type:", type(config.get('confusion_matrix')))
    print("conf_mat len:", len(config.get('confusion_matrix', [])))
    print(config.get('confusion_matrix', []))
    BSClean_Correlations(path="BSClean_Correlations", outerFolder=outerFolder,
                      cfg=config | double_jump_base | double_jump_1d_dict, soc=soc, soccfg=soccfg,).acquire_display(plotDisp=True, block=False)
print(config)

plt.show()
