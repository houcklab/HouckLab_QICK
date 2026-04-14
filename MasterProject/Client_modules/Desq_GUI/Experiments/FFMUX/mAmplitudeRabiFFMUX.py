"""
================================================================================
mAmplitudeRabiFFMUX.py - Amplitude Rabi with Fast Flux and MUX Readout
================================================================================

Calibrates π pulse amplitude by sweeping drive amplitude:
- Fast flux biasing during pulse and readout
- Multiplexed readout capability
- Automatic π pulse amplitude fitting

SEQUENCE:
---------
    FFPulse ON → qubit pulse (swept gain) → FFReadout ON → readout → FF OFF

USAGE:
------
    from StarterPackConfigFFMUX import make_config
    from mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX
    
    cfg = make_config({"max_gain": 30000, "expts": 61}, qubit_indices=[5])
    exp = AmplitudeRabiFFMUX(soc=soc, soccfg=soccfg, cfg=cfg, path='Rabi')
    data = exp.acquire(progress=True)
    exp.display(data)

================================================================================
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

try:
    from qick.asm_v2 import QickSweep1D
    QICK_AVAILABLE = True
except ImportError:
    QICK_AVAILABLE = False
    class QickSweep1D:
        def __init__(self, name, start, end):
            self.name, self.start, self.end = name, start, end

from MasterProject.Client_modules.Desq_GUI.Experiments.FFMUX.FFAveragerProgram import FFAveragerProgramV2
from MasterProject.Client_modules.Desq_GUI.Experiments.FFMUX import FF_utils as FF
from MasterProject.Client_modules.Desq_GUI.CoreLib.Experiment import ExperimentClass
from MasterProject.Client_modules.Desq_GUI.Experiments.FFMUX.BaseConfigFFMUX import IQ_contrast

def frequency_guess(x, y):
    """Estimate oscillation frequency from FFT."""
    from scipy.fft import fft, fftfreq
    y_centered = y - np.mean(y)
    yf = np.abs(fft(y_centered))
    xf = fftfreq(len(x), x[1] - x[0])
    return np.abs(xf[np.argmax(yf[:len(yf)//2])])


def fit_func_simple(gain, ampl, pi_gain):
    """Simple cosine fit for Rabi oscillations."""
    return ampl * np.cos(gain * np.pi / pi_gain)


def rabi_fit_func(gain, A, pi_gain, offset, phi):
    """Full Rabi fit with offset and phase."""
    return offset + A * np.cos(np.pi * gain / pi_gain + phi)


# =============================================================================
# QICK PROGRAM
# =============================================================================

class AmplitudeRabiFFProg(FFAveragerProgramV2):
    """Amplitude Rabi pulse sequence with FF support."""
    
    def _initialize(self, cfg):
        # Declare qubit generator
        self.declare_gen(
            ch=cfg["qubit_ch"],
            nqz=cfg["qubit_nqz"],
            mixer_freq=cfg["qubit_mixer_freq"]
        )
        
        # Declare MUX readout generator
        self.declare_gen(
            ch=cfg["res_ch"],
            nqz=cfg["res_nqz"],
            mixer_freq=cfg["mixer_freq"],
            mux_freqs=cfg["res_freqs"],
            mux_gains=cfg["res_gains"],
            ro_ch=cfg["ro_chs"][0]
        )
        
        for iCh, ch in enumerate(cfg["ro_chs"]):
            self.declare_readout(
                ch=ch,
                length=cfg["readout_lengths"][iCh],
                freq=cfg["res_freqs"][iCh],
                gen_ch=cfg["res_ch"]
            )
        
        self.add_pulse(
            ch=cfg["res_ch"],
            name="res_drive",
            style="const",
            mask=cfg["ro_chs"],
            length=cfg["res_length"]
        )
        
        # Initialize fast flux
        FF.FFDefinitions(self)
        
        # Set up gain sweep
        self.add_loop("qubit_gain_loop", cfg["expts"])
        qubit_gain_sweep = QickSweep1D(
            "qubit_gain_loop",
            start=0,
            end=cfg["max_gain"] / 32766.0  # Normalize to [-1, 1]
        )
        
        # Add Gaussian qubit pulse with swept gain
        self.add_gauss(
            ch=cfg["qubit_ch"],
            name="qubit",
            sigma=cfg["sigma"],
            length=4 * cfg["sigma"]
        )
        self.add_pulse(
            ch=cfg["qubit_ch"],
            name='qubit_drive',
            style="arb",
            envelope="qubit",
            freq=cfg["qubit_freqs"][-1],
            phase=90,
            gain=qubit_gain_sweep
        )
        
        self.qubit_length_us = cfg["sigma"] * 4
        self.delay_auto(0.05)
    
    def _body(self, cfg):
        # FF during qubit pulse
        self.FFPulses(self.FFPulse, cfg["sigma"] * 4 + 1)
        
        # Play qubit pulse (with swept gain)
        self.pulse(ch=cfg["qubit_ch"], name="qubit_drive", t=1)
        self.delay_auto()
        
        # Readout
        self.FFPulses(self.FFReadouts, cfg["res_length"])
        for ro_ch, adc_trig_delay in zip(cfg["ro_chs"], cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0], t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)
        
        # Undo FF
        self.FFPulses(-1 * self.FFReadouts, cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, cfg["sigma"] * 4 + 1)


# =============================================================================
# EXPERIMENT CLASS
# =============================================================================

class AmplitudeRabiFFMUX(ExperimentClass):
    """Amplitude Rabi Calibration with FF/MUX support."""
    
    config_template = {
        "max_gain": 30000,                # Maximum gain to sweep to [DAC units]
        "expts": 61,                      # Number of amplitude points
    }
    
    def __init__(self, soc=None, soccfg=None, path='', outerFolder='',
                 prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(
            soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
            prefix=prefix, cfg=cfg, config_file=config_file, progress=progress
        )
    
    def acquire(self, progress=False):
        # Set defaults
        cfg_defaults = {
            'start': 0,
            'expts': 31,
            'reps': 30,
            'rounds': 30,
            'f_ge': self.cfg["qubit_freqs"][-1]
        }
        self.cfg = cfg_defaults | self.cfg
        self.cfg['step'] = int(self.cfg["max_gain"] / self.cfg['expts'])
        
        prog = AmplitudeRabiFFProg(
            self.soccfg,
            cfg=self.cfg,
            reps=self.cfg["reps"],
            final_delay=self.cfg["relax_delay"],
            initial_delay=10.0
        )
        
        iq_list = prog.acquire(
            self.soc,
            load_envelopes=True,
            rounds=self.cfg.get('rounds', 1),
            progress=progress
        )
        
        avgi, avgq = iq_list[0][0, :, 0], iq_list[0][0, :, 1]
        x_pts = prog.get_pulse_param("qubit_drive", "gain", as_array=True) * 32766
        
        data = {
            'config': self.cfg,
            'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}
        }
        self.data = data
        self.analyze(data)
        return data
    
    def analyze(self, data=None, **kwargs):
        if data is None:
            data = self.data
        
        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']
        contrast = IQ_contrast(avgi, avgq)
        
        # Simple fit
        try:
            gain_guess = 1 / frequency_guess(x_pts, contrast) / 2
            popt, _ = curve_fit(fit_func_simple, x_pts, contrast, 
                               p0=[np.max(contrast), gain_guess])
            self.ampl_fit_simple = popt[0]
            self.pi_gain_fit_simple = np.abs(popt[1])
        except:
            print("[AmplitudeRabi] Simple fit failed")
        
        # Complex fit with offset and phase
        try:
            pi_gain_guess = 1 / frequency_guess(x_pts, contrast) / 2
            A_guess = 0.5 * (np.max(contrast) - np.min(contrast))
            offset_guess = np.mean(contrast)
            
            mask = x_pts <= 2 * pi_gain_guess
            x_fit, y_fit = x_pts[mask], contrast[mask]
            
            popt, _ = curve_fit(
                rabi_fit_func, x_fit, y_fit,
                p0=[A_guess, pi_gain_guess, offset_guess, 0.0],
                bounds=([0, 0.5*pi_gain_guess, -np.inf, -np.pi],
                       [np.inf, 2*pi_gain_guess, np.inf, np.pi])
            )
            
            self.ampl_fit_complex = popt[0]
            self.pi_gain_fit_complex = np.abs(popt[1])
            self.offset_fit_complex = popt[2]
            self.phi_fit_complex = popt[3]
            
            # Check fit quality
            resid = y_fit - rabi_fit_func(x_fit, *popt)
            R2 = 1 - np.var(resid) / np.var(y_fit)
            
            if R2 < 0.8 and hasattr(self, 'pi_gain_fit_simple'):
                print("[AmplitudeRabi] Complex fit poor, using simple fit")
                self.pi_gain_fit = self.pi_gain_fit_simple
            else:
                self.pi_gain_fit = self.pi_gain_fit_complex
                
        except Exception as e:
            print(f"[AmplitudeRabi] Complex fit failed: {e}")
            if hasattr(self, 'pi_gain_fit_simple'):
                self.pi_gain_fit = self.pi_gain_fit_simple
        
        if hasattr(self, 'pi_gain_fit'):
            data['data']['pi_gain_fit'] = self.pi_gain_fit
            print(f"[AmplitudeRabi] π gain = {self.pi_gain_fit:.0f} DAC units")
        
        return data
    
    def display(self, data=None, plotDisp=False, figNum=1, block=True, ax=None, **kwargs):
        if data is None:
            data = self.data
        
        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']
        contrast = IQ_contrast(avgi, avgq)
        
        while plt.fignum_exists(num=figNum):
            figNum += 1
        
        if ax is None:
            plt.figure(figNum)
            ax = plt.gca()
        
        ax.plot(x_pts, contrast, 'o-', color='seagreen', label='IQ contrast')
        ax.plot(x_pts, avgi - np.mean(avgi), 'o-', color='orange', alpha=0.5, label='I')
        ax.plot(x_pts, avgq - np.mean(avgq), 'o-', color='blue', alpha=0.5, label='Q')
        
        # Plot fit
        if 'pi_gain_fit' in data['data']:
            pi_gain = data['data']['pi_gain_fit']
            gains = np.linspace(x_pts[0], x_pts[-1], 200)
            
            if hasattr(self, 'pi_gain_fit_complex') and self.pi_gain_fit_complex == self.pi_gain_fit:
                fit_curve = rabi_fit_func(gains, self.ampl_fit_complex, pi_gain,
                                         self.offset_fit_complex, self.phi_fit_complex)
                ax.plot(gains, fit_curve, '--', color='black')
            elif hasattr(self, 'pi_gain_fit_simple'):
                fit_curve = fit_func_simple(gains, self.ampl_fit_simple, pi_gain)
                ax.plot(gains, fit_curve, '--', color='black')
            
            ax.axvline(pi_gain, color='red', linestyle='--', label=f'π = {int(pi_gain)}')
        
        ax.set_xlabel("Qubit Gain (DAC units)")
        ax.set_ylabel("Signal (a.u.)")
        ax.set_title(self.titlename)
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        if plotDisp:
            plt.show(block=block)
        
        return plt.gcf(), ax
    
    def save_data(self, data=None):
        if data is None:
            data = self.data
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


# =============================================================================
# MOCK VERSION
# =============================================================================

class MockAmplitudeRabiFFMUX(ExperimentClass):
    """Mock Amplitude Rabi for testing."""
    
    config_template = {
        "max_gain": 30000,
        "expts": 61,
        "pi_amplitude": 15000,
        "noise_level": 0.05,
    }
    
    def __init__(self, path='', outerFolder='', prefix='data', cfg=None, **kwargs):
        super().__init__(path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, **kwargs)
    
    def acquire(self, progress=False):
        cfg = self.cfg
        x_pts = np.linspace(0, cfg.get('max_gain', 30000), cfg.get('expts', 61))
        
        pi_amp = cfg.get('pi_amplitude', 15000)
        rabi = np.sin(np.pi * x_pts / pi_amp)**2
        
        avgi = rabi + cfg.get('noise_level', 0.05) * np.random.randn(len(x_pts))
        avgq = 0.2 * rabi + cfg.get('noise_level', 0.05) * np.random.randn(len(x_pts))
        
        data = {'config': cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data
        self.analyze(data)
        return data
    
    def analyze(self, data=None, **kwargs):
        if data is None:
            data = self.data
        
        x_pts = data['data']['x_pts']
        contrast = IQ_contrast(data['data']['avgi'], data['data']['avgq'])
        
        try:
            gain_guess = 1 / frequency_guess(x_pts, contrast) / 2
            popt, _ = curve_fit(fit_func_simple, x_pts, contrast, 
                               p0=[np.ptp(contrast)/2, gain_guess])
            self.pi_gain_fit = np.abs(popt[1])
            data['data']['pi_gain_fit'] = self.pi_gain_fit
            print(f"[MockRabi] π = {self.pi_gain_fit:.0f} (true = {self.cfg.get('pi_amplitude', 15000):.0f})")
        except:
            pass
        return data
    
    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data
        
        x_pts = data['data']['x_pts']
        contrast = IQ_contrast(data['data']['avgi'], data['data']['avgq'])
        
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot(x_pts, contrast, 'o-', color='blue', label='Data')
        
        if 'pi_gain_fit' in data['data']:
            pi_gain = data['data']['pi_gain_fit']
            gains = np.linspace(x_pts[0], x_pts[-1], 200)
            ax.plot(gains, fit_func_simple(gains, np.ptp(contrast)/2, pi_gain), '--', color='black')
            ax.axvline(pi_gain, color='red', linestyle='--', label=f'π = {int(pi_gain)}')
        
        ax.set_xlabel("Qubit Gain (DAC units)")
        ax.set_ylabel("Contrast")
        ax.set_title("Mock Amplitude Rabi (FFMUX)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        if plotDisp:
            plt.show(block=block)
        return fig, ax


if __name__ == '__main__':
    print("Testing MockAmplitudeRabiFFMUX...")
    exp = MockAmplitudeRabiFFMUX(cfg={"max_gain": 30000, "expts": 51, "pi_amplitude": 12000})
    data = exp.acquire()
    exp.display(data)
