# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from matplotlib import pyplot as plt

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampCurrentCalibrationR_SSMUX import \
    RampBeamsplitterGainR, RampBeamsplitterOffsetR, RampBeamsplitterR1D, RampCurrentCorrelationsR
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampCurrentCalibration_SSMUX import \
    (RampCurrentCalibrationGain, RampCurrentCalibration1D,RampCurrentCalibration1DShots, RampCurrentCalibrationOffset,
     RampCurrentCalibrationOffset_Multiple, RampCurrentCalibrationTime)
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampExperiments import RampDurationVsPopulation, \
    FFExptVsPopulation, TimeVsPopulation
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mCurrentCorrelations import CurrentCorrelationMeasurement
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mCorrelationExperiments import PopulationShots, RampPopulationShots, OscillationPopulationShots, RampOscillationPopulationShots

import numpy as np


# Josh parameters
Readout_FF = [5660, 26575, -17231, -5017, 0, 0, 0, 0]
# Readout_FF = [56, 26575, -314, -241, 0, 0, 0, 0]
# (4088.0, 4380.0, 3520.0, 3820.0, 3500.9, 3501.5, 3441.8, 3506.0)

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7121.7 - BaseConfig["res_LO"], 'Gain': 5250,
                      "FF_Gains": Readout_FF, "Readout_Time": 3, "ADC_Offset": 0.5, 'cavmin': True},
          'Qubit': {'Frequency': 4077.2, 'sigma': 0.07, 'Gain': 2388},
          'Pulse_FF': Readout_FF},
    '2': {'Readout': {'Frequency': 7078.3 - BaseConfig["res_LO"], 'Gain': 5200,
                      "FF_Gains": Readout_FF, "Readout_Time": 3.5, "ADC_Offset": 0.5, 'cavmin': True},
          'Qubit': {'Frequency': 4379.9, 'sigma': 0.07, 'Gain': 3200},
          'Pulse_FF': Readout_FF},
    '3': {'Readout': {'Frequency': 7510.55 - BaseConfig["res_LO"], 'Gain': 3200,
                      "FF_Gains": Readout_FF, "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 3624, 'sigma': 0.07, 'Gain': 5000},
          'Pulse_FF': [5660, 26575, -17231 + 5000, -5017, 0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7568.1 - BaseConfig["res_LO"], 'Gain': 6000,
                      "FF_Gains": Readout_FF, "Readout_Time": 3.5, "ADC_Offset": 0.5, 'cavmin': True},
          'Qubit': {'Frequency': 3828.5, 'sigma': 0.07, 'Gain': 3600},
          'Pulse_FF': Readout_FF},
    # Resonant points. Guess: [0,0,0,0]
    '1H': {'Qubit': {'Frequency': 4048.4, 'sigma': 0.07, 'Gain': 3000},
           'Pulse_FF': [56 + 4000, 5, -314, -241, 0, 0, 0, 0]},
    '2H': {'Qubit': {'Frequency': 4043.8, 'sigma': 0.07, 'Gain': 3080},
           'Pulse_FF': [56, 5 + 4000, -314, -241, 0, 0, 0, 0]},
    '3H': {'Qubit': {'Frequency': 4053.2, 'sigma': 0.07, 'Gain': 4050},
           'Pulse_FF': [56, 5, -314 + 4000, -241, 0, 0, 0, 0]},
    '1L': {'Qubit': {'Frequency': 3844.9, 'sigma': 0.07, 'Gain': 4700},
           'Pulse_FF': [56 - 4000, 5, -314, -241, 0, 0, 0, 0]},

    '1HH': {'Qubit': {'Frequency': 4047.3, 'sigma': 0.07, 'Gain': 2700},
            'Pulse_FF': [56 + 4000, 5 - 4000, -314 - 4000, -241, 0, 0, 0, 0]},
    '4HH': {'Qubit': {'Frequency': 3950.3, 'sigma': 0.07, 'Gain': 2200},
            'Pulse_FF': [56 + 4000, 5 - 4000, -314 - 4000, -241, 0, 0, 0, 0]},

}


FF_gain1_expt =  56
FF_gain2_expt =  5
FF_gain3_expt = -314
FF_gain4_expt = -241
FF_gain5_expt =  0
FF_gain6_expt =  0
FF_gain7_expt =  0
FF_gain8_expt =  0

FF_gain1_BS =  17451  # 4300.0
FF_gain2_BS =  17930  # 4300.0
FF_gain3_BS =  -8884  # 3700.0
FF_gain4_BS =  -9834  # 3700.0
FF_gain5_BS =      0  # 3500.9
FF_gain6_BS =      0  # 3501.5
FF_gain7_BS =      0  # 3441.8
FF_gain8_BS =      0  # 3506.0


Qubit_Readout = [1,2,3,4]
Qubit_Pulse = ['1HH', '4HH']


Sweep_BeamsplitterGain = False
sweep_bs_gain_dict = {'swept_qubit': 3, 'reps': 1600, 'ramp_time': 3000,
                      't_offset': [-5,1,-2,3,0,0,0,0], 'relax_delay': 150,
                        'gainStart': -10000, 'gainStop': -8000, 'gainNumPoints': 21,
                        'start': 50, 'step': 8, 'expts': 71}


Sweep_BeamsplitterOffset = False

sweep_bs_offset_dict = {'swept_qubit': 3, 'reps': 100, 'ramp_time': 3000,
                      't_offset': [0,0,0,0,0,0,0,0], 'relax_delay': 200,
                        'offsetStart': -20, 'offsetStop': 20, 'offsetNumPoints': 41,
                        'start': 0, 'step': 8, 'expts': 71}

Beamsplitter1D = False

Run_CurrentCorrelations = True

ramp_beamsplitter_1d_dict = {'reps': 20000, 'ramp_time': 3000,
                        't_offset': [-5,1,-2,3,0,0,0,0], 'relax_delay': 150,
                        'start': 0, 'step': 4, 'expts': 141}



# This ends the working section of the file.
#----------------------------------------

# Translation of Qubit_Parameters dict to resonator and qubit parameters.
# Nothing defined here should be changed in an Experiment unless it is one of the swept variables.
# Update FF_Qubits dict
exec(open("UPDATE_CONFIG.py").read())
# This ends the translation of the Qubit_Parameters dict
#--------------------------------------------------

exec(open("CALIBRATE_SINGLESHOT_READOUTS.py").read())

print(config)

if Sweep_BeamsplitterGain:
    RampBeamsplitterGainR(path="RampBeamsplitterGainR", outerFolder=outerFolder,
                          cfg=config | sweep_bs_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if Sweep_BeamsplitterOffset:
    RampBeamsplitterOffsetR(path="RampBeamsplitterOffsetR", outerFolder=outerFolder,
                          cfg=config | sweep_bs_offset_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if Beamsplitter1D:
    RampBeamsplitterR1D(path="RampBeamsplitterR1D", outerFolder=outerFolder,
                          cfg=config | ramp_beamsplitter_1d_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)

if Run_CurrentCorrelations:
    RampCurrentCorrelationsR(path="RampBeamsplitterCorrelationsR", outerFolder=outerFolder,
                        cfg=config | ramp_beamsplitter_1d_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

plt.show()