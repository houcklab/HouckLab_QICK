import numpy as np
import matplotlib.pyplot as plt
from typing import Any, Dict, List

from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass

from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.Qubit_Parameters_Master import *
from Initialize_Qubit_Information import model_mapping
from Whole_system_to_Voltages import flux_vector, beta_matrix
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Device_calibration import full_device_calib


class PlotFrequenciesExperiment(ExperimentClass):
    """
    Run the original 'FF gains → dressed frequencies across sections' calculation
    as a drop-in experiment (no soc/soccfg needed).
    """

    # Default values,
    config_template = {
        "gains": []
    }

    # Hardcoded
    coupled_pairs = [
        # top rail
        (1, 3), (3, 5), (5, 7),
        # bottom rail
        (2, 4), (4, 6), (6, 8),
        # diagonals (up-right)
        (2, 3), (4, 5), (6, 7),
        # diagonals (down-right)
        (1, 4), (3, 6), (5, 8),
        # Added for testing intersection
        # (1,5),
    ]

    def __init__(self, *args, **kwargs):
        # No soc/soccfg required; just pass through to keep API consistent
        self.outerFolder = ""
        super().__init__(*args, **kwargs)
        self.cfg = self.cfg or {}
        self.cfg.setdefault('plot', True)  # Plot by default
        self.data = None

    @staticmethod
    def ff_gains_to_freqs(ff_gains):
        mappings = ['Q1_bare', 'Q2_bare', 'Q3_bare', 'Q4_bare', 'Q5_bare', 'Q6_bare', 'Q7_bare', 'Q8_bare']
        FF_flux_quanta = np.array([model_mapping[bare_mapping].flux_quantum_voltage for bare_mapping in mappings])

        flux_changes = np.asarray(ff_gains) / FF_flux_quanta

        target_fluxes = flux_vector + np.concatenate([flux_changes, np.zeros(6)])

        bare_order_of_items = ['Q1_bare', 'Q2_bare', 'Q3_bare', 'Q4_bare', 'Q5_bare', 'Q6_bare', 'Q7_bare', 'Q8_bare',
                               'C1', 'C2', 'C3', 'C4', 'C5', 'C6']
        bare_frequencies = [1000 * model_mapping[mapping].freq(flux) for mapping, flux in
                            zip(bare_order_of_items, target_fluxes)]

        dressed_freqs, g_matrix = full_device_calib.dress_system(bare_frequencies, beta_matrix=beta_matrix, plot=False)

        return dressed_freqs

    def acquire(self) -> Dict[str, Any]:
        """
        Not much here most done in main section below.
        """
        cfg = self.cfg
        gains = cfg["gains"]

        freqs = np.array([PlotFrequenciesExperiment.ff_gains_to_freqs(arr) for arr in tuple(gains)])


        # Printing out frequencies
        for i in range(freqs.shape[0]):
            print(list(int(x) for x in freqs[i, :]))

        data = {
            'gains': gains,
            'freqs': freqs,
        }
        self.data = data

        if cfg.get('plot', True):
            self.display(data)

        return data

    def display(self, data: Dict[str, Any] = None, **kwargs) -> None:
        """
        Plot frequency trajectory per qubit across sections.
        """
        if data is None:
            data = self.data
        if not data:
            return

        freqs = data['freqs']
        num_sections, num_qubits = freqs.shape

        for qi in range(num_qubits):
            plt.plot(freqs[:, qi], '-o', label=f'Q{qi+1}')

        plt.xlabel('experimental section index')
        plt.ylabel('Frequency (MHz)')
        plt.legend()
        plt.show()
        plt.pause(0.1)

    def _segment_intersection(self, p1, p2, p3, p4):
        x1, y1 = p1;
        x2, y2 = p2
        x3, y3 = p3;
        x4, y4 = p4
        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(denom) < 1e-12:
            return None
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
        u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / denom
        if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
            xi = x1 + t * (x2 - x1)
            yi = y1 + t * (y2 - y1)
            return (xi, yi)
        return None

    def display(self, data: Dict[str, Any] = None, **kwargs) -> None:
        """
        Plot frequency trajectory per qubit across sections.
        """
        if data is None:
            data = self.data
        if not data:
            return

        freqs = data['freqs']
        S, Q = freqs.shape
        xs = np.arange(S, dtype=float)

        coupled_pairs = self.coupled_pairs

        # plot and label
        for qi in range(Q):
            plt.plot(xs, freqs[:, qi], '-o', label=f'Q{qi + 1}')
            for s in [0, S-1]: # Only label first and last or else they overlap
                label_offset = -0.13 if s == 0 else 0.13
                plt.annotate(f'Q{qi + 1}', (xs[s] + label_offset, freqs[s, qi] - 10), fontsize=8,
                             ha='center', va='bottom')

        # crossings on last ramp
        k_end = S - 1
        k0 = max(0, k_end - 1)
        for (a1, a2) in coupled_pairs:
            i = a1 - 1;
            j = a2 - 1
            if i < 0 or i >= Q or j < 0 or j >= Q:
                continue
            p1 = (xs[k0], freqs[k0, i]);
            p2 = (xs[k_end], freqs[k_end, i])
            p3 = (xs[k0], freqs[k0, j]);
            p4 = (xs[k_end], freqs[k_end, j])
            pt = self._segment_intersection(p1, p2, p3, p4)
            if pt is not None:
                plt.scatter([pt[0]], [pt[1]], marker='^', s=100, color='red', zorder=5)
                plt.text(pt[0]+0.009, pt[1]-5, '!', color='white', fontsize=10,
                         ha='center', va='center', fontweight='bold', zorder=6)

        plt.xticks(xs)
        # print(self.cfg['labels'])
        if 'labels' in self.cfg:
            plt.xticks(xs, self.cfg['labels'])
        plt.xlabel('experimental section index')
        plt.ylabel('Frequency (MHz)')
        plt.legend()
        plt.tight_layout()
        plt.show()
        plt.pause(0.1)

    def save_data(self, data: Dict[str, Any]) -> None:
        pass


