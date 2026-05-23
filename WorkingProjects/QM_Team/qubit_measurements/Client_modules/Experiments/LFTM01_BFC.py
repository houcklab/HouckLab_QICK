# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import *
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.socProxy import *
import json
import os
import time
import numpy as np
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mTransmissionFF import CavitySpecFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleTone import SingleTone

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSpecSliceFF import QubitSpecSliceFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAmplitudeRabiFF import AmplitudeRabiFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAmplitudeRabiFF_noUpdate import AmplitudeRabiFF_N
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mChiShift import ChiShift
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mACStarkShift import ACStarkShift

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1FF import T1FF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2R import T2R
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2EFF import T2EMUX
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleShotProgramFFMUX import SingleShotProgramFFMUX
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1_SS import T1_SS
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mOptimizeReadoutandPulse_FF import ReadOpt_wSingleShotFF, QubitPulseOpt_wSingleShotFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mRB import (
    LIBRARY_AVG_PRIMITIVES_PER_CLIFFORD,
    SingleQubitRB,
)

# from q4diamond.Client_modules.Experiment_Scripts.mT2R import T2R
# from q4diamond.Client_modules.Experiment_Scripts.mChiShift import ChiShift
# from q4diamond.Client_modules.Experiment_Scripts.mSingleShotProgramFF import SingleShotProgramFF
# from q4diamond.Client_modules.Experiment_Scripts.mOptimizeReadoutandPulse_FF import ReadOpt_wSingleShotFF, QubitPulseOpt_wSingleShotFF

soc, soccfg = makeProxy()

############## New TATQ03 (No Charge Lines) ############################
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 4699.14, 'Gain': 1000}, #900 seems to be consistent # res found again # 400 okay for good transmission
          'Qubit': {'Frequency': 1263.035171, 'Gain': 6020,'pi2_Gain' : 6020//2, "sigma": 1.5, "flattop_length": None}, # qubit found again previous frequency 1263.228
          'outerfoldername':"V:/t1Team/Data/2026-05-20_BFC_cooldown/LFTM01/RFSOC/Q1//"},# 2840
    '2': {'Readout': {'Frequency': 4909.554495, 'Gain': 148}, # 148 okay for good transmission, 250 too much.
          'Qubit': {'Frequency': 1144.787819, 'Gain': 1300, 'pi2_Gain' : 1300 // 2, "sigma": 0.1, "flattop_length": None}, # pi pulse gain: 4164  'Gain': 1300, 'pi2_Gain' : 1300 // 2, "sigma": 0.1, "flattop_length": None
          'outerfoldername':"V:/t1Team/Data/2026-05-20_BFC_cooldown/LFTM01/RFSOC/Q2//"},
    }
############## End Can D ############################

# Readout
Qubit_Readout = 1
Qubit_Pulse = 1
outerFolder = Qubit_Parameters[str(Qubit_Readout)]['outerfoldername']

ConstantTone = False  # determine cavity frequency

RunTransmissionSweep = True # determine cavity frequency
Transmission_params = {'reps': 10, 'rounds': 10, 'num_points' : 501, 'span': 100}

Run2ToneSpec =  False
RunTrans_QubitSpec = False
Spec_relevant_params = {"qubit_gain": 100, "SpecSpan": 0.75, "SpecNumPoints": 101,
                        "reps": 10, 'rounds': 10,
                        'Gauss': True, "sigma": 2, "gain": 90,
                        'relax_delay': 5000, 'qubit_length' : 100,
                        "display": True, 'min_sep_MHz': 1,
                        "fit_window_mhz": 0.5, "prominent_ratio": 0.1,
                        } # False -- no pulse #If you don't see RabiAmp but with Gauss True see the qubit, the next thing to check is gain, you might not have the right pi pulse

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
                         "max_gain": 3000, 'number_of_steps': 101,
                         "reps": 10, 'rounds': 10,
                         'relax_delay': 5000,
                         "fit": False}  #Always change the max gain if you don't see it, also compare what you get with Transmission data

RunRB = False
RB_params = {
    "lengths": [1, 2, 4, 8, 16, 24, 32, 48, 64, 80, 96],
    "nseeds": 50,
    "reps": 500,
    "rounds": 1,
    "seed": 1234,
    "relax_delay": 5000,
    "gate_spacing": 0.02,
    "post_sequence_delay": 0.05,
    "fit_primitives_per_clifford": LIBRARY_AVG_PRIMITIVES_PER_CLIFFORD,
    "display": False,
}

RunRBLengthSweep = False
RBLengthSweep_params = {
    "qubits": ["1", "2"], # ["1", "2"]
    "full_sweep_repetitions": 1,
    "inter_sweep_delay_s": 0.0,
    "sigma_sweeps": {
        "1": {
            "sigmas": [1.5, 1.25, 1, 0.75, 0.5, 0.25],
            "rabi_max_gains": [10000, 12000, 15000, 20000, 30000, 64000],
        },
        "2": {
            "sigmas": [0.25, 0.125, 0.12, 0.11, 0.1, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.02, 0.01],
            "rabi_max_gains": [2600,5200, 5200, 6000, 7000,  7800, 9000,10000,12000, 12000, 18000, 23000, 32000, 60000],
        },
    },
    "rabi_points": 501,
    "rabi_reps": 20,
    "rabi_rounds": 20,
    "rabi_fit_channel_preference": "Q",
    "rabi_max_attempts_per_sigma": 5,
    "rabi_retry_delay_s": 0.0,
    "rabi_require_both_fits": True,
    "rabi_fit_max_gain_disagreement_fraction": 0.1,
    "rabi_fit_allowed_overshoot_fraction": 0.05,
    "rb_lengths": RB_params["lengths"],
    "rb_nseeds": RB_params["nseeds"],
    "rb_reps": RB_params["reps"],
    "rb_rounds": RB_params["rounds"],
    "rb_seed": RB_params["seed"],
    "rb_relax_delay": RB_params["relax_delay"],
    "rb_gate_spacing": RB_params["gate_spacing"],
    "rb_post_sequence_delay": RB_params["post_sequence_delay"],
    "rb_fit_primitives_per_clifford": LIBRARY_AVG_PRIMITIVES_PER_CLIFFORD,
    "display_rabi": False,
    "display_rb": False,
}

RunChiShift = False
ChiShift_params = {"reps": 10,
                    'rounds': 10,# this will used for all experiements below unless otherwise changed in between trials
                    "TransSpan": 1,  ### MHz, span will be center+/- this parameter
                    "TransNumPoints": 101,
                    "cavity_shift": 0.0,
                    "relax_delay": 5000}

RunACStarkShift = False
ACStark_params = {
    "stark_freq": Qubit_Parameters[str(Qubit_Readout)]['Readout']['Frequency'],
    "stark_gain_start": 0,
    "stark_gain_stop": 1200,
    "stark_gain_points": 25,
    "stark_length": 20,
    "stark_t0": 0.01,
    "stark_qubit_delay": 0.10,
    "post_stark_wait": 0.05,
    "qubit_freq_center": Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
    "qubit_freq_span": 8,
    "qubit_freq_points": 161,
    "qubit_gain": 100,
    "reps": 20,
    "rounds": 20,
    "relax_delay": 5000,
    "fit_window_pts": 11,
    "display": True,
}

