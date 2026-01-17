"""
MockExperiments.py - Comprehensive mock experiments for GUI testing without RFSoC

These experiments generate fake data and demonstrate various plotting patterns
used in real experiments. They inherit from ExperimentClass (not ExperimentClassPlus).

Plotting patterns covered:
1. Simple 1D decay curves (T1-style)
2. 1D oscillatory fits (Rabi, T2-style)
3. 1D spectroscopy peaks
4. 2D heatmaps (spec vs parameter sweeps)
5. IQ scatter plots (single shot)
6. Multi-channel I/Q transmission
7. Multi-panel correlation plots
8. MUXed multi-qubit readouts
9. Population vs sweep parameter
10. Time-domain pulse visualization

"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
import datetime
import os
from pathlib import Path

from MasterProject.Client_modules.Desq_GUI.CoreLib.Experiment import ExperimentClass

# Use ExperimentClass as the base, with a default outerFolder for mock usage
class MockExperimentClass(ExperimentClass):
    """Thin wrapper that provides default outerFolder for mock experiments."""
    def __init__(self, outerFolder='', **kwargs):
        super().__init__(outerFolder=outerFolder, **kwargs)


# ============================================================================
# 1. T1 DECAY EXPERIMENT (Simple exponential decay)
# ============================================================================

class MockT1Experiment(MockExperimentClass):
    """
    Mock T1 decay experiment with exponential fit.

    Plotting: Single axis, scatter + fit line
    Data: 1D decay curve
    """

    def __init__(self, **kwargs):
        # Default config
        default_cfg = {
            'T1_true': 25.0,  # us, true T1 for simulation
            'stop_delay_us': 100.0,  # Maximum delay time
            'expts': 51,  # Number of points
            'noise_level': 0.05,  # Relative noise
            'qubit_freqs': [4500.0],  # MHz
            'Qubit_Readout_List': [1],
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False):
        cfg = self.cfg

        # Generate time points
        x_pts = np.linspace(0, cfg['stop_delay_us'], cfg['expts'])

        # Generate fake T1 decay with noise
        T1 = cfg['T1_true']
        signal = np.exp(-x_pts / T1)
        noise = cfg['noise_level'] * np.random.randn(len(x_pts))

        # Simulate IQ data
        avgi = signal + noise
        avgq = 0.1 * signal + 0.5 * cfg['noise_level'] * np.random.randn(len(x_pts))

        data = {
            'config': cfg,
            'data': {
                'x_pts': x_pts,
                'avgi': avgi,
                'avgq': avgq,
                'qfreq': cfg['qubit_freqs'][0]
            }
        }
        self.data = data
        return data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']

        # Compute IQ contrast
        contrast = np.sqrt(avgi ** 2 + avgq ** 2)

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig, ax = plt.subplots(figsize=(8, 5), num=figNum)

        # Fit exponential decay
        def fit_func(t, T1, A, y0):
            return A * np.exp(-t / T1) + y0

        try:
            p0 = [x_pts[-1] / 5, contrast[0] - contrast[-1], contrast[-1]]
            popt, _ = curve_fit(fit_func, x_pts, contrast, p0=p0)
            T1_fit, A, y0 = popt

            ax.plot(x_pts, contrast, 'o', color='blue', markersize=6, label='Data')
            t_fine = np.linspace(x_pts[0], x_pts[-1], 200)
            ax.plot(t_fine, fit_func(t_fine, *popt), '--', color='black',
                    linewidth=2, label=f'T1 = {T1_fit:.2f} µs')
            ax.legend(fontsize=12)
        except Exception:
            ax.plot(x_pts, contrast, 'o-', color='blue', label='Data')

        ax.set_xlabel('Wait time (µs)', fontsize=12)
        ax.set_ylabel('IQ Contrast (a.u.)', fontsize=12)
        ax.set_title(f'Mock Experiment', fontsize=10)

        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)

        return fig, ax


# ============================================================================
# 2. T2 RAMSEY EXPERIMENT (Damped oscillations)
# ============================================================================

class MockT2RamseyExperiment(MockExperimentClass):
    """
    Mock T2 Ramsey experiment with damped oscillation fit.

    Plotting: Single axis, oscillatory data + envelope
    Data: Damped sinusoid
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'T2_true': 15.0,  # us
            'freq_detuning': 0.5,  # MHz, oscillation frequency
            'stop_delay_us': 60.0,
            'expts': 101,
            'noise_level': 0.08,
            'qubit_freqs': [4500.0],
            'Qubit_Readout_List': [1],
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False):
        cfg = self.cfg

        x_pts = np.linspace(0, cfg['stop_delay_us'], cfg['expts'])

        # Damped oscillation
        T2 = cfg['T2_true']
        omega = 2 * np.pi * cfg['freq_detuning']
        signal = np.exp(-x_pts / T2) * np.cos(omega * x_pts)
        noise = cfg['noise_level'] * np.random.randn(len(x_pts))

        avgi = signal + noise
        avgq = np.exp(-x_pts / T2) * np.sin(omega * x_pts) + 0.5 * cfg['noise_level'] * np.random.randn(len(x_pts))

        data = {
            'config': cfg,
            'data': {
                'x_pts': x_pts,
                'avgi': avgi,
                'avgq': avgq,
                'qfreq': cfg['qubit_freqs'][0]
            }
        }
        self.data = data
        return data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']

        contrast = np.sqrt(avgi ** 2 + avgq ** 2)

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig, ax = plt.subplots(figsize=(10, 5), num=figNum)

        def fit_func(t, T2, A, y0, omega, phi):
            return A * np.exp(-t / T2) * np.cos(omega * t - phi) + y0

        def envelope(t, T2, A, y0):
            return A * np.exp(-t / T2) + y0

        try:
            # Estimate frequency from zero crossings
            omega_guess = 2 * np.pi * 0.5
            p0 = [x_pts[-1] / 4, 0.5, 0.0, omega_guess, 0]
            popt, _ = curve_fit(fit_func, x_pts, avgi, p0=p0, maxfev=5000)
            T2_fit, A, y0, omega, phi = popt

            ax.plot(x_pts, avgi, 'o', color='blue', markersize=4, label='Data')
            t_fine = np.linspace(x_pts[0], x_pts[-1], 500)
            ax.plot(t_fine, fit_func(t_fine, *popt), '-', color='navy', linewidth=1.5)
            ax.plot(t_fine, envelope(t_fine, T2_fit, A, y0), '--', color='black',
                    linewidth=2, label=f'T2 = {T2_fit:.2f} µs')
            ax.plot(t_fine, envelope(t_fine, T2_fit, -A, y0), '--', color='black', linewidth=2)
            ax.legend(fontsize=11)
        except Exception:
            ax.plot(x_pts, avgi, 'o-', color='blue', label='I')
            ax.plot(x_pts, avgq, 'o-', color='orange', alpha=0.5, label='Q')
            ax.legend()

        ax.set_xlabel('Wait time (µs)', fontsize=12)
        ax.set_ylabel('Signal (a.u.)', fontsize=12)
        ax.set_title(f'Mock Experiment', fontsize=10)
        ax.axhline(0, color='gray', linestyle=':', alpha=0.5)

        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)

        return fig, ax


