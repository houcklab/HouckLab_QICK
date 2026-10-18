"""Session layer: `Session`, the `Step` a PLAN is made of, `run`, `connect`, `run_step`.

`qicklab.runs.recipes` builds Steps; `qicklab.runs.groups` builds the shared group dicts and
registers their library defaults here (core never imports runs). Guide:
docs/running_a_session.md.
"""

import builtins
import contextlib
import copy
import dataclasses
import os
import pprint
import shutil
import tempfile
import time
import traceback
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import matplotlib.pyplot as plt
import pyvisa

from qicklab.core import context as context_module
from qicklab.core import fakes, io
from qicklab.core.config import rebuild_singleshot_config
from qicklab.core.context import build_context
from qicklab.core.experiment import ExperimentClass
from qicklab.hardware import yoko as yoko_module

# session-wide parameter groups (qicklab.runs.groups), shared by every step that names them
GROUPS = ("transmission", "spec", "charge", "tones", "coherence", "echo", "single_shot")
REGIMES = ("A", "B")


@dataclass(frozen=True)
class Step:
    """One PLAN entry: `fn(ctx, *step.arguments(groups, qubit))`.

    `needs` lists fn's positional slots after ctx, in order. A slot named in GROUPS is that
    session group updated with `params[slot]` (the step's overrides); any other slot is
    `params[slot]`, the step's own legacy-keyed value. `resolve(params, qubit)` fills the
    device-dependent values (None) from the pulse qubit; `fill_groups(groups, qubit)` fills
    the group values left at None (recipes pass qicklab.runs.groups.resolve; core cannot
    import runs). Both run inside `arguments`.
    """

    name: str
    fn: Callable
    regime: str
    needs: tuple = ()
    params: dict = field(default_factory=dict, hash=False)
    resolve: Callable | None = field(default=None, compare=False, repr=False)
    fill_groups: Callable | None = field(default=None, compare=False, repr=False)

    def __post_init__(self):
        if self.regime not in REGIMES:
            raise ValueError(
                f"step {self.name}: regime must be one of {REGIMES}, got {self.regime!r}"
            )
        object.__setattr__(self, "needs", tuple(self.needs))
        missing = [s for s in self.needs if s not in GROUPS and s not in self.params]
        if missing:
            raise ValueError(f"step {self.name}: no params for its own slots {missing}")

    def arguments(self, groups, qubit=None):
        """fn's positional arguments after ctx: resolved own slots, group | override dicts.

        `groups` maps group name -> dict; `qubit` is the pulse qubit (`Device.qubits[q]`) or
        None. Own-slot values are passed as the resolver returns them (by identity when it
        leaves them unchanged); a group slot is always a fresh dict: session group, then the
        step's overrides, then `fill_groups` on what is still None (so library value <
        Qubit attribute < session group < step override).
        """
        params = self.resolve(self.params, qubit) if self.resolve is not None else self.params
        args = []
        for slot in self.needs:
            if slot in GROUPS:
                if not isinstance(groups.get(slot), Mapping):
                    raise KeyError(f"step {self.name} needs the session group {slot!r}")
                merged = {**groups[slot], **params.get(slot, {})}
                if self.fill_groups is not None:
                    merged = self.fill_groups({slot: merged}, qubit)[slot]
                args.append(merged)
            else:
                args.append(params[slot])
        return args


# group name -> zero-argument builder of its library default; qicklab.runs.groups fills it
_GROUP_BUILDERS = {}


def register_group_builders(builders):
    """Register the library default of each session group (qicklab.runs.groups does this)."""
    unknown = sorted(set(builders) - set(GROUPS))
    if unknown:
        raise KeyError(f"not session groups: {unknown}; groups are {GROUPS}")
    _GROUP_BUILDERS.update(builders)