RunT1 = False
RunT2 = False
T1T2_params = {"T1_step": 60, "T1_expts": 60, "T1_reps": 20, "T1_rounds": 20, # 80 100 30 30
               "T2_step": 2, "T2_expts": 300, "T2_reps": 20, "T2_rounds": 20, "freq_shift": 0.0,
               "relax_delay": 5000,
               'repetitions': 3000}

RunT1T2E = False

RunT1T2RT2E = False

RunT2E = False
T2E_params = {"T2_max_us": 3600, "T2_expts": 101, "T2_reps": 25, "T2_rounds": 25, "freq_shift": 0.0,
               "relax_delay": 5000, 'num_pi_pulses': 1, #need odd number of pulses
              "rotation_angle": None,
              "min_max": None,
              'repetitions': 3000}

SingleShot = False
SS_params = {"Shots": 1000, "Readout_Time": 25, "ADC_Offset": 1, "Qubit_Pulse": [Qubit_Pulse],
             'number_of_pulses': 1, 'relax_delay': 5000}

RunT1SS = False
T1SS_params = {"T1_step": 80, "T1_expts": 100,
               "reps": 2000,
               'angle': 0, 'threshold': 0,
               "relax_delay": 8000,
               'calibrate_SS': True,
               'repetitions': 11}

SingleShot_ReadoutOptimize = False
SS_R_params = {"gain_start": 100, "gain_stop": 500, "gain_pts": 50, "span": 0.01, "trans_pts": 3}

SingleShot_QubitOptimize = False
SS_Q_params = {"q_gain_span": 100, "q_gain_pts": 201, "q_freq_span": 0.05, "q_freq_pts": 5,
               'number_of_pulses': 5} # for optimizing pi/2 pulse, set the gain to the half of its value and optimize for n=2


cavity_gain = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Gain']
resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Frequency']
qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain']
pi2_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['pi2_Gain']
qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency']

qubit_sigma = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['sigma']
qubit_flattop = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['flattop_length']

trans_config = {
    "reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
    "pulse_style": "const",  # --Fixed
    "readout_length": 30,  # 15 [us]
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
    "qubit_length": 100, # 20, 100
    "SpecSpan": Spec_relevant_params["SpecSpan"],  ### MHz, span will be center+/- this parameter
    "SpecNumPoints": Spec_relevant_params["SpecNumPoints"],  ### number of points in the transmission frequecny
}
expt_cfg = {
    "step": 2 * qubit_config["SpecSpan"] / qubit_config["SpecNumPoints"],
    "start": qubit_config["qubit_freq"] - qubit_config["SpecSpan"],
    "expts": qubit_config["SpecNumPoints"]
}

UpdateConfig = trans_config | qubit_config | expt_cfg
config = BaseConfig | UpdateConfig  ### note that UpdateConfig will overwrite elements in BaseConfig
print(config)
config["FF_Qubits"] = FF_Qubits

#### update the qubit and cavity attenuation
# cavityAtten.SetAttenuation(config["cav_Atten"], printOut=True)

if ConstantTone:
    Instance_trans = SingleTone(path="TransmissionFF", cfg=config, soc=soc, soccfg=soccfg,
                                  outerFolder=outerFolder)
    data_trans = SingleTone.acquire(Instance_trans)

cavity_min = True
config["cavity_min"] = cavity_min  # look for dip, not peak

# perform the cavity transmission experiment
if RunTransmissionSweep:
    config["reps"] = 20  # fast axis number of points
    config["rounds"] = 20  # slow axis number of points
    Instance_trans = CavitySpecFF(path="TransmissionFF", cfg=config, soc=soc, soccfg=soccfg,
                                  outerFolder=outerFolder)
    data_trans = CavitySpecFF.acquire(Instance_trans)
    CavitySpecFF.display(Instance_trans, data_trans, plotDisp=True, figNum=1)
    CavitySpecFF.save_data(Instance_trans, data_trans)
    CavitySpecFF.save_config(Instance_trans)

    # update the transmission frequency to be the peak
    if cavity_min:
        config["pulse_freq"] = Instance_trans.peakFreq_min
    else:
        config["pulse_freq"] = Instance_trans.peakFreq_max
    print("Cavity frequency found at: ", config["pulse_freq"])
else:
    print("Cavity frequency set to: ", config["pulse_freq"])



if Run2ToneSpec:
    config["reps"] = Spec_relevant_params['reps']
    config["rounds"] = Spec_relevant_params['rounds']
    config["Gauss"] = Spec_relevant_params['Gauss']
    if Spec_relevant_params['Gauss']:
        config['sigma'] = Spec_relevant_params["sigma"]
        config["qubit_gain"] = Spec_relevant_params['gain']
        config["qubit_gain"] = Spec_relevant_params['gain']

    config["qubit_length"] = Spec_relevant_params["qubit_length"]
    config["SpecSpan"] = Spec_relevant_params["SpecSpan"]
    config["SpecNumPoints"] = Spec_relevant_params["SpecNumPoints"]
    config["step"] = 2 * config["SpecSpan"] / config["SpecNumPoints"]
    config["start"] = qubit_frequency_center - config["SpecSpan"]
    config["expts"] = config["SpecNumPoints"]
    config['relax_delay'] = Spec_relevant_params['relax_delay']
    display = Spec_relevant_params['display']
    min_sep = Spec_relevant_params['min_sep_MHz']

    Instance_specSlice = QubitSpecSliceFF(
        path="QubitSpecFF",
        cfg=config,
        soc=soc,
        soccfg=soccfg,
        outerFolder=outerFolder
    )
    data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
    QubitSpecSliceFF.display(Instance_specSlice, data_specSlice, plotDisp=display, figNum=2, min_sep=min_sep,
                             fit_window_mhz = 0.5, prominent_ratio = 0.1) # can change to True
    QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)
    QubitSpecSliceFF.save_config(Instance_specSlice)

if RunChiShift:
    updated_params = {
        "pi_gain": qubit_gain,
        "sigma": qubit_sigma, "f_ge": Amplitude_Rabi_params["qubit_freq"],
        "flattop_length": qubit_flattop
    }
    config = config | ChiShift_params | updated_params
    iChi = ChiShift(path="ChiShift", cfg=config, soc=soc, soccfg=soccfg,
                    outerFolder=outerFolder)
    dChi = ChiShift.acquire(iChi)
    ChiShift.display(iChi, dChi, plotDisp=True, figNum=1)
    ChiShift.save_data(iChi, dChi)
    ChiShift.save_config(iChi)

