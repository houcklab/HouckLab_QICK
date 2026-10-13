"""Pyro5 client for remote SignalCore SC5510A generators (run on the client PC).

Server setup, host and usage: docs/hardware.md#signalcore-sc5510a.
"""

import os

import Pyro5.api
from Pyro5 import errors

SERVER_HOST = os.environ.get("SC5510A_SERVER_HOST", "192.168.0.102")
NAME_SERVER_PORT = 9090
NAME_PREFIX = "SC5510A#"


def locate_nameserver(host=SERVER_HOST, port=NAME_SERVER_PORT):
    """Locate the Pyro name server on the server PC."""
    try:
        return Pyro5.api.locate_ns(host=host, port=port)
    except (errors.NamingError, errors.CommunicationError, OSError) as e:
        raise ConnectionError(
            f"Could not reach the Pyro name server at {host}:{port}. "
            f"Is the server PC running start_nameserver.py and reachable on the "
            f"network? Original error: {e}"
        ) from e


def list_instruments(host=SERVER_HOST, port=NAME_SERVER_PORT):
    """Return a sorted list of registered instrument names."""
    nameserver = locate_nameserver(host, port)
    return sorted(nameserver.list(prefix=NAME_PREFIX).keys())


def connect(name=None, host=SERVER_HOST, port=NAME_SERVER_PORT):
    """Return a Pyro proxy to a remote SC5510A.

    name: registered name ("SC5510A#10002D35"), bare device id ("10002D35"), or None for the first.
    """
    nameserver = locate_nameserver(host, port)
    registered = nameserver.list(prefix=NAME_PREFIX)
    if not registered:
        raise RuntimeError(
            "No SC5510A instruments are registered on the server. "
            "Is start_instrument_server.py running on the server PC?"
        )

    if name is None:
        name = sorted(registered)[0]
    elif name not in registered and f"{NAME_PREFIX}{name}" in registered:
        name = f"{NAME_PREFIX}{name}"

    if name not in registered:
        available = ", ".join(sorted(registered)) or "(none)"
        raise KeyError(f"No instrument named '{name}'. Available: {available}")

    return Pyro5.api.Proxy(registered[name])
