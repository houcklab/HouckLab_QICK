from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WTF.Client_modules.CoreLib.Experiment import ExperimentClass
from WTF.Client_modules.Helpers.hist_analysis import *
from WTF.Client_modules.Helpers.MixedShots_analysis import *
from tqdm.notebook import tqdm
import time

##########################################################################################################
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

####################################################################################################################

class LoopbackProgramFFPulse_WTF(RAveragerProgram):
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

        ##### define a fast flux pulse
        self.set_pulse_registers(ch=self.cfg["ff_ch"], style="const", freq=0, phase=0,
                                 gain=self.cfg["ff_gain"],
                                 length=self.us2cycles(self.cfg["ff_length"]))
        self.cfg["ff_length_total"] = self.us2cycles(self.cfg["ff_length"])

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

        # ##### run the fast flux pulse 10 times
        self.pulse(ch=self.cfg["ff_ch"])  # play pulse

        #### wait until everything is finished reading
        self.synci(self.us2cycles(0.20))

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

class FFPulse_WTF(ExperimentClass):
    """
    running the WTF experiment, pulse from half flux and find qubit population before and after with selection
    """
    """
    run a single shot expirement that utilizes a post selection process to handle thermal starting state
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        #### pull the data from the single hots
        prog = LoopbackProgramFFPulse_WTF(self.soccfg, self.cfg)
        i_0, i_1, q_0, q_1 = prog.acquire(self.soc, load_pulses=True, readouts_per_experiment=2, save_experiments=[0,1])

        #### sort into mixed states
        mixed_0 = MixedShots(i_0, q_0, numbins=25)

        #### rotate the full arrays
        theta = mixed_0.theta

        i_0_rot, q_0_rot = rotateBlob(i_0, q_0, theta)

        cen1 = mixed_0.cen1_rot[0]
        cen2 = mixed_0.cen2_rot[0]

        i_0_blob1_size = np.mean(mixed_0.i_blob1_rot)
        i_0_blob2_size = np.mean(mixed_0.i_blob2_rot)

        ### select out data that started in the ground state
        ### convention here is i_[EXPIREMENT NUMBER]_[BLOB NUMBER]
        i_0_1, q_0_1 = SelectShots(i_0, q_0, i_0_rot, cen1, cen2)
        i_0_2, q_0_2 = SelectShots(i_0, q_0, i_0_rot, cen2, cen1)
        i_1_1, q_1_1 = SelectShots(i_1, q_1, i_0_rot, cen1, cen2)
        i_1_2, q_1_2 = SelectShots(i_1, q_1, i_0_rot, cen2, cen1)

        #### try to improve the blob selecting
        # i_0_1, q_0_1 = SelectShots(i_0, q_0, i_0_rot, cen1+i_0_blob1_size/2, cen2- i_0_blob2_size/2)
        # i_0_2, q_0_2 = SelectShots(i_0, q_0, i_0_rot, cen2+ i_0_blob2_size/2, cen1-i_0_blob1_size/2)
        # i_1_1, q_1_1 = SelectShots(i_1, q_1, i_0_rot, cen1+i_0_blob1_size/2, cen2- i_0_blob2_size/2)
        # i_1_2, q_1_2 = SelectShots(i_1, q_1, i_0_rot, cen2+ i_0_blob2_size/2, cen1-i_0_blob1_size/2)

        #### save the data
        data = {'config': self.cfg, 'data': {'i_0': i_0, 'q_0': q_0, 'i_1': i_1, 'q_1': q_1,
                                             'i_0_1': i_0_1, 'q_0_1': q_0_1,
                                             'i_0_2': i_0_2, 'q_0_2': q_0_2,
                                             'i_1_1': i_1_1, 'q_1_1': q_1_1,
                                             'i_1_2': i_1_2, 'q_1_2': q_1_2,
                                             }}
        self.data = data

        return data




    def display(self, data=None, plotDisp = False, figNum = 1, ran=None, **kwargs):
        if data is None:
            data = self.data

        ### pull out raw data
        i_0 = data["data"]["i_0"]
        q_0 = data["data"]["q_0"]
        i_1 = data["data"]["i_1"]
        q_1 = data["data"]["q_1"]

        ### pull out sorted data
        i_0_1 = data["data"]["i_0_1"]
        q_0_1 = data["data"]["q_0_1"]
        i_0_2 = data["data"]["i_0_2"]
        q_0_2 = data["data"]["q_0_2"]

        i_1_1 = data["data"]["i_1_1"]
        q_1_1 = data["data"]["q_1_1"]
        i_1_2 = data["data"]["i_1_2"]
        q_1_2 = data["data"]["q_1_2"]

        #### plotting out all the plots
        fig, axs = plt.subplots(2,2, figsize = (8,8), num = 202)
        alpha = 0.3

        #### plot out the raw intial expirement
        axs[0,0].plot(i_0, q_0, 'o', color = 'darkorange', alpha = alpha, label = '0')
        axs[0,0].set_xlabel('I (a.u.)')
        axs[0,0].set_ylabel('Q (a.u.)')
        axs[0,0].set_title('Half Flux')
        i_0_lim = axs[0,0].get_xlim()
        q_0_lim = axs[0,0].get_ylim()

        #### plot out the raw final expirmement
        axs[0,1].plot(i_1, q_1, 'o', color = 'lightseagreen', alpha = alpha, label = '1')
        axs[0,1].set_xlabel('I (a.u.)')
        axs[0,1].set_ylabel('Q (a.u.)')
        axs[0,1].set_title('FF Pulsed')
        i_1_lim = axs[0,1].get_xlim()
        q_1_lim = axs[0,1].get_ylim()

        #### plot out the sorted intial expirmement
        axs[1,0].plot(i_0_1, q_0_1, 'go', alpha = alpha, label = 'blob 1')
        axs[1,0].plot(i_0_2, q_0_2, 'mo', alpha = alpha, label= 'blob 2')
        axs[1,0].set_xlabel('I (a.u.)')
        axs[1,0].set_ylabel('Q (a.u.)')
        axs[1,0].set_title('Sorted Half Flux data')
        axs[1,0].set_xlim(i_0_lim)
        axs[1,0].set_ylim(q_0_lim)

        #### plot out the sorted final expirmement
        axs[1,1].plot(i_1_1, q_1_1, 'go', alpha = alpha, label = 'blob 1')
        axs[1,1].plot(i_1_2, q_1_2, 'mo', alpha = alpha, label= 'blob 2')
        axs[1,1].set_xlabel('I (a.u.)')
        axs[1,1].set_ylabel('Q (a.u.)')
        axs[1,1].set_title('Sorted FF Pulsed data')
        axs[1,1].set_xlim(i_1_lim)
        axs[1,1].set_ylim(q_1_lim)

        if plotDisp:
            plt.show(block=False)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)


    def process(self, calibData):

        #### pull out calibration data
        i_g = calibData["data"]["i_g"]
        q_g = calibData["data"]["q_g"]
        i_e = calibData["data"]["i_e"]
        q_e = calibData["data"]["q_e"]

        #### append the self.data with the calibration data
        self.data["data"]["i_g"] = i_g
        self.data["data"]["q_g"] = q_g
        self.data["data"]["i_e"] = i_e
        self.data["data"]["q_e"] = q_e

        ### pull out the saved fast data
        i_fast = self.data["data"]["i_1"]
        q_fast = self.data["data"]["q_1"]
        i_fast_1 = self.data["data"]["i_1_1"]
        q_fast_1 = self.data["data"]["q_1_1"]
        i_fast_2 = self.data["data"]["i_1_2"]
        q_fast_2 = self.data["data"]["q_1_2"]

        self.fid, self.threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=None, figNum=10)

        i_g_rot, q_g_rot = rotateBlob(i_g, q_g, angle)
        i_e_rot, q_e_rot = rotateBlob(i_e, q_e, angle)
        i_fast_rot, q_fast_rot = rotateBlob(i_fast, q_fast, angle)
        i_fast_1_rot, q_fast_1_rot = rotateBlob(i_fast_1, q_fast_1, angle)
        i_fast_2_rot, q_fast_2_rot = rotateBlob(i_fast_2, q_fast_2, angle)

        #### calculate the amounts of blob 1 and blob 2 in the ground and excited states
        blob1_g = 0
        blob1_e = 0
        blob2_g = 0
        blob2_e = 0
        for i in range(len(i_fast_1_rot)):
            if i_fast_1_rot[i] < self.threshold:
                blob1_g += 1
            else:
                blob1_e += 1

        for i in range(len(i_fast_2_rot)):
            if i_fast_2_rot[i] < self.threshold:
                blob2_g += 1
            else:
                blob2_e += 1

        self.data["data"]["blob1_g"] = blob1_g / len(i_fast_1_rot) * 1.0
        self.data["data"]["blob1_e"] = blob1_e / len(i_fast_1_rot) * 1.0

        self.data["data"]["blob2_g"] = blob2_g / len(i_fast_2_rot) * 1.0
        self.data["data"]["blob2_e"] = blob2_e / len(i_fast_2_rot) * 1.0

        return i_g_rot, i_e_rot, i_fast_1, q_fast_1, i_fast_2, q_fast_2, i_fast_1_rot, i_fast_2_rot


    def display_process(self, calibData):

        i_g_rot, i_e_rot, i_fast_1, q_fast_1, i_fast_2, q_fast_2, i_fast_1_rot, i_fast_2_rot = self.process(calibData = calibData)

        i_g = self.data["data"]["i_g"]
        q_g = self.data["data"]["q_g"]
        i_e = self.data["data"]["i_e"]
        q_e = self.data["data"]["q_e"]

        #### plotting the data together
        fig, axs = plt.subplots(2, 2, figsize=(8, 8), num=11)
        alpha = 0.3

        #### plot out the raw intial expirement
        axs[0, 0].plot(i_g, q_g, 'ro', alpha=alpha, label='g')
        axs[0, 0].plot(i_e, q_e, 'bo', alpha=alpha, label='e')
        axs[0, 0].set_xlabel('I (a.u.)')
        axs[0, 0].set_ylabel('Q (a.u.)')
        axs[0, 0].set_title('Pi Pulse Calibration')
        i_0_lim = axs[0, 0].get_xlim()
        q_0_lim = axs[0, 0].get_ylim()

        #### plo out histograms for calibration
        xg = np.mean(i_g_rot)
        xe = np.mean(i_e_rot)
        xg_range = np.ptp(i_g_rot)
        xe_range = np.ptp(i_e_rot)
        if xg > xe:
            xlims = [xe - 0.6 * xe_range, xg + 0.6 * xg_range]
        else:
            xlims = [xg - 0.6 * xg_range, xe + 0.6 * xe_range]
        numbins = 200

        ng, binsg, pg = axs[0, 1].hist(i_g_rot, bins=numbins, range=xlims, color='r', label='g', alpha=0.5)
        ne, binse, pe = axs[0, 1].hist(i_e_rot, bins=numbins, range=xlims, color='b', label='e', alpha=0.5)
        axs[0, 1].set_xlabel('I (a.u.)')
        axs[0, 1].set_ylabel('counts')
        axs[0,1].axvline(x = self.threshold)
        axs[0, 1].set_title(f"Fidelity = {self.fid * 100:.2f}%")

        #### plot out the sorted intial expirmement
        axs[1, 0].plot(i_fast_1, q_fast_1, 'go', alpha=alpha, label='blob 1')
        axs[1, 0].plot(i_fast_2, q_fast_2, 'mo', alpha=alpha, label='blob 2')
        axs[1, 0].set_xlabel('I (a.u.)')
        axs[1, 0].set_ylabel('Q (a.u.)')
        axs[1, 0].set_title('sorted flux pulse data')
        axs[1, 0].set_xlim(i_0_lim)
        axs[1, 0].set_ylim(q_0_lim)

        #### plot of histogram of the sorted data
        nfast1, bins_fast1, p_fast1 = axs[1, 1].hist(i_fast_1_rot, bins=numbins, range=xlims, color='g', label='blob 1', alpha=0.5)
        nfast2, bins_fast2, p_fast2 = axs[1, 1].hist(i_fast_2_rot, bins=numbins, range=xlims, color='m', label='blob 2', alpha=0.5)
        axs[1, 1].set_xlabel('I (a.u.)')
        axs[1, 1].set_ylabel('counts')
        axs[1,1].axvline(x = self.threshold)

        plt.legend()

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

