from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



Readout_4578_FF = np.array(
    [-26873, 2277, 25392, -17533, -1000, 14426, -25722, -5631])
# (3535.3, 4100.0, 4389.6, 3640.0, 3900.0, 4300.0, 3460.3, 4000.0)

BS4578_Readout_Josh = {
    '1': {'Readout': {'Frequency': 7120.9, 'Gain': 828,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3535.4, 'sigma': 0.03, 'Gain': 8390},
          'Pulse_FF': Readout_4578_FF},
    '2': {'Readout': {'Frequency': 7077.6, 'Gain': 800,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4099.0, 'sigma': 0.03, 'Gain': 8277},
          'Pulse_FF': Readout_4578_FF},
    '3': {'Readout': {'Frequency': 7511.4, 'Gain': 1057,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4403.2, 'sigma': 0.03, 'Gain': 10802},
          'Pulse_FF': Readout_4578_FF},
    '4': {'Readout': {'Frequency': 7567.7, 'Gain': 1400,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3640.0, 'sigma': 0.03, 'Gain': 6373},
          'Pulse_FF': Readout_4578_FF},
    '5': {'Readout': {'Frequency': 7363.3, 'Gain': 885,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4014.1, 'sigma': 0.03, 'Gain': 4916},
          'Pulse_FF': Readout_4578_FF},
    '6': {'Readout': {'Frequency': 7441.8, 'Gain': 885,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4307.7, 'sigma': 0.03, 'Gain': 5670},
          'Pulse_FF': Readout_4578_FF},
    '7': {'Readout': {'Frequency': 7253.6, 'Gain': 1228,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3416.9, 'sigma': 0.03, 'Gain': 5386},
          'Pulse_FF': Readout_4578_FF},
    '8': {'Readout': {'Frequency': 7308.8, 'Gain': 685,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3902.9, 'sigma': 0.03, 'Gain': 6541},
          'Pulse_FF': Readout_4578_FF},
}

