from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



# (3580.0, 4150.0, 4380.0, 3770.0, 3690.0, 3850.0, 4000.0, 4280.0)
Readout_2378_FF = np.array([-20357, 1500, 21495, -16909, -10406, -6771, 500, 9000])



BS2378_Readout = {
    '1': {'Readout': {'Frequency': 7121.0, 'Gain': 1057,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3576.7, 'sigma': 0.03, 'Gain': 7230},
          'Pulse_FF': Readout_2378_FF},
    '2': {'Readout': {'Frequency': 7077.8, 'Gain': 1057,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4080.9, 'sigma': 0.03, 'Gain': 5970},
          'Pulse_FF': Readout_2378_FF},
    '3': {'Readout': {'Frequency': 7511.6, 'Gain': 1057,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4391.9, 'sigma': 0.03, 'Gain': 13000},
          'Pulse_FF': Readout_2378_FF},
    '4': {'Readout': {'Frequency': 7567.6, 'Gain': 1400,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3649.3, 'sigma': 0.03, 'Gain': 6173},
          'Pulse_FF': Readout_2378_FF},
    '5': {'Readout': {'Frequency': 7362.8, 'Gain': 1228,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3766.0, 'sigma': 0.03, 'Gain': 5814},
          'Pulse_FF': Readout_2378_FF},
    '6': {'Readout': {'Frequency': 7441.1, 'Gain': 1400,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3865.4, 'sigma': 0.03, 'Gain': 8763},
          'Pulse_FF': Readout_2378_FF},
    '7': {'Readout': {'Frequency': 7254.2, 'Gain': 714,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3983.1, 'sigma': 0.03, 'Gain': 6923},
          'Pulse_FF': Readout_2378_FF},
    '8': {'Readout': {'Frequency': 7309.6, 'Gain': 714,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4276.5, 'sigma': 0.03, 'Gain': 7686},
          'Pulse_FF': Readout_2378_FF},
}

