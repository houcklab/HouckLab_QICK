from qick import *
from qick import helpers
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import detrend
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time

class LoopbackProgramTrans(AveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]),
                                 freq=cfg["read_pulse_freq"], gen_ch=cfg["res_ch"])

        freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])

        self.set_pulse_registers(ch=cfg["res_ch"], style=cfg["read_pulse_style"], freq=freq, phase=0, gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]))
        self.synci(200)  # give processor some time to configure pulses

    def body(self):
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"],ro_ch=self.cfg["ro_chs"][0]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

# ====================================================== #

class Transmission_Enhance(ExperimentClass):
    """
    Transmission Experiment basic
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        expt_cfg = {
                "center": self.cfg["read_pulse_freq"],
                "span": self.cfg["TransSpan"],
                "expts": self.cfg["TransNumPoints"]
        }
        expt_cfg["step"] = 2 * expt_cfg["span"] / (expt_cfg["expts"]-1)
        expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
        fpts = expt_cfg["start"] + expt_cfg["step"] * np.arange(expt_cfg["expts"])
        results = []
        start = time.time()
        for f in tqdm(fpts, position=0, disable=True):
            self.cfg["read_pulse_freq"] = f
            prog = LoopbackProgramTrans(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
        if debug:
            print(f'Time: {time.time() - start}')
        results = np.transpose(results)

        data={'config': self.cfg, 'data': {'results': results, 'fpts':fpts}}
        self.data=data

        #### find the frequency corresponding to the peak
        sig = data['data']['results'][0][0][0] + 1j * data['data']['results'][0][0][1]
        avgamp0 = np.abs(sig)
        peak_loc = np.argmin(avgamp0)
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
        plt.plot(x_pts, data['data']['results'][0][0][0],label="I")
        plt.plot(x_pts, data['data']['results'][0][0][1],label="Q")
        plt.plot(x_pts, avgamp0, label="Magnitude")
        plt.ylabel("a.u.")
        plt.xlabel("Cavity Frequency (GHz)")
        plt.title("Averages = " + str(self.cfg["reps"]))
        plt.legend()
        plt.savefig(self.iname)

        if plotDisp:
            plt.show()

        else:
            fig.clf(True)
            plt.close(fig)

    def findOptimalFrequency(self, data = None, window_size = 0.3, debug = False, plotDisp = False):
        """
        Finds the optimal frequency to measure the qubit from the cavity transmission
        :param data: data to be used for calculating the optimal frequency
        :param window_size: (in GHz) this is the window over which the transmission is averaged over
        :param debug: (bool) if True it will create plots of the calculated values
        """

        if data is None:
            data = self.data

        # Get the signal from the data
        sig = data['data']['results'][0][0][0] + 1j * data['data']['results'][0][0][1]

        # Get the phase and frequency
        phase = np.angle(sig)
        freq = (data['data']['fpts'] + self.cfg["cavity_LO"]/1e6)

        # Unwrap the phase
        phase_unrwap = np.unwrap(phase)

        # Using scipy detrend, flatten the phase
        phase_detrend = detrend(phase_unrwap)

        # Calculate the window size
        freq_step = freq[1]-freq[0]
        window = int(window_size/freq_step)

        # Apply a moving average on phase
        phase_smooth = np.convolve(phase_detrend, np.ones(window) / window, mode='same')

        # Calculate the gradient of the smoothened phase
        phase_derivate = np.gradient(phase_smooth, freq)

        # Find the index at which phase derivative is minimum
        if self.cfg['meas_config'] == 'Transmission': #added for measuring WTF; pick max frequency
            index = np.argmax(np.abs(sig))
        else:
            index = np.argmin(phase_derivate)

        # Get the optimal frequency
        opt_freq = freq[index]

        if debug:
            # Create plots of the phase_smooth and phase_derivate
            fig, axs = plt.subplots(2, 1, sharex = True)
            axs[0].plot(freq, phase_smooth, label = "Smoothened Phase")
            axs[0].scatter(freq[index], phase_smooth[index], s = 40, label = "Optimal Point")
            axs[0].set_xlabel("Frequency (in GHz)")
            axs[0].set_ylabel("Phase (in rad)")
            axs[0].legend()
            axs[0].grid()

            axs[1].plot(freq, phase_derivate, label = "Derivated Phase")
            axs[1].scatter(freq[index], phase_derivate[index], s = 40, label = "Optimal Point")
            axs[1].set_xlabel("Frequency (in GHz)")
            axs[1].set_ylabel("Derivated Phase (in rad/GHz)")
            axs[1].legend()
            axs[1].grid()

            # Save the plot
            plt.savefig(self.path_wDate + "_enhance_calc.png")

            if plotDisp:
                plt.show()

            else:
                plt.close()

        return opt_freq

    def save_data(self, data=None):
        # print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


