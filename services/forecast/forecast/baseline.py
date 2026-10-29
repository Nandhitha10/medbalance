"""Baseline Time-Series Consumption Forecasting.

Implements statsmodels Holt-Winters Exponential Smoothing with weekly seasonality (period=7)
for 90+ day historical consumption series, with robust fallback to EWMA for shorter or
degenerate series. Computes p10 and p90 prediction bounds from model residuals.
"""

import logging
from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

logger = logging.getLogger(__name__)


def fit_holt_winters(
    series: List[float],
    seasonal_periods: int = 7,
    target_days: int = 14,
) -> Dict[str, Any]:
    """Fit Holt-Winters Exponential Smoothing with additive weekly seasonality."""
    y = np.array(series, dtype=float)
    if len(y) < 14:
        raise ValueError(f"Series length ({len(y)}) too short for Holt-Winters weekly seasonality (minimum 14 required)")

    # Model fitting
    # Use additive trend and seasonal components
    model = ExponentialSmoothing(
        y,
        trend="add",
        seasonal="add",
        seasonal_periods=seasonal_periods,
        initialization_method="estimated",
    )
    fit = model.fit(optimized=True)
    forecast = fit.forecast(target_days)
    
    # Calculate daily usage rate as mean of forecasted horizon (non-negative)
    baseline_rate = max(0.01, float(np.mean(forecast)))
    
    # Residual analysis for prediction intervals
    residuals = fit.resid
    if len(residuals) > 0:
        res_std = float(np.std(residuals))
        # Use 1.28 std dev corresponding to 80% confidence interval (p10 to p90)
        p10 = max(0.0, round(baseline_rate - 1.28 * res_std, 3))
        p90 = max(p10, round(baseline_rate + 1.28 * res_std, 3))
    else:
        res_std = 0.0
        p10 = round(baseline_rate * 0.8, 3)
        p90 = round(baseline_rate * 1.2, 3)

    return {
        "baseline_rate": round(baseline_rate, 3),
        "p10_daily_rate": p10,
        "p90_daily_rate": p90,
        "model_used": "holt_winters",
        "residual_std": round(res_std, 3),
        "fitted_values": fit.fittedvalues.tolist(),
        "forecast_series": [round(float(val), 3) for val in forecast],
    }


def fit_ewma_fallback(
    series: List[float],
    span: int = 7,
    target_days: int = 14,
) -> Dict[str, Any]:
    """Fallback exponentially weighted moving average for short or non-seasonal series."""
    y = np.array(series, dtype=float)
    if len(y) == 0:
        return {
            "baseline_rate": 0.5,
            "p10_daily_rate": 0.25,
            "p90_daily_rate": 0.75,
            "model_used": "ewma_fallback",
            "residual_std": 0.1,
            "fitted_values": [],
            "forecast_series": [0.5] * target_days,
        }

    s = pd.Series(y)
    ewma_series = s.ewm(span=span, adjust=False).mean()
    baseline_rate = max(0.01, float(ewma_series.iloc[-1]))
    
    residuals = y - ewma_series.values
    res_std = float(np.std(residuals)) if len(residuals) > 1 else 0.1 * baseline_rate
    
    p10 = max(0.0, round(baseline_rate - 1.28 * res_std, 3))
    p90 = max(p10, round(baseline_rate + 1.28 * res_std, 3))

    return {
        "baseline_rate": round(baseline_rate, 3),
        "p10_daily_rate": p10,
        "p90_daily_rate": p90,
        "model_used": "ewma",
        "residual_std": round(res_std, 3),
        "fitted_values": ewma_series.values.tolist(),
        "forecast_series": [round(baseline_rate, 3)] * target_days,
    }


def compute_baseline_forecast(
    series: List[float],
    target_days: int = 14,
) -> Dict[str, Any]:
    """Compute baseline consumption forecast using Holt-Winters with EWMA fallback."""
    if len(series) >= 14:
        try:
            return fit_holt_winters(series, seasonal_periods=7, target_days=target_days)
        except Exception as e:
            logger.debug("Holt-Winters fitting failed (%s); falling back to EWMA", e)
            return fit_ewma_fallback(series, span=7, target_days=target_days)
    else:
        return fit_ewma_fallback(series, span=7, target_days=target_days)
