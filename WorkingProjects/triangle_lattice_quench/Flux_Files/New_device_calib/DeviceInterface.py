from Device_calib.DeviceData import DeviceData
from Device_calib.VoltageConfiguration import VoltageConfiguration
import numpy as np
import scipy
'''the unit to be MHz'''

class DeviceInterface:
    def __init__(self, data: DeviceData):
        # Load and unpack data.
        self.d = data

        # dict mapping name to qubits and couplers
        self.couplings = {tuple(sorted((c.q1, c.q2))): c.gamma for c in self.d.couplings}
        self.transmons = self.d.transmons

        self.qubits = {}
        self.couplers = {}
        for qubit in self.d.transmons.values():
            if qubit.role == "Qubit":
                self.qubits[qubit.name] = qubit
            elif qubit.role == "Coupler":
                self.couplers[qubit.name] = qubit
            else:
                raise ValueError(f"Role must be 'Qubit' or 'Coupler', got: {qubit.role}")
        
        # ['Q1', 'Q2', ... 'C1', 'C2', ...]
        self.ordered_names = list(sorted(self.qubits.keys())) + list(sorted(self.couplers.keys()))
        self.generate_flux_voltage_map()

    def generate_flux_voltage_map(self):
        '''Using the calibration data, generate:
        1. full crosstalk matrix (F = CV) and inverse
        2. zero-voltage fluxes vector
        '''
        # Generate the crosstalk matrix and its inverse
        self.crosstalk_matrix = np.array([[self.transmons[row].crosstalk_map.get(col, 0) for col in self.ordered_names] for row in self.ordered_names])
        self.crosstalk_inverse = np.linalg.inv(self.crosstalk_matrix)

        # Generate the zero-voltage fluxes vector
        self.zero_voltage_fluxes = np.array([self.d.zero_voltage_fluxes.get(q, 0) for q in self.ordered_names])

    '''Interface'''
    def create_voltage_configuration(self, configuration:dict):
        return VoltageConfiguration(self, configuration)
    
    def flux_to_voltage(self, flux_vector:np.ndarray):
        '''Convert an array of fluxes to an array of voltages'''
        return self.crosstalk_inverse @ (flux_vector - self.zero_voltage_fluxes)

    def voltage_to_flux(self, voltage_vector:np.ndarray):
        '''Convert an array of voltages to an array of fluxes'''
        return self.zero_voltage_fluxes + self.crosstalk_matrix @ voltage_vector

    '''Internal retrieval functions'''
    def coupling_exists(self, qubit1: str, qubit2: str):
        '''Check if a coupling exists between two qubits'''
        return tuple(sorted((qubit1, qubit2))) in self.couplings

    def get_coupling(self, **kwargs):
        '''Call: get_coupling(Q1=3800, Q2=3800) to get direct coupling from coupling matrix in MHz'''
        Q1, Q2 = kwargs.keys()
        Ec1, Ec2 = self.transmons[Q1].Ec, self.transmons[Q2].Ec
        w1, w2 = kwargs.values()
        gamma = self.couplings[tuple(sorted((Q1, Q2)))]
        return gamma/4000 * np.sqrt((w1 + Ec1)*(w2 + Ec2))

    def get_adjacent_couplers(self, qubit_name:str):
        '''List adjacent couplers with gamma for a given qubit, form [('C1', 6.01)]'''
        return [(c, self.couplings[tuple(sorted((qubit_name, c)))]) for c in self.couplers.keys() if self.coupling_exists(qubit_name, c)]

    def get_adjacent_qubits_of_coupler(self, coupler_name:str):
        '''List adjacent qubits with gamma for a given coupler, form [('Q1', 90.1)]'''
        return [(q, self.couplings[tuple(sorted((coupler_name, q)))]) for q in self.qubits.keys() if self.coupling_exists(coupler_name, q)]

    def bare_freqs_to_flux(self, bare_freqs:np.ndarray):
        '''Convert an array of bare frequencies to an array of fluxes'''
        return np.array([self.transmons[Q].flux(freq) for Q, freq in zip(self.ordered_names, bare_freqs)])

    
    def determine_coupler_freq(self, c_name:str, g_eff:float, w_q:float):
        '''Uses a Q-C-Q model and the coupling matrix to determine the required frequency for a tunable coupler'''
        bounds=(0,10000)
        adjacent_qubits = self.get_adjacent_qubits_of_coupler(c_name)
        q1, q2 = adjacent_qubits[0][0], adjacent_qubits[1][0]
        gamma1, gamma2 = adjacent_qubits[0][1], adjacent_qubits[1][1]
        
        g12 = self.get_coupling(q1=q1, q2=q2)

        func = lambda wc: (signed_eff_g(w_q, w_q, wc, gamma1/4000*np.sqrt(w_q*wc),  gamma2/4000*np.sqrt(w_q*wc), g12) - g_eff)**2
        guess = w_q - gamma1*gamma2/4000**2 *w_q*w_q/(g_eff - g12)
        return scipy.optimize.minimize(func, x0=guess, bounds=[bounds]).x[0]


def signed_eff_g(w1, w2, wc, g1, g2, g12):
    Δ1, Δ2 = w1 - wc, w2 - wc
    Σ1, Σ2 = w1 + wc, w2 + wc
    return g1*g2/2*(1/Δ1 + 1/Δ2 - 1/Σ1 - 1/Σ2) + g1*g2*2/wc + g12