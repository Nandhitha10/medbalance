"""Cold chain per-device state machine and excursion detection."""

from collections import deque
from datetime import datetime
from enum import Enum
import logging
import time
from typing import Any, Deque, Dict, List, Optional
from uuid import uuid4

from medbal_common.clock import KOLKATA_TZ, now as sim_now

logger = logging.getLogger(__name__)

MIN_SAFE_TEMP_C = 2.0
MAX_SAFE_TEMP_C = 8.0
MAX_DOOR_OPEN_SECONDS = 120.0  # > 2 min door open -> EXCURSION

# Default route assignments for transport fleet and facilities
VEHICLE_ROUTE_MAP = {
    "CV-01": ["RTE-W0-H1", "RTE-H1-W0", "RTE-W0-H3", "RTE-H3-W0", "RTE-W0-H4", "RTE-H4-W0"],
    "CV-02": ["RTE-W0-H2", "RTE-H2-W0", "RTE-H1-H2", "RTE-H2-H1"],
    "H1": ["RTE-H1-H2", "RTE-H1-W0"],
    "H2": ["RTE-H2-H1", "RTE-H2-W0"],
    "H3": ["RTE-H3-H4", "RTE-H3-W0"],
    "H4": ["RTE-H4-H3", "RTE-H4-W0"],
    "W0": ["RTE-W0-H1", "RTE-W0-H2", "RTE-W0-H3", "RTE-W0-H4"],
}


