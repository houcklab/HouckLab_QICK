#### import packages
import os
path = os.getcwd()
os.add_dll_directory(os.path.dirname(path)+'\\PythonDrivers')
from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib_escher.initialize import *
from matplotlib import pyplot as plt
from WorkingProjects.Tantalum_fluxonium.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSpecSlice import LoopbackProgramSpecSlice

#### define the saving path
outerFolder = "Z:\\TantalumFluxonium\\Data\\2023_10_31_BF2_cooldown_6\\WTF\\"

#################################### Running the actual experiments

# Only run this if no proxy already exists
soc, soccfg = makeProxy()
plt.ion()

class SpecVsFlux(ExperimentClass):
    """
    Spec experiment that finds the qubit spectrum as a function of flux, specifically it uses a yoko to sweep
    Notes;
        - this is set up such that it plots out the rows of data as it sweeps through yoko
        - because the cavity frequency changes as a function of flux, it both finds the cavity peak then uses
            the cavity peak to perform the spec drive
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg, config_file=config_file, progress=progress)

    #### during the aquire function here the data is plotted while it comes in if plotDisp is true
    def acquire(self, progress=False, debug=False, plotDisp = True, plotSave = True, figNum = 1):
        # Create the array of different qubit_gains
        self.power_vec = np.linspace(self.cfg["qubit_gain_start"], self.cfg["qubit_gain_stop"], self.cfg["qubit_gain_step"], dtype = int)

        # Create empty array to store data
        self.spec_Idata = np.zeros((self.power_vec.size, self.cfg["SpecNumPoints"]))
        self.spec_Qdata = np.zeros((self.power_vec.size, self.cfg["SpecNumPoints"]))

        # setting the frequency input correctly
        self.cfg["reps"] = self.cfg["spec_reps"]
        self.cfg["start"] = self.cfg["qubit_freq_start"]
        self.cfg["step"] = (self.cfg["qubit_freq_stop"] - self.cfg["qubit_freq_start"])/self.cfg["SpecNumPoints"]
        self.cfg["expts"] = self.cfg["SpecNumPoints"]
        self.qubit_freqs = np.linspace(self.cfg["qubit_freq_start"], self.cfg["qubit_freq_stop"],
                                       self.cfg["SpecNumPoints"])

        # Get data for each qubit_gains
        for i in range(self.power_vec.size):
            self.cfg["qubit_gain"] = self.power_vec[i]
            prog = LoopbackProgramSpecSlice(self.soccfg, self.cfg)
            x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                             readouts_per_experiment=1, save_experiments=None,
                                             start_src="internal", progress=False, debug=False)
            self.spec_Idata[i,:] = avgi
            self.spec_Qdata[i, :] = avgq
            self.data = {'config': self.cfg, 'data': {'freq': self.qubit_freqs, 'qubit_gain' : self.power_vec ,
                                                      'avgi': self.spec_Idata, 'avgq': self.spec_Qdata}}

        return self.data

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data
        spec_Idata = self.data['data']['avgi']
        spec_Qdata = self.data['data']['avgq']
        spec_amp = np.abs()


