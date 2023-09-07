#### this code optimizes readout by driving the qubit and finding optimal single shot seperation

from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from WTF.Client_modules.CoreLib.Experiment import ExperimentClass
from WTF.Client_modules.Helpers.hist_analysis import *
from WTF.Client_modules.Helpers.MixedShots_analysis import *
from tqdm.notebook import tqdm
import time
import datetime
from WTF.Client_modules.PythonDrivers.YOKOGS200 import *

from WTF.Client_modules.Experiments.mSingleShotProgram import LoopbackProgramSingleShot
from WTF.Client_modules.Experiments.mSingleShotPS import LoopbackProgramSingleShotPS
from WTF.Client_modules.Experiments.mSingleShotPS_FF import LoopbackProgramSingleShotPS_FF
from WTF.Client_modules.Experiments.mSingleShotProgramFF import LoopbackProgramSingleShotFF

### define functions to be used later for analysis
#### define a rotation function
def rotateBlob(i, q, theta):
    i_rot = i * np.cos(theta) - q * np.sin(theta)
    q_rot = i * np.sin(theta) + q * np.cos(theta)
    return i_rot, q_rot

def SelectShots(shots_1_i, shots_1_q, shots_0_igRot, gCen, eCen):
    ### shots_1 refers to second measurement, shots_0_iRot is rotated i quad of first measurement
    ### gCen and eCen are centers of the respective blobs from the ground state expirement
    shots_1_iSel = np.array([])
    shots_1_qSel = np.array([])
    if gCen < eCen:
        for i in range(len(shots_0_igRot)):
            if shots_0_igRot[i] < gCen:
                shots_1_iSel = np.append(shots_1_iSel, shots_1_i[i])
                shots_1_qSel = np.append(shots_1_qSel, shots_1_q[i])
    else:
        for i in range(len(shots_0_igRot)):
            if shots_0_igRot[i] > gCen:
                shots_1_iSel = np.append(shots_1_iSel, shots_1_i[i])
                shots_1_qSel = np.append(shots_1_qSel, shots_1_q[i])

    return shots_1_iSel, shots_1_qSel

