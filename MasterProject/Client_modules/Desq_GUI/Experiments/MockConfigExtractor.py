"""
MockConfigExtractor.py - Comprehensive mock experiment runner for GUI testing

This module mimics the pattern of real experiment runner scripts like:
- SingleShot_Experiments.py
- RampBeamsplitter_Correlations.py  
- CurrentCalibration_SSMUX.py

It uses MockExperiments instead of real hardware experiments, allowing GUI
testing without RFSoC hardware. The config extraction pattern matches real
scripts so ExperimentLoader and ConfigCodeEditor work correctly.

Usage in Desq GUI:
    1. Load this file as an experiment file
    2. ExperimentLoader will discover all experiment classes
    3. ConfigTreePanel will display the config hierarchy
    4. ConfigCodeEditor will show the runnable script with booleans

Pattern Elements Mimicked:
    - Import statements at top (experiment classes, parameter files)
    - Qubit_Readout and Qubit_Pulse lists
    - Boolean flags controlling which experiments run
    - Parameter dictionaries with nested merging (config | params)
    - exec() calls to UPDATE_CONFIG and CALIBRATE_SINGLESHOT
    - Final experiment instantiation and acquire_display_save() calls
"""

# =============================================================================
# IMPORTS - Mimicking real experiment script imports
# =============================================================================

# Mock versions of the "real" imports that would fail without hardware
# In real scripts these would be:
#   from WorkingProjects.Triangle_Lattice.Experiments.mT1MUX import T1MUX
#   from WorkingProjects.Triangle_Lattice.Experiments.mT2RMUX import T2RMUX
#   etc.

from MasterProject.Client_modules.Desq_GUI.Experiments.MockExperiments import (
    MockT1Experiment,
    MockT2RamseyExperiment,
    MockSpectroscopyExperiment,
    MockAmplitudeRabiExperiment,
    MockSpec2DExperiment,
    MockSingleShotExperiment,
    MockTransmissionExperiment,
    MockMUXSpectroscopyExperiment,
    MockCorrelationExperiment,
    MockPulseVisualizationExperiment,
    MockPopulationSweepExperiment,
)

from MasterProject.Client_modules.Desq_GUI.Experiments.MockExperimentsAdv import (
    MockGrid1x1,
    MockGrid1x2,
    MockGrid2x1,
    MockGrid2x2,
    MockGrid2x3,
    MockGrid3x3,
    MockGridSpec,
    MockMultiFigure2,
    MockMultiFigure3,
    MockLivePlot1D,
    MockLivePlot2D,
)

import numpy as np

# =============================================================================
# QUBIT PARAMETERS - Mimicking qubit_parameter_files imports
# =============================================================================

# In real scripts: from qubit_parameter_files.Qubit_Parameters_Master import *

# Mock qubit frequencies (MHz)
Qubit_Frequencies = {
    1: 4150.0,
    2: 4225.0,
    3: 4310.0,
    4: 4180.0,
    5: 4275.0,
    6: 4350.0,
    7: 4420.0,
    8: 4500.0,
}

# Mock readout frequencies (MHz)
Readout_Frequencies = {
    1: 7150.0,
    2: 7225.0,
    3: 7300.0,
    4: 7375.0,
    5: 7450.0,
    6: 7525.0,
    7: 7600.0,
    8: 7675.0,
}

# Mock fast-flux (FF) gains for each qubit
Expt_FF = [-26000, -28000, -25000, -27000, -25500, -28500, -26500, -24000]
BS_FF = [-15000, -16000, -14500, -15500, -16500, -17000, -15000, -14000]
Readout_FF = [-26873, -29001, -25392, -27560, 2500, -28060, -25722, -24395]

