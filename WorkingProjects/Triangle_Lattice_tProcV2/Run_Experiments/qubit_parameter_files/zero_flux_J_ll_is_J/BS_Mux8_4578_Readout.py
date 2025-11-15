from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



# (3535.3, 4100.0, 4389.6, 3640.0, 3900.0, 4300.0, 3460.3, 4000.0)
Readout_4578_FF = np.array(
    # [-26873, 2277, 25392, -17533, -1000, 14426, -25722, -5631]
    [-26873, 2277, 25392, -14533, -1000, 14426, -25722, -5631]
)


BS4578_Readout = {
    '1': {'Readout': {'Frequency': 7121.2, 'Gain': 1228,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3534.7, 'sigma': 0.03, 'Gain': 7665},
          'Pulse_FF': Readout_4578_FF},
    '2': {'Readout': {'Frequency': 7077.6, 'Gain': 885,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4098.0, 'sigma': 0.03, 'Gain': 8276},
          'Pulse_FF': Readout_4578_FF},
    '3': {'Readout': {'Frequency': 7511.6, 'Gain': 1400,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4403.6, 'sigma': 0.03, 'Gain': 10166},
          'Pulse_FF': Readout_4578_FF},
    '4': {'Readout': {'Frequency': 7567.8, 'Gain': 1400,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3699.5, 'sigma': 0.03, 'Gain': 7955},
          'Pulse_FF': Readout_4578_FF},
    '5': {'Readout': {'Frequency': 7363.1, 'Gain': 1228,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4015.2, 'sigma': 0.03, 'Gain': 4309},
          'Pulse_FF': Readout_4578_FF},
    '6': {'Readout': {'Frequency': 7442.0, 'Gain': 1400,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4307.7, 'sigma': 0.03, 'Gain': 5854},
          'Pulse_FF': Readout_4578_FF},
    '7': {'Readout': {'Frequency': 7253.6, 'Gain': 1228,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3415.9, 'sigma': 0.03, 'Gain': 5052},
          'Pulse_FF': Readout_4578_FF},
    '8': {'Readout': {'Frequency': 7309.1, 'Gain': 885,
                      'FF_Gains': Readout_4578_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3903.2, 'sigma': 0.03, 'Gain': 6914},
          'Pulse_FF': Readout_4578_FF},

}
