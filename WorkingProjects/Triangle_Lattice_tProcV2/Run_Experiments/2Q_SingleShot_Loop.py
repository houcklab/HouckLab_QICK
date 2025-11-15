'''File to automatically calibrate and run 2Q single shot experiments on arbitrary qubit pairs.'''

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import \
    SingleShotFFMUX, SingleShot_2QFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mOptimizeReadoutandPulse_FFMUX import \
    ReadOpt_wSingleShotFFMUX, QubitPulseOpt_wSingleShotFFMUX
import itertools

from qubit_parameter_files.Qubit_Parameters_Master import *

Adjacency = {
    1: [2,3],
    2: [1,3,4],
    3: [1,2,4,5],
    4: [2,3,5,6],
    5: [3,4,6,7],
    6: [4,5,7,8],
    7: [5,6,8],
    8: [6,7],
}
def are_adjacent(qpair):
    return qpair[1] in Adjacency[qpair[0]]

skip_uncoupled_qubits = False
# List of lists: every combination of 2 qubits in each sublist will be checked
for Q_list in [[5,7]]:
    for Qpair in itertools.combinations(Q_list, 2):
        if skip_uncoupled_qubits and not are_adjacent(Qpair):
            continue

        Qubit_Readout = Qpair
        Qubit_Pulse = Qpair

        Optimize_11 = False

        OptReadout_index = 1
        OptQubit_index = 1

        SS_2Q_params = {"Shots": 2000, 'number_of_pulses': 1, 'relax_delay': 200,
                        'second_qubit_freq': 3966.8, 'second_qubit_gain': 5749}

        SS_Q_params = {"Shots": 500, 'relax_delay': 150,
                       "q_gain_span": 2 * 1000, "q_gain_pts": 2 + 5,
                       "q_freq_span": 2 * 3, "q_freq_pts": 7,
                       'number_of_pulses': 1,
                       'readout_index': OptReadout_index,
                       'qubit_sweep_index': OptQubit_index}

        exec(open("UPDATE_CONFIG.py").read())

        # Optimize second qubit pulse to account for ZZ frequency shift
        if Optimize_11:
            fig, ax = plt.subplots()
            data = QubitPulseOpt_wSingleShotFFMUX(path="SingleShot_OptQubit", outerFolder=outerFolder,
                                                  cfg=config | SS_Q_params, soc=soc,
                                                  soccfg=soccfg).acquire_save(plotDisp=True, ax=ax)
            fid_mat, trans_fpts, gain_pts = (data['data'][key] for key in ('fid_mat', 'qubit_fpts', 'gain_pts'))
            ind = np.unravel_index(np.argmax(fid_mat, axis=None), fid_mat.shape)

            sweep_index = SS_Q_params['qubit_sweep_index']
            config["qubit_gains"][sweep_index] = gain_pts[ind[0]] / 32766.
            config["qubit_freqs"][sweep_index] = trans_fpts[ind[1]]

            best_gain = int(round(gain_pts[ind[0]]))
            best_freq = trans_fpts[ind[1]]
            ax.text(best_freq, best_gain, f"({best_freq:.2f}, {best_gain})", zorder=3, ha='center', va='center',
                    color='black')
            fig.canvas.draw()
            fig.canvas.flush_events()

            print("Qubit gain found at: ", config["qubit_gains"][sweep_index] * 32766)
            print("Qubit frequency found at: ", config["qubit_freqs"][sweep_index])

            SS_2Q_params = SS_2Q_params | {'second_qubit_freq': best_freq, 'second_qubit_gain': best_gain}

        # Run 2 qubit single shot
        SingleShot_2QFFMUX(path="SingleShot_2Qubit", outerFolder=outerFolder,
                               cfg=config | SS_2Q_params, soc=soc, soccfg=soccfg).acquire_save_display(plotDisp=True, block=False)

plt.show()