"""
================================================================================
mT1.py - T1 Relaxation Time Measurement
================================================================================

Measures the qubit energy relaxation time (T1) by:
1. Exciting the qubit with a π pulse
2. Waiting a variable delay time
3. Measuring the qubit state

The resulting decay curve is fit to extract T1.

USAGE:
------
    from StarterPackConfig import BaseConfig, make_config
    from T1Experiment import T1Experiment
    
    exp_cfg = {"ntime_steps": 51, "total_time": 150}
    full_cfg = make_config(exp_cfg, qubit_id='1')
    
    exp = T1Experiment(path='T1', cfg=full_cfg, soc=soc, soccfg=soccfg)
    data = exp.acquire()
    exp.analyze(data)
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
from MasterProject.Client_modules.Desq_GUI.CoreLib.Experiment import ExperimentClass


# =============================================================================
# QICK PROGRAM
# =============================================================================

class T1Program(RAveragerProgram):
    """
    T1 measurement pulse sequence.

    Sequence: π pulse → variable delay → readout
    Sweep: delay time from cfg["start"] to cfg["start"] + cfg["step"]*cfg["expts"]
    """

    def __init__(self, soccfg, cfg):
        super().__init__(soccfg, cfg)

    def initialize(self):
        cfg = self.cfg

        # Calculate sweep parameters
        cfg["step"] = int(cfg["total_time"] / (cfg["ntime_steps"] - 1))
        cfg["expts"] = cfg["ntime_steps"]

        # Get register page for qubit channel
        self.q_rp = self.ch_page(cfg["qubit_ch"])
        self.r_wait = self.us2cycles(0.010)
        self.regwi(self.q_rp, self.r_wait, self.us2cycles(cfg["start"]))

        # Declare generators
        self.declare_gen(ch=cfg["res_ch"], nqz=cfg["nqz"])
        self.declare_gen(ch=cfg["qubit_ch"], nqz=cfg["qubit_nqz"])

        # Declare readouts
        for ch in cfg["ro_chs"]:
            self.declare_readout(
                ch=ch,
                length=self.us2cycles(cfg["read_length"], gen_ch=cfg["res_ch"]),
                freq=cfg["read_pulse_freq"],
                gen_ch=cfg["res_ch"]
            )

        # Convert frequencies
        read_freq = self.freq2reg(cfg["read_pulse_freq"], gen_ch=cfg["res_ch"],
                                  ro_ch=cfg["ro_chs"][0])
        qubit_freq = self.freq2reg(cfg["qubit_freq"], gen_ch=cfg["qubit_ch"])

        # Setup qubit pulse (Gaussian π pulse)
        if cfg["qubit_pulse_style"] == "arb":
            self.add_gauss(
                ch=cfg["qubit_ch"],
                name="qubit",
                sigma=self.us2cycles(cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                length=self.us2cycles(cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4
            )
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style=cfg["qubit_pulse_style"],
                freq=qubit_freq,
                phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]),
                gain=cfg["qubit_gain"],
                waveform="qubit"
            )
        elif cfg["qubit_pulse_style"] == "flat_top":
            self.add_gauss(
                ch=cfg["qubit_ch"],
                name="qubit",
                sigma=self.us2cycles(cfg["sigma"], gen_ch=cfg["qubit_ch"]),
                length=self.us2cycles(cfg["sigma"], gen_ch=cfg["qubit_ch"]) * 4
            )
            self.set_pulse_registers(
                ch=cfg["qubit_ch"],
                style=cfg["qubit_pulse_style"],
                freq=qubit_freq,
                phase=self.deg2reg(90, gen_ch=cfg["qubit_ch"]),
                gain=cfg["qubit_gain"],
                waveform="qubit",
                length=self.us2cycles(cfg["flat_top_length"])
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
        # Play π pulse
        self.pulse(ch=self.cfg["qubit_ch"])
        self.sync_all(self.us2cycles(0.05))

        # Variable delay
        self.sync(self.q_rp, self.r_wait)

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
        # Increment delay time
        self.mathi(self.q_rp, self.r_wait, self.r_wait, '+',
                   self.us2cycles(self.cfg["step"]))


# =============================================================================
# EXPERIMENT CLASS
# =============================================================================

class T1Experiment(ExperimentClass):
    """
    T1 Relaxation Time Measurement

    Measures the qubit energy relaxation time (T1) by:
    1. Exciting the qubit with a π pulse
    2. Waiting a variable delay time
    3. Measuring the qubit state

    The resulting decay curve is fit to extract T1.
    """

    # =========================================================================
    # CONFIGURATION TEMPLATE (Experiment-Specific Parameters Only)
    # =========================================================================
    # Base hardware parameters come from StarterPackConfig.BaseConfig

    config_template = {
        # --- T1 Sweep Parameters ---
        "start": 0,                       # Starting delay time [µs]
        "ntime_steps": 31,                # Number of delay points
        "total_time": 100,                # Total sweep range [µs]
        
        # --- Qubit Pulse Style ---
        "qubit_pulse_style": "arb",       # "arb" (Gaussian) or "flat_top"
        "flat_top_length": 0.5,           # Flat top duration [µs] (if flat_top style)
    }

    # =========================================================================
    # INITIALIZATION
    # =========================================================================

    def __init__(self, path='', outerFolder='', prefix='data',
                 soc=None, soccfg=None, cfg=None, config_file=None, **kwargs):
        """
        Initialize the T1 experiment.

        Parameters:
            path (str): Directory name for saving data
            outerFolder (str): Parent directory for data
            prefix (str): Prefix for data files
            soc: QICK SoC object
            soccfg: QICK SoC configuration
            cfg (dict): Experiment configuration (merged with defaults)
            config_file (str): Optional path to JSON config file
        """
        super().__init__(
            path=path,
            outerFolder=outerFolder,
            prefix=prefix,
            soc=soc,
            soccfg=soccfg,
            cfg=cfg,
            config_file=config_file,
            **kwargs
        )

    # =========================================================================
    # DATA ACQUISITION
    # =========================================================================

    def acquire(self, progress=False, debug=False):
        """
        Run the T1 measurement.

        Parameters:
            progress (bool): Show progress bar
            debug (bool): Print debug information

        Returns:
            dict: Data dictionary with 'config' and 'data' keys
        """
        # Create and run the QICK program
        prog = T1Program(self.soccfg, self.cfg)
        x_pts, avgi, avgq = prog.acquire(
            self.soc,
            threshold=None,
            angle=None,
            load_pulses=True,
            readouts_per_experiment=1,
            save_experiments=None,
            start_src="internal",
            progress=progress
        )

        # Package results
        data = {
            'config': self.cfg,
            'data': {
                'times': x_pts,
                'avgi': avgi,
                'avgq': avgq
            }
        }
        self.data = data
        return data

    # =========================================================================
    # DATA ANALYSIS
    # =========================================================================

    def analyze(self, data=None, **kwargs):
        """
        Fit the T1 decay curve.

        Parameters:
            data (dict): Data dictionary (uses self.data if None)

        Returns:
            dict: Updated data with fit parameters
        """
        if data is None:
            data = self.data

        times = data['data']['times']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]

        # Calculate magnitude
        contrast = np.sqrt(avgi**2 + avgq**2)

        # Fit exponential decay
        def t1_fit(t, T1, A, y0):
            return A * np.exp(-t / T1) + y0

        try:
            p0 = [times[-1] / 5, contrast[0] - contrast[-1], contrast[-1]]
            popt, pcov = curve_fit(t1_fit, times, contrast, p0=p0)
            T1_fit, A, y0 = popt

            data['data']['T1'] = T1_fit
            data['data']['fit_params'] = {'T1': T1_fit, 'A': A, 'y0': y0}
            data['data']['contrast'] = contrast
            print(f"[T1Experiment] Fitted T1 = {T1_fit:.2f} µs")

        except Exception as e:
            print(f"[T1Experiment] Fit failed: {e}")
            data['data']['contrast'] = contrast

        return data

    # =========================================================================
    # VISUALIZATION
    # =========================================================================

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        """
        Plot the T1 measurement results.

        Parameters:
            data (dict): Data to plot (uses self.data if None)
            plotDisp (bool): Display the plot
            figNum (int): Figure number
            block (bool): Block execution until plot is closed
        """
        if data is None:
            data = self.data

        times = data['data']['times']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]

        # Calculate IQ quantities
        sig = avgi + 1j * avgq
        contrast = np.abs(sig)
        phase = np.angle(sig, deg=True)

        # Create figure
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(4, 1, figsize=(10, 10), num=figNum)

        # Plot phase
        axs[0].plot(times, phase, 'o-', color='purple', markersize=4)
        axs[0].set_ylabel("Phase (deg)")
        axs[0].set_xlabel("Time (µs)")
        axs[0].set_title("T1 Measurement")
        axs[0].grid(True, alpha=0.3)

        # Plot magnitude with fit
        axs[1].plot(times, contrast, 'o', color='blue', markersize=4, label='Data')
        if 'fit_params' in data['data']:
            fp = data['data']['fit_params']
            t_fine = np.linspace(times[0], times[-1], 200)
            fit_curve = fp['A'] * np.exp(-t_fine / fp['T1']) + fp['y0']
            axs[1].plot(t_fine, fit_curve, '--', color='black', linewidth=2,
                       label=f"T1 = {fp['T1']:.2f} µs")
            axs[1].legend()
        axs[1].set_ylabel("Magnitude (a.u.)")
        axs[1].set_xlabel("Time (µs)")
        axs[1].grid(True, alpha=0.3)

        # Plot I
        axs[2].plot(times, avgi, 'o-', color='orange', markersize=4)
        axs[2].set_ylabel("I (a.u.)")
        axs[2].set_xlabel("Time (µs)")
        axs[2].grid(True, alpha=0.3)

        # Plot Q
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

    # =========================================================================
    # DATA STORAGE
    # =========================================================================

    def save_data(self, data=None):
        """Save experiment data to HDF5 file."""
        if data is None:
            data = self.data
        print(f"[T1Experiment] Saving to {self.fname}")
        super().save_data(data=data['data'])


# =============================================================================
# MOCK VERSION FOR TESTING
# =============================================================================

class MockT1Experiment(ExperimentClass):
    """
    Mock T1 Experiment - Generates simulated T1 decay data without hardware.
    """

    config_template = {
        # --- T1 Sweep Parameters ---
        "start": 0,
        "ntime_steps": 31,
        "total_time": 100,
        "qubit_pulse_style": "arb",
        "flat_top_length": 0.5,
        
        # --- Mock Simulation Parameters ---
        "T1_true": 25.0,                  # Simulated T1 value [µs]
        "noise_level": 0.05,              # Relative noise amplitude
    }

    def __init__(self, path='', outerFolder='', prefix='data', cfg=None, **kwargs):
        default_cfg = self.config_template.copy()
        if cfg:
            default_cfg.update(cfg)
        super().__init__(path=path, outerFolder=outerFolder, prefix=prefix,
                         cfg=default_cfg, **kwargs)

    def acquire(self, progress=False, debug=False):
        """Generate simulated T1 decay data."""
        cfg = self.cfg
        times = np.linspace(cfg['start'], cfg['total_time'], cfg['ntime_steps'])

        # Generate decay with noise
        T1 = cfg['T1_true']
        decay = np.exp(-times / T1)
        noise = cfg['noise_level'] * np.random.randn(len(times))

        avgi = decay + noise
        avgq = 0.1 * decay + 0.5 * cfg['noise_level'] * np.random.randn(len(times))

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
        """Fit T1 decay."""
        if data is None:
            data = self.data

        times = data['data']['times']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]
        contrast = np.sqrt(avgi**2 + avgq**2)

        def t1_fit(t, T1, A, y0):
            return A * np.exp(-t / T1) + y0

        try:
            p0 = [times[-1] / 5, contrast[0] - contrast[-1], contrast[-1]]
            popt, _ = curve_fit(t1_fit, times, contrast, p0=p0)
            T1_fit, A, y0 = popt
            data['data']['T1'] = T1_fit
            data['data']['fit_params'] = {'T1': T1_fit, 'A': A, 'y0': y0}
            data['data']['contrast'] = contrast
            print(f"[MockT1] Fitted T1 = {T1_fit:.2f} µs (true = {self.cfg['T1_true']:.2f} µs)")
        except Exception as e:
            print(f"[MockT1] Fit failed: {e}")
            data['data']['contrast'] = contrast

        return data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        """Plot T1 results."""
        if data is None:
            data = self.data

        times = data['data']['times']
        avgi = data['data']['avgi'][0][0]
        avgq = data['data']['avgq'][0][0]
        contrast = np.sqrt(avgi**2 + avgq**2)
        phase = np.angle(avgi + 1j * avgq, deg=True)

        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, axs = plt.subplots(4, 1, figsize=(10, 10), num=figNum)

        axs[0].plot(times, phase, 'o-', color='purple', markersize=4)
        axs[0].set_ylabel("Phase (deg)")
        axs[0].set_title("Mock T1 Experiment")
        axs[0].grid(True, alpha=0.3)

        axs[1].plot(times, contrast, 'o', color='blue', markersize=4, label='Data')
        if 'fit_params' in data['data']:
            fp = data['data']['fit_params']
            t_fine = np.linspace(times[0], times[-1], 200)
            fit_curve = fp['A'] * np.exp(-t_fine / fp['T1']) + fp['y0']
            axs[1].plot(t_fine, fit_curve, '--', color='black', linewidth=2,
                       label=f"T1 = {fp['T1']:.2f} µs")
            axs[1].legend()
        axs[1].set_ylabel("Contrast (a.u.)")
        axs[1].grid(True, alpha=0.3)

        axs[2].plot(times, avgi, 'o-', color='orange', markersize=4)
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
        print(f"[MockT1] Saving to {self.fname}")
        super().save_data(data=data.get('data', data))


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    print("Testing MockT1Experiment...")
    exp = MockT1Experiment(path='test', prefix='t1')
    data = exp.acquire()
    exp.analyze(data)
    exp.display(data, plotDisp=True, block=True)
