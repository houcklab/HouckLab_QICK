#### code to perform a T1 experiment

from qick import *
import matplotlib.pyplot as plt
import numpy as np
from Protomon.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time
from scipy.optimize import curve_fit


class LoopbackProgramT1Experiment(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        self.cfg["reps"] = self.cfg["T1_reps"]
        self.cfg["rounds"] = self.cfg["T1_rounds"]
        self.cfg["start"] = self.cfg["T1_start"]
        self.cfg["step"] = self.cfg["T1_step"]
        self.cfg["expts"] = self.cfg["T1_expts"]

        #### set the start, step, and other parameters
        self.q_rp=self.ch_page(cfg["qubit_ch"])     # get register page for qubit_ch
        self.r_wait = self.us2cycles(0.010)
        self.regwi(self.q_rp, self.r_wait, cfg["start"])

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ro_ch in cfg["ro_chs"]:
            self.declare_readout(ch=ro_ch, freq=cfg["read_pulse_freq"],
                                 length=self.us2cycles(self.cfg["read_length"]), gen_ch=cfg["res_ch"])

        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])    # conver f_res to dac register value
        qubit_freq = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg["qubit_ch"])  # convert frequency to dac frequency (ensuring it is an available adc frequency)

        # add qubit and readout pulses to respective channels
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                       sigma=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                       length=self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4)
        self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                 phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["pigain"],
                                 waveform="qubit")
        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=read_freq, phase=0,
                                 gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"],gen_ch=cfg["res_ch"]))

        # Sara changed the set pulse registers to have the right unit conversion for us2cycles with gen_ch included

        self.sync_all(self.us2cycles(1)) # Sara changed 500 to 1 here - 500 as in Xanthe's code


    def body(self):

        self.pulse(ch=self.cfg["qubit_ch"])  #play probe pulse
        self.sync_all()
        self.sync(self.q_rp,self.r_wait)

        #trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
             adcs=self.cfg["ro_chs"],
             adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
             wait=True,
             syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_wait, self.r_wait, '+', self.us2cycles(self.cfg["step"])) ### update wait time


# ====================================================== #

class T1Experiment(ExperimentClass):
    """
    Basic T1 experiment
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        #### pull the data from the amp rabi sweep
        prog = LoopbackProgramT1Experiment(self.soccfg, self.cfg)
        print(self.cfg)
        start = time.time()
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)
        print(f'Time: {time.time() - start}')

        ## Sara: Instead of fitting the magnitude or phase, fit whichever has higher contrast, I or Q (this drifts)
        Iavg_array = avgi[0][0]
        Qavg_array = avgq[0][0]
        Icontrast = np.max(abs(Iavg_array)) - np.min(abs(Iavg_array))
        Qcontrast = np.max(abs(Qavg_array)) - np.min(abs(Qavg_array))
        if Qcontrast > Icontrast:
            fit_array = Qavg_array
            # print("Qcontrast is larger")
        if Icontrast >= Qcontrast:
            fit_array = Iavg_array
            # print("Icontrast is larger")

        data = {'config': self.cfg, 'data': {'times': x_pts, 'avgi': avgi, 'avgq': avgq, 'fit_array': fit_array}}

        #### perform fit for T1 estimate

        #### define T1 function
        def _expFit(x, a, T1, c):
            return a * np.exp(-1 * x / T1) + c

        a_geuss = (np.max(fit_array)-np.min(fit_array))*-1
        b_geuss = np.min(fit_array)
        T1_geuss = np.max(x_pts)/3
        geuss = [a_geuss, T1_geuss, b_geuss]
        self.pOpt, self.pCov = curve_fit(_expFit, x_pts, fit_array, p0=geuss)

        self.T1_fit = _expFit(x_pts, *self.pOpt)

        self.T1_est = self.pOpt[1]
        self.T1_err = np.sqrt(self.pCov[1][1])

        self.data = data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        times = data['data']['times']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]

        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)

        # plt.plot(times, fit_array, 'o-', label="fit array")
        plt.plot(times, self.T1_fit, label='fit')
        plt.plot(times, avgi, 'o-', label="I")
        plt.plot(times, avgq, 'o-', label="Q")
        plt.ylabel("a.u.")
        plt.xlabel("Time (us)")
        plt.legend()
        plt.title("T1 Experiment, T1 = " + str(self.T1_est) + " us" + "T1 Error =" + str(self.T1_err) + "us")

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