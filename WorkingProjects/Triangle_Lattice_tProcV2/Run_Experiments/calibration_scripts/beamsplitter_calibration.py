'''
This file can be used to calibrate beamsplitter resonance points and offsets for even
rungs (12, 34, 56, 78) or odd rungs (12, 45, 67).

This assumes that the ramps (12,34,45,56,67,78) are all defined in the qubit parameters file.
'''


from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampCurrentCalibrationR_SSMUX import \
    RampBeamsplitterGainR, RampBeamsplitterOffsetR

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import \
    SingleShotFFMUX

from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.UPDATE_CONFIG_function import update_config

from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.Qubit_Parameters_Master import *


calibrate_gain = True
calibrate_offset = True


beamsplitter_point = '1254_correlations'
beamsplitter_point = '1267_correlations'
beamsplitter_point = '2356_correlations'
beamsplitter_point = '2378_correlations'
beamsplitter_point = '3467_correlations'
beamsplitter_point = '4578_correlations'
# beamsplitter_point = '2345_correlations'

# rungs = ['34','67']
rungs = ['78']

sweep_bs_gain_dict = {'reps': 200, 'ramp_time': 1000,
                      't_offset': [2, 1, 6, 9, 8, -1, 1, -2],
                      'relax_delay': 120,
                      'gainRange': 3000, 'gainNumPoints': 11,
                      'start': 50, 'step': 8, 'expts': 71}

# sweep_bs_gain_dict = {'reps': 2, 'ramp_time': 10,
#                       't_offset': [-1, 1 - 3, 3, 6, 5, -1, 1, -2],
#                       'relax_delay': 120,
#                       'gainStart': None, 'gainStop': None, 'gainNumPoints': 11,
#                       'start': 50, 'step': 8, 'expts': 71}

sweep_bs_offset_dict = {'reps': 200, 'ramp_time': 1000,
                        't_offset': [23, 25, 14, 25, 9, 9, 9, 0],
                        'relax_delay': 100,
                        'offsetStart': 0, 'offsetStop': 40, 'offsetNumPoints': 41,
                        'start': 0, 'step': 8, 'expts': 71}

sweep_bs_offset_dict = {'reps': 200, 'ramp_time': 1000,
                        't_offset': [23, 25, 14, 25, 9, 9, 9, 0],
                        'relax_delay': 100,
                        'offsetStart': 0, 'offsetStop': 40, 'offsetNumPoints': 41,
                        'start': 0, 'step': 1, 'expts': 71}

###############################


def calibrate_rung_gains(BS_FF, rungs):

    print(f'BS_FF {BS_FF}')

    center_gains_1 = []
    center_gains_2 = []

    swept_qubits = []

    for i in range(len(rungs)):
        rung = rungs[i]

        # redefine ramp initial and final point

        Init_FF = Qubit_Parameters[rung]['Ramp']['Init_FF']
        Ramp_FF = Qubit_Parameters[rung]['Ramp']['Expt_FF']

        q1 = int(rung[0])
        q2 = int(rung[1])

        assert(abs(q1 - q2) == 1)

        Qubit_Pulse = [q1]
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

        for label in ['Gain_Readout', 'Gain_Expt', 'Gain_Pulse', 'Gain_BS', 'ramp_initial_gain']:
            print(f'{label}: {[int(config["FF_Qubits"][q][label]) for q in config["FF_Qubits"]]}')


        exec(open("../CALIBRATE_SINGLESHOT_READOUTS.py").read())

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

        # redefine ramp initial and final point

        Init_FF = Qubit_Parameters[rung]['Ramp']['Init_FF']
        Ramp_FF = Qubit_Parameters[rung]['Ramp']['Expt_FF']

        q1 = int(rung[0])
        q2 = int(rung[1])

        assert(abs(q1 - q2) == 1)

        Qubit_Pulse = [q1]
        Qubit_Readout = [q1, q2]


        sweep_bs_offset_dict['swept_qubit'] = q1
        swept_qubits.append(sweep_bs_offset_dict['swept_qubit'])


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

        for label in ['Gain_Readout', 'Gain_Expt', 'Gain_Pulse', 'Gain_BS', 'ramp_initial_gain']:
            print(f'{label}: {[int(config["FF_Qubits"][q][label]) for q in config["FF_Qubits"]]}')


        exec(open("../CALIBRATE_SINGLESHOT_READOUTS.py").read())

        RampBeamsplitterOffsetR(path="RampBeamsplitterOffsetR", outerFolder=outerFolder,
                                cfg=config | sweep_bs_offset_dict, soc=soc, soccfg=soccfg).acquire_display_save(
            plotDisp=True, block=False)


    return swept_qubits






BS_FF = Qubit_Parameters[beamsplitter_point]['BS']['BS_FF']

new_gains = None

if calibrate_gain:
    swept_qubits, center_gains = calibrate_rung_gains(BS_FF, rungs)
    chosen_center_gains = []

    old_gains = BS_FF
    new_gains = np.copy(old_gains)

    for i in range(len(center_gains[0])):

        center_gain_1 = center_gains[0][i]
        center_gain_2 = center_gains[1][i]
        rung = rungs[i]
        # --- user input step ---
        ### this breaks anydesk so commenting out and defaulting to choice 1 for now
        # while True:
        #     try:
        #         user_choice = int(input(f"\nSelect which center gain to use for rung {rung} "
        #                                 f"(1 = {round(center_gain_1)}, 2 = {round(center_gain_2)}): "))
        #         if user_choice not in (1, 2):
        #             raise ValueError
        #         break
        #     except ValueError:
        #         print("Invalid input. Please type 1 or 2.")

        user_choice = 1

        chosen_center = center_gain_1 if user_choice == 1 else center_gain_2
        chosen_center = round(chosen_center)
        print(f"✅ Using center = {chosen_center} for rung {rung}")

        chosen_center_gains.append(chosen_center)

        new_gains[swept_qubits[i] - 1] = int(chosen_center)

    print(f'old gains: {list(old_gains)}')
    print(f'new gains:')

    new_gains = [int(x) for x in new_gains]

    print(f"\t'{beamsplitter_point}': {{'BS':{{'BS_FF': {list(new_gains)}}}}},")



if calibrate_offset:

    if not new_gains is None:
        BS_FF = new_gains

    calibrate_rung_offset(BS_FF, rungs)

plt.show(block=True)