class PiOpt_wSingleShot(ExperimentClass):
    """
    This experiment sweeps over pi pulse frequency and gain with a set readout power and frequency. This lets one
    figure out the optimal pi pulse parameters for doign single shot

    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None,
                 calibrate = True, cavityAtten =None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix,outerFolder=outerFolder, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False, plotDisp = True, plotSave = True, figNum = 1,
                FF = False, PS = False, FF_PS = False):
        #### function used to actually find the cavity parameters
        expt_cfg = {
            ### define the qubit frequencies
            "qubit_freq_start": self.cfg["qubit_freq_start"],
            "qubit_freq_stop": self.cfg["qubit_freq_stop"],
            "qubit_freq_num": self.cfg["qubit_freq_num"],  ### number of points
            ### define the qubit gain points
            "qubit_gain_start": self.cfg["qubit_gain_start"],
            "qubit_gain_stop": self.cfg["qubit_gain_stop"],
            "qubit_gain_num": self.cfg["qubit_gain_num"],  ### number of points
        }
        self.freq_fpts = np.linspace(expt_cfg["qubit_freq_start"], expt_cfg["qubit_freq_stop"], expt_cfg["qubit_freq_num"])
        self.gain_fpts = np.linspace(expt_cfg["qubit_gain_start"], expt_cfg["qubit_gain_stop"], expt_cfg["qubit_gain_num"], dtype=int)


        ####create arrays for storing the data
        X = self.freq_fpts
        X_step = X[1] - X[0]
        Y = self.gain_fpts
        Y_step = Y[1] - Y[0]
        Z_fid = np.full((len(Y), len(X)), np.nan)
        Z_overlap = np.full((len(Y), len(X)), np.nan)

        self.data= {
            'config': self.cfg,
            'data': {'fid_mat': Z_fid, 'overlap_mat': Z_overlap,
                     'freq_fpts':self.freq_fpts, 'gain_fpts':self.gain_fpts,
                     }
        }

        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num = figNum):
            figNum += 1
        fig, axs = plt.subplots(2,1, figsize = (8,10), num = figNum)

        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('') ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        ### start the loop over attenuations
        for idx_gain in range(len(self.gain_fpts)):
            ### set the cavity attenuation
            self.cfg["qubit_gain"] = self.gain_fpts[idx_gain]
            self.qubit_gain = self.cfg["qubit_gain"]

            ### start the loop over transmission points
            for idx_freq in range(len(self.freq_fpts)):
                self.cfg["qubit_freq"] = self.freq_fpts[idx_freq]

                i_g, q_g, i_e, q_e = self._acquireSingleShotData(FF = FF, PS = PS, FF_PS = FF_PS)

                fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None, figNum=10)

                plt.show(block=False)
                plt.pause(2)
                plt.close(10)

                Z_fid[idx_gain, idx_freq] = fid
                self.data['data']['fid_mat'][idx_gain, idx_freq] = fid

                #### plotting
                ax_plot_0 = axs[0].imshow(
                    Z_fid*100,
                    aspect='auto',
                    extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                            Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                if idx_gain == 0 and idx_freq == 0:  #### if first sweep add a colorbar
                    cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
                    cbar0.set_label('fidelity (%)', rotation=90)
                else:
                    cbar0.remove()
                    cbar0 = fig.colorbar(ax_plot_0, ax=axs[0], extend='both')
                    cbar0.set_label('fidelity (%)', rotation=90)

                axs[0].set_ylabel("Qubit Gain (a.u.)")
                axs[0].set_xlabel("Qubit Frequency (GHz)")
                axs[0].set_title("fidelity")

                #### perform a mixed shot analysis, decide to combine shots or not based on 'arb' or 'const' qubit drive

                if self.cfg["qubit_pulse_style"] in ["flat_top", "arb"]:
                    mixed_i = np.concatenate((i_g, i_e))
                    mixed_q = np.concatenate((q_g, q_e))

                    mixed = MixedShots(mixed_i, mixed_q)

                    overlapErr = mixed.OverlapErr
                    Z_overlap[idx_gain, idx_freq] = overlapErr
                    self.data['data']['overlap_mat'][idx_gain, idx_freq] = overlapErr

                    # while plt.fignum_exists(num=5):
                    #     plt.close(5)
                    # mixed.PlotGaussFit()
                elif self.cfg["qubit_pulse_style"] == "const":
                    mixed = MixedShots(i_e, q_e)

                    overlapErr = mixed.OverlapErr
                    Z_overlap[idx_gain, idx_freq] = overlapErr
                    self.data['data']['overlap_mat'][idx_gain, idx_freq] = overlapErr

                #### plotting
                ax_plot_1 = axs[1].imshow(
                    Z_overlap,
                    aspect='auto',
                    extent=[X[0] - X_step / 2, X[-1] + X_step / 2,
                            Y[0] - Y_step / 2, Y[-1] + Y_step / 2],
                    origin='lower',
                    interpolation='none',
                )
                if idx_gain == 0 and idx_freq == 0:  #### if first sweep add a colorbar
                    cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
                    cbar1.set_label('overlap err (a.u.)', rotation=90)
                else:
                    cbar1.remove()
                    cbar1 = fig.colorbar(ax_plot_1, ax=axs[1], extend='both')
                    cbar1.set_label('overlap err (a.u.)', rotation=90)

                axs[1].set_ylabel("Qubit Gain (a.u.)")
                axs[1].set_xlabel("Qubit Frequency (GHz)")
                axs[1].set_title("overlap err")

                if plotDisp:
                    plt.show(block=False)
                    plt.pause(0.1)


                if idx_gain == 0 and idx_freq ==0:  ### during the first run create a time estimate for the data aqcuisition
                    t_delta = time.time() - start  ### time for single full row in seconds
                    timeEst = t_delta * expt_cfg["qubit_freq_num"] * expt_cfg["qubit_gain_num"]  ### estimate for full scan
                    StopTime = startTime + datetime.timedelta(seconds=timeEst)
                    print('Time for 1 sweep: ' + str(round(t_delta / 60, 2)) + ' min')
                    print('estimated total time: ' + str(round(timeEst / 60, 2)) + ' min')
                    print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))

        print('actual end: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        plt.savefig(self.iname)  #### save the figure

        return self.data

    def _acquireSingleShotData(self, FF = False, PS = False, FF_PS = False):
        #### acquire data given method

        if FF_PS:
            self.cfg["qubit_gain"] = self.qubit_gain
            prog = LoopbackProgramSingleShotPS_FF(self.soccfg, self.cfg)

            ie_0, ie_1, qe_0, qe_1 = prog.acquire(self.soc, load_pulses=True, readouts_per_experiment=2,
                                                  save_experiments=[0, 1])
            ### run ground state expirement
            self.cfg["qubit_gain"] = 0
            prog = LoopbackProgramSingleShotPS_FF(self.soccfg, self.cfg)
            ig_0, ig_1, qg_0, qg_1 = prog.acquire(self.soc, load_pulses=True, readouts_per_experiment=2,
                                                  save_experiments=[0, 1])

            #### sort into mixed states
            mixed_g0 = MixedShots(ig_0, qg_0, numbins=25)

            #### rotate the full arrays
            theta = mixed_g0.theta  #### theta should be basically the same for all scans

            ig_0_rot, qg_0_rot = rotateBlob(ig_0, qg_0, theta)
            ie_0_rot, qe_0_rot = rotateBlob(ie_0, qe_0, theta)

            #### find the centers of the two ground state blobs based on size of initial measurement blobs
            #### ground state blob should be definitively larger
            if len(mixed_g0.i_blob1_rot) > len(mixed_g0.i_blob2_rot):
                g_cen = mixed_g0.cen1_rot[0]
                e_cen = mixed_g0.cen2_rot[0]
            else:
                g_cen = mixed_g0.cen2_rot[0]
                e_cen = mixed_g0.cen1_rot[0]

            ### select out data that started in the ground state
            i_g, q_g = SelectShots(ig_1, qg_1, ig_0_rot, g_cen, e_cen)
            i_e, q_e = SelectShots(ie_1, qe_1, ie_0_rot, g_cen, e_cen)

            #### make sure that the arrays are the same size
            if len(i_g) > len(i_e):
                i_g = i_g[0:len(i_e)]
                q_g = q_g[0:len(i_e)]
            else:
                i_e = i_e[0:len(i_g)]
                q_e = q_e[0:len(i_g)]

        elif PS:
            prog = LoopbackProgramSingleShotPS(self.soccfg, self.cfg)

        elif FF:
            prog = LoopbackProgramSingleShotFF(self.soccfg, self.cfg)
            shots_i0, shots_q0 = prog.acquire(self.soc, load_pulses=True)
            i_g = shots_i0[0]
            q_g = shots_q0[0]
            i_e = shots_i0[1]
            q_e = shots_q0[1]
        else:
            prog = LoopbackProgramSingleShot(self.soccfg, self.cfg)
            shots_i0, shots_q0 = prog.acquire(self.soc, load_pulses=True)
            i_g = shots_i0[0]
            q_g = shots_q0[0]
            i_e = shots_i0[1]
            q_e = shots_q0[1]

        ### use the helper histogram to find the fidelity and such
        fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None)

        self.fid = fid
        self.threshold = threshold
        self.angle = angle

        return i_g, q_g, i_e, q_e


    def save_data(self, data=None):
        ##### save the data to a .h5 file
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])