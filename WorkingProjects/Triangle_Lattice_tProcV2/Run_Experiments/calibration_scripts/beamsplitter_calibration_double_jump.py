'''
This file can be used to calibrate beamsplitter resonance points and offsets for even
rungs (12, 34, 56, 78) or odd rungs (12, 45, 67).

This assumes that the ramps (12,34,45,56,67,78) are all defined in the qubit parameters file.
'''


from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampCurrentCalibrationR_SSMUX import \
    RampBeamsplitterGainR, RampBeamsplitterOffsetR

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import \
    SingleShotFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Beamsplitter_Fit import reconstruct_double_beamsplitter_fit, \
    reconstruct_beamsplitter_offset_fit
from WorkingProjects.Triangle_Lattice_tProcV2.Helpers import SweepHelpers

from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.UPDATE_CONFIG_function import update_config

from WorkingProjects.Triangle_Lattice_tProcV2.Run_Experiments.qubit_parameter_files.Qubit_Parameters_Master import *

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.mRampCurrentCalibrationR_SSMUX import \
    RampBeamsplitterGainR, RampBeamsplitterOffsetR, RampBeamsplitterR1D, RampCurrentCorrelationsR, RampDoubleJumpGainR, \
    RampDoubleJumpIntermediateSamplesR, RampDoubleJumpR1D, RampDoubleJumpCorrelations, SweepRampLengthCorrelations, \
    RampDoubleJump_BS_GainR, RampCorrelations_Sweep_BS_Gain, RampCorrelations_Sweep_BS_Offset


calibrate_gain                  = True
calibrate_intermediate_offset   = True
calibrate_intermediate_gain     = True



# beamsplitter_point = '1234_correlations'
ijump_point        = '1234_intermediate'
beamsplitter_point = '1245_correlations'

# rungs = ['34_dis', '78_dis']
# rungs = ['23_dis', '45_dis', '67_dis']
# rungs = ['23_dis', '67_dis']
# rungs = ['12', '34', '56', '78']
rungs = ['12_dis', '45_dis']

offset_pi_coeff_choice = 0.5 # Choices are 0.5, 1, 2 corresponding to half-pi, pi, 2pi offset points

double_jump_base = {'reps': 200, 'ramp_time': 1000,
                    't_offset':
                    # [21, 24, 13, 24, 8, 8, 9, 0],
                    Qubit_Parameters[beamsplitter_point]['t_offset'],
                    'relax_delay': 180,
                    'start': 0, 'step': 16, 'expts': 71,
                    'intermediate_jump_samples': Qubit_Parameters[ijump_point]['IJ']['samples'],
                    'intermediate_jump_gains': Qubit_Parameters[ijump_point]['IJ']['gains'],}

double_jump_BS_gain_dict = {'t_offset': [2, 1, 6, 9, 8, -1, 1, -2],
                            'gainRange': 3000, 'gainNumPoints': 11}

double_jump_intermediate_offset_dict = {'samples_start': 0, 'samples_stop': 40, 'samples_step': 1}


double_jump_intermediate_gain_dict = {'gainRange': 20000, 'gainNumPoints': 25}

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


        double_jump_BS_gain_dict['swept_qubit'] = q1
        swept_qubits.append(double_jump_BS_gain_dict['swept_qubit'])

        center = BS_FF[q1-1]
        double_jump_BS_gain_dict['gainStart'] = center - double_jump_BS_gain_dict['gainRange']//2
        double_jump_BS_gain_dict['gainStop'] = center + double_jump_BS_gain_dict['gainRange']//2



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

        experiment = RampDoubleJump_BS_GainR(path="RampDoubleJump_BS_GainR", outerFolder=outerFolder,
                              cfg=config | double_jump_base | double_jump_BS_gain_dict, soc=soc, soccfg=soccfg)
        data = experiment.acquire_display_save(plotDisp=True, block=False)

        center_gain_1 = data['data']['popt_list'][0][0]
        center_gain_2 = data['data']['popt_list'][1][0]

        center_gains_1.append(center_gain_1)
        center_gains_2.append(center_gain_2)



    center_gains = [center_gains_1, center_gains_2]

    return swept_qubits, center_gains

def calibrate_rung_intermediate_offset(BS_FF, rungs, plot_fit=False):

    print(f'BS_FF {BS_FF}')

    swept_qubits = []
    optimal_offsets = []

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


        double_jump_intermediate_offset_dict['swept_qubit'] = q1
        swept_qubits.append(double_jump_intermediate_offset_dict['swept_qubit'])


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

        experiment = RampDoubleJumpIntermediateSamplesR(path="RampDoubleJumpIntermediateLength", outerFolder=outerFolder,
                                cfg=config | double_jump_base | double_jump_intermediate_offset_dict, soc=soc, soccfg=soccfg)
        data = experiment.acquire_display_save(plotDisp=True, block=False, plot_fit=plot_fit)

        if 'popt' in data['data']:

            x = np.asarray(data['data'][experiment.loop_names[0]], float)
            y = np.asarray(data['data'][SweepHelpers.key_savename(experiment.y_key)], float)
            Z = np.asarray(data['data'][experiment.z_value], float)
            R, O, T = Z.shape

            popt = data['data']['popt']
            offset_sorted = data['data']['offset_sorted']
            best_wait_idx = data['data']['best_wait_idx']

            print("fFit offset params: {x, y, z}")

            fit = reconstruct_beamsplitter_offset_fit(popt, offset_sorted, best_wait_idx, x, y, Z)
            print(f'offset fit popt: {popt}')

            # extract optimal offsets at chosen pi point
            chosen_pi_point_key = 'pihalf' # default
            if offset_pi_coeff_choice == 1:
                chosen_pi_point_key = 'pi'
            elif offset_pi_coeff_choice == 2:
                chosen_pi_point_key = 'twopi'
            elif offset_pi_coeff_choice == 0.5:
                chosen_pi_point_key = 'pihalf'
            else:
                print(f"Invalid offset_pi_coeff_choice choice, defaulting to {chosen_pi_point_key}")

            offset_candidates = fit[chosen_pi_point_key]

            if len(offset_candidates) == 0 or len(offset_candidates[0]) == 0:
                print(f"No offset {chosen_pi_point_key} candidates found for qubit {q1}")
            else:
                print(f"  Found {chosen_pi_point_key} offset for qubit {q1}: {offset_candidates[0]}")
                optimal_offsets.append(offset_candidates[0])
        else:
            print(f"No offset fitting achieved for qubit {q1}")

    return swept_qubits, optimal_offsets

