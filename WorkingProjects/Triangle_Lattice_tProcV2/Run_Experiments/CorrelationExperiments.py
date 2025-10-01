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

import numpy as np


from qubit_parameter_files.Qubit_Parameters_Master import *


Qubit_Readout = [1,2,3,4,5,6,7,8]
Qubit_Pulse = ['4_4815', '8_4815', '1_4815', '5_4815']


# simple population experiment after pulse state preparation
run_population_shots = True
population_shots_dict = {'reps': 5000, 'relax_delay': 200}

run_oscillation_population_shots = False
oscillation_population_shots_dict = {'reps': 5000,
                                     'start': 1, 'step': 8, 'expts': 201,
                                     'relax_delay': 200, 'res_length':10}



# experiment to measure population shots after adiabatic ramp
run_ramp_population_shots = False
ramp_population_shots_dict = {'reps': 5000, 'ramp_duration': 3000, 'relax_delay': 200}


# adiabatic ramp into beamsplitter current correlation measurement
run_ramp_oscillation_population_shots = False
ramp_oscillation_population_shots_dict = {'reps': 4000,
                                          't_offset': [-5, 1, -6, 7, 0, 0, 0, 0],
                                          'ramp_time': 2000, 'relax_delay': 200,
                                          'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 101}

# full current correlation measurement
run_1D_current_calib_shots = False
current_calibration_dict_shots = {'reps': 4000,
                                  't_offset': [-5, 1, -6, 7, 0, 0, 0, 0],
                                  'ramp_time': 3000, 'relax_delay': 200,
                                  'timeStart': 0, 'timeStop': 500, 'timeNumPoints': 101}



# This ends the working section of the file.
exec(open("UPDATE_CONFIG.py").read())
exec(open("CALIBRATE_SINGLESHOT_READOUTS.py").read())

if run_population_shots:
    instance = PopulationShots(path="PopulationShots", outerFolder=outerFolder,
                   cfg=config | population_shots_dict, soc=soc, soccfg=soccfg)
    instance.acquire_display_save(plotDisp=True)

if run_oscillation_population_shots:
    instance = OscillationPopulationShots(path="OscillationPopulationShots", outerFolder=outerFolder,
                   cfg=config | oscillation_population_shots_dict, soc=soc, soccfg=soccfg)
    instance.acquire_save(plotDisp=False)

if run_ramp_population_shots:
    instance = RampPopulationShots(path="RampPopulationShots", outerFolder=outerFolder,
                   cfg=config | ramp_population_shots_dict, soc=soc, soccfg=soccfg)
    instance.acquire_display_save(plotDisp=True)

if run_ramp_oscillation_population_shots:
    instance = RampOscillationPopulationShots(path="RampOscillationPopulationShots", outerFolder=outerFolder,
                                   cfg=config | ramp_oscillation_population_shots_dict, soc=soc, soccfg=soccfg)
    instance.acquire_save(plotDisp=False)


if run_1D_current_calib_shots:
    instance=RampCurrentCalibration1DShots(path="CurrentCalibration_1D_Shots", outerFolder=outerFolder,
                             cfg=config | current_calibration_dict_shots, soc=soc, soccfg=soccfg)
    instance.acquire_save(plotDisp=False, plotSave=False)

print(config)