from qick import *
from q3diamond.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from q3diamond.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time

# class OscillationsProgram_RAverager_Wrong(RAveragerProgram):
#     def initialize(self):
#         cfg = self.cfg
#
#         self.q_rp = self.ch_page(cfg["ff_ch"])  # get register page for qubit_ch
#         self.r_wait = 3
#         self.regwi(self.q_rp, self.r_wait, self.us2cycles(cfg["start"]))
#
#         self.declare_gen(ch=cfg["res_ch"], nqz=1)  # Readout
#         self.declare_gen(ch=cfg["qubit_ch"], nqz=2)  # Qubit
#         for ch in cfg["ro_chs"]:  # configure the readout lengths and downconversion frequencies
#             self.declare_readout(ch=ch, length=cfg["readout_length"],
#                                  freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])
#
#         f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
#         f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])
#
#         ### Start fast flux
#         self.declare_gen(ch=cfg["ff_ch"], nqz=cfg["ff_nqz"])
#         self.ff_freq = self.freq2reg(cfg["ff_freq"], gen_ch=cfg["ff_ch"])
#
#         self.ff_style = self.cfg["ff_pulse_style"]
#
#         if self.ff_style == 'const':
#             self.set_pulse_registers(ch=cfg["ff_ch"], style=self.ff_style, freq=self.ff_freq, phase=0, gain=cfg["ff_gain"],
#                                      length=cfg["sigma"] * 4 + self.us2cycles(0.1))
#         else:
#             print('No FF pulse style matches: currently only supports const')
#         ### Finish FF
#
#         # add qubit and readout pulses to respective channels
#         self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=cfg["sigma"] * 4)
#         self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=f_ge,
#                                  phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["pi_gain"],
#                                  waveform="qubit")
#
#         self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
#                                  gain=cfg["pulse_gain"],
#                                  length=cfg["length"])
#
#         self.sync_all(self.us2cycles(0.1))
#
#     def body(self):
#         self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns
#         self.set_pulse_registers(ch=self.cfg["ff_ch"], style=self.ff_style, freq=self.ff_freq, phase=0, gain=self.cfg["ff_gain"],
#                                  length=self.cfg["sigma"] * 4 + self.us2cycles(0.1))
#         self.pulse(ch=self.cfg['ff_ch'])
#
#         self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(0.1))  # play probe pulse
#         # self.sync_all(self.us2cycles(0.02))  # align channels and wait 50ns
#         self.sync_all()
#         self.set_pulse_registers(ch=self.cfg["ff_ch"], style=self.ff_style, freq=self.ff_freq, phase=0, gain= -30000,
#                                  length=10)
#         #Copy register value to length area
#         self.pulse(ch=self.cfg['ff_ch'])
#         # self.sync(self.q_rp, self.r_wait)
#
#         # self.sync_all() # Wrong Python function, does not account for updating length
#         self.sync(self.q_rp, self.r_wait)
#
#         self.set_pulse_registers(ch=self.cfg["ff_ch"], style=self.ff_style, freq=self.ff_freq, phase=0, gain= self.cfg["ff_gain"],
#                                  length= self.cfg["length"])
#         self.pulse(ch=self.cfg['ff_ch'])
#
#         # trigger measurement, play measurement pulse, wait for qubit to relax
#         self.measure(pulse_ch=self.cfg["res_ch"],
#                      adcs=self.ro_chs,
#                      adc_trig_offset=self.cfg["adc_trig_offset"],
#                      wait=True,
#                      syncdelay=self.us2cycles(self.cfg["relax_delay"]))
#
#
#     def update(self):
#         self.mathi(self.q_rp, self.r_wait, self.r_wait, '+', self.us2cycles(self.cfg["step"]))  # update frequency l

