"""F41: modified_ramsey_control runs the modified_ramsey sequence and analysis at the sweet spot.

The sweet-spot null used to be a different sequence (df = cd_max_mhz, no tau_harmonic_k, no
bandwidth ratio, mr_relax_delay 0, 500 shots) scored by KMeans + a moving-average
hysteresis switch count, an estimator with no null distribution: it counts thousands of
"jumps" in uncorrelated shots. Given the session's ModifiedRamsey_params it now builds the
Ramsey cfg with build_modified_ramsey_cfg (so df, tau, mr_reps, mr_relax_delay, pulses and
active reset are the MR ones), takes a SingleShot calibration at V_sweet and analyses the
record with the MR analysis (same mapping seed, emission model and gates), reporting gamma,
identifiability, r(1) and the separation-normalised lag-covariance sum next to the newest
analysed MR record (the ACF amplitude is a fit that is NaN for an uncorrelated record, so it
cannot carry the comparison). KMeans and the hysteresis trace remain as diagnostic plots.
docs/experiments/modified_ramsey_control.md

Hardware-free and seeded. Run from the repo root:
    python -m pytest tests/test_mrc_parity_analysis.py
"""

import json
import math
import os

import numpy as np
import pytest

import qicklab.runs.modified_ramsey as mr_runs
from qicklab.analysis.iq import kmeans_split
from qicklab.analysis.modified_ramsey import (
    analyze_modified_ramsey_record,
    true_state_separation,
)
from qicklab.analysis.rates import simulate_telegraph_trace
from qicklab.analysis.readout import calibrate_readout_from_labeled_shots
from qicklab.core.context import Context

N_SHOTS = 256
REP_US = 512.0  # rep period of the CSTQ03 MR settings (500 us relax)


class _FakeMR:
    instances = []

    def __init__(self, path=None, cfg=None, soc=None, soccfg=None, outerFolder=None):
        self.path, self.cfg = path, cfg
        self.fname = os.path.join(outerFolder, path, f"{len(type(self).instances):02d}_data.h5")
        type(self).instances.append(self)

    def acquire(self):
        rng = np.random.default_rng(len(type(self).instances))
        return {
            "config": self.cfg,
            "data": {
                "shots_i": rng.normal(size=N_SHOTS),
                "shots_q": rng.normal(size=N_SHOTS),
                "scheduled_rep_period_us": REP_US,
            },
        }

    def display(self, data, **kwargs):
        pass

    def save_data(self, data):
        pass

    def save_config(self):
        pass


class _Yoko:
    def __init__(self, v):
        self.v = v

    def query(self, cmd):
        return str(self.v)


class _Ctx:
    working_config = Context.working_config

    def __init__(self, outer):
        self.config = {"reps": 10}
        self.outerFolder = outer
        self.qubit_frequency_center = 4186.7
        self.yoko = _Yoko(0.125)
        self.pi2_gain = 2000
        self.qubit_gain = 4000
        self.qubit_sigma = 0.01
        self.qubit_flattop = None
        self.Qubit_Readout = [2]
        self.Qubit_Pulse = 2
        self.soc = None
        self.soccfg = None


def _mr_params(**overrides):
    params = {
        "df": 1.0,
        "f_ge": 4187.2,
        "tau_harmonic_k": 3,
        "symmetric_ramsey": True,
        "max_drive_bandwidth_ratio": 1.4,
        "mr_reps": 50000,
        "mr_relax_delay": 500.0,
        "num_cycles": 1,
        "use_apriori_separator": True,
        "ss_calib_shots": 777,
        "ss_recalib_every_n_cycles": None,
        "parity_analysis_enabled": True,
        "expected_parity_dwell_ms": 2.5,
        "drift_window_ms": 150.0,
        "hmm_min_emission_snr": 0.7,
        "average_n_shots": 8,
    }
    params.update(overrides)
    return params


def _mrc_params(**overrides):
    params = {
        "sweet_spot_max_df_mhz": 0.1,
        "cd_max_mhz": 0.682,
        "cd_period_mv": 4.37,
        "num_cycles": 1,
        "SpecSpan": 1.0,
        "SpecNumPoints": 101,
        "reps": 10,
        "rounds": 10,
        "relax_delay": 1500,
        "sigma": 2,
        "gain": 700,
        "qubit_length": 2,
        "df": 0.5,
        "dV": 5e-4,
        "voltage_min": 0.0,
        "voltage_max": 0.01,
        "max_voltage_tries": 1000,
        "mr_relax_delay": 0.0,
        "mr_reps": 500,
    }
    params.update(overrides)
    return params


