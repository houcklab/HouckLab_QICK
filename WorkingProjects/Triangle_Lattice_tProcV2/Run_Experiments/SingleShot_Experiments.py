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
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mGainSweepQubitOscillationsR import \
    GainSweepOscillationsR
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mSingleQubitOscillations import QubitOscillations

from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mTransmissionFFMUX import CavitySpecFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX, SingleShot_2QFFMUX

import numpy as np




Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7121 - BaseConfig["res_LO"], 'Gain': 5000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3525.7, 'sigma': 0.07, 'Gain': 2400},
          # 'Qubit': {'Frequency': 3687, 'sigma': 0.07, 'Gain': 2400},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7077.2 - BaseConfig["res_LO"], 'Gain': 7400,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2, "ADC_Offset": 0.5, 'cavmin': True},
          'Qubit': {'Frequency': 3778.7, 'sigma': 0.07, 'Gain': 3600},
          # 'Qubit': {'Frequency': 3687, 'sigma': 0.07, 'Gain': 3600},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7510.7 - BaseConfig["res_LO"], 'Gain': 5400,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2, "ADC_Offset": 0.5, 'cavmin': True},
          'Qubit': {'Frequency': 3900.3, 'sigma': 0.07, 'Gain': 6250},
          # 'Qubit': {'Frequency': 3687, 'sigma': 0.07, 'Gain': 5600},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
          # 'Pulse_FF': [0, -4000, 0, 0, 0, 0, 0, 0]},
          # 'Pulse_FF': [13317, 0, 0, 0, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568.1 - BaseConfig["res_LO"], 'Gain': 4500,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2, "ADC_Offset": 0.5, 'cavmin': True},
          'Qubit': {'Frequency': 4122, 'sigma': 0.07, 'Gain': 5800},
          # 'Qubit': {'Frequency': 4200, 'sigma': 0.07, 'Gain': 5800},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    'A': {'Readout': {'Frequency': 7121 - BaseConfig["res_LO"], 'Gain': 5000,
                         "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
              'Qubit': {'Frequency': 3621.6, 'sigma': 0.07, 'Gain': 2940},
              'Pulse_FF': [10000, -4000, -6000, -12500, 0, 0, 0, 0]},
    'B': {'Readout': {'Frequency': 7121 - BaseConfig["res_LO"], 'Gain': 5000,
                          "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
              'Qubit': {'Frequency': 3692, 'sigma': 0.07, 'Gain': 4730},
              'Pulse_FF': [10000, -4000, -6000, -12500, 0, 0, 0, 0]},
    'C': {'Readout': {'Frequency': 7121 - BaseConfig["res_LO"], 'Gain': 5000,
                          "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
              'Qubit': {'Frequency': 3732.8, 'sigma': 0.07, 'Gain': 8050},
              'Pulse_FF': [10000, -4000, -6000, -12500, 0, 0, 0, 0]},
    'D': {'Readout': {'Frequency': 7121 - BaseConfig["res_LO"], 'Gain': 5000,
                          "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
              'Qubit': {'Frequency': 3802, 'sigma': 0.07, 'Gain': 2700},
              'Pulse_FF': [10000, -4000, -6000, -12500, 0, 0, 0, 0]},
}

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7122 - BaseConfig["res_LO"], 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4188.4, 'sigma': 0.07, 'Gain': 3450},
          # 'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 2700},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7077.4 - BaseConfig["res_LO"], 'Gain': 7500,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3796.8, 'sigma': 0.07, 'Gain': 2470},
          # 'Qubit': {'Frequency': 4150, 'sigma': 0.07, 'Gain': 2470},
          # 'Qubit': {'Frequency': 3700, 'sigma': 0.07, 'Gain': 2630},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7510.5 - BaseConfig["res_LO"], 'Gain': 7400,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3598, 'sigma': 0.07, 'Gain': 11130},
          # 'Qubit': {'Frequency': 3606.4, 'sigma': 0.07, 'Gain': 11470},
          # 'Qubit': {'Frequency': 3700, 'sigma': 0.07, 'Gain': 10650},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568.5 - BaseConfig["res_LO"], 'Gain': 8100,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4001.1, 'sigma': 0.07, 'Gain': 6850},
          # 'Qubit': {'Frequency': 3997.7, 'sigma': 0.07, 'Gain': 8300},
          # 'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 5300},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    'D': {'Readout': {'Frequency': 7122.1 - BaseConfig["res_LO"], 'Gain': 6000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3799.3, 'sigma': 0.07, 'Gain': 3250},
          # 'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 2700},
          'Pulse_FF': [-16500, -4200, 2000, -9500, 0, 0, 0, 0]},
    'B': {'Readout': {'Frequency': 7077.5 - BaseConfig["res_LO"], 'Gain': 7500,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3700.9, 'sigma': 0.07, 'Gain': 4500},
          # 'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 2630},
          'Pulse_FF': [-16500, -4200, 2000, -9500, 0, 0, 0, 0]},
    'A': {'Readout': {'Frequency': 7510.6 - BaseConfig["res_LO"], 'Gain': 7400,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3647.2, 'sigma': 0.07, 'Gain': 11850},
          # 'Qubit': {'Frequency': 3700, 'sigma': 0.07, 'Gain': 10650},
          'Pulse_FF': [-16500, -4200, 2000, -9500, 0, 0, 0, 0]},
    'C': {'Readout': {'Frequency': 7568.5 - BaseConfig["res_LO"], 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          # 'Qubit': {'Frequency': 4001.1, 'sigma': 0.07, 'Gain': 6710},
          # 'Qubit': {'Frequency': 3743.6, 'sigma': 0.07, 'Gain': 4580},
          'Qubit': {'Frequency': 3755.6, 'sigma': 0.07, 'Gain': 3950},
          # 'Pulse_FF': [-16500, -4200, 2000, -10000, 0, 0, 0, 0]},
          'Pulse_FF': [-16500, -4200, 2000, -9500, 0, 0, 0, 0]},
    'CD': {'Readout': {'Frequency': 7122.1 - BaseConfig["res_LO"], 'Gain': 6000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3799.3, 'sigma': 0.07, 'Gain': 3250},
          # 'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 2700},
          'Pulse_FF': [-16500, -4200, 2000, -9500, 0, 0, 0, 0]},
    'BD': {'Readout': {'Frequency': 7122.1 - BaseConfig["res_LO"], 'Gain': 6000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3800.6, 'sigma': 0.07, 'Gain': 2930},
          # 'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 2700},
          'Pulse_FF': [-16500, -4200, 2000, -9500, 0, 0, 0, 0]},
    'AB': {'Readout': {'Frequency': 7077.5 - BaseConfig["res_LO"], 'Gain': 7500,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3700.9, 'sigma': 0.07, 'Gain': 4500},
          # 'Qubit': {'Frequency': 3750, 'sigma': 0.07, 'Gain': 2630},
          'Pulse_FF': [-16500, -4200, 2000, -9500, 0, 0, 0, 0]},
}

