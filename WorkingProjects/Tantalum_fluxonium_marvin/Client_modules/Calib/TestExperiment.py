# %%
import os

# path = os.getcwd() # Old method, does not work with cells. I have shifted the following code to initialize
path = r'C:\Users\pjatakia\Documents\GitHub\HouckLab_QICK\WorkingProjects\Tantalum_fluxonium_marvin\Client_modules\PythonDrivers'
os.add_dll_directory(os.path.dirname(path) + '\\PythonDrivers')

from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Calib.initialize import *
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mLoopback import LoopbackProgram
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransmission_SaraTest import Transmission
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransmission_wQubitTone import Transmission_wQubitTone
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransmission_Enhance import \
    Transmission_Enhance
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecSlice_SaraTest import SpecSlice
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecSlice_bkg_subtracted import \
    SpecSlice_bkg_sub
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabi import AmplitudeRabi
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mTransVsGain import TransVsGain
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabi_Blob import AmplitudeRabi_Blob
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mStarkShift import StarkShift
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabiChevron_Energy import \
    RabiChevronEnergy
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabi_CavityPower import \
    AmplitudeRabi_CavityPower
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT1Experiment import T1Experiment
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT2Experiment import T2Experiment
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT2EchoExperiment import T2EchoExperiment
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotProgram import SingleShotProgram
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShot_2Dsweep import SingleShot_2Dsweep
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabiBlob_PS import AmplitudeRabi_PS
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAmplitudeRabiFlux_PS import \
    AmplitudeRabiFlux_PS
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mQubitSpecRepeat import QubitSpecRepeat
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.m2QubitFluxDrift import TwoQubitFluxDrift
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mConstantTone import ConstantTone_Experiment
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mCalibrateRFSOCSignalHound import \
    CalibrateRFSOCSignalHound
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT1_PS import T1_PS
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotTemp_sse import SingleShotSSE
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecSlice_PS_sse import SpecSlice_PS_sse

from matplotlib import pyplot as plt
import datetime

# Define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2024_10_14_cooldown\\QCage_dev\\"

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

# %%

# TITLE: Loopback experiment
config = {"res_ch": 0,  # --Fixed
          "ro_chs": [0],  # --Fixed
          "reps": 1,  # --Fixed
          "relax_delay": 1.0,  # --us
          "res_phase": 0,  # --degrees
          "pulse_style": "const",  # --Fixed

          "length": soc.us2cycles(0.3),  # [Clock ticks] # 1 us is around 430 cycles
          # Try varying length from 10-100 clock ticks

          "readout_length": 200,  # [Clock ticks]
          # Try varying readout_length from 50-1000 clock ticks

          "pulse_gain": 30000,  # [DAC units]
          # Try varying pulse_gain from 500 to 30000 DAC units

          "pulse_freq": 6250,  # [MHz]
          # In this program the signal is up and downconverted digitally so you won't see any frequency
          # components in the I/Q traces below. But since the signal gain depends on frequency,
          # if you lower pulse_freq you will see an increased gain.

          "adc_trig_offset": 230,  # [Clock ticks]
          # Try varying adc_trig_offset from 100 to 220 clock ticks

          "soft_avgs": 5000
          # Try varying soft_avgs from 1 to 200 averages
          }

prog = LoopbackProgram(soccfg, config)
iq_list = prog.acquire_decimated(soc, load_pulses=True, progress=True, debug=False)
fff = plt.figure(1)
for ii, iq in enumerate(iq_list):
    plt.plot(iq[0], label="I value, ADC %d" % (config['ro_chs'][ii]))
    plt.plot(iq[1], label="Q value, ADC %d" % (config['ro_chs'][ii]))
    plt.plot(np.abs(iq[0] + 1j * iq[1]), label="mag, ADC %d" % (config['ro_chs'][ii]))
plt.ylabel("a.u.")
plt.xlabel("Clock ticks")
plt.title("Averages = " + str(config["soft_avgs"]))
plt.legend()
fff.show()

