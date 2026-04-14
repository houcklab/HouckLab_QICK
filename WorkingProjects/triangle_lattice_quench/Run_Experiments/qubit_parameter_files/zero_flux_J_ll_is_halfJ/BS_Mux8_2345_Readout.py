from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import BaseConfig
import numpy as np


Readout_2345_FF = np.array([-12000, 4000, 17468, -7000, -14000, 11500, 1000, -18000])



BS2345_Readout = {
    '1': {'Readout': {'Frequency': 7121.4, 'Gain': 1200,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3725.7, 'sigma': 0.03, 'Gain': 5694},
          'Pulse_FF': Readout_2345_FF},
    '2': {'Readout': {'Frequency': 7078.1, 'Gain': 2100,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4120.9, 'sigma': 0.03, 'Gain': 4861},
          'Pulse_FF': Readout_2345_FF},
    '3': {'Readout': {'Frequency': 7511.4, 'Gain': 2400,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4323.3, 'sigma': 0.03, 'Gain': 5105},
          'Pulse_FF': Readout_2345_FF},
    '4': {'Readout': {'Frequency': 7568.4, 'Gain': 2400,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 2.5, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3853.4, 'sigma': 0.03, 'Gain': 7185},
          'Pulse_FF': Readout_2345_FF},
    '5': {'Readout': {'Frequency': 7363.2, 'Gain': 2100,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3645.3, 'sigma': 0.03, 'Gain': 5507},
          'Pulse_FF': Readout_2345_FF},
    '6': {'Readout': {'Frequency': 7441.9, 'Gain': 1800,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 4229.5, 'sigma': 0.03, 'Gain': 4004},
          'Pulse_FF': Readout_2345_FF},
    '7': {'Readout': {'Frequency': 7254.1, 'Gain': 900,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3974.8, 'sigma': 0.03, 'Gain': 2909},
          'Pulse_FF': Readout_2345_FF},
    '8': {'Readout': {'Frequency': 7308.4, 'Gain': 2100,
                      'FF_Gains': Readout_2345_FF, 'Readout_Time': 3, 'ADC_Offset': 1},
          'Qubit': {'Frequency': 3569.4, 'sigma': 0.03, 'Gain': 4222},
          'Pulse_FF': Readout_2345_FF},
}