def calibrate_rung_intermediate_gains(BS_FF, rungs,  plot_fit=False):

    print(f'BS_FF {BS_FF}')

    swept_qubits = []
    optimal_gains = []

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


        double_jump_intermediate_gain_dict['swept_qubit'] = q1
        swept_qubits.append(double_jump_intermediate_gain_dict['swept_qubit'])

        center = double_jump_base['intermediate_jump_gains'][q1-1]
        double_jump_intermediate_gain_dict['gainStart'] = center - double_jump_intermediate_gain_dict['gainRange']//2
        double_jump_intermediate_gain_dict['gainStop'] = center + double_jump_intermediate_gain_dict['gainRange']//2


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

        experiment = RampDoubleJumpGainR(path="RampDoubleJumpGainR", outerFolder=outerFolder,
                              cfg=config | double_jump_base | double_jump_intermediate_gain_dict, soc=soc, soccfg=soccfg)
        data = experiment.acquire_display_save(plotDisp=True, block=False, plot_fit=False)


        if 'popt' in data['data']:
            y = np.asarray(data['data'][SweepHelpers.key_savename(experiment.y_key)], float)
            Z = np.asarray(data['data'][experiment.z_value], float)
            R, G, T = Z.shape
            popt = data['data']['popt']
            g_sorted = data['data']['g_sorted']

            fit = reconstruct_double_beamsplitter_fit(popt, g_sorted, y, Z)

            print(f"Gain fit: {popt}")

            # Get fitted gains
            zero_candidates = fit['zero']

            if len(zero_candidates) == 0 or len(zero_candidates[0]) == 0:
                print(f'No zero candidates for qubit {q1}')
            else:
                print(f'  Found zero points for qubit {q1}: {zero_candidates[0]}')
                optimal_gains.append(zero_candidates[0]) # only append point for the first plot that is q1
        else:
            print(f'  No gain fitting achieved for qubit {q1}')

    return swept_qubits, optimal_gains






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

    # update BS gains
    BS_FF = new_gains

    print(f'old gains: {list(old_gains)}')
    print(f'new gains:')

    new_gains = [int(x) for x in new_gains]

    print(f"\t'{beamsplitter_point}': {{'BS':{{'BS_FF': {list(new_gains)}}}}},")



if calibrate_intermediate_offset:

    swept_qubits, offsets = calibrate_rung_intermediate_offset(BS_FF, rungs, plot_fit=True)

    if any(offset for offset in offsets):
        print(f"Found optimal offsets: {list(zip(swept_qubits, offsets))}")

        for i in range(len(swept_qubits)):
            if len(offsets[i]) > 0:
                double_jump_base['intermediate_jump_samples'][swept_qubits[i] - 1] = int(np.round(offsets[i][0])) # This always takes the first candidate (shortest offset time)

        print(f"Set intermediate jump offsets: {double_jump_base['intermediate_jump_samples']}")
    else:
        print(f"No intermediate jump offsets fit.")


if calibrate_intermediate_gain:
    swept_qubits, gains = calibrate_rung_intermediate_gains(BS_FF, rungs, plot_fit=True)

    if any(offset for offset in gains):
        print(f"Found optimal gains: {list(zip(swept_qubits, gains))}")

        for i in range(len(swept_qubits)):
            if len(gains[i]) > 0:
                double_jump_base['intermediate_jump_gains'][swept_qubits[i] - 1] = int(np.round(gains[i][0])) # This always takes the first candidate (shortest offset time)

        print(f"Set intermediate jump gains: {double_jump_base['intermediate_jump_gains']}")
    else:
        print(f"No intermediate jump gains fit.")


# Final Print Summary section for easy viewing
print("#" * 18)
if calibrate_gain:
    print("Calibrated Gains:")
    print(f"\t'{beamsplitter_point}': {{'BS':{{'BS_FF': {list([int(x) for x in BS_FF])}}}}}")
if calibrate_intermediate_offset:
    print("Calibrated Intermediate Offsets:")
    print(f"\tFinal intermediate jump offsets: {double_jump_base['intermediate_jump_samples']}")
if calibrate_intermediate_gain:
    print("Calibrated Intermediate Gains:")
    print(f"\tFinal intermediate jump gains: {double_jump_base['intermediate_jump_gains']}")


plt.show(block=True)