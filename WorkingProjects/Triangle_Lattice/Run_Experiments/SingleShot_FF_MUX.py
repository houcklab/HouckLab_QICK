# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice.MUXInitialize import *

from WorkingProjects.Triangle_Lattice.Experimental_Scripts_MUX.mTransmissionFFMUX import CavitySpecFFMUX
from WorkingProjects.Triangle_Lattice.Experimental_Scripts_MUX.mSpecSliceFFMUX import QubitSpecSliceFFMUX
# from WorkingProjects.Triangle_Lattice.Experimental_Scripts_MUX.mSpecSliceFFMUX_CW import QubitSpecSliceFFMUXCW
from WorkingProjects.Triangle_Lattice.Experimental_Scripts_MUX.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX
# from WorkingProjects.Triangle_Lattice.Experimental_Scripts_MUX.mChiShiftMUX import ChiShift
from WorkingProjects.Triangle_Lattice.Experimental_Scripts_MUX.mSingleShotProgramFFMUX import SingleShotProgramFFMUX
# from WorkingProjects.Triangle_Lattice.Experimental_Scripts_MUX.mOptimizeReadoutandPulse_FFMUX import ReadOpt_wSingleShotFFMUX, QubitPulseOpt_wSingleShotFFMUX
from WorkingProjects.Triangle_Lattice.Experimental_Scripts_MUX.mT1MUX import T1MUX
from WorkingProjects.Triangle_Lattice.Experimental_Scripts_MUX.mT2RMUX import T2RMUX
from WorkingProjects.Triangle_Lattice.Experimental_Scripts_MUX.mFFvsSpec import FFvsSpec
# from WorkingProjects.Triangle_Lattice.Experimental_Scripts_MUX.mT1_TLS_SSMUX import T1_TLS_SS
import numpy as np

mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq


Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6978.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 15000,
                      "FF_Gains": [0, 0, -2000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4425, 'Gain': 6200},
          'Pulse_FF': [-30000, 0, 0, 0]},  # third index
    '2': {'Readout': {'Frequency': 7095.9 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5000,
                      "FF_Gains": [0, 0, -2000, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4425, 'Gain': 3160},
          'Pulse_FF':[0, 0, -2000, 0]}, # second index
    '3': {'Readout': {'Frequency': 7524.1 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4488, 'Gain': 10900},
          'Pulse_FF': [0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7305.7 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5130,
                      "FF_Gains": [0, 0, 0, 0], 'cavmin': True},
          'Qubit': {'Frequency': 4625.1, 'Gain': 28000},
          'Pulse_FF': [0, 0, 0, 0]}
    }


FF_gain1_expt = 0  # 8000
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0


Qubit_Readout = [1]
Qubit_Pulse = [1]



RunTransmissionSweep = False # determine cavity frequency
Trans_relevant_params = {"reps": 5000, "TransSpan":1.5, "TransNumPoints": 61,
                        "readout_length": 3, 'cav_relax_delay': 10}

Run2ToneSpec = False
Spec_relevant_params = {"qubit_gain": 2000, "SpecSpan":30, "SpecNumPoints": 71,
                        'Gauss': False, "sigma": 0.05, "Gauss_gain": 950,
                        'reps': 10, 'rounds': 10}

Run_Spec_v_FFgain = True
### Inherits spec parameters from above
FF_sweep_spec_relevant_params = {"qubit_FF_index": 3,
                            "FF_gain_start": -30000, "FF_gain_stop":30000, "FF_gain_steps":11,
                                 "qubit_length" : 50}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"sigma": 0.05, "max_gain":10000}

RunT1 = False
RunT2 = False
RunT2E = False


T1T2_params = {"T1_step": 5, "T1_expts": 40, "T1_reps": 25, "T1_rounds": 25,
               "T2_step": 2.32515 * 1e-3 * 7 * 3, "T2_expts": 100, "T2_reps":20, "T2_rounds": 20, "freq_shift": 0.0, "phase_step_deg": 35,
               "relax_delay": 150}
