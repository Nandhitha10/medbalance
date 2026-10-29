"""Simulation clock management with configurable day length, speed, and Redis event emission."""

import asyncio
from datetime import datetime, timedelta
import logging
import os
import time
from typing import Any, Dict, Optional
from uuid import uuid4

from medbal_common.bus import publish
from medbal_common.clock import KOLKATA_TZ

logger = logging.getLogger(__name__)

DEFAULT_SIM_START_DATE = "2026-11-01T08:00:00+05:30"
DEFAULT_SIM_DAY_SECONDS = 30.0


class SimulationClock:
    """Simulation clock that advances virtual time proportionally to wall-clock time."""

    def __init__(
        self,
        start_date_str: Optional[str] = None,
        sim_day_seconds: Optional[float] = None,
        speed: float = 1.0,
    ):
        raw_start = start_date_str or os.getenv("SIM_START_DATE", DEFAULT_SIM_START_DATE)
        try:
            self.sim_start_time = datetime.fromisoformat(raw_start)
            if self.sim_start_time.tzinfo is None:
                self.sim_start_time = self.sim_start_time.replace(tzinfo=KOLKATA_TZ)
        except Exception:
            self.sim_start_time = datetime(2026, 11, 1, 8, 0, tzinfo=KOLKATA_TZ)

        self.sim_day_seconds = float(
            sim_day_seconds
            or os.getenv("SIM_DAY_SECONDS", str(DEFAULT_SIM_DAY_SECONDS))
        )
        self.speed = float(speed)
        self.is_running = True

        self.current_sim_time = self.sim_start_time
        self.day_index = 0
        self.last_real_time = time.monotonic()
        self.elapsed_sim_seconds = 0.0
        self.accumulated_day_fraction = 0.0

        self._tick_task: Optional[asyncio.Task] = None
        self._on_tick_callbacks: list = []

    def update(self) -> bool:
        """Advance simulation time based on wall-clock progression since last update.
        
        Returns True if a new sim day has rolled over.
        """
        now_real = time.monotonic()
        dt_real = now_real - self.last_real_time
        self.last_real_time = now_real

        if not self.is_running or dt_real <= 0.0:
            return False

        # Virtual seconds per real second: (86400 sim seconds per sim day) / sim_day_seconds * speed
        sim_seconds_per_real_second = (86400.0 / self.sim_day_seconds) * self.speed
        dt_sim = dt_real * sim_seconds_per_real_second

        self.current_sim_time += timedelta(seconds=dt_sim)
        self.elapsed_sim_seconds += dt_sim

        # Check day index turnover
        self.accumulated_day_fraction += dt_real / (self.sim_day_seconds / self.speed)
        new_day = False
        if self.accumulated_day_fraction >= 1.0:
            days_advanced = int(self.accumulated_day_fraction)
            self.accumulated_day_fraction -= days_advanced
            self.day_index += days_advanced
            new_day = True

        return new_day

    def start(self) -> None:
        """Start or resume the clock."""
        self.last_real_time = time.monotonic()
        self.is_running = True

    def pause(self) -> None:
        """Pause the clock."""
        self.update()
        self.is_running = False

    def set_speed(self, speed: float) -> None:
        """Update clock speed multiplier."""
        self.update()
        self.speed = max(0.1, min(100.0, float(speed)))

    def advance_days(self, days: int = 1) -> None:
        """Manually advance clock by N days (useful for testing and deterministic skips)."""
        self.day_index += days
        self.current_sim_time += timedelta(days=days)
        self.elapsed_sim_seconds += days * 86400.0

    def reset(self, start_date_str: Optional[str] = None) -> None:
        """Reset clock back to initial state."""
        raw_start = start_date_str or os.getenv("SIM_START_DATE", DEFAULT_SIM_START_DATE)
        try:
            self.sim_start_time = datetime.fromisoformat(raw_start)
            if self.sim_start_time.tzinfo is None:
                self.sim_start_time = self.sim_start_time.replace(tzinfo=KOLKATA_TZ)
        except Exception:
            self.sim_start_time = datetime(2026, 11, 1, 8, 0, tzinfo=KOLKATA_TZ)

        self.current_sim_time = self.sim_start_time
        self.speed = 1.0
        self.day_index = 0
        self.elapsed_sim_seconds = 0.0
        self.accumulated_day_fraction = 0.0
        self.last_real_time = time.monotonic()
        self.is_running = True

    def get_state(self) -> Dict[str, Any]:
        """Return comprehensive clock state formatted for both prompt & OpenAPI specs."""
        self.update()
        today_date = self.current_sim_time.date()
        return {
            "date": today_date.isoformat(),
            "today": today_date.isoformat(),
            "now": self.current_sim_time.isoformat(),
            "running": self.is_running,
            "is_running": self.is_running,
            "speed": round(self.speed, 2),
            "day_index": self.day_index,
            "elapsed_seconds": int(self.elapsed_sim_seconds),
        }

    async def emit_clock_tick(self) -> None:
        """Publish clock.tick event to Redis Streams."""
        event_payload = {
            "event_id": f"evt-tick-{uuid4().hex[:8]}",
            "event_type": "clock.tick",
            "timestamp": self.current_sim_time.isoformat(),
            "data": {
                "day_index": self.day_index,
                "date": self.current_sim_time.date().isoformat(),
                "now": self.current_sim_time.isoformat(),
                "speed": self.speed,
            },
        }
        try:
            await asyncio.wait_for(publish("clock.tick", event_payload), timeout=0.5)
        except Exception as exc:
            logger.debug(f"Redis tick publication notice: {exc}")

        # Notify any local in-memory listeners
        for cb in self._on_tick_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(self.day_index, self.current_sim_time)
                else:
                    cb(self.day_index, self.current_sim_time)
            except Exception as e:
                logger.error(f"Error in on_tick callback: {e}")

    async def run_loop(self, poll_interval_sec: float = 0.5) -> None:
        """Background loop to advance simulation and trigger daily ticks."""
        while True:
            try:
                await asyncio.sleep(poll_interval_sec)
                new_day = self.update()
                if new_day:
                    await self.emit_clock_tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Clock background loop error: {e}")
                await asyncio.sleep(1.0)


# Global singleton instance
clock = SimulationClock()
