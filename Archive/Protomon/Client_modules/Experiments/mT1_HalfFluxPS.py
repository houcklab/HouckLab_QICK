from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WTF.Client_modules.CoreLib.Experiment import ExperimentClass
from WTF.Client_modules.Helpers.hist_analysis import *
from WTF.Client_modules.Helpers.MixedShots_analysis import *
from tqdm.notebook import tqdm
import time
from sklearn.cluster import KMeans
import math
from scipy.optimize import curve_fit

##########################################################################################################
### define functions to be used later for analysis
#### define a rotation function
def rotateBlob(i, q, theta):
    i_rot = i * np.cos(theta) - q * np.sin(theta)
    q_rot = i * np.sin(theta) + q * np.cos(theta)
    return i_rot, q_rot

def SelectAllShots(shots_1_i, shots_1_q, shots_0_igRot, Cen1, Cen2):
    ### selects out shots and defines based on left being 1 and right being 2
    shots_1_iSel = np.array([])
    shots_1_qSel = np.array([])
    shots_2_iSel = np.array([])
    shots_2_qSel = np.array([])
    if Cen1 < Cen2:
        for i in range(len(shots_0_igRot)):
            if shots_0_igRot[i] < Cen1:
                shots_1_iSel = np.append(shots_1_iSel, shots_1_i[i])
                shots_1_qSel = np.append(shots_1_qSel, shots_1_q[i])

            if shots_0_igRot[i] > Cen2:
                shots_2_iSel = np.append(shots_2_iSel, shots_1_i[i])
                shots_2_qSel = np.append(shots_2_qSel, shots_1_q[i])

        return shots_1_iSel, shots_1_qSel, shots_2_iSel, shots_2_qSel

    else:
        for i in range(len(shots_0_igRot)):
            if shots_0_igRot[i] > Cen1:
                shots_1_iSel = np.append(shots_1_iSel, shots_1_i[i])
                shots_1_qSel = np.append(shots_1_qSel, shots_1_q[i])

            if shots_0_igRot[i] < Cen2:
                shots_2_iSel = np.append(shots_2_iSel, shots_1_i[i])
                shots_2_qSel = np.append(shots_2_qSel, shots_1_q[i])

        return shots_2_iSel, shots_2_qSel, shots_1_iSel, shots_1_qSel

####################################################################################################################

class LoopbackProgramT1_HalfFluxPS(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        ##### set up the expirement updates, only runs it once
        cfg["start"]= 0
        cfg["step"]= 0
        cfg["reps"]=cfg["shots"]
        cfg["expts"]=1

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get frequency register for qubit_ch

        res_ch = cfg["res_ch"]
        #         r_freq=self.sreg(cfg["res_ch"], "freq")   #Get frequency register for res_ch
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])

        # Qubit configuration
        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])

        # configure the readout lengths and downconversion frequencies
        for ro_ch in cfg["ro_chs"]:
            # self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
            #                      length=self.us2cycles(self.cfg["state_read_length"]), gen_ch=cfg["res_ch"])
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(self.cfg["read_length"]), gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][0])
        # convert frequency to dac frequency (ensuring it is an available adc frequency)

        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0, gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]),
                                 )  # mode="periodic")

        self.synci(200)  # give processor some time to configure pulses


    def body(self):
        ### intial pause
        self.sync_all(self.us2cycles(0.010))

        #### measure beginning thermal state
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait = False)

        self.sync_all(self.us2cycles(0.010))

        self.sync_all(self.us2cycles(self.cfg["wait_length"]))

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))


    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"]) # update frequency list index

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=2, save_experiments=[0,1],
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress, debug=debug,
                        readouts_per_experiment=2, save_experiments=[0,1])

        return self.collect_shots()

    def collect_shots(self):
        shots_i0=self.di_buf[0]/self.us2cycles(self.cfg['read_length'], ro_ch = 0)
        shots_q0=self.dq_buf[0]/self.us2cycles(self.cfg['read_length'], ro_ch = 0)

        i_0 = shots_i0[0::2]
        i_1 = shots_i0[1::2]
        q_0 = shots_q0[0::2]
        q_1 = shots_q0[1::2]

        return i_0, i_1, q_0, q_1


# ====================================================== #

