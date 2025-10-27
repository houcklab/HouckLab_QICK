# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mGainSweepQubitOscillations import GainSweepOscillations
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mSingleQubitOscillations import QubitOscillations
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mGainSweepQubitOscillationsR import GainSweepOscillationsR
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mSpecVsQblox import SpecVsQblox
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mT2R_FF import T2RFF
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mTime_domain_spectroscopy import TimeDomainSpec
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.MUXInitialize import *

from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mTransmissionFFMUX import CavitySpecFFMUX
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mSpecSliceFFMUX import QubitSpecSliceFFMUX
# from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts.mSpecSliceFFMUX_CW import QubitSpecSliceFFMUXCW
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX
# from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts.mChiShiftMUX import ChiShift
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mSingleShotProgramFFMUX import SingleShotFFMUX
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mOptimizeReadoutAndPulse import ReadOpt_wSingleShotFFMUX, QubitPulseOpt_wSingleShotFFMUX
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mT1MUX import T1MUX
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mT2RMUX import T2RMUX
from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts_MUX.mFFvsSpec import FFvsSpec
# from WorkingProjects.Legacy_Triangle_Lattice_tProcV1.Experimental_Scripts.mT1_TLS_SSMUX import T1_TLS_SS
import numpy as np



mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq


Qubit_Parameters = {
# center_freq = (7.1225)*1e9; % Q1
#
# % center_freq = (7.077)*1e9;  % Q2
#
# % center_freq = (7.511)*1e9;  % Q3
#
# % center_freq = (7.569)*1e9;  % Q4
#
# % center_freq = (7.3633)*1e9;  % Q5
#
# % center_freq = (7.440)*1e9; % Q6
#
# % center_freq = (7.255)*1e9;  % Q7
#
# % center_freq = (7.310)*1e9;  % Q8
    '1': {'Readout': {'Frequency': 7122.3 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain':3000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4413.2, 'sigma': 0.05, 'Gain': 1650},
          'Pulse_FF': [0, 0, 0, 0]},  # Third index
    '2': {'Readout': {'Frequency': 7077.2 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 2500,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 3599, 'sigma': 0.05, 'Gain': 3200},
          'Pulse_FF': [0, 0, 0, 0]},  # Fourth index
    '3': {'Readout': {'Frequency': 7511.2 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 4500,
              "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
      'Qubit': {'Frequency': 4226.1, 'sigma': 0.05, 'Gain': 2970},
      'Pulse_FF': [0, 0, 0, 0]},  # third index
    '4': {'Readout': {'Frequency': 7568.4 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5000,
                  "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
      'Qubit': {'Frequency': 3947.6, 'sigma': 0.05, 'Gain': 3880},
      'Pulse_FF': [0, 0, 0, 0]},
    '5': {'Readout': {'Frequency': 7362.8 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 4000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
              'Qubit': {'Frequency': 3800, 'sigma': 0.05, 'Gain': 3500},
              'Pulse_FF': [0, 0, 0, 0]},  # third index
    '6': {'Readout': {'Frequency': 7440.4 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7600,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
              'Qubit': {'Frequency': 3932.5, 'sigma': 0.05, 'Gain': 2840},
              'Pulse_FF': [0, 0, 0, 0]},  # third index
    '7': {'Readout': {'Frequency': 7253.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6800,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
              'Qubit': {'Frequency': 3932.7, 'sigma': 0.05, 'Gain': 2500},
              'Pulse_FF': [0, 0, 0, 0]},  # third index
    # '8': {'Readout': {'Frequency': 7308.3 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
    #                   "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
    #           'Qubit': {'Frequency': 3954, 'sigma': 0.05, 'Gain': 3000},
    #           'Pulse_FF': [0, 0, 0, 0]},  # third index
    '8': {'Readout': {'Frequency': 7308.3 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4024, 'sigma': 0.05, 'Gain': 3000},
          'Pulse_FF': [0, 0, 0, 0]},  # third index
    }





FF_gain1_expt = 0  # 8000
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0

FF_gain1_BS = 0
FF_gain2_BS = 0
FF_gain3_BS = 0
FF_gain4_BS = 0

Qubit_Readout = [3]
Qubit_Pulse = [3]

RunTransmissionSweep = False # determine cavity frequency
Trans_relevant_params = {"reps": 400, "TransSpan": 1.5, "TransNumPoints": 71,
                        "readout_length": 2.5, 'cav_relax_delay': 10}
Run2ToneSpec = True
Spec_relevant_params = {"qubit_gain": 2000, "SpecSpan": 200, "SpecNumPoints": 71,
                        'Gauss': False, "sigma": 0.05, "Gauss_gain": 2840,
                        'reps': 20, 'rounds': 20}


Spec_relevant_params = {"qubit_gain": 200, "SpecSpan": 50, "SpecNumPoints": 71,
                        'Gauss': False, "sigma": 0.05, "Gauss_gain": 5640,
                        'reps': 20, 'rounds': 20}


Spec_relevant_params = {"qubit_gain": 100, "SpecSpan":20, "SpecNumPoints": 71,
                        'Gauss': True, "sigma": 0.05, "Gauss_gain": 2460,
                        'reps': 225, 'rounds': 1}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"sigma": 0.05, "max_gain": 15000, 'relax_delay':200}


Run_Spec_v_FFgain = False
### Inherits spec parameters from above
FF_sweep_spec_relevant_params = {"qubit_FF_index": 3,
                            "FF_gain_start": 0, "FF_gain_stop": -15000, "FF_gain_steps": 6}


Run_Spec_v_Qblox = False
# dac is 1 indexed
Spec_v_Qblox_params = {"Qblox_start": -0.3, "Qblox_stop": 0,
                       "Qblox_steps": 11, "DAC": 3}




RunT1 = False
RunT2 = False

T1_params = {"step": 2, "expts": 40, "reps": 20, "rounds": 20}

T2FF = False # Runs one or the other
T2R_params = {"step": 10 * 2.32515e-3, "expts": 125, "reps": 400,
              "freq_shift": 0.0, "phase_step_deg": 26, "relax_delay":200}



SingleShot = False
SS_params = {"Shots": 5000, "readout_length": 3, "adc_trig_offset": 0.3,
             'number_of_pulses': 1, 'relax_delay': 200}

RunT1_TLS = False
T1TLS_params = {'gainStart': 0, 'gainStop': 0, 'gainNumPoints': 1, 'wait_times': np.linspace(0.01, 150, 31),
                'angle': None, 'threshold': None,
                'meas_shots': 50, 'repeated_nums':10, 'SS_calib_shots': 1500,
                'qubitIndex': 2}#, Qubit_Pulse[0]}


SingleShot_ReadoutOptimize = False
SS_R_params = {"Shots":500,
               "gain_start": 3000, "gain_stop": 10000, "gain_pts": 11, "span": 4, "trans_pts": 11, 'number_of_pulses': 1}

SingleShot_QubitOptimize = False
SS_Q_params = {"Shots":500,
               "q_gain_span": 3000, "q_gain_pts": 11, "q_freq_span": 15, "q_freq_pts": 11,
               'number_of_pulses': 1}


Oscillation_Gain = False
oscillation_gain_dict = {'qubit_FF_index': 3, 'reps': 200,
                         'start':0, 'step': 8, 'expts': 301,
                         'gainStart': -18000, 'gainStop': -13500, 'gainNumPoints': 41, 'relax_delay': 150}

# high quality
# oscillation_gain_dict = {'qubit_FF_index': 4, 'reps': 200,
#                          'start':0, 'step': 20, 'expts': 201,
#                          'gainStart': 3500, 'gainStop': 5000, 'gainNumPoints': 41, 'relax_delay': 150}

Sweep2D = True
# oscillation_gain_dictR = {'qubit_FF_index': 3, 'reps': 100,
#                          'start':0, 'step': 1, 'expts': 61,
#                          'gainStart': -3000, 'gainStop': -5000, 'gainNumPoints': 11, 'relax_delay': 250}

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

# Translation of Qubit_Parameters dict to resonator and qubit parameters.
# Nothing defined here should be changed in an Experiment unless it is one of the swept variables.
# Update FF_Qubits dict
FF_gain1_ro, FF_gain2_ro, FF_gain3_ro, FF_gain4_ro = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['FF_Gains']
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse[0])]['Pulse_FF']

FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1_ro, 'Gain_Expt': FF_gain1_expt, 'Gain_Pulse': FF_gain1_pulse}
FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2_ro, 'Gain_Expt': FF_gain2_expt, 'Gain_Pulse': FF_gain2_pulse}
FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3_ro, 'Gain_Expt': FF_gain3_expt, 'Gain_Pulse': FF_gain3_pulse}
FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4_ro, 'Gain_Expt': FF_gain4_expt, 'Gain_Pulse': FF_gain4_pulse}

