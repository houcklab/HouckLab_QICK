#%%
import os

import numpy as np

# path = os.getcwd() # Old method, does not work with cells. I have shifted the following code to initialize
path = r'C:\Users\pjatakia\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_marvin\Client_modules\PythonDrivers'
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecSlice_bkg_subtracted import \
    SpecSlice_bkg_sub

from matplotlib import pyplot as plt
import datetime
from tqdm import tqdm


# Define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2024_07_29_cooldown\\QCage_dev\\"
foldername = "SpecVsCavity"

# Print the start time
print('starting time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

# Only run this if no proxy already exists
# soc, soccfg = makeProxy()

SwitchConfig = {
    "trig_buffer_start": 0.035,  # in us
    "trig_buffer_end": 0.024,  # in us
    "trig_delay": 0.07,  # in us
}
BaseConfig = BaseConfig | SwitchConfig

UpdateConfig_transmission = {
    # Parameters
    "reps": 2000,  # Number of repetitions

    # cavity
    "read_pulse_style": "const",
    "read_length": 70,
    "read_pulse_gain": 1500,
    "read_pulse_freq": 6671.137,  # 6253.8,

    # Experiment Parameters
    "TransSpan": 0.5,  # [MHz] span will be center frequency +/- this parameter
    "TransNumPoints": 301,  # number of points in the transmission frequency
}

UpdateConfig_qubit = {
    "qubit_pulse_style": "flat_top",  # Constant pulse
    "qubit_gain": 2000,  # [DAC Units]
    'sigma': 1,
    'flat_top_length': 10,
    "qubit_length": 10,  # [us]

    # Define spec slice experiment parameters
    "qubit_freq_start": 200,
    "qubit_freq_stop": 300,
    "SpecNumPoints": 51,  # Number of points
    'spec_reps': 2000,  # Number of repetition

    # Define the yoko voltage
    "yokoVoltage": -0.035,
    "relax_delay": 10,  # [us] Delay post one experiment
    'use_switch': True,
}

UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit

config = BaseConfig | UpdateConfig

# Set the yoko voltage
yoko1.SetVoltage(config["yokoVoltage"])

#%%
# Define the cavity frequency range
vary_freq = False
vary_read_gain = False
vary_relax_delay = True

if vary_freq:
    read_freq_vec = np.linspace(6670.5,6673, 81)
    x = read_freq_vec
    key = "read_pulse_freq"
elif vary_read_gain:
    read_gain_vec = np.linspace(100,3000,31, dtype=int)
    x = read_gain_vec
    key = "read_pulse_gain"
elif vary_relax_delay:
    read_delay_vec = np.linspace(500,8000, 17)
    x = read_delay_vec
    key = 'relax_delay'
else:
    print("You need to vary something")

#%%
# Define arrays to save data
amplitude = np.full((x.size, config["SpecNumPoints"]), np.nan)

# Create figure
fig, axs = plt.subplots()

for i in tqdm(range(x.size)):
    config[key] = x[i]
    inst_spec = SpecSlice_bkg_sub(path=foldername, cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    data_specSlice = inst_spec.acquire()
    inst_spec.save_data(data_specSlice)
    # inst_spec.display(data_specSlice, plotDisp=False)

    # Get the data
    if i == 0:
        qubit_freq = data_specSlice["data"]["x_pts"]
        # Create meshgrid for pcolormesh
        x_mesh, qubit_freq_mesh = np.meshgrid(x, qubit_freq)

    amplitude[i,:] = data_specSlice["data"]["amp"]

    # print(amplitude)
    # print(qubit_freq)

    # Plot it
    if i == 0:
        # Use pcolormesh instead of imshow
        im = axs.pcolormesh(x_mesh, qubit_freq_mesh, amplitude.T, shading='auto', cmap='viridis',
                             vmin=np.nanmin(amplitude), vmax=np.nanmax(amplitude))
        cbar = fig.colorbar(im, ax=axs, extend='both')
    else:
        # Update the data in the pcolormesh
        im.set_array(amplitude.T.flatten())
        im.set_clim(vmin=np.nanmin(amplitude), vmax=np.nanmax(amplitude))
        cbar.remove()
        cbar = fig.colorbar(im, ax=axs, extend='both')

    axs.set_xlabel(key)
    axs.set_ylabel("Frequency")
    plt.tight_layout()
    plt.pause(0.1)
    plt.show()
    plt.pause(0.1)

#%%
datetimenow = datetime.datetime.now()
datetimestring = datetimenow.strftime("%Y_%m_%d_%H_%M_%S")
plt.savefig(outerFolder+foldername+"\\scan_" +datetimestring+"_"+key+".png", dpi = 800)

# Save data
data = {
    key:x,
    'qubit_freq':qubit_freq,
}
import h5py
file_loc = outerFolder+foldername+"\\scan_" +datetimestring+"_"+key+".h5"
with h5py.File(file_loc, 'w') as h5file:
    for key, value in data.items():
        h5file.create_dataset(key, data=value)
#%%