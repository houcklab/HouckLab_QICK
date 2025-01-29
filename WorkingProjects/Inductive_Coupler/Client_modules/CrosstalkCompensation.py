import csv
import os
from itertools import product
import numpy as np
import pulp

from WorkingProjects.Inductive_Coupler.Client_modules.Helpers.Qblox_Functions import Qblox


class CrosstalkCompensationOptimization:

    def __init__(self, crosstalk_matrix, crosstalk_inverse_matrix, crosstalk_offset_vector, voltage_threshold=8, single_channel_threshold=4):

        self.crosstalk_matrix = crosstalk_matrix
        self.crosstalk_inverse_matrix = crosstalk_inverse_matrix
        self.crosstalk_offset_vector = crosstalk_offset_vector

        self.voltage_threshold = voltage_threshold
        self.single_channel_threshold = single_channel_threshold

        self.qblox = Qblox()

    def brute_force_get_flux_offset(self, initial_fluxes, flux_ranges=None):

        if flux_ranges is None:
            flux_ranges = [3, 2, 1, 3, 4, 4, 2, 1]

        # up to +/- flux_range for each channel
        minimum_voltage_norm = np.inf
        minimum_voltage_combination = None

        for combination in product(*[range(-flux_range, flux_range + 1) for flux_range in flux_ranges]):
            fluxes = np.array(initial_fluxes) + np.array(combination)

            voltages = self.flux_to_voltage(fluxes)

            voltage_norm = np.linalg.norm(voltages, ord=1)

            if voltage_norm < minimum_voltage_norm:
                minimum_voltage_norm = voltage_norm
                minimum_voltage_combination = combination

        return np.array(minimum_voltage_combination)

    def brute_force_threshold_get_flux_offset(self, initial_fluxes, flux_ranges=None, threshold=None):

        if flux_ranges is None:
            flux_ranges = [3, 2, 1, 3, 4, 4, 2, 1]

        if threshold is None:
            threshold = 8

        # up to +/- flux_range for each channel
        for combination in product(*[range(-flux_range, flux_range + 1) for flux_range in flux_ranges]):
            fluxes = np.array(initial_fluxes) + np.array(combination)

            voltages = self.flux_to_voltage(fluxes)

            voltage_norm = np.linalg.norm(voltages, ord=1)

            if voltage_norm < threshold and all(np.abs(voltages < self.single_channel_threshold)):
                return np.array(combination)

        print(f'combination below threshold not found')
        return None

    def brute_force(self, initial_fluxes, flux_ranges=None):
        brute_force_fluxes = initial_fluxes + self.brute_force_get_flux_offset(initial_fluxes, flux_ranges=flux_ranges)
        return self.flux_to_voltage(brute_force_fluxes)
        
    def brute_force_threshold(self, initial_fluxes, flux_ranges=None, threshold=None):

        combination = self.__brute_force_threshold_get_combination(initial_fluxes, flux_ranges=flux_ranges,
                                                                   threshold=threshold)

        if combination is not None:
            fluxes = np.array(initial_fluxes) + np.array(combination)
            voltages = self.flux_to_voltage(fluxes)

            return voltages
        else:
            return None

    def integer_programming_get_combination(self, initial_fluxes, single_channel_threshold=4):
        # Create the problem instance
        problem = pulp.LpProblem('Minimize_L1_Norm', pulp.LpMinimize)

        # Define decision variables (integer adjustments)
        d_vars = [pulp.LpVariable(f"d_{i}", lowBound=-3, upBound=3, cat='Integer') for i in range(len(initial_fluxes))]

        # Calculate the voltage vector after transformation
        voltage_vector = self.flux_to_voltage(initial_fluxes + np.array(d_vars))

        # Define auxiliary variables for absolute values
        abs_vars = [pulp.LpVariable(f"abs_{i}", lowBound=0) for i in range(len(voltage_vector))]

        # Add constraints to ensure abs_vars[i] >= voltage_vector[i] and abs_vars[i] >= -voltage_vector[i]
        for i in range(len(voltage_vector)):
            problem += abs_vars[i] >= voltage_vector[i]
            problem += abs_vars[i] >= -voltage_vector[i]
            # Add constraints to ensure abs_vars[i] <= single_channel_threshold
            problem += abs_vars[i] <= single_channel_threshold

        # Objective function: Minimize the sum of absolute values (L1 norm)
        l1_norm = pulp.lpSum(abs_vars)
        problem += l1_norm

        # Solve the problem
        problem.solve()

        # Extract the optimal adjustments
        optimal_adjustments = [pulp.value(d_var) for d_var in d_vars]

        return np.array(optimal_adjustments)

    def flux_to_voltage(self, fluxes):
        fluxes = np.copy(np.array(fluxes))
        return np.dot(self.crosstalk_inverse_matrix, fluxes + self.crosstalk_offset_vector)

    def set_voltage_from_flux(self, channel, flux):

        # print(f'set voltage got flux: {flux}')

        if isinstance(channel, int):
            channel = [channel]
        elif not isinstance(channel, (list, np.ndarray)):
            raise ValueError(f'channel must be passed as int or list of ints. Given: {type(channel)}')

        if isinstance(flux, (int, float)):
            flux = [flux]*len(channel)
        elif not isinstance(flux, (list, np.ndarray)):
            raise ValueError(f'flux must be passed as float or list of floats. Given: {type(flux)}')

        voltage = self.flux_to_voltage(flux)

        voltage_norm = np.linalg.norm(voltage, ord=1)

        if voltage_norm > self.voltage_threshold:
            print(f'Voltages are too high: norm = {voltage_norm}')
            print(f'Voltages: {voltage}')
            self.ramp_to_zero(channel)
            return False
        else:
            print(f'Setting voltages to {voltage} on channels {channel}')
            print(f'voltage norm is {round(voltage_norm, 3)}')

            self.qblox.set_voltage(channel, voltage)

            return True

    def get_dir(self):
        return self.crosstalk_matrix_directory

    def ramp_to_zero(channels, self):
        zero_voltage = [0]*len(channels)
        self.qblox.set_voltage(channels, zero_voltage)

