"""Device.chip / package / fab: the structured device name and its validation."""

import json
import warnings

import pytest

from qicklab.core.device import Device, Qubit, Readout, Setup, device_name
from qicklab.core.io import record_calibration


def _device(
    name="CSTQ03_nucell_fab2026_10", chip="CSTQ03", package="nucell", fab="2026-10", root="D:/x"
):
    q = Qubit(freq=2651, gain=4200, sigma=0.08, readout=Readout(freq=7095.4, gain=1500))
    return Device(
        name=name,
        cooldown="2026-10-29",
        data_root=root,
        qubits={1: q},
        setup=Setup(),
        chip=chip,
        package=package,
        fab=fab,
    )


def _validate(dev):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return dev.validate()


def test_device_name_format():
    assert device_name("CSTQ03", "nucell", "2026-10") == "CSTQ03_nucell_fab2026_10"
    assert device_name("CSTQ03", "qcage", "2026-09") == "CSTQ03_qcage_fab2026_09"


def test_structured_device_validates():
    assert _validate(_device()) == []


def test_identity_is_optional():
    assert _validate(_device(name="T", chip="", package="", fab="")) == []


@pytest.mark.parametrize(
    "kwargs, message",
    [
        (
            {"name": "CSTQ03"},
            r"name must be device_name\(chip, package, fab\) = 'CSTQ03_nucell_fab2026_10'",
        ),
        ({"fab": ""}, r"missing \['fab'\]"),
        ({"fab": "2026-13", "name": "CSTQ03_nucell_fab2026_13"}, "fab must be 'YYYY-MM'"),
        ({"fab": "Oct 2026"}, "fab must be 'YYYY-MM'"),
        ({"package": "Nu Cell"}, "package must be a short lowercase tag"),
    ],
)
def test_identity_errors(kwargs, message):
    with pytest.raises(ValueError, match=message):
        _validate(_device(**kwargs))


def test_calibration_record_carries_identity(tmp_path):
    record_calibration(_device(root=str(tmp_path)), 1, step="manual", gain=4300)
    (line,) = (tmp_path / "Q1" / "calibrations.jsonl").read_text().splitlines()
    rec = json.loads(line)
    assert (rec["device"], rec["chip"], rec["package"], rec["fab"]) == (
        "CSTQ03_nucell_fab2026_10",
        "CSTQ03",
        "nucell",
        "2026-10",
    )


def test_calibration_record_without_identity_is_unchanged(tmp_path):
    record_calibration(
        _device(name="T", chip="", package="", fab="", root=str(tmp_path)), 1, gain=4300
    )
    rec = json.loads((tmp_path / "Q1" / "calibrations.jsonl").read_text())
    assert not {"chip", "package", "fab"} & set(rec)