@pytest.fixture
def fakes(monkeypatch):
    _FakeMR.instances = []
    calls = {
        "analyze": [],
        "ss_at_v": [],
        "ss_shots": [],
        "ss_cfg_v": [],
        "records": [],
        "record_exps": [],  # the experiment save_record attributes each record to (F46)
        "summaries": [],
    }
    sweet = {"voltages": [0.0059], "calls": 0}

    def analyze(*args, **kwargs):
        calls["analyze"].append(kwargs)
        return {
            "summary": {
                "identifiable": False,
                "gamma01_hz": float("nan"),
                "gamma10_hz": float("nan"),
                "gamma01_err_hz": float("nan"),
                "warnings": ["no switching"],
                "occupancy_state1": 0.5,
            },
            "hmm": {},
            "calibration": {"separation": 2.0},
            "acf": {
                "amplitude": float("nan"),
                "acf": np.array([1.0, 0.05, 0.01]),
                "lag_covariance_sum": {
                    "available": True,
                    "value": 0.04,  # / separation^2 = 0.01
                    "boot": np.linspace(-0.02, 0.08, 101),
                    "max_lag": 5,
                },
            },
        }

    def sep(ctx, ss_shots=1000, **kw):
        calls["ss_at_v"].append(float(ctx.yoko.query(":SOUR:LEV?")))
        calls["ss_shots"].append(ss_shots)
        calls["ss_cfg_v"].append(kw.get("current_voltage"))
        return {
            "data_ss": None,
            "g_center": np.array([-1.0, 0.0]),
            "e_center": np.array([1.0, 0.0]),
        }

    def search(**kw):
        # moves the yoko, as the real search does
        v = sweet["voltages"][min(sweet["calls"], len(sweet["voltages"]) - 1)]
        sweet["calls"] += 1
        kw["yoko"].v = v
        return 4186.9, v, {"peak_sep": None, "sweet_spot_ok": True, "snr": 9.0}, []

    monkeypatch.setattr(mr_runs, "ModifiedRamsey", _FakeMR)
    monkeypatch.setattr(
        mr_runs, "modified_ramsey_timing", lambda soccfg, cfg: {"scheduled_rep_period_us": REP_US}
    )
    monkeypatch.setattr(mr_runs, "find_sweet_spot", search)
    monkeypatch.setattr(mr_runs, "get_apriori_separator_from_singleshot", sep)
    monkeypatch.setattr(
        mr_runs, "_extract_iq_from_singleshot_data", lambda d, s: (np.zeros(4), np.zeros(4))
    )
    monkeypatch.setattr(mr_runs, "calibrate_readout_from_labeled_shots", lambda *a: {"cal": 1})
    monkeypatch.setattr(mr_runs, "analyze_modified_ramsey_record", analyze)
    monkeypatch.setattr(mr_runs, "compare_parity_controls", lambda p, c: {"all_expected": True})
    monkeypatch.setattr(mr_runs.plt, "savefig", lambda *a, **k: None)

    def record(base, cfg, exp=None, **arrays):
        calls["records"].append(arrays)
        calls["record_exps"].append(exp)

    monkeypatch.setattr(mr_runs, "save_record", record)
    monkeypatch.setattr(
        mr_runs, "save_cycle_summary", lambda d, rows: calls["summaries"].append(rows)
    )
    calls["sweet"] = sweet
    return calls


# keys that legitimately differ between an MR record and its sweet-spot null
_PER_RECORD = {"f_ge", "current_voltage", "f_ge_measured_at_V", "modified_ramsey_timing"}
_ANALYSIS_KEYS = (
    "drift_timescale_s",
    "expected_dwell_s",
    "symmetric_hmm",
    "n_boot",
    "mapping_probabilities",
    "mapping_probabilities_calibrated",
    "fit_mapping",
    "mapping_seed_source",
    "hmm_kwargs",
)


