import os
import json
from typing import Any, Dict, List, Tuple, Optional

import numpy as np
import matplotlib.pyplot as plt

from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass

from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Device_calibration import full_device_calib
from Import_Functions_Transmon import *
from Initialize_Qubit_Information import flux_sign, model_mapping
from Whole_system_to_Voltages import flux_vector, dressed_qubit_freqs, coupler_freqs, beta_matrix


class CalculateFFExperiment(ExperimentClass):
    """Wraps Calculate_FF script into an Experiment-style class.

    This class ignores soc / soccfg and only uses cfg, so it can be invoked uniformly
    with the rest of your experiment suite (e.g., .acquire() and .display()).
    """

    # Default values,
    config_template = {
        "frequencies": {
            'Q1': 0,
            'Q2': 0,
            'Q3': 0,
            'Q4': 0,
            'Q5': 0,
            'Q6': 0,
            'Q7': 0,
            'Q8': 0,
        }
    }

    def __init__(self, *args, **kwargs):
        # No soc/soccfg required; just pass through to keep API consistent
        self.outerFolder = ""
        super().__init__(*args, **kwargs)
        self.cfg = self.cfg or {}
        self.cfg.setdefault('plot_effective_system', True)
        self.cfg.setdefault('suffix', 'BS')

    def acquire(self) -> Dict[str, Any]:
        """Compute target fluxes, gains, and dressed frequencies; optionally plot.

        Returns a data dict suitable for save/display.
        """
        cfg = self.cfg
        plot_effective_system = bool(cfg.get('plot_effective_system', True))
        suffix = str(cfg.get('suffix', 'BS'))
        frequencies = cfg.get('frequencies', self.config_template["frequencies"])

        try:
            flux_was_given = {key: (freq < 10) for key, freq in frequencies.items()}
            target_fluxes = np.copy(flux_vector)

            mappings = ['Q1_bare', 'Q2_bare', 'Q3_bare', 'Q4_bare', 'Q5_bare', 'Q6_bare', 'Q7_bare', 'Q8_bare']
            for index, key in enumerate(['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7', 'Q8']):
                if frequencies.get(key) is not None:
                    if flux_was_given[key]:  # flux given
                        target_fluxes[index] = frequencies[key]

                    elif not type(frequencies[key]) is str:  # dressed_freq -> bare_freq -> flux
                        dressed_freq = frequencies[key]
                        adjacent_couplers = np.nonzero(beta_matrix[index, 8:])[0] + 0
                        bare_freq = full_device_calib.get_bare_freq(dressed_freq,
                                                                    [coupler_freqs[c] for c in adjacent_couplers],
                                                                    betas=[beta_matrix[index, c + 8] for c in
                                                                           adjacent_couplers])
                        flux = flux_sign[mappings[index]] * model_mapping[mappings[index]].flux(bare_freq / 1e3)

                        target_fluxes[index] = flux

            ##!!! models such as Q1_bare have the flux_quanta in FF gain (~100,000) stored in flux_quantum_voltage !!!
            # TODO: find a better place to store this info... - Joshua 7/25/25
            FF_flux_quanta = np.array([model_mapping[bare_mapping].flux_quantum_voltage for bare_mapping in mappings])

            flux_changes = np.asarray(target_fluxes) - np.asarray(flux_vector)
            flux_changes = flux_changes[:8]

            gains_list = flux_changes * FF_flux_quanta

            gains_list = np.rint(gains_list).astype(int)


            bare_order_of_items = ['Q1_bare', 'Q2_bare', 'Q3_bare', 'Q4_bare', 'Q5_bare', 'Q6_bare', 'Q7_bare', 'Q8_bare',
                                   'C1', 'C2', 'C3', 'C4', 'C5', 'C6']
            bare_frequencies = [1000 * model_mapping[mapping].freq(flux) for mapping, flux in
                                zip(bare_order_of_items, target_fluxes)]

            dressed_freqs, g_matrix = full_device_calib.dress_system(bare_frequencies, beta_matrix=beta_matrix,
                                                                     plot=False)
        except Exception as e:
            raise RuntimeError(f"Calculations failed: {e}")


        # Printing Summary
        np.set_printoptions(linewidth=100000)
        print('[' + ', '.join(str(g) for g in gains_list) + ']')
        print('# (' + ', '.join(f"{d:.1f}" for d in dressed_freqs) + ')')
        for j, gain, freq in zip(range(1, 1 + len(gains_list)), gains_list, dressed_freqs):
            print(f"FF_gain{j}_{suffix} = {gain:>6}  # {freq:.1f}")

        # Return a tidy record for saving / plotting
        data = {
            'target_fluxes': np.asarray(target_fluxes, dtype=float),
            'gains_list': np.asarray(gains_list, dtype=int),
            'bare_order': bare_order_of_items,
            'bare_frequencies': np.asarray(bare_frequencies, dtype=float),
            'dressed_freqs': np.asarray(dressed_freqs, dtype=float),
            'g_matrix': np.asarray(g_matrix),
            'suffix': suffix,
        }

        # Plotting if specified
        if plot_effective_system:
            self.display(data)

        return data

    def display(self, data: Dict[str, Any], **kwargs) -> None:
        """
        `dress_system(..., plot=True)` already plotted, we simply call plt.show().
        """
        if not data:
            data = self.data

        print("Plotting FF")

        dressed_freqs = data['dressed_freqs']
        g_matrix = data['g_matrix']
        full_device_calib.plot_dressed_system(dressed_freqs, g_matrix)
        plt.show()
        plt.pause(0.1)

    def save_data(self, data: Dict[str, Any]) -> None:
        pass


