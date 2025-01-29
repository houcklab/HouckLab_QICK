from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mStarkShift import StarkShift
from WorkingProjects.Inductive_Coupler.Client_modules.Running_Experiments_MUX.MUXInitialize import *

mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq

UpdateConfig = {
    "yokoVoltage": 0.015, #0.09473, #3.1
    ##### change gain instead option
    "trans_gain_start": 100,
    "trans_gain_stop": 1500,
    "trans_gain_num": 11,
    ###### cavity
    "read_pulse_style": "const",  # --Fixed
    "readout_length": 5,  # [us]
    "pulse_freqs":  [6664.931 - mixer_freq - BaseConfig["cavity_LO"] / 1e6],
    "units": "DAC",         # in dB or DAC
    # qubit spec parameters

    "qubit_pulse_style": "const",
    "qubit_freq": 1136,
    "qubit_gain": 700,

    # Constant Pulse Tone
    "qubit_length": 1,

    # Flat top or gaussian pulse tone
    "sigma": 0.5,#0.3,
    "flat_top_length": 30.0,

    # define spec slice experiment parameters
    "qubit_ch": 1,
    "qubit_freq_start": 1132, #2105,
    "qubit_freq_stop": 1150,#2120,
    "SpecNumPoints": 801,
    'spec_reps': 100000, #20000,

    # Experiment parameters
    "relax_delay": 10, #2000,
    "fridge_temp": 10,
    "two_pulses": False, # Do e-f pulse
    "use_switch": True,
    "mode_periodic": True,
    "ro_mode_periodic": False,

}
config = BaseConfig | UpdateConfig

import matplotlib
matplotlib.use('Qt5Agg')
Instance_StarkShift = StarkShift(path="dataTestStarkShift", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_StarkShift = StarkShift.acquire(Instance_StarkShift)
StarkShift.save_data(Instance_StarkShift, data_StarkShift)
StarkShift.save_config(Instance_StarkShift)
