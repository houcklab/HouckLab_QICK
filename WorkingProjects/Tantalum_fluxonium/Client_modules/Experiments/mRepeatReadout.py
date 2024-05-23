from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium.Client_modules.Helpers.hist_analysis import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Experiments.mSingleShotProgram import LoopbackProgramSingleShot
from tqdm.notebook import tqdm
import time



class RepeatReadout(ExperimentClass):
    """
    Basic SingleShot experiement that takes a single piece of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False, figNum = 1):

        #### run an initial scan to calibrate the angle and threshold
        prog = LoopbackProgramSingleShot(self.soccfg, self.cfg)
        shots_i0,shots_q0 = prog.acquire(self.soc, load_pulses=True)

        i_g = shots_i0[0]
        q_g = shots_q0[0]
        i_e = shots_i0[1]
        q_e = shots_q0[1]

        # data = {'config': self.cfg, 'data': {'i_g': i_g, 'q_g': q_g, 'i_e': i_e, 'q_e': q_e}}
        # self.data = data

        ### use the helper histogram to find the fidelity and such
        fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=20) ### arbitrary ran, change later

        fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=True, ran=None)


        self.fid = fid
        self.threshold = threshold
        self.angle = angle

        ###### begin looping over sweeps for population measurement
        ### define experiement config
        expt_cfg = {
            ### repetition parameters
            "delay": self.cfg["delay"],
            "repetitions": self.cfg["repetitions"], #### number of times to perform measurement
        }

        ### define qubit frequency array
        self.time_reps = np.arange(0, expt_cfg["repetitions"])
        self.time_stamps = []

        #### define arrays for time steps and ground populations
        X = self.time_reps ### put into units of GHz
        Y = np.full(len(X), np.nan)

        shot_mat = np.full((self.cfg["repetitions"], 2, self.cfg["shots"]*2), np.nan)

        ### create array for storing the data
        self.data= {
            'config': self.cfg,
            'data': {'i_g': i_g, 'q_g': q_g, 'i_e': i_e, 'q_e': q_e,
                     'shot_mat': shot_mat,
                     'g_pop': Y,
                     'time_reps': self.time_reps,
                     'time_stamps': self.time_stamps,
                     }
        }

        #### set the qubit gain to zero
        self.cfg['qubit_gain'] = 0

        ### create the figure and subplots that data will be plotted on
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(1, 1, figsize=(12, 12), num=figNum)

        #### start a timer for estimating the time for the scan
        startTime = datetime.datetime.now()
        print('')  ### print empty row for spacing
        print('starting date time: ' + startTime.strftime("%Y/%m/%d %H:%M:%S"))
        start = time.time()

        ### start the loop over repetitions
        for idx in range(expt_cfg["repetitions"]):
            ### store the time of the measurement
            self.time_stamps.append(time.time())
            #### collect single shot data
            #### run an initial scan to calibrate the angle and threshold
            prog = LoopbackProgramSingleShot(self.soccfg, self.cfg)
            shots_i0, shots_q0 = prog.acquire(self.soc, load_pulses=True)
            ### gather all the i and q shots together
            I = np.append(shots_i0[0], shots_i0[1])
            Q = np.append(shots_q0[0], shots_q0[1])

            ### rotate the data
            I_new = I * np.cos(angle) - Q * np.sin(angle)
            Q_new = I * np.sin(angle) + Q * np.cos(angle)

            #### store the shots
            shot_mat[idx, 0, :] = I
            shot_mat[idx, 1, :] = Q

            self.data['data']['shot_mat'] = shot_mat

            ### find the number of shots in g (less than threshold
            g_count = sum(i < threshold for i in I_new)
            g_pop = g_count / len(I_new)

            Y[idx] = g_pop

            self.data['data']['g_pop'] = Y

            ### save the time stamp data
            self.data['data']['time_stamps'] = self.time_stamps

            ### plot the ground state population
            axs.clear()
            axs.plot(X, Y, 'o')
            axs.set_xlabel('repetition number')
            axs.set_ylabel('g population')

            plt.show(block=False)
            plt.pause(0.1)

            #### self.save_data(data = self.data)

            if idx == 0:  ### during the first run create a time estimate for the data aqcuisition
                t_delta = time.time() - start  ### time for single full row in seconds
                timeEst = (t_delta + self.cfg["delay"]) * len(Y)
                StopTime = startTime + datetime.timedelta(seconds=timeEst)
                print('Time for 1 sweep: ' + str(round((t_delta + self.cfg["delay"]) / 60, 2)) + ' min')
                print('estimated total time: ' + str(round(timeEst / 60, 2)) + ' min')
                print('estimated end: ' + StopTime.strftime("%Y/%m/%d %H:%M:%S"))

            plt.tight_layout()

            # self.save_data(self.data)
            time.sleep(self.cfg["delay"])
        print('actual end: ' + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

        ### save the figure and return the data
        data = self.data
        plt.savefig(self.iname, dpi=600)  #### save the figure

        return data



    # def display(self, data=None, plotDisp = False, figNum = 1, save_fig = True, ran=None, **kwargs):
    #     if data is None:
    #         data = self.data
    #
    #     i_g = data["data"]["i_g"]
    #     q_g = data["data"]["q_g"]
    #     i_e = data["data"]["i_e"]
    #     q_e = data["data"]["q_e"]
    #
    #     #### plotting is handled by the helper histogram
    #     title = ('Read Length: ' + str(self.cfg["read_length"]) + "us, freq: " + str(self.cfg["read_pulse_freq"])
    #                 + "MHz, gain: " + str(self.cfg["read_pulse_gain"]) )
    #     fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=plotDisp, ran=ran, title = title)
    #
    #
    #     self.fid = fid
    #     self.threshold = threshold
    #     self.angle = angle
    #
    #
    #     if save_fig:
    #         plt.savefig(self.iname)
    #
    #     if plotDisp:
    #         plt.show(block=False)
    #         plt.pause(0.1)
    #     # else:
    #         # fig.clf(True)
    #         # plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
