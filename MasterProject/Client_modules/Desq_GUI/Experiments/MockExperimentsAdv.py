"""
MockExperimentAdvanced.py - Advanced mock experiments for testing GUI figure handling

These experiments focus on testing the GUI's ability to handle:
1. Figures with different grid configurations (1x1, 1x2, 2x2, 2x3, 3x3, GridSpec layouts)
2. Experiments that create multiple separate figures
3. Experiments with live plotting (updating during sweeps/loops)

Unlike MockExperiments.py which tests plot appearance, this module tests the
backend's ability to properly route, update, and manage complex figure scenarios.
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import time
from scipy.optimize import curve_fit


# ============================================================================
# BASE CLASS
# ============================================================================

from MasterProject.Client_modules.Desq_GUI.CoreLib.Experiment import ExperimentClass

# Use ExperimentClass as the base, with a default outerFolder for mock usage
class MockExperimentBase(ExperimentClass):
    """Thin wrapper that provides default outerFolder for mock experiments."""
    def __init__(self, outerFolder='', **kwargs):
        super().__init__(outerFolder=outerFolder, **kwargs)
        self.titlename = kwargs.get('titlename', self.__class__.__name__)

# ============================================================================
# PART 1: DIFFERENT GRID CONFIGURATIONS
# ============================================================================

class MockGrid1x1(MockExperimentBase):
    """
    Single subplot (1x1 grid).

    Tests: Basic single-panel figure routing.
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'num_points': 100,
            'noise_level': 0.1,
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False):
        cfg = self.cfg
        x = np.linspace(0, 4 * np.pi, cfg['num_points'])
        y = np.sin(x) + cfg['noise_level'] * np.random.randn(len(x))

        self.data = {'config': cfg, 'data': {'x': x, 'y': y}}
        return self.data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig, ax = plt.subplots(1, 1, figsize=(8, 6), num=figNum)

        ax.plot(data['data']['x'], data['data']['y'], 'b.-', linewidth=1, markersize=3)
        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.set_title(f'{self.titlename} - 1x1 Grid')
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        if plotDisp:
            plt.show(block=block)

        return fig, ax


class MockGrid1x2(MockExperimentBase):
    """
    Two subplots side-by-side (1x2 grid).

    Tests: Horizontal subplot arrangement.
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'num_points': 50,
            'freq1': 1.0,
            'freq2': 2.5,
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False):
        cfg = self.cfg
        t = np.linspace(0, 2 * np.pi, cfg['num_points'])
        y1 = np.sin(cfg['freq1'] * t)
        y2 = np.cos(cfg['freq2'] * t)

        self.data = {'config': cfg, 'data': {'t': t, 'y1': y1, 'y2': y2}}
        return self.data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig, axs = plt.subplots(1, 2, figsize=(12, 5), num=figNum)

        t = data['data']['t']
        axs[0].plot(t, data['data']['y1'], 'r-', linewidth=2)
        axs[0].set_title('Signal 1')
        axs[0].set_xlabel('Time')
        axs[0].set_ylabel('Amplitude')

        axs[1].plot(t, data['data']['y2'], 'b-', linewidth=2)
        axs[1].set_title('Signal 2')
        axs[1].set_xlabel('Time')
        axs[1].set_ylabel('Amplitude')

        fig.suptitle(f'{self.titlename} - 1x2 Grid', fontsize=14)
        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)

        return fig, axs


class MockGrid2x1(MockExperimentBase):
    """
    Two subplots stacked vertically (2x1 grid).

    Tests: Vertical subplot arrangement.
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'num_points': 100,
            'decay_rate': 0.05,
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False):
        cfg = self.cfg
        t = np.linspace(0, 100, cfg['num_points'])
        signal = np.exp(-cfg['decay_rate'] * t) * np.cos(0.5 * t)
        envelope = np.exp(-cfg['decay_rate'] * t)

        self.data = {'config': cfg, 'data': {'t': t, 'signal': signal, 'envelope': envelope}}
        return self.data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig, axs = plt.subplots(2, 1, figsize=(10, 8), num=figNum, sharex=True)

        t = data['data']['t']
        axs[0].plot(t, data['data']['signal'], 'b-')
        axs[0].plot(t, data['data']['envelope'], 'r--', linewidth=2, label='Envelope')
        axs[0].plot(t, -data['data']['envelope'], 'r--', linewidth=2)
        axs[0].set_ylabel('Signal')
        axs[0].legend()
        axs[0].set_title('Damped Oscillation')

        # FFT of signal
        fft = np.abs(np.fft.rfft(data['data']['signal']))
        freqs = np.fft.rfftfreq(len(t), t[1] - t[0])
        axs[1].plot(freqs, fft, 'g-')
        axs[1].set_xlabel('Frequency')
        axs[1].set_ylabel('Magnitude')
        axs[1].set_title('Frequency Spectrum')
        axs[1].set_xlim(0, 1)

        fig.suptitle(f'{self.titlename} - 2x1 Grid', fontsize=14)
        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)

        return fig, axs


