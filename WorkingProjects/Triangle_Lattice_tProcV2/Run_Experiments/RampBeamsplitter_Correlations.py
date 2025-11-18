# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mBeamsplitterCorrelations_CleanTiming import \
    CleanTimingCorrelations, CleanTimingCorrelationsDoubleJump, RampBeamsplitterPopulationVsTime
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampCurrentCalibrationR_SSMUX import \
    RampBeamsplitterGainR, RampBeamsplitterOffsetR, RampBeamsplitterR1D, RampCurrentCorrelationsR, RampDoubleJumpGainR, \
    RampDoubleJumpIntermediateSamplesR, RampDoubleJumpR1D, RampDoubleJumpCorrelations, SweepRampLengthCorrelations, \
    RampDoubleJump_BS_GainR, RampCorrelations_Sweep_BS_Gain, RampCorrelations_Sweep_BS_Offset

# from Qubit_Parameters_8QPiFlux import *
# from qubit_parameter_files.Qubit_Parameters_1234 import *
from qubit_parameter_files.Qubit_Parameters_Master import *

print(Expt_FF)

Qubit_Readout = [1,2,3,4,5,6,7,8]
Qubit_Pulse = ['1_4815', '4_4815', '8_4815', '5_4815']
Qubit_Pulse = ['1_4QB', '4_4QB', '8_4QB', '5_4QB']

Qubit_Pulse = ['1_4Q_readout', '4_4Q_readout', '8_4Q_readout', '5_4Q_readout']
# Qubit_Pulse = [1,4,8,5]
# Qubit_Pulse = ['1_4Q_readout', '5_4Q_readout', '8_4Q_readout', '6_4Q_readout']
# Qubit_Pulse = ['2_4Q_readout','3_4Q_readout','6_4Q_readout','7_4Q_readout']

# Qubit_Pulse = ['4_4Q', '5_4Q', '8_4Q', '1_4Q']


Q = 7
# Qubit_Pulse = [Q]
# Qubit_Readout = [Q, Q+1]

Sweep_BeamsplitterGain = False
sweep_bs_gain_dict = {'swept_qubit': Q, 'reps': 200, 'ramp_time': 1000,
                      # 't_offset': [13,15,4,15,10,10,6,0],
                      # 't_offset': [25,27,16,27,10,10,9,0],
                      't_offset': [-1,1-3,3,6,5,-1,1,-2],
                      'relax_delay': 120,
                        'gainStart':  None, 'gainStop': None, 'gainNumPoints': 11,
                        'start': 50, 'step': 8, 'expts': 71}



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
sweep_bs_offset_dict = {'swept_qubit': Q, 'reps': 200, 'ramp_time': 2000,
                        't_offset': [24,26,15,26,10,10,9,0],
                        'relax_delay': 100,
                        'offsetStart': 0, 'offsetStop': 40, 'offsetNumPoints': 41,
                        'start': 0, 'step': 8, 'expts': 71}

Beamsplitter1D = False
Run_CurrentCorrelations = False

ramp_beamsplitter_1d_dict = {'reps': 100000, 'ramp_time': 1000,
                             't_offset':
                             [23, 25, 14, 20, 9, 7, 7, 0],
                             'relax_delay': 180,
                             'start': 0, 'step': 8, 'expts': 71,
                             'readout_pair_1': [4,5],
                             'readout_pair_2': [7,8],
                             }


# ramp_beamsplitter_1d_dict = {'reps': 3000, 'ramp_time': 1000,
#                              't_offset':
#                              # [21, 23, 12, 23, 7, 7, 8, 0],
#                              [28, 30, 19, 30, 7, 7, 8, 0],
#                              'relax_delay': 140,
#                              'start': 0, 'step': 8, 'expts': 71,
#                              'readout_pair_1': [4,5],
#                              'readout_pair_2': [7,8],
#                              }



Run_CurrentCorrelations_CleanTiming = False
# [13,15,4,15,10,10,6,0]