# ============================================================================
# 3. SPECTROSCOPY EXPERIMENT (Peak finding)
# ============================================================================

class MockSpectroscopyExperiment(MockExperimentClass):
    """
    Mock qubit spectroscopy experiment.

    Plotting: I and Q vs frequency with peak marker
    Data: Lorentzian peak shape
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'qubit_freq_center': 4500.0,  # MHz
            'SpecSpan': 50.0,  # MHz, half-span
            'SpecNumPoints': 101,
            'linewidth': 5.0,  # MHz
            'noise_level': 0.03,
            'qubit_freqs': [4500.0],
            'Qubit_Readout_List': [1],
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False):
        cfg = self.cfg

        f0 = cfg['qubit_freq_center']
        x_pts = np.linspace(f0 - cfg['SpecSpan'], f0 + cfg['SpecSpan'], cfg['SpecNumPoints'])

        # Lorentzian peak
        gamma = cfg['linewidth'] / 2
        lorentzian = gamma ** 2 / ((x_pts - f0) ** 2 + gamma ** 2)

        noise = cfg['noise_level'] * np.random.randn(len(x_pts))

        # I shows dispersive feature, Q shows absorption
        avgi = 0.3 * (x_pts - f0) * lorentzian + noise
        avgq = lorentzian + cfg['noise_level'] * np.random.randn(len(x_pts))

        # Find peak
        contrast = np.sqrt(avgi ** 2 + avgq ** 2)
        peak_idx = np.argmax(contrast)
        self.qubitFreq = x_pts[peak_idx]

        data = {
            'config': cfg,
            'data': {
                'x_pts': x_pts,
                'avgi': avgi,
                'avgq': avgq
            }
        }
        self.data = data
        return data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig, ax = plt.subplots(figsize=(9, 5), num=figNum)

        ax.plot(x_pts, avgi, '.-', color='orange', label='I', linewidth=1, markersize=4)
        ax.plot(x_pts, avgq, '.-', color='blue', label='Q', linewidth=1, markersize=4)
        ax.axvline(self.qubitFreq, color='black', linestyle='--',
                   label=f'Peak: {self.qubitFreq:.1f} MHz')

        ax.set_xlabel('Frequency (MHz)', fontsize=12)
        ax.set_ylabel('Signal (a.u.)', fontsize=12)
        ax.set_title(f'Mock Experiment', fontsize=10)
        ax.legend(fontsize=10)

        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)

        return fig, ax


# ============================================================================
# 4. AMPLITUDE RABI EXPERIMENT (Cosine oscillation fit)
# ============================================================================

class MockAmplitudeRabiExperiment(MockExperimentClass):
    """
    Mock amplitude Rabi experiment.

    Plotting: Oscillation with π-pulse gain marker
    Data: Cosine vs drive amplitude
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'pi_gain_true': 15000,  # DAC units
            'max_gain': 30000,
            'expts': 61,
            'noise_level': 0.06,
            'qubit_freqs': [4500.0],
            'Qubit_Readout_List': [1],
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False):
        cfg = self.cfg

        x_pts = np.linspace(0, cfg['max_gain'], cfg['expts'])

        # Rabi oscillation
        pi_gain = cfg['pi_gain_true']
        signal = np.cos(np.pi * x_pts / pi_gain)
        noise = cfg['noise_level'] * np.random.randn(len(x_pts))

        avgi = signal + noise
        avgq = 0.2 * np.sin(np.pi * x_pts / pi_gain) + 0.5 * cfg['noise_level'] * np.random.randn(len(x_pts))

        data = {
            'config': cfg,
            'data': {
                'x_pts': x_pts,
                'avgi': avgi,
                'avgq': avgq
            }
        }
        self.data = data

        # Fit
        contrast = np.sqrt((avgi - np.mean(avgi)) ** 2 + (avgq - np.mean(avgq)) ** 2)
        try:
            def fit_func(g, A, pi_g):
                return A * np.cos(np.pi * g / pi_g)

            popt, _ = curve_fit(fit_func, x_pts, avgi, p0=[1.0, pi_gain])
            self.pi_gain_fit = abs(popt[1])
            self.ampl_fit = popt[0]
            data['data']['pi_gain_fit'] = self.pi_gain_fit
            data['data']['ampl_fit'] = self.ampl_fit
        except Exception:
            self.pi_gain_fit = None

        return data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        avgi = data['data']['avgi']
        avgq = data['data']['avgq']

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig, ax = plt.subplots(figsize=(9, 5), num=figNum)

        contrast = avgi  # Use I channel for main signal

        ax.plot(x_pts, contrast, 'o', color='seagreen', markersize=5, label='IQ contrast')
        ax.plot(x_pts, avgi - np.mean(avgi), 'o', color='orange', alpha=0.4, markersize=3, label='I')
        ax.plot(x_pts, avgq - np.mean(avgq), 'o', color='blue', alpha=0.4, markersize=3, label='Q')

        if 'pi_gain_fit' in data['data']:
            pi_gain = data['data']['pi_gain_fit']
            ampl = data['data']['ampl_fit']
            g_fine = np.linspace(x_pts[0], x_pts[-1], 200)
            ax.plot(g_fine, ampl * np.cos(np.pi * g_fine / pi_gain), '--',
                    color='black', linewidth=2)
            ax.axvline(pi_gain, color='red', linestyle='-', linewidth=2,
                       label=f'π gain = {int(pi_gain)}')

        ax.set_xlabel('Qubit Gain (DAC units)', fontsize=12)
        ax.set_ylabel('Signal (a.u.)', fontsize=12)
        ax.set_title(f'Mock Experiment', fontsize=10)
        ax.legend(fontsize=10)
        ax.axhline(0, color='gray', linestyle=':', alpha=0.5)

        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)

        return fig, ax


