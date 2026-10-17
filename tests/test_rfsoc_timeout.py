"""make_proxy bounds every remote call: a dead board raises instead of hanging forever (F80).

Hardware-free: a local Pyro4 nameserver plus a daemon serving a stand-in soc on 127.0.0.1.
"""

import socket
import threading
import time

import Pyro4
import Pyro4.errors
import Pyro4.naming
import pytest

import qicklab.core.context as context_mod
import qicklab.hardware.rfsoc as rfsoc
from tests.regression import capture

LOCALHOST = "127.0.0.1"


@Pyro4.expose
class SlowSoc:
    def get_cfg(self):
        return {}

    def nap(self, seconds):
        time.sleep(seconds)
        return seconds


@pytest.fixture
def pyro_globals(monkeypatch):
    """Let the local servers speak pickle and undo make_proxy's global serializer changes."""
    for attr in ("SERIALIZER", "PICKLE_PROTOCOL_VERSION", "COMMTIMEOUT", "SERIALIZERS_ACCEPTED"):
        monkeypatch.setattr(Pyro4.config, attr, getattr(Pyro4.config, attr))
    Pyro4.config.SERIALIZERS_ACCEPTED = set(Pyro4.config.SERIALIZERS_ACCEPTED) | {"pickle"}
    monkeypatch.setattr(rfsoc, "QickConfig", lambda cfg: cfg)  # no board config to parse


@pytest.fixture
def local_board(pyro_globals):
    """A nameserver and a daemon that registers a SlowSoc as ``myqick``; yields the NS port."""
    ns_uri, ns_daemon, _ = Pyro4.naming.startNS(host=LOCALHOST, port=0, enableBroadcast=False)
    daemon = Pyro4.Daemon(host=LOCALHOST)
    uri = daemon.register(SlowSoc())
    stop = threading.Event()
    threads = [
        threading.Thread(target=d.requestLoop, args=(lambda: not stop.is_set(),), daemon=True)
        for d in (ns_daemon, daemon)
    ]
    for t in threads:
        t.start()
    with Pyro4.Proxy(ns_uri) as ns:
        ns.register("myqick", uri)
    yield ns_uri.port
    stop.set()
    daemon.shutdown()
    ns_daemon.shutdown()


def test_default_timeout_covers_a_poll_data_stride():
    # soc.poll_data blocks until one streamer stride is done: int(0.1 avg_maxlen / reads) shots.
    avg_maxlen = capture.FakeSocCfg()["readouts"][0]["avg_maxlen"]
    stride_s = int(0.1 * avg_maxlen / 1) * 8000e-6  # one read per shot, 8 ms relax_delay
    assert 10 < stride_s < 20
    assert rfsoc.DEFAULT_TIMEOUT_S >= 10 * stride_s


def test_hung_call_raises_timeout_error(local_board):
    soc, soccfg = rfsoc.make_proxy(host=LOCALHOST, port=local_board, timeout=0.5)
    assert soccfg == {}
    assert soc._pyroTimeout == 0.5
    t0 = time.monotonic()
    with pytest.raises(Pyro4.errors.TimeoutError):
        soc.nap(3.0)
    assert time.monotonic() - t0 < 2.5
    soc._pyroRelease()


def test_default_timeout_lets_normal_calls_finish(local_board):
    soc, _ = rfsoc.make_proxy(host=LOCALHOST, port=local_board)
    assert soc._pyroTimeout == rfsoc.DEFAULT_TIMEOUT_S
    assert soc.nap(0.2) == 0.2
    assert Pyro4.config.COMMTIMEOUT == 0.0  # the global is restored after locateNS
    soc._pyroRelease()


def test_timeout_none_keeps_the_old_unbounded_proxy(local_board):
    soc, _ = rfsoc.make_proxy(host=LOCALHOST, port=local_board, timeout=None)
    assert not soc._pyroTimeout
    assert soc.nap(0.1) == 0.1
    soc._pyroRelease()


def test_silent_nameserver_raises_instead_of_hanging(pyro_globals):
    # a listener that accepts the TCP connection and never answers the Pyro handshake,
    # like a board whose server process is wedged
    silent = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    silent.bind((LOCALHOST, 0))
    silent.listen(1)
    try:
        t0 = time.monotonic()
        with pytest.raises(Pyro4.errors.NamingError):  # locateNS wraps the TimeoutError
            rfsoc.make_proxy(host=LOCALHOST, port=silent.getsockname()[1], timeout=0.5)
        assert time.monotonic() - t0 < 5
        assert Pyro4.config.COMMTIMEOUT == 0.0
    finally:
        silent.close()


def test_build_context_passes_endpoint_and_timeout(monkeypatch):
    seen = {}

    class _Stop(Exception):
        pass

    def _record(**kwargs):
        seen.update(kwargs)
        raise _Stop

    monkeypatch.setattr(context_mod, "makeProxy", _record)
    qp = {
        "1": {
            "Readout": {"Gain": 1000, "Frequency": 7000.0},
            "Qubit": {"Gain": 1000, "pi2_Gain": 500, "Frequency": 3000.0},
            "outerfoldername": "",
        }
    }
    common = dict(
        Transmission_params={},
        Spec_relevant_params={"qubit_gain": 800},
        tl={},
        ts={},
        charge_params={},
    )
    with pytest.raises(_Stop):
        context_mod.build_context(qp, 1, 1, 0.0, **common)
    assert seen == dict(
        host="192.168.0.103", port=8888, name="myqick", timeout=rfsoc.DEFAULT_TIMEOUT_S
    )
    with pytest.raises(_Stop):
        context_mod.build_context(
            qp,
            1,
            1,
            0.0,
            rfsoc_host="192.168.1.10",
            rfsoc_port=9999,
            rfsoc_name="otherqick",
            rfsoc_timeout_s=None,
            **common,
        )
    assert seen == dict(host="192.168.1.10", port=9999, name="otherqick", timeout=None)
