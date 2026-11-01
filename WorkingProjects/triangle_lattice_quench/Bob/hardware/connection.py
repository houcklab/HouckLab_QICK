"""RFSoC connection over Pyro4, from triangle_lattice_quench/socProxy.py.

Changed: host, port and server name come from the station (station.json -> nameserver),
and nothing connects at import.
"""
from __future__ import annotations


def make_proxy(host: str, port: int = 8888, name: str = "myqick", timeout_s: float = 5.0):
    """Return (soc, soccfg) for the QICK server registered as ``name`` on the nameserver."""
    import Pyro4
    from qick import QickConfig
    Pyro4.config.SERIALIZER = "pickle"
    Pyro4.config.PICKLE_PROTOCOL_VERSION = 4
    Pyro4.config.COMMTIMEOUT = timeout_s
    ns = Pyro4.locateNS(host=host, port=int(port))
    soc = Pyro4.Proxy(ns.lookup(name))
    soccfg = QickConfig(soc.get_cfg())
    return soc, soccfg


def connect_station(station, timeout_s: float = 5.0):
    """make_proxy with the station's nameserver settings (station.json -> "nameserver")."""
    ns = station.data.get("nameserver") or {}
    return make_proxy(ns.get("host", "192.168.1.103"), ns.get("port", 8888), ns.get("name", "myqick"), timeout_s)
