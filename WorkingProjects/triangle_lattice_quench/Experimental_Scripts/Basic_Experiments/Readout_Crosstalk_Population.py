import numpy as np
from qick.asm_v2 import QickSweep1D
from scipy.optimize import curve_fit

from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.AveragerProgramFF import FFAveragerProgramV2
import matplotlib.pyplot as plt
from WorkingProjects.triangle_lattice_quench.Experiment import ExperimentClass
import WorkingProjects.triangle_lattice_quench.Helpers.FF_utils as FF
from WorkingProjects.triangle_lattice_quench.Helpers.IQ_contrast import IQ_contrast, frequency_guess
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotProgram
from WorkingProjects.triangle_lattice_quench.Helpers.rotate_SS_data import correct_occ


class ReadoutCrosstalkPopulation(ExperimentClass):
    """
    Simple experiment that excites >= 1 qubit(s), then immediately measures the population
    all qubits (using calibrated angle and threshold).

    Uses the SingleShot Program, as it has the same logic.
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False):
        if "number_of_pulses" not in self.cfg.keys():
            self.cfg["number_of_pulses"] = 1
        self.cfg["Pulse"] = True

        prog = SingleShotProgram(self.soccfg, cfg=self.cfg, reps=self.cfg["Shots"], final_delay=self.cfg["relax_delay"], initial_delay=10.0)
        uncorrected_pops = prog.acquire_populations(soc=self.soc, load_envelopes=True, progress=False)

        data = {'config': self.cfg, 'data': {'population': uncorrected_pops}}

        if self.cfg.get('confusion_matrix') is not None:
            corrected_pops = np.zeros_like(uncorrected_pops)
            for ro_index in range(len(corrected_pops)):
                corrected_pops[ro_index] = correct_occ(uncorrected_pops[ro_index],
                                                   self.cfg['confusion_matrix'][ro_index])
            data['data']["population_corrected"] = corrected_pops


        self.data = data

        return self.data


    def display(self, data=None, **kwargs):
        if data is None:
            data = self.data
        data_dict = data['data']

        fig, ax = plt.subplots(1, 1, figsize=(7, 4), tight_layout=True)

        n = len(data_dict['population'])
        ax.bar(range(1, n + 1), data_dict['population'], ls='dashed', linewidth=1.5, edgecolor='black',
               color='none', label="Uncorrected", zorder=2)
        bars = ax.bar(range(1, n + 1), data_dict['population_corrected'],
                      color=plt.rcParams['axes.prop_cycle'].by_key()['color'],
                      label=f"Corrected, sum={sum(data_dict['population_corrected']):.2f}")
        ax.set_xticks(range(1, n + 1))
        ax.set_xlabel("Qubit")
        ax.set_ylabel(f"Occupation, pulsed {self.cfg['Qubit_Pulse']}")
        ax.set_xticklabels(data['config']['Qubit_Readout_List'], rotation=70, fontsize=15)
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                    f'{bar.get_height():.3f}', ha='center', va='bottom', fontsize=12)
        ax.legend()



        fig.suptitle(str(self.titlename), fontsize=16)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])