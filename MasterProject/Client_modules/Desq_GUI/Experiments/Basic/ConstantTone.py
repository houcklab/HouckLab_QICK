"""
================================================================================
ConstantTone.py - Constant Tone Output
================================================================================

Outputs a continuous tone at a specified frequency and amplitude.
Useful for:
- Calibrating with a spectrum analyzer
- Finding the resonator with VNA
- Testing DAC output levels

USAGE:
------
    from ConstantToneExperiment import ConstantToneExperiment
    
    cfg = {"freq": 5000, "gain": 10000, "channel": 0, "nqz": 1}
    exp = ConstantToneExperiment(cfg=cfg, soc=soc, soccfg=soccfg)
    exp.acquire()  # Starts tone output
    # Use Ctrl+C to stop

================================================================================
"""

import numpy as np
import matplotlib.pyplot as plt

# QICK imports
try:
    from qick import AveragerProgram
    QICK_AVAILABLE = True
except ImportError:
    QICK_AVAILABLE = False
    class AveragerProgram:
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

class ConstantToneProgram(AveragerProgram):
    """
    Outputs a constant tone.
    
    Uses a very long const pulse that continuously outputs.
    """

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        # Declare generator
        self.declare_gen(ch=cfg["channel"], nqz=cfg["nqz"])

        # Declare minimal readout (required)
        ro_ch = cfg.get("ro_chs", [0])[0]
        self.declare_readout(ch=ro_ch, length=100, freq=cfg["freq"], gen_ch=cfg["channel"])

        # Convert frequency
        freq_reg = self.freq2reg(cfg["freq"], gen_ch=cfg["channel"])

        # Setup continuous pulse (max length)
        self.set_pulse_registers(
            ch=cfg["channel"],
            style="const",
            freq=freq_reg,
            phase=0,
            gain=cfg["gain"],
            length=self.us2cycles(1000)  # 1ms pulse, repeated
        )

        self.sync_all(self.us2cycles(1))

    def body(self):
        # Play pulse
        self.pulse(ch=self.cfg["channel"])
        self.sync_all(self.us2cycles(1000))


# =============================================================================
# EXPERIMENT CLASS
# =============================================================================

class ConstantToneExperiment(ExperimentClass):
    """
    Constant Tone Output

    Outputs a continuous tone for calibration or testing purposes.
    Calculates expected power and voltage based on DAC parameters.
    """

    # =========================================================================
    # CONFIGURATION TEMPLATE (Experiment-Specific Parameters Only)
    # =========================================================================

    config_template = {
        # --- Tone Parameters ---
        "gain": 10000,                    # Output amplitude [DAC units]
        "freq": 5000,                     # Output frequency [MHz]
        "channel": 1,                     # DAC channel to output on
        "nqz": 1,                         # Nyquist zone for output channel
    }

    def __init__(self, path='', outerFolder='', prefix='data',
                 soc=None, soccfg=None, cfg=None, config_file=None, **kwargs):
        super().__init__(
            path=path, outerFolder=outerFolder, prefix=prefix,
            soc=soc, soccfg=soccfg, cfg=cfg, config_file=config_file, **kwargs
        )

    def acquire(self, progress=False, debug=False):
        """
        Start continuous tone output.
        
        Note: This runs indefinitely. Use Ctrl+C to stop.
        """
        # Add required config fields
        self.cfg["reps"] = 1
        self.cfg["ro_chs"] = self.cfg.get("ro_chs", [0])
        
        print(f"[ConstantTone] Starting tone: {self.cfg['freq']} MHz, "
              f"gain={self.cfg['gain']}, ch={self.cfg['channel']}")
        
        # Calculate expected output
        self._calculate_output()

        prog = ConstantToneProgram(self.soccfg, self.cfg)
        
        try:
            # Run continuously
            while True:
                prog.acquire(self.soc, load_pulses=True, progress=False)
        except KeyboardInterrupt:
            print("\n[ConstantTone] Stopped by user")

        data = {
            'config': self.cfg,
            'data': {
                'freq': self.cfg['freq'],
                'gain': self.cfg['gain'],
                'channel': self.cfg['channel'],
            }
        }
        self.data = data
        return data

    def _calculate_output(self):
        """Calculate expected output power and voltage."""
        gain = self.cfg['gain']
        
        # DAC full scale is typically 32767 (15-bit signed)
        dac_fs = 32767
        
        # Typical full-scale voltage is ~0.7 Vpp
        v_fs = 0.7  # Volts peak-to-peak
        
        # Calculate voltage
        v_pp = v_fs * (gain / dac_fs)
        v_rms = v_pp / (2 * np.sqrt(2))
        
        # Calculate power into 50 ohms
        p_watts = v_rms**2 / 50
        p_dbm = 10 * np.log10(p_watts * 1000)
        
        self.cfg['expected_v_pp'] = v_pp
        self.cfg['expected_v_rms'] = v_rms
        self.cfg['expected_power_dbm'] = p_dbm
        
        print(f"[ConstantTone] Expected output:")
        print(f"  Vpp  = {v_pp*1000:.1f} mV")
        print(f"  Vrms = {v_rms*1000:.2f} mV")
        print(f"  Power = {p_dbm:.1f} dBm (into 50Ω)")

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        """Display tone parameters and expected waveform."""
        if data is None:
            data = self.data if hasattr(self, 'data') else {'config': self.cfg, 'data': {}}

        cfg = data['config']
        
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(2, 1, figsize=(10, 6), num=figNum)

        # Time axis (show 2 periods)
        freq_mhz = cfg['freq']
        period_us = 1.0 / freq_mhz
        t = np.linspace(0, 4 * period_us, 1000)

        # Waveform
        gain = cfg['gain']
        dac_fs = 32767
        v_fs = 0.7
        v_pp = v_fs * (gain / dac_fs)
        amplitude = v_pp / 2
        
        waveform = amplitude * np.sin(2 * np.pi * freq_mhz * t)
        
        axs[0].plot(t * 1000, waveform * 1000, 'b-', linewidth=1.5)
        axs[0].set_xlabel("Time (ns)")
        axs[0].set_ylabel("Voltage (mV)")
        axs[0].set_title(f"Constant Tone: {freq_mhz} MHz, Gain={gain}")
        axs[0].grid(True, alpha=0.3)
        axs[0].axhline(0, color='k', linestyle='-', linewidth=0.5)

        # Parameters text
        axs[1].axis('off')
        
        params_text = f"""
        Frequency: {freq_mhz} MHz
        DAC Channel: {cfg['channel']}
        Nyquist Zone: {cfg['nqz']}
        
        Gain: {gain} / 32767 DAC units
        
        Expected Output (into 50Ω):
          Vpp  = {v_pp*1000:.1f} mV
          Vrms = {v_pp/(2*np.sqrt(2))*1000:.2f} mV
          Power = {cfg.get('expected_power_dbm', 'N/A'):.1f} dBm
        """
        
        axs[1].text(0.1, 0.5, params_text, transform=axs[1].transAxes,
                   fontsize=12, verticalalignment='center', fontfamily='monospace',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)
        else:
            plt.close(fig)

        return fig, axs

    def save_data(self, data=None):
        if data is None:
            data = self.data
        print(f"[ConstantToneExperiment] Saving to {self.fname}")
        super().save_data(data=data['data'])