# Mock qubit parameters dictionary (mimics Qubit_Parameters_Master structure)
Qubit_Parameters = {
    '1': {
        'Readout': {'Frequency': 7150.0, 'Gain': 1200, 'FF_Gains': Readout_FF,
                    'Readout_Time': 3, 'ADC_Offset': 1},
        'Qubit': {'Frequency': 4150.0, 'sigma': 0.03, 'Gain': 8000},
        'Pulse_FF': Expt_FF,
    },
    '2': {
        'Readout': {'Frequency': 7225.0, 'Gain': 1100, 'FF_Gains': Readout_FF,
                    'Readout_Time': 3, 'ADC_Offset': 1},
        'Qubit': {'Frequency': 4225.0, 'sigma': 0.03, 'Gain': 7500},
        'Pulse_FF': Expt_FF,
    },
    '3': {
        'Readout': {'Frequency': 7300.0, 'Gain': 1050, 'FF_Gains': Readout_FF,
                    'Readout_Time': 3, 'ADC_Offset': 1},
        'Qubit': {'Frequency': 4310.0, 'sigma': 0.03, 'Gain': 8200},
        'Pulse_FF': Expt_FF,
    },
    '4': {
        'Readout': {'Frequency': 7375.0, 'Gain': 1150, 'FF_Gains': Readout_FF,
                    'Readout_Time': 3, 'ADC_Offset': 1},
        'Qubit': {'Frequency': 4180.0, 'sigma': 0.03, 'Gain': 7800},
        'Pulse_FF': Expt_FF,
    },
    '5': {
        'Readout': {'Frequency': 7450.0, 'Gain': 1057, 'FF_Gains': Readout_FF,
                    'Readout_Time': 3, 'ADC_Offset': 1},
        'Qubit': {'Frequency': 4275.0, 'sigma': 0.03, 'Gain': 7001},
        'Pulse_FF': Expt_FF,
    },
    '6': {
        'Readout': {'Frequency': 7525.0, 'Gain': 1080, 'FF_Gains': Readout_FF,
                    'Readout_Time': 3, 'ADC_Offset': 1},
        'Qubit': {'Frequency': 4350.0, 'sigma': 0.03, 'Gain': 8100},
        'Pulse_FF': Expt_FF,
    },
    '7': {
        'Readout': {'Frequency': 7600.0, 'Gain': 1020, 'FF_Gains': Readout_FF,
                    'Readout_Time': 3, 'ADC_Offset': 1},
        'Qubit': {'Frequency': 4420.0, 'sigma': 0.03, 'Gain': 7600},
        'Pulse_FF': Expt_FF,
    },
    '8': {
        'Readout': {'Frequency': 7675.0, 'Gain': 1100, 'FF_Gains': Readout_FF,
                    'Readout_Time': 3, 'ADC_Offset': 1},
        'Qubit': {'Frequency': 4500.0, 'sigma': 0.03, 'Gain': 7900},
        'Pulse_FF': Expt_FF,
    },
}

# Beamsplitter timing offsets
beamsplitter_point = 'BS_4Q'
Qubit_Parameters['BS_4Q'] = {'t_offset': [22, 24, 13, 24, 8, 8, 9, 0]}

# Intermediate jump parameters
ijump_point = 'IJ_4Q'
Qubit_Parameters['IJ_4Q'] = {
    'IJ': {
        'samples': [15, 15, 15, 15, 15, 15, 15, 15],
        'gains': [-12000, -13000, -11500, -12500, -13500, -14000, -12000, -11000],
    }
}

# =============================================================================
# QUBIT SELECTION - Which qubits to use
# =============================================================================

Qubit_Readout = [1, 2, 3, 4, 5, 6, 7, 8]
Qubit_Pulse = [5]

# Alternative configurations (commented out as in real scripts)
# Qubit_Readout = [5]
# Qubit_Pulse = ['1_4Q_readout', '4_4Q_readout', '8_4Q_readout', '5_4Q_readout']

# =============================================================================
# BASE CONFIG - Hardware and system parameters
# =============================================================================

# This would normally come from BaseConfig import
BaseConfig = {
    'res_LO': 7000.0,  # Resonator LO frequency (MHz)
    'qubit_LO': 4000.0,  # Qubit LO frequency (MHz)
    'nqz_res': 2,  # Nyquist zone for resonator
    'nqz_qubit': 2,  # Nyquist zone for qubit
    'ro_chs': [0, 1, 2, 3, 4, 5, 6, 7],  # Readout channels
    'qubit_chs': [8, 9, 10, 11, 12, 13, 14, 15],  # Qubit drive channels
    'ff_chs': [0, 1, 2, 3, 4, 5, 6, 7],  # Fast-flux channels
    'adc_trig_offset': 0.5,
    'relax_delay': 200,  # us
}