def test_mrc_runs_the_mr_sequence_and_analysis(fakes, tmp_path, capsys):
    outer = str(tmp_path) + "/"
    mr = _mr_params()
    mr_runs.run_modified_ramsey(_Ctx(outer), mr)
    (mr_inst,) = _FakeMR.instances
    mr_analysis = fakes["analyze"][0]

    _FakeMR.instances = []
    ctx = _Ctx(outer)
    mr_runs.run_modified_ramsey_control(ctx, _mrc_params(), mr)
    (mrc_inst,) = _FakeMR.instances
    mrc_analysis = fakes["analyze"][1]
    cfg, ref = mrc_inst.cfg, mr_inst.cfg

    # same sequence: every program key but the per-record ones is the MR one
    assert set(cfg) - _PER_RECORD == set(ref) - _PER_RECORD
    for key in set(ref) - _PER_RECORD:
        assert cfg[key] == ref[key], key
    assert cfg["df"] == 1.0 and cfg["mr_tau_harmonic_k"] == 3
    assert cfg["ramsey_tau_us"] == pytest.approx(3 / (2 * 1.0))
    assert (cfg["reps"], cfg["mr_relax_delay"]) == (50000, 500.0)  # inherited, not 500 / 0
    assert cfg["max_drive_bandwidth_ratio"] == 1.4 and cfg["symmetric_ramsey"] is True
    assert cfg["f_ge"] == 4186.9 and cfg["current_voltage"] == 0.0059
    assert "f_ge_measured_at_V" not in cfg

    # same analysis: settings, gates and emission model
    for key in _ANALYSIS_KEYS:
        assert mrc_analysis[key] == mr_analysis[key], key
    assert mrc_analysis["hmm_kwargs"] == {"min_emission_snr": 0.7}
    assert mrc_analysis["base_name"].endswith("_continuous")
    assert mrc_analysis["out_dir"].endswith("ModifiedRamsey_Control")

    out = capsys.readouterr().out
    assert "ModifiedRamsey_Control_params['mr_reps']=500 ignored" in out
    assert "ModifiedRamsey_Control_params['mr_relax_delay']=0.0 ignored" in out


def test_every_ignored_sequence_key_is_noted(fakes, tmp_path, capsys):
    mrc = _mrc_params(reset_read_latency_us=0.7, use_active_reset=False, symmetric_ramsey=True)
    mr_runs.run_modified_ramsey_control(_Ctx(str(tmp_path) + "/"), mrc, _mr_params())
    (inst,) = _FakeMR.instances
    assert "reset_read_latency_us" not in inst.cfg  # the MR dict does not set it
    out = capsys.readouterr().out
    assert (
        "ModifiedRamsey_Control_params['reset_read_latency_us']=0.7 ignored: the Ramsey uses "
        "ModifiedRamsey_params['reset_read_latency_us']=<unset: program default>" in out
    )
    assert "ModifiedRamsey_Control_params['use_active_reset']=False ignored" in out
    assert "['symmetric_ramsey']" not in out  # same value in both dicts: no note


def test_singleshot_calibrated_at_v_sweet(fakes, tmp_path):
    ctx = _Ctx(str(tmp_path) + "/")
    fakes["sweet"]["voltages"] = [0.0059, 0.0059, 0.0081]
    mr_runs.run_modified_ramsey_control(ctx, _mrc_params(num_cycles=3), _mr_params())
    # after the search moved the yoko; again only when V_sweet moves (cadence None)
    assert fakes["ss_at_v"] == [0.0059, 0.0081]
    # and its saved cfg records that bias, not the session one
    assert fakes["ss_cfg_v"] == [0.0059, 0.0081]
    assert fakes["ss_shots"] == [777, 777]
    assert len(_FakeMR.instances) == 3


def test_singleshot_recalibration_cadence(fakes, tmp_path):
    ctx = _Ctx(str(tmp_path) + "/")
    mr = _mr_params(ss_recalib_every_n_cycles=2)
    mr_runs.run_modified_ramsey_control(ctx, _mrc_params(num_cycles=4), mr)
    assert len(fakes["ss_at_v"]) == 2  # cycles 0 and 2 at an unmoved V_sweet


