# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import \
    QubitSpecSliceFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mSpecVsQblox import SpecVsQblox

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mFFvsSpec import FFvsSpec
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mOptimizeReadoutandPulse_FFMUX import \
    ReadOpt_wSingleShotFFMUX, QubitPulseOpt_wSingleShotFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mGainSweepQubitOscillations import \
    GainSweepOscillations
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mSingleQubitOscillations import QubitOscillations

from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mTransmissionFFMUX import CavitySpecFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX

import numpy as np



mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq
BaseConfig["readout_length"] = 2.5

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7121.3 - BaseConfig["res_LO"] , 'Gain': 10000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3518.5, 'sigma': 0.07, 'Gain': 820},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7078.3 - BaseConfig["res_LO"] , 'Gain': 8000,
                  "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          # 'Qubit': {'Frequency': 3770.7, 'sigma': 0.07, 'Gain': 1221},
          'Qubit': {'Frequency': 3768.6, 'sigma': 0.07, 'Gain': 1240},
          # 'Qubit': {'Frequency': 4200, 'sigma': 0.07, 'Gain': 1194},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7510.8 - BaseConfig["res_LO"] , 'Gain': 8000,
                  "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          # 'Qubit': {'Frequency': 3820.8, 'sigma': 0.07, 'Gain': 1880},
          'Qubit': {'Frequency': 3888.5, 'sigma': 0.07, 'Gain': 1890},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7569.0 - BaseConfig["res_LO"] , 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4300, 'sigma': 0.07, 'Gain': 1414},
          # 'Qubit': {'Frequency': 3800, 'sigma': 0.07, 'Gain': 1000},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    }

# to get around 3.7
# Q2: -3000
# Q4: -26000

FF_gain1_expt = 0
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0
FF_gain5_expt = 0
FF_gain6_expt = 0
FF_gain7_expt = 0
FF_gain8_expt = 0

Qubit_Readout = [2]
Qubit_Pulse = [2]


RunTransmissionSweep = False # determine cavity frequency
Trans_relevant_params = {"reps": 200, "TransSpan": 1.5, "TransNumPoints": 61,
                        "readout_length": 2.5, 'cav_relax_delay': 10}
Run2ToneSpec = False
Spec_relevant_params = {
                      # "qubit_gain": 2000, "SpecSpan":420, "SpecNumPoints": 71,
                      #   "qubit_gain": 1000, "SpecSpan": 200, "SpecNumPoints": 71,
                        "qubit_gain": 500, "SpecSpan": 50, "SpecNumPoints": 71,
                        # "qubit_gain": 200, "SpecSpan":20, "SpecNumPoints": 71,
                        'Gauss': False, "sigma": 0.05, "Gauss_gain": 1800,
                        'reps': 144, 'rounds': 1}


Spec_relevant_params = {"qubit_gain": 100, "SpecSpan": 20, "SpecNumPoints": 71,
                        'Gauss': True, "sigma": 0.05, "Gauss_gain": 1240,
                        'reps': 144, 'rounds': 1}

Run_Spec_v_FFgain = False
### Inherits spec parameters from above
FF_sweep_spec_relevant_params = {"qubit_FF_index": 3,
                            "FF_gain_start": 0, "FF_gain_stop": 12000, "FF_gain_steps": 7}

Run_Spec_v_Qblox = False
Spec_v_Qblox_params = {"Qblox_start": -0.8, "Qblox_stop": -0.4, "Qblox_steps": 11, "DAC": 3}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"sigma": 0.07, "max_gain": 5000, 'relax_delay':200}


RunT1 = False
RunT2 = False

T1_params = {"step": 5, "expts": 40, "reps": 15, "rounds": 15}

T2FF = False # Runs one or the other
T2R_params = {"step": 10 * 2.32515e-3, "expts": 125, "reps": 400,
              "freq_shift": 0.0, "phase_step_deg": 26, "relax_delay":200}



SingleShot = True
# SS_params = {"Shots": 5000, "readout_length": 2.5, "adc_trig_delay": 0.3,
#              'number_of_pulses': 1, 'relax_delay': 200}

SS_params = {"Shots": 5000, "readout_length": 3, "adc_trig_delay": 1,
             'number_of_pulses': 1, 'relax_delay': 200}

