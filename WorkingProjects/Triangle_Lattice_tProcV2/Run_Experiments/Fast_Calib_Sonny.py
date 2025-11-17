"""
Fast Calibration Script

Improvements over original Fast_calib.py:
- Modular structure with calibration stages
- Quality checks after each step with warnings based on specified thresholds
- Optional T1/T2 coherence checks
- Iterative refinement for low fidelity results
"""
import math

import numpy as np
import matplotlib.pyplot as plt
import json
import time
from datetime import datetime
from pathlib import Path

from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSpecSliceFFMUX import QubitSpecSliceFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Characterization_Sweeps.mOptimizeReadoutandPulse_FFMUX import ReadOpt_wSingleShotFFMUX, QubitPulseOpt_wSingleShotFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mTransmissionFFMUX import CavitySpecFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mSingleShotProgramFFMUX import SingleShotFFMUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT1MUX import T1MUX
from WorkingProjects.Triangle_Lattice_tProcV2.Experimental_Scripts.Basic_Experiments.mT2RMUX import T2RMUX

from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Qubit_Parameters_Helpers import QubitConfig

from qubit_parameter_files.Qubit_Parameters_Master import *

t = True
f = False


# ========================================================================
# Calibration Summary
# ========================================================================

def create_calibration_summary_dashboard(Qubit_configs, additional_qubit_data, checkers):
    """
    Create a comprehensive summary dashboard after calibrating all qubits
    """

    # Extract data from all qubits
    qubit_data = []
    for qconf, add_data, checker in zip(Qubit_configs, additional_qubit_data, checkers):
        qubit_data.append({
            'qubit_id': qconf.qubit_id,
            'qubit_freq': qconf.qubit_freq,
            'readout_freq': qconf.readout_freq,
            'qubit_gain': qconf.qubit_gain,
            'readout_gain': qconf.readout_gain,
            'fidelity': add_data['fidelity'],
            'T1': add_data['T1'],
            'T2': add_data['T2'],
            'warnings': len(checker.warnings),
            'issues': len(checker.issues),
            'warning_list': checker.warnings,
            'issue_list': checker.issues
        })

    # Create figure with custom layout
    fig = plt.figure(figsize=(18, 12))
    fig.patch.set_facecolor('#F8F9FA')

    # Define grid for subplots
    gs = fig.add_gridspec(4, 3, hspace=0.35, wspace=0.3,
                          left=0.08, right=0.95, top=0.93, bottom=0.05)

    # Main title
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    fig.suptitle(f'Calibration Summary Dashboard - {timestamp}',
                 fontsize=18, fontweight='bold', y=0.97)

    # ========================================================================
    # PANEL 1: FREQUENCY MAP (Top Left - spans 2 columns)
    # ========================================================================
    ax_freq = fig.add_subplot(gs[0:2, 0:2])

    qubit_ids = [q['qubit_id'] for q in qubit_data]
    qubit_freqs = [q['qubit_freq'] for q in qubit_data]
    readout_freqs = [q['readout_freq'] for q in qubit_data]
    fidelities = [q['fidelity'] for q in qubit_data]

    # Create frequency range plot
    y_positions = np.arange(len(qubit_ids))
    bar_height = 0.35

    # Color code by fidelity
    def fidelity_color(fid):
        if fid >= 0.95:
            return '#06A77D'  # Green
        elif fid >= 0.90:
            return '#F18F01'  # Orange
        elif fid >= 0.85:
            return '#E85D04'  # Dark orange
        else:
            return '#C73E1D'  # Red

    colors = [fidelity_color(f) for f in fidelities]

    # Plot readout frequencies (bottom bars)
    ax_freq.barh(y_positions - bar_height / 2, readout_freqs, bar_height,
                 color=colors, alpha=0.6, label='Readout Freq', edgecolor='black', linewidth=1.5)

    # Plot qubit frequencies (top bars)
    ax_freq.barh(y_positions + bar_height / 2, qubit_freqs, bar_height,
                 color=colors, alpha=0.9, label='Qubit Freq', edgecolor='black', linewidth=1.5)

    # Annotations
    for i, (qid, qf, rf, fid) in enumerate(zip(qubit_ids, qubit_freqs, readout_freqs, fidelities)):
        # Qubit freq label
        ax_freq.text(qf + 10, y_positions[i] + bar_height / 2, f'{qf:.1f}',
                     va='center', fontsize=9, fontweight='bold')
        # Readout freq label
        ax_freq.text(rf + 10, y_positions[i] - bar_height / 2, f'{rf:.1f}',
                     va='center', fontsize=9, fontweight='bold')
        # Fidelity label
        ax_freq.text(max(qf, rf) + 50, y_positions[i], f'{fid * 100:.1f}%',
                     va='center', fontsize=10, fontweight='bold',
                     bbox=dict(boxstyle='round,pad=0.3', facecolor=fidelity_color(fid), alpha=0.3))

    ax_freq.set_yticks(y_positions)
    ax_freq.set_yticklabels([f'Q{qid}' for qid in qubit_ids], fontsize=11, fontweight='bold')
    ax_freq.set_xlabel('Frequency (MHz)', fontsize=12, fontweight='bold')
    ax_freq.set_title('Qubit and Readout Frequency Map', fontsize=13, fontweight='bold', pad=15)
    ax_freq.legend(loc='lower right', fontsize=10, framealpha=0.95)
    ax_freq.grid(axis='x', alpha=0.3, linestyle='--')
    ax_freq.set_axisbelow(True)

    # Add frequency span indicator
    all_freqs = qubit_freqs + readout_freqs
    freq_range = max(all_freqs) - min(all_freqs)
    ax_freq.set_xlim(min(all_freqs) - 0.1 * freq_range, max(all_freqs) + 0.15 * freq_range)

    # ========================================================================
    # PANEL 2: GAIN COMPARISON (Top Right)
    # ========================================================================
    ax_gains = fig.add_subplot(gs[0, 2])

    qubit_gains = [q['qubit_gain'] for q in qubit_data]
    readout_gains = [q['readout_gain'] * 32766 for q in qubit_data]  # Convert to absolute

    x = np.arange(len(qubit_ids))
    width = 0.35

    bars1 = ax_gains.bar(x - width / 2, qubit_gains, width, label='Qubit Gain',
                         color='#457B9D', alpha=0.8, edgecolor='black', linewidth=1)
    bars2 = ax_gains.bar(x + width / 2, readout_gains, width, label='Readout Gain',
                         color='#E63946', alpha=0.8, edgecolor='black', linewidth=1)

    # Add value labels on bars
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            ax_gains.text(bar.get_x() + bar.get_width() / 2., height,
                          f'{int(height)}', ha='center', va='bottom', fontsize=8, fontweight='bold')

    ax_gains.set_xlabel('Qubit', fontsize=11, fontweight='bold')
    ax_gains.set_ylabel('Gain (a.u.)', fontsize=11, fontweight='bold')
    ax_gains.set_title('Pulse Gains', fontsize=12, fontweight='bold', pad=10)
    ax_gains.set_xticks(x)
    ax_gains.set_xticklabels([f'Q{qid}' for qid in qubit_ids], fontsize=9, fontweight='bold')
    ax_gains.legend(fontsize=9, framealpha=0.95)
    ax_gains.grid(axis='y', alpha=0.3, linestyle='--')
    ax_gains.set_axisbelow(True)

    # ========================================================================
    # PANEL 3: FIDELITY COMPARISON (Middle Right)
    # ========================================================================
    ax_fid = fig.add_subplot(gs[1, 2])

    bars = ax_fid.barh(y_positions, [f * 100 for f in fidelities],
                       color=colors, alpha=0.8, edgecolor='black', linewidth=1.5)

    # Add value labels
    for i, (bar, fid) in enumerate(zip(bars, fidelities)):
        width = bar.get_width()
        ax_fid.text(width + 0.5, bar.get_y() + bar.get_height() / 2,
                    f'{fid * 100:.2f}%', va='center', fontsize=10, fontweight='bold')

    ax_fid.set_yticks(y_positions)
    ax_fid.set_yticklabels([f'Q{qid}' for qid in qubit_ids], fontsize=11, fontweight='bold')
    ax_fid.set_xlabel('Single-Shot Fidelity (%)', fontsize=11, fontweight='bold')
    ax_fid.set_title('Readout Fidelity', fontsize=12, fontweight='bold', pad=10)
    ax_fid.axvline(95, color='green', linestyle='--', linewidth=2, alpha=0.5, label='95% Target')
    ax_fid.axvline(90, color='orange', linestyle='--', linewidth=2, alpha=0.5, label='90% Target')
    ax_fid.legend(fontsize=8, framealpha=0.95)
    ax_fid.grid(axis='x', alpha=0.3, linestyle='--')
    ax_fid.set_axisbelow(True)
    ax_fid.set_xlim(80, 100)

    # ========================================================================
    # PANEL 4: COHERENCE TIMES (Middle Left)
    # ========================================================================
    ax_coherence = fig.add_subplot(gs[2, 0])

    T1_values = [q['T1'] if q['T1'] else 0 for q in qubit_data]
    T2_values = [q['T2'] if q['T2'] else 0 for q in qubit_data]

    x = np.arange(len(qubit_ids))
    width = 0.35

    bars1 = ax_coherence.bar(x - width / 2, T1_values, width, label='T₁',
                             color='#06A77D', alpha=0.8, edgecolor='black', linewidth=1)
    bars2 = ax_coherence.bar(x + width / 2, T2_values, width, label='T₂',
                             color='#2E86AB', alpha=0.8, edgecolor='black', linewidth=1)

    # Add value labels
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax_coherence.text(bar.get_x() + bar.get_width() / 2., height,
                                  f'{height:.1f}', ha='center', va='bottom',
                                  fontsize=8, fontweight='bold')

    ax_coherence.set_xlabel('Qubit', fontsize=11, fontweight='bold')
    ax_coherence.set_ylabel('Time (μs)', fontsize=11, fontweight='bold')
    ax_coherence.set_title('Coherence Times', fontsize=12, fontweight='bold', pad=10)
    ax_coherence.set_xticks(x)
    ax_coherence.set_xticklabels([f'Q{qid}' for qid in qubit_ids], fontsize=9, fontweight='bold')
    ax_coherence.legend(fontsize=10, framealpha=0.95)
    ax_coherence.grid(axis='y', alpha=0.3, linestyle='--')
    ax_coherence.set_axisbelow(True)

    # ========================================================================
    # PANEL 5: FREQUENCY DETUNINGS (Middle Center)
    # ========================================================================
    ax_detuning = fig.add_subplot(gs[2, 1])

    # Calculate nearest-neighbor detunings
    if len(qubit_freqs) > 1:
        sorted_qubits = sorted(zip(qubit_ids, qubit_freqs), key=lambda x: x[1])
        detunings = []
        labels = []
        for i in range(len(sorted_qubits) - 1):
            q1_id, q1_freq = sorted_qubits[i]
            q2_id, q2_freq = sorted_qubits[i + 1]
            detuning = abs(q2_freq - q1_freq)
            detunings.append(detuning)
            labels.append(f'Q{q1_id}-Q{q2_id}')

        # Color code: green if >50 MHz, orange if 20-50, red if <20
        colors_det = ['#06A77D' if d > 50 else '#F18F01' if d > 20 else '#C73E1D'
                      for d in detunings]

        bars = ax_detuning.barh(range(len(detunings)), detunings,
                                color=colors_det, alpha=0.8, edgecolor='black', linewidth=1.5)

        # Add value labels
        for i, (bar, det) in enumerate(zip(bars, detunings)):
            width = bar.get_width()
            ax_detuning.text(width + 2, bar.get_y() + bar.get_height() / 2,
                             f'{det:.1f} MHz', va='center', fontsize=9, fontweight='bold')

        ax_detuning.set_yticks(range(len(labels)))
        ax_detuning.set_yticklabels(labels, fontsize=10, fontweight='bold')
        ax_detuning.set_xlabel('Detuning (MHz)', fontsize=11, fontweight='bold')
        ax_detuning.set_title('Nearest-Neighbor Detunings', fontsize=12, fontweight='bold', pad=10)
        ax_detuning.grid(axis='x', alpha=0.3, linestyle='--')
        ax_detuning.set_axisbelow(True)

        # Add reference lines
        ax_detuning.axvline(50, color='green', linestyle='--', linewidth=1.5, alpha=0.4)
        ax_detuning.axvline(20, color='orange', linestyle='--', linewidth=1.5, alpha=0.4)
    else:
        ax_detuning.text(0.5, 0.5, 'Single Qubit\n(No Detunings)',
                         ha='center', va='center', fontsize=12, transform=ax_detuning.transAxes)
        ax_detuning.axis('off')

    # ========================================================================
    # PANEL 6: QUALITY SCORE (Middle Right)
    # ========================================================================
    ax_quality = fig.add_subplot(gs[2, 2])

    # Calculate quality score for each qubit
    def calculate_quality_score(q):
        score = 0
        # Fidelity (40 points max)
        score += min(q['fidelity'] * 40, 40)
        # T1 (20 points max - cap at 50us = 20 points)
        if q['T1']:
            score += min(q['T1'] / 50 * 20, 20)
        # T2 (20 points max - cap at 25us = 20 points)
        if q['T2']:
            score += min(q['T2'] / 25 * 20, 20)
        # Penalties
        score -= q['warnings'] * 2
        score -= q['issues'] * 5
        return max(score, 0)

    quality_scores = [calculate_quality_score(q) for q in qubit_data]

    # Color code
    colors_qual = ['#06A77D' if s >= 70 else '#F18F01' if s >= 50 else '#C73E1D'
                   for s in quality_scores]

    bars = ax_quality.barh(y_positions, quality_scores,
                           color=colors_qual, alpha=0.8, edgecolor='black', linewidth=1.5)

    # Add value labels and grade
    for i, (bar, score) in enumerate(zip(bars, quality_scores)):
        width = bar.get_width()
        grade = 'A' if score >= 80 else 'B' if score >= 70 else 'C' if score >= 50 else 'D'
        ax_quality.text(width + 1, bar.get_y() + bar.get_height() / 2,
                        f'{score:.0f} ({grade})', va='center', fontsize=10, fontweight='bold')

    ax_quality.set_yticks(y_positions)
    ax_quality.set_yticklabels([f'Q{qid}' for qid in qubit_ids], fontsize=11, fontweight='bold')
    ax_quality.set_xlabel('Quality Score', fontsize=11, fontweight='bold')
    ax_quality.set_title('Overall Quality Rating', fontsize=12, fontweight='bold', pad=10)
    ax_quality.grid(axis='x', alpha=0.3, linestyle='--')
    ax_quality.set_axisbelow(True)
    ax_quality.set_xlim(0, 100)

    # Add grade boundaries
    for val, label, color in [(80, 'A', 'green'), (70, 'B', 'orange'), (50, 'C', 'red')]:
        ax_quality.axvline(val, color=color, linestyle='--', linewidth=1, alpha=0.3)

    # ========================================================================
    # PANEL 7: TEXT SUMMARY (Bottom - spans all columns)
    # ========================================================================
    ax_summary = fig.add_subplot(gs[3, :])
    ax_summary.axis('off')

    # Compile summary text
    summary_lines = []
    summary_lines.append("╔" + "═" * 150 + "╗")
    summary_lines.append("║" + " " * 50 + "DETAILED CALIBRATION SUMMARY" + " " * 72 + "║")
    summary_lines.append("╠" + "═" * 150 + "╣")

    for i, (q, checker) in enumerate(zip(qubit_data, checkers)):
        qid = q['qubit_id']
        status_symbol = "✓" if q['issues'] == 0 else "⚠" if q['issues'] <= 1 else "✗"

        line1 = f"║ QUBIT {qid} {status_symbol}  │ "
        line1 += f"Freq: {q['qubit_freq']:>7.2f} MHz  │ "
        line1 += f"Readout: {q['readout_freq']:>7.2f} MHz  │ "
        line1 += f"Fidelity: {q['fidelity'] * 100:>5.2f}%  │ "
        line1 += f"T₁: {q['T1']:>5.1f}μs  │ " if q['T1'] else f"T₁: {'N/A':>5}  │ "
        line1 += f"T₂: {q['T2']:>5.1f}μs" if q['T2'] else f"T₂: {'N/A':>5}"
        line1 += " " * (150 - len(line1)) + "║"
        summary_lines.append(line1)

        line2 = f"║          │ "
        line2 += f"Q Gain: {q['qubit_gain']:>5.0f}  │ "
        line2 += f"RO Gain: {q['readout_gain'] * 32766:>5.0f}  │ "
        line2 += f"Warnings: {q['warnings']:>2}  │ "
        line2 += f"Issues: {q['issues']:>2}"
        line2 += " " * (150 - len(line2)) + "║"
        summary_lines.append(line2)

        # Add warnings/issues if any
        if q['warning_list']:
            for warn in q['warning_list']:
                warn_line = f"║    ⚠ {warn}"
                warn_line += " " * (150 - len(warn_line)) + "║"
                summary_lines.append(warn_line)

        if q['issue_list']:
            for issue in q['issue_list']:
                issue_line = f"║    ✗ {issue}"
                issue_line += " " * (150 - len(issue_line)) + "║"
                summary_lines.append(issue_line)

        if i < len(qubit_data) - 1:
            summary_lines.append("╠" + "─" * 150 + "╣")

    summary_lines.append("╚" + "═" * 150 + "╝")

    summary_text = "\n".join(summary_lines)

    # Determine overall background color
    total_issues = sum(q['issues'] for q in qubit_data)
    bg_color = '#E8F5E9' if total_issues == 0 else '#FFF3E0' if total_issues <= 2 else '#FFEBEE'

    ax_summary.text(0.5, 0.5, summary_text,
                    fontsize=8, fontfamily='monospace',
                    verticalalignment='center', horizontalalignment='center',
                    bbox=dict(boxstyle='round,pad=1', facecolor=bg_color,
                              alpha=0.8, edgecolor='gray', linewidth=2),
                    transform=ax_summary.transAxes)

    return fig

