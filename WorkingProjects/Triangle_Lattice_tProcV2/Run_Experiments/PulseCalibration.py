# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampCurrentCalibration_SSMUX import \
    (RampCurrentCalibrationGain, RampCurrentCalibration1D,RampCurrentCalibration1DShots, RampCurrentCalibrationOffset,
     RampCurrentCalibrationOffset_Multiple, RampCurrentCalibrationTime)
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampExperiments import RampDurationVsPopulation, \
    FFExptVsPopulation, TimeVsPopulation
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mCurrentCorrelations import CurrentCorrelationMeasurement
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mCorrelationExperiments import PopulationShots, RampPopulationShots, OscillationPopulationShots, RampOscillationPopulationShots
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mPulseCalibration import BB1_Base, BB1_SweepGain

import numpy as np


Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7122.2 - BaseConfig["res_LO"], 'Gain': 1200,
                      "FF_Gains": [0, 12000, 0, -12000, 0, 0, 0, 0], "Readout_Time": 3, "ADC_Offset": 1, 'cavmin': True},
          'Qubit': {'Frequency': 4393.15, 'sigma': 0.07, 'Gain': 1920,
                    'Gain_2': 1920, 'Gain_3': 1920*2, 'Gain_4': 1920},
          'Pulse_FF': [0, 12000, 0, -12000, 0, 0, 0, 0]},


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


Qubit_Readout = [1]
Qubit_Pulse = [1]


# simple population experiment after pulse state preparation
run_BB1_base = False
BB1_base_dict = {'reps': 5000, 'relax_delay': 200, 'phase_1': 104.4775, 'phase_2': 313.4325}

# sweep gain of initial naive pi pulse
run_BB1_gain_1_sweep = True
BB1_gain_1_sweep_dict = {'reps': 5000, 'swept_qubit': 1, 'relax_delay': 200,
                         'phase_1': 104.4775, 'phase_2': 313.4325,
                         'swept_qubit_gain_2': 0, 'swept_qubit_gain_3': 0, 'swept_qubit_gain_4': 0,
                         'gainStart': 0, 'gainStop': 2000, 'gainNumPoints': 41}

BB1_gain_1_sweep_dict = {'reps': 5000, 'swept_qubit': 1, 'relax_delay': 200,
                         'phase_1': 104.4775, 'phase_2': 313.4325,
                         'swept_qubit_gain_2': 1920, 'swept_qubit_gain_3': 1920*2, 'swept_qubit_gain_4': 1920,
                         'gainStart': 0, 'gainStop': 4000, 'gainNumPoints': 101}

# sweep gain of second pulse
run_BB1_gain_2_sweep = False
BB1_gain_2_sweep_dict = {'reps': 5000, 'swept_qubit': 1, 'relax_delay': 200,
                         'phase_1': 104.4775, 'phase_2': 313.4325,
                         'swept_qubit_gain_2': 0, 'swept_qubit_gain_3': 0, 'swept_qubit_gain_4': 0,
                         'gainStart': 0, 'gainStop': 3000, 'gainNumPoints': 21}


# sweep gain of third pulse
run_BB1_gain_3_sweep = False
BB1_gain_3_sweep_dict = {'reps': 5000, 'swept_qubit': 1, 'relax_delay': 200,
                         'phase_1': 104.4775, 'phase_2': 313.4325,
                         'swept_qubit_gain_2': 2038, 'swept_qubit_gain_3': 0, 'swept_qubit_gain_4': 0,
                         'gainStart': 1000, 'gainStop': 4500, 'gainNumPoints': 31}

# sweep gain of fourth pulse
run_BB1_gain_4_sweep = False
BB1_gain_4_sweep_dict = {'reps': 5000, 'swept_qubit': 1, 'relax_delay': 200,
                         'phase_1': 104.4775, 'phase_2': 313.4325,
                         'swept_qubit_gain_2': 2038, 'swept_qubit_gain_3': 3493, 'swept_qubit_gain_4': 0,
                         'gainStart': 0, 'gainStop': 5000, 'gainNumPoints': 101}

# This ends the working section of the file.



exec(open("UPDATE_CONFIG.py").read())
exec(open("CALIBRATE_SINGLESHOT_READOUTS.py").read())

# add other pulse gains to config
config['qubit_gains_2'] = [Qubit_Parameters[str(Q)]['Qubit']['Gain_2'] / 32766. for Q in Qubit_Pulse]
config['qubit_gains_3'] = [Qubit_Parameters[str(Q)]['Qubit']['Gain_3'] / 32766. for Q in Qubit_Pulse]
config['qubit_gains_4'] = [Qubit_Parameters[str(Q)]['Qubit']['Gain_4'] / 32766. for Q in Qubit_Pulse]

pulse_calibration_outer_folder = outerFolder + 'pulse_calibration\\'
if run_BB1_base:
    instance = BB1_Base(path="BB1_base", outerFolder=pulse_calibration_outer_folder,
                   cfg=config | BB1_base_dict, soc=soc, soccfg=soccfg)
    instance.acquire_display_save(plotDisp=True)

if run_BB1_gain_1_sweep:
    instance = BB1_SweepGain(path="BB1_gain_1_sweep", outerFolder=pulse_calibration_outer_folder,
                        cfg=config | BB1_gain_1_sweep_dict | {'swept_gain_index': 0}, soc=soc, soccfg=soccfg)
    instance.acquire_display_save(plotDisp=True)

if run_BB1_gain_2_sweep:
    instance = BB1_SweepGain(path="BB1_gain_2_sweep", outerFolder=pulse_calibration_outer_folder,
                        cfg=config | BB1_gain_2_sweep_dict | {'swept_gain_index': 1}, soc=soc, soccfg=soccfg)
    instance.acquire_display_save(plotDisp=True)

if run_BB1_gain_3_sweep:
    instance = BB1_SweepGain(path="BB1_gain_3_sweep", outerFolder=pulse_calibration_outer_folder,
                        cfg=config | BB1_gain_3_sweep_dict | {'swept_gain_index': 2}, soc=soc, soccfg=soccfg)
    instance.acquire_display_save(plotDisp=True)

if run_BB1_gain_4_sweep:
    instance = BB1_SweepGain(path="BB1_gain_4_sweep", outerFolder=pulse_calibration_outer_folder,
                        cfg=config | BB1_gain_4_sweep_dict | {'swept_gain_index': 3}, soc=soc, soccfg=soccfg)
    instance.acquire_display_save(plotDisp=True)


print(config)