#%%
import os
from matplotlib import pyplot as plt
import datetime

from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mQubit_EF_Rabi import Qubit_ef_rabi , Qubit_ef_rabiChevron
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mQubit_EF_Rabi import Qubit_ef_RPM
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mQubit_ef_spectroscopy import Qubit_ef_spectroscopy
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShot_individual_state import SingleShotProgram_ef

# Define the base folder for saving files
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\TF4\\"

# Only run this if no proxy already exists
soc, soccfg = makeProxy()

# print(soccfg) # Can run this to print soc information

# Define switch configs
SwitchConfig = {
    "trig_buffer_start": 0.035, # in us
    "trig_buffer_end": 0.024, # in us
    "trig_delay": 0.07, # in us
}
BaseConfig = BaseConfig  | SwitchConfig

#%%

# TITLE : qubit ef spectroscopy
UpdateConfig = {
    # Yoko
    "yokoVoltage": 6.729,

    # Cavity
    "read_pulse_style": "const",
    "read_length": 4, # us
    "read_pulse_gain": 14000, # [DAC units]
    "read_pulse_freq": 6437.1,

    # g-e parameters
    "qubit_ge_freq": 2054.04,
    "qubit_ge_gain": 2000,

    # e-f parameters
    "qubit_ef_freq_start": 1600,
    "qubit_ef_freq_step": 1,
    "SpecNumPoints": 401,
    'qubit_ef_gain': 16000,
    "qubit_pulse_style": "arb",
    "sigma": 1.00,
    "relax_delay": 500,  #
    "reps": 800,
    'use_switch': True,
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])
# #
Instance_Qubit_ef_spectroscopy = Qubit_ef_spectroscopy(path="dataQubit_ef_spectroscopy", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
data_Qubit_ef_spectroscopy = Qubit_ef_spectroscopy.acquire(Instance_Qubit_ef_spectroscopy)
Qubit_ef_spectroscopy.save_data(Instance_Qubit_ef_spectroscopy, data_Qubit_ef_spectroscopy)
Qubit_ef_spectroscopy.save_config(Instance_Qubit_ef_spectroscopy)
Qubit_ef_spectroscopy.display(Instance_Qubit_ef_spectroscopy, data_Qubit_ef_spectroscopy, plotDisp=True)

#%%
# TITLE: qubit ef rabi measurement
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -1.8,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 5, # us
#     "read_pulse_gain": 10000, # [DAC units]
#     "read_pulse_freq": 6437.4,
#     ###### qubit
#     # g-e parameters
#     "qubit_ge_freq": 2243.4, # MHz
#     "qubit_ge_gain": 600, # Gain for pi pulse in DAC units
#     "apply_ge": True,
#    # e-f parameters
#     "qubit_ef_freq": 2081.5,
#     "qubit_ef_gain_start": 0, #1167-10
#     "qubit_ef_gain_step": 200,
#     "RabiNumPoints": 51,  ### number of points
#     "qubit_pulse_style": "arb",
#     "qubit_length": 1, # us, changes experiment time but is necessary for "const" style
#     "sigma": 0.1,  ### units us
#     # "qubit_length": 1, ### units us, doesnt really get used though
#     # "flat_top_length": 0.025, ### in us
#     "relax_delay": 500,  ### turned into us inside the run function
#     # "qubit_gain": 25000, # Constant gain to use
#     # "qubit_gain_start": 18500, # shouldn't need this...
#     "reps": 2000, # number of averages of every experiment
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# # #
# Instance_Qubit_ef_rabi = Qubit_ef_rabi(path="dataQubit_ef_rabi", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_Qubit_ef_rabi = Qubit_ef_rabi.acquire(Instance_Qubit_ef_rabi)
# Qubit_ef_rabi.save_data(Instance_Qubit_ef_rabi, data_Qubit_ef_rabi)
# Qubit_ef_rabi.save_config(Instance_Qubit_ef_rabi)
# Qubit_ef_rabi.display(Instance_Qubit_ef_rabi, data_Qubit_ef_rabi, plotDisp=True)
#%%

# TITLE: Qubit EF Rabi Chevron
#
# # Making plots update : interactive mode on
# plt.ion()
#
# # Defining Config
# UpdateConfig = {
#     # External Flux Voltage
#     "yokoVoltage": -1.8,
#
#     # Readout
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 5, # us
#     "read_pulse_gain": 10000, # [DAC units]
#     "read_pulse_freq": 6437.4,
#
#     # g-e parameters
#     "apply_ge": False,
#     "qubit_ge_freq": 2243.44, # MHz
#     "qubit_ge_gain": 600, # Gain for pi pulse in DAC units
#
#     # Rabi Chevron
#     "qubit_ef_freq_start": 2075,
#     "qubit_ef_freq_step": 0.5,
#     "qubit_ef_freq_pts": 20,
#     "qubit_ef_gain_start": 0,
#     "qubit_ef_gain_step": 250,
#     "RabiNumPoints": 40,
#
#     # Pulse style
#     "qubit_pulse_style": "arb",
#     "sigma": 0.100,  ### units us, define a 20ns sigma
#
#     # Experiment Misc
#     "relax_delay": 1000,  ### turned into us inside the run function
#     "reps": 800, # number of averages of every experiment
#     'use_switch': True,
# }
# config = BaseConfig | UpdateConfig
#
# # Setting Yoko Voltage
# yoko1.SetVoltage(config["yokoVoltage"])
#
# # Begin Experiment
# rabi_chev_expt = Qubit_ef_rabiChevron(path="dataQubit_ef_RabiChev", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_rabi_chev_expt = rabi_chev_expt.acquire()
# rabi_chev_expt.save_data(data_rabi_chev_expt)
# rabi_chev_expt.save_config()
# rabi_chev_expt.display(data_rabi_chev_expt, plotDisp=True)


#%%
# TITLE : Qubit single shot e-f

UpdateConfig = {
    # set yoko
    "yokoVoltage": 6.729,

    # cavity
    "read_pulse_style": "const",
    "read_length": 4, # [us]
    "read_pulse_gain": 14000, # [DAC units]
    "read_pulse_freq": 6437.1, # [MHz]

    # qubit g-e pulse
    "qubit_pulse_style": "arb",
    "qubit_ge_gain": 2000, # [DAC units]
    "sigma": 1,  # [us]
    "qubit_ge_freq": 2054.04 , # [MHz]
    "relax_delay": 1500,  ### turned into us inside the run function
    "qubit_length": 1,

    # qubit e-f pulse
    "qubit_ef_freq": 1630.503,
    "qubit_ef_gain": 12000,

    # define shots
    "shots": 6000,
    'use_switch': True,
}
config = BaseConfig | UpdateConfig

# Set the YOKO Voltage
yoko1.SetVoltage(config["yokoVoltage"])
plt.close('all')
Instance_SingleShotProgram = SingleShotProgram_ef(path="dataTestSingleShotProgram", outerFolder=outerFolder, cfg=config,
                                                  soc=soc, soccfg=soccfg)
data_SingleShot = SingleShotProgram_ef.acquire(Instance_SingleShotProgram)
SingleShotProgram_ef.save_data(Instance_SingleShotProgram, data_SingleShot)
SingleShotProgram_ef.save_config(Instance_SingleShotProgram)
SingleShotProgram_ef.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=True, save_fig=True)