# Build the config dictionary (mimics UPDATE_CONFIG.py pattern)
config = {
    # Hardware config
    **BaseConfig,

    # Qubit selection
    'Qubit_Readout_List': Qubit_Readout,
    'Qubit_Pulse_List': Qubit_Pulse,

    # Frequencies from qubit parameters
    'res_freqs': [Qubit_Parameters[str(q)]['Readout']['Frequency'] - BaseConfig['res_LO']
                  for q in Qubit_Readout],
    'qubit_freqs': [Qubit_Parameters[str(q)]['Qubit']['Frequency'] - BaseConfig['qubit_LO']
                    for q in Qubit_Pulse if str(q).split('_')[0].isdigit()],

    # Gains
    'res_gains': [Qubit_Parameters[str(q)]['Readout']['Gain'] for q in Qubit_Readout],
    'qubit_gains': [Qubit_Parameters[str(q)]['Qubit']['Gain']
                    for q in Qubit_Pulse if str(q).split('_')[0].isdigit()],

    # FF gains
    'FF_Qubits': Expt_FF,
    'FF_BS': BS_FF,
    'FF_Readout': Readout_FF,
}

# =============================================================================
# BOOLEAN FLAGS - Control which experiments run
# =============================================================================

# Convenience aliases
t = True
f = False

# ------ Basic Characterization ------
RunTransmissionSweep = False
Run2ToneSpec = False
RunAmplitudeRabi = False
SingleShot = False
SingleShotDecimate = False

# ------ T1/T2 Measurements ------
RunT1 = True  # <-- One experiment enabled for testing
RunT2 = False
RunT1_TLS = False

# ------ Optimization Sweeps ------
SingleShot_ReadoutOptimize = False
SingleShot_QubitOptimize = False
SingleShot_SNROptimize = False

# ------ 2D Sweeps ------
Run_Spec_vs_FFgain = False
Run_FF_v_Ramsey = False
FluxStability = False
Run_Spec_vs_Qblox = False

# ------ Oscillations ------
Oscillation_Gain = False
Oscillation_Single = False
Oscillation_Gain_QICK_sweep = False

# ------ Timing Calibration ------
Calib_FF_vs_drive_delay = False

# ------ Multi-Qubit ------
SingleShot_2Qubit = False

# ------ Beamsplitter / Correlations ------
Sweep_BeamsplitterGain = False
Sweep_BeamsplitterOffset = False
Beamsplitter1D = False
Run_CurrentCorrelations = False

# ------ Advanced Grid Tests ------
RunGridTests = False
RunMultiFigureTests = False
RunLivePlotTests = False

# =============================================================================
# EXPERIMENT PARAMETER DICTIONARIES
# =============================================================================

# ------ Transmission ------
Trans_relevant_params = {
    "reps": 200,
    "TransSpan": 1.5,
    "TransNumPoints": 61,
    "readout_length": 3,
    'cav_relax_delay': 10,
}

# ------ Spectroscopy ------
Spec_relevant_params = {
    'Gauss': True,
    "sigma": 0.015,
    "Gauss_gain": 11000,
    "qubit_gain": 400,
    "SpecSpan": 200,
    "SpecNumPoints": 71,
    'reps': 200,
    'rounds': 1,
}

# ------ Amplitude Rabi ------
Amplitude_Rabi_params = {
    "max_gain": 24000,
    'relax_delay': 100,
}

# ------ Single Shot ------
SS_params = {
    "Shots": 2000,
    'number_of_pulses': 1,
    'relax_delay': 200,
}

# ------ T1 ------
T1_params = {
    "stop_delay_us": 100,
    "expts": 40,
    "reps": 150,
    "T1_true": 25.0,  # Mock parameter for simulation
    "noise_level": 0.05,
}

# ------ T2 Ramsey ------
T2R_params = {
    "stop_delay_us": 60,
    "expts": 101,
    "reps": 300,
    "freq_shift": 0.0,
    "phase_shift_cycles": -3,
    "relax_delay": 150,
    "T2_true": 15.0,  # Mock parameter
    "freq_detuning": 0.5,
    "noise_level": 0.08,
}

# ------ T1 vs TLS (FF sweep) ------
T1TLS_params = {
    "FF_gain_start": -20000,
    "FF_gain_stop": -8000,
    "FF_gain_steps": 101,
    "stop_delay_us": 10,
    "expts": 5,
    "reps": 300,
    'qubitIndex': int(str(Qubit_Pulse[0])[0]) if str(Qubit_Pulse[0])[0].isdigit() else 1,
}