def main():

    # Setting gains

    # single jump
    intermediate_jump_gains = Qubit_Parameters[ijump_point]['IJ']['gains']
    # 1234 BOI
    # intermediate_jump_gains = [-14300, None, 4490, None, -20347, None, -2370, None]
    # 2345 BOI
    # intermediate_jump_gains = [None, -2040, None, -13730, None, -7300, None, None]

    for i in range(len(intermediate_jump_gains)):
        if intermediate_jump_gains[i] is None:
            intermediate_jump_gains[i] = BS_FF[i]

    readout_gains = readout_params['1']['Readout']['FF_Gains']

    # gains = [Readout_1234_FF, Init_FF, Ramp_FF, BS_FF, readout_gains]
    gains = [readout_gains, Init_FF, Ramp_FF, intermediate_jump_gains, BS_FF, readout_gains]
    labels = ['RO', 'Init', 'Expt', 'Double', 'BS', 'RO']

    config = {'gains': gains, 'labels':labels, 'plot': True}
    expt = PlotFrequenciesExperiment(path='', prefix='PlotFrequencies', soc=None, soccfg=None, cfg=config)
    expt.acquire() # Also performs plotting if "plot" True


if __name__ == '__main__':
    main()




##############################################################################
###################### Non Experiment Version (Old) ##########################
##############################################################################

# import matplotlib.pyplot as plt
# import numpy as np
#
#
# # import qubit parameters from this file
# from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.Qubit_Parameters_Master import *
#
# from Initialize_Qubit_Information import model_mapping
# from Whole_system_to_Voltages import flux_vector, beta_matrix
# from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Device_calibration import full_device_calib
#
# def ff_gains_to_freqs(ff_gains):
#     mappings = ['Q1_bare', 'Q2_bare', 'Q3_bare', 'Q4_bare', 'Q5_bare', 'Q6_bare', 'Q7_bare', 'Q8_bare']
#     FF_flux_quanta = np.array([model_mapping[bare_mapping].flux_quantum_voltage for bare_mapping in mappings])
#
#     flux_changes = np.asarray(ff_gains) / FF_flux_quanta
#
#     target_fluxes = flux_vector + np.concatenate([flux_changes, np.zeros(6)])
#
#     bare_order_of_items = ['Q1_bare', 'Q2_bare', 'Q3_bare', 'Q4_bare', 'Q5_bare', 'Q6_bare', 'Q7_bare', 'Q8_bare',
#                        'C1', 'C2', 'C3', 'C4', 'C5', 'C6']
#     bare_frequencies = [1000*model_mapping[mapping].freq(flux) for mapping,flux in zip(bare_order_of_items, target_fluxes)]
#
#     dressed_freqs, g_matrix = full_device_calib.dress_system(bare_frequencies, beta_matrix=beta_matrix, plot=False)
#
#     return dressed_freqs
#
# readout_gains = readout_params['1']['Readout']['FF_Gains']
#
# intermediate_jump_gains = [-13804, None, -497, None, -17936, None, -2498, None]
# for i in range(len(intermediate_jump_gains)):
#     if intermediate_jump_gains[i] is None:
#         intermediate_jump_gains[i] = BS_FF[i]
#
# # gains = [Pulse_4815_FF, Init_FF, Ramp_FF, BS_FF, Readout_1234_FF]
# gains = [readout_gains, Init_FF, Ramp_FF, BS_FF, readout_gains]
# gains = [Readout_1234_FF, Init_FF, Ramp_FF, BS_FF, readout_gains]
# gains = [Readout_1234_FF, Init_FF, Ramp_FF, intermediate_jump_gains, BS_FF, readout_gains]
#
#
# freqs = np.array([ff_gains_to_freqs(arr) for arr in tuple(gains)])
#
# for i in range(len(gains)):
#     print(list([int(x) for x in freqs[i,:]]))
#
# # gains = np.array([pulse_145, Readout_FF4])
# for i in range(freqs.shape[1]):
#     plt.plot(freqs[:,i], '-o', label=f'Q{i+1}')
# plt.xlabel('experimental section index')
# plt.ylabel('Frequency (MHz)')
# plt.legend()
# plt.show()


