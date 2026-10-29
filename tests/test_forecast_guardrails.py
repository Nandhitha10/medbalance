"""Unit and Integration Tests for Forecasting: Holt-Winters, Guardrails, and Acceptance."""

from datetime import date
from unittest.mock import AsyncMock, patch
import numpy as np
import pytest

from forecast.baseline import compute_baseline_forecast, fit_ewma_fallback, fit_holt_winters
from forecast.context import apply_guardrails, evaluate_context_multiplier, find_relevant_signals
from forecast.service import generate_forecast_item, run_backtest_report
from medbal_common.fefo import calculate_fefo_position


def test_clamp_guardrail_upper_and_lower():
    """Verify context multipliers are strictly clamped to [0.5, 3.0]."""
    valid_ids = {"SIG-OUTBREAK-01"}

    # Upper clamp: 4.5 -> 3.0
    m_high, conf_high, sigs_high, _ = apply_guardrails(4.5, 0.9, ["SIG-OUTBREAK-01"], valid_ids)
    assert m_high == 3.0
    assert sigs_high == ["SIG-OUTBREAK-01"]

    # Lower clamp: 0.2 -> 0.5
    m_low, conf_low, sigs_low, _ = apply_guardrails(0.2, 0.9, ["SIG-OUTBREAK-01"], valid_ids)
    assert m_low == 0.5
    assert sigs_low == ["SIG-OUTBREAK-01"]

    # Within range: 1.75 preserved
    m_mid, _, sigs_mid, _ = apply_guardrails(1.75, 0.9, ["SIG-OUTBREAK-01"], valid_ids)
    assert m_mid == 1.75
    assert sigs_mid == ["SIG-OUTBREAK-01"]


def test_confidence_guardrail():
    """Verify confidence < 0.5 resets multiplier to 1.0."""
    valid_ids = {"SIG-OUTBREAK-01"}

    # Confidence 0.45 < 0.5 threshold -> reset to 1.0
    m, conf, sigs, note = apply_guardrails(2.5, 0.45, ["SIG-OUTBREAK-01"], valid_ids)
    assert m == 1.0
    assert sigs == []
    assert "confidence below 0.5" in note

    # Confidence 0.50 exactly -> accepted
    m_ok, _, sigs_ok, _ = apply_guardrails(2.5, 0.50, ["SIG-OUTBREAK-01"], valid_ids)
    assert m_ok == 2.5
    assert sigs_ok == ["SIG-OUTBREAK-01"]


def test_citation_guardrail():
    """Verify missing, empty, or ungrounded signal citations reset multiplier to 1.0."""
    valid_ids = {"SIG-OUTBREAK-01", "SIG-CAMPAIGN-02"}

    # Fake/hallucinated signal ID
    m_fake, _, sigs_fake, note_fake = apply_guardrails(2.5, 0.95, ["SIG-HALLUCINATED-99"], valid_ids)
    assert m_fake == 1.0
    assert sigs_fake == []
    assert "no valid active signal ID cited" in note_fake

    # Empty citation list
    m_empty, _, sigs_empty, note_empty = apply_guardrails(2.5, 0.95, [], valid_ids)
    assert m_empty == 1.0
    assert sigs_empty == []
    assert "no valid active signal ID cited" in note_empty


@pytest.mark.asyncio
async def test_no_signal_path_makes_zero_llm_calls():
    """Verify that when no signal affects facility x drug, ZERO LLM calls are made."""
    # Active signal ONLY affects H3 ORS-20
    active_signals = [
        {
            "id": "SIG-DENGUE-01",
            "type": "OUTBREAK",
            "facility": "H3",
            "drugs_affected": ["ORS-20", "PCM-500"],
            "multiplier": 4.0,
        }
    ]

    with patch("httpx.AsyncClient.post") as mock_post:
        # Evaluate H1 / INS-REG (completely unrelated facility & drug)
        res = await evaluate_context_multiplier(
            facility_id="H1",
            drug_code="INS-REG",
            baseline_rate=15.0,
            recent_14_day_series=[15.0] * 14,
            active_signals=active_signals,
            current_date=date(2026, 11, 1),
        )

        # Assert no HTTP calls to LLM gateway
        assert mock_post.call_count == 0
        assert res["llm_called"] is False
        assert res["multiplier"] == 1.0
        assert res["signal_ids"] == []
        assert "Normal seasonal baseline" in res["reasoning"]


