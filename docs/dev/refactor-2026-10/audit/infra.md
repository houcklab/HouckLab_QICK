# Audit: infra group

Root: `WorkingProjects/QM_Team/qubit_measurements/Client_modules` (abbrev. `CM/`). Python 3.13.5, h5py 3.15.1, numpy 2.4.1.
All 10 importable modules import cleanly (`control_atten` not import-tested: it calls `os.add_dll_directory` at import).

## Repo-level facts (group-specific asks)

- **Tracked non-.py files under `WorkingProjects/`: none.** `git ls-files WorkingProjects` = 52 files, all `.py`. Only `__init__.py` is `CM/Runners/runs/__init__.py`; every other dir (CoreLib, Calib, PythonDrivers, Experiments, Helpers) is an implicit namespace package.
- Repo-wide tracked non-.py (outside WorkingProjects, for context): `.claude/settings.local.json`, `.claude/worktrees/tender-buck-5ad471` (gitlink, deleted in working tree), `.env`, `.gitattributes`, `.gitignore`, `.vscode/settings.json`, `AGENTS.md`, `CLAUDE.md`, `README`. `MasterProject/` is **not** in the repo (61 tracked files total), so CLAUDE.md's MasterProject/LAKE_GUI/`192.168.1.7` content is stale.
- **No `.dll` anywhere** in the repo or on disk under WorkingProjects (`VNX_atten64.dll` absent). `PythonDrivers/` contains only the 3 `.py` files + `__pycache__`.
- **`os.add_dll_directory` dance:** only `PythonDrivers/control_atten.py:6` (`os.add_dll_directory(os.getcwd())`, at import time, CWD-dependent). Nothing in the tree imports `control_atten`, so no module currently needs it. No runner contains the `os.add_dll_directory(...'\\PythonDrivers')` line CLAUDE.md describes.
- Deps present in .venv: Pyro4, Pyro5, pywindfreak, pyvisa, qick, h5py; `distutils` only via setuptools shim (removed from stdlib in 3.12).

---

## 1. CoreLib/Experiment.py (185 lines)

**Purpose:** base `ExperimentClass` (file naming, cfg→JSON/h5 attr, h5 dataset save) + `MakeFile` h5py wrapper + `NpEncoder`.

