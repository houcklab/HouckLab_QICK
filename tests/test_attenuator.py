"""hardware.attenuator.set_attenuation against a fake VNX_atten64 DLL (no hardware, any OS)."""

import ctypes
import os

import pytest

from qicklab.hardware import attenuator

BAD_PARAMETER = -0x7FFF0000  # 0x80010000 as the signed int the DLL returns


class FakeVnx:
    """The fnLDA_* subset set_attenuation calls; device ids are 100 + slot."""

    def __init__(self, serials, max_hr=1260, min_hr=0, readback=None, codes=None):
        self.serials = list(serials)
        self.max_hr, self.min_hr = max_hr, min_hr
        self.readback = readback  # None: echo the set value
        self.codes = codes or {}
        self.set_hr = None
        self.open = set()
        self.calls = []

    def fnLDA_SetTestMode(self, mode):
        self.calls.append("SetTestMode")

    def fnLDA_GetNumDevices(self):
        return len(self.serials)

    def fnLDA_GetDevInfo(self, devices):
        for i in range(len(self.serials)):
            devices[i] = 100 + i
        return len(self.serials)

    def fnLDA_GetSerialNumber(self, dev):
        return self.serials[dev - 100]

    def fnLDA_InitDevice(self, dev):
        self.open.add(dev)
        return self.codes.get("InitDevice", 0)

    def fnLDA_GetMinAttenuationHR(self, dev):
        return self.min_hr

    def fnLDA_GetMaxAttenuationHR(self, dev):
        return self.max_hr

    def fnLDA_SetChannel(self, dev, ch):
        return self.codes.get("SetChannel", 0)

    def fnLDA_SetAttenuationHR(self, dev, hr):
        assert isinstance(hr, int)
        self.set_hr = hr
        return self.codes.get("SetAttenuationHR", 0)

    def fnLDA_GetAttenuationHR(self, dev):
        return self.set_hr if self.readback is None else self.readback

    def fnLDA_CloseDevice(self, dev):
        self.open.discard(dev)
        return self.codes.get("CloseDevice", 0)


@pytest.fixture
def fake(monkeypatch):
    def install(*args, **kwargs):
        vnx = FakeVnx(*args, **kwargs)
        monkeypatch.setattr(attenuator, "_load_dll", lambda dll_dir=None: vnx)
        return vnx

    return install


def test_sets_found_serial_and_returns_readback(fake):
    vnx = fake([111, 27786])
    assert attenuator.set_attenuation(30, 27786) == pytest.approx(30.0)
    assert vnx.set_hr == 600
    assert not vnx.open


def test_finds_serial_beyond_the_fifth_device(fake):
    # legacy looped range(5): a 7th device was never reached
    vnx = fake([1, 2, 3, 4, 5, 6, 27786])
    assert attenuator.set_attenuation(12.35, 27786) == pytest.approx(12.35)
    assert vnx.set_hr == 247


def test_more_devices_than_the_legacy_array(fake):
    vnx = fake(list(range(1, 80)) + [27786])
    attenuator.set_attenuation(1, 27786)
    assert vnx.set_hr == 20


def test_missing_serial_raises_with_serials_found(fake):
    vnx = fake([111, 222])
    with pytest.raises(LookupError, match=r"27786.*\[111, 222\]"):
        attenuator.set_attenuation(30, 27786)
    assert vnx.set_hr is None


def test_negative_readback_raises_runtime_error_not_name_error(fake):
    vnx = fake([27786], readback=BAD_PARAMETER)
    with pytest.raises(RuntimeError, match="GetAttenuationHR returned error 0x80010000"):
        attenuator.set_attenuation(30, 27786, verbose=True)
    assert not vnx.open


def test_readback_mismatch_raises(fake):
    fake([27786], readback=500)
    with pytest.raises(RuntimeError, match="reads 25 dB after setting 30 dB"):
        attenuator.set_attenuation(30, 27786)


@pytest.mark.parametrize("db", [63.05, 100.0, -0.05, float("nan")])
def test_out_of_range_db_is_not_sent(fake, db):
    vnx = fake([27786], max_hr=1260)  # a 63 dB model
    with pytest.raises(ValueError):
        attenuator.set_attenuation(db, 27786)
    assert vnx.set_hr is None
    assert not vnx.open


def test_device_max_is_not_hard_coded(fake):
    vnx = fake([27786], max_hr=1915)  # 95.75 dB model
    assert attenuator.set_attenuation(95.75, 27786) == pytest.approx(95.75)
    assert vnx.set_hr == 1915


@pytest.mark.parametrize("call", ["InitDevice", "SetChannel", "SetAttenuationHR", "CloseDevice"])
def test_error_codes_raise_and_device_is_closed(fake, call):
    vnx = fake([27786], codes={call: BAD_PARAMETER})
    with pytest.raises(RuntimeError, match=f"fnLDA_{call} returned error 0x80010000"):
        attenuator.set_attenuation(30, 27786)
    if call != "InitDevice":
        assert not vnx.open


def test_dll_dir_registration_is_held_until_the_dll_loads(monkeypatch, tmp_path):
    events = []

    class Handle:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            events.append("close")

    class FakeLoader:
        def LoadLibrary(self, name):
            events.append(("load", name))
            return "dll"

    monkeypatch.setattr(
        os, "add_dll_directory", lambda d: events.append(("add", d)) or Handle(), raising=False
    )
    monkeypatch.setattr(ctypes, "cdll", FakeLoader())
    assert attenuator._load_dll(tmp_path) == "dll"
    assert events == [
        ("add", str(tmp_path)),
        ("load", os.path.join(str(tmp_path), "VNX_atten64.dll")),
        "close",
    ]


def test_without_dll_dir_uses_the_normal_search(monkeypatch):
    class FakeLoader:
        def LoadLibrary(self, name):
            return name

    monkeypatch.setattr(ctypes, "cdll", FakeLoader())
    assert attenuator._load_dll() == "VNX_atten64.dll"
