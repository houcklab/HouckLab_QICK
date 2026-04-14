from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



# (3580.0, 4150.0, 4380.0, 3770.0, 3690.0, 3850.0, 4000.0, 4280.0)
Readout_2378_FF = np.array([-20357, 1500, 21495, -16909, -10406, -6771, 500, 9000])



BS2378_Readout = {
    '1': {'Readout': {'Frequency': 7121.1, 'Gain': 800,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3570.1, 'sigma': 0.03, 'Gain': 8062},
          'Pulse_FF': Readout_2378_FF},
    '2': {'Readout': {'Frequency': 7077.6, 'Gain': 1000,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4075.6, 'sigma': 0.03, 'Gain': 5253},
          'Pulse_FF': Readout_2378_FF},
    '3': {'Readout': {'Frequency': 7511.2, 'Gain': 800,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4383.6, 'sigma': 0.03, 'Gain': 12885},
          'Pulse_FF': Readout_2378_FF},
    '4': {'Readout': {'Frequency': 7567.7, 'Gain': 1100,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3634.5, 'sigma': 0.03, 'Gain': 7383},
          'Pulse_FF': Readout_2378_FF},
    '5': {'Readout': {'Frequency': 7362.9, 'Gain': 1100,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3748.5, 'sigma': 0.03, 'Gain': 6124},
          'Pulse_FF': Readout_2378_FF},
    '6': {'Readout': {'Frequency': 7441.1, 'Gain': 1100,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3853.6, 'sigma': 0.03, 'Gain': 8166},
          'Pulse_FF': Readout_2378_FF},
    '7': {'Readout': {'Frequency': 7253.9, 'Gain': 600,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3974.5, 'sigma': 0.03, 'Gain': 7038},
          'Pulse_FF': Readout_2378_FF},
    '8': {'Readout': {'Frequency': 7309.4, 'Gain': 1100,
                      'FF_Gains': Readout_2378_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4250.4, 'sigma': 0.03, 'Gain': 6947},
          'Pulse_FF': Readout_2378_FF},
}

