"""In-GUI measurement agent: a chat panel backed by the Claude Code CLI.

The agent ADVISES on calibration/measurement and PROPOSES runnable calibration
actions; the GUI executes an action only after the user clicks Approve. Safety
model:
  * The headless Claude runs in --permission-mode plan (READ-ONLY): it can read
    the repo + data files to give grounded advice, but cannot edit files, run
    shell commands, or touch hardware.
  * Hardware is driven ONLY by the GUI's own AutoCalibWorker, and ONLY on an
    explicit Approve click. The agent never executes anything itself.

Backend: the installed, authenticated `claude` CLI, run at the HouckLab_QICK repo
root so it inherits the project's CLAUDE.md research-scientist persona and the
project subagents. Conversation continuity via --resume <session_id>.
"""
import json
import re
import shutil
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton, QLabel,
    QMessageBox, QCheckBox,
)

# Two permission tiers:
#  * DEFAULT (read-only): the agent advises and proposes GUI-calibration actions that
#    the GUI auto-runs through its own connection. It CANNOT edit code or run shell.
#  * EDIT (only when the user ticks "Allow code edits" for that one message): the agent
#    may write/modify/run code (Edit/Write/MultiEdit/Bash) to handle new-code requests.
# Use only tool names the current CLI recognizes -- an unknown name in a
# --disallowed-tools rule is a FATAL startup error (e.g. MultiEdit/LS were
# removed/merged). The read-only tier also relies on the allowlist: anything not
# allowed is denied in headless mode, so the disallow list is belt-and-suspenders
# over the core mutators.
_AGENT_READ_TOOLS = ["Read", "Grep", "Glob"]
_AGENT_NOEDIT_DISALLOW = ["Bash", "Edit", "Write"]
_AGENT_EDIT_TOOLS = ["Read", "Grep", "Glob", "Edit", "Write", "Bash"]
_AGENT_TIMEOUT_S = 600   # coding turns can take longer than advice turns


