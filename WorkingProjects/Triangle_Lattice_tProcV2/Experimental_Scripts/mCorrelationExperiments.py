import time


import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.RampHelpers as RampHelpers

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Program_Templates.ThreePartProgram import ThreePartProgramOneFF
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Compensated_Pulse_Josh import *
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotProgram
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampCurrentCalibration_SSMUX import RampCurrentCalibration1D
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mSingleQubitOscillations import QubitOscillations


### Simple Singleshot experiment, but uses a separately calibrated angle and threshold to pick 0 or 1
class PopulationShots(ExperimentClass):
    def acquire(self, progress=False, plotDisp=True, plotSave=True, figNum=1):

        readout_list = self.cfg["Qubit_Readout_List"]

        self.cfg['number_of_pulses'] = self.cfg.get('number_of_pulses', 1)
        self.cfg['Pulse'] = self.cfg.get('Pulse', True)

        num_shots = self.cfg['reps'] * self.cfg.get('rounds', 1)

        Z_mat = [np.full(num_shots, np.nan) for _ in readout_list]

        # raw i and q data
        self.I_mat = [np.full(num_shots, np.nan) for _ in readout_list]
        self.Q_mat = [np.full(num_shots, np.nan) for _ in readout_list]


        self.data = {
            'config': self.cfg,
            'data': {'population_shots': Z_mat,
                     "I": self.I_mat,
                     "Q": self.Q_mat,
                     'readout_list': readout_list,
                     'angle': self.cfg['angle'],
                     'threshold': self.cfg['threshold'],
                     'confusion_matrix': self.cfg['confusion_matrix'],
                     'Qubit_Readout_List': self.cfg["Qubit_Readout_List"]},

        }

        self.last_saved_time = time.time()

        '''iterating through itertools.product is equivalent to a nested for loop such as
        for i, y_pt in enumerate(self.y_points):
            for j, x_pt in enumerate(self.x_points):'''

        prog = SingleShotProgram(self.soccfg, cfg=self.cfg, reps=self.cfg["reps"],
                                final_delay=self.cfg["relax_delay"], initial_delay=10.0)

        excited_populations, (self.I_mat, self.Q_mat) = prog.acquire_population_shots(soc=self.soc, return_shots=True,
                                                            load_pulses=True,
                                                            progress=progress)

        excited_populations = np.array(excited_populations)

        for ro_index in range(len(readout_list)):
            Z_mat[ro_index] = excited_populations[ro_index]

        counts = generate_counts(excited_populations, num_qubits=len(readout_list))
        self.data['data']['counts'] = counts

        self.save_data(data=self.data)
        return self.data

    def display(self, data=None, **kwargs):

        if data is None:
            data = self.data

        counts = data['data']['counts']

        display_counts(counts, self.titlename, num_qubits=len(self.cfg["Qubit_Readout_List"]))


        # also display points on IQ plane

        angle = self.cfg['angle']
        threshold = self.cfg['threshold']


        new_I = self.I_mat * np.cos(angle) - self.Q_mat * np.sin(angle)
        new_Q = self.I_mat * np.sin(angle) + self.Q_mat * np.cos(angle)

        plt.scatter(new_I, new_Q, s=2, alpha=0.5)

        plt.axvline(threshold, linestyle='--', color='black', label=f'Threshold: {threshold}')

        plt.xlabel('I (a.u.)')
        plt.ylabel('Q (a.u.)')
        plt.axis('equal')

        plt.title(self.titlename)

        plt.show()

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

### Ramp Correlation
class RampPopulationShots(ExperimentClass):

    def acquire(self, progress=False, plotDisp=True, plotSave=True, figNum=1):

        self.cfg["IDataArray"] = [None]*len(self.cfg['FF_Qubits'])

        '''Create the Ramp '''
        ramp_delay_time = self.cfg.get('ramp_wait_timesteps', 0)
        double_ramp = self.cfg.get('double', False)
        for i in range(len(self.cfg['IDataArray'])):
            Q = str(i+1)
            ramp_on = RampHelpers.generate_cubic_ramp(
                initial_gain=self.cfg['FF_Qubits'][Q]['Gain_Pulse'],
                final_gain=self.cfg['FF_Qubits'][Q]['Gain_Expt'],
                ramp_duration=self.cfg['ramp_duration'])
            ramp_delay = np.full(ramp_delay_time, self.cfg['FF_Qubits'][Q]['Gain_Expt'])
            ramp_off = np.array([]) if not double_ramp else np.flip(ramp_on)

            self.cfg["IDataArray"][i] = np.concatenate([ramp_on, ramp_delay, ramp_off])

        self.cfg['expt_samples'] = len(self.cfg["IDataArray"][0])


        readout_list = self.cfg["Qubit_Readout_List"]

        num_shots = self.cfg['reps'] * self.cfg.get('rounds', 1)

        Z_mat = [np.full(num_shots, np.nan) for _ in readout_list]

        # raw i and q data
        I_mat = [np.full(num_shots, np.nan) for _ in readout_list]
        Q_mat = [np.full(num_shots, np.nan) for _ in readout_list]

        self.data = {
            'config': self.cfg,
            'data': {'population_shots': Z_mat,
                     "I": I_mat,
                     "Q": Q_mat,
                     'readout_list': readout_list,
                     'angle': self.cfg['angle'],
                     'threshold': self.cfg['threshold'],
                     'confusion_matrix': self.cfg['confusion_matrix'],
                     'Qubit_Readout_List': self.cfg["Qubit_Readout_List"]}
        }

        self.last_saved_time = time.time()

        prog = ThreePartProgramOneFF(self.soccfg, cfg=self.cfg, reps=self.cfg["reps"],
                                final_delay=self.cfg["relax_delay"], initial_delay=10.0)

        excited_populations = prog.acquire_population_shots(soc=self.soc, return_shots=False,
                                                            load_pulses=True,
                                                            soft_avgs=self.cfg.get('rounds', 1),
                                                            progress=progress)

        for ro_index in range(len(readout_list)):
            Z_mat[ro_index] = excited_populations[ro_index]


        counts = generate_counts(excited_populations)
        self.data['data']['counts'] = counts

        self.save_data(data=self.data)
        return self.data

    def display(self, data=None, **kwargs):

        if data is None:
            data = self.data

        counts = data['data']['counts']

        display_counts(counts, self.titlename)





    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])