def test_result_saved_and_compared_with_latest_mr(fakes, tmp_path, capsys):
    outer = str(tmp_path) + "/"
    day = os.path.join(outer, "ModifiedRamsey", "2026_10_16")
    os.makedirs(day)
    mr_lag = {
        "available": True,
        "value": 0.4,  # / separation^2 (1.0) = 0.4
        "boot": list(np.linspace(0.3, 0.5, 101)),
        "max_lag": 5,
    }
    with open(os.path.join(day, "Cycle_000_MR_x_continuous_analysis.json"), "w") as fh:
        json.dump(
            {
                "identifiable": True,
                "gamma01_hz": 210.0,
                "acf": {"amplitude": 0.008, "r1": 0.3, "lag_covariance_sum": mr_lag},
                "readout_separation": 1.0,
            },
            fh,
        )

    mr_runs.run_modified_ramsey_control(_Ctx(outer), _mrc_params(), _mr_params())
    (rec,) = fakes["records"]
    # the record's provenance sidecar names the MRC Ramsey experiment that acquired it
    (exp,) = fakes["record_exps"]
    assert exp is _FakeMR.instances[-1] and exp.path == "ModifiedRamsey_Control"
    ((row,),) = fakes["summaries"]
    for d in (rec, row):
        assert bool(d["parity_identifiable"]) is False
        assert math.isnan(float(d["gamma01_hz"]))
        assert math.isnan(float(d["acf_amplitude"]))  # the fit fails on a valid null
        assert float(d["acf_r1"]) == pytest.approx(0.05)
        assert float(d["acf_r1_mr"]) == pytest.approx(0.3)
        assert float(d["lag_covariance_norm"]) == pytest.approx(0.01)
        assert float(d["lag_covariance_norm_mr"]) == pytest.approx(0.4)
        assert float(d["lag_covariance_ratio_to_mr"]) == pytest.approx(0.025)
        assert 0.025 < float(d["lag_covariance_ratio_upper95"]) < 1.0
        assert math.isfinite(float(d["blob_snr"]))
    assert row["lag_covariance_ratio_reason"] == ""
    # a pre-2026-10 sidecar: no readout_separation_source / prep, so the MR separation may
    # be the raw one; flagged, and no prep correction is possible
    assert "biased LOW" in row["lag_covariance_ratio_warning"]
    assert "purity p is unknown" in str(rec["lag_covariance_ratio_warning"])
    assert math.isnan(row["lag_covariance_ratio_prep_corrected"])
    assert row["mr_reference"]["readout_prep_e_predicted"] is None
    assert row["mr_reference"]["gamma01_hz"] == 210.0
    assert row["mr_reference"]["file"].endswith("_continuous_analysis.json")
    assert "lag_covariance_sum" not in row["mr_reference"]  # no bootstrap list per cycle
    assert "state_hysteresis" in row["diagnostic_only"]
    assert "state_hysteresis" in list(rec["diagnostic_only"]) and "state_hysteresis" in rec
    assert row["parity_analysis_warnings"] == ["no switching"]
    out = capsys.readouterr().out
    assert "most recent MR record Cycle_000_MR_x_continuous_analysis.json" in out
    assert "MRC/MR lag covariance = 0.025" in out
    assert "[MRC]   WARNING: the MR readout_separation is the raw labelled-set one" in out


def test_comparison_without_an_mr_reference(fakes, tmp_path):
    mr_runs.run_modified_ramsey_control(_Ctx(str(tmp_path) + "/"), _mrc_params(), _mr_params())
    ((row,),) = fakes["summaries"]
    assert math.isnan(row["lag_covariance_ratio_to_mr"]) and math.isnan(row["acf_r1_mr"])
    assert row["lag_covariance_norm"] == pytest.approx(0.01)
    assert "no analysed MR record" in row["lag_covariance_ratio_reason"]
    assert row["mr_reference"] is None


def test_without_mr_params_falls_back_to_the_control_dict(fakes, tmp_path, capsys):
    mr_runs.run_modified_ramsey_control(_Ctx(str(tmp_path) + "/"), _mrc_params())
    (inst,) = _FakeMR.instances
    cfg = inst.cfg
    assert cfg["df"] == 0.682 and cfg["mr_tau_harmonic_k"] == 1
    assert cfg["ramsey_tau_us"] == 1.0 / (2.0 * 0.682)
    assert (cfg["reps"], cfg["mr_relax_delay"]) == (500, 0.0)
    assert cfg["max_drive_bandwidth_ratio"] == 1.0
    assert len(fakes["ss_at_v"]) == 1 and len(fakes["analyze"]) == 1
    assert "no ModifiedRamsey_params" in capsys.readouterr().out


def test_active_reset_is_calibrated_and_wired(fakes, tmp_path, monkeypatch):
    calibrated = []
    monkeypatch.setattr(
        mr_runs, "calibrate_active_reset_readout", lambda ctx: calibrated.append(True)
    )
    mr = _mr_params(use_active_reset=True)
    mr_runs.run_modified_ramsey_control(_Ctx(str(tmp_path) + "/"), _mrc_params(), mr)
    (inst,) = _FakeMR.instances
    assert calibrated == [True]
    assert inst.cfg["use_active_reset"] is True
    assert inst.cfg["readout_threshold"] == 0.0  # midpoint of the fake g/e centres in I
    assert inst.cfg["reset_ground_below_threshold"] is True


# ---------------------------------------------------------------------------
# the estimator: hysteresis count vs the MR analysis on synthetic sweet-spot records
# ---------------------------------------------------------------------------

MU_E = 3.0


def _cal():
    rng = np.random.default_rng(41)
    n = 4000
    return calibrate_readout_from_labeled_shots(
        rng.normal(0.0, 1.0, n),
        rng.normal(0.0, 1.0, n),
        rng.normal(MU_E, 1.0, n),
        rng.normal(0.0, 1.0, n),
    )