class CrosstalkCompensationSweep:

    def __init__(self, crosstalk_matrix_directory, channels, initial_fluxes, voltage_threshold=8):

        self.channels = channels
        self.initial_fluxes = initial_fluxes
        self.voltage_threshold = voltage_threshold

        self.crosstalk_matrix_directory = crosstalk_matrix_directory
        crosstalk_matrix_filename = os.path.join(crosstalk_matrix_directory, 'crosstalk_matrix.csv')
        crosstalk_inverse_matrix_filename = os.path.join(crosstalk_matrix_directory, 'crosstalk_inverse_matrix.csv')
        crosstalk_offset_vector_filename = os.path.join(crosstalk_matrix_directory, 'crosstalk_offset_vector.csv')

        crosstalk_matrix = []
        crosstalk_inverse_matrix = []
        crosstalk_offset_vector = []

        with open(crosstalk_matrix_filename, newline='') as csvfile:
            reader = csv.reader(csvfile, delimiter=',', quotechar='|')
            for row in reader:
                crosstalk_matrix.append(np.array(row).astype(float))

        with open(crosstalk_inverse_matrix_filename, newline='') as csvfile:
            reader = csv.reader(csvfile, delimiter=',', quotechar='|')
            for row in reader:
                crosstalk_inverse_matrix.append(np.array(row).astype(float))

        with open(crosstalk_offset_vector_filename, newline='') as csvfile:
            reader = csv.reader(csvfile, delimiter=',', quotechar='|')
            for row in reader:
                crosstalk_offset_vector.append(float(row[0]))

        self.crosstalk_matrix = np.array(crosstalk_matrix)
        self.crosstalk_inverse_matrix = np.array(crosstalk_inverse_matrix)
        self.crosstalk_offset_vector = np.array(crosstalk_offset_vector)

        self.optimized_offset_fluxes = [0]*len(self.initial_fluxes)

        self.crosstalk_compensation_optimization = CrosstalkCompensationOptimization(self.crosstalk_matrix, self.crosstalk_inverse_matrix, self.crosstalk_offset_vector, voltage_threshold=self.voltage_threshold)

        self.sweep_running = False

    def start_sweep(self, channel_to_sweep, flux_sweep_points):

        self.channel_to_sweep = channel_to_sweep
        self.flux_sweep_points = flux_sweep_points
        self.sweep_index = 0
        self.sweep_running = True


        ### optimized with brute force method to start

        print(f'initial fluxes: {self.initial_fluxes}')

        self.optimized_offset_fluxes = self.crosstalk_compensation_optimization.brute_force_get_flux_offset(self.initial_fluxes)

        print(f'found brute offset fluxes: {self.optimized_offset_fluxes}')

        self.optimized_fluxes = self.initial_fluxes + self.optimized_offset_fluxes

        self.crosstalk_compensation_optimization.set_voltage_from_flux(self.channels, self.optimized_fluxes)

    def set_next_point_threshold_method(self):

        print(f'sweep index: {self.sweep_index}')
        if not self.sweep_running:
            raise RuntimeError('Need to start sweep before setting next point')

        fluxes = np.copy(self.initial_fluxes)

        fluxes[self.channel_to_sweep] = self.flux_sweep_points[self.sweep_index]

        self.optimized_fluxes = fluxes + self.optimized_offset_fluxes

        print(f'optimized combination: {self.optimized_offset_fluxes}')
        print(f'targeting flux: {self.optimized_fluxes}')

        voltages = self.crosstalk_compensation_optimization.flux_to_voltage(self.optimized_fluxes)
        print(f'voltages: {voltages}')
        voltage_norm = np.linalg.norm(voltages, ord=1)
        print(f'norm is {np.round(voltage_norm, 3)}')

        if voltage_norm > self.voltage_threshold:
            # re-optimize
            print(f'need to optimize')
            threshold_offset_fluxes = self.crosstalk_compensation_optimization.brute_force_threshold_get_flux_offset(fluxes + self.optimized_offset_fluxes,
                                                                          threshold=self.voltage_threshold)
            self.optimized_offset_fluxes += np.array(threshold_offset_fluxes)
            print(f'threshold combination: {threshold_offset_fluxes}')
            print(f'optimized combination: {self.optimized_offset_fluxes}')
            self.optimized_fluxes = fluxes + self.optimized_offset_fluxes
            print(f'optimized fluxes: {self.optimized_fluxes}')
            new_voltages = self.crosstalk_compensation_optimization.flux_to_voltage(self.optimized_fluxes)
            new_voltage_norm = np.linalg.norm(new_voltages, ord=1)
            print(f'new norm is {np.round(new_voltage_norm, 3)}')
            voltages = new_voltages

        success = self.crosstalk_compensation_optimization.set_voltage_from_flux(self.channels, self.optimized_fluxes)

        if not success:
            # stop sweep
            self.sweep_running = False
            return False

        self.sweep_index += 1

        print()
        return True

    def set_next_point_integer_programming_method(self):

        print(f'sweep index: {self.sweep_index}')
        if not self.sweep_running:
            raise RuntimeError('Need to start sweep before setting next point')

        fluxes = np.copy(self.initial_fluxes)

        fluxes[self.channel_to_sweep] = self.flux_sweep_points[self.sweep_index]

        print(f'targeting flux: {fluxes}')
        self.optimized_offset_fluxes = self.crosstalk_compensation_optimization.integer_programming_get_combination(fluxes)
        print("Optimal offsets:", self.optimized_offset_fluxes)

        self.optimized_fluxes = fluxes + self.optimized_offset_fluxes
        voltages = self.crosstalk_compensation_optimization.flux_to_voltage(self.optimized_fluxes)
        print(f'optimal fluxes: {self.optimized_fluxes}')
        print(voltages)
        voltage_norm = np.linalg.norm(voltages, ord=1)
        print(voltage_norm)

    def ramp_to_zero(self):
        self.crosstalk_compensation_optimization.ramp_to_zero(self.channels)

