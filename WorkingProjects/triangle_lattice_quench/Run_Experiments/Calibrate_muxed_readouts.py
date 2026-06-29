import matplotlib.pyplot as plt
import numpy as np

from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import \
    SingleShotProgram
from WorkingProjects.triangle_lattice_quench.Helpers.hist_analysis import hist_process

from WorkingProjects.triangle_lattice_quench.MUXInitialize import outerFolder
from WorkingProjects.triangle_lattice_quench.build_config import build_config

def characterize_readout(Qubit_Readout, soc, soccfg, Readout_Point=None, shots=4000):
    '''Characterize qubits at the current readout point to return angle, threshold, and confusion_matrix for each.
    The |g> cloud is the same for every drive (no pulse), so acquire it once
    and reuse — cuts total acquisitions from 2N to N+1.'''

    angle, threshold, confusion_matrix = [], [], []
    print(f"Running single shot with {shots} shots.")

    fidelity_matrix = np.zeros((len(Qubit_Readout), len(Qubit_Readout)))

    # ---- One shared |g> acquisition ----
    cfg_g = build_config(
        Qubit_Readout=Qubit_Readout,
        Qubit_Pulse=[Qubit_Readout[0]],  # any one; Pulse=False suppresses firing
        Readout_Point=Readout_Point,
    )
    cfg_g['Shots'] = shots
    cfg_g['Pulse'] = False
    cfg_g['number_of_pulses'] = 1
    prog_g = SingleShotProgram(soccfg, cfg=cfg_g, reps=shots,
                               final_delay=cfg_g['relax_delay'], initial_delay=10.0)
    shots_ig, shots_qg = prog_g.acquire_shots(soc, load_envelopes=True, progress=False)

    # ---- Per-drive |e> acquisition; reuse shared |g> for hist_process. ----
    for ro_ind, Qubit in enumerate(Qubit_Readout):
        cfg_e = build_config(
            Qubit_Readout=Qubit_Readout,
            Qubit_Pulse=[Qubit],
            Readout_Point=Readout_Point,
        )
        cfg_e['Shots'] = shots
        cfg_e['Pulse'] = True
        cfg_e['number_of_pulses'] = 1
        prog_e = SingleShotProgram(soccfg, cfg=cfg_e, reps=shots,
                                   final_delay=cfg_e['relax_delay'], initial_delay=10.0)
        shots_ie, shots_qe = prog_e.acquire_shots(soc, load_envelopes=True, progress=False)

        # Crosstalk fidelity row + target's angle/threshold via hist_process.
        for j in range(len(Qubit_Readout)):
            fid_j, threshold_j, angle_j, ne_j, ng_j = hist_process(
                data=[shots_ig[j], shots_qg[j], shots_ie[j], shots_qe[j]],
                plot=False, ran=None, return_errors=True, print_fidelities=False,
            )
            fidelity_matrix[ro_ind, j] = fid_j
            if j == ro_ind:
                angle.append(angle_j)
                threshold.append(threshold_j)
                confusion_matrix.append(np.array([[1 - ng_j, ne_j],
                                                  [ng_j,   1 - ne_j]]))
                print(f"Qubit {Qubit} fidelity = {fid_j:.3f};   "
                      f"ng={ng_j:.3f}, ne={ne_j:.3f}")
        print("All qubit fidelities:", np.round(100 * fidelity_matrix[ro_ind], 1))

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

    return {'angle': angle, 'threshold':threshold, 'confusion_matrix': confusion_matrix}