def _carryover_shots(n, p_e, c, seed):
    """Shot outcomes with no telegraph: P(e) = p_e, plus an AR(1) term c (inter-shot
    T1 carryover at relax 0): P(e_n) = p_e + c * (e_{n-1} - p_e)."""
    rng = np.random.default_rng(seed)
    u = rng.random(n)
    out = np.zeros(n, dtype=bool)
    prev = 1.0 if u[0] < p_e else 0.0
    for i in range(n):
        prev = 1.0 if u[i] < p_e + c * (prev - p_e) else 0.0
        out[i] = prev > 0
    return out


def _telegraph_shots(n, dt, gamma, seed):
    rng = np.random.default_rng(seed)
    hidden = simulate_telegraph_trace(
        n, dt, gamma, gamma, mu0=0.0, mu1=1.0, sigma0=1e-9, sigma1=1e-9, seed=seed + 1
    )["states"]
    return rng.random(n) < np.where(hidden == 0, 0.1, 0.9)


def _both_estimators(excited, dt, seed=7):
    rng = np.random.default_rng(seed)
    I = rng.normal(np.where(excited, MU_E, 0.0), 1.0)
    Q = rng.normal(0.0, 1.0, excited.size)
    res = analyze_modified_ramsey_record(
        I, Q, dt, _cal(), expected_dwell_s=2.5e-3, save_plots=False, save_sidecars=False
    )
    binary = kmeans_split(np.column_stack([I, Q]), min_blob_snr=2.0)[0]
    window_n = max(1, int(round(0.1e-3 / dt)))  # the window_ms = 0.1 default
    jumps = mr_runs.hysteresis_parity_trace(binary, window_n, 0.4, 0.6)[2]
    return res, int(jumps.sum())


@pytest.mark.parametrize("p_e, seed", [(0.5, 3), (0.2, 4)])
def test_uncorrelated_null_is_not_identifiable_but_hysteresis_counts_jumps(p_e, seed):
    # MR settings: 500 us relax, rep ~512 us, no carryover; no switching at all
    res, jumps = _both_estimators(_carryover_shots(20000, p_e, 0.0, seed), 512e-6)
    s = res["summary"]
    assert not s["identifiable"] and math.isnan(s["gamma01_hz"]), s["warnings"]
    assert abs(res["acf"]["acf"][1]) < 0.03
    assert jumps > 1000  # the old MRC output: thousands of "switches" in i.i.d. shots


def test_relax_zero_carryover_shows_as_lag1_correlation():
    # relax 0 (rep ~12 us): inter-shot carryover gives r(1) ~ c with no telegraph, the
    # artefact the CSTQ03 2026-08-04 diagnostic found; inheriting the MR relax removes it
    res, _ = _both_estimators(_carryover_shots(20000, 0.2, 0.4, 6), 12e-6)
    assert res["acf"]["acf"][1] > 0.2


def test_injected_telegraph_is_identified():
    res, _ = _both_estimators(_telegraph_shots(20000, 262e-6, 200.0, 8), 262e-6)
    s = res["summary"]
    assert s["identifiable"], res["hmm"]["unidentifiable_reasons"]
    assert abs(s["gamma01_hz"] - 200.0) < 0.25 * 200.0, s["gamma01_hz"]


def test_hysteresis_trace_matches_the_legacy_loop():
    rng = np.random.default_rng(5)
    binary = (rng.random(500) < 0.3).astype(int)
    avg, hyst, jumps = mr_runs.hysteresis_parity_trace(binary, 7, 0.4, 0.6)
    ref_avg = np.convolve(binary.astype(float), np.ones(7) / 7, mode="same")
    state, ref = int(binary[0]), []
    for v in ref_avg:
        state = 1 if v >= 0.6 else (0 if v <= 0.4 else state)
        ref.append(state)
    assert np.array_equal(avg, ref_avg) and np.array_equal(hyst, ref)
    assert np.array_equal(jumps, (np.diff(ref) != 0).astype(int))