def _library_group(name):
    if name not in _GROUP_BUILDERS:
        raise RuntimeError(
            f"Session({name}=None): the library groups are registered by qicklab.runs.groups; "
            f"import it (from qicklab.runs import groups as G) or pass {name}= explicitly"
        )
    return _GROUP_BUILDERS[name]()


@dataclass(frozen=True)
class Session:
    """Device, selected qubits, bias and the shared groups every step of a PLAN reads.

    A group left at None is its library default (`G.<group>()`); a given group is copied, so
    the caller's dict is never written to. docs/running_a_session.md#session-fields
    """

    device: object
    qubit_readout: int
    qubit_pulse: int
    bias_v: float = 0.0
    yoko_fixed: bool = False
    interactive_plots: bool = False
    transmission: dict | None = None
    spec: dict | None = None
    charge: dict | None = None
    tones: dict | None = None
    coherence: dict | None = None
    echo: dict | None = None
    single_shot: dict | None = None

    def __post_init__(self):
        for role in ("qubit_readout", "qubit_pulse"):
            q = getattr(self, role)
            if q not in self.device.qubits:
                raise KeyError(
                    f"Session({role}={q!r}): {self.device.name} has qubits "
                    f"{sorted(self.device.qubits)}"
                )
        for name in GROUPS:
            value = getattr(self, name)
            if value is None:
                value = _library_group(name)
            elif not isinstance(value, Mapping):
                raise TypeError(
                    f"Session({name}=...) takes the dict a qicklab.runs.groups function returns, "
                    f"got {type(value).__name__}"
                )
            object.__setattr__(self, name, copy.deepcopy(dict(value)))

    def qubit(self, q=None):
        """`device.qubits[q]`; q None is the pulse qubit (the one recipes resolve from)."""
        return self.device.qubits[self.qubit_pulse if q is None else q]

    def groups(self):
        """{group: fresh dict} for the config builders and the steps.

        The single_shot group's None Readout_Time / ADC_Offset become the readout qubit's
        single-shot window (`Device.window(q, single_shot=True)`); its None Qubit_Pulse
        becomes [qubit_pulse].
        """
        out = {name: copy.deepcopy(getattr(self, name)) for name in GROUPS}
        ss = out["single_shot"]
        window = self.device.window(self.qubit_readout, single_shot=True)
        if ss.get("Readout_Time") is None:
            ss["Readout_Time"] = window.length_us
        if ss.get("ADC_Offset") is None:
            ss["ADC_Offset"] = window.adc_offset_us
        if ss.get("Qubit_Pulse") is None:
            ss["Qubit_Pulse"] = [self.qubit_pulse]
        return out


def connect(session):
    """Connect the RFSoC and the charge yoko and build the regime-A config: a Context.

    The legacy `build_context` call, fed the device's numbers, window and endpoints and the
    session's groups; the device is then validated against the board (warnings for soft
    problems). The caller closes `ctx.yoko`; `run` does it for you.
    """
    device = session.device
    setup = device.setup
    if setup.board_overrides or setup.ff_qubits is not None:
        raise NotImplementedError(
            f"{device.name}: Setup.board_overrides / ff_qubits are not applied by build_context "
            f"yet (it builds from hardware.board BaseConfig / FF_Qubits); leave them unset"
        )
    if session.interactive_plots:
        warnings.warn(
            "Session(interactive_plots=True) has no effect yet: importing qicklab.analysis "
            "selects the Agg backend (docs/running_a_session.md#plots)",
            stacklevel=2,
        )
    groups = session.groups()
    window = device.window(session.qubit_readout)
    ctx = build_context(
        device.legacy_parameters(),
        session.qubit_readout,
        session.qubit_pulse,
        session.bias_v,
        Transmission_params=groups["transmission"],
        Spec_relevant_params=groups["spec"],
        tl=groups["tones"],
        charge_params=groups["charge"],
        cavity_min=device.cavity_min,
        yoko_fixed=session.yoko_fixed,
        yoko_addr=setup.yoko_addr,
        readout_length_us=window.length_us,
        adc_trig_offset_us=window.adc_offset_us,
        rfsoc_host=setup.rfsoc_host,
        rfsoc_port=setup.rfsoc_port,
        rfsoc_name=setup.rfsoc_name,
        device=device.name,
    )
    try:
        device.validate(ctx.soccfg)
    except BaseException:
        ctx.yoko.close()
        raise
    ctx.session = session
    ctx.regime = "A"
    ctx.regime_a_config = None
    return ctx


