#%%
import os
import time
from matplotlib import pyplot as plt
import Pyro4.util
import numpy as np

path = r'C:\Users\pjatakia\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_marvin\Client_modules\PythonDrivers'
os.add_dll_directory(path)

from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFTransmission import FFTransmission
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFSpecSliceReverse import FFSpecSliceReverse_Experiment
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFSpecVsFlux_Reversed import SpecVsFluxReversed

# Define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2025_07_25_cooldown\\QCage_dev\\" # end in \\

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
soc.reset_gens()
# print(soccfg)


# plt.ioff()

# Defining the switch configuration
SwitchConfig = {
    "trig_buffer_start": 0.05, #0.035, # in us
    "trig_buffer_end": 0.04, #0.024, # in us
    "trig_delay": 0.07, # in us
}

BaseConfig = BaseConfig | SwitchConfig

#%%
# TITLE : FF Transmission
UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",  # --Fixed
    "read_length": 30,  # [us]
    "read_pulse_gain": 3000,  # 5600,  # [DAC units]
    "read_pulse_freq": 6671.0,  # [MHz]
    "TransSpan": 2,
    "TransNumPoints": 101,

    # Fast flux pulse parameters
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": 2000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.05,  # [us] Half-length of ramp to use when sweeping gain

    # Ramp sweep parameters
    "yokoVoltage": -0.125,  # [V] Yoko voltage for magnet offset of flux
    "relax_delay": 10,  # [us] Relax delay after second readout

    # General parameters
    "reps": 500,
    "cen_num": 2,
    "initialize_pulse": True,
    "negative_pulse": True,
    "pre_meas_delay": 5,
}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
soc.reset_gens()

#%%
inst_ff_trans = FFTransmission(path="FF_Transmission", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder)
try:
    data_ff_trans = inst_ff_trans.acquire()
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
inst_ff_trans.display(data = data_ff_trans,plotDisp = True)
inst_ff_trans.save_data(data_ff_trans)
inst_ff_trans.save_config()
print(inst_ff_trans.peakFreq)


#%%
# TITLE: Fast Flux DC voltage Spec Slice

UpdateConfig = {
    # Readout section
    "read_pulse_style": "const",     # --Fixed
    "read_length": 30,                # [us]
    "read_pulse_gain": 13000,         # [DAC units]
    "read_pulse_freq": 6671.235,#6670.85,      # [MHz]
    "ro_mode_periodic": False,  # currently unused

    # Qubit spec parameters
    "qubit_freq_start": 1000,        # [MHz]
    "qubit_freq_stop": 1600,         # [MHz]
    "qubit_pulse_style": "const", # one of ["const", "flat_top", "arb"]
    "sigma": 0.50,                  # [us], used with "arb" and "flat_top"
    "qubit_length": 2,               # [us], used with "const"
    "flat_top_length": 10,        # [us], used with "flat_top"
    "qubit_gain": 14000,             # [DAC units]
    "qubit_ch": 1,                   # RFSOC output channel of qubit drive
    "qubit_nqz": 1,                  # Nyquist zone to use for qubit drive
    "qubit_mode_periodic": False,    # Currently unused, applies to "const" drive
    "qubit_spec_delay": 0,          # [us] Delay before qubit pulse

    # Fast flux pulse parameters
    "ff_gain": 7450,                  # [DAC units] Gain for fast flux pulse
    "ff_length": 35,                  # [us] Total length of positive fast flux pulse
    "pre_ff_delay": 2,               # [us] Delay before the fast flux pulse
    "ff_pulse_style": "ramp",
    "ff_ramp_length" : 0.2,
    "ff_ch": 6,                      # RFSOC output channel of fast flux drive
    "ff_nqz": 1,                     # Nyquist zone to use for fast flux drive
    "pre_meas_delay": 3,

    "yokoVoltage": -0.13,           # [V] Yoko voltage for DC component of fast flux
    "relax_delay": 20,               # [us]
    "qubit_freq_expts": 101,         # number of points
    "reps": 1000,
    "use_switch": False,
    'negative_pulse': False,
}

config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
soc.reset_gens()
Instance_FFSpecSlice = FFSpecSliceReverse_Experiment(path="FFSpecSlice", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder, short_directory_names = True)

# Estimate Time
time = Instance_FFSpecSlice.estimate_runtime()
print("Time for ff spec experiment is about ", time, " s")

data_FFSpecSlice = FFSpecSliceReverse_Experiment.acquire(Instance_FFSpecSlice, progress = True)
FFSpecSliceReverse_Experiment.display(Instance_FFSpecSlice, data_FFSpecSlice, plot_disp=True)
FFSpecSliceReverse_Experiment.save_data(Instance_FFSpecSlice, data_FFSpecSlice)
FFSpecSliceReverse_Experiment.save_config(Instance_FFSpecSlice)
# print(Instance_specSlice.qubitFreq)
plt.show()

