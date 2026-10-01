# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

import numpy

from triangle_lattice_quench.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import \
    QubitSpecSliceFFMUX
from triangle_lattice_quench.Experimental_Scripts.Characterization_Sweeps.mSpecVsQblox import \
    SpecVsQblox

voltage_arrs = []

from triangle_lattice_quench.Flux_Files.SET_QBLOX_VOLTAGES import reset_voltages
from triangle_lattice_quench.build_config import build_config
from triangle_lattice_quench.socProxy import makeProxy


soc, soccfg = makeProxy()



for Q in [1,2,3,4,5,6]:
    # voltages = voltage_arrs[Q-1]
    DACs, voltages = reset_voltages(rf"C:\Users\houck\Documents\HouckLab_QICK\WorkingProjects\triangle_lattice_quench\Flux_Files\Voltage_jsons\8QV1\couplers_calib\Q{Q}_high.json")
    # spi_rack.close()
    Qubit_Readout = [Q]
    Qubit_Pulse = [Q]

    config = build_config(Qubit_Readout=Qubit_Readout, Qubit_Pulse=Qubit_Pulse, Readout_Point="readout",
                          jd=r"C:\Users\houck\Documents\HouckLab_QICK\WorkingProjects\triangle_lattice_quench\Run_Experiments\Qubit_Parameters\coupler_calib_qparams.json")

    Run2ToneSpec = False
    Spec_relevant_params = {
                          "qubit_gain": 250, "SpecSpan": 200, "SpecNumPoints": 201,
                          #   "qubit_gain": 200, "SpecSpan": 50, "SpecNumPoints": 71,
                          #    "qubit_gain": 100, "SpecSpan": 150, "SpecNumPoints": 4*71,
                          #   "qubit_gain": 199, "SpecSpan": 50, "SpecNumPoints": 71,
                            # "qubit_gain": 10, "SpecSpan": 10, "SpecNumPoints": 71,
                            'Gauss': False, "sigma": 0.03, "Gauss_gain": 300,
                            'reps': 4*155, 'rounds': 1}


    Run_Spec_v_Qblox = True
    center_voltage = voltages[f'C{Q}']
    Spec_v_Qblox_params = {"Qblox_start": center_voltage-1.6, "Qblox_stop": center_voltage+1.6, "Qblox_steps": 31, "DAC": DACs[f'C{Q}']}



    #--------------------------------------------------
    soc.reset_gens()


    if Run2ToneSpec:
        QubitSpecSliceFFMUX(path="QubitSpecFF", cfg=config | Spec_relevant_params,
                            soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)


    if Run_Spec_v_Qblox:
        SpecVsQblox(path="SpecVsQblox", cfg=config | Spec_relevant_params | Spec_v_Qblox_params,
                                 soc=soc, soccfg=soccfg).acquire_display_save(plotDisp=True, block=False)


    # import matplotlib.pyplot as plt
    # while True:
    #     plt.pause(50)
print(config)
