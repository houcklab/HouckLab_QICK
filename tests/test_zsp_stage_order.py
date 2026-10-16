"""Zero-span parity run order and feedback (F44).

With the validation flags on, run_zero_span_parity must run stages 1-3 BEFORE the main
record, on their own ZeroSpanParity instance, and feed them forward: the main record's
read_pulse_freq is the stage-1 best_freq (only when the contrast SNR AT best_freq beats the
look-elsewhere threshold, and, for a separator classifier, only with the g -> e axis
re-derived at that probe), its parity_drive_freq the parked branch of the stage-2 contrast
doublet (by line order when the pair matches the cached splitting, else the line nearest the
parked frequency, with a FLAG), refined below the grid step by a Lorentzian fit (only within half the doublet
splitting, at contrast SNR >= min_peak_snr, and when the shift exceeds 2 fit standard
errors), stage 2 runs at the stage-1 probe, the stage-1 reps_per_point does not leak into stages 2-3 or the main
record, and stage 3 flags (or, with a recipe threshold, raises before the main record) when
the block-means t of the modulation is not significant. Stages 8/7 run on the main instance
after the record; control D drives the cached lines shifted by the stage-2 refinement.
kmeans (no separator) with stages 3/8/7 fails before any acquisition. The stage functions and the experiment are faked: only the orchestration is under test.
"""

import numpy as np
import pytest

import qicklab.runs.zero_span as zs

F_RES = 7000.0
F_Q = 3000.0
REPS = 10_000
REPS_PER_POINT = 2000
N_Q = 161  # stage-2 grid: 10 MHz / 160 = 62.5 kHz step, >= 6 points within the 0.3 MHz capture
HWHM = 0.1  # stage-2 contrast line half-width (MHz)
SEP0 = {
    "g_center": [0.0, 0.0],
    "e_center": [1.0, 0.0],
    "normal": [1.0, 0.0],
    "midpoint": [0.5, 0.0],
}
SEP1 = {
    "g_center": [0.0, 0.0],
    "e_center": [0.0, 1.0],
    "normal": [0.0, 1.0],
    "midpoint": [0.0, 0.5],
}


class _Ctx:
    soc = soccfg = None
    qubit_frequency_center = F_Q
    resonator_frequency_center = F_RES
    start_voltage = 0.0
    qubit_gain = 100
    cavity_gain = 100

    def __init__(self, tmp_path):
        self.outerFolder = str(tmp_path) + "/"

    def working_config(self):
        return {
            "res_ch": 0,
            "qubit_ch": 1,
            "ro_chs": [0],
            "nqz": 2,
            "qubit_nqz": 1,
            "mixer_freq": 0.0,
        }


def _params(**over):
    p = {
        "ZSP_RecalibrateParityFreqs": False,
        "ZSP_ParitySpec_params": {"min_sep_MHz": 0.2},
        "ZSP_ParityFreqs_Cached": {
            "which_to_park": "lower",
            "lower_peak_MHz": F_Q - 0.3,
            "higher_peak_MHz": F_Q + 0.3,
        },
        "ZSP_RecalibrateSeparator": True,
        "ZSP_Separator_Cached": {k: list(v) for k, v in SEP0.items()},
        "ZSP_AnalysisParams": {
            "classifier_method": "apriori_gmm",
            "window_us": 1000.0,
            "k_sigma": 5.0,
            "step_us": None,
            "min_burst_duration_us": None,
            "analysis_bin_us": None,
            "save_plots": False,
        },
        "ZSP_RunMode": "strobe",
        "ZSP_StrobeParams": {"sample_period_us": 20.0, "reps_per_chunk": REPS, "n_chunks": 3},
        "ZSP_DriveParams": {"qubit_gain": 100, "pulse_gain": 100, "res_phase": 0},
        "ZSP_StartSrc": "internal",
        "Validate_StaticContrast": True,
        "StaticContrast_params": {"freq_span_mhz": 2.0, "n_points": 41, "reps_per_point": 2000},
        "Validate_ContrastVsQubitFreq": True,
        "ContrastVsQubit_params": {"qfreq_span_mhz": 10.0, "n_points": N_Q},
        "Validate_ModulationCheck": True,
        "Modulation_params": {"modulation_freq_hz": 25, "n_periods": 10},
        "Validate_ControlSuite": True,
        "Control_params": {"variants": ["A"], "detune_mhz": 50.0},
        "Validate_EnvironmentSweep": True,
        "Environment_params": {"param_name": "power_dB", "values": [1, 2]},
        "Build_EvidenceReport": True,
    }
    p.update(over)
    return p


