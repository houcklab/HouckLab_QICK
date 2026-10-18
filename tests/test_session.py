"""Session layer (qicklab.core.session): Session, connect, run_step, run, dry run, write-back.

Hardware-free: connect() runs the real build_context against the fakes of qicklab.core.fakes
(the regression harness's). The regime switch is pinned against the legacy helpers on the
frozen runner's own parameter dicts (tests/regression/fixtures/cstq03_legacy_params.py).
"""

import dataclasses
import json
import os
import re

import numpy as np
import pytest
import pyvisa

import qicklab.core.device as device_module
import qicklab.core.session as session_module
from devices.CSTQ03 import DEVICE
from qicklab.core import context as context_module
from qicklab.core import fakes, io
from qicklab.core.config import rebuild_singleshot_config
from qicklab.core.context import build_context
from qicklab.core.device import ParityParams, Qubit, Readout, ReadoutWindow, Setup, source
from qicklab.core.session import GROUPS, REGIMES, Session, Step, connect, run, run_step
from qicklab.runs import groups as G
from qicklab.runs import recipes as R
from tests.regression import capture
from tests.regression.fixtures import cstq03_legacy_params as F

pytestmark = pytest.mark.filterwarnings("ignore:CSTQ03")  # Device.validate's soft warnings


@pytest.fixture
def fake_board(monkeypatch):
    """build_context's proxy factory and pyvisa replaced by the fakes."""
    monkeypatch.setattr(context_module, "makeProxy", fakes.fake_make_proxy)
    monkeypatch.setattr(pyvisa, "ResourceManager", fakes.FakeResourceManager)


@pytest.fixture
def device(tmp_path):
    return dataclasses.replace(DEVICE, data_root=str(tmp_path / "data").replace("\\", "/"))


def _runner_session(ns, device=DEVICE):
    """The Session the frozen runner's sections 1-2 describe."""
    groups = {g: G.BUILDERS[g](**F.group_kwargs(g, ns[d])[0]) for d, g in F.GROUP_OF_DICT.items()}
    return Session(
        device,
        qubit_readout=ns["Qubit_Readout"],
        qubit_pulse=ns["Qubit_Pulse"],
        bias_v=ns["start_voltage"],
        yoko_fixed=ns["yoko_fixed"],
        **groups,
    )


def _recorder(regime="A", needs=(), params=None, name="probe"):
    seen = []

    def fn(ctx, *args):
        seen.append((ctx.config, args))
        return len(seen)

    return Step(name, fn, regime, needs=needs, params=params or {}), seen


def _with_fn(step, seen):
    def fn(ctx, *args):
        seen.append(args)

    return dataclasses.replace(step, fn=fn)


# Session


def test_library_groups_by_default_and_given_groups_are_copied():
    session = Session(DEVICE, qubit_readout=5, qubit_pulse=5)
    assert {g: getattr(session, g) for g in GROUPS} == {g: G.BUILDERS[g]() for g in GROUPS}
    mine = G.coherence(relax_delay=1234)
    session = Session(DEVICE, 5, 5, coherence=mine)
    session.coherence["relax_delay"] = 1
    assert mine["relax_delay"] == 1234
    assert session.groups()["coherence"] is not session.coherence


def test_session_rejects_unknown_qubit_and_non_dict_group():
    with pytest.raises(KeyError, match="qubit_pulse=9"):
        Session(DEVICE, 5, 9)
    with pytest.raises(TypeError, match="spec"):
        Session(DEVICE, 5, 5, spec=G.spec)
    with pytest.raises(dataclasses.FrozenInstanceError):
        Session(DEVICE, 5, 5).bias_v = 1.0