def _enter_regime(ctx, regime, single_shot):
    """Switch ctx.config to `regime`: A -> B rebuilds, B -> A restores the held regime-A config.

    docs/concepts/config_regimes.md#what-changes-at-the-switch-a---b
    """
    if ctx.regime == regime:
        return
    if regime == "B":
        ctx.regime_a_config = ctx.config
        rebuild_singleshot_config(ctx, single_shot)
        print(
            "[session] regime A -> B: single-shot config rebuilt from BaseConfig "
            "(carry-overs pulse_freq / res_phase dropped) with the session single_shot group"
        )
        # the config inputs every later regime-B step runs with, also those without the slot
        text = pprint.pformat(single_shot, width=100, sort_dicts=False)
        print("    single_shot = " + text.replace("\n", "\n" + " " * 18))
    else:
        ctx.config, ctx.regime_a_config = ctx.regime_a_config, None
        print("[session] regime B -> A: regime-A config restored (its carry-overs kept)")
    ctx.regime = regime


def _log_step(step, args, label):
    print(f"\n[session] {label}{step.name} (regime {step.regime})")
    for slot, value in zip(step.needs, args):
        text = pprint.pformat(value, width=100, sort_dicts=False)
        print(f"    {slot} = " + text.replace("\n", "\n" + " " * (len(slot) + 7)))


@contextlib.contextmanager
def _step_pi2_ss(ctx, step, args):
    """While a regime-B step runs, ctx.config["pi2_SS"] = its single_shot slot's pi2_SS.

    The config was built from the session group; a step override (R.single_shot(pi2_ss=True))
    changes the pulse its run plays, so the saved cfg must say so too. Restored afterwards.
    """
    cfg = ctx.config
    if step.regime != "B" or "single_shot" not in step.needs or "pi2_SS" not in cfg:
        yield
        return
    wanted = args[step.needs.index("single_shot")].get("pi2_SS", cfg["pi2_SS"])
    held = cfg["pi2_SS"]
    if wanted == held:
        yield
        return
    print(f"    (config pi2_SS = {wanted!r} for this step; the session group's is {held!r})")
    cfg["pi2_SS"] = wanted
    try:
        yield
    finally:
        if ctx.config is cfg:
            cfg["pi2_SS"] = held


def _zsp_fill_from_cache(session, p):
    """Fill the step's still-None cache entries from zsp_cache.json (same readout/pulse qubits)."""
    record = io.read_zsp_cache(session.device, session.qubit_pulse)
    if record is None:
        return
    if (record.get("qubit_readout"), record.get("qubit_pulse")) != (
        session.qubit_readout,
        session.qubit_pulse,
    ):
        return
    filled = []
    for sub in io.ZSP_CACHED:
        target = p.get(sub)
        if not isinstance(target, dict):
            continue
        for key, value in (record.get(sub) or {}).items():
            if key in target and target[key] is None and value is not None:
                target[key] = value
                filled.append(f"{sub}[{key!r}]")
    if filled:
        print(
            f"[zsp cache] {', '.join(filled)} from "
            f"{io.zsp_cache_path(session.device, session.qubit_pulse)} ({record.get('time')})"
        )


