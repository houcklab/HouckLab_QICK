# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from q4diamond.Client_modules.initialize import *

from q4diamond.Client_modules.Running_Experiments.Calibrated_parameters import *
from q4diamond.Client_modules.Experiment_Scripts.mSingleShotProgramFF import SingleShotProgramFF
from q4diamond.Client_modules.Experiment_Scripts.mRabiOscillations_SS import Oscillations_SS

print(soc)

#### define the saving path
outerFolder = "Z:\Jeronimo\Measurements\RFSOC_3Qubit\\"

def threshold_calibration(dictionary_label, shots=6000):
    qubit_reading_from = parameter[dictionary_label]
    config = {}

    FF_Read_params = parameter["FF_gains"]
    FF_gain1_read = FF_Read_params[0]
    FF_gain2_read = FF_Read_params[1]
    FF_gain3_read = FF_Read_params[2]

    FF_gain1_exp = FF_Read_params[0]
    FF_gain2_exp = FF_Read_params[1]
    FF_gain3_exp = FF_Read_params[2]

    UpdateConfig_FF_multiple = {
        "FF_list_readout": [(FF_channel1, FF_gain1_read),
                            (FF_channel2, FF_gain2_read), (FF_channel3, FF_gain3_read)]
    }
    UpdateConfig_FF_pulse = {
        "FF_list_exp": [(FF_channel1, FF_gain1_exp),
                        (FF_channel2, FF_gain2_exp), (FF_channel3, FF_gain3_exp)]
    }
    UpdateConfig_FF_multiple = UpdateConfig_FF_multiple | UpdateConfig_FF_pulse

    cavityAtten.SetAttenuation(qubit_reading_from["cavity_atten"], printOut=False)

    config["read_pulse_freq"] = qubit_reading_from["cavity_frequency"]
    config["read_pulse_gain"] = qubit_reading_from["cavity_gain"]
    config["readout_time"] = qubit_reading_from["readout_time"]
    config["adc_trig_offset"] = qubit_reading_from["adc_offset"]
    config["qubit_freq"] = qubit_reading_from["qubit_frequency"]
    config["sigma"] = qubit_reading_from["qubit_pulse_parameters"]["sigma"]
    config["qubit_gain"] = qubit_reading_from["qubit_pulse_parameters"]["pi_gain"]
    config["relax_delay"] = qubit_reading_from["relax_delay"]
    config["read_length"] = qubit_reading_from["readout_time"]
    config["ff_freq"] = 0
    config["ff_ch"] = 6
    config["ff_nqz"] = 1
    config["ff_pulse_style"] = "const"



    config["shots"] = shots

    leftover_parameters = {
        "read_pulse_style": "const",
        "qubit_pulse_style": "arb",
    }

    config = BaseConfig | UpdateConfig_FF_multiple | leftover_parameters | config
    print(config)
    Instance_SingleShotProgram = SingleShotProgramFF(path="dataSingleShot", outerFolder=outerFolder, cfg=config,
                                                     soc=soc, soccfg=soccfg)
    data_SingleShotProgram = SingleShotProgramFF.acquire(Instance_SingleShotProgram)
    SingleShotProgramFF.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)
    threshold = Instance_SingleShotProgram.threshold
    angle = Instance_SingleShotProgram.angle
    print("Fidelity: ", Instance_SingleShotProgram.fid)
    return (threshold, angle)


parameter = parameter_3Q

yoko_values = parameter["yoko_values"]
yoko72.SetVoltage(yoko_values[0])
yoko74.SetVoltage(yoko_values[1])
yoko76.SetVoltage(yoko_values[2])

FF_channel1 = 6 #6 is left, 4 is middle, 5 is right
FF_channel2 = 4 #4 is middle qubit, 6 is left qubit
FF_channel3 = 5 #4 is middle qubit, 6 is left qubit,


# Left_threshold, Left_angle = threshold_calibration("Left_Qubit")

# print(Left_threshold, Left_angle)
#
# Middle_threshold, Middle_angle = threshold_calibration("Middle_Qubit")

# print(t, c)

Read_Qubit = "Right_Qubit"
Pi_Pulse = "Left_Qubit"
shots = 2000