def test_single_shot_group_takes_the_readout_qubits_window_and_the_pulse_qubit():
    ss = Session(DEVICE, 5, 4).groups()["single_shot"]
    assert (ss["Readout_Time"], ss["ADC_Offset"], ss["Qubit_Pulse"]) == (15, 0.3, [4])
    assert list(ss) == [legacy for legacy, _ in G.KEYS["single_shot"]]  # legacy key order
    own = ReadoutWindow(5, 0.5)
    dev = DEVICE.with_qubit(5, readout=dataclasses.replace(DEVICE.qubits[5].readout, ss_window=own))
    ss = Session(dev, 5, 4).groups()["single_shot"]
    assert (ss["Readout_Time"], ss["ADC_Offset"]) == (5, 0.5)
    ss = Session(dev, 5, 4, single_shot=G.single_shot(readout_time=7, qubit_pulse=[1, 2]))
    ss = ss.groups()["single_shot"]
    assert (ss["Readout_Time"], ss["ADC_Offset"], ss["Qubit_Pulse"]) == (7, 0.5, [1, 2])
    assert (
        Session(dev, 5, 4).qubit() is dev.qubits[4] and Session(dev, 5, 4).qubit(5) is dev.qubits[5]
    )


# connect and the regime switch, pinned against the legacy call shapes


def test_connect_is_the_runners_build_context_call(fake_board):
    ns = F.namespace()
    args, kwargs = F.build_context_call(ns)
    legacy = build_context(*args, **kwargs)
    ctx = connect(_runner_session(ns))
    assert ctx.config == legacy.config and list(ctx.config) == list(legacy.config)
    assert ctx.Qubit_Parameters == legacy.Qubit_Parameters
    for name in ("outerFolder", "Qubit_Readout", "Qubit_Pulse", "start_voltage", "qubit_gain"):
        assert getattr(ctx, name) == getattr(legacy, name), name
    assert ctx.regime == "A" and ctx.session is not None and io.session()["device"] == "CSTQ03"


@pytest.mark.parametrize(
    "setup",
    [Setup(board_overrides={"res_ch": 2}), Setup(ff_qubits={})],
    ids=["board_overrides", "ff_qubits"],
)
def test_connect_refuses_setup_values_build_context_does_not_apply(fake_board, setup):
    fakes.STATE.yoko.append("MARK")
    with pytest.raises(NotImplementedError, match="board_overrides / ff_qubits"):
        connect(Session(dataclasses.replace(DEVICE, setup=setup), 5, 5))
    assert fakes.STATE.yoko[-1] == "MARK"  # refused before anything is opened


def test_connect_warns_that_interactive_plots_has_no_effect_yet(fake_board):
    with pytest.warns(UserWarning, match=r"interactive_plots=True\) has no effect"):
        ctx = connect(Session(DEVICE, 5, 5, interactive_plots=True))
    assert ctx.regime == "A"


def test_connect_closes_the_yoko_when_validate_raises(fake_board, monkeypatch):
    def refuse(self, soccfg=None, **kwargs):
        assert soccfg is not None  # validated against the connected board
        raise ValueError("CSTQ03: invented hard error")

    monkeypatch.setattr(device_module.Device, "validate", refuse)
    fakes.STATE.yoko.append("MARK")
    with pytest.raises(ValueError, match="invented hard error"):
        connect(Session(DEVICE, 5, 5))
    log = fakes.STATE.yoko
    assert log[-1] == "CLOSE" and any(e.startswith("OPEN") for e in log[log.index("MARK") :])


def test_regime_switches_reproduce_rebuild_and_interleave(fake_board):
    ns = F.namespace()
    args, kwargs = F.build_context_call(ns)
    legacy = build_context(*args, **kwargs)
    legacy.config["pulse_freq"], legacy.config["res_phase"] = 1234.5, 7
    rebuild_singleshot_config(legacy, ns["SS_params"])  # the runner's unconditional switch

    ctx = connect(_runner_session(ns))
    regime_a = ctx.config
    regime_a["pulse_freq"], regime_a["res_phase"] = 1234.5, 7  # transmission_fit / ARV carry-overs
    probe_b, seen = _recorder("B")
    probe_a, _ = _recorder("A")
    probe_a = dataclasses.replace(probe_a, fn=probe_b.fn)

    run_step(ctx, probe_b)  # A -> B: carry-overs dropped, exactly the legacy rebuild
    first_b = seen[-1][0]
    assert first_b == legacy.config and list(first_b) == list(legacy.config)
    assert first_b["pulse_freq"] == ctx.resonator_frequency_center and first_b["res_phase"] == 0
    first_b["res_phase"] = 3  # a regime-B carry-over
    run_step(ctx, probe_b)  # same regime: no rebuild
    assert seen[-1][0] is first_b
    run_step(ctx, probe_a)  # B -> A: the held regime-A object, carry-overs intact
    assert seen[-1][0] is regime_a and regime_a["pulse_freq"] == 1234.5
    run_step(ctx, probe_b)  # A -> B again: a fresh rebuild
    assert seen[-1][0] is not first_b and seen[-1][0] == legacy.config