if RunACStarkShift:
    ac_stark_cfg = {
        "Qubit_number": Qubit_Pulse,
        "stark_freq": ACStark_params["stark_freq"],
        "stark_gain_start": ACStark_params["stark_gain_start"],
        "stark_gain_stop": ACStark_params["stark_gain_stop"],
        "stark_gain_points": ACStark_params["stark_gain_points"],
        "stark_length": ACStark_params["stark_length"],
        "stark_t0": ACStark_params["stark_t0"],
        "stark_qubit_delay": ACStark_params["stark_qubit_delay"],
        "post_stark_wait": ACStark_params["post_stark_wait"],
        "qubit_gain": ACStark_params["qubit_gain"],
        "sigma": qubit_sigma,
        "flattop_length": qubit_flattop,
        "readout_length": trans_config["readout_length"],
        "reps": ACStark_params["reps"],
        "rounds": ACStark_params["rounds"],
        "relax_delay": ACStark_params["relax_delay"],
        "start": ACStark_params["qubit_freq_center"] - ACStark_params["qubit_freq_span"],
        "step": 2 * ACStark_params["qubit_freq_span"] / ACStark_params["qubit_freq_points"],
        "expts": ACStark_params["qubit_freq_points"],
        "stark_fit_window_pts": ACStark_params["fit_window_pts"],
    }

    config_ac_stark = config | ac_stark_cfg
    iACStark = ACStarkShift(
        path="ACStarkShift",
        cfg=config_ac_stark,
        soc=soc,
        soccfg=soccfg,
        outerFolder=outerFolder,
    )
    dACStark = ACStarkShift.acquire(iACStark)
    ACStarkShift.display(iACStark, dACStark, plotDisp=ACStark_params["display"], figNum=2)
    ACStarkShift.save_data(iACStark, dACStark)
    ACStarkShift.save_config(iACStark)

# Amplitude Rabi
  ### note that UpdateConfig will overwrite elements in BaseConfig

if RunAmplitudeRabi:
    number_of_steps = Amplitude_Rabi_params["number_of_steps"]
    step = int(Amplitude_Rabi_params["max_gain"] / number_of_steps)
    ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps, "reps": Amplitude_Rabi_params['reps'],
                    "rounds": Amplitude_Rabi_params['rounds'],
                    "sigma": qubit_sigma, "f_ge": Amplitude_Rabi_params["qubit_freq"],
                    "relax_delay": Amplitude_Rabi_params["relax_delay"],
                    "flattop_length": qubit_flattop,
                    "Qubit_number": Qubit_Pulse}

    fit = Amplitude_Rabi_params["fit"]

    config = config | ARabi_config
    if qubit_flattop != None:
        ARabi_config = {'gain_start': 0, "gain_end": Amplitude_Rabi_params["max_gain"],
                        'gainNumPoints': number_of_steps,
                        "reps": Amplitude_Rabi_params['reps'],
                        "rounds": Amplitude_Rabi_params['rounds'],
                        "sigma": qubit_sigma, "f_ge": Amplitude_Rabi_params["qubit_freq"],
                        "relax_delay": 5000,
                        "flattop_length": qubit_flattop}
        config = config | ARabi_config  ### note that UpdateConfig will overwrite elements in BaseConfig
        iAmpRabi = AmplitudeRabiFF_N(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                                   outerFolder=outerFolder)
        dAmpRabi = AmplitudeRabiFF_N.acquire(iAmpRabi)
        AmplitudeRabiFF_N.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
        AmplitudeRabiFF_N.save_data(iAmpRabi, dAmpRabi)
        AmplitudeRabiFF_N.save_config(iAmpRabi)
    else:
        iAmpRabi = AmplitudeRabiFF(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                                   outerFolder=outerFolder)
        dAmpRabi = AmplitudeRabiFF.acquire(iAmpRabi)
        AmplitudeRabiFF.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2, fit=fit)
        AmplitudeRabiFF.save_data(iAmpRabi, dAmpRabi)
        AmplitudeRabiFF.save_config(iAmpRabi)

