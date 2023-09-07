
#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from WTF.Client_modules.Calib.initialize import *
from WTF.Client_modules.Helpers.hist_analysis import *
from WTF.Client_modules.Helpers.MixedShots_analysis import *
from matplotlib import pyplot as plt

from WTF.Client_modules.Experiments.mTransmission import Transmission
from WTF.Client_modules.Experiments.mSpecSlice import SpecSlice
from WTF.Client_modules.Experiments.mSpecVsFlux import SpecVsFlux
from WTF.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from WTF.Client_modules.Experiments.mAmplitudeRabi import AmplitudeRabi
from WTF.Client_modules.Experiments.mAmplitudeRabi_Blob import AmplitudeRabi_Blob
from WTF.Client_modules.Experiments.mT1Experiment import T1Experiment
from WTF.Client_modules.Experiments.mT2Experiment import T2Experiment
from WTF.Client_modules.Experiments.mfastFlux import LoopbackProgramFastFlux
from WTF.Client_modules.Experiments.mTransVsAtten import TransVsAtten
from WTF.Client_modules.Experiments.mTransVsGain import TransVsGain
from WTF.Client_modules.Experiments.mFF_Testing import LoopbackProgramFF_Testing

#### define the saving path
outerFolder = "Z:\JakeB\Data\WTF01_A2_RFSOC\\"

#### define the attenuators
# cavityAtten = attenuator(27787, attenuation_int= 35, print_int = False)
###qubitAtten = attenuator(27797, attenuation_int= 10, print_int = False)

# Configure for transmission experiment
UpdateConfig_transmission={
    "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "readout_length": 3, # us
    "read_pulse_gain": 1600, # [DAC units]
    "read_pulse_freq": 892.50, # [MHz] actual frequency is this number + "cavity_LO"
    ##### define tranmission experiment parameters
    "TransSpan": 2, ### MHz, span will be center+/- this parameter
    "TransNumPoitns": 100, ### number of points in the transmission frequecny
    "cav_Atten": 35, #### cavity attenuator attenuation value
}

# Configure for qubit experiment
UpdateConfig_qubit = {
    "qubit_pulse_style": "const",
    "qubit_gain": 30000,
    "qubit_freq": 4987,
    "qubit_length": 1000,
    ##### define spec slice experiment parameters
    "qubit_freq_start": 4915,
    "qubit_freq_stop": 5015,
    "SpecNumPoints": 150,  ### number of points
    "qubit_Atten": 10, ### qubit attenuator value
    'spec_reps': 100,
    ##### define the yoko voltage
    "yokoVoltage": -0.053,
}

UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit
config = BaseConfig | UpdateConfig ### note that UpdateConfig will overwrite elements in BaseConfig

#### update the qubit and cavity attenuation
# cavityAtten.SetAttenuation(config["cav_Atten"])
###qubitAtten.SetAttenuation(config["qubit_Atten"])

# ### set the yoko frequency
# yoko1.SetVoltage(config["yokoVoltage"])
# print("Voltage is ", yoko1.GetVoltage(), " Volts")

#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# print(soccfg)

plt.ioff()

###################################### code for runnning basic transmission and specSlice
# ### perform the cavity transmission experiment

# Instance_trans = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_trans= Transmission.acquire(Instance_trans)
# Transmission.display(Instance_trans, data_trans, plotDisp=True)
# Transmission.save_data(Instance_trans, data_trans)

#
#
# #
# ### update the transmission frequency to be the peak
# config["read_pulse_freq"] = Instance_trans.peakFreq
#
#### Qubit Spec experiment, readjust the number of reps
# config["reps"] = 2000
#
# Instance_specSlice = SpecSlice(path="dataTestSpecSlice", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_specSlice= SpecSlice.acquire(Instance_specSlice)
# SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True)
# # SpecSlice.save_data(Instance_specSlice, data_specSlice)


########################################################################################################################

####################################### code for transmission vs power
UpdateConfig = {
    ##### define attenuators
    "cav_Atten": 50,  #### cavity attenuator attenuation value
    "yokoVoltage": -0.128,
    # ##### define the attenuator values
    # "trans_attn_start": 30,
    # "trans_attn_stop": 10,
    # "trans_attn_num": 21,
    ##### change gain instead option
    "trans_gain_start": 0,
    "trans_gain_stop": 7500,
    "trans_gain_num": 76,
    ###### cavity
    "trans_reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const",  # --Fixed
    "readout_length": 15,  # [Clock ticks]
    # "read_pulse_gain": 10000,  # [DAC units]
    "trans_freq_start": 890.0,  # [MHz] actual frequency is this number + "cavity_LO"
    "trans_freq_stop": 895.0,  # [MHz] actual frequency is this number + "cavity_LO"
    "TransNumPoints": 200,  ### number of points in the transmission frequecny
}

