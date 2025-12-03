#%%
import os
#path = r'/WorkingProjects/Tantalum_fluxonium_escher/Client_modules/PythonDrivers'
path = r'C:\Users\escher\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_escher\Client_modules\PythonDrivers'
os.add_dll_directory(path)
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib_escher.initialize import *
from matplotlib import pyplot as plt
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mSpecVsFlux import SpecVsFlux
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.PythonDrivers.mlbf_driver import *
# define the saving path
outerFolder = r"Z:\TantalumFluxonium\Data\2025_07_25_cooldown\\HouckCage_dev\\" # end in '\\'



# Only run this if no proxy already exists
soc, soccfg = makeProxy()
# plt.ion()
plt.ioff()
SwitchConfig = {
    "trig_buffer_start": 0.05, #0.035, # in us
    "trig_buffer_end": 0.04, #0.024, # in us
    "trig_delay": 0.07, # in us
}

BaseConfig = BaseConfig | SwitchConfig

UpdateConfig = {
    # set yoko
    "yokoVoltageStart": -1.7,  # 1.06, #-1,
    "yokoVoltageStop": -1.45,  # 1,
    "yokoVoltageNumPoints": 21,  # 5001,

    # Readout parameters
    "trans_reps": 500,
    "read_pulse_style": "const",
    "read_length": 13,
    "read_pulse_gain": 4500,
    # "read_pulse_freq": 6723.5,
    "trans_freq_start": 7390.5,
    "trans_freq_stop": 7393.5,
    'TransNumPoints': 201,

    # qubit spec parameters
    "spec_reps":2000,# 10000,  # 10000,#22000,
    "qubit_pulse_style": "flat_top",  # "flat_top", "const", "arb"
    "qubit_gain": 32000,#25000,  # 3000,
    "qubit_length": 3,
    "flat_top_length": 1,
    "qubit_freq_start": 100,
    "qubit_freq_stop": 1100,
    "SpecNumPoints": 301 ,#101,  # 101,#101
    "sigma": 0.5,
    "relax_delay": 5,  # 150,
    "use_switch": False,

    # Changing qubit channel ( not the standard way !!! )
    "qubit_ch": 1,
    "qubit_nqz": 1,

    # Do we subtract the average of each voltage slice from the spectroscopy data?
    "subtract_avg": False,
    "qubit_mode_periodic": False,  # Is the const qubit tone mode periodic or not
    "ro_mode_periodic": False,

    # Do we draw the point picked out for spectroscopy?
    "draw_read_freq": False,
}

config = BaseConfig | UpdateConfig
#
#mlbf_filter = MLBFDriver("192.168.1.11")
#Updating the mlbf filter
#filter_freq = (config["trans_freq_start"] + config["trans_freq_stop"])/2
#mlbf_filter.set_frequency(filter_freq)
#print("Set filter frequency to %.3f MHz. It is now %.3f" % (filter_freq, mlbf_filter.get_frequency()))

 #%%