def test_run_step_needs_a_connected_ctx_and_a_step(fake_board):
    probe, _ = _recorder()
    with pytest.raises(ValueError, match="connect"):
        run_step(object(), probe)
    ctx = connect(Session(DEVICE, 5, 5))
    with pytest.raises(TypeError, match="Step"):
        run_step(ctx, print)


# precedence, resolution and logging through run_step


def test_precedence_library_session_step(fake_board):
    seen = []
    for session, step, expected in (
        (Session(DEVICE, 5, 5), R.t1(), G.coherence()["relax_delay"]),
        (Session(DEVICE, 5, 5, coherence=G.coherence(relax_delay=1234)), R.t1(), 1234),
        (
            Session(DEVICE, 5, 5, coherence=G.coherence(relax_delay=1234)),
            R.t1(relax_delay=5000),
            5000,
        ),
    ):
        run_step(connect(session), _with_fn(step, seen))
        (coherence,) = seen[-1]
        assert coherence["relax_delay"] == expected
        assert coherence["T1_step"] == session.coherence["T1_step"]


def test_spec_gain_and_parity_resolve_from_the_pulse_qubit(fake_board):
    seen = []
    for spec_gain, expected in ((None, 800), (750, 750)):
        dev = DEVICE.with_qubit(5, spec_gain=spec_gain)
        run_step(connect(Session(dev, 5, 5)), _with_fn(R.two_tone_spec(), seen))
        assert seen[-1][0]["gain"] == expected and seen[-1][0]["qubit_gain"] == 1000
    dev = DEVICE.with_qubit(5, parity=ParityParams(df_mhz=0.7, f_upper_mhz=2651.2))
    run_step(connect(Session(dev, 4, 5)), _with_fn(R.charge_dispersion_quasicw(), seen))
    assert seen[-1][0]["probe_freq"] == 2651.2


def test_precedence_of_a_device_value_library_qubit_group_step(fake_board):
    """spec gain: library 800 < Qubit.spec_gain < session spec group < step override."""
    seen = []
    for spec_gain, group_gain, step_gain, expected in (
        (None, None, None, 800),
        (750, None, None, 750),
        (None, 900, None, 900),
        (750, 900, None, 900),
        (750, 900, 950, 950),
        (750, None, 950, 950),
    ):
        dev = DEVICE.with_qubit(5, spec_gain=spec_gain)
        session = Session(dev, 5, 5, spec=G.spec(gain=group_gain))
        run_step(connect(session), _with_fn(R.two_tone_spec(gain=step_gain), seen))
        assert seen[-1][0]["gain"] == expected, (spec_gain, group_gain, step_gain)
        assert session.spec["gain"] == group_gain  # the session group itself is not filled in


def _swapper(regime, error=None, name="swapper"):
    """A Step whose fn replaces ctx.config (and optionally raises) instead of writing into it."""

    def fn(ctx, *args):
        ctx.config = {"swapped": True}
        if error is not None:
            raise error

    return Step(name, fn, regime)


