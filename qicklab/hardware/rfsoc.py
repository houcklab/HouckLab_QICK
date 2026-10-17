import Pyro4
from qick import QickConfig

# Per-call Pyro4 communication timeout [s]. The longest legitimate remote call is soc.poll_data(),
# which blocks on the board until one streamer stride of shots is done:
#     int(0.1 * avg_maxlen / reads_per_shot) * (relax_delay + sequence) ~ 13 s
# for avg_maxlen 16384 and an 8 ms relax_delay. 300 s leaves room for longer records while still
# turning a dead board (power cycle, lost network: no TCP reset ever arrives) into an error.
DEFAULT_TIMEOUT_S = 300.0


def make_proxy(host="192.168.0.103", port=8888, name="myqick", timeout=DEFAULT_TIMEOUT_S):
    """Connect to the QICK Pyro4 server and return ``(soc, soccfg)``.

    Prints the nameserver listing and sets the global Pyro4 serializer to pickle (protocol 4);
    see docs/hardware.md#rfsoc.

    ``timeout`` [s] bounds every remote call on the nameserver and on ``soc`` (Pyro4 raises
    ``Pyro4.errors.TimeoutError``); ``None`` waits forever (the old behaviour). It is set per
    proxy; the global ``Pyro4.config.COMMTIMEOUT`` is changed only while locating the nameserver
    and restored afterwards. After a timeout inside ``acquire`` the board's Pyro worker can stay
    blocked in ``poll_data``; the next ``start_readout`` stops the tProc and drains the leftover
    readout, so a fresh acquire on a live board recovers. Nothing retries automatically.
    """
    Pyro4.config.SERIALIZER = "pickle"
    Pyro4.config.PICKLE_PROTOCOL_VERSION = 4

    if timeout is None:
        ns = Pyro4.locateNS(host=host, port=port)
    else:
        previous = Pyro4.config.COMMTIMEOUT
        Pyro4.config.COMMTIMEOUT = timeout  # locateNS builds and binds its proxy from the global
        try:
            ns = Pyro4.locateNS(host=host, port=port)
        finally:
            Pyro4.config.COMMTIMEOUT = previous
        ns._pyroTimeout = timeout

    for k, v in ns.list().items():
        print(k, v)

    soc = Pyro4.Proxy(ns.lookup(name))
    if timeout is not None:
        soc._pyroTimeout = timeout
    soccfg = QickConfig(soc.get_cfg())
    return (soc, soccfg)


makeProxy = make_proxy
