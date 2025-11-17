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
    Professional academic style with number line visualizations
    """
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np
    from datetime import datetime

    # Extract data from all qubits
    qubit_data = []
    for qconf, add_data, checker in zip(Qubit_configs, additional_qubit_data, checkers):
        qubit_data.append({
            'qubit_id': qconf.Q,
            'qubit_freq': qconf.qubit_freq,
            'resonator_freq': qconf.resonator_freq,
            'qubit_gain': qconf.qubit_gain,
            'resonator_gain': qconf.res_gain,  # Already normalized (0-1)
            'fidelity': add_data['fidelity'],
            'T1': add_data['T1'],
            'T2': add_data['T2'],
            'warnings': len(checker.warnings),
            'issues': len(checker.issues),
            'warning_list': checker.warnings,
            'issue_list': checker.issues
        })

    # Create figure with academic layout
    fig = plt.figure(figsize=(20, 12))
    fig.patch.set_facecolor('white')

    # Define grid: main plots on left (2/3), summary on right (1/3)
    gs = fig.add_gridspec(5, 3, hspace=0.4, wspace=0.4,
                          left=0.06, right=0.98, top=0.94, bottom=0.05,
                          width_ratios=[1, 1, 1.2])

    # Title
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    fig.suptitle(f'Quantum Calibration Summary | {timestamp}',
                 fontsize=16, fontweight='normal', family='serif')

    qubit_ids = [q['qubit_id'] for q in qubit_data]
    n_qubits = len(qubit_ids)

    # Color scheme: academic palette
    qubit_colors = plt.cm.tab10(np.linspace(0, 0.9, n_qubits))

    def get_status_color(fid, issues):
        """Determine status color based on fidelity and issues"""
        if issues > 0:
            return '#D32F2F'  # Red
        elif fid >= 0.95:
            return '#388E3C'  # Green
        elif fid >= 0.90:
            return '#F57C00'  # Orange
        else:
            return '#D32F2F'  # Red

    # ========================================================================
    # PANEL 1: FREQUENCY NUMBER LINE (Top row, spans 2 columns)
    # ========================================================================
    ax_freq = fig.add_subplot(gs[0, 0:2])

    qubit_freqs = [q['qubit_freq'] for q in qubit_data]
    resonator_freqs = [q['resonator_freq'] for q in qubit_data]

    # Combine all frequencies to determine range
    all_freqs = qubit_freqs + resonator_freqs
    freq_min, freq_max = min(all_freqs), max(all_freqs)
    freq_range = freq_max - freq_min
    margin = max(freq_range * 0.15, 50)  # At least 50 MHz margin

    # Draw number line
    ax_freq.axhline(0, color='black', linewidth=1.5, zorder=1)
    ax_freq.set_xlim(freq_min - margin, freq_max + margin)
    ax_freq.set_ylim(-1.5, 2)

    # Plot qubit frequencies (above line)
    for i, (qid, qf, color) in enumerate(zip(qubit_ids, qubit_freqs, qubit_colors)):
        ax_freq.scatter(qf, 0.8, s=200, marker='o', color=color,
                        edgecolor='black', linewidth=1.5, zorder=3, label=f'Q{qid}')
        ax_freq.plot([qf, qf], [0, 0.8], color=color, linewidth=1.5,
                     linestyle='--', alpha=0.5, zorder=2)
        ax_freq.text(qf, 1.1, f'Q{qid}\n{qf:.1f}', ha='center', va='bottom',
                     fontsize=9, fontweight='bold')

    # Plot resonator frequencies (below line)
    for i, (qid, rf, color) in enumerate(zip(qubit_ids, resonator_freqs, qubit_colors)):
        ax_freq.scatter(rf, -0.8, s=200, marker='s', color=color,
                        edgecolor='black', linewidth=1.5, zorder=3)
        ax_freq.plot([rf, rf], [0, -0.8], color=color, linewidth=1.5,
                     linestyle='--', alpha=0.5, zorder=2)
        ax_freq.text(rf, -1.1, f'{rf:.1f}\nR{qid}', ha='center', va='top',
                     fontsize=9, fontweight='bold')

    ax_freq.set_xlabel('Frequency (MHz)', fontsize=11, fontweight='bold')
    ax_freq.set_title('Frequency Distribution', fontsize=12, fontweight='bold', pad=10)
    ax_freq.set_yticks([])
    ax_freq.spines['left'].set_visible(False)
    ax_freq.spines['right'].set_visible(False)
    ax_freq.spines['top'].set_visible(False)

    # Add legend for symbols
    qubit_patch = mpatches.Patch(color='gray', label='○ Qubit')
    res_patch = mpatches.Patch(color='gray', label='□ Resonator')
    ax_freq.legend(handles=[qubit_patch, res_patch], loc='upper left',
                   fontsize=9, frameon=True, edgecolor='black')

    # ========================================================================
    # PANEL 2: GAIN NUMBER LINE (Second row, spans 2 columns)
    # ========================================================================
    ax_gains = fig.add_subplot(gs[1, 0:2])

    qubit_gains = [q['qubit_gain'] for q in qubit_data]
    resonator_gains = [q['resonator_gain'] for q in qubit_data]  # Keep as 0-1

    # Separate scales for qubit (large) and resonator (small) gains
    # We'll normalize and show them on the same axis with dual labels

    # Draw number line
    ax_gains.axhline(0, color='black', linewidth=1.5, zorder=1)

    # Find max qubit gain for scaling
    max_q_gain = max(qubit_gains)
    gain_margin = max_q_gain * 0.15
    ax_gains.set_xlim(-gain_margin, max_q_gain + gain_margin)
    ax_gains.set_ylim(-1.5, 2)

    # Plot qubit gains (above line)
    for i, (qid, qg, color) in enumerate(zip(qubit_ids, qubit_gains, qubit_colors)):
        ax_gains.scatter(qg, 0.8, s=200, marker='o', color=color,
                         edgecolor='black', linewidth=1.5, zorder=3)
        ax_gains.plot([qg, qg], [0, 0.8], color=color, linewidth=1.5,
                      linestyle='--', alpha=0.5, zorder=2)
        ax_gains.text(qg, 1.1, f'Q{qid}\n{int(qg)}', ha='center', va='bottom',
                      fontsize=9, fontweight='bold')

    # Plot resonator gains (below line) - scale to same axis
    # Convert 0-1 scale to match qubit gain axis
    scaled_res_gains = [rg * max_q_gain for rg in resonator_gains]
    for i, (qid, rg_scaled, rg_actual, color) in enumerate(zip(qubit_ids, scaled_res_gains,
                                                               resonator_gains, qubit_colors)):
        ax_gains.scatter(rg_scaled, -0.8, s=200, marker='s', color=color,
                         edgecolor='black', linewidth=1.5, zorder=3)
        ax_gains.plot([rg_scaled, rg_scaled], [0, -0.8], color=color, linewidth=1.5,
                      linestyle='--', alpha=0.5, zorder=2)
        ax_gains.text(rg_scaled, -1.1, f'{rg_actual:.3f}\nR{qid}', ha='center', va='top',
                      fontsize=9, fontweight='bold')

    ax_gains.set_xlabel('Qubit Gain (a.u.) | Resonator Gain (normalized)',
                        fontsize=11, fontweight='bold')
    ax_gains.set_title('Pulse Gain Distribution', fontsize=12, fontweight='bold', pad=10)
    ax_gains.set_yticks([])
    ax_gains.spines['left'].set_visible(False)
    ax_gains.spines['right'].set_visible(False)
    ax_gains.spines['top'].set_visible(False)

    # Add legend
    qubit_patch = mpatches.Patch(color='gray', label='○ Qubit (a.u.)')
    res_patch = mpatches.Patch(color='gray', label='□ Resonator (0-1)')
    ax_gains.legend(handles=[qubit_patch, res_patch], loc='upper left',
                    fontsize=9, frameon=True, edgecolor='black')

    # ========================================================================
    # PANEL 3: FIDELITY (Third row, left)
    # ========================================================================
    ax_fid = fig.add_subplot(gs[2, 0])

    fidelities = [q['fidelity'] for q in qubit_data]
    x_pos = np.arange(n_qubits)

    bars = ax_fid.bar(x_pos, [f * 100 for f in fidelities],
                      color=qubit_colors, alpha=0.7, edgecolor='black', linewidth=1)

    # Add value labels
    for i, (bar, fid) in enumerate(zip(bars, fidelities)):
        height = bar.get_height()
        ax_fid.text(bar.get_x() + bar.get_width() / 2., height + 0.5,
                    f'{fid * 100:.1f}%', ha='center', va='bottom', fontsize=9)

    ax_fid.axhline(95, color='#388E3C', linestyle='--', linewidth=1.5,
                   alpha=0.5, label='95% target')
    ax_fid.axhline(90, color='#F57C00', linestyle='--', linewidth=1.5,
                   alpha=0.5, label='90% target')

    ax_fid.set_xticks(x_pos)
    ax_fid.set_xticklabels([f'Q{qid}' for qid in qubit_ids], fontsize=10)
    ax_fid.set_ylabel('Fidelity (%)', fontsize=10, fontweight='bold')
    ax_fid.set_title('Single-Shot Readout Fidelity', fontsize=11, fontweight='bold')
    ax_fid.set_ylim(80, 100)
    ax_fid.legend(fontsize=8, loc='lower right', frameon=True, edgecolor='black')
    ax_fid.grid(axis='y', alpha=0.3, linestyle=':')
    ax_fid.set_axisbelow(True)

    # ========================================================================
    # PANEL 4: COHERENCE TIMES (Third row, center)
    # ========================================================================
    ax_coh = fig.add_subplot(gs[2, 1])

    T1_values = [q['T1'] if q['T1'] else 0 for q in qubit_data]
    T2_values = [q['T2'] if q['T2'] else 0 for q in qubit_data]

    x_pos = np.arange(n_qubits)
    width = 0.35

    bars1 = ax_coh.bar(x_pos - width / 2, T1_values, width, label='T₁',
                       color='#1976D2', alpha=0.7, edgecolor='black', linewidth=1)
    bars2 = ax_coh.bar(x_pos + width / 2, T2_values, width, label='T₂',
                       color='#7B1FA2', alpha=0.7, edgecolor='black', linewidth=1)

    # Add value labels
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax_coh.text(bar.get_x() + bar.get_width() / 2., height + 0.5,
                            f'{height:.1f}', ha='center', va='bottom', fontsize=8)

    ax_coh.set_xticks(x_pos)
    ax_coh.set_xticklabels([f'Q{qid}' for qid in qubit_ids], fontsize=10)
    ax_coh.set_ylabel('Time (μs)', fontsize=10, fontweight='bold')
    ax_coh.set_title('Coherence Times', fontsize=11, fontweight='bold')
    ax_coh.legend(fontsize=9, frameon=True, edgecolor='black')
    ax_coh.grid(axis='y', alpha=0.3, linestyle=':')
    ax_coh.set_axisbelow(True)

    # ========================================================================
    # PANEL 5: FREQUENCY DETUNINGS (Fourth row, left)
    # ========================================================================
    ax_det = fig.add_subplot(gs[3, 0])

    if n_qubits > 1:
        # Calculate all pairwise detunings (not just nearest neighbor)
        sorted_qubits = sorted(zip(qubit_ids, qubit_freqs), key=lambda x: x[1])
        detunings = []
        labels = []

        # Just nearest neighbors for clarity
        for i in range(len(sorted_qubits) - 1):
            q1_id, q1_freq = sorted_qubits[i]
            q2_id, q2_freq = sorted_qubits[i + 1]
            detuning = abs(q2_freq - q1_freq)
            detunings.append(detuning)
            labels.append(f'Q{q1_id}–Q{q2_id}')

        y_pos = np.arange(len(detunings))
        colors_det = ['#388E3C' if d > 50 else '#F57C00' if d > 20 else '#D32F2F'
                      for d in detunings]

        bars = ax_det.barh(y_pos, detunings, color=colors_det, alpha=0.7,
                           edgecolor='black', linewidth=1)

        # Add value labels
        for i, (bar, det) in enumerate(zip(bars, detunings)):
            width = bar.get_width()
            ax_det.text(width + 1, bar.get_y() + bar.get_height() / 2,
                        f'{det:.1f}', va='center', fontsize=9)

        ax_det.set_yticks(y_pos)
        ax_det.set_yticklabels(labels, fontsize=9)
        ax_det.set_xlabel('Detuning (MHz)', fontsize=10, fontweight='bold')
        ax_det.set_title('Nearest-Neighbor Detunings', fontsize=11, fontweight='bold')
        ax_det.axvline(50, color='#388E3C', linestyle='--', linewidth=1, alpha=0.4)
        ax_det.axvline(20, color='#F57C00', linestyle='--', linewidth=1, alpha=0.4)
        ax_det.grid(axis='x', alpha=0.3, linestyle=':')
        ax_det.set_axisbelow(True)
    else:
        ax_det.text(0.5, 0.5, 'Single Qubit\n(No Detunings)',
                    ha='center', va='center', fontsize=11,
                    transform=ax_det.transAxes, style='italic')
        ax_det.set_xticks([])
        ax_det.set_yticks([])
        for spine in ax_det.spines.values():
            spine.set_visible(False)

    # ========================================================================
    # PANEL 6: QUBIT FREQUENCY SPAN (Fourth row, center)
    # ========================================================================
    ax_span = fig.add_subplot(gs[3, 1])

    if n_qubits > 1:
        qubit_span = max(qubit_freqs) - min(qubit_freqs)
        res_span = max(resonator_freqs) - min(resonator_freqs)

        data_to_plot = [qubit_span, res_span]
        labels_span = ['Qubit\nSpan', 'Resonator\nSpan']
        colors_span = ['#1976D2', '#E53935']

        bars = ax_span.bar(range(2), data_to_plot, color=colors_span,
                           alpha=0.7, edgecolor='black', linewidth=1)

        for bar, val in zip(bars, data_to_plot):
            height = bar.get_height()
            ax_span.text(bar.get_x() + bar.get_width() / 2., height + 2,
                         f'{val:.1f}', ha='center', va='bottom', fontsize=9, fontweight='bold')

        ax_span.set_xticks(range(2))
        ax_span.set_xticklabels(labels_span, fontsize=10)
        ax_span.set_ylabel('Frequency Span (MHz)', fontsize=10, fontweight='bold')
        ax_span.set_title('Frequency Distribution Span', fontsize=11, fontweight='bold')
        ax_span.grid(axis='y', alpha=0.3, linestyle=':')
        ax_span.set_axisbelow(True)
    else:
        ax_span.text(0.5, 0.5, 'Single Qubit\n(No Span)',
                     ha='center', va='center', fontsize=11,
                     transform=ax_span.transAxes, style='italic')
        ax_span.set_xticks([])
        ax_span.set_yticks([])
        for spine in ax_span.spines.values():
            spine.set_visible(False)

    # ========================================================================
    # RIGHT COLUMN: DETAILED SUMMARY (spans all rows)
    # ========================================================================
    ax_summary = fig.add_subplot(gs[:, 2])
    ax_summary.axis('off')

    # Build detailed summary text
    summary_lines = []
    summary_lines.append("=" * 65)
    summary_lines.append("         CALIBRATION SUMMARY REPORT")
    summary_lines.append("=" * 65)
    summary_lines.append("")

    for i, (q, checker) in enumerate(zip(qubit_data, checkers)):
        qid = q['qubit_id']

        # Status indicator
        if q['issues'] > 0:
            status = "✗ ISSUES"
            color_code = '▓'  # Dark block
        elif q['warnings'] > 0:
            status = "⚠ WARNINGS"
            color_code = '▒'  # Medium block
        else:
            status = "✓ PASSED"
            color_code = '░'  # Light block

        summary_lines.append(f"{color_code * 3} QUBIT {qid} — {status} {color_code * 3}")
        summary_lines.append("-" * 65)

        # Core parameters
        summary_lines.append(f"  Qubit Frequency:      {q['qubit_freq']:>8.2f} MHz")
        summary_lines.append(f"  Resonator Frequency:  {q['resonator_freq']:>8.2f} MHz")
        summary_lines.append(f"  Qubit Gain:           {q['qubit_gain']:>8.0f} a.u.")
        summary_lines.append(f"  Resonator Gain:       {q['resonator_gain']:>8.4f} (norm.)")
        summary_lines.append("")

        # Performance metrics
        summary_lines.append(f"  Readout Fidelity:     {q['fidelity'] * 100:>8.2f} %")
        if q['T1']:
            summary_lines.append(f"  T₁ Coherence:         {q['T1']:>8.1f} μs")
        else:
            summary_lines.append(f"  T₁ Coherence:         {'N/A':>8}")
        if q['T2']:
            summary_lines.append(f"  T₂ Coherence:         {q['T2']:>8.1f} μs")
        else:
            summary_lines.append(f"  T₂ Coherence:         {'N/A':>8}")
        summary_lines.append("")

        # Quality assessment
        summary_lines.append(f"  Warnings:             {q['warnings']:>8}")
        summary_lines.append(f"  Critical Issues:      {q['issues']:>8}")

        # List specific warnings/issues
        if q['warning_list']:
            summary_lines.append("")
            summary_lines.append("  ⚠ Warnings:")
            for warn in q['warning_list']:
                # Wrap long warnings
                if len(warn) > 55:
                    words = warn.split()
                    line = "    • "
                    for word in words:
                        if len(line) + len(word) + 1 > 63:
                            summary_lines.append(line)
                            line = "      " + word
                        else:
                            line += word + " "
                    if line.strip():
                        summary_lines.append(line.rstrip())
                else:
                    summary_lines.append(f"    • {warn}")

        if q['issue_list']:
            summary_lines.append("")
            summary_lines.append("  ✗ Critical Issues:")
            for issue in q['issue_list']:
                # Wrap long issues
                if len(issue) > 55:
                    words = issue.split()
                    line = "    • "
                    for word in words:
                        if len(line) + len(word) + 1 > 63:
                            summary_lines.append(line)
                            line = "      " + word
                        else:
                            line += word + " "
                    if line.strip():
                        summary_lines.append(line.rstrip())
                else:
                    summary_lines.append(f"    • {issue}")

        summary_lines.append("")
        if i < len(qubit_data) - 1:
            summary_lines.append("")

    summary_lines.append("=" * 65)

    # Overall statistics
    total_warnings = sum(q['warnings'] for q in qubit_data)
    total_issues = sum(q['issues'] for q in qubit_data)
    avg_fidelity = np.mean(fidelities) * 100

    summary_lines.append("OVERALL STATISTICS")
    summary_lines.append("-" * 65)
    summary_lines.append(f"  Total Qubits:         {n_qubits:>8}")
    summary_lines.append(f"  Average Fidelity:     {avg_fidelity:>8.2f} %")
    summary_lines.append(f"  Total Warnings:       {total_warnings:>8}")
    summary_lines.append(f"  Total Issues:         {total_issues:>8}")
    summary_lines.append("=" * 65)

    summary_text = "\n".join(summary_lines)

    # Determine background color
    if total_issues == 0 and total_warnings == 0:
        bg_color = '#E8F5E9'  # Light green
    elif total_issues == 0:
        bg_color = '#FFF3E0'  # Light orange
    else:
        bg_color = '#FFEBEE'  # Light red

    ax_summary.text(0.05, 0.98, summary_text,
                    fontsize=8, fontfamily='monospace',
                    verticalalignment='top', horizontalalignment='left',
                    bbox=dict(boxstyle='round,pad=0.8', facecolor=bg_color,
                              alpha=0.6, edgecolor='black', linewidth=1.5),
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
            figsize=(15, 8),
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
        run_singleshot
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
    MIN_FIDELITY = 0.80  # Target acceptable single-shot fidelity
    MIN_T1 = 10.0  # Minimum T1 (us)
    MIN_T2 = 1.0  # Minimum T2 (us)
    MAX_FREQ_DRIFT = 10.0  # Maximum frequency drift from nominal (MHz)
    # Could add stark shift?
    MAX_REFINEMENT_ITERATIONS = 1 # Iterative refinement


if __name__ == "__main__":

    ##################################
    ##### Calibration Parameters #####
    ##################################
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
    ##################################
    ##################################
    ##################################

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