class MockGrid2x2(MockExperimentBase):
    """
    Four subplots in 2x2 arrangement.

    Tests: Standard 2x2 grid layout.
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'grid_size': 50,
            'num_blobs': 4,
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False):
        cfg = self.cfg
        np.random.seed(42)

        # Generate different datasets for each quadrant
        x = np.linspace(-5, 5, cfg['grid_size'])
        y = np.linspace(-5, 5, cfg['grid_size'])
        X, Y = np.meshgrid(x, y)

        # Heatmap
        Z1 = np.sin(X) * np.cos(Y)

        # Scatter data
        scatter_x = np.random.randn(200)
        scatter_y = np.random.randn(200)

        # Line data
        t = np.linspace(0, 10, 100)
        line_y = np.sin(t) * np.exp(-0.1 * t)

        # Histogram data
        hist_data = np.random.normal(0, 1, 1000)

        self.data = {
            'config': cfg,
            'data': {
                'x': x, 'y': y, 'Z1': Z1,
                'scatter_x': scatter_x, 'scatter_y': scatter_y,
                't': t, 'line_y': line_y,
                'hist_data': hist_data
            }
        }
        return self.data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig, axs = plt.subplots(2, 2, figsize=(12, 10), num=figNum)

        d = data['data']

        # Top-left: Heatmap
        im = axs[0, 0].imshow(d['Z1'], extent=[-5, 5, -5, 5], origin='lower', cmap='viridis')
        axs[0, 0].set_title('Heatmap')
        fig.colorbar(im, ax=axs[0, 0])

        # Top-right: Scatter
        axs[0, 1].scatter(d['scatter_x'], d['scatter_y'], alpha=0.5, c='purple', s=10)
        axs[0, 1].set_title('Scatter Plot')
        axs[0, 1].set_aspect('equal')

        # Bottom-left: Line plot
        axs[1, 0].plot(d['t'], d['line_y'], 'b-', linewidth=2)
        axs[1, 0].fill_between(d['t'], 0, d['line_y'], alpha=0.3)
        axs[1, 0].set_title('Line Plot with Fill')

        # Bottom-right: Histogram
        axs[1, 1].hist(d['hist_data'], bins=30, color='green', alpha=0.7, edgecolor='black')
        axs[1, 1].set_title('Histogram')

        fig.suptitle(f'{self.titlename} - 2x2 Grid', fontsize=14)
        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)

        return fig, axs


class MockGrid2x3(MockExperimentBase):
    """
    Six subplots in 2x3 arrangement.

    Tests: Wider grid configuration typical of MUX readouts.
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'num_channels': 6,
            'num_points': 50,
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False):
        cfg = self.cfg
        t = np.linspace(0, 10, cfg['num_points'])

        # Generate different signals for each channel
        signals = []
        for i in range(cfg['num_channels']):
            freq = 0.5 + 0.3 * i
            phase = i * np.pi / 6
            signal = np.sin(freq * t + phase) + 0.1 * np.random.randn(len(t))
            signals.append(signal)

        self.data = {'config': cfg, 'data': {'t': t, 'signals': signals}}
        return self.data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig, axs = plt.subplots(2, 3, figsize=(15, 8), num=figNum)
        axs = axs.flatten()

        t = data['data']['t']
        signals = data['data']['signals']
        colors = plt.cm.tab10(np.linspace(0, 1, len(signals)))

        for i, (signal, color) in enumerate(zip(signals, colors)):
            axs[i].plot(t, signal, color=color, linewidth=1.5)
            axs[i].set_title(f'Channel {i + 1}')
            axs[i].set_xlabel('Time')
            axs[i].set_ylabel('Amplitude')
            axs[i].grid(True, alpha=0.3)

        fig.suptitle(f'{self.titlename} - 2x3 Grid (MUX Style)', fontsize=14)
        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)

        return fig, axs


