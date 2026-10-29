"""FastAPI router for forecasting endpoints and backtesting."""

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query, status

from forecast.models import BacktestResponse, ForecastItem, ForecastRunRequest, ForecastRunResponse
from forecast.service import get_stored_forecasts, run_all_forecasts, run_backtest_report

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Consumption Forecasting"])


@router.post("/forecast/run", response_model=ForecastRunResponse)
@router.post("/run", response_model=ForecastRunResponse)
async def forecast_run(req: Optional[ForecastRunRequest] = None) -> ForecastRunResponse:
    """Run Holt-Winters baseline + signal-cited context multiplier forecasts."""
    fac = req.facility if req else None
    drug = req.drug if req else None
    target_days = req.target_days if req else 14
    fc_date = req.forecast_date if req else None

    items = await run_all_forecasts(
        facility_filter=fac,
        drug_filter=drug,
        target_days=target_days,
        forecast_date=fc_date,
    )

    return ForecastRunResponse(
        status="completed",
        forecasts_generated=len(items),
        forecasts=items,
    )


@router.get("/forecast", response_model=List[ForecastItem])
@router.get("", response_model=List[ForecastItem])
@router.get("/", response_model=List[ForecastItem])
async def get_forecast(
    facility: Optional[str] = Query(None, description="Optional facility ID filter"),
    drug: Optional[str] = Query(None, description="Optional drug code filter"),
) -> List[ForecastItem]:
    """Retrieve computed consumption forecasts."""
    return get_stored_forecasts(facility_filter=facility, drug_filter=drug)


@router.get("/forecast/backtest", response_model=BacktestResponse)
@router.get("/backtest", response_model=BacktestResponse)
async def get_backtest(
    facility: Optional[str] = Query(None, description="Facility ID to evaluate"),
    drug: Optional[str] = Query(None, description="Drug code to evaluate"),
    window_days: int = Query(14, description="Evaluation window days"),
) -> BacktestResponse:
    """Evaluate historical backtest accuracy comparing baseline vs adjusted predictions."""
    return run_backtest_report(facility=facility, drug=drug, window_days=window_days)

