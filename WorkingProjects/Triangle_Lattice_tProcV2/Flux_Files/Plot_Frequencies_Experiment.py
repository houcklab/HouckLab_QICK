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
        label_offset = 0.0

        # plot and label
        for qi in range(Q):
            plt.plot(xs, freqs[:, qi], '-o', label=f'Q{qi + 1}')
            for s in range(S):
                plt.annotate(f'Q{qi + 1}', (xs[s], freqs[s, qi] + label_offset), fontsize=8,
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
                plt.scatter([pt[0]], [pt[1]], marker='^', s=80, zorder=5)

        plt.xticks(xs)
        plt.xlabel('experimental section index')
        plt.ylabel('Frequency (MHz)')
        plt.legend()
        plt.tight_layout()
        plt.show()
        plt.pause(0.1)

    def save_data(self, data: Dict[str, Any]) -> None:
        pass


def main():
    """
    Run the calculation in the same style as the original file,
    but via the Experiment API.
    """

    intermediate_jump_gains = [-13449, None, 8706, None, -5250, None, 19650, None]
    for i in range(len(intermediate_jump_gains)):
        if intermediate_jump_gains[i] is None:
            intermediate_jump_gains[i] = BS_FF[i]

    # gains = [pulse_4815, Ramp_FF, intermediate_jump_gains, BS_FF, Readout_FF]
    gains = [Readout_1254_FF, Init_FF, Ramp_FF, BS_FF, Readout_1254_FF]
    gains = [Readout_1254_FF, Init_FF, Ramp_FF, BS_FF, Readout_1234_FF]

    config = {
        'gains': gains,
    }

    expt = PlotFrequenciesExperiment(path='', prefix='PlotFrequencies', soc=None, soccfg=None, cfg=config)
    expt.acquire()


if __name__ == '__main__':
    main()