class MockGrid3x3(MockExperimentBase):
    """
    Nine subplots in 3x3 arrangement.

    Tests: Large grid configuration.
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'grid_size': 30,
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False):
        cfg = self.cfg
        np.random.seed(42)

        # Generate 9 different 2D patterns
        x = np.linspace(-3, 3, cfg['grid_size'])
        y = np.linspace(-3, 3, cfg['grid_size'])
        X, Y = np.meshgrid(x, y)

        patterns = [
            np.sin(X) * np.cos(Y),  # Checkerboard
            np.exp(-(X ** 2 + Y ** 2)),  # Gaussian
            X ** 2 - Y ** 2,  # Saddle
            np.sin(np.sqrt(X ** 2 + Y ** 2)),  # Circular waves
            np.tanh(X) * np.tanh(Y),  # Tanh product
            np.sin(X + Y),  # Diagonal stripes
            np.exp(-(X ** 2 + Y ** 2)) * np.cos(4 * X),  # Modulated Gaussian
            np.sign(X * Y),  # Quadrant pattern
            np.random.randn(cfg['grid_size'], cfg['grid_size']),  # Noise
        ]

        self.data = {'config': cfg, 'data': {'x': x, 'y': y, 'patterns': patterns}}
        return self.data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig, axs = plt.subplots(3, 3, figsize=(14, 12), num=figNum)
        axs = axs.flatten()

        x, y = data['data']['x'], data['data']['y']
        patterns = data['data']['patterns']
        titles = ['Checkerboard', 'Gaussian', 'Saddle', 'Circular', 'Tanh',
                  'Diagonal', 'Modulated', 'Quadrant', 'Noise']
        cmaps = ['RdBu', 'hot', 'coolwarm', 'viridis', 'PiYG',
                 'seismic', 'twilight', 'binary', 'gray']

        for i, (pattern, title, cmap) in enumerate(zip(patterns, titles, cmaps)):
            im = axs[i].imshow(pattern, extent=[x[0], x[-1], y[0], y[-1]],
                               origin='lower', cmap=cmap, aspect='equal')
            axs[i].set_title(title)
            fig.colorbar(im, ax=axs[i], shrink=0.8)

        fig.suptitle(f'{self.titlename} - 3x3 Grid', fontsize=14)
        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)

        return fig, axs


class MockGridSpec(MockExperimentBase):
    """
    Complex layout using GridSpec with mixed-size subplots.

    Tests: Non-uniform grid layout (like correlation experiments).
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'num_points': 100,
            'num_shots': 1000,
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False):
        cfg = self.cfg
        np.random.seed(42)

        # Time series
        t = np.linspace(0, 10, cfg['num_points'])
        signal = np.sin(t) * np.exp(-0.1 * t)

        # IQ scatter
        i_g = np.random.randn(cfg['num_shots']) * 0.3
        q_g = np.random.randn(cfg['num_shots']) * 0.3
        i_e = np.random.randn(cfg['num_shots']) * 0.3 + 1.0
        q_e = np.random.randn(cfg['num_shots']) * 0.3 + 0.5

        # 2D heatmap
        x = np.linspace(-5, 5, 50)
        y = np.linspace(-5, 5, 50)
        X, Y = np.meshgrid(x, y)
        Z = np.exp(-(X ** 2 + Y ** 2) / 4) * np.cos(2 * X)

        self.data = {
            'config': cfg,
            'data': {
                't': t, 'signal': signal,
                'i_g': i_g, 'q_g': q_g, 'i_e': i_e, 'q_e': q_e,
                'x': x, 'y': y, 'Z': Z
            }
        }
        return self.data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig = plt.figure(figsize=(14, 10), num=figNum)
        gs = GridSpec(3, 3, figure=fig)

        d = data['data']

        # Large panel: 2D heatmap (spans 2x2)
        ax1 = fig.add_subplot(gs[0:2, 0:2])
        im = ax1.imshow(d['Z'], extent=[d['x'][0], d['x'][-1], d['y'][0], d['y'][-1]],
                        origin='lower', cmap='viridis')
        ax1.set_title('Main 2D Plot (2x2 span)')
        fig.colorbar(im, ax=ax1)

        # Right column: IQ scatter (1x1)
        ax2 = fig.add_subplot(gs[0, 2])
        ax2.scatter(d['i_g'], d['q_g'], alpha=0.3, s=2, label='|g⟩')
        ax2.scatter(d['i_e'], d['q_e'], alpha=0.3, s=2, label='|e⟩')
        ax2.set_title('IQ Scatter')
        ax2.legend(markerscale=5)
        ax2.set_aspect('equal')

        # Right column: I histogram (1x1)
        ax3 = fig.add_subplot(gs[1, 2])
        ax3.hist(d['i_g'], bins=30, alpha=0.5, label='|g⟩')
        ax3.hist(d['i_e'], bins=30, alpha=0.5, label='|e⟩')
        ax3.set_title('I Histogram')
        ax3.legend()

        # Bottom row: Time signal (full width)
        ax4 = fig.add_subplot(gs[2, :])
        ax4.plot(d['t'], d['signal'], 'b-', linewidth=1.5)
        ax4.fill_between(d['t'], 0, d['signal'], alpha=0.3)
        ax4.set_title('Time Series (Full Width)')
        ax4.set_xlabel('Time')
        ax4.set_ylabel('Signal')

        fig.suptitle(f'{self.titlename} - GridSpec Layout', fontsize=14)
        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)

        return fig, (ax1, ax2, ax3, ax4)


