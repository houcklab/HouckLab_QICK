from qick import *
# from WorkingProjects.Inductive_Coupler.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time


class SingleToneSpectroscopyProgramFF(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])  # Readout
        for ch in cfg["ro_chs"]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])
        freq = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"],
                             ro_ch=cfg["ro_chs"][0])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=freq, phase=0, gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))
        ### Start FF
        for FF_info in cfg["FF_list_read"]:
            FF_Channel, FF_gain = FF_info
            self.declare_gen(ch=FF_Channel, nqz=cfg["ff_nqz"])
            ff_freq = self.freq2reg(cfg["ff_freq"], gen_ch=FF_Channel)

            ff_style = self.cfg["ff_pulse_style"]

            if ff_style == 'const':
                self.set_pulse_registers(ch=FF_Channel, style=ff_style, freq=ff_freq, phase=0, gain=FF_gain,
                                         length=self.us2cycles(cfg["length"]))
            else:
                print('No FF pulse style matches: currently only supports const')

        self.FF_Channel1, self.FF_Gain1 = self.cfg["FF_list_read"][0]
        self.FF_Channel2, self.FF_Gain2 = self.cfg["FF_list_read"][1]
        self.FF_Channel3, self.FF_Gain3 = self.cfg["FF_list_read"][2]

        #End FF

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.pulse(ch=self.FF_Channel1)
        self.pulse(ch=self.FF_Channel2)
        self.pulse(ch=self.FF_Channel3)

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=False,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))


    # ====================================================== #

class TransmissionFF(ExperimentClass):
    """
    Transmission Experiment basic
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        expt_cfg = {
                "center": self.cfg["pulse_freq"],
                "span": self.cfg["TransSpan"],
                "expts": self.cfg["TransNumPoints"]
        }
        expt_cfg["step"] = 2 * expt_cfg["span"] / expt_cfg["expts"]
        expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
        fpts = expt_cfg["start"] + expt_cfg["step"] * np.arange(expt_cfg["expts"])
        results = []
        start = time.time()
        for f in tqdm(fpts, position=0, disable=True):
            self.cfg["pulse_freq"] = f
            prog = SingleToneSpectroscopyProgramFF(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
        print(f'Time: {time.time() - start}')
        results = np.transpose(results)
        #
        # prog = LoopbackProgram(self.soccfg, self.cfg)
        # self.soc.reset_gens()  # clear any DC or periodic values on generators
        # iq_list = prog.acquire_decimated(self.soc, load_pulses=True, progress=False, debug=False)
        data={'config': self.cfg, 'data': {'results': results, 'fpts':fpts}}
        self.data=data

        #### find the frequency corresponding to the peak
        sig = data['data']['results'][0][0][0] + 1j * data['data']['results'][0][0][1]
        avgamp0 = np.abs(sig)
        peak_loc = np.argmin(avgamp0)
        self.peakFreq_min = data['data']['fpts'][peak_loc]
        peak_loc = np.argmax(avgamp0)
        self.peakFreq_max = data['data']['fpts'][peak_loc]

        return data

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        avgi = data['data']['results'][0][0][0]
        avgq = data['data']['results'][0][0][1]
        x_pts = (data['data']['fpts'] + self.cfg["cavity_LO"] / 1e6) / 1e3  #### put into units of frequency GHz
        sig = data['data']['results'][0][0][0] + 1j * data['data']['results'][0][0][1]
        avgamp0 = np.abs(sig)

        plt.figure(figNum)
        plt.plot(x_pts, avgi, '.-', color = 'Green', label="I")
        plt.plot(x_pts, avgq, '.-', color = 'Blue', label="Q")
        plt.plot(x_pts, avgamp0, color = 'Magenta', label="Amp")
        plt.ylabel("a.u.")
        plt.xlabel("Cavity Frequency (GHz)")
        plt.title(self.titlename)
        plt.legend()

        plt.savefig(self.iname[:-4] + '_IQ.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)


        # plt.figure(figNum + 1)
        # plt.plot(x_pts, avgamp0, label="Amplitude; ADC 0")
        # plt.ylabel("a.u.")
        # plt.xlabel("Cavity Frequency (GHz)")
        # plt.title(self.titlename)
        #
        # plt.savefig(self.iname)
        #
        # if plotDisp:
        #     plt.show(block=True)
        #     plt.pause(0.1)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])





