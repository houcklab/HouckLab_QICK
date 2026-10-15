"""Hardware-free test for the resonator linewidth saved by CavitySpecFF.display (F25).

A synthetic hanger dip with known Qtot/Qext goes through display(); the saved
``hanger_fit_kappa_tot_mhz`` / ``hanger_fit_kappa_ext_mhz`` must be kappa/2pi in MHz
(|f0|/Qtot and |f0|/Qext on the fit axis), both for an absolute-MHz axis (cavity_LO = 0) and
for an IF axis with a nonzero cavity_LO, positive or negative IF (where the fitted Qs are
relative to the IF f0 but |f0|/Q is still the width in MHz). See docs/experiments/transmission_fit.md.

    python -m pytest tests/test_transmission_kappa.py
"""

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pytest

from qicklab.analysis.fitting import hanger_model_db
from qicklab.experiments.transmission import CavitySpecFF

KAPPA_TOT = 0.420  # MHz, kappa_tot/2pi
KAPPA_EXT = 0.353  # MHz, kappa_ext/2pi


@pytest.mark.parametrize(
    "f0_axis, cavity_lo_hz",
    [(7095.0, 0.0), (95.0, 7.0e9), (-95.0, 7.0e9)],
    ids=["absolute_axis", "if_axis_with_lo", "negative_if_axis_with_lo"],
)
def test_saved_kappas_are_linewidths_in_mhz(tmp_path, f0_axis, cavity_lo_hz):
    # Qs are positive and relative to |f0|; a negative IF f0 (resonator below the LO) must
    # still give positive linewidths, which pins the abs() in display().
    qtot, qext = abs(f0_axis) / KAPPA_TOT, abs(f0_axis) / KAPPA_EXT
    fpts = np.linspace(f0_axis - 3.0, f0_axis + 3.0, 301)
    rng = np.random.default_rng(0)
    amp = 10 ** (hanger_model_db(fpts, f0_axis, qtot, qext, 0.0, -20.0) / 20)
    amp = amp * (1 + 2e-3 * rng.standard_normal(fpts.size))

    inst = object.__new__(CavitySpecFF)
    inst.cfg = {"cavity_LO": cavity_lo_hz, "pulse_freq": f0_axis}
    inst.iname = str(tmp_path / "trans.png")
    results = np.zeros((1, 1, 2, fpts.size))
    results[0, 0, 0] = amp  # I = |S21|, Q = 0
    data = {"config": inst.cfg, "data": {"results": results, "fpts": fpts}}

    inst.display(data=data, plotDisp=False, fit=True)

    d = data["data"]
    assert "hanger_fit_kappa_mhz" not in d
    assert float(d["hanger_fit_kappa_tot_mhz"]) == pytest.approx(KAPPA_TOT, rel=0.05)
    assert float(d["hanger_fit_kappa_ext_mhz"]) == pytest.approx(KAPPA_EXT, rel=0.05)
