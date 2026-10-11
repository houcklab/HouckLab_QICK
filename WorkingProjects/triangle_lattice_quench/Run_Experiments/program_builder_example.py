from triangle_lattice_quench.Experimental_Scripts.Program_Templates.ProgramBuilder import ProgramBuilder
from triangle_lattice_quench.build_config import QubitParams
from triangle_lattice_quench.socProxy import makeProxy


soc, soccfg = makeProxy()

print(soccfg)

'''A test file for the program builder. Use with the oscilloscope (to verify timings) and test different
programs with the plot() function.'''

# for det,Q in itertools.product([+20000, -20000],[1,2,3,4,5,6,7,8]):
for Q in [5]:
    Qubit_Readout = [Q]
    Qubit_Pulse = [Q]

    QP = QubitParams("Qubit_Parameters\\qubit_parameters.json")
    config = QP.res_qubit_config("readout_3800", Qubit_Readout, Qubit_Pulse)

    FFSegments = []
    config["ProgramBuilderInfo"] = FFSegments

    prog = ProgramBuilder(soccfg=soccfg, cfg=config, reps=1000000, final_delay=10)
    prog.plot()
    prog.run_rounds(soc)  # Necessary instead of acquire, since we are not collecting any results