@pytest.mark.parametrize("regime", REGIMES)
def test_a_step_that_leaves_ctx_config_replaced_gets_its_config_back(fake_board, capsys, regime):
    ctx = connect(Session(DEVICE, 5, 5))
    run_step(ctx, _recorder(regime)[0])  # enter the regime under test
    handed, config_a = ctx.config, ctx.regime_a_config or ctx.config
    capsys.readouterr()
    run_step(ctx, _swapper(regime))
    out = capsys.readouterr().out
    assert f"swapper left ctx.config replaced; the regime-{regime} config it was handed" in out
    assert ctx.config is handed and ctx.regime == regime
    probe, seen = _recorder(regime)
    run_step(ctx, probe)
    assert seen[-1][0] is handed  # the next step of that regime runs on the handed config
    run_step(ctx, _recorder("B" if regime == "A" else "A")[0])
    run_step(ctx, _recorder("A")[0])
    assert ctx.config is config_a  # the regime-A object survives the later switches
    # a step that only writes into the config it was handed is left alone
    capsys.readouterr()
    run_step(ctx, _recorder("A")[0])
    assert ctx.config is config_a and "left ctx.config replaced" not in capsys.readouterr().out


@pytest.mark.parametrize("regime", REGIMES)
def test_the_config_guard_restores_on_a_raise_and_keeps_the_error(fake_board, capsys, regime):
    ctx = connect(Session(DEVICE, 5, 5))
    run_step(ctx, _recorder(regime)[0])
    handed = ctx.config
    capsys.readouterr()
    with pytest.raises(RuntimeError, match="orig") as raised:
        run_step(ctx, _swapper(regime, RuntimeError("orig")))
    assert raised.value.__context__ is None  # the guard raised nothing of its own
    assert "swapper left ctx.config replaced" in capsys.readouterr().out
    assert ctx.config is handed and ctx.regime == regime and "swapped" not in ctx.config


def test_interleaved_coherence_with_nothing_enabled_leaves_regime_a(fake_board, capsys):
    """run_interleaved_coherence with nothing enabled: the session stays on its regime-A config.

    Today its early return skips its restoring finally (legacy bug, harmless in the legacy
    runner where the regime-B rebuild came right after) and the guard puts the config back;
    once that bug is fixed the guard has nothing to do. Either way the end state is the same.
    """
    ctx = connect(Session(DEVICE, 5, 5))
    config_a = ctx.config
    nothing = R.interleaved_coherence(undriven_single_shot=False, t1=False, t2r=False)
    run_step(ctx, nothing)
    assert "no experiments enabled" in capsys.readouterr().out
    assert ctx.config is config_a and ctx.regime == "A"
    t1, seen = _recorder("A", needs=("coherence",), name="t1")
    run_step(ctx, t1)
    assert seen[-1][0] is config_a  # not the single-shot config (its qubit_gain is the pi gain)
    run_step(ctx, _recorder("B")[0])
    assert ctx.regime_a_config is config_a  # the A -> B switch held the regime-A object


def test_run_step_logs_the_effective_parameters(fake_board, capsys):
    ctx = connect(Session(DEVICE, 5, 5, coherence=G.coherence(relax_delay=1234)))
    capsys.readouterr()
    run_step(ctx, _with_fn(R.t1(relax_delay=5000), []))
    run_step(ctx, _with_fn(R.two_tone_spec(), []))
    out = capsys.readouterr().out
    assert "[session] t1 (regime A)" in out and "[session] two_tone_spec (regime A)" in out
    assert "'relax_delay': 5000" in out and "'T1_step': 5" in out  # group values, not step.params
    assert "'gain': 800" in out  # the resolved spec gain, None in the step and the group


def test_regime_switch_is_logged(fake_board, capsys):
    ctx = connect(Session(DEVICE, 5, 5))
    run_step(ctx, _recorder("B")[0])
    run_step(ctx, _recorder("A")[0])
    out = capsys.readouterr().out
    assert "regime A -> B" in out and "regime B -> A" in out
    # the A -> B line shows the group the regime-B config was built from
    assert "single_shot = {'Shots': 1000" in out and "'Readout_Time': 15" in out


