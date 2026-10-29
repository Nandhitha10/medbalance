"""Computed inventory positions read-model and complete optimizer snapshot."""

from datetime import date
import hashlib
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from sqlalchemy import select

from medbal_common.audit import canonical_json
from medbal_common.clock import now as sim_now, today as sim_today
from medbal_common.db import session_scope
from medbal_common.fefo import calculate_fefo_position
from src.db_models import (
    ConsumptionDailyModel,
    DrugModel,
    FacilityModel,
    ForecastModel,
    LotModel,
    PolicyModel,
    RouteModel,
    SensorReadingModel,
    VehicleModel,
)

router = APIRouter(tags=["Positions & Snapshot"])


def _compute_all_positions(
    session,
    facility_filter: Optional[str] = None,
    drug_filter: Optional[str] = None,
    current_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Compute FEFO positions for facility-drug pairs using latest forecast or 28-day history."""
    today = current_date or sim_today()

    # Determine unique pairs to evaluate
    fac_stmt = select(FacilityModel.id)
    if facility_filter:
        fac_stmt = fac_stmt.where(FacilityModel.id == facility_filter)
    facility_ids = session.execute(fac_stmt.order_by(FacilityModel.id)).scalars().all()

    drug_stmt = select(DrugModel.code)
    if drug_filter:
        drug_stmt = drug_stmt.where(DrugModel.code == drug_filter)
    drug_codes = session.execute(drug_stmt.order_by(DrugModel.code)).scalars().all()

    # Pre-fetch all policies
    policies_map: Dict[tuple[str, str], PolicyModel] = {}
    for pol in session.execute(select(PolicyModel)).scalars().all():
        policies_map[(pol.facility_id, pol.drug_code)] = pol

    # Pre-fetch latest forecasts
    forecasts_map: Dict[tuple[str, str], ForecastModel] = {}
    for fc in session.execute(
        select(ForecastModel).order_by(ForecastModel.forecast_date.desc(), ForecastModel.id.desc())
    ).scalars().all():
        key = (fc.facility_id, fc.drug_code)
        if key not in forecasts_map:
            forecasts_map[key] = fc

    # Pre-fetch active lots
    lot_stmt = select(LotModel).where(LotModel.quantity > 0)
    if facility_filter:
        lot_stmt = lot_stmt.where(LotModel.facility_id == facility_filter)
    if drug_filter:
        lot_stmt = lot_stmt.where(LotModel.drug_code == drug_filter)

    lots_by_pair: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
    for lt in session.execute(lot_stmt.order_by(LotModel.expiry.asc())).scalars().all():
        key = (lt.facility_id, lt.drug_code)
        if key not in lots_by_pair:
            lots_by_pair[key] = []
        lots_by_pair[key].append({
            "batch_no": lt.batch_no,
            "expiry": lt.expiry,
            "quantity": lt.quantity,
        })

    positions = []
    for fac_id in facility_ids:
        for drug_code in drug_codes:
            pair = (fac_id, drug_code)
            lots_list = lots_by_pair.get(pair, [])

            # Determine daily consumption rate:
            # 1. Latest forecast row
            fc = forecasts_map.get(pair)
            if fc is not None:
                rate = float(fc.effective_daily_rate)
                target_days = fc.target_days
            else:
                # 2. 28-day average consumption
                cons_rows = session.execute(
                    select(ConsumptionDailyModel.quantity)
                    .where(
                        ConsumptionDailyModel.facility_id == fac_id,
                        ConsumptionDailyModel.drug_code == drug_code,
                    )
                    .order_by(ConsumptionDailyModel.date.desc())
                    .limit(28)
                ).scalars().all()

                if cons_rows:
                    rate = float(sum(cons_rows)) / 28.0
                else:
                    rate = 0.0
                target_days = 21

            # Determine policy parameters
            policy = policies_map.get(pair)
            min_reserve_days = policy.min_reserve_days if policy else 7
            if policy:
                target_days = policy.target_days
            lead_time_days = policy.lead_time_days if policy else 3

            # Only compute position if there is stock or non-zero demand
            if not lots_list and rate <= 0.0:
                continue

            pos_res = calculate_fefo_position(
                facility_id=fac_id,
                drug_code=drug_code,
                lots=lots_list,
                daily_rate=rate,
                today=today,
                min_reserve_days=min_reserve_days,
                target_days=target_days,
                lead_time_days=lead_time_days,
            )

            positions.append({
                "facility_id": pos_res.facility_id,
                "drug_code": pos_res.drug_code,
                "stock_on_hand": pos_res.stock_on_hand,
                "effective_stock": pos_res.effective_stock,
                "at_risk_stock": pos_res.at_risk_stock,
                "reserve": pos_res.reserve,
                "shortage": pos_res.shortage,
                "daily_consumption_rate": round(pos_res.daily_consumption_rate, 3),
                "lots": [
                    {
                        "batch_no": lt.batch_no,
                        "expiry": lt.expiry.isoformat(),
                        "quantity": lt.quantity,
                        "days_to_expiry": lt.days_to_expiry,
                        "effective_quantity": lt.effective_quantity,
                        "at_risk_quantity": lt.at_risk_quantity,
                        "reserved_quantity": lt.reserved_quantity,
                        "transferable_quantity": lt.transferable_quantity,
                    }
                    for lt in pos_res.lots
                ],
            })

    return positions


@router.get("/positions", response_model=List[Dict[str, Any]])
def get_positions(
    facility: Optional[str] = Query(None, description="Filter by facility"),
    drug: Optional[str] = Query(None, description="Filter by drug code"),
) -> List[Dict[str, Any]]:
    """Query FEFO computed stock positions with per-lot detail."""
    with session_scope() as session:
        return _compute_all_positions(session, facility_filter=facility, drug_filter=drug)


@router.get("/snapshot", response_model=Dict[str, Any])
def get_snapshot() -> Dict[str, Any]:
    """Provide complete district snapshot with SHA-256 integrity hash for the optimizer."""
    current_time = sim_now()
    today = sim_today()

    with session_scope() as session:
        # 1. Facilities
        facilities_raw = session.execute(
            select(FacilityModel).order_by(FacilityModel.id)
        ).scalars().all()
        policies = session.execute(select(PolicyModel)).scalars().all()
        policy_res_map = {p.facility_id: p.min_reserve_days for p in policies}

        facilities = [
            {
                "id": f.id,
                "name": f.name,
                "facility_type": "Hospital" if f.level in ("DH", "TH") else ("Warehouse" if f.level == "WH" else f.level),
                "latitude": float(f.latitude),
                "longitude": float(f.longitude),
                "cold_storage_available": bool(f.cold_storage_ok),
                "min_reserve_days": policy_res_map.get(f.id, 14 if f.level == "WH" else 7),
            }
            for f in facilities_raw
        ]

        # 2. Drugs
        drugs_raw = session.execute(select(DrugModel).order_by(DrugModel.code)).scalars().all()
        drugs = [
            {
                "code": d.code,
                "name": d.name,
                "category": d.category,
                "unit": d.unit,
                "pack_size": d.pack_size,
                "storage_condition": "cold_chain" if d.cold_chain else "ambient",
                "min_residual_days": d.min_residual_days,
                "unit_cost_inr": float(d.unit_cost_inr),
            }
            for d in drugs_raw
        ]

        # 3. Routes
        routes_raw = session.execute(select(RouteModel).order_by(RouteModel.id)).scalars().all()
        routes = [
            {
                "id": r.id,
                "source_facility_id": r.source_id,
                "destination_facility_id": r.destination_id,
                "distance_km": float(r.distance_km),
                "transit_hours": float(r.transit_hours),
                "cold_chain_compliant": bool(r.cold_capable),
                "status": getattr(r, "status", "active") or "active",
                "status_reason": getattr(r, "status_reason", None),
            }
            for r in routes_raw
        ]

        # 4. Vehicles
        vehicles_raw = session.execute(select(VehicleModel).order_by(VehicleModel.id)).scalars().all()
        vehicles = []
        for v in vehicles_raw:
            reading = session.execute(
                select(SensorReadingModel)
                .where(SensorReadingModel.vehicle_id == v.id)
                .order_by(SensorReadingModel.timestamp.desc())
                .limit(1)
            ).scalar_one_or_none()
            temp = float(reading.temperature_c) if reading and reading.temperature_c else (4.0 if v.cold_capable else 24.5)
            vehicles.append({
                "id": v.id,
                "name": v.name,
                "vehicle_type": v.vehicle_type,
                "cold_chain_capable": bool(v.cold_capable),
                "current_temp_c": temp,
                "is_active": bool(v.is_active),
            })

        # 5. Lots
        lots_raw = session.execute(
            select(LotModel).where(LotModel.quantity > 0).order_by(LotModel.expiry.asc(), LotModel.batch_no.asc())
        ).scalars().all()
        lots = [
            {
                "id": lt.id,
                "facility_id": lt.facility_id,
                "drug_code": lt.drug_code,
                "batch_no": lt.batch_no,
                "expiry": lt.expiry.isoformat(),
                "quantity": lt.quantity,
                "created_at": lt.created_at.isoformat() if lt.created_at else None,
            }
            for lt in lots_raw
        ]

        # 6. Positions
        positions = _compute_all_positions(session, current_date=today)

        # 7. Forecasts
        forecasts_raw = session.execute(
            select(ForecastModel).order_by(ForecastModel.forecast_date.desc(), ForecastModel.id.desc())
        ).scalars().all()
        seen_fc = set()
        forecasts = []
        for fc in forecasts_raw:
            key = (fc.facility_id, fc.drug_code)
            if key not in seen_fc:
                seen_fc.add(key)
                forecasts.append({
                    "facility_id": fc.facility_id,
                    "drug_code": fc.drug_code,
                    "forecast_date": fc.forecast_date.isoformat(),
                    "baseline_daily_rate": float(fc.baseline_daily_rate),
                    "llm_multiplier": float(fc.llm_multiplier),
                    "effective_daily_rate": float(fc.effective_daily_rate),
                    "target_days": fc.target_days,
                    "projected_consumption": fc.projected_consumption,
                })

        # 8. Policies
        policies_list = [
            {
                "facility_id": p.facility_id,
                "drug_code": p.drug_code,
                "min_reserve_days": p.min_reserve_days,
                "target_days": p.target_days,
                "max_stock_days": p.max_stock_days,
                "lead_time_days": p.lead_time_days,
            }
            for p in policies
        ]

    snapshot_data: Dict[str, Any] = {
        "timestamp": current_time.isoformat(),
        "today": today.isoformat(),
        "facilities": facilities,
        "drugs": drugs,
        "routes": routes,
        "vehicles": vehicles,
        "lots": lots,
        "positions": positions,
        "forecasts": forecasts,
        "policies": policies_list,
    }

    # Compute deterministic snapshot_hash over canonical JSON
    canon = canonical_json(snapshot_data)
    snapshot_hash = hashlib.sha256(canon.encode("utf-8")).hexdigest()
    snapshot_data["snapshot_hash"] = snapshot_hash

    return snapshot_data