if RunRB:
    rb_cfg = {
        "Qubit_number": Qubit_Pulse,
        "f_ge": qubit_frequency_center,
        "sigma": qubit_sigma,
        "pi_gain": qubit_gain,
        "pi2_gain": pi2_gain,
        "flattop_length": qubit_flattop,
        "relax_delay": RB_params["relax_delay"],
        "rb_lengths": RB_params["lengths"],
        "rb_nseeds": RB_params["nseeds"],
        "rb_reps": RB_params["reps"],
        "rb_rounds": RB_params["rounds"],
        "rb_seed": RB_params["seed"],
        "rb_gate_spacing": RB_params["gate_spacing"],
        "rb_post_sequence_delay": RB_params["post_sequence_delay"],
        "rb_gate_fidelity_primitives_per_clifford": RB_params["fit_primitives_per_clifford"],
    }

    config_rb = config | rb_cfg
    iRB = SingleQubitRB(path="RB", cfg=config_rb, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dRB = SingleQubitRB.acquire(iRB)
    SingleQubitRB.display(iRB, dRB, plotDisp=RB_params["display"], figNum=2)
    SingleQubitRB.save_data(iRB, dRB)
    SingleQubitRB.save_config(iRB)

if RunT1:
    for i in range(T1T2_params['repetitions']):
        if T1T2_params['repetitions'] > 1:
            plot_disp = False
        else:
            plot_disp = True
        expt_cfg = {"start": 0, "step": T1T2_params["T1_step"], "expts": T1T2_params["T1_expts"],
                    "reps": T1T2_params["T1_reps"],"Qubit_number": Qubit_Readout,
                    "rounds": T1T2_params["T1_rounds"], "pi_gain": qubit_gain, "relax_delay": T1T2_params["relax_delay"],
                    "sigma": qubit_sigma, "flattop_length": qubit_flattop,
                    "f_ge": qubit_frequency_center
                    }

        config = config | expt_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
        iT1 = T1FF(path="T1", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        dT1 = T1FF.acquire(iT1)
        T1FF.display(iT1, dT1, plotDisp=plot_disp, figNum=2)
        T1FF.save_data(iT1, dT1)
        T1FF.save_config(iT1)

        time.sleep(10)
        soc.reset_gens()

if RunT1T2E:
    for i in range(T1T2_params['repetitions']):
        # match your plotting behavior
        plot_disp = (T1T2_params['repetitions'] <= 1)

        # -------------------- T1 --------------------
        expt_cfg_T1 = {
            "start": 0,
            "step": T1T2_params["T1_step"],
            "expts": T1T2_params["T1_expts"],
            "reps": T1T2_params["T1_reps"],
            "Qubit_number": Qubit_Readout,
            "rounds": T1T2_params["T1_rounds"],
            "pi_gain": qubit_gain,
            "relax_delay": T1T2_params["relax_delay"],
            "sigma": qubit_sigma,
            "flattop_length": qubit_flattop,
            "f_ge": qubit_frequency_center,
        }

        config_T1 = config | expt_cfg_T1
        iT1 = T1FF(path="T1", cfg=config_T1, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        dT1 = T1FF.acquire(iT1)
        T1FF.display(iT1, dT1, plotDisp=plot_disp, figNum=2)
        T1FF.save_data(iT1, dT1)
        T1FF.save_config(iT1)

        # -------------------- T2E immediately after --------------------
        num_pulses = T2E_params["num_pi_pulses"]

        # compute time step with your hardware quantization
        int_steps = T2E_params["T2_max_us"] // (0.00232515 * (num_pulses + 1) * T2E_params["T2_expts"])
        if int_steps == 0:
            print("[T2E] Step size is 0! need to increase total time or decrease experiments")
            break

        expt_cfg_T2E = {
            "start": 0,
            "step": 0.00232515 * (num_pulses + 1) * int_steps,
            "expts": T2E_params["T2_expts"],
            "reps": T2E_params["T2_reps"],
            "rounds": T2E_params["T2_rounds"],
            "pi_gain": qubit_gain,
            "pi2_gain": pi2_gain,
            "relax_delay": T2E_params["relax_delay"],
            "f_ge": qubit_frequency_center + T2E_params["freq_shift"],
            "num_pi_pulses": num_pulses,
            "sigma": qubit_sigma,
            "flattop_length": qubit_flattop,
            "Qubit_number": Qubit_Readout,
        }

        # optional display normalization params
        if T2E_params.get("rotation_angle", False) != False:
            expt_cfg_T2E["rotation_angle"] = T2E_params["rotation_angle"]
            expt_cfg_T2E["min_max"] = T2E_params["min_max"]

        config_T2E = config | expt_cfg_T2E
        iT2E = T2EMUX(path="T2E", cfg=config_T2E, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        dT2E = T2EMUX.acquire(iT2E)
        T2EMUX.display(iT2E, dT2E, plotDisp=plot_disp, figNum=3)
        T2EMUX.save_data(iT2E, dT2E)
        T2EMUX.save_config(iT2E)

        # -------------------- between iterations --------------------
        time.sleep(10)
        soc.reset_gens()

if RunT1T2RT2E:
    def _run_experiment(ExptClass, path, expt_cfg, figNum, plot_disp=False):
        cfg_run = config | expt_cfg
        inst = ExptClass(path=path, cfg=cfg_run, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        data = ExptClass.acquire(inst)
        ExptClass.display(inst, data, plotDisp=plot_disp, figNum=figNum)
        ExptClass.save_data(inst, data)
        ExptClass.save_config(inst)
        return inst, data

    for i in range(T1T2_params["repetitions"]):
        plot_disp = (T1T2_params["repetitions"] <= 1)

        # -------------------- T1 --------------------
        expt_cfg_T1 = {
            "start": 0,
            "step": T1T2_params["T1_step"],
            "expts": T1T2_params["T1_expts"],
            "reps": T1T2_params["T1_reps"],
            "rounds": T1T2_params["T1_rounds"],
            "Qubit_number": Qubit_Readout,
            "pi_gain": qubit_gain,
            "relax_delay": T1T2_params["relax_delay"],
            "sigma": qubit_sigma,
            "flattop_length": qubit_flattop,
            "f_ge": qubit_frequency_center,
        }
        _run_experiment(T1FF, "T1", expt_cfg_T1, figNum=2, plot_disp=plot_disp)

        # -------------------- T2E --------------------
        num_pulses = T2E_params["num_pi_pulses"]
        int_steps = T2E_params["T2_max_us"] // (
            0.00232515 * (num_pulses + 1) * T2E_params["T2_expts"]
        )
        if int_steps == 0:
            print("[T2E] Step size is 0! need to increase total time or decrease experiments")
            break

        expt_cfg_T2E = {
            "start": 0,
            "step": 0.00232515 * (num_pulses + 1) * int_steps,
            "expts": T2E_params["T2_expts"],
            "reps": T2E_params["T2_reps"],
            "rounds": T2E_params["T2_rounds"],
            "Qubit_number": Qubit_Readout,
            "pi_gain": qubit_gain,
            "pi2_gain": pi2_gain,
            "relax_delay": T2E_params["relax_delay"],
            "f_ge": qubit_frequency_center + T2E_params["freq_shift"],
            "num_pi_pulses": num_pulses,
            "sigma": qubit_sigma,
            "flattop_length": qubit_flattop,
        }
        if T2E_params.get("rotation_angle") is not None:
            expt_cfg_T2E["rotation_angle"] = T2E_params["rotation_angle"]
            expt_cfg_T2E["min_max"] = T2E_params["min_max"]

        _run_experiment(T2EMUX, "T2E", expt_cfg_T2E, figNum=3, plot_disp=plot_disp)

        # -------------------- T2R --------------------
        expt_cfg_T2R = {
            "start": 0,
            "step": T1T2_params["T2_step"],
            "phase_step": soccfg.deg2reg(0 * 360 / 50, gen_ch=2),
            "expts": T1T2_params["T2_expts"],
            "reps": T1T2_params["T2_reps"],
            "rounds": T1T2_params["T2_rounds"],
            "pi_gain": qubit_gain,
            "pi2_gain": pi2_gain,
            "relax_delay": T1T2_params["relax_delay"],
            "f_ge": qubit_frequency_center + T1T2_params["freq_shift"],
            "sigma": qubit_sigma,
            "flattop_length": qubit_flattop,
        }
        _run_experiment(T2R, "T2R", expt_cfg_T2R, figNum=4, plot_disp=plot_disp)

        time.sleep(10)
        soc.reset_gens()


if RunT2:
    T2R_cfg = {"start": 0, "step": T1T2_params["T2_step"], "phase_step": soccfg.deg2reg(0 * 360 / 50, gen_ch=2),
               "expts": T1T2_params["T2_expts"], "reps": T1T2_params["T2_reps"], "rounds": T1T2_params["T2_rounds"],
               "pi_gain": qubit_gain,
               "pi2_gain": pi2_gain, "relax_delay": T1T2_params["relax_delay"],
               'f_ge': qubit_frequency_center + T1T2_params["freq_shift"],
               "sigma": qubit_sigma, "flattop_length": qubit_flattop
               }
    for i in range(T1T2_params['repetitions']):
        config = config | T2R_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
        iT2R = T2R(path="T2R", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        dT2R = T2R.acquire(iT2R)
        T2R.display(iT2R, dT2R, plotDisp=False, figNum=2)
        T2R.save_data(iT2R, dT2R)
        T2R.save_config(iT2R)
        time.sleep(10)
        soc.reset_gens()


if RunT2E:
    for i in range(T2E_params['repetitions']):
        # match T1 behavior: only show plots if single repetition
        if T2E_params['repetitions'] > 1:
            plot_disp = False
        else:
            plot_disp = True

        # decide pi/2 gain
        if T2E_params["pi2_gain"] == False:
            qubit_gain_pi2 = qubit_gain // 2
        else:
            qubit_gain_pi2 = T2E_params["pi2_gain"]

        num_pulses = T2E_params["num_pi_pulses"]

        # compute time step with your hardware quantization
        int_steps = T2E_params["T2_max_us"] // (0.00232515 * (num_pulses + 1) * T2E_params["T2_expts"])
        print(f"[T2E rep {i}] int_steps={int_steps}, step(us)={0.00232515*(num_pulses+1)*int_steps}, expts={T2E_params['T2_expts']}")

        if int_steps == 0:
            print('Step size is 0! need to increase total time or decrease experiments')
            break  # or continue, but breaking is usually safer
        else:
            T2E_cfg = {
                "start": 0,
                "step": 0.00232515 * (num_pulses + 1) * int_steps,
                "expts": T2E_params["T2_expts"],
                "reps": T2E_params["T2_reps"],
                "rounds": T2E_params["T2_rounds"],
                "pi_gain": qubit_gain,
                "pi2_gain": qubit_gain_pi2,
                "relax_delay": T2E_params["relax_delay"],
                "f_ge": qubit_frequency_center + T2E_params["freq_shift"],
                "num_pi_pulses": num_pulses,
                "sigma": qubit_sigma,
                "flattop_length": qubit_flattop,
            }

            # optional display normalization params
            if T2E_params["rotation_angle"] != False:
                T2E_cfg["rotation_angle"] = T2E_params["rotation_angle"]
                T2E_cfg["min_max"] = T2E_params["min_max"]

            config_run = config | T2E_cfg

            # new instance each repetition (like T1)
            iT2E = T2EMUX(path="T2E", cfg=config_run, soc=soc, soccfg=soccfg, outerFolder=outerFolder)

            dT2E = T2EMUX.acquire(iT2E)
            T2EMUX.display(iT2E, dT2E, plotDisp=plot_disp, figNum=2)
            T2EMUX.save_data(iT2E, dT2E)
            T2EMUX.save_config(iT2E)

            time.sleep(10)
            soc.reset_gens()

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

if RunTrans_QubitSpec:
    sanity_dump(config)
    for i in range(T1T2_params['repetitions']):
        # sanity_dump(config)
        # config["reps"] = 20  # fast axis number of points
        # config["rounds"] = 20  # slow axis number of points
        # Instance_trans = CavitySpecFF(path="TransmissionFF", cfg=config, soc=soc, soccfg=soccfg,
        #                               outerFolder=outerFolder)
        # data_trans = CavitySpecFF.acquire(Instance_trans)
        # CavitySpecFF.display(Instance_trans, data_trans, plotDisp=False, figNum=1)
        # CavitySpecFF.save_data(Instance_trans, data_trans)
        # CavitySpecFF.save_config(Instance_trans)
        #
        # # update the transmission frequency to be the peak
        # if cavity_min:
        #     config["pulse_freq"] = Instance_trans.peakFreq_min
        # else:
        #     config["pulse_freq"] = Instance_trans.peakFreq_max
        # print("Cavity frequency found at: ", config["pulse_freq"])

        config["reps"] = Spec_relevant_params['reps']  # want more reps and rounds for qubit data
        config["rounds"] = Spec_relevant_params['rounds']
        config["Gauss"] = Spec_relevant_params['Gauss']
        if Spec_relevant_params['Gauss']:
            config['sigma'] = Spec_relevant_params["sigma"]
            config["qubit_gain"] = Spec_relevant_params['gain']
        Instance_specSlice = QubitSpecSliceFF(path="QubitSpecFF", cfg=config, soc=soc, soccfg=soccfg,
                                              outerFolder=outerFolder)
        data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
        QubitSpecSliceFF.display(Instance_specSlice, data_specSlice, plotDisp=False, figNum=2)
        QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)
        QubitSpecSliceFF.save_config(Instance_specSlice)



#######################################################
qubit_gains = [Qubit_Parameters[str(Q_R)]['Qubit']['Gain'] for Q_R in SS_params["Qubit_Pulse"]]
qubit_frequency_centers = [Qubit_Parameters[str(Q_R)]['Qubit']['Frequency'] for Q_R in SS_params["Qubit_Pulse"]]


UpdateConfig = {
    ###### cavity
    # "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "read_pulse_style": "const", # --Fixed
    "readout_length": SS_params["Readout_Time"], # us (length of the pulse applied)
    "adc_trig_offset": SS_params["ADC_Offset"],
    # "pulse_gain": cavity_gain, # [DAC units]
    "pulse_gain": cavity_gain,  # [DAC units]
    "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "sigma": qubit_sigma,  ### units us, define a 20ns sigma
    "qubit_gain": qubit_gain,
    "f_ge": qubit_frequency_center,
    "qubit_gains": qubit_gains,
    "f_ges": qubit_frequency_centers,
    ##### define shots
    "shots": SS_params["Shots"], ### this gets turned into "reps"
    "relax_delay": SS_params['relax_delay'],  # us
    "flattop_length": qubit_flattop
}

config = BaseConfig | UpdateConfig
config["FF_Qubits"] = FF_Qubits
config['Read_Indeces'] = Qubit_Readout


if SingleShot:
    config['number_of_pulses'] = SS_params['number_of_pulses']
    Instance_SingleShotProgram = SingleShotProgramFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
    # print(data_SingleShotProgram)
    SingleShotProgramFFMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)

    SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
    SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)
    print('Angle: ', data_SingleShotProgram['data']['angle'][0])
    print('threshold: ', data_SingleShotProgram['data']['threshold'][0])

if RunT1SS:
    for i in range(T1SS_params["repetitions"]):
        if T1SS_params["calibrate_SS"]:
            config['number_of_pulses'] = SS_params['number_of_pulses']
            Instance_SingleShotProgram = SingleShotProgramFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=config,
                                                                soc=soc, soccfg=soccfg)
            data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
            SingleShotProgramFFMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=False)
            SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
            SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)
            angle = data_SingleShotProgram['data']['angle'][0]
            threshold = data_SingleShotProgram['data']['threshold'][0]
        else:
            angle = T1SS_params["angle"]
            threshold = T1SS_params["threshold"]
        print(angle, threshold)

        expt_cfg = {"start": 0, "step": T1SS_params["T1_step"], "expts": T1SS_params["T1_expts"],
                    'reps': T1SS_params['reps'],
                    "pi_gain": qubit_gain, "relax_delay": T1SS_params["relax_delay"]
                    }
        config = config | expt_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
        iT1 = T1_SS(path="T1SS", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        dT1 = T1_SS.acquire(iT1, angle = angle, threshold = threshold)
        T1_SS.display(iT1, dT1, plotDisp=False, figNum=2)
        T1_SS.save_data(iT1, dT1)
        T1_SS.save_config(iT1)

        time.sleep(10)
        soc.reset_gens()


if SingleShot_ReadoutOptimize:
    span = SS_R_params['span']
    cav_gain_start = SS_R_params['gain_start']
    cav_gain_stop = SS_R_params['gain_stop']
    cav_gain_pts = SS_R_params['gain_pts']
    cav_trans_pts = SS_R_params['trans_pts']
    config['number_of_pulses'] = 1
    exp_parameters = {
        ###### cavity
        "cav_gain_Start": cav_gain_start,
        "cav_gain_Stop": cav_gain_stop,
        "cav_gain_Points": cav_gain_pts,
        "trans_freq_start": config["pulse_freq"] - span / 2, #249.6,
        "trans_freq_stop": config["pulse_freq"] + span / 2, #250.3,
        "TransNumPoints": cav_trans_pts,
    }
    config = config | exp_parameters
    # Now lets optimize powers and readout frequencies
    Instance_SingleShotOptimize = ReadOpt_wSingleShotFF(path="SingleShot_OptReadout", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgramOptimize = ReadOpt_wSingleShotFF.acquire(Instance_SingleShotOptimize)
    # print(data_SingleShotProgram)
    ReadOpt_wSingleShotFF.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)

    ReadOpt_wSingleShotFF.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
    ReadOpt_wSingleShotFF.save_config(Instance_SingleShotOptimize)

if SingleShot_QubitOptimize:
    q_gain_span = SS_Q_params['q_gain_span']
    q_gain_pts = SS_Q_params['q_gain_pts']
    q_freq_pts = SS_Q_params['q_freq_pts']
    q_freq_span = SS_Q_params['q_freq_span']
    config['number_of_pulses'] = SS_Q_params['number_of_pulses']
    Qubit_Pulse_Index = 0
    exp_parameters = {
        ###### cavity
        "qubit_gain_Start": max([0, int(qubit_gains[Qubit_Pulse_Index] - int(q_gain_span))]), # - q_gain_span / 2,
        "qubit_gain_Stop":  min([32767, int(qubit_gains[Qubit_Pulse_Index] + int(q_gain_span))]),# *qubit_gains[Qubit_Pulse_Index] + q_gain_span / 2,
        "qubit_gain_Points": q_gain_pts,
        "qubit_freq_start": qubit_frequency_centers[Qubit_Pulse_Index] - q_freq_span,
        "qubit_freq_stop": qubit_frequency_centers[Qubit_Pulse_Index] + q_freq_span,
        "QubitNumPoints": q_freq_pts,
        "number_of_pulses": SS_Q_params["number_of_pulses"]
    }
    print(exp_parameters)
    config = config | exp_parameters
    g0 = qubit_gains[Qubit_Pulse_Index]
    f0 = qubit_frequency_centers[Qubit_Pulse_Index]
    # # Now lets optimize powers and readout frequencies
    Instance_SingleShotOptimize = QubitPulseOpt_wSingleShotFF(path="SingleShot_OptQubit", outerFolder=outerFolder,
                                                                 cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgramOptimize = QubitPulseOpt_wSingleShotFF.acquire(Instance_SingleShotOptimize,
                                                                            Qubit_Sweep_Index = Qubit_Pulse_Index)
    # print(data_SingleShotProgram)
    QubitPulseOpt_wSingleShotFF.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)

    QubitPulseOpt_wSingleShotFF.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
    QubitPulseOpt_wSingleShotFF.save_config(Instance_SingleShotOptimize)

###############################################


def _rb_length_sweep_base_config(qubit_label):
    qubit_label = str(qubit_label)
    qubit_entry = Qubit_Parameters[qubit_label]
    readout_cfg = qubit_entry["Readout"]
    qubit_cfg = qubit_entry["Qubit"]

    trans_cfg_local = {
        "reps": 1000,
        "pulse_style": "const",
        "readout_length": trans_config["readout_length"],
        "pulse_gain": readout_cfg["Gain"],
        "pulse_freq": readout_cfg["Frequency"],
        "TransSpan": trans_config["TransSpan"],
        "TransNumPoints": trans_config["TransNumPoints"],
        "cav_relax_delay": trans_config["cav_relax_delay"],
    }
    qubit_cfg_local = {
        "qubit_pulse_style": "const",
        "qubit_gain": Spec_relevant_params["qubit_gain"],
        "qubit_freq": qubit_cfg["Frequency"],
        "qubit_length": qubit_config["qubit_length"],
        "SpecSpan": Spec_relevant_params["SpecSpan"],
        "SpecNumPoints": Spec_relevant_params["SpecNumPoints"],
    }
    expt_cfg_local = {
        "step": 2 * qubit_cfg_local["SpecSpan"] / qubit_cfg_local["SpecNumPoints"],
        "start": qubit_cfg_local["qubit_freq"] - qubit_cfg_local["SpecSpan"],
        "expts": qubit_cfg_local["SpecNumPoints"],
    }

    cfg_local = BaseConfig | trans_cfg_local | qubit_cfg_local | expt_cfg_local
    cfg_local["FF_Qubits"] = FF_Qubits
    cfg_local["cavity_min"] = True
    return cfg_local, qubit_entry["outerfoldername"], readout_cfg, qubit_cfg


def _json_ready(value):
    if isinstance(value, dict):
        return {str(k): _json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(v) for v in value]
    if isinstance(value, np.ndarray):
        return [_json_ready(v) for v in value.tolist()]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def _save_rb_length_sweep_summary(summary_path, payload):
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, "w") as f_summary:
        json.dump(_json_ready(payload), f_summary, indent=2)


