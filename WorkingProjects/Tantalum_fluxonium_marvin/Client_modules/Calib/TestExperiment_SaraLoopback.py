
#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from Tantalum_fluxonium.Client_modules.Calib.initialize import *
from Tantalum_fluxonium.Client_modules.Experiments.mLoopback import Loopback
from Tantalum_fluxonium.Client_modules.Experiments.mTransmission import Transmission
from Tantalum_fluxonium.Client_modules.Experiments.mSpecSlice import SpecSlice
from Tantalum_fluxonium.Client_modules.Experiments.mTransVsGain import TransVsGain
from Tantalum_fluxonium.Client_modules.Experiments.mTransmission_GUI_test import mTransmission_GUI_test
from Tantalum_fluxonium.Client_modules.Experiments.Rabi_ND import Rabi_ND
from matplotlib import pyplot as plt

#### define the saving path
outerFolder = "Z:\Parth\Data\Tantalum_Fluxonium\TF1SC1_B3_RFSOC\Q1\\"

###qubitAtten = attenuator(27797, attenuation_int= 10, print_int = False)


#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# print(soccfg)

plt.ioff()

# config = {"res_ch": 0,  # --Fixed
#           "ro_chs": [0],  # --Fixed
#           "reps": 1,  # --Fixed
#           "relax_delay": 1.0,  # --us
#           "res_phase": 0,  # --degrees
#           "pulse_style": "const",  # --Fixed
#
#           "length": 200,  # [Clock ticks]
#           # Try varying length from 10-100 clock ticks
#
#           "readout_length": 1000,  # [Clock ticks]
#           # Try varying readout_length from 50-1000 clock ticks
#
#           "pulse_gain": 30000,  # [DAC units]
#           # Try varying pulse_gain from 500 to 30000 DAC units
#
#           "pulse_freq": 559.25,  # [MHz]
#           # In this program the signal is up and downconverted digitally so you won't see any frequency
#           # components in the I/Q traces below. But since the signal gain depends on frequency,
#           # if you lower pulse_freq you will see an increased gain.
#
#           "adc_trig_offset": 200,  # [Clock ticks]
#           # Try varying adc_trig_offset from 100 to 220 clock ticks
#
#           "soft_avgs": 50,
#           # Try varying soft_avgs from 1 to 200 averages
#           "yokoVoltage": -0.1
#           }
#
# ## set the yoko frequency
# yoko1.SetVoltage(config["yokoVoltage"])
# print("Voltage is ", yoko1.GetVoltage(), " Volts")
#
# ### Loopback to calibrate the ADC offset
# Instance = Loopback(path="dataTestLoopback", cfg=config,soc=soc,soccfg=soccfg, outerFolder=outerFolder)
# data= Loopback.acquire(Instance)
# Loopback.display(Instance, data)
# Loopback.save_data(Instance, data)
#
# ###################################### code for runnning basic transmission and specSlice
# ## perform the cavity transmission experiment
#
# Instance_trans = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_trans= Transmission.acquire(Instance_trans)
# Transmission.display(Instance_trans, data_trans, plotDisp=True)
# Transmission.save_data(Instance_trans, data_trans)
#
#
# ## update the transmission frequency to be the peak
# config["read_pulse_freq"] = Instance_trans.peakFreq
# print(Instance_trans.peakFreq)
#
# ## Qubit Spec experiment, readjust the number of reps
# config["reps"] = 2000
#
# Instance_specSlice = SpecSlice(path="dataTestSpecSlice", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_specSlice= SpecSlice.acquire(Instance_specSlice)
# SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True)
# SpecSlice.save_data(Instance_specSlice, data_specSlice)


########################################################################################################################

####################################### code for transmission vs power
# UpdateConfig = {
#     "yokoVoltage": -0.136,
#     ##### change gain instead option
#     "trans_gain_start": 0,
#     "trans_gain_stop": 30000,
#     "trans_gain_num": 51,
#     ###### cavity
#     "trans_reps": 400,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const",  # --Fixed
#     "readout_length": 15,  # [Clock ticks]
#     # "read_pulse_gain": 10000,  # [DAC units]
#     "trans_freq_start": 558.50,  # [MHz] actual frequency is this number + "cavity_LO"
#     "trans_freq_stop": 559.50,  # [MHz] actual frequency is this number + "cavity_LO"
#     "TransNumPoints": 100,  ### number of points in the transmission frequecny
# }
#
# config = BaseConfig | UpdateConfig
#
# #### update the qubit and cavity attenuation
# yoko1.SetVoltage(config["yokoVoltage"])
#
# # ##### run actual experiment
#
# #### change gain instead of attenuation
# Instance_TransVsGain = TransVsGain(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_TransVsGain = TransVsGain.acquire(Instance_TransVsGain)
# TransVsGain.save_data(Instance_TransVsGain, data_TransVsGain)
# TransVsGain.save_config(Instance_TransVsGain)

