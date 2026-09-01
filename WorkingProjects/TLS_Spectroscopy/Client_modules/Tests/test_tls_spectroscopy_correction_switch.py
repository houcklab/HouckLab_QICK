import sys
import types

import matplotlib
import numpy as np
import pytest


class _Stub:
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


def _install_hardware_stubs():
    qick = types.ModuleType("qick")
    qick.__path__ = []
    for name in (
        "AveragerProgram",
        "RAveragerProgram",
        "QickProgram",
        "NDAveragerProgram",
        "QickConfig",
        "QickSoc",
        "AbsQickProgram",
    ):
        setattr(qick, name, _Stub)
    sys.modules["qick"] = qick
    for name in ("qick.qick_asm", "qick.averager_program", "qick.helpers", "qick.asm_v1"):
        module = types.ModuleType(name)
        module.__getattr__ = lambda _name: _Stub
        sys.modules[name] = module

    for name in ("Pyro4", "pyro4"):
        module = types.ModuleType(name)
        module.Proxy = _Stub
        module.locateNS = lambda **kwargs: None
        module.config = types.SimpleNamespace(SERIALIZER="pickle", PICKLE_PROTOCOL_VERSION=4)
        module.util = types.SimpleNamespace(SerializerBase=_Stub)
        sys.modules[name] = module

    pyvisa = types.ModuleType("pyvisa")
    pyvisa.ResourceManager = _Stub
    sys.modules["pyvisa"] = pyvisa


matplotlib.use("Agg")
_install_hardware_stubs()

_matplotlib_use = matplotlib.use
matplotlib.use = lambda *args, **kwargs: None
try:
    from WorkingProjects.TLS_Spectroscopy.Client_modules.Runners import TLSSpectroscopy as tls
finally:
    matplotlib.use = _matplotlib_use


def test_step6_can_run_without_flux_tail_compensation(tmp_path, capsys):
    compensation, mode = tls._resolve_step6_correction(
        {"apply_flux_tail_compensation": False}, None, tmp_path
    )

    assert compensation is None
    assert mode == "uncorrected"
    assert "disabled" in capsys.readouterr().out.lower()


def test_step6_still_requires_a_correction_by_default(tmp_path):
    with pytest.raises(ValueError, match="No flux-tail compensation JSON"):
        tls._resolve_step6_correction({}, None, tmp_path)


def test_step6_records_that_compensation_was_disabled():
    cfg = tls._t1_base_cfg(
        {
            "shots": 10,
            "reset_mode": "passive",
            "apply_flux_tail_compensation": False,
        },
        None,
        np.array([10_000.0, 10_500.0]),
    )

    assert cfg["apply_flux_tail_compensation"] is False
    assert cfg["flux_tail_compensation"] is None


@pytest.mark.parametrize("scan_kind", ["3pt", "full"])
def test_step6_runner_honors_disabled_correction(scan_kind, tmp_path, monkeypatch, capsys):
    common = {
        "run": True,
        "apply_flux_tail_compensation": False,
        "shots": 10,
        "dc_min": 10_000,
        "dc_max": 11_000,
        "dc_step": 500,
        "freq_step_mhz": None,
        "wall_clock_duration_min": None,
        "reset_mode": "passive",
    }
    if scan_kind == "3pt":
        config = dict(
            common,
            Ts_us=60.0,
            min_ref_contrast=0.05,
            max_plot_t1_multiple=20.0,
        )
        config_name = "P6_3PT_T1"
        experiment_names = ("T13PointVsFlux",)
        runner = tls.run_step6_3pt_t1
    else:
        config = dict(
            common,
            quality_factor=None,
            t_max_us=None,
            auto_tmax_factor=3.0,
            t_min_us_default=1.0,
            t_points_default=5,
            T1_probe_cfg=None,
        )
        config_name = "P6_FULL_T1"
        experiment_names = ("T1FullCurveVsFlux", "T1FullCurveVsFluxFromFit")
        runner = tls.run_step6_full_t1_vs_flux

    created = {}

    class CapturedExperiment:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def run_once(factory, _wall_clock_s, **_kwargs):
        created["experiment"] = factory({})
        return "uncorrected.csv"

    monkeypatch.setattr(tls, config_name, config)
    for name in experiment_names:
        monkeypatch.setattr(tls, name, CapturedExperiment)
    monkeypatch.setattr(tls, "_run_one_stop_t1", run_once)

    runner(tmp_path, None, None, {"threshold": 0.0}, None)

    kwargs = created["experiment"].kwargs
    assert kwargs["flux_tail_compensation"] is None
    assert kwargs["cfg"]["apply_flux_tail_compensation"] is False
    assert kwargs["suffix"].endswith("_uncorrected")
    assert "(uncorrected)" in capsys.readouterr().out
