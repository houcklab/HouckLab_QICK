"""Qt-free adapter around build_config's stage resolvers.

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

# Re-exported from build_config so both consumers see the same resolution
# rules. build_config is import-safe (no soccfg / no hardware).
from WorkingProjects.triangle_lattice_quench.build_config import (
    _deref_base       as deref_base,
    _resolve_readout  as resolve_readout_entry,
    _resolve_drive    as resolve_drive_entry,
    _resolve_ramp     as resolve_ramp_entry,
    _resolve_dynamics as resolve_dynamics_entry,
)

NONE_LABEL = "(none)"
DRIVE_FALLBACK_LABEL = "(readout)"


def group_names(jd: dict, namespace: str) -> list[str]:
    ns = jd.get(namespace, {})
    if not isinstance(ns, dict):
        return []
    return [n for n, g in ns.items() if isinstance(g, dict)]


def resolve_readout_section(jd: dict, group: str,
                            entry: str) -> Optional[dict]:
    if not group or group == NONE_LABEL:
        return None
    rg = jd.get("readout_groups", {}).get(group)
    if rg is None:
        raise KeyError(f"Readout group {group!r} not in readout_groups.")
    base = jd.get("base_params", {})
    readout_ff = rg.get("Readout_FF")
    pulse_ff = rg.get("Pulse_FF")
    if readout_ff is None:
        raise KeyError(
            f"Readout group {group!r} is missing Readout_FF."
        )
    return {
        "Readout_FF": list(deref_base(readout_ff, base)),
        "Pulse_FF":   (None if pulse_ff is None
                       else list(deref_base(pulse_ff, base))),
    }


def resolve_drive_section(jd: dict, group: str,
                          entry: str) -> Optional[dict]:
    """Decision tree mirrors FFFrequenciesTab._resolve_drive_section."""
    if not group or group in (NONE_LABEL, DRIVE_FALLBACK_LABEL):
        return None
    base = jd.get("base_params", {})
    g = jd.get("drive_groups", {}).get(group)
    # Drive combos in this tab can include readout group names too (parity
    # with build_config._resolve_drive's fallback search).
    if g is None:
        g = jd.get("readout_groups", {}).get(group)
    if not isinstance(g, dict):
        raise KeyError(f"Drive group {group!r} not in drive_groups or readout_groups.")
    if g.get("Pulse_FF") is not None:
        return {"Pulse_FF": list(deref_base(g.get("Pulse_FF"), base))}
    if not entry or entry == NONE_LABEL:
        return None
    return {"Pulse_FF": resolve_drive_entry(jd, entry)["Pulse_FF"]}


def resolve_ramp_section(jd: dict, group: str,
                         entry: str) -> Optional[dict]:
    if not group or group == NONE_LABEL:
        return None
    rg = jd.get("ramp_groups", {}).get(group)
    if rg is None:
        raise KeyError(f"Ramp group {group!r} not in ramp_groups.")
    base = jd.get("base_params", {})
    if entry and entry != NONE_LABEL:
        return resolve_ramp_entry(jd, entry)
    expt_base = rg.get("Expt_FF")
    if expt_base is None:
        raise KeyError(
            f"Ramp group {group!r} is missing Expt_FF."
        )
    return {"Init_FF": None,
            "Expt_FF": list(deref_base(expt_base, base))}


def resolve_dynamics_section(jd: dict, group: str,
                             entry: str) -> Optional[dict]:
    if not group or group == NONE_LABEL:
        return None
    if not entry or entry == NONE_LABEL:
        return None
    return resolve_dynamics_entry(jd, entry)


# kind -> (namespace tuple for groups, has-fallback-sentinel?)
STAGE_KIND_NAMESPACES = {
    "readout":  (("readout_groups",),                  False),
    "drive":    (("drive_groups", "readout_groups"),   True),
    "ramp":     (("ramp_groups",),                     False),
    "dynamics": (("dynamics_groups",),                 False),
}


def entries_for_group(jd: dict, kind: str, group: str) -> list[str]:
    """Return entries under jd[ns][group] for the first ns that has them.

    Mirrors FFFrequenciesTab._refresh_entry_combo's namespace-walk logic.
    """
    if not group or group in (NONE_LABEL, DRIVE_FALLBACK_LABEL):
        return []
    namespaces, _ = STAGE_KIND_NAMESPACES.get(kind, ((), False))
    for ns in namespaces:
        grp = jd.get(ns, {}).get(group)
        if isinstance(grp, dict):
            entries = grp.get("entries", {}) or {}
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

    For ramp: returns Expt_FF (the held value during the experiment).
    For dynamics: Dynamics_FF or BS_FF, whichever is present.
    For readout: Readout_FF.
    For drive: Pulse_FF.
    Returns None when the stage can't resolve a FF array.
    """
    if kind == "readout":
        sec = resolve_readout_section(jd, group, entry)
        return None if sec is None else sec.get("Readout_FF")
    if kind == "drive":
        sec = resolve_drive_section(jd, group, entry)
        return None if sec is None else sec.get("Pulse_FF")
    if kind == "ramp":
        sec = resolve_ramp_section(jd, group, entry)
        return None if sec is None else sec.get("Expt_FF")
    if kind == "dynamics":
        sec = resolve_dynamics_section(jd, group, entry)
        if sec is None:
            return None
        return sec.get("Dynamics_FF") or sec.get("BS_FF")
    return None
