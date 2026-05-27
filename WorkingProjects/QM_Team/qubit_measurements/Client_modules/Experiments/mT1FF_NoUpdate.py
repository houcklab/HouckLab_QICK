from qick import *
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
from scipy.optimize import curve_fit

class T1Program(AveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in cfg["ro_chs"]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch = self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch = self.cfg["qubit_ch"])
        self.add_gauss(ch=cfg["qubit_ch"], name="qubit", sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)

        # self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=f_ge,
        #                          phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["pi_gain"],
        #                          waveform="qubit")
        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        if cfg["flattop_length"] != None:
            flattop_length = self.us2cycles(self.cfg["flattop_length"], gen_ch=self.cfg["qubit_ch"])
            self.set_pulse_registers(ch=cfg["qubit_ch"], style='flat_top', freq=f_ge,
                                     phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]), gain=cfg["pi_gain"],
                                     waveform="qubit",
                                     length=flattop_length) #Flat part of flattop does NOT update with gain
            self.pulse_qubit_lenth += flattop_length
        else:
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=f_ge,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["pi_gain"],
                                     waveform="qubit")

        total_trig_length = cfg["trig_buffer_start"] + cfg["trig_buffer_end"] + cfg["sigma"] * 4
        delay_time = self.cfg["delay_time"] + cfg["sigma"] * 4
        if cfg["flattop_length"] != None:
            total_trig_length += cfg["flattop_length"]
            delay_time += cfg["flattop_length"]

        total_trig_length = min(total_trig_length, delay_time + 0.10)
        self.trig_length = self.us2cycles(total_trig_length)


        self.sync_all(self.us2cycles(0.05))

    def body(self):
        self.sync_all(self.us2cycles(20))
        print('1', self._dac_ts, self._adc_ts)
        self.trigger(pins = [0], t = self.us2cycles(0.01 + self.cfg["trig_delay"] - self.cfg["trig_buffer_start"],
                                                    ),
                     width = self.trig_length)
        print('2', self._dac_ts, self._adc_ts)


        self.pulse(ch=self.cfg["qubit_ch"], t = self.us2cycles(0.01))
        print('4', self._dac_ts, self._adc_ts)

        self.sync_all(self.us2cycles(0.1 + self.cfg["delay_time"]))
        print('5', self._dac_ts, self._adc_ts)

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=self.ro_chs,
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(self.cfg["relax_delay"]))

class T1FF_N(ExperimentClass):
    """
    Basic T1
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        self.cfg['reps'] *= self.cfg['rounds']
        self.cfg['rounds'] = 1
        delay_points = np.linspace(self.cfg["t1_start"],
                              self.cfg["t1_end"],
                              self.cfg["t1_NumPoints"])
        #### pull the data from the amp rabi sweep
        # prog = PulseProbeSpectroscopyProgram(self.soccfg, self.cfg)

        results = []
        start = time.time()
        for d in tqdm(delay_points, position=0, disable=True):

            self.cfg["delay_time"] = d
            prog = T1Program(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
        print(f'Time: {time.time() - start}')
        results = np.transpose(results)
        signal = (results[0][0][0] + 1j * results[0][0][1]) * np.exp(1j * (2 * np.pi * self.cfg['cavity_winding_freq'] *
                                                   self.cfg["pulse_freq"] + self.cfg['cavity_winding_offset']))

        avgi = [[signal.real]]
        avgq = [[signal.imag]]

        data = {'config': self.cfg, 'data': {'x_pts': delay_points, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        return data


    def display(self, data=None, plotDisp = False, figNum = 1, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]

        rotation_angle = Amplitude_IQ(avgi, avgq)
        rotated_IQ = (avgi + 1j * avgq) * np.exp(1j * rotation_angle)

        avgi = rotated_IQ.real
        avgq = rotated_IQ.imag

        def _expFit(x, a, T1, c):
            return a * np.exp(-1 * x / T1) + c

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
        plt.plot(x_pts, avgi, 'o', label="i", color = 'orange')
        plt.plot(x_pts, T1_fit, '-', label="fit", color = 'black')
        plt.ylabel("a.u.")
        plt.xlabel("Wait time (us)")
        plt.legend()
        plt.title('Q: ' + str(self.cfg["Qubit_number"]) + "; " + 'S ' + str(self.cfg["trig_buffer_end"]) + '; ' + self.titlename + "  ; T1 = " + str(round(T1_est,1)) + r" $\pm$ " + str(round(T1_err,1)) + "us")
        plt.savefig(self.iname[:-4] + 'I_Data.png')

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

        # a_guess = avgq[0] - avgq[-1]
        # b_guess = avgq[-1]
        # approx_t1_val = a_guess / 2.6 + b_guess
        # index_t1_guess = np.argmin(np.abs(avgq - approx_t1_val))
        # t1_guess = x_pts[index_t1_guess]
        # if avgq[-1] < avgq[0]:
        #     t1_guess *= -1
        # guess = [a_guess, t1_guess, b_guess]
        # pOpt, pCov = curve_fit(_expFit, x_pts, avgq, p0=guess)
        # perr =np.sqrt(np.diag(pCov))
        #
        # T1_fit = _expFit(x_pts, *pOpt)
        #
        # T1_est = np.abs(pOpt[1])
        # T1_err = perr[1]

        fig = plt.figure(figNum+1)
        # sig = avgi + 1j * avgq
        # avgamp0 = np.abs(sig)
        plt.plot(x_pts, avgq, 'o', label="q")
        # plt.plot(x_pts, T1_fit, '-', label="fit", color = 'black')

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
        new_name = self.fname[:-3] + '_Q' + str(self.cfg["Qubit_number"]) + '_S' + str(self.cfg["trig_buffer_end"]) + '.h5'
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