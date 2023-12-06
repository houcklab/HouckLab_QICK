from qick import *
from WorkingProjects.Inductive_Coupler.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time


class AmplitudeRabiProgram(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get gain register for qubit_ch

        self.declare_gen(ch=cfg["res_ch"], nqz=1)  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=2)  # Qubit
        for ch in cfg["ro_chs"]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        # add qubit and readout pulses to respective channels
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=cfg["sigma"] * 4)
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=f_ge,
                                 phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
                                 waveform="qubit")
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        self.sync_all(self.us2cycles(500))

    def body(self):
        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns
        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns

        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.ro_chs,
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"])  # update gain of the Gaussian

class AmplitudeRabi(ExperimentClass):
    """
    Basic AmplitudeRabi
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        #### pull the data from the amp rabi sweep
        # prog = PulseProbeSpectroscopyProgram(self.soccfg, self.cfg)
        prog = AmplitudeRabiProgram(self.soccfg, self.cfg)

        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]

        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)
        plt.plot(x_pts, avgi, 'o-', label="i", color = 'orange')
        plt.plot(x_pts, avgq, label="q", color = 'blue')
        plt.ylabel("a.u.")
        plt.xlabel("qubit gain")
        plt.legend()
        plt.title(self.titlename)

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

        fig = plt.figure(figNum+1)
        sig = avgi + 1j * avgq
        avgamp0 = np.abs(sig)
        plt.plot(x_pts, avgamp0, label="Amplitude; ADC 0")
        plt.ylabel("a.u.")
        plt.xlabel("qubit gain")
        plt.legend()
        plt.title(self.titlename)

        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

#
# class LoopbackProgramSpecSlice(AveragerProgram):
#     def __init__(self, soccfg, cfg):
#         super().__init__(soccfg, cfg)
#
#     def initialize(self):
#         cfg = self.cfg
#         res_ch = cfg["res_ch"]
#         #         r_freq=self.sreg(cfg["res_ch"], "freq")   #Get frequency register for res_ch
#         self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])
#
#         # Qubit configuration
#         qubit_ch = cfg["qubit_ch"]
#         self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])
#
#         # configure the readout lengths and downconversion frequencies
#         for ro_ch in cfg["ro_chs"]:
#             self.declare_readout(ch=ro_ch, freq=cfg["pulse_freq"], length=cfg["readout_length"], gen_ch=cfg["res_ch"])
#         style = self.cfg["pulse_style"]
#         freq = self.freq2reg(cfg["pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][
#             0])  # convert frequency to dac frequency (ensuring it is an available adc frequency)
#
#         qubit_freq = self.freq2reg(cfg["qubit_freq"],
#                                    gen_ch=qubit_ch)  # convert frequency to dac frequency (ensuring it is an available adc frequency)
#
#         # print("generator freq:", self.reg2freq(freq, gen_ch=res_ch))
#         if style in ["flat_top", "arb"]:
#             sigma = cfg["sigma"]
#             nsigma = 5
#             samples_per_clock = self.soccfg['gens'][res_ch]['samps_per_clk']
#             idata = helpers.gauss(mu=sigma * samples_per_clock * nsigma / 2,
#                                   si=sigma * samples_per_clock,
#                                   length=sigma * samples_per_clock * nsigma,
#                                   maxv=np.iinfo(np.int16).max - 1)
#             self.add_pulse(ch=res_ch, name="measure", idata=idata)
#         if style == "const":
#             self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["pulse_gain"],
#                                      length=cfg["length"],
#                                      )  # mode="periodic")
#             #             self.set_pulse_registers(ch=qubit_ch, style=style, freq=qubit_freq, phase=0, gain=cfg["qubit_gain"],
#             #                                      length=cfg["qubit_length"],mode="periodic")
#             self.set_pulse_registers(ch=qubit_ch, style=style, freq=qubit_freq, phase=0, gain=cfg["qubit_gain"],
#                                      length=cfg["qubit_length"])
#
#         elif style == "flat_top":
#             self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["pulse_gain"],
#                                      waveform="measure", length=cfg["length"])
#         elif style == "arb":
#             self.set_pulse_registers(ch=res_ch, style=style, freq=freq, phase=0, gain=cfg["pulse_gain"],
#                                      waveform="measure")
#
#         self.synci(200)  # give processor some time to configure pulses
#
#     def body(self):
#         self.synci(200)  # give processor time to get ahead of the pulses
#
#         # Play qubit pulse
#         self.pulse(ch=self.cfg["qubit_ch"])  # play readout pulse
#         self.synci(1000)  # give processor time to get ahead of the pulses
#
#         # self.sync_all()
#         # Play measurement pulse and trigger readout
#         self.trigger(adcs=self.ro_chs, pins=[0],
#                      adc_trig_offset=self.cfg["adc_trig_offset"])  # trigger the adc acquisition
#         self.pulse(ch=self.cfg["res_ch"])  # play readout pulse
#         # control should wait until the readout is over
#         self.waiti(0, self.cfg["adc_trig_offset"] + self.cfg["readout_length"])
#         self.sync_all(self.us2cycles(self.cfg["relax_delay"]))  # sync all channels
#
#
# class PulseProbeSpectroscopyProgram(RAveragerProgram):
#     def initialize(self):
#         cfg = self.cfg
#
#         self.declare_gen(ch=cfg["res_ch"], nqz=1)  # Readout
#         self.declare_gen(ch=cfg["qubit_ch"], nqz=2)  # Qubit
#         for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
#             self.declare_readout(ch=ch, length=cfg["readout_length"],
#                                  freq=cfg["f_res"], gen_ch=cfg["res_ch"])
#
#         self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
#         self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch
#
#         f_res = self.freq2reg(cfg["f_res"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value
#
#         self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
#         self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])
#
#         # add qubit and readout pulses to respective channels
#         self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0, gain=cfg["qubit_gain"],
#                                  length=cfg["probe_length"])
#         self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
#                                  gain=cfg["res_gain"],
#                                  length=cfg["readout_length"])
#
#         self.sync_all(self.us2cycles(1))
#
#     def body(self):
#         self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
#         self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns
#
#         # trigger measurement, play measurement pulse, wait for qubit to relax
#         self.measure(pulse_ch=self.cfg["res_ch"],
#                      adcs=[0, 1],
#                      adc_trig_offset=self.cfg["adc_trig_offset"],
#                      wait=True,
#                      syncdelay=self.us2cycles(self.cfg["relax_delay"]))
#
#     def update(self):
#         self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index
# # ====================================================== #
#
# class SpecSlice(ExperimentClass):
#     """
#     Basic spec experiement that takes a single slice of data
#     """
#
#     def __init__(self, soc=None, soccfg=None, path='', prefix='data', cfg=None, config_file=None, progress=None):
#         super().__init__(soc=soc, soccfg=soccfg, path=path, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)
#
#     def acquire(self, progress=False, debug=False):
#         expt_cfg = {
#                 "center": self.cfg["qubit_freq"],
#                 "span": self.cfg["SpecSpan"],
#                 "expts": self.cfg["SpecNumPoitns"]
#         }
#         expt_cfg["step"] = 2 * expt_cfg["span"] / expt_cfg["expts"]
#         expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
#         fpts = expt_cfg["start"] + expt_cfg["step"] * np.arange(expt_cfg["expts"])
#         results = []
#         start = time.time()
#         for f in tqdm(fpts, position=0, disable=True):
#             self.cfg["qubit_freq"] = f
#             prog = LoopbackProgramSpecSlice(self.soccfg, self.cfg)
#             results.append(prog.acquire(self.soc, load_pulses=True))
#         print(f'Time: {time.time() - start}')
#         results = np.transpose(results)
#         #
#         # prog = LoopbackProgram(self.soccfg, self.cfg)
#         # self.soc.reset_gens()  # clear any DC or periodic values on generators
#         # iq_list = prog.acquire_decimated(self.soc, load_pulses=True, progress=False, debug=False)
#         data={'config': self.cfg, 'data': {'results': results, 'fpts':fpts}}
#         self.data=data
#
#         #### find the frequency corresponding to the qubit dip
#         sig = data['data']['results'][0][0][0] + 1j * data['data']['results'][0][0][1]
#         avgamp0 = np.abs(sig)
#         peak_loc = np.argmin(avgamp0)
#         self.qubitFreq = data['data']['fpts'][peak_loc]
#
#         return data
#
#     def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
#         if data is None:
#             data = self.data
#         plt.figure(figNum)
#         x_pts = data['data']['fpts'] /1e3 #### put into units of frequency GHz
#         sig = data['data']['results'][0][0][0] + 1j * data['data']['results'][0][0][1]
#         avgamp0 = np.abs(sig)
#         # plt.plot(x_pts, results[0][0][0],label="I value; ADC 0")
#         # plt.plot(x_pts, results[0][0][1],label="Q value; ADC 0")
#         plt.plot(x_pts, avgamp0, label="Amplitude; ADC 0")
#         plt.ylabel("a.u.")
#         plt.xlabel("Qubit Frequency (GHz)")
#         plt.title("Averages = " + str(self.cfg["reps"]))
#
#         plt.savefig(self.iname)
#
#         if plotDisp:
#             plt.show(block=True)
#             plt.pause(0.1)
#
#     def save_data(self, data=None):
#         print(f'Saving {self.fname}')
#         super().save_data(data=data['data'])
#
#
