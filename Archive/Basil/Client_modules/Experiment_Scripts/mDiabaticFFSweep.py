from qick import *
from q3diamond.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from q3diamond.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
from q3diamond.Client_modules.Helpers.rotate_SS_data import *
import time

class DiabaticSweepProgram(AveragerProgram):
    def initialize(self):
        cfg = self.cfg

        res_ch = cfg["res_ch"]
        self.declare_gen(ch=res_ch, nqz=cfg["nqz"], mixer_freq=cfg["mixer_freq"], ro_ch=cfg["ro_chs"][0])
        qubit_ch = cfg["qubit_ch"]
        self.declare_gen(ch=qubit_ch, nqz=cfg["qubit_nqz"])

        for ro_ch in cfg["ro_chs"]:
            # self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
            #                      length=self.us2cycles(self.cfg["state_read_length"]), gen_ch=cfg["res_ch"])
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(self.cfg["read_length"]), gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=res_ch, ro_ch=cfg["ro_chs"][0])
        # convert frequency to dac frequency (ensuring it is an available adc frequency)
        qubit_freq = self.freq2reg(cfg["qubit_freq"],
                                   gen_ch=qubit_ch)

        ### Start fast flux
        for FF_info in cfg["FF_list_readout"]:
            self.declare_gen(ch=FF_info[0], nqz=cfg["ff_nqz"])

        self.ff_freq = self.freq2reg(cfg["ff_freq"], gen_ch=cfg["ff_ch"])
        self.ff_style = self.cfg["ff_pulse_style"]

        ### Finish FF
        self.FF_Channel1, self.FF_Gain1_readout = self.cfg["FF_list_readout"][0]
        self.FF_Channel2, self.FF_Gain2_readout = self.cfg["FF_list_readout"][1]
        self.FF_Channel3, self.FF_Gain3_readout = self.cfg["FF_list_readout"][2]


        self.FFChannels = np.array([self.FF_Channel1, self.FF_Channel2, self.FF_Channel3])


        self.FFQ1Pi = np.array([self.cfg["FF_list_Q1_Pi"][0][1], self.cfg["FF_list_Q1_Pi"][1][1],
                                 self.cfg["FF_list_Q1_Pi"][2][1]])
        self.FFQ2Sw = np.array([self.cfg["FF_list_Q2_Sweep"][0][1], self.cfg["FF_list_Q2_Sweep"][1][1],
                                 self.cfg["FF_list_Q2_Sweep"][2][1]])
        self.FFQ1Sw = np.array([self.cfg["FF_list_Q1_Sweep"][0][1], self.cfg["FF_list_Q1_Sweep"][1][1],
                                 self.cfg["FF_list_Q1_Sweep"][2][1]])
        self.FFReadouts = np.array([self.FF_Gain1_readout, self.FF_Gain2_readout, self.FF_Gain3_readout])

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
        self.FFPulses(-1 * self.FFQ1Pi, self.us2cycles(1) + self.qubit_pulseLength)
        self.sync_all(self.us2cycles(5))  # align channels and wait 50ns
        self.FFPulses(self.FFQ1Pi, self.us2cycles(1) + self.qubit_pulseLength)

        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(1))  # play probe pulse
        self.sync_all()
        self.FFPulses(self.FFQ2Sw, self.us2cycles(0.1)) #all of these play in rapid succession
        self.sync_all()
        self.FFPulses(self.FFQ1Sw, self.us2cycles(0.16))
        self.sync_all()
        self.FFPulses(self.FFReadouts, self.us2cycles(0.5))
        self.sync_all()
        self.FFPulses(self.FFReadouts, self.us2cycles(self.cfg["length"]))


        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(5))

        self.FFPulses(-1 * self.FFQ2Sw, self.us2cycles(0.1)) #all of these play in rapid succession
        self.sync_all()
        self.FFPulses(-1 * self.FFQ1Sw, self.us2cycles(0.16))
        self.sync_all()
        self.FFPulses(-1 * self.FFReadouts, self.us2cycles(0.5 + self.cfg["length"]))

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))


        #
        #
        #
        #
        #
        #
        #
        # put qubit 1 at lowest frequency possible. wait 1 us
        #
        # pi pulse qubit
        #
        # move qubit 2 to position? wait like 500ns to stabilize?
        #
        # sweep qubit 1 to second position
        # move qubit 2 to original position for readout/single shot?
        #
        #
        # keep them there
        #
        # readout qubit 1
        #
        # self.sync_all(200)  # align channels and wait 50ns
        # self.FFPulses([-1 * x for x in self.FFReadouts], self.qubit_pulseLength + self.us2cycles(0.01))
        # self.sync_all(self.us2cycles(0.05))
        #
        # self.FFPulses(self.FFReadouts, self.qubit_pulseLength + self.us2cycles(0.01))
        #
        # self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(0.01))  # play probe pulse
        #
        # self.sync_all()
        # if self.cfg["variable_wait"] > 0.01:
        #     self.FFPulses([-5000, -5000, -1300], 4)
        #
        #     self.FFPulses(self.FFExpts, self.us2cycles(self.cfg["variable_wait"]))
        #
        #     self.sync_all()
        #
        #
        # self.FFPulses([int(x * 2) for x in self.FFReadouts], 3)
        # self.FFPulses(self.FFReadouts, self.us2cycles(self.cfg["length"]))
        #
        #
        #
        # self.measure(pulse_ch=self.cfg["res_ch"],
        #              adcs=[0],
        #              adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
        #              wait=True,
        #              syncdelay=self.us2cycles(0.05))
        #
        # self.FFPulses([-1 * x for x in self.FFReadouts], self.us2cycles(self.cfg["length"]))
        #
        # self.sync_all(self.us2cycles(self.cfg["relax_delay"]))
        #

    def acquire(self, soc, threshold=None, angle=None, load_pulses=True, readouts_per_experiment=1,
                save_experiments=None,
                start_src="internal", progress=False, debug=False):

        super().acquire(soc, load_pulses=load_pulses, progress=progress, debug=debug)

        return self.collect_shots()

    def collect_shots(self):
        shots_i0 = self.di_buf[0].reshape((1, self.cfg["reps"])) / self.us2cycles(
            self.cfg['read_length'], ro_ch=0)
        shots_q0 = self.dq_buf[0].reshape((1, self.cfg["reps"])) / self.us2cycles(
            self.cfg['read_length'], ro_ch=0)

        return shots_i0, shots_q0

    def FFPulses(self, list_of_gains, length, t_offset = 0):
        for i, gain in enumerate(list_of_gains):
            self.set_pulse_registers(ch=self.FFChannels[i], style=self.ff_style, freq=self.ff_freq, phase=0,
                                     gain=gain,
                                     length=length)
        self.pulse(ch=self.FF_Channel1, t = t_offset)
        self.pulse(ch=self.FF_Channel2, t = t_offset)
        self.pulse(ch=self.FF_Channel3, t = t_offset)