def _zsp_store(session, p):
    """After a zero_span_parity step: persist the run's caches; record a recalibrated doublet."""
    parity, separator = (p.get(sub) or {} for sub in io.ZSP_CACHED)
    if all(v is None for v in (*parity.values(), *separator.values())):
        return
    io.write_zsp_cache(
        session.device,
        session.qubit_pulse,
        parity,
        separator,
        qubit_readout=session.qubit_readout,
        qubit_pulse=session.qubit_pulse,
    )
    lower, higher = parity.get("lower_peak_MHz"), parity.get("higher_peak_MHz")
    if p.get("ZSP_RecalibrateParityFreqs") and lower is not None and higher is not None:
        io.record_calibration(
            session.device,
            session.qubit_pulse,
            step="zero_span_parity",
            parity_f_upper_mhz=float(higher),
            parity_df_mhz=float(higher) - float(lower),
        )


# steps whose run writes a measured readout frequency into ctx.config["pulse_freq"] (the gated
# carry-over, docs/experiments/transmission_fit.md#carry-over-gate)
_READOUT_FREQ_STEPS = ("transmission_fit", "transmission_sweep")


def _record_readout_freq(ctx, step, config, before):
    """After a transmission step: record a carried-over readout frequency (record_calibration).

    Only when the step's gate wrote a new pulse_freq into the same config object; an IF
    (cavity_LO != 0) is printed, not recorded, because Readout.freq is the absolute frequency.
    """
    if ctx.config is not config or "pulse_freq" not in config:
        return
    freq = config["pulse_freq"]
    if freq == before:
        return
    session = ctx.session
    if config.get("cavity_LO", 0):
        print(
            f"[calibration] {step.name}: pulse_freq {freq} MHz is an IF (cavity_LO = "
            f"{config['cavity_LO']}); not recorded"
        )
        return
    io.record_calibration(
        session.device, session.qubit_readout, step=step.name, readout_freq=float(freq)
    )


def _keep_regime_config(ctx, step, config):
    """After a step: ctx.config is again the config object the step was handed.

    The session tracks the regime by that object (ctx.regime, ctx.regime_a_config). A run_*
    may only write into it; run_interleaved_coherence swaps in its single-shot config and
    restores the regime-A one on exit, except on its early return with no sub-experiment
    enabled (a legacy bug the unconditional rebuild after it hid in the legacy runner). The
    session puts the object back so the next step does not run on the wrong regime.
    """
    if ctx.config is config:
        return
    print(
        f"[session] {step.name} left ctx.config replaced; the regime-{ctx.regime} config it "
        "was handed is restored"
    )
    ctx.config = config


def _run_step(ctx, step, label=""):
    session = getattr(ctx, "session", None)
    if session is None:
        raise ValueError("ctx has no session: make it with connect(session)")
    if not isinstance(step, Step):
        raise TypeError(f"a PLAN entry must be a Step (R.<step>(...)), got {step!r}")
    groups = session.groups()
    _enter_regime(ctx, step.regime, groups["single_shot"])
    # built immediately before the call: an own dict a previous step wrote into is seen here
    args = step.arguments(groups, session.qubit())
    zsp = step.name == "zero_span_parity" and bool(args) and isinstance(args[0], dict)
    if zsp:
        _zsp_fill_from_cache(session, args[0])
    _log_step(step, args, label)
    config, pulse_freq = ctx.config, ctx.config.get("pulse_freq")
    with _step_pi2_ss(ctx, step, args):
        try:
            result = step.fn(ctx, *args)
        finally:
            _keep_regime_config(ctx, step, config)
    if zsp:
        _zsp_store(session, args[0])
    if step.name in _READOUT_FREQ_STEPS:
        _record_readout_freq(ctx, step, config, pulse_freq)
    return result


def run_step(ctx, step):
    """Run one Step on a connected ctx (REPL use): regime switch, resolved parameters, log, call.

    Returns what the step's run_* returns.
    """
    return _run_step(ctx, step)


def _check_plan(plan):
    plan = list(plan)
    for i, step in enumerate(plan):
        if not isinstance(step, Step):
            raise TypeError(f"PLAN[{i}] must be a Step (R.<step>(...)), got {step!r}")
    return plan