# ============================================================================
# 5. 2D HEATMAP EXPERIMENT (Spec vs Parameter)
# ============================================================================

class MockSpec2DExperiment(MockExperimentClass):
    """
    Mock 2D spectroscopy experiment (e.g., spec vs flux).

    Plotting: 2D color heatmap with colorbar
    Data: 2D array showing avoided crossing pattern
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'freq_center': 4500.0,  # MHz
            'freq_span': 100.0,  # MHz
            'freq_points': 101,
            'flux_start': -1.0,
            'flux_stop': 1.0,
            'flux_points': 51,
            'coupling': 30.0,  # MHz, avoided crossing gap
            'noise_level': 0.02,
            'Qubit_Readout_List': [1],
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False):
        cfg = self.cfg

        freq_pts = np.linspace(cfg['freq_center'] - cfg['freq_span'],
                               cfg['freq_center'] + cfg['freq_span'],
                               cfg['freq_points'])
        flux_pts = np.linspace(cfg['flux_start'], cfg['flux_stop'], cfg['flux_points'])

        # Create avoided crossing pattern
        F, Freq = np.meshgrid(flux_pts, freq_pts, indexing='ij')

        # Two coupled modes
        f1 = cfg['freq_center'] + 80 * F
        f2 = cfg['freq_center'] - 80 * F
        g = cfg['coupling']

        # Hybridized frequencies
        delta = f1 - f2
        f_plus = 0.5 * (f1 + f2) + 0.5 * np.sqrt(delta ** 2 + 4 * g ** 2)
        f_minus = 0.5 * (f1 + f2) - 0.5 * np.sqrt(delta ** 2 + 4 * g ** 2)

        # Lorentzian response at each point
        linewidth = 3.0
        signal = (linewidth ** 2 / ((Freq - f_plus) ** 2 + linewidth ** 2) +
                  linewidth ** 2 / ((Freq - f_minus) ** 2 + linewidth ** 2))

        noise = cfg['noise_level'] * np.random.randn(*signal.shape)
        Z_mat = signal + noise

        data = {
            'config': cfg,
            'data': {
                'freq_pts': freq_pts,
                'flux_pts': flux_pts,
                'contrast': [Z_mat],  # Wrapped in list for MUX compatibility
                'readout_list': cfg['Qubit_Readout_List']
            }
        }
        self.data = data
        return data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data

        freq_pts = data['data']['freq_pts']
        flux_pts = data['data']['flux_pts']
        Z_mat = data['data']['contrast'][0]

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig, ax = plt.subplots(figsize=(10, 7), num=figNum)

        freq_step = freq_pts[1] - freq_pts[0]
        flux_step = flux_pts[1] - flux_pts[0]

        im = ax.imshow(Z_mat, aspect='auto', origin='lower',
                       extent=[freq_pts[0] - freq_step / 2, freq_pts[-1] + freq_step / 2,
                               flux_pts[0] - flux_step / 2, flux_pts[-1] + flux_step / 2],
                       cmap='viridis', interpolation='none')

        cbar = fig.colorbar(im, ax=ax, extend='both')
        cbar.set_label('IQ Contrast (a.u.)', rotation=90, fontsize=11)

        ax.set_xlabel('Frequency (MHz)', fontsize=12)
        ax.set_ylabel('Flux (a.u.)', fontsize=12)
        ax.set_title(f'Mock Experiment', fontsize=10)

        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)

        return fig, ax


# ============================================================================
# 6. SINGLE SHOT IQ SCATTER EXPERIMENT
# ============================================================================

class MockSingleShotExperiment(MockExperimentClass):
    """
    Mock single shot experiment with IQ scatter plots.

    Plotting: 2D scatter + histograms for ground/excited state discrimination
    Data: Two blob IQ distributions
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'Shots': 5000,
            'i_g_center': 0.0,
            'q_g_center': 0.0,
            'i_e_center': 1.0,
            'q_e_center': 0.5,
            'sigma': 0.25,  # Blob width
            'Qubit_Readout_List': [1],
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False):
        cfg = self.cfg
        n_shots = cfg['Shots']
        sigma = cfg['sigma']

        # Ground state blob
        i_g = cfg['i_g_center'] + sigma * np.random.randn(n_shots)
        q_g = cfg['q_g_center'] + sigma * np.random.randn(n_shots)

        # Excited state blob
        i_e = cfg['i_e_center'] + sigma * np.random.randn(n_shots)
        q_e = cfg['q_e_center'] + sigma * np.random.randn(n_shots)

        # Calculate optimal angle and threshold
        i_diff = np.mean(i_e) - np.mean(i_g)
        q_diff = np.mean(q_e) - np.mean(q_g)
        angle = np.arctan2(q_diff, i_diff)

        # Rotate data
        i_g_rot = i_g * np.cos(angle) + q_g * np.sin(angle)
        i_e_rot = i_e * np.cos(angle) + q_e * np.sin(angle)

        threshold = 0.5 * (np.mean(i_g_rot) + np.mean(i_e_rot))

        # Fidelity estimate
        fid_g = np.mean(i_g_rot < threshold)
        fid_e = np.mean(i_e_rot > threshold)
        fidelity = 0.5 * (fid_g + fid_e)

        data = {
            'config': cfg,
            'data': {
                'i_g1': i_g,
                'q_g1': q_g,
                'i_e1': i_e,
                'q_e1': q_e,
                'angle': [angle],
                'threshold': [threshold],
                'fid': [fidelity]
            }
        }
        self.data = data
        self.fid = [fidelity]
        self.angle = [angle]
        self.threshold = [threshold]
        return data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data

        i_g = data['data']['i_g1']
        q_g = data['data']['q_g1']
        i_e = data['data']['i_e1']
        q_e = data['data']['q_e1']
        fidelity = data['data']['fid'][0]
        angle = data['data']['angle'][0]
        threshold = data['data']['threshold'][0]

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig = plt.figure(figsize=(12, 5), num=figNum)

        # IQ scatter plot
        ax1 = fig.add_subplot(121)
        ax1.scatter(i_g, q_g, s=1, alpha=0.3, label='Ground', color='blue')
        ax1.scatter(i_e, q_e, s=1, alpha=0.3, label='Excited', color='red')

        # Draw discrimination line
        line_length = 2
        x_line = threshold * np.cos(angle) + np.array([-line_length, line_length]) * np.sin(angle)
        y_line = threshold * np.sin(angle) - np.array([-line_length, line_length]) * np.cos(angle)
        ax1.plot(x_line, y_line, 'k--', linewidth=2, label='Threshold')

        ax1.set_xlabel('I (a.u.)', fontsize=11)
        ax1.set_ylabel('Q (a.u.)', fontsize=11)
        ax1.legend(fontsize=9, markerscale=5)
        ax1.set_title(f'IQ Scatter - Fidelity: {fidelity:.1%}', fontsize=11)
        ax1.set_aspect('equal')
        ax1.grid(True, alpha=0.3)

        # Rotated histogram
        ax2 = fig.add_subplot(122)
        i_g_rot = i_g * np.cos(angle) + q_g * np.sin(angle)
        i_e_rot = i_e * np.cos(angle) + q_e * np.sin(angle)

        bins = np.linspace(min(i_g_rot.min(), i_e_rot.min()),
                           max(i_g_rot.max(), i_e_rot.max()), 50)
        ax2.hist(i_g_rot, bins=bins, alpha=0.5, label='Ground', color='blue', density=True)
        ax2.hist(i_e_rot, bins=bins, alpha=0.5, label='Excited', color='red', density=True)
        ax2.axvline(threshold, color='black', linestyle='--', linewidth=2, label='Threshold')

        ax2.set_xlabel('Rotated I (a.u.)', fontsize=11)
        ax2.set_ylabel('Density', fontsize=11)
        ax2.legend(fontsize=10)
        ax2.set_title('Rotated Histogram', fontsize=11)

        plt.suptitle(f'Mock Experiment', fontsize=10)
        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)

        return fig, (ax1, ax2)


