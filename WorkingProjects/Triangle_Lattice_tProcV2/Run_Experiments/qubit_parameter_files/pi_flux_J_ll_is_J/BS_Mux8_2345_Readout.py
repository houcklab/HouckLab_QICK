from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np


Readout_2345_FF = np.array([-12000, 4000, 17468, -7500, -14000, 12000, 0, -18000])

Readout_2345_FF = np.array([-12000, 4000, 17468, -7500, -14000, 11500, 0, -18000])

Readout_2345_FF = np.array([-12000, 4000, 17468, -7500, -14000, 11500, 1000, -18000])

Readout_2345_FF = np.array([-12000, 4000, 17468, -7000, -14000, 11500, 1000, -18000])



BS2345_Readout = {
    '1': {'Readout': {'Frequency': 7121.1, 'Gain': 1057,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3721.3, 'sigma': 0.03, 'Gain': 11372},
          'Pulse_FF': Readout_2345_FF},
    '2': {'Readout': {'Frequency': 7077.8, 'Gain': 1400,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4112.9, 'sigma': 0.03, 'Gain': 9459},
          'Pulse_FF': Readout_2345_FF},
    '3': {'Readout': {'Frequency': 7511.6, 'Gain': 1228,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4300.2, 'sigma': 0.03, 'Gain': 8214},
          'Pulse_FF': Readout_2345_FF},
    '4': {'Readout': {'Frequency': 7567.8, 'Gain': 1228,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3843.0, 'sigma': 0.03, 'Gain': 9939},
          'Pulse_FF': Readout_2345_FF},
    '5': {'Readout': {'Frequency': 7363.0, 'Gain': 1057,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3637.4, 'sigma': 0.03, 'Gain': 8149},
          'Pulse_FF': Readout_2345_FF},
    '6': {'Readout': {'Frequency': 7441.5, 'Gain': 1000,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4210.3, 'sigma': 0.03, 'Gain': 6025},
          'Pulse_FF': Readout_2345_FF},
    '7': {'Readout': {'Frequency': 7253.8, 'Gain': 542,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3967.7, 'sigma': 0.03, 'Gain': 4375},
          'Pulse_FF': Readout_2345_FF},
    '8': {'Readout': {'Frequency': 7308.7, 'Gain': 1057,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3565.7, 'sigma': 0.03, 'Gain': 8210},
          'Pulse_FF': Readout_2345_FF},
}