qubit_reading_from = parameter[Read_Qubit]
qubit_pi_pulsing = parameter[Pi_Pulse]

threshold, angle = threshold_calibration(Read_Qubit)
threshold = threshold

print("threshold: ", threshold)
print("Angle: ", angle)

config = {}

FF_Read_params = parameter["FF_gains"]
FF_gain1_read = FF_Read_params[0]
FF_gain2_read = FF_Read_params[1]
FF_gain3_read = FF_Read_params[2]

FF_gain1_exp = 0 #FF_Read_params[0]  # Left Qubit
FF_gain2_exp = 0 #FF_Read_params[1]  # Middle Qubit
FF_gain3_exp = 500 #FF_Read_params[1]  # Right Qubit

UpdateConfig_FF_multiple = {
    "FF_list_readout": [(FF_channel1, FF_gain1_read),
    (FF_channel2, FF_gain2_read), (FF_channel3, FF_gain3_read)]
}
UpdateConfig_FF_pulse = {
    "FF_list_exp": [(FF_channel1, FF_gain1_exp),
    (FF_channel2, FF_gain2_exp), (FF_channel3, FF_gain3_exp)]
}
UpdateConfig_FF_multiple = UpdateConfig_FF_multiple | UpdateConfig_FF_pulse

cavityAtten.SetAttenuation(qubit_reading_from["cavity_atten"], printOut=False)

config["read_pulse_freq"] = qubit_reading_from["cavity_frequency"]
config["read_pulse_gain"] = qubit_reading_from["cavity_gain"]
config["readout_time"] = qubit_reading_from["readout_time"]
config["adc_trig_offset"] = qubit_reading_from["adc_offset"]
config["relax_delay"] = qubit_reading_from["relax_delay"]
config["read_length"] = qubit_reading_from["readout_time"]

config["qubit_freq"] = qubit_pi_pulsing["qubit_frequency"]
config["sigma"] = qubit_pi_pulsing["qubit_pulse_parameters"]["sigma"]
config["qubit_gain"] = qubit_pi_pulsing["qubit_pulse_parameters"]["pi_gain"]

shots = 1500
config["shots"] = shots

leftover_parameters = {
    "read_pulse_style": "const",
    "qubit_pulse_style": "arb",
    "ff_freq": 0,
    "ff_ch": 6,
    "ff_nqz": 1,
    "ff_pulse_style": "const",
}

config = BaseConfig | UpdateConfig_FF_multiple | leftover_parameters | config

leftover_parameters = {
        "read_pulse_style": "const",
        "qubit_pulse_style": "arb",
    }

config = BaseConfig | UpdateConfig_FF_multiple | leftover_parameters | config

expt_cfg={ "start":0.0, "step":0.0026 * 1.5, "expts":70,
       }
# expt_cfg={ "start":0.0, "step":0.0026, "expts":300,
#         "pi_gain": 7000, "relax_delay" : 300
#        }

config = config | expt_cfg
print(config)

iOscillations_SS = Oscillations_SS(path="QubitOscillations", cfg=config,soc=soc,soccfg=soccfg,outerFolder=outerFolder)
dOscillations_SS = Oscillations_SS.acquire(iOscillations_SS, threshold= threshold, angle=angle)
Oscillations_SS.display(iOscillations_SS, dOscillations_SS, plotDisp=True, figNum=2)
Oscillations_SS.save_data(iOscillations_SS, dOscillations_SS)


expt_cfg={ "start":0.0, "step":0.0026 * 2, "expts":50,
           "yokoStart": 0.001 - 0.015, "yokoStop": 0.001 + 0.015, "yokoNumPoints": 9
       }
# # expt_cfg={ "start":0.0, "step":0.0026, "expts":300,
# #         "pi_gain": 7000, "relax_delay" : 300
# #        }
#
config = config | expt_cfg
print(config)

# iOscillations_SS = Oscillations_SS_Yoko(path="QubitOscillations_SSYoko", cfg=config,soc=soc,soccfg=soccfg,
#                                         outerFolder=outerFolder, yoko = yoko74)
# dOscillations_SS = Oscillations_SS_Yoko.acquire(iOscillations_SS, threshold= threshold, angle=angle)
# Oscillations_SS_Yoko.save_data(iOscillations_SS, dOscillations_SS)




