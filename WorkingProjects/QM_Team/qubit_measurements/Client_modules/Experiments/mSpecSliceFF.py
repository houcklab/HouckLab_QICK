from qick import *
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time


class QubitSpecSliceFFProg(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.declare_gen(
            ch=cfg["res_ch"],
            nqz=cfg["nqz"],
            mixer_freq=cfg["mixer_freq"],
            ro_ch=cfg["ro_chs"][0],) # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")  # get frequency register for qubit_ch

        ### Start fast flux
        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=0)  # conver f_res to dac register value

        self.f_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])  # get start/step frequencies
        self.f_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])

        # add qubit and readout pulses to respective channels
        if cfg['Gauss']:
            self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
            self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=self.f_start,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")
            self.qubit_length_us = cfg["sigma"] * 4
        else:
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=self.f_start, phase=0, gain=cfg["qubit_gain"],
                                     length=self.us2cycles(cfg["qubit_length"]))
            self.qubit_length_us = cfg["qubit_length"]
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        print("\n--- Initializing QubitSpec ---")



    def body(self):
        self.sync_all()
        self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(1))  # play probe pulse
        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.sync_all(self.us2cycles(0.5))
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0, 1],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)  # update frequency list index
# ====================================================== #

class QubitSpecSliceFF(ExperimentClass):
    """
    Basic spec experiement that takes a single slice of data
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):


        prog = QubitSpecSliceFFProg(self.soccfg, self.cfg)
        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False)# , debug=False)
        # Convert avgi and avgq to NumPy arrays
        avgi = np.asarray(avgi)
        avgq = np.asarray(avgq)

        # Compute the complex signal
        signal = (avgi + 1j * avgq) * np.exp(
            1j * (2 * np.pi * self.cfg['cavity_winding_freq'] *
                  self.cfg["pulse_freq"] + self.cfg['cavity_winding_offset'])
        )

        # Separate back into real and imaginary parts
        avgi = signal.real
        avgq = signal.imag

        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']

        #### find the frequency corresponding to the qubit dip
        sig = avgi + 1j * avgq
        avgamp0 = np.abs(sig)
        peak_loc = np.argmax(avgamp0)
        self.qubitFreq = x_pts[peak_loc]

        return data

    def display(self, data=None, plotDisp=False, figNum=1, min_sep=0.01, **kwargs):
        if data is None:
            data = self.data

        x_pts = np.array(data['data']['x_pts'])
        avgi = np.array(data['data']['avgi'][0][0])
        avgq = np.array(data['data']['avgq'][0][0])

        # complex signal and amplitude^2
        sig = avgi + 1j * avgq
        avgamp0 = np.abs(sig) ** 2

        # -----------------------------
        # Find the two highest amplitude peaks
        # with at least 0.1 MHz separation
        # -----------------------------
        min_sep_mhz = min_sep

        # candidate local maxima
        candidate_inds = []
        n = len(avgamp0)

        if n == 1:
            candidate_inds = [0]
        else:
            # include endpoints if they are peaks
            if avgamp0[0] > avgamp0[1]:
                candidate_inds.append(0)

            for i in range(1, n - 1):
                if avgamp0[i] > avgamp0[i - 1] and avgamp0[i] >= avgamp0[i + 1]:
                    candidate_inds.append(i)

            if avgamp0[-1] > avgamp0[-2]:
                candidate_inds.append(n - 1)

        # fallback: if no strict local maxima found, use all points
        if len(candidate_inds) == 0:
            candidate_inds = list(range(n))

        # sort candidates by descending amplitude
        candidate_inds = sorted(candidate_inds, key=lambda i: avgamp0[i], reverse=True)

        selected_peaks = []
        for idx in candidate_inds:
            if len(selected_peaks) == 0:
                selected_peaks.append(idx)
            else:
                far_enough = all(abs(x_pts[idx] - x_pts[j]) >= min_sep_mhz for j in selected_peaks)
                if far_enough:
                    selected_peaks.append(idx)

            if len(selected_peaks) == 2:
                break

        # print peak info
        print("I Max", x_pts[np.argmax(avgi)])
        print("Q Max", x_pts[np.argmax(avgq)])
        print("Max Amplitude ^2", x_pts[np.argmax(avgamp0)], "Amplitude ^2", np.max(avgamp0))

        if len(selected_peaks) >= 1:
            i0 = selected_peaks[0]
            print(f"Peak 1: freq = {x_pts[i0]:.6f} MHz, amplitude^2 = {avgamp0[i0]:.6f}")

        if len(selected_peaks) >= 2:
            i1 = selected_peaks[1]
            print(f"Peak 2: freq = {x_pts[i1]:.6f} MHz, amplitude^2 = {avgamp0[i1]:.6f}")
            print(f"Peak separation: {abs(x_pts[i1] - x_pts[i0]):.6f} MHz")
        else:
            print("Could not find a second peak at least 0.1 MHz away from the first.")

        # -----------------------------
        # Plot I and Q
        # -----------------------------
        plt.figure(figNum)
        plt.plot(x_pts, avgi, '.-', color='Orange', label="I")
        plt.plot(x_pts, avgq, '.-', color='Blue', label="Q")

        # mark selected peaks on the amplitude trace if desired
        for k, idx in enumerate(selected_peaks):
            plt.axvline(x_pts[idx], linestyle='--', label=f"Peak {k + 1}: {x_pts[idx]:.6f} MHz")

        plt.ylabel("a.u.")
        plt.xlabel("Qubit Frequency (GHz)")
        plt.title(self.titlename)
        plt.legend()
        plt.savefig(self.iname[:-4] + '_IQ.png')

        if plotDisp:
            plt.show()

            plt.figure(figNum + 1)
            plt.plot(x_pts, avgamp0, '.-', color='Purple', label="|I+iQ|^2")

            for k, idx in enumerate(selected_peaks):
                plt.axvline(x_pts[idx], linestyle='--', label=f"Peak {k + 1}: {x_pts[idx]:.6f} MHz")
                plt.plot(x_pts[idx], avgamp0[idx], 'o')

            plt.ylabel("a.u.")
            plt.xlabel("Qubit Frequency (GHz)")
            plt.title(self.titlename + " Amplitude^2")
            plt.legend()
            plt.show()
            plt.pause(0.1)

        plt.close(figNum)
        if plotDisp:
            plt.close(figNum + 1)


    def get_amplitude_slice(self, data=None):
        if data is None:
            data = self.data
        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]
        sig = avgi + 1j * avgq
        avgamp0 = np.abs(sig)
        return x_pts, avgamp0, avgi, avgq


    def save_data(self, data=None):
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


