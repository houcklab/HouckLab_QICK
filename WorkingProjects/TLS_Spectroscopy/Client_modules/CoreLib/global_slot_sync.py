import json
import math
import os
import socket
import statistics
import struct
import time
from datetime import datetime
from pathlib import Path


def ntp_sample_metrics(t1, t2, t3, t4):
    offset = ((float(t2) - float(t1)) + (float(t3) - float(t4))) / 2.0
    delay = (float(t4) - float(t1)) - (float(t3) - float(t2))
    return offset, delay


def measure_ntp_offset(host="time.windows.com", samples=7, timeout_s=2.0):
    packet = b"\x1b" + 47 * b"\0"
    offsets = []
    delays = []
    for _ in range(int(samples)):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(float(timeout_s))
            t1 = time.time()
            sock.sendto(packet, (str(host), 123))
            data, _ = sock.recvfrom(512)
            t4 = time.time()
        if len(data) < 48:
            raise RuntimeError("NTP response was truncated")
        words = struct.unpack("!12I", data[:48])
        t2 = float(words[8]) - 2208988800.0 + float(words[9]) / 2**32
        t3 = float(words[10]) - 2208988800.0 + float(words[11]) / 2**32
        offset, delay = ntp_sample_metrics(t1, t2, t3, t4)
        offsets.append(offset)
        delays.append(delay)
        time.sleep(0.05)
    return {
        "host": str(host),
        "samples": int(len(offsets)),
        "offset_s": float(statistics.median(offsets)),
        "median_round_trip_s": float(statistics.median(delays)),
        "offset_span_s": float(max(offsets) - min(offsets)),
    }


def wait_until_epoch(target_epoch, clock=time.time, sleeper=time.sleep):
    while True:
        remaining = float(target_epoch) - float(clock())
        if remaining <= 0.0:
            return float(clock())
        sleeper(min(0.1, remaining))


def unique_sync_path(path, token):
    path = Path(path)
    run_id = str(token).rsplit(":", 1)[-1]
    return path.with_name(f"{path.stem}_{run_id}{path.suffix}")


def next_slot_boundary(epoch_s, slot_s, origin_s, guard_s=0.0):
    """Return the first slot boundary safely after ``epoch_s``."""
    candidate = float(epoch_s) + float(guard_s)
    steps = math.ceil(((candidate - float(origin_s)) / float(slot_s)) - 1e-12)
    return float(origin_s) + max(0, int(steps)) * float(slot_s)


def _write_payload(path, payload):
    path = Path(path)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)
    return payload


