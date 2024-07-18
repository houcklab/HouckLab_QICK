import os

# path = os.getcwd() # Old method, does not work with cells. I have shifted the following code to initialize
path = r'C:\Users\pjatakia\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_marvin\Client_modules\PythonDrivers'
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')

from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransmission_SaraTest import Transmission
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransVsGain import TransVsGain
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from matplotlib import pyplot as plt
import datetime
from tqdm import tqdm

# Define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2024_06_29_cooldown\\QCage_dev\\Cavity_characterize\\"

# Only run this if no proxy already exists
soc, soccfg = makeProxy()

SwitchConfig = {
    "trig_buffer_start": 0.035, # in us
    "trig_buffer_end": 0.024, # in us
    "trig_delay": 0.07, # in us
}
BaseConfig = BaseConfig  | SwitchConfig

yoko_vector = np.linspace(2.5,4.0,16)

# Transmission Experiment Dictionary
UpdateConfig_transmission = {
    # Parameters
    "reps": 1000,  # Number of repetitions

    # cavity
    "read_pulse_style": "const",
    "read_length": 20,
    "read_pulse_gain": 500,
    "read_pulse_freq": 6246.36,

    # Experiment Parameters
    "TransSpan": 20,  # [MHz] span will be center frequency +/- this parameter
    "TransNumPoints": 501,  # number of points in the transmission frequency
    "yoko_voltage" : 0,
}
config_trans = BaseConfig | UpdateConfig_transmission

# Transmission vs Gain Experiment Dictionary
UpdateConfig_transVsGain = {
    "yokoVoltage": 2.5,
    "trans_gain_start": 50,
    "trans_gain_stop": 30000,
    "trans_gain_num": 51,
    "trans_reps": 500,
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

    # Get the cavity frequency
    cavity_freq = inst_trans.peakFreq
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