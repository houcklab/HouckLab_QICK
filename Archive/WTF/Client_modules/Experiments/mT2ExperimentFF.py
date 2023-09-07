#### code to perform a T2 Ramsey experiment

from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WTF.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time
from scipy.optimize import curve_fit


class LoopbackProgramT2ExperimentFF(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        cfg["f_res"] = self.cfg["read_pulse_freq"]
        cfg["f_ge"] = self.cfg["qubit_freq"]
        cfg["res_gain"] = self.cfg["read_pulse_gain"]

        #### adjust the qubit gain so it is a pi/2 pulse
        # self.cfg["qubit_gain"] = int(self.cfg["qubit_gain"])

        #### set the start, step, and other parameters
        self.q_rp=self.ch_page(cfg["qubit_ch"])     # get register page for qubit_ch
        self.r_wait = self.us2cycles(0.010)
        self.regwi(self.q_rp, self.r_wait, self.us2cycles(cfg["start"]))

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get gain register for qubit_ch
        self.r_gain2 = self.sreg(cfg["qubit_ch"], "gain2")  # get frequency register for qubit_ch

        self.declare_gen(ch=cfg["res_ch"], nqz=1)  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=2)  # Qubit
        for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"]),
                                 freq=cfg["f_res"], gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])    # conver f_res to dac register value
        qubit_freq = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg["qubit_ch"])  # convert frequency to dac frequency (ensuring it is an available adc frequency)

        ##### define a fast flux pulse
        self.set_pulse_registers(ch=self.cfg["ff_ch"], style="const", freq=0, phase=0,
                                 gain=self.cfg["ff_gain"],
                                 length=self.us2cycles(self.cfg["ff_length"]))

        # add qubit and readout pulses to respective channels
        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"]),
                           length=self.us2cycles(self.cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=self.cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4

        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"]),
                           length=self.us2cycles(self.cfg["sigma"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=self.cfg["qubit_gain"],
                                     waveform="qubit",  length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4 + self.us2cycles(self.cfg["flat_top_length"])

        else:
            print("define pi or flat top pulse")

        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]))

        ##### define fast flux parameters
        self.cfg["ff_length_total"] = self.us2cycles(self.cfg["ff_length"]*10)
        self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4
        self.qubit_wait = ( self.cfg["ff_length_total"] - self.us2cycles(self.cfg["read_length"])
                            - self.us2cycles(0.02) - self.qubit_pulseLength )
        self.res_wait = self.qubit_pulseLength + self.us2cycles(0.01)

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))


    def body(self):

        # ##### run the fast flux pulse 12 times
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
        self.pulse(ch=self.cfg["ff_ch"])  # play pulse
        self.pulse(ch=self.cfg["ff_ch"])  # play pulse

        self.synci(self.qubit_wait) # wait to play other pulses

        self.pulse(ch=self.cfg["qubit_ch"])  #play probe pulse

        self.synci(self.res_wait)  # wait to play other pulses

        self.sync(self.q_rp,self.r_wait)
        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse

        self.synci(self.res_wait)  # wait to play other pulses

        # Play measurement pulse and trigger readout
        self.trigger(adcs=self.ro_chs, pins=[0],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]))  # trigger the adc acquisition
        self.pulse(ch=self.cfg["res_ch"])  # play readout pulse
        # control should wait until the readout is over
        self.waiti(0, self.us2cycles(self.cfg["adc_trig_offset"]) + self.us2cycles(self.cfg["read_length"]))
        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))  # sync all channels

    def update(self):
        self.mathi(self.q_rp, self.r_wait, self.r_wait, '+', self.us2cycles(self.cfg["step"])) ### update wait time


# ====================================================== #

class T2ExperimentFF(ExperimentClass):
    """
    Basic T2 Ramsey experiment with fast flux
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        #### pull the data from the amp rabi sweep
        prog = LoopbackProgramT2ExperimentFF(self.soccfg, self.cfg)

        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)
        mag = np.abs(avgi[0][0] + 1j * avgq[0][0])
        phase = np.arctan2(avgq[0][0], avgi[0][0])

        data = {'config': self.cfg, 'data': {'times': x_pts, 'avgi': avgi, 'avgq': avgq, 'mag': mag, 'phase': phase}}

        ### perform fit for T1 estimate

        #### define T2 function
        def _expCosFit(x, offset, amp, T2, freq, phaseOffset):
            return offset + (amp * np.exp(-1 * x / T2) * np.cos(2*np.pi*freq*x + phaseOffset) )

        offset_geuss = (np.max(mag) + np.min(mag))/2
        amp_geuss = (np.max(mag) - np.min(mag))/2
        T2_geuss = np.max(x_pts)/3
        freq_geuss = np.abs(x_pts[np.argmax(mag)] - x_pts[np.argmin(mag)])*2
        phaseOffset_geuss = np.pi

        geuss = [offset_geuss, amp_geuss, T2_geuss, freq_geuss, phaseOffset_geuss]

        self.pOpt, self.pCov = curve_fit(_expCosFit, x_pts, mag, p0=geuss)

        self.T2_fit = _expCosFit(x_pts, *self.pOpt)

        self.T2_est = self.pOpt[2]

        self.data = data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        times = data['data']['times']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']

        mag = np.abs(avgi[0][0] + 1j * avgq[0][0])

        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)

        plt.plot(times, mag, 'o-', label="magnitude")
        plt.plot(times, self.T2_fit, label='fit')
        # plt.plot(x_pts, avgq[0][0], label="q")
        plt.ylabel("a.u.")
        plt.xlabel("Time (us)")
        plt.legend()
        plt.title("T2 Experiment, T2 = " + str(self.T2_est) + " us")
        # plt.title("T2 Experiment")

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