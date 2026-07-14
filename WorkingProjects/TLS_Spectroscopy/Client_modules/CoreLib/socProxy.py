"""
Pyro4 proxy connection to the RFSoC running the FTTv02_SiOxJJ device.

This is a direct copy of the connection used by the QM_Team / BFF_ACStark QICK
setup for the same board (nameserver 192.168.1.125:8888, server name "myqick").

NOTE (deliberate difference from some lab copies of socProxy.py): this module does
NOT open a connection at import time.  Importing ``initialize`` therefore does not
attempt a live Pyro4 connection, so the modules import cleanly off the lab network.
Call ``makeProxy()`` explicitly from a runner when you actually want the board.
"""

import Pyro4
from qick import QickConfig

# Default nameserver for the FTTv02_SiOxJJ RFSoC.  Override per-call if the board
# is served from a different host.
DEFAULT_NS_HOST = "192.168.1.125"
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

    # print the nameserver entries: you should see the QickSoc proxy
    for k, v in ns.list().items():
        print(k, v)

    soc = Pyro4.Proxy(ns.lookup(server_name))
    soccfg = QickConfig(soc.get_cfg())
    return soc, soccfg


# Alternate boards seen on the FTTv02 setup (kept for convenience / parity with
# the QM_Team socProxy.py).  Uncomment / edit as needed.
def makeProxy_RFSOC_124():
    return makeProxy(ns_host="192.168.1.124")