# %%
# # TITLE: Transmission + Spectroscopy
UpdateConfig_transmission = {
    # Parameters
    "reps": 500,  # Number of repetitions

    # cavity
    "read_pulse_style": "const",
    "read_length": 35,
    "read_pulse_gain": 25000,
    "read_pulse_freq": 6664.89,  # 6253.8,

    # Experiment Parameter
    "TransSpan": 1,  # [MHz] span will be center frequency +/- this parameter
    "TransNumPoints": 201,  # number of points in the transmission frequency
}

UpdateConfig_qubit = {
    "qubit_pulse_style": "const",  # Constant pulse
    "qubit_gain": 6000,  # [DAC Units]
    'sigma': 1,
    'flat_top_length': 5,
    "qubit_length": 50,  # [us]

    # Define spec slice experiment parameters
    "qubit_freq_start": 1126,
    "qubit_freq_stop": 1156,
    "SpecNumPoints": 201,  # Number of points
    'spec_reps': 10000,  # Number of repetition

    # Define the yoko voltage
    "yokoVoltage": 0.005,
    "relax_delay": 10,  # [us] Delay post one experiment
    'use_switch': False,
    'mode_periodic': False,
    'ro_periodic': False,
}

UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit

config = BaseConfig | UpdateConfig

# Set the yoko voltage
yoko1.SetVoltage(config["yokoVoltage"])


# %%
# TITLE Perform the cavity transmission experiment

