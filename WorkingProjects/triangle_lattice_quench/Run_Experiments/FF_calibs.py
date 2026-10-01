'''
File for doing qubit spec sweeps over FF gain -> calibrate flux quantum and flux offset in RFSoC gain
'''

from matplotlib import pyplot as plt

from triangle_lattice_quench.build_config import build_config
from triangle_lattice_quench.socProxy import makeProxy
from triangle_lattice_quench.Experimental_Scripts.Characterization_Sweeps.mSpecVsFF import SpecVsFF

soc, soccfg = makeProxy()


for Q in [1]:
    Qubit_Readout = [Q]
    Qubit_Pulse = [Q]

    config = build_config(
        Readout_Point='readout_3800_new',
        Qubit_Readout=Qubit_Readout,  # required: list of readout-entry labels
        Qubit_Pulse=Qubit_Pulse,  # optional: list of drive-entry labels
        Ramp_State=None,  # optional: key in ramp_groups
        Dynamics_Point=None,  # optional: key in dynamics_groups
    )
    config['qubit_freqs'][0] = 3950

    Spec_relevant_params = {
        # "qubit_gain": 100, "SpecSpan":150, "SpecNumPoints": 301,
        #   "qubit_gain": 100, "SpecSpan": 550, "SpecNumPoints": 1001,
        "qubit_gain": 300, "SpecSpan": 550, "SpecNumPoints": 801,
        # "qubit_gain": 100, "SpecSpan": 20, "SpecNumPoints": 71,
        'Gauss': False, "sigma": 0.05, "Gauss_gain": 3200,
        'relax_delay': 300,
        'reps': 360}

    FF_sweep_spec_relevant_params = {"qubit_FF_index": Q,
                                "FF_gain_start": -32000, "FF_gain_stop": 32000, "FF_gain_steps": 31}
    # FF_sweep_spec_relevant_params = {"qubit_FF_index": Q,
    #                                  "FF_gain_start": -25000, "FF_gain_stop": +25000, "FF_gain_steps": 2}


    SpecVsFF(cfg=config | Spec_relevant_params | FF_sweep_spec_relevant_params,
             soc=soc, soccfg=soccfg, prefix=f"Q{Q}").acquire_display_save(plotDisp=True, block=False if Q < 8 else True)

plt.show()