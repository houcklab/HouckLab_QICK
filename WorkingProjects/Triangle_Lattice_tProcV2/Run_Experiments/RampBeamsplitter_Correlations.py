# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from matplotlib import pyplot as plt

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampCurrentCalibrationR_SSMUX import \
    RampBeamsplitterGainR, RampBeamsplitterOffsetR, RampBeamsplitterR1D, RampCurrentCorrelationsR, RampDoubleJumpGainR, \
    RampDoubleJumpIntermediateSamplesR, RampDoubleJumpR1D, RampDoubleJumpCorrelations

# from Qubit_Parameters_8QPiFlux import *
from qubit_parameter_files.Qubit_Parameters_1234 import *

Qubit_Readout = [1,2,3,4]
Qubit_Pulse = ['4HHH', '1HHH', '5HHH']


Sweep_BeamsplitterGain = True
# Q2-Q3
sweep_bs_gain_dict = {'swept_qubit': 2, 'reps': 200, 'ramp_time': 3000,
                      't_offset': [0,0,0,0,0,0,0,0], 'relax_delay': 150,
                        'gainStart':  22734 - 3000 , 'gainStop': 22734 + 3000, 'gainNumPoints': 11,
                        'start': 50, 'step': 12, 'expts': 71}


# sweep_bs_gain_dict = {'swept_qubit': 4, 'reps': 1, 'ramp_time': 1,
#                       't_offset': [0,0,0,0,0,0,0,0], 'relax_delay': 1,
#                         'gainStart':  -16119 - 1000, 'gainStop': -16119 + 1000, 'gainNumPoints': 11,
#                         'start': 50, 'step': 12, 'expts': 11}



Sweep_BeamsplitterOffset = False

# Think about how t_offset will cause some qubits to stay at FF_BS for longer than others
sweep_bs_offset_dict = {'swept_qubit': 2, 'reps': 200, 'ramp_time': 3000,
                      't_offset': [0,2,0,11,0,0,0,0], 'relax_delay': 100,
                        'offsetStart': -20, 'offsetStop': 20, 'offsetNumPoints': 41,
                        'start': 0, 'step': 8, 'expts': 71}

Beamsplitter1D = False

Run_CurrentCorrelations = False

ramp_beamsplitter_1d_dict = {'reps': 17000, 'ramp_time': 3000,
                        't_offset':  [0,11,3,5,0,0,0,0],
                             'relax_delay': 100,
                        'start': 0, 'step': 8, 'expts': 201}

# --------------------------------
# Base dict that will be used for all below experiments

double_jump_base = {'reps': 500, 'ramp_time': 3000,
                      't_offset': [0+9,2+9,0,11,0,0,0,0], 'relax_delay': 150,
                        'start': 0, 'step': 16, 'expts': 71,
                    'intermediate_jump_samples': [0, 23, 0, 9, 0, 0, 0, 0],
                    'intermediate_jump_gains': [None, 9900, None, -200, None, None, None, None]}





Sweep_DoubleJump_IntermediateSamples = False
sweep_intermediate_samples_dict = {
                        'swept_qubit': 2,
                        'samples_start': 0, 'samples_stop': 30,
                        'samples_numPoints': 31}

Sweep_DoubleJumpGain = False
# Q1-Q2
double_jump_gain_dict = {'swept_qubit': 2,
                        'gainStart':  10089 - 2000, 'gainStop': 10089 + 2000, 'gainNumPoints': 21}

# double_jump_gain_dict = {'swept_qubit': 4,
#                         'gainStart':  -4428*2 - 1000, 'gainStop': -4428*2 + 1000, 'gainNumPoints': 21}

# Q3-Q4
# double_jump_gain_dict = {'swept_qubit': 4,
#                         'gainStart':  -9834//2 - 1000, 'gainStop': -9834//2 + 1000, 'gainNumPoints': 21}
                    # gains = None -> do not do a first jump, jump directly from FF_expt --> FF_BS



DoubleJump1D = False

DoubleJump_CurrentCorrelations = True

double_jump_1d_dict = {'reps': 5000,
                        'start': 0, 'step': 4, 'expts': 201}

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


if Sweep_DoubleJumpGain:
    RampDoubleJumpGainR(path="RampDoubleJumpGainR", outerFolder=outerFolder,
                          cfg=config | double_jump_base | double_jump_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if Sweep_DoubleJump_IntermediateSamples:
    RampDoubleJumpIntermediateSamplesR(path="RampDoubleJumpIntermediateLength", outerFolder=outerFolder,
                          cfg=config | double_jump_base | sweep_intermediate_samples_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if DoubleJump1D:
    RampDoubleJumpR1D(path="RampDoubleJump1D", outerFolder=outerFolder,
                      cfg=config | double_jump_base | double_jump_1d_dict, soc=soc, soccfg=soccfg,).acquire_display_save(plotDisp=True)

if DoubleJump_CurrentCorrelations:
    RampDoubleJumpCorrelations(path="RampDoubleJumpCurrentCorrelations", outerFolder=outerFolder,
                      cfg=config | double_jump_base | double_jump_1d_dict, soc=soc, soccfg=soccfg,).acquire_display_save(plotDisp=True)
plt.show()