class DiabaticSweepGain(ExperimentClass):
    """
    Basic T1
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, threshold = None, angle = None, progress=False, debug=False):

        tpts = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])
        self.cfg["reps"] = self.cfg["shots"]
        print(tpts)
        results = []
        start = time.time()
        for gain in tqdm(tpts, position=0, disable=True):
            print(gain)
            self.cfg["FF_list_Q2_Sweep"][1][1] = gain
            self.cfg["FF_list_Q1_Sweep"][1][1] = gain

            prog = DiabaticSweepProgram(self.soccfg, self.cfg)
            shots_i0, shots_q0 = prog.acquire(self.soc,
                                              load_pulses=True)
            rotated_iq = rotate_data((shots_i0, shots_q0), theta=angle)
            excited_percentage = count_percentage(rotated_iq, threshold=threshold)
            results.append(excited_percentage)

        data = {'config': self.cfg, 'data': {'results': results, 'tpts': tpts, 'thresholds': (threshold, angle)}}
        self.data = data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['tpts']
        percent_excited = data['data']['results']

        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1

        while plt.fignum_exists(num=figNum):  ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)
        plt.plot(x_pts, percent_excited, 'o-', label="i", color='orange')
        plt.ylabel("Excited Population")
        plt.xlabel("Gain")
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


class DiabaticSweep(ExperimentClass):
    """
    Basic T1
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, threshold = None, angle = None, progress=False, debug=False):
        prog = DiabaticSweepProgram(self.soccfg, self.cfg)
        shots_i0, shots_q0 = prog.acquire(self.soc,
                                          load_pulses=True)
        rotated_iq = rotate_data((shots_i0, shots_q0), theta=angle)
        excited_percentage = count_percentage(rotated_iq, threshold=threshold)
        data={'config': self.cfg, 'data': {'iqshots': (shots_i0, shots_q0), 'rotated_iq':rotated_iq,
                                           'thresholds': (threshold, angle), 'excited_amount': excited_percentage}}

        self.data=data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        rotated_iq = data['data']['rotated_iq']
        threshold = data['data']['thresholds'][0]
        excited_percentage = data['data']['excited_amount']

        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1

        fig = plt.figure(figNum)
        plt.scatter(rotated_iq[0], rotated_iq[1], label='g', color='darkorchid', marker='*', alpha=0.5)
        plt.axvline(threshold, 0, 20, color='black', alpha=0.7, ls='--')
        plt.title(self.titlename + f' exc: {excited_percentage * 100:.2f}%')
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