class MockGrid2x4(MockExperimentBase):
    """
    Eight subplots in 2x4 arrangement.

    Tests: Maximum MUX qubit readout configuration.
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'num_qubits': 8,
            'num_points': 40,
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False):
        cfg = self.cfg

        freq_pts = np.linspace(4400, 4600, cfg['num_points'])

        # Generate spectroscopy peaks for each qubit
        spectra = []
        for i in range(cfg['num_qubits']):
            center = 4450 + 20 * i
            width = 3 + i * 0.5
            peak = width ** 2 / ((freq_pts - center) ** 2 + width ** 2)
            peak += 0.05 * np.random.randn(len(freq_pts))
            spectra.append(peak)

        self.data = {'config': cfg, 'data': {'freq_pts': freq_pts, 'spectra': spectra}}
        return self.data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig, axs = plt.subplots(2, 4, figsize=(20, 8), num=figNum)
        axs = axs.flatten()

        freq_pts = data['data']['freq_pts']
        spectra = data['data']['spectra']
        colors = plt.cm.Set1(np.linspace(0, 1, 8))

        for i, (spectrum, color) in enumerate(zip(spectra, colors)):
            axs[i].plot(freq_pts, spectrum, color=color, linewidth=1.5)
            axs[i].fill_between(freq_pts, 0, spectrum, alpha=0.3, color=color)
            axs[i].set_title(f'Qubit {i + 1}')
            axs[i].set_xlabel('Frequency (MHz)')
            axs[i].set_ylabel('Signal')
            axs[i].grid(True, alpha=0.3)

        fig.suptitle(f'{self.titlename} - 2x4 Grid (8-Qubit MUX)', fontsize=14)
        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)

        return fig, axs


# ============================================================================
# PART 2: MULTIPLE FIGURES
# ============================================================================

class MockMultiFigure2(MockExperimentBase):
    """
    Experiment that creates 2 separate figures.

    Tests: Backend's ability to route multiple figures from same experiment.
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'num_points': 100,
            'num_shots': 500,
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False):
        cfg = self.cfg
        np.random.seed(42)

        # Figure 1 data: Time series
        t = np.linspace(0, 10, cfg['num_points'])
        y1 = np.sin(t) * np.exp(-0.1 * t)
        y2 = np.cos(t) * np.exp(-0.1 * t)

        # Figure 2 data: IQ scatter
        i_g = np.random.randn(cfg['num_shots']) * 0.25
        q_g = np.random.randn(cfg['num_shots']) * 0.25
        i_e = np.random.randn(cfg['num_shots']) * 0.25 + 1.0
        q_e = np.random.randn(cfg['num_shots']) * 0.25 + 0.5

        self.data = {
            'config': cfg,
            'data': {
                't': t, 'y1': y1, 'y2': y2,
                'i_g': i_g, 'q_g': q_g, 'i_e': i_e, 'q_e': q_e
            }
        }
        return self.data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data

        d = data['data']
        figs = []

        # Figure 1: Time series
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig1, axs1 = plt.subplots(2, 1, figsize=(10, 6), num=figNum, sharex=True)

        axs1[0].plot(d['t'], d['y1'], 'b-', linewidth=1.5, label='I')
        axs1[0].set_ylabel('I Component')
        axs1[0].legend()

        axs1[1].plot(d['t'], d['y2'], 'r-', linewidth=1.5, label='Q')
        axs1[1].set_xlabel('Time')
        axs1[1].set_ylabel('Q Component')
        axs1[1].legend()

        fig1.suptitle(f'{self.titlename} - Figure 1: Time Series')
        plt.tight_layout()

        if plotDisp:
            plt.show(block=False)

        figs.append(fig1)

        # Figure 2: IQ scatter
        figNum += 1
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig2, ax2 = plt.subplots(figsize=(8, 8), num=figNum)

        ax2.scatter(d['i_g'], d['q_g'], alpha=0.5, s=10, label='|g⟩', c='blue')
        ax2.scatter(d['i_e'], d['q_e'], alpha=0.5, s=10, label='|e⟩', c='red')
        ax2.set_xlabel('I')
        ax2.set_ylabel('Q')
        ax2.set_title(f'{self.titlename} - Figure 2: IQ Scatter')
        ax2.legend()
        ax2.set_aspect('equal')
        ax2.grid(True, alpha=0.3)

        if plotDisp:
            plt.show(block=block)

        figs.append(fig2)

        return figs


class MockMultiFigure3(MockExperimentBase):
    """
    Experiment that creates 3 separate figures.

    Tests: Routing multiple figures with different sizes/layouts.
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'num_points': 80,
            'grid_size': 40,
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False):
        cfg = self.cfg
        np.random.seed(42)

        # Figure 1: 1D sweeps
        x = np.linspace(0, 10, cfg['num_points'])
        y_rabi = np.cos(2 * np.pi * x / 3) * 0.5 + 0.5
        y_t1 = np.exp(-x / 5)

        # Figure 2: 2D heatmap
        fx = np.linspace(4400, 4600, cfg['grid_size'])
        flux = np.linspace(-1, 1, cfg['grid_size'])
        FX, FLUX = np.meshgrid(fx, flux)
        spec2d = np.exp(-((FX - 4500 - 50 * FLUX) ** 2) / 100)

        # Figure 3: Histograms
        shots_g = np.random.randn(1000) * 0.3
        shots_e = np.random.randn(1000) * 0.3 + 1.0

        self.data = {
            'config': cfg,
            'data': {
                'x': x, 'y_rabi': y_rabi, 'y_t1': y_t1,
                'fx': fx, 'flux': flux, 'spec2d': spec2d,
                'shots_g': shots_g, 'shots_e': shots_e
            }
        }
        return self.data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        if data is None:
            data = self.data

        d = data['data']
        figs = []

        # Figure 1: Two 1D sweeps (1x2)
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig1, axs1 = plt.subplots(1, 2, figsize=(12, 5), num=figNum)

        axs1[0].plot(d['x'], d['y_rabi'], 'bo-', markersize=4)
        axs1[0].set_title('Rabi Oscillation')
        axs1[0].set_xlabel('Drive Amplitude')
        axs1[0].set_ylabel('Population')

        axs1[1].plot(d['x'], d['y_t1'], 'ro-', markersize=4)
        axs1[1].set_title('T1 Decay')
        axs1[1].set_xlabel('Wait Time (µs)')
        axs1[1].set_ylabel('Population')

        fig1.suptitle(f'{self.titlename} - Figure 1: 1D Sweeps')
        plt.tight_layout()

        if plotDisp:
            plt.show(block=False)
        figs.append(fig1)

        # Figure 2: 2D heatmap
        figNum += 1
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig2, ax2 = plt.subplots(figsize=(10, 7), num=figNum)

        im = ax2.imshow(d['spec2d'], extent=[d['fx'][0], d['fx'][-1], d['flux'][0], d['flux'][-1]],
                        origin='lower', aspect='auto', cmap='inferno')
        ax2.set_xlabel('Frequency (MHz)')
        ax2.set_ylabel('Flux (a.u.)')
        ax2.set_title(f'{self.titlename} - Figure 2: 2D Spec')
        fig2.colorbar(im, label='Signal')

        if plotDisp:
            plt.show(block=False)
        figs.append(fig2)

        # Figure 3: Histograms
        figNum += 1
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig3, ax3 = plt.subplots(figsize=(8, 5), num=figNum)

        ax3.hist(d['shots_g'], bins=40, alpha=0.7, label='|g⟩', color='blue')
        ax3.hist(d['shots_e'], bins=40, alpha=0.7, label='|e⟩', color='red')
        ax3.set_xlabel('Rotated I')
        ax3.set_ylabel('Counts')
        ax3.set_title(f'{self.titlename} - Figure 3: Single Shot Histogram')
        ax3.legend()

        if plotDisp:
            plt.show(block=block)
        figs.append(fig3)

        return figs


class MockMultiFigureSequential(MockExperimentBase):
    """
    Experiment that creates figures sequentially during execution.

    Tests: Figures created at different times during acquire().
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'num_stages': 4,
            'delay_sec': 0.5,
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False, plotDisp=True, figNum=1, block=False):
        """Creates figures during acquisition, not in display()."""
        cfg = self.cfg

        figs = []
        results = []

        for stage in range(cfg['num_stages']):
            # Simulate some data acquisition
            time.sleep(cfg['delay_sec'])

            x = np.linspace(0, 10, 50)
            y = np.sin(x * (stage + 1)) * np.exp(-0.1 * x * (stage + 1))
            results.append({'x': x, 'y': y})

            # Create figure for this stage
            while plt.fignum_exists(num=figNum):
                figNum += 1
            fig, ax = plt.subplots(figsize=(8, 5), num=figNum)

            ax.plot(x, y, 'o-', linewidth=1.5, markersize=4)
            ax.set_title(f'{self.titlename} - Stage {stage + 1}/{cfg["num_stages"]}')
            ax.set_xlabel('X')
            ax.set_ylabel('Y')
            ax.grid(True, alpha=0.3)

            plt.tight_layout()

            if plotDisp:
                plt.show(block=False)

            figs.append(fig)
            figNum += 1

        self.data = {'config': cfg, 'data': {'results': results}}
        self.figs = figs
        return self.data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        """Figures already created in acquire()."""
        if hasattr(self, 'figs'):
            return self.figs
        return None