T2E_params = {"T2_step": 0.3, "T2_expts": 150, "T2_reps": 30, "T2_rounds": 30, "freq_shift": 0, "angle_shift": 0,
               "relax_delay": 200,
               "pi2_gain": 10000 // 2}

RunT1_TLS = False
T1TLS_params = {'gainStart': 0, 'gainStop': 0, 'gainNumPoints': 1, 'wait_times': np.linspace(0.01, 150, 31),
                'angle': None, 'threshold': None,
                'meas_shots': 50, 'repeated_nums':10, 'SS_calib_shots': 1500,
                'qubitIndex': 2}#, Qubit_Pulse[0]}

SingleShot = False
SS_params = {"Shots":200, "Readout_Time": 2.5, "ADC_Offset": 0.3, "Qubit_Pulse": Qubit_Pulse,
             'number_of_pulses': 1, 'relax_delay': 250}

Oscillation_Gain = False
oscillation_gain_dict = {'reps': 1000, 'start': int(0), 'step': int(0.25 * 64), 'expts': 121, 'gainStart': 1000,
                         'gainStop': 1300, 'gainNumPoints': 11, 'relax_delay': 150}

SingleShot_ReadoutOptimize = False
SS_R_params = {"gain_start": 3000, "gain_stop": 20000, "gain_pts": 7, "span": 3, "trans_pts": 9, 'number_of_pulses': 1}

SingleShot_QubitOptimize = False
SS_Q_params = {"Optimize_Index": 0, "q_gain_span": 5000, "q_gain_pts": 9, "q_freq_span": 5, "q_freq_pts": 9,
               'number_of_pulses': 1}

RunChiShift = False
ChiShift_Params = {'pulse_expt': {'check_12': False},
                   'qubit_freq01': Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['Frequency'], 'qubit_gain01': 1670 // 2,
                   'qubit_freq12':  Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['Frequency'],  'qubit_gain12': 1670 // 2}


Run2ToneSpecCW = False
Spec_relevant_paramsCW = {"qubit_gain": 150, "SpecSpan": 60, "SpecNumPoints": 51, 'Gauss': False, "sigma": 0.05,
                        "gain": 1230}


# This ends the working section of the file.
#----------------------------------------

# Update FF_Qubits dict
FF_gain1_ro, FF_gain2_ro, FF_gain3_ro, FF_gain4_ro = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['FF_Gains']
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse[0])]['Pulse_FF']

FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1_ro, 'Gain_Expt': FF_gain1_expt, 'Gain_Pulse': FF_gain1_pulse}
FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2_ro, 'Gain_Expt': FF_gain2_expt, 'Gain_Pulse': FF_gain2_pulse}
FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3_ro, 'Gain_Expt': FF_gain3_expt, 'Gain_Pulse': FF_gain3_pulse}
FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4_ro, 'Gain_Expt': FF_gain4_expt, 'Gain_Pulse': FF_gain4_pulse}

BaseConfig['ro_chs'] = [i for i in range(len(Qubit_Readout))]

# Translation of Qubit_Parameters dict to resonator and qubit parameters.
# Nothing defined here should be changed in an Experiment unless it is one of the swept variables.

trans_config = {
    "res_pulse_style": "const",  # --Fixed
    "res_gains": [Qubit_Parameters[str(Q_R)]['Readout']['Gain'] / 32000. * len(Qubit_Readout) for Q_R in Qubit_Readout],  # [DAC units]
    "res_freqs": [Qubit_Parameters[str(Q_R)]['Readout']['Frequency'] for Q_R in Qubit_Readout], # [MHz] actual frequency is this number + "cavity_LO"
    "res_gain": Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Gain'],  # [DAC units]
    "readout_length":Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Readout_Time']
}
qubit_config = {
    "qubit_freqs": [Qubit_Parameters[str(Q)]['Qubit']['Frequency'] for Q in Qubit_Pulse],
    "qubit_gains": [Qubit_Parameters[str(Q)]['Qubit']['Gain'] for Q in Qubit_Pulse],
}
config = BaseConfig | trans_config | qubit_config
config["FF_Qubits"] = FF_Qubits
config["Qubit_Readout_List"] = Qubit_Readout