class T1_HalfFluxPS(ExperimentClass):
    """
    Use post selection at half flux to determine T1
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        expt_cfg = {
            ### define the wait times
            "wait_start": self.cfg["wait_start"],
            "wait_stop": self.cfg["wait_stop"],
            "wait_num": self.cfg["wait_num"],
        }

        wait_vec = np.linspace(expt_cfg["wait_start"], expt_cfg["wait_stop"], expt_cfg["wait_num"])

        self.cfg["wait_length"] = expt_cfg["wait_start"]

        ##### create arrays to store all the raw data
        i_0_arr = np.full((expt_cfg["wait_num"], int(self.cfg["shots"]) ), np.nan)
        q_0_arr = np.full((expt_cfg["wait_num"], int(self.cfg["shots"]) ), np.nan)
        i_1_arr = np.full((expt_cfg["wait_num"], int(self.cfg["shots"]) ), np.nan)
        q_1_arr = np.full((expt_cfg["wait_num"], int(self.cfg["shots"]) ), np.nan)

        ##### create arrays to store all the processed data
        i_0_1_arr = np.full((expt_cfg["wait_num"], int(self.cfg["shots"]) ), np.nan)
        q_0_1_arr = np.full((expt_cfg["wait_num"], int(self.cfg["shots"]) ), np.nan)
        i_1_1_arr = np.full((expt_cfg["wait_num"], int(self.cfg["shots"]) ), np.nan)
        q_1_1_arr = np.full((expt_cfg["wait_num"], int(self.cfg["shots"]) ), np.nan)
        i_0_2_arr = np.full((expt_cfg["wait_num"], int(self.cfg["shots"]) ), np.nan)
        q_0_2_arr = np.full((expt_cfg["wait_num"], int(self.cfg["shots"]) ), np.nan)
        i_1_2_arr = np.full((expt_cfg["wait_num"], int(self.cfg["shots"]) ), np.nan)
        q_1_2_arr = np.full((expt_cfg["wait_num"], int(self.cfg["shots"]) ), np.nan)

        ##### create arrays to store the popultaions
        pop_arr = np.full((expt_cfg["wait_num"], 4), np.nan)

        for idx_wait in range(expt_cfg["wait_num"]):
            self.cfg["wait_length"] = wait_vec[idx_wait]

            #### pull the data from the single shots for the first run
            prog = LoopbackProgramT1_HalfFluxPS(self.soccfg, self.cfg)
            i_0, i_1, q_0, q_1 = prog.acquire(self.soc, load_pulses=True, readouts_per_experiment=2, save_experiments=[0,1])

            #### save all the data to arrays
            i_0_arr[idx_wait, :] = i_0
            q_0_arr[idx_wait, :] = q_0
            i_1_arr[idx_wait, :] = i_1
            q_1_arr[idx_wait, :] = q_1

            #### sort into mixed states
            mixed_0 = MixedShots(i_0, q_0, numbins=25)

            #### rotate the full arrays
            theta = mixed_0.theta

            i_0_rot, q_0_rot = rotateBlob(i_0, q_0, theta)

            cen1 = mixed_0.cen1_rot[0]
            cen2 = mixed_0.cen2_rot[0]
            mid = (cen1 + cen2)/2.0

            ### select out data that started in the ground state
            ### convention here is i_[EXPIREMENT NUMBER]_[BLOB NUMBER]
            i_0_1, q_0_1, i_0_2, q_0_2 = SelectAllShots(i_0, q_0, i_0_rot, cen1, cen2)
            i_1_1, q_1_1, i_1_2, q_1_2 = SelectAllShots(i_1, q_1, i_0_rot, cen1, cen2)

            #### intset above data into arrays for storage
            i_0_1_arr[idx_wait, 0:len(i_0_1)] = i_0_1
            q_0_1_arr[idx_wait, 0:len(q_0_1)] = q_0_1
            i_0_2_arr[idx_wait, 0:len(i_0_2)] = i_0_2
            q_0_2_arr[idx_wait, 0:len(q_0_2)] = q_0_2
            i_1_1_arr[idx_wait, 0:len(i_1_1)] = i_1_1
            q_1_1_arr[idx_wait, 0:len(q_1_1)] = q_1_1
            i_1_2_arr[idx_wait, 0:len(i_1_2)] = i_1_2
            q_1_2_arr[idx_wait, 0:len(q_1_2)] = q_1_2

            ### rotate the blobs for population counting
            i_1_1_rot, q_1_1_rot = rotateBlob(i_1_1, q_1_1, theta)
            i_1_2_rot, q_1_2_rot = rotateBlob(i_1_2, q_1_2, theta)

            populations = np.zeros(4)
            for i in range(len(i_1_1_rot)):
                if i_1_1_rot[i] < mid:
                    populations[0] += 1  ### blob1
                else:
                    populations[1] += 1  ### blob1_e

            for i in range(len(i_1_2_rot)):
                if i_1_2_rot[i] < mid:
                    populations[2] += 1  ### blob2_g
                else:
                    populations[3] += 1  ### blob2_e

            populations[0] = populations[0] / len(i_1_1_rot) * 1.0
            populations[1] = populations[1] / len(i_1_1_rot) * 1.0
            populations[2] = populations[2] / len(i_1_2_rot) * 1.0
            populations[3] = populations[3] / len(i_1_2_rot) * 1.0

            pop_arr[idx_wait, :] = populations

        #### define T1 function
        def _expFit(x, a, T1, c):
            return a * np.exp(-1 * x / T1) + c

        a_geuss = (np.max(pop_arr[:,0])-np.min(pop_arr[:,0]))*-1
        b_geuss = np.min(pop_arr[:,0])
        T1_geuss = np.max(wait_vec)/3
        geuss = [a_geuss, T1_geuss, b_geuss]

        self.pOpt1, self.pCov1 = curve_fit(_expFit, wait_vec, pop_arr[:,0], p0=geuss)

        self.T1_fit1 = _expFit(wait_vec, *self.pOpt1)

        self.T1_est1 = self.pOpt1[1]

        self.pOpt2, self.pCov2 = curve_fit(_expFit, wait_vec, pop_arr[:,2], p0=geuss)

        self.T1_fit2 = _expFit(wait_vec, *self.pOpt2)

        self.T1_est2 = self.pOpt2[1]

        #### save the data
        data = {'config': self.cfg, 'data': {
                                             "wait_vec": wait_vec, 'T1_est1': self.T1_est1, 'T1_est2': self.T1_est2,
                                             'i_0_arr': i_0_arr, 'q_0_arr': q_0_arr,
                                             'i_1_arr': i_1_arr, 'q_1_arr': q_1_arr,
                                             'i_0_1_arr': i_0_1_arr, 'q_0_1_arr': q_0_1_arr,
                                             'i_0_2_arr': i_0_2_arr, 'q_0_2_arr': q_0_2_arr,
                                             'i_1_1_arr': i_1_1_arr, 'q_1_1_arr': q_1_1_arr,
                                             'i_1_2_arr': i_1_2_arr, 'q_1_2_arr': q_1_2_arr,
                                             'pop_arr': pop_arr
                                             }
                }

        self.data = data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, ran=None, **kwargs):
        if data is None:
            data = self.data

        pop_arr = data['data']['pop_arr']
        wait_vec = data['data']['wait_vec']

        fig, axs = plt.subplots(1, 2, figsize=(10, 6), num=figNum)

        axs[0].plot(wait_vec, pop_arr[:,0], 'o-',
                    color='g')

        axs[0].plot(wait_vec, pop_arr[:,2], 'o-',
                    color='m')

        axs[0].plot(wait_vec, self.T1_fit1, label='fit 1')
        axs[0].plot(wait_vec, self.T1_fit2, label='fit 2')

        axs[0].set_ylim([-0.05, 1.05])
        axs[0].set_xlabel('wait time (us)')
        axs[0].set_ylabel('population (%)')
        axs[0].set_title("T1_1 = " + str(round(self.T1_est1, 3)) + " us, T1_2 = " + str(round(self.T1_est2, 3)))

        #### plot the excited state populations
        axs[1].plot(wait_vec, pop_arr[:,1], 'o-',
                    color='g')

        axs[1].plot(wait_vec, pop_arr[:,3], 'o-',
                    color='m')

        axs[1].set_ylim([-0.05, 1.05])
        axs[1].set_xlabel('wait time (us)')
        axs[1].set_ylabel('population (%)')
        axs[1].set_title('blob 2')

        if plotDisp:
            plt.show(block=False)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

