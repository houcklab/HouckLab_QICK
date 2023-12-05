from qick import *
from q4diamond.Client_modules.socProxy import makeProxy
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from q4diamond.Client_modules.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
from q4diamond.Client_modules.Helpers.rotate_SS_data import *

class T1Program(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        cfg["reps"]=cfg["shots"] // 4

        self.q_rp = self.ch_page(cfg["qubit_ch"])  # get register page for qubit_ch

        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"],
                         mixer_freq=cfg["mixer_freq"],
                         mux_freqs=cfg["pulse_freqs"],
                         mux_gains=cfg["pulse_gains"],
                         ro_ch=cfg["ro_chs"][0])  # Readout
        for iCh, ch in enumerate(cfg["ro_chs"]):  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freqs"][iCh], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", mask=cfg["ro_chs"],  # gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        self.f_qubit01 = self.freq2reg(cfg["qubit_freq01"], gen_ch=cfg["qubit_ch"])
        self.f_qubit12 = self.freq2reg(cfg["qubit_freq12"], gen_ch=cfg["qubit_ch"])

        # self.FFDefinitions()

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)

        # self.res_wait = cfg["sigma"] * 4 + self.us2cycles(0.02 + 0.05)


        self.sync_all(self.us2cycles(0.05))

    def body(self):
        self.sync_all(self.us2cycles(0.05))
        self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=self.f_qubit01, phase=0,
                             gain=self.cfg["qubit_gain01"], waveform="qubit")
        if self.cfg['Excited_PulseT1'] == 2:
            self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=self.f_qubit12, phase=0,
                                 gain=self.cfg["qubit_gain12"], waveform="qubit")
        self.sync_all(self.us2cycles(self.cfg["variable_wait"]))

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"], pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=False,
                     syncdelay=self.us2cycles(10))
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))
    def FFPulses(self, list_of_gains, length_us, t_start=None):
        for i, gain in enumerate(list_of_gains):
            length = self.us2cycles(length_us, gen_ch=self.FFChannels[i])
            self.set_pulse_registers(ch=self.FFChannels[i], style=self.ff_style, freq=self.ff_freq, phase=0,
                                     gain=gain,
                                     length=length)
        if t_start is None:
            self.pulse(ch=self.FF_Channel1)
            self.pulse(ch=self.FF_Channel2)
            self.pulse(ch=self.FF_Channel3)
            self.pulse(ch=self.FF_Channel4)
        else:
            self.pulse(ch=self.FF_Channel1, t = t_start)
            self.pulse(ch=self.FF_Channel2, t = t_start)
            self.pulse(ch=self.FF_Channel3, t = t_start)
            self.pulse(ch=self.FF_Channel4, t = t_start)

    def FFDefinitions(self):
        ### Start fast flux
        for FF_info in self.cfg["FF_list_read"]:
            self.declare_gen(ch=FF_info[0], nqz=self.cfg["ff_nqz"])

        self.ff_freq = self.freq2reg(self.cfg["ff_freq"])
        self.ff_style = self.cfg["ff_pulse_style"]

        ### Finish FF
        self.FF_Channel1, self.FF_Gain1_readout = self.cfg["FF_list_read"][0]
        self.FF_Channel2, self.FF_Gain2_readout = self.cfg["FF_list_read"][1]
        self.FF_Channel3, self.FF_Gain3_readout = self.cfg["FF_list_read"][2]
        self.FF_Channel4, self.FF_Gain4_readout = self.cfg["FF_list_read"][3]

        self.FF_Gain1_step = self.cfg["FF_list_step"][0][1]
        self.FF_Gain2_step = self.cfg["FF_list_step"][1][1]
        self.FF_Gain3_step = self.cfg["FF_list_step"][2][1]
        self.FF_Gain4_step = self.cfg["FF_list_step"][3][1]

        self.FFChannels = np.array([self.FF_Channel1, self.FF_Channel2, self.FF_Channel3, self.FF_Channel4])
        self.FFReadouts = np.array([self.FF_Gain1_readout, self.FF_Gain2_readout, self.FF_Gain3_readout, self.FF_Gain4_readout])
        self.FFExpts = np.array([self.FF_Gain1_step, self.FF_Gain2_step, self.FF_Gain3_step, self.FF_Gain4_step])

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

class T1_TwoPulseMUXSS(ExperimentClass):
    """
    Basic T1
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, threshold = None, angle = None, excited_pulse = 2, progress=False, debug=False):
        tpts = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])
        self.cfg['Excited_PulseT1'] = excited_pulse

        results = []
        rotated_iq_array = []
        for t in tqdm(tpts, position=0, disable=True):
            self.cfg["variable_wait"] = t
            print(t)
            prog = T1Program(self.soccfg, self.cfg)
            shots_i0, shots_q0 = prog.acquire(self.soc,
                                              load_pulses=True)
            rotated_iq = rotate_data((shots_i0, shots_q0), theta=angle)
            rotated_iq_array.append(rotated_iq)
            excited_percentage = count_percentage(rotated_iq, threshold=threshold)
            results.append(excited_percentage)


        results = np.transpose(results)

        self.data= {
            'config': self.cfg,
            'data': {'Exp_values': results, 'RotatedIQ': rotated_iq_array, 'threshold':threshold,
                        'angle': angle, 'wait_times': tpts,
                     }
        }
        return self.data

    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['wait_times']
        expectation_values = data['data']['Exp_values']

        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)
        plt.plot(x_pts, expectation_values, 'o-', label="i", color = 'orange')
        plt.ylabel("a.u.")
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


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