# This ends the translation of the Qubit_Parameters dict
#--------------------------------------------------
# This begins the booleans

if RunTransmissionSweep:
    config |= Trans_relevant_params
    Instance_trans = CavitySpecFFMUX(path="TransmissionFF", cfg=config, soc=soc, soccfg=soccfg,
                                  outerFolder=outerFolder)

    Instance_trans.acquire_display_save(plotDisp=True, figNum=1)

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
    config |= Spec_relevant_params
    Instance_specSlice = QubitSpecSliceFFMUX(path="QubitSpecFF", cfg=config, soc=soc, soccfg=soccfg,
                                          outerFolder=outerFolder)
    Instance_specSlice.acquire_display_save(plotDisp=True, figNum=2)


if Run_Spec_v_FFgain:
    config |= Spec_relevant_params
    config |= FF_sweep_spec_relevant_params
    Instance_SvFF = FFvsSpec(path="FF_vs_Spec", cfg=config, soc=soc, soccfg=soccfg,
                                          outerFolder=outerFolder)
    Instance_SvFF.acquire_display_save(plotDisp=True, figNum=1)


if RunAmplitudeRabi:

    config |= ARabi_config
    iAmpRabi = AmplitudeRabiFFMUX(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                               outerFolder=outerFolder)
    dAmpRabi = AmplitudeRabiFFMUX.acquire(iAmpRabi)
    AmplitudeRabiFFMUX.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
    AmplitudeRabiFFMUX.save_data(iAmpRabi, dAmpRabi)

#
if RunT1:
    expt_cfg = {"start": 0, "step": T1T2_params["T1_step"], "expts": T1T2_params["T1_expts"],
                "reps": T1T2_params["T1_reps"],
                "rounds": T1T2_params["T1_rounds"], "pi_gain": qubit_gain, "relax_delay": T1T2_params["relax_delay"]
                }

    config = config | expt_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
    iT1 = T1MUX(path="T1", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dT1 = T1MUX.acquire(iT1)
    T1MUX.save_data(iT1, dT1)
    T1MUX.display(iT1, dT1, plotDisp=True, figNum=2)


if RunT2:
    T2R_cfg = {"start": 0, "step": T1T2_params["T2_step"], "phase_step": soccfg.deg2reg(T1T2_params["phase_step_deg"], gen_ch=2),
               "expts": T1T2_params["T2_expts"], "reps": T1T2_params["T2_reps"], "rounds": T1T2_params["T2_rounds"],
               "pi_gain": qubit_gain,
               "pi2_gain": qubit_gain // 2, "relax_delay": T1T2_params["relax_delay"],
               'f_ge': qubit_frequency_center + T1T2_params["freq_shift"]
               }
    config = config | T2R_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
    iT2R = T2RMUX(path="T2R", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dT2R = T2RMUX.acquire(iT2R)
    T2RMUX.save_data(iT2R, dT2R)
    T2RMUX.display(iT2R, dT2R, plotDisp=True, figNum=2)




if SingleShot:
    print(config)
    config['number_of_pulses'] = SS_params['number_of_pulses']
    Instance_SingleShotProgram = SingleShotProgramFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
    # print(data_SingleShotProgram)
    SingleShotProgramFFMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)

    SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
    SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)

if SingleShot_ReadoutOptimize:
    span = SS_R_params['span']
    cav_gain_start = SS_R_params['gain_start']
    cav_gain_stop = SS_R_params['gain_stop']
    cav_gain_pts = SS_R_params['gain_pts']
    cav_trans_pts = SS_R_params['trans_pts']

    exp_parameters = {
        ###### cavity
        "cav_gain_Start": cav_gain_start,
        "cav_gain_Stop": cav_gain_stop,
        "cav_gain_Points": cav_gain_pts,
        "trans_freq_start": config["mixer_freq"] - span / 2, #249.6,
        "trans_freq_stop": config["mixer_freq"] + span / 2, #250.3,
        "TransNumPoints": cav_trans_pts,
    }
    config = config | exp_parameters
    # Now lets optimize powers and readout frequencies
    Instance_SingleShotOptimize = ReadOpt_wSingleShotFFMUX(path="SingleShot_OptReadout", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgramOptimize = ReadOpt_wSingleShotFFMUX.acquire(Instance_SingleShotOptimize)
    # print(data_SingleShotProgram)
    ReadOpt_wSingleShotFFMUX.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)

    ReadOpt_wSingleShotFFMUX.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
    ReadOpt_wSingleShotFFMUX.save_config(Instance_SingleShotOptimize)




