"""
================================================================================
mT2Ramsey.py - T2 Ramsey Dephasing Measurement
================================================================================

Measures the qubit dephasing time (T2*) using Ramsey interferometry:
1. Apply π/2 pulse to create superposition
2. Wait variable delay time
3. Apply second π/2 pulse
4. Measure qubit state

The resulting oscillations decay with characteristic time T2*.

USAGE:
------
    from StarterPackConfig import BaseConfig, make_config
    from T2RamseyExperiment import T2RamseyExperiment
    
    exp_cfg = {"expts": 61, "step": 0.5}
    full_cfg = make_config(exp_cfg, qubit_id='1')
    
    exp = T2RamseyExperiment(path='T2', cfg=full_cfg, soc=soc, soccfg=soccfg)
    data = exp.acquire()
    exp.display(data)

================================================================================
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

# QICK imports
try:
    from qick import RAveragerProgram
    QICK_AVAILABLE = True
except ImportError:
    QICK_AVAILABLE = False
    class RAveragerProgram:
        pass

# Base experiment class
try:
    from MasterProject.Client_modules.Desq_GUI.CoreLib.Experiment import ExperimentClass
except ImportError:
    try:
        from WorkingProjects.Triangle_Lattice_tProcV2.Experiment import ExperimentClass
    except ImportError:
        try:
            from .StarterPackConfig import ExperimentClass
        except ImportError:
            from StarterPackConfig import ExperimentClass


# =============================================================================
# QICK PROGRAM
# =============================================================================

class T2RamseyProgram(RAveragerProgram):
    """
    T2 Ramsey measurement pulse sequence.

    Sequence: π/2 pulse → variable delay → π/2 pulse → readout
    Sweep: delay time
    """

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        # T2 sweep registers
        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_wait = self.us2cycles(0.010)
        self.r_phase2 = 4
        self.r_phase = self.sreg(cfg["qubit_ch"], "phase")
        self.regwi(self.q_rp, self.r_wait, self.us2cycles(cfg["start"]))
        self.regwi(self.q_rp, self.r_phase2, 0)

        # Declare channels
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])

        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["read_length"]),
                freq=cfg["read_pulse_freq"],
                gen_ch=cfg["res_ch"]
            )

        # Frequencies
        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"],
                                  ro_ch=cfg["ro_chs"][0])
        qubit_freq = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg["qubit_ch"])

        # Qubit pulse (π/2)
        self.add_gauss(
            ch=cfg["qubit_ch"],
            name="qubit",
            sigma=self.us2cycles(cfg["sigma"]),
            length=self.us2cycles(cfg["sigma"]) * 4
        )
        self.set_pulse_registers(
            ch=cfg["qubit_ch"],
            style="arb",
            freq=qubit_freq,
            phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]),
            gain=cfg["pi2_qubit_gain"],
            waveform="qubit"
        )

        # Readout pulse
        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style=cfg["read_pulse_style"],
            freq=read_freq,
            phase=0,
            gain=cfg["read_pulse_gain"],
            length=self.us2cycles(cfg["read_length"])
        )

        self.sync_all(self.us2cycles(0.2))

    def body(self):
        self.regwi(self.q_rp, self.r_phase, 0)

        # First π/2 pulse
        self.pulse(ch=self.cfg["qubit_ch"])
        self.mathi(self.q_rp, self.r_phase, self.r_phase2, "+", 0)
        self.sync_all()

        # Variable delay
        self.sync(self.q_rp, self.r_wait)

        # Second π/2 pulse
        self.pulse(ch=self.cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.05))

        # Readout
        self.measure(
            pulse_ch=self.cfg["res_ch"],
            adcs=self.cfg["ro_chs"],
            adc_trig_offset=self.us2cycles(self.cfg["adc_trig_offset"],
                                           ro_ch=self.cfg["ro_chs"][0]),
            wait=True,
            syncdelay=self.us2cycles(self.cfg["relax_delay"])
        )

    def update(self):
        self.mathi(self.q_rp, self.r_wait, self.r_wait, '+',
                   self.us2cycles(self.cfg["step"]))


# =============================================================================
# EXPERIMENT CLASS
# =============================================================================

class T2RamseyExperiment(ExperimentClass):
    """
    T2 Ramsey Dephasing Measurement

    Measures the qubit dephasing time (T2*) using Ramsey interferometry.
    The π/2 - delay - π/2 sequence produces oscillations that decay
    with characteristic time T2*.
    """

    # =========================================================================
    # CONFIGURATION TEMPLATE (Experiment-Specific Parameters Only)
    # =========================================================================

    config_template = {
        # --- T2 Ramsey Sweep Parameters ---
        "start": 0.010,                   # Starting delay [µs]
        "step": 1.0,                      # Delay step [µs]
        "expts": 51,                      # Number of points
        
        # --- Qubit Pulse Parameters ---
        "qubit_pulse_style": "arb",       # Pulse style
        "pi2_qubit_gain": 10000,          # π/2 pulse amplitude [DAC units]
    }

    def __init__(self, path='', outerFolder='', prefix='data',
                 soc=None, soccfg=None, cfg=None, config_file=None, **kwargs):
        super().__init__(
            path=path, outerFolder=outerFolder, prefix=prefix,
            soc=soc, soccfg=soccfg, cfg=cfg, config_file=config_file, **kwargs
        )

    def acquire(self, progress=False, debug=False):
        """Run T2 Ramsey measurement."""
        prog = T2RamseyProgram(self.soccfg, self.cfg)
        x_pts, avgi, avgq = prog.acquire(
            self.soc, threshold=None, angle=None, load_pulses=True,
            readouts_per_experiment=1, save_experiments=None,
            start_src="internal", progress=progress
        )

        data = {
            'config': self.cfg,
            'data': {
                'times': x_pts,
                'avgi': avgi,
                'avgq': avgq,
            }
        }
        self.data = data
        return data

    def analyze(self, data=None, **kwargs):
        """Fit damped oscillation to extract T2*."""
        if data is None:
            data = self.data

        times = data['data']['times']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]
        
        # Fit damped cosine
        def ramsey_fit(t, T2, freq, A, phi, y0):
            return A * np.exp(-t / T2) * np.cos(2 * np.pi * freq * t + phi) + y0

        try:
            # Initial guess from FFT
            from scipy.fft import fft, fftfreq
            yf = np.abs(fft(avgi - np.mean(avgi)))
            xf = fftfreq(len(times), times[1] - times[0])
            idx = np.argmax(yf[:len(yf)//2])
            freq_guess = abs(xf[idx])
            
            p0 = [times[-1]/3, freq_guess, np.ptp(avgi)/2, 0, np.mean(avgi)]
            popt, _ = curve_fit(ramsey_fit, times, avgi, p0=p0, maxfev=5000)
            
            data['data']['T2'] = popt[0]
            data['data']['detuning'] = popt[1]
            data['data']['fit_params'] = {
                'T2': popt[0], 'freq': popt[1], 'A': popt[2], 
                'phi': popt[3], 'y0': popt[4]
            }
            print(f"[T2Ramsey] Fitted T2* = {popt[0]:.2f} µs, detuning = {popt[1]:.3f} MHz")
        except Exception as e:
            print(f"[T2Ramsey] Fit failed: {e}")

        return data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        """Plot T2 Ramsey results."""
        if data is None:
            data = self.data

        times = data['data']['times']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]
        mag = np.abs(avgi + 1j * avgq)
        phase = np.angle(avgi + 1j * avgq, deg=True)

        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(4, 1, figsize=(10, 10), num=figNum)

        axs[0].plot(times, phase, 'o-', color='purple', markersize=4)
        axs[0].set_ylabel("Phase (deg)")
        axs[0].set_title("T2 Ramsey Measurement")
        axs[0].grid(True, alpha=0.3)

        axs[1].plot(times, mag, 'o-', color='blue', markersize=4)
        axs[1].set_ylabel("Magnitude (a.u.)")
        axs[1].grid(True, alpha=0.3)

        axs[2].plot(times, avgi, 'o-', color='orange', markersize=4, label='Data')
        if 'fit_params' in data['data']:
            fp = data['data']['fit_params']
            t_fine = np.linspace(times[0], times[-1], 500)
            fit = fp['A'] * np.exp(-t_fine/fp['T2']) * np.cos(2*np.pi*fp['freq']*t_fine + fp['phi']) + fp['y0']
            axs[2].plot(t_fine, fit, '--', color='black', linewidth=2,
                       label=f"T2* = {fp['T2']:.2f} µs")
            axs[2].legend()
        axs[2].set_ylabel("I (a.u.)")
        axs[2].grid(True, alpha=0.3)

        axs[3].plot(times, avgq, 'o-', color='green', markersize=4)
        axs[3].set_ylabel("Q (a.u.)")
        axs[3].set_xlabel("Time (µs)")
        axs[3].grid(True, alpha=0.3)

        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)
        else:
            plt.close(fig)

        return fig, axs

    def save_data(self, data=None):
        if data is None:
            data = self.data
        print(f"[T2RamseyExperiment] Saving to {self.fname}")
        super().save_data(data=data['data'])


# =============================================================================
# MOCK VERSION FOR TESTING
# =============================================================================

class MockT2RamseyExperiment(ExperimentClass):
    """
    Mock T2 Ramsey Experiment - Simulates dephasing measurement without hardware.
    """

    config_template = {
        # --- T2 Ramsey Sweep Parameters ---
        "start": 0.010,
        "step": 1.0,
        "expts": 61,
        "qubit_pulse_style": "arb",
        "pi2_qubit_gain": 10000,
        
        # --- Mock Simulation Parameters ---
        "T2_true": 15.0,                  # Simulated T2* value [µs]
        "detuning": 0.5,                  # Detuning frequency [MHz]
        "noise_level": 0.08,
    }

    def __init__(self, path='', outerFolder='', prefix='data', cfg=None, **kwargs):
        default_cfg = self.config_template.copy()
        if cfg:
            default_cfg.update(cfg)
        super().__init__(path=path, outerFolder=outerFolder, prefix=prefix,
                         cfg=default_cfg, **kwargs)

    def acquire(self, progress=False, debug=False):
        """Generate simulated Ramsey oscillation data."""
        cfg = self.cfg
        times = np.linspace(cfg['start'], cfg['start'] + cfg['step'] * cfg['expts'],
                           cfg['expts'])

        T2 = cfg['T2_true']
        omega = 2 * np.pi * cfg['detuning']
        envelope = np.exp(-times / T2)

        avgi = envelope * np.cos(omega * times)
        avgi += cfg['noise_level'] * np.random.randn(len(times))

        avgq = envelope * np.sin(omega * times)
        avgq += cfg['noise_level'] * np.random.randn(len(times))

        data = {
            'config': cfg,
            'data': {
                'times': times,
                'avgi': [[avgi]],
                'avgq': [[avgq]],
            }
        }
        self.data = data
        return data

    def analyze(self, data=None, **kwargs):
        """Fit damped oscillation."""
        if data is None:
            data = self.data

        times = data['data']['times']
        avgi = data['data']['avgi'][0][0]
        
        def ramsey_fit(t, T2, freq, A, phi, y0):
            return A * np.exp(-t / T2) * np.cos(2 * np.pi * freq * t + phi) + y0

        try:
            p0 = [self.cfg['T2_true'], self.cfg['detuning'], 1.0, 0, 0]
            popt, _ = curve_fit(ramsey_fit, times, avgi, p0=p0, maxfev=5000)
            
            data['data']['T2'] = popt[0]
            data['data']['fit_params'] = {
                'T2': popt[0], 'freq': popt[1], 'A': popt[2], 
                'phi': popt[3], 'y0': popt[4]
            }
            print(f"[MockT2Ramsey] Fitted T2* = {popt[0]:.2f} µs (true = {self.cfg['T2_true']:.2f} µs)")
        except Exception as e:
            print(f"[MockT2Ramsey] Fit failed: {e}")

        return data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        """Plot Ramsey results."""
        if data is None:
            data = self.data

        times = data['data']['times']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]
        mag = np.abs(avgi + 1j * avgq)
        phase = np.angle(avgi + 1j * avgq, deg=True)

        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(4, 1, figsize=(10, 10), num=figNum)

        axs[0].plot(times, phase, 'o-', color='purple', markersize=3)
        axs[0].set_ylabel("Phase (deg)")
        axs[0].set_title("Mock T2 Ramsey Experiment")
        axs[0].grid(True, alpha=0.3)

        axs[1].plot(times, mag, 'o-', color='blue', markersize=3)
        axs[1].set_ylabel("Magnitude (a.u.)")
        axs[1].grid(True, alpha=0.3)

        axs[2].plot(times, avgi, 'o-', color='orange', markersize=3, label='Data')
        if 'fit_params' in data['data']:
            fp = data['data']['fit_params']
            t_fine = np.linspace(times[0], times[-1], 500)
            fit = fp['A'] * np.exp(-t_fine/fp['T2']) * np.cos(2*np.pi*fp['freq']*t_fine + fp['phi']) + fp['y0']
            axs[2].plot(t_fine, fit, '--', color='black', linewidth=2,
                       label=f"T2* = {fp['T2']:.2f} µs")
            axs[2].legend()
        axs[2].set_ylabel("I (a.u.)")
        axs[2].grid(True, alpha=0.3)

        axs[3].plot(times, avgq, 'o-', color='green', markersize=3)
        axs[3].set_ylabel("Q (a.u.)")
        axs[3].set_xlabel("Time (µs)")
        axs[3].grid(True, alpha=0.3)

        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)
        else:
            plt.close(fig)

        return fig, axs

    def save_data(self, data=None):
        if data is None:
            data = self.data
        print(f"[MockT2Ramsey] Saving to {self.fname}")
        super().save_data(data=data.get('data', data))


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    print("Testing MockT2RamseyExperiment...")
    exp = MockT2RamseyExperiment(path='test', prefix='t2')
    data = exp.acquire()
    exp.analyze(data)
    exp.display(data, plotDisp=True, block=True)