# Instance_SingleShotProgram = SingleShotProgramFF(path="dataSingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
# data_SingleShotProgram = SingleShotProgramFF.acquire(Instance_SingleShotProgram)
# # print(data_SingleShotProgram)
# SingleShotProgramFF.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)
#
# SingleShotProgramFF.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
# SingleShotProgramFF.save_config(Instance_SingleShotProgram)





#
#
#
#
# #########################################################
# FF_channel = 4 #4 is middle qubit, 6 is left qubit
# FF_gain = 0
#
# FF_channel1 = 6 #4 is middle qubit, 6 is left qubit
# FF_channel2 = 4 #4 is middle qubit, 6 is left qubit
#
# FF_Read_params = parameter["FF_gains"]
# FF_gain1_read = FF_Read_params[0]
# FF_gain2_read = FF_Read_params[1]
#
# FF_gain1_exp = -30000  #Left Qubit
# FF_gain2_exp = -30000  #Middle Qubit
#
# UpdateConfig_FF_multiple = {
#     "FF_list_readout": [(FF_channel1, FF_gain1_read),
#     (FF_channel2, FF_gain2_read)]
# }
# UpdateConfig_FF_pulse = {
#     "FF_list_exp": [(FF_channel1, FF_gain1_exp),
#     (FF_channel2, FF_gain2_exp)]
# }
# UpdateConfig_FF_multiple = UpdateConfig_FF_multiple | UpdateConfig_FF_pulse
#
#
# UpdateConfig_FF = {
#     "ff_pulse_style": "const", # --Fixed
#     "ff_additional_length": soc.us2cycles(1), # [Clock ticks]
#     "ff_gain": FF_gain, # [DAC units]
#     "ff_freq": 0, # [MHz] actual frequency is this number + "cavity_LO"
#     ##### define tranmission experiment parameters
#     "ff_nqz": 1, ### MHz, span will be center+/- this parameter
#     "relax_delay": 200, ### in units us
#     "ff_ch": FF_channel, #### cavity attenuator attenuation value
# }
#
# UpdateConfig = UpdateConfig_FF | UpdateConfig_FF_multiple
# config = BaseConfig | UpdateConfig ### note that UpdateConfig will overwrite elements in BaseConfig
# #### update the qubit and cavity attenuation
#
#
#
# qubit_reading_from = parameter["Left_Qubit"]
# config["pulse_freq"] = qubit_reading_from["cavity_frequency"]
#
# cavityAtten.SetAttenuation(qubit_reading_from["cavity_atten"], printOut=True)
# config["pulse_gain"] = qubit_reading_from["cavity_gain"]
# config["relax_decay"] = qubit_reading_from["relax_decay"]
# config["readout_time"] = qubit_reading_from["readout_time"]
# config["adc_offset"] = qubit_reading_from["adc_offset"]
#
#
# config["shots"] = 2000
# config["rounds"] = 1
#
# qubit_pi_pulse = parameter["Left_Qubit"]
# ARabi_config = {"sigma":qubit_pi_pulse["qubit_pulse_parameters"]["sigma"],"f_ge": qubit_pi_pulse["qubit_frequency"],}
#
# config = config | ARabi_config
# #Start cannot be shorter than like 20 ns!!!!
# expt_cfg={ "start":0.0, "step":0.0026, "expts":40,
#         "pi_gain": qubit_pi_pulse["qubit_pulse_parameters"]["pi_gain"]
#        }
# # expt_cfg={ "start":0.0, "step":0.0026, "expts":300,
# #         "pi_gain": 7000, "relax_delay" : 300
# #        }
#
# config = config | expt_cfg
# print(config)


# iOscillations = Oscillations(path="QubitOscillations", cfg=config,soc=soc,soccfg=soccfg,outerFolder=outerFolder)
# dOscillations = Oscillations.acquire(iOscillations)
# Oscillations.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
# Oscillations.save_data(iOscillations, dOscillations)
