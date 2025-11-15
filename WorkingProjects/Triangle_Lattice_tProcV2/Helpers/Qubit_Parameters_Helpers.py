from collections import defaultdict

import numpy as np

LEN_FF_ARRAY = 8

class FF_gains:
    '''Summary:
        ExptFF = FFgain([0, 0, 0, 0, 0, 0, 0, 0])
        ExptFF + [1000,1000,0,0,0,0,0,0] -> FFgain([1000,1000,0,0,0,0,0,0])
        ExptFF.set(Q1=4000, q4=2000) -> FFgain([4000,0,0,2000,0,0,0,0]
        ExptFF.add(Q1=4000, q4=2000) -> FFgain([4000,0,0,2000,0,0,0,0]
        ExptFF.subsys(3,4) -> FFgain([4000,4000,0,0,4000,4000,4000,4000])
    '''
    def __init__(self, arr):
        '''Usage:
            ExptFF = FFgain([0, 0, 0, 0, 0, 0, 0, 0])
            PulseFF = FFgain([0,0,0,0,1000,0,0,0])
        '''
        self.arr = np.asarray(arr)

    def __iter__(self):
        return iter(self.arr)

    def __repr__(self):
        return f"FFgain({str(self.arr)})"

    def __getitem__(self, i):
        return self.arr[i]

    def __setitem__(self, i, val):
        self.arr[i] = val

    def __len__(self):
        return len(self.arr)

    def __add__(self, other):
        ''' ExptFF + [1000,1000,0,0,0,0,0,0] -> FFgain([1000,1000,0,0,0,0,0,0])'''
        if type(other) is FF_gains:
            return FF_gains(self.arr + other.arr)
        else:
            return FF_gains(self.arr + other)

    def set(self, **kwargs):
        '''Usage:
             ExptFF.set(Q1=4000, (q3,q4)=2000, Q5=PulseFF) -> FF_gains([4000,0,2000,2000,1000,0,0,0]
        '''
        new_arr = self.arr.copy()
        for qubit, gain in kwargs.items():
            if isinstance(qubit, (list, tuple)):
                # Not currently usable, you can't pass a tuple as a param name
                for q in qubit:
                    index = int(q[1:]) - 1
                    if isinstance(gain, (list, tuple, FF_gains, np.ndarray)):
                        new_arr[index] = gain[index]
                    else:
                        new_arr[index] = gain
            else:
                index = int(qubit[1:]) - 1
                if isinstance(gain, (list, tuple, FF_gains, np.ndarray)):
                    new_arr[index] = gain[index]
                else:
                    new_arr[index] = gain

        return FF_gains(new_arr)

    def add(self, **kwargs):
        '''Usage:
             ExptFF.add(Q1=4000, q4=2000) -> FF_gains([4000,0,0,2000,0,0,0,0]
        '''
        new_arr = self.arr.copy()
        for qubit, gain in kwargs.items():
            if isinstance(qubit, (list, tuple)):
                # Not currently usable, you can't pass a tuple as a param name
                for q in qubit:
                    new_arr[int(q[1:]) - 1] += gain
            new_arr[int(qubit[1:]) - 1] += gain
        return FF_gains(new_arr)

    def subsys(self, *args, det=4000):
        '''Usage:
            ExptFF.subsys(3,4) -> FF_gains([4000,4000,0,0,4000,4000,4000,4000])
        '''
        detuning_list = np.full_like(self.arr, det)
        for qubit in args:
            detuning_list[qubit-1] = 0

        return FF_gains(self.arr + detuning_list)

class QubitParams:
    def __init__(self, param_dict={}):
        self.d = defaultdict(dict, param_dict)
    
    def __or__(self, other):
        if type(other) is QubitParams:
            return QubitParams(self.d | other.d)
        else:
            return QubitParams(self.d | other)

    def add_pulse(self, name, freq, gain, sigma, ff_array = None):
        if ff_array is None:
            ff_array = np.zeros(LEN_FF_ARRAY)
        self.d[name]['Qubit'] = {'Frequency': freq, 'Gain': gain, 'sigma': sigma,}
        self.d[name]['Pulse_FF'] = ff_array

    def add_readout(self, name, freq, gain, ff_array = None, read_time=3, adc_off=1):
        if ff_array is None:
            ff_array = np.zeros(LEN_FF_ARRAY)
        self.d[name]['Readout'] = {'Frequency': freq, 'Gain': gain,
                                     "FF_Gains": ff_array, "Readout_Time": read_time, "ADC_Offset": adc_off},
        
    def add_expt(self, name, ff_array, ff_init=None):
        self.d[name]['Expt'] = {'Expt_FF': ff_array, 'Init_FF': ff_init}

class QubitConfig:
    def __init__(self, cfg, Qubit, L, OptReadout_index, OptQubit_index, varname_FF=None):
        self.Q = Qubit
        self.qubit_freq = cfg["qubit_freqs"][OptQubit_index]
        self.resonator_freq = cfg["res_freqs"][OptReadout_index] + cfg["res_LO"]
        self.qubit_gain = int(32766 * cfg["qubit_gains"][OptQubit_index])
        self.res_gain = int(32766 * cfg["res_gains"][OptReadout_index] / L) # divide by num readouts
        self.sigma = cfg["sigma"]
        self.readout_time = cfg["readout_lengths"][OptReadout_index]
        self.adc_offset = cfg["adc_trig_delays"][OptReadout_index]

        if varname_FF is None:
            self.ReadoutFF = [int(cfg['FF_Qubits'][Q]['Gain_Readout']) for Q in cfg['FF_Qubits']]
            self.PulseFF = [int(cfg['FF_Qubits'][Q]['Gain_Pulse']) for Q in cfg['FF_Qubits']]
        else:
            self.ReadoutFF = varname_FF
            self.PulseFF = varname_FF

    def __repr__(self):
        return f"   '{self.Q}': {{'Readout': {{'Frequency': {self.resonator_freq:.1f}, 'Gain': {self.res_gain},\n\
                          'FF_Gains': {self.ReadoutFF}, 'Readout_Time': {self.readout_time}, 'ADC_Offset': {self.adc_offset}}},\n\
              'Qubit': {{'Frequency': {self.qubit_freq:.1f}, 'sigma': {self.sigma}, 'Gain': {self.qubit_gain}}},\n\
              'Pulse_FF': {self.PulseFF}}},"
