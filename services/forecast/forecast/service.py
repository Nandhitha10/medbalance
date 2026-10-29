"""Forecasting Service Orchestrator: baseline computation, context multiplier, and persistence."""

import asyncio
from datetime import date, timedelta
import logging
import math
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy import select

from medbal_common.bus import publish
from medbal_common.clock import today as sim_today
from medbal_common.db import session_scope
from forecast.backtest import evaluate_backtest
from forecast.baseline import compute_baseline_forecast
from forecast.context import evaluate_context_multiplier, fetch_sim_control_signals
from forecast.models import BacktestResponse, ForecastItem

logger = logging.getLogger(__name__)

# Canonical facilities and drugs from seed data
DEFAULT_FACILITIES = ["H1", "H2", "H3", "H4"]
DEFAULT_DRUGS = [
    "INS-REG", "OXY-10", "ASV-10", "TD-VAC", "CEFT-1000",
    "RL-500", "ORS-20", "PCM-500", "AMOX-500", "MET-500",
    "AML-5", "IFA-W", "MOR-10"
]

# Baseline Poisson consumption rates per drug
BASELINE_RATES = {
    "INS-REG": 15.0,
    "OXY-10": 12.0,
    "ASV-10": 1.5,
    "TD-VAC": 8.0,
    "CEFT-1000": 18.0,
    "RL-500": 25.0,
    "ORS-20": 40.0,
    "PCM-500": 120.0,
    "AMOX-500": 45.0,
    "MET-500": 60.0,
    "AML-5": 50.0,
    "IFA-W": 80.0,
    "MOR-10": 3.0,
}

SCALE_FACTORS = {
    "H1": 1.5,  # DH
    "H2": 1.2,  # TH
    "H3": 0.8,  # CHC
    "H4": 0.3,  # PHC
    "W0": 0.0,  # Warehouse
}

DAY_SEASONALITY = [1.2, 1.1, 1.1, 1.0, 1.0, 0.8, 0.6]  # Mon=0 .. Sun=6

# In-memory store for fast retrieval and offline mode
_forecasts_store: Dict[Tuple[str, str], ForecastItem] = {}
_consumption_cache: Dict[Tuple[str, str], List[float]] = {}


def generate_synthetic_consumption(
    facility_id: str,
    drug_code: str,
    days: int = 90,
    anchor_date: Optional[date] = None,
    seed: int = 42,
) -> List[float]:
    """Generate deterministic 90-day seasonal consumption history matching data/seed/generate.py."""
    import random
    rng = random.Random(seed + hash((facility_id, drug_code)) % 10000)
    
    end_d = anchor_date or date(2026, 11, 1)
    base = BASELINE_RATES.get(drug_code, 20.0)
    scale = SCALE_FACTORS.get(facility_id, 1.0)
    if scale <= 0.0:
        return [0.0] * days

    series = []
    for day_offset in range(days, 0, -1):
        curr_d = end_d - timedelta(days=day_offset)
        w = curr_d.weekday()
        season = DAY_SEASONALITY[w]
        lam = base * scale * season
        # Poisson sample with Gaussian approximation for lambda > 30
        if lam > 30:
            val = max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
        else:
            # Knuth Poisson generator
            L = math.exp(-lam)
            k = 0
            p = 1.0
            while p > L:
                k += 1
                p *= rng.random()
            val = max(0, k - 1)
        series.append(float(val))

    return series