import matplotlib
matplotlib.use('Qt5Agg')
Instance_SpecVsFlux = SpecVsFlux(path="dataTestSpecVsFlux", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_SpecVsFlux = SpecVsFlux.acquire(Instance_SpecVsFlux, subtract_avg=config["subtract_avg"])
SpecVsFlux.save_data(Instance_SpecVsFlux, data_SpecVsFlux)
SpecVsFlux.save_config(Instance_SpecVsFlux)
plt.show()

#%%
# TITLE : Plot just the transmission vs flux

yoko_vec = data_SpecVsFlux['data']['voltVec']
trans_fpts = data_SpecVsFlux['data']['trans_fpts']
trans_mas = np.abs( data_SpecVsFlux['data']['trans_Imat'] + 1j*data_SpecVsFlux['data']['trans_Qmat'])

plt.figure(figsize=(18, 8))
plt.imshow(np.transpose(trans_mas), aspect='auto', origin='lower',
           extent=[yoko_vec[0], yoko_vec[-1], trans_fpts[0], trans_fpts[-1]],
           interpolation='nearest', cmap='viridis')
plt.colorbar(label='Transmission Magnitude')
plt.xlabel('Voltage Vector')
plt.ylabel('Transmission Frequency Points')
plt.title('Transmission Magnitude vs Voltage and Frequency')
plt.tight_layout()
plt.show()


#%%
#
# #%%
# #TITLE: For multiple scans
#
# # define the saving path
# outerFolder = r"Z:\TantalumFluxonium\Data\2024_10_14_cooldown\HouckCage_dev\\"
#
# mlbf_filter = MLBFDriver("192.168.1.100")
# # Dictionary for multiple qubits
#
# qubit_dicts = {
#     "Q2_6p5": {
#     # set yoko
#     "yokoVoltageStart": -2.2,  # 1.06, #-1,
#     "yokoVoltageStop": 2.8,  # 1,
#     "yokoVoltageNumPoints": 501,  # 5001,
#
#     # Readout parameters
#     "trans_reps": 1000,
#     "read_pulse_style": "const",
#     "read_length": 30,
#     "read_pulse_gain": 5000,
#     "trans_freq_start": 6422.0,
#     "trans_freq_stop": 6424.0,
#     "TransNumPoints": 301,
#
#     # qubit spec parameters
#     "spec_reps": 2,  # 5000,
#     "qubit_pulse_style": "flat_top",  # "flat_top",
#     "qubit_gain": 0,  # 2500,
#     "qubit_length": .01,
#     "flat_top_length": .01,
#     "qubit_freq_start": 1200,
#     "qubit_freq_stop": 1500,
#     "SpecNumPoints": 2,  # 301,
#     "sigma": 0.5,
#     "relax_delay": 50,  # 150,
#     "use_switch": False,
#
#     # Changing qubit channel ( not the standard way !!! )
#     "qubit_ch": 1,
#     "qubit_nqz": 1,
#
#     # Do we subtract the average of each voltage slice from the spectroscopy data?
#     "subtract_avg": True,
#     "ro_mode_periodic": False,
#     "qubit_mode_periodic": False,
#     },
#
#     "Q3_6p75": {
#         "yokoVoltageStart": -.1,  # 1.06, #-1,
#         "yokoVoltageStop": 0.18,  # 1,
#         "yokoVoltageNumPoints": 501,  # 5001,
#
#         # Readout parameters
#         "trans_reps": 1000,
#         "read_pulse_style": "const",
#         "read_length": 30,
#         "read_pulse_gain": 5000,
#         "trans_freq_start": 6664.0,
#         "trans_freq_stop": 6665.5,
#         "TransNumPoints": 301,
#     }
#
# }
#
# # Loop over each qubit
# qubits = qubit_dicts.keys()
# for qubit in qubits:
#     print("Running transmission vs flux for ", qubit)
#     # Updating all the keys in config that are in qubit
#     config_keys = qubit_dicts[qubit].keys()
#     for config_key in config_keys:
#         config[config_key] = qubit_dicts[qubit][config_key]
#
#     # Updating the mlbf filter
#     filter_freq = (config["trans_freq_start"] + config["trans_freq_stop"])/2
#     mlbf_filter.set_frequency(filter_freq)
#
#     # Running transmission vs flux
#     Instance_SpecVsFlux = SpecVsFlux(path="dataTestSpecVsFlux", outerFolder=outerFolder, cfg=config, soc=soc,
#                                      soccfg=soccfg)
#     data_SpecVsFlux = SpecVsFlux.acquire(Instance_SpecVsFlux, subtract_avg=config["subtract_avg"])
#     SpecVsFlux.save_data(Instance_SpecVsFlux, data_SpecVsFlux)
#     SpecVsFlux.save_config(Instance_SpecVsFlux)
#
#     # Close the plot
#     plt.close('all')
#
#%%
from tqdm import tqdm
import matplotlib
matplotlib.use('Qt5Agg')

# Sweep one more parameters along with flux
read_pulse_gain_vec = np.array([1, 10, 30, 100, 300, 1000, 3000])
trans_reps_vec = np.array([10000, 3000, 1000, 500, 400, 400, 300])

for i in tqdm(range(read_pulse_gain_vec.size)):
    config["read_pulse_gain"] = read_pulse_gain_vec[i]
    config['trans_reps'] = trans_reps_vec[i]
    prefix = "_gain_"+str(read_pulse_gain_vec[i])+"_reps_"+str(trans_reps_vec[i])

    # Running transmission vs flux
    Instance_SpecVsFlux = SpecVsFlux(path="TransmissionVsFluxVsPower", outerFolder=outerFolder, cfg=config, soc=soc,
                                     soccfg=soccfg, prefix = prefix)
    data_SpecVsFlux = SpecVsFlux.acquire(Instance_SpecVsFlux, subtract_avg=config["subtract_avg"])
    SpecVsFlux.save_data(Instance_SpecVsFlux, data_SpecVsFlux)
    SpecVsFlux.save_config(Instance_SpecVsFlux)
    plt.close()

#%%