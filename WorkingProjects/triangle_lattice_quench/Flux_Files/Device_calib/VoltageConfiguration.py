import numpy as np
from scipy.optimize import root_scalar
import json
from .DeviceInterface import DeviceInterface
from .DeviceData import DeviceData
from .qt_qubit_sys import M_qubit_sys

class VoltageConfiguration:
    '''The interface for fast-flux-gain to qubit frequency.
    Instance variables:
        flux_map: {str: float}, qubit name -> flux at this voltage point
    '''

    @classmethod
    def from_json(cls, DEVICE_PATH, VOLTAGES_PATH):
        ''' Convenience constructor from DEVICE_PATH and VOLTAGES_PATH

            DEVICE_PATH: DeviceData info
            VOLTAGES_PATH: json with an entry "voltages" of the form {'Q1', 1.0, ...} '''
        device = DeviceInterface.from_json(DEVICE_PATH)
        with open(VOLTAGES_PATH, 'r') as f:
            raw_voltages = json.load(f)['voltages']
        return cls(device, raw_voltages=raw_voltages)  # Returns a new Date instance

    def __init__(self, device:DeviceInterface, configuration:dict=None, raw_voltages:dict=None):
        '''
        Pass either 'configuration' or 'raw_voltages'.

        configuration:
            Convert {qubit names : frequencies, fluxes (or 'J_||/J' for couplers)} to a flux configuration.
            Rules for configuration:
                1. Frequencies in MHz,                              e.g. 'Q1': 4000,
                2. Fluxes (unitless)                                e.g. 'Q2': -0.25,
                3. J_||/|J|@<w_q> as a string for tunable couplers: e.g. 'C1': '3@3800', # gives J_||/|J|=3 given qubit frequencies 3800 MHz

                A. Omitted qubit names default to 0 flux (will be noted), invalid names raise a ValueError.

        raw_voltages:
            Dict of voltages, {'Q1', 1.0, 'Q2': 0.1, ...} in V
        '''

        assert (configuration is None or raw_voltages is None), "Pass in either a configuration or raw_voltages dict, not both!!!"
        assert (configuration is not None or raw_voltages is not None), "Pass in either a configuration or raw_voltages dict!!!"

        self.device = device
        self.base_flux_map = {}  # {'Q1': -0.25, ...}

        if configuration is not None:
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
                    self.base_flux_map[coupler] = device.transmons[coupler].flux(w_c)
                # Frequency in MHz
                elif given_value > 10:
                    self.base_flux_map[coupler] = device.transmons[coupler].flux(given_value)
                # Flux directly given
                else:
                    self.base_flux_map[coupler] = given_value

            # Determine qubit fluxes
            for qubit in sorted(self.device.qubits.keys()):
                value = configuration.get(qubit, 0)

                # Frequency in MHz
                if value > 10:
                    bare_freq = self.dressed_to_bare_freq(qubit, value)
                    self.base_flux_map[qubit] = self.device.transmons[qubit].flux(bare_freq)

                # Flux in dimensionless units
                elif value <= 10:
                    self.base_flux_map[qubit] = value


        else: # raw_voltages is not None, use them
            voltage_arr = np.array([raw_voltages[name] for name in self.device.dc_lines])
            flux_arr = self.device.voltage_to_flux(voltage_arr)
            self.base_flux_map = dict(zip(self.device.ordered_all_transmons, flux_arr))

    def get_fluxes_dict(self):
        '''Get the bare flux map {'Q1': -0.25, ...} for all qubits and couplers at this voltage'''
        return self.base_flux_map
    
    def get_fluxes_dict_with_fast_flux(self, fast_flux_dict):
        '''Get the flux map {'Q1': -0.25, ...} for all qubits at this voltage when the fast fluxes of ff_dict are applied'''
        '''Convert a dictionary of qubit fast fluxes {'Q1':1000, ...} to a dictionary of frequencies'''
        if fast_flux_dict is None:
            return self.base_flux_map
        if isinstance(fast_flux_dict, (list, np.ndarray)):
            fast_flux_dict = {key: fast_flux_dict[i] for i, key in enumerate(self.device.ff_lines)}
        ff_flux_map = self.base_flux_map.copy()
        for q_name, fast_flux in fast_flux_dict.items():
            if q_name not in self.device.ff_lines:
                raise ValueError(f"Unknown fast-flux line name: {q_name}")
            current_flux = self.base_flux_map[q_name]
            ff_flux_map[q_name] = current_flux + fast_flux / self.device.transmons[q_name].ffgain_quantum
        return ff_flux_map
    
    def get_voltages_dict(self):
        '''Return dict of all raw DC voltages at this configuration, one entry per DC line'''
        flux_arr = np.array([self.base_flux_map[name] for name in self.device.dc_lines])
        voltage_arr = self.device.flux_to_voltage(flux_arr)
        return dict(zip(self.device.dc_lines, voltage_arr))


    def get_bare_frequencies_dict(self, fast_flux_dict=None):
        '''Return dict of all base bare frequencies (qubits AND couplers, all fast fluxes=0) at this configuration'''
        flux_map = self.get_fluxes_dict_with_fast_flux(fast_flux_dict)
        freqs_dict = {}
        for q_name, current_flux in flux_map.items():
            freqs_dict[q_name] = self.device.transmons[q_name].freq(current_flux)
        return freqs_dict

    def get_all_bare_couplings_dict(self, fast_flux_dict=None):
        '''Return dict of all bare couplings at this configuration'''
        couplings_dict = {}
        bare_freqs = self.get_bare_frequencies_dict(fast_flux_dict)
        for key in self.device.couplings:
            q1, q2 = key
            couplings_dict[key] = self.device.get_coupling(**{q1: bare_freqs[q1], q2: bare_freqs[q2]})

        return couplings_dict

    def get_dressed_frequencies_dict(self, fast_flux_dict=None):
        '''Return dict of all dressed frequencies (qubits only, all fast fluxes=0) at this configuration'''
        flux_map = self.get_fluxes_dict_with_fast_flux(fast_flux_dict)
        freqs_dict = {}
        for q_name in self.device.qubits:
            current_flux = flux_map[q_name]
            freqs_dict[q_name] = self.bare_to_dressed_freq(q_name, self.device.transmons[q_name].freq(current_flux))
        return freqs_dict


    def get_all_dressed_couplings_dict(self, fast_flux_dict=None):
        '''Return dict of all bare couplings at this configuration'''
        couplings_dict = {}
        bare_freqs = self.get_bare_frequencies_dict(fast_flux_dict)
        bare_couplings = self.get_all_bare_couplings_dict(fast_flux_dict)
        for key in bare_couplings:
            q1, q2 = key
            # only qubit-qubit couplings
            if q1 in self.device.qubits and q2 in self.device.qubits:
                coupler = self.device.check_tunable_coupler(q1, q2)
                if coupler is None:
                    couplings_dict[key] = self.device.get_coupling(**{q1:bare_freqs[q1], q2:bare_freqs[q2]})
                else:
                    couplings_dict[key] = self.device.get_effective_coupling(**{q1:bare_freqs[q1], q2:bare_freqs[q2], coupler:bare_freqs[coupler]})

        return couplings_dict

    def desired_freqs_to_fast_flux(self, desired_freqs:dict)->dict:
        '''Convert a dictionary of desired qubit frequencies {'Q1':3800, ...} to a dictionary of fast flux gains'''
        if isinstance(desired_freqs, (list, np.ndarray)):
            desired_freqs = {key:desired_freqs[i] for i, key in enumerate(self.device.ff_lines)}
        gains_dict = {}
        for q_name, desired_freq in desired_freqs.items():
            if q_name not in self.device.ff_lines:
                raise ValueError(f"Unknown fast-flux line name: {q_name}")
            bare_freq = self.dressed_to_bare_freq(q_name, desired_freq)
            desired_flux = self.device.transmons[q_name].flux(bare_freq)
            current_flux = self.base_flux_map[q_name]
            gains_dict[q_name] = round((desired_flux - current_flux) * self.device.transmons[q_name].ffgain_quantum)
        return gains_dict

    def fast_flux_to_dressed_freqs(self, fast_fluxes:dict)->dict:
        '''Convert a dictionary of qubit fast fluxes {'Q1':1000, ...} to a dictionary of frequencies'''
        if isinstance(fast_fluxes, (list, np.ndarray)):
            fast_fluxes = {key:fast_fluxes[i] for i, key in enumerate(self.device.ff_lines)}
        freqs_dict = {}
        for q_name, fast_flux in fast_fluxes.items():
            if q_name not in self.device.ff_lines:
                raise ValueError(f"Unknown fast-flux line name: {q_name}")
            current_flux = self.base_flux_map[q_name]
            desired_flux = current_flux + fast_flux / self.device.transmons[q_name].ffgain_quantum
            freqs_dict[q_name] = self.bare_to_dressed_freq(q_name, self.device.transmons[q_name].freq(desired_flux))
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

    def dressed_freq_to_flux(self, q_name:str, dressed_freq:float)->float:
        bare_freq = self.dressed_to_bare_freq(q_name, dressed_freq)
        transmon = self.device.transmons[q_name]
        flux = self.device.transmons[q_name].flux(bare_freq)
        return flux
    
    def _adjacent_coupler_data(self, q_name:str):
        '''Pull adjacent coupler bare frequencies and gammas (from device.couplings) for q_name.
        Coupler bare frequency is read from self.base_flux_map[c] via the transmon spectrum.'''
        adjacent = self.device.get_adjacent_couplers(q_name)
        c_names = [c for c, _ in adjacent]
        gammas = np.array([gamma for _, gamma in adjacent])
        coupler_freqs = np.array([self.device.transmons[c].freq(self.base_flux_map[c]) for c in c_names])
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

    