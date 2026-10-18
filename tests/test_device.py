"""qicklab.core.device and devices/CSTQ03.py: legacy round trip, folders, with_qubit, validate."""

import ast
import copy
import dataclasses
import inspect
import json
import pickle
import warnings
from pathlib import Path

import pytest

from devices.archive.CSTQ03_v2b import DEVICE as V2B
from devices.CSTQ03 import DEVICE
from qicklab.core.context import build_context
from qicklab.core.device import (
    Device,
    ParityParams,
    Qubit,
    Readout,
    ReadoutWindow,
    Setup,
)
from tests.regression.capture import FakeSocCfg

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "regression" / "fixtures" / "cstq03_legacy_runner.py.txt"


def _sections_1_2(path):
    """Execute a legacy runner's top-level statements up to `ctx = build_context(...)`, no imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    body = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "ctx" for t in node.targets
        ):
            break
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            body.append(node)
    ns = {}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), ns)
    return ns


@pytest.fixture(scope="module", params=[FIXTURE], ids=["frozen_fixture"])
def legacy(request):
    """Sections 1-2 of the legacy CSTQ03 runner (deleted in 5b) from its frozen copy."""
    return _sections_1_2(request.param)


def _quiet_validate(device, soccfg=None):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        report = device.validate(soccfg)
    return report, [str(w.message) for w in caught]


def _device(**qubit_changes):
    q = Qubit(freq=2651, gain=4200, sigma=0.08, readout=Readout(freq=7095.4, gain=1500))
    q = dataclasses.replace(q, **qubit_changes)
    return Device(name="T", cooldown="2026-01-01", data_root="D:/x", qubits={1: q}, setup=Setup())


# ── legacy shape ────────────────────────────────────────────────────────────


def test_legacy_parameters_byte_identical(legacy):
    new = DEVICE.legacy_parameters()
    old = legacy["Qubit_Parameters"]
    assert repr(new) == repr(old)  # same keys, order, values and int/float types
    assert json.dumps(new) == json.dumps(old)


def test_legacy_parameters_is_a_fresh_dict():
    a = DEVICE.legacy_parameters()
    a["5"]["Qubit"]["Frequency"] = 0
    assert DEVICE.legacy_parameters()["5"]["Qubit"]["Frequency"] == 2651


def test_archived_v2b_is_the_runner_table(legacy):
    """devices/archive/CSTQ03_v2b.py is the legacy runner's unused Qubit_Parameters_v2b."""
    new = V2B.legacy_parameters()
    old = legacy["Qubit_Parameters_v2b"]
    assert repr(new) == repr(old)  # same keys, order, values and int/float types
    assert V2B.name == DEVICE.name and V2B.cooldown != DEVICE.cooldown
    _quiet_validate(V2B)  # no hard error (pi2/gain warnings are the table's own)


def test_no_session_code_imports_the_archive():
    users = [
        str(path.relative_to(REPO))
        for top in ("qicklab", "runners", "devices")
        for path in (REPO / top).rglob("*.py")
        if "devices.archive" in path.read_text(encoding="utf-8")
    ]
    assert not users


def test_folders_match_qubit_folders(legacy):
    assert {str(q): DEVICE.folder(q) for q in DEVICE.qubits} == legacy["QubitFolders"]
    assert DEVICE.folder(4) == "V:/t1Team/Data/2026-10-01_BFC_cooldown/CSTQ03/RFSOC/Q4//"


def test_windows_and_flags_match_runner(legacy):
    assert DEVICE.readout_window == ReadoutWindow(legacy["Readout_Time"], legacy["ADC_Offset"])
    ss = legacy["SS_params"]
    assert DEVICE.ss_window == ReadoutWindow(ss["Readout_Time"], ss["ADC_Offset"])
    assert DEVICE.cavity_min is legacy["cavity_min"]
    q = legacy["Qubit_Readout"]
    assert DEVICE.window(q) == DEVICE.readout_window
    assert DEVICE.window(q, single_shot=True) == DEVICE.ss_window


def test_setup_defaults_match_build_context():
    params = inspect.signature(build_context).parameters
    s = DEVICE.setup
    for name in ("rfsoc_host", "rfsoc_port", "rfsoc_name", "yoko_addr"):
        assert getattr(Setup(), name) == params[name].default == getattr(s, name)
    assert s.board_overrides == {} and s.ff_qubits is None


