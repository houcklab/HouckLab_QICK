from qick import RAveragerProgram
from MasterProject.Client_modules.CoreLib.ExperimentV2 import ExperimentClassV2

import datetime
import numpy as np
import matplotlib.pyplot as plt

class SampleProgram(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        print("The initialized config is: " + str(self.cfg))

    def body(self):
        print("Syncing channels")
        print("Measuring")

    def update(self):
        print("Updating")

    ### Define the program template config ###
    config_template = {
        "reps": 100,
        "sets": 5,
    }


# ====================================================== #

class SampleExperiment_Experiment(ExperimentClassV2):
    """
    Basic sample experiment wrapper class
    """

    # Specify the hardware requirement for this experiment
    hardware_requirement = ["RFSoC", "VoltageInterface"]

    ### Define the experiment template config ###
    config_template = {
        "Voltage Config": {
            "ChannelCount": 1,
            "1": {
                "VoltageStart": 0,
                "VoltageStop": 10,
                "VoltageNumPoints": 10,
            },
        },

        "Experiment Config": { # Corresponds to the cfg given to the program (ie, SampleProgram)
            "reps": 100,
            "sets": 5,
        }
    }

    def __init__(self, path='', outerFolder='', prefix='data', hardware=None,
                 cfg = None, config_file=None, progress=None):

        super().__init__(path=path, outerFolder=outerFolder, prefix=prefix, hardware=hardware, cfg=cfg,
                         config_file=config_file, progress=progress)

        # retrieve the hardware that corresponds to what was required
        self.soc, self.soccfg = hardware["RFSoC"]
        self.voltage_interface = hardware["VoltageInterface"]

    def acquire(self, progress=False, debug=False):

        self.volt_cfg = self.cfg["Voltage Config"]
        self.expt_cfg = self.cfg["Experiment Config"]

        ### Define the program
        prog = SampleProgram(self.soccfg, self.expt_cfg)


        voltVec = np.linspace(self.volt_cfg["1"]["VoltageStart"], self.volt_cfg["1"]["VoltageStop"],
                              self.volt_cfg["1"]["VoltageNumPoints"])


        for i in voltVec:
            self.voltage_interface.SetVoltage(i)

            x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                             readouts_per_experiment=1, save_experiments=None,
                                             start_src="internal", progress=False)

            data = {'config': self.cfg,
                    'data': {'x_pts': self.qubit_freqs, 'avgi': avgi, 'avgq': avgq}}

            # perform some averaging across iterations / some data handling


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