def _extract_fitted_pi_gains(rabi_instance, rabi_data):
    rabi_data_dict = rabi_data.get("data", {})

    fit_i_pi_gain = np.nan
    fit_q_pi_gain = np.nan

    if "fit_i_pi_gain" in rabi_data_dict:
        fit_i_pi_gain = float(np.asarray(rabi_data_dict["fit_i_pi_gain"]).item())
    elif getattr(rabi_instance, "fit_i", None) is not None:
        fit_i_pi_gain = float(rabi_instance.fit_i["pi_gain"])

    if "fit_q_pi_gain" in rabi_data_dict:
        fit_q_pi_gain = float(np.asarray(rabi_data_dict["fit_q_pi_gain"]).item())
    elif getattr(rabi_instance, "fit_q", None) is not None:
        fit_q_pi_gain = float(rabi_instance.fit_q["pi_gain"])

    return fit_i_pi_gain, fit_q_pi_gain


def _choose_rabi_pi_gain(fit_i_pi_gain, fit_q_pi_gain, preference="I"):
    preference = str(preference).upper()
    if preference == "Q":
        ordered = [("Q", fit_q_pi_gain), ("I", fit_i_pi_gain)]
    else:
        ordered = [("I", fit_i_pi_gain), ("Q", fit_q_pi_gain)]

    for source, value in ordered:
        if np.isfinite(value) and value > 0:
            return float(value), source

    raise RuntimeError("No valid fitted pi gain was found in the Rabi data.")


