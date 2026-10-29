"""Master data endpoints: facilities, drugs, routes, vehicles."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from medbal_common.audit import append
from medbal_common.db import session_scope
from src.db_models import (
    DrugModel,
    FacilityModel,
    PolicyModel,
    RouteModel,
    SensorReadingModel,
    VehicleModel,
)

router = APIRouter(tags=["Master Data"])


@router.get("/facilities", response_model=List[Dict[str, Any]])
def get_facilities() -> List[Dict[str, Any]]:
    """List all facilities from database."""
    with session_scope() as session:
        facilities = session.execute(
            select(FacilityModel).order_by(FacilityModel.id)
        ).scalars().all()

        # Query policies to extract facility min_reserve_days if present
        policies = session.execute(select(PolicyModel)).scalars().all()
        policy_map: Dict[str, int] = {}
        for p in policies:
            if p.facility_id not in policy_map:
                policy_map[p.facility_id] = p.min_reserve_days

        result = []
        for f in facilities:
            default_res = 14 if f.level == "WH" else (5 if f.level in ("CHC", "PHC") else 7)
            min_res = policy_map.get(f.id, default_res)
            fac_type = "Hospital" if f.level in ("DH", "TH") else ("Warehouse" if f.level == "WH" else f.level)
            result.append({
                "id": f.id,
                "name": f.name,
                "facility_type": fac_type,
                "latitude": float(f.latitude),
                "longitude": float(f.longitude),
                "cold_storage_available": bool(f.cold_storage_ok),
                "min_reserve_days": min_res,
            })
        return result


@router.get("/drugs", response_model=List[Dict[str, Any]])
def get_drugs() -> List[Dict[str, Any]]:
    """List drug formulary."""
    with session_scope() as session:
        drugs = session.execute(
            select(DrugModel).order_by(DrugModel.code)
        ).scalars().all()

        return [
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
            for d in drugs
        ]


@router.get("/routes", response_model=List[Dict[str, Any]])
def get_routes() -> List[Dict[str, Any]]:
    """List transit routes between facilities."""
    with session_scope() as session:
        routes = session.execute(
            select(RouteModel).order_by(RouteModel.id)
        ).scalars().all()

        return [
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
            for r in routes
        ]


class VehicleStatusUpdatePayload(BaseModel):
    cold_ok: bool
    route_status: Optional[str] = "unsafe"
    status_reason: Optional[str] = ""
    route_ids: Optional[List[str]] = None


@router.post("/vehicles/{id}/status", response_model=Dict[str, Any])
@router.post("/internal/coldchain/vehicle-status", response_model=Dict[str, Any])
def update_vehicle_status(
    id: Optional[str] = None, payload: Optional[VehicleStatusUpdatePayload] = None
) -> Dict[str, Any]:
    """Update vehicle cold capability and mark associated routes safe/unsafe."""
    # Handle id from either path parameter or payload
    target_id = id
    if payload is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload required")

    with session_scope() as session:
        vehicle = session.execute(
            select(VehicleModel).where(VehicleModel.id == target_id)
        ).scalar_one_or_none()

        if vehicle is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Vehicle '{target_id}' not found")

        vehicle.cold_capable = payload.cold_ok

        # Update routes
        routes_query = select(RouteModel)
        if payload.route_ids:
            routes_query = routes_query.where(RouteModel.id.in_(payload.route_ids))
        else:
            routes_query = routes_query.where(RouteModel.cold_capable == True)

        routes = session.execute(routes_query).scalars().all()
        for r in routes:
            r.status = payload.route_status
            r.status_reason = payload.status_reason
            if not payload.cold_ok:
                r.cold_capable = False
            else:
                r.cold_capable = True

        append(
            session=session,
            actor="coldchain-service",
            action="UPDATE_VEHICLE_STATUS",
            entity="vehicle",
            entity_id=target_id,
            payload={
                "cold_ok": payload.cold_ok,
                "route_status": payload.route_status,
                "status_reason": payload.status_reason,
                "updated_routes": [r.id for r in routes],
            },
        )

        return {
            "vehicle_id": target_id,
            "cold_ok": payload.cold_ok,
            "route_status": payload.route_status,
            "status_reason": payload.status_reason,
            "updated_routes_count": len(routes),
            "status": "updated",
        }


@router.get("/vehicles", response_model=List[Dict[str, Any]])
def get_vehicles() -> List[Dict[str, Any]]:
    """List vehicle fleet with cold chain capabilities and latest temperatures."""
    with session_scope() as session:
        vehicles = session.execute(
            select(VehicleModel).order_by(VehicleModel.id)
        ).scalars().all()

        result = []
        for v in vehicles:
            # Check latest sensor reading
            reading = session.execute(
                select(SensorReadingModel)
                .where(SensorReadingModel.vehicle_id == v.id)
                .order_by(SensorReadingModel.timestamp.desc())
                .limit(1)
            ).scalar_one_or_none()

            current_temp = (
                float(reading.temperature_c)
                if reading is not None and reading.temperature_c is not None
                else (4.0 if v.cold_capable else 24.5)
            )

            result.append({
                "id": v.id,
                "name": v.name,
                "vehicle_type": v.vehicle_type,
                "cold_chain_capable": bool(v.cold_capable),
                "current_temp_c": current_temp,
                "is_active": bool(v.is_active),
            })
        return result
