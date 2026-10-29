"""MQTT telemetry subscriber and excursion handler."""

import asyncio
from datetime import datetime
import json
import logging
import os
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import paho.mqtt.client as mqtt
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, Numeric, String

from medbal_common.bus import publish
from medbal_common.clock import KOLKATA_TZ, now as sim_now
from medbal_common.db import Base, session_scope
from medbal_common.http import create_client

from coldchain.state_machine import ColdChainManager, DeviceState

logger = logging.getLogger(__name__)

DEFAULT_MQTT_URL = os.getenv("MQTT_URL", "mqtt://localhost:1883")
DEFAULT_CORE_API_URL = os.getenv("CORE_API_URL", "http://localhost:8001")


class SensorReadingModel(Base):
    __tablename__ = "sensor_reading"
    __table_args__ = {"extend_existing": True}

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    vehicle_id = Column(String(64), nullable=True)
    facility_id = Column(String(64), nullable=True)
    device_id = Column(String(64), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    temperature_c = Column(Numeric(5, 2), nullable=False)
    humidity_pct = Column(Numeric(5, 2), nullable=True)
    battery_pct = Column(Integer, nullable=True)
    is_excursion = Column(Boolean, default=False)


class ColdChainSubscriber:
    """Consumes telemetry from MQTT, runs the state machine, records downsampled DB readings, and raises alerts."""

    def __init__(
        self,
        manager: Optional[ColdChainManager] = None,
        mqtt_url: Optional[str] = None,
        core_api_url: Optional[str] = None,
    ):
        self.manager = manager or ColdChainManager()
        self.mqtt_url = mqtt_url or DEFAULT_MQTT_URL
        self.core_api_url = core_api_url or DEFAULT_CORE_API_URL
        self._mqtt_client: Optional[mqtt.Client] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """Start background MQTT subscriber."""
        self._loop = loop or asyncio.get_event_loop()
        try:
            parsed = urlparse(self.mqtt_url)
            host = parsed.hostname or "localhost"
            port = parsed.port or 1883

            if hasattr(mqtt, "CallbackAPIVersion"):
                client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="coldchain-service")
            else:
                client = mqtt.Client(client_id="coldchain-service")

            client.on_connect = self._on_connect
            client.on_message = self._on_message

            client.connect_async(host, port, keepalive=60)
            client.loop_start()
            self._mqtt_client = client
            logger.info(f"Coldchain MQTT subscriber connected to {host}:{port}")
        except Exception as exc:
            logger.warning(f"Could not connect MQTT subscriber to {self.mqtt_url}: {exc}")

    def stop(self) -> None:
        """Stop MQTT client."""
        if self._mqtt_client is not None:
            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
            except Exception:
                pass
            self._mqtt_client = None

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Callback on MQTT connection: subscribe to district/coldchain/+/telemetry."""
        topic = "district/coldchain/+/telemetry"
        client.subscribe(topic, qos=0)
        logger.info(f"Subscribed to topic '{topic}'")

    def _on_message(self, client, userdata, message):
        """Callback on telemetry packet arrival."""
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self.handle_telemetry(payload), self._loop)
            else:
                asyncio.run(self.handle_telemetry(payload))
        except Exception as exc:
            logger.debug(f"Error handling MQTT message: {exc}")

    async def handle_telemetry(self, payload: Dict[str, Any]) -> None:
        """Process telemetry packet through state machine, trigger alerts, and downsample to DB."""
        device_id = payload.get("device_id") or "UNKNOWN"
        assigned_to = payload.get("assigned_to")

        dev = self.manager.get_or_create_device(device_id, assigned_to)
        alert = dev.process_reading(payload)

        # 1. If state transition occurred, handle alert and update core-api
        if alert is not None:
            await self._handle_alert_transition(dev, alert)

        # 2. Downsampled database persistence (1 per 60s per device)
        now_ts = time.monotonic()
        should_persist = (
            dev.last_persisted_time is None
            or (now_ts - dev.last_persisted_time) >= 60.0
            or alert is not None
        )
        if should_persist and dev.latest_temp_c is not None:
            dev.last_persisted_time = now_ts
            self._persist_sensor_reading(dev)

    async def _handle_alert_transition(self, dev, alert: Dict[str, Any]) -> None:
        """Publish coldchain.alert to Redis Streams and notify core-api."""
        alert_data = alert["data"]
        severity = alert_data["severity"]

        logger.warning(
            f"Coldchain state transition on {dev.device_id} ({dev.assigned_to}) -> {dev.state.value} (severity: {severity})"
        )

        # Publish to Redis Streams: stream 'coldchain.alert'
        try:
            await publish("coldchain.alert", alert_data)
            logger.info(f"Published coldchain.alert for {dev.device_id} to Redis")
        except Exception as exc:
            logger.debug(f"Could not publish coldchain.alert to Redis: {exc}")

        # If device is assigned to a vehicle, update vehicle & route status in core-api
        if dev.vehicle_id:
            cold_ok = (dev.state != DeviceState.EXCURSION)
            route_status = "safe" if cold_ok else "unsafe"
            reason = (
                f"Cold chain excursion: {alert_data['temperature_c']}°C on {dev.vehicle_id}"
                if not cold_ok
                else "Cold chain normalized"
            )

            await self._update_core_api_vehicle_status(
                vehicle_id=dev.vehicle_id,
                cold_ok=cold_ok,
                route_status=route_status,
                status_reason=reason,
                route_ids=dev.assigned_route_ids,
            )

    async def _update_core_api_vehicle_status(
        self,
        vehicle_id: str,
        cold_ok: bool,
        route_status: str,
        status_reason: str,
        route_ids: list,
    ) -> None:
        """Call core-api POST /vehicles/{id}/status to mark vehicle and routes."""
        url = f"{self.core_api_url}/vehicles/{vehicle_id}/status"
        payload = {
            "cold_ok": cold_ok,
            "route_status": route_status,
            "status_reason": status_reason,
            "route_ids": route_ids,
        }
        try:
            async with create_client(timeout=0.3, max_retries=0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    logger.info(f"core-api updated vehicle {vehicle_id} cold_ok={cold_ok}")
                else:
                    logger.debug(f"core-api returned {resp.status_code} for vehicle {vehicle_id}")
        except Exception as exc:
            logger.debug(f"Could not notify core-api of vehicle {vehicle_id} status: {exc}")

    def _persist_sensor_reading(self, dev) -> None:
        """Store downsampled reading row in PostgreSQL sensor_reading table."""
        try:
            with session_scope() as session:
                reading_row = SensorReadingModel(
                    vehicle_id=dev.vehicle_id,
                    facility_id=dev.facility_id,
                    device_id=dev.device_id,
                    timestamp=dev.last_ping or sim_now(),
                    temperature_c=dev.latest_temp_c,
                    humidity_pct=dev.latest_humidity,
                    battery_pct=dev.latest_battery,
                    is_excursion=(dev.state == DeviceState.EXCURSION),
                )
                session.add(reading_row)
        except Exception as exc:
            # Standalone tests or unseeded environments can continue safely
            logger.debug(f"DB sensor_reading persist note: {exc}")


coldchain_manager = ColdChainManager()
coldchain_subscriber = ColdChainSubscriber(manager=coldchain_manager)