# ============================================================================
# PART 3: LIVE PLOTTING (UPDATING DURING SWEEPS)
# ============================================================================

class MockLivePlot1D(MockExperimentBase):
    """
    1D sweep with live updating line plot.

    Tests: Live update of line data during sweep.
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'sweep_points': 50,
            'delay_per_point': 0.1,
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False, plotDisp=True, figNum=1, block=False):
        cfg = self.cfg

        x_pts = np.linspace(0, 10, cfg['sweep_points'])
        y_data = np.full(len(x_pts), np.nan)

        self.data = {'config': cfg, 'data': {'x_pts': x_pts, 'y_data': y_data}}

        # Create figure before sweep
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, ax = plt.subplots(figsize=(10, 6), num=figNum)

        line, = ax.plot(x_pts, y_data, 'bo-', markersize=5, linewidth=1.5)
        ax.set_xlim(x_pts[0] - 0.5, x_pts[-1] + 0.5)
        ax.set_ylim(-1.5, 1.5)
        ax.set_xlabel('Sweep Parameter')
        ax.set_ylabel('Signal')
        ax.set_title(f'{self.titlename} - Live 1D Sweep')
        ax.grid(True, alpha=0.3)

        if plotDisp:
            plt.show(block=False)

        # Sweep loop with live updates
        for i, x in enumerate(x_pts):
            # Simulate measurement
            time.sleep(cfg['delay_per_point'])
            y_data[i] = np.sin(x) * np.exp(-0.1 * x) + 0.1 * np.random.randn()

            # Update plot
            line.set_ydata(y_data)
            ax.relim()
            ax.autoscale_view(scalex=False, scaley=True)

            fig.canvas.draw()
            fig.canvas.flush_events()

        self.data['data']['y_data'] = y_data

        if plotDisp and block:
            plt.show(block=True)

        return self.data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        """Re-display completed data."""
        if data is None:
            data = self.data

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig, ax = plt.subplots(figsize=(10, 6), num=figNum)
        ax.plot(data['data']['x_pts'], data['data']['y_data'], 'bo-', markersize=5, linewidth=1.5)
        ax.set_xlabel('Sweep Parameter')
        ax.set_ylabel('Signal')
        ax.set_title(f'{self.titlename} - Live 1D Sweep (Completed)')
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        if plotDisp:
            plt.show(block=block)

        return fig, ax


class MockLivePlot2D(MockExperimentBase):
    """
    2D sweep with live updating heatmap.

    Tests: Live update of imshow data during nested sweep.
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'x_points': 30,
            'y_points': 20,
            'delay_per_row': 0.2,
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False, plotDisp=True, figNum=1, block=False):
        cfg = self.cfg

        x_pts = np.linspace(-5, 5, cfg['x_points'])
        y_pts = np.linspace(-3, 3, cfg['y_points'])
        Z_data = np.full((len(y_pts), len(x_pts)), np.nan)

        self.data = {'config': cfg, 'data': {'x_pts': x_pts, 'y_pts': y_pts, 'Z_data': Z_data}}

        # Create figure before sweep
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, ax = plt.subplots(figsize=(10, 7), num=figNum)

        im = ax.imshow(Z_data, extent=[x_pts[0], x_pts[-1], y_pts[0], y_pts[-1]],
                       origin='lower', aspect='auto', cmap='viridis', vmin=-1, vmax=1)
        cbar = fig.colorbar(im, ax=ax)
        cbar.set_label('Signal')
        ax.set_xlabel('X Parameter')
        ax.set_ylabel('Y Parameter')
        ax.set_title(f'{self.titlename} - Live 2D Sweep')

        if plotDisp:
            plt.show(block=False)

        # Sweep loop with live updates (row by row)
        for j, y in enumerate(y_pts):
            # Simulate row measurement
            time.sleep(cfg['delay_per_row'])

            for i, x in enumerate(x_pts):
                Z_data[j, i] = np.sin(x) * np.cos(y) + 0.1 * np.random.randn()

            # Update plot
            im.set_data(Z_data)
            im.autoscale()
            cbar.update_normal(im)

            fig.canvas.draw()
            fig.canvas.flush_events()

        self.data['data']['Z_data'] = Z_data

        if plotDisp and block:
            plt.show(block=True)

        return self.data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        """Re-display completed data."""
        if data is None:
            data = self.data

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig, ax = plt.subplots(figsize=(10, 7), num=figNum)

        d = data['data']
        im = ax.imshow(d['Z_data'], extent=[d['x_pts'][0], d['x_pts'][-1], d['y_pts'][0], d['y_pts'][-1]],
                       origin='lower', aspect='auto', cmap='viridis')
        fig.colorbar(im, ax=ax, label='Signal')
        ax.set_xlabel('X Parameter')
        ax.set_ylabel('Y Parameter')
        ax.set_title(f'{self.titlename} - Live 2D Sweep (Completed)')

        plt.tight_layout()
        if plotDisp:
            plt.show(block=block)

        return fig, ax


