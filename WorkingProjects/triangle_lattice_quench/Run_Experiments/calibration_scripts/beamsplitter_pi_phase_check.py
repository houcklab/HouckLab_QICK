'''
This file can be used to calibrate beamsplitter resonance points and offsets for even
rungs (12, 34, 56, 78) or odd rungs (12, 45, 67).

This assumes that the ramps (12,34,45,56,67,78) are all defined in the qubit parameters file.
'''
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.mBSDoubleJump_CleanTiming import BSClean_offset
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.mRampCurrentCalibrationR_SSMUX import \
    RampBeamsplitterGainR, RampBeamsplitterOffsetR

from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import \
    SingleShotFFMUX

from WorkingProjects.triangle_lattice_quench.Run_Experiments.Qubit_Parameters.UPDATE_CONFIG_function import update_config

from WorkingProjects.triangle_lattice_quench.Run_Experiments.qubit_parameter_files.Qubit_Parameters_Master import *






###############################


def calibrate_rung_gains(BS_FF, rungs):

    print(f'BS_FF {BS_FF}')

    center_gains_1 = []
    center_gains_2 = []

    swept_qubits = []

    for i in range(len(rungs)):
        rung = rungs[i]
        q1 = int(rung[0])
        q2 = int(rung[1])

        assert (abs(q1 - q2) == 1)

        # redefine ramp initial and final point
        if Override_ramp_state == None:
            rampstate = ''.join(sorted(rung))
            print(rampstate)

        else:
            rampstate = Override_ramp_state

        if Override_Qubit_Pulse == None:
            Qubit_Pulse = [q1]
        else:
            Qubit_Pulse = Override_Qubit_Pulse
        Init_FF = Qubit_Parameters[rampstate]['Ramp']['Init_FF']
        Ramp_FF = Qubit_Parameters[rampstate]['Ramp']['Expt_FF']




        Qubit_Readout = [q1, q2]


        sweep_bs_gain_dict['swept_qubit'] = q1
        swept_qubits.append(sweep_bs_gain_dict['swept_qubit'])

        center = BS_FF[q1-1]
        sweep_bs_gain_dict['gainStart'] = center - sweep_bs_gain_dict['gainRange']//2
        sweep_bs_gain_dict['gainStop'] = center + sweep_bs_gain_dict['gainRange']//2



        sweep_bs_offset_dict['swept_qubit'] = q1


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

        # ----------------------------------------

        # Translation of Qubit_Parameters dict to resonator and qubit parameters.
        # Nothing defined here should be changed in an Experiment unless it is one of the swept variables.
        # Update FF_Qubits dict
        namespace = globals() | locals()

        config = update_config(**namespace)
        # This ends the translation of the Qubit_Parameters dict
        # --------------------------------------------------

        for label in ['Gain_Readout', 'Gain_Expt', 'Gain_Pulse', 'Gain_BS', 'Gain_RampInit']:
            print(f'{label}: {[int(config["FF_Qubits"][q][label]) for q in config["FF_Qubits"]]}')


        exec(open("../Legacy_CALIBRATE_SINGLESHOT_READOUTS.py").read())

        experiment = RampBeamsplitterGainR(path="RampBeamsplitterGainR", outerFolder=outerFolder,
                              cfg=config | sweep_bs_gain_dict, soc=soc, soccfg=soccfg)
        data = experiment.acquire_display_save(plotDisp=True, block=False)

        center_gain_1 = data['data']['popt_list'][0][0]
        center_gain_2 = data['data']['popt_list'][1][0]

        center_gains_1.append(center_gain_1)
        center_gains_2.append(center_gain_2)



    center_gains = [center_gains_1, center_gains_2]

    return swept_qubits, center_gains



def calibrate_rung_offset(BS_FF, rungs):

    print(f'BS_FF {BS_FF}')

    swept_qubits = []

    for i in range(len(rungs)):
        rung = rungs[i]

        q1 = int(rung[0])
        q2 = int(rung[1])

        # redefine ramp initial and final point
        if Override_ramp_state == None:
            rampstate = ''.join(sorted(rung))

        else:
            rampstate = Override_ramp_state

        if Override_Qubit_Pulse == None:
            Qubit_Pulse = [q1]
        else:
            Qubit_Pulse = Override_Qubit_Pulse



        Init_FF = Qubit_Parameters[rampstate]['Ramp']['Init_FF']
        Ramp_FF = Qubit_Parameters[rampstate]['Ramp']['Expt_FF']



        assert(abs(q1 - q2) == 1)

        Qubit_Readout = [q1, q2]


        sweep_bs_offset_dict['swept_qubit'] = q1
        swept_qubits.append(sweep_bs_offset_dict['swept_qubit'])

        center = sweep_bs_offset_dict['t_offset'][q1 - 1]
        sweep_bs_offset_dict['offsetStart'] = center - sweep_bs_offset_dict['offset_span']
        sweep_bs_offset_dict['offsetStop'] = center + sweep_bs_offset_dict['offset_span']

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

        # ----------------------------------------

        # Translation of Qubit_Parameters dict to resonator and qubit parameters.
        # Nothing defined here should be changed in an Experiment unless it is one of the swept variables.
        # Update FF_Qubits dict
        namespace = globals() | locals()

        config = update_config(**namespace)
        # This ends the translation of the Qubit_Parameters dict
        # --------------------------------------------------

        for label in ['Gain_Readout', 'Gain_Expt', 'Gain_Pulse', 'Gain_BS', 'Gain_RampInit']:
            print(f'{label}: {[int(config["FF_Qubits"][q][label]) for q in config["FF_Qubits"]]}')


        exec(open("../Legacy_CALIBRATE_SINGLESHOT_READOUTS.py").read())

        BSClean_offset(path="BSClean_offset", outerFolder=outerFolder, prefix=f'{beamsplitter_point}_{rung}',
                       cfg=config | sweep_bs_offset_dict, soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True,
                                                                                                       block=False)

    return swept_qubits


