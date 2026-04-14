'''
File for doing qubit spec sweeps over FF gain -> calibrate flux quantum and flux offset in RFSoC gain
'''

from matplotlib import pyplot as plt

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mSpecVsFF import SpecVsFF
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *


Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7122.6, 'Gain': 1500,
                      'FF_Gains': [0, 0, 20000, 20000, 20000, 20000, 20000, 20000], 'Readout_Time': 3, 'ADC_Offset': 1,
                      'cavmin': True},
          'Qubit': {'Frequency': 3950, 'sigma': 0.07, 'Gain': 1200},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7077.9, 'Gain': 1000,
                      'FF_Gains': [20000, 0, 20000, 20000, 20000, 20000, 20000, 20000], 'Readout_Time': 3,
                      'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 3950, 'sigma': 0.07, 'Gain': 1200},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7511.23, 'Gain': 1500,
                      'FF_Gains': [20000, 0, 0, 20000, 20000, 20000, 20000, 20000], 'Readout_Time': 3, 'ADC_Offset': 1,
                      'cavmin': True},
          'Qubit': {'Frequency': 3950, 'sigma': 0.07, 'Gain': 1200},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568.65, 'Gain': 1200,
                      'FF_Gains': [20000, 0, 20000, 0, 20000, 20000, 20000, 20000], 'Readout_Time': 3, 'ADC_Offset': 1,
                      'cavmin': True},
          'Qubit': {'Frequency': 3950, 'sigma': 0.07, 'Gain': 1200},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '5': {'Readout': {'Frequency': 7363.46, 'Gain': 2000,
                      'FF_Gains': [20000, 0, 20000, 20000, 0, 20000, 20000, 20000], 'Readout_Time': 3, 'ADC_Offset': 1,
                      'cavmin': True},
          'Qubit': {'Frequency': 3950, 'sigma': 0.07, 'Gain': 3200},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '6': {'Readout': {'Frequency': 7441.54, 'Gain': 1000,
                      'FF_Gains': [20000, 0, 20000, 20000, 20000, 0, 20000, 20000], 'Readout_Time': 3, 'ADC_Offset': 1,
                      'cavmin': True},
          'Qubit': {'Frequency': 3950, 'sigma': 0.07, 'Gain': 1200},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '7': {'Readout': {'Frequency': 7254.06, 'Gain': 900,
                      'FF_Gains': [20000, 0, 20000, 20000, 20000, 20000, 0, 20000], 'Readout_Time': 3, 'ADC_Offset': 1,
                      'cavmin': True},
          'Qubit': {'Frequency': 3950, 'sigma': 0.07, 'Gain': 1200},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
    '8': {'Readout': {'Frequency': 7309.23, 'Gain': 900,
                      'FF_Gains': [20000, 0, 20000, 20000, 20000, 20000, 20000, 0], 'Readout_Time': 3, 'ADC_Offset': 1,
                      'cavmin': True},
          'Qubit': {'Frequency': 3950, 'sigma': 0.07, 'Gain': 1200},
          'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
}

# Qubit_Parameters = {
#     '8': {'Readout': {'Frequency': 7309.53, 'Gain': 1000,
#                       'FF_Gains': [0, 0, 0, 0, 0, 0, 0, 0], 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
#           'Qubit': {'Frequency': 3950, 'sigma': 0.07, 'Gain': 1200},
#           'Pulse_FF': [0, 0, 0, 0, 0, 0, 0, 0]},
# }


FF_gain1_expt = 0
FF_gain2_expt = 0
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

# for Q in range(1,9):
#     Qubit_Readout = [Q]
#     Qubit_Pulse = [Q]
#
#     fig, axs = plt.subplots(3,3,figsize=(10,10))
#     axs = [ax for xs in axs for ax in xs]
#
#     Spec_relevant_params = {
#         # "qubit_gain": 500, "SpecSpan":550, "SpecNumPoints": 1101,
#         #   "qubit_gain": 1000, "SpecSpan": 200, "SpecNumPoints": 71,
#         # "qubit_gain": 500, "SpecSpan": 50, "SpecNumPoints": 71,
#         "qubit_gain": 100, "SpecSpan": 550, "SpecNumPoints": 41,
#         'Gauss': False, "sigma": 0.05, "Gauss_gain": 3200,
#         'reps': 10, 'rounds': 10}
#
#     for i in range(8):
#         if i != Q-1:
#             FF_sweep_spec_relevant_params = {"qubit_FF_index": i+1,
#                                         "FF_gain_start": -32000, "FF_gain_stop": 32000, "FF_gain_steps": 2}
#             exec(open("UPDATE_CONFIG.py").read())
#
#
#             SpecVsFF(path="SpecVsFF", cfg=config | Spec_relevant_params | FF_sweep_spec_relevant_params,
#                      soc=soc, soccfg=soccfg, outerFolder=outerFolder).acquire_display_save(fig_axs=(fig, [axs[i]]), plotDisp=True, block=False if Q < 8 else True)
#

for Q in [3,4,5,6,7,8]:
    Qubit_Readout = [Q]
    Qubit_Pulse = [Q]

    Spec_relevant_params = {
        # "qubit_gain": 100, "SpecSpan":150, "SpecNumPoints": 301,
          "qubit_gain": 100, "SpecSpan": 550, "SpecNumPoints": 1001,
        # "qubit_gain": 400, "SpecSpan": 550, "SpecNumPoints": 251,
        # "qubit_gain": 100, "SpecSpan": 20, "SpecNumPoints": 71,
        'Gauss': False, "sigma": 0.05, "Gauss_gain": 3200,
        'relax_delay': 150,
        'reps': 144*2}

    FF_sweep_spec_relevant_params = {"qubit_FF_index": Q,
                                "FF_gain_start": -32000, "FF_gain_stop": 32000, "FF_gain_steps": 41}
    # FF_sweep_spec_relevant_params = {"qubit_FF_index": Q,
    #                                  "FF_gain_start": -25000, "FF_gain_stop": +25000, "FF_gain_steps": 2}

    exec(open("UPDATE_CONFIG.py").read())

    SpecVsFF(path="FF_vs_Spec", cfg=config | Spec_relevant_params | FF_sweep_spec_relevant_params,
             soc=soc, soccfg=soccfg, outerFolder=outerFolder, prefix=f"Q{Q}").acquire_display_save(plotDisp=True, block=False if Q < 8 else True)

plt.show()