class MockLivePlotMultiChannel(MockExperimentBase):
    """
    Multi-channel live updating sweep (like MUX readout).

    Tests: Live update of multiple subplots simultaneously.
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'num_channels': 4,
            'sweep_points': 40,
            'delay_per_point': 0.08,
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False, plotDisp=True, figNum=1, block=False):
        cfg = self.cfg

        x_pts = np.linspace(0, 8, cfg['sweep_points'])
        y_data = [np.full(len(x_pts), np.nan) for _ in range(cfg['num_channels'])]

        self.data = {'config': cfg, 'data': {'x_pts': x_pts, 'y_data': y_data}}

        # Create figure with multiple subplots
        while plt.fignum_exists(num=figNum):
            figNum += 1

        nrows = 2 if cfg['num_channels'] > 2 else 1
        ncols = (cfg['num_channels'] + 1) // 2
        fig, axs = plt.subplots(nrows, ncols, figsize=(5 * ncols, 4 * nrows), num=figNum, squeeze=False)
        axs = axs.flatten()

        lines = []
        colors = plt.cm.tab10(np.linspace(0, 1, cfg['num_channels']))

        for i in range(cfg['num_channels']):
            line, = axs[i].plot(x_pts, y_data[i], 'o-', color=colors[i], markersize=4, linewidth=1.5)
            lines.append(line)
            axs[i].set_xlim(x_pts[0] - 0.5, x_pts[-1] + 0.5)
            axs[i].set_ylim(-1.5, 1.5)
            axs[i].set_xlabel('Sweep Parameter')
            axs[i].set_ylabel('Signal')
            axs[i].set_title(f'Channel {i + 1}')
            axs[i].grid(True, alpha=0.3)

        fig.suptitle(f'{self.titlename} - Live Multi-Channel Sweep', fontsize=14)
        plt.tight_layout()

        if plotDisp:
            plt.show(block=False)

        # Sweep loop with live updates
        for j, x in enumerate(x_pts):
            # Simulate measurement for all channels
            time.sleep(cfg['delay_per_point'])

            for i in range(cfg['num_channels']):
                freq = 0.5 + 0.2 * i
                decay = 0.1 + 0.02 * i
                y_data[i][j] = np.sin(freq * x) * np.exp(-decay * x) + 0.1 * np.random.randn()

            # Update all plots
            for i, line in enumerate(lines):
                line.set_ydata(y_data[i])
                axs[i].relim()
                axs[i].autoscale_view(scalex=False, scaley=True)

            fig.canvas.draw()
            fig.canvas.flush_events()

        self.data['data']['y_data'] = y_data

        if plotDisp and block:
            plt.show(block=True)

        return self.data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        """Re-display completed data."""
        if data is None:
            data = self.data

        cfg = self.cfg
        while plt.fignum_exists(num=figNum):
            figNum += 1

        nrows = 2 if cfg['num_channels'] > 2 else 1
        ncols = (cfg['num_channels'] + 1) // 2
        fig, axs = plt.subplots(nrows, ncols, figsize=(5 * ncols, 4 * nrows), num=figNum, squeeze=False)
        axs = axs.flatten()

        x_pts = data['data']['x_pts']
        y_data = data['data']['y_data']
        colors = plt.cm.tab10(np.linspace(0, 1, cfg['num_channels']))

        for i in range(cfg['num_channels']):
            axs[i].plot(x_pts, y_data[i], 'o-', color=colors[i], markersize=4, linewidth=1.5)
            axs[i].set_xlabel('Sweep Parameter')
            axs[i].set_ylabel('Signal')
            axs[i].set_title(f'Channel {i + 1}')
            axs[i].grid(True, alpha=0.3)

        fig.suptitle(f'{self.titlename} - Live Multi-Channel (Completed)', fontsize=14)
        plt.tight_layout()

        if plotDisp:
            plt.show(block=block)

        return fig, axs


class MockLivePlotWithFit(MockExperimentBase):
    """
    Live sweep that updates both data and fit overlay.

    Tests: Live update with progressive fitting.
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'sweep_points': 60,
            'delay_per_point': 0.08,
            'T1_true': 5.0,
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False, plotDisp=True, figNum=1, block=False):
        cfg = self.cfg

        t_pts = np.linspace(0, 20, cfg['sweep_points'])
        y_data = np.full(len(t_pts), np.nan)

        self.data = {'config': cfg, 'data': {'t_pts': t_pts, 'y_data': y_data}}

        # Create figure
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, ax = plt.subplots(figsize=(10, 6), num=figNum)

        data_line, = ax.plot(t_pts, y_data, 'bo', markersize=6, label='Data')
        fit_line, = ax.plot([], [], 'r-', linewidth=2, label='Fit')

        ax.set_xlim(t_pts[0] - 1, t_pts[-1] + 1)
        ax.set_ylim(-0.1, 1.1)
        ax.set_xlabel('Wait Time (µs)')
        ax.set_ylabel('Population')
        ax.set_title(f'{self.titlename} - Live T1 with Fit')
        ax.legend()
        ax.grid(True, alpha=0.3)

        fit_text = ax.text(0.95, 0.95, '', transform=ax.transAxes,
                           ha='right', va='top', fontsize=12,
                           bbox=dict(boxstyle='round', facecolor='wheat'))

        if plotDisp:
            plt.show(block=False)

        def exp_decay(t, T1, A, y0):
            return A * np.exp(-t / T1) + y0

        # Sweep with live fitting
        for i, t in enumerate(t_pts):
            time.sleep(cfg['delay_per_point'])
            y_data[i] = np.exp(-t / cfg['T1_true']) + 0.05 * np.random.randn()

            # Update data
            data_line.set_ydata(y_data)

            # Try fitting with enough points
            if i >= 5:
                valid_mask = ~np.isnan(y_data)
                t_valid = t_pts[valid_mask]
                y_valid = y_data[valid_mask]

                try:
                    popt, _ = curve_fit(exp_decay, t_valid, y_valid,
                                        p0=[5.0, 1.0, 0.0], maxfev=1000)
                    T1_fit, A, y0 = popt

                    # Update fit line
                    t_fine = np.linspace(0, t_pts[-1], 200)
                    fit_line.set_data(t_fine, exp_decay(t_fine, *popt))
                    fit_text.set_text(f'T1 = {T1_fit:.2f} µs')
                except Exception:
                    pass

            ax.relim()
            ax.autoscale_view(scalex=False, scaley=True)

            fig.canvas.draw()
            fig.canvas.flush_events()

        self.data['data']['y_data'] = y_data

        if plotDisp and block:
            plt.show(block=True)

        return self.data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        """Re-display with final fit."""
        if data is None:
            data = self.data

        def exp_decay(t, T1, A, y0):
            return A * np.exp(-t / T1) + y0

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig, ax = plt.subplots(figsize=(10, 6), num=figNum)

        t_pts = data['data']['t_pts']
        y_data = data['data']['y_data']

        ax.plot(t_pts, y_data, 'bo', markersize=6, label='Data')

        try:
            popt, _ = curve_fit(exp_decay, t_pts, y_data, p0=[5.0, 1.0, 0.0])
            t_fine = np.linspace(0, t_pts[-1], 200)
            ax.plot(t_fine, exp_decay(t_fine, *popt), 'r-', linewidth=2,
                    label=f'Fit: T1 = {popt[0]:.2f} µs')
        except Exception:
            pass

        ax.set_xlabel('Wait Time (µs)')
        ax.set_ylabel('Population')
        ax.set_title(f'{self.titlename} - T1 Measurement (Completed)')
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        if plotDisp:
            plt.show(block=block)

        return fig, ax