config = BaseConfig | UpdateConfig

# #### update the qubit and cavity attenuation
# cavityAtten.SetAttenuation(config["cav_Atten"])
# yoko1.SetVoltage(config["yokoVoltage"])
#
# # ##### run actual experiment
# # Instance_TransVsAtten = TransVsAtten(path="dataTestTransVsAtten", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# # data_TransVsAtten = TransVsAtten.acquire(Instance_TransVsAtten)
# # TransVsAtten.save_data(Instance_TransVsAtten, data_TransVsAtten)
# # TransVsAtten.save_config(Instance_TransVsAtten)
#
# #### change gain instead of attenuation
# Instance_TransVsGain = TransVsGain(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_TransVsGain = TransVsGain.acquire(Instance_TransVsGain)
# TransVsGain.save_data(Instance_TransVsGain, data_TransVsGain)
# TransVsGain.save_config(Instance_TransVsGain)


# ########################################################################################################################



####################################### code for running spec vs flux experiement
UpdateConfig = {
    ##### define attenuators
    "qubit_Atten": 20,  ### qubit attenuator value
    "cav_Atten": 50,  #### cavity attenuator attenuation value
    ##### define the yoko voltage
    "yokoVoltageStart": -0.060,
    "yokoVoltageStop": -0.050,
    "yokoVoltageNumPoints": 3,
    ###### cavity
    "trans_reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const",  # --Fixed
    "readout_length": 5,  # [Clock ticks]
    "pulse_gain": 30000,  # [DAC units]
    "trans_freq_start": 892.5,  # [MHz] actual frequency is this number + "cavity_LO"
    "trans_freq_stop": 894.5,  # [MHz] actual frequency is this number + "cavity_LO"
    "TransNumPoints": 10,  ### number of points in the transmission frequecny
    ##### qubit spec parameters
    "spec_reps": 1000,
    "qubit_pulse_style": "const",
    "qubit_gain": 30000,
    "qubit_length": 10, ###us
    "qubit_freq_start": 4915,
    "qubit_freq_stop": 5015,
    "SpecNumPoints": 10,  ### number of points
}

config = BaseConfig | UpdateConfig

# #### update the qubit and cavity attenuation
# cavityAtten.SetAttenuation(config["cav_Atten"])
# ###qubitAtten.SetAttenuation(config["qubit_Atten"])
#
# ##### run actual experiment
# Instance_SpecVsFlux = SpecVsFlux(path="dataTestSpecVsFlux", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_SpecVsFlux = SpecVsFlux.acquire(Instance_SpecVsFlux)
# SpecVsFlux.save_data(Instance_SpecVsFlux, data_SpecVsFlux)
# SpecVsFlux.save_config(Instance_SpecVsFlux)



####################################### code for running basic single shot exerpiment
UpdateConfig = {
    ##### define attenuators
    "qubit_Atten": 0,  ### qubit attenuator value
    "cav_Atten": 45,  #### cavity attenuator attenuation value
    "yokoVoltage": -0.060,
    ###### cavity
    "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    "read_pulse_style": "const", # --Fixed
    "readout_length": soc.us2cycles(5), # [Clock ticks]
    "read_pulse_gain":30000, # [DAC units]
    "read_pulse_freq": 893.25, # [MHz] actual frequency is this number + "cavity_LO"
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "qubit_gain": 30000,
    "qubit_length": 10,  ###us, this is used if pulse style is const
    "sigma": 0.050,  ### units us, define a 20ns sigma
    "qubit_freq": 4927.33,
    ##### define shots
    "shots": 2000, ### this gets turned into "reps"
}
config = BaseConfig | UpdateConfig

# yoko1.SetVoltage(config["yokoVoltage"])
# cavityAtten.SetAttenuation(config["cav_Atten"])
# ###qubitAtten.SetAttenuation(config["qubit_Atten"])
#
# ##### run the single shot experiment
# Instance_SingleShotProgram = SingleShotProgram(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_SingleShot = SingleShotProgram.acquire(Instance_SingleShotProgram)
# SingleShotProgram.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True)


