from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from WTF.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time

class LoopbackProgramTransFF(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        res_ch = cfg["res_ch"]
        #         r_freq=self.sreg(cfg["res_ch"], "freq")   #Get frequency register for res_ch
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])

        # configure the readout lengths and downconversion frequencies
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"], length=self.us2cycles((cfg["read_length"]), gen_ch=cfg["res_ch"]))

        style = self.cfg["read_pulse_style"]
        freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][
            0])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        # print("generator freq:", self.reg2freq(freq, gen_ch=res_ch))

        ##### define a fast flux pulse
        self.set_pulse_registers(ch=self.cfg["ff_ch"], style="const", freq=0, phase=0,
                                 gain=self.cfg["ff_gain"],
                                 length=self.us2cycles(self.cfg["ff_length"]))
        self.cfg["ff_length_total"] = self.us2cycles(self.cfg["ff_length"] * 10)

        if style in ["flat_top", "arb"]:
            sigma = cfg["sigma"]
            nsigma = 5
            samples_per_clock = self.soccfg['gens'][res_ch]['samps_per_clk']
            idata = helpers.gauss(mu=sigma * samples_per_clock * nsigma / 2,
                                  si=sigma * samples_per_clock,
                                  length=sigma * samples_per_clock * nsigma,
                                  maxv=np.iinfo(np.int16).max - 1)
            self.add_pulse(ch=res_ch, name="measure", idata=idata)

        if style == "const":
            self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["read_pulse_gain"],
                                     length=self.us2cycles(cfg["read_length"]), )  # mode="periodic")
        elif style == "flat_top":
            self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["read_pulse_gain"],
                                     waveform="measure", length=self.us2cycles(cfg["read_length"]) )
        elif style == "arb":
            self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["read_pulse_gain"],
                                     waveform="measure")

        ### define the amount of time to wait between starting the flux pulse and running the qubit and cavity pulses
        self.res_wait = ( self.cfg["ff_length_total"] - self.us2cycles(self.cfg["read_length"]) - self.us2cycles(1))

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.synci(200)  # give processor time to get ahead of the pulses

        # ##### run the fast flux pulse 10 times
        self.pulse(ch=self.cfg["ff_ch"])  # play pulse
        self.pulse(ch=self.cfg["ff_ch"])  # play pulse
        self.pulse(ch=self.cfg["ff_ch"])  # play pulse
        self.pulse(ch=self.cfg["ff_ch"])  # play pulse
        self.pulse(ch=self.cfg["ff_ch"])  # play pulse
        self.pulse(ch=self.cfg["ff_ch"])  # play pulse
        self.pulse(ch=self.cfg["ff_ch"])  # play pulse
        self.pulse(ch=self.cfg["ff_ch"])  # play pulse
        self.pulse(ch=self.cfg["ff_ch"])  # play pulse
        self.pulse(ch=self.cfg["ff_ch"])  # play pulse
        self.synci(self.res_wait) # wait to play other pulses

        self.trigger(adcs=self.ro_chs, pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]))  # trigger the adc acquisition
        self.pulse(ch=self.cfg["res_ch"])  # play readout pulse
        # control should wait until the readout is over
        self.waiti(0, self.us2cycles(self.cfg["adc_trig_offset"]) + self.us2cycles(self.cfg["read_length"]) )
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))  # sync all channels


# ====================================================== #

class TransmissionFF(ExperimentClass):
    """
    Transmission Experiment basic
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        expt_cfg = {
                "center": self.cfg["read_pulse_freq"],
                "span": self.cfg["TransSpan"],
                "expts": self.cfg["TransNumPoitns"]
        }
        expt_cfg["step"] = 2 * expt_cfg["span"] / expt_cfg["expts"]
        expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
        fpts = expt_cfg["start"] + expt_cfg["step"] * np.arange(expt_cfg["expts"])
        results = []
        start = time.time()
        for f in tqdm(fpts, position=0, disable=True):
            self.cfg["read_pulse_freq"] = f
            prog = LoopbackProgramTransFF(self.soccfg, self.cfg)
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
        peak_loc = np.argmax(avgamp0)
        self.peakFreq = data['data']['fpts'][peak_loc]

        return data

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        while plt.fignum_exists(num = figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)

        x_pts = (data['data']['fpts'] + self.cfg["cavity_LO"]/1e6) /1e3 #### put into units of frequency GHz
        sig = data['data']['results'][0][0][0] + 1j * data['data']['results'][0][0][1]
        avgamp0 = np.abs(sig)
        # plt.plot(x_pts, results[0][0][0],label="I value; ADC 0")
        # plt.plot(x_pts, results[0][0][1],label="Q value; ADC 0")
        plt.plot(x_pts, avgamp0, label="Amplitude; ADC 0")
        plt.ylabel("a.u.")
        plt.xlabel("Cavity Frequency (GHz)")
        plt.title("Averages = " + str(self.cfg["reps"]))

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


