"""
==============
SmartFitter.py
==============
Intelligent fitting system that analyzes data and suggests/applies appropriate fits.
Includes common quantum experiment models and general curve fitting.
"""

import numpy as np
from scipy.optimize import curve_fit
from scipy.signal import find_peaks
from scipy.fft import fft, fftfreq
from scipy.ndimage import center_of_mass
import traceback
from PyQt5.QtCore import qInfo, qWarning, qCritical
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Callable
from abc import ABC, abstractmethod


@dataclass
class FitResult:
    """Data class to store fitting results."""
    model_name: str
    params: Dict[str, float]
    params_stderr: Dict[str, float]
    fit_data: np.ndarray
    r_squared: float
    success: bool
    message: str
    equation: str

    def format_params(self) -> str:
        """Format parameters as a readable string."""
        lines = [f"Model: {self.model_name}", f"R^2 = {self.r_squared:.4f}", ""]
        for name, value in self.params.items():
            stderr = self.params_stderr.get(name, 0)
            lines.append(f"{name} = {value:.6g} +/- {stderr:.6g}")
        return "\n".join(lines)


class FitModel(ABC):
    """Base class for all fit models."""

    def __init__(self):
        self.name = "Base Model"
        self.description = "Base fit model"
        self.param_names = []
        self.equation = ""

    @abstractmethod
    def function(self, x: np.ndarray, *params) -> np.ndarray:
        """The mathematical function to fit."""
        pass

    @abstractmethod
    def initial_guess(self, x: np.ndarray, y: np.ndarray) -> List[float]:
        """Generate initial parameter guess from data."""
        pass

    @abstractmethod
    def bounds(self, x: np.ndarray, y: np.ndarray) -> Tuple[List[float], List[float]]:
        """Return parameter bounds (lower, upper)."""
        pass

    def fit(self, x: np.ndarray, y: np.ndarray) -> FitResult:
        """Perform the fit and return results."""
        try:
            # Get initial guess and bounds
            p0 = self.initial_guess(x, y)
            bounds = self.bounds(x, y)

            # Perform curve fit
            popt, pcov = curve_fit(self.function, x, y, p0=p0, bounds=bounds, maxfev=10000)

            # Calculate uncertainties
            perr = np.sqrt(np.diag(pcov))

            # Generate fit data
            x_fit = np.linspace(x.min(), x.max(), 500)
            y_fit = self.function(x_fit, *popt)

            # Calculate R-squared
            residuals = y - self.function(x, *popt)
            ss_res = np.sum(residuals ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

            # Package results
            params_dict = {name: val for name, val in zip(self.param_names, popt)}
            params_stderr_dict = {name: val for name, val in zip(self.param_names, perr)}

            return FitResult(
                model_name=self.name,
                params=params_dict,
                params_stderr=params_stderr_dict,
                fit_data=np.column_stack([x_fit, y_fit]),
                r_squared=r_squared,
                success=True,
                message="Fit successful",
                equation=self.equation
            )

        except Exception as e:
            qWarning(f"Fit failed for {self.name}: {str(e)}")
            return FitResult(
                model_name=self.name,
                params={},
                params_stderr={},
                fit_data=np.array([]),
                r_squared=0,
                success=False,
                message=f"Fit failed: {str(e)}",
                equation=self.equation
            )


# ==================== 1D Fit Models ====================

class LinearModel(FitModel):
    """Linear fit: y = m*x + b"""

    def __init__(self):
        super().__init__()
        self.name = "Linear"
        self.description = "Linear fit"
        self.param_names = ["slope", "intercept"]
        self.equation = "y = m*x + b"

    def function(self, x, m, b):
        return m * x + b

    def initial_guess(self, x, y):
        m = (y[-1] - y[0]) / (x[-1] - x[0]) if x[-1] != x[0] else 0
        b = y[0]
        return [m, b]

    def bounds(self, x, y):
        return ([-np.inf, -np.inf], [np.inf, np.inf])


class SinusoidalModel(FitModel):
    """Sinusoidal fit: y = A*sin(2*pi*f*x + phi) + offset"""

    def __init__(self):
        super().__init__()
        self.name = "Sinusoidal"
        self.description = "Sinusoidal oscillation"
        self.param_names = ["amplitude", "frequency", "phase", "offset"]
        self.equation = "y = A*sin(2*pi*f*x + phi) + offset"

    def function(self, x, A, f, phi, offset):
        return A * np.sin(2 * np.pi * f * x + phi) + offset

    def initial_guess(self, x, y):
        # FFT to estimate frequency
        N = len(x)
        T = (x[-1] - x[0]) / (N - 1) if N > 1 else 1
        yf = fft(y - np.mean(y))
        xf = fftfreq(N, T)[:N // 2]

        # Find dominant frequency
        power = np.abs(yf[:N // 2])
        if len(power) > 1:
            freq_idx = np.argmax(power[1:]) + 1  # Skip DC component
            f_guess = abs(xf[freq_idx])
        else:
            f_guess = 1 / (x[-1] - x[0]) if x[-1] != x[0] else 1

        A_guess = (np.max(y) - np.min(y)) / 2
        offset_guess = np.mean(y)
        phi_guess = 0

        return [A_guess, f_guess, phi_guess, offset_guess]

    def bounds(self, x, y):
        y_range = np.max(y) - np.min(y)
        max_freq = 20 / (x[-1] - x[0]) if x[-1] != x[0] else 20
        return (
            [0, 0, -2 * np.pi, np.min(y) - y_range],
            [y_range * 2, max_freq, 2 * np.pi, np.max(y) + y_range]
        )


class RabiModel(FitModel):
    """Rabi oscillations: y = A*exp(-x/T2)*sin(2*pi*f*x + phi) + offset"""

    def __init__(self):
        super().__init__()
        self.name = "Rabi Oscillations"
        self.description = "Damped Rabi oscillations"
        self.param_names = ["amplitude", "T2_Rabi", "rabi_freq", "phase", "offset"]
        self.equation = "y = A*exp(-x/T2)*sin(2*pi*f*x + phi) + offset"

    def function(self, x, A, T2, f, phi, offset):
        return A * np.exp(-x / T2) * np.sin(2 * np.pi * f * x + phi) + offset

    def initial_guess(self, x, y):
        # Use sinusoidal model for initial frequency/phase
        sin_model = SinusoidalModel()
        A, f, phi, offset = sin_model.initial_guess(x, y)

        # Estimate decay from envelope
        envelope = np.abs(y - offset)
        if len(envelope) > 2:
            # Find where amplitude drops to 1/e
            target = A / np.e
            try:
                tau_idx = np.where(envelope < target)[0][0] if np.any(envelope < target) else len(x) // 2
                T2 = x[tau_idx] - x[0]
            except:
                T2 = (x[-1] - x[0]) / 2
        else:
            T2 = (x[-1] - x[0]) / 2

        return [A, max(T2, (x[-1] - x[0]) / 100), f, phi, offset]

    def bounds(self, x, y):
        y_range = np.max(y) - np.min(y)
        x_range = x[-1] - x[0]
        max_freq = 20 / x_range if x_range > 0 else 20
        return (
            [0, x_range / 100, 0, -2 * np.pi, np.min(y) - y_range],
            [y_range * 2, x_range * 10, max_freq, 2 * np.pi, np.max(y) + y_range]
        )


class T1DecayModel(FitModel):
    """T1 decay: y = A*exp(-x/T1) + offset"""

    def __init__(self):
        super().__init__()
        self.name = "T1 Decay"
        self.description = "Energy relaxation (T1)"
        self.param_names = ["amplitude", "T1", "offset"]
        self.equation = "y = A*exp(-x/T1) + offset"

    def function(self, x, A, T1, offset):
        return A * np.exp(-x / T1) + offset

    def initial_guess(self, x, y):
        A = y[0] - y[-1]
        offset = y[-1]
        # Find where signal drops to 1/e
        target = A / np.e + offset
        try:
            tau_idx = np.argmin(np.abs(y - target))
            T1 = x[tau_idx] - x[0]
        except:
            T1 = (x[-1] - x[0]) / 3

        return [A, max(T1, (x[-1] - x[0]) / 100), offset]

    def bounds(self, x, y):
        y_range = np.max(y) - np.min(y)
        x_range = x[-1] - x[0]
        return (
            [-y_range * 2, x_range / 100, np.min(y) - y_range],
            [y_range * 2, x_range * 10, np.max(y) + y_range]
        )


class RamseyModel(FitModel):
    """Ramsey fringes: y = A*exp(-x/T2)*cos(2*pi*detuning*x + phi) + offset"""

    def __init__(self):
        super().__init__()
        self.name = "Ramsey Fringes"
        self.description = "Ramsey interference with T2* decay"
        self.param_names = ["amplitude", "T2_star", "detuning", "phase", "offset"]
        self.equation = "y = A*exp(-x/T2*)*cos(2*pi*Deltaf*x + phi) + offset"

    def function(self, x, A, T2_star, detuning, phi, offset):
        return A * np.exp(-x / T2_star) * np.cos(2 * np.pi * detuning * x + phi) + offset

    def initial_guess(self, x, y):
        # Similar to Rabi but use cosine
        sin_model = SinusoidalModel()
        A, f, phi, offset = sin_model.initial_guess(x, y)

        # Estimate decay
        envelope = np.abs(y - offset)
        if len(envelope) > 2:
            target = A / np.e
            try:
                tau_idx = np.where(envelope < target)[0][0] if np.any(envelope < target) else len(x) // 2
                T2_star = x[tau_idx] - x[0]
            except:
                T2_star = (x[-1] - x[0]) / 2
        else:
            T2_star = (x[-1] - x[0]) / 2

        return [A, max(T2_star, (x[-1] - x[0]) / 100), f, phi, offset]

    def bounds(self, x, y):
        y_range = np.max(y) - np.min(y)
        x_range = x[-1] - x[0]
        max_freq = 10 / x_range if x_range > 0 else 10
        return (
            [0, x_range / 100, 0, -2 * np.pi, np.min(y) - y_range],
            [y_range * 2, x_range * 10, max_freq, 2 * np.pi, np.max(y) + y_range]
        )


class GaussianModel(FitModel):
    """Gaussian: y = A*exp(-(x-mu)^2/(2*sigma^2)) + offset"""

    def __init__(self):
        super().__init__()
        self.name = "Gaussian"
        self.description = "Gaussian peak"
        self.param_names = ["amplitude", "center", "sigma", "offset"]
        self.equation = "y = A*exp(-(x-mu)^2/(2*sigma^2)) + offset"

    def function(self, x, A, mu, sigma, offset):
        return A * np.exp(-(x - mu) ** 2 / (2 * sigma ** 2)) + offset

    def initial_guess(self, x, y):
        offset = np.min(y)
        A = np.max(y) - offset
        mu = x[np.argmax(y)]
        sigma = (x[-1] - x[0]) / 6
        return [A, mu, abs(sigma), offset]

    def bounds(self, x, y):
        y_range = np.max(y) - np.min(y)
        x_range = x[-1] - x[0]
        return (
            [0, x[0] - x_range, x_range / 100, np.min(y) - y_range],
            [y_range * 2, x[-1] + x_range, x_range * 2, np.max(y) + y_range]
        )


class LorentzianModel(FitModel):
    """Lorentzian: y = A*gamma^2/((x-x0)^2 + gamma^2) + offset"""

    def __init__(self):
        super().__init__()
        self.name = "Lorentzian"
        self.description = "Lorentzian resonance"
        self.param_names = ["amplitude", "center", "gamma", "offset"]
        self.equation = "y = A*gamma^2/((x-x0)^2 + gamma^2) + offset"

    def function(self, x, A, x0, gamma, offset):
        return A * gamma ** 2 / ((x - x0) ** 2 + gamma ** 2) + offset

    def initial_guess(self, x, y):
        offset = np.min(y)
        A = (np.max(y) - offset)
        x0 = x[np.argmax(y)]
        gamma = (x[-1] - x[0]) / 10
        return [A, x0, abs(gamma), offset]

    def bounds(self, x, y):
        y_range = np.max(y) - np.min(y)
        x_range = x[-1] - x[0]
        return (
            [0, x[0] - x_range, x_range / 100, np.min(y) - y_range],
            [y_range * 3, x[-1] + x_range, x_range * 2, np.max(y) + y_range]
        )


class PolynomialModel(FitModel):
    """Polynomial fit"""

    def __init__(self, degree=2):
        super().__init__()
        self.degree = min(degree, 4)
        self.name = f"Polynomial (deg {self.degree})"
        self.description = f"Polynomial degree {self.degree}"
        self.param_names = [f"c{i}" for i in range(self.degree + 1)]
        self.equation = " + ".join([f"c{i}*x^{i}" if i > 0 else "c0" for i in range(self.degree + 1)])

    def function(self, x, *coeffs):
        return np.polyval(coeffs[::-1], x)

    def initial_guess(self, x, y):
        coeffs = np.polyfit(x, y, self.degree)
        return coeffs[::-1].tolist()

    def bounds(self, x, y):
        return ([-np.inf] * (self.degree + 1), [np.inf] * (self.degree + 1))


# ==================== 2D Analysis ====================

class Chevron2DAnalyzer:
    """Chevron pattern analysis for 2D image data with full fitting."""

    def __init__(self):
        self.name = "Chevron Pattern"
        self.description = "Analyzes and fits chevron/diamond patterns"

    @staticmethod
    def cosfit(t, freq, A, y0, tau, phi):
        """Damped cosine fit for each chevron row."""
        return y0 + np.abs(A) * np.exp(-t / np.abs(tau)) * np.cos(2 * np.pi * freq * t + phi)

    @staticmethod
    def freqfit(d, d0, b, g):
        d = np.asarray(d, dtype=np.float64)
        rad = b * (d - d0) ** 2 + g ** 2
        # Prevent tiny negative due to rounding, and larger negatives if b<0
        rad = np.maximum(rad, 0.0)
        return 2.0 * np.sqrt(rad)

    @staticmethod
    def frequency_guess(times, signal):
        """Estimate frequency from signal using FFT."""
        N = len(times)
        T = (times[-1] - times[0]) / (N - 1) if N > 1 else 1
        yf = fft(signal - np.mean(signal))
        xf = fftfreq(N, T)[:N // 2]

        power = np.abs(yf[:N // 2])
        if len(power) > 1:
            freq_idx = np.argmax(power[1:]) + 1
            return abs(xf[freq_idx])
        else:
            return 1 / (times[-1] - times[0]) if times[-1] != times[0] else 1

    def fit_chevron(self, gains: np.ndarray, times: np.ndarray, pop_matrix: np.ndarray,
                    b_guess: float = 1.36055267e-04, return_fit_points: bool = False) -> Dict:
        """
        Fit chevron pattern to extract coupling strength g and other parameters.

        Parameters:
        -----------
        gains : array of gains/detunings (y-axis)
        times : array of times (x-axis)
        pop_matrix : (gains, times) matrix of populations
        b_guess : initial guess for b parameter
        return_fit_points : whether to return individual fit points

        Returns:
        --------
        dict with fit parameters and optionally fit data
        """
        try:
            freq_list = []
            fit_gains_list = []
            row_fits = []

            qInfo(f"Fitting chevron: {pop_matrix.shape[0]} rows, {pop_matrix.shape[1]} columns")

            # Fit each row with damped cosine
            for i, row_data in enumerate(pop_matrix):
                try:
                    # Initial guess for cosine fit
                    freq_guess = self.frequency_guess(times, row_data)
                    amp_guess = np.max(row_data) - np.min(row_data)
                    y0_guess = row_data[0]
                    tau_guess = times[-1]
                    phi_guess = 1e-3

                    p0 = [freq_guess, amp_guess, y0_guess, tau_guess, phi_guess]

                    # Fit this row
                    cos_params, cos_cov = curve_fit(self.cosfit, times, row_data, p0, maxfev=int(1e9))

                    # Extract frequency and store
                    freq_list.append(cos_params[0])
                    fit_gains_list.append(gains[i])
                    row_fits.append({
                        'gain': gains[i],
                        'freq': cos_params[0],
                        'amplitude': cos_params[1],
                        'offset': cos_params[2],
                        'tau': cos_params[3],
                        'phi': cos_params[4]
                    })

                except RuntimeError as e:
                    qWarning(f"Row {i} fit failed: {str(e)}")
                    continue
                except Exception as e:
                    qWarning(f"Row {i} unexpected error: {str(e)}")
                    continue

            if len(freq_list) < 3:
                return {
                    "success": False,
                    "message": f"Too few successful row fits: {len(freq_list)}"
                }

            freq_list = np.array(freq_list)
            fit_gains_list = np.array(fit_gains_list)

            # Fit frequency vs gain to extract g (coupling strength)
            center_gain_guess = fit_gains_list[np.argmin(freq_list)]
            g_guess = np.min(freq_list) / 2

            p0 = [center_gain_guess, b_guess, g_guess]

            try:
                freq_params, freq_cov = curve_fit(self.freqfit, fit_gains_list, freq_list, p0=p0)

                # Calculate uncertainties
                freq_perr = np.sqrt(np.diag(freq_cov))

                # Generate fit curve
                gains_fit = np.linspace(fit_gains_list.min(), fit_gains_list.max(), 200)
                freq_fit = self.freqfit(gains_fit, *freq_params)

                # Calculate R-squared
                freq_predicted = self.freqfit(fit_gains_list, *freq_params)
                residuals = freq_list - freq_predicted
                ss_res = np.sum(residuals ** 2)
                ss_tot = np.sum((freq_list - np.mean(freq_list)) ** 2)
                r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

                result = {
                    "success": True,
                    "d0": freq_params[0],  # Center detuning
                    "d0_stderr": freq_perr[0],
                    "b": freq_params[1],  # Asymmetry parameter
                    "b_stderr": freq_perr[1],
                    "g": freq_params[2],  # Coupling strength (MHz if times in us)
                    "g_stderr": freq_perr[2],
                    "r_squared": r_squared,
                    "n_rows_fit": len(freq_list),
                    "sweet_spot_gain": freq_params[0],
                    "min_frequency": np.min(freq_list),
                    "equation": "f(Delta) = 2*sqrt(b*(Delta-Delta0)^2 + g^2)"
                }

                if return_fit_points:
                    result.update({
                        "freq_list": freq_list.tolist(),
                        "fit_gains_list": fit_gains_list.tolist(),
                        "gains_fit": gains_fit.tolist(),
                        "freq_fit": freq_fit.tolist(),
                        "row_fits": row_fits
                    })

                return result

            except Exception as e:
                return {
                    "success": False,
                    "message": f"Frequency fit failed: {str(e)}",
                    "freq_list": freq_list.tolist(),
                    "fit_gains_list": fit_gains_list.tolist()
                }

        except Exception as e:
            qWarning(f"Chevron fit failed: {str(e)}")
            traceback.print_exc()
            return {"success": False, "message": str(e)}

    def analyze(self, data: np.ndarray, gains: Optional[np.ndarray] = None,
                times: Optional[np.ndarray] = None, do_fit: bool = True) -> Dict:
        """
        Analyze a 2D chevron pattern with optional full fitting.

        Parameters:
        -----------
        data : 2D array (gains x times)
        gains : array of gain/detuning values (y-axis), optional
        times : array of time values (x-axis), optional
        do_fit : whether to perform full chevron fit
        """
        try:
            # Basic pattern detection (always done)
            data_norm = (data - np.min(data)) / (np.max(data) - np.min(data) + 1e-10)
            contrasts = np.std(data_norm, axis=1)

            contrast_threshold = np.percentile(contrasts, 60)
            high_contrast_rows = np.where(contrasts > contrast_threshold)[0]

            if len(high_contrast_rows) < 2:
                return {"success": False, "message": "No chevron pattern detected"}

            # Find edges
            left_edge = []
            right_edge = []
            valid_rows = []

            for row_idx in high_contrast_rows:
                row = data_norm[row_idx, :]
                peaks, properties = find_peaks(row, prominence=0.2)

                if len(peaks) >= 2:
                    left_edge.append(peaks[0])
                    right_edge.append(peaks[-1])
                    valid_rows.append(row_idx)

            if len(valid_rows) < 2:
                return {"success": False, "message": "Could not detect chevron edges"}

            left_edge = np.array(left_edge)
            right_edge = np.array(right_edge)
            valid_rows = np.array(valid_rows)

            # Basic edge fitting
            left_fit = np.polyfit(valid_rows, left_edge, 1)
            right_fit = np.polyfit(valid_rows, right_edge, 1)

            width = right_edge - left_edge
            min_width_idx = np.argmin(width)
            sweet_spot_row = valid_rows[min_width_idx]
            sweet_spot_col = int((left_edge[min_width_idx] + right_edge[min_width_idx]) / 2)

            result = {
                "success": True,
                "left_slope": left_fit[0],
                "left_intercept": left_fit[1],
                "right_slope": right_fit[0],
                "right_intercept": right_fit[1],
                "sweet_spot": (sweet_spot_row, sweet_spot_col),
                "min_width": np.min(width),
                "max_contrast": np.max(contrasts),
                "edge_data": {
                    "rows": valid_rows.tolist(),
                    "left": left_edge.tolist(),
                    "right": right_edge.tolist()
                }
            }

            # Full fit if requested and axes provided
            if do_fit and gains is not None and times is not None:
                qInfo("Performing full chevron fit...")
                fit_result = self.fit_chevron(gains, times, data, return_fit_points=True)

                if fit_result["success"]:
                    result.update({
                        "fit_performed": True,
                        "coupling_g": fit_result["g"],
                        "coupling_g_stderr": fit_result["g_stderr"],
                        "center_detuning": fit_result["d0"],
                        "center_detuning_stderr": fit_result["d0_stderr"],
                        "asymmetry_b": fit_result["b"],
                        "asymmetry_b_stderr": fit_result["b_stderr"],
                        "fit_r_squared": fit_result["r_squared"],
                        "fit_equation": fit_result["equation"],
                        "freq_fit_data": {
                            "gains_fit": fit_result["gains_fit"],
                            "freq_fit": fit_result["freq_fit"],
                            "gains_points": fit_result["fit_gains_list"],
                            "freq_points": fit_result["freq_list"]
                        }
                    })
                else:
                    result["fit_performed"] = False
                    result["fit_message"] = fit_result.get("message", "Fit failed")
            else:
                result["fit_performed"] = False

            return result

        except Exception as e:
            qWarning(f"Chevron analysis failed: {str(e)}")
            traceback.print_exc()
            return {"success": False, "message": str(e)}


# ==================== Data Analyzer ====================

class DataAnalyzer:
    """Analyzes data to suggest appropriate fit models."""

    @staticmethod
    def analyze_1d(x: np.ndarray, y: np.ndarray) -> List[str]:
        """Analyze 1D data and suggest models."""
        suggestions = []

        # Basic stats
        y_range = np.max(y) - np.min(y)
        y_mean = np.mean(y)

        if y_range < 1e-10:
            return ["Linear"]

        # Check for periodicity using FFT
        if len(y) > 10:
            yf = fft(y - np.mean(y))
            power = np.abs(yf[:len(y) // 2])

            if len(power) > 2:
                max_power = np.max(power[1:])
                mean_power = np.mean(power[1:])

                if max_power > 4 * mean_power:
                    # Strong periodicity
                    # Check for damping
                    first_quarter = y[:len(y) // 4]
                    last_quarter = y[-len(y) // 4:]

                    amp_ratio = np.std(last_quarter) / (np.std(first_quarter) + 1e-10)

                    if amp_ratio < 0.6:
                        suggestions.append("Rabi Oscillations")
                        suggestions.append("Ramsey Fringes")

                    suggestions.append("Sinusoidal")

        # Check for exponential decay
        if y[0] > y[-1] + 0.1 * y_range:
            try:
                y_shifted = y - np.min(y) + 1e-10
                if np.all(y_shifted > 0):
                    log_y = np.log(y_shifted)
                    if np.all(np.isfinite(log_y)):
                        slope, _ = np.polyfit(x, log_y, 1)
                        if slope < -0.1:
                            suggestions.append("T1 Decay")
            except:
                pass

        # Check for peak
        if len(y) > 5:
            peak_idx = np.argmax(y)
            if 0.15 * len(y) < peak_idx < 0.85 * len(y):
                if y[peak_idx] - y_mean > 0.3 * y_range:
                    suggestions.append("Gaussian")
                    suggestions.append("Lorentzian")

        # Always include polynomial as fallback
        if len(x) > 5:
            suggestions.append("Polynomial (deg 2)")

        # Linear as ultimate fallback
        if not suggestions:
            suggestions.append("Linear")

        return suggestions

    @staticmethod
    def analyze_2d(data: np.ndarray) -> List[str]:
        """Analyze 2D data and suggest methods."""
        suggestions = []

        # Check for diagonal structure (chevron)
        row_contrasts = np.std(data, axis=1)

        if len(row_contrasts) > 10:
            # Look for variation in contrast
            contrast_variation = np.std(row_contrasts) / (np.mean(row_contrasts) + 1e-10)

            if contrast_variation > 0.3:
                suggestions.append("Chevron Pattern")

        # Always include chevron as option for 2D data
        if "Chevron Pattern" not in suggestions:
            suggestions.append("Chevron Pattern")

        return suggestions


# ==================== Fit Manager ====================

class FitManager:
    """Manages all fitting operations."""

    def __init__(self):
        # 1D models
        self.models_1d = {
            "Linear": LinearModel(),
            "Polynomial (deg 2)": PolynomialModel(2),
            "Polynomial (deg 3)": PolynomialModel(3),
            "Sinusoidal": SinusoidalModel(),
            "Rabi Oscillations": RabiModel(),
            "Ramsey Fringes": RamseyModel(),
            "T1 Decay": T1DecayModel(),
            "Gaussian": GaussianModel(),
            "Lorentzian": LorentzianModel(),
        }

        # 2D analyzers
        self.analyzers_2d = {
            "Chevron Pattern": Chevron2DAnalyzer(),
        }

        self.analyzer = DataAnalyzer()

    def get_available_models_1d(self) -> List[str]:
        """Get list of available 1D models."""
        return list(self.models_1d.keys())

    def get_available_models_2d(self) -> List[str]:
        """Get list of available 2D models."""
        return list(self.analyzers_2d.keys())

    def fit_1d(self, x: np.ndarray, y: np.ndarray, model_name: Optional[str] = None) -> FitResult:
        """
        Fit 1D data. If model_name is None, auto-detect best model.
        """
        # Clean data
        mask = np.isfinite(x) & np.isfinite(y)
        x_clean = x[mask]
        y_clean = y[mask]

        if len(x_clean) < 3:
            return FitResult("None", {}, {}, np.array([]), 0, False,
                             "Insufficient data points", "")

        # Auto-detect if needed
        if model_name is None or model_name == "Auto":
            suggestions = self.analyzer.analyze_1d(x_clean, y_clean)
            if suggestions:
                model_name = suggestions[0]
            else:
                model_name = "Linear"

        # Perform fit
        if model_name in self.models_1d:
            qInfo(f"Fitting with {model_name}")
            return self.models_1d[model_name].fit(x_clean, y_clean)
        else:
            return FitResult("None", {}, {}, np.array([]), 0, False,
                             f"Unknown model: {model_name}", "")

    def fit_multiple_1d(self, x: np.ndarray, y: np.ndarray, top_n: int = 3) -> List[FitResult]:
        """
        Try multiple models and return top N by R-squared.
        """
        # Clean data
        mask = np.isfinite(x) & np.isfinite(y)
        x_clean = x[mask]
        y_clean = y[mask]

        if len(x_clean) < 3:
            return []

        # Get suggestions
        suggestions = self.analyzer.analyze_1d(x_clean, y_clean)

        # Try each suggested model
        results = []
        for model_name in suggestions[:top_n + 2]:  # Try a few extra
            if model_name in self.models_1d:
                result = self.models_1d[model_name].fit(x_clean, y_clean)
                if result.success:
                    results.append(result)

        # Sort by R-squared
        results.sort(key=lambda r: r.r_squared, reverse=True)

        return results[:top_n]

    def analyze_2d(self, data: np.ndarray, method_name: Optional[str] = None,
                   x_axis: Optional[np.ndarray] = None, y_axis: Optional[np.ndarray] = None,
                   do_fit: bool = True) -> Dict:
        """
        Analyze 2D data with optional axis information for full fitting.

        Parameters:
        -----------
        data : 2D array
        method_name : analysis method ('Chevron Pattern' or 'Auto')
        x_axis : x-axis values (e.g., times)
        y_axis : y-axis values (e.g., gains/detunings)
        do_fit : whether to perform full fitting (requires axes)
        """
        if data.ndim != 2:
            return {"success": False, "message": "Data must be 2D"}

        # Auto-detect if needed
        if method_name is None or method_name == "Auto":
            suggestions = self.analyzer.analyze_2d(data)
            if suggestions:
                method_name = suggestions[0]
            else:
                return {"success": False, "message": "Could not detect pattern"}

        # Perform analysis
        if method_name in self.analyzers_2d:
            qInfo(f"Analyzing with {method_name}")

            # Pass axis information if available
            if method_name == "Chevron Pattern":
                return self.analyzers_2d[method_name].analyze(
                    data, gains=y_axis, times=x_axis, do_fit=do_fit
                )
            else:
                return self.analyzers_2d[method_name].analyze(data)
        else:
            return {"success": False, "message": f"Unknown method: {method_name}"}
