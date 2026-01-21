"""
================================================================================
mAmplitudeRabi.py - Amplitude Rabi Oscillations
================================================================================

Calibrates the π pulse amplitude by sweeping the drive amplitude:
1. Apply qubit pulse with variable amplitude
2. Measure qubit state
3. Find amplitude that gives maximum excitation (π pulse)

Can also do 2D sweeps (amplitude vs frequency) by setting qubit_freq_expts > 1.

USAGE:
------
    from StarterPackConfig import BaseConfig, make_config
    from AmplitudeRabiExperiment import AmplitudeRabiExperiment
    
    exp_cfg = {"qubit_gain_start": 0, "qubit_gain_stop": 30000, "qubit_gain_expts": 61}
    full_cfg = make_config(exp_cfg, qubit_id='1')
    
    exp = AmplitudeRabiExperiment(path='Rabi', cfg=full_cfg, soc=soc, soccfg=soccfg)
    data = exp.acquire()
    exp.display(data)

================================================================================
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

# QICK imports
try:
    from qick import NDAveragerProgram
    QICK_AVAILABLE = True
except ImportError:
    QICK_AVAILABLE = False
    class NDAveragerProgram:
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

class AmplitudeRabiProgram(NDAveragerProgram):
    """
    Amplitude Rabi pulse sequence using NDAveragerProgram for flexible sweeps.

    Sequence: variable amplitude qubit pulse → readout
    Sweep: qubit drive amplitude (and optionally frequency)
    """

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

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

        # Setup qubit pulse with sweep
        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(
                ch=cfg["qubit_ch"],
                name="qubit",
                sigma=self.us2cycles(cfg["sigma"]),
                length=self.us2cycles(cfg["sigma"]) * 4
            )
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="arb",
                freq=self.freq2reg(cfg["qubit_freq_start"], gen_ch=cfg["qubit_ch"]),
                phase=0,
                gain=cfg["qubit_gain_start"],
                waveform="qubit"
            )
        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(
                ch=cfg["qubit_ch"],
                name="qubit",
                sigma=self.us2cycles(cfg["sigma"]),
                length=self.us2cycles(cfg["sigma"]) * 4
            )
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="flat_top",
                freq=self.freq2reg(cfg["qubit_freq_start"], gen_ch=cfg["qubit_ch"]),
                phase=0,
                gain=cfg["qubit_gain_start"],
                waveform="qubit",
                length=self.us2cycles(cfg["flat_top_length"])
            )
        else:  # const
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="const",
                freq=self.freq2reg(cfg["qubit_freq_start"], gen_ch=cfg["qubit_ch"]),
                phase=0,
                gain=cfg["qubit_gain_start"],
                length=self.us2cycles(cfg["qubit_length"])
            )

        # Setup readout pulse
        self.set_pulse_registers(
            ch=cfg["res_ch"],
            style=cfg["read_pulse_style"],
            freq=read_freq,
            phase=0,
            gain=cfg["read_pulse_gain"],
            length=self.us2cycles(cfg["read_length"])
        )

        self.sync_all(self.us2cycles(cfg["relax_delay"]))

    def body(self):
        # Play qubit pulse
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


# =============================================================================
# EXPERIMENT CLASS
# =============================================================================

class AmplitudeRabiExperiment(ExperimentClass):
    """
    Amplitude Rabi Oscillation Measurement

    Sweeps the qubit drive amplitude to observe Rabi oscillations.
    Used to calibrate the π pulse amplitude.
    """

    # =========================================================================
    # CONFIGURATION TEMPLATE (Experiment-Specific Parameters Only)
    # =========================================================================

    config_template = {
        # --- Amplitude Sweep Parameters ---
        "qubit_gain_start": 0,            # Start amplitude [DAC units]
        "qubit_gain_stop": 30000,         # Stop amplitude [DAC units]
        "qubit_gain_expts": 61,           # Number of amplitude points

        # --- Optional Frequency Sweep (for 2D) ---
        "qubit_freq_start": 4500,         # Start frequency [MHz]
        "qubit_freq_stop": 4500,          # Stop frequency [MHz] (same = no sweep)
        "qubit_freq_expts": 1,            # Number of freq points (1 = amp only)
        
        # --- Pulse Style ---
        "qubit_pulse_style": "arb",       # "arb", "flat_top", or "const"
        "flat_top_length": 0.300,         # Flat top duration [µs] (if flat_top)
        "qubit_length": 1.0,              # Const pulse length [µs] (if const)
    }

    def __init__(self, path='', outerFolder='', prefix='data',
                 soc=None, soccfg=None, cfg=None, config_file=None, **kwargs):
        super().__init__(
            path=path, outerFolder=outerFolder, prefix=prefix,
            soc=soc, soccfg=soccfg, cfg=cfg, config_file=config_file, **kwargs
        )

    def acquire(self, progress=False, debug=False):
        """Run amplitude Rabi measurement."""
        cfg = self.cfg

        # Create sweep axes
        gains = np.linspace(cfg["qubit_gain_start"], cfg["qubit_gain_stop"],
                           cfg["qubit_gain_expts"])
        freqs = np.linspace(cfg["qubit_freq_start"], cfg["qubit_freq_stop"],
                           cfg["qubit_freq_expts"])

        # Configure NDAveragerProgram sweeps
        cfg["sweep_axes"] = {}
        
        # Add gain sweep
        gain_reg = self.soccfg.get_gen_reg(cfg["qubit_ch"], "gain")
        cfg["sweep_axes"]["gain"] = {
            "register": gain_reg,
            "start": int(cfg["qubit_gain_start"]),
            "stop": int(cfg["qubit_gain_stop"]),
            "expts": cfg["qubit_gain_expts"]
        }

        # Add frequency sweep if requested
        if cfg["qubit_freq_expts"] > 1:
            freq_reg = self.soccfg.get_gen_reg(cfg["qubit_ch"], "freq")
            f_start = self.soccfg.freq2reg(cfg["qubit_freq_start"], gen_ch=cfg["qubit_ch"])
            f_stop = self.soccfg.freq2reg(cfg["qubit_freq_stop"], gen_ch=cfg["qubit_ch"])
            cfg["sweep_axes"]["freq"] = {
                "register": freq_reg,
                "start": f_start,
                "stop": f_stop,
                "expts": cfg["qubit_freq_expts"]
            }

        prog = AmplitudeRabiProgram(self.soccfg, cfg)
        avgi, avgq = prog.acquire(
            self.soc, threshold=None, angle=None, load_pulses=True,
            readouts_per_experiment=1, save_experiments=None,
            start_src="internal", progress=progress
        )

        data = {
            'config': cfg,
            'data': {
                'gains': gains,
                'freqs': freqs,
                'avgi': avgi,
                'avgq': avgq,
            }
        }
        self.data = data
        return data

    def analyze(self, data=None, **kwargs):
        """Fit Rabi oscillation to find π amplitude."""
        if data is None:
            data = self.data

        gains = data['data']['gains']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]
        
        # For 1D sweep, fit sinusoidal oscillation
        if self.cfg["qubit_freq_expts"] == 1:
            mag = np.abs(avgi + 1j * avgq)
            
            def rabi_fit(x, A, pi_amp, phi, y0):
                return A * np.sin(np.pi * x / pi_amp + phi)**2 + y0

            try:
                # Find approximate period from data
                p0 = [np.ptp(mag)/2, gains[-1]/2, 0, np.min(mag)]
                popt, _ = curve_fit(rabi_fit, gains, mag, p0=p0, maxfev=5000)
                
                data['data']['pi_amplitude'] = popt[1]
                data['data']['fit_params'] = {
                    'A': popt[0], 'pi_amp': popt[1], 'phi': popt[2], 'y0': popt[3]
                }
                print(f"[AmplitudeRabi] π amplitude = {popt[1]:.0f} DAC units")
            except Exception as e:
                print(f"[AmplitudeRabi] Fit failed: {e}")

        return data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        """Plot Rabi oscillation results."""
        if data is None:
            data = self.data

        gains = data['data']['gains']
        freqs = data['data']['freqs']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']

        while plt.fignum_exists(num=figNum):
            figNum += 1

        if len(freqs) == 1:
            # 1D plot
            avgi = avgi[0][0]
            avgq = avgq[0][0]
            mag = np.abs(avgi + 1j * avgq)
            phase = np.angle(avgi + 1j * avgq, deg=True)

            fig, axs = plt.subplots(4, 1, figsize=(10, 10), num=figNum)

            axs[0].plot(gains, phase, 'o-', color='purple', markersize=4)
            axs[0].set_ylabel("Phase (deg)")
            axs[0].set_title("Amplitude Rabi Oscillations")
            axs[0].grid(True, alpha=0.3)

            axs[1].plot(gains, mag, 'o-', color='blue', markersize=4, label='Data')
            if 'fit_params' in data['data']:
                fp = data['data']['fit_params']
                g_fine = np.linspace(gains[0], gains[-1], 200)
                fit = fp['A'] * np.sin(np.pi * g_fine / fp['pi_amp'] + fp['phi'])**2 + fp['y0']
                axs[1].plot(g_fine, fit, '--', color='black', linewidth=2,
                           label=f"π = {fp['pi_amp']:.0f}")
                axs[1].legend()
            axs[1].set_ylabel("Magnitude (a.u.)")
            axs[1].grid(True, alpha=0.3)

            axs[2].plot(gains, avgi, 'o-', color='orange', markersize=4)
            axs[2].set_ylabel("I (a.u.)")
            axs[2].grid(True, alpha=0.3)

            axs[3].plot(gains, avgq, 'o-', color='green', markersize=4)
            axs[3].set_ylabel("Q (a.u.)")
            axs[3].set_xlabel("Qubit Gain (DAC units)")
            axs[3].grid(True, alpha=0.3)

        else:
            # 2D plot
            fig, axs = plt.subplots(2, 2, figsize=(12, 10), num=figNum)
            
            mag = np.abs(avgi[0] + 1j * avgq[0])
            
            im0 = axs[0, 0].pcolormesh(gains, freqs, avgi[0], shading='auto', cmap='RdBu_r')
            axs[0, 0].set_xlabel("Gain (DAC)")
            axs[0, 0].set_ylabel("Frequency (MHz)")
            axs[0, 0].set_title("I")
            plt.colorbar(im0, ax=axs[0, 0])

            im1 = axs[0, 1].pcolormesh(gains, freqs, avgq[0], shading='auto', cmap='RdBu_r')
            axs[0, 1].set_xlabel("Gain (DAC)")
            axs[0, 1].set_ylabel("Frequency (MHz)")
            axs[0, 1].set_title("Q")
            plt.colorbar(im1, ax=axs[0, 1])

            im2 = axs[1, 0].pcolormesh(gains, freqs, mag, shading='auto', cmap='viridis')
            axs[1, 0].set_xlabel("Gain (DAC)")
            axs[1, 0].set_ylabel("Frequency (MHz)")
            axs[1, 0].set_title("Magnitude")
            plt.colorbar(im2, ax=axs[1, 0])

            axs[1, 1].axis('off')
            
            fig.suptitle("2D Amplitude Rabi", fontsize=12)

        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)
        else:
            plt.close(fig)

        return fig, axs

    def save_data(self, data=None):
        if data is None:
            data = self.data
        print(f"[AmplitudeRabiExperiment] Saving to {self.fname}")
        super().save_data(data=data['data'])


# =============================================================================
# MOCK VERSION FOR TESTING
# =============================================================================

class MockAmplitudeRabiExperiment(ExperimentClass):
    """
    Mock Amplitude Rabi Experiment - Generates simulated Rabi oscillations without hardware.
    """

    config_template = {
        # --- Amplitude Sweep Parameters ---
        "qubit_gain_start": 0,
        "qubit_gain_stop": 30000,
        "qubit_gain_expts": 61,
        "qubit_freq_start": 4500,
        "qubit_freq_stop": 4500,
        "qubit_freq_expts": 1,
        "qubit_pulse_style": "arb",
        "flat_top_length": 0.300,
        "qubit_length": 1.0,
        
        # --- Mock Simulation Parameters ---
        "pi_amplitude": 15000,            # Simulated π pulse amplitude [DAC units]
        "noise_level": 0.05,
    }

    def __init__(self, path='', outerFolder='', prefix='data', cfg=None, **kwargs):
        default_cfg = self.config_template.copy()
        if cfg:
            default_cfg.update(cfg)
        super().__init__(path=path, outerFolder=outerFolder, prefix=prefix,
                         cfg=default_cfg, **kwargs)

    def acquire(self, progress=False, debug=False):
        """Generate simulated Rabi oscillation data."""
        cfg = self.cfg
        gains = np.linspace(cfg['qubit_gain_start'], cfg['qubit_gain_stop'],
                           cfg['qubit_gain_expts'])
        freqs = np.linspace(cfg['qubit_freq_start'], cfg['qubit_freq_stop'],
                           cfg['qubit_freq_expts'])

        pi_amp = cfg['pi_amplitude']

        if cfg['qubit_freq_expts'] == 1:
            # 1D Rabi
            rabi = np.sin(np.pi * gains / pi_amp)**2
            noise_i = cfg['noise_level'] * np.random.randn(len(gains))
            noise_q = cfg['noise_level'] * np.random.randn(len(gains))

            avgi = rabi + noise_i
            avgq = 0.2 * rabi + noise_q

            data = {
                'config': cfg,
                'data': {
                    'gains': gains,
                    'freqs': freqs,
                    'avgi': [[avgi]],
                    'avgq': [[avgq]],
                }
            }
        else:
            # 2D Rabi
            GAINS, FREQS = np.meshgrid(gains, freqs)
            # Rabi with frequency-dependent pi amplitude
            pi_amp_2d = pi_amp * (1 + 0.01 * (FREQS - np.mean(freqs)))
            rabi = np.sin(np.pi * GAINS / pi_amp_2d)**2
            noise = cfg['noise_level'] * np.random.randn(*GAINS.shape)

            avgi = rabi + noise
            avgq = 0.2 * rabi + 0.5 * noise

            data = {
                'config': cfg,
                'data': {
                    'gains': gains,
                    'freqs': freqs,
                    'avgi': [avgi],
                    'avgq': [avgq],
                }
            }

        self.data = data
        return data

    def analyze(self, data=None, **kwargs):
        """Fit Rabi oscillation."""
        if data is None:
            data = self.data

        if self.cfg['qubit_freq_expts'] == 1:
            gains = data['data']['gains']
            avgi = data['data']['avgi'][0][0]
            avgq = data['data']['avgq'][0][0]
            mag = np.abs(avgi + 1j * avgq)

            def rabi_fit(x, A, pi_amp, phi, y0):
                return A * np.sin(np.pi * x / pi_amp + phi)**2 + y0

            try:
                p0 = [np.ptp(mag)/2, self.cfg['pi_amplitude'], 0, np.min(mag)]
                popt, _ = curve_fit(rabi_fit, gains, mag, p0=p0, maxfev=5000)
                
                data['data']['pi_amplitude'] = popt[1]
                data['data']['fit_params'] = {
                    'A': popt[0], 'pi_amp': popt[1], 'phi': popt[2], 'y0': popt[3]
                }
                print(f"[MockAmplitudeRabi] π amp = {popt[1]:.0f} (true = {self.cfg['pi_amplitude']:.0f})")
            except Exception as e:
                print(f"[MockAmplitudeRabi] Fit failed: {e}")

        return data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        """Plot Rabi results."""
        if data is None:
            data = self.data

        gains = data['data']['gains']
        freqs = data['data']['freqs']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']

        while plt.fignum_exists(num=figNum):
            figNum += 1

        if len(freqs) == 1:
            avgi = avgi[0][0]
            avgq = avgq[0][0]
            mag = np.abs(avgi + 1j * avgq)
            phase = np.angle(avgi + 1j * avgq, deg=True)

            fig, axs = plt.subplots(4, 1, figsize=(10, 10), num=figNum)

            axs[0].plot(gains, phase, 'o-', color='purple', markersize=3)
            axs[0].set_ylabel("Phase (deg)")
            axs[0].set_title("Mock Amplitude Rabi")
            axs[0].grid(True, alpha=0.3)

            axs[1].plot(gains, mag, 'o-', color='blue', markersize=3, label='Data')
            if 'fit_params' in data['data']:
                fp = data['data']['fit_params']
                g_fine = np.linspace(gains[0], gains[-1], 200)
                fit = fp['A'] * np.sin(np.pi * g_fine / fp['pi_amp'] + fp['phi'])**2 + fp['y0']
                axs[1].plot(g_fine, fit, '--', color='black', linewidth=2,
                           label=f"π = {fp['pi_amp']:.0f}")
                axs[1].legend()
            axs[1].set_ylabel("Magnitude (a.u.)")
            axs[1].grid(True, alpha=0.3)

            axs[2].plot(gains, avgi, 'o-', color='orange', markersize=3)
            axs[2].set_ylabel("I (a.u.)")
            axs[2].grid(True, alpha=0.3)

            axs[3].plot(gains, avgq, 'o-', color='green', markersize=3)
            axs[3].set_ylabel("Q (a.u.)")
            axs[3].set_xlabel("Qubit Gain (DAC units)")
            axs[3].grid(True, alpha=0.3)
        else:
            fig, axs = plt.subplots(2, 2, figsize=(12, 10), num=figNum)
            
            mag = np.abs(avgi[0] + 1j * avgq[0])
            
            im0 = axs[0, 0].pcolormesh(gains, freqs, avgi[0], shading='auto', cmap='RdBu_r')
            axs[0, 0].set_xlabel("Gain (DAC)")
            axs[0, 0].set_ylabel("Frequency (MHz)")
            axs[0, 0].set_title("I")
            plt.colorbar(im0, ax=axs[0, 0])

            im1 = axs[0, 1].pcolormesh(gains, freqs, avgq[0], shading='auto', cmap='RdBu_r')
            axs[0, 1].set_xlabel("Gain (DAC)")
            axs[0, 1].set_ylabel("Frequency (MHz)")
            axs[0, 1].set_title("Q")
            plt.colorbar(im1, ax=axs[0, 1])

            im2 = axs[1, 0].pcolormesh(gains, freqs, mag, shading='auto', cmap='viridis')
            axs[1, 0].set_xlabel("Gain (DAC)")
            axs[1, 0].set_ylabel("Frequency (MHz)")
            axs[1, 0].set_title("Magnitude")
            plt.colorbar(im2, ax=axs[1, 0])

            axs[1, 1].axis('off')
            
            fig.suptitle("Mock 2D Amplitude Rabi", fontsize=12)

        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)
        else:
            plt.close(fig)

        return fig, axs

    def save_data(self, data=None):
        if data is None:
            data = self.data
        print(f"[MockAmplitudeRabi] Saving to {self.fname}")
        super().save_data(data=data.get('data', data))


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    print("Testing MockAmplitudeRabiExperiment...")
    exp = MockAmplitudeRabiExperiment(path='test', prefix='rabi')
    data = exp.acquire()
    exp.analyze(data)
    exp.display(data, plotDisp=True, block=True)
