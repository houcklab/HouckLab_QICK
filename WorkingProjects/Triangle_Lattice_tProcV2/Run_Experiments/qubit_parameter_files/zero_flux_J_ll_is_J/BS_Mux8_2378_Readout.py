from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



# (3580.0, 4150.0, 4380.0, 3770.0, 3690.0, 3850.0, 4000.0, 4280.0)
Readout_2378_FF = np.array([-20357, 1500, 21495, -16909, -10406, -6771, 500, 9000])



BS2378_Readout = {
    '1': {'Readout': {'Frequency': 7121.1, 'Gain':886,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3561.1, 'sigma': 0.03, 'Gain': 7800},
          'Pulse_FF': Readout_2378_FF},
    '2': {'Readout': {'Frequency': 7077.6, 'Gain': 1228,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4059.6, 'sigma': 0.03, 'Gain': 5750},
          'Pulse_FF': Readout_2378_FF},
    '3': {'Readout': {'Frequency': 7511.7, 'Gain': 714,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4329.9, 'sigma': 0.03, 'Gain': 11288},
          'Pulse_FF': Readout_2378_FF},
    '4': {'Readout': {'Frequency': 7567.6, 'Gain': 1400,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3611.2, 'sigma': 0.03, 'Gain': 8913},
          'Pulse_FF': Readout_2378_FF},
    '5': {'Readout': {'Frequency': 7363.1, 'Gain': 1400,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3722.4, 'sigma': 0.03, 'Gain': 11826},
          'Pulse_FF': Readout_2378_FF},
    '6': {'Readout': {'Frequency': 7441.1, 'Gain': 1057,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3828.3, 'sigma': 0.03, 'Gain': 6286},
          'Pulse_FF': Readout_2378_FF},
    '7': {'Readout': {'Frequency': 7253.9, 'Gain': 542,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3954.5, 'sigma': 0.03, 'Gain': 4359},
          'Pulse_FF': Readout_2378_FF},
    '8': {'Readout': {'Frequency': 7309.4, 'Gain': 1228,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4247.1, 'sigma': 0.03, 'Gain': 8849},
          'Pulse_FF': Readout_2378_FF},
}

