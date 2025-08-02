import numpy as np
from uncertainties import ufloat, unumpy
from scipy.stats import norm


def poly8_with_confidence(x, conf=0.95):
    """
    Evaluate the Poly8 model with a variable confidence interval.

    The model is:
        polyfit_8(x) = p1*x^8 + p2*x^7 + p3*x^6 + p4*x^5 +
                       p5*x^4 + p6*x^3 + p7*x^2 + p8*x + p9

    where x is normalized as:
        xn = (x - 4040) / 604.1

    Coefficients (with 95% confidence intervals provided):
        p1 =   0.0003638  (-0.0001372, 0.0008647)
        p2 =   0.0009647  (9.142e-05, 0.001838)
        p3 =   -0.001174  (-0.003055, 0.0007068)
        p4 =   -0.004276  (-0.007128, -0.001425)
        p5 =   0.0001963  (-0.002442, 0.002835)
        p6 =    0.001399  (-0.001434, 0.004231)
        p7 =    0.004389  (0.002911, 0.005866)
        p8 =    -0.02012  (-0.02095, -0.01929)
        p9 =     0.03881  (0.03856, 0.03905)

    We approximate the standard uncertainty for each coefficient as half the width
    of its 95% confidence interval. To get a different confidence interval, the
    returned uncertainty bounds will be scaled accordingly assuming a normal distribution.

    Parameters:
      x    : float or array-like
             The input value(s) at which to evaluate the polynomial.
      conf : float, optional
             The desired confidence level (default is 0.95 for a 95% confidence interval).

    Returns:
      nominal : float or numpy array
                The nominal (best estimate) value of the polynomial.
      lower   : float or numpy array
                The lower bound of the specified confidence interval.
      upper   : float or numpy array
                The upper bound of the specified confidence interval.
    """
    # Normalize x
    x = np.array(x)  # Ensure numpy array for vectorized operations if needed
    xn = (x - 4040) / 604.1

    # Define coefficients as ufloats (value, uncertainty)
    # Uncertainty is estimated as half the width of the provided 95% confidence interval.
    p1 = ufloat(0.0003638, (0.0008647 - (-0.0001372)) / 2)
    p2 = ufloat(0.0009647, (0.001838 - 9.142e-05) / 2)
    p3 = ufloat(-0.001174, (0.0007068 - (-0.003055)) / 2)
    p4 = ufloat(-0.004276, (-0.001425 - (-0.007128)) / 2)
    p5 = ufloat(0.0001963, (0.002835 - (-0.002442)) / 2)
    p6 = ufloat(0.001399, (0.004231 - (-0.001434)) / 2)
    p7 = ufloat(0.004389, (0.005866 - 0.004389) / 2)
    p8 = ufloat(-0.02012, (-0.01929 - (-0.02095)) / 2)
    p9 = ufloat(0.03881, (0.03905 - 0.03881) / 2)

    # Compute the polynomial using uncertainties.
    result = (p1 * xn ** 8 +
              p2 * xn ** 7 +
              p3 * xn ** 6 +
              p4 * xn ** 5 +
              p5 * xn ** 4 +
              p6 * xn ** 3 +
              p7 * xn ** 2 +
              p8 * xn +
              p9)

    # Extract the nominal values and standard deviations.
    nominal = unumpy.nominal_values(result)
    std_dev = unumpy.std_devs(result)

    # Calculate the multiplier for the desired confidence interval.
    # For a two-sided interval:
    multiplier = norm.ppf(1 - (1 - conf) / 2)

    lower = nominal - multiplier * std_dev
    upper = nominal + multiplier * std_dev

    return nominal, lower, upper


# Example usage:
if __name__ == '__main__':
    # Test with a single value at the default 95% confidence level.
    test_x = 4040  # When x is the mean, xn = 0.
    value, conf_lower, conf_upper = poly8_with_confidence(test_x)
    print(f"For x = {test_x} at 95% CI:")
    print(f"  Nominal value: {value}")
    print(f"  95% CI: [{conf_lower}, {conf_upper}]")

    # Test with a single value at a 99% confidence level.
    value99, conf_lower99, conf_upper99 = poly8_with_confidence(test_x, conf=0.66)
    print(f"\nFor x = {test_x} at 66% CI:")
    print(f"  Nominal value: {value99}")
    print(f"  99% CI: [{conf_lower99}, {conf_upper99}]")

    # Test with multiple values.
    x_values = [3500, 4040, 4500]
    values, lowers, uppers = poly8_with_confidence(x_values, conf=0.95)
    print("\nFor multiple x values at 95% CI:")
    for x_val, val, low, up in zip(x_values, values, lowers, uppers):
        print(f"x = {x_val}: value = {val}, 95% CI = [{low}, {up}]")