def test_pi2_gain_default_is_half_gain():
    assert _device().qubits[1].effective_pi2_gain == 2100
    assert _device(pi2_gain=1987).qubits[1].effective_pi2_gain == 1987
    assert DEVICE.qubits[1].pi2_gain == 1987 and DEVICE.qubits[2].pi2_gain is None


def test_per_qubit_window_override():
    w = ReadoutWindow(5, 0.3)
    dev = _device(readout=Readout(freq=7095.4, gain=1500, ss_window=w))
    assert dev.window(1, single_shot=True) == w
    assert dev.window(1) == dev.readout_window


# ── with_qubit ──────────────────────────────────────────────────────────────


def test_with_qubit_returns_new_device_and_leaves_original():
    trial = DEVICE.with_qubit(4, gain=4800, sigma=0.025)
    assert trial is not DEVICE
    assert (trial.qubits[4].gain, trial.qubits[4].sigma) == (4800, 0.025)
    assert (DEVICE.qubits[4].gain, DEVICE.qubits[4].sigma) == (4900, 0.02)
    assert trial.legacy_parameters()["4"]["Qubit"]["pi2_Gain"] == 2400  # still gain // 2
    assert trial.qubits[1] is DEVICE.qubits[1]
    assert trial.legacy_parameters()["1"] == DEVICE.legacy_parameters()["1"]


def test_with_qubit_rejects_unknown_qubit_and_field():
    with pytest.raises(KeyError):
        DEVICE.with_qubit(7, gain=1)
    with pytest.raises(TypeError):
        DEVICE.with_qubit(4, gian=1)


def test_dataclasses_are_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEVICE.name = "x"
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEVICE.qubits[1].gain = 1


def test_dict_fields_are_read_only_copies():
    with pytest.raises(TypeError):
        DEVICE.qubits[4] = DEVICE.qubits[1]
    with pytest.raises(TypeError):
        DEVICE.setup.board_overrides["nqz"] = 1
    with pytest.raises(TypeError):
        Setup(ff_qubits={"1": {"channel": 0}}).ff_qubits["2"] = {}
    qubits, overrides = {1: _device().qubits[1]}, {"ro_chs": [0]}
    dev = Device("T", "c", "D:/x", qubits, Setup(board_overrides=overrides))
    qubits[2], overrides["nqz"] = qubits[1], 1  # the caller's dicts do not leak in
    assert list(dev.qubits) == [1] and dict(dev.setup.board_overrides) == {"ro_chs": [0]}
    dev.setup.board_config()["ro_chs"].append(1)  # nor does a mutated cfg leak back
    assert dev.setup.board_config()["ro_chs"] == [0]
    assert repr(dev.qubits) == repr({1: qubits[1]}) and dev.qubits == {1: qubits[1]}


def test_device_hash_copy_and_pickle():
    assert hash(DEVICE) == hash(dataclasses.replace(DEVICE))
    for clone in (copy.copy(DEVICE), copy.deepcopy(DEVICE), pickle.loads(pickle.dumps(DEVICE))):
        assert clone == DEVICE
        assert clone.legacy_parameters() == DEVICE.legacy_parameters()
        with pytest.raises(TypeError):
            clone.qubits[1] = None


# ── validate ────────────────────────────────────────────────────────────────


def test_cstq03_validates_without_board():
    report, warned = _quiet_validate(DEVICE)
    assert report == []
    assert any("Nyquist-zone and image check skipped" in w for w in warned)
    pi2 = [w for w in warned if "pi2_gain/gain" in w]
    assert len(pi2) == 2 and "Q1" in pi2[0] and "Q3" in pi2[1]  # 3975 // 2 vs 5000


def test_cstq03_zones_variant_a():
    report, warned = _quiet_validate(DEVICE, FakeSocCfg("A"))
    zones = {line.split(" MHz")[0]: int(line.split("zone ")[1].split(",")[0]) for line in report}
    readout = [zones[f"Q{q} readout {DEVICE.qubits[q].readout.freq}"] for q in range(1, 7)]
    assert readout == [2, 3, 3, 3, 3, 3]
    zone2 = [w for w in warned if "Nyquist zone 2 with nqz 1" in w]
    assert len(zone2) == 2 and "Q2 qubit" in zone2[0] and "Q4 qubit" in zone2[1]
    collisions = [w for w in warned if "has an image at" in w]
    assert len(collisions) == 2
    assert "Q1 qubit 2763 MHz has an image at 4118.28 MHz" in collisions[0]
    assert "Q4 qubit 4117 MHz has an image at 2764.28 MHz" in collisions[1]


