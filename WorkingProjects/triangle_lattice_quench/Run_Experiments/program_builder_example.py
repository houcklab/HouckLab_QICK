from WorkingProjects.triangle_lattice_quench.Experimental_Scripts.Program_Templates.ProgramBuilder import ProgramBuilder
from WorkingProjects.triangle_lattice_quench.build_config import build_config
from WorkingProjects.triangle_lattice_quench.socProxy import makeProxy


soc, soccfg = makeProxy()

'''A test file for the program builder. Use with the oscilloscope (to verify timings) and test different
programs with the plot() function.'''

# for det,Q in itertools.product([+20000, -20000],[1,2,3,4,5,6,7,8]):
for Q in [5]:
    Qubit_Readout = [Q]
    Qubit_Pulse = [Q]

    config = build_config(
        Readout_Point='readout_3800_new',
        Qubit_Readout=Qubit_Readout,  # required: list of readout-entry labels
        Qubit_Pulse=Qubit_Pulse,  # optional: list of drive-entry labels
        Ramp_State=None,  # optional: key in ramp_groups
        Dynamics_Point=None,  # optional: key in dynamics_groups
    )

    FFSegments = []

    prog = ProgramBuilder(soccfg=soccfg, cfg=config, reps=1000000, final_delay=10)
    prog.plot()
    prog.run_rounds(soc)  # Necessary instead of acquire, since we are not collecting any results
