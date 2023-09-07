#### an experiment for finding the qubit frequency, waiting some set time, then finding it again
#### this loops many times and can build statistics on how much the qubit frequency drifts over time

from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from Protomon.Client_modules.CoreLib.Experiment import ExperimentClass
from Protomon.Client_modules.Experiments.mSpecSlice_ShashwatTest import PulseProbeSpectroscopyProgram
from tqdm.notebook import tqdm
import time
import datetime
from matplotlib.dates import DateFormatter
from matplotlib.dates import HourLocator


class FluxDriftTest(ExperimentClass):
    """
    loop over a spec sweep to find the drift over time of the qubit frequency to get an idea for the flux drift
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg, config_file=config_file, progress=progress)

    #### during the aquire function here the data is plotted while it comes in if plotDisp is true
    def acquire(self, progress=False, debug=False, plotDisp = True, plotSave = True, figNum = 1):
        expt_cfg = {
            ### spec parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],
            "SpecNumPoints": self.cfg["SpecNumPoints"],  ### number of points
            ### timing parameters
            "wait_step": self.cfg["drift_wait_step"], ### time of each waiting step
            "wait_num": self.cfg['drift_wait_num'], ### number of steps to take
        }

        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplots(1,1, figsize = (6,6), num = figNum)

        ### create the frequency arrays for both transmission and spec
        ### also create empty array to fill with transmission and spec data
        self.spec_fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["SpecNumPoints"])
        self.wait_fpts = np.arange(0, expt_cfg["wait_num"] )*expt_cfg["wait_step"]
        self.qubit_pks = np.zeros(expt_cfg["wait_num"])
        X = self.spec_fpts/1e3
        X_step = X[1] - X[0]
        Y = self.wait_fpts
        Y_step = Y[1] - Y[0]
        Z = np.full((expt_cfg["wait_num"], expt_cfg["SpecNumPoints"]), np.nan)

        ### create an initial data dictionary that will be filled with data as it is taken during sweeps
        self.spec_Imat = np.zeros((expt_cfg["wait_num"], expt_cfg["SpecNumPoints"]))
        self.spec_Qmat = np.zeros((expt_cfg["wait_num"], expt_cfg["SpecNumPoints"]))
        self.data= {
            'config': self.cfg,
            'data': {
                        'spec_Imat': self.spec_Imat, 'spec_Qmat': self.spec_Qmat, 'spec_fpts': self.spec_fpts,
                        'wait_vec': self.wait_fpts,
                     }
        }

        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        #### loop over the waiting vector
        for i in range(expt_cfg["wait_num"]):
            ### set the yoko voltage for the specific run

            ### take the spec data
            data_I, data_Q = self._aquireSpecData()
            self.data['data']['spec_Imat'][i,:] = data_I
            self.data['data']['spec_Qmat'][i,:] = data_Q

            #### plot out the spec data
            sig = data_I + 1j * data_Q
            avgamp0 = np.abs(sig) -np.mean(np.abs(sig))

            #### find the qubit frequency
            amp_avg = np.mean(avgamp0)
            amp_minDiff = np.abs(np.min(avgamp0) - amp_avg)
            amp_maxDiff = np.abs(np.max(avgamp0) - amp_avg)

            if amp_maxDiff > amp_minDiff:
                self.qubit_pks[i] = self.spec_fpts[np.argmax(avgamp0)]
            else:
                self.qubit_pks[i] = self.spec_fpts[np.argmin(avgamp0)]


            Z[i, :] = avgamp0
            ax_plot = axs.imshow(
                Z,
                aspect='auto',
                extent=[np.min(X)-X_step/2,np.max(X)+X_step/2,np.min(Y)-Y_step/2,np.max(Y)+Y_step/2],
                origin='lower',
                interpolation = 'none',
            )
            if i ==0: #### if first sweep add a colorbar
                cbar = fig.colorbar(ax_plot, ax=axs, extend='both')
                cbar.set_label('a.u.', rotation=90)
            else:
                cbar.remove()
                cbar = fig.colorbar(ax_plot, ax=axs, extend='both')
                cbar.set_label('a.u.', rotation=90)

            # axs.yaxis.set_major_locator(HourLocator())
            # axs.yaxis.set_major_formatter(DateFormatter('%H:%M'))
            axs.set_ylabel("Time (min)")
            axs.set_xlabel("Qubit Frequency (GHz)")
            axs.set_title("Qubit Drift Test")
            axs.tick_params(axis='x', labelrotation=45)

            plt.tight_layout()

            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)

            if plotSave:
                plt.savefig(self.iname)  #### save the figure

            if i < expt_cfg["wait_num"]-1:
                time.sleep(expt_cfg["wait_step"]*60)

            if i ==0: ### during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start ### time for single full row in seconds
                timeEst = t_delta*(expt_cfg["wait_num"]) ### estimate for full scan
                StopTime = startTime + datetime.timedelta(seconds=timeEst)
                print('Time for 1 sweep: ' + str(round(t_delta/60, 2)) + ' min')
                print('estimated total time: ' + str(round(timeEst/60, 2)) + ' min')
                print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))
                ### Adjust y axis accordingly to include the time it takes to do a SpecScan
                Y = np.arange(0, expt_cfg["wait_num"] )*(expt_cfg["wait_step"] + round(t_delta/60, 2))
                Y_step = Y[1] - Y[0]

            print('Current time: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        print('actual end: '+ datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        #### add the drift statisitics to the plot title
        drift_mean = "{0:.5}".format(np.mean(self.qubit_pks))
        drift_std = "{0:.3}".format(np.std(self.qubit_pks))
        drift_span = "{0:.3}".format(( np.max(self.qubit_pks) - np.min(self.qubit_pks) ))

        axs.set_title("Qubit Freq: " + drift_mean + "MHz, std: " + drift_std + "MHz, span: " + drift_span + "MHz")

        plt.savefig(self.iname) #### save the figure

        if plotDisp == False:
            fig.clf(True)
            plt.close(fig)

        return self.data


    def _aquireSpecData(self):
        ##### code to aquire just the qubit spec data
        expt_cfg = {
            ### spec parameters
            "qubit_freq_start": self.cfg["qubit_freq_start"],
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],
            "SpecNumPoints": self.cfg["SpecNumPoints"],  ### number of points
        }
        ### take the transmission data
        fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["SpecNumPoints"])
        self.cfg["step"] = np.float(
            (expt_cfg["qubit_freq_stop"] - expt_cfg["qubit_freq_start"]) / expt_cfg["SpecNumPoints"])
        self.cfg["start"] = self.cfg["qubit_freq_start"]
        self.cfg["expts"] = self.cfg["SpecNumPoints"]
        self.cfg["reps"] = self.cfg["spec_reps"]
        self.cfg["rounds"] = self.cfg["spec_rounds"]
        self.cfg["qubit_pulse_style"] = "const"
        print("beginning acquire spec")
        print(self.cfg)
        start = time.time()
        prog = PulseProbeSpectroscopyProgram(self.soccfg, self.cfg)
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)
        print(f'Time: {time.time() - start}')
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        #### pull out I and Q data
        data_I = data['data']['avgi'][0][0]
        data_Q = data['data']['avgq'][0][0]

        return data_I, data_Q


    def save_data(self, data=None):
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
