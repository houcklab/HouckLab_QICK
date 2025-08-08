#%%
import os
# path = os.getcwd() # Old method, does not work with cells
path = r'C:\Users\pjatakia\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_marvin\Client_modules\PythonDrivers'
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
from matplotlib import pyplot as plt
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecVsFlux import SpecVsFlux


# define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2025_07_25_cooldown\\QCage_dev\\"

# Only run this if no proxy already exists
# soc, soccfg = makeProxy()
plt.ioff()
# yoko2.SetVoltage(0)

# Defining changes to the config
UpdateConfig = {
    # define the yoko voltage
    "yokoVoltageStart": -0.095,
    "yokoVoltageStop": -0.088,
    "yokoVoltageNumPoints": 21,
    # "yoko2": yoko2.GetVoltage(),

    # cavity and readout
    "trans_reps": 200,
    "read_pulse_style": "const",
    "read_length": 20,  # us
    "read_pulse_gain": 1200,  # [DAC units]
    "trans_freq_start": 6671,
    "trans_freq_stop": 6673.5,
    "TransNumPoints": 101,

    # qubit spec parameters
    "spec_reps": 2000,
    "qubit_pulse_style": "const",
    "qubit_gain": 10000,
    "qubit_length": 2,
    "flat_top_length" : 10,
    "qubit_freq_start": 100,
    "qubit_freq_stop": 400,
    "SpecNumPoints": 101,
    "sigma": 1,
    "relax_delay":10,
    'use_switch': False,
    'initialize_pulse': False,
    'fridge_temp': 420,
    "mode_periodic": False,
    'ro_periodic': False,
    "measurement_style": "std", # std : standard, bkg : background subtracted, ps : post-selected
    "magnet_relax": 0, # [s] wait time after each magnet change

    "trans_method": "enhanced", # Seitch between using pphase
    "meas_config": 'Hanger',
    "draw_read_freq": False,
}
config = BaseConfig | UpdateConfig

# Check if the start is less than stop
if config["yokoVoltageStart"] > config['yokoVoltageStop']:
    print("The start is greater than the stop. ALERT !!!")
#%%
# Run the experiment
soc.reset_gens()
filter_freq = (config["trans_freq_start"] + config['trans_freq_stop'])/2

mlbf_filter.set_frequency(filter_freq)
# sometimes this doesn't work on the first try
mlbf_filter.set_frequency(filter_freq)

Instance_SpecVsFlux = SpecVsFlux(path="dataTestSpecVsFlux", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_SpecVsFlux = SpecVsFlux.acquire(Instance_SpecVsFlux, individ_fit = False)
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
# TITLE : For multiple scans

# define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2024_10_14_cooldown\\QCage_dev\\TransVsFlux\\"

# Dictionary for multiple qubit
qubit_dicts = {
    # "Q1_6p25": {
    #     "yokoVoltageStart": -6,
    #     "yokoVoltageStop": 14,
    #     "trans_freq_start": 6230,
    #     "trans_freq_stop": 6270,
    #     "yokoVoltageNumPoints": 1201,
    # },
    # "Q2_6p5": {
    #     "yokoVoltageStart": 0.0,
    #     "yokoVoltageStop": 2,
    #     "trans_freq_start": 6431,
    #     "trans_freq_stop": 6433,
    #     "yokoVoltageNumPoints": 51,
    # },
    # "Q3_6p75": {
    #     "yokoVoltageStart": -0.3,
    #     "yokoVoltageStop": 0.5,
    #     "trans_freq_start": 6670.5,
    #     "trans_freq_stop": 6673,
    #     "yokoVoltageNumPoints": 1201,
    # }
}

# Loop around each qubit
qubits = qubit_dicts.keys()
for qubit in qubits:
    print("Running Transmission vs Flux for ", qubit)

    # Updating all the keys in config that are in qubit
    config_keys = qubit_dicts[qubit].keys()
    for config_key in config_keys:
        config[config_key] = qubit_dicts[qubit][config_key]

    # Updating mlbf filter
    filter_freq = (config["trans_freq_start"] + config['trans_freq_stop']) / 2
    mlbf_filter.set_frequency(filter_freq)

    # Running transmission vs Flux
    my_trans_vs_flux = SpecVsFlux(path=qubit, outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_trans_vs_flux = my_trans_vs_flux.acquire(individ_fit=False)
    my_trans_vs_flux.save_data(data_trans_vs_flux)
    my_trans_vs_flux.save_config()

    # Closing the plot
    plt.close('all')
