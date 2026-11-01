"""The triangle-lattice backend: stitching, padding, delays, clipping, compensation, cfg."""
import numpy as np
import pytest

from Bob.blocks.registry import make_block
from Bob.compiler.backend import CompileError
from Bob.compiler.tlq_backend import TLQBackend, compile_sequence
from Bob.config.resolver import Resolver
from Bob.core.params import Value, VectorSource
from Bob.core.sequence import Sequence
from Bob.hardware.compensation import Compensator


def _compile(seq, st, calib, compensate=False, compensator=None):
    res = Resolver(st, calib).resolve(seq)
    assert res.ok, [str(p) for p in res.problems]
    return TLQBackend(st, compensator or Compensator.disabled(), compensate=compensate).compile(seq, res), res


def test_waveform_is_whole_cycles_padded_at_readout_level(basic_seq, station, calib):
    prog, res = _compile(basic_seq, station, calib)
    assert prog.n_samples % 16 == 0
    ro = np.asarray(res.measure.params["ff_readout_gains"])
    assert np.allclose(prog.ff_raw[:, -1], ro)
    body = res.segments[0].wave.length
    assert np.allclose(prog.ff_raw[:, 0], res.segments[0].params["gains"])
    assert np.allclose(prog.ff_raw[:, body + 1], ro)                # tail starts right after the body


def test_channel_delays_shift_each_channel(basic_seq, fresh_station, calib):
    delays = [0, 5, 10, 0, 0, 0, 0, 3]
    fresh_station.data["ff_channel_delays_samples"] = delays
    prog, res = _compile(basic_seq, fresh_station, calib)
    init = res.segments[0].params["gains"]
    body = res.segments[0].wave.length
    for j, d in enumerate(delays):
        assert np.all(prog.ff_raw[j, :d] == init[j])                 # head at the init level
        tail_start = d + body
        assert prog.ff_raw[j, tail_start] == res.measure.params["ff_readout_gains"][j]


def test_out_of_range_after_compensation_is_clipped_and_reported(basic_seq, fresh_station, calib, tmp_path):
    # a "filter" that doubles the waveform pushes gains past 32766
    iir = tmp_path / "iir"
    iir.mkdir()
    np.savetxt(iir / "x.csv", np.vstack([np.r_[1.0, 0, 0] + 0j, np.r_[2.0, 0, 0] + 0j]))
    fresh_station.folder = tmp_path
    fresh_station.data["compensation"] = {"iir_dir": "iir", "files": {str(q): ["x.csv"] for q in range(1, 9)}}
    h = basic_seq.segments[0]
    h.set_field("gains", VectorSource(Value([30000.0] + [0.0] * 7)))
    res = Resolver(fresh_station, calib).resolve(basic_seq)
    prog = TLQBackend(fresh_station).compile(basic_seq, res)
    assert prog.compensated
    assert np.abs(prog.ff).max() <= 32766
    assert any("exceeds" in p.message for p in res.problems)


def test_missing_iir_files_compile_uncompensated_with_a_note(basic_seq, station, calib):
    prog, _ = _compile(basic_seq, station, calib, compensate=True, compensator=Compensator.from_station(station))
    assert not prog.compensated
    assert any("IIR compensation files not found" in n for n in prog.notes)


def test_qick_cfg_contents(basic_seq, station, calib):
    basic_seq.settings.reps = 777
    prog, res = _compile(basic_seq, station, calib)
    cfg = prog.qick_cfg
    assert cfg["reps"] == 777
    assert cfg["relax_delay"] == station["relax_delay"]
    assert cfg["fast_flux_chs"] == station["fast_flux_chs"]
    d = cfg["bob"]["drives"][0]
    q3 = calib.get("drive_groups/readout_3800/entries/3/Qubit")
    assert d["freq"] == pytest.approx(q3["Frequency"] - station["qubit_LO"])
    assert d["gain"] == pytest.approx(q3["Gain"] / 32766)
    assert d["length"] == pytest.approx(4 * q3["sigma"])
    assert cfg["Qubit_Readout_List"] == [1, 2, 3, 4]
    assert cfg["bob"]["init_hold_us"] == station["init_hold_us"]


def test_relax_delay_override(basic_seq, station, calib):
    basic_seq.settings.relax_delay_us = 55.0
    prog, _ = _compile(basic_seq, station, calib)
    assert prog.qick_cfg["relax_delay"] == 55.0


def test_drive_offset_cycles_delays_drives(basic_seq, fresh_station, calib):
    p0, _ = _compile(basic_seq, fresh_station, calib)
    fresh_station.data["drive_offset_cycles"] = 3
    p3, _ = _compile(basic_seq, fresh_station, calib)
    assert p3.drives[0].t_us - p0.drives[0].t_us == pytest.approx(3 * fresh_station.cycle_us)


def test_compile_refuses_sequences_with_errors(basic_seq, station, calib):
    basic_seq.pulses[0].set_field("freq", Value(9999.0))
    compiled, res, problems = compile_sequence(basic_seq, station, calib)
    assert compiled is None
    assert any(p.level == "error" and "mixer band" in p.message for p in problems)


def test_backend_raises_on_unresolved_sequence(station, calib):
    s = Sequence()
    s.insert_segment(make_block("FFRamp"))                            # FromPrev with nothing before it
    res = Resolver(station, calib).resolve(s)
    with pytest.raises(CompileError):
        TLQBackend(station).compile(s, res)


def test_empty_sequence_does_not_compile_but_is_not_an_error(station, calib):
    compiled, res, problems = compile_sequence(Sequence(), station, calib)
    assert compiled is None
    assert all(p.level != "error" for p in problems)


def test_segment_bounds_and_names(station, calib):
    s = Sequence()
    for name, us in (("a", 0.1), ("b", 0.2)):
        b = make_block("FFHold", name=name)
        b.set_field("duration_us", Value(us))
        s.insert_segment(b)
    prog, res = _compile(s, station, calib)
    n0 = res.segments[0].wave.length
    assert prog.segment_bounds[:2] == [0, n0] and prog.segment_names == ["a", "b"]