def test_valid_null_vs_telegraph_mr_through_the_sidecar(tmp_path):
    """The real analysis end to end: an MR record with a 200 Hz telegraph is written as a
    sidecar, read back by latest_modified_ramsey_analysis, and an i.i.d. null with a 2x
    larger readout scale is compared with it. The null's ACF amplitude is NaN; r(1) and
    the normalised lag-covariance ratio separate it from the MR record."""
    dt = REP_US * 1e-6
    rng = np.random.default_rng(11)
    tele = _telegraph_shots(20000, dt, 200.0, 12)
    day = tmp_path / "ModifiedRamsey" / "2026_10_16"
    analyze_modified_ramsey_record(
        rng.normal(np.where(tele, MU_E, 0.0), 1.0),
        rng.normal(0.0, 1.0, tele.size),
        dt,
        _cal(),
        expected_dwell_s=2.5e-3,
        save_plots=False,
        save_sidecars=True,
        out_dir=str(day),
        base_name="Cycle_000_MR_x_continuous",
    )
    ref = mr_runs.latest_modified_ramsey_analysis(str(tmp_path))
    assert ref["acf_r1"] > 0.2 and ref["readout_separation"] == pytest.approx(MU_E, rel=0.1)
    assert ref["lag_covariance_sum"]["available"]

    scale = 2.0  # another bias, another readout scale
    cal2 = calibrate_readout_from_labeled_shots(
        scale * rng.normal(0.0, 1.0, 4000),
        scale * rng.normal(0.0, 1.0, 4000),
        scale * rng.normal(MU_E, 1.0, 4000),
        scale * rng.normal(0.0, 1.0, 4000),
    )

    def scaled(excited):
        return analyze_modified_ramsey_record(
            scale * rng.normal(np.where(excited, MU_E, 0.0), 1.0),
            scale * rng.normal(0.0, 1.0, excited.size),
            dt,
            cal2,
            expected_dwell_s=2.5e-3,
            save_plots=False,
            save_sidecars=False,
        )

    res = scaled(_carryover_shots(20000, 0.5, 0.0, 13))
    assert math.isnan(res["acf"]["amplitude"])  # no amplitude to compare for a valid null
    cmp = mr_runs.null_lag_covariance_vs_mr(
        res["acf"], true_state_separation(res["calibration"])[0], ref
    )
    assert cmp["reason"] == "", cmp["reason"]
    assert abs(cmp["ratio"]) < 0.1 and cmp["upper95"] < 0.3, cmp
    # the same telegraph at the other readout scale reads ratio ~ 1 after normalisation
    res_t = scaled(tele)
    cmp_t = mr_runs.null_lag_covariance_vs_mr(
        res_t["acf"], true_state_separation(res_t["calibration"])[0], ref
    )
    assert 0.7 < cmp_t["ratio"] < 1.4, cmp_t


def test_normalisation_uses_the_true_state_separation(tmp_path):
    """The SingleShot pi pulse plays at qubit_frequency_center, df/2 from each parity branch
    at the MR bias (e-cloud purity < 1) but on the degenerate line at V_sweet (purity ~1).
    The raw labelled-set separation at the MR bias is then shrunk by the purity, and dividing
    by it would inflate MR's normalised lag sum by 1/purity^2 and bias the MRC/MR ratio low
    (~purity^2). The sidecar stores the mixture-fit (clean-cloud) separation instead, so the
    same telegraph at both biases reads ratio ~ 1."""
    dt = REP_US * 1e-6
    rng = np.random.default_rng(21)
    purity = 0.7
    n = 4000
    e_prepared = rng.random(n) < purity
    cal_mr = calibrate_readout_from_labeled_shots(
        rng.normal(0.0, 1.0, n),
        rng.normal(0.0, 1.0, n),
        rng.normal(np.where(e_prepared, MU_E, 0.0), 1.0),
        rng.normal(0.0, 1.0, n),
    )
    assert cal_mr["clean_cloud_source"] == "mixture"
    assert cal_mr["separation"] == pytest.approx(purity * MU_E, rel=0.05)  # raw: shrunk
    sep_true, source = true_state_separation(cal_mr)
    assert source == "mixture" and sep_true == pytest.approx(MU_E, rel=0.05)

    tele = _telegraph_shots(20000, dt, 200.0, 22)
    day = tmp_path / "ModifiedRamsey" / "2026_10_16"
    analyze_modified_ramsey_record(
        rng.normal(np.where(tele, MU_E, 0.0), 1.0),
        rng.normal(0.0, 1.0, tele.size),
        dt,
        cal_mr,
        expected_dwell_s=2.5e-3,
        save_plots=False,
        save_sidecars=True,
        out_dir=str(day),
        base_name="Cycle_000_MR_x_continuous",
    )
    ref = mr_runs.latest_modified_ramsey_analysis(str(tmp_path))
    assert ref["readout_separation"] == pytest.approx(sep_true)
    assert ref["readout_separation_source"] == "mixture"

    # V_sweet: perfect prep (no resolvable mixture, raw == clean) and a 2x readout scale
    scale = 2.0
    cal_sw = calibrate_readout_from_labeled_shots(
        scale * rng.normal(0.0, 1.0, n),
        scale * rng.normal(0.0, 1.0, n),
        scale * rng.normal(MU_E, 1.0, n),
        scale * rng.normal(0.0, 1.0, n),
    )
    assert true_state_separation(cal_sw)[0] == pytest.approx(cal_sw["separation"], rel=0.02)
    res = analyze_modified_ramsey_record(
        scale * rng.normal(np.where(tele, MU_E, 0.0), 1.0),
        scale * rng.normal(0.0, 1.0, tele.size),
        dt,
        cal_sw,
        expected_dwell_s=2.5e-3,
        save_plots=False,
        save_sidecars=False,
    )
    cmp = mr_runs.null_lag_covariance_vs_mr(
        res["acf"], true_state_separation(res["calibration"])[0], ref
    )
    assert cmp["reason"] == "", cmp["reason"]
    assert 0.8 < cmp["ratio"] < 1.25, cmp
    # the raw MR separation would have read ~ purity^2 for the same telegraph
    ref_raw = dict(ref, readout_separation=cal_mr["separation"])
    cmp_raw = mr_runs.null_lag_covariance_vs_mr(
        res["acf"], true_state_separation(res["calibration"])[0], ref_raw
    )
    assert cmp_raw["ratio"] == pytest.approx(purity**2 * cmp["ratio"], rel=0.1)
    assert cmp_raw["ratio"] < 0.65


