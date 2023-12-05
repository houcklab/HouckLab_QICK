# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from q4diamond.Client_modules.initialize import *

from q4diamond.Client_modules.Running_Experiments.Calibrated_parameters import *
from q4diamond.Client_modules.Experiment_Scripts.mSingleShotProgramFF import SingleShotProgramFF
from q4diamond.Client_modules.Experiment_Scripts.mDiabaticFFSweep import DiabaticSweepGain

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


parameter = parameter_dia

Read_Qubit = "Left_Qubit"
Pi_Pulse = "Left_Qubit"
Read_Qubit = "Middle_Qubit"
Pi_Pulse = "Middle_Qubit"

FF_Read_params = parameter["FF_gains"]
FF_gain1_Q1_PiPulse = 15000
FF_gain2_Q1_PiPulse = -30000
FF_gain3_Q1_PiPulse = 0

FF_gain1_Q2_DuringRamp = 15000
FF_gain2_Q2_DuringRamp = -7000
FF_gain3_Q2_DuringRamp = 0

FF_gain1_Q1_RampUp = 15000
FF_gain2_Q1_RampUp = -7000
FF_gain3_Q1_RampUp = 0

FF_gain1_Q2_Readout = FF_Read_params[0]
FF_gain2_Q2_Readout = FF_Read_params[1]
FF_gain3_Q2_Readout = FF_Read_params[2]


shots = 8000

yoko_values = parameter["yoko_values"]
yoko72.SetVoltage(yoko_values[0])
yoko74.SetVoltage(yoko_values[1])
yoko76.SetVoltage(yoko_values[2])

FF_channel1 = 6 #6 is left, 4 is middle, 5 is right
FF_channel2 = 4 #4 is middle qubit, 6 is left qubit
FF_channel3 = 5 #4 is middle qubit, 6 is left qubit,

qubit_reading_from = parameter[Read_Qubit]
qubit_pi_pulsing = parameter[Pi_Pulse]

threshold, angle = threshold_calibration(Read_Qubit)
threshold = threshold

print("threshold: ", threshold)
print("Angle: ", angle)

config = {}

# qubit_pi_pulsing = parameter["Pi_pulse_Left_Qubit"]
# qubit_pi_pulsing = parameter[Pi_Pulse]


UpdateConfig_FF_Q1_Pi = {
    "FF_list_Q1_Pi": [(FF_channel1, FF_gain1_Q1_PiPulse),
    (FF_channel2, FF_gain2_Q1_PiPulse), (FF_channel3, FF_gain3_Q1_PiPulse)]
}
UpdateConfig_FF_Q2Sweep = {
    "FF_list_Q2_Sweep": [[FF_channel1, FF_gain1_Q2_DuringRamp],
    [FF_channel2, FF_gain2_Q2_DuringRamp], (FF_channel3, FF_gain3_Q2_DuringRamp)]
}
UpdateConfig_FF_Q1Sweep = {
    "FF_list_Q1_Sweep": [[FF_channel1, FF_gain1_Q1_RampUp],
    [FF_channel2, FF_gain2_Q1_RampUp], (FF_channel3, FF_gain1_Q1_RampUp)]
}
UpdateConfig_FF_Readout = {
    "FF_list_readout": [(FF_channel1, FF_gain1_Q2_Readout),
    (FF_channel2, FF_gain2_Q2_Readout), (FF_channel3, FF_gain3_Q2_Readout)]
}
UpdateConfig_FF_multiple = UpdateConfig_FF_Readout | UpdateConfig_FF_Q1_Pi | UpdateConfig_FF_Q2Sweep | UpdateConfig_FF_Q1Sweep

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

config = config
print(config)

# idiab = DiabaticSweep(path="DiabaticSweep", cfg=config,soc=soc,soccfg=soccfg,outerFolder=outerFolder)
# ddiab = DiabaticSweep.acquire(idiab, threshold= threshold, angle=angle)
# DiabaticSweep.display(idiab, ddiab, plotDisp=True, figNum=2)
# DiabaticSweep.save_data(idiab, ddiab)


exp_config = {'start': -20000, 'step': 150, 'expts': 200}
config = config | exp_config

idiab = DiabaticSweepGain(path="DiabaticSweepGain", cfg=config,soc=soc,soccfg=soccfg,outerFolder=outerFolder)
ddiab = DiabaticSweepGain.acquire(idiab, threshold= threshold, angle=angle)
DiabaticSweepGain.display(idiab, ddiab, plotDisp=True, figNum=2)
DiabaticSweepGain.save_data(idiab, ddiab)