def _evaluate_rabi_fit_quality(
    fit_i_pi_gain,
    fit_q_pi_gain,
    rabi_max_gain,
    require_both_fits=True,
    max_gain_disagreement_fraction=0.15,
    allowed_overshoot_fraction=0.10,
):
    issues = []
    rabi_max_gain = float(rabi_max_gain)
    comparison_gain = max(abs(rabi_max_gain), 1.0)
    fit_i_valid = bool(np.isfinite(fit_i_pi_gain) and fit_i_pi_gain > 0)
    fit_q_valid = bool(np.isfinite(fit_q_pi_gain) and fit_q_pi_gain > 0)

    if require_both_fits:
        if not fit_i_valid:
            issues.append("I fit missing or non-positive")
        if not fit_q_valid:
            issues.append("Q fit missing or non-positive")
    elif not (fit_i_valid or fit_q_valid):
        issues.append("Neither I nor Q fit produced a valid pi gain")

    if fit_i_valid and fit_q_valid:
        gain_difference = abs(float(fit_i_pi_gain) - float(fit_q_pi_gain))
        allowed_difference = max_gain_disagreement_fraction * comparison_gain
        if gain_difference > allowed_difference:
            issues.append(
                f"I/Q pi-gain mismatch {gain_difference:.1f} exceeds "
                f"{allowed_difference:.1f} ({max_gain_disagreement_fraction:.3f} of sweep max)"
            )

    upper_allowed_gain = (1.0 + allowed_overshoot_fraction) * comparison_gain
    if fit_i_valid and float(fit_i_pi_gain) > upper_allowed_gain:
        issues.append(
            f"I pi gain {float(fit_i_pi_gain):.1f} exceeds allowed range up to {upper_allowed_gain:.1f}"
        )
    if fit_q_valid and float(fit_q_pi_gain) > upper_allowed_gain:
        issues.append(
            f"Q pi gain {float(fit_q_pi_gain):.1f} exceeds allowed range up to {upper_allowed_gain:.1f}"
        )

    return len(issues) == 0, issues


