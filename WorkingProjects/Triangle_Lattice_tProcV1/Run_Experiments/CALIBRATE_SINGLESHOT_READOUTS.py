def characterize_readout(config, Qubit_Readout):
    '''Characterize qubits at the current readout point to return angle, threshold, and confusion_matrix for each.
    trans_config remains the same because we want to know the readout error under the MUXed pulse we will use.'''
    angle, threshold, confusion_matrix = [], [], []

    import copy

    new_config = config.copy()
    new_config["FF_Qubits"] = copy.deepcopy(new_config["FF_Qubits"])
    new_config["Shots"] = 3000

    for ro_ind, Qubit in enumerate(Qubit_Readout):
        '''Pulse each at a time, using the QubitParameters Pulse parameters'''
        new_config["qubit_freqs"] = [Qubit_Parameters[str(Qubit)]['Qubit']['Frequency']]
        new_config["qubit_gains"] = [Qubit_Parameters[str(Qubit)]['Qubit']['Gain']]
        new_config['sigma']       =  Qubit_Parameters[str(Qubit)]['Qubit']['sigma']

        FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit)]['Pulse_FF']
        new_config["FF_Qubits"]['1']['Gain_Pulse'] = FF_gain1_pulse
        new_config["FF_Qubits"]['2']['Gain_Pulse'] = FF_gain2_pulse
        new_config["FF_Qubits"]['3']['Gain_Pulse'] = FF_gain3_pulse
        new_config["FF_Qubits"]['4']['Gain_Pulse'] = FF_gain4_pulse

        SSExp = SingleShotFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=new_config, soc=soc, soccfg=soccfg)
        data = SSExp.acquire_display_save(plotDisp=True, block=False, display_indices=[Qubit])

        angle.append(    data['data']['angle'][ro_ind])
        threshold.append(data['data']['threshold'][ro_ind])
        ng_contrast = data['data']['ng_contrast'][ro_ind]
        ne_contrast = data['data']['ne_contrast'][ro_ind]
        conf_mat = np.array([[1 - ng_contrast, ne_contrast],
                             [ng_contrast, 1 - ne_contrast]])
        confusion_matrix.append(conf_mat)

    return angle, threshold, confusion_matrix

angle, threshold, confusion_matrix = characterize_readout(config, Qubit_Readout)
config['angle'], config['threshold'] = angle, threshold
config['confusion_matrix'] = confusion_matrix
if 'confusion_matrix' in config:
    print("Correcting using CONFUSION MATRIX")