def _find_repo_root() -> Path:
    """Walk up from this file to the dir containing CLAUDE.md (HouckLab_QICK)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "CLAUDE.md").exists():
            return parent
    # Fallback: .../HouckLab_QICK/WorkingProjects/triangle_lattice_quench/Run_Experiments
    return here.parents[3]


def _find_claude() -> str:
    """Locate the claude CLI; fall back to the known per-user install path."""
    exe = shutil.which("claude")
    if exe:
        return exe
    cand = Path.home() / ".local" / "bin" / "claude.exe"
    return str(cand) if cand.exists() else "claude"


def find_recent_h5(root: str, n: int = 8) -> list:
    """Most-recently-modified .h5 files under `root` (recursive).

    NOTE: recursive; can be slow on a network share. Use only off the GUI thread
    or on a user action, never per-message."""
    try:
        files = sorted(Path(root).rglob("*.h5"),
                       key=lambda f: f.stat().st_mtime, reverse=True)
        return files[:n]
    except Exception:
        return []


def list_experiment_dirs(root: str, n: int = 30) -> str:
    """Cheap depth-1 listing of experiment-type subdirs under `root` (no recursive
    glob, no per-entry stat) -- fast even on a network share. Gives the agent
    ambient awareness of what experiment data exists."""
    import os
    try:
        names = sorted(e.name for e in os.scandir(root) if e.is_dir())
    except Exception:
        return "  (unavailable)"
    if not names:
        return "  (none found)"
    return "\n".join(f"  - {x}/" for x in names[:n])


def summarize_h5(path) -> str:
    """Compact, bounded text summary of a measurement .h5 for the agent to read.

    Lists top-level datasets with shape/stats; expands small arrays and known
    scalar fields (r_squared, *_cal, swept_qubit, readout_list); gives per-readout
    min/max for population/contrast maps. Never dumps full large arrays; never
    raises."""
    import numpy as np
    path = Path(path)
    out = [f"file: {path.name}", f"experiment dir: {path.parent.name}"]
    try:
        import h5py
        with h5py.File(str(path), "r") as h:
            grp = h["data"] if ("data" in h and isinstance(h["data"], h5py.Group)) else h
            for k in grp:
                item = grp[k]
                if not isinstance(item, h5py.Dataset):
                    continue
                a = np.asarray(item[()])
                if a.dtype.kind in "OSU":                      # strings / object
                    vals = [x.decode() if isinstance(x, bytes) else str(x)
                            for x in a.ravel()[:12]]
                    out.append(f"  {k}: {vals}")
                elif a.ndim == 0:
                    out.append(f"  {k}: {a.item()}")
                elif a.size <= 16:
                    out.append(f"  {k}: shape{a.shape} {np.round(a.astype(float), 4).tolist()}")
                elif a.ndim >= 2 and k in ("population_corrected", "population", "contrast") and a.shape[0] <= 8:
                    rows = []
                    for r in range(a.shape[0]):
                        rr = a[r].astype(float); fr = rr[np.isfinite(rr)]
                        rows.append(f"ro{r}[{fr.min():.3g},{fr.max():.3g}]" if fr.size else f"ro{r}[nan]")
                    out.append(f"  {k}: shape{a.shape} per-readout(min,max) " + " ".join(rows))
                else:
                    af = a.astype(float); fin = af[np.isfinite(af)]
                    if fin.size:
                        out.append(f"  {k}: shape{a.shape} min={fin.min():.4g} "
                                   f"max={fin.max():.4g} mean={fin.mean():.4g}")
                    else:
                        out.append(f"  {k}: shape{a.shape} (no finite values)")
    except Exception as exc:
        out.append(f"  (could not read h5: {exc})")
    return "\n".join(out)


def resolve_params(defaults: dict, agent_params: dict | None):
    """Merge an agent's param overrides over a stage's defaults. Only keys present
    in `defaults` are honored (others returned in `dropped`, never injected into
    cfg); each override is coerced to the default's type. Returns (resolved, dropped)."""
    resolved = dict(defaults)
    dropped = []
    for k, v in (agent_params or {}).items():
        if k not in resolved:
            dropped.append(k)
            continue
        d = resolved[k]
        try:
            if isinstance(d, bool):
                resolved[k] = bool(v)
            elif isinstance(d, int):
                resolved[k] = int(v)
            elif isinstance(d, float):
                resolved[k] = float(v)
            else:
                resolved[k] = v
        except Exception:
            resolved[k] = v
    return resolved, dropped


_ACTION_RE = re.compile(r"```action\s*\n(.*?)\n```", re.DOTALL)


def parse_actions(text: str) -> list[dict]:
    """Extract proposed calibration actions from agent text.

    An action is a fenced ```action ... ``` block holding a JSON object with at
    least {stage, qubits}. Malformed blocks are skipped (never raise)."""
    out = []
    for m in _ACTION_RE.finditer(text or ""):
        try:
            obj = json.loads(m.group(1))
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        # Two forms: Auto-Calib stage ({stage, qubits}) or a tab calibration ({calibration}).
        if (obj.get("stage") and obj.get("qubits")) or obj.get("calibration"):
            out.append(obj)
    return out


def build_claude_cmd(claude_path: str, sys_prompt: str, session_id: str | None,
                     allow_edits: bool = False) -> list[str]:
    """Construct the headless claude command (prompt arrives on stdin).

    allow_edits=False -> read-only advice tier (no edits/shell). True -> edit tier
    (Edit/Write/MultiEdit/Bash auto-approved) for an explicitly-approved code change."""
    cmd = [claude_path, "-p", "--output-format", "json", "--append-system-prompt", sys_prompt]
    if allow_edits:
        cmd += ["--allowed-tools", *_AGENT_EDIT_TOOLS]
    else:
        cmd += ["--allowed-tools", *_AGENT_READ_TOOLS,
                "--disallowed-tools", *_AGENT_NOEDIT_DISALLOW]
    if session_id:
        cmd += ["--resume", session_id]
    return cmd


