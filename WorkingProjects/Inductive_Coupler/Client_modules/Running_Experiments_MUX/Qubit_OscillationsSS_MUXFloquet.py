# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from q4diamond.Client_modules.Running_Experiments_MUX.MUXInitialize import *
from q4diamond.Client_modules.Experimental_Scripts_MUX.mSingleShotProgramFFMUX import SingleShotProgramFFMUX
from q4diamond.Client_modules.Experimental_Scripts_MUX.mRabiOscillations_SSMUX import WalkFFSSMUX
from q4diamond.Client_modules.Experimental_Scripts_MUX.mRabiOscillations_GainSweepSSMUX import Oscillations_Gain_SSMUX
from q4diamond.Client_modules.Experimental_Scripts_MUX.mRabiOscillations_SSMUXFloquet import WalkFFSSMUXFloquet
from q4diamond.Client_modules.Experimental_Scripts_MUX.mRabiOscillations_GainSweepSSMUXFloquet import Oscillations_Gain_SSMUXFloquet



print(soc)


yoko69.rampstep = 0.0005
yoko70.rampstep = 0.0005
yoko71.rampstep = 0.0005
yoko72.rampstep = 0.0005

# yoko69.SetVoltage(-0.0479)
# yoko70.SetVoltage(0.0904)
# yoko71.SetVoltage(-0.1262)
# yoko72.SetVoltage(0.0051)

yoko69.SetVoltage(0.1722)
yoko70.SetVoltage(0.1905)
yoko71.SetVoltage(-0.2115)
yoko72.SetVoltage(0.1263)

mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6962.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6800,
                      "FF_Gains": [-7000, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit01': {'Frequency': 4850, 'Gain': 800},
          'Qubit12': {'Frequency': 4531.2, 'Gain': 770 * 0},
          'Pulse_FF': [-5000, 0, 0, 0],
          'Floquet': {'Frequency': 50, 'Gain': 9600, 'Phase': 0}},
    '2': {'Readout': {'Frequency': 7033.8 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
                          "FF_Gains": [-7000, 5000, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit01':  {'Frequency': 5004.5, 'Gain': 1100},
          'Qubit12': {'Frequency': 4746, 'Gain': 750},
          'Pulse_FF': [-5000, 0, 0, 0],
          'Floquet': {'Frequency': 30, 'Gain': 16000, 'Phase': 0}},
    '3': {'Readout': {'Frequency': 7117.4 - mixer_freq - BaseConfig["cavity_LO"] / 1e6,
                      'Gain': 5000, "FF_Gains": [0, 13900, 17000, 0]},
          'Qubit01': {'Frequency': 4687.1, 'Gain': 1420},
          'Qubit12': {'Frequency': 4504.8, 'Gain': 1000 * 0},
          'Pulse_FF': [0, 7800, 9000, 0],
          'Floquet': {'Frequency': 0, 'Gain': 0, 'Phase': 0}},
    '4': {'Readout': {'Frequency': 7230.6 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5000, "FF_Gains": [0, 0, 0, -16000]},
          'Qubit01': {'Frequency': 4762.8, 'Gain': 1250},
          'Qubit12': {'Frequency': 4532.5, 'Gain': 700 * 0},
          'Pulse_FF':  [0, 0, 0, -13000],
          'Floquet': {'Frequency': 0, 'Gain': 0, 'Phase': 0}}
    }

Qubit_Readout = [1]
Qubit_Pulse = [1]
Floquet_Drive = [1]

FF_gain1_expt = 100  # 8000
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0

swept_qubit_index = 1 #1 indexed

Oscillation_Gain = False
oscillation_gain_dict = {'reps': 250, 'start': int(0 * 16 ), 'step': int(2 * 16), 'expts': 100, 'gainStart': -300,
                         'gainStop': 700, 'gainNumPoints': 11, 'relax_delay': 200}

Oscillation_Single = False
oscillation_single_dict = {'reps': 500, 'start': int(0), 'step': int(1 * 16), 'expts': 200, 'relax_delay': 200}

Oscillation_Single_Floquet = False
oscillation_single_dict_floquet = {'reps': 500, 'start': int(0), 'step': int(1 * 16), 'expts': 200, 'relax_delay': 200}

Oscillation_Gain_Floquet = True
oscillation_gain_dict_floquet = {'reps': 500, 'start': int(0 * 16), 'step': int(1 * 16), 'expts': 200, 'gainStart': 0,
                         'gainStop': 19000, 'gainNumPoints': 96, 'relax_delay': 200}

Floquet_Frequencies = np.zeros(len(Qubit_Parameters))
Floquet_Gains = np.zeros(len(Qubit_Parameters))
Floquet_Phases = np.zeros(len(Qubit_Parameters))

for F_D in Floquet_Drive:
    Floquet_Frequencies[F_D - 1] = Qubit_Parameters[str(F_D)]['Floquet']['Frequency']
    Floquet_Gains[F_D - 1] = Qubit_Parameters[str(F_D)]['Floquet']['Gain']
    Floquet_Phases[F_D - 1] = Qubit_Parameters[str(F_D)]['Floquet']['Phase']

SS_params_2States = {"ground": 0, 'excited': 1, "Shots": 4000, "Readout_Time": 3, "ADC_Offset": 0.5}

FF_gain1, FF_gain2, FF_gain3, FF_gain4 = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']["FF_Gains"]


# cavity_gain = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Gain']
# resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Frequency']
# qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
# qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']

resonator_frequencies = [Qubit_Parameters[str(Q_R)]['Readout']['Frequency'] for Q_R in Qubit_Readout]
gains = [Qubit_Parameters[str(Q_R)]['Readout']['Gain'] / 32000. * len(Qubit_Readout) for Q_R in Qubit_Readout]

qubit_gains = [Qubit_Parameters[str(Q)]['Qubit01']['Gain'] for Q in Qubit_Pulse]
qubit_frequency_centers = [Qubit_Parameters[str(Q)]['Qubit01']['Frequency'] for Q in Qubit_Pulse]
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse[0])]['Pulse_FF']