def _print_plan(session, plan, tag="plan"):
    d = session.device
    print(
        f"[session] {tag}: {d.name} ({d.cooldown}), readout Q{session.qubit_readout}, "
        f"pulse Q{session.qubit_pulse}, bias {session.bias_v} V, {len(plan)} step(s): "
        + ", ".join(s.name for s in plan)
    )


def run(session, plan, dry_run=False):
    """Run the PLAN in order: connect, each step as run_step does it, close the yoko in `finally`.

    Returns the steps' return values. dry_run=True runs on the fakes (qicklab.core.fakes) in a
    temp data root removed afterwards, returns the per-step report and raises if a step
    failed. docs/running_a_session.md#running
    """
    plan = _check_plan(plan)
    if dry_run:
        return _dry_run(session, plan)
    _print_plan(session, plan)
    ctx = connect(session)
    results = []
    try:
        for i, step in enumerate(plan, 1):
            results.append(_run_step(ctx, step, f"step {i}/{len(plan)}: "))
    finally:
        ctx.yoko.close()
    return results


# --------------------------------------------------------------------------------------------
# Dry run (docs/running_a_session.md#dry-run)
# --------------------------------------------------------------------------------------------
# Every experiment a step builds runs, so a stage after a calibration loop compiles too
# (auto_coherence with library defaults: about 90 experiments, its longest same-experiment
# loops about 30, under a minute). A step is stopped, and reported INCOMPLETE, only after DRY_RUN_MAX_REPEATS
# consecutive builds of experiments (class, path) it already built (a repetition loop or a
# long grid), or DRY_RUN_MAX_EXPERIMENTS builds in all (an unbounded loop).
DRY_RUN_MAX_REPEATS = 40
DRY_RUN_MAX_EXPERIMENTS = 200


class _DryRunBudget(BaseException):
    """Stops a dry-run step at the guards above (BaseException: no run swallows it)."""


