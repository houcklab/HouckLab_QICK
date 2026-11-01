"""Warning when calibration values a saved sequence used have changed."""
import json

from Bob.config.calib_drift import changed, describe_change, drift_problems, flatten, used_values
from Bob.config.calibration import CalibrationStore
from Bob.config.resolver import Resolver

Q3_FREQ = "drive_groups/readout_3800/entries/3/Qubit/Frequency"


def _edited(calib, edit):
    d = json.loads(json.dumps(calib.data))
    edit(d)
    return CalibrationStore(d, "edited.json", "other-hash")


def test_flatten_walks_dicts_and_keeps_lists():
    assert flatten("a", {"b": 1, "c": {"d": [1, 2]}}) == {"a/b": 1, "a/c/d": [1, 2]}


def test_records_refs_and_readout_entries(basic_seq, station, calib):
    used = used_values(Resolver(station, calib).resolve(basic_seq))
    assert used[Q3_FREQ] == calib.get(Q3_FREQ)
    assert "drive_groups/readout_3800/FF_Readouts" in used                     # Measure's FF gains
    assert "drive_groups/readout_3800/entries/1/Readout/Frequency" in used    # MUX readout of Q1
    json.dumps(used)                                                          # goes into the .json file


def test_no_warnings_when_nothing_changed(basic_seq, station, calib):
    res = Resolver(station, calib).resolve(basic_seq)
    assert drift_problems(used_values(res), res) == []
    assert drift_problems(None, res) == []


def test_changed_value_warns_on_the_block_that_uses_it(basic_seq, station, calib):
    baseline = used_values(Resolver(station, calib).resolve(basic_seq))

    def edit(d):
        d["drive_groups"]["readout_3800"]["entries"]["3"]["Qubit"]["Frequency"] += 2.5
    res = Resolver(station, _edited(calib, edit)).resolve(basic_seq)
    probs = drift_problems(baseline, res)
    assert len(probs) == 1
    p = probs[0]
    assert p.level == "warning" and p.block_id == basic_seq.pulses[0].id and p.field == "freq"
    assert "entries/3/Qubit/Frequency" in p.message and "Save to accept" in p.message


def test_vector_change_names_the_qubit(basic_seq, station, calib):
    baseline = used_values(Resolver(station, calib).resolve(basic_seq))

    def edit(d):
        d["drive_groups"]["readout_3800"]["FF_Readouts"][1] += 100
    res = Resolver(station, _edited(calib, edit)).resolve(basic_seq)
    msgs = [p.message for p in drift_problems(baseline, res)]
    assert any("FF_Readouts: Q2 " in m for m in msgs)


def test_values_not_used_when_saved_are_not_compared(basic_seq, station, calib):
    res = Resolver(station, calib).resolve(basic_seq)
    baseline = {k: v for k, v in used_values(res).items() if k != Q3_FREQ}

    def edit(d):
        d["drive_groups"]["readout_3800"]["entries"]["3"]["Qubit"]["Frequency"] += 1
    assert changed(baseline, Resolver(station, _edited(calib, edit)).resolve(basic_seq)) == []


def test_describe_change_lists_a_few_entries():
    s = describe_change("x/FF", [0, 0, 0, 0, 0], [1, 2, 3, 4, 0], n_channels=5)
    assert s.startswith("x/FF: Q1 0 → 1, Q2 0 → 2, Q3 0 → 3") and s.endswith("and 1 more")
