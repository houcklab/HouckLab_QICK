# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import \
    QubitSpecSliceFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mOptimizeReadoutandPulse_FFMUX import \
    ReadOpt_wSingleShotFFMUX, QubitPulseOpt_wSingleShotFFMUX

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mTransmissionFFMUX import CavitySpecFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX

# from Qubit_Parameters_8QPiFlux import *
# from Qubit_Parameters_8QPiFlux_Matt import *
# from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.Qubit_Parameters_5678 import *
from qubit_parameter_files.Qubit_Parameters_1234 import *

Q = 4
# Qubit_Readout = ['5HHH', '1HHH', '4HHH']
Qubit_Readout = [1]

Qubit_Pulse = ['1H']
# Qubit_Pulse = ['5HHH', '4HHH']
# Qubit_Pulse = ['4HHH', '1HHH']
# Qubit_Pulse = ['4HHH', '1HHH', '5HHH']
# Qubit_Pulse = ['4HHH', '1HHH', '6HHH']
# Qubit_Pulse = ['6HHH']

f = False
t = True

RunTransmissionSweep =       f
RunFirst2ToneSpec =          f
RunSecond2ToneSpec =         t
RunAmplitudeRabi =           f
SingleShot_ReadoutOptimize = f
SingleShot_QubitOptimize =   f
SingleShot = True


Trans_relevant_params = {"reps": 200, "TransSpan": 1.5, "TransNumPoints": 61,
                        "readout_length": 2.5, 'cav_relax_delay': 10}

First_Spec_params = {   "qubit_gain": 500, "SpecSpan": 100, "SpecNumPoints": 71,
                        'Gauss': False, "sigma": 0.07, "Gauss_gain": 3350,
                        'reps': 144, 'rounds': 1}


Second_Spec_params = {"qubit_gain": 50, "SpecSpan": 10, "SpecNumPoints": 71,
                        'Gauss': False, "sigma": 0.05, "Gauss_gain": 1200,
                        'reps': 144, 'rounds': 1}


Amplitude_Rabi_params = {"max_gain": 9000, 'relax_delay':200}

SS_R_params = {"Shots":500, 'relax_delay':100,
               "gain_start": 2000, "gain_stop": 8000, "gain_pts": 10, "span": 1, "trans_pts": 6, 'number_of_pulses': 1}


SS_Q_params = {"Shots": 500, 'relax_delay':150,
               "q_gain_span": 1000, "q_gain_pts": 7, "q_freq_span": 3, "q_freq_pts": 7,
               'number_of_pulses': 3, 'qubit_sweep_index': -1}

SS_params = {"Shots": 5000,
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
    data = Instance_trans.acquire_display_save(plotDisp=True, block=True)

    #update the transmission frequency to be the peak
    config["res_freqs"][0] = Instance_trans.peakFreq_min
    print("Cavity frequency found at: ", config["res_freqs"][0] + BaseConfig["res_LO"])

if RunFirst2ToneSpec:
    Instance_spec = QubitSpecSliceFFMUX(path="QubitSpecFF", cfg=config | First_Spec_params,
                        soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    data = Instance_spec.acquire_display_save(plotDisp=True, block=True)
    config["qubit_freqs"][0] = Instance_spec.qubitFreq
    print("Qubit frequency found at: ", config["qubit_freqs"][0])
    
if RunSecond2ToneSpec:
    Instance_spec = QubitSpecSliceFFMUX(path="QubitSpecFF", cfg=config | Second_Spec_params,
                        soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    data = Instance_spec.acquire_display_save(plotDisp=True, block=True)
    config["qubit_freqs"][0] = Instance_spec.qubitFreq
    print("Qubit frequency found at: ", config["qubit_freqs"][0])

if RunAmplitudeRabi:
    data = AmplitudeRabiFFMUX(path="AmplitudeRabi", cfg=config | Amplitude_Rabi_params,
                        soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(plotDisp=True, block=True)
    
    # avgi, avgq, gains = data['data']['avgi'], data['data']['avgq'], data['data']['x_pts']
    # contrast = IQ_contrast(avgi, avgq)
    # def fit_func(gain, ampl, pi_gain):
    #     return ampl*np.cos(gain * np.pi/pi_gain)
    # popt, _ = curve_fit(fit_func, gains, contrast, p0=[30, 1000])
    # config["qubit_gains"][0] = np.abs(popt[1]) / 32766.
    user_gain = input("Enter gain:")
    config["qubit_gains"][0] = int(user_gain) / 32766

    print("Qubit gain found at: ", config["qubit_gains"][0] * 32766)

if SingleShot_ReadoutOptimize:
    data = ReadOpt_wSingleShotFFMUX(path="SingleShot_OptReadout", outerFolder=outerFolder,
                             cfg=config | SS_params | SS_R_params,soc=soc,soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)
    fid_mat, trans_fpts, gain_pts = (data['data'][key] for key in ('fid_mat', 'trans_fpts', 'gain_pts'))
    ind = np.unravel_index(np.argmax(fid_mat, axis=None), fid_mat.shape)
    
    config["res_gains"][0] = gain_pts[ind[0]] / 32766.
    config["res_freqs"][0] = trans_fpts[ind[1]]

    print("Cavity gain found at: ", config["res_gains"][0] * 32766)
    print("Cavity frequency found at: ", config["res_freqs"][0] + BaseConfig["res_LO"])

if SingleShot_QubitOptimize:
    data = QubitPulseOpt_wSingleShotFFMUX(path="SingleShot_OptQubit", outerFolder=outerFolder,
                                   cfg=config | SS_params | SS_Q_params,soc=soc,soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)
    fid_mat, trans_fpts, gain_pts = (data['data'][key] for key in ('fid_mat', 'qubit_fpts', 'gain_pts'))
    ind = np.unravel_index(np.argmax(fid_mat, axis=None), fid_mat.shape)
    
    config["qubit_gains"][0] = gain_pts[ind[0]] / 32766.
    config["qubit_freqs"][0] = trans_fpts[ind[1]]

    print("Qubit gain found at: ", config["res_gains"][0] * 32766)
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

