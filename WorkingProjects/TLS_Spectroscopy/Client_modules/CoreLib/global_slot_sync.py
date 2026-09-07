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
        self.ntp = None
        self.first_start_epoch_s = None
        self.token = None
        self.bootstrap_path = None
        self.ready_path = None
        self.schedule_path = None
        self._last_ntp_monotonic = None
        if self.enabled:
            if self.role not in {"leader", "follower"}:
                raise ValueError("sync role must be leader or follower")
            if not self.session:
                raise ValueError("sync session is required")
            if self.directory is None:
                raise ValueError("sync directory is required")
            if self.slot_s <= 0.0 or self.lead_s < 0.0:
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
        )

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
            previous = float(self.ntp["offset_s"])
            self._refresh_ntp()
            current = float(self.ntp["offset_s"])
            print(f"  [sync] NTP offset refreshed {previous:+.6f}s -> {current:+.6f}s.")

    def prepare(self):
        if not self.enabled:
            return {}
        self.directory.mkdir(parents=True, exist_ok=True)
        self.bootstrap_path = self.directory / "qick_qua_3pt_production_sync.json"
        self._refresh_ntp(required=True)
        if self.role == "leader":
            self.token = f"{self.session}:{os.getpid()}:{time.time_ns()}"
            self.ready_path = unique_sync_path(self.directory / "qick_qua_3pt_production_ready.json", self.token)
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
            payload = _await_payload(self.schedule_path, self.session, "scheduled", self.token, self.timeout_s)
            first_start = float(payload["start_epoch_s"])
            if first_start <= self.corrected_clock():
                raise RuntimeError("received a synchronization deadline that has already passed")
        self.first_start_epoch_s = float(first_start)
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
        }

    def has_slot(self, run_index, wall_clock_s):
        if not self.enabled or wall_clock_s is None:
            return True
        return float(run_index) * self.slot_s < float(wall_clock_s) - 1e-9

    def wait_for_start(self, run_index, wall_clock_s=None):
        if not self.enabled:
            return {}
        if not self.has_slot(run_index, wall_clock_s):
            return None
        target = self.first_start_epoch_s + int(run_index) * self.slot_s
        now = self.corrected_clock()
        if now - target > self.late_tolerance_s:
            raise RuntimeError(f"missed synchronized scan start by {now - target:.3f} s")
        wait_until_epoch(target, self.corrected_clock)
        actual = self.corrected_clock()
        return {
            **self.metadata(),
            "sync_scheduled_start_epoch_s": float(target),
            "sync_scheduled_end_epoch_s": float(target + self.slot_s),
            "sync_actual_start_epoch_s": float(actual),
            "sync_start_lag_s": float(actual - target),
        }

    def wait_for_end(self, run_index):
        if not self.enabled:
            return {}
        self.refresh_ntp_if_due()
        target = self.first_start_epoch_s + (int(run_index) + 1) * self.slot_s
        now = self.corrected_clock()
        if now > target:
            raise RuntimeError(f"synchronized scan overran its slot by {now - target:.3f} s")
        idle = target - now
        wait_until_epoch(target, self.corrected_clock)
        actual = self.corrected_clock()
        return {
            "sync_scheduled_end_epoch_s": float(target),
            "sync_actual_end_epoch_s": float(actual),
            "sync_post_scan_idle_s": float(idle),
            "sync_slot_end_lag_s": float(actual - target),
        }