class DeviceState(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    EXCURSION = "EXCURSION"
    RECOVERED = "RECOVERED"
    OFFLINE = "offline"


class DeviceStateMachine:
    """Manages state transitions, door open timers, excursion rules, and alert generation for a single device."""

    def __init__(
        self,
        device_id: str,
        assigned_to: str,
        device_type: str = "vehicle",  # "vehicle" or "facility"
    ):
        self.device_id = device_id
        self.assigned_to = assigned_to
        self.device_type = device_type
        self.state = DeviceState.OK
        self.consecutive_bad_count = 0
        self.consecutive_good_count = 0

        self.door_open = False
        self.door_open_since: Optional[float] = None
        self.warning_since: Optional[datetime] = None
        self.excursion_since: Optional[datetime] = None
        self.last_alert_state: Optional[DeviceState] = None

        self.latest_temp_c: Optional[float] = None
        self.latest_battery: int = 100
        self.latest_humidity: float = 55.0
        self.last_ping: Optional[datetime] = None
        self.last_persisted_time: Optional[float] = None

        self.telemetry_history: Deque[Dict[str, Any]] = deque(maxlen=200)

    @property
    def assigned_route_ids(self) -> List[str]:
        """Routes associated with this device's vehicle or facility."""
        return VEHICLE_ROUTE_MAP.get(self.assigned_to, [])

    @property
    def vehicle_id(self) -> Optional[str]:
        """Return vehicle ID if device is assigned to a vehicle."""
        if self.device_type == "vehicle" or self.assigned_to.startswith("CV-"):
            return self.assigned_to
        return None

    @property
    def facility_id(self) -> Optional[str]:
        """Return facility ID if device is assigned to a facility."""
        if self.device_type == "facility" or self.assigned_to.startswith("H") or self.assigned_to == "W0":
            return self.assigned_to
        return None

    def _create_alert(
        self, severity: str, timestamp: datetime, temp_c: Optional[float]
    ) -> Dict[str, Any]:
        """Format coldchain.alert Redis event."""
        duration_minutes = 0
        if self.excursion_since:
            duration_minutes = int((timestamp - self.excursion_since).total_seconds() / 60)
        elif self.warning_since:
            duration_minutes = int((timestamp - self.warning_since).total_seconds() / 60)

        alert_data = {
            "device_id": self.device_id,
            "device": self.device_id,
            "vehicle": self.vehicle_id,
            "vehicle_id": self.vehicle_id,
            "route_ids": self.assigned_route_ids,
            "severity": severity,
            "temperature_c": temp_c if temp_c is not None else 0.0,
            "temp_c": temp_c if temp_c is not None else 0.0,
            "min_allowed_c": MIN_SAFE_TEMP_C,
            "max_allowed_c": MAX_SAFE_TEMP_C,
            "duration_minutes": duration_minutes,
            "since": (self.excursion_since or self.warning_since or timestamp).isoformat(),
        }

        return {
            "event_id": f"evt-cc-{uuid4().hex[:8]}",
            "event_type": "coldchain.alert",
            "timestamp": timestamp.isoformat(),
            "data": alert_data,
        }

    def process_reading(self, reading: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process incoming telemetry reading, update state machine, and return alert if transition occurred."""
        raw_ts = reading.get("ts") or reading.get("timestamp")
        if isinstance(raw_ts, str):
            try:
                dt = datetime.fromisoformat(raw_ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=KOLKATA_TZ)
            except Exception:
                dt = sim_now()
        elif isinstance(raw_ts, datetime):
            dt = raw_ts
        else:
            dt = sim_now()

        self.last_ping = dt

        # Handle offline status
        status_val = reading.get("status")
        if status_val == "offline" or reading.get("temp_c") is None and reading.get("temperature_c") is None:
            self.state = DeviceState.OFFLINE
            self.latest_temp_c = None
            return None

        temp_c = float(reading.get("temp_c") if reading.get("temp_c") is not None else reading.get("temperature_c"))
        self.latest_temp_c = temp_c
        self.latest_battery = int(reading.get("battery", reading.get("battery_percent", 95)))
        self.latest_humidity = float(reading.get("humidity_percent", 55.0))

        # Record telemetry sparkline point
        self.telemetry_history.append({
            "device_id": self.device_id,
            "timestamp": dt.isoformat(),
            "temperature_c": temp_c,
            "humidity_percent": self.latest_humidity,
            "battery_percent": self.latest_battery,
        })

        # Door tracking
        door_open = bool(reading.get("door_open", False))
        self.door_open = door_open
        door_excursion = False
        if door_open:
            if self.door_open_since is None:
                self.door_open_since = time.monotonic()
            elif (time.monotonic() - self.door_open_since) > MAX_DOOR_OPEN_SECONDS:
                door_excursion = True
        else:
            self.door_open_since = None

        # Excursion conditions
        is_bad_reading = (temp_c < MIN_SAFE_TEMP_C or temp_c > MAX_SAFE_TEMP_C) or door_excursion

        alert_to_publish = None

        # --- State Machine Transitions ---
        if self.state in (DeviceState.OK, DeviceState.OFFLINE):
            if is_bad_reading:
                self.consecutive_bad_count = 1
                self.consecutive_good_count = 0
                self.warning_since = dt
                if door_excursion:
                    self.state = DeviceState.EXCURSION
                    self.excursion_since = dt
                    if self.last_alert_state != DeviceState.EXCURSION:
                        self.last_alert_state = DeviceState.EXCURSION
                        alert_to_publish = self._create_alert("CRITICAL", dt, temp_c)
                else:
                    self.state = DeviceState.WARNING
            else:
                self.state = DeviceState.OK
                self.consecutive_bad_count = 0
                self.consecutive_good_count += 1

        elif self.state == DeviceState.WARNING:
            if is_bad_reading:
                self.consecutive_bad_count += 1
                self.consecutive_good_count = 0
                if self.consecutive_bad_count >= 3 or door_excursion:
                    self.state = DeviceState.EXCURSION
                    self.excursion_since = dt
                    if self.last_alert_state != DeviceState.EXCURSION:
                        self.last_alert_state = DeviceState.EXCURSION
                        alert_to_publish = self._create_alert("CRITICAL", dt, temp_c)
            else:
                # 1 good reading resolves a warning before excursion threshold
                self.consecutive_bad_count = 0
                self.consecutive_good_count = 1
                self.state = DeviceState.OK
                self.warning_since = None

        elif self.state == DeviceState.EXCURSION:
            if is_bad_reading:
                self.consecutive_bad_count += 1
                self.consecutive_good_count = 0
                # Alert already published upon entering EXCURSION; do not republish on every tick
            else:
                self.consecutive_good_count += 1
                if self.consecutive_good_count >= 6:
                    self.state = DeviceState.RECOVERED
                    self.consecutive_bad_count = 0
                    self.excursion_since = None
                    self.warning_since = None
                    if self.last_alert_state != DeviceState.RECOVERED:
                        self.last_alert_state = DeviceState.RECOVERED
                        alert_to_publish = self._create_alert("NORMAL", dt, temp_c)

        elif self.state == DeviceState.RECOVERED:
            if is_bad_reading:
                self.consecutive_bad_count = 1
                self.consecutive_good_count = 0
                self.warning_since = dt
                self.state = DeviceState.WARNING
            else:
                self.consecutive_good_count += 1
                if self.consecutive_good_count >= 10:
                    self.state = DeviceState.OK
                    self.last_alert_state = None

        return alert_to_publish


class ColdChainManager:
    """Oversees all registered cold chain devices, status aggregation, and persistence."""

    def __init__(self):
        self.devices: Dict[str, DeviceStateMachine] = {
            "DEV-CV-01": DeviceStateMachine("DEV-CV-01", assigned_to="CV-01", device_type="vehicle"),
            "DEV-CV-02": DeviceStateMachine("DEV-CV-02", assigned_to="CV-02", device_type="vehicle"),
            "DEV-ILR-H1": DeviceStateMachine("DEV-ILR-H1", assigned_to="H1", device_type="facility"),
            "DEV-ILR-H2": DeviceStateMachine("DEV-ILR-H2", assigned_to="H2", device_type="facility"),
            "DEV-ILR-H3": DeviceStateMachine("DEV-ILR-H3", assigned_to="H3", device_type="facility"),
            "DEV-ILR-H4": DeviceStateMachine("DEV-ILR-H4", assigned_to="H4", device_type="facility"),
            "DEV-ILR-W0": DeviceStateMachine("DEV-ILR-W0", assigned_to="W0", device_type="facility"),
        }

    def get_or_create_device(self, device_id: str, assigned_to: Optional[str] = None) -> DeviceStateMachine:
        """Retrieve existing device state machine or initialize dynamic unit."""
        if device_id in self.devices:
            return self.devices[device_id]
        
        # Check if mapped by assigned_to
        for dev in self.devices.values():
            if dev.assigned_to == device_id or dev.assigned_to == assigned_to:
                return dev

        target = assigned_to or device_id
        dev_type = "vehicle" if (target.startswith("CV-") or "VEH" in device_id) else "facility"
        new_dev = DeviceStateMachine(device_id=device_id, assigned_to=target, device_type=dev_type)
        self.devices[device_id] = new_dev
        return new_dev

    def get_status_summary(self) -> Dict[str, Any]:
        """Aggregate network health status for GET /status."""
        monitored_vehicles = 0
        monitored_facilities = 0
        active_excursions = 0
        has_warnings = False

        devices_list = []
        for dev in self.devices.values():
            if dev.device_type == "vehicle":
                monitored_vehicles += 1
            else:
                monitored_facilities += 1

            if dev.state == DeviceState.EXCURSION:
                active_excursions += 1
            elif dev.state == DeviceState.WARNING:
                has_warnings = True

            devices_list.append({
                "device_id": dev.device_id,
                "assigned_to": dev.assigned_to,
                "latest_temp_c": dev.latest_temp_c if dev.latest_temp_c is not None else 4.0,
                "battery_percent": dev.latest_battery,
                "last_ping": dev.last_ping.isoformat() if dev.last_ping else sim_now().isoformat(),
                "status": dev.state.value,
            })

        if active_excursions > 0:
            system_status = "CRITICAL"
        elif has_warnings:
            system_status = "WARNING"
        else:
            system_status = "NORMAL"

        return {
            "monitored_vehicles_count": monitored_vehicles,
            "monitored_facilities_count": monitored_facilities,
            "active_excursions_count": active_excursions,
            "system_status": system_status,
            "devices": devices_list,
        }
