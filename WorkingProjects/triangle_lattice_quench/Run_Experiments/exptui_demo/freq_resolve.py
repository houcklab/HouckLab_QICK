"""Qt-free stage resolvers over qubit_parameters.json (drive_groups + flat ff_groups).

Used by both ExptUIDemoTab (for stage-y-position rendering) and codegen
tests. The four ``resolve_*_section`` helpers here mirror FFFrequenciesTab's
private ``_resolve_*_section`` methods exactly; ExptUI calls them with the
same ``(none)`` / ``(readout)`` sentinel semantics.

Heavy flux-model resolution (FF gain array -> MHz) is intentionally NOT in
this module — that path requires the Device_calibration import which is a
hardware-side dependency. The tab does the MHz computation lazily inside a
try/except; if the import fails the stage lines simply fall back to qubit-
index y-positions.
"""

from __future__ import annotations

from typing import Optional

# build_config is import-safe (no soccfg / no hardware).
from triangle_lattice_quench.build_config import QubitParams

NONE_LABEL = "(none)"
DRIVE_FALLBACK_LABEL = "(readout)"


def _groups(jd: dict, namespace: str) -> dict:
    """Groups of 'drive_groups' or of ff_groups/<namespace> (ramp_groups, dynamics_groups)."""
    if namespace == "drive_groups":
        return (jd or {}).get("drive_groups") or {}
    return ((jd or {}).get("ff_groups") or {}).get(namespace) or {}


def _entries(namespace: str, grp: dict) -> dict:
    """drive groups nest entries under 'entries'; ff groups hold them flat next to 'description'."""
    if namespace == "drive_groups":
        return (grp or {}).get("entries") or {}
    return {k: v for k, v in (grp or {}).items() if k != "description"}


def group_names(jd: dict, namespace: str) -> list[str]:
    """Group names; 'readout_groups' = drive_groups with a group-level FF_Readouts."""
    if namespace == "readout_groups":
        return [n for n, g in _groups(jd, "drive_groups").items() if isinstance(g, dict) and "FF_Readouts" in g]
    return [n for n, g in _groups(jd, namespace).items() if isinstance(g, dict)]


def resolve_readout_section(jd: dict, group: str,
                            entry: str) -> Optional[dict]:
    if not group or group == NONE_LABEL:
        return None
    rg = _groups(jd, "drive_groups").get(group)
    if rg is None:
        raise KeyError(f"Readout group {group!r} not in drive_groups.")
    readout_ff = rg.get("FF_Readouts")
    pulse_ff = rg.get("FF_Pulses")
    if readout_ff is None:
        raise KeyError(
            f"Readout group {group!r} is missing FF_Readouts."
        )
    return {
        "FF_Readouts": list(readout_ff),
        "FF_Pulses":   (None if pulse_ff is None
                       else list(pulse_ff)),
    }


def resolve_drive_section(jd: dict, group: str,
                          entry: str) -> Optional[dict]:
    """Decision tree mirrors FFFrequenciesTab._resolve_drive_section."""
    if not group or group in (NONE_LABEL, DRIVE_FALLBACK_LABEL):
        return None
    g = _groups(jd, "drive_groups").get(group)
    if not isinstance(g, dict):
        raise KeyError(f"Drive group {group!r} not in drive_groups.")
    if g.get("FF_Pulses") is not None:
        return {"FF_Pulses": list(g.get("FF_Pulses"))}
    if not entry or entry == NONE_LABEL:
        return None
    return {"FF_Pulses": QubitParams(jd).drive_ff("FF_Pulses", group, entry)}


def resolve_ramp_section(jd: dict, group: str,
                         entry: str) -> Optional[dict]:
    if not group or group == NONE_LABEL:
        return None
    rg = _groups(jd, "ramp_groups").get(group)
    if rg is None:
        raise KeyError(f"Ramp group {group!r} not in ramp_groups.")
    if entry and entry != NONE_LABEL:
        return {"Init_FF": None, "FF_Expt": QubitParams(jd).get_ff("ramp_groups", group, entry, "FF_Expt")}  # Init_FF no longer resolved
    expt_base = rg.get("FF_Expt")
    if expt_base is None:
        raise KeyError(
            f"Ramp group {group!r} is missing FF_Expt."
        )
    return {"Init_FF": None,
            "FF_Expt": list(expt_base)}


def resolve_dynamics_section(jd: dict, group: str,
                             entry: str) -> Optional[dict]:
    if not group or group == NONE_LABEL:
        return None
    if not entry or entry == NONE_LABEL:
        return None
    e = _entries("dynamics_groups", _groups(jd, "dynamics_groups").get(group)).get(entry)
    if e is None:
        raise KeyError(f"dynamics entry {entry!r} not in dynamics group {group!r}")
    return {k: list(e[k]) for k in ("FF_Dynamics", "FF_BS") if k in e}


# kind -> (namespace tuple for groups, has-fallback-sentinel?)
STAGE_KIND_NAMESPACES = {
    "readout":  (("readout_groups",),   False),
    "drive":    (("drive_groups",),     True),
    "ramp":     (("ramp_groups",),      False),
    "dynamics": (("dynamics_groups",),  False),
}


def entries_for_group(jd: dict, kind: str, group: str) -> list[str]:
    """Return the entry names of `group` in the stage's namespace.

    Mirrors FFFrequenciesTab._refresh_entry_combo's namespace-walk logic.
    """
    if not group or group in (NONE_LABEL, DRIVE_FALLBACK_LABEL):
        return []
    namespaces, _ = STAGE_KIND_NAMESPACES.get(kind, ((), False))
    for ns in namespaces:
        ns = "drive_groups" if ns == "readout_groups" else ns
        grp = _groups(jd, ns).get(group)
        if isinstance(grp, dict):
            entries = _entries(ns, grp)
            if entries:
                return list(entries.keys())
    return []


def groups_for_kind(jd: dict, kind: str) -> list[str]:
    """Return all group names that should appear in a stage's group combo."""
    namespaces, _ = STAGE_KIND_NAMESPACES.get(kind, ((), False))
    seen: set[str] = set()
    out: list[str] = []
    for ns in namespaces:
        for n in group_names(jd, ns):
            if n not in seen:
                out.append(n)
                seen.add(n)
    return out


def resolve_stage_ff(jd: dict, kind: str, group: str,
                     entry: str) -> Optional[list[int]]:
    """Return the single FF gain array (length 8) representing this stage's
    'rest frequency' — what to use for the qubit-line y-positions.

    For ramp: returns FF_Expt (the held value during the experiment).
    For dynamics: FF_Dynamics or FF_BS, whichever is present.
    For readout: FF_Readouts.
    For drive: FF_Pulses.
    Returns None when the stage can't resolve a FF array.
    """
    if kind == "readout":
        sec = resolve_readout_section(jd, group, entry)
        return None if sec is None else sec.get("FF_Readouts")
    if kind == "drive":
        sec = resolve_drive_section(jd, group, entry)
        return None if sec is None else sec.get("FF_Pulses")
    if kind == "ramp":
        sec = resolve_ramp_section(jd, group, entry)
        return None if sec is None else sec.get("FF_Expt")
    if kind == "dynamics":
        sec = resolve_dynamics_section(jd, group, entry)
        if sec is None:
            return None
        return sec.get("FF_Dynamics") or sec.get("FF_BS")
    return None