# ============================================================================
# 7. TRANSMISSION EXPERIMENT (Multi-trace I/Q)
# ============================================================================

class MockTransmissionExperiment(MockExperimentClass):
    """
    Mock cavity transmission experiment.

    Plotting: I, Q, and magnitude vs frequency
    Data: Lorentzian dip/peak
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'res_freq_center': 7000.0,  # MHz
            'TransSpan': 20.0,  # MHz
            'TransNumPoints': 101,
            'linewidth': 2.0,  # MHz
            'noise_level': 0.02,
            'res_LO': 0,
            'Qubit_Readout_List': [1],
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False):
        cfg = self.cfg

        f0 = cfg['res_freq_center']
        fpts = np.linspace(f0 - cfg['TransSpan'], f0 + cfg['TransSpan'], cfg['TransNumPoints'])

        # Lorentzian transmission dip
        gamma = cfg['linewidth'] / 2
        lorentzian = 1 - 0.8 * gamma ** 2 / ((fpts - f0) ** 2 + gamma ** 2)

        # I and Q with phase rotation across resonance
        phase = np.arctan2(fpts - f0, gamma)
        avgi = lorentzian * np.cos(phase) + cfg['noise_level'] * np.random.randn(len(fpts))
        avgq = lorentzian * np.sin(phase) + cfg['noise_level'] * np.random.randn(len(fpts))

        # Results in shape expected by display
        results = np.zeros((len(fpts), 1, 1, 2))
        results[:, 0, 0, 0] = avgi
        results[:, 0, 0, 1] = avgq

        # Find minimum
        amp = np.sqrt(avgi ** 2 + avgq ** 2)
        self.peakFreq_min = fpts[np.argmin(amp)]
        self.peakFreq_max = fpts[np.argmax(amp)]

        data = {
            'config': cfg,
            'data': {
                'results': results,
                'fpts': fpts
            }
        }
        self.data = data
        return data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data

        fpts = data['data']['fpts']
        avgi = data['data']['results'][:, 0, 0, 0]
        avgq = data['data']['results'][:, 0, 0, 1]
        amp = np.sqrt(avgi ** 2 + avgq ** 2)

        # Convert to GHz for display
        x_pts = (fpts + self.cfg.get('res_LO', 0)) / 1e3
        freq_min = (self.peakFreq_min + self.cfg.get('res_LO', 0)) / 1e3

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig, ax = plt.subplots(figsize=(9, 5), num=figNum)

        ax.plot(x_pts, avgi, '.-', color='green', label='I', markersize=3)
        ax.plot(x_pts, avgq, '.-', color='blue', label='Q', markersize=3)
        ax.plot(x_pts, amp, '-', color='magenta', linewidth=2, label='Magnitude')
        ax.axvline(freq_min, color='black', linestyle='--',
                   label=f'Min: {1e3 * freq_min:.1f} MHz')

        ax.set_xlabel('Frequency (GHz)', fontsize=12)
        ax.set_ylabel('Transmission (a.u.)', fontsize=12)
        ax.set_title(f'Mock Experiment', fontsize=10)
        ax.legend(fontsize=10)

        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)

        return fig, ax


# ============================================================================
# 8. MUX MULTI-QUBIT EXPERIMENT (Multiple subplots)
# ============================================================================

class MockMUXSpectroscopyExperiment(MockExperimentClass):
    """
    Mock multiplexed spectroscopy for multiple qubits.

    Plotting: Grid of subplots, one per readout channel
    Data: Different peak positions for each qubit
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'qubit_freqs': [4200.0, 4400.0, 4600.0, 4800.0],  # MHz for each qubit
            'SpecSpan': 30.0,
            'SpecNumPoints': 81,
            'linewidths': [3.0, 4.0, 3.5, 5.0],  # MHz
            'noise_level': 0.04,
            'Qubit_Readout_List': [1, 2, 3, 4],
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False):
        cfg = self.cfg
        n_qubits = len(cfg['Qubit_Readout_List'])

        # Use first qubit freq as center for common sweep
        f_center = cfg['qubit_freqs'][0]
        x_pts = np.linspace(f_center - cfg['SpecSpan'], f_center + cfg['SpecSpan'], cfg['SpecNumPoints'])

        contrast_list = []
        I_list = []
        Q_list = []

        for i in range(n_qubits):
            f0 = cfg['qubit_freqs'][i] if i < len(cfg['qubit_freqs']) else cfg['qubit_freqs'][0]
            lw = cfg['linewidths'][i] if i < len(cfg['linewidths']) else 3.0

            gamma = lw / 2
            lorentzian = gamma ** 2 / ((x_pts - f0) ** 2 + gamma ** 2)

            noise = cfg['noise_level'] * np.random.randn(len(x_pts))
            avgi = 0.3 * (x_pts - f0) * lorentzian / gamma + noise
            avgq = lorentzian + cfg['noise_level'] * np.random.randn(len(x_pts))

            contrast = np.sqrt(avgi ** 2 + avgq ** 2)

            I_list.append(avgi)
            Q_list.append(avgq)
            contrast_list.append(contrast)

        data = {
            'config': cfg,
            'data': {
                'x_pts': x_pts,
                'contrast': contrast_list,
                'I': I_list,
                'Q': Q_list,
                'readout_list': cfg['Qubit_Readout_List']
            }
        }
        self.data = data
        return data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        contrast_list = data['data']['contrast']
        readout_list = data['data']['readout_list']
        n_qubits = len(readout_list)

        while plt.fignum_exists(num=figNum):
            figNum += 1

        # Create subplot grid
        if n_qubits == 1:
            fig, axs = plt.subplots(1, 1, figsize=(8, 5), num=figNum)
            axs = [axs]
        elif n_qubits == 2:
            fig, axs = plt.subplots(1, 2, figsize=(14, 5), num=figNum)
        elif n_qubits <= 4:
            fig, axs = plt.subplots(2, 2, figsize=(12, 10), num=figNum)
            axs = axs.flatten()
        else:
            cols = 3
            rows = (n_qubits + cols - 1) // cols
            fig, axs = plt.subplots(rows, cols, figsize=(15, 4 * rows), num=figNum)
            axs = axs.flatten()

        colors = plt.cm.tab10(np.linspace(0, 1, n_qubits))

        for i, (ro_ch, contrast) in enumerate(zip(readout_list, contrast_list)):
            if i < len(axs):
                ax = axs[i]
                ax.plot(x_pts, contrast, 'o-', color=colors[i], markersize=4)

                # Find and mark peak
                peak_idx = np.argmax(contrast)
                peak_freq = x_pts[peak_idx]
                ax.axvline(peak_freq, color='black', linestyle='--', alpha=0.7)

                ax.set_xlabel('Frequency (MHz)', fontsize=11)
                ax.set_ylabel('Contrast (a.u.)', fontsize=11)
                ax.set_title(f'Readout {ro_ch} - Peak: {peak_freq:.1f} MHz', fontsize=11)

        # Hide extra axes
        for i in range(n_qubits, len(axs)):
            axs[i].set_visible(False)

        fig.suptitle(f'Mock Experiment', fontsize=12)
        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)

        return fig, axs