def _modulated(depth, n_periods=10, block=200, noise=1.0, seed=0):
    """Synthetic stage-3 record: on/off blocks, on-level shifted by depth, white noise."""
    rng = np.random.default_rng(seed)
    ref = np.concatenate([np.full(block, 1.0 - (b % 2)) for b in range(2 * n_periods)])
    scores = depth * ref + noise * rng.standard_normal(ref.size)
    gaps = list(range(block, ref.size, block))
    return scores, ref, gaps


def _stage2(qlist, peaks, snr_pp=20.0, noise=0.0, seed=0):
    """Synthetic stage-2 result: Lorentzian contrast lines at the true centres `peaks`; the
    peak finder's peak_freqs are grid points (as find_two_tone_peaks returns them)."""
    qlist = np.asarray(qlist, dtype=float)
    contrast = sum(HWHM**2 / ((qlist - f) ** 2 + HWHM**2) for f in peaks)
    contrast = contrast + noise * np.random.default_rng(seed).standard_normal(qlist.size)
    inds = [int(np.argmin(np.abs(qlist - f))) for f in peaks]
    return {
        "qfreqs": qlist,
        "contrast": contrast,
        "peaks": {"peak_freqs": qlist[inds], "peak_inds": inds, "peak_sep": 0.55},
        "contrast_snr_per_point": np.full(qlist.size, float(snr_pp)),
    }


def _install(
    monkeypatch,
    tmp_path,
    best_freq=F_RES + 0.25,
    best_snr=9.0,
    peaks=None,
    snr_pp=20.0,
    corr=0.2,
    mod_snr=0.3,
    mod_depth=0.3,
    noise=0.0,
):
    """Fake the experiment and every stage; return the event log."""
    log = []
    peaks = [F_Q - 0.3 + 0.05, F_Q + 0.3] if peaks is None else peaks

    class FakeZsp:
        n = 0

        def __init__(self, soc=None, soccfg=None, path="", outerFolder="", cfg=None):
            FakeZsp.n += 1
            self.id = FakeZsp.n
            self.cfg = cfg
            self.cfg["reps"] = int(cfg["reps_per_chunk"])
            self.fname = str(tmp_path / "ZeroSpanParity" / "day" / f"run{self.id}.h5")
            log.append(("new", self.id, dict(cfg)))

        def acquire(self, progress=False):
            log.append(("acquire", self.id, dict(self.cfg)))

        def save_data(self):
            log.append(("save_data", self.id, dict(self.cfg)))

        def save_config(self):
            pass

    def chunked(exp, n_chunks, progress=False):
        log.append(("chunked_acquire", exp.id, dict(exp.cfg)))

    def s1(exp, flist, qubit_gain_on, out_dir=None):
        log.append(("stage1", exp.id, dict(exp.cfg)))
        # the max over the sweep is always significant: only the SNR AT best_freq may gate
        return {
            "best_freq": best_freq,
            "contrast_snr": best_snr,
            "contrast_snr_max": 9.0,
            "contrast_snr_threshold": 4.4,
            "contrast_significant": True,
        }

    def s2(exp, qlist_, out_dir=None):
        log.append(("stage2", exp.id, dict(exp.cfg)))
        return _stage2(qlist_, peaks, snr_pp=snr_pp, noise=noise)

    def s3(exp, separator, modulation_freq_hz, n_periods, out_dir=None):
        # the real stage 3 projects on the separator (classify_parity_trace raises on None)
        assert separator is not None
        log.append(("stage3", exp.id, dict(exp.cfg), dict(separator)))
        scores, ref, gaps = _modulated(mod_depth, n_periods=n_periods)
        return {
            "correlation": corr,
            "modulation_depth": mod_depth,
            "snr": mod_snr,
            "classification": {"scores": scores},
            "acq": {"modulation_reference": ref, "gap_indices": gaps},
        }

    def s8(exp, **kw):
        log.append(("stage8", exp.id, dict(exp.cfg), dict(kw["parity_freqs"])))
        return {"variants": {}}

    def s7(exp, **kw):
        log.append(("stage7", exp.id, dict(exp.cfg)))
        return {"table": {}}

    def sep(ctx, pulse_freq=None):
        log.append(("separator", None, {"pulse_freq": pulse_freq}))
        # the run's own calibration (nominal probe) gives SEP0, one at a moved probe SEP1
        src = SEP0 if pulse_freq is None else SEP1
        return {k: np.asarray(v, dtype=float) for k, v in src.items()}

    monkeypatch.setattr(zs, "ZeroSpanParity", FakeZsp)
    monkeypatch.setattr(zs, "chunked_acquire", chunked)
    monkeypatch.setattr(zs, "analyze_parity_run", lambda **kw: log.append(("analyze", None, kw)))
    monkeypatch.setattr(zs, "run_static_contrast", s1)
    monkeypatch.setattr(zs, "run_contrast_vs_qubit_freq", s2)
    monkeypatch.setattr(zs, "run_modulation_check", s3)
    monkeypatch.setattr(zs, "run_control_suite", s8)
    monkeypatch.setattr(zs, "run_environment_sweep", s7)
    monkeypatch.setattr(zs, "build_evidence_report", lambda d, o: log.append(("stage9", None, {})))
    monkeypatch.setattr(zs, "get_apriori_separator_from_singleshot", sep)
    return log