# ------ Spec vs FF ------
Q = 5  # Selected qubit for sweeps
FF_sweep_spec_relevant_params = {
    "qubit_FF_index": Q,
    "FF_gain_start": Expt_FF[Q - 1] - 6000,
    "FF_gain_stop": Expt_FF[Q - 1] + 6000,
    "FF_gain_steps": 11,
    'relax_delay': 100,
}

# ------ Ramsey vs FF ------
FF_sweep_Ramsey_relevant_params = {
    "stop_delay_us": 4,
    "expts": 61,
    "reps": 200,
    "qubit_FF_index": int(str(Qubit_Readout[0])[0]) if str(Qubit_Readout[0])[0].isdigit() else 1,
    "FF_gain_start": Expt_FF[0] - 100,
    "FF_gain_stop": Expt_FF[0] + 100,
    "FF_gain_steps": 11,
    "relax_delay": 100,
    'populations': True,
}

# ------ Flux Stability ------
Flux_Stability_params = {
    "delay_minutes": 1 / 60,
    "num_steps": 3600,
}

# ------ Readout Optimize ------
SS_R_params = {
    "Shots": 500,
    "gain_start": 2000,
    "gain_stop": 8000,
    "gain_pts": 8,
    "span": 1,
    "trans_pts": 6,
    'number_of_pulses': 1,
}

# ------ Qubit Optimize ------
SS_Q_params = {
    "Shots": 500,
    "q_gain_span": 8000,
    "q_gain_pts": 7,
    "q_freq_span": 6.0,
    "q_freq_pts": 7,
    'number_of_pulses': 1,
    'qubit_sweep_index': -1,
}

# ------ SNR Optimize ------
SNR_params = {
    'Shots': 1000,
    'gain_start': -2,
    'gain_stop': 0.5,
    'gain_pts': 10,
    'freq_start': 7800,
    'freq_stop': 8000,
    'freq_pts': 10,
    'number_of_pulses': 1,
}

# ------ Oscillation Gain Sweep ------
oscillation_gain_dict = {
    'qubit_FF_index': 6,
    'reps': 1000,
    'start': 0,
    'step': 4,
    'expts': 141,
    'gainStart': -9500,
    'gainStop': -8500,
    'gainNumPoints': 9,
    'relax_delay': 200,
    'fit': True,
}

# ------ FF vs Drive Timing ------
ff_drive_delay_dict = {
    'start': 200,
    'step': 8,
    'expts': 200,
    'qubit_delay_cycles': 80,
    'reps': 4000,
    'qubit_index': Qubit_Pulse[0],
}

# ------ 2-Qubit Single Shot ------
SS_2Q_params = {
    "Shots": 2500,
    'number_of_pulses': 1,
    'relax_delay': 300,
    'second_qubit_freq': 4271.5,
    'second_qubit_gain': 8000,
}

# ------ Beamsplitter Gain Sweep ------
sweep_bs_gain_dict = {
    'swept_qubit': Q,
    'reps': 200,
    'ramp_time': 1000,
    't_offset': Qubit_Parameters[beamsplitter_point]['t_offset'],
    'relax_delay': 120,
    'gainStart': BS_FF[Q - 1] - 1000,
    'gainStop': BS_FF[Q - 1] + 1000,
    'gainNumPoints': 11,
    'start': 50,
    'step': 8,
    'expts': 71,
}

# ------ Beamsplitter Offset Sweep ------
sweep_bs_offset_dict = {
    'swept_qubit': Q,
    'reps': 5000,
    'ramp_time': 1000,
    't_offset': Qubit_Parameters[beamsplitter_point]['t_offset'],
    'relax_delay': 180,
    'offsetStart': 10,
    'offsetStop': 30,
    'offsetStep': 1,
    'start': 0,
    'step': 12,
    'expts': 71,
}

# ------ 1D Beamsplitter / Correlations ------
ramp_beamsplitter_1d_dict = {
    'reps': 10000,
    'ramp_time': 1000,
    't_offset': Qubit_Parameters[beamsplitter_point]['t_offset'],
    'relax_delay': 180,
    'start': 0,
    'step': 8,
    'expts': 71,
    'readout_pair_1': [2, 3],
    'readout_pair_2': [4, 5],
}

# ------ Double Jump Base ------
double_jump_base = {
    'reps': 400,
    'ramp_time': 1000,
    't_offset': Qubit_Parameters[beamsplitter_point]['t_offset'],
    'relax_delay': 180,
    'start': 0,
    'step': 16,
    'expts': 71,
    'intermediate_jump_samples': Qubit_Parameters[ijump_point]['IJ']['samples'],
    'intermediate_jump_gains': Qubit_Parameters[ijump_point]['IJ']['gains'],
}


