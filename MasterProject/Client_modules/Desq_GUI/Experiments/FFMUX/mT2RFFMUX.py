"""
================================================================================
mT2RFFMUX.py - T2 Ramsey Measurement with Fast Flux and MUX Readout
================================================================================

Measures the qubit dephasing time (T2*) using Ramsey interferometry:
- Fast flux biasing during pulse and readout
- Multiplexed readout capability
- Optional artificial detuning via freq_shift

SEQUENCE:
---------
    FFPulse ON → π/2 → delay → π/2 (with phase) → FFReadout ON → readout → FF OFF

USAGE:
------
    from StarterPackConfigFFMUX import make_config
    from mT2RFFMUX import T2RMUX
    
    cfg = make_config({"stop_delay_us": 50, "expts": 61, "freq_shift": 0.5}, 
                      qubit_indices=[5])
    exp = T2RMUX(soc=soc, soccfg=soccfg, cfg=cfg, path='T2R')
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

class T2RProgram(FFAveragerProgramV2):
    """T2 Ramsey pulse sequence with FF support."""
    
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
        
        # Declare readout channels
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
        
        # Set up delay sweep
        self.add_loop("delay_loop", cfg["expts"])
        self.delay_loop = QickSweep1D("delay_loop", start=0, end=cfg["stop_delay_us"])
        
        # Warn if step size is too small
        step_size = cfg["stop_delay_us"] / cfg["expts"]
        if step_size < 0.00465:
            print(f"WARNING: Step size ({step_size:.5f} µs) < 1 clock cycle (4.65 ns)!")
        
        # Phase sweep for artificial detuning (optional)
        if cfg.get("phase_shift_cycles", 0) != 0:
            self.phase_loop = QickSweep1D("delay_loop", start=0, end=360*cfg["phase_shift_cycles"])
        else:
            self.phase_loop = 180  # Fixed phase for second pulse
        
        # Add qubit π/2 pulses
        self.add_gauss(
            ch=cfg["qubit_ch"],
            name="qubit",
            sigma=cfg["sigma"],
            length=4 * cfg["sigma"]
        )
        
        # First π/2 pulse (phase = 0)
        self.add_pulse(
            ch=cfg["qubit_ch"],
            name='qubit_drive_1',
            style="arb",
            envelope="qubit",
            freq=cfg["qubit_drive_freq"],
            phase=0,
            gain=cfg["pi2_gain"]
        )
        
        # Second π/2 pulse (phase swept or fixed)
        self.add_pulse(
            ch=cfg["qubit_ch"],
            name='qubit_drive_2',
            style="arb",
            envelope="qubit",
            freq=cfg["qubit_drive_freq"],
            phase=self.phase_loop,
            gain=cfg["pi2_gain"]
        )
        
        self.qubit_length_us = cfg["sigma"] * 4
    
    def _body(self, cfg):
        # Total experiment length
        expt_length = self.qubit_length_us + 10.05 + self.delay_loop + self.qubit_length_us + 1
        
        # FF during experiment
        self.FFPulses(self.FFPulse, expt_length)
        self.delay(10.0)
        
        # First π/2
        self.pulse(ch=cfg["qubit_ch"], name="qubit_drive_1", t=0)
        self.delay(self.qubit_length_us)
        
        # Second π/2 after variable delay
        self.pulse(ch=cfg["qubit_ch"], name="qubit_drive_2", t=self.delay_loop, tag='swept_delay')
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
        self.FFPulses(-1 * self.FFPulse, expt_length)
    
    def loop_pts(self):
        return (self.get_time_param("swept_delay", "t", as_array=True),)


# =============================================================================
# EXPERIMENT CLASS
# =============================================================================

class T2RMUX(ExperimentClass):
    """T2 Ramsey Dephasing Measurement with FF/MUX support."""
    
    config_template = {
        "stop_delay_us": 50,              # Maximum delay [µs]
        "expts": 61,                      # Number of points
        "freq_shift": 0.0,                # Artificial detuning [MHz]
        "phase_shift_cycles": 0,          # Phase accumulation cycles (0 = fixed)
    }
    
    def __init__(self, soc=None, soccfg=None, path='', outerFolder='',
                 prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(
            soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
            prefix=prefix, cfg=cfg, config_file=config_file, progress=progress
        )
    
    def acquire(self, progress=False):
        # Set defaults
        self.cfg.setdefault('qubit_drive_freq', 
                           self.cfg['qubit_freqs'][0] + self.cfg.get("freq_shift", 0))
        self.cfg.setdefault('pi_gain', self.cfg['qubit_gains'][0])
        self.cfg.setdefault('pi2_gain', self.cfg['qubit_gains'][0] / 2)
        
        prog = T2RProgram(
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
        x_pts = prog.get_time_param("swept_delay", "t", as_array=True)
        
        data = {
            'config': self.cfg,
            'data': {
                'x_pts': x_pts,
                'avgi': avgi,
                'avgq': avgq,
                'qfreq': self.cfg["qubit_freqs"][0],
            }
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
        
        def ramsey_fit(t, T2, A, y0, omega, phi):
            return A * np.exp(-t / T2) * np.cos(omega * t - phi) + y0
        
        def exp_fit(t, T2, A, y0):
            return A * np.exp(-t / T2) + y0
        
        try:
            # Estimate frequency from FFT
            from scipy.fft import fft, fftfreq
            y_centered = contrast - np.mean(contrast)
            yf = np.abs(fft(y_centered))
            xf = fftfreq(len(x_pts), x_pts[1] - x_pts[0])
            omega_guess = 2 * np.pi * np.abs(xf[np.argmax(yf[:len(yf)//2])])
            
            p0 = [x_pts[-1]/5, (np.max(contrast)-np.min(contrast))/2, 
                  contrast[-1], omega_guess, 0.01]
            popt, _ = curve_fit(ramsey_fit, x_pts, contrast, p0=p0, maxfev=5000)
            
            self.T2 = popt[0]
            data['data']['T2'] = self.T2
            data['data']['fit_params'] = {
                'T2': popt[0], 'A': popt[1], 'y0': popt[2], 
                'omega': popt[3], 'phi': popt[4]
            }
            print(f"[T2RMUX] T2* = {self.T2:.2f} µs")
        except Exception as e:
            print(f"[T2RMUX] Fit failed: {e}")
        
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
            fig, ax = plt.subplots(figsize=(7.2, 4.8), num=figNum)
            ax.set_title(f"Qubit: {self.cfg.get('Qubit_Readout_List', [])}")
            plt.suptitle(self.titlename)
        else:
            fig = ax.get_figure()
        
        ax.plot(x_pts, contrast, 'o-', color='blue', 
               label=f'qfreq = {self.cfg.get("qubit_drive_freq", 0):.2f} MHz')
        
        if 'fit_params' in data['data']:
            fp = data['data']['fit_params']
            t_fine = np.linspace(x_pts[0], x_pts[-1], 500)
            fit_curve = fp['A'] * np.exp(-t_fine/fp['T2']) * np.cos(fp['omega']*t_fine - fp['phi']) + fp['y0']
            env_upper = fp['A'] * np.exp(-t_fine/fp['T2']) + fp['y0']
            env_lower = -fp['A'] * np.exp(-t_fine/fp['T2']) + fp['y0']
            
            ax.plot(t_fine, fit_curve, '-', color='black')
            ax.plot(t_fine, env_upper, '--', color='black', label=f"T2* = {fp['T2']:.2f} µs")
            ax.plot(t_fine, env_lower, '--', color='black')
        
        ax.set_xlabel("Wait time (µs)")
        ax.set_ylabel("Contrast (a.u.)")
        ax.legend(prop={'size': 12})
        ax.grid(True, alpha=0.3)
        
        plt.savefig(self.iname[:-4] + '.png')
        
        if plotDisp:
            plt.show(block=block)
            plt.pause(0.01)
        else:
            fig.clf(True)
            plt.close(fig)
        
        return fig, ax
    
    def save_data(self, data=None):
        if data is None:
            data = self.data
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


# =============================================================================
# MOCK VERSION
# =============================================================================

class MockT2RMUX(ExperimentClass):
    """Mock T2 Ramsey experiment for testing."""
    
    config_template = {
        "stop_delay_us": 50,
        "expts": 61,
        "freq_shift": 0.5,
        "T2_true": 15.0,
        "noise_level": 0.08,
    }
    
    def __init__(self, path='', outerFolder='', prefix='data', cfg=None, **kwargs):
        super().__init__(path=path, outerFolder=outerFolder, prefix=prefix, cfg=cfg, **kwargs)
    
    def acquire(self, progress=False):
        cfg = self.cfg
        x_pts = np.linspace(0, cfg.get('stop_delay_us', 50), cfg.get('expts', 61))
        
        T2 = cfg.get('T2_true', 15.0)
        omega = 2 * np.pi * cfg.get('freq_shift', 0.5)
        envelope = np.exp(-x_pts / T2)
        
        avgi = envelope * np.cos(omega * x_pts) + cfg.get('noise_level', 0.08) * np.random.randn(len(x_pts))
        avgq = envelope * np.sin(omega * x_pts) + cfg.get('noise_level', 0.08) * np.random.randn(len(x_pts))
        
        data = {
            'config': cfg,
            'data': {'x_pts': x_pts, 'avgi': avgi, 'avgq': avgq, 'qfreq': 4500}
        }
        self.data = data
        return data
    
    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data
        
        x_pts = data['data']['x_pts']
        contrast = IQ_contrast(data['data']['avgi'], data['data']['avgq'])
        
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot(x_pts, contrast, 'o-', label='Data')
        ax.set_xlabel("Wait time (µs)")
        ax.set_ylabel("Contrast")
        ax.set_title("Mock T2 Ramsey (FFMUX)")
        ax.grid(True, alpha=0.3)
        
        if plotDisp:
            plt.show(block=block)
        return fig, ax


if __name__ == '__main__':
    print("Testing MockT2RMUX...")
    exp = MockT2RMUX(cfg={"stop_delay_us": 40, "expts": 51, "T2_true": 12, "freq_shift": 0.8})
    data = exp.acquire()
    exp.display(data)