def _main(log):
    return next(e for e in log if e[0] == "chunked_acquire")


def test_stages_1_to_3_run_first_and_feed_the_main_record(monkeypatch, tmp_path):
    log = _install(monkeypatch, tmp_path)
    zs.run_zero_span_parity(_Ctx(tmp_path), _params())
    order = [e[0] for e in log if e[0] != "new"]
    assert order == [
        "separator",  # the run's own calibration at the nominal probe
        "stage1",
        "separator",  # re-derived at the stage-1 probe, before stages 2-3
        "stage2",
        "stage3",
        "chunked_acquire",
        "save_data",
        "analyze",
        "stage8",
        "stage7",
        "stage9",
    ]
    ev = {e[0]: e for e in log if e[0] != "new"}
    pre, main = ev["stage1"][1], ev["chunked_acquire"][1]
    assert pre != main  # the main record is a fresh instance
    assert ev["stage2"][1] == ev["stage3"][1] == pre
    assert ev["stage8"][1] == ev["stage7"][1] == main
    # stage 1 at reps_per_point; stages 2-3 and the main record back at the run's reps
    assert ev["stage1"][2]["reps_per_chunk"] == REPS_PER_POINT
    for k in ("stage2", "stage3", "chunked_acquire", "stage8"):
        assert ev[k][2]["reps_per_chunk"] == REPS and ev[k][2]["reps"] == REPS, k
    # stage 2 at the stage-1 probe; stage 3 and the main record also at the refined line
    assert ev["stage2"][2]["read_pulse_freq"] == pytest.approx(F_RES + 0.25)
    assert ev["stage2"][2]["parity_drive_freq"] == pytest.approx(F_Q - 0.3)
    # the true line is at F_Q - 0.25, between grid points (F_Q - 0.3, F_Q - 0.2375): the
    # Lorentzian centre recovers it below the grid step (the partner's tail biases the
    # single-line fit by ~3 kHz here)
    for k in ("stage3", "chunked_acquire"):
        assert ev[k][2]["read_pulse_freq"] == pytest.approx(F_RES + 0.25), k
        assert ev[k][2]["parity_drive_freq"] == pytest.approx(F_Q - 0.25, abs=5e-3), k
    cfg = ev["chunked_acquire"][2]
    assert cfg["read_pulse_freq_source"] == "stage1_static_contrast"
    assert cfg["read_pulse_freq_nominal"] == F_RES
    assert cfg["separator_probe_freq"] == pytest.approx(F_RES + 0.25)
    assert cfg["parity_drive_freq_refined"] is True
    assert cfg["parity_drive_freq_stage2_fit_center"] == cfg["parity_drive_freq"]
    assert 0 < cfg["parity_drive_freq_stage2_fit_se"] < 0.01  # << the 62.5 kHz step
    assert cfg["parity_drive_freq_unrefined"] == pytest.approx(F_Q - 0.3)
    assert cfg["parity_drive_freq_stage2_snr"] == pytest.approx(20.0)
    # per-sample snr 0.3 / corr 0.2 are low, but 200-sample blocks make the shift significant
    assert cfg["modulation_block_t"] > zs.MODULATION_MIN_BLOCK_T
    assert cfg["modulation_gate_passed"] is True
    assert cfg["modulation_correlation"] == pytest.approx(0.2)
    # control D drives the cached lines shifted by the stage-2 refinement (+0.05 MHz)
    assert ev["stage8"][3]["lower"] == pytest.approx(F_Q - 0.25, abs=5e-3)
    assert ev["stage8"][3]["higher"] == pytest.approx(F_Q + 0.35, abs=5e-3)


