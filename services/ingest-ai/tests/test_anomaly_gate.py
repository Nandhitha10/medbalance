"""Tests for anomaly detection gate across the 5 safety conditions."""

from datetime import date
import pytest

from ingest_ai.anomaly import AnomalyDetector


@pytest.fixture
def detector():
    return AnomalyDetector(session=None)


def test_anomaly_unknown_drug(detector):
    res = detector.evaluate_item(
        facility_id="H1",
        drug_code="UNKNOWN",
        batch_no="LOT-001",
        expiry=date(2026, 12, 1),
        quantity=50,
        confidence=0.90,
        report_date=date(2026, 11, 1),
        known_drug_codes={"INS-REG", "PCM-500"},
    )
    assert res.is_anomalous is True
    assert "UNKNOWN_DRUG" in res.triggered_rules
    assert res.anomaly_type == "UNKNOWN_DRUG"


def test_anomaly_past_expiry(detector):
    # Year 1999 when report date is 2026-11-01
    res = detector.evaluate_item(
        facility_id="H4",
        drug_code="INS-REG",
        batch_no="B-999",
        expiry=date(1999, 8, 14),
        quantity=50,
        confidence=0.95,
        report_date=date(2026, 11, 1),
        known_drug_codes={"INS-REG"},
    )
    assert res.is_anomalous is True
    assert "SUSPICIOUS_EXPIRY_PAST" in res.triggered_rules
    assert res.anomaly_type == "SUSPICIOUS_EXPIRY"


def test_anomaly_far_future_expiry(detector):
    # Year 2035 (> 5 years from 2026)
    res = detector.evaluate_item(
        facility_id="H4",
        drug_code="INS-REG",
        batch_no="B-123",
        expiry=date(2035, 1, 1),
        quantity=50,
        confidence=0.95,
        report_date=date(2026, 11, 1),
        known_drug_codes={"INS-REG"},
    )
    assert res.is_anomalous is True
    assert "SUSPICIOUS_EXPIRY_FUTURE" in res.triggered_rules


def test_anomaly_quantity_spike(detector):
    # 10,000 vials of insulin (typical on-hand is ~100) -> 100x spike!
    res = detector.evaluate_item(
        facility_id="H4",
        drug_code="INS-REG",
        batch_no="B-999",
        expiry=date(2026, 12, 1),
        quantity=10000,
        confidence=0.95,
        report_date=date(2026, 11, 1),
        known_drug_codes={"INS-REG"},
    )
    assert res.is_anomalous is True
    assert "QUANTITY_SPIKE" in res.triggered_rules
    assert res.anomaly_type == "QUANTITY_SPIKE"


def test_anomaly_low_confidence(detector):
    # Confidence 0.70 < threshold 0.85
    res = detector.evaluate_item(
        facility_id="H3",
        drug_code="PCM-500",
        batch_no="B-001",
        expiry=date(2026, 12, 1),
        quantity=50,
        confidence=0.70,
        report_date=date(2026, 11, 1),
        known_drug_codes={"PCM-500"},
    )
    assert res.is_anomalous is True
    assert "LOW_CONFIDENCE" in res.triggered_rules


def test_clean_item_not_anomalous(detector):
    res = detector.evaluate_item(
        facility_id="H1",
        drug_code="PCM-500",
        batch_no="LOT-PCM-H1-01",
        expiry=date(2027, 1, 30),
        quantity=500,
        confidence=0.95,
        report_date=date(2026, 11, 1),
        known_drug_codes={"PCM-500"},
    )
    assert res.is_anomalous is False
    assert len(res.triggered_rules) == 0