#%%
# Parameters to vary
qubit_ef_freq_arr = 1545.5 + np.linspace(-1, 1, 5)
qubit_ef_gain_arr = np.linspace(6000,10000,25, dtype = int)
fid = np.zeros((qubit_ef_freq_arr.size,qubit_ef_gain_arr.size))

for i in range(qubit_ef_freq_arr.size):
# for j in range(qubit_ef_gain_arr.size):
    config["qubit_ef_freq"] = qubit_ef_freq_arr[i]
    # config["qubit_ef_gain"] = qubit_ef_gain_arr[j]
    # Run the experiment
    Instance_SingleShotProgram = SingleShotProgram_ef(path="dataTestSingleShotefProgram", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShot = SingleShotProgram_ef.acquire(Instance_SingleShotProgram)
    # fid[i,j] = Instance_SingleShotProgram.fid
    SingleShotProgram_ef.save_data(Instance_SingleShotProgram, data_SingleShot)
    SingleShotProgram_ef.save_config(Instance_SingleShotProgram)
#     SingleShotProgram_ef.display(Instance_SingleShotProgram, data_SingleShot, plotDisp=False, save_fig=True)
#%%
# # Plot the data
# X = qubit_ef_freq_arr
# Y = qubit_ef_gain_arr
# X_step = X[1] - X[0]
# Y_step = Y[1] - Y[0]
# fig, axs = plt.subplots(1,1, figsize=(8,8))
# axs_plot_0 = axs.imshow(fid, aspect='auto',
#                         extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
#                                 Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
#                         origin = 'lower',
#                         interpolation = 'none'
#                         )
# cbar0 = fig.colorbar(axs_plot_0, ax = axs, extend = 'both')
# cbar0.set_label('fidelity', rotation=90)
# plt.savefig(Instance_SingleShotProgram.iname, dpi = 600)
#%%

# # #######################################################################################################################
# # ####### code for perfoming the qubit RPM
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -2.8,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 5, # us
#     "read_pulse_gain": 10000, # [DAC units]
#     "read_pulse_freq": 6437.2,
#     ###### qubit
#     # g-e parameters
#     "qubit_ge_freq": 2033, # MHz
#     "qubit_ge_gain": 10000, # Gain for pi pulse in DAC units
#     "apply_ge": False,
#    # e-f parameters
#     "qubit_ef_freq": 1545,
#     "qubit_ef_gain_start": 0, #1167-10
#     "qubit_ef_gain_step": 250,
#     "RabiNumPoints": 41,  ### number of points
#     "qubit_pulse_style": "arb",
#     "qubit_length": 1, # us, changes experiment time but is necessary for "const" style
#     "sigma": 0.025,  ### units us, define a 20ns sigma
#     "relax_delay": 1500,  ### turned into us inside the run function
#     "g_reps": 2000, # number of averages of every experiment
#     "e_reps": 2000, # number of averages of every experiment
#     "reps": 1
# }
# config = BaseConfig | UpdateConfig
#
# yoko1.SetVoltage(config["yokoVoltage"])
# # #
# Instance_Qubit_ef_rabi = Qubit_ef_RPM(path="dataQubit_ef_RPM", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg, progress=True)
# data_Qubit_ef_rabi = Qubit_ef_RPM.acquire(Instance_Qubit_ef_rabi)
# print('scan finished time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
# Qubit_ef_RPM.save_data(Instance_Qubit_ef_rabi, data_Qubit_ef_rabi)
# Qubit_ef_RPM.save_config(Instance_Qubit_ef_rabi)
# Qubit_ef_RPM.display(Instance_Qubit_ef_rabi, data_Qubit_ef_rabi, plotDisp=True)

#######################################################################################################################

#######################################################################################################################


print('end time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

plt.show()