# =============================================================================
# MOCK "UPDATE_CONFIG" - Would normally be exec(open("UPDATE_CONFIG.py").read())
# =============================================================================

# In real scripts, this translates Qubit_Parameters to config entries
# Here we just ensure config has all necessary fields

def update_config():
    """Simulate UPDATE_CONFIG.py behavior."""
    global config

    # Update qubit frequencies if Qubit_Pulse changed
    valid_qubits = [q for q in Qubit_Pulse if str(q).split('_')[0].isdigit()]
    if valid_qubits:
        config['qubit_freqs'] = [
            Qubit_Parameters[str(q).split('_')[0]]['Qubit']['Frequency'] - BaseConfig['qubit_LO']
            for q in valid_qubits
        ]
        config['qubit_gains'] = [
            Qubit_Parameters[str(q).split('_')[0]]['Qubit']['Gain']
            for q in valid_qubits
        ]

    # Update readout frequencies
    config['res_freqs'] = [
        Qubit_Parameters[str(q)]['Readout']['Frequency'] - BaseConfig['res_LO']
        for q in Qubit_Readout
    ]

    config['Qubit_Readout_List'] = Qubit_Readout
    config['Qubit_Pulse_List'] = Qubit_Pulse


# Run the mock update
update_config()


# =============================================================================
# MOCK "CALIBRATE_SINGLESHOT" - Would be exec(open("CALIBRATE_SINGLESHOT_READOUTS.py").read())
# =============================================================================

def calibrate_singleshot_readouts():
    """
    Simulate single-shot calibration.

    In real scripts, this would:
    1. Run single-shot measurements
    2. Compute IQ thresholds
    3. Update config with calibration data
    """
    config['singleshot_calibrated'] = True
    config['iq_thresholds'] = {q: {'I': 0.0, 'Q': 0.0, 'angle': 0.0}
                               for q in Qubit_Readout}


# Calibration would be called before experiments that need populations
# (commented out as in real scripts until needed)
# calibrate_singleshot_readouts()

# =============================================================================
# MOCK HARDWARE OBJECTS - soc, soccfg, outerFolder
# =============================================================================

# In real scripts these come from MUXInitialize or similar
soc = None  # Would be RFSoC proxy
soccfg = None  # Would be RFSoC configuration
outerFolder = "/tmp/MockExperiments"  # Data save location

# =============================================================================
# EXPERIMENT EXECUTION - Conditional running based on boolean flags
# =============================================================================

# This section mimics the structure of real experiment scripts.
# When loaded by ExperimentLoader, only the class definitions are extracted.
# When run directly (or via exec in GUI), experiments execute.