class OscillationsProgram(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=1)  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=2)  # Qubit
        for ch in cfg["ro_chs"]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        ### Start fast flux
        # self.declare_gen(ch=cfg["ff_ch"], nqz=cfg["ff_nqz"])
        self.ff_freq = self.freq2reg(cfg["ff_freq"], gen_ch=cfg["ff_ch"])
        #
        self.ff_style = self.cfg["ff_pulse_style"]
        #
        # if self.ff_style == 'const':
        #     self.set_pulse_registers(ch=cfg["ff_ch"], style=self.ff_style, freq=self.ff_freq, phase=0, gain=cfg["ff_gain"],
        #                              length=cfg["sigma"] * 4 + self.us2cycles(0.1))
        # else:
        #     print('No FF pulse style matches: currently only supports const')
        for FF_info in cfg["FF_list"]:
            FF_Channel, FF_gain = FF_info
            self.declare_gen(ch=FF_Channel, nqz=cfg["ff_nqz"])
            ff_freq = self.freq2reg(cfg["ff_freq"], gen_ch=FF_Channel)

            ff_style = self.cfg["ff_pulse_style"]

            if ff_style == 'const':
                self.set_pulse_registers(ch=FF_Channel, style=ff_style, freq=ff_freq, phase=0, gain=FF_gain,
                                         length=self.us2cycles(cfg["sigma"] * 4) + self.us2cycles(0.1))
            else:
                print('No FF pulse style matches: currently only supports const')

        self.FF_Channel1, self.FF_Gain1 = self.cfg["FF_list"][0]
        self.FF_Channel2, self.FF_Gain2 = self.cfg["FF_list"][1]

        ### Finish FF

        # add qubit and readout pulses to respective channels
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.us2cycles(cfg["sigma"]), length=self.us2cycles(cfg["sigma"] * 4))
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=f_ge,
                                 phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["pi_gain"],
                                 waveform="qubit")

        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        self.sync_all(self.us2cycles(0.1))

    def body(self):
        self.sync_all(self.us2cycles(0.05))  # align channels and wait 50ns
        # self.set_pulse_registers(ch=self.cfg["ff_ch"], style=self.ff_style, freq=self.ff_freq, phase=0, gain=self.cfg["ff_gain"],
        #                          length=self.cfg["sigma"] * 4 + self.us2cycles(0.1) )
        # self.pulse(ch=self.cfg['ff_ch'])
        self.set_pulse_registers(ch=self.FF_Channel1, style=self.ff_style, freq=self.ff_freq, phase=0, gain=self.FF_Gain1,
                                 length=self.us2cycles(self.cfg["sigma"] * 4 + 0.1) )
        self.set_pulse_registers(ch=self.FF_Channel2, style=self.ff_style, freq=self.ff_freq, phase=0, gain=self.FF_Gain2,
                                 length=self.us2cycles(self.cfg["sigma"] * 4 + 0.1) )

        self.pulse(ch=self.FF_Channel1)
        self.pulse(ch=self.FF_Channel2)

        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(0.1))  # play probe pulse

        self.sync_all()
        if self.cfg["variable_wait"] > 0.01:
            self.set_pulse_registers(ch=self.FF_Channel1, style=self.ff_style, freq=self.ff_freq, phase=0,
                                     gain=-1 * self.FF_Gain1,
                                     length=self.us2cycles(self.cfg["variable_wait"]))
            self.set_pulse_registers(ch=self.FF_Channel2, style=self.ff_style, freq=self.ff_freq, phase=0,
                                     gain=-1 * self.FF_Gain2,
                                     length=self.us2cycles(self.cfg["variable_wait"]))

            # self.set_pulse_registers(ch=self.FF_Channel1, style=self.ff_style, freq=self.ff_freq, phase=0, gain= -1 * self.cfg["ff_gain"],
            #                           length=self.us2cycles(self.cfg["variable_wait"])) #self.us2cycles(1))

            self.pulse(ch=self.FF_Channel1)
            self.pulse(ch=self.FF_Channel2)

            self.sync_all()

        # self.set_pulse_registers(ch=self.cfg["ff_ch"], style=self.ff_style, freq=self.ff_freq, phase=0, gain= self.cfg["ff_gain"],
        #                          length= self.cfg["length"])
        self.set_pulse_registers(ch=self.FF_Channel1, style=self.ff_style, freq=self.ff_freq, phase=0,
                                 gain=1 * self.FF_Gain1,
                                 length=self.us2cycles(self.cfg["length"]))
        self.set_pulse_registers(ch=self.FF_Channel2, style=self.ff_style, freq=self.ff_freq, phase=0,
                                 gain=1 * self.FF_Gain2,
                                 length=self.us2cycles(self.cfg["length"]))
        self.pulse(ch=self.FF_Channel1)
        self.pulse(ch=self.FF_Channel2)

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.ro_chs,
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=None)

        time_to_balance = self.us2cycles(self.cfg["length"]) - self.us2cycles(self.cfg["variable_wait"]) +  \
                                 self.us2cycles(self.cfg["sigma"] * 4) + self.us2cycles(0.1)
        if time_to_balance > 5:
            self.set_pulse_registers(ch=self.FF_Channel1, style=self.ff_style, freq=self.ff_freq, phase=0,
                                     gain=-1 * self.FF_Gain1,
                                     length=time_to_balance)
            self.set_pulse_registers(ch=self.FF_Channel2, style=self.ff_style, freq=self.ff_freq, phase=0,
                                     gain=-1 * self.FF_Gain2,
                                     length=time_to_balance)
            self.pulse(ch=self.FF_Channel1)
            self.pulse(ch=self.FF_Channel2)
            self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

        elif time_to_balance < -5:
            self.set_pulse_registers(ch=self.FF_Channel1, style=self.ff_style, freq=self.ff_freq, phase=0,
                                     gain= self.FF_Gain1,
                                     length= -1 * time_to_balance)
            self.set_pulse_registers(ch=self.FF_Channel2, style=self.ff_style, freq=self.ff_freq, phase=0,
                                     gain= self.FF_Gain2,
                                     length=-1 * time_to_balance)
            self.pulse(ch=self.FF_Channel1)
            self.pulse(ch=self.FF_Channel2)
            self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

        else:
            self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

        # self.sync_all(self.us2cycles(0.02))  # align channels and wait 50ns
        # self.sync_all()
        # self.set_pulse_registers(ch=self.cfg["ff_ch"], style=self.ff_style, freq=self.ff_freq, phase=0, gain= -1 * self.cfg["ff_gain"],
        #                          length=self.us2cycles(self.cfg["variable_wait"]))
        # self.pulse(ch=self.cfg['ff_ch'])
        # self.sync_all()
        # # self.sync(self.q_rp, self.r_wait)
        # # self.sync(self.q_rp, self.r_wait)
        #
        # self.set_pulse_registers(ch=self.cfg["ff_ch"], style=self.ff_style, freq=self.ff_freq, phase=0, gain= self.cfg["ff_gain"],
        #                          length= self.cfg["length"])
        # self.pulse(ch=self.cfg['ff_ch'])
        #
        # # trigger measurement, play measurement pulse, wait for qubit to relax
        # self.measure(pulse_ch=self.cfg["res_ch"],
        #              adcs=self.ro_chs,
        #              adc_trig_offset=self.cfg["adc_trig_offset"],
        #              wait=True,
        #              syncdelay=self.us2cycles(self.cfg["relax_delay"]))

