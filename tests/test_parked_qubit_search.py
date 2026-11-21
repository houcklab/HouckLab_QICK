import importlib

import numpy as np
import pytest


MODULE = "WorkingProjects.TLS_Spectroscopy.Client_modules.Runners.Test"
FIT = [7005693310.219587, 125664785.8662649, 13.550189128853306,
       0.23483392070686102, 89314.89331157962, -5756.039169389053,
       0.5844195230341026]


def test_new_qubit_search_uses_one_fit_derived_park_and_readout():
    module = importlib.import_module(MODULE)
    base = {"ff_park_gain": 0, "read_pulse_freq": 6933.026,
            "read_length": 15, "read_pulse_gain": 5000}
    cfg, frequencies = module.parked_qubit_search_config(base, FIT)
    assert base["ff_park_gain"] == 0
    assert cfg["ff_park_gain"] == cfg["ff_gain"] == cfg["ff_hold_gain"] == -5756
    assert cfg["read_pulse_freq"] == pytest.approx(7012.8639, abs=.001)
    assert cfg["reset_mode"] == "passive"
    assert cfg["opx_persistent_park"] is True
    assert cfg["opx_hard_flux_steps"] is True
    assert cfg["qua_passive_pre_point_delay_us"] == 300
    assert frequencies[[0, -1]].tolist() == [3500, 5500]
    assert len(frequencies) == 2001
    assert np.allclose(np.diff(frequencies), 1)


def test_explicit_park_override_recalculates_readout():
    module = importlib.import_module(MODULE)
    cfg, frequencies = module.parked_qubit_search_config(
        {}, FIT, park_gain=24550, freq_min_mhz=4000, freq_max_mhz=4100,
        freq_step_mhz=.5, shots=40,
    )
    assert cfg["ff_park_gain"] == 24550
    assert cfg["read_pulse_freq"] == pytest.approx(7010.9353, abs=.001)
    assert cfg["shots"] == cfg["reps"] == 40
    assert len(frequencies) == 201


@pytest.mark.parametrize("options", [
    {"park_gain": 50000}, {"freq_step_mhz": 0},
    {"freq_min_mhz": 5500, "freq_max_mhz": 3500},
    {"freq_step_mhz": 3}, {"shots": 0}, {"spec_gain": 40000},
])
def test_invalid_search_settings_fail_before_hardware(options):
    module = importlib.import_module(MODULE)
    with pytest.raises(ValueError):
        module.parked_qubit_search_config({}, FIT, **options)


def test_search_saves_all_blocks_in_canonical_on_off_order(tmp_path, monkeypatch):
    import sys
    import types
    import matplotlib
    matplotlib.use("Agg", force=True)
    module = importlib.import_module(MODULE)
    prefix = "WorkingProjects.TLS_Spectroscopy.Client_modules"
    soc = types.SimpleNamespace(streamer=types.SimpleNamespace(readout_running=lambda: False))
    tls = types.ModuleType(prefix + ".Runners.TLSSpectroscopy")
    tls.BaseConfig = {"read_length": 15, "read_pulse_gain": 5000}
    tls.RESONATOR_FIT_PARAMS = FIT
    tls.makeProxy = lambda: (soc, {})
    tls.QUBIT, tls.outerFolder, tls.LIVE_PLOTS = "TL", str(tmp_path), False
    monkeypatch.setitem(sys.modules, tls.__name__, tls)
    monkeypatch.setattr(importlib.import_module(prefix + ".Runners"),
                        "TLSSpectroscopy", tls, raising=False)

    class Experiment:
        def __init__(self, **kwargs):
            self.cfg = kwargs["cfg"]
            self.dname = str(tmp_path / kwargs["suffix"])
            self.pname, self.iname = self.dname + ".pkl", self.dname + ".png"

        def save_config(self):
            pass

        def pickle_data(self):
            pass

    class Transmission(Experiment):
        def acquire(self, **kwargs):
            assert self.cfg["ff_park_gain"] == -5756
            return {"data": {"resonator_dip_freq_mhz": 7012.86}}

    acquisition_calls = []

    def acquire(soc, soccfg, cfg, **kwargs):
        assert cfg["read_pulse_freq"] == 7012.86
        assert cfg["ff_park_gain"] == -5756
        gains = kwargs["gains"]
        acquisition_calls.append((cfg["shots"], gains))
        shape = (len(kwargs["frequencies_mhz"]), 2, cfg["shots"])
        i = np.broadcast_to(np.array(gains)[None, :, None], shape).astype(float)
        kwargs["progress"](cfg["shots"], cfg["shots"])
        return i, np.zeros_like(i), {"order": "shot_frequency_gain"}

    for name, attrs in {
        ".Experiments.mTransmission": {"Transmission": Transmission},
        ".CoreLib.Experiment": {"ExperimentClass": Experiment},
        ".active_reset_OPX.qua_order": {"acquire_passive_pulse_grid": acquire},
    }.items():
        stub = types.ModuleType(prefix + name)
        stub.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, prefix + name, stub)
    result = module.run_parked_qubit_search([
        "--qubit-search", "--freq-min-mhz", "4500", "--freq-max-mhz", "4502",
        "--shots", "41",
    ])
    assert acquisition_calls == [(20, [0, 25000]), (20, [25000, 0]), (1, [0, 25000])]
    raw = np.load(result.dname + "_raw_iq.npz")
    assert raw["I"].shape == (3, 2, 41)
    assert np.all(raw["I"][:, 0] == 0)
    assert np.all(raw["I"][:, 1] == 25000)
    assert result.data["completed_shots_per_condition"] == 41
    assert tls.BaseConfig == {"read_length": 15, "read_pulse_gain": 5000}