def test_unrefined_line_leaves_control_d_on_the_cached_lines(monkeypatch, tmp_path):
    log = _install(monkeypatch, tmp_path, peaks=[F_Q - 0.8, F_Q + 0.3])
    zs.run_zero_span_parity(_Ctx(tmp_path), _params())
    pf = next(e for e in log if e[0] == "stage8")[3]
    assert pf == {"lower": F_Q - 0.3, "higher": F_Q + 0.3}


def test_insignificant_best_point_or_distant_peak_is_not_adopted(monkeypatch, tmp_path):
    # the sweep max is significant but the SNR at best_freq is not; the nearest stage-2 line
    # is 0.5 MHz away (> half the 0.6 MHz doublet splitting)
    log = _install(monkeypatch, tmp_path, best_snr=3.0, peaks=[F_Q - 0.8, F_Q + 0.3])
    zs.run_zero_span_parity(_Ctx(tmp_path), _params())
    cfg = _main(log)[2]
    assert cfg["read_pulse_freq"] == F_RES
    assert cfg["read_pulse_freq_source"] == "resonator_center"
    assert cfg["parity_drive_freq"] == pytest.approx(F_Q - 0.3)
    assert cfg["parity_drive_freq_refined"] is False


def test_low_snr_stage2_peak_is_not_adopted(monkeypatch, tmp_path):
    log = _install(monkeypatch, tmp_path, snr_pp=3.0)
    zs.run_zero_span_parity(_Ctx(tmp_path), _params())
    cfg = _main(log)[2]
    assert cfg["parity_drive_freq"] == pytest.approx(F_Q - 0.3)
    assert cfg["parity_drive_freq_refined"] is False
    assert cfg["parity_drive_freq_stage2_snr"] == pytest.approx(3.0)


def test_stage2_capture_is_half_the_doublet_splitting(monkeypatch, tmp_path):
    # a 0.25 MHz Stark shift (beyond min_sep_MHz = 0.2, inside 0.6 / 2) is adopted
    log = _install(monkeypatch, tmp_path, peaks=[F_Q - 0.05, F_Q + 0.55])
    zs.run_zero_span_parity(_Ctx(tmp_path), _params())
    assert _main(log)[2]["parity_drive_freq"] == pytest.approx(F_Q - 0.05, abs=5e-3)
    # with the partner unknown the capture falls back to min_sep_MHz: not adopted
    log = _install(monkeypatch, tmp_path, peaks=[F_Q - 0.05, F_Q + 0.55])
    pf = {"which_to_park": "lower", "lower_peak_MHz": F_Q - 0.3, "higher_peak_MHz": None}
    zs.run_zero_span_parity(_Ctx(tmp_path), _params(ZSP_ParityFreqs_Cached=pf))
    cfg = _main(log)[2]
    assert cfg["parity_drive_freq"] == F_Q - 0.3 and cfg["parity_drive_freq_refined"] is False


def test_coarse_stage2_grid_is_not_snapped_to_a_grid_point(monkeypatch, tmp_path, capsys):
    # 81 points over 10 MHz: 0.125 MHz step, 5 points within +/- 0.3 MHz, too few to fit
    log = _install(monkeypatch, tmp_path)
    p = _params()
    p["ContrastVsQubit_params"]["n_points"] = 81
    zs.run_zero_span_parity(_Ctx(tmp_path), p)
    cfg = _main(log)[2]
    assert cfg["parity_drive_freq"] == F_Q - 0.3 and cfg["parity_drive_freq_refined"] is False
    assert "fit_failed" in capsys.readouterr().out


def test_shift_within_the_fit_error_is_not_adopted():
    # line exactly at the parked frequency, noisy contrast (5 % of the line height): the
    # fitted centre jitters by a few kHz, not by the 62.5 kHz grid step, and is mostly left
    # in place (|shift| <= 2 se); when adopted the move is far below one bin
    q = np.linspace(F_Q - 5.3, F_Q + 4.7, N_Q)
    out = [
        zs.nearest_contrast_peak(
            _stage2(q, [F_Q - 0.3, F_Q + 0.3], noise=0.05, seed=s), F_Q - 0.3, 0.3
        )
        for s in range(100)
    ]
    reasons = [o[2]["reason"] for o in out]
    assert set(reasons) <= {"adopted", "consistent_with_f0"}
    assert reasons.count("adopted") < 25
    moves = [abs(o[2]["fit_center"] - (F_Q - 0.3)) for o in out]
    assert max(moves) < 0.02


