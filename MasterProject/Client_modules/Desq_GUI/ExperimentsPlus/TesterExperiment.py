"""
===================
TesterExperiment.py
===================
A Tester experiment for testing the GUI without needing any soc connection.
Has examples for generating random data in the format of a SpecSlice or SpecVsVoltage to be plotted via a matplotlib
display function that the GUI intercepts (their respective pyqtgraph plotter functions can be found in their actual
experiment files).

Important: Set the TESTING variable in Desq.py to True.

"""

import time
import datetime
import numpy as np
import matplotlib.pyplot as plt
from Pyro4 import Proxy
from qick import QickConfig

from PyQt5.QtCore import pyqtSignal

from MasterProject.Client_modules.Desq_GUI.CoreLib.ExperimentPlus import ExperimentClassPlus
from MasterProject.Client_modules.Desq_GUI.CoreLib.VoltageInterface import VoltageInterface

class TesterProgram():
    def __init__(self, soccfg, cfg):
        self.soccfg = soccfg
        self.cfg = cfg

    def initialize(self):
        print("The initialized config is: " + str(self.cfg))

    def body(self):
        print("Measuring")
        time.sleep(0.2)

    def update(self):
        print("Updating")

class TesterExperiment(ExperimentClassPlus):
    """
    Tester Experiment for testing the GUI without connecting to actual RFSoC.
    """

    ### The signal sent to the experiment thread if any intermediate data is sent
    intermediateData = pyqtSignal(object)  # argument is ip_address

    ### Define the template config
    config_template = {'VoltageNumPoints': 5, 'sleep_time': 0, 'DACs': [5],
        'VoltageStart': [-0.5], 'VoltageStop': [0], 'reps': 20, 'sets': 1,
        'step': 5.714285714285714, 'start': 4408, 'expts': 71,
    }

    ### Hardware Requirement
    hardware_requirement = [Proxy, QickConfig, VoltageInterface]

    def __init__(self, path='', outerFolder='', prefix='data', hardware=None,
                 cfg=None, config_file=None, progress=None):

        super().__init__(path=path, outerFolder=outerFolder, prefix=prefix, hardware=hardware,
                         hardware_requirement=self.hardware_requirement, cfg=cfg,
                         config_file=config_file, progress=progress, is_tester=True)

        # retrieve the hardware that corresponds to what was required
        self.soc, self.soccfg, self.voltage_interface = hardware
        self.stop_flag = False

    #### during the aquire function here the data is plotted while it comes in if plotDisp is true
    def acquire(self, progress=False, plotDisp = True, plotSave = True, figNum = 1,
                smart_normalize = True):
        reps = self.cfg["reps"]

        ############################################################
        ################## FAKE DATA FOR A SPECSLICE ###############
        ############################################################

        x_pts = np.arange(0, reps)
        avgi = [[np.random.randint(0, 10, reps),np.random.randint(0, 10, reps)]]
        avgq = [[np.random.randint(0, 10, reps),np.random.randint(0, 10, reps)]]

        self.data = {'config': self.cfg,
                'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}
        }
        time.sleep(1)

        ############################################################
        ################ FAKE DATA FOR A SPECvsVOLT ################
        ############################################################

        expt_cfg = {
            ### define the voltage parameters
            "VoltageStart": self.cfg["VoltageStart"],
            "VoltageStop": self.cfg["VoltageStop"],
            "VoltageNumPoints": self.cfg["VoltageNumPoints"],
            "step": self.cfg["step"],
            "start": self.cfg["start"],
            "expts": self.cfg["expts"],
        }

        voltage_matrix = []
        for n in range(len(expt_cfg["VoltageStart"])):
            voltage_matrix.append(
                np.linspace(expt_cfg["VoltageStart"][n], expt_cfg["VoltageStop"][n], expt_cfg["VoltageNumPoints"]))

        self.spec_fpts = expt_cfg["start"] + np.arange(expt_cfg["expts"]) * expt_cfg["step"]
        self.spec_Imat = np.full((self.cfg["VoltageNumPoints"], self.cfg["expts"]), np.nan)  # make nan
        self.spec_Qmat = np.full((self.cfg["VoltageNumPoints"], self.cfg["expts"]), np.nan)

        self.data = {
            'config': self.cfg,
            'data': {  # 'trans_Imat': self.trans_Imat, 'trans_Qmat': self.trans_Qmat, 'trans_fpts':self.trans_fpts,
                'spec_Imat': self.spec_Imat, 'spec_Qmat': self.spec_Qmat, 'spec_fpts': self.spec_fpts,
                'voltage_matrix': voltage_matrix
            }
        }

        for i in range(expt_cfg["VoltageNumPoints"]):
            if self.stop_flag:
                break
            if i != 0:
                time.sleep(self.cfg['sleep_time'])

            # Setting voltages
            if 'DACs' in self.cfg:
                for m in range(len(self.cfg['DACs'])):
                    print("Setting channel " + str(self.cfg['DACs'][m]) + " to " + str(voltage_matrix[m][i]))
                    # self.voltage_interface.set_voltage(voltage_matrix[m][i], [self.cfg['DACs'][m]])
            time.sleep(1)

            ### take the spec data
            data_I = [np.random.randint(0, 10, expt_cfg["expts"]),np.random.randint(0, 10, expt_cfg["expts"])]
            data_Q = [np.random.randint(0, 10, expt_cfg["expts"]), np.random.randint(0, 10, expt_cfg["expts"])]
            data_I = data_I[0]
            data_Q = data_Q[0]

            self.data['data']['spec_Imat'][i,:] = data_I
            self.data['data']['spec_Qmat'][i,:] = data_Q

            # send out signal for updated data
            if i != expt_cfg["VoltageNumPoints"] - 1:
                self.intermediateData.emit(self.data)

        ############################################################

        return self.data

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):

        if data is None:
            data = self.data

        ############################################################
        ################## DISPLAY FOR A SPECSLICE #################
        ############################################################

        # x_pts = data['data']['x_pts']
        # avgi = data['data']['avgi'][0][0]
        # avgq = data['data']['avgq'][0][0]
        #
        # sig = avgi + 1j * avgq
        #
        # plt.figure(figNum)
        # plt.plot(x_pts, avgi, '.-', color = 'Orange', label="I")
        # plt.plot(x_pts, avgq, '.-', color = 'Blue', label="Q")
        # plt.ylabel("a.u.")
        # plt.xlabel("Qubit Frequency (GHz)")
        # plt.legend()
        #
        # if plotDisp:
        #     plt.show(block=True)
        #     plt.pause(0.1)
        # plt.close(figNum)

        ############################################################
        ################# DISPLAY FOR A SPECvsVOLT #################
        ############################################################

        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(1, 1, figsize=(8, 6), num=figNum)

        voltage_matrix = data['data']['voltage_matrix']
        X_spec = self.spec_fpts / 1e3
        X_spec_step = X_spec[1] - X_spec[0]
        Y = voltage_matrix[0]
        Y_step = Y[1] - Y[0]
        Z_spec = np.full((self.cfg["VoltageNumPoints"], self.cfg["expts"]), np.nan)

        for i in range(self.cfg["VoltageNumPoints"]):

            data_I = data['data']['spec_Imat'][i, :]
            data_Q = data['data']['spec_Qmat'][i, :]
            sig = data_I + 1j * data_Q

            avgamp0 = np.abs(sig)

            Z_spec[i, :] = avgamp0  #- self.cfg["minADC"]
            if i == 0:
                ax_plot_1 = axs.imshow(
                    Z_spec,
                    aspect='auto',
                    extent=[X_spec[0]-X_spec_step/2,X_spec[-1]+X_spec_step/2,Y[0]-Y_step/2,Y[-1]+Y_step/2],
                    origin='lower',
                    interpolation = 'none',
                )
                cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
                cbar1.set_label('a.u.', rotation=90)
            else:
                ax_plot_1.set_data(Z_spec)
                ax_plot_1.autoscale()
                cbar1.remove()
                cbar1 = fig.colorbar(ax_plot_1, ax=axs, extend='both')
                cbar1.set_label('a.u.', rotation=90)

        axs.set_ylabel("Voltage (V)")
        axs.set_xlabel("Spec Frequency (GHz)")

        if plotDisp:
            plt.show(block=False)
            plt.pause(0.1)
        plt.close(figNum)

        ############################################################

    @classmethod
    def export_data(cls, data_file, data, config):
        super().export_data(data_file, data, config)
        pass

    @classmethod
    def estimate_runtime(self, cfg):
        return 5 # some arbitrarily random value in seconds