class MockLivePlotScatter(MockExperimentBase):
    """
    Live scatter plot that accumulates points.

    Tests: Live update of scatter data (IQ accumulation).
    """

    def __init__(self, **kwargs):
        default_cfg = {
            'total_shots': 500,
            'shots_per_update': 25,
            'delay_per_batch': 0.15,
        }
        cfg = kwargs.pop('cfg', {})
        merged_cfg = {**default_cfg, **cfg}
        super().__init__(cfg=merged_cfg, **kwargs)

    def acquire(self, progress=False, plotDisp=True, figNum=1, block=False):
        cfg = self.cfg
        np.random.seed(42)

        # Generate all data upfront (simulating pre-acquired shots)
        i_g_all = np.random.randn(cfg['total_shots']) * 0.25
        q_g_all = np.random.randn(cfg['total_shots']) * 0.25
        i_e_all = np.random.randn(cfg['total_shots']) * 0.25 + 1.0
        q_e_all = np.random.randn(cfg['total_shots']) * 0.25 + 0.5

        self.data = {
            'config': cfg,
            'data': {
                'i_g': i_g_all, 'q_g': q_g_all,
                'i_e': i_e_all, 'q_e': q_e_all
            }
        }

        # Create figure
        while plt.fignum_exists(num=figNum):
            figNum += 1
        fig, ax = plt.subplots(figsize=(8, 8), num=figNum)

        scatter_g = ax.scatter([], [], alpha=0.5, s=10, label='|g⟩', c='blue')
        scatter_e = ax.scatter([], [], alpha=0.5, s=10, label='|e⟩', c='red')

        ax.set_xlim(-1, 2)
        ax.set_ylim(-1, 1.5)
        ax.set_xlabel('I')
        ax.set_ylabel('Q')
        ax.set_title(f'{self.titlename} - Live IQ Accumulation (0/{cfg["total_shots"]} shots)')
        ax.legend()
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.3)

        if plotDisp:
            plt.show(block=False)

        # Accumulate shots
        current_shots = 0
        while current_shots < cfg['total_shots']:
            time.sleep(cfg['delay_per_batch'])

            end_idx = min(current_shots + cfg['shots_per_update'], cfg['total_shots'])

            # Update scatter data
            scatter_g.set_offsets(np.c_[i_g_all[:end_idx], q_g_all[:end_idx]])
            scatter_e.set_offsets(np.c_[i_e_all[:end_idx], q_e_all[:end_idx]])

            ax.set_title(f'{self.titlename} - Live IQ Accumulation ({end_idx}/{cfg["total_shots"]} shots)')

            fig.canvas.draw()
            fig.canvas.flush_events()

            current_shots = end_idx

        if plotDisp and block:
            plt.show(block=True)

        return self.data

    def display(self, data=None, plotDisp=True, figNum=1, block=True, **kwargs):
        """Re-display completed scatter."""
        if data is None:
            data = self.data

        while plt.fignum_exists(num=figNum):
            figNum += 1

        fig, ax = plt.subplots(figsize=(8, 8), num=figNum)

        d = data['data']
        ax.scatter(d['i_g'], d['q_g'], alpha=0.5, s=10, label='|g⟩', c='blue')
        ax.scatter(d['i_e'], d['q_e'], alpha=0.5, s=10, label='|e⟩', c='red')

        ax.set_xlabel('I')
        ax.set_ylabel('Q')
        ax.set_title(f'{self.titlename} - IQ Scatter (Completed)')
        ax.legend()
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        if plotDisp:
            plt.show(block=block)

        return fig, ax


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def get_grid_experiments():
    """Get list of experiments testing different grid configurations."""
    return [
        MockGrid1x1,
        MockGrid1x2,
        MockGrid2x1,
        MockGrid2x2,
        MockGrid2x3,
        MockGrid3x3,
        MockGridSpec,
        MockGrid2x4,
    ]


