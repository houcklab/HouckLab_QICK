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


def test_modulated_strobe_acquire(soc, soccfg):
    loopback_cfg = _base_cfg()
    loopback_cfg.update({"mode": "strobe", "sample_period_us": 5.0, "reps_per_chunk": 1000})
    tmp_dir = "./_loopback_tmp/"
    # --- Loopback: modulated_strobe_acquire ---
    from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.utils import modulated_strobe_acquire
    zsp_mod = ZeroSpanParity(soc=soc, soccfg=soccfg, cfg=dict(loopback_cfg), outerFolder=tmp_dir, prefix="loopback_mod")
    schedule = [loopback_cfg["qubit_gain"], 0] * 2   # 2 periods
    acq = modulated_strobe_acquire(zsp_mod, schedule, reps_per_block=1000)
    assert acq["I"].shape == (4000,), acq["I"].shape
    assert acq["gap_indices"] == [1000, 2000, 3000], acq["gap_indices"]
    assert np.array_equal((acq["modulation_reference"] > 0.5),
                          np.tile(np.concatenate([np.ones(1000), np.zeros(1000)]), 2).astype(bool)), "ref misaligned"
    assert acq["block_labels"] == schedule, acq["block_labels"]
    print("loopback modulated_strobe_acquire: OK")


def test_run_static_contrast(soc, soccfg):
    loopback_cfg = _base_cfg()
    loopback_cfg.update({"mode": "strobe", "sample_period_us": 5.0, "reps_per_chunk": 1000})
    tmp_dir = "./_loopback_tmp/"
    # --- Loopback: run_static_contrast plumbing ---
    from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.validate_ZeroSpanParity import run_static_contrast
    zsp_sc = ZeroSpanParity(soc=soc, soccfg=soccfg, cfg=dict(loopback_cfg), outerFolder=tmp_dir, prefix="loopback_sc")
    f0 = loopback_cfg["read_pulse_freq"]
    flist = np.linspace(f0 - 0.5, f0 + 0.5, 5)
    sc = run_static_contrast(zsp_sc, flist, qubit_gain_on=loopback_cfg["qubit_gain"], out_dir=tmp_dir)
    assert sc["contrast"].shape == (5,), sc["contrast"].shape
    assert np.all(np.isfinite(sc["Z_on"])) and np.all(np.isfinite(sc["Z_off"]))
    print("loopback run_static_contrast: OK")


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
    test_modulated_strobe_acquire(soc, soccfg)
    test_run_static_contrast(soc, soccfg)
    test_decimated_shape(soc, soccfg)
    print("All loopback checks passed.")
