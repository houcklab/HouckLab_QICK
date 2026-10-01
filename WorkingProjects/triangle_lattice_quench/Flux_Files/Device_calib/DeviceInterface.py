from Device_calib.DeviceData import DeviceData
import numpy as np
import scipy
import scipy.optimize
from functools import lru_cache

'''the unit to be MHz'''

class DeviceInterface:
    '''
        self.couplings -> {tuple(str,str) : float} # gamma, ~ coupling at 4 GHz
        self.transmons -> {str : TransmonData}
        self.qubits -> {str : TransmonData}
        self.couplers -> {str : TransmonData}
    '''
    @classmethod
    def from_json(cls, DEVICE_PATH):
        '''convenience function'''
        return cls(DeviceData.from_json(DEVICE_PATH))

    def __init__(self, data: DeviceData):
        # Load and unpack data.
        self.ddata = data

        # dict mapping name to qubits and couplers
        self.couplings = {tuple(sorted((c.q1, c.q2))): c.gamma for c in self.ddata.couplings}
        self.transmons = self.ddata.transmons

        self.qubits = {}
        self.couplers = {}
        for qubit in self.ddata.transmons.values():
            if qubit.role == "Qubit":
                self.qubits[qubit.name] = qubit
            elif qubit.role == "Coupler":
                self.couplers[qubit.name] = qubit
            else:
                raise ValueError(f"Role must be 'Qubit' or 'Coupler', got: {qubit.role}")
        
        # ['Q1', 'Q2', ... 'C1', 'C2', ...] - the ordering of entries whenever a transmon quantity is held as an array
        self.ordered_all_transmons = list(sorted(self.qubits.keys())) + list(sorted(self.couplers.keys()))

        # A name is a DC line if it appears as a key in some transmon's DC crosstalk map; it is a
        # fast-flux line if it has a gain quantum, so ff_lines holds before ff crosstalk is calibrated
        dc_keys = set().union(*(t.crosstalk_dc_fq.keys() for t in self.transmons.values()))
        self.dc_lines = [n for n in self.ordered_all_transmons if n in dc_keys]
        self.ff_lines = [n for n in self.ordered_all_transmons if self.transmons[n].ffgain_quantum]

        self.generate_flux_voltage_map()

    def generate_flux_voltage_map(self):
        '''Using the calibration data, generate:
        1. full DC crosstalk matrix (F = CV, rows=ordered_all_transmons, cols=dc_lines) and the inverse of its square dc_lines block
        2. zero-voltage fluxes vector (over ordered_all_transmons) and its dc_lines slice
        '''
        # Generate the crosstalk matrix (n_transmons x n_dc_lines); a line missing from a transmon's map is zero crosstalk
        self.crosstalk_matrix = np.array([[self.transmons[row].crosstalk_dc_fq.get(col, 0) for col in self.dc_lines] for row in self.ordered_all_transmons])

        dc_rows = [self.ordered_all_transmons.index(n) for n in self.dc_lines]
        self.crosstalk_inverse = np.linalg.inv(self.crosstalk_matrix[dc_rows, :])

        # Generate the zero-voltage fluxes vector, plus its dc_lines slice used by flux_to_voltage
        self.zero_voltage_fluxes = np.array([self.ddata.zero_voltage_fluxes.get(q, 0) for q in self.ordered_all_transmons])
        self._zero_voltage_fluxes_dc = self.zero_voltage_fluxes[dc_rows]

    def flux_to_voltage(self, flux_vector:np.ndarray):
        '''Convert an array of target fluxes (over dc_lines) to an array of voltages (over dc_lines)'''
        return self.crosstalk_inverse @ (flux_vector - self._zero_voltage_fluxes_dc)

    def voltage_to_flux(self, voltage_vector:np.ndarray):
        '''Convert an array of voltages (over dc_lines) to an array of fluxes (over ordered_all_transmons)'''
        return self.zero_voltage_fluxes + self.crosstalk_matrix @ voltage_vector

    '''Internal retrieval functions'''
    def coupling_exists(self, qubit1: str, qubit2: str):
        '''Check if a coupling exists between two qubits'''
        return tuple(sorted((qubit1, qubit2))) in self.couplings

    @lru_cache
    def check_tunable_coupler(self, qubit1: str, qubit2: str):
        '''Get the name of the tunable coupler between two qubits, or None if none exists'''
        q1_couplers = set(name for name, gamma in self.get_adjacent_couplers(qubit1))
        q2_couplers = set(name for name, gamma in self.get_adjacent_couplers(qubit2))
        overlap = q1_couplers & q2_couplers
        if overlap:
            return overlap.pop()
        else:
            return None

    def get_coupling(self, **kwargs):
        '''Call: get_coupling(Q1=3800, Q2=3800) to get direct coupling from coupling matrix in MHz'''
        Q1, Q2 = kwargs.keys()
        Ec1, Ec2 = self.transmons[Q1].Ec, self.transmons[Q2].Ec
        w1, w2 = kwargs.values()
        gamma = self.couplings.get(tuple(sorted((Q1, Q2))), 0)
        return gamma/4000 * np.sqrt((w1 + Ec1)*(w2 + Ec2))

    def get_effective_coupling(self, **kwargs):
        '''Call: get_effective_coupling(Q1=3800, C1=5000, Q3=3800) to get effective coupling between the two qubits in MHz'''
        qubits, couplers = [], []
        for name in kwargs.keys():
            if name in self.qubits:
                qubits.append(name)
            elif name in self.couplers:
                couplers.append(name)
            else:
                raise KeyError(f"Unknown name: {name}")
        assert len(qubits)==2 and len(couplers)==1, "Must have two qubits and one coupler!"
        c = couplers[0]
        ((q1, gamma1), (q2, gamma2)) = self.get_adjacent_qubits_of_coupler(c)
        assert q1 in qubits and q2 in qubits, f"Invalid key combination: coupler {c} is between {sorted([q1,q2])}, not {sorted(qubits)}!"

        w1, w2, wc = kwargs[q1], kwargs[q2], kwargs[c]
        Ec1, Ec2, Ecc = (self.transmons[_q].Ec for _q in (q1, q2, c))
        g12 = self.get_coupling(**{q1:w1, q2:w2})

        return signed_eff_g(w1, w2, wc, gamma1 / 4000 * np.sqrt((w1 + Ec1) * (wc + Ecc)),
                     gamma2 / 4000 * np.sqrt((w2 + Ec2) * (wc + Ecc)), g12)

    @lru_cache
    def get_adjacent_couplers(self, qubit_name:str):
        '''List adjacent ('coupler_name', gamma) for a given qubit, form [('C1', 6.01)]'''
        return tuple((c, self.couplings[tuple(sorted((qubit_name, c)))]) for c in self.couplers.keys() if self.coupling_exists(qubit_name, c))

    @lru_cache
    def get_adjacent_qubits_of_coupler(self, coupler_name:str):
        '''List adjacent ('qubit_name', gamma) for a given coupler, form [('Q1', 90.1)]'''
        return tuple((q, self.couplings[tuple(sorted((coupler_name, q)))]) for q in self.qubits.keys() if self.coupling_exists(coupler_name, q))

    def bare_freqs_to_flux(self, bare_freqs:np.ndarray):
        '''Convert an array of bare frequencies to an array of fluxes'''
        return np.array([self.transmons[Q].flux(freq) for Q, freq in zip(self.ordered_all_transmons, bare_freqs)])

    
    def determine_coupler_freq(self, c_name:str, ratio:float, w_q:float):
        '''Determine the coupler frequency giving J_||/|J| = ratio (J_|| = coupler-mediated coupling,
        J = mean of the two rung couplings via the in-between qubit), with qubits at w_q.'''
        bounds=(0,10000)
        adjacent_qubits = self.get_adjacent_qubits_of_coupler(c_name)
        q1, q2 = adjacent_qubits[0][0], adjacent_qubits[1][0]
        gamma1, gamma2 = adjacent_qubits[0][1], adjacent_qubits[1][1]

        Ec1, Ec2, Ecc = self.transmons[q1].Ec, self.transmons[q2].Ec, self.transmons[c_name].Ec

        g12 = self.get_coupling(**{q1: w_q, q2: w_q})

        # J_||/|J| ratio -> absolute target g_eff: J = mean of the two rung couplings via the in-between qubit
        qm = next(q for q in self.qubits if q not in (q1, q2) and self.coupling_exists(q1, q) and self.coupling_exists(q, q2))
        g_eff = ratio * 0.5 * np.abs(self.get_coupling(**{q1: w_q, qm: w_q}) + self.get_coupling(**{qm: w_q, q2: w_q}))

        func = lambda wc: (signed_eff_g(w_q, w_q, wc, gamma1/4000*np.sqrt((w_q+Ec1)*(wc+Ecc)),  gamma2/4000*np.sqrt((w_q+Ec2)*(wc+Ecc)), g12) - g_eff)**2
        guess = w_q - gamma1*gamma2/4000**2 *w_q*w_q/(g_eff - g12)
        return scipy.optimize.minimize(func, x0=guess, bounds=[bounds]).x[0]


def signed_eff_g(w1, w2, wc, g1, g2, g12):
    Δ1, Δ2 = w1 - wc, w2 - wc
    Σ1, Σ2 = w1 + wc, w2 + wc
    return g1*g2/2*(1/Δ1 + 1/Δ2 - 1/Σ1 - 1/Σ2) + g1*g2*2/wc + g12