class CrosstalkCompensationMatlabWrapper:
    '''
    This class is intended to be called from matlab code in order to find the optimal set of voltages to apply a set
    of specified magnetic fluxes on each flux line channel. This method is used to compensate for crosstalk between
    flux lines.

    There are limitations in passing in arrays from matlab to python functions. Originally, python would convert passed
    in arrays to numpy arrays using the `fromstring`. This is removed in Python 3.9. Potential workarounds include
    downgrading python when running code from matlab, converting matlab arrays to strings before passing and strings to
    numpy arrays in the python code, or designing functions so that only scalar inputs are needed. We decide to go with
    the last option.

    This class acts as a wrapper to the CrosstalkCompensationOptimization class. This class maintains a list of channels
    and fluxes on those channels. Call `set_flux` to change the recorded value on the provided channel. Once all fluxes
    are set this way, then `update_voltage` can be called to change the voltages such that all flux lines are set to the
    fluxes in the underlying list.



    '''

    def __init__(self, number_of_channels, crosstalk_matrix_directory, voltage_threshold):


        self.number_of_channels = int(number_of_channels)
        self.channels = [0] * self.number_of_channels
        self.fluxes = [0] * self.number_of_channels

        self.crosstalk_matrix_directory = crosstalk_matrix_directory

        self.voltage_threshold = voltage_threshold

        # self.crosstalk_compensation = CrosstalkCompensationOptimization(crosstalk_matrix_directory)

    def set_channel(self, index, channel):
        self.channels[int(index)] = channel

    def set_flux(self, index, flux):
        self.fluxes[int(index)] = flux

    def print_channels(self):
        print(self.channels)

    # def update_voltage(self):
    #     self.crosstalk_compensation.set_voltage_from_flux(self.channels, self.fluxes)

    def init_sweep(self, start, end, num_points, channel_to_sweep):

        flux_sweep_points = np.linspace(start, end, int(num_points))

        self.crosstalk_compensation_sweep = CrosstalkCompensationSweep(self.crosstalk_matrix_directory, self.channels, self.fluxes, voltage_threshold=self.voltage_threshold)
        self.crosstalk_compensation_sweep.start_sweep(int(channel_to_sweep), flux_sweep_points)

    def next_point_in_sweep(self):
        self.crosstalk_compensation_sweep.set_next_point_integer_programming_method()

    def ramp_to_zero(self):
        self.crosstalk_compensation_sweep.ramp_to_zero(self.channels)


if __name__ == '__main__':

    crosstalk_matrix_directory = r'Z:\QSimMeasurements\Measurements\4Q_Triangle_Lattice\crosstalk_matrices'



    crosstalk_compensation_matlab = CrosstalkCompensationMatlabWrapper(8, crosstalk_matrix_directory, voltage_threshold=8)

    channels = [0, 1, 2, 3, 4, 5, 8, 10]
    initial_flux = [0, 0, 0, 0, 0, 0, 0, 0]

    for i in range(len(channels)):
        crosstalk_compensation_matlab.set_channel(i, channels[i])
        crosstalk_compensation_matlab.set_flux(i, initial_flux[i])

    crosstalk_compensation_matlab.init_sweep(0, 1, 11, 3)

    flux_points = np.linspace(0, 1, 11)

    for i in range(len(flux_points)):
        crosstalk_compensation_matlab.next_point_in_sweep()
