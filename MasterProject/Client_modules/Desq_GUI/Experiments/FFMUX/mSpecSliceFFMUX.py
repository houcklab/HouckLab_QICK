"""
================================================================================
mSpecSliceFFMUX.py - Qubit Spectroscopy with Fast Flux and MUX Readout
================================================================================

Two-tone spectroscopy to find the qubit frequency:
- Sweeps qubit drive frequency
- Fast flux biasing during pulse and readout
- Multiplexed readout capability

SEQUENCE:
---------
    FFPulse ON → spec pulse (swept freq) → FFReadout ON → readout → FF OFF

USAGE:
------
    from StarterPackConfigFFMUX import make_config
    from mSpecSliceFFMUX import QubitSpecSliceFFMUX
    
    cfg = make_config({"SpecSpan": 50, "SpecNumPoints": 81}, qubit_indices=[5])
    exp = QubitSpecSliceFFMUX(soc=soc, soccfg=soccfg, cfg=cfg, path='Spec')
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

# =============================================================================
# QICK PROGRAM
# =============================================================================

class QubitSpecSliceFFProg(FFAveragerProgramV2):
    """Qubit spectroscopy pulse sequence with FF support."""
    
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
        
        # Set up frequency sweep
        self.add_loop("qubit_freq_loop", cfg["SpecNumPoints"])
        qubit_freq_sweep = QickSweep1D(
            "qubit_freq_loop",
            start=cfg["qubit_freqs"][0] - cfg["SpecSpan"],
            end=cfg["qubit_freqs"][0] + cfg["SpecSpan"]
        )
        
        # Add spectroscopy pulse
        if cfg.get('Gauss', False):
            # Gaussian pulse
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
                freq=qubit_freq_sweep,
                phase=90,
                gain=cfg.get("Gauss_gain", cfg["qubit_gain"]) / 32766.0
            )
            self.qubit_length_us = cfg["sigma"] * 4
        else:
            # Constant pulse (longer, for better frequency resolution)
            self.add_pulse(
                ch=cfg["qubit_ch"],
                name='qubit_drive',
                style="const",
                freq=qubit_freq_sweep,
                phase=0,
                gain=cfg["qubit_gain"] / 32766.0,
                length=cfg.get("qubit_length", 10)
            )
            self.qubit_length_us = cfg.get("qubit_length", 10)
    
    def _body(self, cfg):
        FF_pulse_delay = 1
        
        # FF during spec pulse
        self.FFPulses(self.FFPulse, self.qubit_length_us + FF_pulse_delay + 0.05)
        
        # Play spectroscopy pulse
        self.pulse(ch=cfg["qubit_ch"], name="qubit_drive", t=FF_pulse_delay)
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
        self.FFPulses(-1 * self.FFPulse, self.qubit_length_us + 1.05)
    
    def loop_pts(self):
        return (self.get_pulse_param("qubit_drive", "freq", as_array=True) + self.cfg.get('qubit_LO', 0),)


# =============================================================================
# EXPERIMENT CLASS
# =============================================================================

class QubitSpecSliceFFMUX(ExperimentClass):
    """Qubit Spectroscopy with FF/MUX support."""
    
    config_template = {
        "SpecSpan": 50,                   # Half-width of freq sweep [MHz]
        "SpecNumPoints": 81,              # Number of frequency points
        "Gauss": True,                    # Use Gaussian pulse (vs const)
        "Gauss_gain": 20000,              # Gain for Gaussian pulse
        "qubit_gain": 5000,               # Gain for const pulse
        "qubit_length": 10,               # Length for const pulse [µs]
    }
    
    def __init__(self, soc=None, soccfg=None, path='', outerFolder='',
                 prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(
            soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
            prefix=prefix, cfg=cfg, config_file=config_file, progress=progress
        )
    
    def acquire(self, progress=False, use_lorentzian=False):
        self.cfg.setdefault("qubit_length", 100)
        
        prog = QubitSpecSliceFFProg(
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
        x_pts = prog.get_pulse_param("qubit_drive", "freq", as_array=True) + self.cfg.get('qubit_LO', 0)
        
        data = {
            'config': self.cfg,
            'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}
        }
        self.data = data
        self.analyze(data, use_lorentzian=use_lorentzian)
        return data
    
    def analyze(self, data=None, use_lorentzian=False, **kwargs):
        if data is None:
            data = self.data
        
        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']
        
        sig = IQ_contrast(avgi, avgq)
        peak_loc = np.argmax(sig)
        self.qubitFreq_argmax = x_pts[peak_loc]
        
        # Lorentzian fit
        def lorentzian(f, f0, gamma, A, offset):
            return A / (1 + ((f - f0) / gamma)**2) + offset
        
        try:
            N = max(10, len(x_pts) // 20)
            i_min, i_max = max(0, peak_loc - N), min(len(x_pts), peak_loc + N)
            x_fit, y_fit = x_pts[i_min:i_max], sig[i_min:i_max]
            
            p0 = [x_pts[peak_loc], (x_fit[-1]-x_fit[0])/6, np.max(y_fit)-np.min(y_fit), np.min(y_fit)]
            popt, pcov = curve_fit(lorentzian, x_fit, y_fit, p0=p0,
                                  bounds=([x_fit[0], 0, 0, -np.inf], [x_fit[-1], x_fit[-1]-x_fit[0], np.inf, np.inf]))
            
            self.qubitFreq_lorentz = popt[0]
            self.qubit_linewidth = popt[1]
            self.lorentz_fit = lorentzian(x_pts, *popt)
            self.freq_uncertainty = np.sqrt(pcov[0, 0])
            
            self.qubitFreq = self.qubitFreq_lorentz if use_lorentzian and self.freq_uncertainty < 0.2*self.qubit_linewidth else self.qubitFreq_argmax
            
            data['data']['qubitFreq'] = self.qubitFreq
            data['data']['linewidth'] = self.qubit_linewidth
            print(f"[SpecSlice] Peak at {self.qubitFreq:.3f} MHz, linewidth = {self.qubit_linewidth:.2f} MHz")
        except:
            self.qubitFreq = self.qubitFreq_argmax
            data['data']['qubitFreq'] = self.qubitFreq
            print(f"[SpecSlice] Peak at {self.qubitFreq:.3f} MHz (argmax)")
        
        return data
    
    def display(self, data=None, plotDisp=False, figNum=1, block=True, ax=None, **kwargs):
        if data is None:
            data = self.data
        
        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']
        sig = np.abs(avgi + 1j * avgq)
        
        if ax is None:
            plt.figure(figsize=(8, 5))
            ax = plt.gca()
        
        ax.plot(x_pts, avgi, '.-', color='orange', label="I", alpha=0.7)
        ax.plot(x_pts, avgq, '.-', color='blue', label="Q", alpha=0.7)
        
        if hasattr(self, 'lorentz_fit') and self.lorentz_fit is not None:
            ax.plot(x_pts, self.lorentz_fit, '-', linewidth=2, color='black')
            ax.axvline(self.qubitFreq_lorentz, color='black', linestyle='--', 
                      label=f"Lorentz: {self.qubitFreq_lorentz:.2f} MHz")
        
        if hasattr(self, 'qubitFreq_argmax'):
            ax.axvline(self.qubitFreq_argmax, color='gray', linestyle=':',
                      label=f"Argmax: {self.qubitFreq_argmax:.2f} MHz")
        
        ax.set_xlabel("Qubit Frequency (MHz)")
        ax.set_ylabel("Signal (a.u.)")
        ax.set_title(self.titlename)
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plt.savefig(self.iname[:-4] + '_IQ.png')
        
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

class MockQubitSpecSliceFFMUX(ExperimentClass):
    """Mock spectroscopy for testing."""
    
    config_template = {
        "SpecSpan": 50,
        "SpecNumPoints": 81,
        "qubit_freq_true": 4500.0,
        "linewidth": 5.0,
        "noise_level": 0.05,
    }
    
    def __init__(self, path='', outerFolder='', prefix='data', cfg=None, **kwargs):
        super().__init__(path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, **kwargs)
    
    def acquire(self, progress=False, **kwargs):
        cfg = self.cfg
        center = cfg.get('qubit_freqs', [cfg.get('qubit_freq_true', 4500)])[0]
        span = cfg.get('SpecSpan', 50)
        x_pts = np.linspace(center - span, center + span, cfg.get('SpecNumPoints', 81))
        
        f0 = cfg.get('qubit_freq_true', center)
        gamma = cfg.get('linewidth', 5.0)
        lorentzian = gamma**2 / ((x_pts - f0)**2 + gamma**2)
        
        avgi = lorentzian + cfg.get('noise_level', 0.05) * np.random.randn(len(x_pts))
        avgq = 0.3 * lorentzian + cfg.get('noise_level', 0.05) * np.random.randn(len(x_pts))
        
        data = {'config': cfg, 'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq}}
        self.data = data
        
        self.qubitFreq = x_pts[np.argmax(IQ_contrast(avgi, avgq))]
        data['data']['qubitFreq'] = self.qubitFreq
        print(f"[MockSpec] Peak at {self.qubitFreq:.3f} MHz (true = {f0:.3f} MHz)")
        return data
    
    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data
        
        x_pts = data['data']['x_pts']
        avgi, avgq = data['data']['avgi'], data['data']['avgq']
        
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot(x_pts, avgi, '.-', color='orange', label='I')
        ax.plot(x_pts, avgq, '.-', color='blue', label='Q')
        ax.axvline(data['data']['qubitFreq'], color='red', linestyle='--', label=f"Peak: {data['data']['qubitFreq']:.2f} MHz")
        ax.set_xlabel("Frequency (MHz)")
        ax.set_ylabel("Signal (a.u.)")
        ax.set_title("Mock Qubit Spectroscopy (FFMUX)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        if plotDisp:
            plt.show(block=block)
        return fig, ax


if __name__ == '__main__':
    print("Testing MockQubitSpecSliceFFMUX...")
    exp = MockQubitSpecSliceFFMUX(cfg={"SpecSpan": 30, "SpecNumPoints": 61, "qubit_freq_true": 4500, "qubit_freqs": [4500]})
    data = exp.acquire()
    exp.display(data)
