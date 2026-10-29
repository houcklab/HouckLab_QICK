"""Every live device file and session runner follows the naming of docs/adding_a_device.md."""

import importlib
import re
import warnings
from pathlib import Path

import pytest

from qicklab.core.device import device_name

REPO = Path(__file__).resolve().parents[1]
LIVE_DEVICES = sorted(p.stem for p in (REPO / "devices").glob("*.py") if p.stem != "__init__")


def test_there_are_live_devices():
    assert LIVE_DEVICES


@pytest.mark.parametrize("stem", LIVE_DEVICES)
def test_live_device_follows_the_naming(stem):
    """devices/<name>.py: name = file stem = <chip>_<package>_fab<YYYY>_<MM>, data under
    <data drive>/<cooldown>_<fridge>_cooldown/<name>/RFSOC, and validate raises nothing."""
    dev = importlib.import_module(f"devices.{stem}").DEVICE
    assert dev.chip and dev.package and dev.fab, "live devices carry chip / package / fab"
    assert dev.name == stem == device_name(dev.chip, dev.package, dev.fab)
    assert re.fullmatch(rf"V:/t1Team/Data/{dev.cooldown}_\w+_cooldown/{stem}/RFSOC", dev.data_root)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dev.validate()


@pytest.mark.parametrize(
    "path", sorted((REPO / "runners").glob("*_session.py")), ids=lambda p: p.stem
)
def test_live_session_runner_imports_its_device(path):
    device = path.stem.removesuffix("_session")
    assert device in LIVE_DEVICES, f"{path.name}: no devices/{device}.py"
    assert f"from devices.{device} import DEVICE" in path.read_text(encoding="utf-8")
