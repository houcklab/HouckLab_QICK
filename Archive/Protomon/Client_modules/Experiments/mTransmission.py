from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from Protomon.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time
from scipy.signal import savgol_filter


class LoopbackProgramTrans(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])

        self.set_pulse_registers(ch=cfg["res_ch"], style=cfg["read_pulse_style"], freq=freq, phase=0, gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]) )#)
        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"],ro_ch=self.cfg["ro_chs"][0]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

# ====================================================== #


class Transmission(ExperimentClass):
    """
    Transmission Experiment basic
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        # expt_cfg = {
        #         "center": self.cfg["read_pulse_freq"],
        #         "span": self.cfg["TransSpan"],
        #         "expts": self.cfg["TransNumPoints"]
        # }
        # expt_cfg["step"] = 2 * expt_cfg["span"] / expt_cfg["expts"]
        # expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
        # fpts = expt_cfg["start"] + expt_cfg["step"] * np.arange(expt_cfg["expts"]
        expt_cfg = {
            ### transmission parameters
            "trans_freq_start": self.cfg["trans_freq_start"],  # [MHz] actual frequency is this number + "cavity_LO"
            "trans_freq_stop": self.cfg["trans_freq_stop"],  # [MHz] actual frequency is this number + "cavity_LO"
            "TransNumPoints": self.cfg["TransNumPoints"],  ### number of points in the transmission frequecny
        }
        self.cfg["reps"] = self.cfg["trans_reps"]
        ### take the transmission data
        fpts = np.linspace(expt_cfg["trans_freq_start"], expt_cfg["trans_freq_stop"], expt_cfg["TransNumPoints"])
        results = []
        print("beginning acquire transmission")
        print(self.cfg)
        start = time.time()
        for f in tqdm(fpts, position=0, disable=True):
            self.cfg["read_pulse_freq"] = f
            prog = LoopbackProgramTrans(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
        print(f'Time: {time.time() - start}')
        results = np.transpose(results)
        #
        # prog = LoopbackProgram(self.soccfg, self.cfg)
        # self.soc.reset_gens()  # clear any DC or periodic values on generators
        # iq_list = prog.acquire_decimated(self.soc, load_pulses=True, progress=False, debug=False)
        data={'config': self.cfg, 'data': {'results': results, 'fpts':fpts}}
        self.data=data

        return data

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        while plt.fignum_exists(num = figNum): ###account for if figure with number already exists
            figNum += 1

        fig, axs = plt.subplots(4, num=figNum)

        x_pts = (data['data']['fpts'] + self.cfg["cavity_LO"]/1e6) /1e3 #### put into units of frequency GHz
        iavg = data['data']['results'][0][0][0]
        qavg = data['data']['results'][0][0][1]
        sig = iavg + 1j * qavg
        ampdata = np.abs(sig)
        phasedata = np.arctan2(qavg, iavg)

        # Smooth out the fit array and overlay that smoothed fit
        smoothed = savgol_filter(ampdata, np.shape(data['data']['fpts'])[0], 10) ## Figure out if 51, 3 is correct

        # peak_loc = np.argmin(smoothed)
        peak_loc = np.argmin(ampdata)
        self.peakFreq = data['data']['fpts'][peak_loc]


        # plt.plot(x_pts, data['data']['results'][0][0][0],label="I value; ADC 0")
        # plt.plot(x_pts, data['data']['results'][0][0][1],label="Q value; ADC 0")
        axs[0].plot(x_pts, ampdata, label="Amplitude")
        # axs[0].plot(x_pts, smoothed, label="Smoothed amplitude")
        axs[0].legend(loc='upper left')
        axs[1].plot(x_pts, phasedata, label="Phase")
        axs[1].legend(loc='upper left')
        axs[2].plot(x_pts, iavg, label="I")
        axs[2].legend(loc='upper left')
        axs[3].plot(x_pts, qavg, label="Q")
        axs[3].legend(loc='upper left')

        #
        # plt.ylabel("a.u.")
        # plt.xlabel("Cavity Frequency (GHz)")
        # plt.title("Averages = " + str(self.cfg["reps"]))
        plt.tight_layout()
        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=False)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