def _extract_result_json(stdout: str):
    """Pull the result JSON object out of `claude -p --output-format json` stdout,
    tolerating non-JSON preamble/trailing lines (update notices, warnings, etc.).
    Returns a dict or None."""
    s = (stdout or "").strip()
    if not s:
        return None
    try:                                            # 1. whole stdout is the JSON
        d = json.loads(s)
        if isinstance(d, dict):
            return d
    except Exception:
        pass
    for line in reversed(s.splitlines()):           # 2. last line that is a JSON object
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                d = json.loads(line)
                if isinstance(d, dict):
                    return d
            except Exception:
                continue
    start = s.find("{")                             # 3. a brace-balanced result blob
    while start != -1:
        depth = 0
        for i in range(start, len(s)):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        d = json.loads(s[start:i + 1])
                        if isinstance(d, dict) and ("result" in d or "session_id" in d):
                            return d
                    except Exception:
                        pass
                    break
        start = s.find("{", start + 1)
    return None


class AgentWorker(QThread):
    """Run one headless `claude` turn off the GUI thread. Prompt via stdin so
    long messages / quoting are never an issue."""

    finished_ok = pyqtSignal(str, str)   # (assistant_text, session_id)
    failed = pyqtSignal(str)

    def __init__(self, prompt: str, session_id: str | None, sys_prompt: str,
                 cwd: str, claude_path: str, allow_edits: bool = False):
        super().__init__()
        self.prompt = prompt
        self.session_id = session_id
        self.sys_prompt = sys_prompt
        self.cwd = cwd
        self.claude_path = claude_path
        self.allow_edits = allow_edits

    def run(self):
        import subprocess
        cmd = build_claude_cmd(self.claude_path, self.sys_prompt, self.session_id,
                               allow_edits=self.allow_edits)
        # On Windows, launching a console exe from a GUI app pops a black console
        # window each call. CREATE_NO_WINDOW suppresses it (no-op off Windows).
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.run(
                cmd, cwd=self.cwd, input=self.prompt,
                capture_output=True, text=True, timeout=_AGENT_TIMEOUT_S,
                creationflags=creationflags,
            )
        except FileNotFoundError:
            self.failed.emit(f"claude CLI not found ({self.claude_path}).")
            return
        except subprocess.TimeoutExpired:
            self.failed.emit(f"agent timed out after {_AGENT_TIMEOUT_S}s.")
            return
        except Exception as exc:
            self.failed.emit(f"agent subprocess error: {exc}")
            return
        if proc.returncode != 0:
            self.failed.emit(
                f"claude exited {proc.returncode}:\n{(proc.stderr or '')[-2000:]}")
            return
        data = _extract_result_json(proc.stdout or "")
        if not isinstance(data, dict):
            # Surface generously so the actual cause is visible (auth notice, warning
            # preamble, rate-limit text, etc.). stdout head AND tail + stderr tail.
            out = proc.stdout or ""
            self.failed.emit(
                "could not parse claude output as JSON.\n"
                f"--- stdout[:1200] ---\n{out[:1200]}\n"
                f"--- stdout[-800:] ---\n{out[-800:]}\n"
                f"--- stderr[-800:] ---\n{(proc.stderr or '')[-800:]}")
            return
        text = data.get("result") or data.get("text") or "(no result text)"
        if data.get("is_error") or data.get("subtype") == "error_max_turns":
            text = f"[agent error: {data.get('subtype', 'error')}] " + str(text)
        sid = data.get("session_id") or self.session_id or ""
        self.finished_ok.emit(str(text), sid)


