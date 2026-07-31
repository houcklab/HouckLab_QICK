import Pyro4
from qick import QickConfig

DEFAULT_NS_HOST = "192.168.1.139"
NS_PORT = 8888
SERVER_NAME = "myqick"


def makeProxy(ns_host=DEFAULT_NS_HOST, ns_port=NS_PORT, server_name=SERVER_NAME):
    """Open a Pyro4 proxy to the QickSoc on the board.

    Returns
    -------
    (soc, soccfg)
        ``soc``    : Pyro4 proxy to the remote ``QickSoc`` (all board I/O).
        ``soccfg`` : a *local* ``QickConfig`` built from ``soc.get_cfg()`` for
                     unit conversions (freq2reg / us2cycles / deg2reg) with no
                     round-trips to the board.
    """
    Pyro4.config.SERIALIZER = "pickle"
    Pyro4.config.PICKLE_PROTOCOL_VERSION = 4

    ns = Pyro4.locateNS(host=ns_host, port=ns_port)

    for k, v in ns.list().items():
        print(k, v)

    soc = Pyro4.Proxy(ns.lookup(server_name))
    soccfg = QickConfig(soc.get_cfg())
    return soc, soccfg


def makeProxy_RFSOC_124():
    return makeProxy(ns_host="192.168.1.124")
