#%%
import os
# path = os.getcwd() # Old method, does not work with cells
path = r'C:\Users\pjatakia\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_marvin\Client_modules\PythonDrivers'
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
from matplotlib import pyplot as plt
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecVsFlux import SpecVsFlux
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.PythonDrivers.agilent33250a import Agilent33250A

# define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2025_07_25_cooldown\\QCage_dev\\"

# Only run this if no proxy already exists
# soc, soccfg = makeProxy()
plt.ioff()
# yoko2.SetVoltage(0)

# Defining changes to the config
UpdateConfig = {
    # define the yoko voltage
    "yokoVoltageStart": -0.125,
    "yokoVoltageStop": -0.09,
    "yokoVoltageNumPoints": 51,
    # "yoko2": yoko2.GetVoltage(),

    # cavity and readout
    "trans_reps": 1000,
    "read_pulse_style": "const",
    "read_length": 20,  # us
    "read_pulse_gain": 2000,  # [DAC units]
    "trans_freq_start":6669,
    "trans_freq_stop": 6673,
    "TransNumPoints": 401,

    # qubit spec parameters
    "spec_reps": 2000,
    "qubit_pulse_style": "const",
    "qubit_gain": 2000,
    "qubit_length": 5,
    "flat_top_length" : 10,
    "qubit_freq_start": 200,
    "qubit_freq_stop": 1000,
    "SpecNumPoints": 801,
    "sigma": 1,
    "relax_delay": 20,
    'use_switch': False,
    'initialize_pulse': False,
    'fridge_temp': 420,
    "mode_periodic": False,
    'ro_periodic': False,
    "measurement_style": "std", # std : standard, bkg : background subtracted, ps : post-selected
    "magnet_relax": 1, # [s] wait time after each magnet change

    "trans_method": "std", # Seitch between using pphase
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
outerFolder = "Z:\\TantalumFluxonium\\Data\\2025_07_25_cooldown\\QCage_dev\\TransVsFluxZoomed2\\"

UpdateConfig = {
    # define the yoko voltage
    "yokoVoltageStart": -0.16,
    "yokoVoltageStop": -0.11,
    "yokoVoltageNumPoints": 501,
    # "yoko2": yoko2.GetVoltage(),

    # cavity and readout
    "trans_reps": 2000,
    "read_pulse_style": "const",
    "read_length": 20,  # us
    "read_pulse_gain": 500,  # [DAC units]
    "trans_freq_start": 6668,
    "trans_freq_stop": 6673.5,
    "TransNumPoints": 201,

    # qubit spec parameters
    "spec_reps": 2,
    "qubit_pulse_style": "const",
    "qubit_gain": 0,
    "qubit_length": 0.05,
    "flat_top_length" : 10,
    "qubit_freq_start": 2100,
    "qubit_freq_stop": 2300,
    "SpecNumPoints": 3,
    "sigma": 1,
    "relax_delay": 20,
    'use_switch': False,
    'initialize_pulse': False,
    'fridge_temp': 7,
    "mode_periodic": False,
    'ro_periodic': False,
    "measurement_style": "std", # std : standard, bkg : background subtracted, ps : post-selected
    "magnet_relax": 1, # [s] wait time after each magnet change

    "trans_method": "std", # Seitch between using pphase
    "meas_config": 'Hanger',
    "draw_read_freq": False,
    "awg_volts": 0,
}
config = BaseConfig | UpdateConfig

# Check if the start is less than stop
if config["yokoVoltageStart"] > config['yokoVoltageStop']:
    raise Exception("The start is greater than the stop. ALERT !!!")

# Dictionary for multiple variations
sweeps_dicts = {
    # "600drive0awg":
    #     {
    #         "read_pulse_gain": 600,
    #         "awg_volts": 0,
    #
    #     },
    # "600drive0p2awg":
    #     {
    #         "read_pulse_gain": 600,
    #         "awg_volts": 0.2,
    #     },
    # "600drive0p4awg":
    #     {
    #         "read_pulse_gain": 600,
    #         "awg_volts": 0.4,
    #     },
    # "600drive0p6awg":
    #     {
    #         "read_pulse_gain": 600,
    #         "awg_volts": 0.6,
    #     },
    # "600drive0p8awg":
    #     {
    #         "read_pulse_gain": 600,
    #         "awg_volts": 0.8,
    #     },
    "950drive0awg":
        {
            "read_pulse_gain": 950,
            "awg_volts": 0,
            "trans_reps": 600,
        },
    "1700drive0awg":
        {
            "read_pulse_gain": 1700,
            "awg_volts": 0,
            "trans_reps": 600,
        },
    "2450drive0awg":
        {
            "read_pulse_gain": 2450,
            "awg_volts": 0,
            "trans_reps": 400,
        },
    "3500drive0awg":
        {
            "read_pulse_gain": 3500,
            "awg_volts": 0,
            "trans_reps": 400,
        },
    "7000drive0awg":
        {
            "read_pulse_gain": 7000,
            "awg_volts": 0,
            "trans_reps": 400,
        },
    # "100drive0awg":
    #     {
    #         "read_pulse_gain": 100,
    #         "awg_volts": 0,
    #         "trans_reps": 5000,
    #     },
}

#%%

if 'awg_volts' in config:
    awg = Agilent33250A(resource='GPIB1::13::INSTR')
    awg.set_noise()  # Set to white noise
    awg.output_off()  # Turn it off for now

# Loop around each qubit
sweeps = sweeps_dicts.keys()
for sweep in sweeps:
    print("Running Transmission vs Flux for ", sweep)

    # Updating all the keys in config that are in qubit
    config_keys = sweeps_dicts[sweep].keys()
    for config_key in config_keys:
        config[config_key] = sweeps_dicts[sweep][config_key]

    # Updating mlbf filter
    filter_freq = (config["trans_freq_start"] + config['trans_freq_stop']) / 2
    mlbf_filter.set_frequency(filter_freq)

    # Updating the awg agilent
    if 'awg_volts' in config:
        if config['awg_volts'] == 0 :
            print("Turning off awg")
            awg.set_voltage(0)
            awg.output_off()
        else:
            awg.output_on()
            awg.set_voltage(config['awg_volts'])

    # Running transmission vs Flux

    my_trans_vs_flux = SpecVsFlux(path=sweep, outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    while True:
        try:
            data_trans_vs_flux = my_trans_vs_flux.acquire(individ_fit=False)
            break  # exit the loop if no exception is raised
        except Exception as e:
            print(f"Acquisition failed: {e}. Retrying...")
            # optionally add a short delay to avoid hammering the system
            import time

            time.sleep(1)
    my_trans_vs_flux.save_data(data_trans_vs_flux)
    my_trans_vs_flux.save_config()

    # Closing the plot
    plt.close('all')

    # Plotting just the transmission
    yoko_vec = data_trans_vs_flux['data']['voltVec']
    trans_fpts = data_trans_vs_flux['data']['trans_fpts']
    trans_mas = np.abs(data_trans_vs_flux['data']['trans_Imat'] + 1j * data_trans_vs_flux['data']['trans_Qmat'])

    plt.figure(figsize=(18, 8))
    plt.imshow(np.transpose(trans_mas), aspect='auto', origin='lower',
               extent=[yoko_vec[0], yoko_vec[-1], trans_fpts[0], trans_fpts[-1]],
               interpolation='nearest', cmap='viridis')
    plt.colorbar(label='Transmission Magnitude')
    plt.xlabel('Voltage Vector')
    plt.ylabel('Transmission Frequency Points')
    plt.title('Transmission Magnitude vs Voltage and Frequency')
    plt.tight_layout()
    plt.savefig(my_trans_vs_flux.path_wDate + "justTransmission.png", dpi = 600)
    plt.savefig(my_trans_vs_flux.path_wDate + "justTransmission.pdf")
    plt.close('all')
