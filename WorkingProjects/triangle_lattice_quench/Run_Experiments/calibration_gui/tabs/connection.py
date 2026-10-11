"""Connection dialog + Qblox D5a coupler-bias loader / worker / dialog.

The pre-step ``ConnectionDialog`` (Pyro4 nameserver lookup, RFSoC proxy pick,
and channel mapping) plus the D5a coupler-bias loader, its off-thread apply
worker, and its dialog. No other tab imports from here.

Depends on the state foundation only.
"""
from __future__ import annotations

import copy
import json
import threading
import traceback
from pathlib import Path
from typing import Any, Optional

from PyQt5.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import style as st
from ..state import (
    CalibState,
    make_default_ff_qubits,
    DEFAULT_BASE_CONFIG,
    DEFAULT_D5A_VOLTAGES_FILE,
    DEFAULT_D5A_PORT,
    DEFAULT_D5A_BAUD,
    DEFAULT_D5A_TIMEOUT,
    DEFAULT_D5A_MODULE,
    DEFAULT_D5A_RAMP_STEP,
    DEFAULT_D5A_RAMP_INTERVAL,
    SETTING_CHANNEL_MAP,
    SETTING_NS_HOST,
    SETTING_NS_PORT,
    SETTING_PROXY_NAME,
    get_settings,
    set_d5a_settings,
)
from ..helpers import dump_pretty


# ---------------------------------------------------------------------------
# Qblox D5a coupler-bias loader, worker, and dialog
# ---------------------------------------------------------------------------


