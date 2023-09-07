from qick import *
import matplotlib.pyplot as plt
import numpy as np
from q3diamond.Client_modules.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time
import datetime
from q3diamond.Client_modules.PythonDrivers.YOKOGS200 import *
from scipy.signal import savgol_filter
import time

class T2Program(AveragerProgram):
    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=1)  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=2)  # Qubit
        for ch in cfg["ro_chs"]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=cfg["readout_length"],
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"],
                              ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        ### Start fast flux
        for FF_info in cfg["FF_list"]:
            FF_Channel, FF_gain = FF_info
            self.declare_gen(ch=FF_Channel, nqz=cfg["ff_nqz"])
            ff_freq = self.freq2reg(cfg["ff_freq"], gen_ch=FF_Channel)

            ff_style = self.cfg["ff_pulse_style"]

            if ff_style == 'const':
                self.set_pulse_registers(ch=FF_Channel, style=ff_style, freq=ff_freq, phase=0, gain=FF_gain,
                                         length=cfg["sigma"] * 4 + self.us2cycles(0.1))
            else:
                print('No FF pulse style matches: currently only supports const')
        self.ff_freq = ff_freq
        self.ff_style = ff_style
        self.FF_Channel1, self.FF_Gain1 = self.cfg["FF_list"][0]
        self.FF_Channel2, self.FF_Gain2 = self.cfg["FF_list"][1]
        ### Finish FF

        self.FF_Gain1_pulse = self.cfg["FF_list_pulse"][0][1]
        self.FF_Gain2_pulse = self.cfg["FF_list_pulse"][1][1]

        # add qubit and readout pulses to respective channels
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma=cfg["sigma"], length=cfg["sigma"] * 4)
        self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=f_ge, phase=0, gain=cfg["pi2_gain"],
                                 waveform="qubit")
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=cfg["length"])

        self.sync_all(self.us2cycles(0.2))

    def body(self):
        self.set_pulse_registers(ch=self.FF_Channel1, style=self.ff_style, freq=self.ff_freq, phase=0, gain=self.FF_Gain1,
                                 length=self.cfg["sigma"] * 4 + self.us2cycles(0.1))
        self.set_pulse_registers(ch=self.FF_Channel2, style=self.ff_style, freq=self.ff_freq, phase=0, gain=self.FF_Gain2,
                                 length=self.cfg["sigma"] * 4 + self.us2cycles(0.1))
        self.pulse(ch=self.FF_Channel1)
        self.pulse(ch=self.FF_Channel2)
        self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(0.1))  # play probe pulse
        self.sync_all()

        self.set_pulse_registers(ch=self.FF_Channel1, style=self.ff_style, freq=self.ff_freq, phase=0, gain=self.FF_Gain1_pulse,
                                 length=self.us2cycles(self.cfg["variable_wait"]))
        self.set_pulse_registers(ch=self.FF_Channel2, style=self.ff_style, freq=self.ff_freq, phase=0, gain=self.FF_Gain2_pulse,
                                 length=self.us2cycles(self.cfg["variable_wait"]))
        self.pulse(ch=self.FF_Channel1)
        self.pulse(ch=self.FF_Channel2)

        self.sync_all()

        self.set_pulse_registers(ch=self.FF_Channel1, style=self.ff_style, freq=self.ff_freq, phase=0, gain=self.FF_Gain1,
                                 length=self.us2cycles(self.cfg["Wait_PiPulse"]) + self.cfg["sigma"] * 4 + self.cfg["length"])
        self.set_pulse_registers(ch=self.FF_Channel2, style=self.ff_style, freq=self.ff_freq, phase=0, gain=self.FF_Gain2,
                                 length=self.us2cycles(self.cfg["Wait_PiPulse"]) + self.cfg["sigma"] * 4 + self.cfg["length"])
        self.pulse(ch=self.FF_Channel1)
        self.pulse(ch=self.FF_Channel2)

        self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(self.cfg["Wait_PiPulse"]))  # play probe pulse
        self.synci(self.us2cycles(self.cfg["Wait_PiPulse"]) + self.cfg["sigma"] * 4)
        # self.sync_all(self.us2cycles(0.05))

        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.ro_chs,
                     adc_trig_offset=self.cfg["adc_trig_offset"],
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

class T2R_FFCalibration(ExperimentClass):
    """
    Basic T2R
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        #### pull the data from the amp rabi sweep
        # prog = PulseProbeSpectroscopyProgram(self.soccfg, self.cfg)
        tpts = self.cfg["start"] + self.cfg["step"] * np.arange(self.cfg["expts"])
        print(tpts)
        results = []
        start = time.time()
        for t in tqdm(tpts, position=0, disable=True):
            print(t)
            self.cfg["variable_wait"] = t
            prog = T2Program(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
            # time.sleep(5)
        print(f'Time: {time.time() - start}')
        results = np.transpose(results)

        data = {'config': self.cfg, 'data': {'results': results, 'tpts': tpts}}
        self.data = data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

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

    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