if SingleShot_QubitOptimize:
    q_gain_span = SS_Q_params['q_gain_span']
    q_gain_pts = SS_Q_params['q_gain_pts']
    q_freq_pts = SS_Q_params['q_freq_pts']
    q_freq_span = SS_Q_params['q_freq_span']
    Qubit_Pulse_Index = SS_Q_params['Optimize_Index']
    exp_parameters = {
        ###### cavity
        "qubit_gain_Start": qubit_gains[Qubit_Pulse_Index] - q_gain_span / 2,
        "qubit_gain_Stop": qubit_gains[Qubit_Pulse_Index] + q_gain_span / 2,
        "qubit_gain_Points": q_gain_pts,
        "qubit_freq_start": qubit_frequency_centers[Qubit_Pulse_Index] - q_freq_span / 2, #249.6,
        "qubit_freq_stop": qubit_frequency_centers[Qubit_Pulse_Index] + q_freq_span / 2, #250.3,
        "QubitNumPoints": q_freq_pts,
        "number_of_pulses": SS_Q_params["number_of_pulses"]
    }
    config = config | exp_parameters
    # # Now lets optimize powers and readout frequencies
    Instance_SingleShotOptimize = QubitPulseOpt_wSingleShotFFMUX(path="SingleShot_OptQubit", outerFolder=outerFolder,
                                                                 cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgramOptimize = QubitPulseOpt_wSingleShotFFMUX.acquire(Instance_SingleShotOptimize,
                                                                            Qubit_Sweep_Index = Qubit_Pulse_Index)
    # print(data_SingleShotProgram)
    QubitPulseOpt_wSingleShotFFMUX.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)

    QubitPulseOpt_wSingleShotFFMUX.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
    QubitPulseOpt_wSingleShotFFMUX.save_config(Instance_SingleShotOptimize)

if RunT1_TLS:
    config['number_of_pulses'] = 1

    if T1TLS_params['angle'] == None:
        config["shots"] = T1TLS_params['SS_calib_shots']

        Instance_SingleShotProgram = SingleShotProgramFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=config,
                                                            soc=soc, soccfg=soccfg)
        # data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
        data_SingleShotProgram = Instance_SingleShotProgram.acquire()

        angle, threshold = Instance_SingleShotProgram.angle, Instance_SingleShotProgram.threshold
        print(Instance_SingleShotProgram.angle, Instance_SingleShotProgram.threshold)

        # data_SingleShotProgram = SingleShotProgramFFMUX.analyze(Instance_SingleShotProgram, data_SingleShotProgram)

        SingleShotProgramFFMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=False)
        SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
        SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)
    else:
        angle = T1TLS_params['angle']
        threshold = T1TLS_params['threshold']

    config["FF_Qubits"] = FF_Qubits
    config["reps"] = T1TLS_params['meas_shots']

    for key in config["FF_Qubits"].keys():
        config["FF_Qubits"][key]['Gain_Expt'] = config["FF_Qubits"][key]['Gain_Pulse']
    config = config | T1TLS_params

    Instance_T1_TLS = T1_TLS_SS(path="T1_TLS", outerFolder=outerFolder, cfg=config,
                                                        soc=soc, soccfg=soccfg)
    data_T1_TLS = Instance_T1_TLS.acquire(angle = angle, threshold = threshold)
    print()
    # SingleShotProgramFFMUX.display(Instance_T1_TLS, data_T1_TLS, plotDisp=True)
    T1_TLS_SS.save_data(Instance_T1_TLS, data_T1_TLS)
    T1_TLS_SS.save_config(Instance_T1_TLS)


print(config)