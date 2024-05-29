from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm import tqdm
import time
import datetime
from WorkingProjects.Tantalum_fluxonium.Client_modules.PythonDrivers.YOKOGS200 import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSpecSlice import LoopbackProgramSpecSlice
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mTransmission_SaraTest import LoopbackProgramTrans
from WorkingProjects.Tantalum_fluxonium.Client_modules.Calib_escher.initialize import yoko1
import plotly.graph_objects as go
from plotly.subplots import make_subplots

class SpecVsFlux(ExperimentClass):
    """
    Spec experiment that finds the qubit spectrum as a function of flux, specifically it uses a yoko to sweep
    Notes;
        - this is set up such that it plots out the rows of data as it sweeps through yoko
        - because the cavity frequency changes as a function of flux, it both finds the cavity peak then uses
            the cavity peak to perform the spec drive
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None,
                 progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix, outerFolder=outerFolder, cfg=cfg,
                         config_file=config_file, progress=progress)

    def acquire(self, **kwargs):
        """
        Acquire the data for the SpecVsFlux experiment
        """
        # Define the voltage vector for the yoko
        voltVec = np.linspace(self.cfg["yokoVoltageStart"], self.cfg["yokoVoltageStop"],
                              self.cfg["yokoVoltageNumPoints"])

        # create the frequency arrays for both transmission and spec
        self.trans_fpts = np.linspace(self.cfg["trans_freq_start"], self.cfg["trans_freq_stop"],
                                      self.cfg["TransNumPoints"])
        self.spec_fpts = np.linspace(self.cfg["qubit_freq_start"], self.cfg["qubit_freq_stop"],
                                     self.cfg["SpecNumPoints"])

        # create an initial data dictionary that will be filled with data as it is taken during sweeps
        self.trans_Imat = np.zeros((self.cfg["yokoVoltageNumPoints"], self.cfg["TransNumPoints"]))
        self.trans_Qmat = np.zeros((self.cfg["yokoVoltageNumPoints"], self.cfg["TransNumPoints"]))
        self.trans_Amp = np.zeros((self.cfg["yokoVoltageNumPoints"], self.cfg["TransNumPoints"]))
        self.spec_Imat = np.zeros((self.cfg["yokoVoltageNumPoints"], self.cfg["SpecNumPoints"]))
        self.spec_Qmat = np.zeros((self.cfg["yokoVoltageNumPoints"], self.cfg["SpecNumPoints"]))
        self.spec_Amp = np.zeros((self.cfg["yokoVoltageNumPoints"], self.cfg["SpecNumPoints"]))
        self.spec_Phase = np.zeros((self.cfg["yokoVoltageNumPoints"], self.cfg["SpecNumPoints"]))

        # Create a dictionary to store the data
        self.data = {
            'trans_Imat': self.trans_Imat, 'trans_Qmat': self.trans_Qmat, 'trans_fpts': self.trans_fpts,
            'spec_Imat': self.spec_Imat, 'spec_Qmat': self.spec_Qmat, 'spec_fpts': self.spec_fpts,
            'voltVec': voltVec
        }

        fig = make_subplots(rows=3,cols=2,specs=[[{"colspan":2}, None],[{},{}],[{},{}]],
                            subplot_titles=("Qubit Spec : Amplitude","Cavity Transmission","Qubit Spec : Phase","Qubit Spec : I","Qubit Spec : Q"))

        def fetch_data(i):
            # Set the yoko voltage
            yoko1.SetVoltage(voltVec[i])

            # Take the transmission data
            data_I, data_Q = self._aquireTransData()
            self.trans_Imat[i, :] = data_I
            self.trans_Qmat[i, :] = data_Q
            self.trans_Amp[i, :] = np.abs(data_I + 1j * data_Q)
            self.data['trans_Imat'][i, :] = data_I
            self.data['trans_Qmat'][i, :] = data_Q

            # take the spec data
            data_I, data_Q = self._aquireSpecData()
            self.spec_Imat[i, :] = data_I
            self.spec_Qmat[i, :] = data_Q
            self.spec_Amp[i, :] = np.abs(data_I + 1j * data_Q)
            self.spec_Phase[i, :] = np.angle(data_I + 1j * data_Q, deg=True)
            self.data['spec_Imat'][i, :] = data_I
            self.data['spec_Qmat'][i, :] = data_Q

        def update_plot(fig, i):
            fetch_data(i)

            # Update the spec amplitude data
            fig.data[0].z = self.spec_Amp

            # Update the cavity transmission data
            fig.data[1].z = self.trans_Amp

            # Update the spec phase data
            fig.data[2].z = self.spec_Phase

            # Update the spec I data
            fig.data[3].z = self.spec_Imat

            # Update the spec Q data
            fig.data[4].z = self.spec_Qmat

            # Redraw the fig
            fig.update_layout(height =  600, width = 800, title_text="Data Acquisition Update Iteration : {}".format(i))

        # Initial Data
        fetch_data(0)

        # Add initial plots to the figure
        fig.add_trace(go.Heatmap(z=self.spec_Amp, x=self.spec_fpts, y=voltVec, colorscale='Viridis'), row=1, col=1)
        fig.add_trace(go.Heatmap(z=self.trans_Amp, x = self.trans_fpts, y = voltVec, colorscale='Viridis'), row=2, col=1)
        fig.add_trace(go.Heatmap(z=self.spec_Phase, x=self.spec_fpts, y=voltVec, colorscale='Viridis'), row=2, col=2)
        fig.add_trace(go.Heatmap(z=self.spec_Imat, x=self.spec_fpts, y=voltVec, colorscale='Viridis'), row=3, col=1)
        fig.add_trace(go.Heatmap(z=self.spec_Qmat, x=self.spec_fpts, y=voltVec, colorscale='Viridis'), row=3, col=2)

        # Configure the layout and color axes
        fig.update_layout(height =  600, width = 800, title_text="Data Acquisition Update Iteration : 0")
        fig.update_layout(coloraxis1=dict(colorscale='Viridis'), coloraxis2=dict(colorscale='Cividis'))

        # Show initial plot
        fig.show()

        # loop over the yoko vector
        for i in tqdm(range(1,self.cfg["yokoVoltageNumPoints"])):
            update_plot(fig, i)

        # save the figure
        fig.write_image(self.fname + ".png")

        return self.data

    def _aquireTransData(self):
        ##### code to aquire just the cavity transmission data
        expt_cfg = {
            ### transmission parameters
            "trans_freq_start": self.cfg["trans_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
            "trans_freq_stop": self.cfg["trans_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
            "TransNumPoints": self.cfg["TransNumPoints"],  ### number of points in the transmission frequecny
        }
        ### take the transmission data
        self.cfg["reps"] = self.cfg["trans_reps"]
        fpts = np.linspace(expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"], expt_cfg["TransNumPoints"])
        results = []
        start = time.time()
        for f in tqdm(fpts, position=0, disable=True):
            self.cfg["read_pulse_freq"] = f
            prog = LoopbackProgramTrans(self.soccfg, self.cfg)
            # prog = LoopbackProgramTransFF(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
        results = np.transpose(results)
        #### pull out I and Q data
        data_I = results[0][0][0]
        data_Q = results[0][0][1]

        #### find the frequency corresponding to the cavity peak and set as cavity transmission number
        sig = data_I + 1j * data_Q
        avgamp0 = np.abs(sig)
        # peak_loc = np.argmin(avgamp0)
        peak_loc = np.argmax(avgamp0)
        self.cfg["read_pulse_freq"] = self.trans_fpts[peak_loc]

        return data_I, data_Q

    def _aquireSpecData(self):
        ##### code to aquire just the qubit spec data
        expt_cfg = {
            ### spec parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],
            "SpecNumPoints": self.cfg["SpecNumPoints"],  ### number of points
        }
        ### take the transmission data
        self.cfg["reps"] = self.cfg["spec_reps"]
        self.cfg["start"] = expt_cfg["qubit_freq_start"]
        self.cfg["step"] = (expt_cfg["qubit_freq_stop"] - expt_cfg["qubit_freq_start"]) / expt_cfg["SpecNumPoints"]
        self.cfg["expts"] = expt_cfg["SpecNumPoints"]
        fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["SpecNumPoints"])
        results = []
        start = time.time()
        prog = LoopbackProgramSpecSlice(self.soccfg, self.cfg)
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        data_I = data['data']['avgi']
        data_Q = data['data']['avgq']

        return data_I, data_Q

    def save_data(self, data=None):
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data)