class Oscillations(ExperimentClass):
    """
    Basic T1
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        # expt_cfg = {
        #     "center": self.cfg["pulse_freq"],
        #     "span": self.cfg["TransSpan"],
        #     "expts": self.cfg["TransNumPoitns"]
        # }
        # expt_cfg["step"] = 2 * expt_cfg["span"] / expt_cfg["expts"]
        # expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
        #############################################

        tpts = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])
        print(tpts)
        results = []
        start = time.time()
        for t in tqdm(tpts, position=0, disable=True):
            print(t)
            self.cfg["variable_wait"] = t
            prog = OscillationsProgram(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
            # time.sleep(5)
        print(f'Time: {time.time() - start}')
        results = np.transpose(results)

        data={'config': self.cfg, 'data': {'results': results, 'tpts':tpts}}
        self.data=data

        #### pull the data from the amp rabi sweep
        # prog = OscillationsProgram_RAverager_Wrong(self.soccfg, self.cfg)
        #
        # x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
        #                                  readouts_per_experiment=1, save_experiments=None,
        #                                  start_src="internal", progress=False, debug=False)
        # data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        # self.data = data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        # x_pts = data['data']['x_pts']
        # avgi = data['data']['avgi'][0][0]
        # avgq = data['data']['avgq'][0][0]

        x_pts = data['data']['tpts']
        avgi = data['data']['results'][0][0][0]
        avgq = data['data']['results'][0][0][1]


        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)
        plt.plot(x_pts, avgi, 'o-', label="i", color = 'orange')
        plt.ylabel("a.u.")
        plt.xlabel("Wait time (us)")
        plt.legend()
        plt.title(self.titlename)
        plt.savefig(self.iname[:-4] + 'I_Data.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

        fig = plt.figure(figNum+1)
        # sig = avgi + 1j * avgq
        # avgamp0 = np.abs(sig)
        plt.plot(x_pts, avgq, 'o-', label="q")
        plt.ylabel("a.u.")
        plt.xlabel("Wait time (us)")
        plt.legend()
        plt.title(self.titlename)


        plt.savefig(self.iname[:-4] + 'Q_Data.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

        fig = plt.figure(figNum+2)
        # sig = avgi + 1j * avgq
        # avgamp0 = np.abs(sig)
        plt.plot(x_pts, np.abs(avgi + 1j * avgq), 'o-', label="Amplitude")
        plt.ylabel("a.u.")
        plt.xlabel("Wait time (us)")
        plt.legend()
        plt.title(self.titlename)


        plt.savefig(self.iname[:-4] + 'Amp_Data.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