# =============================================================================
# QUALITY CHECK FUNCTIONS
# =============================================================================

class QualityChecker:
    """Handles quality checks and warnings for calibration steps"""

    def __init__(self, qubit_id, config):
        self.qubit_id = qubit_id
        self.config = config
        self.warnings = []
        self.issues = []

    def check_transmission(self, data):
        """Check if transmission sweep found a clear cavity peak"""
        freq_found = data.get('peakFreq_min')
        if freq_found is None:
            self.issues.append("Transmission: No cavity peak found")
            return False
        print(f"Cavity frequency found at: {freq_found + self.config['res_LO']:.2f}")
        return True

    def check_spectroscopy(self, data, nominal_freq=None):
        """Check spectroscopy quality"""
        qubit_freq = data.get('qubitFreq')

        if qubit_freq is None:
            self.issues.append("Spectroscopy: No qubit peak found")
            return False

        # Check for large drift if nominal frequency provided
        if nominal_freq is not None:
            drift = abs(qubit_freq - nominal_freq)
            if drift > CalibrationConfig.MAX_FREQ_DRIFT:
                self.warnings.append(f"Large frequency drift: {drift:.1f} MHz from nominal")

        print(f"Qubit frequency found at: {qubit_freq:.2f}")
        return True

    def check_rabi(self, data):
        """Check if Rabi oscillation was found"""
        if 'pi_gain_fit' not in data['data']:
            self.warnings.append("Rabi: No oscillation fit - using manual gain")
            return False

        pi_gain = data['data']['pi_gain_fit']
        print(f"Qubit gain found at: {pi_gain:.0f}")
        return True

    def check_singleshot(self, data):
        """Check single-shot fidelity"""
        fidelity = data.get('fidelity', 0)

        if fidelity < CalibrationConfig.MIN_FIDELITY:
            self.issues.append(f"Single-shot fidelity too low: {fidelity:.3f} < {CalibrationConfig.MIN_FIDELITY}")
            return False
        elif fidelity < 0.90:
            self.warnings.append(f"Single-shot fidelity marginal: {fidelity:.3f}")

        return True

    def check_coherence(self, t1_data=None, t2_data=None):
        """Check T1 and T2 coherence times"""
        if t1_data is not None:
            t1 = t1_data.get('T1', 0)
            if t1 < CalibrationConfig.MIN_T1:
                self.warnings.append(f"T1 = {t1:.1f} us is low (< {CalibrationConfig.MIN_T1} us)")

        if t2_data is not None:
            t2 = t2_data.get('T2', 0)
            if t2 < CalibrationConfig.MIN_T2:
                self.warnings.append(f"T2 = {t2:.1f} us is low (< {CalibrationConfig.MIN_T2} us)")

        return True

    def print_summary(self):
        """Print all warnings and issues"""
        if self.warnings:
            print("\nWARNINGS:")
            for warning in self.warnings:
                print(f"  {warning}")

        if self.issues:
            print("\nCRITICAL ISSUES:")
            for issue in self.issues:
                print(f"  {issue}")
            print("\nCalibration may need to be repeated or parameters adjusted.")

        if not self.warnings and not self.issues:
            print("\nAll quality checks passed.")

