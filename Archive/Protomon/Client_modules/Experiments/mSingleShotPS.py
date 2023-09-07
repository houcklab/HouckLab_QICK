from qick import *
import matplotlib.pyplot as plt
import numpy as np
from Protomon.Client_modules.CoreLib.Experiment import ExperimentClass
from Protomon.Client_modules.Helpers.hist_analysis import *
from Protomon.Client_modules.Helpers.MixedShots_analysis import *
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

class LoopbackProgramSingleShotPS(RAveragerProgram):
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
        qubit_freq = self.freq2reg(cfg["qubit_freq"],
                                   gen_ch=qubit_ch)  # convert frequency to dac frequency (ensuring it is an available adc frequency)

        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"]),
                           length=self.us2cycles(self.cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4

        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"]),
                           length=self.us2cycles(self.cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit",  length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4 + self.us2cycles(self.cfg["flat_top_length"])

        else:
            print("define pi or flat top pulse")

        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0, gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]),
                                 )  # mode="periodic")

        self.synci(200)  # give processor some time to configure pulses

        # self.r_thresh = 6

    def body(self):
        ### intial pause
        self.sync_all(self.us2cycles(0.05))
        #### measure starting ground states
        self.measure(pulse_ch=self.cfg["res_ch"],
             adcs=[0],
             adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]) )

        #### wait 10us
        self.sync_all(self.us2cycles(0.01))

        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.sync_all(self.us2cycles(0.010)) # wait 10ns after pulse ends
        self.measure(pulse_ch=self.cfg["res_ch"],
             adcs=[0],
             adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
             wait=True,
             syncdelay=self.us2cycles(self.cfg["relax_delay"]))

        # self.sync_all(self.us2cycles(self.cfg["relax_delay"]))


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

class SingleShotPS(ExperimentClass):
    """
    run a single shot expirement that utilizes a post selection process to handle thermal starting state
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        #### pull the data from the single hots
        prog = LoopbackProgramSingleShotPS(self.soccfg, self.cfg)
        ie_0, ie_1, qe_0, qe_1 = prog.acquire(self.soc, load_pulses=True, readouts_per_experiment=2, save_experiments=[0,1])
        ### run ground state expirement
        self.cfg["qubit_gain"] = 0
        prog = LoopbackProgramSingleShotPS(self.soccfg, self.cfg)
        ig_0, ig_1, qg_0, qg_1 = prog.acquire(self.soc, load_pulses=True, readouts_per_experiment=2, save_experiments=[0,1])

        #### sort into mixed states
        mixed_g0 = MixedShots(ig_0, qg_0, numbins=25)
        # mixed_g1 = MixedShots(ig_1, qg_1, numbins=25)
        # mixed_e0 = MixedShots(ie_0, qe_0, numbins=25)
        # mixed_e1 = MixedShots(ie_1, qe_1, numbins=25)

        #### rotate the full arrays
        theta = mixed_g0.theta  #### theta should be basically the same for all scans

        ig_0_rot, qg_0_rot = rotateBlob(ig_0, qg_0, theta)
        # ig_1_rot, qg_1_rot = rotateBlob(ig_1, qg_1, theta)
        ie_0_rot, qe_0_rot = rotateBlob(ie_0, qe_0, theta)
        # ie_1_rot, qe_1_rot = rotateBlob(ie_1, qe_1, theta)

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

        #### save the data
        data = {'config': self.cfg, 'data': {'i_g': i_g, 'q_g': q_g, 'i_e': i_e, 'q_e': q_e,
                                             'ig_0': ig_0, 'qg_0': qg_0, 'ie_0': ie_0, 'qe_0': qe_0,
                                             'ig_1': ig_1, 'qg_1': qg_1, 'ie_1': ie_1, 'qe_1': qe_1}}
        self.data = data

        ### use the helper histogram to find the fidelity and such
        fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=False, ran=20) ### arbitrary ran, change later

        self.fid = fid
        self.threshold = threshold
        self.angle = angle

        return data

    def display(self, data=None, plotDisp = False, figNum = 1, ran=None, **kwargs):
        if data is None:
            data = self.data

        i_g = data["data"]["i_g"]
        q_g = data["data"]["q_g"]
        i_e = data["data"]["i_e"]
        q_e = data["data"]["q_e"]

        ig_1 = data["data"]["ig_1"]
        qg_1 = data["data"]["qg_1"]
        ie_1 = data["data"]["ie_1"]
        qe_1 = data["data"]["qe_1"]

        #### plotting is handled by the helper histogram
        fid, threshold, angle = hist_process(data=[i_g, q_g, i_e, q_e], plot=plotDisp, ran=ran, figNum=1)
        plt.suptitle('selected data')
        plt.savefig(self.iname)

        fid, threshold, angle = hist_process(data=[ig_1, qg_1, ie_1, qe_1], plot=plotDisp, ran=ran, figNum=2)
        plt.suptitle('raw data')

        if plotDisp:
            plt.show(block=False)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