RunT1_TLS = False
T1TLS_params = {'gainStart': 0, 'gainStop': 0, 'gainNumPoints': 1, 'wait_times': np.linspace(0.01, 150, 31),
                'angle': None, 'threshold': None,
                'meas_shots': 50, 'repeated_nums':10, 'SS_calib_shots': 1500,
                'qubitIndex': 2}#, Qubit_Pulse[0]}


SingleShot_ReadoutOptimize = False
SS_R_params = {"Shots": 1000,
               "gain_start": 4000, "gain_stop": 14000, "gain_pts": 11, "span": 1, "trans_pts": 6, 'number_of_pulses': 1}

SingleShot_QubitOptimize = True
SS_Q_params = {"Shots": 1000,
               "q_gain_span": 500, "q_gain_pts": 5, "q_freq_span": 4, "q_freq_pts": 7,
               'number_of_pulses': 1}

Oscillation_Gain = False
oscillation_gain_dict = {'qubit_FF_index': 4, 'reps': 100,
                         'start': 0, 'step': 4, 'expts': 101,
                         'gainStart': -27500,
                         'gainStop': -25500, 'gainNumPoints': 11, 'relax_delay': 200}
Sweep2D = True

Oscillation_Single = False
# RunChiShift = False
# ChiShift_Params = {'pulse_expt': {'check_12': False},
#                    'qubit_freq01': Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['Frequency'], 'qubit_gain01': 1670 // 2,
#                    'qubit_freq12':  Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['Frequency'],  'qubit_gain12': 1670 // 2}

CalibrationFF_params = {'FFQubitIndex': 3, 'FFQubitExpGain': 3000,
                        "start": 0, "step": 1, "expts": 20 * 16 * 1,
                        "reps": 100, "rounds": 200, "relax_delay": 100, "YPulseAngle": 93,
           }

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


if RunAmplitudeRabi:
    AmplitudeRabiFFMUX(path="AmplitudeRabi", cfg=config | Amplitude_Rabi_params,
                        soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True)

if RunT1:
    T1MUX(path="T1", cfg=config | T1_params, soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_save_display(plotDisp=True)
if RunT2:
    if not T2FF:
        T2RMUX(path="T2R", cfg=config | T2R_params,
                  soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_save_display(plotDisp=True)
    else:
        T2RFF(path="T2RFF", cfg=config | T2R_params,
               soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_save_display(plotDisp=True)


if SingleShot:
    SingleShotFFMUX(path="SingleShot", outerFolder=outerFolder,
                           cfg=config | SS_params, soc=soc,soccfg=soccfg).acquire_save_display(plotDisp=True)
if SingleShot_ReadoutOptimize:
    ReadOpt_wSingleShotFFMUX(path="SingleShot_OptReadout", outerFolder=outerFolder,
                             cfg=config | SS_params | SS_R_params,soc=soc,soccfg=soccfg).acquire_display_save(plotDisp=True)
if SingleShot_QubitOptimize:
    QubitPulseOpt_wSingleShotFFMUX(path="SingleShot_OptQubit", outerFolder=outerFolder,
                                   cfg=config | SS_params | SS_Q_params,soc=soc,soccfg=soccfg).acquire_display_save(plotDisp=True)


if Oscillation_Gain or Oscillation_Single:
    exec(open("CALIBRATE_SINGLESHOT_READOUTS.py").read())

if Oscillation_Gain:
    if Sweep2D:
        GainSweepOscillations(path="GainSweepOscillations", outerFolder=outerFolder,
                              cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)
    else:
        # raise AssertionError('this sweep not working yet.')
        print("Testing arbitrary waveform sweep")
        # GainSweepOscillations(path="GainSweepOscillations", outerFolder=outerFolder,
                              # cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=False)
        GainSweepOscillationsR(path="GainSweepOscillationsR", outerFolder=outerFolder,
                              cfg=config | oscillation_gain_dictR, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)
if Oscillation_Single:
    QubitOscillations(path="QubitOscillations", outerFolder=outerFolder,
                          cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

# TimeDomainSpec(path="TimeDomainSpec", outerFolder=outerFolder,
#                           cfg=config | {'reps': 5,
#                          'start':1, 'step': 16, 'expts': 50,}, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)


# import matplotlib.pyplot as plt
# while True:
#     plt.pause(50)
print(config)

