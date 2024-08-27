#%%
import os

# path = os.getcwd() # Old method, does not work with cells. I have shifted the following code to initialize
path = r'C:\Users\pjatakia\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_marvin\Client_modules\PythonDrivers'
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')

from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mLoopback import LoopbackProgram
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransmission_SaraTest import Transmission
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecSlice_SaraTest import SpecSlice
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecSlice_bkg_subtracted import SpecSlice_bkg_sub
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabi import AmplitudeRabi
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransVsGain import TransVsGain
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabi_Blob import AmplitudeRabi_Blob
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabi_CavityPower import \
    AmplitudeRabi_CavityPower
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT1Experiment import T1Experiment
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT2Experiment import T2Experiment
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT2EchoExperiment import T2EchoExperiment
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShot_2Dsweep import SingleShot_2Dsweep
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabiBlob_PS import AmplitudeRabi_PS
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabiFlux_PS import AmplitudeRabiFlux_PS
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mQubitSpecRepeat import QubitSpecRepeat
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.m2QubitFluxDrift import TwoQubitFluxDrift
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mConstantTone import ConstantTone_Experiment
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT1_PS import T1_PS
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotTemp_sse import SingleShotSSE
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecSlice_PS_sse import SpecSlice_PS_sse

from matplotlib import pyplot as plt
import datetime

# Define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2024_07_29_cooldown\\QCage_dev\\Magnet_Heat_Check_3\\"

