"""Simulated temperature sensor network for vehicles and facility cold storage."""

import asyncio
from datetime import datetime
import json
import logging
import os
import random
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import paho.mqtt.client as mqtt

from medbal_common.bus import get_redis_client
from medbal_common.clock import KOLKATA_TZ, now as sim_now

logger = logging.getLogger(__name__)

DEFAULT_MQTT_URL = os.getenv("MQTT_URL", "mqtt://localhost:1883")


class SensorDevice:
    """Simulated telemetry unit on a vehicle or inside facility cold storage."""

    def __init__(
        self,
        device_id: str,
        assigned_to: str,
        device_type: str = "vehicle",  # "vehicle" or "facility"
        base_temp_c: float = 4.5,
        is_offline: bool = False,
    ):
        self.device_id = device_id
        self.assigned_to = assigned_to
        self.device_type = device_type
        self.base_temp_c = base_temp_c
        self.is_offline = is_offline
        self.door_open = False
        self.door_open_since: Optional[float] = None
        self.battery_percent = 95 if device_type == "vehicle" else 100

        # Fault state
        self.fault_active = False
        self.fault_start_time: Optional[float] = None
        self.target_fault_temp: float = 11.4
        self.drift_duration_seconds: float = 60.0

    def trigger_fault(self, target_temp: float = 11.4, drift_seconds: float = 60.0) -> None:
        """Trigger heating excursion fault drift."""
        self.fault_active = True
        self.fault_start_time = time.monotonic()
        self.target_fault_temp = target_temp
        self.drift_duration_seconds = drift_seconds

    def clear_fault(self) -> None:
        """Clear active fault, returning temperature to normal range."""
        self.fault_active = False
        self.fault_start_time = None

    def set_offline(self, offline: bool) -> None:
        """Toggle offline status."""
        self.is_offline = offline

    def set_door_open(self, open_state: bool) -> None:
        """Toggle door open/closed."""
        self.door_open = open_state
        if open_state:
            if self.door_open_since is None:
                self.door_open_since = time.monotonic()
        else:
            self.door_open_since = None

    def read_telemetry(self, current_dt: Optional[datetime] = None) -> Dict[str, Any]:
        """Generate reading according to device operating mode."""
        dt = current_dt or sim_now()
        iso_ts = dt.isoformat()

        if self.is_offline:
            return {
                "device_id": self.device_id,
                "assigned_to": self.assigned_to,
                "ts": iso_ts,
                "timestamp": iso_ts,
                "temp_c": None,
                "temperature_c": None,
                "door_open": False,
                "battery": 0,
                "battery_percent": 0,
                "status": "offline",
            }

        # Temperature calculation
        noise = random.gauss(0.0, 0.15)
        if self.fault_active and self.fault_start_time is not None:
            elapsed = time.monotonic() - self.fault_start_time
            progress = min(1.0, elapsed / max(0.001, self.drift_duration_seconds))
            # Smooth drift from base_temp_c to target_fault_temp
            calc_temp = self.base_temp_c + (self.target_fault_temp - self.base_temp_c) * progress
            final_temp = round(calc_temp + noise, 2)
            status_str = "EXCURSION" if final_temp > 8.0 else "WARNING"
        elif self.door_open and self.door_open_since is not None:
            elapsed_door = time.monotonic() - self.door_open_since
            # Temperature rises by ~0.05 C per second when door open
            calc_temp = self.base_temp_c + min(6.0, elapsed_door * 0.05)
            final_temp = round(calc_temp + noise, 2)
            status_str = "EXCURSION" if (final_temp > 8.0 or elapsed_door > 120) else "WARNING"
        else:
            # Normal operating range: 4.5 C +/- 1.0 with noise
            variation = random.uniform(-0.8, 0.8)
            final_temp = round(self.base_temp_c + variation + noise, 2)
            # Ensure within standard normal bounds 2.5 - 6.5
            final_temp = max(2.5, min(6.5, final_temp))
            status_str = "OK"

        return {
            "device_id": self.device_id,
            "assigned_to": self.assigned_to,
            "ts": iso_ts,
            "timestamp": iso_ts,
            "temp_c": final_temp,
            "temperature_c": final_temp,
            "humidity_percent": round(50.0 + random.uniform(-5.0, 5.0), 1),
            "door_open": self.door_open,
            "battery": self.battery_percent,
            "battery_percent": self.battery_percent,
            "status": status_str,
        }


