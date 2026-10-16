"""Hardware-free tests of the Stage 1 sweet-spot search (F35).

The Strategy-B walk measures each grid voltage of [ss_voltage_min, ss_voltage_max] once,
then ramps to the best voltage and re-acquires a spectrum there; every spectrum must clear
the peak-SNR gate (freqcal_min_snr), and the start spectrum gets the Stage 1.5 gain raise.
A pass in which no spectrum clears the gate returns sweet_spot_ok=False, which
ModifiedRamsey_Control treats as "not verified". See
docs/experiments/auto_coherence.md#stages-in-detail.

    python -m pytest tests/test_sweet_spot_search.py
"""

import json
import os
import types

import numpy as np
import pytest

import qicklab.runs.auto_coherence as ac
import qicklab.runs.modified_ramsey as mr_runs
from qicklab.analysis.spectroscopy import find_two_tone_peaks
from qicklab.runs.sweet_spot import find_sweet_spot

CENTER = 4000.0  # MHz
HWHM = 0.02  # MHz


class _Yoko:
    def __init__(self, level):
        self.level = level

    def query(self, cmd):
        assert cmd == ":SOUR:LEV?"
        return str(self.level)


class _Source:
    """Fake spectrometer: line(s) set by the yoko voltage and drive gain, bounded uniform noise.

    ``sep(V)`` is the doublet separation (MHz, < 0.1 merges into one line) and ``amp(gain)``
    the line height; the noise is uniform in [-1, 1], so its MAD sigma is 0.74 and a spectrum
    without a line has a peak SNR of at most 1.35.
    """

    def __init__(self, yoko, sep, amp, seed=0):
        self.yoko, self.sep, self.amp = yoko, sep, amp
        self.rng = np.random.default_rng(seed)
        self.calls = []  # (voltage, gain) per spectrum
        self.ramps = []

    def ramp_to(self, yoko, v):
        assert yoko is self.yoko
        self.ramps.append(v)
        yoko.level = v

    def acquire_spec(self, soc, soccfg, cfg, outerFolder, qubit_freq_center, params):
        v, gain = self.yoko.level, int(params["spec_gain"])
        x = np.linspace(qubit_freq_center - 1.0, qubit_freq_center + 1.0, 101)
        amp = self.rng.uniform(-1.0, 1.0, x.size)
        sep, height = self.sep(v), self.amp(gain)
        if height:
            lines = [qubit_freq_center] if sep < 0.1 else [CENTER - sep / 2, CENTER + sep / 2]
            for f0 in lines:
                amp = amp + height / (1.0 + ((x - f0) / HWHM) ** 2)
        peak_info = dict(find_two_tone_peaks(x, amp), call=len(self.calls))
        self.calls.append((v, gain))
        return x, amp, np.zeros_like(x), amp, peak_info


def _run(monkeypatch, src, **overrides):
    monkeypatch.setattr(ac, "_acquire_spec", src.acquire_spec)
    monkeypatch.setattr(ac, "ramp_to", src.ramp_to)
    params = {
        "ss_accept_sep": 0.08,
        "ss_dV": 5e-4,
        "ss_voltage_min": 0.0,
        "ss_voltage_max": 0.010,
        "ss_max_tries": 200,
        "cd_period_mv": None,
        **overrides,
    }
    return find_sweet_spot(None, None, {}, "unused/", CENTER, 1, src.yoko, params)


def _grid(v):
    return round(v, 7)


def test_walk_measures_each_voltage_once_and_reacquires_at_best(monkeypatch):
    # always a resolved doublet, narrowest (0.3 MHz) at 3 mV: no voltage is accepted
    yoko = _Yoko(0.005)
    src = _Source(yoko, sep=lambda v: 0.3 + 100.0 * abs(v - 0.003), amp=lambda g: 20.0)
    qfreq, voltage, peak_info, log = _run(monkeypatch, src)

    walk = [_grid(v) for v, _ in src.calls[:-1]]
    grid = [_grid(k * 5e-4) for k in range(21)]
    assert sorted(walk) == grid  # one pass of [0, 10] mV, each voltage measured once
    assert len(src.calls) == 22  # 21 voltages + the re-acquisition (the old walk took 200)
    assert _grid(src.calls[-1][0]) == 0.003  # re-acquired at the best voltage
    assert voltage == pytest.approx(0.003) and yoko.level == pytest.approx(0.003)
    assert peak_info["call"] == 21  # the fresh spectrum, not the one stored during the walk
    assert peak_info["sweet_spot_ok"] is True and peak_info["snr"] >= 4.0
    assert peak_info["peak_sep"] == pytest.approx(0.3, abs=0.03)
    assert qfreq == pytest.approx(CENTER, abs=0.02)
    assert any("Every voltage in [vmin, vmax] measured" in line for line in log)


