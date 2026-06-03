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


class AmplitudeRabiFFProg(AveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])  # Readout
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])  # Qubit
        for ch in [0, 1]:  # configure the readout lengths and downconversion frequencies
            self.declare_readout(ch=ch, length=self.us2cycles(cfg["readout_length"]),
                                 freq=cfg["pulse_freq"], gen_ch=cfg["res_ch"])
        f_res = self.freq2reg(cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0])  # conver f_res to dac register value
        f_ge = self.freq2reg(cfg["f_ge"], gen_ch=cfg["qubit_ch"])

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=self.cfg["qubit_ch"])
        self.pulse_qubit_lenth = self.us2cycles(cfg["sigma"] * 4, gen_ch=self.cfg["qubit_ch"])

        self.add_gauss(ch=cfg["qubit_ch"], name="qubit",
                       sigma=self.pulse_sigma,
                       length=self.pulse_qubit_lenth)
        if cfg["flattop_length"] != None:
            flattop_length = self.us2cycles(self.cfg["flattop_length"], gen_ch=self.cfg["qubit_ch"])
            self.set_pulse_registers(ch=cfg["qubit_ch"], style='flat_top', freq=f_ge,
                                     phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit",
                                     length=flattop_length) #Flat part of flattop does NOT update with gain
            self.pulse_qubit_lenth += flattop_length
        else:
            self.set_pulse_registers(ch=cfg["qubit_ch"], style="arb", freq=f_ge,
                                     phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]), gain=cfg["qubit_gain"],
                                     waveform="qubit")

        trig_length = cfg["trig_buffer_start"] + cfg["trig_buffer_end"] + cfg["sigma"] * 4
        if cfg["flattop_length"] != None:
            trig_length += self.cfg["flattop_length"]
        self.trig_length = self.us2cycles(trig_length)

        self.set_pulse_registers(ch=cfg["res_ch"], style="const", freq=f_res, phase=cfg["res_phase"],
                                 gain=cfg["pulse_gain"],
                                 length=self.us2cycles(cfg["length"]))

        self.sync_all(self.us2cycles(0.05))

    def body(self):
        self.sync_all()
        self.trigger(pins = [0], t = self.us2cycles(1 + self.cfg["trig_delay"] - self.cfg["trig_buffer_start"]), width = self.trig_length)

        self.pulse(ch=self.cfg["qubit_ch"], t=self.us2cycles(1))  # play probe pulse
        self.sync_all(self.us2cycles(0.05))

        self.measure(pulse_ch=self.cfg["res_ch"],
                     adcs=[0, 1],
                     adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"]),
                     wait=True,
                     syncdelay=self.us2cycles(10))

        self.sync_all(self.us2cycles(self.cfg["relax_delay"]))
class AmplitudeRabiFF_N(ExperimentClass):
    """
    Basic AmplitudeRabi
    """

    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, config_file=config_file, progress=progress)

    def acquire(self, progress=False, debug=False):
        self.cfg['reps'] *= self.cfg['rounds']
        self.cfg['rounds'] = 1
        gainpts = np.linspace(self.cfg["gain_start"],
                           self.cfg["gain_end"],
                           self.cfg["gainNumPoints"])
        results = []
        start = time.time()
        for g in tqdm(gainpts, position=0, disable=True):
            self.cfg["qubit_gain"] = int(g)
            prog = AmplitudeRabiFFProg(self.soccfg, self.cfg)
            results.append(prog.acquire(self.soc, load_pulses=True))
        print(f'Time: {time.time() - start}')
        results = np.transpose(results)
        signal = (results[0][0][0] + 1j * results[0][0][1]) * np.exp(1j * (2 * np.pi * self.cfg['cavity_winding_freq'] *
                                                   self.cfg["pulse_freq"] + self.cfg['cavity_winding_offset']))

        avgi = [[signal.real]]
        avgq = [[signal.imag]]
        data = {'config': self.cfg, 'data': {'x_pts': gainpts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data

        return data


    def display(self, data=None, plotDisp=False, figNum=1, fit=True, **kwargs):
        if data is None:
            data = self.data

        x_pts = np.asarray(data['data']['x_pts'], dtype=float)
        avgi = np.asarray(data['data']['avgi'][0][0], dtype=float)
        avgq = np.asarray(data['data']['avgq'][0][0], dtype=float)

        x_min, x_max = float(np.min(x_pts)), float(np.max(x_pts))

        fit_i = fit_q = None
        if fit:
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
        plt.plot(x_pts, avgq, 'o', label="Q data", color='blue')

        if fit:
            plt.plot(x_pts, fit_i['yfit'], '-', label=f"I fit, pi={fit_i['pi_gain']:.1f}", color='orange')
            plt.plot(x_pts, fit_q['yfit'], '-', label=f"Q fit, pi={fit_q['pi_gain']:.1f}", color='blue')

            # Only draw the pi-gain marker if the fit landed inside the swept range.
            # A failed cosine fit (no visible oscillation) returns a runaway period,
            # which would otherwise autoscale the x-axis out to ~1e9.
            for f, color, lbl in ((fit_i, 'orange', "I pi gain"), (fit_q, 'blue', "Q pi gain")):
                if x_min <= f['pi_gain'] <= x_max:
                    plt.axvline(f['pi_gain'], linestyle='--', color=color, alpha=0.7, label=lbl)
                else:
                    print(f"  [warn] {lbl} = {f['pi_gain']:.3g} outside swept range "
                          f"[{x_min:.0f}, {x_max:.0f}] -- fit likely failed, marker hidden.")

        plt.xlim(x_min, x_max)
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
        #print(f'Saving {self.fname}')
        new_name = self.fname[:-3] + '_Q' + str(self.cfg["Qubit_number"]) + '.h5'
        self.fname = new_name
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


def Amplitude_IQ(I, Q, phase_num_points = 500):
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