# ---------------------------------------------------------------------------
# a raw ("moments") MR separation: flagged, and corrected with the predicted prep
# ---------------------------------------------------------------------------


def test_predicted_singleshot_prep():
    ctx = _Ctx("unused")  # pi at 4186.7 MHz
    # a 40 ns pulse is ~25 MHz wide: +-0.5 MHz detuning is ~ on resonance
    assert mr_runs.predicted_singleshot_prep(ctx, 4187.2, 1.0) > 0.99
    # a 1 us (sigma 0.25 us) pulse is ~1 MHz wide: the branches are poorly excited
    ctx.qubit_sigma = 0.25
    p_mr = mr_runs.predicted_singleshot_prep(ctx, 4187.2, 1.0)
    assert p_mr < mr_runs.SS_PREP_NEAR_ONE
    assert p_mr == pytest.approx(mr_runs.predict_pi_transfer(0.25, 0.5))  # symmetric
    # the degenerate line on the pi frequency (V_sweet with f_ge = the qubit centre)
    assert mr_runs.predicted_singleshot_prep(ctx, 4186.7, 0.0) == pytest.approx(1.0, abs=1e-6)
    ctx.qubit_flattop = 1  # a flat-top pi is not modelled
    assert mr_runs.predicted_singleshot_prep(ctx, 4187.2, 1.0) is None


def test_low_snr_calibration_falls_back_to_the_shrunk_raw_separation(tmp_path):
    """At the CSTQ03 analog SNR (~0.77) the SingleShot mixture fit does not resolve even at
    purity 0.7: the source is "moments" and the separation is the raw one, shrunk by the
    purity. The MR sidecar records that source and the predicted purity."""
    rng = np.random.default_rng(5)
    snr, purity, n = 0.77, 0.7, 1000
    e_prepared = rng.random(n) < purity
    cal = calibrate_readout_from_labeled_shots(
        rng.normal(0.0, 1.0, n),
        rng.normal(0.0, 1.0, n),
        rng.normal(np.where(e_prepared, snr, 0.0), 1.0),
        rng.normal(0.0, 1.0, n),
    )
    sep, source = true_state_separation(cal)
    assert source == "moments"
    assert sep == pytest.approx(purity * snr, rel=0.25) and sep < 0.85 * snr  # not true-state

    day = tmp_path / "ModifiedRamsey" / "2026_10_16"
    analyze_modified_ramsey_record(
        rng.normal(0.0, 1.0, 4000),
        rng.normal(0.0, 1.0, 4000),
        REP_US * 1e-6,
        cal,
        expected_dwell_s=2.5e-3,
        save_plots=False,
        save_sidecars=True,
        out_dir=str(day),
        base_name="Cycle_000_MR_x_continuous",
        readout_prep_e_predicted=purity,
    )
    ref = mr_runs.latest_modified_ramsey_analysis(str(tmp_path))
    assert ref["readout_separation_source"] == "moments"
    assert ref["readout_separation"] == pytest.approx(sep)
    assert ref["readout_prep_e_predicted"] == purity


def _lag_sum(value, max_lag=5):
    # a significant lag-covariance sum with a +-20 % bootstrap
    return {
        "available": True,
        "value": value,
        "boot": list(np.linspace(0.8 * value, 1.2 * value, 101)),
        "max_lag": max_lag,
    }