class AgentChatTab(QWidget):
    """Chat panel for the measurement agent. Advises + proposes actions; runs
    approved actions through the existing AutoCalibWorker."""

    name = "Measurement Agent"

    def __init__(self, state, get_main, parent=None):
        super().__init__(parent)
        self.state = state
        self.get_main = get_main
        self.session_id: str | None = None
        self.worker: AgentWorker | None = None
        self.calib_worker = None                # AutoCalibWorker for an agent-run calibration
        self._edits_allowed_this_turn = False   # set from the checkbox per send
        # Autopilot loop state: after each run, feed the result back so the agent runs the
        # next step itself, until it stops emitting actions or the step cap is hit.
        self._auto_steps = 0
        self._auto_step_cap = 25
        self._stop_autopilot = False
        self._last_run_results = []             # stage summaries accumulated during a run
        self._repo_root = str(_find_repo_root())
        self._claude = _find_claude()

        root = QVBoxLayout(self)

        hint = QLabel(
            "Measurement agent (Claude Code). It advises, AUTO-RUNS the GUI's built-in "
            "calibrations it proposes (no approval), and can interpret attached data. "
            "It CANNOT change code unless you tick 'Allow code edits' on that message."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555;")
        root.addWidget(hint)

        self.transcript = QPlainTextEdit()
        self.transcript.setReadOnly(True)
        root.addWidget(self.transcript, 1)

        in_row = QHBoxLayout()
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText(
            "Ask or instruct the agent (e.g. 'Q6 readout fidelity is low — fix it'). "
            "Ctrl+Enter to send.")
        self.input.setFixedHeight(70)
        self.input.installEventFilter(self)   # Ctrl+Enter to send (child consumes keys)
        in_row.addWidget(self.input, 1)

        btns = QVBoxLayout()
        self.autopilot_chk = QCheckBox("Autopilot (run full plan)")
        self.autopilot_chk.setChecked(True)
        self.autopilot_chk.setToolTip(
            "ON: after each calibration finishes, its result is fed back to the agent "
            "automatically and the agent runs the next step until the plan is done (or the "
            f"{self._auto_step_cap}-step cap). The GUI follows along, showing the running "
            "tab. Stop run halts the loop. OFF: the agent pauses after each step.")
        btns.addWidget(self.autopilot_chk)
        self.allow_edits_chk = QCheckBox("Allow code edits")
        self.allow_edits_chk.setToolTip(
            "OFF by default: the agent is read-only and only auto-runs existing GUI "
            "calibrations. Tick this for ONE message to let the agent write/modify/run "
            "code (e.g. a new measurement). It auto-resets after that message.")
        btns.addWidget(self.allow_edits_chk)
        self.attach_btn = QPushButton("Attach data…")
        self.attach_btn.setToolTip(
            "Load a saved .h5 and insert a compact summary into your message for the "
            "agent to interpret.")
        self.attach_btn.clicked.connect(self._on_attach_data)
        btns.addWidget(self.attach_btn)
        row2 = QHBoxLayout()
        self.stop_btn = QPushButton("Stop run")
        self.stop_btn.setToolTip("Abort the calibration the agent is currently running.")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        row2.addWidget(self.stop_btn)
        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self._on_send)
        row2.addWidget(self.send_btn)
        btns.addLayout(row2)
        in_row.addLayout(btns)
        root.addLayout(in_row)

    # ---- conversation ----------------------------------------------------

    def eventFilter(self, obj, ev):
        from PyQt5.QtCore import QEvent
        if (obj is self.input and ev.type() == QEvent.KeyPress
                and ev.key() in (Qt.Key_Return, Qt.Key_Enter)
                and (ev.modifiers() & Qt.ControlModifier)):
            self._on_send()
            return True
        return super().eventFilter(obj, ev)

    def _append(self, who: str, text: str):
        self.transcript.appendPlainText(f"\n[{who}]\n{text}")

    def _on_attach_data(self):
        """Pick a saved .h5, summarize it, and prepend the summary to the input box
        so the user can add a question and send it to the agent for interpretation."""
        from PyQt5.QtWidgets import QFileDialog
        start = getattr(self.state, "outer_folder", "") or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Attach measurement .h5", start, "HDF5 (*.h5);;All files (*)")
        if not path:
            return
        summary = summarize_h5(path)
        cur = self.input.toPlainText().strip()
        block = f"Here is measurement data to interpret:\n{summary}\n\nMy question: "
        self.input.setPlainText((cur + "\n\n" if cur else "") + block)
        self.input.setFocus()

    def _resolve_params(self, stage_name: str, agent_params: dict | None):
        """(resolved_params or None, dropped_keys). resolved = the stage's current
        param_form values with the agent's KNOWN-key overrides applied, coerced to
        each default's type. Unknown keys are dropped (never injected into cfg)."""
        try:
            main = self.get_main()
            stage = {s.name: s for s in main.stages}.get(stage_name)
        except Exception:
            stage = None
        if stage is None:
            return None, []
        try:
            defaults = dict(stage.param_form.values())
        except Exception:
            return None, []
        return resolve_params(defaults, agent_params)

    def _build_sys_prompt(self) -> str:
        """Snapshot the GUI/calibration state + the action protocol for the agent."""
        st = self.state
        jpath = getattr(st, "qubit_parameters_json_path", None)
        rg = getattr(st, "current_readout_group", "") or "(none)"
        connected = "yes" if st.is_connected() else "NO (cannot run hardware)"
        # Per-stage parameter schema so the agent can set sweep params, not just defaults.
        stage_params = {}
        tab_cals = {}
        try:
            main = self.get_main()
            for s in getattr(main, "stages", []):
                try:
                    stage_params[s.name] = list(s.param_form.values().keys())
                except Exception:
                    stage_params[s.name] = []
            # Whole-tab calibrations (chevron, pi2-phase, ...) auto-discovered by AGENT_ACTION.
            for i in range(main.tabs.count()):
                w = main.tabs.widget(i)
                aid = getattr(w, "AGENT_ACTION", None)
                if aid:
                    tab_cals[aid] = getattr(w, "AGENT_PARAMS", "")
        except Exception:
            pass
        # Experiment-type dirs present (cheap depth-1 listing -- NO recursive network glob
        # on the GUI thread). The user attaches a specific .h5 via the Attach button.
        exp_dirs = list_experiment_dirs(getattr(st, "outer_folder", "") or "")
        last = list((getattr(st, "last_results", {}) or {}).keys())
        edits = "ENABLED for this message" if self._edits_allowed_this_turn else "OFF"
        return (
            "You are the in-GUI MEASUREMENT AGENT for a QICK/RFSoC superconducting-qubit "
            "calibration GUI. Advise the scientist, interpret data, and drive calibrations.\n\n"
            "WHEN PLANNING A CALIBRATION/MEASUREMENT WORKFLOW, first Read "
            "`.claude/skills/measurement-calibration/SKILL.md` -- it gives the general->specific "
            "calibration order, the pair->ramp->swap-dynamics rule, and time-respecting (fast vs "
            "careful) parameter ranges. Use it for sane VALUES; use this prompt for the action keys.\n\n"
            "RUNNING EXISTING CALIBRATIONS (no approval needed): to run one of the GUI's "
            "built-in stages, emit a fenced block EXACTLY like:\n"
            "```action\n{\"stage\": \"<stage name>\", \"qubits\": [6], "
            "\"params\": {\"<param>\": <value>}, \"summary\": \"one line\"}\n```\n"
            "The GUI AUTOMATICALLY runs each such block via its calibration worker (using its "
            "own RFSoC connection) and reports the result back to you -- no user approval. "
            "`params` is OPTIONAL: only the keys listed per stage below are honored (others "
            "dropped); omitted keys keep the GUI's current value. Emit an action ONLY for a "
            "real run; do not claim a result until the GUI reports it.\n\n"
            "RUNNING A WHOLE-TAB CALIBRATION (no approval): for the chevron / pi2-phase / etc., "
            "emit instead:\n"
            "```action\n{\"calibration\": \"<id below>\", \"params\": {\"<param>\": <value>}, "
            "\"summary\": \"one line\"}\n```\n"
            "The GUI runs it on the owning tab and reports the tab's result back to you. "
            f"Available tab calibrations and their params: {json.dumps(tab_cals)}\n\n"
            "CHANGING CODE (gated): you may edit/write/run code with Edit/Write/Bash ONLY when "
            f"the user ticks 'Allow code edits' for their message (currently: {edits}). When it "
            "is OFF and a request needs new or modified code, DO NOT attempt it -- explain what "
            "you'd change and ask the user to re-send with 'Allow code edits' ticked. Treat core "
            "experiment code (Experimental_Scripts/, Helpers/, Program_Templates/, build_config) "
            "with extra care.\n\n"
            f"Stages and their settable params: {json.dumps(stage_params)}\n"
            f"RFSoC connected: {connected}\n"
            f"Loaded qubit_parameters JSON: {jpath}\n"
            f"Current readout group: {rg}\n"
            f"Qubits with cached results this session: {last}\n"
            f"Experiment data folders present (ask the user to Attach a specific .h5 to "
            f"interpret it):\n{exp_dirs}\n"
        )

    def _on_send(self):
        if self.worker is not None and self.worker.isRunning():
            return
        msg = self.input.toPlainText().strip()
        if not msg:
            return
        # A user message starts a fresh plan: reset the autopilot step counter + stop flag.
        self._auto_steps = 0
        self._stop_autopilot = False
        # One-message edit elevation: read the checkbox, then auto-reset it so editing is
        # never left ON by accident.
        self._edits_allowed_this_turn = self.allow_edits_chk.isChecked()
        self.allow_edits_chk.setChecked(False)
        self.input.clear()
        self._append("you", msg + ("   [code edits ALLOWED this message]"
                                   if self._edits_allowed_this_turn else ""))
        self._send_to_agent(msg, allow_edits=self._edits_allowed_this_turn)

    def _send_to_agent(self, msg: str, allow_edits: bool = False):
        """Spawn one agent turn (used by both user sends and autopilot continuations)."""
        self.send_btn.setEnabled(False)
        self.send_btn.setText("…thinking")
        self.worker = AgentWorker(
            prompt=msg, session_id=self.session_id,
            sys_prompt=self._build_sys_prompt(),
            cwd=self._repo_root, claude_path=self._claude,
            allow_edits=allow_edits,
        )
        self.worker.finished_ok.connect(self._on_agent_done)
        self.worker.failed.connect(self._on_agent_failed)
        self.worker.start()

    def _on_agent_done(self, text: str, session_id: str):
        self.session_id = session_id or self.session_id
        self._append("agent", text)
        self.send_btn.setEnabled(True)
        self.send_btn.setText("Send")
        # Auto-run everything the agent proposed (no approval). Two forms:
        #  * {stage, qubits} -> Auto-Calib stages (combined into one AutoCalibWorker)
        #  * {calibration}   -> a whole-tab calibration (chevron, pi2-phase, ...)
        actions = parse_actions(text)
        if self._stop_autopilot and actions:
            # Stop was pressed while the agent was thinking -- do NOT run what it proposed.
            self._append("gui", "[STOP] autopilot halted; not running the agent's proposed actions.")
            try:
                self.get_main().tabs.setCurrentWidget(self)
            except Exception:
                pass
            return
        stage_actions = [a for a in actions if a.get("stage")]
        cal_actions = [a for a in actions if a.get("calibration")]
        if stage_actions:
            self._auto_run_actions(stage_actions)
        for a in cal_actions:
            self._run_tab_calibration(a)
        if not actions:
            # No run to do -> the agent answered/reported. Bring this panel forward so the
            # final report (or its question) is visible; the autopilot loop ends here.
            try:
                self.get_main().tabs.setCurrentWidget(self)
            except Exception:
                pass

    def _on_agent_failed(self, err: str):
        self._append("agent", f"[ERROR] {err}")
        self.send_btn.setEnabled(True)
        self.send_btn.setText("Send")

    # ---- auto-run proposed calibrations (no approval) -------------------

    def _auto_run_actions(self, actions: list):
        """Run the agent's proposed GUI calibrations automatically via AutoCalibWorker.
        Guards: RFSoC connected, no other auto-calib run in flight."""
        if self.calib_worker is not None and self.calib_worker.isRunning():
            self._append("gui", "[skip] a calibration is already running; ignoring new actions.")
            return
        if not self.state.is_connected():
            self._append("gui", "[skip] RFSoC not connected; cannot run the proposed calibration(s).")
            return
        try:
            main = self.get_main()
            ac_worker = getattr(getattr(main, "auto_calib_tab", None), "worker", None)
            if ac_worker is not None and ac_worker.isRunning():
                self._append("gui", "[skip] Auto-Calibration tab is running; try again after it finishes.")
                return
            stages_by_name = {s.name: s for s in main.stages}
        except Exception as exc:
            self._append("gui", f"[skip] could not access GUI stages: {exc}")
            return

        # Build a combined schedule from all valid actions.
        schedule = []
        for action in actions:
            stage_name = str(action.get("stage", ""))
            if stage_name not in stages_by_name:
                self._append("gui", f"[skip] unknown stage '{stage_name}' (have {list(stages_by_name)}).")
                continue
            params, dropped = self._resolve_params(stage_name, action.get("params"))
            if params is None:
                self._append("gui", f"[skip] could not read params for {stage_name}.")
                continue
            if dropped:
                self._append("gui", f"[note] ignored unknown {stage_name} params: {dropped}")
            qubits = [str(q) for q in action.get("qubits", [])]
            for Q in qubits:
                schedule.append((Q, stage_name, params))
        if not schedule:
            return

        from WorkingProjects.triangle_lattice_quench.Run_Experiments.calibration_gui import (
            AutoCalibWorker,
        )
        self._append("gui", "auto-running: "
                      + "; ".join(f"{s} Q{q}" for q, s, _ in schedule))
        self.stop_btn.setEnabled(True)
        self._last_run_results = []
        try:
            main.tabs.setCurrentWidget(main.auto_calib_tab)   # show the live auto-calib plot
        except Exception:
            pass
        self.calib_worker = AutoCalibWorker(self.state, schedule, stages_by_name)
        self.calib_worker.log_msg.connect(self.transcript.appendPlainText)
        self.calib_worker.stage_done.connect(self._on_stage_done)
        self.calib_worker.stage_failed.connect(self._on_stage_failed)
        self.calib_worker.finished_all.connect(self._on_run_finished)
        self.calib_worker.start()

    def _run_tab_calibration(self, action: dict):
        """Run a whole-tab calibration (chevron, pi2-phase, ...) the agent proposed.
        Routes to the owning tab's agent_run (auto-discovered by its AGENT_ACTION) and
        reports the tab's result label when its worker finishes."""
        cal_id = str(action.get("calibration", ""))
        params = action.get("params") or {}
        if not self.state.is_connected():
            self._append("gui", f"[skip] RFSoC not connected; cannot run {cal_id}.")
            return
        try:
            main = self.get_main()
            registry = {}
            for i in range(main.tabs.count()):
                w = main.tabs.widget(i)
                aid = getattr(w, "AGENT_ACTION", None)
                if aid:
                    registry[aid] = w
        except Exception as exc:
            self._append("gui", f"[skip] could not access tabs: {exc}")
            return
        tab = registry.get(cal_id)
        if tab is None:
            self._append("gui", f"[skip] unknown calibration '{cal_id}' (have {list(registry)}).")
            return
        # Busy guard: refuse if this tab, our auto-calib worker, or the agent's last tab
        # run is still going (concurrent RFSoC access corrupts runs).
        tw = getattr(tab, "worker", None)
        busy = ((tw is not None and tw.isRunning())
                or (self.calib_worker is not None and self.calib_worker.isRunning()))
        if busy:
            self._append("gui", f"[skip] a run is in progress; retry {cal_id} when it finishes.")
            return
        # Snapshot the tab's worker so we can tell whether agent_run actually started a NEW
        # run. The tab's _on_run can bail (not connected, missing selection, cfg error) and
        # leave worker None/stale -- arming .finished on that would stall or fire on an old
        # thread, and (in autopilot) march on as if the step ran.
        prev_worker = getattr(tab, "worker", None)
        try:
            status = tab.agent_run(params)
        except Exception as exc:
            self._append("gui", f"[skip] {cal_id} setup failed: {exc}")
            return
        tw = getattr(tab, "worker", None)
        if tw is None or tw is prev_worker:
            self._append("gui", f"[skip] {cal_id} did not start (check RFSoC connection and "
                                f"the tab's required selections). Status: {status}")
            return
        self._append("gui", f"auto-running {cal_id}: {status}")
        try:
            main.tabs.setCurrentWidget(tab)   # show the live calibration plot
        except Exception:
            pass
        self.stop_btn.setEnabled(True)
        tw.finished.connect(lambda t=tab, c=cal_id: self._on_tab_cal_finished(t, c))

    def _on_tab_cal_finished(self, tab, cal_id: str):
        self.stop_btn.setEnabled(False)
        summary = ""
        try:
            summary = tab.result_lbl.text()
        except Exception:
            pass
        self._append("result", f"{cal_id} finished: {summary}")
        self._maybe_autocontinue(f"{cal_id}", summary)

    def _on_stop(self):
        # Halt the autopilot loop AND abort the current run if it supports it.
        self._stop_autopilot = True
        if self.calib_worker is not None and self.calib_worker.isRunning():
            try:
                self.calib_worker.stop()
                self._append("gui", "[STOP] autopilot halted; finishing current stage...")
            except Exception as exc:
                self._append("gui", f"[STOP] failed: {exc}")
        else:
            self._append("gui", "[STOP] autopilot halted. (A tab calibration already in "
                                "flight can't be interrupted mid-run; it will finish.)")

    def _on_run_finished(self):
        self.stop_btn.setEnabled(False)
        # Summarize the stages that ran, then (autopilot) feed it back to the agent.
        summary = "; ".join(self._last_run_results) or "(no per-stage summary)"
        self._maybe_autocontinue("auto-calib run", summary)

    def _maybe_autocontinue(self, what: str, summary: str):
        """Autopilot: feed the just-finished result back to the agent so it runs the next
        step itself. Ends when autopilot is off, Stop was pressed, or the step cap is hit."""
        if not self.autopilot_chk.isChecked() or self._stop_autopilot:
            self._append("gui", "--- run finished. Send a message (e.g. 'what next?') to continue. ---")
            return
        if self._auto_steps >= self._auto_step_cap:
            self._append("gui", f"--- autopilot cap ({self._auto_step_cap} steps) reached; "
                                "paused. Send a message to continue. ---")
            return
        self._auto_steps += 1
        self._append("gui", f"[autopilot {self._auto_steps}/{self._auto_step_cap}] "
                            "feeding result to the agent...")
        self._send_to_agent(
            f"{what} finished. Result: {summary}\n\n"
            "Continue the plan: if there is a next calibration step, emit its action now; "
            "if the whole plan is complete, reply with 'DONE' and a short summary for the user.",
            allow_edits=False,   # autopilot stays read-only; code changes need the user's tick
        )

    def _on_stage_done(self, Q, stage_name, summary, expt, data, elapsed):
        line = f"{stage_name} on Q{Q}: {summary}"
        self._last_run_results.append(line)
        self._append("result", f"{line} ({elapsed:.1f}s)")

    def _on_stage_failed(self, Q, stage_name, err, *rest):
        # Record failures in the run summary too, so autopilot tells the agent a step
        # FAILED rather than silently omitting it and marching on as if it succeeded.
        line = f"{stage_name} on Q{Q} FAILED: {err}"
        self._last_run_results.append(line)
        self._append("result", line)
