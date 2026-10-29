"""Shared Pydantic domain models for MedBalance-Q."""

from datetime import date, datetime
from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field


class Facility(BaseModel):
    id: str = Field(..., description="Unique facility identifier, e.g. SIM-HOSP-01")
    name: str
    facility_type: str = Field(..., description="Hospital, Warehouse, PHC, CHC")
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    cold_storage_available: bool = False
    min_reserve_days: int = 7


class Drug(BaseModel):
    code: str = Field(..., description="Standard drug code")
    name: str
    category: Literal["V", "E", "N"] = Field(
        ..., description="Vital (3), Essential (2), Non-essential (1)"
    )
    unit: str = Field("tablet", description="Base unit: tablet, vial, sachet")
    pack_size: int = 1
    storage_condition: Literal["ambient", "cold_chain"] = "ambient"
    min_residual_days: int = Field(
        30, description="Minimum remaining shelf life allowed for transfer"
    )


class Lot(BaseModel):
    id: Optional[int] = None
    facility_id: str
    drug_code: str
    batch_no: str
    expiry: date
    quantity: int = Field(..., ge=0, description="Integer base units")
    created_at: Optional[datetime] = None


class Route(BaseModel):
    id: str
    source_facility_id: str
    destination_facility_id: str
    distance_km: float
    transit_hours: float
    cold_chain_compliant: bool = False


class Vehicle(BaseModel):
    id: str
    name: str
    vehicle_type: str
    cold_chain_capable: bool = False
    current_temp_c: Optional[float] = None
    is_active: bool = True


class Position(BaseModel):
    facility_id: str
    drug_code: str
    stock_on_hand: int = Field(..., ge=0)
    effective_stock: int = Field(..., ge=0, description="FEFO units consumed before expiry")
    at_risk_stock: int = Field(..., ge=0, description="FEFO units expiring unconsumed")
    reserve: int = Field(..., ge=0, description="Protected buffer stock R")
    shortage: int = Field(..., ge=0, description="Unmet demand n")
    daily_consumption_rate: float = Field(..., ge=0.0)


class Candidate(BaseModel):
    id: str
    lot_batch_no: str
    drug_code: str
    source_facility_id: str
    destination_facility_id: str
    chunk_quantity: int = Field(..., gt=0)
    usable_quantity: int = Field(..., ge=0)
    is_feasible: bool = True
    feasibility_flags: Dict[str, bool] = Field(
        default_factory=lambda: {
            "F1": True,  # Identity
            "F2": True,  # Route
            "F3": True,  # Cold chain
            "F4": True,  # Usable & residual shelf life
            "F5": True,  # Reserve protected
            "F6": True,  # Not controlled
        }
    )
    reward: float = 0.0
    cost: float = 0.0


class TransferOrder(BaseModel):
    id: str = Field(
        ...,
        description="DTA voucher number, format DTA/BLR-U/YYYY/NNNNNN",
        pattern=r"^DTA/[A-Z0-9\-]+/\d{4}/\d{6}$",
    )
    source_facility_id: str
    destination_facility_id: str
    drug_code: str
    batch_no: str
    quantity: int = Field(..., gt=0)
    status: Literal["DRAFT", "APPROVED", "IN_TRANSIT", "DELIVERED", "CANCELLED"] = "DRAFT"
    temperature_controlled: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None


class CustodyEvent(BaseModel):
    id: Optional[int] = None
    order_id: str
    actor: str
    event_type: Literal["DISPATCH", "HANDOVER", "RECEIVE"]
    timestamp: datetime
    location: Optional[str] = None
    temperature_c: Optional[float] = None
    notes: Optional[str] = None


class PlanRun(BaseModel):
    id: str
    timestamp: datetime
    status: str = "COMPLETED"
    total_transfers: int = 0
    total_units: int = 0
    shortage_reduction: int = 0
    expected_expiry_avoidance: int = 0
    solver_tier: str = Field("greedy", description="platform | LocalProvider | dwave-neal | greedy")
    execution_time_sec: float = 0.0