#%%
#TITLE Spec vs FF

UpdateConfig = {
    # define the yoko voltage
    "FFStart": 0,
    "FFStop": 10000,
    "FFNumPoints": 11,
    "yokoVoltage": -0.125,  # [V] Yoko voltage for DC component of fast flux

    # cavity and readout
    "trans_reps": 500,
    "read_pulse_style": "const",
    "read_length": 30,  # us
    "read_pulse_gain": 2000,  # [DAC units]
    "trans_freq_start": 6668,
    "trans_freq_stop": 6673,
    "TransNumPoints": 201,
    "ro_mode_periodic": False,  # currently unused

    # qubit spec parameters
    "spec_reps": 1000,
    "qubit_pulse_style": "const",
    "qubit_gain": 15000,
    "qubit_length": 2,
    "flat_top_length" : 10,
    "qubit_freq_start": 400,
    "qubit_freq_stop": 1500,
    "SpecNumPoints": 101,
    "sigma": 1,
    "relax_delay": 20,
    "draw_read_freq": True,
    "qubit_spec_delay": 2,  # [us] Delay before qubit pulse

    # Fast Flux Params
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": 2000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.05,  # [us] Half-length of ramp to use when sweeping gain
    "ff_gain": 2000,  # [DAC units] Gain for fast flux pulse
    "ff_length": 40,  # [us] Total length of positive fast flux pulse
    "pre_ff_delay": 0,  # [us] Delay before the fast flux pulse
    "ff_pulse_style": "ramp",
    "pre_meas_delay": 4.5,

}

config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])
Instance_SpecVsFlux = SpecVsFluxReversed(path="SpecVsFF", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
data_SpecVsFlux = SpecVsFluxReversed.acquire(Instance_SpecVsFlux, individ_fit = False)
SpecVsFluxReversed.save_data(Instance_SpecVsFlux, data_SpecVsFlux)
SpecVsFluxReversed.save_config(Instance_SpecVsFlux)
plt.show()
#%%
# TITLE : Search Spec vs FF
UpdateConfig = {
    # define the yoko voltage
    "FFStart": 0,
    "FFStop": 10000,
    "FFNumPoints": 11,
    "yokoVoltage": -0.13,  # [V] Yoko voltage for DC component of fast flux

    # cavity and readout
    "trans_reps": 500,
    "read_pulse_style": "const",
    "read_length": 30,  # us
    "read_pulse_gain": 2000,  # [DAC units]
    "trans_freq_start": 6668,
    "trans_freq_stop": 6673,
    "TransNumPoints": 201,
    "ro_mode_periodic": False,  # currently unused

    # qubit spec parameters
    "spec_reps": 1500,
    "qubit_pulse_style": "const",
    "qubit_gain": 15000,
    "qubit_length": 2,
    "flat_top_length": 10,
    "qubit_freq_start": 800,
    "qubit_freq_stop": 1200,
    "SpecNumPoints": 101,
    "sigma": 1,
    "relax_delay": 20,
    "draw_read_freq": True,
    "qubit_spec_delay": 2,  # [us] Delay before qubit pulse

    # Fast Flux Params
    "ff_ramp_style": "linear",  # one of ["linear"]
    "ff_ramp_start": 0,  # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
    "ff_ramp_stop": 2000,  # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
    "ff_ch": 6,  # RFSOC output channel of fast flux drive
    "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
    "ff_ramp_length": 0.05,  # [us] Half-length of ramp to use when sweeping gain
    "ff_gain": 2000,  # [DAC units] Gain for fast flux pulse
    "ff_length": 40,  # [us] Total length of positive fast flux pulse
    "pre_ff_delay": 0,  # [us] Delay before the fast flux pulse
    "ff_pulse_style": "ramp",
    "pre_meas_delay": 4.5,

    # Calibration Parameters
    "m_ff" : -0.0531,
    "c_ff" : 1188.2,
    "m_yoko" : -40000,
    "c_yoko" : -3804.39,
}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
inst_search_spec = SpecVsFluxReversed(path="Search_Spec", cfg=config,soc=soc,soccfg=soccfg, outerFolder=outerFolder)
try :
    data_search_spec = inst_search_spec.search_frequency(target_freq = 1000, threshold=10, plotDisp=True, search_span=2000)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))
inst_search_spec.save_data(data_search_spec)
inst_search_spec.save_config()
plt.show()
#%%