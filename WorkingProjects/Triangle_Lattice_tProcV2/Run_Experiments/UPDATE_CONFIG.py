# Translation of Qubit_Parameters dict to resonator and qubit parameters.
# Nothing defined here should be changed in an Experiment unless it is one of the swept variables.
# Update FF_Qubits dict
FFReadouts = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['FF_Gains']
FFPulse = Qubit_Parameters[str(Qubit_Pulse[0])]['Pulse_FF']
FFExpt = [FF_gain1_expt, FF_gain2_expt, FF_gain3_expt, FF_gain4_expt, FF_gain5_expt, FF_gain6_expt, FF_gain7_expt, FF_gain8_expt]
FF_BS = [FF_gain1_BS, FF_gain2_BS, FF_gain3_BS, FF_gain4_BS, FF_gain5_BS, FF_gain6_BS, FF_gain7_BS, FF_gain8_BS]



for Qubit, FFR, FFE, FFP, FFBS in zip(('1','2','3','4','5','6','7','8'), FFReadouts, FFExpt, FFPulse, FF_BS):
    FF_Qubits[Qubit] |= {'Gain_Readout': FFR, 'Gain_Expt': FFE, 'Gain_Pulse': FFP, 'Gain_BS': FFBS}
try:
    if Init_FF is not None:
        for Qubit, FFI in zip(('1', '2', '3', '4', '5', '6', '7', '8'), Init_FF):
            FF_Qubits[Qubit]['ramp_initial_gain'] = FFI
        print('using init FFs')
except:
    pass

del Qubit

trans_config = {
    "res_gains": [Qubit_Parameters[str(Q_R)]['Readout']['Gain'] / 32766. * len(Qubit_Readout) for Q_R in Qubit_Readout],  # [DAC units]
    "res_freqs": [Qubit_Parameters[str(Q_R)]['Readout']['Frequency'] for Q_R in Qubit_Readout], # [MHz] actual frequency is this number + "cavity_LO"
    "readout_lengths":[Qubit_Parameters[str(Q_R)]['Readout']['Readout_Time'] for Q_R in Qubit_Readout],
    "adc_trig_delays": [Qubit_Parameters[str(Q_R)]['Readout']['ADC_Offset'] for Q_R in Qubit_Readout],
}
qubit_config = {
    "qubit_freqs": [Qubit_Parameters[str(Q)]['Qubit']['Frequency'] - BaseConfig['qubit_LO'] for Q in Qubit_Pulse],
    "qubit_gains": [Qubit_Parameters[str(Q)]['Qubit']['Gain'] / 32766. for Q in Qubit_Pulse],
    "sigma" : Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['sigma']
}
config = BaseConfig | trans_config | qubit_config
config["FF_Qubits"] = FF_Qubits
config["Qubit_Readout_List"] = Qubit_Readout
config['ro_chs'] = [i for i in range(len(Qubit_Readout))]

# This ends the translation of the Qubit_Parameters dict