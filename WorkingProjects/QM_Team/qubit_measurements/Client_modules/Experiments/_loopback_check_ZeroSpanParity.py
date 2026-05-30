"""
Loopback smoke test for ZeroSpanParity (spec §6.2).

Requires RFSoC Pyro4 server reachable and a DAC->ADC loopback cable installed.
Run from repo root:
  python -m WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments._loopback_check_ZeroSpanParity

This is a throwaway diagnostic — keep it under version control for repeatability
but do not import from it elsewhere.
"""

import os

import numpy as np

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.socProxy import makeProxy
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mZeroSpanParity import ZeroSpanParity
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import chunked_acquire
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.analyze_ZeroSpanParity import analyze_parity_run


def _base_cfg():
    return {
        "res_ch": 0, "qubit_ch": 1, "ro_chs": [0],
        "nqz": 2, "qubit_nqz": 2, "mixer_freq": 0.0,
        "read_pulse_freq": 1000.0,         # any safe in-range freq for loopback
        "parity_drive_freq": 1000.0,       # same — placeholder
        "qubit_gain": 100, "pulse_gain": 100,
        "res_phase": 0,
        "adc_trig_offset": 0.488,
        "read_length": 1.0,
        "start_src": "internal",
    }


def test_strobe_shape(soc, soccfg):
    cfg = _base_cfg()
    cfg.update({"mode": "strobe", "sample_period_us": 5.0, "reps_per_chunk": 1000})
    exp = ZeroSpanParity(soc=soc, soccfg=soccfg, path="Loopback_Strobe",
                         outerFolder="./_loopback_tmp/", cfg=cfg)
    data = exp.acquire(progress=False)
    assert data["I"].shape == (1000,), f"strobe I shape: {data['I'].shape}"
    assert data["Q"].shape == (1000,), f"strobe Q shape: {data['Q'].shape}"
    assert data["t_us"].shape == (1000,)
    dt = np.diff(data["t_us"])
    assert np.all(dt > 0), "t_us not monotonic"
    assert abs(float(np.mean(dt)) - 5.0) < 0.1, f"t step off: {np.mean(dt)}"
    print("loopback strobe shape: OK")


def test_chunked_stitch(soc, soccfg):
    cfg = _base_cfg()
    cfg.update({"mode": "strobe", "sample_period_us": 5.0, "reps_per_chunk": 1000})
    exp = ZeroSpanParity(soc=soc, soccfg=soccfg, path="Loopback_Chunked",
                         outerFolder="./_loopback_tmp/", cfg=cfg)
    stitched = chunked_acquire(exp, n_chunks=5)
    assert stitched["I"].shape == (5000,), stitched["I"].shape
    assert list(stitched["gap_indices"]) == [1000, 2000, 3000, 4000]
    assert np.all(np.diff(stitched["t_us"]) > 0), "stitched t_us not monotonic"
    print("loopback chunked stitch: OK")


def test_decimated_shape(soc, soccfg):
    cfg = _base_cfg()
    cfg.update({"mode": "decimated", "capture_length_us": 2.0,
                "soft_avgs": 1, "read_length": 2.0})
    exp = ZeroSpanParity(soc=soc, soccfg=soccfg, path="Loopback_Decimated",
                         outerFolder="./_loopback_tmp/", cfg=cfg)
    data = exp.acquire(progress=False)
    # Note: soccfg["readouts"][ro]["f_output"] (307.2 MHz on this firmware) is
    # NOT the actual rate of the samples returned by acquire_decimated. The
    # firmware-internal decimation produces samples at a higher rate. Rather
    # than encode a brittle exact-count check, verify the basic invariants:
    # (a) non-empty I/Q, (b) equal lengths, (c) finite values, (d) monotonic
    # time axis.
    assert data["I"].size > 0, "decimated returned empty I"
    assert data["I"].size == data["Q"].size, (
        f"I/Q length mismatch: I={data['I'].size}, Q={data['Q'].size}"
    )
    assert data["t_us"].size == data["I"].size, (
        f"t_us length {data['t_us'].size} != I length {data['I'].size}"
    )
    assert np.all(np.isfinite(data["I"])) and np.all(np.isfinite(data["Q"])), (
        "decimated I or Q contains non-finite values"
    )
    assert np.all(np.diff(data["t_us"]) > 0), "decimated t_us not monotonic"
    decimated_fs_reported = float(soccfg["readouts"][cfg["ro_chs"][0]]["f_output"])
    print(f"loopback decimated shape ({data['I'].size} samples, "
          f"reported f_output={decimated_fs_reported} MHz): OK")


def test_save_analyze_roundtrip(soc, soccfg):
    """Exercise the real producer->HDF5->consumer contract (spec §6.2/§3.5).

    Acquire, persist via ZeroSpanParity.save_data, then run analyze_parity_run
    on the produced .h5. This is the only test that binds the saved dataset
    names/dtypes/attrs to what the analysis module reads back; a schema drift
    (renamed dataset, gap_indices dtype, missing attr) fails here rather than
    silently on the next real measurement.
    """
    cfg = _base_cfg()
    cfg.update({"mode": "strobe", "sample_period_us": 5.0, "reps_per_chunk": 1000})
    exp = ZeroSpanParity(soc=soc, soccfg=soccfg, path="Loopback_RoundTrip",
                         outerFolder="./_loopback_tmp/", cfg=cfg)
    exp.acquire(progress=False)
    exp.save_data()
    exp.save_config()
    assert os.path.exists(exp.fname), f"save_data wrote no file at {exp.fname}"

    # kmeans needs no prior calibration — loopback IQ has no real parity
    # structure, so this only asserts the pipeline runs end-to-end and writes
    # its sidecars from a genuine save_data .h5.
    summary = analyze_parity_run(
        h5_path=exp.fname, separator=None, classifier_method="kmeans",
        window_us=1000.0, save_plots=False,
        out_dir=os.path.dirname(exp.fname),
    )
    for key in ("n_bursts", "baseline_rate_Hz", "mean_dwell_0_us", "mode"):
        assert key in summary, f"analysis summary missing {key}"
    base = os.path.splitext(os.path.basename(exp.fname))[0]
    sidecar = os.path.join(os.path.dirname(exp.fname), base + "_analysis.json")
    assert os.path.exists(sidecar), f"no analysis sidecar at {sidecar}"
    print("loopback save_data -> analyze_parity_run round-trip: OK")


def test_validation_rules_fire(soc, soccfg):
    from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mZeroSpanParity import _validate_cfg
    bad = _base_cfg()
    bad.update({"mode": "strobe", "sample_period_us": 0.1, "reps_per_chunk": 10})
    try:
        _validate_cfg(bad, soccfg)
    except RuntimeError as ex:
        assert "rule 1" in str(ex), ex
        print("loopback validation rule 1 fires: OK")
    else:
        raise AssertionError("expected rule 1 to fire on loopback soccfg")


if __name__ == "__main__":
    os.makedirs("./_loopback_tmp/", exist_ok=True)
    soc, soccfg = makeProxy()
    test_validation_rules_fire(soc, soccfg)
    test_strobe_shape(soc, soccfg)
    test_chunked_stitch(soc, soccfg)
    test_decimated_shape(soc, soccfg)
    test_save_analyze_roundtrip(soc, soccfg)
    print("All loopback checks passed.")