config = BaseConfig | UpdateConfig
Instance_trans = Transmission(path="dataTestTransmission", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
data_trans = Instance_trans.acquire()
Instance_trans.save_data(data_trans)
Instance_trans.display(data_trans, plotDisp=True)
plt.show()

# Update the transmission frequency to be the peak

config["read_pulse_freq"] = Instance_trans.peakFreq
print("Cavity freq IF [MHz] = ", Instance_trans.peakFreq)

# %%
# TITLE: Cavity Transmission with phase calculated optimal point of measurement
transm_exp = Transmission_Enhance(path="TransmisionEnhanced", cfg=config, soc=soc, soccfg=soccfg,
                                  outerFolder=outerFolder)
data_transm = transm_exp.acquire()
transm_exp.save_data(data_transm)
transm_exp.save_config()
transm_exp.display(data_transm, plotDisp=True)
opt_freq = transm_exp.findOptimalFrequency(data=data_transm, debug=True,window_size = 0.1)
config["read_pulse_freq"] = opt_freq
print(opt_freq)
#%%
# TITLE Perform the cavity transmission experiment with qubit tone

config = BaseConfig | UpdateConfig
config["qubit_freq"] = 1976.58
Instance_trans = Transmission_wQubitTone(path="Transmission_wQubTone", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
data_trans = Instance_trans.acquire()
Instance_trans.save_data(data_trans)
Instance_trans.display(data_trans, plotDisp=True)
plt.show()

# Update the transmission frequency to be the peak

config["read_pulse_freq"] = Instance_trans.peakFreq
print("Cavity freq IF [MHz] = ", Instance_trans.peakFreq)


    # %%
# TITLE Perform the spec slice experiment

# Estimate Time
time = config["spec_reps"] * config["SpecNumPoints"] * (
            config["relax_delay"] + config["qubit_length"] + config["read_length"]) * 1e-6
# print("Time required for spec slice experiment is ", datetime.timedelta(seconds = time).strftime('%H::%M::%S'))
print(time)

Instance_specSlice = SpecSlice(path="dataTestSpecSlice", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
data_specSlice = SpecSlice.acquire(Instance_specSlice)
SpecSlice.display(Instance_specSlice, data_specSlice, plotDisp=True)
SpecSlice.save_data(Instance_specSlice, data_specSlice)
print(Instance_specSlice.qubitFreq)
plt.show()

# %%
# TITLE Perform the spec slice with background subtracted
# config["relax_delay"] = 2000
# config["qubit_gain"] = 20000
time = config["spec_reps"] * config["SpecNumPoints"] * (
            config["relax_delay"] + config["flat_top_length"] + config["read_length"]) * 1e-6
print(time / 60)

Instance_specSlice = SpecSlice_bkg_sub(path="dataTestSpecSlice_temp", cfg=config,
                                       soc=soc, soccfg=soccfg, outerFolder=outerFolder)
data_specSlice = SpecSlice_bkg_sub.acquire(Instance_specSlice)
SpecSlice_bkg_sub.save_data(Instance_specSlice, data_specSlice)
SpecSlice_bkg_sub.display(Instance_specSlice, data_specSlice, plotDisp=True)

# %%
# TITLE : Perform the spec slice with Post Selection
config_spec_ps = {
    'spec_reps': 8000,  # Converted to shots
    'initialize_pulse': False,
    'fridge_temp': 420,
    "qubit_pulse_style": "flat_top"
}
config_spec_ps = config | config_spec_ps
inst_specslice = SpecSlice_PS_sse(path="dataTestSpecSlice_PS", cfg=config_spec_ps,
                                  soc=soc, soccfg=soccfg, outerFolder=outerFolder)
data_specSlice_PS = inst_specslice.acquire()
data_specSlice_PS = inst_specslice.process_data(data=data_specSlice_PS)
inst_specslice.display(data=data_specSlice_PS, plotDisp=True)
inst_specslice.save_data(data_specSlice_PS)

# %%
# TITLE: Amplitude Rabi

UpdateConfig_spec = {

    # Experiment
    "qubit_gain_start": 0,  # [DAC Units]
    "qubit_gain_step": 2000,  # [DAC Units] gain step size
    "qubit_gain_expts": 17,  # 26,  ### number of steps
    "AmpRabi_reps": 10000,  # 10000,  # number of averages for the experiment
    "relax_delay": 6 * 1600,

    # Qubit Tone
    "qubit_pulse_style": "const",
    "sigma": 0.05,
    "flat_top_length": 10,
    "qubit_freq": 244,
    "qubit_length": 0.025,
    "use_switch": True,
}

config = config | UpdateConfig_spec

Instance_AmplitudeRabi = AmplitudeRabi(path="dataTestAmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                                       outerFolder=outerFolder)
data_AmplitudeRabi = AmplitudeRabi.acquire(Instance_AmplitudeRabi)
AmplitudeRabi.display(Instance_AmplitudeRabi, data_AmplitudeRabi, plotDisp=True)
AmplitudeRabi.save_data(Instance_AmplitudeRabi, data_AmplitudeRabi)
AmplitudeRabi.save_config(Instance_AmplitudeRabi)
# endregion
# %%
# TITLE: Transmission vs Power

UpdateConfig = {
    "yokoVoltage": 0.005,
    "trans_gain_start": 100,
    "trans_gain_stop": 6000,
    "trans_gain_num": 31,
    "trans_reps": 500,
    "read_pulse_style": "const",
    "readout_length": 50,  # [us]
    "trans_freq_start": 6664.94 - 0.5,  # [MHz]
    "trans_freq_stop": 6664.94 + 0.5,  # [MHz]
    "TransNumPoints": 101,
    "relax_delay": 2,
    "units": "DAC",  # use "dB" or "DAC"
    "normalize": True,
}
config = BaseConfig | UpdateConfig

# Set the yoko voltage
# yoko1.SetVoltage(config["yokoVoltage"])

# Run experiment
Instance_TransVsGain = TransVsGain(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config, soc=soc,
                                   soccfg=soccfg)
data_TransVsGain = TransVsGain.acquire(Instance_TransVsGain)
TransVsGain.save_data(Instance_TransVsGain, data_TransVsGain)
TransVsGain.save_config(Instance_TransVsGain)

#%%
# TITLE: Amplitude rabi Chevron
UpdateConfig = {
    ##### define attenuators
    "yokoVoltage": -0.465,
    ###### cavity
    "read_pulse_style": "const",  # --Fixed
    "read_length": 20,  # us
    "read_pulse_gain": 3500,  # [DAC units]
    "read_pulse_freq": 6671.88,
    ##### spec parameters for finding the qubit frequency
    "qubit_freq_start": 1920,
    "qubit_freq_stop": 2050,
    "RabiNumPoints": 131,  ### number of points
    "qubit_pulse_style": "const",
    "sigma": 1,  ### units us, define a 20ns sigma
    "qubit_length": 20,
    "flat_top_length": 30,  ### in us
    "relax_delay": 10,  ### turned into us inside the run function
    "qb_periodic": True,
    ##### amplitude rabi parameters
    "qubit_gain_start": 0,
    "qubit_gain_step": 1000,  ### stepping amount of the qubit gain
    "qubit_gain_expts": 11,  ### number of steps
    "AmpRabi_reps": 6000,  # number of averages for the experiment

    "use_switch": True,
}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
print('Running Rabi Chevron: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
time_estimate = (config['relax_delay'] + config['sigma'] * 4 + config['read_length']) * config['RabiNumPoints'] * \
                config['qubit_gain_expts'] * config['AmpRabi_reps'] * 1e-6 / 60
print("Time required is - " + str(time_estimate) + " in min")
Instance_AmplitudeRabi_Blob = AmplitudeRabi_Blob(path="dataTestRabiAmpBlob", outerFolder=outerFolder, cfg=config,
                                                 soc=soc, soccfg=soccfg, progress=True)
data_AmplitudeRabi_Blob = AmplitudeRabi_Blob.acquire(Instance_AmplitudeRabi_Blob)
AmplitudeRabi_Blob.save_data(Instance_AmplitudeRabi_Blob, data_AmplitudeRabi_Blob)
AmplitudeRabi_Blob.save_config(Instance_AmplitudeRabi_Blob)

# %%
# TITLE: Amplitude Rabi Chevron with energy of the pulse being constant
UpdateConfig = {
    "yokoVoltage": -0.09666934840425528,

    # Readout Parameters
    "read_pulse_style": "const",  # --Fixed
    "read_length": 20,  # us
    "read_pulse_gain": 3000,  # [DAC units]
    "read_pulse_freq": 6671.77,

    # spec parameters for finding the qubit frequency
    "qubit_freq_start": 2000,
    "qubit_freq_stop": 3000,
    "RabiNumPoints": 101,  ### number of points
    "qubit_pulse_style": "flat_top",
    "sigma": 2,  ### units us, define a 20ns sigma
    "qubit_length": 40,
    "flat_top_length": 20,  ### in us
    "relax_delay": 10,  ### turned into us inside the run function

    # amplitude rabi parameters
    "qubit_gain_start": 0,
    "qubit_gain_step": 250,  ### stepping amount of the qubit gain
    "qubit_gain_expts": 21,  ### number of steps
    "AmpRabi_reps": 10000,  # number of averages for the experiment

    "use_switch": True,
}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
print('Running Rabi Chevron: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
time_estimate = (config['relax_delay'] + config['sigma'] * 4 + config['read_length']) * config['RabiNumPoints'] * \
                config['qubit_gain_expts'] * config['AmpRabi_reps'] * 1e-6 / 60
print("Time required is - " + str(time_estimate) + " in min")

inst_arc_exp = RabiChevronEnergy(path="RabiChevronPower", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg,
                                 progress=True)
data_arc_exp = inst_arc_exp.acquire(debug=True)
inst_arc_exp.save_data(data_arc_exp)
inst_arc_exp.save_config()

#%%
# TITLE : Stark Shift

UpdateConfig = {

    # cavity
    "read_pulse_style": "const",
    "read_length": 20,
    "read_pulse_gain": 2000,
    "read_pulse_freq": 6671.87,

    # Parameters
    "reps": 8000,  # Number of repetitions
    "TransSpan": 1,  # [MHz] span will be center frequency +/- this parameter
    "TransNumPoints": 51,  # number of points in the transmission frequency

    # Qubit
    "qubit_pulse_style": "const",  # Constant pulse
    "qubit_gain": 6000,  # [DAC Units]
    "qubit_length": 25,  # [us]

    # Define qubit experiment parameters
    "qubit_freq_start": 1970,
    "qubit_freq_stop": 2000,
    "SpecNumPoints": 101,  # Number of points
    'spec_reps': 12000,

    # Define cavity experiment parameters
    "trans_gain_start" : 0,
    "trans_gain_stop" : 800,
    "trans_gain_num" : 5,

    # Define experiment
    "yokoVoltage": -0.465,
    "relax_delay": 0.05,  # [us] Delay post one experiment
    'use_switch': False,
    'mode_periodic': False,
    'ro_periodic': False,
    'units': 'DAC',
    "calibrate_cav": False
}

config = BaseConfig | UpdateConfig
# yoko1.SetVoltage(config["yokoVoltage"])
inst_stark_shift = StarkShift(path="StarkShift", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg,
                                 progress=True)
data_stark_shift = inst_stark_shift.acquire()
inst_stark_shift.save_data(data = data_stark_shift)
inst_stark_shift.save_config()

#%%
# TITLE : Qubit Spec Repeat
UpdateConfig = {

    # cavity
    "read_pulse_style": "const",
    "read_length": 30,
    "read_pulse_gain": 900,
    "read_pulse_freq": 6671.88,  # 6253.8,

    # Qubit
    "qubit_pulse_style": "const",  # Constant pulse
    "qubit_gain": 6000,  # [DAC Units]
    "qubit_length": 25,  # [us]

    # Define qubit experiment parameters
    "qubit_freq_start": 1975,
    "qubit_freq_stop": 1985,
    "SpecNumPoints": 201,  # Number of points
    'spec_reps': 5000,
    'repetitions': 151,
    'delay': 1,

    # Define experiment
    "yokoVoltage": -0.465,
    "relax_delay": 10,  # [us] Delay post one experiment
    'use_switch': False,
    'mode_periodic': False,
    'ro_periodic': False,
    'units': 'DAC',
    "calibrate_cav": True,
}
config = BaseConfig | UpdateConfig
# yoko1.SetVoltage(config["yokoVoltage"])
inst_qspec_repeat = QubitSpecRepeat(path="Qubit_Spec_Repeat", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg,
                                 progress=True)
data_qspec_repeat = inst_qspec_repeat.acquire()
inst_qspec_repeat.save_data(data = data_qspec_repeat)
inst_qspec_repeat.save_config()

# %%
# TITLE: T1 measurement

UpdateConfig = {
    "yokoVoltage": -0.12,

    # Readout
    "read_pulse_style": "const",
    "read_length": 50,
    "read_pulse_gain": 1960,
    "read_pulse_freq": 6672.7,

    # Qubit Tone
    "qubit_freq": 65.4,
    "qubit_gain": 5000,
    "qubit_pulse_style": "const",
    "sigma": 1,
    "flat_top_length": 10,
    "qubit_length": 10,

    # Experiment
    "relax_delay": 20000,
    "start": 0,
    "step": 300,
    "expts": 21,
    "reps": 4000,

    # Switch
    "use_switch": True,
}
config = BaseConfig | UpdateConfig

yoko1.SetVoltage(config["yokoVoltage"])
print("Voltage is ", yoko1.GetVoltage(), " Volts")

# Estimate time required to run this experiment
tot_time = (np.sum(np.linspace(config["start"], config['step'] * (config["expts"] - 1), config["expts"]))
            + config["expts"] * config["relax_delay"]) * config["reps"]
print("Time required for T1 Experiment is ", datetime.timedelta(seconds=tot_time * 1e-6))

# Run Experiment
inst_t1 = T1Experiment(path="dataTestT1Experiment", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg,
                       progress=True)
data_t1 = inst_t1.acquire()

# Process
inst_t1.display(data_t1, plotDisp=True)
inst_t1.save_data(data_t1)
inst_t1.save_config()


# %%
# TITLE: T2 Measurement
UpdateConfig = {
    "yokoVoltage": -0.035,

    # Readout Parameters
    "read_pulse_style": "const",
    "read_length": 70,  # us
    "read_pulse_gain": 1500,  # [DAC units]
    "read_pulse_freq": 6671.2,  # [MHz]

    # Qubit Parameters
    "qubit_freq": 244,
    "qubit_gain": 58000,
    "pi2_qubit_gain": 29000,
    "sigma": 0.150,  # [us]
    "qubit_pulse_style": "const",
    "flat_top_length": 0.080,
    "qubit_length": 0.013,

    # Experiment Parameters
    "relax_delay": 5*1600,
    "start": 0,  # [us]
    "step": 0.002,   # [us]
    "expts": 11,
    "reps": 40000,
    "use_switch": True
}
config = BaseConfig | UpdateConfig

# yoko1.SetVoltage(config["yokoVoltage"])

t2_exp = T2Experiment(path="T2_RamseyExperiment", outerFolder=outerFolder, cfg=config, soc=soc,soccfg=soccfg)
data_t2exp = t2_exp.acquire()
t2_exp.save_data(data_t2exp)
t2_exp.save_config()
t2_exp.display(data_t2exp, plotDisp=True)

# %%
# # for idx in range(4):
# #     Instance_T2Experiment = T2Experiment(path="dataTestT2RExperiment", outerFolder=outerFolder, cfg=config, soc=soc,
# #                                          soccfg=soccfg)
# #     data_T2Experiment = T2Experiment.acquire(Instance_T2Experiment)
# #     T2Experiment.display(Instance_T2Experiment, data_T2Experiment, plotDisp=True)
# #     T2Experiment.save_data(Instance_T2Experiment, data_T2Experiment)
# #     T2Experiment.save_config(Instance_T2Experiment)
# endregion
#%%
# TITLE: T2 echo measurement
# region Config File
# UpdateConfig = {
#     ##### define attenuators
#     "yokoVoltage": -1.16,
#     ###### cavity
#     "read_pulse_style": "const", # --Fixed
#     "read_length": 10, # us
#     "read_pulse_gain": 10000, # [DAC units]
#     "read_pulse_freq": 5988.37, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### spec parameters for finding the qubit frequency
#     "qubit_freq": 1716.5,
#     "pi_qubit_gain": 3300,
#     "pi2_qubit_gain": 1650,
#     "sigma": 0.050,  ### units us, define a 20ns sigma
#     "qubit_pulse_style": "arb", #### arb means gaussain here
#     "relax_delay": 3000,  ### turned into us inside the run function
#     ##### T1 parameters
#     "start": 0, ### us
#     "step": 5, ### us
#     "expts": 201, ### number of experiemnts
#     "reps": 500, ### number of averages on each experiment
# }
# config = BaseConfig | UpdateConfig
# yoko1.SetVoltage(config["yokoVoltage"])
# print("Voltage is ", yoko1.GetVoltage(), " Volts")
#
# Instance_T2EchoExperiment = T2EchoExperiment(path="dataTestT2EchoExperiment", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg,  progress=True)
# data_T2EchoExperiment = T2EchoExperiment.acquire(Instance_T2EchoExperiment)
# T2EchoExperiment.display(Instance_T2EchoExperiment, data_T2EchoExperiment, plotDisp=True)
# T2EchoExperiment.save_data(Instance_T2EchoExperiment, data_T2EchoExperiment)
# T2EchoExperiment.save_config(Instance_T2EchoExperiment)
# endregion

# %%
# #TITLE Constant tone experiment
UpdateConfig = {
    ###### cavity
    "read_pulse_style": "const",  # --Fixed
    "gain": 0,  # [DAC units]
    "freq": 6500,  # [MHz]
    "channel": 0,  # TODO default value
    "nqz": 2,  # TODO default value
}

config = BaseConfig | UpdateConfig
#

ConstantTone_Instance = ConstantTone_Experiment(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config,
                                                soc=soc, soccfg=soccfg)
data_ConstantTone = ConstantTone_Experiment.acquire(ConstantTone_Instance)
ConstantTone_Experiment.save_data(ConstantTone_Instance, data_ConstantTone)
ConstantTone_Experiment.save_config(ConstantTone_Instance)
print("Done")
# %%
# TITLE: Calibrate RFSOC with Signal Hound

UpdateConfig = {
    "read_pulse_style": "const",  # --Fixed
    "gain_start": 1000,  # [DAC units]
    'gain_stop': 30000,
    'gain_num': 15,
    'freq_start': 10,
    'freq_stop': 1000,
    'freq_num': 100,
    "channel": 1,  # TODO default value
    "nqz": 1,  # TODO default value
}

config = BaseConfig | UpdateConfig

my_calib = CalibrateRFSOCSignalHound(path="RFSOC_calib", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg)
data = my_calib.calibrate(meas_span=1e6, debug=False)
my_calib.display_calibrated_data(data=data, plotDisp=True)
my_calib.save_config()
my_calib.save_data(data=data)

# %%
# UpdateConfig = {
#     # Set Yoko Voltage
#     "yokoVoltage": -1.8,
#
#     # Readout Parameters
#     "read_pulse_style": "const",  # Constant Tone
#     "read_length": 5,  # [us]
#     "read_pulse_gain": 7400,  # [DAC units]
#     "read_pulse_freq": 6437.4,  # [MHz]
#
#     # qubit parameters
#     "qubit_pulse_style": "arb",
#     "sigma": 0.100,
#     "qubit_ge_gain": 600,
#     "qubit_ge_freq": 2243.4,
#     "qubit_ef_gain": 8000,
#     "qubit_ef_freq": 2081.5,
#     "relax_delay": 500,
#
#     # Experiment time
#     "cen_num": 3,
#     "use_switch": True,
# }
# config = BaseConfig | UpdateConfig
#
# Update_config_ss = {
#     # qubit parameters
#     "qubit_pulse_style": "arb",
#     "sigma": 0.100,
#     "qubit_ge_gain": 250,
#     "qubit_ef_gain": 8000,
#
#     # Experiment parameters
#     'shots': 40000,
#     'relax_delay': 4000,
#     'initialize_pulse': True,
#     'fridge_temp': 10.0,
#     'qubit_freq': 2200,
# }
# config_ss = config | Update_config_ss
#
# scan_time = (config_ss["relax_delay"] * config_ss["shots"] * 2) * 1e-6 / 60
# print('estimated time: ' + str(round(scan_time, 2)) + ' minutes')
# Instance_SingleShotSSE = SingleShotSSE(path="dataSingleShot_TempCalc_temp_",
#                                        outerFolder=outerFolder,
#                                        cfg=config_ss,
#                                        soc=soc, soccfg=soccfg)
# data_SingleShotSSE = SingleShotSSE.acquire(Instance_SingleShotSSE)
# data_SingleShotSSE = SingleShotSSE.process_data(Instance_SingleShotSSE, data_SingleShotSSE, cen_num = 3)
# SingleShotSSE.display(Instance_SingleShotSSE, data_SingleShotSSE, plotDisp=True, save_fig=True)
# SingleShotSSE.save_data(Instance_SingleShotSSE, data_SingleShotSSE)
# SingleShotSSE.save_config(Instance_SingleShotSSE)

# %%
# # TITLE: Auto Calibration
#
# # import the measurement class
# from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mAutoCalibrator import CalibratedFlux
#
# # Defining changes to the config
# UpdateConfig = {
#     # define the yoko voltage
#     "yokoVoltageStart": 0.0,
#     "yokoVoltageStop": 10.0,
#     "yokoVoltageNumPoints": 81,
#
#     # cavity and readout
#     "trans_reps": 50,
#     "read_pulse_style": "const",
#     "read_length": 20,  # us
#     "read_pulse_gain": 7000,  # [DAC units]
#     "trans_freq_start": 6437.4 - 2.0,  # [MHz]
#     "trans_freq_stop": 6437.4 + 2.0,  # [MHz]
#     "TransNumPoints": 51,
#
#     # Experiment Parameters
#     "relax_delay": 5,
#     'use_switch': True,
# }
# config = BaseConfig | UpdateConfig
#
# yoko_calibration = CalibratedFlux(path="data_calibration", outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg)
# yoko_calibration.calibrate()
# yoko_calibration.save_data()
# yoko_calibration.display()

# %%