class BS:
    def __init__(self, Readout, beamsplitter_point, rung_list):
        self.Readout = Readout
        self.beamsplitter_point = beamsplitter_point
        self.rung_list = rung_list

BS_list = [
    BS(BS1234_Readout, '1234_correlations', ['21','34','78']), #0
    BS(BS1245_Readout, '1245_correlations', ['21']),           #1
    BS(BS1267_Readout, '1267_correlations', ['21','67']),           #2
    BS(BS2345_Readout, '2345_correlations', ['32','67']),      #3
    BS(BS2356_Readout, '2356_correlations', ['32']),           #4
    BS(BS2378_Readout, '2378_correlations', ['32','78']),           #5
    BS(BS3467_Readout, '3467_correlations', ['34','67']),           #6
    BS(BS4578_Readout, '4578_correlations', ['78']),           #7
]


BS_4200 = FF_gains([8353, 8867, 11160, 8689, -15706, 11637, 12836, 7550])
# (4200.0, 4200.0, 4200.0, 4200.0, 4200.0, 4200.0, 4200.0, 4200.0)
BS_3900 = FF_gains([-4869, -5138, -2519, -4827, -29214, -3602, -1602, -4250])

calibrate_gain   = True
calibrate_offset = True


# For gain sweep only, override the ramp state with the 8Q state if you'd like
Override_ramp_state = None
# Override_ramp_state = '2345_dis'

Override_Qubit_Pulse = None
# Override_Qubit_Pulse = ['1_4Q_readout', '4_4Q_readout', '8_4Q_readout', '5_4Q_readout']
# Override_Qubit_Pulse = [6, 1, 5, 8]


sweep_bs_gain_dict = {'reps': 2*200, 'ramp_time': 1000,
                      't_offset': [2, 1, 6, 9, 8, -1, 1, -2],
                      'relax_delay': 120,
                      'gainRange': 3000, 'gainNumPoints': 11,
                      'start': 50, 'step': 8, 'expts': 71}


sweep_bs_offset_dict = {'reps': 2*200, 'ramp_time': 1000,
                        'intermediate_jump_samples': [None]*8,
                        'intermediate_jump_gains':  [None]*8,
                        'relax_delay': 150,
                        'offset_span': 9, # Sweep +- this amount, e.g. -10 to +10
                        'offsetStep': 1,
                        'start': 0, 'step': 6, 'expts': 71}

for j in [0,2,3,6]:
    BS = BS_list[j]
    readout_params = BS1234_Readout#BS.Readout#TEST_Readout
    beamsplitter_point =  BS.beamsplitter_point#[:5] + 'bonds'
    rungs = BS.rung_list

    for rung in rungs:
        BS_FF = BS_3900.set(**{f'Q{rung[0]}':BS_4200, f'Q{rung[1]}':BS_4200})

        new_gains = BS_FF
        sweep_bs_offset_dict['t_offset'] = Qubit_Parameters[beamsplitter_point]['t_offset']

        if calibrate_gain:
            swept_qubits, center_gains = calibrate_rung_gains(BS_FF, [rung])
            chosen_center_gains = []

            old_gains = BS_FF
            new_gains = np.copy(old_gains)

            for i in range(len(center_gains[0])):

                center_gain_1 = center_gains[0][i]
                center_gain_2 = center_gains[1][i]

                if center_gain_1 is None:
                    user_choice = 2
                else:
                    user_choice = 1

                chosen_center = center_gain_1 if user_choice == 1 else center_gain_2
                chosen_center = round(chosen_center)
                print(f"✅ Using center = {chosen_center} for rung {rung}")

                chosen_center_gains.append(chosen_center)

                new_gains[swept_qubits[i] - 1] = int(chosen_center)

            print(f'old gains: {list(old_gains)}')
            print(f'new gains: {list(new_gains)}')

            new_gains = [int(x) for x in new_gains]

            # print(f"\t'{beamsplitter_point}': {{'BS':{{'BS_FF': {list(new_gains)}}}}},")



        if calibrate_offset:

            # if not new_gains is None:
            BS_FF = new_gains

            calibrate_rung_offset(BS_FF, [rung])

plt.show(block=True)