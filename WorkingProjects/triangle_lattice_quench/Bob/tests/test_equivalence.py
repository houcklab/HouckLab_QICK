"""Gate A at the waveform level: Bob's flux waveforms and drive times against the
existing code (tests/reference/legacy.py holds the original logic verbatim).

The full Gate A, compiling BobProgram and the original programs on a real QickConfig and
comparing the QICK programs, needs the board config saved at the lab
(library/stations/8QV1/soccfg.json); see README."""
import numpy as np
import pytest

from Bob.blocks.registry import make_block
from Bob.compiler.timing import schedule_drives
from Bob.compiler.tlq_backend import TLQBackend
from Bob.config.resolver import Resolver
from Bob.config.station import Station
from Bob.core.block import DriveSpec
from Bob.core.params import Value, VectorSource
from Bob.core.sequence import Sequence
from Bob.hardware.compensation import Compensator

from .reference import legacy


def _station(delays=None):
    st = Station.load("8QV1")
    st.data = dict(st.data)
    if delays is not None:
        st.data["ff_channel_delays_samples"] = list(delays)
    return st


def test_drive_schedule_matches_programbuilder():
    spu = 3440.64
    cyc = 16 / spu
    segs = [(37, [DriveSpec(1, 3800, 7000, 0, 0.03), DriveSpec(3, 3700, 9000, 0, 0.03)]),
            (100, []),
            (233, [DriveSpec(2, 3800, 1, 0, 0.02, relative_t=0.01), DriveSpec(2, 3800, 1, 0, 0.02)])]
    for offset in (0, 3):
        ours = schedule_drives([n for n, _ in segs], [[(i, d) for i, d in enumerate(ds)] for _, ds in segs],
                               spu, offset)
        ref = legacy.pb_drive_schedule([{"length": n, "drives": [{"relative_t": d.relative_t,
                                                                  "len_us": d.length_us()} for d in ds]}
                                        for n, ds in segs], cyc, offset)
        assert [round(s.t_us, 12) for s in ours] == [round(t, 12) for _, _, t in ref]


def test_stitching_matches_programbuilder_uncompensated(calib):
    delays = [22, 25, 14, 25, 14, 14, 14, 6]
    st = _station(delays)
    s = Sequence()
    a = make_block("FFHold")
    a.set_field("duration_us", Value(37 / st.samples_per_us))
    b = make_block("FFDynamics")
    b.set_field("duration_us", Value(250 / st.samples_per_us))
    s.insert_segment(a)
    s.insert_segment(b)
    s.set_measure(make_block("Measure"))
    res = Resolver(st, calib).resolve(s)
    prog = TLQBackend(st, Compensator.disabled(), compensate=False).compile(s, res)
    gains = [res.segments[0].params["gains"], res.segments[1].params["gains"]]
    ref, ref_len = legacy.pb_combined_iq(gains, [37, 250], np.array(delays) - min(delays),
                                         res.measure.params["ff_readout_gains"])
    for j in range(8):
        n = len(ref[j])
        assert np.array_equal(prog.ff_raw[j, :n], ref[j])
        # Bob pads the END to a whole clock cycle at the readout gains (ProgramBuilder pads the front)
        assert np.all(prog.ff_raw[j, n:] == res.measure.params["ff_readout_gains"][j])
    assert prog.n_samples % 16 == 0


