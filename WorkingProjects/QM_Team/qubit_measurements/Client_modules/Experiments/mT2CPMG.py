from qick import *
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time

from scipy.optimize import curve_fit


class T2EProgram(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.q_rp=self.ch_page(cfg["qubit_ch"])     # get register page for qubit_ch
        self.r_wait = 3
        self.regwi(self.q_rp, self.r_wait, cfg["start"])

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in cfg["ro_chs"]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])
        self.f_ge = f_ge

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)

        trig_length = cfg["trig_buffer_start"] + cfg["trig_buffer_end"] + cfg["sigma"] * 4

        if cfg["flattop_length"] != None:
            trig_length += self.cfg["flattop_length"]
        self.trig_length = self.us2cycles(trig_length)

        self.sync_all(self.us2cycles(0.2))

    def body(self):
        self.sync_all(self.us2cycles(0.05))
        self.trigger(pins=[0], t=self.us2cycles(0.01 + self.cfg["trig_delay"] - self.cfg["trig_buffer_start"]),
                     width=self.trig_length)

        if self.cfg["flattop_length"] != None:
            flattop_length = self.us2cycles(self.cfg["flattop_length"], gen_ch=self.cfg["qubit_ch"])
            self.setup_and_pulse(self.cfg["qubit_ch"], style='flat_top', freq=self.f_ge,
                                 phase=0,
                                 gain=self.cfg["pi2_gain"],waveform="qubit",
                                 length=flattop_length, t = self.us2cycles(0.01))
        else:
            self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=self.f_ge,
                                 phase=0,
                                 gain=self.cfg["pi2_gain"], waveform="qubit", t = self.us2cycles(0.01))
        self.sync_all()

        for i in range(self.cfg['num_pi_pulses']):
            self.sync_all()
            self.sync(self.q_rp, self.r_wait)
            self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"] - self.cfg["trig_buffer_start"]),
                         width=self.trig_length)
            if self.cfg["flattop_length"] != None:
                self.setup_and_pulse(self.cfg["qubit_ch"], style='flat_top', freq=self.f_ge,
                                     phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]),
                                     gain=self.cfg["pi_gain"],
                                     waveform="qubit",
                                     length=flattop_length)
            else:
                self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=self.f_ge,
                                     phase=self.deg2reg(90, gen_ch=self.cfg["qubit_ch"]),
                                     gain=self.cfg["pi_gain"],
                                     waveform="qubit")
            self.sync_all()
            self.sync(self.q_rp, self.r_wait)

        if self.cfg['num_pi_pulses'] == 0:
            self.sync(self.q_rp, self.r_wait)
            self.sync(self.q_rp, self.r_wait)

        self.trigger(pins=[0], t=self.us2cycles(self.cfg["trig_delay"] - self.cfg["trig_buffer_start"]),
                     width=self.trig_length)
        if self.cfg["flattop_length"] != None:
            self.setup_and_pulse(self.cfg["qubit_ch"], style='flat_top', freq=self.f_ge,
                                 phase=0,
                                 gain=self.cfg["pi2_gain"],waveform="qubit",
                                 length=flattop_length)
        else:
            self.setup_and_pulse(ch=self.cfg["qubit_ch"], style="arb", freq=self.f_ge,
                                 phase=0,
                                 gain=self.cfg["pi2_gain"], waveform="qubit")
        self.sync_all(self.us2cycles(0.05))

        # trigger measurement, play measurement pulse, wait for qubit to relax
        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.ro_chs,
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        if self.cfg["num_pi_pulses"] == 0:
            self.mathi(self.q_rp, self.r_wait, self.r_wait, '+', self.us2cycles(self.cfg["step"] / 2))  # update the time between two π/2 pulses
        else:
            self.mathi(self.q_rp, self.r_wait, self.r_wait, '+', self.us2cycles(self.cfg["step"] /
                                                                                (self.cfg["num_pi_pulses"]) / 2))