def test_single_shot_pi2_override_reaches_the_config_for_that_step(fake_board, capsys):
    ctx = connect(Session(DEVICE, 5, 5, single_shot=G.single_shot(pi2_ss=False)))
    seen = []

    def fn(ctx, ss):
        seen.append((ss["pi2_SS"], ctx.working_config()["pi2_SS"]))
        if ss.get("number_of_pulses") == 0:
            raise RuntimeError("boom")

    run_step(ctx, dataclasses.replace(R.single_shot(), fn=fn))
    assert "config pi2_SS" not in capsys.readouterr().out  # no override: nothing changed
    run_step(ctx, dataclasses.replace(R.single_shot(pi2_ss=True), fn=fn))
    assert "config pi2_SS = True for this step" in capsys.readouterr().out
    assert seen == [(False, False), (True, True)]  # the saved cfg records the pulse played
    assert ctx.config["pi2_SS"] is False  # put back for the later steps
    with pytest.raises(RuntimeError, match="boom"):
        run_step(ctx, dataclasses.replace(R.single_shot(pi2_ss=True, number_of_pulses=0), fn=fn))
    assert seen[-1] == (True, True) and ctx.config["pi2_SS"] is False  # restored on a raise


# run


def test_run_runs_in_order_and_closes_the_yoko(fake_board, device, capsys):
    a, seen = _recorder("A", name="first")
    b = dataclasses.replace(a, name="second", regime="B")
    assert run(Session(device, 5, 5), [a, b, a]) == [1, 2, 3]
    assert fakes.STATE.yoko[-1] == "CLOSE"
    out = capsys.readouterr().out
    assert "3 step(s): first, second, first" in out
    assert re.search(r"step 1/3: first.*step 2/3: second.*step 3/3: first", out, re.S)


def test_run_closes_the_yoko_when_a_step_raises(fake_board, device):
    def boom(ctx):
        raise RuntimeError("boom")

    fakes.STATE.yoko.append("MARK")
    with pytest.raises(RuntimeError, match="boom"):
        run(Session(device, 5, 5), [Step("boom", boom, "A")])
    log = fakes.STATE.yoko
    assert log[-1] == "CLOSE" and "MARK" in log[log.index("MARK") :]


def test_run_rejects_a_plan_entry_that_is_not_a_step():
    with pytest.raises(TypeError, match=r"PLAN\[1\]"):
        run(Session(DEVICE, 5, 5), [R.t1(), R.t1], dry_run=True)


# dry run


