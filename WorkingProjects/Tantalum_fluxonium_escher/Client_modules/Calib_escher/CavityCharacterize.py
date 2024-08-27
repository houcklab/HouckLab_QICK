import os

# path = os.getcwd() # Old method, does not work with cells. I have shifted the following code to initialize
path = r'C:\Users\escher\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_escher\Client_modules\PythonDrivers'
os.add_dll_directory(path)

from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Calib_escher.initialize import *
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mTransmission_SaraTest import Transmission
from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mTransVsGain import TransVsGain
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from matplotlib import pyplot as plt
import datetime
from tqdm import tqdm

# Function to help in smoothening the transmission
from scipy.ndimage import uniform_filter1d
def moving_average(arr, window_size):
    # Apply the uniform filter to calculate the moving average
    return uniform_filter1d(arr, size=window_size, mode='nearest')


# Define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2024_06_29_cooldown\\HouckCage_dev\\Cavity_characterize\\"

# Only run this if no proxy already exists
soc, soccfg = makeProxy()

SwitchConfig = {
    "trig_buffer_start": 0.035, # in us
    "trig_buffer_end": 0.024, # in us
    "trig_delay": 0.07, # in us
}
BaseConfig = BaseConfig  | SwitchConfig

yoko_vector = np.linspace(-0.2,0.2,41)

# Transmission Experiment Dictionary
UpdateConfig_transmission = {
    # Parameters
    "reps": 1000,  # Number of repetitions

    # cavity
    "read_pulse_style": "const",
    "read_length": 20,
    "read_pulse_gain": 3000,
    "read_pulse_freq": 6423.375,

    # Experiment Parameters
    "TransSpan": 20,  # [MHz] span will be center frequency +/- this parameter
    "TransNumPoints": 301,  # number of points in the transmission frequency
    "yoko_voltage" : 0,
    "relax_delay": 2,
}
config_trans = BaseConfig | UpdateConfig_transmission

# Transmission vs Gain Experiment Dictionary
UpdateConfig_transVsGain = {
    "yokoVoltage": -0.2,
    "trans_gain_start": 50,
    "trans_gain_stop": 30000,
    "trans_gain_num": 21,
    "trans_reps": 1000,
    "read_pulse_style": "const",
    "readout_length": 20,  # [us]
    "trans_freq_start": 6247 - 3,  # [MHz]
    "trans_freq_stop": 6247 + 3,  # [MHz]
    "trans_span": 3,
    "TransNumPoints": 101,
    "relax_delay": 2,
    "units": "dB",  # use "dB" or "DAC"
    "normalize": True,
}
config_transVsGain = BaseConfig | UpdateConfig_transVsGain

for i in tqdm(range(yoko_vector.size)):
    # Set yoko voltage
    yoko1.SetVoltage(yoko_vector[i])

    # Update dictionaries
    config_trans["yoko_voltage"] = yoko_vector[i]
    config_transVsGain["yoko_voltage"] = yoko_vector[i]

    # Run Cavity Transmission
    inst_trans = Transmission(path="Transmission", cfg=config_trans, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    data_trans = inst_trans.acquire()
    inst_trans.save_data(data_trans)
    inst_trans.display(data_trans, plotDisp=False)

    # Get the data
    amp = np.abs(data_trans["data"]["results"][0][0][0] + 1j * data_trans["data"]["results"][0][0][1])
    freq = data_trans["data"]["fpts"]
    amp_avg = moving_average(amp, 25)
    amp_diff = amp - amp_avg
    indx_freq = np.argmin(amp_diff)

    # Plot and save the data
    fig, axs = plt.subplots(1, 1, figsize=(10, 5))
    axs.plot(freq, amp_diff, label="Transmission - Background")
    axs.plot(freq, amp_avg, label="Background")
    axs.set_xlabel("Frequency [MHz]")
    axs.set_ylabel("Amplitude")
    axs.legend()
    print(inst_trans.iname[:-4] + "_bkg_sub" + ".png")
    plt.savefig(inst_trans.iname[:-4] + "_bkg_sub" + ".png")
    plt.close(fig= fig)

    # Get the cavity frequency
    cavity_freq = freq[indx_freq]
    print("Cavity Freq: ", cavity_freq)

    # Update dictionaries
    config_trans["read_pulse_freq"] = cavity_freq
    config_transVsGain["trans_freq_start"] = cavity_freq - config_transVsGain["trans_span"]
    config_transVsGain["trans_freq_stop"] = cavity_freq + config_transVsGain["trans_span"]

    # Run Transmission vs Gain
    inst_tvg = TransVsGain(path="TransVsGain", outerFolder=outerFolder, cfg=config_transVsGain, soc=soc, soccfg=soccfg)
    data_tvg = inst_tvg.acquire()
    inst_tvg.save_data(data_tvg)
    inst_tvg.save_config()
    plt.close()