trans_config = {
    "res_gains": [Qubit_Parameters[str(Q_R)]['Readout']['Gain'] / 32000. * len(Qubit_Readout) for Q_R in Qubit_Readout],  # [DAC units]
    "res_freqs": [Qubit_Parameters[str(Q_R)]['Readout']['Frequency'] for Q_R in Qubit_Readout], # [MHz] actual frequency is this number + "cavity_LO"
    # "res_gain": Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Gain'],  # [DAC units]
    "readout_length":Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Readout_Time']
}
qubit_config = {
    "qubit_freqs": [Qubit_Parameters[str(Q)]['Qubit']['Frequency'] for Q in Qubit_Pulse],
    "qubit_gains": [Qubit_Parameters[str(Q)]['Qubit']['Gain'] for Q in Qubit_Pulse],
    "sigma" : Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['sigma']
}
config = BaseConfig | trans_config | qubit_config
config["FF_Qubits"] = FF_Qubits
config["Qubit_Readout_List"] = Qubit_Readout
config['ro_chs'] = [i for i in range(len(Qubit_Readout))]

# This ends the translation of the Qubit_Parameters dict
#--------------------------------------------------
# This begins the booleans

if RunTransmissionSweep:
    Instance_trans = CavitySpecFFMUX(path="TransmissionFF", cfg=config | Trans_relevant_params,
                                     soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    print(Instance_trans.cfg)
    Instance_trans.acquire_display_save(plotDisp=True)

    # update the transmission frequency to be the peak
    if Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['cavmin']:
        config["res_freqs"][0] += Instance_trans.peakFreq_min - mixer_freq
        config["mixer_freq"] = Instance_trans.peakFreq_min
    else:
        config["res_freqs"][0] += Instance_trans.peakFreq_max - mixer_freq
        config["mixer_freq"] = Instance_trans.peakFreq_max
    print("Cavity frequency found at: ", config["res_freqs"][0] + mixer_freq + BaseConfig["cavity_LO"] / 1e6)
else:
    print("Cavity frequency set to: ", config["res_freqs"][0] + mixer_freq + BaseConfig["cavity_LO"] / 1e6)


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



def characterize_readout(config, Qubit_Readout):
    '''Characterize qubits at the current readout point to return angle, threshold, and confusion_matrix for each.
    trans_config remains the same because we want to know the readout error under the MUXed pulse we will use.'''
    angle, threshold, confusion_matrix = [], [], []

    new_config = config.copy()
    new_config["Shots"] = 2000

    for ro_ind, Qubit in enumerate(Qubit_Readout):
        '''Pulse each at a time, using the QubitParameters Pulse parameters'''
        new_config["qubit_freqs"] = [Qubit_Parameters[str(Qubit)]['Qubit']['Frequency']]
        new_config["qubit_gains"] = [Qubit_Parameters[str(Qubit)]['Qubit']['Gain']]
        new_config['sigma']       =  Qubit_Parameters[str(Qubit)]['Qubit']['sigma']

        FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit)]['Pulse_FF']
        new_config["FF_Qubits"]['1']['Gain_Pulse'] = FF_gain1_pulse
        new_config["FF_Qubits"]['2']['Gain_Pulse'] = FF_gain2_pulse
        new_config["FF_Qubits"]['3']['Gain_Pulse'] = FF_gain3_pulse
        new_config["FF_Qubits"]['4']['Gain_Pulse'] = FF_gain4_pulse

        SSExp = SingleShotFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=new_config, soc=soc, soccfg=soccfg)
        data = SSExp.acquire_display_save(plotDisp=True, block=False, display_indices=[Qubit])

        angle.append(    data['data']['angle'][ro_ind])
        threshold.append(data['data']['threshold'][ro_ind])
        ng_contrast = data['data']['ng_contrast'][ro_ind]
        ne_contrast = data['data']['ne_contrast'][ro_ind]
        conf_mat = np.array([[1 - ng_contrast, ne_contrast],
                             [ng_contrast, 1 - ne_contrast]])
        confusion_matrix.append(conf_mat)

    return angle, threshold, confusion_matrix




if Oscillation_Gain or Oscillation_Single:
    angle, threshold, confusion_matrix = characterize_readout(config, Qubit_Readout)
    config['angle'], config['threshold'], config['confusion_matrix'] = angle, threshold, confusion_matrix

# if use_confusion_matrix == False:
    # config['confusion_matrix'] = None

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