#### code to perform a T2 Ramsey experiment

from qick import *
import matplotlib.pyplot as plt
import numpy as np
from WorkingProjects.Tantalum_fluxonium_marvin.Client_modules.CoreLib.Experiment import ExperimentClass
from tqdm.notebook import tqdm
import time
from scipy.optimize import curve_fit


class LoopbackProgramT2Experiment(RAveragerProgram):
    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        cfg["f_res"] = self.cfg["read_pulse_freq"]
        cfg["f_ge"] = self.cfg["qubit_freq"]
        cfg["res_gain"] = self.cfg["read_pulse_gain"]

        # Create a linspace of the different wait time
        self.wait_arr = np.linspace(self.cfg['start'], self.cfg['start'] + (self.cfg['expts']-1)*self.cfg['step'], self.cfg['expts'])

        for i in range(self.wait_arr.size):
            print(self.us2cycles(self.wait_arr[i]))

        self.q_rp = self.ch_page(cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_wait = self.us2cycles(0.010)
        self.r_phase2 = 4
        self.r_phase = self.sreg(cfg["qubit_ch"], "phase")
        self.regwi(self.q_rp, self.r_wait, self.us2cycles(cfg["start"]))
        self.regwi(self.q_rp, self.r_phase2, 0)

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in cfg["ro_chs"]:
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["read_length"], ro_ch = self.cfg["res_ch"]),
                                 freq=cfg["f_res"], gen_ch=cfg["res_ch"])

        f_res = self.freq2reg(cfg["f_res"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        qubit_freq = f_ge

        ### Declaration of Pulses
        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["pi2_qubit_gain"],
                                     waveform="qubit")
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"]) * 4

        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]),
                           length=self.us2cycles(self.cfg["sigma"],gen_ch=cfg["qubit_ch"]) * 4)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style=cfg["qubit_pulse_style"], freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["pi2_qubit_gain"],
                                     waveform="qubit",  length=self.us2cycles(self.cfg["flat_top_length"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4 + self.us2cycles(
                self.cfg["flat_top_length"], gen_ch=cfg["qubit_ch"])
        elif cfg["qubit_pulse_style"] == "const":
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="const", freq=qubit_freq,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["pi2_qubit_gain"],
                                     length=self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"]))
            self.qubit_pulseLength = self.us2cycles(self.cfg["qubit_length"], gen_ch=cfg["qubit_ch"])
        else:
            print("define pi or flat top pulse")

        self.set_pulse_registers(ch=cfg["res_ch"], style=self.cfg["read_pulse_style"], freq=f_res, phase=0,
                                 gain=cfg["read_pulse_gain"],
                                 length=self.us2cycles(self.cfg["read_length"]))

        # Calculate length of trigger pulse
        self.cfg["trig_len"] = self.us2cycles(self.cfg["trig_buffer_start"] + self.cfg["trig_buffer_end"],
                                              gen_ch=cfg["qubit_ch"]) + self.qubit_pulseLength  ####

        self.sync_all(self.us2cycles(10))

    def body(self):
        self.regwi(self.q_rp, self.r_phase, 0)
        self.sync_all(self.us2cycles(0.05))
        if self.cfg["use_switch"]:
            self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                         width=self.cfg["trig_len"])  # trigger for switch
        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.mathi(self.q_rp, self.r_phase, self.r_phase2, "+", 0)
        self.sync_all()
        self.sync(self.q_rp, self.r_wait)

        if self.cfg["use_switch"]:
            self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"]),
                         width=self.cfg["trig_len"])  # trigger for switch
        self.pulse(ch=self.cfg["qubit_ch"])  # play probe pulse
        self.sync_all(self.us2cycles(0.05))

        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.cfg["ro_chs"],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_wait, self.r_wait, '+', self.us2cycles(self.cfg["step"]))  # update the time between two π/2 pulses
        # self.mathi(self.q_rp, self.r_phase2, self.r_phase2, '+', self.cfg["phase_step"])  # advance the phase of t
# ====================================================== #

class T2Experiment(ExperimentClass):
    """
    Basic T2 Ramsey experiment
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):

        start_time = time.time()

        #### pull the data from the amp rabi sweep
        prog = LoopbackProgramT2Experiment(self.soccfg, self.cfg)

        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False, debug=False)
        mag = np.abs(avgi[0][0] + 1j * avgq[0][0])
        phase = np.arctan2(avgq[0][0], avgi[0][0])

        data = {'config': self.cfg, 'data': {'times': x_pts, 'avgi': avgi, 'avgq': avgq, 'mag': mag, 'phase': phase, 'volt':self.cfg["yokoVoltage"]}}

        ## perform fit for T2 estimate
        try:
            # mag =  avgq[0][0]
            mag = mag

            ### define T2 function
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
            self.freq_est = self.pOpt[3]

            print('T2 estimate: ' + str(self.T2_est))
        except:
            print('fit failed')


        self.data = data
        print("--- %s seconds ---" % (time.time() - start_time))

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        times = data['data']['times']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']

        mag = np.abs(avgi[0][0] + 1j * avgq[0][0])
        phase = np.angle(avgi[0][0] + 1j * avgq[0][0], deg = True)

        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(4, 1, figsize=(12, 12), num=figNum)

        ax0 = axs[0].plot(times, phase, 'o-', label="phase")
        axs[0].set_ylabel("degree.")
        axs[0].set_xlabel("Time (us)")
        axs[0].legend()

        ax1 = axs[1].plot(times, mag, 'o-', label="magnitude")
        axs[1].set_ylabel("a.u.")
        axs[1].set_xlabel("Time (us)")
        axs[1].legend()

        try:
            axs[1].plot(times, self.T2_fit, '-', label="T2R fit")
        except:
            pass

        ax2 = axs[2].plot(times, avgi[0][0], 'o-', label="I - Data")
        axs[2].set_ylabel("a.u.")
        axs[2].set_xlabel("Time (us)")
        axs[2].legend()

        ax3 = axs[3].plot(times, avgq[0][0], 'o-', label="Q - Data")

        # try:
        #     axs[3].plot(times, self.T2_fit, '-', label="T2R fit")
        # except:
        #     pass

        axs[3].set_ylabel("a.u.")
        axs[3].set_xlabel("Time (us)")
        axs[3].legend()

        try:
            fig.suptitle('T2 Experiment, T2R estimate: ' + str(self.T2_est) + ' us')
        except:
            fig.suptitle('T2 Experiment | Voltage = ' + str(self.cfg["yokoVoltage"]))

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