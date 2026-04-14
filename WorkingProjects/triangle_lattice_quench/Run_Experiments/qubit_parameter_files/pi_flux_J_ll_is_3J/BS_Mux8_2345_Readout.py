from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np


Readout_2345_FF = np.array([-12000, 4000, 17468, -7500, -14000, 12000, 0, -18000])

Readout_2345_FF = np.array([-12000, 4000, 17468, -7500, -14000, 11500, 0, -18000])

Readout_2345_FF = np.array([-12000, 4000, 17468, -7500, -14000, 11500, 1000, -18000])


#updated after copy
Readout_2345_FF = np.array([-12686, 4933, 25392, -8399, -26700, 13611, 738, -16988])


# hunt for new Q4 and Q5 readouts
Readout_2345_FF = np.array([-12686, 4933, 25392, -1500, -23700, 13611, 738, -16988])

Readout_2345_FF = np.array([-12686, 4933, 25392, -4000, -8500, 13611, 3353, -16988])


BS2345_Readout = {
    '1': {'Readout': {'Frequency': 7121.1, 'Gain': 1200,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3727.0, 'sigma': 0.03, 'Gain': 4795},
          'Pulse_FF': Readout_2345_FF},
    '2': {'Readout': {'Frequency': 7077.5, 'Gain': 1200,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4159.9, 'sigma': 0.03, 'Gain': 2732},
          'Pulse_FF': Readout_2345_FF},
    '3': {'Readout': {'Frequency': 7511.4, 'Gain': 1500,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4406.3, 'sigma': 0.03, 'Gain': 4498},
          'Pulse_FF': Readout_2345_FF},
    '4': {'Readout': {'Frequency': 7568.1, 'Gain': 2100,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3967.9, 'sigma': 0.03, 'Gain': 4762},
          'Pulse_FF': Readout_2345_FF},
    '5': {'Readout': {'Frequency': 7362.6, 'Gain': 2000,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3821.4, 'sigma': 0.03, 'Gain': 7008},
          'Pulse_FF': Readout_2345_FF},
    '6': {'Readout': {'Frequency': 7441.9, 'Gain': 2400,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4299.5, 'sigma': 0.03, 'Gain': 3337},
          'Pulse_FF': Readout_2345_FF},
    '7': {'Readout': {'Frequency': 7253.9, 'Gain': 1200,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4052.2, 'sigma': 0.03, 'Gain': 6535},
          'Pulse_FF': Readout_2345_FF},
    '8': {'Readout': {'Frequency': 7308.4, 'Gain': 2400,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3613.0, 'sigma': 0.03, 'Gain': 3256},
          'Pulse_FF': Readout_2345_FF},

}

