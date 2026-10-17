"""Vaunix LDA step attenuator driven through ``VNX_atten64.dll`` (Windows only; the DLL is not in
the repository). Nothing is loaded at import: the DLL is loaded by ``set_attenuation``.
docs/hardware.md#attenuator-vaunix-lda
"""

import ctypes
import math
import os

DLL_NAME = "VNX_atten64.dll"
DEFAULT_SERIAL = 27786
HR_STEP_DB = 0.05  # the *HR calls count attenuation in 0.05 dB units
_MIN_DEVICE_ARRAY = 64  # the SDK's MAXDEVICES: GetDevInfo may fill this many slots


def _load_dll(dll_dir=None):
    """Load ``VNX_atten64.dll``. With ``dll_dir``, register it with ``os.add_dll_directory`` (Python
    3.8+ does not search PATH for DLLs) and keep that registration open until the DLL has loaded.
    Without it, the normal DLL search applies (the caller registered the directory itself)."""
    if dll_dir is None:
        return ctypes.cdll.LoadLibrary(DLL_NAME)
    if not hasattr(os, "add_dll_directory"):
        raise OSError(f"{DLL_NAME} is a Windows DLL; os.add_dll_directory is Windows-only")
    with os.add_dll_directory(os.fspath(dll_dir)):
        return ctypes.cdll.LoadLibrary(os.path.join(os.fspath(dll_dir), DLL_NAME))


def _check(code, call, serial):
    if code != 0:
        raise RuntimeError(
            f"Vaunix LDA serial {serial}: fnLDA_{call} returned error {code & 0xFFFFFFFF:#010x}"
        )


def set_attenuation(db, serial=DEFAULT_SERIAL, dll_dir=None, verbose=False):
    """Set channel 1 of the LDA attenuator with serial number ``serial`` to ``db`` dB and return
    the attenuation read back from the device, in dB.

    ``dll_dir``: directory holding ``VNX_atten64.dll``; registered with ``os.add_dll_directory``
    for the load. Raises ``LookupError`` (listing the serials found) when no attached device has
    ``serial``, ``ValueError`` when ``db`` is outside the device's own min/max attenuation,
    ``RuntimeError`` when an SDK call returns an error code or the read-back differs from the
    request by more than half a 0.05 dB step. The device is closed again on every path.
    """
    db = float(db)
    if not math.isfinite(db):
        raise ValueError(f"attenuation must be finite, got {db!r}")
    vnx = _load_dll(dll_dir)
    vnx.fnLDA_SetTestMode(False)

    num_devices = vnx.fnLDA_GetNumDevices()
    if verbose:
        print(f"{num_devices} device(s) found")
    devices = (ctypes.c_int * max(num_devices, _MIN_DEVICE_ARRAY))()
    num_active = vnx.fnLDA_GetDevInfo(devices)
    serials = [vnx.fnLDA_GetSerialNumber(devices[i]) for i in range(min(num_active, len(devices)))]
    if verbose:
        for i, s in enumerate(serials):
            print(f"Device {i} serial number: {s}")
    if serial not in serials:
        raise LookupError(f"no Vaunix LDA attenuator with serial {serial}; found serials {serials}")
    dev = devices[serials.index(serial)]
    if verbose:
        print(f"Device was found to be device {serials.index(serial)}")

    _check(vnx.fnLDA_InitDevice(dev), "InitDevice", serial)
    try:
        lo, hi = vnx.fnLDA_GetMinAttenuationHR(dev), vnx.fnLDA_GetMaxAttenuationHR(dev)
        if lo < 0 or hi < 0:
            raise RuntimeError(
                f"Vaunix LDA serial {serial}: attenuation range query returned error ({lo}, {hi})"
            )
        steps = int(round(db / HR_STEP_DB))
        if not lo <= steps <= hi:
            raise ValueError(
                f"{db} dB is outside the range of Vaunix LDA serial {serial}: "
                f"{lo * HR_STEP_DB:g} to {hi * HR_STEP_DB:g} dB"
            )
        _check(vnx.fnLDA_SetChannel(dev, 1), "SetChannel", serial)
        _check(vnx.fnLDA_SetAttenuationHR(dev, steps), "SetAttenuationHR", serial)
        readback = vnx.fnLDA_GetAttenuationHR(dev)
        if readback < 0:
            _check(readback, "GetAttenuationHR", serial)
        atten_db = readback * HR_STEP_DB
        if abs(atten_db - db) > HR_STEP_DB / 2 + 1e-9:
            raise RuntimeError(
                f"Vaunix LDA serial {serial} reads {atten_db:g} dB after setting {db:g} dB"
            )
        if verbose:
            print("Set attenuation:", atten_db)
    except BaseException:
        vnx.fnLDA_CloseDevice(dev)  # the original error wins over a close error
        raise
    _check(vnx.fnLDA_CloseDevice(dev), "CloseDevice", serial)
    return atten_db


if __name__ == "__main__":
    # Manual hardware check: 30 dB on serial 27786, DLL in the current directory (as the legacy
    # driver assumed).
    set_attenuation(30, DEFAULT_SERIAL, dll_dir=os.getcwd(), verbose=True)
