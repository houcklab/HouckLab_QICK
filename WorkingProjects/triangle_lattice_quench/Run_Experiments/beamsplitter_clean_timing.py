'''Run experiments taking the clean timing experiment to be the base for gain and offset sweeps.
    Includes double jump functionality; treat single jump as a special case with intermediate jump gain == None.

    - Joshua 11/29/25'''

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mBSDoubleJump_CleanTiming import \
    BSClean_Correlations, BSClean_offset, BSClean_BSGain, BSClean_ISamples, BSClean_IGain, BSClean
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampCurrentCalibrationR_SSMUX import \
    RampBeamsplitterOffsetR, RampBeamsplitterGainR, RampDoubleJumpGainR, RampDoubleJumpIntermediateSamplesR

from qubit_parameter_files.Qubit_Parameters_Master import *

class BS:
    def __init__(self, Readout, beamsplitter_point, rung_list):
        self.Readout = Readout
        self.beamsplitter_point = beamsplitter_point
        self.rung_list = rung_list

BS_list = [
    BS(BS1234_Readout, '1234_correlations', ['12','34','65','78']), #0
    BS(BS1245_Readout, '1245_correlations', ['12','45']),           #1
    BS(BS1267_Readout, '1267_correlations', ['12','67']),           #2
    BS(BS2345_Readout, '2345_correlations', ['23','45','67']),      #3
    BS(BS2356_Readout, '2356_correlations', ['23','65']),           #4
    BS(BS2378_Readout, '2378_correlations', ['23','78']),           #5
    BS(BS3467_Readout, '3467_correlations', ['34','67']),           #6
    BS(BS4578_Readout, '4578_correlations', ['45','78']),           #7
]

# ijumps that need calibration
BS_list = [
    BS(BS1234_Readout, '1234_correlations', ['21','34','78']), #0
    BS(BS1245_Readout, '1245_correlations', ['21']),           #1
    BS(BS1267_Readout, '1267_correlations', ['21','76']),           #2
    BS(BS2345_Readout, '2345_correlations', ['32','76']),      #3
    BS(BS2356_Readout, '2356_correlations', ['32']),           #4
    BS(BS2378_Readout, '2378_correlations', ['32','78']),           #5
    BS(BS3467_Readout, '3467_correlations', ['34','76']),           #6
    BS(BS4578_Readout, '4578_correlations', ['78']),           #7
]

# for bond orders
BS_list = [
    BS(BS1234_Readout, '1234_correlations', ['21','34','56','78']), #0
    BS(BS1245_Readout, '1245_correlations', ['21']),           #1
    BS(BS1267_Readout, '1267_correlations', ['21','67']),           #2
    BS(BS2345_Readout, '2345_correlations', ['32','45','76']),      #3
    BS(BS2356_Readout, '2356_correlations', ['32']),           #4
    BS(BS2378_Readout, '2378_correlations', ['32','78']),           #5
    BS(BS3467_Readout, '3467_correlations', ['34','67']),           #6
    BS(BS4578_Readout, '4578_correlations', ['78']),           #7
]
#
BS_list = [
    BS(BS1234_Readout, '1234_correlations', ['12','43','65','87']), #0
    BS(BS1245_Readout, '1245_correlations', ['21']),           #1
    BS(BS1267_Readout, '1267_correlations', ['21','67']),           #2
    BS(BS2345_Readout, '2345_correlations', ['23','54','67']),      #3
    BS(BS2356_Readout, '2356_correlations', ['32']),           #4
    BS(BS2378_Readout, '2378_correlations', ['32','78']),           #5
    BS(BS3467_Readout, '3467_correlations', ['34','67']),           #6
    BS(BS4578_Readout, '4578_correlations', ['78']),           #7
]

#19 rungs total

Qubit_Readout = [1,2,3,4,5,6,7,8]
Qubit_Pulse = ['1_4Q_readout', '4_4Q_readout', '8_4Q_readout', '5_4Q_readout']
# Qubit_Pulse = [1,4,8,5]



