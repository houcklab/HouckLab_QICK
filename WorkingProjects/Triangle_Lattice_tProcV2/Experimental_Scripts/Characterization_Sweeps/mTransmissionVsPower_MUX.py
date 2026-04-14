from qick import *

import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
import WorkingProjects.Triangle_Lattice_tProcV2.Helpers.FF_utils as FF
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mTransmissionFFMUX import CavitySpecFFProg


class TransmissionVsPower(ExperimentClass):
    """
    Spec experiment that finds the qubit spectrum as a function of flux, specifically it uses a qblox to sweep
    Notes;
        - this is set up such that it plots out the rows of data as it sweeps through qblox
        - because the cavity frequency changes as a function of flux, it both finds the cavity peak then uses
            the cavity peak to perform the spec drive
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None,
                 config_file=None, progress=None, qblox = None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg,
                         config_file=config_file, progress=progress, qblox = qblox)

    #### during the aquire function here the data is plotted while it comes in if plotDisp is true
    def acquire(self, progress=False, plotDisp = True, plotSave = True, figNum = 1,
                smart_normalize = True):
        cfg = self.cfg

        gain_pts = np.linspace(cfg["gain_start"], cfg["gain_stop"], cfg["gain_num_points"])
        freq_pts = np.linspace(cfg["res_freqs"][0] - cfg["TransSpan"],
                           cfg["res_freqs"][0] + cfg["TransSpan"],
                           cfg["TransNumPoints"])
        self.freq_pts = freq_pts

        fig, axs = plt.subplots(1,1, figsize = (8,6))



        # X_trans = (self.trans_fpts + self.cfg["cavity_LO"]/1e6) /1e3
        X_trans = (self.freq_pts + self.cfg["res_LO"]) / 1e3  #### put into units of frequency GHz
        X_trans_step = X_trans[1] - X_trans[0]
        Y = gain_pts
        Y_step = Y[1] - Y[0]
        Z_trans = np.full((cfg["gain_num_points"], cfg["TransNumPoints"]), np.nan)

        ### create an initial data dictionary that will be filled with data as it is taken during sweeps
        self.trans_Imat = np.zeros((cfg["gain_num_points"], cfg["TransNumPoints"]))
        self.trans_Qmat = np.zeros((cfg["gain_num_points"], cfg["TransNumPoints"]))

        self.data= {
            'config': self.cfg,
            'data': {'trans_Imat': self.trans_Imat, 'trans_Qmat': self.trans_Qmat, 'trans_freq_pts': X_trans,
                     'trans_amplitude': Z_trans, 'gain_pts': gain_pts
                     }
        }

        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()


        #### loop over the gain vector
        for i in range(len(gain_pts)):
            if i % 5 == 1:
                self.save_data(self.data)
                self.soc.reset_gens()
            ### set the gain for the specific run
            self.cfg["res_gains"][0] = gain_pts[i] / 32766.

            ### take the transmission data
            data_I, data_Q = self._acquireTransData()

            ampl = np.abs(np.mean(data_I) + 1j*np.mean(data_Q))
            ampl = self.cfg["res_gains"][0]
            data_I /= ampl
            data_Q /= ampl

            self.data['data']['trans_Imat'][i,:] = data_I
            self.data['data']['trans_Qmat'][i,:] = data_Q

            #### plot out the transmission data
            sig = data_I + 1j * data_Q
            avgamp0 = np.abs(sig)
            Z_trans[i, :] = avgamp0
            # axs[0].plot(x_pts, avgamp0, label="Amplitude; ADC 0")
            if i == 0:
                ax_plot_0 = axs.imshow(
                    Z_trans,
                    aspect='auto',
                    extent=[np.min(X_trans)-X_trans_step/2,np.max(X_trans)+X_trans_step/2,np.min(Y)-Y_step/2,np.max(Y)+Y_step/2],
                    origin= 'lower',
                    interpolation= 'none',
                )
                cbar0 = fig.colorbar(ax_plot_0, ax=axs, extend='both')
                cbar0.set_label('a.u.', rotation=90)
            else:
                ax_plot_0.set_data(Z_trans)
                ax_plot_0.autoscale()
                cbar0.remove()
                cbar0 = fig.colorbar(ax_plot_0, ax=axs, extend='both')
                cbar0.set_label('a.u.', rotation=90)

            axs.set_ylabel("Cavity Gain")
            axs.set_xlabel("Cavity Frequency (GHz)")
            axs.set_title(f"{self.titlename}, "
                          f"Cav Freq: {np.round(self.cfg['res_freqs'][0] + self.cfg['res_LO'] , 3)}")

            if plotDisp:
                plt.show(block=False)
                plt.pause(0.1)

            if i ==0: ### during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start### time for single full row in seconds
                timeEst = (t_delta )*cfg["gain_num_points"]  ### estimate for full scan
                StopTime = startTime + datetime.timedelta(seconds=timeEst)
                print('Time for 1 sweep: ' + str(round(t_delta/60, 2)) + ' min')
                print('estimated total time: ' + str(round(timeEst/60, 2)) + ' min')
                print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))

        print('actual end: '+ datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        if plotSave:
            plt.savefig(self.iname) #### save the figure

        if plotDisp == False:
            fig.clf(True)
            plt.close(fig)
        else:
            plt.show(block=False)

        return self.data

    def _acquireTransData(self, progress=False):
        fpts = self.freq_pts
        results = []
        for f in fpts:
            self.cfg["res_freqs"][0] = f
            prog = CavitySpecFFProg(self.soccfg, reps=self.cfg['reps'], cfg=self.cfg,
                                    final_delay=self.cfg['cav_relax_delay'])
            results.append(prog.acquire(self.soc, rounds=self.cfg.get('rounds', 1), load_envelopes=True, progress=progress))
        results = np.array(results)

        return results[:, 0, 0, 0], results[:, 0, 0, 1]


    def save_data(self, data=None):
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