# Print the start time
print('starting time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

# Only run this if no proxy already exists
soc, soccfg = makeProxy()

SwitchConfig = {
    "trig_buffer_start": 0.035, # in us
    "trig_buffer_end": 0.024, # in us
    "trig_delay": 0.07, # in us
}
BaseConfig = BaseConfig  | SwitchConfig

#%%

# TITLE: Loopback experiment
config = {"res_ch": 0,  # --Fixed
          "ro_chs": [0],  # --Fixed
          "reps": 1,  # --Fixed
          "relax_delay": 1.0,  # --us
          "res_phase": 0,  # --degrees
          "pulse_style": "const",  # --Fixed

          "length": soc.us2cycles(0.3),  # [Clock ticks] # 1 us is around 430 cycles
          # Try varying length from 10-100 clock ticks

          "readout_length": 200,  # [Clock ticks]
          # Try varying readout_length from 50-1000 clock ticks

          "pulse_gain": 30000,  # [DAC units]
          # Try varying pulse_gain from 500 to 30000 DAC units

          "pulse_freq": 6250,  # [MHz]
          # In this program the signal is up and downconverted digitally so you won't see any frequency
          # components in the I/Q traces below. But since the signal gain depends on frequency,
          # if you lower pulse_freq you will see an increased gain.

          "adc_trig_offset": 230,  # [Clock ticks]
          # Try varying adc_trig_offset from 100 to 220 clock ticks

          "soft_avgs": 5000
          # Try varying soft_avgs from 1 to 200 averages
          }

prog = LoopbackProgram(soccfg, config)
iq_list = prog.acquire_decimated(soc, load_pulses=True, progress=True, debug=False)
fff = plt.figure(1)
for ii, iq in enumerate(iq_list):
    plt.plot(iq[0], label="I value, ADC %d"%(config['ro_chs'][ii]))
    plt.plot(iq[1], label="Q value, ADC %d"%(config['ro_chs'][ii]))
    plt.plot(np.abs(iq[0]+1j*iq[1]), label="mag, ADC %d"%(config['ro_chs'][ii]))
plt.ylabel("a.u.")
plt.xlabel("Clock ticks")
plt.title("Averages = " + str(config["soft_avgs"]))
plt.legend()
fff.show()

#%%
# # TITLE: Transmission + Spectroscopy
UpdateConfig_transmission = {
    # Parameters
    "reps": 1000,  # Number of repetitions

    # cavity
    "read_pulse_style": "const",
    "read_length": 75,
    "read_pulse_gain": 1200,
    "read_pulse_freq":  6672.38, #6253.8,

    # Experiment Parameters
    "TransSpan": 3,  # [MHz] span will be center frequency +/- this parameter
    "TransNumPoints": 501,  # number of points in the transmission frequency
}

UpdateConfig_qubit = {
    "qubit_pulse_style": "flat_top",  # Constant pulse
    "qubit_gain": 10000,  # [DAC Units]
    'sigma': 1,
    'flat_top_length': 10,
    "qubit_length": 10,  # [us]

    # Define spec slice experiment parameters
    "qubit_freq_start": 50,
    "qubit_freq_stop": 650,
    "SpecNumPoints": 301,  # Number of points
    'spec_reps': 300,  # Number of repetition

    # Define the yoko voltage
    "yokoVoltage": -1.98395416666666,
    "relax_delay": 10,  # [us] Delay post one experiment
    'use_switch': True,
}

UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit

config = BaseConfig | UpdateConfig

# Set the yoko frequency
# yoko1.SetVoltage(config["yokoVoltage"])


#%%
# TITLE Perform the cavity transmission experiment


Instance_trans = Transmission(path="dataTestTransmission", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
data_trans = Instance_trans.acquire()
Instance_trans.save_data(data_trans)
Instance_trans.display(data_trans, plotDisp=True)
plt.show()

# Update the transmission frequency to be the peak

config["read_pulse_freq"] = Instance_trans.peakFreq
print("Cavity freq IF [MHz] = ", Instance_trans.peakFreq)

#%%
# TITLE Perform the spec slice experiment

# Estimate Time
time = config["spec_reps"]*config["SpecNumPoints"]*(config["relax_delay"] + config["qubit_length"] + config["read_length"])*1e-6
#print("Time required for spec slice experiment is ", datetime.timedelta(seconds = time).strftime('%H::%M::%S'))
print(time)

Instance_specSlice = SpecSlice(path="dataTestSpecSlice", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
data_specSlice= SpecSlice.acquire(Instance_specSlice)
SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True)
SpecSlice.save_data(Instance_specSlice, data_specSlice)
print(Instance_specSlice.qubitFreq)
plt.show()

#%%
# TITLE Perform the spec slice with background subtracted
Instance_specSlice = SpecSlice_bkg_sub(path="dataTestSpecSlice_temp", cfg=config,
                                        soc=soc, soccfg=soccfg, outerFolder=outerFolder)
data_specSlice = SpecSlice_bkg_sub.acquire(Instance_specSlice)
SpecSlice_bkg_sub.save_data(Instance_specSlice, data_specSlice)
SpecSlice_bkg_sub.display(Instance_specSlice, data_specSlice, plotDisp=True)

#%%
# TITLE : Perform the spec slice with Post Selection
config_spec_ps = {
    'spec_reps' : 1000, # Converted to shots
    'initialize_pulse': False,
    'fridge_temp': 420,
    "qubit_pulse_style": "flat_top"
}
config_spec_ps = config | config_spec_ps
inst_specslice = SpecSlice_PS_sse(path="dataTestSpecSlice_PS", cfg=config_spec_ps,
                                        soc=soc, soccfg=soccfg, outerFolder=outerFolder)
data_specSlice_PS = inst_specslice.acquire()
data_specSlice_PS = inst_specslice.process_data(data = data_specSlice_PS)
inst_specslice.display(data = data_specSlice_PS, plotDisp=True)
inst_specslice.save_data(data_specSlice_PS)

#%%
# TITLE: Amplitude Rabi

UpdateConfig_spec = {

    # Experiment
    "qubit_gain_start": 1000,    # [DAC Units]
    "qubit_gain_step": 6000,   # [DAC Units] gain step size
    "qubit_gain_expts": 61,  # 26,  ### number of steps
    "AmpRabi_reps": 500,  # 10000,  # number of averages for the experiment
    "relax_delay": 500,

    # Qubit Tone
    "qubit_pulse_style": "arb",
    "sigma": 0.5,
    "flat_top_length": 10,
    "qubit_freq" : 620,
    "qubit_length" : 10,
    "use_switch": True,
}

config = config | UpdateConfig_spec

Instance_AmplitudeRabi = AmplitudeRabi(path="dataTestAmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                                       outerFolder=outerFolder)
data_AmplitudeRabi = AmplitudeRabi.acquire(Instance_AmplitudeRabi)
AmplitudeRabi.display(Instance_AmplitudeRabi, data_AmplitudeRabi, plotDisp=True)
AmplitudeRabi.save_data(Instance_AmplitudeRabi, data_AmplitudeRabi)
AmplitudeRabi.save_config(Instance_AmplitudeRabi)
#endregion
#%%
# TITLE: Transmission vs Power

UpdateConfig = {
    "yokoVoltage": -0.1433,
    "trans_gain_start": 20,
    "trans_gain_stop": 3000,
    "trans_gain_num": 101,
    "trans_reps": 1000,
    "read_pulse_style": "const",
    "readout_length": 20,  # [us]
    "trans_freq_start": 6671.5 - 1,  # [MHz]
    "trans_freq_stop": 6671.5 + 1,  # [MHz]
    "TransNumPoints": 101,
    "relax_delay": 2,
    "units":"DAC", # use "dB" or "DAC"
    "normalize": True,
}
config = BaseConfig | UpdateConfig

# Set the yoko voltage
yoko1.SetVoltage(config["yokoVoltage"])

# Run experiment
Instance_TransVsGain = TransVsGain(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_TransVsGain = TransVsGain.acquire(Instance_TransVsGain)
TransVsGain.save_data(Instance_TransVsGain, data_TransVsGain)
TransVsGain.save_config(Instance_TransVsGain)

#%%
# TITLE: Amplitude rabi Blob
UpdateConfig = {
    ##### define attenuators
    "yokoVoltage": -0.12,
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 50, # us
    "read_pulse_gain": 1960, # [DAC units]
    "read_pulse_freq": 6672.7,
    ##### spec parameters for finding the qubit frequency
    "qubit_freq_start": 10,
    "qubit_freq_stop": 100,
    "RabiNumPoints": 151,  ### number of points
    "qubit_pulse_style": "const",
    "sigma": 0.5, ### units us, define a 20ns sigma
    "qubit_length": 10,
    "flat_top_length": 10, ### in us
    "relax_delay": 5,  ### turned into us inside the run function
    ##### amplitude rabi parameters
    "qubit_gain_start": 1000,
    "qubit_gain_step": 1000, ### stepping amount of the qubit gain
    "qubit_gain_expts": 10, ### number of steps
    "AmpRabi_reps": 800,  # number of averages for the experiment

    "use_switch": True,
}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
print('Running Rabi Chevron: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
time_estimate = (config['relax_delay'] + config['sigma']*4 + config['read_length'])*config['RabiNumPoints']*config['qubit_gain_expts']*config['AmpRabi_reps']*1e-6/60
print("Time required is - " + str(time_estimate) + " in min")
Instance_AmplitudeRabi_Blob = AmplitudeRabi_Blob(path="dataTestRabiAmpBlob", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
data_AmplitudeRabi_Blob = AmplitudeRabi_Blob.acquire(Instance_AmplitudeRabi_Blob)
AmplitudeRabi_Blob.save_data(Instance_AmplitudeRabi_Blob, data_AmplitudeRabi_Blob)
AmplitudeRabi_Blob.save_config(Instance_AmplitudeRabi_Blob)

#%%
# TITLE: T1 measurement

UpdateConfig = {
    "yokoVoltage": -0.12,

    # Readout
    "read_pulse_style": "const",
    "read_length": 50,
    "read_pulse_gain": 1960,
    "read_pulse_freq": 6672.7,

    # Qubit Tone
    "qubit_freq": 65.4,
    "qubit_gain": 5000,
    "qubit_pulse_style": "const",
    "sigma": 1,
    "flat_top_length": 10,
    "qubit_length": 10,

    # Experiment
    "relax_delay": 20000,
    "start": 0,
    "step": 300,
    "expts": 21,
    "reps": 4000,

    # Switch
    "use_switch": True,
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])
print("Voltage is ", yoko1.GetVoltage(), " Volts")

# Estimate time required to run this experiment
tot_time = (np.sum(np.linspace(config["start"], config['step'] * (config["expts"] - 1), config["expts"]))
            + config["expts"]*config["relax_delay"])*config["reps"]
print("Time required for T1 Experiment is ", datetime.timedelta(seconds = tot_time*1e-6))

# Run Experiment
inst_t1 = T1Experiment(path="dataTestT1Experiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg,  progress=True)
data_t1 = inst_t1.acquire()

# Process
inst_t1.display(data_t1, plotDisp=True)
inst_t1.save_data(data_t1)
inst_t1.save_config()

#%%
#
# # #### loop over readout parameters
# # delay_vec = np.linspace(1000, 5000, 5)
# #
# # for idx in range(len(delay_vec)):
# #     print('starting run number ' + str(idx))
# #     config["relax_delay"] = int(delay_vec[idx])
# #     print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
# #
# #     Instance_T1Experiment = T1Experiment(path="dataTestT1Experiment_DelaySweep", outerFolder=outerFolder, cfg=config, soc=soc,
# #                                          soccfg=soccfg, progress=True)
# #     data_T1Experiment = T1Experiment.acquire(Instance_T1Experiment)
# #     T1Experiment.display(Instance_T1Experiment, data_T1Experiment, plotDisp=True, save_fig=True)
# #     T1Experiment.save_data(Instance_T1Experiment, data_T1Experiment)
# #     T1Experiment.save_config(Instance_T1Experiment)
#
# # # #
# # # # #### loop over a tight flux range
# # # # yoko_vec = np.linspace(-1.16 - 0.2, -1.16 + 0.2, 11)
# # # #
# # # # for idx in range(len(yoko_vec)):
# # # #     print('starting run number ' + str(idx))
# # # #     config["yokoVoltage"] = yoko_vec[idx]
# # # #     yoko1.SetVoltage(config["yokoVoltage"])
# # # #     print('starting scan: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
# # # #
# # # #     Instance_T1Experiment = T1Experiment(path="dataTestT1Experiment_yokoSweep", outerFolder=outerFolder, cfg=config, soc=soc,
# # # #                                          soccfg=soccfg, progress=True)
# # # #     data_T1Experiment = T1Experiment.acquire(Instance_T1Experiment)
# # # #     T1Experiment.display(Instance_T1Experiment, data_T1Experiment, plotDisp=True, save_fig=True)
# # # #     T1Experiment.save_data(Instance_T1Experiment, data_T1Experiment)
# # # #     T1Experiment.save_config(Instance_T1Experiment)
#endregion

# TITLE: T2 Measurement
#region Config File
# UpdateConfig = {
#     ##### define flux point
#     "yokoVoltage": -2.8,    ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 5, # us
#     "read_pulse_gain": 10000, # [DAC units]
#     "read_pulse_freq": 6437.2, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq": 2034.5 - 1.0,
#     "qubit_gain": 16000,
#     "pi2_qubit_gain": 8000,
#     "sigma": 0.150,  ### units us, define a 20ns sigma
#     "qubit_pulse_style": "arb", #### arb means gaussain here
#     # "flat_top_length": 0.080,
#     "relax_delay": 1000,  ### turned into us inside the run function
#     ##### T2 ramsey parameters
#     "start": 0.00, ### us
#     "step": 0.05, ### us
#     "expts": 101, ### number of experiemnts
#     "reps": 500, ### number of averages on each experiment
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_T2Experiment = T2Experiment(path="dataTestT2RExperiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_T2Experiment = T2Experiment.acquire(Instance_T2Experiment)
# T2Experiment.display(Instance_T2Experiment, data_T2Experiment, plotDisp=True)
# T2Experiment.save_data(Instance_T2Experiment, data_T2Experiment)
# T2Experiment.save_config(Instance_T2Experiment)
#
# # for idx in range(4):
# #     Instance_T2Experiment = T2Experiment(path="dataTestT2RExperiment", outerFolder=outerFolder, cfg=config, soc=soc,
# #                                          soccfg=soccfg)
# #     data_T2Experiment = T2Experiment.acquire(Instance_T2Experiment)
# #     T2Experiment.display(Instance_T2Experiment, data_T2Experiment, plotDisp=True)
# #     T2Experiment.save_data(Instance_T2Experiment, data_T2Experiment)
# #     T2Experiment.save_config(Instance_T2Experiment)
#endregion

# TITLE: T2 echo measurement
#region Config File
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -1.16,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 10000, # [DAC units]
#     "read_pulse_freq": 5988.37, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq": 1716.5,
#     "pi_qubit_gain": 3300,
#     "pi2_qubit_gain": 1650,
#     "sigma": 0.050,  ### units us, define a 20ns sigma
#     "qubit_pulse_style": "arb", #### arb means gaussain here
#     "relax_delay": 3000,  ### turned into us inside the run function
#     ##### T1 parameters
#     "start": 0, ### us
#     "step": 5, ### us
#     "expts": 201, ### number of experiemnts
#     "reps": 500, ### number of averages on each experiment
# }
# config = BaseConfig | UpdateConfig
# yoko1.SetVoltage(config["yokoVoltage"])
# print("Voltage is ", yoko1.GetVoltage(), " Volts")
#
# Instance_T2EchoExperiment = T2EchoExperiment(path="dataTestT2EchoExperiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg,  progress=True)
# data_T2EchoExperiment = T2EchoExperiment.acquire(Instance_T2EchoExperiment)
# T2EchoExperiment.display(Instance_T2EchoExperiment, data_T2EchoExperiment, plotDisp=True)
# T2EchoExperiment.save_data(Instance_T2EchoExperiment, data_T2EchoExperiment)
# T2EchoExperiment.save_config(Instance_T2EchoExperiment)
#endregion

# TITLE: Basic Single shot experiment
#region Config File
# UpdateConfig = {
#     # set yoko
#     "yokoVoltage": -2.25,    # [V]
#
#     # cavity parameters
#     "reps": 2000,   # Number of repetitions
#     "read_pulse_style": "const",    # Constant pulse
#     "read_length": 10,  # [us]
#     "read_pulse_gain": 8000,    # [us]
#     "read_pulse_freq": 6436.95,     # [MHz]
#
#     # qubit parameters
#     "qubit_pulse_style": "arb",     # Gaussian Pulse
#     "qubit_gain": 0,    # [DAC Units]
#     # "qubit_length": 10,  # [us] for constant qubit pulse
#     "sigma": 0.100,  # [us]
#     "qubit_freq": 525.0,   # [MHz]
#     "relax_delay": 5000,  # [us]
#
#     # define shots
#     "shots": 4000,   # this gets turned into "reps"
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# #region Optimize over parameters
# loop_len = 5
# # freq_vec = config["read_pulse_freq"] + np.linspace(-0.5, 0.5, loop_len)
# #qubit_gain_vec = np.linspace(10000, 29000, loop_len, dtype=int)
# read_gain_vec = np.linspace(5000, 9000, loop_len, dtype=int)
# fid_vec = np.zeros(loop_len)
# for idx in range(loop_len):
#     # config["read_pulse_freq"] = freq_vec[idx]
#     #config["qubit_gain"] = qubit_gain_vec[idx]
#     config["read_pulse_gain"] = read_gain_vec[idx]
#     Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
#     data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
#     SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)
#     SingleShotProgram.save_data(Instance_SingleShotProgram, data_SingleShot)
#     # SingleShotProgram.save_config(Instance_SingleShotProgram)
#
#     plt.show()
#     print(Instance_SingleShotProgram.fid)
#     fid_vec[idx] = Instance_SingleShotProgram.fid
#
# plt.figure(107)
# #plt.plot(qubit_gain_vec, fid_vec, 'o')
# #plt.xlabel('qubit gain')
#
# # plt.plot(read_gain_vec, fid_vec, 'o')
# # plt.xlabel('readout gain')
#
# plt.plot(freq_vec, fid_vec, 'o')
# plt.xlabel('read pulse freq')
# plt.ylabel('fidelity')
# plt.ylim([0,1])
# #endregion
#
# # Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,
# #                                                soc=soc, soccfg=soccfg)
# # data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# # SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)
#endregion

# TITLE: 2D single shot fidelity optimization
#region Config File
# UpdateConfig = {
#     ##### set yoko
#     "yokoVoltage": -7.2,
#     #### define basic parameters
#     ###### cavity
#     "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # [Clock ticks]
#     "read_pulse_gain": 3500, # [DAC units]
#     "read_pulse_freq": 5988.275, # [MHz]
#     ##### qubit spec parameters
#     "qubit_pulse_style": "arb",
#     "qubit_gain": 20000,
#     # "qubit_length": 10,  ###us, this is used if pulse style is const
#     "sigma": 0.200,  ### units us, define a 20ns sigma
#     "qubit_freq": 1202.5,
#     "relax_delay": 1000,  ### turned into us inside the run function
#     #### define shots
#     "shots": 1000, ### this gets turned into "reps"
#     #### define the loop parameters
#     "x_var": "read_pulse_freq",
#     "x_start": 5988.275 - 0.5,
#     "x_stop": 5988.275 + 0.5,
#     "x_num": 21,
#
#     "y_var": "read_pulse_gain",
#     "y_start": 3000,
#     "y_stop": 5000,
#     "y_num": 3,
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_SingleShot_2Dsweep = SingleShot_2Dsweep(path="dataTestSingleShot_2Dsweep", outerFolder=outerFolder, cfg=config,
#                                                soc=soc, soccfg=soccfg)
# data_SingleShot_2Dsweep = SingleShot_2Dsweep.acquire(Instance_SingleShot_2Dsweep)
# SingleShot_2Dsweep.save_data(Instance_SingleShot_2Dsweep, data_SingleShot_2Dsweep)
# SingleShot_2Dsweep.save_config(Instance_SingleShot_2Dsweep)
#endregion

# TITLE: Amplitude rabi Blob with post selection
#region Config File
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -2.25,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 8000, # [DAC units]
#     "read_pulse_freq": 6436.95, # [MHz]
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 2815,
#     "qubit_freq_stop": 2830,
#     "RabiNumPoints": 21,  ### number of points
#     "qubit_pulse_style": "arb",
#     "sigma": 0.1,  ### units us, define a 20ns sigma
#     # "flat_top_length": 0.600, ### in us
#     "relax_delay": 2000,  ### turned into us inside the run function
#     ##### amplitude rabi parameters
#     "qubit_gain_start": 0,
#     "qubit_gain_step": 1000, ### stepping amount of the qubit gain
#     "qubit_gain_expts": 11, ### number of steps
#     # "AmpRabi_reps": 2000,  # number of averages for the experiment
#     ##### define number of clusters to use
#     "cen_num": 2,
#     "shots": 3000,  ### this gets turned into "reps"
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_AmplitudeRabi_PS = AmplitudeRabi_PS(path="dataTestAmplitudeRabi_PS", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_AmplitudeRabi_PS = AmplitudeRabi_PS.acquire(Instance_AmplitudeRabi_PS)
# AmplitudeRabi_PS.save_data(Instance_AmplitudeRabi_PS, data_AmplitudeRabi_PS)
# AmplitudeRabi_PS.save_config(Instance_AmplitudeRabi_PS)
# endregion

#
# #################################### code for running Amplitude rabi Blob while sweeping flux
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -0.18,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 5, # us
#     "read_pulse_gain": 8000, # [DAC units]
#     "read_pulse_freq": 6064.9, # [MHz]
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 290 - 20,
#     "qubit_freq_stop": 290 + 20,
#     "RabiNumPoints": 21,  ### number of points
#     "qubit_pulse_style": "arb",
#     "sigma": 0.015,  ### units us, define a 20ns sigma
#     "qubit_gain": 18000,
#     # "flat_top_length": 0.200, ### in us
#     "relax_delay": 100,  ### turned into us inside the run function
#     ##### define the yoko voltage
#     "yokoVoltageStart": -0.18 - 0.02,
#     "yokoVoltageStop": -0.18 + 0.02,
#     "yokoVoltageNumPoints": 11,
#     # "AmpRabi_reps": 2000,  # number of averages for the experiment
#     ##### define number of clusters to use
#     "cen_num": 2,
#     "shots": 4000,  ### this gets turned into "reps"
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
#
# Instance_AmplitudeRabiFlux_PS = AmplitudeRabiFlux_PS(path="dataTestAmplitudeRabiFlux_PS", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_AmplitudeRabiFlux_PS = AmplitudeRabiFlux_PS.acquire(Instance_AmplitudeRabiFlux_PS)
# AmplitudeRabiFlux_PS.save_data(Instance_AmplitudeRabiFlux_PS, data_AmplitudeRabiFlux_PS)
# AmplitudeRabiFlux_PS.save_config(Instance_AmplitudeRabiFlux_PS)


# # # ##################################################################################################################
# ################################## code for running qubit spec on repeat
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -2.97 - 0.00,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 20, # us
#     "read_pulse_gain": 11000, # [DAC units]
#     "read_pulse_freq": 6437.5,
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq_start": 1908.5 - 5,
#     "qubit_freq_stop": 1908.5 + 5,
#     "SpecNumPoints": 201,  ### number of points
#     "qubit_pulse_style": "arb",
#     "sigma": 0.400,  ### units us
#     "qubit_length": 1, ### units us, doesnt really get used though
#     # "flat_top_length": 0.300, ### in us
#     "relax_delay": 800,  ### turned into us inside the run function
#     "qubit_gain": 400, # Constant gain to use
#     # "qubit_gain_start": 18500, # shouldn't need this...
#     "reps": 750,
#     ##### time parameters
#     "delay": 120, # s
#     "repetitions": 201,  ### number of steps
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# #
# Instance_QubitSpecRepeat = QubitSpecRepeat(path="dataQubitSpecRepeat", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_QubitSpecRepeat = QubitSpecRepeat.acquire(Instance_QubitSpecRepeat)
# QubitSpecRepeat.save_data(Instance_QubitSpecRepeat, data_QubitSpecRepeat)
# QubitSpecRepeat.save_config(Instance_QubitSpecRepeat)

# #
# for idx in range(5):
#     Instance_QubitSpecRepeat = QubitSpecRepeat(path="dataQubitSpecRepeat", outerFolder=outerFolder, cfg=config, soc=soc,
#                                                soccfg=soccfg, progress=True)
#     data_QubitSpecRepeat = QubitSpecRepeat.acquire(Instance_QubitSpecRepeat)
#     QubitSpecRepeat.save_data(Instance_QubitSpecRepeat, data_QubitSpecRepeat)
#     QubitSpecRepeat.save_config(Instance_QubitSpecRepeat)

# ##################################################################################################################
# ################################## code for running qubit spec on repeat on multiple qubits
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -3.1,
#     ########################### Qubit 1
#     ###### cavity
#     "read1_pulse_style": "const", # --Fixed
#     "read1_length": 20, # us
#     "read1_pulse_gain": 8000, # [DAC units]
#     "read1_pulse_freq": 6437.5,
#     ##### spec parameters for finding the qubit frequency
#     "qubit1_freq_start": 1789.5 - 10,
#     "qubit1_freq_stop": 1789.5 + 10,
#     "SpecNumPoints1": 101,  ### number of points
#     "qubit1_pulse_style": "arb",
#     "sigma1": 0.400,  ### units us
#     # "qubit1_length": 1, ### units us, doesnt really get used though
#     # "flat_top_length": 0.025, ### in us
#     "qubit1_gain": 12000, # Constant gain to use
#     # "qubit_gain_start": 18500, # shouldn't need this...
#
#     ############################ Qubit 2
#     ###### cavity
#     "read2_pulse_style": "const",  # --Fixed
#     "read2_length": 20,  # us
#     "read2_pulse_gain": 8000,  # [DAC units]
#     "read2_pulse_freq": 6437.5,
#     ##### spec parameters for finding the qubit frequency
#     "qubit2_freq_start": 2925.0 - 10,
#     "qubit2_freq_stop": 2925.0 + 10,
#     "SpecNumPoints2": 101,  ### number of points
#     "qubit2_pulse_style": "arb",
#     "sigma2": 0.400,  ### units us
#     # "qubit2_length": 1,  ### units us, doesnt really get used though
#     # "flat_top_length": 0.025, ### in us
#     "qubit2_gain": 2000,  # Constant gain to use
#     # "qubit_gain_start": 18500, # shouldn't need this...
#
#     #### for both qubits
#     "relax_delay": 750,  ### turned into us inside the run function
#     "reps": 750,
#     ##### time parameters
#     "delay":  120, # s
#     "repetitions": 331,  ### number of steps
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# #
# Instance_TwoQubitFluxDrift = TwoQubitFluxDrift(path="dataTwoQubitFluxDrift", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_TwoQubitFluxDrift = TwoQubitFluxDrift.acquire(Instance_TwoQubitFluxDrift)
# TwoQubitFluxDrift.save_data(Instance_TwoQubitFluxDrift, data_TwoQubitFluxDrift)
# TwoQubitFluxDrift.save_config(Instance_TwoQubitFluxDrift)

#%%
# #TITLE Constant tone experiment
UpdateConfig = {
    ###### cavity
    "read_pulse_style": "const",  # --Fixed
    "gain": 0,  # [DAC units]
    "freq": 4000,  # [MHz]
    "channel": 1,  # TODO default value
        "nqz": 1,  # TODO default value
}

config = BaseConfig | UpdateConfig
#

ConstantTone_Instance = ConstantTone_Experiment(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_ConstantTone = ConstantTone_Experiment.acquire(ConstantTone_Instance)
ConstantTone_Experiment.save_data(ConstantTone_Instance, data_ConstantTone)
ConstantTone_Experiment.save_config(ConstantTone_Instance)
print("Done")
#%%

# UpdateConfig = {
#     # Set Yoko Voltage
#     "yokoVoltage": -1.8,
#
#     # Readout Parameters
#     "read_pulse_style": "const",  # Constant Tone
#     "read_length": 5,  # [us]
#     "read_pulse_gain": 7400,  # [DAC units]
#     "read_pulse_freq": 6437.4,  # [MHz]
#
#     # qubit parameters
#     "qubit_pulse_style": "arb",
#     "sigma": 0.100,
#     "qubit_ge_gain": 600,
#     "qubit_ge_freq": 2243.4,
#     "qubit_ef_gain": 8000,
#     "qubit_ef_freq": 2081.5,
#     "relax_delay": 500,
#
#     # Experiment time
#     "cen_num": 3,
#     "use_switch": True,
# }
# config = BaseConfig | UpdateConfig
#
# Update_config_ss = {
#     # qubit parameters
#     "qubit_pulse_style": "arb",
#     "sigma": 0.100,
#     "qubit_ge_gain": 250,
#     "qubit_ef_gain": 8000,
#
#     # Experiment parameters
#     'shots': 40000,
#     'relax_delay': 4000,
#     'initialize_pulse': True,
#     'fridge_temp': 10.0,
#     'qubit_freq': 2200,
# }
# config_ss = config | Update_config_ss
#
# scan_time = (config_ss["relax_delay"] * config_ss["shots"] * 2) * 1e-6 / 60
# print('estimated time: ' + str(round(scan_time, 2)) + ' minutes')
 #Instance_SingleShotSSE = SingleShotSSE(path="dataSingleShot_TempCalc_temp_",
#                                        outerFolder=outerFolder,
#                                        cfg=config_ss,
#                                        soc=soc, soccfg=soccfg)
# data_SingleShotSSE = SingleShotSSE.acquire(Instance_SingleShotSSE)
# data_SingleShotSSE = SingleShotSSE.process_data(Instance_SingleShotSSE, data_SingleShotSSE, cen_num = 3)
# SingleShotSSE.display(Instance_SingleShotSSE, data_SingleShotSSE, plotDisp=True, save_fig=True)
# SingleShotSSE.save_data(Instance_SingleShotSSE, data_SingleShotSSE)
# SingleShotSSE.save_config(Instance_SingleShotSSE)

#%%
# # TITLE: Auto Calibration
#
# # import the measurement class
# from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAutoCalibrator import CalibratedFlux
#
# # Defining changes to the config
# UpdateConfig = {
#     # define the yoko voltage
#     "yokoVoltageStart": 0.0,
#     "yokoVoltageStop": 10.0,
#     "yokoVoltageNumPoints": 81,
#
#     # cavity and readout
#     "trans_reps": 50,
#     "read_pulse_style": "const",
#     "read_length": 20,  # us
#     "read_pulse_gain": 7000,  # [DAC units]
#     "trans_freq_start": 6437.4 - 2.0,  # [MHz]
#     "trans_freq_stop": 6437.4 + 2.0,  # [MHz]
#     "TransNumPoints": 51,
#
#     # Experiment Parameters
#     "relax_delay": 5,
#     'use_switch': True,
# }
# config = BaseConfig | UpdateConfig
#
# yoko_calibration = CalibratedFlux(path="data_calibration", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg)
# yoko_calibration.calibrate()
# yoko_calibration.save_data()
# yoko_calibration.display()

#%%