def _run_rabi_for_rb_length_sweep(
    base_cfg_sweep,
    sweep_outer_folder,
    qubit_label,
    qubit_cfg_sweep,
    sigma_value,
    rabi_max_gain,
    rabi_points,
    run_prefix,
):
    rabi_step = max(1, int(np.ceil(rabi_max_gain / max(1, rabi_points - 1))))
    rabi_cfg = {
        "Qubit_number": int(qubit_label),
        "sigma": sigma_value,
        "f_ge": qubit_cfg_sweep["Frequency"],
        "flattop_length": qubit_cfg_sweep["flattop_length"],
        "relax_delay": RBLengthSweep_params["rb_relax_delay"],
    }

    if qubit_cfg_sweep["flattop_length"] is not None:
        rabi_cfg |= {
            "gain_start": 0,
            "gain_end": rabi_max_gain,
            "gainNumPoints": rabi_points,
            "reps": RBLengthSweep_params["rabi_reps"],
            "rounds": RBLengthSweep_params["rabi_rounds"],
        }
        rabi_run_cfg = base_cfg_sweep | rabi_cfg
        i_rabi = AmplitudeRabiFF_N(
            path="AmplitudeRabiLengthSweep",
            cfg=rabi_run_cfg,
            soc=soc,
            soccfg=soccfg,
            outerFolder=sweep_outer_folder,
            prefix=run_prefix,
        )
        d_rabi = AmplitudeRabiFF_N.acquire(i_rabi)
        AmplitudeRabiFF_N.display(
            i_rabi,
            d_rabi,
            plotDisp=RBLengthSweep_params["display_rabi"],
            figNum=2,
        )
        AmplitudeRabiFF_N.save_data(i_rabi, d_rabi)
        AmplitudeRabiFF_N.save_config(i_rabi)
    else:
        rabi_cfg |= {
            "start": 0,
            "step": rabi_step,
            "expts": rabi_points,
            "reps": RBLengthSweep_params["rabi_reps"],
            "rounds": RBLengthSweep_params["rabi_rounds"],
        }
        rabi_run_cfg = base_cfg_sweep | rabi_cfg
        i_rabi = AmplitudeRabiFF(
            path="AmplitudeRabiLengthSweep",
            cfg=rabi_run_cfg,
            soc=soc,
            soccfg=soccfg,
            outerFolder=sweep_outer_folder,
            prefix=run_prefix,
        )
        d_rabi = AmplitudeRabiFF.acquire(i_rabi)
        AmplitudeRabiFF.display(
            i_rabi,
            d_rabi,
            plotDisp=RBLengthSweep_params["display_rabi"],
            figNum=2,
            fit=True,
        )
        AmplitudeRabiFF.save_data(i_rabi, d_rabi)
        AmplitudeRabiFF.save_config(i_rabi)

    fit_i_pi_gain, fit_q_pi_gain = _extract_fitted_pi_gains(i_rabi, d_rabi)
    return i_rabi, d_rabi, fit_i_pi_gain, fit_q_pi_gain, rabi_step