def _await_payload(path, session, state, token, timeout_s, minimum_epoch=None):
    deadline = time.monotonic() + float(timeout_s)
    while time.monotonic() < deadline:
        try:
            payload = json.loads(Path(path).read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            time.sleep(0.1)
            continue
        matches = (
            payload.get("session") == str(session)
            and payload.get("state") == str(state)
            and (token is None or payload.get("token") == str(token))
        )
        if minimum_epoch is not None:
            matches = matches and float(payload.get("leader_corrected_epoch_s", 0.0)) >= float(minimum_epoch)
        if matches:
            return payload
        time.sleep(0.1)
    raise TimeoutError(f"timed out waiting for synchronization state {state}")


def _await_completion(path, session, token, role, run_index, timeout_s):
    deadline = time.monotonic() + max(0.0, float(timeout_s))
    while True:
        try:
            payload = json.loads(Path(path).read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            payload = None
        if payload is not None and (
            payload.get("session") == str(session)
            and payload.get("state") == "complete"
            and payload.get("token") == str(token)
            and payload.get("role") == str(role)
            and int(payload.get("run_index", -1)) == int(run_index)
        ):
            return payload
        if time.monotonic() >= deadline:
            raise TimeoutError(f"timed out waiting for {role} completion of run {run_index + 1}")
        time.sleep(0.1)


class GlobalSlotSynchronizer:
    def __init__(
        self,
        enabled=False,
        role=None,
        session=None,
        directory=None,
        slot_s=120.0,
        lead_s=60.0,
        timeout_s=3600.0,
        ntp_host="time.windows.com",
        ntp_samples=7,
        ntp_refresh_s=1800.0,
        late_tolerance_s=0.5,
        peer_wait_s=180.0,
        boundary_guard_s=5.0,
    ):
        self.enabled = bool(enabled)
        self.role = None if role is None else str(role).strip().lower()
        self.session = None if session is None else str(session)
        self.directory = None if directory is None else Path(directory)
        self.slot_s = float(slot_s)
        self.lead_s = float(lead_s)
        self.timeout_s = float(timeout_s)
        self.ntp_host = str(ntp_host)
        self.ntp_samples = int(ntp_samples)
        self.ntp_refresh_s = float(ntp_refresh_s)
        self.late_tolerance_s = float(late_tolerance_s)
        self.peer_wait_s = float(peer_wait_s)
        self.boundary_guard_s = float(boundary_guard_s)
        self.ntp = None
        self.first_start_epoch_s = None
        self.next_start_epoch_s = None
        self.token = None
        self.bootstrap_path = None
        self.ready_path = None
        self.schedule_path = None
        self._last_ntp_monotonic = None
        self.sync_state = "disabled" if not self.enabled else "initializing"
        self.sync_warning = None
        self.peer_status = None
        if self.enabled:
            if self.role not in {"leader", "follower"}:
                raise ValueError("sync role must be leader or follower")
            if not self.session:
                raise ValueError("sync session is required")
            if self.directory is None:
                raise ValueError("sync directory is required")
            if (
                self.slot_s <= 0.0
                or self.lead_s < 0.0
                or self.peer_wait_s < 0.0
                or self.boundary_guard_s < 0.0
            ):
                raise ValueError("sync timing values are invalid")

    @classmethod
    def from_config(cls, config):
        return cls(
            enabled=config.get("sync_enabled", False),
            role=config.get("sync_role"),
            session=config.get("sync_session"),
            directory=config.get("sync_directory"),
            slot_s=config.get("sync_slot_s", 120.0),
            lead_s=config.get("sync_lead_s", 60.0),
            timeout_s=config.get("sync_timeout_s", 3600.0),
            ntp_host=config.get("sync_ntp_host", "time.windows.com"),
            ntp_samples=config.get("sync_ntp_samples", 7),
            ntp_refresh_s=config.get("sync_ntp_refresh_s", 1800.0),
            peer_wait_s=config.get("sync_peer_wait_s", 180.0),
            boundary_guard_s=config.get("sync_boundary_guard_s", 5.0),
        )

    def _mark_degraded(self, warning):
        was_degraded = self.sync_state == "degraded"
        self.sync_state = "degraded"
        self.sync_warning = str(warning)
        if not was_degraded:
            print(f"[sync] degraded ({self.sync_warning}); continuing on the wall-clock grid.")

    def _fallback_ntp(self, warning):
        self.ntp = {
            "host": self.ntp_host,
            "samples": 0,
            "offset_s": 0.0,
            "median_round_trip_s": float("nan"),
            "offset_span_s": float("nan"),
        }
        self._last_ntp_monotonic = time.monotonic()
        self._mark_degraded(warning)

    def corrected_clock(self):
        offset = 0.0 if self.ntp is None else float(self.ntp["offset_s"])
        return time.time() + offset

    def _refresh_ntp(self, required=False):
        try:
            measured = measure_ntp_offset(self.ntp_host, self.ntp_samples)
        except Exception as exc:
            if required or self.ntp is None:
                raise
            print(f"  [sync] NTP refresh failed ({type(exc).__name__}: {exc}); keeping prior offset.")
            return
        self.ntp = measured
        self._last_ntp_monotonic = time.monotonic()

    def refresh_ntp_if_due(self):
        if not self.enabled:
            return
        if self._last_ntp_monotonic is None or time.monotonic() - self._last_ntp_monotonic >= self.ntp_refresh_s:
            previous = 0.0 if self.ntp is None else float(self.ntp["offset_s"])
            self._refresh_ntp()
            current = float(self.ntp["offset_s"])
            print(f"  [sync] NTP offset refreshed {previous:+.6f}s -> {current:+.6f}s.")

    def prepare(self):
        if not self.enabled:
            return {}
        self.bootstrap_path = self.directory / "qick_qua_3pt_production_sync.json"
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._mark_degraded(f"shared directory unavailable: {exc}")
        try:
            self._refresh_ntp(required=True)
        except Exception as exc:
            self._fallback_ntp(f"NTP unavailable: {type(exc).__name__}: {exc}")
        payload = None
        try:
            if self.role == "leader":
                self.token = f"{self.session}:{os.getpid()}:{time.time_ns()}"
                self.ready_path = unique_sync_path(
                    self.directory / "qick_qua_3pt_production_ready.json", self.token
                )
                self.schedule_path = unique_sync_path(self.bootstrap_path, self.token)
                _write_payload(self.bootstrap_path, {
                    "session": self.session,
                    "state": "waiting",
                    "token": self.token,
                    "ready_path": str(self.ready_path),
                    "schedule_path": str(self.schedule_path),
                    "leader_corrected_epoch_s": float(self.corrected_clock()),
                })
                print(f"[sync] leader ready; waiting for follower session={self.session}")
                _await_payload(self.ready_path, self.session, "ready", self.token, self.timeout_s)
                first_start = math.ceil((self.corrected_clock() + self.lead_s) / 60.0) * 60.0
                payload = _write_payload(self.schedule_path, {
                    "session": self.session,
                    "state": "scheduled",
                    "token": self.token,
                    "start_epoch_s": float(first_start),
                    "start_local": datetime.fromtimestamp(first_start).astimezone().isoformat(),
                    "slot_s": self.slot_s,
                })
                _write_payload(self.bootstrap_path, {
                    "session": self.session,
                    "state": "scheduled",
                    "token": self.token,
                    "schedule_path": str(self.schedule_path),
                    "leader_corrected_epoch_s": float(self.corrected_clock()),
                })
            else:
                leader = _await_payload(
                    self.bootstrap_path,
                    self.session,
                    "waiting",
                    None,
                    self.timeout_s,
                    minimum_epoch=self.corrected_clock() - 600.0,
                )
                self.token = str(leader["token"])
                self.ready_path = Path(leader["ready_path"])
                self.schedule_path = Path(leader["schedule_path"])
                _write_payload(self.ready_path, {
                    "session": self.session,
                    "state": "ready",
                    "token": self.token,
                    "ready_corrected_epoch_s": float(self.corrected_clock()),
                })
                print(f"[sync] follower ready session={self.session}")
                payload = _await_payload(
                    self.schedule_path,
                    self.session,
                    "scheduled",
                    self.token,
                    self.timeout_s,
                )
                first_start = float(payload["start_epoch_s"])
                if first_start <= self.corrected_clock():
                    raise RuntimeError("received a synchronization deadline that has already passed")
            if self.sync_state != "degraded":
                self.sync_state = "coordinated"
                self.sync_warning = None
        except Exception as exc:
            if self.token is None:
                self.token = f"{self.session}:{self.role}:{os.getpid()}:{time.time_ns()}"
            if self.schedule_path is None:
                self.schedule_path = unique_sync_path(self.bootstrap_path, self.token)
            first_start = math.ceil((self.corrected_clock() + self.lead_s) / 60.0) * 60.0
            self._mark_degraded(f"startup peer coordination failed: {type(exc).__name__}: {exc}")
            payload = {
                "start_epoch_s": float(first_start),
                "start_local": datetime.fromtimestamp(first_start).astimezone().isoformat(),
            }
        self.first_start_epoch_s = float(first_start)
        self.next_start_epoch_s = float(first_start)
        print(f"[sync] synchronized start={payload['start_local']} slot={self.slot_s:g}s")
        print(f"[sync] NTP offset={self.ntp['offset_s']:+.6f}s span={self.ntp['offset_span_s']:.6f}s")
        return self.metadata()

    def metadata(self):
        if not self.enabled:
            return {}
        return {
            "sync_session": self.session,
            "sync_role": self.role,
            "sync_slot_s": self.slot_s,
            "sync_first_start_epoch_s": self.first_start_epoch_s,
            "sync_ntp_offset_s": float(self.ntp["offset_s"]),
            "sync_ntp_span_s": float(self.ntp["offset_span_s"]),
            "sync_schedule_path": str(self.schedule_path),
            "sync_state": self.sync_state,
            "sync_warning": self.sync_warning,
            "sync_peer_status": self.peer_status,
        }

    def completion_path(self, run_index, role=None):
        selected_role = self.role if role is None else str(role)
        run_id = str(self.token).rsplit(":", 1)[-1]
        return self.directory / (
            f"qick_qua_3pt_complete_{run_id}_{int(run_index):08d}_{selected_role}.json"
        )

    def has_slot(self, run_index, wall_clock_s):
        if not self.enabled or wall_clock_s is None:
            return True
        target = self.next_start_epoch_s
        if target is None:
            target = self.first_start_epoch_s + int(run_index) * self.slot_s
        return float(target) < float(self.first_start_epoch_s) + float(wall_clock_s) - 1e-9

    def wait_for_start(self, run_index, wall_clock_s=None):
        if not self.enabled:
            return {}
        if not self.has_slot(run_index, wall_clock_s):
            return None
        target = self.next_start_epoch_s
        if target is None:
            target = self.first_start_epoch_s + int(run_index) * self.slot_s
        now = self.corrected_clock()
        if now - target > self.late_tolerance_s:
            missed_by = now - target
            target = next_slot_boundary(
                now,
                self.slot_s,
                self.first_start_epoch_s,
                self.boundary_guard_s,
            )
            self.next_start_epoch_s = float(target)
            self._mark_degraded(
                f"missed run {run_index + 1} start by {missed_by:.3f} s; rolled forward"
            )
            if not self.has_slot(run_index, wall_clock_s):
                return None
        wait_until_epoch(target, self.corrected_clock)
        actual = self.corrected_clock()
        return {
            **self.metadata(),
            "sync_scheduled_start_epoch_s": float(target),
            "sync_scheduled_end_epoch_s": float(target + self.slot_s),
            "sync_actual_start_epoch_s": float(actual),
            "sync_start_lag_s": float(actual - target),
            "sync_pair_index": int(run_index),
        }

    def wait_for_end(self, run_index, status="success", error=None):
        if not self.enabled:
            return {}
        self.refresh_ntp_if_due()
        finish = float(self.corrected_clock())
        own_payload = {
            "session": self.session,
            "state": "complete",
            "token": self.token,
            "role": self.role,
            "run_index": int(run_index),
            "finish_epoch_s": finish,
            "status": str(status),
            "error": None if error is None else str(error)[:500],
        }
        try:
            _write_payload(self.completion_path(run_index), own_payload)
        except OSError as exc:
            self._mark_degraded(f"could not publish run completion: {exc}")
        peer_role = "follower" if self.role == "leader" else "leader"
        peer = None
        try:
            peer = _await_completion(
                self.completion_path(run_index, peer_role),
                self.session,
                self.token,
                peer_role,
                run_index,
                self.peer_wait_s,
            )
        except Exception as exc:
            self.peer_status = "unavailable"
            self._mark_degraded(str(exc))
        else:
            self.peer_status = str(peer.get("status", "unknown"))
            self.sync_state = "coordinated"
            self.sync_warning = None
            print(f"[sync] run {run_index + 1} paired; next start follows the slower completion.")
        basis = max(finish, float(self.corrected_clock()))
        if peer is not None:
            basis = max(basis, float(peer["finish_epoch_s"]))
        next_start = next_slot_boundary(
            basis,
            self.slot_s,
            self.first_start_epoch_s,
            self.boundary_guard_s,
        )
        self.next_start_epoch_s = float(next_start)
        nominal_end = (
            float(self.first_start_epoch_s) + (int(run_index) + 1) * self.slot_s
        )
        return {
            **self.metadata(),
            "sync_actual_end_epoch_s": finish,
            "sync_slot_overrun_s": max(0.0, finish - nominal_end),
            "sync_next_start_epoch_s": float(next_start),
            "sync_peer_finish_epoch_s": None if peer is None else float(peer["finish_epoch_s"]),
        }