SEP_STAGES = ("Validate_ModulationCheck", "Validate_ControlSuite", "Validate_EnvironmentSweep")


def test_kmeans_with_separator_stages_fails_before_any_acquisition(monkeypatch, tmp_path):
    a = dict(_params()["ZSP_AnalysisParams"], classifier_method="kmeans")
    for flag in SEP_STAGES:
        log = _install(monkeypatch, tmp_path)
        on = {f: f == flag for f in SEP_STAGES}
        with pytest.raises(RuntimeError, match=flag):
            zs.run_zero_span_parity(_Ctx(tmp_path), _params(ZSP_AnalysisParams=a, **on))
        assert log == []
    # stages 1-2 need no separator: kmeans adopts the stage-1 probe without one
    log = _install(monkeypatch, tmp_path)
    off = dict.fromkeys(SEP_STAGES, False)
    zs.run_zero_span_parity(
        _Ctx(tmp_path), _params(ZSP_AnalysisParams=a, ZSP_RecalibrateSeparator=False, **off)
    )
    assert not any(e[0] == "separator" for e in log)
    cfg = _main(log)[2]
    assert cfg["read_pulse_freq"] == pytest.approx(F_RES + 0.25)
    assert "separator_probe_freq" not in cfg


def _sep_params(recalibrate):
    return _params(ZSP_RecalibrateSeparator=recalibrate)


def test_cached_separator_blocks_a_probe_move(monkeypatch, tmp_path, capsys):
    log = _install(monkeypatch, tmp_path)
    zs.run_zero_span_parity(_Ctx(tmp_path), _sep_params(recalibrate=False))
    cfg = _main(log)[2]
    assert cfg["read_pulse_freq"] == F_RES
    assert cfg["read_pulse_freq_source"] == "resonator_center_cached_separator"
    assert not any(e[0] == "separator" for e in log)
    assert "FLAG: best_freq" in capsys.readouterr().out


def test_probe_move_re_derives_the_separator_there(monkeypatch, tmp_path):
    log = _install(monkeypatch, tmp_path)
    p = _sep_params(recalibrate=True)
    zs.run_zero_span_parity(_Ctx(tmp_path), p)
    seps = [e[2]["pulse_freq"] for e in log if e[0] == "separator"]
    assert seps == [None, F_RES + 0.25]  # the run's calibration, then one at the new probe
    names = [e[0] for e in log if e[0] != "new"]
    assert names.index("separator", 1) == names.index("stage1") + 1  # before stages 2-3
    cfg = _main(log)[2]
    assert cfg["read_pulse_freq"] == pytest.approx(F_RES + 0.25)
    assert cfg["separator_probe_freq"] == pytest.approx(F_RES + 0.25)
    # stage 3 and the main analysis project on the re-derived axis
    s3_sep = next(e for e in log if e[0] == "stage3")[3]
    assert np.allclose(s3_sep["normal"], SEP1["normal"])
    an = next(e for e in log if e[0] == "analyze")[2]
    assert np.allclose(an["separator"]["normal"], SEP1["normal"])


def test_best_freq_at_the_nominal_probe_keeps_the_cached_separator(monkeypatch, tmp_path):
    log = _install(monkeypatch, tmp_path, best_freq=F_RES)
    zs.run_zero_span_parity(_Ctx(tmp_path), _sep_params(recalibrate=False))
    cfg = _main(log)[2]
    assert cfg["read_pulse_freq"] == F_RES
    assert cfg["read_pulse_freq_source"] == "stage1_static_contrast"


def test_stage3_failure_flags_by_default_and_raises_with_a_recipe_threshold(
    monkeypatch, tmp_path, capsys
):
    log = _install(monkeypatch, tmp_path, mod_depth=0.0)
    zs.run_zero_span_parity(_Ctx(tmp_path), _params())
    assert _main(log)[2]["modulation_gate_passed"] is False
    assert "FLAG: modulation not recovered" in capsys.readouterr().out

    log = _install(monkeypatch, tmp_path, mod_depth=0.0)
    p = _params()
    p["Modulation_params"]["min_block_t"] = 5.0
    with pytest.raises(RuntimeError, match="modulation not recovered"):
        zs.run_zero_span_parity(_Ctx(tmp_path), p)
    assert not any(e[0] == "chunked_acquire" for e in log)  # no main record


