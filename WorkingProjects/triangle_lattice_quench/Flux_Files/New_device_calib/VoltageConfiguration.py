import numpy as np
from scipy.optimize import root_scalar
from Device_calib.qt_qubit_sys import M_qubit_sys

class VoltageConfiguration:
    '''The interface for fast-flux-gain to qubit frequency.
    Stores flux_map {name: flux} as the qubit fluxes without FF gain and applies FF gains on top.
    '''
    def __init__(self, device:"DeviceInterface", configuration:dict):
        '''Convert {qubit names : frequencies, fluxes (or 'J_||/J' for couplers)} to a flux configuration.
        Rules: 
            1. Frequencies in MHz, e.g. 4000
            2. Fluxes in e.g. -0.25, 0, 1
            3. J_||/J@<w_q> as a string for tunable couplers: e.g. '3@3800' gives J_||/J=3 given qubit frequencies 3800 MHz

            A. Omitted qubit names default to 0 flux (will be noted), invalid names raise a ValueError.
        '''
        self.device = device
        self.flux_map = {} # {'Q1': -0.25, ...}

        # Check keys given
        valid_names = set(device.transmons)
        unknown = set(configuration) - valid_names
        if unknown:
            raise ValueError(f"Unknown qubit/coupler names in configuration: {sorted(unknown)}")
        omitted = valid_names - set(configuration)
        if omitted:
            print(f"VoltageConfiguration: defaulting to flux=0 for {sorted(omitted)}")

        # Determine coupler fluxes first, frequency dressing is insignificant
        for coupler in sorted(device.couplers.keys()):
            # Omitted, default to 0
            given_value = configuration.get(coupler, 0)
            # Tunable coupler J_||/J values
            if type(given_value) == str:
                J_ratio, w_q = given_value.split('@')
                w_c = device.determine_coupler_freq(coupler, float(J_ratio), float(w_q))
                self.flux_map[coupler] = device.transmons[coupler].flux(w_c)
            # Frequency in MHz
            elif given_value > 10:
                self.flux_map[coupler] = device.transmons[coupler].flux(given_value)
            # Flux directly given
            else:
                self.flux_map[coupler] = given_value

        # Determine qubit fluxes
        for qubit in sorted(self.device.qubits.keys()):
            value = configuration.get(qubit, 0)

            # Frequency in MHz
            if value > 10:
                bare_freq = self.dressed_to_bare_freq(qubit, value)
                self.flux_map[qubit] = self.device.transmons[qubit].flux(bare_freq)

            # Flux in dimensionless units
            elif value <= 10:
                self.flux_map[qubit] = value

    def desired_freqs_to_fast_flux(self, desired_freqs:dict)->dict:
        '''Convert a dictionary of desired frequencies to a dictionary of fast flux gains'''
        gains_dict = {}
        for q_name, desired_freq in desired_freqs.items():
            if q_name not in self.device.qubits:
                raise ValueError(f"Unknown qubit name: {q_name}")
            bare_freq = self.dressed_to_bare_freq(q_name, desired_freq)
            desired_flux = self.device.transmons[q_name].flux(bare_freq)
            current_flux = self.flux_map[q_name]
            gains_dict[q_name] = (desired_flux - current_flux) * self.device.transmons[q_name].ffgain_quantum
        return gains_dict

    def fast_fluxes_to_freqs(self, fast_fluxes:dict)->dict:
        '''Convert a dictionary of fast fluxes to a dictionary of all frequencies'''
        freqs_dict = {}
        for q_name, fast_flux in fast_fluxes.items():
            if q_name not in self.device.qubits:
                raise ValueError(f"Unknown qubit name: {q_name}")
            current_flux = self.flux_map[q_name]
            desired_flux = current_flux + fast_flux / self.device.transmons[q_name].ffgain_quantum
            freqs_dict[q_name] = self.device.transmons[q_name].freq(desired_flux)
        return freqs_dict

    def bare_to_dressed_freq(self, q_name:str, bare_freq:float)->float:
        '''Diagonalize the C-Q-C subspace: bare qubit frequency -> dressed qubit frequency.'''
        _, coupler_freqs, gammas = self._adjacent_coupler_data(q_name)
        return self._dressed_qubit_freq(bare_freq, q_name, coupler_freqs, gammas)
    
    def dressed_to_bare_freq(self, q_name:str, dressed_freq:float)->float:
        '''Invert the C-Q-C diagonalization: dressed qubit frequency -> bare qubit frequency.'''
        _, coupler_freqs, gammas = self._adjacent_coupler_data(q_name)
        transmon = self.device.transmons[q_name]

        def residual(bare_qubit_freq):
            return self._dressed_qubit_freq(float(bare_qubit_freq), q_name, coupler_freqs, gammas) - dressed_freq

        return float(root_scalar(residual, bracket=[transmon.w_min, transmon.w_max]).root)

    

    
    def _adjacent_coupler_data(self, q_name:str):
        '''Pull adjacent coupler bare frequencies and gammas (from device.couplings) for q_name.
        Coupler bare frequency is read from self.flux_map[c] via the transmon spectrum.'''
        adjacent = self.device.get_adjacent_couplers(q_name)
        c_names = [c for c, _ in adjacent]
        gammas = np.array([gamma for _, gamma in adjacent])
        coupler_freqs = np.array([self.device.transmons[c].freq(self.flux_map[c]) for c in c_names])
        return c_names, coupler_freqs, gammas

    def _dressed_qubit_freq(self, bare_qubit_freq:float, q_name:str, coupler_freqs:np.ndarray, gammas:np.ndarray)->float:
        '''Diagonalize the C-Q-C subspace and return the eigenenergy of the qubit-like 1-particle eigenstate.'''
        all_freqs = np.array([bare_qubit_freq, *coupler_freqs])
        Ec_q = self.device.transmons[q_name].Ec
        Ec_cs = np.array([self.device.transmons[c].Ec for c, _ in self.device.get_adjacent_couplers(q_name)])
        Ecs = np.array([Ec_q, *Ec_cs])

        # g_ij = gamma/4000 * sqrt((w_i+Ec_i)(w_j+Ec_j))
        couplings = {
            (1, j+2): gammas[j]/4000 * np.sqrt((bare_qubit_freq + Ec_q) * (coupler_freqs[j] + Ec_cs[j]))
            for j in range(len(coupler_freqs))
        }

        sys = M_qubit_sys(w=all_freqs, U=Ecs, couplings=couplings,
                          RWA=True, N=3, verbose=False)

        # Track the qubit-like eigenstate by overlap with |1, 0, 0, ...> (qubit excited, couplers ground)
        fock_label = [1] + [0] * len(coupler_freqs)
        _, energy = sys.dressed_state(fock_label)
        return energy

    