Run_RampBeamsplitterVsTime = False
ramp_beamsplitter_vs_time_dict = {'reps': 5000, 'ramp_time': 1000,
                             't_offset': [24,26,15,26,10,10,9,0],
                             'relax_delay': 100,
                             'start': 0, 'stop': 1500,
                             'ramp_expts': 101, 'BS_expts': 101,
                             }


sweep_ramp_length_correlations = False
sweep_ramp_length_correlations_dict = {'ramp_length_start': 0, 'ramp_length_stop': 3000,
                                       'ramp_length_num_points': 11}

sweep_BS_gain_correlations = False
sweep_BS_gain_correlations_dict = {'swept_qubit': 3, 'reps': 2000,
                                   'gainNumPoints': 11}

center = BS_FF[sweep_BS_gain_correlations_dict['swept_qubit']-1]
# center = -13000
sweep_BS_gain_correlations_dict['gainStart'] = center - 1000
sweep_BS_gain_correlations_dict['gainStop'] = center + 1000


sweep_BS_offset_correlations = False
sweep_BS_offset_correlations_dict = {'swept_qubit': 5, 'reps': 1000,
                                     'offsetStart': 0, 'offsetStop': 22, 'offsetNumPoints': 3,
                                     'gainNumPoints': 11}

# --------------------------------
# Base dict that will be used for all below experiments

Q = 1
# Qubit_Pulse = [Q]
# Qubit_Readout = [Q, Q+1]

double_jump_base = {'reps': 400, 'ramp_time': 1000,
                    't_offset':
                    # [22, 24, 13, 24, 8, 8, 9, 0],
                      [22, 24, 13, 20, 8, 9, 9, 0],
                    'relax_delay': 150,
                    'start': 0, 'step': 16, 'expts': 71,
                    # 1234 BOI
                    'intermediate_jump_samples': [9, 0, 3, 0, 4, 0, 2, 0],
                    'intermediate_jump_gains': [-14300, None, 4490, None, -20347, None, -2370, None]}
                    # 2345 BOI
                    # 'intermediate_jump_samples': [0, 3, 0, 15, 0, 2, 0, 0],
                    # 'intermediate_jump_gains': [None, -2040, None, -13730, None, -5300, None, None]}


Sweep_DoubleJump_BS_Gain = False
double_jump_BS_gain_dict = {'swept_qubit': Q,
                            'gainStart':  -11777 - 2000, 'gainStop': -11777 + 2000,
                            'gainNumPoints': 11}

center = BS_FF[double_jump_BS_gain_dict['swept_qubit']-1]
# center = -13000
double_jump_BS_gain_dict['gainStart'] = center - 1000
double_jump_BS_gain_dict['gainStop'] = center + 1000



Sweep_DoubleJump_IntermediateSamples = False
sweep_intermediate_samples_dict = {
                        'swept_qubit': Q,
                        'samples_start': 0, 'samples_stop': 30,
                        'samples_numPoints': 31}

# sweep_intermediate_samples_dict = {
#                         'swept_qubit': Q,
#                         'samples_start': 30, 'samples_stop': 50,
#                         'samples_numPoints': 21}

Sweep_DoubleJump_IntermediateGain = False
double_jump_intermediate_gain_dict = {'swept_qubit': Q,
                        'gainStart':  -11777 - 2000, 'gainStop': -11777 + 2000,
                         'gainNumPoints': 3 * 21}

center = double_jump_base['intermediate_jump_gains'][double_jump_intermediate_gain_dict['swept_qubit'] - 1]
double_jump_intermediate_gain_dict['gainStart'] = center - 1000
double_jump_intermediate_gain_dict['gainStop'] = center + 1000


# double_jump_gain_dict = {'swept_qubit': 4,
#                         'gainStart':  -4428*2 - 1000, 'gainStop': -4428*2 + 1000, 'gainNumPoints': 21}

