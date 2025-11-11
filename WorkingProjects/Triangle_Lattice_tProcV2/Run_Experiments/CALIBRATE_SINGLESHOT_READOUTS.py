import matplotlib.pyplot as plt
import numpy as np

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import \
    SingleShotFFMUX


def characterize_readout(config, Qubit_Readout):
    '''Characterize qubits at the current readout point to return angle, threshold, and confusion_matrix for each.
    trans_config remains the same because we want to know the readout error under the MUXed pulse we will use.'''
    angle, threshold, confusion_matrix = [], [], []

    import copy

    new_config = config.copy()
    new_config["FF_Qubits"] = copy.deepcopy(new_config["FF_Qubits"])
    new_config["Shots"] = 4000
    # new_config["Shots"] = 1
    print(f"Running single shot with {new_config['Shots']} shots.")

    fidelity_matrix = np.zeros((len(Qubit_Readout), len(Qubit_Readout)))

    for ro_ind, Qubit in enumerate(Qubit_Readout):
        '''Pulse each at a time, using the QubitParameters Pulse parameters'''
        new_config["qubit_freqs"] = [Qubit_Parameters[str(Qubit)]['Qubit']['Frequency'] - BaseConfig['qubit_LO']]
        new_config["qubit_gains"] = [Qubit_Parameters[str(Qubit)]['Qubit']['Gain'] / 32766.]
        new_config['sigma']       =  Qubit_Parameters[str(Qubit)]['Qubit']['sigma']

        for Q, Gain in enumerate(Qubit_Parameters[str(Qubit)]['Pulse_FF']):
            new_config["FF_Qubits"][str(Q+1)]['Gain_Pulse'] = Gain

        SSExp = SingleShotFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=new_config, soc=soc, soccfg=soccfg)
        data = SSExp.acquire()
        # SSExp.display(data, plotDisp=True, block=False, display_indices=[Q])

        angle.append(data['data']['angle'][ro_ind])
        threshold.append(data['data']['threshold'][ro_ind])
        ng_contrast = data['data']['ng_contrast'][ro_ind]
        ne_contrast = data['data']['ne_contrast'][ro_ind]
        fidelity = -np.array(data['data']['ng_contrast']) - data['data']['ne_contrast'] + 1


        print(f"Qubit {Qubit} fidelity = {1-ng_contrast-ne_contrast:.3f};   ng={ng_contrast:.3f}, ne={ne_contrast:.3f}")
        print("All qubit fidelities:",  np.round(100*fidelity, 1))
        fidelity_matrix[ro_ind,:] = fidelity

        conf_mat = np.array([[1 - ng_contrast, ne_contrast],
                             [ng_contrast, 1 - ne_contrast]])
        confusion_matrix.append(conf_mat)

    fig, ax = plt.subplots()
    im = ax.imshow(fidelity_matrix, vmin=0, vmax=1, interpolation='none', origin='upper')
    for (j, i), label in np.ndenumerate(fidelity_matrix):
        ax.text(i, j, f"{np.round(label * 100, 1)}", ha='center', va='center',
                 color='white' if i != j else 'black')
    ax.set_xlabel('Readout Qubit')
    ax.set_ylabel('Pulse Qubit')
    fig.colorbar(im, label='Fidelity')
    ax.set_title('Readout Fidelity Crosstalk Matrix')

    tick_labels = list([f'Q{Q}' for Q in Qubit_Readout])

    # Set the colorbar tick locations and labels
    ax.set_xticks(range(len(Qubit_Readout)))
    ax.set_yticks(range(len(Qubit_Readout)))
    ax.set_xticklabels(tick_labels)
    ax.set_yticklabels(tick_labels)

    plt.show(block=False)
    plt.pause(0.01)

    return angle, threshold, confusion_matrix

angle, threshold, confusion_matrix = characterize_readout(config, Qubit_Readout)
config['angle'], config['threshold'] = angle, threshold
config['confusion_matrix'] = confusion_matrix
if 'confusion_matrix' in config:
    print("Correcting using CONFUSION MATRIX")