def main():

    # Frequencies
    frequencies = {
        'Q1': 3700,
        'Q2': 4350,
        'Q3': -0.5,
        'Q4': -0.5,
        'Q5': -0.5,
        'Q6': 4250,
        'Q7': 4250,
        'Q8': -0.5,
    }

    cfg = {
        'plot_effective_system': True,
        'suffix': 'BS',
        'frequencies': frequencies,
    }

    expt = CalculateFFExperiment(path='', prefix='CalculateFF', soc=None, soccfg=None, cfg=cfg)
    expt.acquire() # Display determined by config field "plot_effective_system", can also call display manually

if __name__ == '__main__':
    main()




##############################################################################
###################### Non Experiment Version (Old) ##########################
##############################################################################

# import numpy as np
# from matplotlib import pyplot as plt
#
# from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Device_calibration import full_device_calib
# from Import_Functions_Transmon import *
# from Initialize_Qubit_Information import flux_sign, model_mapping
#
#
#
#
# from Whole_system_to_Voltages import flux_vector, dressed_qubit_freqs, coupler_freqs, beta_matrix
#
# plot_effective_system = True
# suffix = "BS"
# # (4100.0, 4419.1, 3600.0, 3900.0, 4250.0, 4250.0, 4250.0, 4250.0)
#
# # (4050.0, 3750.0, 4350.0, 3950.0, 3650.0, 4250.0, 4150.0, 3550.0)
# # (3600.0, 3600.0, 4000.0, 4400.0, 4400.0, 3700.0, 3700.0, 4300.0)
# # (3900.0, 3527.2, 4300.0, 4000.0, 3700.0, 4392.0, 4100.0, 3522.7)
# # 7584
# # (4000.0, 4000.0, 4000.0, 3700.0, 3700.0, 4000.0, 4300.0, 4300.0)
# # (3535.3, 4100.0, 4389.6, 3640.0, 3900.0, 4390.0, 3460.3, 4000.0)
#
# frequencies = {
#     'Q1': 3700,
#     'Q2': 3600,
#     'Q3': 4000,
#     'Q4': 4320,
#     'Q5': 3600,
#     'Q6': 3750,
#     'Q7': 3900,
#     'Q8': 4100,
# }
#
#
#
#
# flux_was_given = {key: (freq < 10) for key,freq in frequencies.items()}
#
# target_fluxes = np.copy(flux_vector)
#
#
# mappings = ['Q1_bare', 'Q2_bare', 'Q3_bare', 'Q4_bare', 'Q5_bare', 'Q6_bare', 'Q7_bare', 'Q8_bare']
# for index, key in enumerate(['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7', 'Q8']):
#     if frequencies.get(key) is not None:
#         if flux_was_given[key]: # flux given
#             target_fluxes[index] = frequencies[key]
#
#         elif not type(frequencies[key]) is str : # dressed_freq -> bare_freq -> flux
#             dressed_freq = frequencies[key]
#             adjacent_couplers = np.nonzero(beta_matrix[index, 8:])[0] + 0
#             bare_freq = full_device_calib.get_bare_freq(dressed_freq, [coupler_freqs[c] for c in adjacent_couplers], betas= [beta_matrix[index, c+8] for c in adjacent_couplers])
#             flux = flux_sign[mappings[index]]*model_mapping[mappings[index]].flux(bare_freq / 1e3)
#
#             target_fluxes[index] = flux
#
# ##!!! models such as Q1_bare have the flux_quanta in FF gain (~100,000) stored in flux_quantum_voltage !!!
# # TODO: find a better place to store this info... - Joshua 7/25/25
# FF_flux_quanta = np.array([model_mapping[bare_mapping].flux_quantum_voltage for bare_mapping in mappings])
#
# flux_changes = np.asarray(target_fluxes) - np.asarray(flux_vector)
# flux_changes = flux_changes[:8]
#
# gains_list = flux_changes * FF_flux_quanta
#
# gains_list = np.rint(gains_list).astype(int)
#
# np.set_printoptions(linewidth=100000)
# print('['+', '.join(str(g) for g in gains_list)+']')
#
#
# bare_order_of_items = ['Q1_bare', 'Q2_bare', 'Q3_bare', 'Q4_bare', 'Q5_bare', 'Q6_bare', 'Q7_bare', 'Q8_bare',
#                    'C1', 'C2', 'C3', 'C4', 'C5', 'C6']
# bare_frequencies = [1000*model_mapping[mapping].freq(flux) for mapping,flux in zip(bare_order_of_items, target_fluxes)]
#
# dressed_freqs, g_matrix = full_device_calib.dress_system(bare_frequencies, beta_matrix=beta_matrix, plot=plot_effective_system)
# print('# ('+', '.join(f'{d:.1f}' for d in dressed_freqs)+')')
# for j, gain, freq in zip(range(1, 1+len(gains_list)), gains_list, dressed_freqs):
#     print(f"FF_gain{j}_{suffix} = {gain:>6}  # {freq:.1f}")
#
#
#
# plt.show()