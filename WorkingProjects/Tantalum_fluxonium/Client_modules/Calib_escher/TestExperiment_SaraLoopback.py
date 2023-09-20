
#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mLoopback import Loopback
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mTransmission import Transmission
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSpecSlice import SpecSlice
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mTransVsGain import TransVsGain
from matplotlib import pyplot as plt

#### define the saving path
outerFolder = "Z:\Parth\Data\Tantalum_Fluxonium\TF1SC1_B3_RFSOC\Q1\\"

###qubitAtten = attenuator(27797, attenuation_int= 10, print_int = False)


#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
print(soccfg)

plt.ioff()

config = {"res_ch": 0,  # --Fixed
          "ro_chs": [0],  # --Fixed
          "reps": 1,  # --Fixed
          "relax_delay": 1.0,  # --us
          "res_phase": 0,  # --degrees
          "pulse_style": "const",  # --Fixed

          "length": 200,  # [Clock ticks]
          # Try varying length from 10-100 clock ticks

          "readout_length": 1000,  # [Clock ticks]
          # Try varying readout_length from 50-1000 clock ticks

          "pulse_gain": 30000,  # [DAC units]
          # Try varying pulse_gain from 500 to 30000 DAC units

          "pulse_freq": 559.25,  # [MHz]
          # In this program the signal is up and downconverted digitally so you won't see any frequency
          # components in the I/Q traces below. But since the signal gain depends on frequency,
          # if you lower pulse_freq you will see an increased gain.

          "adc_trig_offset": 200,  # [Clock ticks]
          # Try varying adc_trig_offset from 100 to 220 clock ticks

          "soft_avgs": 50,
          # Try varying soft_avgs from 1 to 200 averages
          "yokoVoltage": -0.1
          }

## set the yoko frequency
yoko1.SetVoltage(config["yokoVoltage"])
print("Voltage is ", yoko1.GetVoltage(), " Volts")

### Loopback to calibrate the ADC offset
Instance = Loopback(path="dataTestLoopback", cfg=config,soc=soc,soccfg=soccfg, outerFolder=outerFolder)
data= Loopback.acquire(Instance)
Loopback.display(Instance, data)
Loopback.save_data(Instance, data)
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


#####################################################################################################################
plt.show()

# #
# plt.show(block = True)