def test_beamsplitter_matches_bsclean(calib, station):
    entry = calib.get("ff_groups/dynamics_groups/four_qubit_correlations/2345_bonds")
    bs = make_block("Beamsplitter")
    bs.set_field("bs_entry", Value("2345_bonds"))
    bs.set_field("bs_samples", VectorSource(Value(calib.get(
        "ff_groups/dynamics_groups/four_qubit_correlations/2345_bonds/exact_t_bs"))))
    bs.set_field("intermediate_gains", VectorSource(Value(entry["ij_gains"])))
    bs.set_field("intermediate_samples", VectorSource(Value(entry["ij_samples"])))
    bs.set_field("pad_samples", VectorSource(Value(entry["pad_bs"])))
    bs.set_field("extra_samples", Value(7))
    s = Sequence()
    s.insert_segment(make_block("FFRamp"))
    s.insert_segment(bs)
    s.segments.insert(0, make_block("FFHold"))
    res = Resolver(station, calib).resolve(s)
    assert res.ok, [str(p) for p in res.problems]
    p = res.segments[2].params
    ours = res.segments[2].wave.samples
    ref = legacy.bsclean_arrays(entry["t_offset"], entry["ij_gains"], entry["ij_samples"],
                                np.array(entry["exact_t_bs"]) + np.array(entry["pad_bs"]), 7,
                                entry["FF_BS"], p["from_gains"], p["exit_gains"])
    for j in range(8):
        assert np.array_equal(ours[j], ref[j]), j


def test_quench_matches_mottquench_uncompensated(calib):
    """MottQuench builds [t_offset @ Gain_Pulse, expt @ Gain_Expt, pad @ Gain_Readout] per channel.
    Bob gets the same samples from station delays = t_offset, a zero-length hold at the pulse
    gains (so the init level is Gain_Pulse) and a Dynamics segment."""
    t_off = [22, 25, 14, 25, 14, 14, 14, 6]
    st = _station(t_off)
    n_expt = 600
    s = Sequence()
    init = make_block("FFHold")
    init.set_field("duration_us", Value(0.0))
    q = make_block("FFDynamics")
    q.set_field("duration_us", Value(n_expt / st.samples_per_us))
    s.insert_segment(init)
    s.insert_segment(q)
    s.set_measure(make_block("Measure"))
    res = Resolver(st, calib).resolve(s)
    prog = TLQBackend(st, Compensator.disabled(), compensate=False).compile(s, res)
    ref = legacy.mott_quench_arrays(t_off, n_expt, res.segments[0].params["gains"],
                                    res.segments[1].params["gains"], res.measure.params["ff_readout_gains"])
    shift = np.array(t_off) - min(t_off)
    for j in range(8):
        n = shift[j] + n_expt              # the part MottQuench plays (FFPlay_Arb truncates to expt_samples)
        assert np.array_equal(prog.ff_raw[j, :n], ref[j][:n])


@pytest.fixture
def iir_station(tmp_path):
    """A station whose compensation folder holds small, stable synthetic IIR files."""
    rng = np.random.default_rng(0)
    st = _station()
    st.folder = tmp_path
    iir = tmp_path / "iir"
    iir.mkdir()
    files = {}
    for q in range(1, 9):
        names = []
        for k in range(2):
            b = np.r_[1.0, 0.3 * rng.standard_normal(2)] + 0j
            a = np.r_[1.0, -0.2 + 0.05 * rng.standard_normal(), 0.0] + 0j
            name = f"ff{q}_{k}.csv"
            np.savetxt(iir / name, np.vstack([a, b]))
            names.append(name)
        files[str(q)] = names
    st.data["compensation"] = dict(st.data["compensation"], iir_dir="iir", files=files)
    return st


def test_compensation_matches_original_and_shows_pb_offset_bug(iir_station):
    st = iir_station
    comp = Compensator.from_station(st)
    assert comp.available()
    files = {int(q): [str(st.folder / "iir" / f) for f in fs] for q, fs in st.data["compensation"]["files"].items()}
    scale = comp.asymptote_scale
    init, level = -18125.0, -6890.0
    arr = np.r_[np.full(50, init), np.full(400, level)]
    ours = comp.apply(arr - init, init, 1)
    original = legacy.Compensate(arr - init, init, 1, files, scale)   # how MottQuench / BSClean call it
    assert np.allclose(ours, original)
    pb_style = legacy.Compensate(arr, init, 1, files, scale)          # how ProgramBuilder calls it
    assert ours[0] == pytest.approx(init)
    assert abs(pb_style[0] - 2 * init) < abs(pb_style[0] - init)       # ProgramBuilder adds the init twice
