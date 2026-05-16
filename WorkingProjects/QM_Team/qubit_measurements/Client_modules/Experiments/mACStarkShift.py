from qick import *
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import curve_fit

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.Experiment import ExperimentClass


def _lorentzian(x, y0, a, x0, gamma):
    return y0 + a * (gamma ** 2 / ((x - x0) ** 2 + gamma ** 2))


def _extract_peak_center(x_pts, signal_power, fit_window_pts=11):
    x_pts = np.asarray(x_pts, dtype=float).ravel()
    signal_power = np.asarray(signal_power, dtype=float).ravel()

    peak_idx = int(np.argmax(signal_power))
    peak_x = float(x_pts[peak_idx])

    half_window = max(int(fit_window_pts) // 2, 2)
    lo = max(0, peak_idx - half_window)
    hi = min(len(x_pts), peak_idx + half_window + 1)

    if hi - lo < 5:
        return peak_x, None

    xf = x_pts[lo:hi]
    yf = signal_power[lo:hi]
    y0_guess = float(np.median(yf))
    a_guess = float(np.max(yf) - y0_guess)
    gamma_guess = max(float((xf[-1] - xf[0]) / 6.0), 1e-6)

    try:
        popt, pcov = curve_fit(
            _lorentzian,
            xf,
            yf,
            p0=[y0_guess, a_guess, peak_x, gamma_guess],
            bounds=(
                [-np.inf, 0.0, np.min(xf), 1e-9],
                [np.inf, np.inf, np.max(xf), max(np.max(xf) - np.min(xf), 1e-6)],
            ),
            maxfev=20000,
        )
        return float(popt[2]), np.asarray(popt, dtype=float)
    except Exception:
        return peak_x, None


class ACStarkShiftProgram(RAveragerProgram):
    def initialize(self):
        cfg = self.cfg

        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")

        self.declare_gen(
            ch=cfg["res_ch"],
            nqz=cfg["nqz"],
            mixer_freq=cfg.get("mixer_freq", 0.0),
            ro_ch=cfg["ro_chs"][0],
        )
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])

        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["readout_length"]),
                freq=cfg["pulse_freq"],
                gen_ch=cfg["res_ch"],
            )

        self.qubit_freq_start = self.freq2reg(cfg["start"], gen_ch=cfg["qubit_ch"])
        self.qubit_freq_step = self.freq2reg(cfg["step"], gen_ch=cfg["qubit_ch"])
        self.regwi(self.q_rp, self.r_freq, self.qubit_freq_start)

        self.measure_freq = self.freq2reg(
            cfg["pulse_freq"], gen_ch=cfg["res_ch"], ro_ch=cfg["ro_chs"][0]
        )
        self.stark_freq = self.freq2reg(
            cfg.get("stark_freq", cfg["pulse_freq"]),
            gen_ch=cfg["res_ch"],
            ro_ch=cfg["ro_chs"][0],
        )

        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style="const",
            freq=self.measure_freq,
            phase=cfg["res_phase"],
            gain=cfg["pulse_gain"],
            length=self.us2cycles(cfg["length"]),
        )

        self.pulse_sigma = self.us2cycles(cfg["sigma"], gen_ch=cfg["qubit_ch"])
        self.pulse_qubit_length = self.us2cycles(cfg["sigma"] * 4.0, gen_ch=cfg["qubit_ch"])
        self.add_gauss(
            ch=cfg["qubit_ch"],
            name="qubit",
            sigma=self.pulse_sigma,
            length=self.pulse_qubit_length,
        )

        self.qubit_flattop_cycles = None
        if cfg["flattop_length"] is not None:
            self.qubit_flattop_cycles = self.us2cycles(
                cfg["flattop_length"], gen_ch=cfg["qubit_ch"]
            )

        self.stark_length_cycles = self.us2cycles(cfg["stark_length"])
        self.stark_t0_cycles = self.us2cycles(cfg.get("stark_t0", 0.01))
        self.stark_qubit_delay_cycles = self.us2cycles(cfg.get("stark_qubit_delay", 0.1))
        self.post_stark_wait_cycles = self.us2cycles(cfg.get("post_stark_wait", 0.05))

        self.sync_all(self.us2cycles(0.2))

    def body(self):
        cfg = self.cfg

        self.sync_all()

        if cfg.get("stark_gain", 0) > 0:
            self.setup_and_pulse(
                ch=cfg["res_ch"],
                style="const",
                freq=self.stark_freq,
                phase=cfg["res_phase"],
                gain=cfg["stark_gain"],
                length=self.stark_length_cycles,
                t=self.stark_t0_cycles,
            )

        qubit_t = self.stark_t0_cycles + self.stark_qubit_delay_cycles
        if self.qubit_flattop_cycles is not None:
            self.setup_and_pulse(
                ch=cfg["qubit_ch"],
                style="flat_top",
                freq=self.qubit_freq_start,
                phase=self.deg2reg(0, gen_ch=cfg["qubit_ch"]),
                gain=cfg["qubit_gain"],
                waveform="qubit",
                length=self.qubit_flattop_cycles,
                t=qubit_t,
            )
        else:
            self.setup_and_pulse(
                ch=cfg["qubit_ch"],
                style="arb",
                freq=self.qubit_freq_start,
                phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]),
                gain=cfg["qubit_gain"],
                waveform="qubit",
                t=qubit_t,
            )

        total_wait_cycles = max(
            self.stark_length_cycles + self.stark_t0_cycles,
            qubit_t + self.pulse_qubit_length,
        ) + self.post_stark_wait_cycles
        self.sync_all(total_wait_cycles)

        self.measure(
            pulse_ch=cfg["res_ch"],
            adcs=self.ro_chs,
            adc_trig_offset=self.us2cycles(cfg["adc_trig_offset"]),
            wait=True,
            syncdelay=self.us2cycles(cfg["relax_delay"]),
        )

    def update(self):
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.qubit_freq_step)


