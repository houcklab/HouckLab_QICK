from qick import *
from q4diamond.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from q4diamond.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
from q4diamond.Client_modules.Helpers.rotate_SS_data import *
import time

# class OscillationsProgram_RAverager_Wrong(RAveragerProgram):
#     def initialize(self):
#         cfg = self.cfg
#
#         self.q_rp = self.ch_page(cfg["ff_ch"])  # get register page for qubit_ch
#         self.r_wait = 3
#         self.regwi(self.q_rp, self.r_wait, self.us2cycles(cfg["start"]))
#
#         self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
#         self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
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

class OscillationsProgramSS(AveragerProgram):
    def initialize(self):
        cfg = self.cfg

        res_ch = cfg["res_ch"]
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])
        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])

        for ro_ch in cfg["ro_chs"]:
            # self.declare_readout(ch=ro_ch, freq=cfg["pulse_freq"],
            #                      length=self.us2cycles(self.cfg["state_readout_length"]), gen_ch=cfg["res_ch"])
            self.declare_readout(ch=ro_ch, freq=cfg["pulse_freq"],
                                 length=self.us2cycles(self.cfg["readout_length"]), gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][0])
        # convert frequency to dac frequency (ensuring it is an available adc frequency)
        qubit_freq = self.freq2reg(cfg["qubit_freq"],
                                   gen_ch=qubit_ch)


        # self.declare_gen(ch=cfg["res_ch"], nqz=1)  # Readout
        # self.declare_gen(ch=cfg["qubit_ch"], nqz=2)  # Qubit
        # for ch in cfg["ro_chs"]:  # configure the readout lengths and downconversion frequencies
        #     self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
        #                          freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])
        #
        # f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
        # f_ge = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg["qubit_ch"])

        ### Start fast flux
        # self.declare_gen(ch=cfg["ff_ch"], nqz=cfg["ff_nqz"])
        for FF_info in cfg["FF_list_readout"]:
            self.declare_gen(ch=FF_info[0], nqz=cfg["ff_nqz"])

        self.ff_freq = self.freq2reg(cfg["ff_freq"], gen_ch=cfg["ff_ch"])
        self.ff_style = self.cfg["ff_pulse_style"]

        ### Finish FF
        self.FF_Channel1, self.FF_Gain1_readout = self.cfg["FF_list_readout"][0]
        self.FF_Channel2, self.FF_Gain2_readout = self.cfg["FF_list_readout"][1]
        self.FF_Channel3, self.FF_Gain3_readout = self.cfg["FF_list_readout"][2]


        self.FF_Gain1_exp = self.cfg["FF_list_exp"][0][1]
        self.FF_Gain2_exp = self.cfg["FF_list_exp"][1][1]
        self.FF_Gain3_exp = self.cfg["FF_list_exp"][2][1]

        self.FFChannels = [self.FF_Channel1, self.FF_Channel2, self.FF_Channel3]
        self.FFReadouts = np.array([self.FF_Gain1_readout, self.FF_Gain2_readout, self.FF_Gain3_readout])
        self.FFExpts = np.array([self.FF_Gain1_exp, self.FF_Gain2_exp, self.FF_Gain3_exp])

        ### Finish FF

        # add qubit and readout pulses to respective channels

        self.qubit_pulseLength = self.us2cycles(cfg["sigma"] * 4)
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=self.us2cycles(cfg["sigma"]), length=self.qubit_pulseLength)
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=qubit_freq,
                                 phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"] ,
                                 waveform="qubit")

        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=read_freq, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        self.sync_all(200)  # give processor some time to configure pulses

    def body(self):
        self.sync_all(200)  # align channels and wait 50ns
        self.FFPulses([-1 * x for x in self.FFReadouts], self.qubit_pulseLength + self.us2cycles(0.01))
        self.sync_all(self.us2cycles(0.1))

        self.FFPulses(self.FFReadouts, self.qubit_pulseLength + self.us2cycles(0.01))

        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(0.01))  # play probe pulse

        self.sync_all()
        if self.cfg["variable_wait"] > 0.01:
            self.FFPulses([-5000, -5000, 700], 4)
            # self.FFPulses(self.FFExpts, 4)
            # self.FFPulses(self.FFReadouts, 4)


            self.FFPulses(self.FFExpts, self.us2cycles(self.cfg["variable_wait"]))

            self.sync_all()

        self.FFPulses([int(x * 2) for x in self.FFReadouts], 3)
        self.FFPulses(self.FFReadouts, self.us2cycles(self.cfg["length"]))



        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(0.05))

        self.FFPulses([-1 * x for x in self.FFReadouts], self.us2cycles(self.cfg["length"]))

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

        # time_to_balance = self.us2cycles(self.cfg["length"]) - self.us2cycles(self.cfg["variable_wait"]) +  \
        #                          self.us2cycles(self.cfg["sigma"] * 4) + self.us2cycles(0.1)
        # if time_to_balance > 5:
        #     self.set_pulse_registers(ch=self.FF_Channel1, style=self.ff_style, freq=self.ff_freq, phase=0,
        #                              gain=-1 * self.FF_Gain1,
        #                              length=time_to_balance)
        #     self.set_pulse_registers(ch=self.FF_Channel2, style=self.ff_style, freq=self.ff_freq, phase=0,
        #                              gain=-1 * self.FF_Gain2,
        #                              length=time_to_balance)
        #     self.pulse(ch=self.FF_Channel1)
        #     self.pulse(ch=self.FF_Channel2)
        #     self.sync_all(self.us2cycles(self.cfg["relax_delay"]))
        #
        # elif time_to_balance < -5:
        #     self.set_pulse_registers(ch=self.FF_Channel1, style=self.ff_style, freq=self.ff_freq, phase=0,
        #                              gain= self.FF_Gain1,
        #                              length= -1 * time_to_balance)
        #     self.set_pulse_registers(ch=self.FF_Channel2, style=self.ff_style, freq=self.ff_freq, phase=0,
        #                              gain= self.FF_Gain2,
        #                              length=-1 * time_to_balance)
        #     self.pulse(ch=self.FF_Channel1)
        #     self.pulse(ch=self.FF_Channel2)
        #     self.sync_all(self.us2cycles(self.cfg["relax_delay"]))
        #
        # else:

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=1,
                save_experiments=None,
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress, debug=debug)

        return self.collect_shots()

    def collect_shots(self):
        shots_i0 = self.di_buf[0].reshape((1, self.cfg["reps"])) / self.us2cycles(
            self.cfg['readout_length'], ro_ch=0)
        shots_q0 = self.dq_buf[0].reshape((1, self.cfg["reps"])) / self.us2cycles(
            self.cfg['readout_length'], ro_ch=0)

        return shots_i0, shots_q0

    def FFPulses(self, list_of_gains, length):
        for i, gain in enumerate(list_of_gains):
            self.set_pulse_registers(ch=self.FFChannels[i], style=self.ff_style, freq=self.ff_freq, phase=0,
                                     gain=gain,
                                     length=length)
        self.pulse(ch=self.FF_Channel1)
        self.pulse(ch=self.FF_Channel2)
        self.pulse(ch=self.FF_Channel3)