# Q3-Q4
# double_jump_gain_dict = {'swept_qubit': 4,
#                         'gainStart':  -9834//2 - 1000, 'gainStop': -9834//2 + 1000, 'gainNumPoints': 21}
                    # gains = None -> do not do a first jump, jump directly from FF_expt --> FF_BS



DoubleJump1D = False

DoubleJump_CurrentCorrelations = True


double_jump_1d_dict = {'reps': 100_000,
                        'start': 0, 'step': 8, 'expts': 71,
                       'readout_pair_1': [1,2],
                       'readout_pair_2': [3,4],}
# double_jump_1d_dict = {'reps': 100000,
#                         'start': 0, 'step': 4, 'expts': 141,
#                        'readout_pair_1': [2,3],
#                        'readout_pair_2': [4,5],}

DoubleJump_Correlations_CleanTiming = False
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
if Run_CurrentCorrelations_CleanTiming:
    CleanTimingCorrelations(path="RampBeamsplitterCleanTiming", outerFolder=outerFolder,
                        cfg=config | ramp_beamsplitter_1d_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)


if Run_RampBeamsplitterVsTime:
    RampBeamsplitterPopulationVsTime(path="RampBeamsplitterPopulationVsTime", outerFolder=outerFolder,
                                cfg=config | ramp_beamsplitter_vs_time_dict,
                                soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)


if sweep_ramp_length_correlations:
    SweepRampLengthCorrelations(path="SweepRampLengthCorrelations", outerFolder=outerFolder,
                             cfg=config | ramp_beamsplitter_1d_dict | sweep_ramp_length_correlations_dict,
                                soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if sweep_BS_gain_correlations:
    RampCorrelations_Sweep_BS_Gain(path="RampCorrelations_Sweep_BS_Gain", outerFolder=outerFolder,
                                cfg=config | ramp_beamsplitter_1d_dict | sweep_BS_gain_correlations_dict,
                                soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if sweep_BS_offset_correlations:
    RampCorrelations_Sweep_BS_Offset(path="RampCorrelations_Sweep_BS_Offset", outerFolder=outerFolder,
                                cfg=config | ramp_beamsplitter_1d_dict | sweep_BS_offset_correlations_dict,
                                soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)


# if Sweep_CurrentCorrelations_Ramp_Length:

if Sweep_DoubleJump_BS_Gain:
    RampDoubleJump_BS_GainR(path="RampDoubleJump_BS_GainR", outerFolder=outerFolder,
                          cfg=config | double_jump_base | double_jump_BS_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if Sweep_DoubleJump_IntermediateSamples:
    RampDoubleJumpIntermediateSamplesR(path="RampDoubleJumpIntermediateLength", outerFolder=outerFolder,
                          cfg=config | double_jump_base | sweep_intermediate_samples_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)

if Sweep_DoubleJump_IntermediateGain:
    RampDoubleJumpGainR(path="RampDoubleJumpGainR", outerFolder=outerFolder,
                        cfg=config | double_jump_base | double_jump_intermediate_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True)


if DoubleJump1D:
    RampDoubleJumpR1D(path="RampDoubleJump1D", outerFolder=outerFolder,
                      cfg=config | double_jump_base | double_jump_1d_dict, soc=soc, soccfg=soccfg,).acquire_display_save(plotDisp=True)

if DoubleJump_CurrentCorrelations:
    RampDoubleJumpCorrelations(path="RampDoubleJumpCurrentCorrelations", outerFolder=outerFolder,
                      cfg=config | double_jump_base | double_jump_1d_dict, soc=soc, soccfg=soccfg,).acquire_display_save(plotDisp=True)

if DoubleJump_Correlations_CleanTiming:
    CleanTimingCorrelationsDoubleJump(path="RampDoubleJumpCleanTiming", outerFolder=outerFolder,
                               cfg=config | double_jump_base | double_jump_1d_dict, soc=soc,
                               soccfg=soccfg, ).acquire_display_save(plotDisp=True)

plt.show()