"""Core model, resolver and validator."""
import pytest

from Bob.blocks.registry import all_block_classes, make_block
from Bob.config.resolver import Resolver
from Bob.config.settings import SweepAxis
from Bob.config.validate import validate
from Bob.core.params import FromPrev, Ref, Sweep, Value, VectorSource, source_from_dict
from Bob.core.sequence import Sequence


def _basic(hold_us=0.4):
    s = Sequence()
    h = make_block("FFHold")
    h.set_field("duration_us", Value(hold_us))
    s.insert_segment(h)
    p = make_block("PiPulse")
    p.set_field("qubit", Value(3))
    s.add_pulse(p, h.id)
    s.set_measure(make_block("Measure"))
    return s, h, p


def test_eight_base_blocks():
    assert [c.TYPE for c in all_block_classes()] == [
        "FFHold", "FFRamp", "FFDynamics", "PiPulse", "Pi2Pulse", "Drive", "Beamsplitter", "Measure"]


@pytest.mark.parametrize("src", [Value(3), Value([1, None]), Ref("calib:a/b", 0.5), Sweep("t"), FromPrev(),
                                 VectorSource(Ref("calib:x"), {2: 100.0})])
def test_source_round_trip(src):
    assert source_from_dict(src.to_dict()) == src


def test_sequence_round_trip():
    s, _, _ = _basic()
    s.settings.sweeps.append(SweepAxis("t", 0, 1, 11, "us"))
    d = s.to_dict()
    assert Sequence.from_dict(d).to_dict() == d


def test_remove_segment_removes_its_pulses():
    s, h, p = _basic()
    removed = s.remove(h.id)
    assert {b.id for b in removed} == {h.id, p.id}
    assert s.pulses == [] and s.segments == []


def test_two_ramps_stay_separate(station, calib):
    s = Sequence()
    s.insert_segment(make_block("FFHold"))
    r1, r2 = make_block("FFRamp", name="r1"), make_block("FFRamp", name="r2")
    r2.set_field("ramp_entry", Value("1234"))
    s.insert_segment(r1)
    s.insert_segment(r2)
    res = Resolver(station, calib).resolve(s)
    assert res.ok
    e1, e2 = res.segments[1].params["end_gains"], res.segments[2].params["end_gains"]
    assert e1 != e2
    # r2 starts where r1 ended
    assert res.segments[2].params["start_gains"] == e1


def test_refs_resolve_against_real_calibration(station, calib):
    s, h, p = _basic()
    res = Resolver(station, calib).resolve(s)
    assert res.ok, [str(x) for x in res.problems]
    q3 = calib.get("drive_groups/readout_3800/entries/3/Qubit")
    d = res.pulses[0].drive
    assert (d.freq_mhz, d.gain, d.sigma_us) == (q3["Frequency"], q3["Gain"], q3["sigma"])
    assert res.segments[0].params["gains"] == calib.get("drive_groups/readout_3800/FF_Pulses")


def test_pi2_is_half_gain(station, calib):
    s, h, _ = _basic()
    p2 = make_block("Pi2Pulse")
    p2.set_field("qubit", Value(3))
    s.add_pulse(p2, h.id)
    res = Resolver(station, calib).resolve(s)
    assert res.pulses[1].drive.gain == pytest.approx(res.pulses[0].drive.gain / 2)


def test_entry_field_avoids_name_parsing(station, calib):
    s, h, p = _basic()
    p.set_field("drive_group", Value("ramsey_3800+"))
    p.set_field("entry", Value("3_3800+"))
    res = Resolver(station, calib).resolve(s)
    assert res.ok
    assert res.pulses[0].drive.freq_mhz == calib.get("drive_groups/ramsey_3800+/entries/3_3800+/Qubit/Frequency")


def test_vector_override(station, calib):
    s, h, _ = _basic()
    h.set_field("gains", VectorSource(Ref("calib:drive_groups/{group}/FF_Pulses"), {2: 1234.0}))
    res = Resolver(station, calib).resolve(s)
    g = res.segments[0].params["gains"]
    assert g[2] == 1234.0 and g[0] == calib.get("drive_groups/readout_3800/FF_Pulses")[0]


def test_sweep_values_flow_through(station, calib):
    s, h, _ = _basic()
    h.set_field("duration_us", Sweep("t"))
    s.settings.sweeps.append(SweepAxis("t", 0.5, 1.5, 3, "us"))
    r = Resolver(station, calib)
    lengths = [r.resolve(s, pt).segments[0].wave.length for _, pt in s.settings.iter_points()]
    assert lengths == [round(x * station.samples_per_us) for x in (0.5, 1.0, 1.5)]


def test_resolver_problems_name_the_field(station, calib):
    s, h, p = _basic()
    h.set_field("duration_us", Sweep("nope"))
    p.set_field("freq", Ref("calib:drive_groups/readout_3800/entries/3/Qubit/Freq"))
    s.segments.insert(0, make_block("FFRamp"))          # FromPrev with nothing before it
    res = Resolver(station, calib).resolve(s)
    fields = {(x.block_id, x.field) for x in res.problems}
    assert (h.id, "duration_us") in fields
    assert (p.id, "freq") in fields
    assert (s.segments[0].id, "start_gains") in fields
    msg = next(x.message for x in res.problems if x.field == "freq")
    assert "'Freq' not found" in msg and "Frequency" in msg


def test_validator_catches_pulse_overflow_and_order(station, calib):
    s, h, p = _basic(hold_us=0.05)
    s.insert_segment(make_block("FFHold", act="readout"))
    s.insert_segment(make_block("FFHold", act="prep"))
    res = Resolver(station, calib).resolve(s)
    probs = validate(s, res, station)
    msgs = " ".join(x.message for x in probs)
    assert "past the end of its segment" in msgs
    assert "acts must run" in msgs


def test_validator_mixer_band(station, calib):
    s, h, p = _basic()
    p.set_field("freq", Value(6000.0))
    res = Resolver(station, calib).resolve(s)
    assert any("mixer band" in x.message for x in validate(s, res, station))


def test_populations_need_single_shot(station, calib):
    s, _, _ = _basic()
    s.measure.set_field("readout_group", Value("Upper_sweetspot"))
    res = Resolver(station, calib).resolve(s)
    has_ss = all(calib.get(f"drive_groups/Upper_sweetspot/entries/{q}").get("SingleShot") for q in (1, 2, 3, 4))
    found = any("SingleShot" in x.message for x in validate(s, res, station))
    assert found == (not has_ss)


def test_sweep_users_lists_fields_in_play_order():
    from Bob.core.params import Sweep
    from Bob.core.sequence import Sequence, sweep_users_text
    from Bob.library import build_library
    seq = Sequence.load(build_library.HERE / "templates" / "mott_quench.json")
    init = seq.segments[0]
    init.set_field("duration_us", Sweep("t_dyn"))
    users = seq.sweep_users()
    assert list(users) == ["t_dyn"]
    assert sweep_users_text(users["t_dyn"]) == "Init › Duration, Quench › Duration"
