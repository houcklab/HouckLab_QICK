"""
================================================================================
mSpecSlice.py - Qubit Spectroscopy (Two-Tone)
================================================================================

Performs two-tone spectroscopy to find the qubit frequency:
1. Apply a spectroscopy tone at variable frequency
2. Immediately measure the resonator response
3. Look for dispersive shift indicating qubit excitation

USAGE:
------
    from StarterPackConfig import BaseConfig, make_config
    from SpecSliceExperiment import SpecSliceExperiment
    
    exp_cfg = {"qubit_freq_start": 4450, "qubit_freq_stop": 4550, "qubit_freq_expts": 101}
    full_cfg = make_config(exp_cfg, qubit_id='1')
    
    exp = SpecSliceExperiment(path='Spec', cfg=full_cfg, soc=soc, soccfg=soccfg)
    data = exp.acquire()
    exp.display(data)

================================================================================
"""

import numpy as np
import matplotlib.pyplot as plt

# QICK imports
try:
    from qick import RAveragerProgram
    QICK_AVAILABLE = True
except ImportError:
    QICK_AVAILABLE = False
    class RAveragerProgram:
        pass

# Base experiment class
from MasterProject.Client_modules.Desq_GUI.CoreLib.Experiment import ExperimentClass


# =============================================================================
# QICK PROGRAM
# =============================================================================

class SpecSliceProgram(RAveragerProgram):
    """
    Two-tone spectroscopy pulse sequence.

    Sequence: spectroscopy pulse (variable freq) → readout
    Sweep: qubit drive frequency
    """

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        # Frequency sweep setup
        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_freq = self.sreg(cfg["qubit_ch"], "freq")

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
        
        # Calculate frequency step
        self.f_start = self.freq2reg(cfg["qubit_freq_start"], gen_ch=cfg["qubit_ch"])
        self.f_stop = self.freq2reg(cfg["qubit_freq_stop"], gen_ch=cfg["qubit_ch"])
        self.f_step = (self.f_stop - self.f_start) // (cfg["qubit_freq_expts"] - 1)

        # Setup qubit pulse
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
                freq=self.f_start,
                phase=0,
                gain=cfg["qubit_gain"],
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
                freq=self.f_start,
                phase=0,
                gain=cfg["qubit_gain"],
                waveform="qubit",
                length=self.us2cycles(cfg["flat_top_length"])
            )
        else:  # const
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style="const",
                freq=self.f_start,
                phase=0,
                gain=cfg["qubit_gain"],
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
        # Play spectroscopy pulse
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
        # Step frequency
        self.mathi(self.q_rp, self.r_freq, self.r_freq, '+', self.f_step)


# =============================================================================
# EXPERIMENT CLASS
# =============================================================================

class SpecSliceExperiment(ExperimentClass):
    """
    Qubit Spectroscopy (Two-Tone Measurement)

    Sweeps the qubit drive frequency while monitoring the resonator response.
    The qubit transition appears as a dispersive shift in the resonator.
    """

    # =========================================================================
    # CONFIGURATION TEMPLATE (Experiment-Specific Parameters Only)
    # =========================================================================

    config_template = {
        # --- Spectroscopy Sweep Parameters ---
        "qubit_freq_start": 4450,         # Start frequency [MHz]
        "qubit_freq_stop": 4550,          # Stop frequency [MHz]
        "qubit_freq_expts": 81,           # Number of points
        
        # --- Spectroscopy Pulse Parameters ---
        "qubit_pulse_style": "flat_top",  # "arb", "flat_top", or "const"
        "flat_top_length": 0.500,         # Flat top duration [µs]
        "qubit_length": 1.0,              # Const pulse length [µs] (if const style)
        "qubit_gain": 20000,              # Spectroscopy pulse amplitude [DAC units]
    }

    def __init__(self, path='', outerFolder='', prefix='data',
                 soc=None, soccfg=None, cfg=None, config_file=None, **kwargs):
        super().__init__(
            path=path, outerFolder=outerFolder, prefix=prefix,
            soc=soc, soccfg=soccfg, cfg=cfg, config_file=config_file, **kwargs
        )

    def acquire(self, progress=False, debug=False):
        """Run spectroscopy measurement."""
        # Set up expts for RAveragerProgram
        self.cfg["expts"] = self.cfg["qubit_freq_expts"]
        
        prog = SpecSliceProgram(self.soccfg, self.cfg)
        x_pts, avgi, avgq = prog.acquire(
            self.soc, threshold=None, angle=None, load_pulses=True,
            readouts_per_experiment=1, save_experiments=None,
            start_src="internal", progress=progress
        )

        # Create frequency axis
        freqs = np.linspace(
            self.cfg["qubit_freq_start"],
            self.cfg["qubit_freq_stop"],
            self.cfg["qubit_freq_expts"]
        )

        data = {
            'config': self.cfg,
            'data': {
                'freqs': freqs,
                'avgi': avgi,
                'avgq': avgq,
            }
        }
        self.data = data

        # Find peak
        mag = np.abs(avgi[0][0] + 1j * avgq[0][0])
        peak_idx = np.argmax(mag)
        data['data']['qubit_freq'] = freqs[peak_idx]
        print(f"[SpecSlice] Peak at {freqs[peak_idx]:.3f} MHz")

        return data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        """Plot spectroscopy results."""
        if data is None:
            data = self.data

        freqs = data['data']['freqs']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]
        mag = np.abs(avgi + 1j * avgq)
        phase = np.angle(avgi + 1j * avgq, deg=True)

        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(4, 1, figsize=(10, 10), num=figNum)

        axs[0].plot(freqs, phase, 'o-', color='purple', markersize=4)
        axs[0].set_ylabel("Phase (deg)")
        axs[0].set_title("Qubit Spectroscopy")
        axs[0].grid(True, alpha=0.3)

        axs[1].plot(freqs, mag, 'o-', color='blue', markersize=4)
        if 'qubit_freq' in data['data']:
            axs[1].axvline(data['data']['qubit_freq'], color='red', linestyle='--',
                          label=f"Peak: {data['data']['qubit_freq']:.3f} MHz")
            axs[1].legend()
        axs[1].set_ylabel("Magnitude (a.u.)")
        axs[1].grid(True, alpha=0.3)

        axs[2].plot(freqs, avgi, 'o-', color='orange', markersize=4)
        axs[2].set_ylabel("I (a.u.)")
        axs[2].grid(True, alpha=0.3)

        axs[3].plot(freqs, avgq, 'o-', color='green', markersize=4)
        axs[3].set_ylabel("Q (a.u.)")
        axs[3].set_xlabel("Frequency (MHz)")
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
        print(f"[SpecSliceExperiment] Saving to {self.fname}")
        super().save_data(data=data['data'])