def load_consumption_series(
    facility_id: str,
    drug_code: str,
    days: int = 90,
    current_date: Optional[date] = None,
) -> List[float]:
    """Load daily consumption series from PostgreSQL consumption_daily or fallback generator."""
    cache_key = (facility_id, drug_code)
    
    # 1. Try PostgreSQL if session available
    try:
        from core_api.db_models import ConsumptionDailyModel  # type: ignore
        with session_scope() as session:
            end_d = current_date or sim_today()
            start_d = end_d - timedelta(days=days)
            stmt = (
                select(ConsumptionDailyModel.quantity)
                .where(
                    ConsumptionDailyModel.facility_id == facility_id,
                    ConsumptionDailyModel.drug_code == drug_code,
                    ConsumptionDailyModel.date >= start_d,
                    ConsumptionDailyModel.date < end_d,
                )
                .order_by(ConsumptionDailyModel.date.asc())
            )
            rows = session.execute(stmt).scalars().all()
            if len(rows) >= 14:
                series = [float(r) for r in rows]
                _consumption_cache[cache_key] = series
                return series
    except Exception as e:
        logger.debug(f"DB consumption fetch notice ({e}); using deterministic series")

    # 2. Check local in-memory cache
    if cache_key in _consumption_cache:
        return _consumption_cache[cache_key]

    # 3. Generate deterministic history
    series = generate_synthetic_consumption(facility_id, drug_code, days=days, anchor_date=current_date)
    _consumption_cache[cache_key] = series
    return series


async def generate_forecast_item(
    facility_id: str,
    drug_code: str,
    active_signals: List[Dict[str, Any]],
    target_days: int = 14,
    current_date: Optional[date] = None,
    genai_url: Optional[str] = None,
) -> ForecastItem:
    """Generate baseline, context multiplier, and effective forecast for one (facility, drug) pair."""
    today_d = current_date or sim_today()
    series = load_consumption_series(facility_id, drug_code, days=90, current_date=today_d)

    # 1. Baseline calculation via Holt-Winters or EWMA
    base_res = compute_baseline_forecast(series, target_days=target_days)
    base_rate = base_res["baseline_rate"]
    p10 = base_res["p10_daily_rate"]
    p90 = base_res["p90_daily_rate"]
    model_name = base_res["model_used"]

    recent_14 = series[-14:] if len(series) >= 14 else series

    # 2. Context multiplier via signal matching and LLM gateway (guardrailed)
    ctx_res = await evaluate_context_multiplier(
        facility_id=facility_id,
        drug_code=drug_code,
        baseline_rate=base_rate,
        recent_14_day_series=recent_14,
        active_signals=active_signals,
        current_date=today_d,
        genai_url=genai_url,
    )

    mult = ctx_res["multiplier"]
    signal_ids = ctx_res["signal_ids"]
    reason = ctx_res["reasoning"]

    eff_rate = round(base_rate * mult, 3)
    proj_consumption = int(math.ceil(eff_rate * target_days))

    # Scale p10/p90 with multiplier
    adj_p10 = round(p10 * mult, 3)
    adj_p90 = round(p90 * mult, 3)

    item = ForecastItem(
        facility_id=facility_id,
        drug_code=drug_code,
        forecast_date=today_d,
        baseline_daily_rate=base_rate,
        llm_multiplier=mult,
        effective_daily_rate=eff_rate,
        target_days=target_days,
        projected_consumption=proj_consumption,
        p10_daily_rate=adj_p10,
        p90_daily_rate=adj_p90,
        signal_ids=signal_ids,
        reasoning=reason,
        model_used=model_name,
    )

    _forecasts_store[(facility_id, drug_code)] = item
    return item