# =============================================================================
# MAIN CALIBRATION CLASS
# =============================================================================

class EnhancedCalibration:
    """Enhanced calibration workflow with quality checks"""

    def __init__(self, soc, soccfg, config, outerFolder, qubit_id):
        self.soc = soc
        self.soccfg = soccfg
        self.config = config
        self.outerFolder = outerFolder
        self.qubit_id = qubit_id

        self.checker = QualityChecker(qubit_id, config)

        self.fig = None
        self.axs = None

        # Store info for QubitConfig
        self.num_readout_qubits = None
        self.OptReadout_index = None
        self.OptQubit_index = None
        self.varname_FF = None

    def set_final_fidelity(self, fidelity):
        self.final_fidelity = fidelity

    def setup_plot(self, num_steps=6):
        """Set up figure for displaying results."""
        # Decide grid size
        ncols = min(3, num_steps)
        nrows = math.ceil(num_steps / ncols)

        self.fig, self.axs = plt.subplots(
            nrows, ncols,
            figsize=(5 * ncols, 4 * nrows),
            tight_layout=True
        )

        self.fig.suptitle(
            f"Qubit_{self.qubit_id}_Calibration_{datetime.now().strftime('%Y_%m_%d_%H_%M')}",
            fontsize=14
        )

        # Make sure we always have a flat iterable of axes
        axs_flat = np.atleast_1d(self.axs).ravel()

        # Hide any unused axes (if grid bigger than num_steps)
        for ax in axs_flat[num_steps:]:
            ax.set_visible(False)

        # Iterator over only the axes we actually use
        self.iter_axs = iter(axs_flat[:num_steps])

        return self.fig, self.axs

    def run_transmission(self, params):
        """Step 1: Find cavity frequency"""
        expt = CavitySpecFFMUX(
            path="TransmissionFF",
            cfg=self.config | params,
            soc=self.soc,
            soccfg=self.soccfg,
            outerFolder=self.outerFolder
        )
        data = expt.acquire(use_lorentzian=True)
        expt.display(plotDisp=True, block=False, ax=next(self.iter_axs))
        data["peakFreq_min"] = expt.peakFreq_min

        # Update config
        if self.checker.check_transmission(data):
            self.config["res_freqs"][0] = expt.peakFreq_min
        else:
            print("[WARNING]: TRANSMISSION FIT FAILED")

        print(f"Transmission Step: freq_found: {self.config["res_freqs"][0] + self.config.get("res_LO", 0)}")
        return data

    def run_spectroscopy(self, params, coarse=True):
        """Step 2/3: Find qubit frequency (coarse then fine)"""
        nominal_freq = self.config.get("qubit_freqs", [None])[0]

        expt = QubitSpecSliceFFMUX(
            path=f"QubitSpec_{'Coarse' if coarse else 'Fine'}",
            cfg=self.config | params,
            soc=self.soc,
            soccfg=self.soccfg,
            outerFolder=self.outerFolder
        )
        data = expt.acquire(use_lorentzian=True)
        expt.display(plotDisp=True, block=False, ax=next(self.iter_axs))
        data["qubitFreq"] = expt.qubitFreq

        # Check quality and update
        if self.checker.check_spectroscopy(data, nominal_freq):
            self.config["qubit_freqs"][0] = expt.qubitFreq
        else:
            self.config["qubit_freqs"][0] = expt.qubitFreq
            print("[WARNING]: SPEC FIT FAILED")

        print(f"Spectroscopy {"coarse" if coarse else "fine"} Step: freq_found: {self.config["qubit_freqs"][0]}")

        return data

    def run_rabi(self, params, OptQubit_index):
        """Step 4: Amplitude Rabi to find pi pulse"""
        expt = AmplitudeRabiFFMUX(
            path="AmplitudeRabi",
            cfg=self.config | params,
            soc=self.soc,
            soccfg=self.soccfg,
            outerFolder=self.outerFolder
        )
        data = expt.acquire_display_save(plotDisp=True, block=False, ax=next(self.iter_axs))

        # Update config
        if self.checker.check_rabi(data):
            self.config["qubit_gains"][OptQubit_index] = data['data']['pi_gain_fit'] / 32766
        else:
            # Manual entry if fit failed
            print("[WARNING]: RABI FIT FAILED")
            pass

        print(f"Rabi Step: Pi Gain: {self.config["qubit_gains"][OptQubit_index] * 32766}")

        return data

    def run_readout_optimization(self, params, OptReadout_index, iteration=1):
        """Step 5: Optimize readout for maximum fidelity"""
        expt = ReadOpt_wSingleShotFFMUX(
            path="SingleShot_OptReadout",
            outerFolder=self.outerFolder,
            cfg=self.config | params,
            soc=self.soc,
            soccfg=self.soccfg
        )
        ax = next(self.iter_axs)
        data = expt.acquire_save(plotDisp=True, ax=ax)

        # Extract optimized parameters
        fid_mat = data['data']['fid_mat']
        trans_fpts = data['data']['trans_fpts']
        gain_pts = data['data']['gain_pts']
        ro_opt_index = data['data']['ro_opt_index']
        ind = np.unravel_index(np.argmax(fid_mat, axis=None), fid_mat.shape)

        # Update config
        self.config["res_gains"][ro_opt_index] = gain_pts[ind[0]] / 32766. * len(params.get('Qubit_Readout', [1]))
        self.config["res_freqs"][ro_opt_index] = trans_fpts[ind[1]]

        max_fid = np.max(fid_mat)

        best_gain = int(round(gain_pts[ind[0]]))
        best_freq = round(trans_fpts[ind[1]] + BaseConfig["res_LO"], 2)
        ax.text(best_freq, best_gain, f"({best_freq}, {best_gain})", zorder=3, ha='center', va='center', color='black')
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()

        print(f"Optimize Readout Step:")
        print(f"   Q{params.get('Qubit_Readout', [0])[ro_opt_index]} cavity gain found at: {gain_pts[ind[0]]:.0f}")
        print(f"   Cavity frequency found at: {trans_fpts[ind[1]] + self.config.get('res_LO', 0):.2f}")
        print(f"   Max fid found at: {max_fid}")

        return data, max_fid

    def run_qubit_optimization(self, params, OptQubit_index, iteration=1):
        """Step 6: Optimize qubit pulse for maximum fidelity"""
        expt = QubitPulseOpt_wSingleShotFFMUX(
            path="SingleShot_OptQubit",
            outerFolder=self.outerFolder,
            cfg=self.config | params,
            soc=self.soc,
            soccfg=self.soccfg
        )
        ax =  next(self.iter_axs)
        data = expt.acquire_save(plotDisp=True, ax=ax)

        # Extract optimized parameters
        fid_mat = data['data']['fid_mat']
        qubit_fpts = data['data']['qubit_fpts']
        gain_pts = data['data']['gain_pts']
        ind = np.unravel_index(np.argmax(fid_mat, axis=None), fid_mat.shape)

        sweep_index = params['qubit_sweep_index']
        self.config["qubit_gains"][sweep_index] = gain_pts[ind[0]] / 32766.
        self.config["qubit_freqs"][sweep_index] = qubit_fpts[ind[1]]

        max_fid = np.max(fid_mat)

        best_gain = int(round(gain_pts[ind[0]]))
        best_freq = round(qubit_fpts[ind[1]], 2)
        ax.text(best_freq, best_gain, f"({best_freq}, {best_gain})", zorder=3, ha='center', va='center', color='black')
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()

        print(f"Optimize Pulse Step:")
        print(f"   Qubit gain found at: {gain_pts[ind[0]]:.0f}")
        print(f"   Qubit frequency found at: {qubit_fpts[ind[1]]:.2f}")
        print(f"   Max fid found at: {max_fid}")

        return data, max_fid

    def run_singleshot_verification(self, params):
        """Step 7: Final single-shot verification"""
        expt = SingleShotFFMUX(
            path="SingleShot",
            outerFolder=self.outerFolder,
            cfg=self.config | params,
            soc=self.soc,
            soccfg=self.soccfg
        )
        ss_data = expt.acquire()

        # Display with appropriate indices
        try:
            expt.display(ss_data, plotDisp=True, block=False, display_indices=[self.qubit_id])
        except:
            expt.display(ss_data, plotDisp=True, block=False)

        # Check final fidelity
        fidelity = ss_data['data'].get('fid', 0)[0]
        print(fidelity)
        self.checker.check_singleshot({'fidelity': fidelity})

        print(f"Singleshot Step: fidelity: {fidelity}")

        return ss_data

    def run_coherence_check(self, t1_params, t2_params):
        """T1/T2 check"""

        # Quick T1 (5 time points)
        try:
            t1_expt = T1MUX(
                path="T1",
                cfg=self.config | t1_params,
                soc=self.soc,
                soccfg=self.soccfg,
                outerFolder=self.outerFolder
            )
            t1_data = t1_expt.acquire()
            t1_expt.display(plotDisp=True, block=False, ax=next(self.iter_axs))

            # Quick T2 (5 time points)
            t2_expt = T2RMUX(
                path="T2R",
                cfg=self.config | t2_params,
                soc=self.soc,
                soccfg=self.soccfg,
                outerFolder=self.outerFolder
            )
            t2_data = t2_expt.acquire()
            t2_expt.display(plotDisp=True, block=False, ax=next(self.iter_axs))

            t1 = t1_expt.T1
            t2 = t2_expt.T2
            self.T1 = t1
            self.T2 = t2
            self.checker.check_coherence(t1, t2)

            print(f"T1/T2 Step:")
            print(f"   T1: {t1}")
            print(f"   T2: {t2}")

            return t1_data, t2_data

        except Exception as e:
            print(f"Coherence check failed: {e}")
            return None, None

    def finalize(self):
        """Print summary, save logs, and create QubitConfig"""
        self.checker.print_summary()
        # Create QubitConfig for formatted printing
        if self.num_readout_qubits is not None:
            qubit_config = QubitConfig(
                self.config,
                self.qubit_id,
                self.num_readout_qubits,
                self.OptReadout_index,
                self.OptQubit_index,
                self.varname_FF
            )
            additional_data = {
                "fidelity": getattr(self, 'final_fidelity', 0),
                "T1": getattr(self, 'T1', None),
                "T2": getattr(self, 'T2', None),
            }
            return qubit_config, additional_data
        return None, None