# ============================================================================
# 9. CORRELATION EXPERIMENT (Multi-panel: populations + correlations)
# ============================================================================

class MockCorrelationExperiment(MockExperimentClass):
    """
    Mock correlation experiment with population and correlation panels.

    Plotting: Two-panel figure - populations and correlations vs time
    Data: Simulated beamsplitter dynamics with correlations
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'start': 0,
            'stop': 500,
            'expts': 51,
            'coupling_strength': 0.05,
            'decoherence_rate': 0.002,
            'noise_level': 0.03,
            'Qubit_Readout_List': [1, 2, 3, 4],
            'readout_pair_1': [1, 2],
            'readout_pair_2': [3, 4],
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False):
        cfg = self.cfg

        t_pts = np.linspace(cfg['start'], cfg['stop'], cfg['expts'])
        g = cfg['coupling_strength']
        gamma = cfg['decoherence_rate']

        # Simulate coupled qubit dynamics
        # Population oscillates between sites
        p1 = 0.5 * (1 + np.cos(2 * g * t_pts) * np.exp(-gamma * t_pts))
        p2 = 0.5 * (1 - np.cos(2 * g * t_pts) * np.exp(-gamma * t_pts))
        p3 = 0.5 * (1 + 0.8 * np.cos(2 * g * t_pts + 0.3) * np.exp(-gamma * t_pts))
        p4 = 0.5 * (1 - 0.8 * np.cos(2 * g * t_pts + 0.3) * np.exp(-gamma * t_pts))

        # Add noise
        noise = cfg['noise_level']
        populations = [
            p1 + noise * np.random.randn(len(t_pts)),
            p2 + noise * np.random.randn(len(t_pts)),
            p3 + noise * np.random.randn(len(t_pts)),
            p4 + noise * np.random.randn(len(t_pts)),
        ]

        # Current correlations (product of pair differences)
        n12 = populations[0] - populations[1]  # Current on pair 1
        n34 = populations[2] - populations[3]  # Current on pair 2

        nn_correlations = n12 * n34

        # "Corrected" correlations (slightly different)
        corrected_nn = nn_correlations * 1.1 - 0.02

        data = {
            'config': cfg,
            'data': {
                't_pts': t_pts,
                'population': populations,
                'population_corrected': populations,
                'nn_correlations': nn_correlations,
                'corrected_nn': corrected_nn,
                'readout_list': cfg['Qubit_Readout_List']
            }
        }
        self.data = data
        return data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data

        t_pts = data['data']['t_pts']
        populations = data['data']['population']
        nn_corr = data['data']['nn_correlations']
        corrected_nn = data['data']['corrected_nn']
        readout_list = data['data']['readout_list']

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), num=figNum)

        # Population panel
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
        for i, (pop, ro_ch) in enumerate(zip(populations, readout_list)):
            ax1.plot(t_pts, pop, 'o-', color=colors[i % len(colors)],
                     markersize=4, label=f'Q{ro_ch}')

        ax1.set_xlabel('Time (samples)', fontsize=11)
        ax1.set_ylabel('Population', fontsize=11)
        ax1.set_title('Qubit Populations', fontsize=11)
        ax1.legend(fontsize=9, ncol=2)
        ax1.set_ylim(-0.1, 1.1)

        # Correlation panel
        q1, q2 = self.cfg['readout_pair_1']
        q3, q4 = self.cfg['readout_pair_2']
        ylabel = rf'$\langle n_{{{q2}{q1}}} n_{{{q4}{q3}}}\rangle$'

        ax2.plot(t_pts, nn_corr, 'o-', color='black', markersize=4, label='Raw')
        ax2.plot(t_pts, corrected_nn, 'o-', color='blue', markersize=4, label='Corrected')
        ax2.axhline(0, color='gray', linestyle=':', alpha=0.5)

        ax2.set_xlabel('Time (samples)', fontsize=11)
        ax2.set_ylabel(ylabel, fontsize=11)
        ax2.set_title('Current-Current Correlations', fontsize=11)
        ax2.legend(fontsize=10)

        fig.suptitle(f'Mock Experiment', fontsize=12)
        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)

        return fig, (ax1, ax2)


# ============================================================================
# 10. PULSE VISUALIZATION EXPERIMENT (Time-domain waveforms)
# ============================================================================

class MockPulseVisualizationExperiment(MockExperimentClass):
    """
    Mock experiment showing pulse waveforms in time domain.

    Plotting: Multiple waveform traces
    Data: Various pulse shapes (Gaussian, flat-top, etc.)
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'sigma': 0.05,  # us
            'flat_length': 0.2,  # us
            'total_length': 1.0,  # us
            'n_points': 500,
            'n_channels': 4,
            'Qubit_Readout_List': [1, 2, 3, 4],
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False):
        cfg = self.cfg

        t_pts = np.linspace(0, cfg['total_length'], cfg['n_points'])
        sigma = cfg['sigma']
        flat = cfg['flat_length']

        waveforms = []

        for ch in range(cfg['n_channels']):
            # Different pulse types for each channel
            if ch == 0:
                # Gaussian
                t0 = 0.3
                wf = np.exp(-(t_pts - t0) ** 2 / (2 * sigma ** 2))
            elif ch == 1:
                # Flat-top Gaussian
                t_rise = 0.2
                t_fall = t_rise + flat
                wf = np.zeros_like(t_pts)
                wf += np.exp(-(t_pts - t_rise) ** 2 / (2 * sigma ** 2)) * (t_pts < t_rise)
                wf += (t_pts >= t_rise) * (t_pts <= t_fall) * 1.0
                wf += np.exp(-(t_pts - t_fall) ** 2 / (2 * sigma ** 2)) * (t_pts > t_fall)
            elif ch == 2:
                # DRAG-like (derivative)
                t0 = 0.5
                wf = -(t_pts - t0) / sigma ** 2 * np.exp(-(t_pts - t0) ** 2 / (2 * sigma ** 2))
            else:
                # Square pulse
                wf = ((t_pts > 0.4) & (t_pts < 0.6)).astype(float)

            waveforms.append(wf * (0.8 + 0.2 * ch))  # Scale differently

        data = {
            'config': cfg,
            'data': {
                't_pts': t_pts,
                'waveforms': waveforms,
                'channel_names': [f'Ch {i + 1}' for i in range(cfg['n_channels'])]
            }
        }
        self.data = data
        return data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data

        t_pts = data['data']['t_pts'] * 1000  # Convert to ns
        waveforms = data['data']['waveforms']
        channel_names = data['data']['channel_names']

        while plt.fignum_exists(num=figNum):
            figNum += 1

        n_ch = len(waveforms)
        fig, axs = plt.subplots(n_ch, 1, figsize=(10, 2.5 * n_ch), num=figNum, sharex=True)
        if n_ch == 1:
            axs = [axs]

        colors = plt.cm.viridis(np.linspace(0.2, 0.8, n_ch))

        for i, (wf, name) in enumerate(zip(waveforms, channel_names)):
            axs[i].plot(t_pts, wf, '-', color=colors[i], linewidth=1.5)
            axs[i].fill_between(t_pts, 0, wf, alpha=0.3, color=colors[i])
            axs[i].set_ylabel(name, fontsize=11)
            axs[i].set_xlim(t_pts[0], t_pts[-1])
            axs[i].grid(True, alpha=0.3)

        axs[-1].set_xlabel('Time (ns)', fontsize=11)
        fig.suptitle(f'Mock Experiment - Pulse Waveforms', fontsize=12)
        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)

        return fig, axs


