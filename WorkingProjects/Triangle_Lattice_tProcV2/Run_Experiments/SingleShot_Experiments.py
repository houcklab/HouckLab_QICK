# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

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
    '1': {'Readout': {'Frequency': 7122.1 - BaseConfig["res_LO"], 'Gain': 8200,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4393.76, 'sigma': 0.07, 'Gain': 3920},
          # 'Qubit': {'Frequency': 4000, 'sigma': 0.07, 'Gain': 3920},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7077.3 - BaseConfig["res_LO"], 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3829.2, 'sigma': 0.07, 'Gain': 4240},
          # 'Qubit': {'Frequency': 4000, 'sigma': 0.07, 'Gain': 4240},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7510.5 - BaseConfig["res_LO"], 'Gain': 7000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3560.5, 'sigma': 0.07, 'Gain': 17000},
          # 'Qubit': {'Frequency': 3559.8, 'sigma': 0.07, 'Gain': 17150},
          # 'Qubit': {'Frequency': 3950, 'sigma': 0.07, 'Gain': 17000},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568.2 - BaseConfig["res_LO"], 'Gain': 7400,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4116.7, 'sigma': 0.07 , 'Gain': 6400 },
          # 'Qubit': {'Frequency': 4000, 'sigma': 0.07, 'Gain': 6400},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    'D': {'Readout': {'Frequency': 7122.1 - BaseConfig["res_LO"], 'Gain': 8200,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4101.3, 'sigma': 0.07, 'Gain': 5100},
          'Pulse_FF': [-18700, 7000, 14500, -2800, 0, 0, 0, 0]},
    'B': {'Readout': {'Frequency': 7077.3 - BaseConfig["res_LO"], 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4000.9, 'sigma': 0.07, 'Gain': 3844},
          'Pulse_FF': [-18700, 7000, 14500, -2800, 0, 0, 0, 0]},
    'A': {'Readout': {'Frequency': 7510.5 - BaseConfig["res_LO"], 'Gain': 7000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3937.4, 'sigma': 0.07, 'Gain': 10202},
          'Pulse_FF': [-18700, 7000, 14500, -2800, 0, 0, 0, 0]},
    'C': {'Readout': {'Frequency': 7568.2 - BaseConfig["res_LO"], 'Gain': 7400,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4049.9, 'sigma': 0.07, 'Gain': 5810},
          'Pulse_FF': [-18700, 7000, 14500, -2800, 0, 0, 0, 0]},
    'BD': {'Readout': {'Frequency': 7122.1 - BaseConfig["res_LO"], 'Gain': 8200,
                       "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
           'Qubit': {'Frequency': 4101.97, 'sigma': 0.07, 'Gain': 4800},
           'Pulse_FF': [-18700, 7000, 14500, -2800, 0, 0, 0, 0]},
    'BC': {'Readout': {'Frequency': 7568.2 - BaseConfig["res_LO"], 'Gain': 7400,
                       "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
           'Qubit': {'Frequency': 4051.2, 'sigma': 0.07, 'Gain': 4220},
           'Pulse_FF': [-18700, 7000, 14500, -2800, 0, 0, 0, 0]},
}

FF_gain1_expt = 0
FF_gain2_expt = 0
FF_gain3_expt = 16829
FF_gain4_expt = -4685
FF_gain5_expt = 0
FF_gain6_expt = 0
FF_gain7_expt = 0
FF_gain8_expt = 0

FF_gain1_expt = -22765
FF_gain2_expt = -10000
FF_gain3_expt = 16829
FF_gain4_expt = 10000
FF_gain5_expt = 0
FF_gain6_expt = 0
FF_gain7_expt = 0
FF_gain8_expt = 0



Qubit_Readout = [4]
Qubit_Pulse   = [4]


RunTransmissionSweep = False # determine cavity frequency
Trans_relevant_params = {"reps": 300, "TransSpan": 1.5, "TransNumPoints": 61,
                        "readout_length": 3, 'cav_relax_delay': 10}
Run2ToneSpec = False
Spec_relevant_params = {
                      # "qubit_gain": 2000, "SpecSpan":420, "SpecNumPoints": 71,
                        "qubit_gain": 1000, "SpecSpan": 200, "SpecNumPoints": 71,
                        # "qubit_gain": 200, "SpecSpan": 50, "SpecNumPoints": 141,
                        "qubit_gain": 5, "SpecSpan": 1, "SpecNumPoints": 141,
                        'Gauss': False, "sigma": 0.05, "Gauss_gain": 3200,
                        'reps': 20, 'rounds': 10}


# Spec_relevant_params = {"qubit_gain": 100, "SpecSpan": 20, "SpecNumPoints": 71,
#                         'Gauss': True, "sigma": 0.05, "Gauss_gain": 1260,
#                         'reps': 144, 'rounds': 1}

Run_Spec_v_FFgain = False
### Inherits spec parameters from above

FF_sweep_spec_relevant_params = {"qubit_FF_index": 4,
                            "FF_gain_start": -20000, "FF_gain_stop": -10000, "FF_gain_steps": 11}

# FF_sweep_spec_relevant_params = {"qubit_FF_index": 2,
#                             "FF_gain_start": -5500, "FF_gain_stop": -4500, "FF_gain_steps": 11}
#
# FF_sweep_spec_relevant_params = {"qubit_FF_index": 3,
#                             "FF_gain_start": -8500, "FF_gain_stop": -7000, "FF_gain_steps": 11}

FluxStability = False
#### Repeat SpecSlice over time
Flux_Stability_params = {"delay_minutes":10, "num_steps":80}


Run_Spec_v_Qblox = False
Spec_v_Qblox_params = {"Qblox_start": 0.4, "Qblox_stop": 1.2, "Qblox_steps": 6, "DAC": 9}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"sigma": 0.035, "max_gain": 20000, 'relax_delay':200}


