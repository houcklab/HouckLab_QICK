# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import \
    QubitSpecSliceFFMUX
# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mGainSweepQubitOscillations import GainSweepOscillations
# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mSingleQubitOscillations import QubitOscillations
# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mGainSweepQubitOscillationsR import GainSweepOscillationsR
# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mSpecVsQblox import SpecVsQblox
# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mT2R_FF import T2RFF
# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mTime_domain_spectroscopy import TimeDomainSpec
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mTransmissionFFMUX import CavitySpecFFMUX
# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mSpecSliceFFMUX import QubitSpecSliceFFMUX
# # from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mSpecSliceFFMUX_CW import QubitSpecSliceFFMUXCW
# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX
# # from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mChiShiftMUX import ChiShift
# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mSingleShotProgramFFMUX import SingleShotFFMUX
# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mOptimizeReadoutAndPulse import ReadOpt_wSingleShotFFMUX, QubitPulseOpt_wSingleShotFFMUX
# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mT1MUX import T1MUX
# from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mT2RMUX import T2RMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mFFvsSpec import FFvsSpec
# # from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mT1_TLS_SSMUX import T1_TLS_SS
import numpy as np



mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq
BaseConfig["readout_length"] = 2.5

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7122.0 - BaseConfig["res_LO"] , 'Gain': 4000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 3950, 'sigma': 0.05, 'Gain': 2550},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7077. - BaseConfig["res_LO"] , 'Gain': 4000,
                  "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 3792, 'sigma': 0.05, 'Gain': 2260},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7510.5 - BaseConfig["res_LO"] , 'Gain': 4000,
                  "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 3780, 'sigma': 0.05, 'Gain': 3500},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568.1 - BaseConfig["res_LO"] , 'Gain': 4000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4000, 'sigma': 0.05, 'Gain': 3350},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '5': {'Readout': {'Frequency': 7362.8 - BaseConfig["res_LO"] , 'Gain': 4000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
              'Qubit': {'Frequency': 4000, 'sigma': 0.05, 'Gain': 3500},
              'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '6': {'Readout': {'Frequency': 7441.5 - BaseConfig["res_LO"] , 'Gain': 4000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4000, 'sigma': 0.05, 'Gain': 2166},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '7': {'Readout': {'Frequency': 7254.9 - BaseConfig["res_LO"] , 'Gain': 4000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
              'Qubit': {'Frequency': 4000, 'sigma': 0.05, 'Gain': 2500},
              'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '8': {'Readout': {'Frequency': 7309.85 - BaseConfig["res_LO"] , 'Gain': 4000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4100, 'sigma': 0.05, 'Gain': 5600},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    }

FF_gain1_expt = 0
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0
FF_gain5_expt = 0
FF_gain6_expt = 0
FF_gain7_expt = 0
FF_gain8_expt = 0

Qubit_Readout = [5]
Qubit_Pulse = [5]


RunTransmissionSweep = False # determine cavity frequency
Trans_relevant_params = {"reps": 200, "TransSpan": 1.5, "TransNumPoints": 61,
                        "readout_length": 2.5, 'cav_relax_delay': 10}
Run2ToneSpec = True
Spec_relevant_params = {
                      # "qubit_gain": 10000, "SpecSpan":420, "SpecNumPoints": 71,
                      #   "qubit_gain": 5000, "SpecSpan":100, "SpecNumPoints": 201,
                        "qubit_gain": 1000, "SpecSpan":30, "SpecNumPoints": 71,
                        # "qubit_gain": 500, "SpecSpan":20, "SpecNumPoints": 71,
                        'Gauss': False, "sigma": 0.05, "Gauss_gain": 4000,
                        'reps': 15, 'rounds': 15}

Run_Spec_v_FFgain = False
### Inherits spec parameters from above
FF_sweep_spec_relevant_params = {"qubit_FF_index": 2,
                            "FF_gain_start": -30000, "FF_gain_stop":30000, "FF_gain_steps":6}

Run_Spec_v_Qblox = False
Spec_v_Qblox_params = {"Qblox_start":-0.3, "Qblox_stop":-0.2, "Qblox_steps":3, "DAC":9}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"sigma": 0.05, "max_gain":32000, 'relax_delay':200}


RunT1 = False
RunT2 = False

T1_params = {"step": 5, "expts": 40, "reps": 15, "rounds": 15}

T2FF = False # Runs one or the other
T2R_params = {"step": 10 * 2.32515e-3, "expts": 125, "reps": 400,
              "freq_shift": 0.0, "phase_step_deg": 26, "relax_delay":200}



SingleShot = False
SS_params = {"Shots":2000, "readout_length": 2.5, "adc_trig_offset": 0.3,
             'number_of_pulses': 1, 'relax_delay': 200}

RunT1_TLS = False
T1TLS_params = {'gainStart': 0, 'gainStop': 0, 'gainNumPoints': 1, 'wait_times': np.linspace(0.01, 150, 31),
                'angle': None, 'threshold': None,
                'meas_shots': 50, 'repeated_nums':10, 'SS_calib_shots': 1500,
                'qubitIndex': 2}#, Qubit_Pulse[0]}


SingleShot_ReadoutOptimize = False
SS_R_params = {"Shots":500,
               "gain_start": 2000, "gain_stop":20000, "gain_pts": 7, "span": 3, "trans_pts": 6, 'number_of_pulses': 1}

SingleShot_QubitOptimize = False
SS_Q_params = {"Shots":500,
               "q_gain_span": 500, "q_gain_pts": 5, "q_freq_span": 4, "q_freq_pts": 7,
               'number_of_pulses': 1}

Oscillation_Gain = False
oscillation_gain_dict = {'qubit_FF_index': 3, 'reps': 100,
                         'start':0, 'step': 16, 'expts': 61,
                         'gainStart': 15500,
                         'gainStop': 16300, 'gainNumPoints': 6, 'relax_delay': 150}
Sweep2D = False
oscillation_gain_dictR = {'qubit_FF_index': 3, 'reps': 100,
                         'start':0, 'step': 1, 'expts': 61,
                         'gainStart': 15500,
                         'gainStop': 16300, 'gainNumPoints': 6, 'relax_delay': 250}

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
FFReadouts = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['FF_Gains']
FFPulse = Qubit_Parameters[str(Qubit_Pulse[0])]['Pulse_FF']
FFExpt = [FF_gain1_expt, FF_gain2_expt, FF_gain3_expt, FF_gain4_expt, FF_gain5_expt, FF_gain6_expt, FF_gain7_expt, FF_gain8_expt]

for Qubit, FFR, FFE, FFP in zip(('1','2','3','4','5','6','7','8'), FFReadouts, FFExpt, FFPulse):
    FF_Qubits[Qubit] |= {'Gain_Readout': FFR, 'Gain_Expt': FFE, 'Gain_Pulse': FFP}

trans_config = {
    "res_gains": [Qubit_Parameters[str(Q_R)]['Readout']['Gain'] / 32766. * len(Qubit_Readout) for Q_R in Qubit_Readout],  # [DAC units]
    "res_freqs": [Qubit_Parameters[str(Q_R)]['Readout']['Frequency'] for Q_R in Qubit_Readout], # [MHz] actual frequency is this number + "cavity_LO"
    "readout_length":Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Readout_Time']
}
qubit_config = {
    "qubit_freqs": [Qubit_Parameters[str(Q)]['Qubit']['Frequency'] for Q in Qubit_Pulse],
    "qubit_gains": [Qubit_Parameters[str(Q)]['Qubit']['Gain'] / 32766. for Q in Qubit_Pulse],
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