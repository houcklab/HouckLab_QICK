# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import \
    QubitSpecSliceFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mFFvsSpec import FFvsSpec
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mOptimizeReadoutandPulse_FFMUX import \
    ReadOpt_wSingleShotFFMUX, QubitPulseOpt_wSingleShotFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mGainSweepQubitOscillations import \
    GainSweepOscillations

from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mTransmissionFFMUX import CavitySpecFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.IQ_contrast import IQ_contrast

import numpy as np
from scipy.optimize import curve_fit


mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq
BaseConfig["readout_length"] = 2.5

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7121.0 - BaseConfig["res_LO"] , 'Gain': 7000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 3518.3, 'sigma': 0.05, 'Gain': 1200},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7077.3 - BaseConfig["res_LO"] , 'Gain': 4000,
                  "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 3700, 'sigma': 0.05, 'Gain': 2260},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7511.0 - BaseConfig["res_LO"] , 'Gain': 4000,
                  "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 3900, 'sigma': 0.05, 'Gain': 3500},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568.6 - BaseConfig["res_LO"] , 'Gain': 4000,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 4100, 'sigma': 0.05, 'Gain': 3350},
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

Qubit_Readout = [1]
Qubit_Pulse = [1]


RunTransmissionSweep = True # determine cavity frequency
RunFirst2ToneSpec = True
RunSecond2ToneSpec = True
RunAmplitudeRabi = True
SingleShot_ReadoutOptimize = True
SingleShot_QubitOptimize = True
SingleShot = True


Trans_relevant_params = {"reps": 200, "TransSpan": 1.5, "TransNumPoints": 61,
                        "readout_length": 2.5, 'cav_relax_delay': 10}

First_Spec_params = {   "qubit_gain": 500, "SpecSpan":100, "SpecNumPoints": 71,
                        'Gauss': False, "sigma": 0.05, "Gauss_gain": 1200,
                        'reps': 144, 'rounds': 1}


Second_Spec_params = {"qubit_gain": 100, "SpecSpan": 10, "SpecNumPoints": 71,
                        'Gauss': False, "sigma": 0.05, "Gauss_gain": 1200,
                        'reps': 144, 'rounds': 1}

Amplitude_Rabi_params = {"sigma": 0.05, "max_gain": 10000, 'relax_delay':200}

SS_R_params = {"Shots":400,
               "gain_start": 2000, "gain_stop": 20000, "gain_pts": 10, "span": 1, "trans_pts": 6, 'number_of_pulses': 1}


SS_Q_params = {"Shots":400,
               "q_gain_span": 500, "q_gain_pts": 5, "q_freq_span": 4, "q_freq_pts": 7,
               'number_of_pulses': 1}

SS_params = {"Shots": 5000, "readout_length": 2.5, "adc_trig_delay": 0.3,
             'number_of_pulses': 1, 'relax_delay': 200}


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
    data = Instance_trans.acquire_display_save(plotDisp=True)

    #update the transmission frequency to be the peak
    config["res_freqs"][0] = Instance_trans.peakFreq_min
    print("Cavity frequency found at: ", config["res_freqs"][0] + BaseConfig["res_LO"])

if RunFirst2ToneSpec:
    Instance_spec = QubitSpecSliceFFMUX(path="QubitSpecFF", cfg=config | First_Spec_params,
                        soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    data = Instance_spec.acquire_display_save(plotDisp=True)
    config["qubit_freqs"][0] = Instance_spec.qubitFreq
    print("Qubit frequency found at: ", config["qubit_freqs"][0])
    
if RunSecond2ToneSpec:
    Instance_spec = QubitSpecSliceFFMUX(path="QubitSpecFF", cfg=config | Second_Spec_params,
                        soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    data = Instance_spec.acquire_display_save(plotDisp=True)
    config["qubit_freqs"][0] = Instance_spec.qubitFreq
    print("Qubit frequency found at: ", config["qubit_freqs"][0])

if RunAmplitudeRabi:
    data = AmplitudeRabiFFMUX(path="AmplitudeRabi", cfg=config | Amplitude_Rabi_params,
                        soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True)
    
    avgi, avgq, gains = data['data']['avgi'], data['data']['avgq'], data[]
    contrast = IQ_contrast(avgi, avgq)
    def fit_func(gain, ampl, pi_gain):
        return ampl*np.cos(gain / (2*pi_gain))
    popt = curve_fit(fit_func, gains, contrast)
    config["qubit_gains"][0] = popt[1]

    print("Qubit gain found at: ", config["qubit_gains"][0])

if SingleShot_ReadoutOptimize:
    data = ReadOpt_wSingleShotFFMUX(path="SingleShot_OptReadout", outerFolder=outerFolder,
                             cfg=config | SS_params | SS_R_params,soc=soc,soccfg=soccfg).acquire_display_save(plotDisp=True)
    fid_mat, trans_fpts, gain_pts = (data['data'][key] for key in ('fid_mat', 'trans_fpts', 'gain_pts'))
    ind = np.unravel_index(np.argmax(fid_mat, axis=None), fid_mat.shape)
    
    config["res_gains"][0] = gain_pts[ind[0]]
    config["res_freqs"][0] = trans_fpts[ind[1]]

    print("Cavity gain found at: ", config["res_gains"][0])
    print("Cavity frequency found at: ", config["res_freqs"][0] + BaseConfig["res_LO"])

if SingleShot_QubitOptimize:
    data = QubitPulseOpt_wSingleShotFFMUX(path="SingleShot_OptQubit", outerFolder=outerFolder,
                                   cfg=config | SS_params | SS_Q_params,soc=soc,soccfg=soccfg).acquire_display_save(plotDisp=True)
    fid_mat, trans_fpts, gain_pts = (data['data'][key] for key in ('fid_mat', 'qubit_fpts', 'gain_pts'))
    ind = np.unravel_index(np.argmax(fid_mat, axis=None), fid_mat.shape)
    
    config["qubit_gains"][0] = gain_pts[ind[0]]
    config["qubit_freqs"][0] = trans_fpts[ind[1]]

    print("Qubit gain found at: ", config["res_gains"][0])
    print("Qubit frequency found at: ", config["res_freqs"][0] + BaseConfig["res_LO"])

if SingleShot:
    SingleShotFFMUX(path="SingleShot", outerFolder=outerFolder,
                           cfg=config | SS_params, soc=soc,soccfg=soccfg).acquire_save_display(plotDisp=True)



# TimeDomainSpec(path="TimeDomainSpec", outerFolder=outerFolder,
#                           cfg=config | {'reps': 5,
#                          'start':1, 'step': 16, 'expts': 50,}, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)


# import matplotlib.pyplot as plt
# while True:
#     plt.pause(50)
print(config)