def get_multifigure_experiments():
    """Get list of experiments creating multiple figures."""
    return [
        MockMultiFigure2,
        MockMultiFigure3,
        MockMultiFigureSequential,
    ]


def get_liveplot_experiments():
    """Get list of experiments with live plotting."""
    return [
        MockLivePlot1D,
        MockLivePlot2D,
        MockLivePlotMultiChannel,
        MockLivePlotWithFit,
        MockLivePlotScatter,
    ]


def get_all_advanced_experiments():
    """Get list of all advanced mock experiments."""
    return get_grid_experiments() + get_multifigure_experiments() + get_liveplot_experiments()


def run_grid_experiments(plotDisp=True, block=False):
    """Run all grid configuration experiments."""
    print("=" * 60)
    print("Running Grid Configuration Experiments")
    print("=" * 60)

    experiments = {}
    for ExpClass in get_grid_experiments():
        name = ExpClass.__name__
        print(f"\n{name}...")
        exp = ExpClass(path=name, prefix='test', titlename=name)
        exp.acquire()
        exp.display(plotDisp=plotDisp, block=block)
        experiments[name] = exp

    return experiments


def run_multifigure_experiments(plotDisp=True, block=False):
    """Run all multi-figure experiments."""
    print("=" * 60)
    print("Running Multi-Figure Experiments")
    print("=" * 60)

    experiments = {}
    for ExpClass in get_multifigure_experiments():
        name = ExpClass.__name__
        print(f"\n{name}...")
        exp = ExpClass(path=name, prefix='test', titlename=name)

        if ExpClass == MockMultiFigureSequential:
            exp.acquire(plotDisp=plotDisp, block=block)
        else:
            exp.acquire()
            exp.display(plotDisp=plotDisp, block=block)

        experiments[name] = exp

    return experiments


def run_liveplot_experiments(plotDisp=True, block=False):
    """Run all live plotting experiments."""
    print("=" * 60)
    print("Running Live Plotting Experiments")
    print("=" * 60)

    experiments = {}
    for ExpClass in get_liveplot_experiments():
        name = ExpClass.__name__
        print(f"\n{name}...")
        exp = ExpClass(path=name, prefix='test', titlename=name)
        exp.acquire(plotDisp=plotDisp, block=block)
        experiments[name] = exp

    return experiments


def run_all_advanced_experiments(plotDisp=True, block=False):
    """Run all advanced mock experiments."""
    experiments = {}

    experiments.update(run_grid_experiments(plotDisp=plotDisp, block=block))
    experiments.update(run_multifigure_experiments(plotDisp=plotDisp, block=block))
    experiments.update(run_liveplot_experiments(plotDisp=plotDisp, block=block))

    print("\n" + "=" * 60)
    print("All advanced experiments completed!")
    print("=" * 60)

    return experiments


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Run advanced mock experiments for GUI testing')
    parser.add_argument('--category', choices=['grid', 'multi', 'live', 'all'],
                        default='all', help='Which category to run')
    parser.add_argument('--block', action='store_true', help='Block on each plot')
    parser.add_argument('--no-display', action='store_true', help='Disable plot display')

    args = parser.parse_args()

    plotDisp = not args.no_display
    block = args.block

    if args.category == 'grid':
        run_grid_experiments(plotDisp=plotDisp, block=block)
    elif args.category == 'multi':
        run_multifigure_experiments(plotDisp=plotDisp, block=block)
    elif args.category == 'live':
        run_liveplot_experiments(plotDisp=plotDisp, block=block)
    else:
        run_all_advanced_experiments(plotDisp=plotDisp, block=block)