def test_no_validation_builds_one_instance_with_unchanged_cfg(monkeypatch, tmp_path):
    log = _install(monkeypatch, tmp_path)
    off = {k: False for k in _params() if k.startswith("Validate_") or k == "Build_EvidenceReport"}
    zs.run_zero_span_parity(_Ctx(tmp_path), _params(**off))
    assert [e[0] for e in log] == ["separator", "new", "chunked_acquire", "save_data", "analyze"]
    assert log[0][2]["pulse_freq"] is None  # only the run's own calibration
    cfg = _main(log)[2]
    assert cfg["read_pulse_freq"] == F_RES and cfg["parity_drive_freq"] == F_Q - 0.3
    assert not any(k.startswith(("read_pulse_freq_", "modulation_", "separator_")) for k in cfg)


def test_nearest_contrast_peak():
    q = np.linspace(0.0, 4.0, 201)  # 20 kHz grid
    s2 = _stage2(q, [1.013, 2.5], snr_pp=8.0)
    f, snr, info = zs.nearest_contrast_peak(s2, 1.1, 0.2)
    assert f == pytest.approx(1.013, abs=1e-3) and snr == 8.0  # sub-bin, not the 1.02 grid
    assert info["reason"] == "adopted" and info["grid_freq"] == pytest.approx(1.02)
    f, snr, info = zs.nearest_contrast_peak(s2, 1.1, 0.08)  # centre 0.087 MHz from f0
    assert (f, info["reason"]) == (None, "outside_capture")
    f, snr, info = zs.nearest_contrast_peak(s2, 1.1, 0.2, min_snr=10.0)
    assert (f, snr, info["reason"]) == (None, 8.0, "low_snr")
    s1 = _stage2(q, [1.013], snr_pp=8.0, noise=0.01, seed=1)  # one line: no partner tail
    f, snr, info = zs.nearest_contrast_peak(s1, 1.013, 0.2)
    assert (f, info["reason"]) == (None, "consistent_with_f0")  # no shift to adopt
    s2c = _stage2(np.linspace(0.0, 4.0, 41), [1.013, 2.5], snr_pp=8.0)  # 0.1 MHz grid
    f, snr, info = zs.nearest_contrast_peak(s2c, 1.1, 0.2)
    assert (f, info["reason"]) == (None, "fit_failed")  # never snapped to a grid point
    assert zs.nearest_contrast_peak({"peaks": {}}, 1.1, 0.2)[:2] == (None, None)


def test_modulation_block_t():
    scores, ref, gaps = _modulated(0.3)
    bt = zs.modulation_block_t(scores, ref, gaps)
    assert bt["n_on_blocks"] == bt["n_off_blocks"] == 10
    # depth 0.3 per sample, 200-sample blocks: block-mean se 1/sqrt(200), t ~ 0.3*sqrt(1000)
    assert bt["block_t"] == pytest.approx(0.3 * np.sqrt(1000), rel=0.35)
    assert zs.modulation_block_t(-scores, ref, gaps)["block_t"] < 0  # signed
    # null: pure noise stays well below the default threshold
    null = [zs.modulation_block_t(*_modulated(0.0, seed=s))["block_t"] for s in range(200)]
    assert np.mean(np.abs(null) >= zs.MODULATION_MIN_BLOCK_T) < 0.01
    assert np.isnan(zs.modulation_block_t(scores[:400], ref[:400], gaps[:1])["block_t"])


def test_modulation_gate():
    good = {"block_t": -12.0, "correlation": 0.2, "snr": 0.3}
    g = zs.modulation_gate(good, {})
    assert g["passed"] and not g["enforced"]  # |block_t|: a sign flip still passes
    assert g["thresholds"] == {"min_block_t": zs.MODULATION_MIN_BLOCK_T}
    # recipe thresholds replace the default and are enforced; only the ones set are tested
    g = zs.modulation_gate(good, {"min_snr": 1.0})
    assert not g["passed"] and g["enforced"] and g["thresholds"] == {"min_snr": 1.0}
    g = zs.modulation_gate(good, {"min_abs_correlation": 0.1})
    assert g["passed"] and g["enforced"]
    assert not zs.modulation_gate({**good, "block_t": float("nan")}, {})["passed"]