def test_max_tries_is_still_a_hard_cap(monkeypatch):
    yoko = _Yoko(0.005)
    src = _Source(yoko, sep=lambda v: 0.3 + 100.0 * abs(v - 0.003), amp=lambda g: 20.0)
    _, voltage, peak_info, _ = _run(monkeypatch, src, ss_max_tries=3)
    # start + 3 steps up (5.5, 6.0, 6.5 mV), then back to the best (the start) and re-acquire
    assert [_grid(v) for v, _ in src.calls] == [0.005, 0.0055, 0.006, 0.0065, 0.005]
    assert voltage == pytest.approx(0.005) and peak_info["call"] == 4


def test_noise_only_pass_returns_failure_flag(monkeypatch):
    yoko = _Yoko(0.005)
    src = _Source(yoko, sep=lambda v: 0.5, amp=lambda g: 0.0)  # no line at any gain
    qfreq, voltage, peak_info, log = _run(monkeypatch, src)

    gains = [g for _, g in src.calls]
    # Stage 1.5 gain raise at the start voltage (5 retries); no line showed at any gain, so
    # the walk goes back to spec_gain (no power-broadened walk at 19x the nominal gain)
    assert gains[:6] == [700, 1260, 2268, 4082, 7348, 13226]
    assert gains[6:] == [700] * 20 and len(src.calls) == 26
    assert any("the walk uses spec_gain=700" in line for line in log)
    assert peak_info["sweet_spot_ok"] is False and peak_info["snr"] < 4.0
    assert qfreq == CENTER  # not the argmax of the noise
    assert voltage == pytest.approx(0.005) and yoko.level == pytest.approx(0.005)
    assert src.ramps[-1] == pytest.approx(0.005)  # back at the start voltage
    assert any("sweet spot NOT found" in line for line in log)


def test_failed_reacquisition_returns_to_the_start_voltage(monkeypatch):
    # as the one-pass walk test, but the line is gone when the best voltage is re-measured
    yoko = _Yoko(0.005)
    src = _Source(yoko, sep=lambda v: 0.3 + 100.0 * abs(v - 0.003), amp=lambda g: 20.0)
    src.amp = lambda g: 0.0 if len(src.calls) == 21 else 20.0
    qfreq, voltage, peak_info, log = _run(monkeypatch, src)

    assert len(src.calls) == 22 and _grid(src.calls[-1][0]) == 0.003  # re-acquired at best
    assert peak_info["sweet_spot_ok"] is False
    assert qfreq == CENTER
    assert voltage == pytest.approx(0.005) and yoko.level == pytest.approx(0.005)
    assert src.ramps[-1] == pytest.approx(0.005)  # ramped back to the start voltage
    assert peak_info["call"] == 0  # the start spectrum, matching the returned voltage
    assert any("on re-acquiring at the best voltage" in line for line in log)


def test_strategy_a_keeps_the_start_voltage_as_a_candidate(monkeypatch):
    # cd_period 4 mV: the start doublet (0.6 MHz >= ss_search_df_trigger 0.5) triggers the
    # half-period jump to 7 mV, where it is wider (0.8 MHz); the start must stay the best
    # point and is re-measured
    yoko = _Yoko(0.005)
    src = _Source(yoko, sep=lambda v: 0.6 + 100.0 * abs(v - 0.005), amp=lambda g: 20.0)
    _, voltage, peak_info, _ = _run(monkeypatch, src, cd_period_mv=4.0)

    volts = [_grid(v) for v, _ in src.calls]
    assert volts[:2] == [0.005, 0.007]  # start, then the Strategy-A jump
    assert sorted(volts[:-1]) == [_grid(k * 5e-4) for k in range(21)]  # each once
    assert volts[-1] == 0.005  # re-acquired at the start voltage, the best one
    assert voltage == pytest.approx(0.005) and peak_info["sweet_spot_ok"] is True


def test_strategy_a_is_skipped_when_the_start_spectrum_is_gated(monkeypatch):
    # the start shows a resolved 0.6 MHz doublet (would trigger the jump) but below the gate
    yoko = _Yoko(0.005)
    src = _Source(yoko, sep=lambda v: 0.0 if abs(v - 0.0055) < 1e-9 else 0.6, amp=lambda g: 20.0)
    real_snr = ac._spec_peak_snr
    monkeypatch.setattr(
        ac,
        "_spec_peak_snr",
        lambda a, p: 1.0 if abs(yoko.level - 0.005) < 1e-9 else real_snr(a, p),
    )
    _, voltage, peak_info, _ = _run(monkeypatch, src, cd_period_mv=4.0, freqcal_auto_gain=False)
    # no half-period jump to 7 mV: the walk starts from the start voltage
    assert [_grid(v) for v, _ in src.calls] == [0.005, 0.0055]
    assert voltage == pytest.approx(0.0055) and peak_info["sweet_spot_ok"] is True