# Qubit oscillation over time, but measure shots
class OscillationPopulationShots(QubitOscillations):
    def init_sweep_vars(self):
        super().init_sweep_vars()
        # change acquire type to population shots
        self.z_value = 'population_shots' # contrast or population

    def acquire(self, progress=False, plotDisp=False, plotSave=False, figNum=0):
        if plotDisp or plotSave:
            print(f'Warning: display not implemented for this experiment.')
        self.data = super().acquire(progress=progress, plotDisp=False, plotSave=False, figNum=0)

        population_shots = np.array(self.data['data']['population_shots'])

        num_qubits = population_shots.shape[0]


        counts = np.zeros((2**num_qubits, population_shots.shape[1]))

        # iterate over time axis
        for i in range(population_shots.shape[1]):
            counts[:,i] = generate_counts(population_shots[:,i,:])

        self.data['data']['counts'] = counts
        return self.data

# Adiabatic ramp to prepare initial state then oscillations
class RampOscillationPopulationShots(RampCurrentCalibration1D):
    def init_sweep_vars(self):
        super().init_sweep_vars()
        # change acquire type to population shots
        self.z_value = 'population_shots' # contrast or population

    def acquire(self, progress=False, plotDisp=False, plotSave=False, figNum=0):
        if plotDisp or plotSave:
            print(f'Warning: display not implemented for this experiment.')
        self.data = super().acquire(progress=progress, plotDisp=False, plotSave=False, figNum=0)

        population_shots = np.array(self.data['data']['population_shots'])

        num_qubits = population_shots.shape[0]


        counts = np.zeros((2**num_qubits, population_shots.shape[1]))

        # iterate over time axis
        for i in range(population_shots.shape[1]):
            counts[:,i] = generate_counts(population_shots[:,i,:])

        self.data['data']['counts'] = counts
        return self.data


#### Correlation Experiment helper functions

def generate_counts(populations, num_qubits=2):

    print(f'generating_counts for populations with shape: {populations.shape}')

    # if num_qubits != 2:
    #     raise ValueError('unimplemented for num qubits other than 2')

    if num_qubits == 1:
        counts = np.zeros(2)
        num_ones = np.sum(populations)
        counts[0] = populations.shape[-1] - num_ones
        counts[1] = num_ones

    else:
        bit_values = 0
        for i in range(num_qubits):
            bit_values = populations[i, :] * 2**(num_qubits - 1 - i)

            # conventional order is 00, 01, 10, 11 where the ith bit is readout_list[i]
            # Count occurrences of each bitstring from 0 to 3 (00 to 11)
            counts = np.bincount(bit_values, minlength=4)

    if num_qubits == 2:

        # calculate counts
        # Convert bitstrings to integers
        bit_values = populations[0, :] * 2 + populations[1, :]

        # conventional order is 00, 01, 10, 11 where the ith bit is readout_list[i]
        # Count occurrences of each bitstring from 0 to 3 (00 to 11)
        counts = np.bincount(bit_values, minlength=4)

    return counts

def display_counts(counts, title, num_qubits=2):

    if num_qubits == 2:
        bitstrings = ['00', '01', '10', '11']
    elif num_qubits == 1:
        bitstrings = ['0', '1']

    fig, ax = plt.subplots()
    # Plotting
    ax.bar(bitstrings, counts/np.sum(counts))
    ax.set_xlabel('Bitstring')
    ax.set_ylabel('Normalized Counts')
    ax.set_title(title)
    ax.grid(axis='y', linestyle='--', alpha=0.7)
    plt.yticks(np.arange(0, 1.1, 0.1))
    plt.ylim(0,1)
    plt.show()

def display_counts_sweep(counts, title):
    pass