class SensorSimulator:
    """Simulates fleet and facility temperature sensors, reading faults from Redis and publishing to MQTT."""

    def __init__(self, mqtt_url: Optional[str] = None):
        self.mqtt_url = mqtt_url or DEFAULT_MQTT_URL
        self.devices: Dict[str, SensorDevice] = {
            # Cold transport vans
            "DEV-CV-01": SensorDevice("DEV-CV-01", assigned_to="CV-01", device_type="vehicle", base_temp_c=4.5),
            "DEV-CV-02": SensorDevice("DEV-CV-02", assigned_to="CV-02", device_type="vehicle", base_temp_c=4.5),
            # Facility ILR units
            "DEV-ILR-H1": SensorDevice("DEV-ILR-H1", assigned_to="H1", device_type="facility", base_temp_c=3.8),
            "DEV-ILR-H2": SensorDevice("DEV-ILR-H2", assigned_to="H2", device_type="facility", base_temp_c=4.2),
            "DEV-ILR-H3": SensorDevice("DEV-ILR-H3", assigned_to="H3", device_type="facility", base_temp_c=4.0),
            "DEV-ILR-H4": SensorDevice("DEV-ILR-H4", assigned_to="H4", device_type="facility", base_temp_c=4.5, is_offline=True),
            "DEV-ILR-W0": SensorDevice("DEV-ILR-W0", assigned_to="W0", device_type="facility", base_temp_c=4.0),
        }
        self.is_running = False
        self._mqtt_client: Optional[mqtt.Client] = None

    def get_device_by_target(self, target: str) -> Optional[SensorDevice]:
        """Find device by assigned vehicle or facility (e.g. 'CV-02', 'H4')."""
        for d in self.devices.values():
            if d.assigned_to == target or d.device_id == target:
                return d
        return None

    def connect_mqtt(self) -> None:
        """Establish non-blocking MQTT client connection."""
        try:
            parsed = urlparse(self.mqtt_url)
            host = parsed.hostname or "localhost"
            port = parsed.port or 1883

            if hasattr(mqtt, "CallbackAPIVersion"):
                client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sensor-simulator")
            else:
                client = mqtt.Client(client_id="sensor-simulator")

            client.connect_async(host, port, keepalive=60)
            client.loop_start()
            self._mqtt_client = client
            logger.info(f"MQTT publisher connected to {host}:{port}")
        except Exception as exc:
            logger.warning(f"Could not connect MQTT client to {self.mqtt_url}: {exc}")

    def stop_mqtt(self) -> None:
        """Disconnect MQTT client."""
        if self._mqtt_client is not None:
            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
            except Exception:
                pass
            self._mqtt_client = None

    def publish_reading(self, payload: Dict[str, Any]) -> None:
        """Publish telemetry payload over MQTT topic district/coldchain/{device_id}/telemetry."""
        device_id = payload["device_id"]
        topic = f"district/coldchain/{device_id}/telemetry"
        msg_str = json.dumps(payload)

        if self._mqtt_client is not None:
            try:
                self._mqtt_client.publish(topic, msg_str, qos=0)
            except Exception as e:
                logger.debug(f"MQTT publish failed for {device_id}: {e}")

    async def poll_redis_faults(self) -> None:
        """Poll Redis key 'sensors:faults' and 'sensors:ilr_repaired' to apply scenario changes."""
        try:
            r_client = get_redis_client()
            raw_fault = await asyncio.wait_for(r_client.get("sensors:faults"), timeout=0.2)
            if raw_fault:
                fault_data = json.loads(raw_fault)
                v_id = fault_data.get("vehicle_id") or fault_data.get("device_id")
                dev = self.get_device_by_target(v_id)
                if dev and fault_data.get("fault") == "EXCURSION":
                    if not dev.fault_active:
                        target_temp = float(fault_data.get("temperature_c", 11.4))
                        dev.trigger_fault(target_temp=target_temp, drift_seconds=60.0)
                        logger.info(f"Activated fault drift on {dev.device_id} ({dev.assigned_to}) -> {target_temp}°C")

            # Check ILR repaired signal
            raw_repaired = await asyncio.wait_for(r_client.get("sensors:ilr_repaired"), timeout=0.2)
            if raw_repaired:
                h4_dev = self.devices.get("DEV-ILR-H4")
                if h4_dev and h4_dev.is_offline:
                    h4_dev.set_offline(False)
                    logger.info("ILR repaired at H4: online and reporting normal temperature")
        except Exception:
            pass

    async def step(self) -> List[Dict[str, Any]]:
        """Advance simulator step: check faults, generate readings, and publish."""
        await self.poll_redis_faults()
        readings = []
        now_dt = sim_now()

        for dev in self.devices.values():
            telemetry = dev.read_telemetry(now_dt)
            readings.append(telemetry)
            self.publish_reading(telemetry)

        return readings

    async def run_loop(self, interval_seconds: float = 5.0) -> None:
        """Continuously publish telemetry every interval_seconds (default 5 real seconds)."""
        self.is_running = True
        self.connect_mqtt()

        while self.is_running:
            try:
                await self.step()
            except Exception as err:
                logger.warning(f"Error in sensor simulation step: {err}")
            await asyncio.sleep(interval_seconds)


sensor_simulator = SensorSimulator()