# =============================================================================
# MOCK VERSION FOR TESTING
# =============================================================================

class MockSpecSliceExperiment(ExperimentClass):
    """
    Mock Spectroscopy Experiment - Generates simulated Lorentzian peak without hardware.
    """

    config_template = {
        # --- Spectroscopy Sweep Parameters ---
        "qubit_freq_start": 4450,
        "qubit_freq_stop": 4550,
        "qubit_freq_expts": 81,
        "qubit_pulse_style": "flat_top",
        "flat_top_length": 0.500,
        "qubit_length": 1.0,
        "qubit_gain": 20000,
        
        # --- Mock Simulation Parameters ---
        "qubit_freq_true": 4500.0,        # Simulated qubit frequency [MHz]
        "linewidth": 5.0,                 # Peak linewidth [MHz]
        "noise_level": 0.05,
    }

    def __init__(self, path='', outerFolder='', prefix='data', cfg=None, **kwargs):
        default_cfg = self.config_template.copy()
        if cfg:
            default_cfg.update(cfg)
        super().__init__(path=path, outerFolder=outerFolder, prefix=prefix,
                         cfg=default_cfg, **kwargs)

    def acquire(self, progress=False, debug=False):
        """Generate simulated Lorentzian peak data."""
        cfg = self.cfg
        freqs = np.linspace(cfg['qubit_freq_start'], cfg['qubit_freq_stop'],
                           cfg['qubit_freq_expts'])

        f0 = cfg['qubit_freq_true']
        gamma = cfg['linewidth']

        # Lorentzian in magnitude
        lorentzian = gamma**2 / ((freqs - f0)**2 + gamma**2)
        noise_i = cfg['noise_level'] * np.random.randn(len(freqs))
        noise_q = cfg['noise_level'] * np.random.randn(len(freqs))

        avgi = lorentzian + noise_i
        avgq = 0.3 * lorentzian + noise_q

        data = {
            'config': cfg,
            'data': {
                'freqs': freqs,
                'avgi': [[avgi]],
                'avgq': [[avgq]],
            }
        }
        self.data = data

        # Find peak
        mag = np.abs(avgi + 1j * avgq)
        peak_idx = np.argmax(mag)
        data['data']['qubit_freq'] = freqs[peak_idx]
        print(f"[MockSpecSlice] Peak at {freqs[peak_idx]:.3f} MHz (true = {f0:.3f} MHz)")

        return data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        """Plot spectroscopy results."""
        if data is None:
            data = self.data

        freqs = data['data']['freqs']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]
        mag = np.abs(avgi + 1j * avgq)
        phase = np.angle(avgi + 1j * avgq, deg=True)

        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(4, 1, figsize=(10, 10), num=figNum)

        axs[0].plot(freqs, phase, 'o-', color='purple', markersize=3)
        axs[0].set_ylabel("Phase (deg)")
        axs[0].set_title("Mock Qubit Spectroscopy")
        axs[0].grid(True, alpha=0.3)

        axs[1].plot(freqs, mag, 'o-', color='blue', markersize=3)
        if 'qubit_freq' in data['data']:
            axs[1].axvline(data['data']['qubit_freq'], color='red', linestyle='--',
                          label=f"Peak: {data['data']['qubit_freq']:.3f} MHz")
            axs[1].legend()
        axs[1].set_ylabel("Magnitude (a.u.)")
        axs[1].grid(True, alpha=0.3)

        axs[2].plot(freqs, avgi, 'o-', color='orange', markersize=3)
        axs[2].set_ylabel("I (a.u.)")
        axs[2].grid(True, alpha=0.3)

        axs[3].plot(freqs, avgq, 'o-', color='green', markersize=3)
        axs[3].set_ylabel("Q (a.u.)")
        axs[3].set_xlabel("Frequency (MHz)")
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
        print(f"[MockSpecSlice] Saving to {self.fname}")
        super().save_data(data=data.get('data', data))


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    print("Testing MockSpecSliceExperiment...")
    exp = MockSpecSliceExperiment(path='test', prefix='spec')
    data = exp.acquire()
    exp.display(data, plotDisp=True, block=True)