# ####################################### code for running Amplitude rabi
UpdateConfig = {
    ##### define attenuators
    "qubit_Atten": 0,  ### qubit attenuator value
    "cav_Atten": 24,  #### cavity attenuator attenuation value
    "yokoVoltage": -0.055,
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 2, # us
    "read_pulse_gain": 30000, # [DAC units]
    "read_pulse_freq": 891.0, # [MHz] actual frequency is this number + "cavity_LO"
    "TransSpan": 1, ### MHz, span will be center+/- this parameter
    "TransNumPoitns": 100, ### number of points in the transmission frequecny
    "trans_reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
    ##### spec parameters for finding the qubit frequency
    "qubit_freq_start": 4880,
    "qubit_freq_stop": 4980,
    "SpecNumPoints": 200,  ### number of points
    "qubit_gain": 5000,
    "sigma": 0.050,  ### units us, define a 20ns sigma
    "qubit_pulse_style": "arb", #### arb means gaussain here
    "relax_delay": 50,  ### turned into us inside the run function
    "spec_reps": 2000, ### number of reps
    ##### amplitude rabi parameters
    "qubit_freq": 4969.0, ### just an estimate
    "qubit_gain_start": 0,
    "qubit_gain_step": 300, ### stepping amount of the qubit gain
    "qubit_gain_expts": 100, ### number of steps
    "AmpRabi_reps": 2000,  # number of averages for the experiment
}
config = BaseConfig | UpdateConfig

# yoko1.SetVoltage(config["yokoVoltage"])
# cavityAtten.SetAttenuation(config["cav_Atten"])
###qubitAtten.SetAttenuation(config["qubit_Atten"])

# Instance_trans = Transmission(path="dataTestTransmission", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_trans= Transmission.acquire(Instance_trans)
# Transmission.display(Instance_trans, data_trans, plotDisp=True)
# Transmission.save_data(Instance_trans, data_trans)
#
# plt.show(block=False)
# plt.pause(0.1)
#
# ### update the transmission frequency to be the peak
# config["read_pulse_freq"] = Instance_trans.peakFreq

# Instance_specSlice = SpecSlice(path="dataTestSpecSlice", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_specSlice= SpecSlice.acquire(Instance_specSlice)
# SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True)
# SpecSlice.save_data(Instance_specSlice, data_specSlice)
#
# plt.show(block=False)
# plt.pause(0.1)
#
# ## update the transmission frequency to be the peak
# config["qubit_freq"] = Instance_specSlice.qubitFreq
# print("new qubit freq: " + str(config["qubit_freq"]))
#
# Instance_AmplitudeRabi = AmplitudeRabi(path="dataTestAmplitudeRabi", cfg=config,soc=soc,soccfg=soccfg, outerFolder = outerFolder)
# data_AmplitudeRabi = AmplitudeRabi.acquire(Instance_AmplitudeRabi)
# AmplitudeRabi.display(Instance_AmplitudeRabi, data_AmplitudeRabi, plotDisp=True)
# AmplitudeRabi.save_data(Instance_AmplitudeRabi, data_AmplitudeRabi)
# AmplitudeRabi.save_config(Instance_AmplitudeRabi)


# ####################################### code for running Amplitude rabi
UpdateConfig = {
    ##### define attenuators
    "cav_Atten": 17,  #### cavity attenuator attenuation value
    "yokoVoltage": -0.128,
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 10, # us
    "read_pulse_gain": 1500, # [DAC units]
    "read_pulse_freq": 893.50, # [MHz] actual frequency is this number + "cavity_LO"
    ##### spec parameters for finding the qubit frequency
    "qubit_freq_start": 4940,
    "qubit_freq_stop": 4960,
    "RabiNumPoints": 11,  ### number of points
    "qubit_pulse_style": "flat_top",
    "sigma": 0.015,  ### units us, define a 20ns sigma
    "flat_top_length": 0.025, ### in us
    "relax_delay": 1000,  ### turned into us inside the run function
    ##### amplitude rabi parameters
    "qubit_gain_start": 0,
    "qubit_gain_step": 300, ### stepping amount of the qubit gain
    "qubit_gain_expts": 101, ### number of steps
    "AmpRabi_reps": 200,  # number of averages for the experiment
}
config = BaseConfig | UpdateConfig

# yoko1.SetVoltage(config["yokoVoltage"])
# cavityAtten.SetAttenuation(config["cav_Atten"])
#
# Instance_AmplitudeRabi_Blob = AmplitudeRabi_Blob(path="dataTestRabiAmpBlob", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_AmplitudeRabi_Blob = AmplitudeRabi_Blob.acquire(Instance_AmplitudeRabi_Blob)
# AmplitudeRabi_Blob.save_data(Instance_AmplitudeRabi_Blob, data_AmplitudeRabi_Blob)
# # AmplitudeRabi_Blob.save_config(Instance_AmplitudeRabi_Blob)