def test_holt_winters_synthetic_seasonal_data():
    """Verify statsmodels Holt-Winters Exponential Smoothing on synthetic weekly seasonal series."""
    np.random.seed(42)
    t = np.arange(90)
    # 7-day weekly sinusoidal seasonality
    seasonality = 4.0 * np.sin(2 * np.pi * t / 7)
    trend = 0.02 * t
    noise = np.random.normal(0, 0.5, 90)
    series = np.maximum(1.0, 15.0 + seasonality + trend + noise).tolist()

    res = compute_baseline_forecast(series, target_days=14)

    assert res["model_used"] == "holt_winters"
    assert 13.0 <= res["baseline_rate"] <= 18.0
    # Prediction intervals: p10 <= baseline <= p90
    assert res["p10_daily_rate"] <= res["baseline_rate"]
    assert res["baseline_rate"] <= res["p90_daily_rate"]
    assert res["residual_std"] > 0.0
    assert len(res["forecast_series"]) == 14


def test_ewma_fallback_on_short_series():
    """Verify robust fallback to EWMA when history is too short for weekly seasonality."""
    short_series = [10.0, 12.0, 11.0, 13.0, 12.0]
    res = compute_baseline_forecast(short_series, target_days=14)

    assert res["model_used"] == "ewma"
    assert res["baseline_rate"] > 0
    assert res["p10_daily_rate"] <= res["baseline_rate"] <= res["p90_daily_rate"]


@pytest.mark.asyncio
async def test_dengue_outbreak_h3_ors_acceptance():
    """ACCEPTANCE TEST:
    After dengue_outbreak, H3 ORS forecast shows multiplier > 1 with the outbreak signal id and a reason;
    optimizer's FEFO target and position reflect the higher rate.
    """
    outbreak_signal = {
        "id": "SIG-DENGUE_OUTBREAK-01",
        "type": "OUTBREAK",
        "signal_type": "OUTBREAK",
        "facility": "H3",
        "facility_id": "H3",
        "drug_code": "ORS-20",
        "drugs_affected": ["ORS-20", "PCM-500"],
        "multiplier": 4.0,
        "multipliers": {"ORS-20": 4.0, "PCM-500": 2.5},
        "text": "IDSP Bulletin: Dengue and acute diarrheal disease cluster reported in Yelahanka taluk (H3)",
    }

    item = await generate_forecast_item(
        facility_id="H3",
        drug_code="ORS-20",
        active_signals=[outbreak_signal],
        target_days=14,
        current_date=date(2026, 11, 1),
    )

    # 1. Multiplier must be > 1.0 (clamped to 3.0 per guardrails)
    assert item.llm_multiplier > 1.0
    assert item.llm_multiplier <= 3.0
    assert item.effective_daily_rate > item.baseline_daily_rate

    # 2. Outbreak signal ID must be cited
    assert "SIG-DENGUE_OUTBREAK-01" in item.signal_ids

    # 3. Clinical reasoning must be provided citing the outbreak
    assert item.reasoning is not None
    assert ("Dengue" in item.reasoning or "OUTBREAK" in item.reasoning or "dengue" in item.reasoning.lower())

    # 4. Verify optimizer's FEFO position calculation reflects the higher rate
    # Normal baseline rate position
    lots = [
        {"facility_id": "H3", "drug_code": "ORS-20", "batch_no": "LOT-ORS-01", "quantity": 100, "expiry": "2026-12-01"}
    ]
    pos_normal = calculate_fefo_position(
        facility_id="H3",
        drug_code="ORS-20",
        lots=lots,
        daily_rate=item.baseline_daily_rate,
        today=date(2026, 11, 1),
        target_days=14,
    )

    # Outbreak rate position
    pos_outbreak = calculate_fefo_position(
        facility_id="H3",
        drug_code="ORS-20",
        lots=lots,
        daily_rate=item.effective_daily_rate,
        today=date(2026, 11, 1),
        target_days=14,
    )

    # Higher rate increases daily rate, reserve, and clinical shortage
    assert pos_outbreak.daily_consumption_rate > pos_normal.daily_consumption_rate
    assert pos_outbreak.shortage >= pos_normal.shortage
    assert pos_outbreak.reserve >= pos_normal.reserve


def test_backtest_report_evaluation():
    """Verify backtest endpoint returns MAPE and RMSE comparing baseline vs adjusted."""
    report = run_backtest_report(facility="H3", drug="ORS-20", window_days=14)

    assert report.facility_id == "H3"
    assert report.drug_code == "ORS-20"
    assert report.evaluation_window_days == 14
    assert report.mape_percent >= 0.0
    assert report.baseline_mape_percent >= 0.0
    assert report.rmse >= 0.0
    assert report.model_used in ("holt_winters", "holt_winters_weekly", "ewma")
