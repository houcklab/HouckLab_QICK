import sys
import types


qick = sys.modules.get("qick")
if qick is None:
    qick = types.ModuleType("qick")
    qick.AveragerProgram = type("AveragerProgram", (), {})
    qick.RAveragerProgram = type("RAveragerProgram", (), {})
    sys.modules["qick"] = qick


from WorkingProjects.TLS_Spectroscopy.Client_modules.Experiments import (
    mRabiChevronIQ as R,
    mTransmissionVsFlux as TVF,
)
from WorkingProjects.TLS_Spectroscopy.Client_modules.Helpers import ff_pulse


class FakeProgram:
    def __init__(self, cfg):
        self.cfg = dict(cfg)
        self.events = []

    def us2cycles(self, value, **kwargs):
        return int(round(float(value) * 100))

    def sync_all(self, cycles):
        self.events.append(("sync", int(cycles)))

    def pulse(self, **kwargs):
        self.events.append(("pulse", kwargs.get("ch")))

    def measure(self, **kwargs):
        self.events.append(("measure", kwargs.get("pulse_ch")))


def test_build_park_hold_uses_config_in_dynamic_programs(monkeypatch):
    program = FakeProgram({"ff_ch": 3, "ff_park_gain": -7000})
    monkeypatch.setattr(
        ff_pulse,
        "build_ramp_hold_ramp",
        lambda prog, **kwargs: kwargs,
    )

    segments = ff_pulse.build_park_hold(program, hold_us=0.5)

    assert segments["ff_gain"] == -7000
    assert segments["park_gain"] == 0
    assert segments["hold_us"] == 0.5


def test_rabi_excursion_enters_park_before_payload_and_releases_after_readout(monkeypatch):
    cfg = {
        "reset_mode": "passive",
        "n_pulses": 1,
        "qubit_ch": 1,
        "res_ch": 0,
        "ro_chs": [0],
        "adc_trig_offset": 0.5,
        "readout_after_park": True,
        "relax_delay": 400.0,
        "flux_settle_time_us": 0.5,
    }
    program = FakeProgram(cfg)
    program.ff_park_segs = "park"
    program.ff_segs = "excursion"
    program.do_flux_hold = True
    monkeypatch.setattr(
        R.ff_pulse,
        "play_park_up",
        lambda prog, segs: prog.events.append(("park_up", segs)),
    )
    monkeypatch.setattr(
        R.ff_pulse,
        "play_park_down",
        lambda prog, segs: prog.events.append(("park_down", segs)),
    )
    monkeypatch.setattr(
        R.ff_pulse,
        "play_ramp_up_hold",
        lambda prog, segs, **kwargs: prog.events.append(("excursion_up", segs)),
    )
    monkeypatch.setattr(
        R.ff_pulse,
        "play_ramp_down",
        lambda prog, segs: prog.events.append(("excursion_down", segs)),
    )

    R.rabi_flux_body(program)

    names = [event[0] for event in program.events]
    assert names[0] == "park_up"
    assert names.index("park_up") < names.index("excursion_up")
    assert names.index("excursion_down") < names.index("measure")
    assert names.index("measure") < names.index("park_down")
    assert names[-1] == "sync"


def test_external_flux_transmission_bounds_static_rfsoc_park(monkeypatch):
    program = FakeProgram({
        "res_ch": 0,
        "ro_chs": [0],
        "adc_trig_offset": 0.5,
        "relax_delay": 400.0,
    })
    program.ff_park_segs = "park"
    monkeypatch.setattr(
        TVF.ff_pulse,
        "play_park_up",
        lambda prog, segs: prog.events.append(("park_up", segs)),
    )
    monkeypatch.setattr(
        TVF.ff_pulse,
        "play_park_down",
        lambda prog, segs: prog.events.append(("park_down", segs)),
    )

    TVF.TransmissionProgram.body(program)

    names = [event[0] for event in program.events]
    assert names == ["park_up", "measure", "park_down", "sync"]
