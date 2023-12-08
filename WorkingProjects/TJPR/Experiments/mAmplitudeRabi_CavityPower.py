##### this experiment performs a loop over the normal amplitudeRabi, looking across a number of frequencies
##### this lets you see a full rabi blob

from qick import *
import matplotlib.pyplot as plt
import numpy as np
from STFU.Client_modules.CoreLib.Experiment import ExperimentClass
from STFU.Client_modules.Experiments.mAmplitudeRabi import LoopbackProgramAmplitudeRabi
from STFU.Client_modules.Experiments.mTransmission_SaraTest import Transmission
from tqdm.notebook import tqdm
import time
import datetime



class AmplitudeRabi_CavityPower(ExperimentClass):
    """
    sweep across qubit frequencies while doing amplitude rabi to find a rabi power blob
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False, plotDisp = True, figNum = 1):
        ### define frequencies to sweep over
        expt_cfg = {
            ### cavity amp parameters
            "cav_amp_start": self.cfg["cav_amp_start"],
            "cav_amp_stop": self.cfg["cav_amp_stop"],
            "cavNumPoints": self.cfg["cavNumPoints"],  ### number of points
            ### rabi amp parameters
            "qubit_gain_start": self.cfg["qubit_gain_start"],
            "qubit_gain_step": self.cfg["qubit_gain_step"],
            "qubit_gain_expts": self.cfg["qubit_gain_expts"], #### plus one to account for 0 index
        }

        ### define arrays
        self.cav_amps = np.linspace(expt_cfg["cav_amp_start"], expt_cfg["cav_amp_stop"], expt_cfg["cavNumPoints"])
        self.qubit_amps = np.arange(0, expt_cfg["qubit_gain_expts"] )*expt_cfg["qubit_gain_step"] + expt_cfg["qubit_gain_start"]

        #### define the plotting X and Y and data holders Z
        X = self.cav_amps
        X_step = X[1] - X[0]
        Y = self.qubit_amps
        Y_step = Y[1] - Y[0]
        Z_avgi = np.full((len(Y), len(X)), np.nan)
        Z_avgq = np.full((len(Y), len(X)), np.nan)
        Z_amp = np.full((len(Y), len(X)), np.nan)
        Z_phase = np.full((len(Y), len(X)), np.nan)
        ### create array for storing the data
        self.data= {
            'config': self.cfg,
            'data': {'avgi_mat': Z_avgi, 'avgq_mat': Z_avgq,
                     'cav_amps':self.cav_amps, 'qubit_amps':self.qubit_amps,
                     }
        }

        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplots(4,1, figsize = (12,12), num = figNum)

        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()
        Instance_trans = []
        ### start the loop over qubit frequencies
        for idx in range(len(X)):
            print(idx)
            #### set new cavity power and aquire data
            self.cfg["read_pulse_gain"] = int(self.cav_amps[idx])

            # #### Find Cavity Frequency
            # Instance_trans.append(Transmission(path="dataTestTransmission", cfg=self.cfg,soc=self.soc,soccfg=self.soccfg, outerFolder = self.outerFolder))
            # data_trans = Transmission.acquire(Instance_trans[idx])
            # Transmission.display(Instance_trans[idx], data_trans, plotDisp=False)
            # Transmission.save_data(Instance_trans[idx], data_trans)


            ## update the transmission frequency to be the peak
            self.cfg["read_pulse_freq"] = 559.17
            # Find the Rabi Amp
            prog = LoopbackProgramAmplitudeRabi(self.soccfg, self.cfg)

            x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                             readouts_per_experiment=1, save_experiments=None,
                                             start_src="internal", progress=False, debug=False)
            Z_avgi[:, idx] = avgi[0][0]
            self.data['data']['avgi_mat'][:, idx] = avgi[0][0]

            Z_avgq[:, idx] = avgq[0][0]
            self.data['data']['avgq_mat'][:, idx] = avgq[0][0]

            sig = avgi[0][0] + 1j * avgq[0][0]
            Z_amp[:, idx] = np.abs(sig)
            Z_phase[:,idx] = np.angle(sig, deg=True)


            ####### plotting data
            #### plotting
            ax_plot_0 = axs[0].imshow(
                Z_avgi,
                aspect='auto',
                extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                        Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                origin='lower',
                interpolation='none',
            )
            if idx == 0:  #### if first sweep add a colorbar
                cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
                cbar0.set_label('a.u.', rotation=90)
            else:
                cbar0.remove()
                cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
                cbar0.set_label('a.u.', rotation=90)

            axs[0].set_ylabel("qubit gain")
            axs[0].set_xlabel("cavity gain")
            axs[0].set_title("rabi power blob: avgi")

            #### plot the q
            ax_plot_1 = axs[1].imshow(
                Z_avgq,
                aspect='auto',
                extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                        Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                origin='lower',
                interpolation='none',
            )
            if idx == 0:  #### if first sweep add a colorbar
                cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
                cbar1.set_label('a.u.', rotation=90)
            else:
                cbar1.remove()
                cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
                cbar1.set_label('a.u.', rotation=90)

            axs[1].set_ylabel("qubit gain")
            axs[1].set_xlabel("cavity gain")
            axs[1].set_title("rabi power blob: avgq")

            #### plot the amp
            ax_plot_2 = axs[2].imshow(
                Z_amp,
                aspect='auto',
                extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                        Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                origin='lower',
                interpolation='none',
            )
            if idx == 0:  #### if first sweep add a colorbar
                cbar2 = fig.colorbar(ax_plot_2, ax=axs[2], extend='both')
                cbar2.set_label('a.u.', rotation=90)
            else:
                cbar2.remove()
                cbar2 = fig.colorbar(ax_plot_2, ax=axs[2], extend='both')
                cbar2.set_label('a.u.', rotation=90)

            axs[2].set_ylabel("qubit gain")
            axs[2].set_xlabel("cavity gain")
            axs[2].set_title("rabi power blob: amp")

            #### plot the phase
            ax_plot_3 = axs[3].imshow(
                Z_phase,
                aspect='auto',
                extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                        Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                origin='lower',
                interpolation='none',
            )
            if idx == 0:  #### if first sweep add a colorbar
                cbar3 = fig.colorbar(ax_plot_3, ax=axs[3], extend='both')
                cbar3.set_label('a.u.', rotation=90)
            else:
                cbar3.remove()
                cbar3 = fig.colorbar(ax_plot_3, ax=axs[3], extend='both')
                cbar3.set_label('a.u.', rotation=90)

            axs[3].set_ylabel("qubit gain")
            axs[3].set_xlabel("cavity gain")
            axs[3].set_title("rabi power blob: phase")

            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)

            if idx == 0:  ### during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start  ### time for single full row in seconds
                timeEst = t_delta * len(X)
                StopTime = startTime + datetime.timedelta(seconds=timeEst)
                print('Time for 1 sweep: ' + str(round(t_delta / 60, 2)) + ' min')
                print('estimated total time: ' + str(round(timeEst / 60, 2)) + ' min')
                print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))

            plt.tight_layout()
        print('actual end: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        ### save the figure and return the data
        data = self.data
        plt.savefig(self.iname, dpi = 600)  #### save the figure

        return data

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

