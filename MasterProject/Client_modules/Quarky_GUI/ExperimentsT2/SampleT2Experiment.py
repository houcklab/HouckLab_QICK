import numpy as np
import time

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
        "sets": 1,
    }


# ====================================================== #

class SampleExperiment_Experiment(ExperimentClassT2):
    """
    Basic sample experiment wrapper class
    """

    ### Define the experiment template config ###
    config_template = {
        "reps": 100,
        "sets": 1,
        "VoltageStart": 0,
        "VoltageStop": 0.6,
        "VoltageNumPoints": 3,
    }

    ## Define the Voltage Config ### NOT USING VOLTAGE CONFIG ANYMORE
    # voltage_config = {
    #     "Channels": [1, 3, 5, 8, 9], # Specifies which channels to use
    #     "VoltageMatrix": [np.linspace(-2,2,7),
    #                       np.linspace(-1,5,7),
    #                       np.linspace(-1, 4, 7),
    #                       np.linspace(-1, 4, 7),
    #                       [0,1.1,1.2,1.3,1.4,3.9,3.7]], # Specifies the voltage points where the ith row
    #                                                 # corresponds to the ith channel in the channels list
    # }

    ### Specify the hardware requirement for this experiment
    hardware_requirement = [Proxy, QickConfig, VoltageInterface]

    def __init__(self, path='', outerFolder='', prefix='data', hardware=None,
                 cfg=None, config_file=None, progress=None):

        super().__init__(path=path, outerFolder=outerFolder, prefix=prefix, hardware=hardware,
                         hardware_requirement=self.hardware_requirement, cfg=cfg,
                         config_file=config_file, progress=progress)

        # retrieve the hardware that corresponds to what was required
        self.soc, self.soccfg, self.voltage_interface = hardware

    def acquire(self, progress=False, debug=False):

        # self.volt_cfg = self.cfg.get("Voltage Config", None) # will be none if Voltage Config doesnt exist
        # expt_cfg = {key: value for key, value in self.cfg.items() if key != "Voltage Config"}
        expt_cfg = self.cfg

        voltage_vec = np.linspace(expt_cfg["VoltageStart"], expt_cfg["VoltageStop"], expt_cfg["VoltageNumPoints"])
        print(voltage_vec)

        for voltage in voltage_vec:

            print("setting voltage to: ", voltage)
            self.voltage_interface.set_voltage(voltage)

            # prog = SampleProgram(self.soccfg, expt_cfg)
            # data = prog.acquire(...)
            # add data to something

            data = {'config': self.cfg,
                    'data': {'x_pts': [0,0]}}

            time.sleep(4)

        self.data = data
        return data

    @classmethod
    def plotter(cls, plot_widget, plots, data):
        # Implement here using pyqtgraph
        pass

    @classmethod
    def export_data(cls, data_file, data, config):
        return
        super().export_data(data_file, data, config)

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        # Your own display function using matplotlib or other if you'd like
        pass

    def save_data(self, data=None):
        pass
        super().save_data(data=data['data'])
