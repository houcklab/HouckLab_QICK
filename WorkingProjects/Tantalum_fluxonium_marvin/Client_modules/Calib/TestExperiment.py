# %%
import os

import Pyro4.util

from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mFFRampTest import FFRampTest_Experiment
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mQubitTwoToneResonatorCool import \
    QubitTwoToneResonatorCoolExperiment

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
# from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mConstantTone import ConstantTone_Experiment
# from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mCalibrateRFSOCSignalHound import \
#     CalibrateRFSOCSignalHound
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mT1_PS import T1_PS
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSingleShotTemp_sse import SingleShotSSE
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.Experiments.mSpecSlice_PS_sse import SpecSlice_PS_sse

from matplotlib import pyplot as plt
import datetime

# Define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2025_07_25_cooldown\\QCage_dev\\"

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

#%%
# # TITLE: Constant Tone Experiment
# UpdateConfig = {
#     ###### cavity
#     "read_pulse_style": "const",  # --Fixed
#     "gain": 0,  # [DAC units]
#
#     "freq": 6672.42966,#3713,  # [MHz]
#
#     "channel": 0, #0,  # TODO default value # 0 is resonator, 1 is qubit
#     "nqz": 2, #2,#1,  # TODO default value
# }
#
# config = BaseConfig | UpdateConfig
#
# ConstantTone_Instance = ConstantTone_Experiment(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# try:
#     ConstantTone_Experiment.acquire(ConstantTone_Instance)
# except Exception:
#     print("Pyro traceback:")
#     print("".join(Pyro4.util.getPyroTraceback()))
# ConstantTone_Experiment.save_data(ConstantTone_Instance)
# ConstantTone_Experiment.save_config(ConstantTone_Instance)
#
# # using the 10MHz-1GHz balun
# # f_center = 10e9 #Hz
# # settings = set_filter(f_center)
# # print(settings)
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

          "pulse_gain": 10000,  # [DAC units]
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
    "reps": 3000,  # Number of repetitions

    # cavity
    "read_pulse_style": "const",
    "read_length": 30,
    "read_pulse_gain": 5000,
    "read_pulse_freq": 6671.695,  # 6253.8,

    # Experiment Parameter
    "TransSpan":  0.75,  # [MHz] span will be center frequency +/- this parameter
    "TransNumPoints": 101,  # number of points in the transmission frequency
    "meas_config": "hanger"
,}