if RunRBLengthSweep:
    full_sweep_repetitions = int(RBLengthSweep_params.get("full_sweep_repetitions", 1))
    if full_sweep_repetitions < 1:
        raise ValueError("RBLengthSweep_params['full_sweep_repetitions'] must be at least 1.")

    rabi_points = int(RBLengthSweep_params["rabi_points"])
    if rabi_points < 2:
        raise ValueError("RBLengthSweep_params['rabi_points'] must be at least 2.")

    for full_sweep_index in range(full_sweep_repetitions):
        for qubit_label in RBLengthSweep_params["qubits"]:
            qubit_label = str(qubit_label)
            if qubit_label not in RBLengthSweep_params["sigma_sweeps"]:
                raise KeyError(f"No RB length sweep entry was provided for qubit {qubit_label}.")

            sigma_sweep_cfg = RBLengthSweep_params["sigma_sweeps"][qubit_label]
            sigma_values = sigma_sweep_cfg["sigmas"]
            rabi_max_gains = sigma_sweep_cfg["rabi_max_gains"]

            if len(sigma_values) != len(rabi_max_gains):
                raise ValueError(
                    f"Length mismatch for qubit {qubit_label}: "
                    f"{len(sigma_values)} sigmas but {len(rabi_max_gains)} Rabi max gains."
                )

            base_cfg_sweep, sweep_outer_folder, _, qubit_cfg_sweep = _rb_length_sweep_base_config(qubit_label)
            summary_path = os.path.join(
                sweep_outer_folder,
                "RBLengthSweepSummaries",
                f"RBLengthSweep_Q{qubit_label}.json",
            )

            if os.path.exists(summary_path):
                with open(summary_path, "r") as f_summary:
                    summary_payload = json.load(f_summary)
            else:
                summary_payload = {
                    "qubit": qubit_label,
                    "outerFolder": sweep_outer_folder,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "sweep_parameters": {},
                    "records": [],
                }

            summary_payload["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            summary_payload["sweep_parameters"] = {
                "sigmas": list(sigma_values),
                "rabi_max_gains": list(rabi_max_gains),
                "full_sweep_repetitions": full_sweep_repetitions,
                "rabi_points": RBLengthSweep_params["rabi_points"],
                "rabi_reps": RBLengthSweep_params["rabi_reps"],
                "rabi_rounds": RBLengthSweep_params["rabi_rounds"],
                "rabi_fit_channel_preference": RBLengthSweep_params["rabi_fit_channel_preference"],
                "rabi_max_attempts_per_sigma": RBLengthSweep_params["rabi_max_attempts_per_sigma"],
                "rabi_require_both_fits": RBLengthSweep_params["rabi_require_both_fits"],
                "rabi_fit_max_gain_disagreement_fraction": (
                    RBLengthSweep_params["rabi_fit_max_gain_disagreement_fraction"]
                ),
                "rabi_fit_allowed_overshoot_fraction": (
                    RBLengthSweep_params["rabi_fit_allowed_overshoot_fraction"]
                ),
                "rb_lengths": list(RBLengthSweep_params["rb_lengths"]),
                "rb_nseeds": RBLengthSweep_params["rb_nseeds"],
                "rb_reps": RBLengthSweep_params["rb_reps"],
                "rb_rounds": RBLengthSweep_params["rb_rounds"],
            }
            _save_rb_length_sweep_summary(summary_path, summary_payload)

            for sigma_value, rabi_max_gain in zip(sigma_values, rabi_max_gains):
                sigma_value = float(sigma_value)
                rabi_max_gain = int(rabi_max_gain)
                sigma_tag = f"{sigma_value:.6f}".rstrip("0").rstrip(".").replace(".", "p")
                run_prefix_base = f"rep{full_sweep_index + 1}_Q{qubit_label}_sigma_{sigma_tag}"
                sweep_record = {
                    "full_sweep_index": full_sweep_index + 1,
                    "sigma": sigma_value,
                    "requested_rabi_max_gain": rabi_max_gain,
                    "status": "started",
                    "attempts": [],
                }
                summary_payload["records"].append(sweep_record)
                summary_payload["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                _save_rb_length_sweep_summary(summary_path, summary_payload)

                if rabi_max_gain <= 0:
                    sweep_record["status"] = "invalid_rabi_max_gain"
                    sweep_record["error"] = "Requested Rabi max gain must be positive."
                    summary_payload["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    _save_rb_length_sweep_summary(summary_path, summary_payload)
                    continue

                selected_pi_gain_float = None
                selected_pi_source = None
                selected_pi_gain = None
                selected_pi2_gain = None
                valid_rabi_found = False

                for attempt_index in range(int(RBLengthSweep_params["rabi_max_attempts_per_sigma"])):
                    attempt_number = attempt_index + 1
                    attempt_prefix = f"{run_prefix_base}_attempt{attempt_number}"
                    attempt_record = {
                        "attempt_number": attempt_number,
                        "status": "started",
                    }
                    sweep_record["attempts"].append(attempt_record)
                    summary_payload["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    _save_rb_length_sweep_summary(summary_path, summary_payload)

                    i_rabi, d_rabi, fit_i_pi_gain, fit_q_pi_gain, rabi_step = _run_rabi_for_rb_length_sweep(
                        base_cfg_sweep,
                        sweep_outer_folder,
                        qubit_label,
                        qubit_cfg_sweep,
                        sigma_value,
                        rabi_max_gain,
                        rabi_points,
                        attempt_prefix,
                    )

                    attempt_record.update(
                        {
                            "rabi_points": rabi_points,
                            "rabi_step": rabi_step,
                            "rabi_h5": i_rabi.fname,
                            "rabi_png": i_rabi.iname,
                            "rabi_config": i_rabi.cname,
                            "fit_i_pi_gain": fit_i_pi_gain,
                            "fit_q_pi_gain": fit_q_pi_gain,
                        }
                    )

                    fit_is_good, fit_issues = _evaluate_rabi_fit_quality(
                        fit_i_pi_gain,
                        fit_q_pi_gain,
                        rabi_max_gain,
                        require_both_fits=bool(RBLengthSweep_params["rabi_require_both_fits"]),
                        max_gain_disagreement_fraction=float(
                            RBLengthSweep_params["rabi_fit_max_gain_disagreement_fraction"]
                        ),
                        allowed_overshoot_fraction=float(
                            RBLengthSweep_params["rabi_fit_allowed_overshoot_fraction"]
                        ),
                    )

                    if not fit_is_good:
                        attempt_record["status"] = "bad_fit_retry"
                        attempt_record["fit_issues"] = fit_issues
                        summary_payload["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        _save_rb_length_sweep_summary(summary_path, summary_payload)
                        if attempt_number < int(RBLengthSweep_params["rabi_max_attempts_per_sigma"]):
                            retry_delay_s = float(RBLengthSweep_params.get("rabi_retry_delay_s", 0.0))
                            if retry_delay_s > 0:
                                time.sleep(retry_delay_s)
                        continue

                    try:
                        selected_pi_gain_float, selected_pi_source = _choose_rabi_pi_gain(
                            fit_i_pi_gain,
                            fit_q_pi_gain,
                            preference=RBLengthSweep_params["rabi_fit_channel_preference"],
                        )
                    except Exception as fit_err:
                        attempt_record["status"] = "bad_fit_retry"
                        attempt_record["fit_issues"] = [str(fit_err)]
                        summary_payload["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        _save_rb_length_sweep_summary(summary_path, summary_payload)
                        if attempt_number < int(RBLengthSweep_params["rabi_max_attempts_per_sigma"]):
                            retry_delay_s = float(RBLengthSweep_params.get("rabi_retry_delay_s", 0.0))
                            if retry_delay_s > 0:
                                time.sleep(retry_delay_s)
                        continue

                    selected_pi_gain = int(np.clip(np.rint(selected_pi_gain_float), 1, 32767))
                    selected_pi2_gain = max(1, selected_pi_gain // 2)
                    attempt_record.update(
                        {
                            "status": "accepted",
                            "selected_pi_gain_source": selected_pi_source,
                            "selected_pi_gain_float": selected_pi_gain_float,
                            "selected_pi_gain": selected_pi_gain,
                            "selected_pi2_gain": selected_pi2_gain,
                        }
                    )
                    valid_rabi_found = True
                    summary_payload["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    _save_rb_length_sweep_summary(summary_path, summary_payload)
                    break

                if not valid_rabi_found:
                    sweep_record["status"] = "rabi_fit_failed_all_attempts"
                    summary_payload["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    _save_rb_length_sweep_summary(summary_path, summary_payload)
                    print(
                        f"Skipping RB for qubit {qubit_label}, sigma={sigma_value}: "
                        f"Rabi fit remained bad after {RBLengthSweep_params['rabi_max_attempts_per_sigma']} attempts."
                    )
                    continue

                sweep_record.update(
                    {
                        "selected_pi_gain_source": selected_pi_source,
                        "selected_pi_gain_float": selected_pi_gain_float,
                        "selected_pi_gain": selected_pi_gain,
                        "selected_pi2_gain": selected_pi2_gain,
                        "status": "running_rb",
                    }
                )
                summary_payload["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                _save_rb_length_sweep_summary(summary_path, summary_payload)

                rb_cfg = {
                    "Qubit_number": int(qubit_label),
                    "f_ge": qubit_cfg_sweep["Frequency"],
                    "sigma": sigma_value,
                    "pi_gain": selected_pi_gain,
                    "pi2_gain": selected_pi2_gain,
                    "flattop_length": qubit_cfg_sweep["flattop_length"],
                    "relax_delay": RBLengthSweep_params["rb_relax_delay"],
                    "rb_lengths": RBLengthSweep_params["rb_lengths"],
                    "rb_nseeds": RBLengthSweep_params["rb_nseeds"],
                    "rb_reps": RBLengthSweep_params["rb_reps"],
                    "rb_rounds": RBLengthSweep_params["rb_rounds"],
                    "rb_seed": RBLengthSweep_params["rb_seed"],
                    "rb_gate_spacing": RBLengthSweep_params["rb_gate_spacing"],
                    "rb_post_sequence_delay": RBLengthSweep_params["rb_post_sequence_delay"],
                    "rb_gate_fidelity_primitives_per_clifford": (
                        RBLengthSweep_params["rb_fit_primitives_per_clifford"]
                    ),
                }
                rb_run_cfg = base_cfg_sweep | rb_cfg
                i_rb = SingleQubitRB(
                    path="RBLengthSweep",
                    cfg=rb_run_cfg,
                    soc=soc,
                    soccfg=soccfg,
                    outerFolder=sweep_outer_folder,
                    prefix=run_prefix_base,
                )
                d_rb = SingleQubitRB.acquire(i_rb)
                SingleQubitRB.display(
                    i_rb,
                    d_rb,
                    plotDisp=RBLengthSweep_params["display_rb"],
                    figNum=2,
                )
                SingleQubitRB.save_data(i_rb, d_rb)
                SingleQubitRB.save_config(i_rb)

                rb_data_dict = d_rb["data"]
                sweep_record.update(
                    {
                        "rb_h5": i_rb.fname,
                        "rb_png": i_rb.iname,
                        "rb_config": i_rb.cname,
                        "rb_fit_success": bool(int(np.asarray(rb_data_dict["fit_success"]).item())),
                        "rb_p_clifford": float(np.asarray(rb_data_dict["p_clifford"]).item()),
                        "rb_clifford_error": float(np.asarray(rb_data_dict["clifford_error"]).item()),
                        "rb_gate_fidelity": float(np.asarray(rb_data_dict["gate_fidelity"]).item()),
                        "rb_gate_fidelity_err": float(np.asarray(rb_data_dict["gate_fidelity_err"]).item()),
                        "status": "complete",
                    }
                )
                summary_payload["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                _save_rb_length_sweep_summary(summary_path, summary_payload)
                soc.reset_gens()

        inter_sweep_delay_s = float(RBLengthSweep_params.get("inter_sweep_delay_s", 0.0))
        if full_sweep_index < full_sweep_repetitions - 1 and inter_sweep_delay_s > 0:
            time.sleep(inter_sweep_delay_s)
