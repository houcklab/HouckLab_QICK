import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7121.5, 'Gain': 800,
                      "FF_Gains": [0, 4087, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1., 'cavmin': True},
          'Qubit': {'Frequency': 3798.9, 'sigma': 0.05, 'Gain': 2744},
          'Pulse_FF': [0, -4087, 0, 0, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7077.55, 'Gain': 800,
                      "FF_Gains": [0, 4087, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1., 'cavmin': True},
          'Qubit': {'Frequency': 3898.3, 'sigma': 0.05, 'Gain': 3100},
          'Pulse_FF': [0, -4087, 0, 0, 0, 0, 0, 0]},
    '2R': {'Qubit': {'Frequency': 3799.4, 'sigma': 0.05, 'Gain':2768},
          'Pulse_FF': [-4000, -43, 0, 0, 0, 0, 0, 0]},

    '3': {'Readout': {'Frequency': 7511.0, 'Gain': 500,
                      "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3.0, "ADC_Offset": 0.9, 'cavmin': True},
          'Qubit': {'Frequency': 3989.2, 'sigma': 0.05, 'Gain': 9730},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568.5, 'Gain': 500,
                          "FF_Gains": [0, 0, 0, 0, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 0.9, 'cavmin': True},
              'Qubit': {'Frequency': 4047.7, 'sigma': 0.05, 'Gain': 4500},
            'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
}
Expt_FF = [0,0,0,0,0,0,0,0]

FF_gain1_expt = 0
FF_gain2_expt = -43
FF_gain3_expt = 0
FF_gain4_expt = 0
FF_gain5_expt = 0
FF_gain6_expt = 0
FF_gain7_expt = 0
FF_gain8_expt = 0

FF_gain1_BS = 0
FF_gain2_BS = 0
FF_gain3_BS = 0
FF_gain4_BS = 0
FF_gain5_BS = 0
FF_gain6_BS = 0
FF_gain7_BS = 0
FF_gain8_BS = 0