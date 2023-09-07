from qick import *
from q3diamond.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from q3diamond.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time



class Transmission_No_PiPulse(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)
    def initialize(self):
        cfg = self.cfg
        res_ch = cfg["res_ch"]
        #         r_freq=self.sreg(cfg["res_ch"], "freq")   #Get frequency register for res_ch
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])

        # configure the readout lengths and downconversion frequencies
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["pulse_freq"], length=cfg["readout_length"], gen_ch=cfg["res_ch"])

        style = self.cfg["pulse_style"]
        freq = self.freq2reg(cfg["pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][
            0])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        # print("generator freq:", self.reg2freq(freq, gen_ch=res_ch))

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
            self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["pulse_gain"],
                                     length=cfg["length"],
                                     )  # mode="periodic")
        elif style == "flat_top":
            self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["pulse_gain"],
                                     waveform="measure", length=cfg["length"])
        elif style == "arb":
            self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["pulse_gain"],
                                     waveform="measure")

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.synci(200)  # give processor time to get ahead of the pulses
        self.trigger(adcs=self.ro_chs, pins=[0],
                     adc_trig_offset=self.cfg["adc_trig_offset"])  # trigger the adc acquisition
        self.pulse(ch=self.cfg["res_ch"])  # play readout pulse
        # control should wait until the readout is over
        self.waiti(0, self.cfg["adc_trig_offset"] + self.cfg["readout_length"])
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))  # sync all channels



class Transmission_PiPulse(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])  # Readout
        for ch in cfg["ro_chs"]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=cfg["readout_length"],
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])
        freq = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"],
                             ro_ch=cfg["ro_chs"][0])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=freq, phase=0, gain=cfg["pulse_gain"],
                                 length=cfg["length"])

        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.cfg["adc_trig_offset"],
                     wait=False,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

class Transmission_PiPulse(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=1)  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=2)  # Qubit
        for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=cfg["readout_length"],
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value
        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        # add qubit and readout pulses to respective channels
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=cfg["sigma"] * 4)
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=f_ge,
                                 phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["pi_gain"],
                                 waveform="qubit")
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=cfg["length"])

        self.sync_all(self.us2cycles(0.1))

    def body(self):
        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns

        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0, 1],
                     adc_trig_offset=self.cfg["adc_trig_offset"],
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

class Transmission_NoPiPulse(AveragerProgram):
        def initialize(self):
            cfg = self.cfg
            self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"],
                             ro_ch=cfg["ro_chs"][0])  # Readout
            for ch in cfg["ro_chs"]:  # configure the readout lengths and downconversion frequencies
                self.declare_readout(ch=ch, length=cfg["readout_length"],
                                     freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])
            freq = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"],
                                 ro_ch=cfg["ro_chs"][
                                     0])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
            self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=freq, phase=0, gain=cfg["pulse_gain"],
                                     length=cfg["length"])

            self.synci(200)  # give processor some time to configure pulses

        def body(self):
            self.measure(pulse_ch=self.cfg["res_ch"],
                         adcs=[0],
                         adc_trig_offset=self.cfg["adc_trig_offset"],
                         wait=False,
                         syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    # ====================================================== #

class Optimize_Power(ExperimentClass):
    """
    Transmission Experiment basic
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None,
                 cavityAtten = None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg,
                         config_file=config_file, progress=progress, cavityAtten = cavityAtten)

    def acquire(self, progress=False, debug=False):
        expt_cfg = {
                "start": self.cfg["CavityAtten_Start"],
                "end": self.cfg["CavityAtten_End"],
                "expts": self.cfg["CavityAtten_Points"]
        }

        if self.cavityAtten == None:
            print('Didnt define attenuator!!!!')

        results_pipulse = []
        results_nopipulse = []

        start = time.time()
        atten_points = np.linspace(self.cfg["CavityAtten_Start"], self.cfg["CavityAtten_End"],
                                   self.cfg["CavityAtten_Points"])
        for power in tqdm(atten_points, position=0, disable=True):
            self.cavityAtten.SetAttenuation(power, printOut=True)
            time.sleep(2)
            prog = Transmission_NoPiPulse(self.soccfg, self.cfg)
            prog_Pi = Transmission_PiPulse(self.soccfg, self.cfg)
            results_pipulse.append(prog.acquire(self.soc, load_pulses=True))
            results_nopipulse.append(prog_Pi.acquire(self.soc, load_pulses=True))

        print(f'Time: {time.time() - start}')
        results = np.transpose(results_nopipulse)
        results_pi = np.transpose(results_pipulse)

        #
        # prog = LoopbackProgram(self.soccfg, self.cfg)
        # self.soc.reset_gens()  # clear any DC or periodic values on generators
        # iq_list = prog.acquire_decimated(self.soc, load_pulses=True, progress=False, debug=False)
        data={'config': self.cfg, 'data': {'results': results, 'results_pi': results_pi, 'atten_pts':atten_points}}
        self.data=data

        #### find the frequency corresponding to the peak



        return data

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data
        x_pts = data['data']['atten_pts'] #### put into units of frequency GHz
        I_data = data['data']['results'][0][0][0]
        Q_data = data['data']['results'][0][0][1]
        I_data_Pi = data['data']['results_pi'][0][0][0]
        Q_data_Pi = data['data']['results_pi'][0][0][1]
        sig = I_data + 1j * Q_data
        sig_pi = I_data_Pi + 1j * Q_data_Pi

        avgamp = np.abs(sig)
        avgamp_pi = np.abs(sig_pi)



        # plt.plot(x_pts, results[0][0][0],label="I value; ADC 0")
        # plt.plot(x_pts, results[0][0][1],label="Q value; ADC 0")
        plt.figure(figNum)
        plt.plot(x_pts, np.abs(avgamp - avgamp_pi), label="Amplitude; ADC 0")
        plt.ylabel("a.u.")
        plt.xlabel("Cavity Frequency (GHz)")
        plt.title(self.titlename)

        plt.savefig(self.iname[:-4] + "abs_amp.png")

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        plt.figure(figNum + 1)
        plt.plot(x_pts, np.abs(I_data - I_data_Pi), 'o-', label="Q_data")
        plt.plot(x_pts, np.abs(Q_data - Q_data_Pi), 'o-', label="I Data")

        plt.ylabel("a.u.")
        plt.xlabel("Cavity Frequency (GHz)")
        plt.title(self.titlename)

        plt.savefig(self.iname[:-4] + "IQ_data.png")

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)

        plt.figure(figNum + 2)
        plt.plot(x_pts, np.abs(np.angle(sig) - np.angle(sig_pi)), 'o-', label="Phase")

        plt.ylabel("a.u.")
        plt.xlabel("Cavity Frequency (GHz)")
        plt.title(self.titlename)

        plt.savefig(self.iname[:-4] + "Phase.png")

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

