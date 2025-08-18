# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.CalibrateFFvsDriveTiming import \
    CalibrateFFvsDriveTiming
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotDecimated import \
    SingleShotDecimated
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import \
    QubitSpecSliceFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT1MUX import T1MUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT2RMUX import T2RMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mFFvsRamsey import FFvsRamsey
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mFluxStabilitySpec import \
    FluxStabilitySpec
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mSpecVsQblox import SpecVsQblox

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mFFvsSpec import FFvsSpec
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mOptimizeReadoutandPulse_FFMUX import \
    ReadOpt_wSingleShotFFMUX, QubitPulseOpt_wSingleShotFFMUX, ROTimingOpt_wSingleShotFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mGainSweepQubitOscillations import \
    GainSweepOscillations
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mGainSweepQubitOscillationsR import \
    GainSweepOscillationsR
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mSingleQubitOscillations import QubitOscillations

from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mTransmissionFFMUX import CavitySpecFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX, SingleShot_2QFFMUX

import numpy as np



Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7121.4 - BaseConfig["res_LO"], 'Gain': 1200,
                      "FF_Gains": [-21498, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3892.33, 'sigma': 0.05, 'Gain': 1800},
          'Pulse_FF': [-21498, 0, 0, 0, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7077.6 - BaseConfig["res_LO"], 'Gain': 2000,
                      "FF_Gains": [0, -23200, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3895.2, 'sigma': 0.05, 'Gain': 1540},
          'Pulse_FF': [0, -23200, 0, 0, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7510.9 - BaseConfig["res_LO"], 'Gain': 1500,
                      "FF_Gains": [0, 0, -19298, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3881.1, 'sigma': 0.05, 'Gain': 4000},
          'Pulse_FF': [0, 0, -19298, 0, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568.2 - BaseConfig["res_LO"], 'Gain': 1900,
                      "FF_Gains": [0, 0, 0, -22048, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3913.1, 'sigma': 0.05, 'Gain': 2400},
          'Pulse_FF': [0, 0, 0, -22048, 0, 0, 0, 0]},
    '5': {'Readout': {'Frequency': 7363.2 - BaseConfig["res_LO"], 'Gain': 2000,
                      "FF_Gains": [0, 0, 0, 0, -20560, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3873.62, 'sigma': 0.05, 'Gain': 2300},
          'Pulse_FF': [0, 0, 0, 0, -20560, 0, 0, 0]},
    '6': {'Readout': {'Frequency': 7441.3 - BaseConfig["res_LO"], 'Gain': 2000,
                      "FF_Gains": [0, 0, 0, 0, 0, -22448, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3877.2, 'sigma': 0.05, 'Gain': 2400},
          'Pulse_FF': [0, 0, 0, 0, 0, -22448, 0, 0]},
    '7': {'Readout': {'Frequency': 7253.8 - BaseConfig["res_LO"], 'Gain': 1800,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, -20578, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3812.7, 'sigma': 0.05, 'Gain': 1668},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, -20578, 0]},
    '8': {'Readout': {'Frequency': 7309.1 - BaseConfig["res_LO"], 'Gain': 1000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, -19516], "Readout_Time": 2.5, "ADC_Offset":1.5, 'cavmin': True},
          'Qubit': {'Frequency': 3861.5, 'sigma': 0.05, 'Gain': 2180},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, -19516]},
}



Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7122.4 - BaseConfig["res_LO"], 'Gain': 2100,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 1.7, "ADC_Offset": 1.5, 'cavmin': True},
          'Qubit': {'Frequency': 4398.8, 'sigma': 0.05, 'Gain': 2000},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7078.5 - BaseConfig["res_LO"], 'Gain': 2200,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.4, "ADC_Offset": 1.4, 'cavmin': True},
          'Qubit': {'Frequency': 4119.2, 'sigma': 0.05, 'Gain': 1350},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7511.6 - BaseConfig["res_LO"], 'Gain': 2050,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.0, "ADC_Offset": 0.9, 'cavmin': True},
          'Qubit': {'Frequency': 4366.4, 'sigma': 0.05, 'Gain': 2550},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7569.0 - BaseConfig["res_LO"], 'Gain': 1050,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2, "ADC_Offset": 1.6, 'cavmin': True},
          'Qubit': {'Frequency': 4421.2, 'sigma': 0.05, 'Gain': 1830},
          'Pulse_FF': [0, 0, 0, -677, 0, 0, 0, 0]},
}

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7121.6 - BaseConfig["res_LO"], 'Gain': 6400,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1., 'cavmin': True},
          'Qubit': {'Frequency': 4028.5, 'sigma': 0.05, 'Gain': 3000},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7077.7 - BaseConfig["res_LO"], 'Gain': 6500,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1., 'cavmin': True},
          'Qubit': {'Frequency': 4029.7, 'sigma': 0.05, 'Gain': 2450},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7511.0 - BaseConfig["res_LO"], 'Gain': 5000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3.0, "ADC_Offset": 0.9, 'cavmin': True},
          'Qubit': {'Frequency': 3989.2, 'sigma': 0.05, 'Gain': 9730},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568.5 - BaseConfig["res_LO"], 'Gain': 5000,
                          "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 0.9, 'cavmin': True},
              'Qubit': {'Frequency': 4047.7, 'sigma': 0.05, 'Gain': 4500},
            'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
}



Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7121.8 - BaseConfig["res_LO"], 'Gain': 5400,
                      "FF_Gains": [-19000, 31000, 0, -8400, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 0.75, 'cavmin': True},
          'Qubit': {'Frequency': 4086.3, 'sigma': 0.07, 'Gain': 2000},
          'Pulse_FF': [-19000, 31000, 0, -8400, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7078.3 - BaseConfig["res_LO"], 'Gain': 5000,
                      "FF_Gains" : [-19000, 31000, 0, -8400, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 0.75, 'cavmin': True},
          'Qubit': {'Frequency': 4399, 'sigma': 0.07, 'Gain': 2570},
          'Pulse_FF': [-19000, 31000, 0, -8400, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7510.5 - BaseConfig["res_LO"], 'Gain': 6000,
                      "FF_Gains": [-19000, 31000, 0, -8400, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3560.7, 'sigma': 0.07, 'Gain': 9500},
          'Pulse_FF': [-19000, 31000, 0, -8400, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568.0 - BaseConfig["res_LO"], 'Gain': 6500,
                      "FF_Gains": [-19000, 31000, 0, -8400, 0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3905, 'sigma': 0.07, 'Gain': 2820},
          'Pulse_FF': [-19000, 31000, 0, -8400, 0, 0, 0, 0]},
    'D': {'Readout': {'Frequency': 7122.2 - BaseConfig["res_LO"], 'Gain': 5000,
                      "FF_Gains": [0, 12000, 0, -12000, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 0.75,
                      'cavmin': True},
          'Qubit': {'Frequency': 4393.6, 'sigma': 0.07, 'Gain': 3280},
          'Pulse_FF': [0, 12000, 0, -12000, 0, 0, 0, 0]},
    'C': {'Readout': {'Frequency': 7077.6 - BaseConfig["res_LO"], 'Gain': 3200,
                      "FF_Gains": [0, 12000, 0, -12000, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 0.75,
                      'cavmin': True},
          'Qubit': {'Frequency': 4120.9, 'sigma': 0.07, 'Gain': 3500},
          'Pulse_FF': [0, 12000, 0, -12000, 0, 0, 0, 0]},
    'B': {'Readout': {'Frequency': 7567.9 - BaseConfig["res_LO"], 'Gain': 1500,
                  "FF_Gains": [0, 12000, 0, -12000, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
      # 'Qubit': {'Frequency': 3809.7, 'sigma': 0.07, 'Gain': 2000},
          'Qubit': {'Frequency': 3900, 'sigma': 0.07, 'Gain': 2820},
          'Pulse_FF': [0, 12000, 0, -12000, 0, 0, 0, 0]},
    'A': {'Readout': {'Frequency': 7510.6 - BaseConfig["res_LO"], 'Gain': 1000,
                      "FF_Gains": [0, 12000, 0, -12000, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1,
                      'cavmin': True},
          'Qubit': {'Frequency': 3560.3, 'sigma': 0.07, 'Gain': 9500},
          'Pulse_FF': [0, 12000, 0, -12000, 0, 0, 0, 0]},

}

Readout_FF = [5660, 26575, -17231, -5017, 0, 0, 0, 0]
# Readout_FF = [56, 26575, -314, -241, 0, 0, 0, 0]
# (4088.0, 4380.0, 3520.0, 3820.0, 3500.9, 3501.5, 3441.8, 3506.0)
# Josh parameters
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7121.7 - BaseConfig["res_LO"], 'Gain': 5250,
                      "FF_Gains": Readout_FF, "Readout_Time": 3, "ADC_Offset": 0.5, 'cavmin': True},
          'Qubit': {'Frequency': 4077.2, 'sigma': 0.07, 'Gain': 2388},
          'Pulse_FF': Readout_FF},
    '2': {'Readout': {'Frequency': 7078.3 - BaseConfig["res_LO"], 'Gain': 5200,
                      "FF_Gains": Readout_FF, "Readout_Time": 3.5, "ADC_Offset": 0.5, 'cavmin': True},
          'Qubit': {'Frequency': 4379.9, 'sigma': 0.07, 'Gain': 3200},
          'Pulse_FF': Readout_FF},
    '3': {'Readout': {'Frequency': 7510.55 - BaseConfig["res_LO"], 'Gain': 3200,
                      "FF_Gains": Readout_FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3624, 'sigma': 0.07, 'Gain': 5000},
          'Pulse_FF': [5660, 26575, -17231 + 5000, -5017, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568.1 - BaseConfig["res_LO"], 'Gain': 6000,
                      "FF_Gains": Readout_FF, "Readout_Time": 3.5, "ADC_Offset": 0.5, 'cavmin': True},
          'Qubit': {'Frequency': 3828.5, 'sigma': 0.07, 'Gain': 3600},
          'Pulse_FF': Readout_FF},
    # Resonant points. Guess: [0,0,0,0]
    '1H': {'Qubit': {'Frequency': 4048.4, 'sigma': 0.07, 'Gain': 3000},
           'Pulse_FF': [56 + 4000, 5, -314, -241, 0, 0, 0, 0]},
    '2H': {'Qubit': {'Frequency': 4043.8, 'sigma': 0.07, 'Gain': 3080},
           'Pulse_FF': [56, 5 + 4000, -314, -241, 0, 0, 0, 0]},
    '3H': {'Qubit': {'Frequency': 4053.2, 'sigma': 0.07, 'Gain': 4050},
           'Pulse_FF': [56, 5, -314 + 4000, -241, 0, 0, 0, 0]},
    '1L': {'Qubit': {'Frequency': 3844.9, 'sigma': 0.07, 'Gain': 4700},
           'Pulse_FF': [56 - 4000, 5, -314, -241, 0, 0, 0, 0]},

    '1HH': {'Qubit': {'Frequency': 4047.3, 'sigma': 0.07, 'Gain': 2700},
            'Pulse_FF': [56 + 4000, 5 - 4000, -314 - 4000, -241, 0, 0, 0, 0]},
    '4HH': {'Qubit': {'Frequency': 3950.3, 'sigma': 0.07, 'Gain': 2200},
            'Pulse_FF': [56 + 4000, 5 - 4000, -314 - 4000, -241, 0, 0, 0, 0]},

}

FF_gain1_expt =  56
FF_gain2_expt =  5
FF_gain3_expt = -314
FF_gain4_expt = -241
FF_gain5_expt =  0
FF_gain6_expt =  0
FF_gain7_expt =  0
FF_gain8_expt =  0

Qubit_Readout =[4]
Qubit_Pulse   = ['1HH', '4HH']

#
# Qubit_Readout = [2]
# Qubit_Pulse   = [2]

FF_gain1_expt = -22657
FF_gain1_expt = 0

FF_gain2_expt = 7000
FF_gain2_expt = 12000

FF_gain3_expt = 16829
FF_gain3_expt = 0

FF_gain4_expt = -4685
FF_gain4_expt = -12000


FF_gain1_expt = -21800
FF_gain2_expt = 12000
# FF_gain3_expt = 0
FF_gain3_expt = 14500
FF_gain4_expt = -4750

FF_gain5_expt = 0
FF_gain6_expt = 0
FF_gain7_expt = 0
FF_gain8_expt = 0




RunTransmissionSweep = False # determine cavity frequency
Trans_relevant_params = {"reps": 200, "TransSpan": 1.5, "TransNumPoints": 61,
                        "readout_length": 3, 'cav_relax_delay': 10}
Run2ToneSpec = False
Spec_relevant_params = {
                      # "qubit_gain": 2000, "SpecSpan":420, "SpecNumPoints": 71,
                      #   "qubit_gain": 1000, "SpecSpan": 200, "SpecNumPoints": 71,
                      #   "qubit_gain": 500, "SpecSpan": 50, "SpecNumPoints": 71,
                        "qubit_gain": 20, "SpecSpan": 10, "SpecNumPoints": 71,
                        'Gauss': False, "sigma": 0.05, "Gauss_gain": 3200,
                        'reps': 5*150, 'rounds': 1}

Run_Spec_v_FFgain = False
### Inherits spec parameters from above
FF_sweep_spec_relevant_params = {"qubit_FF_index": 4,
                            "FF_gain_start": -12000, "FF_gain_stop": -5000, "FF_gain_steps": 21,
                                 'relax_delay':100}


FluxStability = False
#### Repeat SpecSlice over time
Flux_Stability_params = {"delay_minutes": 10, "num_steps": 6 * 8}


Run_Spec_v_Qblox = False
Spec_v_Qblox_params = {"Qblox_start": 0.4, "Qblox_stop": 1.2, "Qblox_steps": 6, "DAC": 9}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"max_gain": 20000, 'relax_delay':100}


SingleShot = True
SS_params = {"Shots": 4000, 'number_of_pulses': 1, 'relax_delay': 200}

SingleShotDecimate = False

SingleShot_ReadoutOptimize = False
SS_R_params = {"Shots": 500,
               "gain_start": 2000, "gain_stop": 7000, "gain_pts": 8, "span": 1, "trans_pts": 6, 'number_of_pulses': 1}

SingleShot_QubitOptimize = True
SS_Q_params = {"Shots": 500,
               "q_gain_span": 500, "q_gain_pts": 7, "q_freq_span": 3.5, "q_freq_pts": 7,
               'number_of_pulses': 1,
               'qubit_sweep_index': -1}

if SingleShot_QubitOptimize and SS_Q_params['qubit_sweep_index'] >= len(Qubit_Pulse):
    raise ValueError("Qubit optimize sweep index out of range")

# These T1 and T2R experiments are done at FFPulses!
RunT1 = False
RunT2 = False

T1_params = {"stop_delay_us": 250, "expts": 40, "reps": 150}

T2R_params = {"stop_delay_us": 7, "expts": 125, "reps": 300,
              "freq_shift": 0.0, "phase_shift_cycles": -4, "relax_delay":200}

Run_FF_v_Ramsey = False
FF_sweep_Ramsey_relevant_params = {"stop_delay_us": 5, "expts": 100, "reps":200,
                                    "qubit_FF_index": Qubit_Readout[0],
                                    "FF_gain_start": -300, "FF_gain_stop": -210, "FF_gain_steps":21,
                                   "relax_delay":100,
                                   # "qubit_drive_freq":4393.76
                                   }



RunT1_TLS = False
T1TLS_params = {"FF_gain_start": 21000, "FF_gain_stop": 23000, "FF_gain_steps": 11,
                "stop_delay_us": 250, "expts": 40, "reps": 150,
                'qubitIndex': Qubit_Pulse[0]}

# SingleShot_ROTimingOptimize = False
# SS_Timing_params = {"Shots": 500,
#                   "read_length_start":1, "read_length_end":10, "read_length_points":5,
#                   "trig_time_start":0.1, "trig_time_end":3, "trig_time_points":5}


# SS_Q_params = {"Shots": 500,
#                "q_gain_span": 5000, "q_gain_pts": 6, "q_freq_span": 50, "q_freq_pts": 11,
#                'number_of_pulses': 1,
#                'qubit_sweep_index': 1}

Oscillation_Gain = False
oscillation_gain_dict = {'qubit_FF_index': 3, 'reps': 150,
                         'start': 1, 'step': 20, 'expts': 51,
                         'gainStart': -600,
                         'gainStop': 0, 'gainNumPoints': 9, 'relax_delay': 100}
Oscillation_Gain_QICK_sweep = True

Oscillation_Single = False # uses same dict as gain sweep

Calib_FF_vs_drive_delay = False
ff_drive_delay_dict = {'start':200, 'step':8, 'expts': 200, # delay of FF, units of samples
                       'qubit_delay_cycles': 80,
                       'reps': 4000,
                        'qubit_index': Qubit_Pulse[0],}

# RunChiShift = False
# ChiShift_Params = {'pulse_expt': {'check_12': False},
#                    'qubit_freq01': Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['Frequency'], 'qubit_gain01': 1670 // 2,
#                    'qubit_freq12':  Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['Frequency'],  'qubit_gain12': 1670 // 2}


CalibrationFF_params = {'FFQubitIndex': 3, 'FFQubitExpGain': 3000,
                        "start": 0, "step": 1, "expts": 20 * 16 * 1,
                        "reps": 100, "rounds": 200, "relax_delay": 100, "YPulseAngle": 93,
           }


SingleShot_2Qubit = False
SS_2Q_params = {"Shots": 5000, 'number_of_pulses': 1, 'relax_delay': 400}


SS_2Q_params = {"Shots": 5000, 'number_of_pulses': 1, 'relax_delay': 400,
                'second_qubit_freq': 3809.3, 'second_qubit_gain': 1140}

# This ends the working section of the file.
#----------------------------------------
# Not used
FF_gain1_BS = 0
FF_gain2_BS = 0
FF_gain3_BS = 0
FF_gain4_BS = 0
FF_gain5_BS = 0
FF_gain6_BS = 0
FF_gain7_BS = 0
FF_gain8_BS = 0
exec(open("UPDATE_CONFIG.py").read())
#--------------------------------------------------
# This begins the booleans
soc.reset_gens()
if RunTransmissionSweep:
    Instance_trans = CavitySpecFFMUX(path="TransmissionFF", cfg=config | Trans_relevant_params,
                                     soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    Instance_trans.acquire_display_save(plotDisp=True)

    #update the transmission frequency to be the peak
    if Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['cavmin']:
        config["res_freqs"][0] = Instance_trans.peakFreq_min
    else:
        config["res_freqs"][0] = Instance_trans.peakFreq_max

    print("Cavity frequency found at: ", config["res_freqs"][0] + BaseConfig["res_LO"])
else:
    print("Cavity frequency set to: ", config["res_freqs"][0] + BaseConfig["res_LO"])
    pass

if Run2ToneSpec:
    QubitSpecSliceFFMUX(path="QubitSpecFF", cfg=config | Spec_relevant_params,
                        soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True)

if Run_Spec_v_FFgain:
    FFvsSpec(path="FF_vs_Spec", cfg=config | Spec_relevant_params | FF_sweep_spec_relevant_params,
                             soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True)

if Run_Spec_v_Qblox:
    SpecVsQblox(path="SpecVsQblox", cfg=config | Spec_relevant_params | Spec_v_Qblox_params,
                             soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True)

if FluxStability:
    FluxStabilitySpec(path="FluxStability", cfg=config | Spec_relevant_params | Flux_Stability_params,
                soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True)

if RunAmplitudeRabi:
    AmplitudeRabiFFMUX(path="AmplitudeRabi", cfg=config | Amplitude_Rabi_params,
                        soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True)

if RunT1:
    T1MUX(path="T1", cfg=config | T1_params, soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_save_display(plotDisp=True)
if RunT2:
    T2RMUX(path="T2R", cfg=config | T2R_params,
              soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_save_display(plotDisp=True)

if Run_FF_v_Ramsey:
    FFvsRamsey(path="FF_vs_Ramsey", cfg=config | FF_sweep_Ramsey_relevant_params,
                             soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True)

if SingleShot:
    SingleShotFFMUX(path="SingleShot", outerFolder=outerFolder,
                           cfg=config | SS_params, soc=soc,soccfg=soccfg).acquire_save_display(plotDisp=True)

if SingleShotDecimate:
    SingleShotDecimated(path="SingleShotDecimated", outerFolder=outerFolder,
                           cfg=config | SS_params, soc=soc,soccfg=soccfg).acquire_save_display(plotDisp=True)
if SingleShot_ReadoutOptimize:
    ReadOpt_wSingleShotFFMUX(path="SingleShot_OptReadout", outerFolder=outerFolder,
                             cfg=config | SS_params | SS_R_params,soc=soc,soccfg=soccfg).acquire_display_save(plotDisp=True)
if SingleShot_QubitOptimize:
    QubitPulseOpt_wSingleShotFFMUX(path="SingleShot_OptQubit", outerFolder=outerFolder,
                                   cfg=config | SS_params | SS_Q_params,soc=soc,soccfg=soccfg).acquire_display_save(plotDisp=True)

# if SingleShot_ROTimingOptimize:
#     ROTimingOpt_wSingleShotFFMUX(path="SingleShot_OptReadout", outerFolder=outerFolder,
#                              cfg=config | SS_params | SS_Timing_params,soc=soc,soccfg=soccfg).acquire_display_save(plotDisp=True)

if Oscillation_Gain or Oscillation_Single or Calib_FF_vs_drive_delay:
    exec(open("CALIBRATE_SINGLESHOT_READOUTS.py").read())

if Oscillation_Gain:
    if not Oscillation_Gain_QICK_sweep:
        GainSweepOscillations(path="GainSweepOscillations", outerFolder=outerFolder,
                              cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)
    else:
        # raise AssertionError('this sweep not working yet.')
        print("Testing arbitrary waveform sweep")
        # GainSweepOscillations(path="GainSweepOscillations", outerFolder=outerFolder,
                              # cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=False)
        GainSweepOscillationsR(path="GainSweepOscillationsR", outerFolder=outerFolder,
                              cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)
if Oscillation_Single:
    QubitOscillations(path="QubitOscillations", outerFolder=outerFolder,
                          cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

# TimeDomainSpec(path="TimeDomainSpec", outerFolder=outerFolder,
#                           cfg=config | {'reps': 5,
#                          'start':1, 'step': 16, 'expts': 50,}, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)


if SingleShot_2Qubit:
    SingleShot_2QFFMUX(path="SingleShot_2Qubit", outerFolder=outerFolder,
                           cfg=config | SS_2Q_params, soc=soc,soccfg=soccfg).acquire_save_display(plotDisp=True)

if Calib_FF_vs_drive_delay:
    CalibrateFFvsDriveTiming(path="FF_drive_timing", outerFolder=outerFolder,
                           cfg=config | ff_drive_delay_dict, soc=soc,soccfg=soccfg).acquire_save_display(plotDisp=True)
# import matplotlib.pyplot as plt
# while True:
#     plt.pause(50)
print(config)

