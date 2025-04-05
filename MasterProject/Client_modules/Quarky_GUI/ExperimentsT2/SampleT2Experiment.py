import numpy as np

from qick import RAveragerProgram
from Pyro4 import Proxy
from qick import QickConfig

from MasterProject.Client_modules.Quarky_GUI.CoreLib.VoltageInterface import VoltageInterface
from MasterProject.Client_modules.Quarky_GUI.CoreLib.ExperimentT2 import ExperimentClassT2
from MasterProject.Client_modules.Quarky_GUI.PythonDrivers.QBLOX import QBLOX

class SampleProgram(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        print("The initialized config is: " + str(self.cfg))

    def body(self):
        print("Measuring")

    def update(self):
        print("Updating")

    ### Define the program template config ###
    config_template = {
        "reps": 100,
        "sets": 5,
    }


# ====================================================== #

class SampleExperiment_Experiment(ExperimentClassT2):
    """
    Basic sample experiment wrapper class
    """

    ### Define the experiment template config ###
    config_template = {
        "Voltage Config": {
            "ChannelCount": 1,
            "VoltageNumPoints": 10,
            "Channels" : {
                1: [1,3], # start, stop
                2: [-1,1]
            }
        },

        "Experiment Config": { # Corresponds to the cfg given to the program (ie, SampleProgram)
            "reps": 100,
            "sets": 5,
        }
    }

    ### Specify the hardware requirement for this experiment
    hardware_requirement = [Proxy, QickConfig, QBLOX]

    def __init__(self, path='', outerFolder='', prefix='data', hardware=None,
                 cfg = None, config_file=None, progress=None):

        super().__init__(path=path, outerFolder=outerFolder, prefix=prefix, hardware=hardware, cfg=cfg,
                         config_file=config_file, progress=progress)

        # retrieve the hardware that corresponds to what was required
        self.soc, self.soccfg, self.qblox = hardware

    def acquire(self, progress=False, debug=False):

        self.volt_cfg = self.cfg["Voltage Config"]
        self.expt_cfg = self.cfg["Experiment Config"]

        DACs = [key for key in self.volt_cfg["Channels"]]
        VoltageNumPoints = self.volt_cfg["VoltageNumPoints"]

        for i in range(VoltageNumPoints):

            # Setting voltage in the case where each channel sweeping a different range
            for channel in DACs:
                voltVec = np.linspace(self.volt_cfg[channel][0], self.volt_cfg["1"][1], VoltageNumPoints)
                self.qblox.set_voltage(voltVec[i], channel)

            prog = SampleProgram(self.soccfg, self.expt_cfg)
            # data = prog.acquire(...)
            # add data to something

            data = {'config': self.cfg,
                    'data': {}}

        self.data = data
        return data

    @classmethod
    def plotter(cls, plot_widget, plots, data):
        # Implement here using pyqtgraph
        pass

    @classmethod
    def export_data(cls, data_file, data, config):
        super().export_data(data_file, data, config)
        pass

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        # Your own display function using matplotlib or other if you'd like
        pass

    def save_data(self, data=None):
        super().save_data(data=data['data'])
