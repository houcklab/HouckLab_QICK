"""
================================================================================
mT1FFMUX.py - T1 Relaxation Measurement with Fast Flux and MUX Readout
================================================================================

Measures the qubit energy relaxation time (T1) using:
- Fast flux biasing during pulse and readout
- Multiplexed readout capability
- QickSweep1D for efficient delay sweeping

SEQUENCE:
---------
    FFPulse ON → π pulse → variable delay → FFReadout ON → readout → FF OFF

USAGE:
------
    from StarterPackConfigFFMUX import make_config
    from mT1FFMUX import T1MUX
    
    cfg = make_config({"stop_delay_us": 100, "expts": 51}, qubit_indices=[5])
    exp = T1MUX(soc=soc, soccfg=soccfg, cfg=cfg, path='T1')
    data = exp.acquire(progress=True)
    exp.display(data)

================================================================================
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

# QICK imports
try:
    from qick.asm_v2 import QickSweep1D
    QICK_AVAILABLE = True
except ImportError:
    QICK_AVAILABLE = False
    class QickSweep1D:
        def __init__(self, name, start, end):
            self.name = name
            self.start = start
            self.end = end

# Local imports
try:
    from .FFAveragerProgram import FFAveragerProgramV2
    from . import FF_utils as FF
    from .BaseConfigFFMUX import ExperimentClass, IQ_contrast
except ImportError:
    from FFAveragerProgram import FFAveragerProgramV2
    import FF_utils as FF
    from BaseConfigFFMUX import ExperimentClass, IQ_contrast


# =============================================================================
# QICK PROGRAM
# =============================================================================

class T1Program(FFAveragerProgramV2):
    """
    T1 measurement pulse sequence with FF support.
    
    Sequence: π pulse → variable delay → readout
    FF bias applied during both pulse and readout phases.
    """
    
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
        
        # Add MUX readout pulse
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
        
        # Add qubit π pulse (Gaussian)
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
            freq=cfg["qubit_freqs"][0],
            phase=90,
            gain=cfg["qubit_gains"][0]
        )
        
        self.qubit_length_us = cfg["sigma"] * 4
    
    def _body(self, cfg):
        # Calculate total experiment length (for FF pulse)
        expt_length = self.qubit_length_us + 1.05 + self.delay_loop
        
        # Turn on FF during experiment
        self.FFPulses(self.FFPulse, expt_length)
        
        # Play π pulse
        self.pulse(ch=cfg["qubit_ch"], name="qubit_drive", t=1)
        
        # Wait for pulse to complete
        self.delay(self.qubit_length_us + 1.05)
        
        # Variable delay (T1 sweep)
        self.delay(self.delay_loop, tag='swept_delay')
        
        # Readout with FF
        self.FFPulses(self.FFReadouts, cfg["res_length"])
        for ro_ch, adc_trig_delay in zip(cfg["ro_chs"], cfg["adc_trig_delays"]):
            self.trigger(ros=[ro_ch], pins=[0], t=adc_trig_delay)
        self.pulse(cfg["res_ch"], name='res_drive')
        self.wait_auto()
        self.delay_auto(10)
        
        # Undo FF pulses
        self.FFPulses(-1 * self.FFReadouts, cfg["res_length"])
        self.FFPulses(-1 * self.FFPulse, expt_length)
    
    def loop_pts(self):
        """Return the sweep points (delay times)."""
        return (self.get_time_param("swept_delay", "t", as_array=True),)


# =============================================================================
# EXPERIMENT CLASS
# =============================================================================

class T1MUX(ExperimentClass):
    """
    T1 Relaxation Time Measurement with FF/MUX support.
    """
    
    # Experiment-specific config (merges with BaseConfig)
    config_template = {
        "stop_delay_us": 100,             # Maximum delay time [µs]
        "expts": 51,                      # Number of delay points
    }
    
    def __init__(self, soc=None, soccfg=None, path='', outerFolder='', 
                 prefix='data', cfg=None, config_file=None, progress=None):
        super().__init__(
            soc=soc, soccfg=soccfg, path=path, outerFolder=outerFolder,
            prefix=prefix, cfg=cfg, config_file=config_file, progress=progress
        )
    
    def acquire(self, progress=False):
        """Run T1 measurement."""
        prog = T1Program(
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
        
        # Extract data: shape [num_ROs, 1, expts, 2]
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
        
        # Attempt fit
        self.analyze(data)
        
        return data
    
    def analyze(self, data=None, **kwargs):
        """Fit T1 decay curve."""
        if data is None:
            data = self.data
        
        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']
        
        contrast = IQ_contrast(avgi, avgq)
        
        def t1_fit(t, T1, A, y0):
            return A * np.exp(-t / T1) + y0
        
        try:
            p0 = [x_pts[-1] / 5, np.max(contrast) - np.min(contrast), contrast[-1]]
            popt, pcov = curve_fit(t1_fit, x_pts, contrast, p0=p0)
            
            self.T1 = popt[0]
            data['data']['T1'] = self.T1
            data['data']['fit_params'] = {'T1': popt[0], 'A': popt[1], 'y0': popt[2]}
            print(f"[T1MUX] T1 = {self.T1:.2f} µs")
        except Exception as e:
            print(f"[T1MUX] Fit failed: {e}")
        
        return data
    
    def display(self, data=None, plotDisp=False, figNum=1, block=True, ax=None, **kwargs):
        """Plot T1 measurement results."""
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
        
        # Plot data
        sign = 1
        if 'fit_params' in data['data']:
            sign = np.sign(data['data']['fit_params']['A'])
        
        ax.plot(x_pts, sign * contrast, 'o-', color='blue', 
               label=f'qfreq = {self.cfg["qubit_freqs"][0]:.1f} MHz')
        
        # Plot fit
        if 'fit_params' in data['data']:
            fp = data['data']['fit_params']
            t_fine = np.linspace(x_pts[0], x_pts[-1], 200)
            fit_curve = fp['A'] * np.exp(-t_fine / fp['T1']) + fp['y0']
            ax.plot(t_fine, sign * fit_curve, '--', color='black', 
                   label=f"T1 = {fp['T1']:.2f} µs")
        
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
        """Save experiment data."""
        if data is None:
            data = self.data
        print(f'Saving {self.fname}')
        super().save_data(data=data['data'])


# =============================================================================
# MOCK VERSION
# =============================================================================

class MockT1MUX(ExperimentClass):
    """Mock T1 experiment for testing without hardware."""
    
    config_template = {
        "stop_delay_us": 100,
        "expts": 51,
        "T1_true": 30.0,                  # Simulated T1 [µs]
        "noise_level": 0.05,
    }
    
    def __init__(self, soc=None, soccfg=None, path='', outerFolder='',
                 prefix='data', cfg=None, **kwargs):
        super().__init__(path=path, outerFolder=outerFolder, prefix=prefix,
                         cfg=cfg, **kwargs)
    
    def acquire(self, progress=False):
        cfg = self.cfg
        x_pts = np.linspace(0, cfg.get('stop_delay_us', 100), cfg.get('expts', 51))
        
        T1 = cfg.get('T1_true', 30.0)
        decay = np.exp(-x_pts / T1)
        noise = cfg.get('noise_level', 0.05) * np.random.randn(len(x_pts))
        
        avgi = decay + noise
        avgq = 0.1 * decay + 0.5 * cfg.get('noise_level', 0.05) * np.random.randn(len(x_pts))
        
        data = {
            'config': cfg,
            'data': {
                'x_pts': x_pts,
                'avgi': avgi,
                'avgq': avgq,
                'qfreq': cfg.get('qubit_freqs', [4500])[0],
            }
        }
        self.data = data
        self.analyze(data)
        return data
    
    def analyze(self, data=None, **kwargs):
        if data is None:
            data = self.data
        
        x_pts = data['data']['x_pts']
        contrast = IQ_contrast(data['data']['avgi'], data['data']['avgq'])
        
        def t1_fit(t, T1, A, y0):
            return A * np.exp(-t / T1) + y0
        
        try:
            p0 = [x_pts[-1] / 5, contrast[0] - contrast[-1], contrast[-1]]
            popt, _ = curve_fit(t1_fit, x_pts, contrast, p0=p0)
            self.T1 = popt[0]
            data['data']['T1'] = self.T1
            data['data']['fit_params'] = {'T1': popt[0], 'A': popt[1], 'y0': popt[2]}
            print(f"[MockT1MUX] T1 = {self.T1:.2f} µs (true = {self.cfg.get('T1_true', 30):.2f} µs)")
        except:
            pass
        return data
    
    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data
        
        x_pts = data['data']['x_pts']
        contrast = IQ_contrast(data['data']['avgi'], data['data']['avgq'])
        
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, ax = plt.subplots(figsize=(8, 5), num=figNum)
        
        ax.plot(x_pts, contrast, 'o-', color='blue', label='Data')
        
        if 'fit_params' in data['data']:
            fp = data['data']['fit_params']
            t_fine = np.linspace(x_pts[0], x_pts[-1], 200)
            fit_curve = fp['A'] * np.exp(-t_fine / fp['T1']) + fp['y0']
            ax.plot(t_fine, fit_curve, '--', color='black', label=f"T1 = {fp['T1']:.2f} µs")
        
        ax.set_xlabel("Wait time (µs)")
        ax.set_ylabel("Contrast (a.u.)")
        ax.set_title("Mock T1 Measurement (FFMUX)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        if plotDisp:
            plt.show(block=block)
        else:
            plt.close(fig)
        
        return fig, ax
    
    def save_data(self, data=None):
        print(f"[MockT1MUX] Would save to {self.fname}")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    print("Testing MockT1MUX...")
    cfg = {"stop_delay_us": 100, "expts": 41, "T1_true": 25, "noise_level": 0.04}
    exp = MockT1MUX(path='test', prefix='t1', cfg=cfg)
    data = exp.acquire()
    exp.display(data, plotDisp=True, block=True)