# ###### run and plot the test transmission GUI
# # #################################### code for transmission vs power
# UpdateConfig = {
#     "yokoVoltage": 0.25,
#     ##### change gain instead option
#     "trans_gain_start": 1000,
#     "trans_gain_stop": 20000,
#     "trans_gain_num": 20,
#     ###### cavity
#     "trans_reps": 200,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const",  # --Fixed
#     "readout_length": 10,  # [us]
#     "read_pulse_gain": 10000,  # [DAC units]
#     "read_freq_start": 6424.5 - 1,  # [MHz] actual frequency is this number + "cavity_LO"
#     "read_freq_stop": 6424.5 + 2,  # [MHz] actual frequency is this number + "cavity_LO"
#     "TransNumPoints": 301,  ### number of points in the transmission frequecny
#     "relax_delay": 2,
# }
# config = BaseConfig | UpdateConfig
#
# prog = mTransmission_GUI_test(soccfg, config)
#
# x_pts, avgi, avgq = prog.acquire(soc)
#
# plt.figure(101)
# plt.plot(x_pts, np.abs(avgi[0][0]))


################################### code for running Amplitude rabi Blob

def Amplitude_IQ(I, Q, phase_num_points = 100):
    complex = I + 1j * Q
    phase_values = np.linspace(0, np.pi, phase_num_points)
    multiplied_phase = [complex * np.exp(1j * phase) for phase in phase_values]
    Q_range = np.array([np.max(IQPhase.imag) - np.min(IQPhase.imag) for IQPhase in multiplied_phase])
    phase_index = np.argmin(Q_range)
    final_complex = complex * np.exp(1j * phase_values[phase_index])
    return(final_complex.real)

UpdateConfig = {
    ##### define attenuators
    "yokoVoltage": 0.25,
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 10, # us
    "read_pulse_gain": 10000, # [DAC units]
    "read_pulse_freq": 6425.3,
    ##### spec parameters for finding the qubit frequency
    "qubit_freq_start": 2869 - 10,
    "qubit_freq_stop": 2869 + 10,
    "qubit_freq_expts": 41,
    "qubit_pulse_style": "arb",
    "sigma": 0.300,  ### units us, define a 20ns sigma
    # "flat_top_length": 0.300, ### in us
    "relax_delay": 500,  ### turned into us inside the run function
    ##### amplitude rabi parameters
    "qubit_gain_start": 20000,
    "qubit_gain_stop": 30000, ### stepping amount of the qubit gain
    "qubit_gain_expts": 3, ### number of steps
    "reps": 50,  # number of averages for the experiment
}
config = BaseConfig | UpdateConfig


prog = Rabi_ND(soccfg, config)

expt_pts, avg_di, avg_dq = prog.acquire()
avg_abs = Amplitude_IQ(avg_di, avg_dq)
avg_angle = np.angle(avg_di + 1j * avg_dq)
# avg_abs, avg_angle = np.abs(avg_di + 1j * avg_dq), np.angle(avg_di + 1j * avg_dq)

##### plot data

### check if the sweep is 1D
if len(expt_pts) == 1:
    fig, axes = plt.subplots(1, 1, figsize=(12,5))
    axes.plot(expt_pts[0], avg_di[0][0])
    axes.set_xlabel(prog.sweep_var[0])

else:

    fig, axes = plt.subplots(1, 2, figsize=(12,5))
    for i, d in enumerate([avg_di, avg_dq]):
        pcm = axes[i].pcolormesh(prog.get_expt_pts()[1], prog.get_expt_pts()[0], d[0,0].T, shading="Auto")
        axes[i].set_xlabel(prog.sweep_var[1])
        axes[i].set_ylabel(prog.sweep_var[0])
        axes[i].set_title("I data" if i ==0 else "Q data")
        plt.colorbar(pcm, ax=axes[i])

    ##### plotting the amp and phase
    fig, axes = plt.subplots(1, 2, figsize=(12,5))

    for i, d in enumerate([avg_abs, avg_angle]):
        if i==0:
            pcm = axes[i].pcolormesh(prog.get_expt_pts()[1], prog.get_expt_pts()[0], d[0,0].T, shading="Auto")
        else:
            pcm = axes[i].pcolormesh(prog.get_expt_pts()[1], prog.get_expt_pts()[0], np.unwrap(d[0, 0].T), shading="Auto")
        axes[i].set_xlabel(prog.sweep_var[1])
        axes[i].set_ylabel(prog.sweep_var[0])
        axes[i].set_title("IQ Amp" if i ==0 else "IQ phase")
        plt.colorbar(pcm, ax=axes[i])

#####################################################################################################################
plt.show()

# #
# plt.show(block = True)