# =============================================================================
# MOCK VERSION FOR TESTING
# =============================================================================

class MockConstantToneExperiment(ExperimentClass):
    """
    Mock Constant Tone Experiment - Calculates expected output without hardware.
    """

    config_template = {
        "gain": 10000,
        "freq": 5000,
        "channel": 1,
        "nqz": 1,
    }

    def __init__(self, path='', outerFolder='', prefix='data', cfg=None, **kwargs):
        default_cfg = self.config_template.copy()
        if cfg:
            default_cfg.update(cfg)
        super().__init__(path=path, outerFolder=outerFolder, prefix=prefix,
                         cfg=default_cfg, **kwargs)

    def acquire(self, progress=False, debug=False):
        """Calculate expected tone output."""
        cfg = self.cfg
        gain = cfg['gain']
        
        dac_fs = 32767
        v_fs = 0.7
        
        v_pp = v_fs * (gain / dac_fs)
        v_rms = v_pp / (2 * np.sqrt(2))
        p_watts = v_rms**2 / 50
        p_dbm = 10 * np.log10(p_watts * 1000)

        data = {
            'config': cfg,
            'data': {
                'freq': cfg['freq'],
                'gain': cfg['gain'],
                'channel': cfg['channel'],
                'expected_v_pp': v_pp,
                'expected_v_rms': v_rms,
                'expected_power_dbm': p_dbm,
            }
        }
        
        cfg['expected_v_pp'] = v_pp
        cfg['expected_v_rms'] = v_rms
        cfg['expected_power_dbm'] = p_dbm
        
        print(f"[MockConstantTone] {cfg['freq']} MHz @ gain={gain}")
        print(f"  Vpp = {v_pp*1000:.1f} mV, Power = {p_dbm:.1f} dBm")

        self.data = data
        return data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        """Display tone parameters."""
        if data is None:
            data = self.data

        cfg = data['config']
        
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(2, 1, figsize=(10, 6), num=figNum)

        # Waveform
        freq_mhz = cfg['freq']
        period_us = 1.0 / freq_mhz
        t = np.linspace(0, 4 * period_us, 1000)

        gain = cfg['gain']
        dac_fs = 32767
        v_fs = 0.7
        v_pp = v_fs * (gain / dac_fs)
        amplitude = v_pp / 2
        
        waveform = amplitude * np.sin(2 * np.pi * freq_mhz * t)
        
        axs[0].plot(t * 1000, waveform * 1000, 'b-', linewidth=1.5)
        axs[0].set_xlabel("Time (ns)")
        axs[0].set_ylabel("Voltage (mV)")
        axs[0].set_title(f"Mock Constant Tone: {freq_mhz} MHz, Gain={gain}")
        axs[0].grid(True, alpha=0.3)

        # Parameters
        axs[1].axis('off')
        
        p_dbm = cfg.get('expected_power_dbm', 10 * np.log10((v_pp/(2*np.sqrt(2)))**2 / 50 * 1000))
        
        params_text = f"""
        Frequency: {freq_mhz} MHz
        Channel: {cfg['channel']}
        Nyquist Zone: {cfg['nqz']}
        Gain: {gain} DAC units
        
        Expected Output:
          Vpp = {v_pp*1000:.1f} mV
          Power = {p_dbm:.1f} dBm
        """
        
        axs[1].text(0.1, 0.5, params_text, transform=axs[1].transAxes,
                   fontsize=12, verticalalignment='center', fontfamily='monospace',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)
        else:
            plt.close(fig)

        return fig, axs

    def save_data(self, data=None):
        if data is None:
            data = self.data
        print(f"[MockConstantTone] Saving to {self.fname}")
        super().save_data(data=data.get('data', data))


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    print("Testing MockConstantToneExperiment...")
    exp = MockConstantToneExperiment(path='test', prefix='tone')
    data = exp.acquire()
    exp.display(data, plotDisp=True, block=True)
