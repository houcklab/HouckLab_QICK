import Pyro4
from qick import QickConfig


def make_proxy(host="192.168.0.103", port=8888, name="myqick"):
    """Connect to the QICK Pyro4 server and return ``(soc, soccfg)``.

    Prints the nameserver listing and sets the global Pyro4 serializer to pickle (protocol 4);
    see docs/hardware.md#rfsoc.
    """
    Pyro4.config.SERIALIZER = "pickle"
    Pyro4.config.PICKLE_PROTOCOL_VERSION = 4

    ns = Pyro4.locateNS(host=host, port=port)

    for k, v in ns.list().items():
        print(k, v)

    soc = Pyro4.Proxy(ns.lookup(name))
    soccfg = QickConfig(soc.get_cfg())
    return (soc, soccfg)


makeProxy = make_proxy