class Oscillations_SS(ExperimentClass):
    """
    Basic T1
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, threshold = None, angle = None, progress=False, debug=False):

        # expt_cfg = {
        #     "center": self.cfg["pulse_freq"],
        #     "span": self.cfg["TransSpan"],
        #     "expts": self.cfg["TransNumPoitns"]
        # }
        # expt_cfg["step"] = 2 * expt_cfg["span"] / expt_cfg["expts"]
        # expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
        #############################################

        tpts = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])
        self.cfg["reps"] = self.cfg["shots"]
        print(tpts)
        results = []
        start = time.time()
        for t in tqdm(tpts, position=0, disable=True):
            print(t)
            self.cfg["variable_wait"] = t
            prog = OscillationsProgramSS(self.soccfg, self.cfg)
            shots_i0, shots_q0 = prog.acquire(self.soc,
                                              load_pulses=True)
            # print(np.median(shots_i0), np.median(shots_q0))
            # results.append((shots_i0[0], shots_q0[0]))
            rotated_iq = rotate_data((shots_i0, shots_q0), theta=angle)
            # plt.figure(10, figsize=(10, 7))
            # plt.scatter(rotated_iq[0], rotated_iq[1], label='g', color='r', marker='*', alpha=0.5)
            # plt.axvline(threshold, 0, 20, color='black', alpha=0.7, ls='--')

            # plt.show()

            # print("angle ", angle)
            # print("threshold: ", threshold)
            excited_percentage = count_percentage(rotated_iq, threshold = threshold)
            # excited_percentage = average_data(rotated_iq)

            # print('Excited perc. :', excited_percentage)
            results.append(excited_percentage)
            # time.sleep(5)
        print(f'Time: {time.time() - start}')
        # results = np.transpose(results)

        data={'config': self.cfg, 'data': {'results': results, 'tpts':tpts, 'thresholds': (threshold, angle)}}
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
        percent_excited = data['data']['results']
        # avgi = data['data']['results'][0][0][0]
        # avgq = data['data']['results'][0][0][1]


        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)
        plt.plot(x_pts, percent_excited, 'o-', label="i", color = 'orange')
        plt.ylabel("Excited Population")
        plt.xlabel("Wait time (us)")
        plt.legend()
        plt.title(self.titlename)
        plt.savefig(self.iname)

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

        # fig = plt.figure(figNum+1)
        # # sig = avgi + 1j * avgq
        # # avgamp0 = np.abs(sig)
        # plt.plot(x_pts, avgq, 'o-', label="q")
        # plt.ylabel("a.u.")
        # plt.xlabel("Wait time (us)")
        # plt.legend()
        # plt.title(self.titlename)
        #
        #
        # plt.savefig(self.iname[:-4] + 'Q_Data.png')
        #
        # if plotDisp:
        #     plt.show(block=True)
        #     plt.pause(0.1)
        # else:
        #     fig.clf(True)
        #     plt.close(fig)
        #
        # fig = plt.figure(figNum+2)
        # # sig = avgi + 1j * avgq
        # # avgamp0 = np.abs(sig)
        # plt.plot(x_pts, np.abs(avgi + 1j * avgq), 'o-', label="Amplitude")
        # plt.ylabel("a.u.")
        # plt.xlabel("Wait time (us)")
        # plt.legend()
        # plt.title(self.titlename)
        #
        #
        # plt.savefig(self.iname[:-4] + 'Amp_Data.png')
        #
        # if plotDisp:
        #     plt.show(block=True)
        #     plt.pause(0.1)
        # else:
        #     fig.clf(True)
        #     plt.close(fig)

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

