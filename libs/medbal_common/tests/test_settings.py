"""Tests for settings parsing."""

from medbal_common.settings import Settings


def test_settings_defaults():
    s = Settings(
        DATABASE_URL="sqlite:///:memory:",
        REDIS_URL="redis://localhost:6379/1",
        MQTT_URL="mqtt://localhost:1883",
        DEMO_MODE="live",
        USE_FIXTURES=True,
    )
    assert s.DATABASE_URL == "sqlite:///:memory:"
    assert s.DEMO_MODE == "live"
    assert s.USE_FIXTURES is True
    assert s.LLM_MODEL_FAST is not None
    assert s.SIM_START_DATE.startswith("2026-")
