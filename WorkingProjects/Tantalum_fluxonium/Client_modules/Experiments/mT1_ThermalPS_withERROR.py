from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium.Client_modules.CoreLib.Experiment import ExperimentClass
from WorkingProjects.Tantalum_fluxonium.Client_modules.Helpers.hist_analysis import *
from WorkingProjects.Tantalum_fluxonium.Client_modules.Helpers.MixedShots_analysis import *
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

class LoopbackProgramT1_ThermalPS(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        ##### set up the expirement updates, only runs it once
        cfg["start"] = 0
        cfg["step"] = 0
        cfg["reps"] = cfg["shots"]
        cfg["expts"] = 1

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

        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=cfg["read_pulse_gain"],
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
                     wait=False)

        self.sync_all(self.us2cycles(0.010))

        self.sync_all(self.us2cycles(self.cfg["wait_length"]))

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"])  # update frequency list index

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=2,
                save_experiments=[0, 1],
                start_src="internal", progress=False, debug=False):
        super().acquire(soc, load_pulses=load_pulses, progress=progress, debug=debug,
                        readouts_per_experiment=2, save_experiments=[0, 1])

        return self.collect_shots()

    def collect_shots(self):
        shots_i0 = self.di_buf[0] / self.us2cycles(self.cfg['read_length'], ro_ch=0)
        shots_q0 = self.dq_buf[0] / self.us2cycles(self.cfg['read_length'], ro_ch=0)

        i_0 = shots_i0[0::2]
        i_1 = shots_i0[1::2]
        q_0 = shots_q0[0::2]
        q_1 = shots_q0[1::2]

        return i_0, i_1, q_0, q_1


# ====================================================== #

class T1_ThermalPS_Err(ExperimentClass):

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None,
                 progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress)
        self.data = None

    def acquire(self, progress=False, debug=False):

        # Define the wait array
        wait_arr = np.linspace(self.cfg["wait_start"], self.cfg["wait_stop"], self.cfg["wait_num"])

        # Create a new pointer called time array to the wait array. Relabeling for reading convenience
        t_arr = wait_arr

        # Create arrays to store all the raw data
        i_0_arr = np.full((wait_arr.size, int(self.cfg["shots"])), np.nan)
        q_0_arr = np.full((wait_arr.size, int(self.cfg["shots"])), np.nan)
        i_1_arr = np.full((wait_arr.size, int(self.cfg["shots"])), np.nan)
        q_1_arr = np.full((wait_arr.size, int(self.cfg["shots"])), np.nan)

        # Loop over all wait times and collect raw data
        for idx_wait in range(wait_arr.size):
            self.cfg["wait_length"] = wait_arr[idx_wait]

            # Pull the data from the single shots for the first run
            prog = LoopbackProgramT1_ThermalPS(self.soccfg, self.cfg)
            i_0, i_1, q_0, q_1 = prog.acquire(self.soc, load_pulses=True, readouts_per_experiment=2,
                                              save_experiments=[0, 1])

            # Save all the data to arrays
            i_0_arr[idx_wait, :] = i_0
            q_0_arr[idx_wait, :] = q_0
            i_1_arr[idx_wait, :] = i_1
            q_1_arr[idx_wait, :] = q_1
            iq_data_0 = np.stack((i_0, q_0), axis=1)
            iq_data_1 = np.stack((i_1, q_1), axis=1)

        data = {'config': self.cfg, 'data': { "wait_arr": wait_arr,
                                              "i_0_arr": i_0_arr, "q_0_arr" :q_0_arr,
                                              "i_1_arr": i_1_arr, "q_1_arr" : q_1_arr}}
        self.data = data
        return data

    def display(self, data=None, plotDisp=False, figNum=1, ran=None, **kwargs):
        if data is None:
            data = self.data

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