BaseConfig['ro_chs'] = [i for i in range(len(Qubit_Readout))]


FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1, 'Gain_Expt': FF_gain1_expt, 'Gain_Pulse': FF_gain1_pulse}
FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2, 'Gain_Expt': FF_gain2_expt, 'Gain_Pulse': FF_gain2_pulse}
FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3, 'Gain_Expt': FF_gain3_expt, 'Gain_Pulse': FF_gain3_pulse}
FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4, 'Gain_Expt': FF_gain4_expt, 'Gain_Pulse': FF_gain4_pulse}

# Configure for qubit experiment
UpdateConfig_qubit = {
    "qubit_pulse_style": "const",
    "qubit_gain": 1000,
    # "qubit_freq": qubit_frequency_center,
    "qubit_gains": qubit_gains,
    "f_ges": qubit_frequency_centers,
    "qubit_length": soc.us2cycles(40),
    ##### define spec slice experiment parameters
    "SpecSpan": 12,  ### MHz, span will be center+/- this parameter
    "SpecNumPoints": 60,  ### number of points in the transmission frequecny
}
UpdateConfig_FF = {
    "ff_pulse_style": "const",  # --Fixed
    "ff_freq": 0,  # [MHz] actual frequency is this number + "cavity_LO"
    ##### define tranmission experiment parameters
    "ff_nqz": 1,  ### MHz, span will be center+/- this parameter
    "relax_delay": 300,  ### in units us
}

UpdateConfig_transmission = {
    "reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
    "pulse_style": "const",  # --Fixed
    "readout_length": 2,  # [Clock ticks]
    # "pulse_gain": cavity_gain,  # [DAC units]
    # "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "pulse_gains": gains,  # [DAC units]
    "pulse_freqs": resonator_frequencies,
    ##### define tranmission experiment parameters
    "TransSpan": 1.5,  ### MHz, span will be center+/- this parameter
    "TransNumPoints": 60,  ### number of points in the transmission frequecny
}

UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit | UpdateConfig_FF
config = BaseConfig | UpdateConfig  ### note that UpdateConfig will overwrite elements in BaseConfig
config["FF_Qubits"] = FF_Qubits
config['Read_Indeces'] = Qubit_Readout


#### update the qubit and cavity attenuation

