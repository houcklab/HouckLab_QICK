from matplotlib import pyplot as plt

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mCrosstalkRandomFFvsSpec import \
    CrosstalkRandomFFvsSpec
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mFFvsSpec import FFvsSpec
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *


Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7122.3 - BaseConfig['res_LO'], 'Gain': 6000,
                      'FF_Gains': [25000, 0, 0, 0, 0, 0, 0, 0], 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 4022.6, 'sigma': 0.07, 'Gain': 2300},
          'Pulse_FF': [0, -20000, -20000, -20000, -20000, -20000, -20000, -20000]},
    '2': {'Readout': {'Frequency': 7078.2 - BaseConfig['res_LO'], 'Gain': 5000,
                      'FF_Gains': [0, 25000, 0, 0, 0, 0, 0, 0], 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 4039.8, 'sigma': 0.07, 'Gain': 2000},
          'Pulse_FF': [-20000, 0, -20000, -20000, -20000, -20000, -20000, -20000]},
    '3': {'Readout': {'Frequency': 7511.6 - BaseConfig['res_LO'], 'Gain': 4500,
                      'FF_Gains': [0, 0, 25000, 0, 0, 0, 0, 0], 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 3989.1, 'sigma': 0.07, 'Gain': 7700},
          'Pulse_FF': [-20000, -20000, 0, -20000, -20000, -20000, -20000, -20000]},
    '4': {'Readout': {'Frequency': 7568.65 - BaseConfig['res_LO'], 'Gain': 4000,
                      'FF_Gains': [0, 0, 0, 30000, 0, 0, 0, 0], 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 3917.0, 'sigma': 0.07, 'Gain': 3000 / 2},
          'Pulse_FF': [-20000, -20000, -20000, 0, -20000, -20000, -20000, -20000]},
    '5': {'Readout': {'Frequency': 7363.8 - BaseConfig['res_LO'], 'Gain': 5500,
                      'FF_Gains': [0, 0, 0, 0, 25000, 0, 0, 0], 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 4016.1, 'sigma': 0.07, 'Gain': 1800},
          'Pulse_FF': [-20000, -20000, -20000, -20000, 0, -20000, -20000, -20000]},
    '6': {'Readout': {'Frequency': 7442.14 - BaseConfig['res_LO'], 'Gain': 4000,
                      'FF_Gains':[0, 0, 0, 0, 0, 25000, 0, 0], 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 4007.4, 'sigma': 0.07, 'Gain': 5000},
          'Pulse_FF': [-20000, -20000, -20000, -20000, -20000, 0, -20000, -20000]},
    '7': {'Readout': {'Frequency': 7254.4 - BaseConfig['res_LO'], 'Gain': 6000,
                      'FF_Gains': [0, 0, 0, 0, 0, 0, 25000, 0], 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 3953.7, 'sigma': 0.07, 'Gain': 1850},
          'Pulse_FF': [-20000, -20000, -20000, -20000, -20000, -20000, 0, -20000]},
    '8': {'Readout': {'Frequency': 7309.6 - BaseConfig['res_LO'], 'Gain': 4000,
                      'FF_Gains': [0, 0, 0, 0, 0, 0, 0, 30000], 'Readout_Time': 3, 'ADC_Offset': 1, 'cavmin': True},
          'Qubit': {'Frequency': 3945.4, 'sigma': 0.07, 'Gain': 3900 / 2},
          'Pulse_FF': [-20000, -20000, -20000, -20000, -20000, -20000, -20000, 0]},
}


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

for Q in [8]:
    Qubit_Readout = [Q]
    Qubit_Pulse = [Q]
    exec(open("UPDATE_CONFIG.py").read())

    Spec_relevant_params = {
        "qubit_gain": Qubit_Parameters[str(Q)]['Qubit']['Gain']/40, "SpecSpan": 16, "SpecNumPoints": 101,
        'Gauss': False, "sigma": 0.05, "Gauss_gain": 3200,
        'reps': 200,}

    crosstalk_ff_params = {"filename": rf"Z:\QSimMeasurements\Measurements\8QV1_Triangle_Lattice\FF_gain_matrices\random_gains_Q{Q}_tester_3.csv"}


    CrosstalkRandomFFvsSpec(path="CrosstalkFF", cfg=config | Spec_relevant_params | crosstalk_ff_params,
             soc=soc, soccfg=soccfg, outerFolder=outerFolder, prefix=f"Q{Q}").acquire_display_save(plotDisp=True, block=False)

plt.show()