class ACStarkShift(ExperimentClass):
    def __init__(
        self,
        soc=None,
        soccfg=None,
        path='ACStarkShift',
        outerFolder='',
        prefix='data',
        cfg=None,
        config_file=None,
        progress=None,
    ):
        super().__init__(
            soc=soc,
            soccfg=soccfg,
            path=path,
            outerFolder=outerFolder,
            prefix=prefix,
            cfg=cfg,
            config_file=config_file,
            progress=progress,
        )

    def acquire(self, progress=False, debug=False):
        cfg = self.cfg

        stark_gain_pts = np.linspace(
            cfg["stark_gain_start"],
            cfg["stark_gain_stop"],
            cfg["stark_gain_points"],
        )

        avgi_mat = []
        avgq_mat = []
        centers = []
        fit_params = []

        for stark_gain in stark_gain_pts:
            run_cfg = dict(cfg)
            run_cfg["stark_gain"] = int(round(float(stark_gain)))

            prog = ACStarkShiftProgram(self.soccfg, run_cfg)
            x_pts, avgi, avgq = prog.acquire(
                self.soc,
                threshold=None,
                angle=None,
                load_pulses=True,
                readouts_per_experiment=1,
                save_experiments=None,
                start_src="internal",
                progress=False,
            )

            avgi = np.asarray(avgi, dtype=float)
            avgq = np.asarray(avgq, dtype=float)
            signal = (avgi + 1j * avgq) * np.exp(
                1j * (
                    2 * np.pi * cfg['cavity_winding_freq'] * cfg["pulse_freq"]
                    + cfg['cavity_winding_offset']
                )
            )
            avgi = signal.real
            avgq = signal.imag

            avgi_line = np.asarray(avgi[0][0], dtype=float)
            avgq_line = np.asarray(avgq[0][0], dtype=float)
            power_line = np.abs(avgi_line + 1j * avgq_line) ** 2

            center, popt = _extract_peak_center(
                x_pts,
                power_line,
                fit_window_pts=cfg.get("stark_fit_window_pts", 11),
            )

            avgi_mat.append(avgi_line)
            avgq_mat.append(avgq_line)
            centers.append(center)
            if popt is None:
                fit_params.append(np.full(4, np.nan))
            else:
                fit_params.append(popt)

        avgi_mat = np.asarray(avgi_mat, dtype=float)
        avgq_mat = np.asarray(avgq_mat, dtype=float)
        centers = np.asarray(centers, dtype=float)
        fit_params = np.asarray(fit_params, dtype=float)
        x_pts = np.asarray(x_pts, dtype=float)

        center_shift = centers - centers[0] if len(centers) else np.asarray([])

        data = {
            'config': cfg,
            'data': {
                'stark_gain_pts': np.asarray(stark_gain_pts, dtype=float),
                'qubit_freq_pts': x_pts,
                'avgi_mat': avgi_mat,
                'avgq_mat': avgq_mat,
                'signal_power_mat': np.abs(avgi_mat + 1j * avgq_mat) ** 2,
                'qubit_centers': centers,
                'qubit_center_shift': center_shift,
                'lorentz_popts': fit_params,
                'stark_freq': np.asarray(cfg.get("stark_freq", cfg["pulse_freq"])),
            }
        }
        self.data = data
        return data

    def display(self, data=None, plotDisp=False, figNum=1, **kwargs):
        if data is None:
            data = self.data

        gain_pts = np.asarray(data['data']['stark_gain_pts'], dtype=float)
        qubit_freq_pts = np.asarray(data['data']['qubit_freq_pts'], dtype=float)
        signal_power_mat = np.asarray(data['data']['signal_power_mat'], dtype=float)
        qubit_centers = np.asarray(data['data']['qubit_centers'], dtype=float)
        qubit_center_shift = np.asarray(data['data']['qubit_center_shift'], dtype=float)

        while plt.fignum_exists(num=figNum):
            figNum += 1

        x_step = qubit_freq_pts[1] - qubit_freq_pts[0] if len(qubit_freq_pts) > 1 else 1.0
        y_step = gain_pts[1] - gain_pts[0] if len(gain_pts) > 1 else 1.0

        fig, axs = plt.subplots(2, 1, figsize=(8, 10), num=figNum)
        plt.suptitle(self.titlename)

        img = axs[0].imshow(
            signal_power_mat,
            aspect='auto',
            extent=[
                qubit_freq_pts[0] - x_step / 2,
                qubit_freq_pts[-1] + x_step / 2,
                gain_pts[0] - y_step / 2,
                gain_pts[-1] + y_step / 2,
            ],
            origin='lower',
            interpolation='none',
        )
        axs[0].plot(qubit_centers, gain_pts, color='white', linewidth=1.5, label='Extracted center')
        axs[0].set_xlabel("Qubit Frequency (MHz)")
        axs[0].set_ylabel("Stark Tone Gain (DAC)")
        axs[0].set_title("Qubit Spectroscopy Under Cavity Stark Tone")
        axs[0].legend(loc='best')
        cbar = fig.colorbar(img, ax=axs[0])
        cbar.set_label('Signal power (a.u.)')

        axs[1].plot(gain_pts, qubit_center_shift, 'o-', color='tab:blue')
        axs[1].set_xlabel("Stark Tone Gain (DAC)")
        axs[1].set_ylabel("Center Shift (MHz)")
        axs[1].set_title("Extracted AC Stark Shift")
        axs[1].grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(self.iname)

        if len(qubit_centers):
            print(f"Reference qubit center: {qubit_centers[0]:.6f} MHz")
            print(f"Max extracted shift:    {np.max(np.abs(qubit_center_shift)):.6f} MHz")

        if plotDisp:
            plt.show(block=True)
            plt.pause(0.1)
        else:
            fig.clf(True)
            plt.close(fig)

    def save_data(self, data=None):
        if data is None:
            data = self.data
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])