@pytest.mark.parametrize(
    "ok, sep, found, sep_mhz",
    [
        (True, None, True, None),  # accepted single line
        (True, 0.05, True, 0.05),  # accepted, below ss_accept_sep
        (True, 0.3, False, 0.3),  # best voltage, ss_accept_sep (0.08) never reached
        (False, None, False, None),  # failed the SNR gate
    ],
)
def test_auto_coherence_records_sweet_spot_found(tmp_path, monkeypatch, ok, sep, found, sep_mhz):
    """A complete run_auto_coherence keeps the Stage-1 sweet-spot record through the
    post-Stage-3 calibration rebuild, in the summary json and in the returned results."""

    def stage(ret=None):
        return lambda **kwargs: ret

    snr = 5.0 if ok else 1.2
    peak_info = {"peak_freqs": [CENTER], "peak_sep": sep, "snr": snr, "sweet_spot_ok": ok}
    monkeypatch.setattr(ac, "_stage_sweet_spot_search", stage((CENTER, 0.004, peak_info)))
    monkeypatch.setattr(ac, "_stage_amplitude_rabi", stage((1200, 0.05)))
    monkeypatch.setattr(ac, "_stage_singleshot_optimize", stage((1210, 605, 0.91, 12.5, 0.3)))
    for name in ("_stage_run_t1", "_stage_run_t2", "_stage_run_t2e"):
        monkeypatch.setattr(ac, name, stage())
    qubit_params = {
        "1": {
            "Readout": {"Frequency": 7000.0, "Gain": 800},
            "Qubit": {"Frequency": CENTER, "Gain": 1000, "sigma": 0.05, "flattop_length": None},
        }
    }
    results = ac._run_auto_coherence(
        soc=None,
        soccfg=None,
        config={},
        outerFolder=str(tmp_path) + "/",
        qubit_readout=1,
        qubit_params=qubit_params,
        yoko=None,
        auto_params={"calibrate_qubit_freq": False, "auto_readout_opt": False},
    )
    assert results["sweet_spot_found"] is found and results["sweet_spot_sep_mhz"] == sep_mhz
    folder = os.path.dirname(results["summary_file"])
    (js,) = [f for f in os.listdir(folder) if f.endswith(".json")]
    with open(os.path.join(folder, js)) as fh:
        summary = json.load(fh)
    assert summary["stage_reached"] == "complete"
    assert summary["calibration"]["sweet_spot_found"] is found
    assert summary["calibration"]["sweet_spot_sep_mhz"] == sep_mhz
    if sep_mhz is None:
        assert results["sweet_spot_sep_mhz"] is None
        assert summary["calibration"]["sweet_spot_sep_mhz"] is None
    assert summary["calibration"]["sweet_spot_voltage"] == 0.004


@pytest.mark.parametrize(
    "ok, sep, found, sep_mhz",
    [
        (True, None, True, None),  # accepted single line
        (True, 0.05, True, 0.05),  # accepted, below ss_accept_sep
        (True, 0.3, False, 0.3),  # best voltage, ss_accept_sep never reached
        (False, 0.6, False, None),  # failed the SNR gate: the start spectrum's sep is noise
    ],
)
def test_sweet_spot_record_separates_accepted_from_best(ok, sep, found, sep_mhz):
    pi = {"peak_freqs": [CENTER], "peak_sep": sep, "snr": 5.0, "sweet_spot_ok": ok}
    rec = ac._sweet_spot_record(pi, ac.AUTO_COHERENCE_PARAMS["ss_accept_sep"])
    assert rec == {"sweet_spot_found": found, "sweet_spot_sep_mhz": sep_mhz}


def test_noise_only_spectrum_is_not_accepted_without_yoko(monkeypatch):
    src = _Source(_Yoko(0.0), sep=lambda v: 0.5, amp=lambda g: 0.0)
    monkeypatch.setattr(ac, "_acquire_spec", src.acquire_spec)
    log = []
    params = {**ac.AUTO_COHERENCE_PARAMS, "freqcal_auto_gain": False}
    qfreq, voltage, peak_info = ac._stage_sweet_spot_search(
        None, None, {}, "unused/", CENTER, 1, params, None, log
    )
    assert peak_info["sweet_spot_ok"] is False and qfreq == CENTER and voltage is None
    assert len(src.calls) == 1