######################################################################################################################
########### T1 measurement
UpdateConfig = {
    ##### define attenuators
    "cav_Atten": 15,  #### cavity attenuator attenuation value
    "yokoVoltage": -0.055,
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 10, # us
    "read_pulse_gain": 30000, # [DAC units]
    "read_pulse_freq": 891.0, # [MHz] actual frequency is this number + "cavity_LO"
    ##### spec parameters for finding the qubit frequency
    "qubit_freq": 4937.0,
    "qubit_gain": 27000,
    "sigma": 0.025,  ### units us, define a 20ns sigma
    "qubit_pulse_style": "arb", #### arb means gaussain here
    "relax_delay": 1000,  ### turned into us inside the run function
    ##### T1 parameters
    "start": 0, ### us
    "step": 1, ### us
    "expts": 500, ### number of experiemnts
    "reps": 1000, ### number of averages on each experiment
}
config = BaseConfig | UpdateConfig

# yoko1.SetVoltage(config["yokoVoltage"])
# cavityAtten.SetAttenuation(config["cav_Atten"])
#
# Instance_T1Experiment = T1Experiment(path="dataTestT1Experiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_T1Experiment = T1Experiment.acquire(Instance_T1Experiment)
# T1Experiment.display(Instance_T1Experiment, data_T1Experiment, plotDisp=True)
# T1Experiment.save_data(Instance_T1Experiment, data_T1Experiment)
# T1Experiment.save_config(Instance_T1Experiment)


######################################################################################################################
########### T2 measurement
UpdateConfig = {
    ##### define attenuators
    "cav_Atten": 15,  #### cavity attenuator attenuation value
    "yokoVoltage": -0.055,
    ###### cavity
    "read_pulse_style": "const", # --Fixed
    "read_length": 10, # us
    "read_pulse_gain": 30000, # [DAC units]
    "read_pulse_freq": 891.0, # [MHz] actual frequency is this number + "cavity_LO"
    ##### spec parameters for finding the qubit frequency
    "qubit_freq": 4937.0 - 10,
    "qubit_gain": 27000,
    "sigma": 0.025,  ### units us, define a 20ns sigma
    "qubit_pulse_style": "arb", #### arb means gaussain here
    "relax_delay": 1500,  ### turned into us inside the run function
    ##### T2 ramsey parameters
    "start": 0.010, ### us
    "step": 0.005, ### us
    "expts": 150, ### number of experiemnts
    "reps": 200, ### number of averages on each experiment
}
config = BaseConfig | UpdateConfig

# yoko1.SetVoltage(config["yokoVoltage"])
# cavityAtten.SetAttenuation(config["cav_Atten"])
#
# Instance_T2Experiment = T2Experiment(path="dataTestT2Experiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_T2Experiment = T2Experiment.acquire(Instance_T2Experiment)
# T2Experiment.display(Instance_T2Experiment, data_T2Experiment, plotDisp=True)
# T2Experiment.save_data(Instance_T2Experiment, data_T2Experiment)
# T2Experiment.save_config(Instance_T2Experiment)

###################################################################################################################
###### testing fast flux experiement
config={
    "reps": 2000,  # this will used for all experiements below unless otherwise changed in between trials
    # "ff_pulse_style": "const", # --Fixed
    "ff_length": soc.us2cycles(100), # [Clock ticks]
    "ff_gain": 10000, # [DAC units]
    "ff_freq": 0, # [MHz] actual frequency is this number + "cavity_LO"
    ##### define tranmission experiment parameters
    # "ff_nqz": 1, ### MHz, span will be center+/- this parameter
    "relax_delay": 50, ### number of points in the transmission frequecny
    # "ff_ch": 4, #### cavity attenuator attenuation value
    "soft_avgs": 20000
}

#
# ###prog = LoopbackProgramFastFlux(soccfg, config)
# ###prog.acquire_decimated(soc, load_pulses=True, progress=False)

####################################################################################################################
########### testing driving a fast flux pulse continuously
UpdateConfig = {
    "reps": 200000,  #
    "ff_pulse_style": "arb", #
    "ff_sigma": soc.us2cycles(0.005), # [Clock ticks]
    "ff_gain": 30000, # [DAC units]
    "ff_freq": 0, # [MHz] actual frequency is this number + "cavity_LO"
    "length_us": 0.015,
}
config = BaseConfig | UpdateConfig

#
Instance_FF_Testing = LoopbackProgramFF_Testing(cfg=config,soccfg=soccfg)
Instance_FF_Testing.acquire(soc, load_pulses=True, progress=False)



#####################################################################################################################
plt.show()

# #
# plt.show(block = True)