**Public symbols**
| symbol | description | external use |
|---|---|---|
| `MakeFile(h5py.File)` L8 | h5py.File subclass; `add(key, data)` creates resizable float64 dataset and writes | internal only (unused externally) |
| `NpEncoder(json.JSONEncoder)` L38 | JSON encoder for np int/float/ndarray | internal only (unused externally) |
| `ExperimentClass` L49 | base class; subclassed by 19 experiment modules | imported by mActiveResetVerify, mAmplitudeRabiFF, mAmplitudeRabiFF_noUpdate, mChargeDispersion, mChargeDispersionQuasiCW, mChiShift, mConstantTwoTone, mModifiedRamsey, mOptimizeReadoutandPulse_FF, mSingleShotProgramFFMUX, mSingleTone, mSpecSliceFF, mT1FF, mT1_SS, mT2EFF, mT2R, mTransmissionFF, mUndrivenSingleShot, mZeroSpanParity |
| `.save_config()` L122 | writes `self.cfg` to `.json` (cname) and h5 attr `config` (fname) | ~40 call sites in runs/* + mAutoCoherence (called unbound: `Cls.save_config(inst)`) |
| `.datafile(group, remote, data_file, swmr)` L128 | opens `MakeFile(fname,'a')` | internal only; params `group/remote/swmr` unused |
| `.go()` L152 | acquire→analyze→save→display | **dead** (no caller) |
| `.acquire/.analyze/.display` L163-170 | stubs overridden by subclasses | — |
| `.save_data(data=None)` L172 | `f.add(k, np.array(d))` for each item | many (subclasses call super) |
| `.load_data(f)` L180 | reads all datasets + `f.get_dict()` | **dead** and broken (h5py File has no `get_dict`) |

**cfg keys:** none read/written; `self.cfg` stored and serialized whole.

**File naming / pathing — MUST be preserved byte-for-byte** (L65-94):
```
self.__dict__.update(kwargs)            # FIRST; explicit attrs below override kwargs (e.g. progress=... survives)
now = datetime.datetime.now()           # one timestamp for all 3 files
datetimestring = now.strftime("%Y_%m_%d_%H_%M_%S")
datestring     = now.strftime("%Y_%m_%d")
dir   = os.path.join(outerFolder + path, path + "_" + datestring)     # NOTE string concat, no separator
os.makedirs(dir, exist_ok=True)                                         # side effect in __init__
fname = os.path.join(outerFolder + path, path + "_" + datestring, path + "_" + datetimestring + "_" + prefix + ".h5")
iname = ... same ... + ".png"
cname = ... same ... + ".json"
titlename = path + "_" + datetimestring
config_file = os.path.join(path, config_file) if given else None       # stored, never used
```
Defaults: `path=''`, `outerFolder=''`, `prefix='data'`, `liveplot_enabled` ignored.
Concrete example (CSTQ03 runner: `outerFolder = "V:/t1Team/Data/2026-10-01_BFC_cooldown/CSTQ03/RFSOC/Q1//"`, `path="TransmissionFF"`) →
`V:/t1Team/Data/2026-10-01_BFC_cooldown/CSTQ03/RFSOC/Q1//TransmissionFF\TransmissionFF_2026_10_13\TransmissionFF_2026_10_13_14_03_22_data.h5`
(mixed `/`, `//`, `\` is what is on disk today; a refactor must keep `outerFolder + path` concatenation and `os.path.join` on Windows; do not switch to `pathlib` normalisation or the strings change — harmless for the filesystem but changes `fname` strings saved/printed and any code that string-compares them).
Attribute use outside the class: `.fname` (20 files), `.iname` (16), `.titlename` (14), `.cname` (0 outside), `.prefix`/`.config_file` (0).

**h5 write semantics (MakeFile.add L25-36):** dtype is always `'float64'` (`str(data.astype(np.float64).dtype)`); shape resizable (`maxshape=(None,)*ndim`). Verified on h5py 3.15.1: duplicate `create_dataset` raises **ValueError**, not `RuntimeError` → the `except RuntimeError` overwrite branch (L31-35) is unreachable; re-saving an existing key raises. Complex arrays: `astype(float64)` warns, then write of complex into float dataset raises `ValueError`. String arrays raise in `astype`.

**Dead code:** L11-22 (commented save_script), L79-82 (InstrumentManager/LivePlot), L95 (print), L96-121 (commented `load_config`), L135-149 (commented SlabFile/swmr), `go()` L152-161, `load_data()` L180-185, `config_file` attr, `liveplot_enabled`, `datafile` params `group/remote/swmr`.

**Lab notes:** L16 "Automatic [script-into-h5] feature taken out. Caused more trouble than convenience. Ge Yang" → architecture (one line: scripts are intentionally not embedded in .h5).

**Noise:** L11-15, L17-22, L55-63 (stale docstring: InstrumentManager/LivePlotter), L79-82, L84-86, L93, L95-121, L129-130 (stale "SlabFile" docstring), L135-149, L153, L172 trailing comment.

**Bugs**
- L123 `if self.cname[:-3] != '.h5'` — slices off the extension instead of `[-3:]`; always True (harmless, but meaningless).
- L125 trailing comma after `json.dump(...)` (creates a discarded tuple).
- L126 `self.datafile().attrs[...]` opens h5 in `'a'` and never closes it explicitly (relies on CPython refcount GC).
- L31 `except RuntimeError` never catches h5py ≥3 "name already exists" (ValueError) → overwrite path dead; second `save_data` with same key crashes.
- L30 forced float64: complex/str/bool-object data cannot be saved through base `save_data` (subclasses like mZeroSpanParity L529-546 re-implement save_data with delete-then-recreate for this reason).
- L174 `save_data()` with no arg reads `self.data` → AttributeError if subclass never set it.
- L184 `f.get_dict()` does not exist.
- L52-54 docstring says `path` is "directory where data will be stored"; actually it is both subdir name and filename stem.

**Destination:** `qicklab/core/experiment.py` (`ExperimentClass`, keep name for compat or alias `Experiment`), `qicklab/core/h5.py` (or same module) for `MakeFile` → `H5File` + `NpEncoder` → `NumpyJSONEncoder`. Pathing logic → a pure function `data_paths(outer_folder, path, prefix, now) -> (dir, fname, iname, cname, titlename)` so it is unit-testable (tests/ should pin the exact strings above).

**Style:** CamelCase `outerFolder`, `== None` (L131), `super(NpEncoder, self)` py2 style, `__dict__.update(kwargs)` magic, stubs with `pass` instead of `NotImplementedError`/abstract.

---

## 2. CoreLib/socProxy.py (95 lines)

**Purpose:** connect to QICK Pyro4 server; returns `(soc, soccfg)`.

**Public symbols:** `makeProxy()` L4 (ns `192.168.0.103:8888`, name `myqick`) — used by `runs/context.py:142` (via star import). `makeProxy_RFSOC_10` L22 (192.168.1.10), `makeProxy_RFSOC_11` L40 (192.168.1.11), `makeProxy_RFSOC_12` L58 (192.168.1.12), `makeProxy_RFSOC_119` L76 (192.168.1.119) — **dead** (no references anywhere). All five are copy-paste identical except host.
Each sets global `Pyro4.config.SERIALIZER="pickle"`, `PICKLE_PROTOCOL_VERSION=4`, prints every nameserver entry, `QickConfig(soc.get_cfg())`.

**Imports:** Pyro4, qick.QickConfig. **Imported by:** `Calib/initialize4Q.py:9` (star; re-exports `makeProxy` etc.), `Runners/runs/context.py:20` (star; redundant with initialize4Q's re-export).

**cfg keys:** none.
**Dead code:** L22-92 (4 duplicate functions), L94-95 commented.
**Lab notes:** board IPs (code, not comments): active board `192.168.0.103:8888 / myqick`; legacy boards 192.168.1.10/.11/.12/.119 → device/architecture "hardware endpoints" table. CLAUDE.md claims 192.168.1.7 — stale.
**Noise:** L14, L32, L50, L68, L86 (identical comment), L94-95.
**Bugs:** none functional; prints full ns listing on every connect; global Pyro4 config mutation.
**Destination:** `qicklab/hardware/rfsoc.py` → `make_proxy(host="192.168.0.103", port=8888, server_name="myqick", verbose=False)`; host lives in a session/device-level setting, not hardcoded. Keep `makeProxy = make_proxy` alias only if old runners must run unchanged.
**Style:** copy-paste x5, `return(...)` parens, camelCase.

---

## 3. Calib/initialize4Q.py (52 lines)

**Purpose:** hardware-level default cfg `BaseConfig` and fast-flux channel map `FF_Qubits`.

**Imports:** `from ...CoreLib.socProxy import *` (star), `h5py`, `os`, `platform`, `pyvisa as visa` — **all four unused**. **Imported by:** `Runners/runs/context.py:19` (star). Text references: `runs/zero_span.py:107` comment, `verify_ModifiedRamsey_timing.py:56` comment (`initialize4Q.py:30`).

**Public symbols:** `BaseConfig` (dict), `FF_channel1..4` (ints 2,4,5,6; only used to build FF_Qubits → unused externally), `FF_Qubits` (dict). Re-exports socProxy names.

### BaseConfig key by key
Consumers = files reading the key (from grep of quoted key, comments excluded). "Overridden" = rewritten by `runs/context.py` before any experiment sees it.

| key | value | meaning / units | read by | notes |
|---|---|---|---|---|
| `res_ch` | 0 | readout DAC gen channel | mActiveResetVerify, mAmplitudeRabiFF(+_noUpdate), mChargeDispersion(+QuasiCW), mChiShift, mConstantTwoTone, mModifiedRamsey, mSingleShotProgramFFMUX, mSingleTone, mSpecSliceFF, mT1FF, mT1_SS, mT2EFF, mT2R, mTransmissionFF, mUndrivenSingleShot, mZeroSpanParity; runs/calibration, charge_parity, zero_span | hardware wiring |
| `qubit_ch` | 1 | qubit drive DAC gen channel | same set (minus mSingleTone/mTransmissionFF) + mAutoCoherence | hardware wiring |
| `mixer_freq` | 0.0 | readout DAC mixer/NCO freq, MHz (`declare_gen(mixer_freq=)`) | mChargeDispersionQuasiCW, mChiShift, mSingleShotProgramFFMUX, mSingleTone, mSpecSliceFF, mTransmissionFF, mZeroSpanParity, runs/zero_span; printed by mConstantTwoTone | **written** by mOptimizeReadoutandPulse_FF L513, L746 (`self.cfg["mixer_freq"] = trans_fpts[idx]`) |
| `ro_chs` | [0] | ADC readout channel list | nearly every experiment | hardware wiring |
| `reps` | 1000 | averages per point | many | overridden by context.trans_config (1000) and per-run cfgs |
| `nqz` | 2 | readout DAC Nyquist zone | every program's `declare_gen(res_ch)` | inline note "refers to cavity" |
| `qubit_nqz` | 1 | qubit DAC Nyquist zone | every program's `declare_gen(qubit_ch)` | |
| `relax_delay` | 3000 | wait between shots, us (`us2cycles`) | many | overridden in SS regime (`SS_params['relax_delay']`) and per-run |
| `res_phase` | 0 | readout pulse phase, **tProc register units** (passed raw to `set_pulse_registers(phase=)`) | all readout programs | **mutated** by `runs/calibration.py` L135, L154 (active-reset readout calib rotates it) |
| `pulse_style` | "const" | — | **nobody** (programs use `read_pulse_style`/`qubit_pulse_style` or hardcode `style="const"`) | dead key; also rewritten by context L181 |
| `length` | 30 | readout tone duration, us | many programs (`us2cycles(cfg["length"])`) | **overridden** by context: `adc_trig_offset + readout_length` (L185, L94); mActiveResetVerify/mModifiedRamsey assert `length >= adc_trig_offset + readout_length` |
| `pulse_gain` | 30000 | readout DAC gain, DAC units | all readout programs | overridden by context with `Qubit_Parameters[Q]['Readout']['Gain']` |
| `adc_trig_offset` | 1 | ADC trigger delay after readout tone start, us | all readout programs | default source for `build_context(adc_trig_offset_us=None)` (context L169); overridden in SS regime |
| `cavity_LO` | 0 | external readout LO, **Hz** (code does `/1e6`) | mChiShift L110, mOptimizeReadoutandPulse_FF, mTransmissionFF, runs/charge_parity; printed by mConstantTwoTone, context.sanity_dump | 0 = no external LO |
| `cavity_winding_freq` | 0 | cable-delay phase unwinding slope (rad / (2π·MHz)) applied as `exp(1j*(2π·f_wind·pulse_freq + offset))` | mAmplitudeRabiFF, mAmplitudeRabiFF_noUpdate, mChargeDispersionQuasiCW, mSpecSliceFF, mT1FF | 0 → identity |
| `cavity_winding_offset` | 0 | phase offset, rad | same 5 | |
| `trig_buffer_start` | 0.02 | us, lead of external trigger (pin 0) before qubit pulse | mAmplitudeRabiFF, mAmplitudeRabiFF_noUpdate, mSingleShotProgramFFMUX, mT1FF, mT2EFF | trig length = start+end+4σ |
| `trig_buffer_end` | 0.02 | us, trigger tail after pulse | same | |
| `trig_delay` | 0.082 | us, cable/latency delay of trigger pin vs DAC | same | |

`FF_Qubits` (written into cfg as `config["FF_Qubits"]` by `context.py` L116, L214):
| key | channel | delay_time (us) |
|---|---|---|
| `'1'` | 2 | 0.017 + 0.0045 = 0.0215 |
| `'2'` | 4 | 0 |
| `'3'` | 5 | 0 |
| `'4'` | 6 | 0 |
**No active code reads `cfg["FF_Qubits"]`, `channel`, or `delay_time`** (only commented code mSingleShotProgramFFMUX L542-545; mSingleShotProgramFFMUX uses separate `FF_list_readout`/`FF_list_exp`/`ff_ch`). It is persisted metadata only. Device-dependent (CSTQ03 has 6 qubits; this map has 4) → belongs in devices/, not hardware base.

**Dead code:** unused imports L10-13; L33-34 commented values; `pulse_style` key; FF_Qubits effectively unread.
**Lab notes:**
- L33-34: earlier cable-winding calibration `cavity_winding_freq 0.45917414` (older 1.0903695), `cavity_winding_offset -32.10723885 + π` (older -15.77597); device/date unknown → parameters page "historical, not in use" (or drop).
- L48: FF qubit-1 line delay 0.017 + 0.0045 us → parameters (FF_Qubits) note.
**Noise:** L1-6 (stale docstring: claims attenuator/yoko names defined here — they are not), L8, L16, inline `# --Fixed` L18,19,21,22,25,26,27, L31 (stale: "adc_trig_offset 100 to 220 clock ticks" — value is now us).
**Bugs:** none functional. `BaseConfig` is a module-level mutable dict shared by all importers; context does `BaseConfig | UpdateConfig` (copy) so not mutated today — keep it that way (freeze/`MappingProxyType` or factory function).
**Destination:** split: hardware-wiring keys (`res_ch, qubit_ch, ro_chs, nqz, qubit_nqz, mixer_freq, cavity_LO, trig_*`, `cavity_winding_*`) → `qicklab/hardware/wiring.py` (or `devices/_base.py` `HARDWARE_DEFAULTS`); measurement defaults (`reps, relax_delay, length, pulse_gain, adc_trig_offset, res_phase`) → `qicklab/core/config.py` `DEFAULTS`; `FF_Qubits` → `devices/<chip>.py`. Drop `pulse_style`. Provide `base_config()` returning a fresh dict.
**Style:** star import re-export, `str(1)` keys, mixed quote style, unused imports.

---

## 4. PythonDrivers/YOKOGS200.py (87 lines)

**Purpose:** VISA wrapper class for Yokogawa GS200 source with software ramping.
**Public symbols:** class `YOKOGS200(VISAaddress, rm)`: `OutputOn/OutputOff`, `SetVoltage(v)` (ramp, `_rampstep`=1e-4, `_rampinterval`=0.01 s), `SetCurrent(i)` (ramp, no dwell), `SetMode('voltage'|'current')`, `GetVoltage`, `GetCurrent`, `GetMode`.
**Imports:** sys, pyvisa, numpy, time. **Imported by: nobody** → whole module unused externally. Active code drives YOKOs with raw pyvisa: `runs/context.py:147-151` + `Experiments/utils.py:333 ramp_to` (voltage), `mAutoCoherence.py:~200-209` (another ramp copy), `twpa_set_bias.slow_ramp_to_current` (current).
**Lab notes:** L8 "_rampinterval default MATLAB is 0.01 s; CANNOT be lower than 0.001 s otherwise fridge heats up" → parameters/architecture (yoko ramp constraint).
**Noise:** L7 inline `#0.0001 #0.001`, L10-11, L20, L22, L26, L30, L32-33, L39, L45-46, L56, L63, L65, L72, L79, L87.
**Bugs:**
- L51 `SetCurrent`: `np.linspace(start, stop, num=steps)` with `steps=1` → writes only `start`, never reaches target (|Δ| < 1.5e-4 A). Also no `time.sleep` → no rate limit; `_rampstep` 1e-4 A = 100 uA per step (would violate the TWPA 300 nA/s limit by orders of magnitude).
- L67/L74 `GetVoltage/GetCurrent` **switch the source function** as a side effect (`SOURce:FUNCtion VOLTage/CURRent`).
- L18 `sys.exit()` inside a library constructor; `ex` unused.
**Destination:** `qicklab/hardware/yoko.py` — merge with `utils.ramp_to`, mAutoCoherence ramp and `twpa_set_bias.pick_current_range/slow_ramp_to_current` into one `Yoko` helper (`ramp_voltage`, `ramp_current(max_rate)`, `pick_current_range`). Do not keep the class as-is.
**Style:** CamelCase methods, `%` formatting, comments instead of docstrings, banner lines.

---

## 5. PythonDrivers/control_atten.py (92 lines)

**Purpose:** set a Vaunix LDA attenuator (by serial) via `VNX_atten64.dll` ctypes.
**Public symbols:** `setatten(attenu, serial, printv)` — **unused externally** (no importer). `__main__` block: atten=30 dB, serial=27786, printv=True.
**Imports:** sys (unused), `from ctypes import *` (star), `from distutils.util import strtobool` (deprecated; only via setuptools shim on 3.13; only used in `__main__`), os.
**DLL:** L6 `os.add_dll_directory(os.getcwd())` at import (works only if CWD contains the DLL); `cdll.VNX_atten64` L11. DLL not present in repo.
**Lab notes:** HR attenuation unit = 0.05 dB (L51 `atten/.05`, L73 readback `/20`); default attenuator serial 27786 → parameters/hardware page. DLL must be on the DLL search path (Python ≥3.8) → architecture.
**Noise:** L17, L22-24, L26, L30, L36, L38, L40-41, L46-49, L54, L59, L65, L68, L77, inline L88-90.
**Bugs:**
- L71 `print(..., result)` → `NameError` (`result` undefined until L78; should be `result_1`) when GetAttenuationHR < 0 and printv.
- L28 loops fixed `range(0,5)` irrespective of `numDevices`/`dev_info`; queries serials of zero handles.
- L37 `init_dev`, L25 `dev_info`, L42 `num_channels` set but unused (num_channels clamp is dead logic).
- Silent no-op if serial not found; errors only printed when `printv`.
- `printv == True` comparisons.
**Destination:** `qicklab/hardware/attenuator.py` → `set_attenuation(db, serial, dll_dir=None, verbose=False)`, with DLL directory passed explicitly (handle from `add_dll_directory` kept), raise on not-found/errors. Drop `distutils`.
**Style:** star import, semicolon L42, `== True`, unused vars.

---

## 6. PythonDrivers/sc5510a_client.py (77 lines)

**Purpose:** Pyro5 client for remote SignalCore SC5510A generators.
**Public symbols:** `SERVER_HOST` (env `SC5510A_SERVER_HOST`, default `192.168.0.102`), `NAME_SERVER_PORT=9090`, `NAME_PREFIX="SC5510A#"`, `locate_nameserver(host, port)`, `list_instruments(host, port)`, `connect(name=None, host, port)` → Pyro5 proxy with `.frequency` (Hz), `.power` (dBm), `.output`, `.clocked`. **Unused externally** (only self-reference in its docstring L13).
**Imports:** os, Pyro5.api, Pyro5.errors.
**Lab notes:** L3-9: source repo `https://github.com/NPdL-SQTeam/sc5510a-py`; server PC must run `start_nameserver.py` and `start_instrument_server.py`; host via env var → architecture/hardware page. Example device id `10002D35`.
**Noise:** L30 only. Docstring is good quality; condense to 5 lines.
**Bugs:** default args bind `SERVER_HOST` at import (env var change after import ignored) — minor.
**Destination:** `qicklab/hardware/sc5510a.py` (unchanged logic).
**Style:** fine.

---

## 7-11. TWPA scripts (Experiments/twpa_*.py)

All five are **standalone `__main__` scripts** (`if __name__ == "__main__": main()`), configured by module-level UPPERCASE constants, each prompts `input("Type 'yes' to proceed: ")` (aborts with `sys.exit(0)`). Not ExperimentClass, no QICK, no cfg dict. Importable without side effects. Only cross-import: `twpa_flux_sweep_pnax` imports `TWPA_YOKO_ADDRESS, MAX_RATE_nA_per_s, pick_current_range, slow_ramp_to_current` from `twpa_set_bias`. Nothing else in the tree imports any twpa_* module.

Instruments:
| script | YOKO GS200 (pyvisa, `GPIB1::12::INSTR`, current mode) | Windfreak SynthHD (`pywindfreak`, `COM5`) | Keysight PNA-X (pyvisa, `GPIB0::16::INSTR`) |
|---|---|---|---|
| twpa_set_bias | yes | – | – |
| twpa_set_pump | – | yes (per-channel settings) | – |
| twpa_flux_sweep_pnax | yes (via set_bias helpers) | – | yes |
| twpa_pump_sweep_pnax | – | yes (identical channels) | yes |
| twpa_gain_compare_pnax | – | yes (identical channels) | yes |

Output convention (different from ExperimentClass): `SAVE_DIR/<%Y%m%d_%H%M%S>_<RUN_TAG>.npz/.png`, `SAVE_DIR = "V:/t1Team/Data/2026-10-01_BFC_cooldown/TWPA_calibration"` (duplicated in 3 files), incremental `np.savez` each point.

**Duplicated code to factor** (→ `qicklab/hardware/pnax.py`, `qicklab/hardware/synthhd.py`, `qicklab/hardware/yoko.py`, `qicklab/twpa/common.py`):
- `configure_pnax`: flux L89-121 and pump L106-139 identical except pump sizes timeout via `estimate_group_timeout_ms`; gain L86-106 is the LIN/no-averaging subset.
- `measure_s21_band`: flux L124-137 == pump L142-155. gain's `measure_s21_trace` L122-133 = same with n_avg=1 + strict size check.
- `band_mean_dB`: flux L140-144 == pump L158-162.
- `set_pump_channels`: gain L139-144 == pump L168-173; set_pump L61-67 is the per-channel (dict) variant.
- `disable_pump_channels`: 3 variants (set_pump L70-75 by index; gain L147-152 == pump L176-181 by channel obj).
- Pre-flight banner + yes-confirm: 5 copies. Timestamped save base: 3 copies. Teardown (`disable pump; synth.close(); pnax SOUR:POW1:MODE OFF; close`): 2 copies (gain L269-282, pump L339-352).
- Pump operating point `(10.7165 GHz, -5.5 dBm, ch1)` duplicated in set_pump L51 and gain_compare L59-60; addresses `COM5`, `GPIB0::16::INSTR` in 3 files each → one `devices/<setup>` TWPA section.

### 7. twpa_set_pump.py (158 lines)
Purpose: park SynthHD pump channel(s) at (freq, power) and leave RF ON; or disable.
Symbols: constants `PUMP_SYNTH_PORT="COM5"`, `PUMP_SETTINGS={1: (10.7165, -5.5)}`, `PUMP_POWER_MAX_dBm=0.0`, `DISABLE_PUMP=True`; `set_pump_channels(synth, settings, rf_enable)`, `disable_pump_channels(synth, indices)`, `main()`; CLI flag `--off`.
Lab notes:
- L50-51: pump op points — ch1 10.7165 GHz / −5.5 dBm (active); ch0 10.7831 GHz / −1.0 dBm (commented, earlier) → device:CSTQ03 (TWPA, 2026-10 cooldown).
- L53: pump power ceiling 0 dBm → parameters (TWPA).
- L139-142 (+L124-125): `SynthHD.__init__` disables RF on both channels and locks to external 10 MHz ref; `SynthHD.close()` disables RF on both channels, so the script deliberately does not close the port to leave the pump ON → twpa/architecture (verified against installed pywindfreak).
- Order of operations: bias first (twpa_set_bias), then pump → twpa procedure page.
Noise: L41-44, L47-48 (partly), L58-60, L78-80, L86, L99, L123, L138; docstring L1-34 → condense to ~5 lines.
Bugs:
- L16-17 docstring/L48 comment "Channels not listed here are left untouched" is **false**: `SynthHD(PUMP_SYNTH_PORT)` (L126) disables RF on both channels on connect, so ch0 is switched off whenever ch1 is set.
- L55 `DISABLE_PUMP = True` committed → running the script only turns pump OFF (likely leftover).
Destination: `qicklab/twpa/set_pump.py` (CLI `python -m qicklab.twpa.set_pump [--off]`), settings from device file.

### 8. twpa_set_bias.py (171 lines)
Purpose: ramp dedicated TWPA YOKO (current mode) to target at ≤300 nA/s.
Symbols: `TWPA_YOKO_ADDRESS="GPIB1::12::INSTR"`, `TARGET_CURRENT_uA=0`, `MAX_RATE_nA_per_s=300.0`, `SAFETY_CAP_uA=25.0`, `ALLOW_CALIBRATION=False`, `STEP_PERIOD_S=0.05`, `YOKO_CURR_RANGE_A=None`; `pick_current_range(required_A)` (used by flux_sweep), `slow_ramp_to_current(yoko, target_A, max_rate_A_per_s, dt)` (used by flux_sweep), `main()`.
Lab notes:
- L4-11: TWPA datasheet constraints: ramp with pump OFF from 0; max sweep 300 nA/s (flux trapping); nominal op point ~11 uA (≈15 uT internal field, impedance matched); first flux period ends ~25 uA (calibration only); don't sweep well above ~11 uA in normal operation → parameters (TWPA) + twpa page.
- L17-24: YOKO in current-source mode directly into TWPA bias port; earlier voltage-mode + series-resistor scheme dropped because resistor value unreliable → twpa/hardware page.
- L41: TWPA YOKO is GPIB1::12, distinct from charge-line YOKO GPIB1::9 → device/hardware.
- L43: `TARGET_CURRENT_uA = 0`; "18 (10/7/26)"; earlier optimum from flux sweep `20260521_144734` (max |S21|, broad 3.5–5.5 uA plateau); datasheet nominal ≈11 uA → device:CSTQ03 (TWPA bias history).
- L51-53: GS200 current ranges {1, 10, 100, 200} mA; setpoints above active range are silently clipped → hardware page.
Noise: L38-40, L57-59, L106-108, L110, L132, L155; docstring condense.
Bugs:
- L46 `SAFETY_CAP_uA = 25.0` equals the hard limit at L113 (`>25` raises first) → `ALLOW_CALIBRATION` branch L118-122 is **unreachable**; the "do not exceed ~11 uA" guidance is not enforced (flux_sweep docstring L25 refers to a "12 uA safety cap" that no longer exists).
- L27, L144 reference Holzworth HS9004A as the pump; current pump is Windfreak SynthHD (stale; also flux_sweep L22, L201).
- L159 `:SOUR:FUNC CURR` issued without checking current mode/output; if the YOKO were in voltage mode with output on, the function switch happens before the ramp (dedicated YOKO, so low risk).
Destination: helpers → `qicklab/hardware/yoko.py` (`pick_current_range`, `ramp_current`); script → `qicklab/twpa/set_bias.py`.

### 9. twpa_gain_compare_pnax.py (335 lines)
Purpose: |S21| pump-OFF vs pump-ON across signal band, interleaved N_REPEATS; gain = ON − OFF (dB).
Symbols: constants `PUMP_SYNTH_PORT, PUMP_CHANNELS=[1], PUMP_ON_FREQ_GHz=10.7165, PUMP_ON_POWER_dBm=-5.5, PUMP_POWER_MAX_dBm=0.0, F_SIGNAL_START_GHz=2.0, F_SIGNAL_STOP_GHz=10.0, N_SIGNAL_POINTS=401, N_REPEATS=10, SETTLE_AFTER_PUMP_S=0.30, PNAX_ADDRESS, PNAX_IF_BW_HZ=1000, PNAX_POWER_dBm=-25, PNAX_TIMEOUT_MS=60000, SAVE_DIR, RUN_TAG="gain_on_vs_off"`; `configure_pnax`, `read_freq_axis`, `measure_s21_trace`, `set_pump_channels`, `disable_pump_channels`, `main`.
Lab notes:
- L13-14: good op point shows broadband positive gain, often ~15–20 dB, modest ripple → twpa page.
- L16-18: OFF/ON interleaving cancels slow thermal/cable drift → twpa page.
- L56-57: earlier pump ON point 10.9187 GHz / −18 dBm (commented) → device:CSTQ03 TWPA history.
- L75: PNA-X power kept at −25 dBm so signal does not saturate TWPA → parameters (TWPA).
- L327-329: band-mean gain < 1 dB ⇒ pump off-optimum / under-powered / not reaching TWPA (diagnostic) → twpa page.
Noise: banners L47-50, L54, L63, L68, L72, L78, L83-85, L136-138, L155-157, L159, L180, L222, L226, L231, L284, L296, L319; TODO tags L59-65 stale.
Bugs: L211-217 PNA-X opened before SynthHD connect outside `try` → if SynthHD fails, pnax left open. `np.nanmean` on unfinished (all-NaN) rows warns. Otherwise sound.
Destination: `qicklab/twpa/gain_compare.py`.

### 10. twpa_flux_sweep_pnax.py (336 lines)
Purpose: sweep TWPA bias over ±25 uA at ≤300 nA/s with pump OFF, read PNA-X |S21| (BAND mean or CW), report best bias; ramps back to 0 on exit.
Symbols: constants `PNAX_ADDRESS, I_START_uA=-25, I_STOP_uA=25, N_BIAS_POINTS=51, SETTLE_AFTER_RAMP_S=0.5, PNAX_MEAS_MODE="BAND", PNAX_CW_FREQ_HZ=7e9, PNAX_F_START_HZ=5e9, PNAX_F_STOP_HZ=8e9, PNAX_N_FREQ_POINTS=201, PNAX_IF_BW_HZ=100, PNAX_POWER_dBm=-25, PNAX_N_AVG=4, PNAX_TIMEOUT_MS=30000, SAVE_DIR, RUN_TAG="first_period_sweep"`; `configure_pnax`, `measure_s21_band`, `band_mean_dB`, `main`.
Lab notes:
- L13-17: expected signature: transmission enhancement near ~11 uA (op point), strong suppression near ~25 uA (end of first flux period); flat mean-band |S21| vs current ⇒ DC line open → twpa page.
- L18-19: pump OFF ⇒ bare transmission, not gain → twpa page.
- L329-332: spread < 0.5 dB ⇒ DC path open / not flux-responsive (diagnostic) → twpa page.
Noise: banners L55-57, L60, L66-68, L72, L81, L86-88, L147-149, L151, L180, L227, L232, L278, L291, L305, L319; L63 stale.
Bugs / stale:
- Docstring L6 "0 → ~25 uA" and L63 "51 points → 0.5 uA spacing across 0–25 uA" contradict config (−25→+25, 1.0 uA spacing).
- L25-27 "overrides the 12 uA safety cap" — no such cap exists (set_bias cap is 25).
- Fixed `PNAX_TIMEOUT_MS` (no `estimate_group_timeout_ms` like pump_sweep) → VISA timeout if N_AVG/points raised or IF BW lowered (currently ~8 s/group, OK).
- L218-219 yoko and pnax opened outside `try`.
Destination: `qicklab/twpa/flux_sweep.py`.

### 11. twpa_pump_sweep_pnax.py (417 lines)
Purpose: 2-D pump (freq × power) sweep with bias parked, PNA-X band-mean |S21| (or CW) per point; map + best point.
Symbols: constants `PUMP_SYNTH_PORT, PUMP_CHANNELS=[1], F_START_GHz=10.7, F_STOP_GHz=10.73, N_FREQ_POINTS=401, P_START_dBm=-10, P_STOP_dBm=0, N_POWER_POINTS=21, PUMP_POWER_MAX_dBm=20.0, SETTLE_AFTER_FREQ_S=0.20, SETTLE_AFTER_POWER_S=0.05, PNAX_ADDRESS, PNAX_MEAS_MODE="BAND", PNAX_CW_FREQ_HZ=7e9, PNAX_F_START_HZ=6e9, PNAX_F_STOP_HZ=8e9, PNAX_N_FREQ_POINTS=21, PNAX_IF_BW_HZ=500, PNAX_POWER_dBm=-25, PNAX_N_AVG=100, PNAX_TIMEOUT_MS=30000, SAVE_DIR, RUN_TAG="pump_sweep"`; `estimate_group_timeout_ms`, `configure_pnax`, `measure_s21_band`, `band_mean_dB`, `set_pump_channels`, `disable_pump_channels`, `main`.
Lab notes:
- L12-14: reports transmission not gain; subtract unpumped reference offline for gain → twpa page.
- L95-98: PNA-X sweep time ≈ n_points/IF_BW per sweep × n_avg; fixed 30 s VISA timeout was exceeded at low IF BW + many averages → timeout = 3×estimate + 5 s, floor = PNAX_TIMEOUT_MS → architecture (pnax helper).
- L80: PNA-X previously −20 dBm, now −25 dBm (TWPA may be under-pumped at start) → parameters (TWPA).
- L243-247: wall-clock model (per point = n_freq/IF_BW × N_avg + power settle; + N_freq × freq settle) → keep as code, not doc.
Noise: banners L47-50, L54, L59, L65, L69-72, L84, L89-91, L165-167, L184-186, L188, L223, L282-283, L286, L294, L354-356, L370, L377, L403; stale L57, L62.
Bugs / stale:
- L57 comment "25 MHz spacing across 12.0–13.5 GHz (centered on ~12.7 GHz)" vs config 10.70–10.73 GHz, 401 pts (0.075 MHz). L62 "0.5 dB spacing across −25 → 0 dBm" vs −10→0 dBm.
- L63 `PUMP_POWER_MAX_dBm = 20.0` vs 0.0 in set_pump/gain_compare — inconsistent ceiling.
- Current config: 401×21 = 8421 points × ~4.25 s ≈ 10 h runtime (printed estimate exists, but worth flagging).
- L272-278 pnax opened before SynthHD outside `try`.
Destination: `qicklab/twpa/pump_sweep.py`.

---

## Proposed layout summary
| old | new |
|---|---|
| CoreLib/Experiment.py | qicklab/core/experiment.py (+ `data_paths()` pure fn; `H5File`, `NumpyJSONEncoder`) |
| CoreLib/socProxy.py | qicklab/hardware/rfsoc.py (`make_proxy(host,port,name)`) |
| Calib/initialize4Q.py | qicklab/core/config.py (`base_config()`), hardware wiring in qicklab/hardware/wiring.py; FF_Qubits → devices/cstq03.py |
| PythonDrivers/YOKOGS200.py | qicklab/hardware/yoko.py (merged with utils.ramp_to, mAutoCoherence ramp, twpa_set_bias helpers) |
| PythonDrivers/control_atten.py | qicklab/hardware/attenuator.py |
| PythonDrivers/sc5510a_client.py | qicklab/hardware/sc5510a.py |
| Experiments/twpa_set_bias.py | qicklab/twpa/set_bias.py (helpers → hardware/yoko.py) |
| Experiments/twpa_set_pump.py | qicklab/twpa/set_pump.py |
| Experiments/twpa_flux_sweep_pnax.py | qicklab/twpa/flux_sweep.py |
| Experiments/twpa_pump_sweep_pnax.py | qicklab/twpa/pump_sweep.py |
| Experiments/twpa_gain_compare_pnax.py | qicklab/twpa/gain_compare.py |
| (new) | qicklab/hardware/pnax.py (configure, measure, freq axis, timeout estimate), qicklab/hardware/synthhd.py (set/disable channels), qicklab/twpa/common.py (confirm prompt, timestamped save path, TWPA safety limits as constants) |

TWPA settings (addresses COM5 / GPIB0::16 / GPIB1::12, pump op point, bias target, SAVE_DIR) → one TWPA block in the device/session file so the five scripts share it.
