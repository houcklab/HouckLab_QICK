from qick import *
import matplotlib.pyplot as plt
import numpy as np
from qick.helpers import gauss
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass
import datetime
from tqdm.notebook import tqdm
import time
from scipy.optimize import curve_fit

def cos_func(x, y0, A, P, phi):
    return y0 + A * np.cos(2 * np.pi * x / P + phi)


def fit_rabi_cosine(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    # basic guesses
    y0_guess = np.mean(y)
    A_guess = 0.5 * (np.max(y) - np.min(y))

    # estimate period from sweep span: assume at least ~half an oscillation is visible
    x_span = np.max(x) - np.min(x)
    P_guess = max(x_span, 1.0)

    # phase guess from first point
    phi_guess = 0.0

    p0 = [y0_guess, A_guess, P_guess, phi_guess]

    bounds = (
        [-np.inf, -np.inf, 1e-9, -4 * np.pi],
        [ np.inf,  np.inf, np.inf,  4 * np.pi]
    )

    popt, pcov = curve_fit(cos_func, x, y, p0=p0, bounds=bounds, maxfev=50000)
    perr = np.sqrt(np.diag(pcov))

    yfit = cos_func(x, *popt)

    y0_fit, A_fit, P_fit, phi_fit = popt
    dy0_fit, dA_fit, dP_fit, dphi_fit = perr

    pi_gain = P_fit / 2.0

    return {
        "popt": popt,
        "perr": perr,
        "yfit": yfit,
        "y0": y0_fit,
        "A": A_fit,
        "P": P_fit,
        "phi": phi_fit,
        "dy0": dy0_fit,
        "dA": dA_fit,
        "dP": dP_fit,
        "dphi": dphi_fit,
        "pi_gain": pi_gain,
    }


class AmplitudeRabiFFProg(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.q_rp = self.ch_page(self.cfg["qubit_ch"])  # get register page for qubit_ch
        self.r_gain = self.sreg(cfg["qubit_ch"], "gain")  # get gain register for qubit_ch

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])

        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])
        print(self.pulse_sigma, self.pulse_qubit_lenth)

        if cfg["flattop_length"] != None:
            print('yes!')
            flattop_length = self.us2cycles(self.cfg["flattop_length"], gen_ch=self.cfg["qubit_ch"])
            print(flattop_length)
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma=self.pulse_sigma,
                           length=self.pulse_qubit_lenth)
            self.set_pulse_registers(ch=cfg["qubit_ch"], style='flat_top', freq=f_ge,
                                     phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
                                     waveform="qubit",
                                     length=flattop_length) #Flat part of flattop does NOT update with gain
            # self.set_pulse_registers(ch=cfg["qubit_ch"], style='const', freq=f_ge,
            #                          phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
            #                          length=flattop_length)
            self.pulse_qubit_lenth += flattop_length
        else:
            self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                           sigma= self.pulse_sigma, length= self.pulse_qubit_lenth)

            self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=f_ge,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["start"],
                                     waveform="qubit")

        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        trig_length = cfg["trig_buffer_start"] + cfg["trig_buffer_end"] + cfg["sigma"] * 4

        if cfg["flattop_length"] != None:
            trig_length += self.cfg["flattop_length"]
        self.trig_length = self.us2cycles(trig_length)

        self.sync_all(self.us2cycles(0.05))

    def body(self):
        self.sync_all()
        # self.pulse(ch=self.cfg['ff_ch'])
        self.trigger(pins = [0], t = self.us2cycles(1 + self.cfg["trig_delay"] -
                                                    self.cfg["trig_buffer_start"]), width = self.trig_length)

        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(1))  # play probe pulse
        self.sync_all(self.us2cycles(0.05))

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0, 1],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))

    def update(self):
        self.mathi(self.q_rp, self.r_gain, self.r_gain, '+', self.cfg["step"])  # update gain of the Gaussian

class AmplitudeRabiFF(ExperimentClass):
    """
    Basic AmplitudeRabi
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        #### pull the data from the amp rabi sweep
        # prog = PulseProbeSpectroscopyProgram(self.soccfg, self.cfg)
        prog = AmplitudeRabiFFProg(self.soccfg, self.cfg)

        x_pts, avgi, avgq = prog.acquire(self.soc, threshold=None, angle=None, load_pulses=True,
                                         readouts_per_experiment=1, save_experiments=None,
                                         start_src="internal", progress=False)# , debug=False)

        # Ensure numeric arrays (handles nested lists)
        avgi = np.asarray(avgi, dtype=np.float64)
        avgq = np.asarray(avgq, dtype=np.float64)

        # Optional: ensure x_pts is numeric too
        x_pts = np.asarray(x_pts, dtype=np.float64)

        phase = 2 * np.pi * self.cfg['cavity_winding_freq'] * self.cfg["pulse_freq"] + self.cfg['cavity_winding_offset']
        signal = (avgi + 1j * avgq) * np.exp(1j * phase)

        avgi = signal.real
        avgq = signal.imag

        data = {'config': self.cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        return data


    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data

        x_pts = np.asarray(data['data']['x_pts'], dtype=float)
        avgi = np.asarray(data['data']['avgi'][0][0], dtype=float)
        avgq = np.asarray(data['data']['avgq'][0][0], dtype=float)

        # fit I and Q separately
        fit_i = fit_rabi_cosine(x_pts, avgi)
        fit_q = fit_rabi_cosine(x_pts, avgq)

        print("Raw extrema:")
        print("  Max I gain:", x_pts[np.argmax(avgi)], " Max Q gain:", x_pts[np.argmax(avgq)])
        print("  Min I gain:", x_pts[np.argmin(avgi)], " Min Q gain:", x_pts[np.argmin(avgq)])

        print("\nCosine fit results:")
        print(f"  I fit period P       = {fit_i['P']:.3f} ± {fit_i['dP']:.3f}")
        print(f"  I fit phase phi      = {fit_i['phi']:.3f} ± {fit_i['dphi']:.3f}")
        print(f"  I-derived pi gain    = {fit_i['pi_gain']:.3f}")

        print(f"  Q fit period P       = {fit_q['P']:.3f} ± {fit_q['dP']:.3f}")
        print(f"  Q fit phase phi      = {fit_q['phi']:.3f} ± {fit_q['dphi']:.3f}")
        print(f"  Q-derived pi gain    = {fit_q['pi_gain']:.3f}")

        # store fit results on the object in case you want to inspect later
        self.fit_i = fit_i
        self.fit_q = fit_q

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig = plt.figure(figNum)
        plt.plot(x_pts, avgi, 'o', label="I data", color='orange')
        plt.plot(x_pts, fit_i['yfit'], '-', label=f"I fit, pi={fit_i['pi_gain']:.1f}", color='orange')

        plt.plot(x_pts, avgq, 'o', label="Q data", color='blue')
        plt.plot(x_pts, fit_q['yfit'], '-', label=f"Q fit, pi={fit_q['pi_gain']:.1f}", color='blue')

        plt.axvline(fit_i['pi_gain'], linestyle='--', color='orange', alpha=0.7, label="I pi gain")
        plt.axvline(fit_q['pi_gain'], linestyle='--', color='blue', alpha=0.7, label="Q pi gain")

        plt.ylabel("a.u.")
        plt.xlabel("qubit gain")
        plt.legend()
        plt.title(self.titlename)
        plt.tight_layout()
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