def test_cstq03_zones_variant_b_is_clean():
    report, warned = _quiet_validate(DEVICE, FakeSocCfg("B"))
    assert len(report) == 12
    assert [w for w in warned if "pi2_gain/gain" not in w] == []


@pytest.mark.parametrize(
    "device, message",
    [
        (lambda: _device(gain=40000), "gain must be an integer within 0..32767"),
        (lambda: _device(gain=4200.5), r"Q1.gain must be an integer .* got 4200.5"),
        (lambda: _device(pi2_gain=2000.0), r"Q1.pi2_gain must be an integer .* got 2000.0"),
        (lambda: _device(spec_gain=True), r"Q1.spec_gain must be an integer .* got True"),
        (
            lambda: _device(readout=Readout(freq=7095.4, gain=1500.0)),
            r"Q1.readout.gain must be an integer .* got 1500.0",
        ),
        (lambda: _device(pi2_gain=5000), "pi2_gain 5000 exceeds the pi gain 4200"),
        (
            lambda: _device(readout=Readout(freq=7095.4, gain=-1)),
            "readout.gain must be an integer within",
        ),
        (lambda: _device(spec_gain=33000), "spec_gain must be an integer within"),
        (lambda: _device(sigma=0), "sigma must be > 0"),
        (lambda: _device(freq=-1), "freq must be a positive frequency"),
        (lambda: _device(parity=ParityParams(df_mhz=0, f_upper_mhz=2651)), "df_mhz must be > 0"),
        (
            lambda: _device(readout=Readout(freq=7095.4, gain=1, window=ReadoutWindow(0, 0.3))),
            "length_us must be > 0",
        ),
        (
            lambda: Device(
                "T", "c", "D:/x", {1: _device().qubits[1], 3: _device().qubits[1]}, Setup()
            ),
            "qubit keys must be the ints 1..N",
        ),
        (
            lambda: Device("T", "c", "D:/x", {"1": _device().qubits[1]}, Setup()),
            "qubit keys must be the ints 1..N",
        ),
        (
            lambda: dataclasses.replace(_device(), setup=Setup(board_overrides={"nqzz": 2})),
            "not in BASE_CONFIG",
        ),
        (
            lambda: dataclasses.replace(_device(), setup=Setup(board_overrides={"qubit_nqz": 3})),
            "qubit_nqz must be 1 or 2",
        ),
    ],
)
def test_validate_raises(device, message):
    with pytest.raises(ValueError, match=message):
        _quiet_validate(device())


def test_validate_reports_every_error_at_once():
    with pytest.raises(ValueError) as err:
        _quiet_validate(_device(gain=40000, sigma=0))
    assert "gain must be an integer within" in str(err.value) and "sigma must be > 0" in str(
        err.value
    )


def test_validate_warns_on_stale_parity_f_upper():
    dev = _device(parity=ParityParams(df_mhz=1, f_upper_mhz=3754.5))
    _, warned = _quiet_validate(dev)
    assert any("parity.f_upper_mhz 3754.5" in w for w in warned)
    _, warned = _quiet_validate(_device(parity=ParityParams(df_mhz=1, f_upper_mhz=2651.5)))
    assert not any("f_upper" in w for w in warned)


def test_validate_rejects_tone_on_a_zone_edge():
    soccfg = {"gens": [{"fs": 6881.28}, {"fs": 6881.28}]}
    with pytest.raises(ValueError, match="tone and image coincide"):
        _quiet_validate(_device(freq=3440.0), soccfg)
    with pytest.raises(ValueError, match="above 2 fs"):
        _quiet_validate(_device(readout=Readout(freq=14000, gain=1)), soccfg)


@pytest.mark.parametrize(
    "freq, zone, image",
    [(5000, 2, 1881.28), (8000, 3, 1118.72), (12000, 4, 1762.56)],
    ids=["zone2", "zone3", "zone4"],
)
def test_nqz1_warning_names_the_first_zone_image(freq, zone, image):
    soccfg = {"gens": [{"fs": 6881.28}, {"fs": 6881.28}]}
    _, warned = _quiet_validate(_device(freq=freq), soccfg)
    (msg,) = [w for w in warned if f"Q1 qubit {freq} MHz is in Nyquist zone" in w]
    assert f"zone {zone} with nqz 1" in msg and f"image at {image} MHz" in msg
