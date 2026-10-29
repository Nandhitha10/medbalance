"""Pydantic and Domain Models for Forecast Service."""

from datetime import date
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ForecastItem(BaseModel):
    """Forecast representation conforming to OpenAPI components.yaml#/components/schemas/Forecast."""
    facility_id: str = Field(..., description="Healthcare facility ID (H1..H4, W0)")
    drug_code: str = Field(..., description="Canonical drug code")
    forecast_date: date = Field(..., description="Forecast calculation date")
    baseline_daily_rate: float = Field(..., description="Holt-Winters or EWMA baseline daily consumption rate")
    llm_multiplier: float = Field(default=1.0, description="Clamped LLM context multiplier")
    effective_daily_rate: float = Field(..., description="Effective usage rate r = baseline * multiplier")
    target_days: int = Field(default=14, description="Forecast planning horizon days")
    projected_consumption: int = Field(..., description="Total projected consumption over target_days")
    p10_daily_rate: Optional[float] = Field(default=None, description="10th percentile daily rate estimate")
    p90_daily_rate: Optional[float] = Field(default=None, description="90th percentile daily rate estimate")
    signal_ids: List[str] = Field(default_factory=list, description="Cited active public health signal IDs")
    reasoning: Optional[str] = Field(default=None, description="Contextual reasoning from LLM or heuristic")
    model_used: str = Field(default="holt_winters", description="Model algorithm used (holt_winters, ewma)")


class ForecastRunRequest(BaseModel):
    facility: Optional[str] = Field(default=None, description="Optional facility filter")
    drug: Optional[str] = Field(default=None, description="Optional drug code filter")
    target_days: int = Field(default=14, description="Target forecast horizon days")
    forecast_date: Optional[date] = Field(default=None, description="Optional target forecast date")


class ForecastRunResponse(BaseModel):
    status: str = Field(default="completed")
    forecasts_generated: int = Field(default=0)
    forecasts: List[ForecastItem] = Field(default_factory=list)


class BacktestResponse(BaseModel):
    """Backtest performance evaluation report."""
    drug_code: str
    facility_id: str
    evaluation_window_days: int
    mape_percent: float
    rmse: float
    model_used: str
    baseline_mape_percent: float
    baseline_rmse: Optional[float] = None
    historical_points: Optional[int] = None
    comparison: Optional[List[Dict[str, Any]]] = None