def load_d5a_voltages_from_file(path: str) -> dict[str, float]:
    """Return a {label: volts} dict loaded from a .py or .json setpoint file.

    Accepted formats:
      - .json containing either {"voltages": {...}} or a flat dict.
      - .py defining a top-level dict variable whose values are all numbers.
        Dict variables containing "voltage" in the name are preferred.
    The .py path stubs the SPIRack/D5aModule imports so the file can be
    parsed without touching hardware.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    if p.suffix.lower() == ".json":
        with open(p, "r") as fh:
            d = json.load(fh)
        if isinstance(d, dict) and "voltages" in d and isinstance(d["voltages"], dict):
            d = d["voltages"]
        if not isinstance(d, dict):
            raise ValueError(f"{p} JSON is not a dict")
        return {str(k): float(v) for k, v in d.items()}

    # .py path — stub the SPIRack drivers so import is harmless.
    import runpy
    import sys
    import types

    class _StubD5a:
        range_4V_uni = 0
        range_4V_bi = 2
        range_2V_bi = 4
        _num_dacs = 16
        def __init__(self, *a, **kw): pass
        def get_settings(self, dac): return (0.0, self.range_4V_bi)
        def change_span(self, dac, span): pass
        def change_span_update(self, dac, span): pass
        def set_voltage(self, dac, v): pass
        def set_voltage_ramp(self, dac, v): pass

    class _StubSPIRack:
        def __init__(self, *a, **kw): pass
        def close(self): pass
        def unlock(self): pass

    targets = [
        "triangle_lattice_quench.Equipment_Drivers.SPIRackvoltage",
        "triangle_lattice_quench.Client_modules.Equipment_Drivers.SPIRackvoltage",
    ]
    saved = {t: sys.modules.get(t) for t in targets}
    fake = types.ModuleType("spirack_stub")
    fake.SPIRack = _StubSPIRack
    fake.D5aModule = _StubD5a
    for t in targets:
        sys.modules[t] = fake
    try:
        ns = runpy.run_path(str(p), run_name="<gui-load-d5a>")
    finally:
        for t, mod in saved.items():
            if mod is None:
                sys.modules.pop(t, None)
            else:
                sys.modules[t] = mod

    candidates: list[tuple[str, dict]] = []
    for name, val in ns.items():
        if name.startswith("_"):
            continue
        if isinstance(val, dict) and val and \
                all(isinstance(v, (int, float)) for v in val.values()):
            candidates.append((name, val))
    if not candidates:
        raise ValueError(
            f"No voltage dictionary found in {p}. "
            "Expected a top-level dict whose values are numbers."
        )
    candidates.sort(key=lambda nv: 0 if "voltage" in nv[0].lower() else 1)
    chosen = candidates[0][1]
    return {str(k): float(v) for k, v in chosen.items()}


class D5aApplyWorker(QThread):
    """Open the SPI rack, ramp every configured channel to its target voltage,
    set unused channels to 0 (optional), then close the connection.

    All hardware access is on the worker thread so the GUI stays responsive.
    """

    log = pyqtSignal(str)
    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, port: str, baud: int, timeout: float, module: int,
                 voltages_by_dac: dict[int, float], set_unused_to_zero: bool):
        super().__init__()
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.module = module
        self.voltages_by_dac = dict(voltages_by_dac)
        self.set_unused_to_zero = set_unused_to_zero

    def run(self):
        spi = None
        try:
            self.log.emit(f"Opening SPI rack on {self.port} (module={self.module})...")
            from triangle_lattice_quench.Equipment_Drivers.SPIRackvoltage import (
                SPIRack, D5aModule,
            )
            spi = SPIRack(self.port, self.baud, self.timeout)
            d5a = D5aModule(
                spi, module=self.module, reset_voltages=False,
                ramp_step=DEFAULT_D5A_RAMP_STEP,
                ramp_interval=DEFAULT_D5A_RAMP_INTERVAL,
            )

            # Make sure every DAC is on the bipolar 4 V span.
            span = d5a.range_4V_bi
            for i in range(d5a._num_dacs):
                if d5a.get_settings(i)[1] != span:
                    cur = d5a.get_settings(i)[0]
                    d5a.change_span(i, span)
                    d5a.set_voltage(i, cur)

            # Apply target voltages with ramp.
            for dac in sorted(self.voltages_by_dac):
                v = float(self.voltages_by_dac[dac])
                self.log.emit(f"DAC {dac:2d} -> {v:+.4f} V")
                d5a.set_voltage_ramp(int(dac), v)

            if self.set_unused_to_zero:
                used = set(int(d) for d in self.voltages_by_dac)
                for i in range(d5a._num_dacs):
                    if i not in used:
                        d5a.set_voltage(i, 0.0)
                self.log.emit("Unused DACs zeroed.")

            # Read back final voltages for the log.
            self.log.emit("Final readback:")
            for i in range(d5a._num_dacs):
                self.log.emit(f"  DAC {i:2d}: {d5a.get_settings(i)[0]:+.4f} V")

            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(f"{exc}\n\n{traceback.format_exc()}")
        finally:
            if spi is not None:
                try:
                    spi.close()
                except Exception:
                    pass


class D5aCouplerDialog(QDialog):
    """Edit + apply Qblox D5a coupler-bias voltages.

    Two-column form for connection params (port / module / etc.), an editable
    table of (label, DAC, target voltage), Load / Save / Apply buttons, and a
    log pane showing the worker's progress.
    """

    def __init__(self, state: CalibState, parent=None):
        super().__init__(parent)
        self.state = state
        self.worker: Optional[D5aApplyWorker] = None
        self.setWindowTitle("Qblox D5a coupler bias")
        self.resize(720, 720)

        # ---- connection params ----
        conn_box = QGroupBox("SPI rack connection")
        conn_form = QFormLayout(conn_box)
        self.port_edit = QLineEdit(state.d5a_port or DEFAULT_D5A_PORT)
        self.module_spin = QSpinBox(); self.module_spin.setRange(0, 31)
        self.module_spin.setValue(state.d5a_module or DEFAULT_D5A_MODULE)
        self.baud_spin = QSpinBox(); self.baud_spin.setRange(9600, 10_000_000)
        self.baud_spin.setValue(DEFAULT_D5A_BAUD)
        self.timeout_spin = QDoubleSpinBox(); self.timeout_spin.setRange(0.05, 30.0)
        self.timeout_spin.setDecimals(2); self.timeout_spin.setValue(DEFAULT_D5A_TIMEOUT)
        self.zero_unused_check = QCheckBox("Set unused DACs to 0 V on apply")
        self.zero_unused_check.setChecked(True)
        conn_form.addRow("COM port:", self.port_edit)
        conn_form.addRow("Module index:", self.module_spin)
        conn_form.addRow("Baud:", self.baud_spin)
        conn_form.addRow("Timeout (s):", self.timeout_spin)
        conn_form.addRow(self.zero_unused_check)

        # ---- voltage table ----
        table_box = QGroupBox("Channel voltages (span = 4V_bi, +/-4 V)")
        table_layout = QVBoxLayout(table_box)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Label", "DAC", "Target voltage (V)"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.verticalHeader().setVisible(False)
        table_layout.addWidget(self.table, 1)

        # ---- buttons ----
        btn_row = QHBoxLayout()
        self.load_btn = QPushButton("Load voltages...")
        self.load_btn.clicked.connect(self.on_load)
        self.save_btn = QPushButton("Save voltages...")
        self.save_btn.clicked.connect(self.on_save)
        self.reload_default_btn = QPushButton("Reload default")
        self.reload_default_btn.setToolTip(
            "Reload voltages from the project default file "
            f"({DEFAULT_D5A_VOLTAGES_FILE.name})."
        )
        self.reload_default_btn.clicked.connect(self.on_reload_default)
        self.apply_btn = QPushButton("Apply (ramp to targets)")
        self.apply_btn.setStyleSheet("font-weight: bold;")
        self.apply_btn.clicked.connect(self.on_apply)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.load_btn)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.reload_default_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.apply_btn)
        btn_row.addWidget(self.close_btn)
        btn_widget = QWidget(); btn_widget.setLayout(btn_row)

        # ---- log ----
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        st.make_mono(self.log)
        self.log.setPlaceholderText("Apply progress will appear here.")

        layout = QVBoxLayout(self)
        layout.addWidget(conn_box)
        layout.addWidget(table_box, 2)
        layout.addWidget(btn_widget)
        layout.addWidget(self.log, 1)

        # populate from state (or default file if state is empty).
        if not self.state.d5a_voltages:
            self._try_load_default_silently()
        self._populate_table()

    # ---- helpers ----

    def _try_load_default_silently(self):
        try:
            volts = load_d5a_voltages_from_file(str(DEFAULT_D5A_VOLTAGES_FILE))
            self.state.d5a_voltages = volts
            self.state.d5a_voltages_path = str(DEFAULT_D5A_VOLTAGES_FILE)
        except Exception as exc:
            self.log.appendPlainText(f"[default load failed] {exc}")

    def _populate_table(self):
        labels = sorted(
            self.state.d5a_dac_map.keys(),
            key=lambda lbl: self.state.d5a_dac_map.get(lbl, 1 << 30),
        )
        self.table.setRowCount(len(labels))
        for r, lbl in enumerate(labels):
            label_item = QTableWidgetItem(lbl)
            label_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(r, 0, label_item)
            dac_item = QTableWidgetItem(str(self.state.d5a_dac_map[lbl]))
            dac_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(r, 1, dac_item)
            v = self.state.d5a_voltages.get(lbl, 0.0)
            v_item = QTableWidgetItem(f"{float(v):+.4f}")
            self.table.setItem(r, 2, v_item)
        self.table.resizeColumnsToContents()

    def _read_table_into_state(self) -> None:
        """Read every editable cell into self.state.d5a_voltages, raising on bad input."""
        new_volts: dict[str, float] = {}
        for r in range(self.table.rowCount()):
            lbl = self.table.item(r, 0).text()
            txt = self.table.item(r, 2).text().strip()
            if txt == "":
                continue
            try:
                v = float(txt)
            except ValueError:
                raise ValueError(f"Row {r+1} ({lbl}): cannot parse {txt!r} as a float.")
            if abs(v) > 4.0 + 1e-6:
                raise ValueError(
                    f"Row {r+1} ({lbl}): {v:+.4f} V is outside the +/-4 V span."
                )
            new_volts[lbl] = v
        self.state.d5a_voltages = new_volts

    def _voltages_by_dac(self) -> dict[int, float]:
        return {
            int(self.state.d5a_dac_map[lbl]): float(v)
            for lbl, v in self.state.d5a_voltages.items()
            if lbl in self.state.d5a_dac_map
        }

    # ---- handlers ----

    def on_load(self):
        start_dir = ""
        if self.state.d5a_voltages_path and Path(self.state.d5a_voltages_path).exists():
            start_dir = str(Path(self.state.d5a_voltages_path).parent)
        elif DEFAULT_D5A_VOLTAGES_FILE.parent.exists():
            start_dir = str(DEFAULT_D5A_VOLTAGES_FILE.parent)
        path, _ = QFileDialog.getOpenFileName(
            self, "Load D5a voltages", start_dir, "Python or JSON (*.py *.json)"
        )
        if not path:
            return
        try:
            volts = load_d5a_voltages_from_file(path)
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", f"{exc}")
            return
        self.state.d5a_voltages = volts
        self.state.d5a_voltages_path = path
        self._populate_table()
        self.log.appendPlainText(f"Loaded {len(volts)} voltages from {path}")

    def on_reload_default(self):
        try:
            volts = load_d5a_voltages_from_file(str(DEFAULT_D5A_VOLTAGES_FILE))
        except Exception as exc:
            QMessageBox.critical(self, "Default load failed", f"{exc}")
            return
        self.state.d5a_voltages = volts
        self.state.d5a_voltages_path = str(DEFAULT_D5A_VOLTAGES_FILE)
        self._populate_table()
        self.log.appendPlainText(f"Loaded default ({DEFAULT_D5A_VOLTAGES_FILE.name})")

    def on_save(self):
        try:
            self._read_table_into_state()
        except Exception as exc:
            QMessageBox.warning(self, "Invalid value", str(exc))
            return
        start_path = ""
        if self.state.d5a_voltages_path:
            stem = Path(self.state.d5a_voltages_path).stem
            start_path = str(Path(self.state.d5a_voltages_path).with_name(f"{stem}.json"))
        path, _ = QFileDialog.getSaveFileName(
            self, "Save D5a voltages", start_path or "d5a_voltages.json",
            "JSON (*.json)"
        )
        if not path:
            return
        payload = {"voltages": self.state.d5a_voltages,
                   "dac_map": self.state.d5a_dac_map}
        try:
            with open(path, "w") as fh:
                dump_pretty(payload, fh)
            self.log.appendPlainText(f"Saved to {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def on_apply(self):
        if self.worker is not None and self.worker.isRunning():
            return
        try:
            self._read_table_into_state()
        except Exception as exc:
            QMessageBox.warning(self, "Invalid value", str(exc))
            return
        self.state.d5a_port = self.port_edit.text().strip() or DEFAULT_D5A_PORT
        self.state.d5a_module = int(self.module_spin.value())
        baud = int(self.baud_spin.value())
        timeout = float(self.timeout_spin.value())
        zero_unused = self.zero_unused_check.isChecked()
        v_by_dac = self._voltages_by_dac()
        if not v_by_dac:
            QMessageBox.warning(self, "Empty voltage list",
                                "No DACs to apply. Load or enter voltages first.")
            return
        self.apply_btn.setEnabled(False)
        self.load_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.reload_default_btn.setEnabled(False)
        self.log.appendPlainText("--- Apply started ---")
        self.worker = D5aApplyWorker(
            port=self.state.d5a_port, baud=baud, timeout=timeout,
            module=self.state.d5a_module,
            voltages_by_dac=v_by_dac, set_unused_to_zero=zero_unused,
        )
        self.worker.log.connect(self.log.appendPlainText)
        self.worker.finished_ok.connect(self._on_finished_ok)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_finished_ok(self):
        from datetime import datetime
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.state.d5a_last_applied_at = ts
        set_d5a_settings(
            voltages_path=self.state.d5a_voltages_path,
            port=self.state.d5a_port,
            module=self.state.d5a_module,
            last_applied_at=ts,
        )
        self.log.appendPlainText(f"--- Apply OK at {ts} ---")
        self._reenable_buttons()
        # Tell the parent main window so the toolbar status updates.
        parent = self.parent()
        if parent is not None and hasattr(parent, "_refresh_d5a_status"):
            try:
                parent._refresh_d5a_status()
            except Exception:
                pass

    def _on_failed(self, msg: str):
        QMessageBox.critical(self, "D5a apply failed", msg)
        self.log.appendPlainText("--- Apply FAILED ---")
        self._reenable_buttons()

    def _reenable_buttons(self):
        self.apply_btn.setEnabled(True)
        self.load_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.reload_default_btn.setEnabled(True)
        self.worker = None


# ---------------------------------------------------------------------------
# Connection dialog — Pyro4 nameserver / RFSoC proxy / channel mapping
# ---------------------------------------------------------------------------


# Defaults for the nameserver address. Edit here or override in the dialog.
DEFAULT_NS_HOST = "192.168.1.104"  # matches socProxy.py
DEFAULT_NS_PORT = 8888
DEFAULT_SERVER_NAME = "myqick"


CONNECT_TIMEOUT_S = 15.0   # per-proxy timeout for the get_cfg() call of one attempt


def pyro_connect(host: str, port: int, name: str):
    """Blocking lookup + get_cfg; returns (soc, soccfg, cfg_dict). Runs on a worker thread."""
    import Pyro4
    from qick import QickConfig
    Pyro4.config.SERIALIZER = "pickle"
    Pyro4.config.PICKLE_PROTOCOL_VERSION = 4
    ns = Pyro4.locateNS(host=host, port=port)
    soc = Pyro4.Proxy(ns.lookup(name))
    soc._pyroTimeout = CONNECT_TIMEOUT_S      # this proxy only; cleared so long acquire() calls are unaffected
    cfg_dict = soc.get_cfg()
    soc._pyroTimeout = None
    return soc, QickConfig(cfg_dict), cfg_dict


class ConnectionController(QObject):
    """One RFSoC connection attempt at a time, on a daemon thread.

    A blocked Pyro call cannot be interrupted, so abort() / a newer connect_to() just bump a
    generation counter and the stale attempt's result is dropped when it finally arrives.
    """
    started = pyqtSignal(str)
    succeeded = pyqtSignal(object, object, dict, dict)   # soc, soccfg, cfg_dict, {host, port, name}
    failed = pyqtSignal(str)
    aborted = pyqtSignal()
    disconnected = pyqtSignal()
    _result = pyqtSignal(int, bool, object)

    def __init__(self, connector=None, parent=None):
        super().__init__(parent)
        self._connector = connector or pyro_connect
        self._gen = 0
        self.pending = False
        self.params: dict = {}
        self._result.connect(self._on_result)

    def connect_to(self, host: str, port: int, name: str) -> None:
        """Start an attempt; one already in flight is abandoned (its result will be ignored)."""
        self._gen += 1
        self.pending = True
        self.params = {"host": host, "port": int(port), "name": name}
        self.started.emit(f"Connecting to '{name}' at {host}:{int(port)}...")
        threading.Thread(target=self._work, args=(self._gen, host, int(port), name),
                         daemon=True, name="rfsoc-connect").start()

    def _work(self, gen: int, host: str, port: int, name: str) -> None:
        try:
            ok, payload = True, self._connector(host, port, name)
        except Exception as exc:
            ok, payload = False, f"{type(exc).__name__}: {exc}"
        self._result.emit(gen, ok, payload)

    def _on_result(self, gen: int, ok: bool, payload) -> None:
        if gen != self._gen:
            return                                 # aborted or superseded
        self.pending = False
        if ok:
            soc, soccfg, cfg_dict = payload
            self.succeeded.emit(soc, soccfg, cfg_dict, dict(self.params))
        else:
            self.failed.emit(str(payload))

    def abort(self) -> None:
        if self.pending:
            self._gen += 1
            self.pending = False
            self.aborted.emit()

    def disconnect_(self) -> None:
        self._gen += 1
        self.pending = False
        self.disconnected.emit()


def saved_connection_params() -> dict:
    """Host / port / proxy name of the previous session (the defaults when there is none)."""
    s = get_settings()
    return {"host": str(s.value(SETTING_NS_HOST, DEFAULT_NS_HOST, type=str) or DEFAULT_NS_HOST),
            "port": int(s.value(SETTING_NS_PORT, DEFAULT_NS_PORT, type=int) or DEFAULT_NS_PORT),
            "name": str(s.value(SETTING_PROXY_NAME, DEFAULT_SERVER_NAME, type=str) or DEFAULT_SERVER_NAME)}


def save_connection_params(host: str, port: int, name: str) -> None:
    s = get_settings()
    s.setValue(SETTING_NS_HOST, host)
    s.setValue(SETTING_NS_PORT, int(port))
    s.setValue(SETTING_PROXY_NAME, name)


def default_channel_map() -> dict:
    ff = [int(c) for c in DEFAULT_BASE_CONFIG["fast_flux_chs"]]
    return {"res_ch": int(DEFAULT_BASE_CONFIG["res_ch"]), "qubit_ch": int(DEFAULT_BASE_CONFIG["qubit_ch"]),
            "n_qubits": len(ff), "ff_channels": ff}


def initial_channel_map() -> dict:
    """The channel map applied last time, else the BaseConfig defaults."""
    try:
        m = json.loads(str(get_settings().value(SETTING_CHANNEL_MAP, "", type=str) or ""))
        ff = [int(c) for c in m["ff_channels"]]
        n = int(m["n_qubits"])
        if len(ff) == n and 1 <= n <= len(DEFAULT_BASE_CONFIG["fast_flux_chs"]):
            return {"res_ch": int(m["res_ch"]), "qubit_ch": int(m["qubit_ch"]), "n_qubits": n, "ff_channels": ff}
    except Exception:
        pass
    return default_channel_map()


def state_from_channel_map(cmap: dict) -> CalibState:
    """A disconnected CalibState (soc/soccfg unset) carrying this channel map."""
    base = copy.deepcopy(DEFAULT_BASE_CONFIG)
    n = int(cmap["n_qubits"])
    base.update(res_ch=int(cmap["res_ch"]), qubit_ch=int(cmap["qubit_ch"]),
                ro_chs=list(range(n)), fast_flux_chs=list(cmap["ff_channels"]))
    return CalibState(base_config=base, ff_qubits=make_default_ff_qubits(n, cmap["ff_channels"]), n_qubits=n)


def apply_channel_map(state: CalibState, cmap: dict) -> bool:
    """Update the channel map of a live state in place (tabs keep their reference).

    The qubit COUNT is fixed once the tabs are built: returns False, leaving the FF map alone,
    when cmap asks for a different one (restart needed)."""
    state.base_config["res_ch"] = int(cmap["res_ch"])
    state.base_config["qubit_ch"] = int(cmap["qubit_ch"])
    if int(cmap["n_qubits"]) != state.n_qubits:
        return False
    state.base_config["fast_flux_chs"] = list(cmap["ff_channels"])
    for i, ch in enumerate(cmap["ff_channels"]):
        state.ff_qubits.setdefault(str(i + 1), {})["channel"] = int(ch)
    return True


class ConnectionDialog(QDialog):
    """RFSoC connection panel: nameserver lookup, proxy, channel map. Opened on demand.

    The connection itself is made by the shared :class:`ConnectionController` (background
    thread, abortable); this panel edits the parameters, starts / aborts attempts, shows their
    status, and emits ``channel_map_applied`` when Apply is pressed.
    """

    channel_map_applied = pyqtSignal(dict)

    def __init__(self, controller: ConnectionController, state: CalibState, busy_check=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RFSoC connection — nameserver & channel map")
        self.resize(1000, 780)

        self.ctrl = controller
        self.state = state
        self._busy_check = busy_check or (lambda: False)   # True while an experiment is running
        self._seed = {"res_ch": int(state.base_config["res_ch"]), "qubit_ch": int(state.base_config["qubit_ch"]),
                      "n_qubits": int(state.n_qubits),
                      "ff_channels": [int(c) for c in state.base_config["fast_flux_chs"]]}
        self._gens: list = []
        self.ns: Any = None

        # cached so we know how many channels are available for the dropdowns
        self.n_gens = 0
        self.n_readouts = 0

        # ---- Nameserver group ----
        ns_box = QGroupBox("Pyro4 nameserver")
        ns_form = QFormLayout()
        _saved = saved_connection_params()  # the previous session's values (else the constants)
        self.host_edit = QLineEdit(_saved["host"])
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(_saved["port"])
        self.list_btn = QPushButton("List nameserver entries")
        self.list_btn.clicked.connect(self.on_list_ns)
        self.ns_list = QListWidget()
        self.ns_list.itemSelectionChanged.connect(self.on_ns_item_selected)
        ns_form.addRow("Host:", self.host_edit)
        ns_form.addRow("Port:", self.port_spin)
        ns_form.addRow(self.list_btn)
        ns_form_widget = QWidget()
        ns_form_widget.setLayout(ns_form)
        ns_layout = QVBoxLayout(ns_box)
        ns_layout.addWidget(ns_form_widget)
        ns_layout.addWidget(QLabel("Registered names (click to select):"))
        ns_layout.addWidget(self.ns_list, 1)

        # ---- Proxy group ----
        proxy_box = QGroupBox("RFSoC proxy")
        proxy_form = QFormLayout(proxy_box)
        self.proxy_name_edit = QLineEdit(_saved["name"])
        self.connect_btn = QPushButton("Connect to RFSoC")
        self.connect_btn.clicked.connect(self.on_connect)
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self.on_disconnect)
        self.disconnect_btn.setEnabled(False)
        self.connection_status = QLabel("Not connected.")
        self.connection_status.setWordWrap(True)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.connect_btn)
        btn_row.addWidget(self.disconnect_btn)
        btn_row.addStretch(1)
        btn_row_widget = QWidget(); btn_row_widget.setLayout(btn_row)
        proxy_form.addRow("Proxy name:", self.proxy_name_edit)
        proxy_form.addRow(btn_row_widget)
        proxy_form.addRow("Status:", self.connection_status)

        # ---- soccfg description ----
        cfg_box = QGroupBox("soccfg description (read-only)")
        cfg_layout = QVBoxLayout(cfg_box)
        self.cfg_view = QPlainTextEdit()
        self.cfg_view.setReadOnly(True)
        st.make_mono(self.cfg_view)
        cfg_layout.addWidget(self.cfg_view)

        # ---- Channels (editable; defaults from BaseConfig) ----
        # Dropdowns are pre-populated from DEFAULT_BASE_CONFIG so the dialog is
        # functional before the user connects (99% of users will accept the
        # defaults and click Continue). On connect, the combos are repopulated
        # from cfg_dict['gens'] with richer fs/type labels, with the previous
        # selection restored by data value via _select_combo_value.
        # NOTE: no ADC combo — for MUX firmware, ro_chs is derived from
        # n_qubits (first n MUXed ADC channels of the 8-channel readout).
        chan_box = QGroupBox("Channels (editable; defaults from BaseConfig)")
        chan_layout = QVBoxLayout(chan_box)

        shared_form = QFormLayout()
        self.res_ch_combo = QComboBox()
        self.qubit_ch_combo = QComboBox()
        shared_form.addRow("Readout DAC channel (shared, MUX):", self.res_ch_combo)
        shared_form.addRow("Qubit DAC channel (shared, MUX):",   self.qubit_ch_combo)
        shared_widget = QWidget(); shared_widget.setLayout(shared_form)
        chan_layout.addWidget(shared_widget)

        # Number of qubits = number of MUXed readouts to use.
        nq_row = QHBoxLayout()
        nq_row.addWidget(QLabel("Number of qubits (= MUXed readouts to enable):"))
        self.n_qubits_spin = QSpinBox()
        self.n_qubits_spin.setRange(1, len(DEFAULT_BASE_CONFIG["fast_flux_chs"]))
        self.n_qubits_spin.setValue(self._seed["n_qubits"])
        self.n_qubits_spin.valueChanged.connect(self.on_n_qubits_changed)
        nq_row.addWidget(self.n_qubits_spin)
        nq_row.addStretch(1)
        nq_widget = QWidget(); nq_widget.setLayout(nq_row)
        chan_layout.addWidget(nq_widget)

        # Per-qubit FF DAC channel table (one row per qubit, combo per row).
        self.qubit_table = QTableWidget(0, 2)
        self.qubit_table.setHorizontalHeaderLabels(["Qubit", "FF DAC channel"])
        self.qubit_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.qubit_table.verticalHeader().setVisible(False)
        chan_layout.addWidget(self.qubit_table, 1)

        # Derived ro_chs display (updates when n_qubits changes).
        self.ro_chs_label = QLabel()
        chan_layout.addWidget(self.ro_chs_label)

        chan_hint = QLabel(
            "Defaults come from BaseConfig (MUXInitialize.py). Firmware MUXes "
            "ADC channels 0–7; ro_chs is derived as the first n_qubits of "
            "those (not user-editable here). After connecting to the RFSoC, "
            "the combos refresh with fs/type labels from the live soccfg."
        )
        chan_hint.setWordWrap(True)
        chan_hint.setStyleSheet("color: #555;")
        chan_layout.addWidget(chan_hint)

        # Seed all combos from DEFAULT_BASE_CONFIG so the dialog is usable
        # before the user connects (no soccfg available yet).
        self._populate_channel_combos_from_defaults()

        # ---- Continue / Cancel ----
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.button_box.button(QDialogButtonBox.Ok).setText("Apply channel map")
        self.button_box.accepted.connect(self.on_accept)
        self.button_box.rejected.connect(self.reject)

        # ---- Layout (left = ns/proxy, right = soccfg + channels) ----
        left = QVBoxLayout()
        left.addWidget(ns_box, 1)
        left.addWidget(proxy_box)
        left_w = QWidget(); left_w.setLayout(left)

        right = QVBoxLayout()
        right.addWidget(cfg_box, 1)
        right.addWidget(chan_box, 1)
        right_w = QWidget(); right_w.setLayout(right)

        splitter = QSplitter()
        splitter.addWidget(left_w)
        splitter.addWidget(right_w)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        outer = QVBoxLayout(self)
        outer.addWidget(splitter, 1)
        outer.addWidget(self.button_box)

        # initial empty table
        self.on_n_qubits_changed(self.n_qubits_spin.value())

        self.ctrl.started.connect(self._on_started)
        self.ctrl.succeeded.connect(self._on_succeeded)
        self.ctrl.failed.connect(self._on_failed)
        self.ctrl.aborted.connect(self._on_aborted)
        self.ctrl.disconnected.connect(self._on_disconnected)
        self._refresh_buttons()

    # ------------------ nameserver / proxy actions ------------------

    def _busy(self, msg: str):
        self.connection_status.setText(msg)
        QApplication.processEvents()

    def on_list_ns(self):
        host = self.host_edit.text().strip()
        port = int(self.port_spin.value())
        try:
            import Pyro4
        except ImportError as exc:
            QMessageBox.critical(self, "Pyro4 missing", str(exc))
            return
        Pyro4.config.SERIALIZER = "pickle"
        Pyro4.config.PICKLE_PROTOCOL_VERSION = 4
        self._busy(f"Locating nameserver at {host}:{port}...")
        try:
            ns = Pyro4.locateNS(host=host, port=port)
            entries = ns.list()
        except Exception as exc:
            QMessageBox.critical(self, "Nameserver error",
                                 f"Could not reach Pyro4 NS at {host}:{port}:\n{exc}")
            self.connection_status.setText("Nameserver unreachable.")
            return
        self.ns = ns
        self.ns_list.clear()
        # Sort with likely-soc names on top
        def rank(name: str) -> int:
            n = name.lower()
            if "qick" in n or "soc" in n:
                return 0
            if name.startswith("Pyro.NameServer"):
                return 2
            return 1
        for name in sorted(entries, key=lambda n: (rank(n), n)):
            uri = entries[name]
            item = QListWidgetItem(f"{name}    =>    {uri}")
            item.setData(Qt.UserRole, name)
            self.ns_list.addItem(item)
        self.connection_status.setText(
            f"Nameserver OK — {len(entries)} entries. Pick one and Connect."
        )

    def on_ns_item_selected(self):
        items = self.ns_list.selectedItems()
        if not items:
            return
        name = items[0].data(Qt.UserRole)
        if name and not name.startswith("Pyro.NameServer"):
            self.proxy_name_edit.setText(name)

    def on_connect(self):
        """Start (or restart) a background connection with the parameters shown; an attempt
        already in flight is abandoned."""
        if self._busy_check():
            QMessageBox.information(self, "Experiment running",
                                    "Stop the running experiment before changing the connection.")
            return
        name = self.proxy_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing name",
                                "Enter a Pyro4 proxy name (or pick one from the list).")
            return
        host, port = self.host_edit.text().strip(), int(self.port_spin.value())
        save_connection_params(host, port, name)
        self.ctrl.connect_to(host, port, name)

    def on_disconnect(self):
        """"Abort" while an attempt is pending, "Disconnect" once connected."""
        if self.ctrl.pending:
            self.ctrl.abort()
            return
        if self._busy_check():
            QMessageBox.information(self, "Experiment running",
                                    "Stop the running experiment before disconnecting.")
            return
        self.ctrl.disconnect_()

    def _refresh_buttons(self) -> None:
        pending, connected = self.ctrl.pending, self.state.is_connected()
        self.connect_btn.setEnabled(True)           # always: restarts an attempt / reconnects
        self.disconnect_btn.setText("Abort" if pending else "Disconnect")
        self.disconnect_btn.setEnabled(pending or connected)

    def _on_started(self, msg: str) -> None:
        self.connection_status.setText(msg + " (Abort to stop, or Connect again with new parameters)")
        self._refresh_buttons()

    def _on_failed(self, msg: str) -> None:
        self.connection_status.setText(f"Connect failed: {msg}")
        self._refresh_buttons()

    def _on_aborted(self) -> None:
        self.connection_status.setText("Connection attempt aborted.")
        self._refresh_buttons()

    def _on_disconnected(self) -> None:
        self.cfg_view.clear()
        self.connection_status.setText("Disconnected.")
        self._refresh_buttons()

    def _on_succeeded(self, soc, soccfg, cfg_dict: dict, params: dict) -> None:
        """Show the soccfg and relabel the channel combos with the live gens (selections kept).
        MainWindow stores soc / soccfg in the shared state; this only updates the panel."""
        self.connection_status.setText(
            f"Connected to '{params['name']}' at {params['host']}:{params['port']}.")
        try:
            self.cfg_view.setPlainText(soccfg.description())
        except Exception:
            self.cfg_view.setPlainText(repr(cfg_dict))

        gens = cfg_dict.get("gens", []) or []
        self._gens = list(gens)

        # Capture prior selections so we can restore them after clear/refill.
        prev_res = self.res_ch_combo.currentData()
        prev_qubit = self.qubit_ch_combo.currentData()
        prev_ff: list = []
        for i in range(self.qubit_table.rowCount()):
            w = self.qubit_table.cellWidget(i, 1)
            prev_ff.append(w.currentData() if w is not None else None)

        def _gen_label(i: int, gen: dict) -> str:
            return f"{i}: {gen.get('type', '?')} fs={gen.get('fs', '?')} MHz"

        for combo in (self.res_ch_combo, self.qubit_ch_combo):
            combo.blockSignals(True)
            combo.clear()
            for i, gen in enumerate(gens):
                combo.addItem(_gen_label(i, gen), i)
            combo.blockSignals(False)
        self._select_combo_value(
            self.res_ch_combo, prev_res if prev_res is not None else self._seed["res_ch"])
        self._select_combo_value(
            self.qubit_ch_combo, prev_qubit if prev_qubit is not None else self._seed["qubit_ch"])
        self._populate_qubit_table(prev_ff=prev_ff)
        self.on_n_qubits_changed(self.n_qubits_spin.value())
        self._refresh_buttons()

    def on_n_qubits_changed(self, n: int):
        # ro_chs = first n MUXed ADC channels of the 8-channel firmware.
        ro_chs = list(range(n))
        self.ro_chs_label.setText(f"<b>ro_chs (derived):</b> {ro_chs}")
        # Resize the per-qubit FF table to match n; preserve existing combos'
        # data values so changing n doesn't reset user picks for unchanged rows.
        prev_ff: list[int | None] = []
        for i in range(self.qubit_table.rowCount()):
            w = self.qubit_table.cellWidget(i, 1)
            prev_ff.append(w.currentData() if w is not None else None)
        self._populate_qubit_table(prev_ff=prev_ff)

    @staticmethod
    def _select_combo_value(combo: QComboBox, value):
        """Select the combo entry whose data() == value, if it exists."""
        if value is None:
            return
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _populate_channel_combos_from_defaults(self) -> None:
        """Seed res/qubit/per-qubit FF combos from DEFAULT_BASE_CONFIG.

        Used at dialog construction (no soccfg yet) and as a fallback path.
        Items carry the int channel as their data so currentData() works
        identically before and after a connect (where the labels become
        richer fs/type strings but the data values stay the same).
        """
        default_ff_chs = list(self._seed["ff_channels"])
        # The two shared combos: list every plausible channel index. We don't
        # have a soccfg yet, so use the union of BaseConfig's res/qubit/FF
        # channels — enough to surface the default and any sibling channel
        # the user might want to pick before connecting.
        candidate_chs = sorted(set(
            [int(self._seed["res_ch"]),
             int(self._seed["qubit_ch"])]
            + [int(c) for c in default_ff_chs]
            + [int(c) for c in DEFAULT_BASE_CONFIG["fast_flux_chs"]]
        ))
        for combo in (self.res_ch_combo, self.qubit_ch_combo):
            combo.blockSignals(True)
            combo.clear()
            for ch in candidate_chs:
                combo.addItem(f"ch {ch} (BaseConfig default)", ch)
            combo.blockSignals(False)
        self._select_combo_value(self.res_ch_combo, int(self._seed["res_ch"]))
        self._select_combo_value(self.qubit_ch_combo, int(self._seed["qubit_ch"]))
        # Build the FF rows for the initial n_qubits.
        self._populate_qubit_table(prev_ff=None)

    def _populate_qubit_table(self, prev_ff: Optional[list] = None) -> None:
        """(Re)build the per-qubit FF combo table to match n_qubits_spin.

        Each row's combo is populated from the live gens list when connected,
        else from DEFAULT_BASE_CONFIG['fast_flux_chs']. `prev_ff[i]` (data
        value, int or None) is used to restore row i's selection; if missing,
        the default per-qubit FF channel from BaseConfig is used.
        """
        n = int(self.n_qubits_spin.value())
        default_ff_chs = list(self._seed["ff_channels"])
        gens = self._gens          # from the last successful connect (empty before the first)

        self.qubit_table.setRowCount(n)
        for i in range(n):
            label_item = QTableWidgetItem(f"Q{i + 1}")
            label_item.setFlags(Qt.ItemIsEnabled)
            self.qubit_table.setItem(i, 0, label_item)
            existing = self.qubit_table.cellWidget(i, 1)
            combo = existing if isinstance(existing, QComboBox) else QComboBox()
            if existing is None:
                self.qubit_table.setCellWidget(i, 1, combo)
            combo.blockSignals(True)
            combo.clear()
            if gens:
                for j, gen in enumerate(gens):
                    combo.addItem(
                        f"{j}: {gen.get('type', '?')} fs={gen.get('fs', '?')} MHz",
                        j,
                    )
            else:
                # Pre-connect: list BaseConfig's FF channels as candidates so
                # the user can change a mapping before connecting if needed.
                for ch in sorted(set(int(c) for c in default_ff_chs) | set(int(c) for c in DEFAULT_BASE_CONFIG["fast_flux_chs"])):
                    combo.addItem(f"ch {ch} (BaseConfig default)", ch)
            combo.blockSignals(False)
            # Restore prior data, else fall back to BaseConfig default for Q_i.
            prev_val = prev_ff[i] if (prev_ff is not None and i < len(prev_ff)) else None
            if prev_val is not None:
                self._select_combo_value(combo, int(prev_val))
            else:
                default_ch = int(default_ff_chs[i]) if i < len(default_ff_chs) else i
                self._select_combo_value(combo, default_ch)

    # ------------------ accept ------------------

    def channel_map(self) -> Optional[dict]:
        """The channel map as currently entered, or None (after a warning) when incomplete."""
        n_qubits = int(self.n_qubits_spin.value())
        ff_channels: list[int] = []
        for i in range(n_qubits):
            combo = self.qubit_table.cellWidget(i, 1)
            if combo is None or combo.currentData() is None:
                QMessageBox.warning(self, "Missing FF channel", f"Q{i + 1} has no FF DAC channel selected.")
                return None
            ff_channels.append(int(combo.currentData()))
        return {"res_ch": int(self.res_ch_combo.currentData()), "qubit_ch": int(self.qubit_ch_combo.currentData()),
                "n_qubits": n_qubits, "ff_channels": ff_channels}

    def on_accept(self):
        """Apply the channel map to the live state (and remember it), then close the panel."""
        cmap = self.channel_map()
        if cmap is None:
            return
        # Warn (don't block) on duplicate FF channel assignments: the firmware accepts it,
        # but it is almost always a mistake.
        if len(set(cmap["ff_channels"])) != len(cmap["ff_channels"]):
            res = QMessageBox.question(
                self, "Duplicate FF channels",
                "Two or more qubits are assigned to the same FF DAC channel. Apply anyway?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if res != QMessageBox.Yes:
                return
        get_settings().setValue(SETTING_CHANNEL_MAP, json.dumps(cmap))
        self.channel_map_applied.emit(cmap)
        self.accept()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
