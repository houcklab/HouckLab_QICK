from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np


# (3550.0, 3800.0, 4300.0, 4150.0, 4000.0, 3900.0, 3650.0, 4200.0)
Readout_1254_FF = np.array([-22047, -9897, 16124, 5700, -2000, -6341, -13053, 10250])

Readout_1254_FF = np.array([-22047, -11000, 16124, 5700, -2000, -6341, -13053, 10250])
Readout_1254_FF = np.array([-22047, -11000, 16124, 5700, 500, -6341, -13053, 10250])

# new readout point
# (4280.0, 4130.0, 4350.0, 3880.0, 3750.0, 3960.0, 4055.0, 4205.0)
Readout_1254_FF = np.array([11035, 3643, 17468, -7290, -10862, -2912, 3665, 6214])
Readout_1254_FF = np.array([11035, 3643, 17468, -7290, -10862, -2400, 3665, 6214]) # 6 good

Readout_1254_FF = np.array([11035, 3643, 17468, -7290, -8500, -2400, 3665, 6214]) # 6 good
Readout_1254_FF = np.array([11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214]) # 6 good


BS1254_Readout = {
    '1': {'Readout': {'Frequency': 7121.9, 'Gain': 1057,
                      'FF_Gains': [11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214], 'Readout_Time': 3,
                      'ADC_Offset': 1},
          'Qubit': {'Frequency': 4277.4, 'sigma': 0.03, 'Gain': 8288},
          'Pulse_FF': [11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214]},
    '2': {'Readout': {'Frequency': 7077.8, 'Gain': 885,
                      'FF_Gains': [11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214], 'Readout_Time': 3,
                      'ADC_Offset': 1},
          'Qubit': {'Frequency': 4127.6, 'sigma': 0.03, 'Gain': 5781},
          'Pulse_FF': [11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214]},
    '3': {'Readout': {'Frequency': 7511.4, 'Gain': 885,
                      'FF_Gains': [11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214], 'Readout_Time': 3,
                      'ADC_Offset': 1},
          'Qubit': {'Frequency': 4362.9, 'sigma': 0.03, 'Gain': 7435},
          'Pulse_FF': [11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214]},
    '4': {'Readout': {'Frequency': 7568.1, 'Gain': 1400,
                      'FF_Gains': [11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214], 'Readout_Time': 2,
                      'ADC_Offset': 1},
          'Qubit': {'Frequency': 3867.9, 'sigma': 0.03, 'Gain': 10917},
          'Pulse_FF': [11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214]},
    '5': {'Readout': {'Frequency': 7362.8, 'Gain': 1400,
                      'FF_Gains': [11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214], 'Readout_Time': 3,
                      'ADC_Offset': 1},
          'Qubit': {'Frequency': 3814.0, 'sigma': 0.03, 'Gain': 10166},
          'Pulse_FF': [11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214]},
    '6': {'Readout': {'Frequency': 7441.2, 'Gain': 1057,
                      'FF_Gains': [11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214], 'Readout_Time': 3,
                      'ADC_Offset': 1},
          'Qubit': {'Frequency': 3973.4, 'sigma': 0.03, 'Gain': 6752},
          'Pulse_FF': [11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214]},
    '7': {'Readout': {'Frequency': 7253.8, 'Gain': 700,
                      'FF_Gains': [11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214], 'Readout_Time': 3,
                      'ADC_Offset': 1},
          'Qubit': {'Frequency': 4058.8, 'sigma': 0.03, 'Gain': 10876},
          'Pulse_FF': [11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214]},
    '8': {'Readout': {'Frequency': 7309.3, 'Gain': 885,
                      'FF_Gains': [11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214], 'Readout_Time': 3,
                      'ADC_Offset': 1},
          'Qubit': {'Frequency': 4209.7, 'sigma': 0.03, 'Gain': 6339},
          'Pulse_FF': [11035, 3643, 17468, -7500, -8500, -2400, 3665, 6214]},
}