config["rounds"] = 1
config["sigma"] = 0.05

config["shots"] = 2000
config['qubit_gains'] = [Qubit_Parameters[str(Q)]['Qubit01']['Gain'] for Q in Qubit_Readout]
config['f_ges'] = [Qubit_Parameters[str(Q)]['Qubit01']['Frequency'] for Q in Qubit_Readout]
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Readout[0])]['Pulse_FF']
config["FF_Qubits"]['1']['Gain_Pulse'] = FF_gain1_pulse
config["FF_Qubits"]['2']['Gain_Pulse'] = FF_gain2_pulse
config["FF_Qubits"]['3']['Gain_Pulse'] = FF_gain3_pulse
config["FF_Qubits"]['4']['Gain_Pulse'] = FF_gain4_pulse

config["readout_length"] = SS_params_2States["Readout_Time"]  # us (length of the pulse applied)
config["adc_trig_offset"] = SS_params_2States["ADC_Offset"]
print(config["pulse_freqs"])
Instance_SingleShotProgram = SingleShotProgramFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=config,
                                                         soc=soc, soccfg=soccfg)
# data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
data_SingleShotProgram = Instance_SingleShotProgram.acquire()

angle, threshold = Instance_SingleShotProgram.angle, Instance_SingleShotProgram.threshold
print(Instance_SingleShotProgram.angle,Instance_SingleShotProgram.threshold)

# data_SingleShotProgram = SingleShotProgramFFMUX.analyze(Instance_SingleShotProgram, data_SingleShotProgram)

SingleShotProgramFFMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)
SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)


config['qubit_gains'] = [Qubit_Parameters[str(Q)]['Qubit01']['Gain'] for Q in Qubit_Pulse]
config['f_ges'] = [Qubit_Parameters[str(Q)]['Qubit01']['Frequency'] for Q in Qubit_Pulse]
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse[0])]['Pulse_FF']
config["FF_Qubits"]['1']['Gain_Pulse'] = FF_gain1_pulse
config["FF_Qubits"]['2']['Gain_Pulse'] = FF_gain2_pulse
config["FF_Qubits"]['3']['Gain_Pulse'] = FF_gain3_pulse
config["FF_Qubits"]['4']['Gain_Pulse'] = FF_gain4_pulse

if Oscillation_Gain:
    config["reps"] = oscillation_gain_dict['reps']
    expt_cfg = {"start": oscillation_gain_dict['start'], "step": oscillation_gain_dict['step'],
                "expts": oscillation_gain_dict['expts'],
                "gainStart": oscillation_gain_dict['gainStart'],
                "gainStop": oscillation_gain_dict['gainStop'], "gainNumPoints": oscillation_gain_dict['gainNumPoints'],
                "qubitIndex": swept_qubit_index, "relax_delay": oscillation_gain_dict['relax_delay'],
                "Swept_Coupler_Parameters": Qubit_Parameters[str(swept_qubit_index)]['Floquet']
                }
    config['IDataArray'] = [1, None, None, None]
    config = config | expt_cfg
    print(config["FF_Qubits"])


    iOscillations = Oscillations_Gain_SSMUX(path="QubitOscillations_GainSweepMUX", cfg=config, soc=soc, soccfg=soccfg,
                                      outerFolder=outerFolder)
    dOscillations = Oscillations_Gain_SSMUX.acquire(iOscillations, angle=angle, threshold= threshold)
    Oscillations_Gain_SSMUX.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
    Oscillations_Gain_SSMUX.save_data(iOscillations, dOscillations)


