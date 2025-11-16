"""
Fast Calibration Script

Improvements over original Fast_calib.py:
- Modular structure with calibration stages
- Quality checks after each step with warnings based on specified thresholds
- Optional T1/T2 coherence checks
- Iterative refinement for low fidelity results
"""

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


# =============================================================================
# Calibration Config Thresholds
# =============================================================================

class CalibrationConfig:
    """Centralized calibration configuration and thresholds"""

    # Quality thresholds
    MIN_FIDELITY = 0.85  # Target acceptable single-shot fidelity
    MIN_T1 = 10.0  # Minimum T1 (us)
    MIN_T2 = 5.0  # Minimum T2 (us)
    MAX_FREQ_DRIFT = 10.0  # Maximum frequency drift from nominal (MHz)
    # Could add stark shift?

    # Iterative refinement
    MAX_REFINEMENT_ITERATIONS = 2

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

    def setup_plot(self, num_steps=6):
        """Set up figure for displaying results"""
        self.fig, self.axs = plt.subplots(4, 3, figsize=(15, 8), tight_layout=True)
        self.fig.suptitle(f"Qubit_{self.qubit_id}_Calibration_{datetime.now().strftime('%Y_%m_%d_%H_%M')}",
                          fontsize=14)
        self.iter_axs = iter(self.axs.flatten())
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
        data = expt.acquire_display_save(plotDisp=True, block=False, ax=next(self.iter_axs))
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
        data = expt.acquire_display_save(plotDisp=True, block=False, ax=next(self.iter_axs))
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
            return qubit_config
        return None


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
        run_singleshot=True,
        run_coherence=False,
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
    calib.setup_plot()

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
        'reps': 144, 'rounds': 1
    }

    Second_Spec_params = {
        "qubit_gain": 50, "SpecSpan": 10, "SpecNumPoints": 81,
        'Gauss': False, "sigma": 0.05, "Gauss_gain": 1200,
        'reps': 200, 'rounds': 1
    }

    Rabi_params = {
        "max_gain": 12000, 'relax_delay': 150
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
        'relax_delay': 250
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

                refined_params['reps'] += 200

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

                refined_params["reps"] += 200

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

    qubit_config = calib.finalize()

    return config, calib.checker, qubit_config

if __name__ == "__main__":

    qubits_to_calibrate = [4]
    Qubit_configs = []
    varname_FF = 'Readout_1234_FF'

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
        config, checker, qubit_config = run_enhanced_calibration(
            soc=soc,
            soccfg=soccfg,
            config=config,
            outerFolder=outerFolder,
            qubit_id=Q,
            OptReadout_index=OptReadout_index,
            OptQubit_index=OptQubit_index,
            num_readout_qubits=len(Qubit_Readout),
            varname_FF=varname_FF,
            run_transmission=       True,
            run_coarse_spec=        True,
            run_fine_spec=          True,
            run_rabi=               True,
            run_readout_opt=        True,
            run_qubit_opt=          True,
            run_singleshot=         True,
            run_coherence=          True,
            enable_refinement=      True  # Enable iterative refinement for low fidelity
        )

        # Collect QubitConfig object
        if qubit_config is not None:
            Qubit_configs.append(qubit_config)

    print("=" * 17)
    print(f"FINAL QUBIT PARAMETERS")
    print("=" * 17)
    # Print all calibrated qubit configs (same format as original Fast_calib.py)
    for qconf in Qubit_configs:
        print(qconf)

    plt.show()