def test_weak_real_line_passes_after_gain_raise(monkeypatch):
    # a single line (at the sweet spot) that only clears the gate from spec_gain 2000 up
    yoko = _Yoko(0.005)
    src = _Source(yoko, sep=lambda v: 0.0, amp=lambda g: 8.0 if g >= 2000 else 1.0)
    qfreq, voltage, peak_info, _ = _run(monkeypatch, src)
    assert [g for _, g in src.calls] == [700, 1260, 2268]
    assert src.ramps == []  # accepted at the start voltage, no walk
    assert peak_info["sweet_spot_ok"] is True and peak_info["peak_sep"] is None
    assert voltage == pytest.approx(0.005) and qfreq == pytest.approx(CENTER, abs=0.02)


def test_walk_keeps_the_raised_gain_and_skips_gated_spectra(monkeypatch):
    # weak doublet, single line at 6 mV only; the walk runs at the gain the start settled on
    yoko = _Yoko(0.005)
    src = _Source(
        yoko,
        sep=lambda v: 0.0 if abs(v - 0.006) < 1e-9 else 0.4,
        amp=lambda g: 8.0 if g >= 2000 else 1.0,
    )
    _, voltage, peak_info, _ = _run(monkeypatch, src)
    assert [g for _, g in src.calls] == [700, 1260, 2268, 2268, 2268]
    assert voltage == pytest.approx(0.006) and peak_info["sweet_spot_ok"] is True


def test_gated_spectrum_never_becomes_best(monkeypatch):
    # the narrowest doublet (0.15 MHz at 3 mV) is below the SNR gate there: it is "no data"
    yoko = _Yoko(0.005)
    src = _Source(yoko, sep=lambda v: 0.3 + 100.0 * abs(v - 0.003), amp=lambda g: 20.0)
    src.sep = lambda v: 0.15 if abs(v - 0.003) < 1e-9 else 0.3 + 100.0 * abs(v - 0.003)
    real_snr = ac._spec_peak_snr
    monkeypatch.setattr(
        ac,
        "_spec_peak_snr",
        lambda a, p: 1.0 if abs(yoko.level - 0.003) < 1e-9 else real_snr(a, p),
    )
    _, voltage, peak_info, _ = _run(monkeypatch, src, freqcal_auto_gain=False)
    assert any(abs(v - 0.003) < 1e-9 for v, _ in src.calls)  # measured, then ignored
    assert voltage in (pytest.approx(0.0025), pytest.approx(0.0035))
    assert peak_info["sweet_spot_ok"] is True


def test_next_unvisited_voltage_covers_range_then_stops():
    visited = {_grid(0.002)}
    v, d, order = 0.002, +1, []
    while True:
        v, d = ac._next_unvisited_voltage(v, 1e-3, 0.0, 0.004, d, visited)
        if v is None:
            break
        visited.add(_grid(v))
        order.append(_grid(v))
    assert order == [0.003, 0.004, 0.001, 0.0]
    assert ac._next_unvisited_voltage(0.002, 1e-3, 0.002, 0.002, +1, set())[0] is None


def test_mrc_marks_cycle_not_verified_without_a_line(monkeypatch, tmp_path, capsys):
    """ModifiedRamsey_Control: sweet_spot_ok False -> no Ramsey, cycle not verified."""
    summaries = []

    def no_line(**kwargs):
        pki = {"peak_freqs": [CENTER], "peak_sep": None, "snr": 1.2, "sweet_spot_ok": False}
        return CENTER, 0.004, pki, []

    class _NoRamsey:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Ramsey run on an unverified sweet spot")

    monkeypatch.setattr(mr_runs, "find_sweet_spot", no_line)
    monkeypatch.setattr(mr_runs, "ModifiedRamsey", _NoRamsey)
    monkeypatch.setattr(mr_runs, "save_cycle_summary", lambda d, s: summaries.append(s))
    ctx = types.SimpleNamespace(
        outerFolder=str(tmp_path),
        yoko=types.SimpleNamespace(query=lambda cmd: "0.0"),
        working_config=dict,
        soc=None,
        soccfg=None,
        qubit_frequency_center=CENTER,
        Qubit_Readout=[1],
    )
    params = {
        "sweet_spot_max_df_mhz": 1e9,  # would accept any separation
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
    }
    mr_runs.run_modified_ramsey_control(ctx, params)
    (cycle,) = summaries[0]
    assert cycle["sweet_verified"] is False
    assert cycle["stage_failed"] == "sweet_spot_not_verified"
    out = capsys.readouterr().out
    assert (
        "sweet spot not verified (search failed the peak-SNR gate, start-voltage SNR 1.20)" in out
    )