# These T1 and T2R experiments are done at FFPulses!
RunT1 = True
RunT2 = False

T1_params = {"stop_delay_us": 160, "expts": 40, "reps": 150}

T2R_params = {"stop_delay_us": 7, "expts": 125, "reps": 300,
              "freq_shift": 0.0, "phase_shift_cycles": -4, "relax_delay":200}

Run_FF_v_Ramsey = False
FF_sweep_Ramsey_relevant_params = {"stop_delay_us": 10, "expts": 100, "reps":1000,
                                    "qubit_FF_index": 1,
                                    "FF_gain_start": -20, "FF_gain_stop": 100, "FF_gain_steps": 31,
                                   "relax_delay":200,
                                   # "qubit_drive_freq":4393.76
                                   }

SingleShot = True
# SS_params = {"Shots": 5000, "readout_length": 2.5, "adc_trig_delay": 0.3,
#              'number_of_pulses': 1, 'relax_delay': 200}

# SS_params = {"Shots": 5000, "readout_length": 3, "adc_trig_delay": 1,
#              'number_of_pulses': 1, 'relax_delay': 400}

SS_params = {"Shots": 5000, 'number_of_pulses': 1, 'relax_delay': 200}

RunT1_TLS = False
T1TLS_params = {'gainStart': 0, 'gainStop': 0, 'gainNumPoints': 1, 'wait_times': np.linspace(0.01, 150, 31),
                'angle': None, 'threshold': None,
                'meas_shots': 50, 'repeated_nums':10, 'SS_calib_shots': 1500,
                'qubitIndex': 2}#, Qubit_Pulse[0]}


SingleShot_ReadoutOptimize = False
SS_R_params = {"Shots": 500,
               "gain_start": 1000, "gain_stop": 32766//4, "gain_pts": 11, "span": 1, "trans_pts": 6, 'number_of_pulses': 1}

SingleShot_QubitOptimize = False
SS_Q_params = {"Shots": 3000,
               "q_gain_span": 1000, "q_gain_pts": 7, "q_freq_span": 4, "q_freq_pts": 7,
               'number_of_pulses': 1,
               'qubit_sweep_index': 0}

# SingleShot_ROTimingOptimize = False
# SS_Timing_params = {"Shots": 500,
#                   "read_length_start":1, "read_length_end":10, "read_length_points":5,
#                   "trig_time_start":0.1, "trig_time_end":3, "trig_time_points":5}


# SS_Q_params = {"Shots": 500,
#                "q_gain_span": 5000, "q_gain_pts": 6, "q_freq_span": 50, "q_freq_pts": 11,
#                'number_of_pulses': 1,
#                'qubit_sweep_index': 1}

Oscillation_Gain = False
oscillation_gain_dict = {'qubit_FF_index': 3, 'reps': 100,
                         'start': 1, 'step': 16, 'expts': 71,
                         'gainStart': 15500,
                         'gainStop': 17500, 'gainNumPoints': 11, 'relax_delay': 100, 'res_length':10}

Oscillation_Gain_QICK_sweep = False

Oscillation_Single = False
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


# SS_2Q_params = {"Shots": 5000, 'number_of_pulses': 1, 'relax_delay': 400,
#                 'second_qubit_freq': 3559.8, 'second_qubit_gain': 17150}


# This ends the working section of the file.
#----------------------------------------
FF_gain1_BS = -5000
FF_gain2_BS = -15000
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
if SingleShot_ReadoutOptimize:
    ReadOpt_wSingleShotFFMUX(path="SingleShot_OptReadout", outerFolder=outerFolder,
                             cfg=config | SS_params | SS_R_params,soc=soc,soccfg=soccfg).acquire_display_save(plotDisp=True)
if SingleShot_QubitOptimize:
    QubitPulseOpt_wSingleShotFFMUX(path="SingleShot_OptQubit", outerFolder=outerFolder,
                                   cfg=config | SS_params | SS_Q_params,soc=soc,soccfg=soccfg).acquire_display_save(plotDisp=True)

# if SingleShot_ROTimingOptimize:
#     ROTimingOpt_wSingleShotFFMUX(path="SingleShot_OptReadout", outerFolder=outerFolder,
#                              cfg=config | SS_params | SS_Timing_params,soc=soc,soccfg=soccfg).acquire_display_save(plotDisp=True)

if Oscillation_Gain or Oscillation_Single:
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

# import matplotlib.pyplot as plt
# while True:
#     plt.pause(50)
print(config)

