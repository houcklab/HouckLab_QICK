from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np



Readout_TEST_FF = np.array([-10300, -20001, 2000, -6900, -25700, -11986, 952, -19595])
# [3765, 3546, 4026, 3725, 3486, 4005, 3689, 3517]
# Readout_TEST_FF = np.array([-12706,   4899,  13421,  -4010,  -8537,  20543,   3328, -17003])
BSTEST_Readout = {
    '1': {'Readout': {'Frequency': 7121.2, 'Gain': 1200,
                      'FF_Gains': Readout_TEST_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3743.0, 'sigma': 0.015, 'Gain': 8386},
          'Pulse_FF': Readout_TEST_FF},
    '2': {'Readout': {'Frequency': 7077.1, 'Gain': 1500,
                      'FF_Gains': Readout_TEST_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3571.9, 'sigma': 0.015, 'Gain': 8900},
          'Pulse_FF': Readout_TEST_FF},
    '3': {'Readout': {'Frequency': 7511.1, 'Gain': 1500,
                      'FF_Gains': Readout_TEST_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3969.1, 'sigma': 0.025, 'Gain': 20900},
          'Pulse_FF': Readout_TEST_FF},
    '4': {'Readout': {'Frequency': 7568.1, 'Gain': 1500,
                      'FF_Gains': Readout_TEST_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3826.9, 'sigma': 0.01, 'Gain': 11810},
          'Pulse_FF': Readout_TEST_FF},
    '5': {'Readout': {'Frequency': 7362.7, 'Gain': 2000,
                      'FF_Gains': Readout_TEST_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3491.2, 'sigma': 0.015, 'Gain': 11217},
          'Pulse_FF': Readout_TEST_FF},
    '6': {'Readout': {'Frequency': 7441.0, 'Gain': 2400,
                      'FF_Gains': Readout_TEST_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3688.2, 'sigma': 0.01, 'Gain': 11993},
          'Pulse_FF': Readout_TEST_FF},
    '7': {'Readout': {'Frequency': 7253.9, 'Gain': 1200,
                      'FF_Gains': Readout_TEST_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3940.2, 'sigma': 0.015, 'Gain': 5520},
          'Pulse_FF': Readout_TEST_FF},
    '8': {'Readout': {'Frequency': 7308.6, 'Gain': 1500,
                      'FF_Gains': Readout_TEST_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3526.8, 'sigma': 0.015, 'Gain': 15475},
          'Pulse_FF': Readout_TEST_FF},
}

