# Translation of Qubit_Parameters dict to resonator and qubit parameters.
# Nothing defined here should be changed in an Experiment unless it is one of the swept variables.
# Update FF_Qubits dict
FF_gain1_ro, FF_gain2_ro, FF_gain3_ro, FF_gain4_ro = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['FF_Gains'] / 32766
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse[0])]['Pulse_FF']

FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1_ro, 'Gain_Expt': FF_gain1_expt, 'Gain_Pulse': FF_gain1_pulse, 'Gain_Init':FF_gain1_init}
FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2_ro, 'Gain_Expt': FF_gain2_expt, 'Gain_Pulse': FF_gain2_pulse, 'Gain_Init':FF_gain2_init}
FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3_ro, 'Gain_Expt': FF_gain3_expt, 'Gain_Pulse': FF_gain3_pulse, 'Gain_Init':FF_gain3_init}
FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4_ro, 'Gain_Expt': FF_gain4_expt, 'Gain_Pulse': FF_gain4_pulse, 'Gain_Init':FF_gain4_init}

trans_config = {
    "res_gains": [Qubit_Parameters[str(Q_R)]['Readout']['Gain'] / 32000. * len(Qubit_Readout) for Q_R in Qubit_Readout],  # [DAC units]
    "res_freqs": [Qubit_Parameters[str(Q_R)]['Readout']['Frequency'] - BaseConfig["res_LO"] for Q_R in Qubit_Readout], # [MHz] actual frequency is this number + "cavity_LO"
    # "res_gain": Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Gain'],  # [DAC units]
    "readout_length":Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Readout_Time']
}
qubit_config = {
    "qubit_freqs": [Qubit_Parameters[str(Q)]['Qubit']['Frequency'] for Q in Qubit_Pulse],
    "qubit_gains": [Qubit_Parameters[str(Q)]['Qubit']['Gain'] for Q in Qubit_Pulse],
    "sigma" : Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['sigma']
}
config = BaseConfig | trans_config | qubit_config
config["FF_Qubits"] = FF_Qubits
config["Qubit_Readout_List"] = Qubit_Readout
config['ro_chs'] = [i for i in range(len(Qubit_Readout))]

# This ends the translation of the Qubit_Parameters dict