@pytest.mark.parametrize("shift", [-0.2, -0.45, -0.6, 0.45, 1.5])
@pytest.mark.parametrize("which", ["lower", "higher"])
def test_stage2_branch_follows_the_doublet_order(shift, which):
    # a common CW-readout shift beyond half the 0.6 MHz splitting puts the partner nearest
    # the parked line; a stage-2 doublet matching the cached splitting is assigned by order
    q = np.linspace(F_Q - 5.3, F_Q + 4.7, N_Q)
    lines = [F_Q - 0.3 + shift, F_Q + 0.3 + shift]
    f0 = F_Q - 0.3 if which == "lower" else F_Q + 0.3
    f, _, info = zs.nearest_contrast_peak(_stage2(q, lines), f0, 0.3, which=which, expected_sep=0.6)
    assert info["doublet"] == "matched" and info["assignment"] == "doublet_order"
    assert info["reason"] == "adopted"
    assert f == pytest.approx(lines[0] if which == "lower" else lines[1], abs=5e-3)
    # without the doublet check the nearest line is taken: the partner for |shift| > 0.3
    f_near, _, info_near = zs.nearest_contrast_peak(_stage2(q, lines), f0, 0.3)
    assert info_near["assignment"] == "nearest" and info_near["doublet"] == "unknown"
    if abs(shift) > 0.3 and abs(shift) < 0.9 and f_near is not None:
        assert f_near != pytest.approx(f, abs=5e-3)


def test_stage2_doublet_mismatch_falls_back_to_nearest_and_flags(monkeypatch, tmp_path, capsys):
    q = np.linspace(F_Q - 5.3, F_Q + 4.7, N_Q)
    # one line found (the partner shifted out of the peak finder) or a 1.1 MHz pair
    for lines in ([F_Q - 0.25], [F_Q - 0.25, F_Q + 0.85]):
        f, _, info = zs.nearest_contrast_peak(
            _stage2(q, lines), F_Q - 0.3, 0.3, which="lower", expected_sep=0.6
        )
        assert info["doublet"] == "mismatch" and info["assignment"] == "nearest"
        assert f == pytest.approx(F_Q - 0.25, abs=5e-3)
    # an explicit tolerance decides the match
    f, _, info = zs.nearest_contrast_peak(
        _stage2(q, [F_Q - 0.25, F_Q + 0.85]),
        F_Q - 0.3,
        0.3,
        which="lower",
        expected_sep=0.6,
        sep_tol=0.6,
    )
    assert info["doublet"] == "matched"
    # the run prints a FLAG and records the stage-2 doublet in the main cfg
    log = _install(monkeypatch, tmp_path, peaks=[F_Q - 0.25, F_Q + 0.85])
    zs.run_zero_span_parity(_Ctx(tmp_path), _params())
    assert "do not match the cached doublet" in capsys.readouterr().out
    cfg = _main(log)[2]
    assert cfg["parity_stage2_doublet"] == "mismatch"
    assert cfg["parity_stage2_peak_sep_MHz"] == pytest.approx(1.1, abs=0.07)
    assert cfg["parity_drive_freq"] == pytest.approx(F_Q - 0.25, abs=5e-3)


def test_run_adopts_the_parked_branch_for_a_shift_beyond_half_the_splitting(
    monkeypatch, tmp_path, capsys
):
    # common shift -0.45 MHz: lines at F_Q - 0.75 / F_Q - 0.15; the parked (lower) line is
    # F_Q - 0.75, and control D drives both cached lines shifted by -0.45 MHz
    log = _install(monkeypatch, tmp_path, peaks=[F_Q - 0.75, F_Q - 0.15])
    zs.run_zero_span_parity(_Ctx(tmp_path), _params())
    assert "assigned by doublet order" in capsys.readouterr().out
    cfg = _main(log)[2]
    assert cfg["parity_stage2_doublet"] == "matched"
    assert cfg["parity_drive_freq"] == pytest.approx(F_Q - 0.75, abs=5e-3)
    pf = next(e for e in log if e[0] == "stage8")[3]
    assert pf["lower"] == pytest.approx(F_Q - 0.75, abs=5e-3)
    assert pf["higher"] == pytest.approx(F_Q - 0.15, abs=5e-3)
