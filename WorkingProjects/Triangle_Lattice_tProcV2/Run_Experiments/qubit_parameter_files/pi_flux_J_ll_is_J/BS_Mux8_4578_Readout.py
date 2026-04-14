from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



Readout_4578_FF = np.array(
    [-26873, 2277, 25392, -18000, -1000, 14426, -25722, -5631])
# (3535.3, 4100.0, 4389.6, 3640.0, 3900.0, 4300.0, 3460.3, 4000.0)

BS4578_Readout = {
    '1': {'Readout': {'Frequency': 7120.9, 'Gain': 1100,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3525.4, 'sigma': 0.03, 'Gain': 4372},
          'Pulse_FF': Readout_4578_FF},
    '2': {'Readout': {'Frequency': 7077.6, 'Gain': 1000,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4093.9, 'sigma': 0.03, 'Gain': 7000},
          'Pulse_FF': Readout_4578_FF},
    '3': {'Readout': {'Frequency': 7511.4, 'Gain': 1000,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4395.5, 'sigma': 0.03, 'Gain': 12949},
          'Pulse_FF': Readout_4578_FF},
    '4': {'Readout': {'Frequency': 7567.7, 'Gain': 1200,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3614.7, 'sigma': 0.03, 'Gain': 7364},
          'Pulse_FF': Readout_4578_FF},
    '5': {'Readout': {'Frequency': 7362.8, 'Gain': 800,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4002.0, 'sigma': 0.03, 'Gain': 6934},
          'Pulse_FF': Readout_4578_FF},
    '6': {'Readout': {'Frequency': 7441.8, 'Gain': 1100,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4297.2, 'sigma': 0.03, 'Gain': 5555},
          'Pulse_FF': Readout_4578_FF},
    '7': {'Readout': {'Frequency': 7253.35, 'Gain': 800,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3428.9, 'sigma': 0.03, 'Gain': 5843},
          'Pulse_FF': Readout_4578_FF},
    '8': {'Readout': {'Frequency': 7308.8, 'Gain': 1100,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3864.3, 'sigma': 0.03, 'Gain': 6200},
          'Pulse_FF': Readout_4578_FF},
}