@pytest.mark.parametrize(
    "source, prep, warned, factor",
    [
        ("mixture", None, False, 1.0),  # true-state: nothing to correct
        ("moments", 0.98, False, 1 / 0.98**2),  # raw, but the prep is near 1
        ("moments", 0.7, True, 1 / 0.7**2),  # raw and poor prep: flagged and corrected
        ("moments", None, True, float("nan")),  # raw, prep unknown: flagged, no correction
        ("moments_fallback", 0.7, True, 1 / 0.7**2),
        ("moments", 0.07, True, float("nan")),  # too poorly prepared to correct
    ],
)
def test_raw_mr_separation_is_flagged_and_corrected(source, prep, warned, factor):
    """The same telegraph (normalised lag sum 0.25) at both biases. MR: true separation 1,
    the reference's separation 0.7 when raw (purity 0.7), else 1. MRC: true-state, 2."""
    sep_mr = 1.0 if source == "mixture" else (prep or 0.7)
    ref = {
        "lag_covariance_sum": _lag_sum(0.25 * 1.0**2),
        "readout_separation": sep_mr,
        "readout_separation_source": source,
        "readout_prep_e_predicted": prep,
    }
    mrc_acf = {"lag_covariance_sum": _lag_sum(0.25 * 2.0**2)}
    cmp = mr_runs.null_lag_covariance_vs_mr(mrc_acf, 2.0, ref, mrc_separation_source="mixture")
    assert cmp["reason"] == ""
    assert cmp["ratio"] == pytest.approx(sep_mr**2)  # biased low by the shrink^2
    assert bool(cmp["warning"]) is warned
    if warned:
        assert "biased LOW" in cmp["warning"] and source in cmp["warning"]
    if prep is not None and prep < mr_runs.SS_PREP_CORRECTABLE:
        assert "too low to correct" in cmp["warning"]
    if math.isnan(factor):
        assert math.isnan(cmp["ratio_prep_corrected"])
        assert math.isnan(cmp["upper95_prep_corrected"])
    else:
        assert cmp["ratio_prep_corrected"] == pytest.approx(cmp["ratio"] * factor)
        assert cmp["ratio_prep_corrected"] == pytest.approx(1.0)  # the true-state ratio
        assert cmp["upper95_prep_corrected"] == pytest.approx(cmp["upper95"] * factor)


def test_raw_mrc_separation_correction_is_conservative():
    """A raw MRC separation (shrunk by its own purity) biases the ratio HIGH; its predicted
    purity corrects it down, an unknown one is left as 1 (the larger, conservative value)."""
    ref = {
        "lag_covariance_sum": _lag_sum(0.25),
        "readout_separation": 1.0,
        "readout_separation_source": "mixture",
        "readout_prep_e_predicted": None,
    }
    mrc_acf = {"lag_covariance_sum": _lag_sum(0.25 * 2.0**2)}
    known = mr_runs.null_lag_covariance_vs_mr(
        mrc_acf, 0.9 * 2.0, ref, mrc_separation_source="moments", mrc_prep_predicted=0.9
    )
    assert known["warning"] == ""
    assert known["ratio"] == pytest.approx(1 / 0.81)
    assert known["ratio_prep_corrected"] == pytest.approx(1.0)
    unknown = mr_runs.null_lag_covariance_vs_mr(
        mrc_acf, 0.9 * 2.0, ref, mrc_separation_source="moments"
    )
    assert unknown["ratio_prep_corrected"] == pytest.approx(unknown["ratio"])
    # a predicted MRC purity too low to trust is not used to scale the ratio down
    tiny = mr_runs.null_lag_covariance_vs_mr(
        mrc_acf, 0.9 * 2.0, ref, mrc_separation_source="moments", mrc_prep_predicted=0.01
    )
    assert tiny["ratio_prep_corrected"] == pytest.approx(tiny["ratio"])


def test_mr_and_mrc_sidecars_get_the_predicted_prep(fakes, tmp_path):
    outer = str(tmp_path) + "/"
    ctx = _Ctx(outer)
    ctx.qubit_sigma = 0.25  # ~1 MHz wide: df/2 = 0.5 MHz detuning matters
    mr_runs.run_modified_ramsey(ctx, _mr_params())
    mr_runs.run_modified_ramsey_control(ctx, _mrc_params(), _mr_params())
    mr_kw, mrc_kw = fakes["analyze"]
    assert mr_kw["readout_prep_e_predicted"] == pytest.approx(
        mr_runs.predicted_singleshot_prep(ctx, 4187.2, 1.0)
    )
    assert mr_kw["readout_prep_e_predicted"] < mr_runs.SS_PREP_NEAR_ONE
    # V_sweet: f_ge = 4186.9, degenerate (S_sweet 0), 0.2 MHz from the pi
    assert mrc_kw["readout_prep_e_predicted"] == pytest.approx(
        mr_runs.predict_pi_transfer(0.25, 0.2)
    )