# =============================================================================
# MAIN CALIBRATION WORKFLOW
# =============================================================================

def run_enhanced_calibration(
        soc, soccfg, config, outerFolder,
        qubit_id,
        OptReadout_index,
        OptQubit_index,
        num_readout_qubits=None,  # Number of qubits in readout list
        varname_FF=None,  # FF variable name (e.g., 'Readout_1234_FF')
        run_transmission=True,
        run_coarse_spec=True,
        run_fine_spec=True,
        run_rabi=True,
        run_readout_opt=True,
        run_qubit_opt=True,
        run_coherence=False,
        run_singleshot=True,
        enable_refinement=True
):
    """
    Run full enhanced calibration workflow

    Parameters:
    -----------
    num_readout_qubits : int, optional
        Number of qubits in Qubit_Readout list (default: auto-detect from config)
    varname_FF : str, optional
        Fast flux variable name for QubitConfig (e.g., 'Readout_1234_FF')
    enable_refinement : bool
        If True and fidelity < MIN_FIDELITY, retry optimization steps
    """

    print(f"\nCalibrating Qubit {qubit_id}...")

    calib = EnhancedCalibration(soc, soccfg, config, outerFolder, qubit_id)

    max_num_steps = sum([
        run_transmission,
        run_coarse_spec,
        run_fine_spec,
        run_rabi,
        run_readout_opt * CalibrationConfig.MAX_REFINEMENT_ITERATIONS,
        run_qubit_opt * CalibrationConfig.MAX_REFINEMENT_ITERATIONS,
        run_coherence,
        run_singleshot,
        enable_refinement
    ])

    calib.setup_plot(max_num_steps)

    # Store QubitConfig parameters
    calib.OptReadout_index = OptReadout_index
    calib.OptQubit_index = OptQubit_index
    calib.varname_FF = varname_FF

    # Auto-detect number of readout qubits if not provided
    if num_readout_qubits is None:
        num_readout_qubits = len(config.get('Qubit_Readout_List', [1]))
    calib.num_readout_qubits = num_readout_qubits

    start_time = time.time()

    # Define experiment parameters
    Trans_params = {
        "reps": 250, "TransSpan": 1.5, "TransNumPoints": 91,
        "readout_length": 2.5, 'cav_relax_delay': 10
    }

    First_Spec_params = {
        "qubit_gain": 500, "SpecSpan": 100, "SpecNumPoints": 71,
        'Gauss': False, "sigma": 0.07, "Gauss_gain": 3350,
        'reps': 200, 'rounds': 1
    }

    Second_Spec_params = {
        "qubit_gain": 50, "SpecSpan": 10, "SpecNumPoints": 81,
        'Gauss': False, "sigma": 0.05, "Gauss_gain": 1200,
        'reps': 250, 'rounds': 1
    }

    Rabi_params = {
        "max_gain": 12000, 'relax_delay': 100
    }

    if qubit_id in [3, 5]:
        Rabi_params['max_gain'] *= 1.4

    SS_R_params = {
        "Shots": 500, 'relax_delay': 150,
        "gain_start": 200, "gain_stop": 1400, "gain_pts": 8,
        "span": 1, "trans_pts": 5, 'number_of_pulses': 1,
        'qubit_sweep_index': OptReadout_index
    }

    SS_Q_params = {
        "Shots": 500, 'relax_delay': 150,
        "q_gain_span": 2 * 1000, "q_gain_pts": 7,
        "q_freq_span": 2 * 3, "q_freq_pts": 7,
        'number_of_pulses': 1,
        'readout_index': OptReadout_index,
        'qubit_sweep_index': OptQubit_index
    }

    SS_params = {
        "Shots": 2500,
        'number_of_pulses': 1,
        'relax_delay': 200
    }

    t1_params = {"stop_delay_us": 100, "expts": 40, "reps": 150}

    t2_params = {
        "stop_delay_us": 5,
        "expts": 125,
        "reps": 300,
        "freq_shift": 0.0,
        "phase_shift_cycles": -3,
        "relax_delay": 150
    }

    # Run calibration steps
    if run_transmission:
        calib.run_transmission(Trans_params)

    if run_coarse_spec:
        calib.run_spectroscopy(First_Spec_params, coarse=True)

    if run_fine_spec:
        calib.run_spectroscopy(Second_Spec_params, coarse=False)

    if run_rabi:
        calib.run_rabi(Rabi_params, OptQubit_index)

    # Optimization with optional refinement
    final_fidelity = 0
    if run_readout_opt:
        data, fid = calib.run_readout_optimization(SS_R_params | SS_params, OptReadout_index, iteration=1)
        final_fidelity = fid

        # Iterative refinement if fidelity is low
        if enable_refinement and fid < CalibrationConfig.MIN_FIDELITY:
            print(f"Fidelity {fid:.3f} < {CalibrationConfig.MIN_FIDELITY}, attempting refinement...")

            for iter_num in range(2, CalibrationConfig.MAX_REFINEMENT_ITERATIONS + 1):
                # Narrow the search range around current best
                refined_params = SS_R_params.copy()
                current_gain = config["res_gains"][OptReadout_index] * 32766
                current_freq = config["res_freqs"][OptReadout_index]

                refined_params["gain_start"] = max(100, int(current_gain - 300))
                refined_params["gain_stop"] = int(current_gain + 300)
                refined_params["span"] = 0.5

                refined_params['Shots'] += 200

                data, fid = calib.run_readout_optimization(refined_params | SS_params, OptReadout_index,
                                                           iteration=iter_num)
                final_fidelity = fid

                if fid >= CalibrationConfig.MIN_FIDELITY:
                    print(f"Refinement successful: fidelity = {fid:.3f}")
                    break
                else:
                    print(f"Refinement failed: fidelity = {fid:.3f}")

    if run_qubit_opt:
        data, fid = calib.run_qubit_optimization(SS_Q_params | SS_params, OptQubit_index, iteration=1)
        final_fidelity = max(final_fidelity, fid)

        # Iterative refinement
        if enable_refinement and fid < CalibrationConfig.MIN_FIDELITY:
            print(f"Fidelity {fid:.3f} < {CalibrationConfig.MIN_FIDELITY}, attempting refinement...")

            for iter_num in range(2, CalibrationConfig.MAX_REFINEMENT_ITERATIONS + 1):
                refined_params = SS_Q_params.copy()
                refined_params["q_gain_span"] = 1000
                refined_params["q_freq_span"] = 2

                refined_params["Shots"] += 200

                data, fid = calib.run_qubit_optimization(refined_params | SS_params, OptQubit_index, iteration=iter_num)
                final_fidelity = max(final_fidelity, fid)

                if fid >= CalibrationConfig.MIN_FIDELITY:
                    print(f"Refinement successful: fidelity = {fid:.3f}")
                    break

    if run_coherence:
        calib.run_coherence_check(t1_params, t2_params)

    if run_singleshot:
        calib.run_singleshot_verification(SS_params)

    # Finalize
    elapsed_time = time.time() - start_time
    print(f"\nCalibration complete - Qubit {qubit_id}")
    print(f"Total time: {elapsed_time / 60:.1f} minutes")
    print(f"Final fidelity: {final_fidelity:.3f}")
    calib.set_final_fidelity(final_fidelity)

    qubit_config, additional_data = calib.finalize()

    return config, calib.checker, qubit_config, additional_data


