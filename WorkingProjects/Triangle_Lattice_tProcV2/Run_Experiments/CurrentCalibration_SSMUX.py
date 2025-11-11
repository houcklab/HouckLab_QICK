# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mCurrentCalibration_SSMUX import \
    CurrentCalibrationGain, CurrentCalibrationOffset, CurrentCalibrationSingle
from WorkingProjects.Triangle_Lattice_tProcV2.MUXInitialize import *
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX

from qubit_parameter_files.Qubit_Parameters_Master import *


CurrentCalibration = False
# t_evolve: time spent swapping in units of 1/16 clock cycles
# t_BS: beam splitter interaction time in units of 1/16 clock cycles
# sweep gain during beamsplitter interaction
current_calibration_dict = {'reps': 1000, 't_evolve': 225,  't_offset': [0,0,0,-2,0,0,0,0],
                            'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 41}

CurrentCalibration_GainSweep = False
# sweep gain of the first beamsplitter qubit relative to other qubit during beamsplitter interaction and sweep time
# current_calibration_gain_dict = {'reps': 1000, 't_evolve': 0, 't_offset': 0, 'relax_delay': 150, "plotDisp": True,
#                             'gainStart': 5000, 'gainStop': 5400, 'gainNumPoints': 11, 'fixed_gain': -20000,
#                             'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 101,}


# current_calibration_gain_dict = {'swept_index': 1,
#                                 'reps': 100, 't_evolve': 280, 't_offset': [0,0,0,0,0,0,0,0],
#                                  'relax_delay': 100, "plotDisp": True,
#                                 'gainStart': 22300, 'gainStop': 23000, 'gainNumPoints': 11,
#                                 'timeStart': 1, 'timeStop': 2000, 'timeNumPoints': 101,}

current_calibration_gain_dict = {'swept_index': 3,
                                'reps': 100, 't_evolve': 250, 't_offset': [0,0,0,0,0,0,0,0],
                                 'relax_delay': 100, "plotDisp": True,
                                'gainStart': -10000, 'gainStop': -9200, 'gainNumPoints': 11,
                                'timeStart': 1, 'timeStop': 2000, 'timeNumPoints': 101,}


CurrentCalibration_OffsetSweep = True
# t_evolve: time spent swapping in units of 1/16 clock cycles
# sweep t_BS time and sweep offset time


# current_calibration_offset_dict = {'swept_index': 2, 't_offset': [0,0,0,0,0,0,0,0],
#                                    'reps': 100, 't_evolve': 200*3//4, 'relax_delay': 100, "plotDisp": True,
#                                    'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 101,
#                                    'offsetStart': -20, 'offsetStop': 20, 'offsetNumPoints': 41}

current_calibration_offset_dict = {'swept_index': 3, 't_offset': [0,0,0,0,0,0,0,0],
                                   'reps': 100, 't_evolve': 321*3//4, 'relax_delay': 200, "plotDisp": True,
                                   'timeStart': 0, 'timeStop': 1000, 'timeNumPoints': 101,
                                   'offsetStart': -20, 'offsetStop': 20, 'offsetNumPoints': 41}


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

if CurrentCalibration:
    CurrentCalibrationSingle(path="CurrentCalibration_Single", outerFolder=outerFolder,
                          cfg=config | current_calibration_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if CurrentCalibration_GainSweep:
    CurrentCalibrationGain(path="CurrentCalibration_GainSweep", outerFolder=outerFolder,
                          cfg=config | current_calibration_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if CurrentCalibration_OffsetSweep:
    CurrentCalibrationOffset(path="CurrentCalibration_OffsetSweep", outerFolder=outerFolder,
                          cfg=config | current_calibration_offset_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)