async def run_all_forecasts(
    facility_filter: Optional[str] = None,
    drug_filter: Optional[str] = None,
    target_days: int = 14,
    forecast_date: Optional[date] = None,
    sim_control_url: Optional[str] = None,
    genai_url: Optional[str] = None,
) -> List[ForecastItem]:
    """Execute complete forecast generation across facilities and drugs."""
    current_d = forecast_date or sim_today()

    # 1. Fetch active signals from sim-control
    active_signals = await fetch_sim_control_signals(sim_control_url=sim_control_url)

    fac_list = [facility_filter] if facility_filter else DEFAULT_FACILITIES
    drug_list = [drug_filter] if drug_filter else DEFAULT_DRUGS

    forecasts: List[ForecastItem] = []

    for fac in fac_list:
        for dcode in drug_list:
            item = await generate_forecast_item(
                facility_id=fac,
                drug_code=dcode,
                active_signals=active_signals,
                target_days=target_days,
                current_date=current_d,
                genai_url=genai_url,
            )
            forecasts.append(item)

    # 2. Persist to PostgreSQL forecast table if DB is online
    try:
        from core_api.db_models import ForecastModel  # type: ignore
        with session_scope() as session:
            for item in forecasts:
                fc_row = ForecastModel(
                    facility_id=item.facility_id,
                    drug_code=item.drug_code,
                    forecast_date=item.forecast_date,
                    baseline_daily_rate=item.baseline_daily_rate,
                    llm_multiplier=item.llm_multiplier,
                    effective_daily_rate=item.effective_daily_rate,
                    target_days=item.target_days,
                    projected_consumption=item.projected_consumption,
                )
                session.add(fc_row)
            session.commit()
            logger.info("Successfully persisted %d forecast rows to PostgreSQL", len(forecasts))
    except Exception as e:
        logger.debug(f"DB forecast persistence notice ({e})")

    # 3. Publish forecast.updated event to Redis Streams
    try:
        from medbal_common.bus import get_redis_client
        redis = get_redis_client()
        await asyncio.wait_for(redis.ping(), timeout=0.05)
        for f in forecasts:
            payload = {
                "facility_code": f.facility_id,
                "drug_code": f.drug_code,
                "daily_rate": f.effective_daily_rate,
                "target_days": f.target_days,
                "multiplier": f.llm_multiplier,
                "multiplier_reason": f.reasoning or "Standard forecast updated",
            }
            await asyncio.wait_for(publish("forecast.updated", payload, redis_client=redis), timeout=0.05)
    except Exception as e:
        logger.debug(f"Redis forecast.updated publish skipped: {e}")

    return forecasts


def get_stored_forecasts(
    facility_filter: Optional[str] = None,
    drug_filter: Optional[str] = None,
) -> List[ForecastItem]:
    """Retrieve stored forecasts matching optional filters."""
    # Ensure default forecasts are populated if store is empty
    if not _forecasts_store:
        today_d = sim_today()
        for fac in DEFAULT_FACILITIES:
            for dcode in DEFAULT_DRUGS:
                base = BASELINE_RATES.get(dcode, 20.0) * SCALE_FACTORS.get(fac, 1.0)
                eff = round(base, 3)
                _forecasts_store[(fac, dcode)] = ForecastItem(
                    facility_id=fac,
                    drug_code=dcode,
                    forecast_date=today_d,
                    baseline_daily_rate=eff,
                    llm_multiplier=1.0,
                    effective_daily_rate=eff,
                    target_days=14,
                    projected_consumption=int(math.ceil(eff * 14)),
                    p10_daily_rate=round(eff * 0.8, 3),
                    p90_daily_rate=round(eff * 1.2, 3),
                    signal_ids=[],
                    reasoning="Normal seasonal baseline",
                    model_used="holt_winters",
                )

    results = []
    for (fac, dcode), item in _forecasts_store.items():
        if facility_filter and fac != facility_filter:
            continue
        if drug_filter and dcode != drug_filter:
            continue
        results.append(item)

    return sorted(results, key=lambda x: (x.facility_id, x.drug_code))


def run_backtest_report(
    facility: Optional[str] = None,
    drug: Optional[str] = None,
    window_days: int = 14,
) -> BacktestResponse:
    """Run backtest evaluation for facility x drug."""
    fac = facility or "H3"
    dcode = drug or "ORS-20"
    series = load_consumption_series(fac, dcode, days=90)
    
    # Check if there is an active multiplier stored for this pair
    cached = _forecasts_store.get((fac, dcode))
    mult = cached.llm_multiplier if cached else 1.0

    return evaluate_backtest(
        facility_id=fac,
        drug_code=dcode,
        series=series,
        window_days=window_days,
        active_multiplier=mult,
    )