for j in [0]:
    BS = BS_list[j]
    readout_params = BS.Readout#TEST_Readout
    beamsplitter_point =  BS.beamsplitter_point#[:5] + 'bonds'
    rungs = BS.rung_list

    # rungs = ['3']
    # rungs = ['78']
    Qubit_Parameters |= readout_params

    # rungs = ['21','34','65', '78']
    # rungs = ['65', '78']
    # rungs = ['23', '76']
    # rungs = ['4','1']
    # rungs = ['78']
    # rungs = ['34']
    # rungs = [-2, -1, 0, 1, 2]
    Q2_states = True
    rungs = ['65']
    # rungs = ['2', '1']
    # rungs = ['21', '43', '87']
    # rungs = ['3', '4', '0', '1']
    print(beamsplitter_point)
    print('rungs:', rungs)
    for rung in rungs:
        Q = int(rung[0])
        # Qubit_Readout = [int(rung[0]), int(rung[1])]

        if Q2_states:
            Qubit_Readout = [int(rung[0]), int(rung[1])]
            Qubit_Pulse = [int(rung[0])]
            Ramp_state = ''.join(sorted(rung))

        else:
            #Q-1, so 1 indexed
            # Ramp_state = ['8Q_4815','2345_dis10', '8Q_4815',
                          # '8Q_4815_lowest','2345_dis10_lowest', '8Q_4815_lowest',][Q-1]
            # Ramp_state = '2345_dis10'
            Ramp_state = '8Q_4815'

        Init_FF = Qubit_Parameters[Ramp_state]['Ramp']['Init_FF']
        Ramp_FF = Qubit_Parameters[Ramp_state]['Ramp']['Expt_FF']

        BS_FF = Qubit_Parameters[beamsplitter_point]['BS']['BS_FF']

        FF_gain1_expt = Ramp_FF[0]  # resonance
        FF_gain2_expt = Ramp_FF[1]  # resonance
        FF_gain3_expt = Ramp_FF[2]  # resonance
        FF_gain4_expt = Ramp_FF[3]  # resonance
        FF_gain5_expt = Ramp_FF[4]  # resonance
        FF_gain6_expt = Ramp_FF[5]  # resonance
        FF_gain7_expt = Ramp_FF[6]  # resonance
        FF_gain8_expt = Ramp_FF[7]  # resonance

        FF_gain1_BS = BS_FF[0]
        FF_gain2_BS = BS_FF[1]
        FF_gain3_BS = BS_FF[2]
        FF_gain4_BS = BS_FF[3]
        FF_gain5_BS = BS_FF[4]
        FF_gain6_BS = BS_FF[5]
        FF_gain7_BS = BS_FF[6]
        FF_gain8_BS = BS_FF[7]

        double_jump_base = {'reps': 400, 'ramp_time': 1000,
                            't_offset':
                            # [0] * 8,
                            # [22, 24, 13, 24, 8, 8, 9, 0],
                                Qubit_Parameters[beamsplitter_point]['t_offset'],
                            'relax_delay': 180,
                            'start': 0, 'step': 8, 'expts': 71,
                            'intermediate_jump_samples': Qubit_Parameters[beamsplitter_point].get('ij_samples',[None]*8),
                            'intermediate_jump_gains':   Qubit_Parameters[beamsplitter_point].get('ij_gains',[None]*8),
                            'bs_samples': Qubit_Parameters[beamsplitter_point].get('pad_bs',[0]*8),
                            }
        print(double_jump_base['intermediate_jump_gains'])
        print(double_jump_base['intermediate_jump_samples'])
        # 'pad_bs' accounts for the intermediate jump samples where a qubit does not get to swap with its partner

        # "good" offsets = [22, 24, 13, 24, 8, 8, 9, 0]
        Sweep_BeamsplitterOffset = True
        Sweep_BeamsplitterOffset_tprocSweep = False
        sweep_bs_offset_dict = {'swept_qubit': Q, 'reps': 2000, 'offsetStep': 1,
                                'intermediate_jump_samples': [0]*8,
                                'bs_samples':[0]*8,

                                'offsetStart': Qubit_Parameters[beamsplitter_point]['t_offset'][Q-1]-2*15,
                                'offsetStop': Qubit_Parameters[beamsplitter_point]['t_offset'][Q-1]+2*15,
                                'start': 0, 'step': 4, 'expts': 162}

        # sweep_bs_offset_dict = {'swept_qubit': Q, 'reps': 1600, 'offsetStep': 1,
        #                         'intermediate_jump_samples': [0] * 8,
        #                         'bs_samples': [0] * 8,
        #
        #                         'offsetStart': Qubit_Parameters[beamsplitter_point]['t_offset'][Q - 1] - 30,
        #                         'offsetStop': Qubit_Parameters[beamsplitter_point]['t_offset'][Q - 1] + 30,
        #                         'start': 0, 'step': 1, 'expts': 71}

        Sweep_BeamsplitterGain = False
        Sweep_BeamsplitterGain_tprocSweep = False
        sweep_bs_gain_dict = {'swept_qubit': Q, 'gainNumPoints': 11,
                              # 't_offset':[0,0,0,0,0,3,0,0],
                              # 't_offset': [2, 1, 6, 6, 8, -1, 1, -2],
                              # 'intermediate_jump_samples': [0] * 8,
                              # 'bs_samples': [0] * 8,
                                    'gainStart':  BS_FF[Q-1] - 1000,
                                    'gainStop': BS_FF[Q-1] + 1000,
                              'start':40}


        Sweep_IntermediateSamples = False
        Sweep_IntermediateSamples_tprocSweep = False
        sweep_intermediate_samples_dict = {'swept_qubit': Q, 'samples_step': 1,
                                           'samples_start': 0, 'samples_stop': 6,}


        Sweep_IntermediateGain = False
        Sweep_IntermediateGain_tprocSweep = False
        IJGains = double_jump_base['intermediate_jump_gains']
        print(IJGains[Q-1])
        try:
            double_jump_intermediate_gain_dict = {'swept_qubit': Q, 'reps': 2000,
                                'gainStart': IJGains[Q-1] - 15000,
                                'gainStop':  IJGains[Q-1] + 15000,
                                 'gainNumPoints': 11}
        except:
            pass

        DoubleJump1D = False
        DoubleJump_CurrentCorrelations = False
        # Time trace or single point
        # SinglePoint = (Q == 3) or (Q == 6)
        SinglePoint = False

        if not SinglePoint:
            double_jump_1d_dict = {'reps': 100_000,
                                    'start': 0, 'step': 8, 'expts': 71,
                                   'readout_pair_1': [int(s) for s in beamsplitter_point[0:2]],
                                   'readout_pair_2': [int(s) for s in beamsplitter_point[2:4]],
                                }
        elif SinglePoint:
            double_jump_1d_dict = {'reps': 4_000_000,
                                   'start': Q, 'step': 1, 'expts': 1,
                                   'readout_pair_1': [int(s) for s in beamsplitter_point[0:2]],
                                   'readout_pair_2': [int(s) for s in beamsplitter_point[2:4]],
                                   'bs_samples':np.array(Qubit_Parameters[beamsplitter_point]['exact_t_bs'])
                                   + Qubit_Parameters[beamsplitter_point].get('pad_bs',[0]*8),
                                   'exact_t_bs':np.array(Qubit_Parameters[beamsplitter_point]['exact_t_bs'])}

        print('bs_point:',beamsplitter_point)
        # This ends the working section of the file.
        #----------------------------------------

        # Translation of Qubit_Parameters dict to resonator and qubit parameters.
        # Nothing defined here should be changed in an Experiment unless it is one of the swept variables.
        # Update FF_Qubits dict
        exec(open("UPDATE_CONFIG.py").read())
        # This ends the translation of the Qubit_Parameters dict
        #--------------------------------------------------

        exec(open("CALIBRATE_SINGLESHOT_READOUTS.py").read())

        config = config | double_jump_base

        if Sweep_BeamsplitterOffset:
            BSClean_offset(path="BSClean_offset", outerFolder=outerFolder, prefix = f'{beamsplitter_point}_{rung}',
                                  cfg=config | sweep_bs_offset_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)

        if Sweep_BeamsplitterOffset_tprocSweep:
            RampBeamsplitterOffsetR(path="RampBeamsplitterOffsetR", outerFolder=outerFolder, prefix = f'{beamsplitter_point}_{rung}',
                                    cfg=config | sweep_bs_offset_dict, soc=soc, soccfg=soccfg).acquire_display_save(
                plotDisp=True, block=False)


        if Sweep_BeamsplitterGain:
            BSClean_BSGain(path="BSClean_BSGain", outerFolder=outerFolder, prefix = f'{beamsplitter_point}_{rung}',
                                  cfg=config | sweep_bs_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)
        if Sweep_BeamsplitterGain_tprocSweep:
            RampBeamsplitterGainR(path="RampBeamsplitterGainR", outerFolder=outerFolder, prefix = f'{beamsplitter_point}_{rung}',
                                    cfg=config | sweep_bs_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(
                plotDisp=True, block=False)

        if Sweep_IntermediateSamples:
            BSClean_ISamples(path="BSClean_ISamples", outerFolder=outerFolder, prefix = f'{beamsplitter_point}_{rung}',
                                  cfg=config | double_jump_base | sweep_intermediate_samples_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)
        if Sweep_IntermediateSamples_tprocSweep:
            RampDoubleJumpIntermediateSamplesR(path="RampDoubleJumpIntermediateLength", outerFolder=outerFolder,
                                               cfg=config | double_jump_base | sweep_intermediate_samples_dict, soc=soc,
                                               soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)

        if Sweep_IntermediateGain:
            BSClean_IGain(path="BSClean_IGain", outerFolder=outerFolder, prefix = f'{beamsplitter_point}_{rung}',
                                cfg=config | double_jump_base | double_jump_intermediate_gain_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)
        if Sweep_IntermediateGain_tprocSweep:
            RampDoubleJumpGainR(path="RampDoubleJumpGainR", outerFolder=outerFolder,
                                cfg=config | double_jump_base | double_jump_intermediate_gain_dict, soc=soc,
                                soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)

        if DoubleJump1D:
            BSClean(path="BSClean", outerFolder=outerFolder,
                              cfg=config | double_jump_base | double_jump_1d_dict, soc=soc, soccfg=soccfg,).acquire_display_save(plotDisp=True, block=False)

        if DoubleJump_CurrentCorrelations:
            BSClean_Correlations(path="BSClean_Correlations", outerFolder=outerFolder,
                              cfg=config | double_jump_base | double_jump_1d_dict, soc=soc, soccfg=soccfg,).acquire_display(plotDisp=True, block=False)

plt.show()