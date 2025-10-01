# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')
from matplotlib import pyplot as plt

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampCurrentCalibrationR_SSMUX import \
    RampBeamsplitterGainR, RampBeamsplitterOffsetR, RampBeamsplitterR1D, RampCurrentCorrelationsR, RampDoubleJumpGainR, \
    RampDoubleJumpIntermediateSamplesR, RampDoubleJumpR1D, RampDoubleJumpCorrelations, SweepRampLengthCorrelations, \
    RampDoubleJump_BS_GainR

# from Qubit_Parameters_8QPiFlux import *
# from qubit_parameter_files.Qubit_Parameters_1234 import *
from qubit_parameter_files.Qubit_Parameters_Master import *

print(Expt_FF)

Qubit_Readout = [1,2,3,4,5,6,7,8]
# Qubit_Readout = [1,2]
Qubit_Pulse = ['4_4815', '8_4815', '1_4815', '5_4815']

Sweep_BeamsplitterGain = False
sweep_bs_gain_dict = {'swept_qubit': 7, 'reps': 600, 'ramp_time': 200,
                      't_offset': [0,0,4,5,5,-1,1,-2], 'relax_delay': 150,
                        'gainStart':  -18386 - 1000 , 'gainStop': -18386 + 1000, 'gainNumPoints': 11,
                        'start': 50, 'step': 12, 'expts': 71}

center = BS_FF[sweep_bs_gain_dict['swept_qubit']-1]
# center = -13000
sweep_bs_gain_dict['gainStart'] = center - 1000
sweep_bs_gain_dict['gainStop'] = center + 1000


# sweep_bs_gain_dict = {'swept_qubit': 4, 'reps': 1, 'ramp_time': 1,
#                       't_offset': [0,0,0,0,0,0,0,0], 'relax_delay': 1,
#                         'gainStart':  -16119 - 1000, 'gainStop': -16119 + 1000, 'gainNumPoints': 11,
#                         'start': 50, 'step': 12, 'expts': 11}



Sweep_BeamsplitterOffset = False

# Think about how t_offset will cause some qubits to stay at FF_BS for longer than others
sweep_bs_offset_dict = {'swept_qubit': 7, 'reps': 200, 'ramp_time': 2000,
                      't_offset': [9,11,0,11,3,3,0,0], 'relax_delay': 100,
                        'offsetStart': -20, 'offsetStop': 20, 'offsetNumPoints': 41,
                        'start': 0, 'step': 8, 'expts': 71}

Beamsplitter1D = False

Run_CurrentCorrelations = True

ramp_beamsplitter_1d_dict = {'reps': 10000, 'ramp_time': 200,
                             't_offset':
                                 #[13,19,16,21,10,10,0,1],# [0,11,3,5,0,0,0,0],
                             [13,15,4,15,10,10,6,0],
                             'relax_delay': 100,
                             'start': 0, 'step': 2, 'expts': 101,
                             'readout_pair_1': [1,2],
                             'readout_pair_2': [5,6],
                             }


ramp_beamsplitter_1d_dict = {'reps': 5000, 'ramp_time': 1000,
                             't_offset':
                                 #[13,19,16,21,10,10,0,1],# [0,11,3,5,0,0,0,0],
                             [13,15,4,15,10,10,6,0],
                             'relax_delay': 100,
                             'start': 0, 'step': 4, 'expts': 71,
                             'readout_pair_1': [1,2],
                             'readout_pair_2': [3,4],
                             }

sweep_ramp_length_correlations = False
sweep_ramp_length_correlations_dict = {'ramp_length_start': 0, 'ramp_length_stop': 500,
                                       'ramp_length_num_points': 21}

# --------------------------------
# Base dict that will be used for all below experiments

double_jump_base = {'reps': 400, 'ramp_time': 1000,
                      't_offset': [13,15,4,15,10,10,6,0], 'relax_delay': 150,
                        'start': 0, 'step': 16, 'expts': 71,
                    'intermediate_jump_samples': [31, 0, 36, 0, 17, 0, 19, 0],
                    'intermediate_jump_gains': [-13344, None, 8565, None, -4754, None, 19250, None]}


Sweep_DoubleJump_BS_Gain = False
double_jump_BS_gain_dict = {'swept_qubit': 1,
                            'gainStart':  -11777 - 2000, 'gainStop': -11777 + 2000,
                            'gainNumPoints': 11}

center = BS_FF[double_jump_BS_gain_dict['swept_qubit']-1]
# center = -13000
double_jump_BS_gain_dict['gainStart'] = center - 1000
double_jump_BS_gain_dict['gainStop'] = center + 1000



Sweep_DoubleJump_IntermediateSamples = False
sweep_intermediate_samples_dict = {
                        'swept_qubit': 5,
                        'samples_start': 0, 'samples_stop': 25,
                        'samples_numPoints': 26}

Sweep_DoubleJumpGain = False
double_jump_gain_dict = {'swept_qubit': 5,
                        'gainStart':  -11777 - 2000, 'gainStop': -11777 + 2000, 'gainNumPoints': 21}

center = double_jump_base['intermediate_jump_gains'][double_jump_gain_dict['swept_qubit']-1]
double_jump_gain_dict['gainStart'] = center - 1000
double_jump_gain_dict['gainStop'] = center + 1000


# double_jump_gain_dict = {'swept_qubit': 4,
#                         'gainStart':  -4428*2 - 1000, 'gainStop': -4428*2 + 1000, 'gainNumPoints': 21}

# Q3-Q4
# double_jump_gain_dict = {'swept_qubit': 4,
#                         'gainStart':  -9834//2 - 1000, 'gainStop': -9834//2 + 1000, 'gainNumPoints': 21}
                    # gains = None -> do not do a first jump, jump directly from FF_expt --> FF_BS



DoubleJump1D = False

DoubleJump_CurrentCorrelations = False

double_jump_1d_dict = {'reps': 1000,
                        'start': 0, 'step': 4, 'expts': 201//3,
                       'readout_pair_1': [1,2],
                       'readout_pair_2': [3,4],}

# This ends the working section of the file.
#----------------------------------------

# Translation of Qubit_Parameters dict to resonator and qubit parameters.
# Nothing defined here should be changed in an Experiment unless it is one of the swept variables.
# Update FF_Qubits dict
exec(open("UPDATE_CONFIG.py").read())
# This ends the translation of the Qubit_Parameters dict
#--------------------------------------------------

exec(open("CALIBRATE_SINGLESHOT_READOUTS.py").read())


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

if sweep_ramp_length_correlations:
    SweepRampLengthCorrelations(path="SweepRampLengthCorrelations", outerFolder=outerFolder,
                             cfg=config | ramp_beamsplitter_1d_dict | sweep_ramp_length_correlations_dict,
                                soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

# if Sweep_CurrentCorrelations_Ramp_Length:

if Sweep_DoubleJump_BS_Gain:
    RampDoubleJump_BS_GainR(path="RampDoubleJump_BS_GainR", outerFolder=outerFolder,
                          cfg=config | double_jump_base | double_jump_BS_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)


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