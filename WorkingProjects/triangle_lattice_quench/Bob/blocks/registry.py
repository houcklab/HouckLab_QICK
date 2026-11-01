"""Block registry: every block class registers itself here so the palette and the file
loader can find it by its TYPE string."""
from __future__ import annotations

_REGISTRY: dict = {}
_ORDER: list = []


def register(cls):
    _REGISTRY[cls.TYPE] = cls
    if cls.TYPE not in _ORDER:
        _ORDER.append(cls.TYPE)
    return cls


def _ensure_loaded():
    # importing the modules runs their @register decorators
    from . import flux, pulses, beamsplitter, measure  # noqa: F401


def block_class(type_name: str):
    _ensure_loaded()
    try:
        return _REGISTRY[type_name]
    except KeyError:
        raise KeyError(f"unknown block type {type_name!r}; known: {sorted(_REGISTRY)}") from None


def all_block_classes() -> list:
    _ensure_loaded()
    return [_REGISTRY[t] for t in _ORDER]


def block_from_dict(d: dict):
    return block_class(d["type"]).from_dict(d)


def make_block(type_name: str, **kwargs):
    return block_class(type_name)(**kwargs)