def _no_real_hardware(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("dry run touched the real hardware factory")

    monkeypatch.setattr(context_module, "makeProxy", refuse)
    monkeypatch.setattr(pyvisa, "ResourceManager", refuse)


def test_dry_run_compiles_every_step_and_writes_nothing(monkeypatch, tmp_path, capsys):
    _no_real_hardware(monkeypatch)
    temp = tmp_path / "tmp"
    temp.mkdir()
    monkeypatch.setattr("tempfile.tempdir", str(temp))
    real_root = tmp_path / "real"
    dev = dataclasses.replace(DEVICE, data_root=str(real_root))
    before = io.session()
    plan = [R.transmission_fit(), R.t1(), R.single_shot(), R.t1(relax_delay=5000)]
    report = run(Session(dev, 5, 5), plan, dry_run=True)
    assert [e["step"] for e in report] == [s.name for s in plan]
    assert all(e["status"] == "ok" and e["programs"] > 0 for e in report), report
    assert not real_root.exists() and list(temp.iterdir()) == []  # temp root removed
    assert io.session() == before  # the provenance session record is restored
    assert context_module.makeProxy.__name__ == "refuse"  # patches undone
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "regime A -> B" in out and "'relax_delay': 5000" in out


def test_dry_run_reports_failures_and_goes_on(monkeypatch, tmp_path):
    _no_real_hardware(monkeypatch)
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    plan = [R.t1(repetitions=2), R.charge_dispersion_ramsey(), R.t1()]
    with pytest.raises(RuntimeError, match=r"1 step\(s\) failed: charge_dispersion_ramsey"):
        run(Session(DEVICE, 5, 5), plan, dry_run=True)
    assert list(tmp_path.iterdir()) == []


def test_dry_run_of_zero_span_parity_with_a_given_doublet(monkeypatch, tmp_path):
    # the fake spectroscopy resolves no doublet: the documented offline form skips the search
    _no_real_hardware(monkeypatch)
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    step = R.zero_span_parity(
        recalibrate_parity_freqs=False,
        parity_freqs_cached={"lower_peak_MHz": 2649.0, "higher_peak_MHz": 2651.7},
    )
    (entry,) = run(Session(DEVICE, 5, 5), [step], dry_run=True)
    assert entry["status"] == "ok" and entry["programs"] > 1, entry
    assert list(tmp_path.iterdir()) == []


def test_dry_run_compiles_every_stage_of_multi_stage_steps(monkeypatch, tmp_path):
    # repeats of one experiment are not cut: the stages after a calibration loop compile too
    _no_real_hardware(monkeypatch)
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    auto = R.auto_coherence(  # the runner's skip, smaller loops (same stages, shorter test)
        skip_sweet_spot_search=True,
        rabi_max_sigma_retries=1,
        readout_length_pts=2,
        adc_offset_pts=2,
        ss_gain_pts=3,
        ss_max_scan_expansions=0,
    )
    arv, ac = run(Session(DEVICE, 5, 5), [R.active_reset_verify(), auto], dry_run=True)
    assert arv["status"] == "ok" and ac["status"] == "ok", (arv, ac)
    assert arv["built"]["SingleShotProgramFFMUX/SingleShot_MRCalib"] == 3  # separator, +, -
    assert arv["built"]["ActiveResetVerify/ActiveResetVerify"] >= 1
    stages = ("auto-AmplitudeRabi", "auto-ReadoutOpt", "auto-SingleShot")
    assert all(any(k.endswith("/" + s) for k in ac["built"]) for s in stages), ac["built"]
    assert ac["built"]["SingleShotProgramFFMUX/auto-ReadoutOpt"] > 3  # a loop, not cut
    for kind in ("T1FF/auto-T1", "T2R/auto-T2", "T2EMUX/auto-T2E"):
        assert ac["built"][kind] == 1, ac["built"]
    assert list(tmp_path.iterdir()) == []


def test_dry_run_guards_report_an_incomplete_step(monkeypatch, tmp_path, capsys):
    _no_real_hardware(monkeypatch)
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    session = Session(DEVICE, 5, 5)
    monkeypatch.setattr(session_module, "DRY_RUN_MAX_REPEATS", 2)  # consecutive repeats
    first, second = run(session, [R.t1(repetitions=5), R.t1()], dry_run=True)
    assert first["status"].startswith("INCOMPLETE") and first["experiments"] == 4
    assert "3 builds in a row" in first["status"] and "not compiled" in first["status"]
    assert second["status"] == "ok" and second["experiments"] == 1  # the guards are per step
    out = capsys.readouterr().out
    assert "dry run INCOMPLETE for t1" in out and "built: T1FF/T1 x4" in out
    monkeypatch.setattr(session_module, "DRY_RUN_MAX_REPEATS", 40)
    monkeypatch.setattr(session_module, "DRY_RUN_MAX_EXPERIMENTS", 3)  # builds in all
    (entry,) = run(session, [R.t1(repetitions=5)], dry_run=True)
    assert (
        entry["status"].startswith("INCOMPLETE (3 experiments built") and entry["experiments"] == 3
    )


# fakes moved out of the harness


def test_harness_uses_the_core_fakes():
    for name in ("FakeSoc", "FakeSocCfg", "FakeYoko", "FakeResourceManager", "STATE", "BOARDS"):
        assert getattr(capture, name) is getattr(fakes, name), name
    capture.set_board("B")
    try:
        assert fakes.current_board() == "B" and fakes.FakeSocCfg()["board"] == "synthetic-B"
    finally:
        capture.set_board("A")


# calibration write-back


def _paste_line(out):
    line = [ln for ln in out.splitlines() if re.match(r"\s+\d+: Qubit\(", ln)][-1]
    q, text = line.strip().split(": ", 1)
    return int(q), eval(text.rstrip(","), vars(device_module))


def test_record_calibration_appends_and_prints_a_paste_ready_line(device, capsys):
    new = io.record_calibration(device, 5, step="amplitude_rabi", gain=np.int64(4300))
    io.record_calibration(device, 5, readout_freq=np.float64(7095.41), t1_us=55.0)
    lines = open(io.qubit_file(device, 5, io.CALIBRATIONS_FILE)).read().splitlines()
    first, second = (json.loads(ln) for ln in lines)
    assert first["values"] == {"gain": 4300} and first["step"] == "amplitude_rabi"
    assert (first["device"], first["cooldown"], first["qubit"]) == ("CSTQ03", "2026-10-01", 5)
    assert second["values"] == {"readout_freq": 7095.41, "t1_us": 55.0} and second["step"] is None
    q, pasted = _paste_line(capsys.readouterr().out)
    assert q == 5 and pasted == dataclasses.replace(
        device.qubits[5],
        readout=dataclasses.replace(device.qubits[5].readout, freq=7095.41),
        t1_us=55.0,
    )
    assert new.gain == 4300 and type(new.gain) is int
    assert device.qubits[5].gain == 4200  # the device itself is untouched


def test_record_calibration_parity_and_rejections(device, capsys):
    io.record_calibration(device, 2, parity_f_upper_mhz=3755.0, parity_df_mhz=0.6)
    _, pasted = _paste_line(capsys.readouterr().out)
    assert pasted.parity == ParityParams(df_mhz=0.6, f_upper_mhz=3755.0)
    new = io.record_calibration(device, 2, parity_df_mhz=0.6)  # no ParityParams to complete
    assert new.parity is None and "no ParityParams" in capsys.readouterr().out
    path = io.qubit_file(device, 3, io.CALIBRATIONS_FILE)
    with pytest.raises(TypeError, match="pi_gain"):
        io.record_calibration(device, 3, pi_gain=1)
    with pytest.raises(KeyError):
        io.record_calibration(device, 9, gain=1)
    assert not os.path.exists(path)


def test_source_omits_defaults_and_round_trips():
    qb = Qubit(freq=1.5, gain=10, sigma=0.1, readout=Readout(freq=7000.0, gain=5), notes="x")
    assert source(qb) == (
        "Qubit(freq=1.5, gain=10, sigma=0.1, readout=Readout(freq=7000.0, gain=5), notes='x')"
    )
    for q in DEVICE.qubits.values():
        assert eval(source(q), vars(device_module)) == q


# zero-span cache


def _fake_zsp(recalibrated):
    def fn(ctx, p):
        recalibrated.append({k: dict(p[k]) for k in io.ZSP_CACHED})
        if p["ZSP_RecalibrateParityFreqs"]:
            p["ZSP_ParityFreqs_Cached"].update(lower_peak_MHz=2650.0, higher_peak_MHz=2650.8)
        if p["ZSP_RecalibrateSeparator"]:
            p["ZSP_Separator_Cached"].update(
                g_center=np.array([1.0, 2.0]),
                e_center=np.array([3.0, 4.0]),
                normal=np.array([2.0, 2.0]),
                midpoint=np.array([2.0, 3.0]),
            )

    return fn


def test_transmission_steps_record_a_carried_readout_frequency(fake_board, device, capsys):
    ctx = connect(Session(device, 4, 5))  # the resonator belongs to the readout qubit
    path = io.qubit_file(device, 4, io.CALIBRATIONS_FILE)

    def gate(new):
        def fn(ctx, params):
            if new is not None:
                ctx.config["pulse_freq"] = new

        return fn

    run_step(ctx, dataclasses.replace(R.transmission_fit(), fn=gate(None)))  # gate refused
    assert not os.path.exists(path)
    run_step(ctx, dataclasses.replace(R.transmission_fit(), fn=gate(np.float64(6900.123))))
    run_step(ctx, dataclasses.replace(R.transmission_sweep(), fn=gate(6900.5)))
    first, second = (json.loads(ln) for ln in open(path))
    assert (first["step"], first["values"]) == ("transmission_fit", {"readout_freq": 6900.123})
    assert (second["step"], second["values"]) == ("transmission_sweep", {"readout_freq": 6900.5})
    q, pasted = _paste_line(capsys.readouterr().out)
    assert q == 4 and pasted.readout.freq == 6900.5
    assert pasted.readout.gain == device.qubits[4].readout.gain

    ctx.config["cavity_LO"] = 6000.0  # pulse_freq is then an IF: printed, not recorded
    run_step(ctx, dataclasses.replace(R.transmission_fit(), fn=gate(900.0)))
    assert "is an IF" in capsys.readouterr().out and len(open(path).readlines()) == 2
    run_step(ctx, dataclasses.replace(R.t1(), fn=lambda ctx, c: gate(1.0)(ctx, c)))
    assert len(open(path).readlines()) == 2  # only the transmission steps record


def test_zsp_cache_round_trip(device):
    sep = {"g_center": np.array([1.0, 2.0]), "e_center": None, "normal": None, "midpoint": None}
    path = io.write_zsp_cache(device, 5, {"lower_peak_MHz": 1.0}, sep, qubit_readout=5)
    assert path == f"{device.data_root}/Q5/zsp_cache.json"
    record = io.read_zsp_cache(device, 5)
    assert record["qubit_readout"] == 5 and record["ZSP_ParityFreqs_Cached"] == {
        "lower_peak_MHz": 1.0
    }
    assert np.array_equal(record["ZSP_Separator_Cached"]["g_center"], [1.0, 2.0])
    assert io.read_zsp_cache(device, 4) is None
    os.makedirs(f"{device.data_root}/Q4")
    with open(io.zsp_cache_path(device, 4), "w") as f:
        f.write("{not json")
    assert io.read_zsp_cache(device, 4) is None


def test_zero_span_step_writes_and_reuses_the_cache(fake_board, device, capsys):
    ctx = connect(Session(device, 5, 5))
    seen = []
    step = dataclasses.replace(R.zero_span_parity(), fn=_fake_zsp(seen))
    run_step(ctx, step)
    record = io.read_zsp_cache(device, 5)
    assert record["ZSP_ParityFreqs_Cached"]["higher_peak_MHz"] == 2650.8
    assert (record["qubit_readout"], record["qubit_pulse"]) == (5, 5)
    (cal,) = (json.loads(ln) for ln in open(io.qubit_file(device, 5, io.CALIBRATIONS_FILE)))
    assert cal["step"] == "zero_span_parity"
    assert cal["values"]["parity_f_upper_mhz"] == 2650.8
    assert cal["values"]["parity_df_mhz"] == pytest.approx(0.8)

    cached = R.zero_span_parity(
        recalibrate_parity_freqs=False,
        recalibrate_separator=False,
        parity_freqs_cached={"lower_peak_MHz": 1.0},  # an explicit value wins over the cache
    )
    run_step(ctx, dataclasses.replace(cached, fn=_fake_zsp(seen)))
    parity, separator = seen[-1]["ZSP_ParityFreqs_Cached"], seen[-1]["ZSP_Separator_Cached"]
    assert (parity["lower_peak_MHz"], parity["higher_peak_MHz"]) == (1.0, 2650.8)
    assert np.array_equal(separator["midpoint"], [2.0, 3.0])
    assert "[zsp cache]" in capsys.readouterr().out

    other = connect(Session(device, 4, 5))  # another readout qubit: not this cache
    run_step(other, dataclasses.replace(R.zero_span_parity(), fn=_fake_zsp(seen)))
    assert seen[-1]["ZSP_ParityFreqs_Cached"]["higher_peak_MHz"] is None


def test_device_parity_wins_over_the_cache(fake_board, device):
    io.write_zsp_cache(
        device,
        5,
        {"lower_peak_MHz": 1.0, "higher_peak_MHz": 2.0, "which_to_park": "lower"},
        {"g_center": None, "e_center": None, "normal": None, "midpoint": None},
        qubit_readout=5,
        qubit_pulse=5,
    )
    dev = device.with_qubit(5, parity=ParityParams(df_mhz=0.5, f_upper_mhz=2651.0))
    seen = []
    step = R.zero_span_parity(recalibrate_parity_freqs=False, recalibrate_separator=False)
    run_step(connect(Session(dev, 5, 5)), dataclasses.replace(step, fn=_fake_zsp(seen)))
    parity = seen[-1]["ZSP_ParityFreqs_Cached"]
    assert (parity["lower_peak_MHz"], parity["higher_peak_MHz"]) == (2650.5, 2651.0)