# ============================================================================
# 11. POPULATION VS SWEEP (1D Line plot with markers)
# ============================================================================

class MockPopulationSweepExperiment(MockExperimentClass):
    """
    Mock population vs parameter sweep.

    Plotting: Simple line plot with error indicators
    Data: Population vs some swept parameter
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'sweep_start': 0,
            'sweep_stop': 100,
            'sweep_points': 41,
            'transition_center': 50,
            'transition_width': 10,
            'noise_level': 0.03,
            'Qubit_Readout_List': [1, 2],
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False):
        cfg = self.cfg

        x_pts = np.linspace(cfg['sweep_start'], cfg['sweep_stop'], cfg['sweep_points'])
        center = cfg['transition_center']
        width = cfg['transition_width']

        # Sigmoid transition
        populations = []
        for i, ro in enumerate(cfg['Qubit_Readout_List']):
            offset = 5 * i  # Slight offset per qubit
            pop = 1 / (1 + np.exp(-(x_pts - center - offset) / width))
            pop += cfg['noise_level'] * np.random.randn(len(x_pts))
            pop = np.clip(pop, 0, 1)
            populations.append(pop)

        data = {
            'config': cfg,
            'data': {
                'x_pts': x_pts,
                'population': populations,
                'population_corrected': populations,
                'readout_list': cfg['Qubit_Readout_List']
            }
        }
        self.data = data
        return data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data

        x_pts = data['data']['x_pts']
        populations = data['data']['population']
        readout_list = data['data']['readout_list']

        while plt.fignum_exists(num=figNum):
            figNum += 1

        n_ro = len(readout_list)
        fig, axs = plt.subplots(1, n_ro, figsize=(6 * n_ro, 5), num=figNum, squeeze=False)
        axs = axs.flatten()

        colors = plt.cm.tab10(np.linspace(0, 1, n_ro))

        for i, (pop, ro_ch) in enumerate(zip(populations, readout_list)):
            ax = axs[i]
            ax.plot(x_pts, pop, 'o-', color=colors[i], markersize=5, label=f'Read: {ro_ch}')
            ax.axhline(0.5, color='gray', linestyle=':', alpha=0.5)

            ax.set_xlabel('Sweep Parameter (a.u.)', fontsize=11)
            ax.set_ylabel('Population', fontsize=11)
            ax.set_ylim(-0.05, 1.05)
            ax.legend(fontsize=10)
            ax.set_title(f'Qubit {ro_ch}', fontsize=11)

        fig.suptitle(f'Mock Experiment', fontsize=12)
        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)

        return fig, axs


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def run_all_mock_experiments(plotDisp=True, block=False):
    """
    Run all mock experiments to test plotting functionality.

    Parameters
    ----------
    plotDisp : bool
        Whether to display plots
    block : bool
        Whether to block on each plot

    Returns
    -------
    dict
        Dictionary of experiment instances keyed by name
    """
    experiments = {}

    print("=" * 60)
    print("Running Mock Experiments for GUI Testing")
    print("=" * 60)

    # 1. T1
    print("\n1. MockT1Experiment...")
    exp = MockT1Experiment(path='MockT1', prefix='test')
    exp.acquire()
    exp.display(plotDisp=plotDisp, block=block)
    experiments['T1'] = exp

    # 2. T2 Ramsey
    print("\n2. MockT2RamseyExperiment...")
    exp = MockT2RamseyExperiment(path='MockT2', prefix='test')
    exp.acquire()
    exp.display(plotDisp=plotDisp, block=block)
    experiments['T2'] = exp

    # 3. Spectroscopy
    print("\n3. MockSpectroscopyExperiment...")
    exp = MockSpectroscopyExperiment(path='MockSpec', prefix='test')
    exp.acquire()
    exp.display(plotDisp=plotDisp, block=block)
    experiments['Spec'] = exp

    # 4. Amplitude Rabi
    print("\n4. MockAmplitudeRabiExperiment...")
    exp = MockAmplitudeRabiExperiment(path='MockRabi', prefix='test')
    exp.acquire()
    exp.display(plotDisp=plotDisp, block=block)
    experiments['Rabi'] = exp

    # 5. 2D Spec
    print("\n5. MockSpec2DExperiment...")
    exp = MockSpec2DExperiment(path='MockSpec2D', prefix='test')
    exp.acquire()
    exp.display(plotDisp=plotDisp, block=block)
    experiments['Spec2D'] = exp

    # 6. Single Shot
    print("\n6. MockSingleShotExperiment...")
    exp = MockSingleShotExperiment(path='MockSS', prefix='test')
    exp.acquire()
    exp.display(plotDisp=plotDisp, block=block)
    experiments['SingleShot'] = exp

    # 7. Transmission
    print("\n7. MockTransmissionExperiment...")
    exp = MockTransmissionExperiment(path='MockTrans', prefix='test')
    exp.acquire()
    exp.display(plotDisp=plotDisp, block=block)
    experiments['Transmission'] = exp

    # 8. MUX Spectroscopy
    print("\n8. MockMUXSpectroscopyExperiment...")
    exp = MockMUXSpectroscopyExperiment(path='MockMUXSpec', prefix='test')
    exp.acquire()
    exp.display(plotDisp=plotDisp, block=block)
    experiments['MUXSpec'] = exp

    # 9. Correlations
    print("\n9. MockCorrelationExperiment...")
    exp = MockCorrelationExperiment(path='MockCorr', prefix='test')
    exp.acquire()
    exp.display(plotDisp=plotDisp, block=block)
    experiments['Correlation'] = exp

    # 10. Pulse Visualization
    print("\n10. MockPulseVisualizationExperiment...")
    exp = MockPulseVisualizationExperiment(path='MockPulse', prefix='test')
    exp.acquire()
    exp.display(plotDisp=plotDisp, block=block)
    experiments['Pulse'] = exp

    # 11. Population Sweep
    print("\n11. MockPopulationSweepExperiment...")
    exp = MockPopulationSweepExperiment(path='MockPopSweep', prefix='test')
    exp.acquire()
    exp.display(plotDisp=plotDisp, block=block)
    experiments['PopSweep'] = exp

    print("\n" + "=" * 60)
    print("All mock experiments completed!")
    print("=" * 60)

    return experiments


def get_mock_experiment_list():
    """
    Returns list of available mock experiment classes.
    """
    return [
        MockT1Experiment,
        MockT2RamseyExperiment,
        MockSpectroscopyExperiment,
        MockAmplitudeRabiExperiment,
        MockSpec2DExperiment,
        MockSingleShotExperiment,
        MockTransmissionExperiment,
        MockMUXSpectroscopyExperiment,
        MockCorrelationExperiment,
        MockPulseVisualizationExperiment,
        MockPopulationSweepExperiment,
    ]


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    # Run all experiments when executed directly
    experiments = run_all_mock_experiments(plotDisp=True, block=True)