if __name__ == "__main__" or 'experiment_runner_active' in dir():
    # Note: In GUI context, experiments are instantiated individually by the user
    # This section runs when the script is executed directly

    import matplotlib.pyplot as plt

    print("=" * 60)
    print("Mock Config Extractor - Running Enabled Experiments")
    print("=" * 60)
    print(f"Qubit Readout: {Qubit_Readout}")
    print(f"Qubit Pulse: {Qubit_Pulse}")
    print()

    # ------ Basic Characterization ------

    if RunTransmissionSweep:
        print("Running MockTransmissionExperiment...")
        exp = MockTransmissionExperiment(
            path="TransmissionFF",
            cfg=config | Trans_relevant_params,
            outerFolder=outerFolder,
        )
        exp.acquire()
        exp.display(plotDisp=True, block=False)

    if Run2ToneSpec:
        print("Running MockSpectroscopyExperiment...")
        exp = MockSpectroscopyExperiment(
            path="QubitSpecFF",
            cfg=config | Spec_relevant_params,
            outerFolder=outerFolder,
        )
        exp.acquire()
        exp.display(plotDisp=True, block=False)

    if RunAmplitudeRabi:
        print("Running MockAmplitudeRabiExperiment...")
        exp = MockAmplitudeRabiExperiment(
            path="AmplitudeRabi",
            cfg=config | Amplitude_Rabi_params,
            outerFolder=outerFolder,
        )
        exp.acquire()
        exp.display(plotDisp=True, block=False)

    # ------ T1/T2 ------

    if RunT1:
        print("Running MockT1Experiment...")
        exp = MockT1Experiment(
            path="T1",
            cfg=config | T1_params,
            outerFolder=outerFolder,
        )
        exp.acquire()
        exp.display(plotDisp=True, block=False)

    if RunT2:
        print("Running MockT2RamseyExperiment...")
        exp = MockT2RamseyExperiment(
            path="T2R",
            cfg=config | T2R_params,
            outerFolder=outerFolder,
        )
        exp.acquire()
        exp.display(plotDisp=True, block=False)

    # ------ Single Shot ------

    if SingleShot:
        print("Running MockSingleShotExperiment...")
        exp = MockSingleShotExperiment(
            path="SingleShot",
            cfg=config | SS_params,
            outerFolder=outerFolder,
        )
        exp.acquire()
        exp.display(plotDisp=True, block=False)

    # ------ 2D Sweeps ------

    if Run_Spec_vs_FFgain:
        print("Running MockSpec2DExperiment (Spec vs FF)...")
        exp = MockSpec2DExperiment(
            path="SpecVsFF",
            cfg=config | Spec_relevant_params | FF_sweep_spec_relevant_params,
            outerFolder=outerFolder,
        )
        exp.acquire()
        exp.display(plotDisp=True, block=False)

    # ------ Correlations ------

    if Run_CurrentCorrelations:
        print("Running MockCorrelationExperiment...")
        exp = MockCorrelationExperiment(
            path="RampBeamsplitterCorrelationsR",
            cfg=config | ramp_beamsplitter_1d_dict,
            outerFolder=outerFolder,
        )
        exp.acquire()
        exp.display(plotDisp=True, block=False)

    # ------ MUX Spectroscopy ------

    if SingleShot_2Qubit:
        print("Running MockMUXSpectroscopyExperiment...")
        exp = MockMUXSpectroscopyExperiment(
            path="SingleShot_2Qubit",
            cfg=config | SS_2Q_params,
            outerFolder=outerFolder,
        )
        exp.acquire()
        exp.display(plotDisp=True, block=False)

    # ------ Grid Layout Tests ------

    if RunGridTests:
        print("Running Grid Layout Tests...")

        for GridClass in [MockGrid1x1, MockGrid1x2, MockGrid2x1, MockGrid2x2,
                          MockGrid2x3, MockGrid3x3, MockGridSpec]:
            exp = GridClass(path=GridClass.__name__, cfg=config, outerFolder=outerFolder)
            exp.acquire()
            exp.display(plotDisp=True, block=False)

    # ------ Multi-Figure Tests ------

    if RunMultiFigureTests:
        print("Running Multi-Figure Tests...")

        for FigClass in [MockMultiFigure2, MockMultiFigure3]:
            exp = FigClass(path=FigClass.__name__, cfg=config, outerFolder=outerFolder)
            exp.acquire()
            exp.display(plotDisp=True, block=False)

    # ------ Live Plot Tests ------

    if RunLivePlotTests:
        print("Running Live Plot Tests...")

        exp = MockLivePlot1D(path="LivePlot1D", cfg=config, outerFolder=outerFolder)
        exp.acquire()
        exp.display(plotDisp=True, block=False)

    # Final show (non-blocking already handled)
    print()
    print("All enabled experiments complete.")
    print(f"Config keys: {list(config.keys())}")
    plt.show()

# =============================================================================
# EXPERIMENT CLASS REGISTRY - For ExperimentLoader discovery
# =============================================================================

# These aliases help ExperimentLoader find experiments with familiar names
# (matching real experiment class names)

T1MUX = MockT1Experiment
T2RMUX = MockT2RamseyExperiment
QubitSpecSliceFFMUX = MockSpectroscopyExperiment
AmplitudeRabiFFMUX = MockAmplitudeRabiExperiment
CavitySpecFFMUX = MockTransmissionExperiment
SingleShotFFMUX = MockSingleShotExperiment
SpecVsFF = MockSpec2DExperiment
RampCurrentCorrelationsR = MockCorrelationExperiment
MockPopulationSweep = MockPopulationSweepExperiment

# Grid tests
Grid1x1 = MockGrid1x1
Grid1x2 = MockGrid1x2
Grid2x1 = MockGrid2x1
Grid2x2 = MockGrid2x2

# Live plotting
LivePlot1D = MockLivePlot1D
LivePlot2D = MockLivePlot2D