class T2ECPMG(ExperimentClass):
    """
    Basic T2R
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False):

        #### pull the data from the amp rabi sweep
        # prog = PulseProbeSpectroscopyProgram(self.soccfg, self.cfg)
        prog = T2EProgram(self.soccfg, self.cfg)

        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False)
        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq, 'qfreq': self.cfg["f_ge"],
                                             'n_pulses': self.cfg["num_pi_pulses"]}}

        if self.cfg["num_pi_pulses"] == 0:
            data['data']['step']= self.cfg["step"]
            data['data']['taus'] = x_pts
        else:
            data['data']['taus']= self.cfg["step"] / self.cfg["num_pi_pulses"]
            data['data']['step']= x_pts / self.cfg["num_pi_pulses"]

        if 'rotation_angle' in self.cfg:
            data['rotation_angle'] = self.cfg['rotation_angle']
        if 'min_max' in self.cfg:
            data['min_max'] = self.cfg['min_max']
        self.data = data
        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]

        if 'rotation_angle' not in self.cfg:
            rotation_angle = Amplitude_IQ(avgi, avgq)
        else:
            rotation_angle = self.cfg['rotation_angle']
        rotated_IQ = (avgi + 1j * avgq) * np.exp(1j * rotation_angle)

        avgi = rotated_IQ.real
        avgq = rotated_IQ.imag

        def _expFit(x, a, T1, c):
            return a * np.exp(-1 * x / T1) + c

        if self.cfg["num_pi_pulses"] != 0:
            a_guess = avgi[0] - avgi[-1]
            b_guess = avgi[-1]
            approx_t1_val = a_guess / 2.6 + b_guess
            index_t1_guess = np.argmin(np.abs(avgi - approx_t1_val))
            t1_guess = x_pts[index_t1_guess]
            guess = [a_guess, t1_guess, b_guess]
            pOpt, pCov = curve_fit(_expFit, x_pts, avgi, p0=guess)
            perr =np.sqrt(np.diag(pCov))

            T1_fit = _expFit(x_pts, *pOpt)

            T1_est = np.abs(pOpt[1])
            T1_err = perr[1]


        while plt.fignum_exists(num=figNum): ###account for if figure with number already exists
            figNum += 1
        fig = plt.figure(figNum)
        plt.plot(x_pts, avgi, 'o-', label="i", color = 'orange')
        plt.ylabel("a.u.")
        plt.xlabel("Wait time (us)")
        plt.legend()
        if self.cfg["num_pi_pulses"] != 0:
            plt.plot(x_pts, T1_fit, '-', label="fit", color='black')
            plt.title('Num Pulses: ' + str(self.cfg["num_pi_pulses"]) + " ; " + self.titlename + "  ; T2E = " + str(
                round(T1_est, 1)) + r" $\pm$ " + str(round(T1_err, 1)) + "us")
        else:
            plt.title('Num Pulses: ' + str(self.cfg["num_pi_pulses"]) + " ; " + self.titlename)

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
        plt.title('Num Pulses: ' + str(self.cfg["num_pi_pulses"]) + " ; " + self.titlename)



        plt.savefig(self.iname[:-4] + 'Q_Data.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        new_name = self.fname[:-3] + '_n' + str(self.cfg["num_pi_pulses"]) + '.h5'
        self.fname = new_name
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])

def Amplitude_IQ(I, Q, phase_num_points = 200):
    '''
    IQ data is inputted and it will multiply by a phase such that all of the
    information is in I
    :param I:
    :param Q:
    :param phase_num_points:
    :return:
    '''
    complex = I + 1j * Q
    phase_values = np.linspace(0, np.pi, phase_num_points)
    multiplied_phase = [complex * np.exp(1j * phase) for phase in phase_values]
    Q_range = np.array([np.max(IQPhase.imag) - np.min(IQPhase.imag) for IQPhase in multiplied_phase])
    phase_index = np.argmin(Q_range)
    return(phase_values[phase_index])