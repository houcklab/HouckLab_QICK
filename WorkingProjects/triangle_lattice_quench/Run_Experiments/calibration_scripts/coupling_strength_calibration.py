'''
This file can be used to find coupling strengths for all pairs of qubits.
Can be used when starting from a new coupling point to find the coupling of couplers
'''
from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.mGainSweepQubitOscillationsR import \
    GainSweepOscillationsR

from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import \
    SingleShotFFMUX


from WorkingProjects.triangle_lattice_quench.Run_Experiments.Qubit_Parameters.UPDATE_CONFIG_function import update_config
from WorkingProjects.triangle_lattice_quench.Run_Experiments.qubit_parameter_files.Qubit_Parameters_Master import *




rungs = ['12', '23', '34', '45', '56', '67', '78']
legs = ['13', '24', '35', '46', '57', '68']

pairs = legs

# pairs = ['35', '46']
# pairs = ['46','68']
# pairs = ['68']
# pairs = ['12', '23', '34', '45']

oscillation_gain_dict = {'qubit_FF_index': None, 'reps': 200,
                             'start': 1, 'step': 7, 'expts': 71,
                             'gainRange': 2000, 'gainNumPoints': 11, 'relax_delay': 150,
                             'fit': True}

###############################


def calibrate_coupling(pairs):
    for pair in pairs:
        q_i, q_j = [int(c) for c in pair]

        Qubit_Readout = [q_i, q_j]
        # Qubit_Pulse =   [f"{q_i}R"]
        Qubit_Pulse =   [q_i]

        Expt_FF_subsys = Expt_FF.subsys(q_i, q_j, det= -10000)


        FF_gain1_expt = Expt_FF_subsys[0]
        FF_gain2_expt = Expt_FF_subsys[1]
        FF_gain3_expt = Expt_FF_subsys[2]
        FF_gain4_expt = Expt_FF_subsys[3]
        FF_gain5_expt = Expt_FF_subsys[4]
        FF_gain6_expt = Expt_FF_subsys[5]
        FF_gain7_expt = Expt_FF_subsys[6]
        FF_gain8_expt = Expt_FF_subsys[7]

        oscillation_gain_dict['qubit_FF_index'] = q_j if q_j != 7 else q_i

        oscillation_gain_dict['gainStart'] = Expt_FF[oscillation_gain_dict['qubit_FF_index']-1] - oscillation_gain_dict['gainRange']//2
        oscillation_gain_dict['gainStop'] = Expt_FF[oscillation_gain_dict['qubit_FF_index']-1] + oscillation_gain_dict['gainRange']//2



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

        experiment = GainSweepOscillationsR(path="GainSweepOscillationsR", outerFolder=outerFolder,
                               cfg=config | oscillation_gain_dict, soc=soc, soccfg=soccfg)

        data = experiment.acquire_display_save(plotDisp=True, block=False)

        try:
            center_gain_1 = data['data']['popt_list'][0][0]
            center_gain_2 = data['data']['popt_list'][1][0]

            coupling_1 = data['data']['popt_list'][0][2]
            coupling_2 = data['data']['popt_list'][1][2]

            print(f'coupling strength {coupling_1:.2f} MHz found at gain {round(center_gain_1)}')
        except:
            print("Coupling strength could not be found.")




calibrate_coupling(pairs)
plt.show(block=True)