class _Tally:
    """The experiments one dry-run step built: {(class, path): n} and the current repeat run."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.built, self.repeats = {}, 0

    def add(self, kind):
        """Count one build; raise _DryRunBudget when a guard is passed."""
        if sum(self.built.values()) >= DRY_RUN_MAX_EXPERIMENTS:
            raise _DryRunBudget(f"{DRY_RUN_MAX_EXPERIMENTS} experiments built")
        self.repeats = self.repeats + 1 if kind in self.built else 0
        self.built[kind] = self.built.get(kind, 0) + 1
        if self.repeats > DRY_RUN_MAX_REPEATS:
            raise _DryRunBudget(
                f"{self.repeats} builds in a row of experiments already built, the last "
                f"{kind[0]}/{kind[1]}"
            )


def _no_stdin(prompt=""):
    raise EOFError("no interactive stdin in a dry run")


@contextlib.contextmanager
def _patched(owner, name, value):
    saved = getattr(owner, name)
    setattr(owner, name, value)
    try:
        yield
    finally:
        setattr(owner, name, saved)


@contextlib.contextmanager
def _fake_hardware(tally):
    """Fakes for the RFSoC proxy and the yoko, no blocking calls, the per-step experiment guards.

    Every ExperimentClass built is counted in `tally` (a _Tally; the caller resets it per step).
    The provenance state (session record, the yoko's last landed levels) and open figures are
    restored.
    """
    original_init = ExperimentClass.__dict__["__init__"]

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        tally.add((type(self).__name__, getattr(self, "path", None)))

    saved_session = (io.session(), io._SESSION_SOCCFG[0])
    saved_levels = copy.deepcopy(yoko_module._LAST_LEVELS)
    figures = set(plt.get_fignums())
    with contextlib.ExitStack() as stack:
        stack.enter_context(_patched(context_module, "makeProxy", fakes.fake_make_proxy))
        stack.enter_context(_patched(pyvisa, "ResourceManager", fakes.FakeResourceManager))
        stack.enter_context(_patched(builtins, "input", _no_stdin))
        stack.enter_context(_patched(time, "sleep", lambda *a, **k: None))
        stack.enter_context(_patched(plt, "show", lambda *a, **k: None))
        stack.enter_context(_patched(plt, "pause", lambda *a, **k: None))
        stack.enter_context(_patched(ExperimentClass, "__init__", init))
        try:
            yield
        finally:
            for num in set(plt.get_fignums()) - figures:
                plt.close(num)
            io._SESSION.clear()
            io._SESSION.update(saved_session[0])
            io._SESSION_SOCCFG[0] = saved_session[1]
            yoko_module._LAST_LEVELS.clear()
            yoko_module._LAST_LEVELS.update(saved_levels)


def _programs():
    """tProc programs loaded on the fake board so far (outside a harness capture)."""
    entry = fakes.STATE.hashers.get(None)
    return entry[1].get("load_bin_program", 0) if entry else 0


def _copy_caches(device, root):
    """Mirror the real zsp_cache.json files into the dry-run root (read, never written)."""
    for q in device.qubits:
        src = io.zsp_cache_path(device, q)
        if os.path.exists(src):
            os.makedirs(f"{root}/Q{q}", exist_ok=True)
            shutil.copyfile(src, f"{root}/Q{q}/{io.ZSP_CACHE_FILE}")


def _dry_run(session, plan):
    _print_plan(session, plan, tag="DRY RUN (fake board, nothing is kept)")
    root = tempfile.mkdtemp(prefix="qicklab_dryrun_").replace("\\", "/")
    report = []
    tally = _Tally()
    try:
        _copy_caches(session.device, root)
        dry = dataclasses.replace(
            session, device=dataclasses.replace(session.device, data_root=root)
        )
        with _fake_hardware(tally):
            ctx = connect(dry)
            figures = set(plt.get_fignums())
            try:
                for i, step in enumerate(plan, 1):
                    tally.reset()
                    programs = _programs()
                    entry = {"step": step.name, "status": "ok", "error": None}
                    try:
                        _run_step(ctx, step, f"dry run {i}/{len(plan)}: ")
                    except _DryRunBudget as exc:
                        entry["status"] = f"INCOMPLETE ({exc}; later programs not compiled)"
                    except Exception as exc:
                        entry["status"] = "raised"
                        entry["error"] = f"{type(exc).__name__}: {exc}"
                        traceback.print_exc()
                    entry["experiments"] = sum(tally.built.values())
                    entry["built"] = {f"{c}/{p}": n for (c, p), n in tally.built.items()}
                    entry["programs"] = _programs() - programs
                    report.append(entry)
                    for num in set(plt.get_fignums()) - figures:  # as a step's own window would
                        plt.close(num)
            finally:
                ctx.yoko.close()
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print("\n[session] dry run report:")
    for i, e in enumerate(report, 1):
        error = f": {e['error']}" if e["error"] else ""
        print(
            f"    {i:>2}. {e['step']:<36} {e['experiments']:>3} experiment(s) "
            f"{e['programs']:>4} program(s)  {e['status']}{error}"
        )
        if e["built"]:
            print("        built: " + ", ".join(f"{k} x{n}" for k, n in e["built"].items()))
    incomplete = [e["step"] for e in report if e["status"].startswith("INCOMPLETE")]
    if incomplete:
        print(
            f"[session] dry run INCOMPLETE for {', '.join(incomplete)}: the programs after the "
            "stop were not compiled; shorten its repetitions or sweep to check them"
        )
    failed = [e for e in report if e["status"] == "raised"]
    if failed:
        raise RuntimeError(
            f"dry run: {len(failed)} step(s) failed: "
            + "; ".join(f"{e['step']}: {e['error']}" for e in failed)
        )
    return report