# =============================================================================
# Calibration Config Thresholds
# =============================================================================

class CalibrationConfig:
    """Centralized calibration configuration and thresholds"""

    # Quality thresholds
    MIN_FIDELITY = 0.85  # Target acceptable single-shot fidelity
    MIN_T1 = 10.0  # Minimum T1 (us)
    MIN_T2 = 1.0  # Minimum T2 (us)
    MAX_FREQ_DRIFT = 10.0  # Maximum frequency drift from nominal (MHz)
    # Could add stark shift?
    MAX_REFINEMENT_ITERATIONS = 3 # Iterative refinement


def main():

    ##### Calibration Parameters #####
    qubits_to_calibrate = [4]
    varname_FF = 'Readout_1234_FF'

    run_transmission = t
    run_coarse_spec = t
    run_fine_spec = t
    run_rabi = t
    run_readout_opt = t
    run_qubit_opt = t
    run_coherence = t
    run_singleshot = t
    enable_refinement = t

    print_summary = t
    #################################

    Qubit_configs = []  # Saves all final qubit configurations
    checkers_list = []  # Store all QualityChecker objects used
    additional_qubit_data = [] # Store additional qubit data such as T1/T2

    for Q in qubits_to_calibrate:
        # Set up qubit-specific parameters
        Qubit_Readout = [Q]
        Qubit_Pulse = [Q]

        pulse_numbers = [int(label[0]) if isinstance(label, str) else label for label in Qubit_Readout]
        OptReadout_index = pulse_numbers.index(Q)
        pulse_numbers = [int(label[0]) if isinstance(label, str) else label for label in Qubit_Pulse]
        OptQubit_index = pulse_numbers.index(Q)

        FF_gain1_BS = -5000
        FF_gain2_BS = -15000
        FF_gain3_BS = 0
        FF_gain4_BS = 0
        FF_gain5_BS = 0
        FF_gain6_BS = 0
        FF_gain7_BS = 0
        FF_gain8_BS = 0
        exec(open("UPDATE_CONFIG.py").read())

        # Run calibration
        config, checker, qubit_config, additional_data = run_enhanced_calibration(
            soc=soc,
            soccfg=soccfg,
            config=config,
            outerFolder=outerFolder,
            qubit_id=Q,
            OptReadout_index=OptReadout_index,
            OptQubit_index=OptQubit_index,
            num_readout_qubits=len(Qubit_Readout),
            varname_FF=varname_FF,
            run_transmission=run_transmission,
            run_coarse_spec=run_coarse_spec,
            run_fine_spec=run_fine_spec,
            run_rabi=run_rabi,
            run_readout_opt=run_readout_opt,
            run_qubit_opt=run_qubit_opt,
            run_coherence=run_coherence,
            run_singleshot=run_singleshot,
            enable_refinement=enable_refinement  # Enable iterative refinement for low fidelity
        )

        # Collect QubitConfig object
        if qubit_config is not None:
            Qubit_configs.append(qubit_config)
            checkers_list.append(checker)
            additional_qubit_data.append(additional_data)

    print("=" * 17)
    print(f"FINAL QUBIT PARAMETERS")
    print("=" * 17)

    if print_summary and len(Qubit_configs) > 0:
        # Print the final summary
        summary_fig = create_calibration_summary_dashboard(
            Qubit_configs,
            additional_qubit_data,
            checkers_list,
        )

        # Print all calibrated qubit configs (same format as original Fast_calib.py)
        for qconf in Qubit_configs:
            print(qconf)

    plt.show()

if __name__ == "__main__":
    main()