UpdateConfig_qubit = {
    "qubit_pulse_style": "const",  # Constant pulse
    "qubit_gain": 1000,  # [DAC Units]
    'sigma': 2,
    'flat_top_length': 2,
    "qubit_length": 4,  # [us]

    # Define spec slice experiment parameters
    "qubit_freq_start": 1200,
    "qubit_freq_stop": 1800,
    "SpecNumPoints": 101,  # Number of points
    'spec_reps': 5000,  # Number of repetition
    "delay_btwn_pulses" : 0.05, # Delay between the qubit tone and the readout tone. If not defined it uses 50ns

    # Define the yoko voltage
    "yokoVoltage": 0.0113,
    "relax_delay": 10,  # [us] Delay post one experiment
    'use_switch': False, # This is for turning off the heating tone
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
soc.reset_gens()
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
config["qubit_freq"] = 1960
Instance_trans = Transmission_wQubitTone(path="Transmission_wQubTone", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
data_trans = Instance_trans.acquire()
Instance_trans.save_data(data_trans)
Instance_trans.display(data_trans, plotDisp=True)
plt.show()


    # %%
# TITLE Perform the spec slice experiment
soc.reset_gens()
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
time = 2*config["spec_reps"] * config["SpecNumPoints"] * (
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
    'initialize_pulse': True,
    'initialize_qubit_gain' : 1000,
    'fridge_temp': 420,
    "qubit_pulse_style": "const",
    'qubit_freq_base': 156,
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
    "qubit_gain_step": 8000,  # [DAC Units] gain step size
    "qubit_gain_expts": 11,  # 26,  ### number of steps
    "AmpRabi_reps": 8000,  # 10000,  # number of averages for the experiment
    "relax_delay": 3000,#6 * 1600,

    # Qubit Tone
    "qubit_pulse_style": "flat_top",
    "sigma": 0.05,
    "flat_top_length": 20,
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
    "yokoVoltage": 0.0113,
    "trans_gain_start": 100,
    "trans_gain_stop": 12000,
    "trans_gain_num": 31,
    "trans_reps": 800,
    "read_pulse_style": "const",
    "readout_length": 10,  # [us]
    "trans_freq_start": 6671,  # [MHz]
    "trans_freq_stop": 6673,  # [MHz]
    "TransNumPoints": 101,
    "relax_delay": 10,
    "units": "DAC",  # use "dB" or "DAC"
    "normalize": True,
}
config = BaseConfig | UpdateConfig
#%%
# Set the yoko voltage
yoko1.SetVoltage(config["yokoVoltage"])

# Run experiment
Instance_TransVsGain = TransVsGain(path="dataTestTransVsGain", outerFolder=outerFolder, cfg=config, soc=soc,
                                   soccfg=soccfg)
data_TransVsGain = TransVsGain.acquire(Instance_TransVsGain)
TransVsGain.save_data(Instance_TransVsGain, data_TransVsGain)
TransVsGain.save_config(Instance_TransVsGain)

# %%
# TITLE : Check  Trans vs Power for multiple flux points

flux_list = [-0.122,-0.1215, -0.121, -0.1205, -0.12, -0.1195, -0.119, -0.1185]

for flux in flux_list:
    config['yokoVoltage'] = flux
    yoko1.SetVoltage(config["yokoVoltage"])
    print("Yoko voltage set tos ", yoko1.GetVoltage(), " Volts")
    time.sleep(2)
    # Run experiment
    Instance_TransVsGain = TransVsGain(path="dataTestTransVsGain_flux" + str(flux).replace('.', 'p'),
                                        outerFolder=outerFolder, cfg=config, soc=soc, soccfg=soccfg, prefix = str(flux))
    data_TransVsGain = TransVsGain.acquire(Instance_TransVsGain)
    TransVsGain.save_data(Instance_TransVsGain, data_TransVsGain)
    TransVsGain.save_config(Instance_TransVsGain)
#%%
# TITLE: Amplitude rabi Chevron
UpdateConfig = {
    ##### define attenuators
    "yokoVoltage": 0.01,
    ###### cavity
    "read_pulse_style": "const",  # --Fixed
    "read_length": 30,  # us
    "read_pulse_gain": 8000,  # [DAC units]
    "read_pulse_freq": 6671.65,
    ##### spec parameters for finding the qubit frequency
    "qubit_freq_start": 1400,
    "qubit_freq_stop": 1700,
    "RabiNumPoints": 101,  ### number of points
    "qubit_pulse_style": "const",
    "sigma": 1,  ### units us, define a 20ns sigma
    "qubit_length": 5,
    "flat_top_length": 25,  ### in us
    "relax_delay": 50,  ### turned into us inside the run function
    "qb_periodic": False,
    ##### amplitude rabi parameters
    "qubit_gain_start": 0,
    "qubit_gain_step": 500,  ### stepping amount of the qubit gain
    "qubit_gain_expts": 11,  ### number of steps
    "AmpRabi_reps": 4000,  # number of averages for the experiment
    "use_switch": False,
}
config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yokoVoltage"])
print('Running Rabi Chevron: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
time_estimate = (config['relax_delay'] + config['sigma'] * 4 + config['read_length']) * config['RabiNumPoints'] * \
                config['qubit_gain_expts'] * config['AmpRabi_reps'] * 1e-6 / 60
print("Time required is - " + str(time_estimate) + " in min")
try:
    Instance_AmplitudeRabi_Blob = AmplitudeRabi_Blob(path="dataTestRabiAmpBlob", outerFolder=outerFolder, cfg=config,
                                                     soc=soc, soccfg=soccfg, progress=True)
    data_AmplitudeRabi_Blob = AmplitudeRabi_Blob.acquire(Instance_AmplitudeRabi_Blob)
    AmplitudeRabi_Blob.save_data(Instance_AmplitudeRabi_Blob, data_AmplitudeRabi_Blob)
    AmplitudeRabi_Blob.save_config(Instance_AmplitudeRabi_Blob)
except:
    print("Pyro Traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))

# %%
# TITLE: Amplitude Rabi Chevron with energy of the pulse being constant
UpdateConfig = {
    "yokoVoltage": -0.092,

    # Readout Parameters
    "read_pulse_style": "const",  # --Fixed
    "read_length": 40,  # us
    "read_pulse_gain": 5000,  # [DAC units]
    "read_pulse_freq": 6672.498,

    # spec parameters for finding the qubit frequency
    "qubit_freq_start": 140,
    "qubit_freq_stop": 180,
    "RabiNumPoints": 101,  ### number of points
    "qubit_pulse_style": "flat_top",
    "sigma": 1,  ### units us, define a 20ns sigma
    "qubit_length": 5,
    "flat_top_length": 20,  ### in us
    "relax_delay": 1000,  ### turned into us inside the run function

    # amplitude rabi parameters
    "qubit_gain_start": 50,
    "qubit_gain_step": 500,  ### stepping amount of the qubit gain
    "qubit_gain_expts": 21,  ### number of steps
    "AmpRabi_reps": 5000,  # number of averages for the experiment
    'ro_periodic':False,
    "use_switch": False,
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
    "yokoVoltage": -0.42,

    # Readout
    "read_pulse_style": "const",
    "read_length": 10,
    "read_pulse_gain": 10000,
    "read_pulse_freq": 6671.6812,

    # Qubit Tone
    "qubit_freq": 2184,
    "qubit_gain": 4000,
    "qubit_pulse_style": "const",
    "sigma": 1,
    "flat_top_length": 20,
    "qubit_length": 0.5,

    # Experiment
    "relax_delay": 100,
    "start": 0,
    "step": 3,
    "expts": 51,
    "reps": 50000,

    # Switch
    "use_switch": False,
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
# TITLE: Two-tone parametric qubit cooling through resonator

UpdateConfig = {
    # Readout parameters
    "read_length": 10,
    "read_pulse_gain": 10000,
    "read_pulse_freq": 6432,

    # Parametric drive parameters
    "cavity_drive_gain": 30000, # DAC units
    "qubit_drive_gain": 30000, # DAC units
    "qubit_freq": 1395, # MHz
    "Delta": 5, # MHz
    "T": 100, # us

    # sweep parameters
    "start": -3, # MHz
    "stop": 3, # MHz
    "steps": 51,
    "sweep": "delta",

    # Experiment parameters
    "yoko_voltage": -0.72,
    "relax_delay": 5000, #us
    "reps": 50000,
    "use_switch": False,
}

config = BaseConfig | UpdateConfig
yoko1.SetVoltage(config["yoko_voltage"])

inst_q2trc = QubitTwoToneResonatorCoolExperiment(path="dataQubit2TResonatorCool", outerFolder = outerFolder,
                                                 cfg = config, soc = soc, soccfg = soccfg)
data_q2trc = inst_q2trc.acquire()
inst_q2trc.display()
inst_q2trc.save_config()

#%%
# Fast flux ramp test experiment

config = {
        # Readout section
        "read_pulse_style": "const",  # --Fixed
        "read_length": 2,  # [us]
        "read_pulse_gain": 300,  # [DAC units]
        "read_pulse_freq": 6723.5,  # [MHz]
        # Fast flux pulse parameters
        "ff_ramp_style": "linear",  # one of ["linear"]
        "ff_ramp_start": 0, # [DAC units] Starting amplitude of ff ramp, -32766 < ff_ramp_start < 32766
        "ff_ramp_stop": 5000, # [DAC units] Ending amplitude of ff ramp, -32766 < ff_ramp_stop < 32766
        "ff_delay": 0., # [us] Delay between fast flux ramps
        "ff_ch": 6,  # RFSOC output channel of fast flux drive
        "ff_nqz": 1,  # Nyquist zone to use for fast flux drive
        # Sweep parameters
        "ff_ramp_length_start": 10,  # [us] Total length of positive fast flux pulse, start of sweep
        "ff_ramp_length_stop": 10,  # [us] Total length of positive fast flux pulse, end of sweep
        "ff_ramp_expts": 3, # [int] Number of points in the ff ramp length sweep
        "yokoVoltage": 3.12,  # [V] Yoko voltage for magnet offset of flux
        "relax_delay_1": 10 - BaseConfig["adc_trig_offset"],  # [us] Relax delay after first readout
        "relax_delay_2": 10 - BaseConfig["adc_trig_offset"], # [us] Relax delay after second readout
        "reps": 100000,
        "sets": 5,
        "angle": None, # [radians] Angle of rotation for readout
        "threshold": None, # [DAC units] Threshold between g and e
    }

# We have 65536 samples (9.524 us) wave memory on the FF channel (and all other channels)

#yoko.SetVoltage(config["yokoVoltage"])

mlbf_filter = MLBFDriver("169.254.1.1")
filter_freq = (config["read_pulse_freq"])
mlbf_filter.set_frequency(int(filter_freq))

config = BaseConfig | config
# length = 1.5
#from WorkingProjects.Tantalum_fluxonium_escher.Client_modules.Experiments.mFFRampTest import FFRampTest
#prog = FFRampTest(soccfg, cfg | {"ff_ramp_length": length})

Instance_FFRampTest = FFRampTest_Experiment(path="FFRampTest", cfg=config,soc=soc,soccfg=soccfg,
                                              outerFolder = outerFolder, short_directory_names = True)

# Estimate Time
time = Instance_FFRampTest.estimate_runtime()
print("Time for ff spec experiment is about ", time, " s")

try:
    data_FFRampTest = FFRampTest_Experiment.acquire(Instance_FFRampTest, progress = True)
    FFRampTest_Experiment.display(Instance_FFRampTest, data_FFRampTest, plot_disp=True)
    FFRampTest_Experiment.save_data(Instance_FFRampTest, data_FFRampTest)
    FFRampTest_Experiment.save_config(Instance_FFRampTest)
except Exception:
    print("Pyro traceback:")
    print("".join(Pyro4.util.getPyroTraceback()))

# print(Instance_specSlice.qubitFreq)
plt.show()