if Oscillation_Single:
    config["reps"] = oscillation_single_dict['reps']
    expt_cfg = {"start": oscillation_single_dict['start'], "step": oscillation_single_dict['step'],
                "expts": oscillation_single_dict['expts'], "relax_delay": oscillation_single_dict['relax_delay']}
    # config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
    # config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
    # config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency']
    # config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Gain']

    config['qubit_gains'] = [Qubit_Parameters[str(Q)]['Qubit01']['Gain'] for Q in Qubit_Pulse]
    config['f_ges'] = [Qubit_Parameters[str(Q)]['Qubit01']['Frequency'] for Q in Qubit_Pulse]

    print(config["FF_Qubits"])

    config["FF_Qubits"]['1']['Gain_Expt'] = FF_gain1_expt
    config["FF_Qubits"]['2']['Gain_Expt'] = FF_gain2_expt
    config["FF_Qubits"]['3']['Gain_Expt'] = FF_gain3_expt
    config["FF_Qubits"]['4']['Gain_Expt'] = FF_gain4_expt
    #
    config = config | expt_cfg
    config['IDataArray'] = [1, None, None, None]

    iOscillations = WalkFFSSMUX(path="QubitOscillationsMUX", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dOscillations = WalkFFSSMUX.acquire(iOscillations, angle=angle, threshold= threshold)
    WalkFFSSMUX.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
    WalkFFSSMUX.save_data(iOscillations, dOscillations)

if Oscillation_Single_Floquet:
    config["reps"] = oscillation_single_dict_floquet['reps']
    expt_cfg = {"start": oscillation_single_dict_floquet['start'], "step": oscillation_single_dict_floquet['step'],
                "expts": oscillation_single_dict_floquet['expts'], "relax_delay": oscillation_single_dict_floquet['relax_delay']}
    config_floquet = {'Floquet_Frequencies': Floquet_Frequencies, 'Floquet_Gains': Floquet_Gains,
                      'Floquet_Phases': Floquet_Phases, 'Floquet_Drive': Floquet_Drive}


    # config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
    # config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
    # config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency']
    # config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Gain']

    config['qubit_gains'] = [Qubit_Parameters[str(Q)]['Qubit01']['Gain'] for Q in Qubit_Pulse]
    config['f_ges'] = [Qubit_Parameters[str(Q)]['Qubit01']['Frequency'] for Q in Qubit_Pulse]

    print(config["FF_Qubits"])

    config["FF_Qubits"]['1']['Gain_Expt'] = FF_gain1_expt
    config["FF_Qubits"]['2']['Gain_Expt'] = FF_gain2_expt
    config["FF_Qubits"]['3']['Gain_Expt'] = FF_gain3_expt
    config["FF_Qubits"]['4']['Gain_Expt'] = FF_gain4_expt
    #
    config = config | expt_cfg | config_floquet
    config['IDataArray'] = [1, None, None, None]

    iOscillations = WalkFFSSMUXFloquet(path="QubitOscillationsMUX", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dOscillations = WalkFFSSMUXFloquet.acquire(iOscillations, angle=angle, threshold= threshold)
    WalkFFSSMUXFloquet.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
    WalkFFSSMUXFloquet.save_data(iOscillations, dOscillations)

if Oscillation_Gain_Floquet:
    config["reps"] = oscillation_gain_dict_floquet['reps']
    expt_cfg = {"start": oscillation_gain_dict_floquet['start'], "step": oscillation_gain_dict_floquet['step'],
                "expts": oscillation_gain_dict_floquet['expts'],
                "gainStart": oscillation_gain_dict_floquet['gainStart'],
                "gainStop": oscillation_gain_dict_floquet['gainStop'], "gainNumPoints": oscillation_gain_dict_floquet['gainNumPoints'],
                "qubitIndex": swept_qubit_index, "relax_delay": oscillation_gain_dict_floquet['relax_delay'],
                "Swept_Coupler_Parameters": Qubit_Parameters[str(swept_qubit_index)]['Floquet']
                }
    config_floquet = {'Floquet_Frequencies': Floquet_Frequencies, 'Floquet_Gains': Floquet_Gains,
                      'Floquet_Phases': Floquet_Phases, 'Floquet_Drive': Floquet_Drive}
    config['IDataArray'] = [1, None, None, None]
    config = config | expt_cfg | config_floquet

    iOscillations = Oscillations_Gain_SSMUXFloquet(path="QubitOscillations_GainSweepMUX", cfg=config, soc=soc, soccfg=soccfg,
                                      outerFolder=outerFolder)
    dOscillations = Oscillations_Gain_SSMUXFloquet.acquire(iOscillations, angle=angle, threshold= threshold)
    Oscillations_Gain_SSMUXFloquet.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
    Oscillations_Gain_SSMUXFloquet.save_data(iOscillations, dOscillations)