FF_gain1_expt = 0
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0
FF_gain5_expt = 0
FF_gain6_expt = 0
FF_gain7_expt = 0
FF_gain8_expt = 0



Qubit_Readout = [2,3]
Qubit_Pulse   = ['A', 'B']


RunTransmissionSweep = False # determine cavity frequency
Trans_relevant_params = {"reps": 400, "TransSpan": 1.5, "TransNumPoints": 61,
                        "readout_length": 3, 'cav_relax_delay': 10}
Run2ToneSpec = False
Spec_relevant_params = {
                      # "qubit_gain": 2000, "SpecSpan":420, "SpecNumPoints": 71,
                        "qubit_gain": 1000, "SpecSpan": 200, "SpecNumPoints": 71,
                      #   "qubit_gain": 200, "SpecSpan": 50, "SpecNumPoints": 71,
                      #   "qubit_gain": 200, "SpecSpan": 25, "SpecNumPoints": 71,
                        'Gauss': False, "sigma": 0.05, "Gauss_gain": 3200,
                        'reps': 20, 'rounds': 10}


# Spec_relevant_params = {"qubit_gain": 100, "SpecSpan": 20, "SpecNumPoints": 71,
#                         'Gauss': True, "sigma": 0.05, "Gauss_gain": 1260,
#                         'reps': 144, 'rounds': 1}

Run_Spec_v_FFgain = False
### Inherits spec parameters from above

FF_sweep_spec_relevant_params = {"qubit_FF_index": 4,
                            "FF_gain_start": -10500, "FF_gain_stop": -8500, "FF_gain_steps": 11}

# FF_sweep_spec_relevant_params = {"qubit_FF_index": 2,
#                             "FF_gain_start": -5500, "FF_gain_stop": -4500, "FF_gain_steps": 11}
#
# FF_sweep_spec_relevant_params = {"qubit_FF_index": 3,
#                             "FF_gain_start": -8500, "FF_gain_stop": -7000, "FF_gain_steps": 11}



Run_Spec_v_Qblox = False
Spec_v_Qblox_params = {"Qblox_start": 0.4, "Qblox_stop": 1.2, "Qblox_steps": 6, "DAC": 9}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"sigma": 0.07, "max_gain": 20000, 'relax_delay':200}


RunT1 = False
RunT2 = False

T1_params = {"step": 5, "expts": 40, "reps": 15, "rounds": 15}

T2FF = False # Runs one or the other
T2R_params = {"step": 10 * 4.65515e-3, "expts": 125, "reps": 400,
              "freq_shift": 0.0, "phase_step_deg": 26, "relax_delay":200}



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


SingleShot_QubitOptimize = True
SS_Q_params = {"Shots": 1000,
               "q_gain_span": 1000, "q_gain_pts": 7, "q_freq_span": 4, "q_freq_pts": 7,
               'number_of_pulses': 1,
               'qubit_sweep_index': 1}

# SS_Q_params = {"Shots": 500,
#                "q_gain_span": 5000, "q_gain_pts": 6, "q_freq_span": 50, "q_freq_pts": 11,
#                'number_of_pulses': 1,
#                'qubit_sweep_index': 1}

Oscillation_Gain = False
oscillation_gain_dict = {'qubit_FF_index': 2, 'reps': 200,
                         'start': 1, 'step': 20, 'expts': 30,
                         'gainStart': 7000,
                         'gainStop': 10000, 'gainNumPoints': 6, 'relax_delay': 10, 'res_length':10}
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


SS_2Q_params = {"Shots": 5000, 'number_of_pulses': 1, 'relax_delay': 400,
                'second_qubit_freq': 3997.7, 'second_qubit_gain': 8300}


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

