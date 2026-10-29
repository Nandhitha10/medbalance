"""Domain models for MedBalance optimizer planning pipeline."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional


@dataclass
class Chunk:
    """Discrete pack-rounded chunk of a lot's transferable quantity."""
    chunk_id: str
    lot_id: Optional[int]
    batch_no: str
    source_facility_id: str
    drug_code: str
    quantity: int
    expiry: date
    chunk_index: int


@dataclass
class Candidate:
    """Evaluated (chunk, destination) transfer candidate."""
    candidate_id: str
    chunk_id: str
    source_facility_id: str
    destination_facility_id: str
    drug_code: str
    batch_no: str
    quantity: int
    usable_quantity: int
    expiry: date
    route_id: Optional[str] = None
    distance_km: float = 0.0
    transit_hours: float = 0.0
    reward_inr: float = 0.0
    cost_inr: float = 0.0
    net_benefit_inr: float = 0.0
    feasible: bool = True
    failed_rules: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "chunk_id": self.chunk_id,
            "source_facility_id": self.source_facility_id,
            "destination_facility_id": self.destination_facility_id,
            "drug_code": self.drug_code,
            "batch_no": self.batch_no,
            "quantity": self.quantity,
            "usable_quantity": self.usable_quantity,
            "expiry": self.expiry.isoformat() if isinstance(self.expiry, date) else str(self.expiry),
            "route_id": self.route_id,
            "distance_km": self.distance_km,
            "transit_hours": self.transit_hours,
            "reward_inr": self.reward_inr,
            "cost_inr": self.cost_inr,
            "net_benefit_inr": self.net_benefit_inr,
            "feasible": self.feasible,
            "failed_rules": self.failed_rules,
        }


@dataclass
class TransferOrder:
    """Synthesized transfer order ready for persistence and execution."""
    order_id: str
    plan_id: str
    source_facility_id: str
    destination_facility_id: str
    drug_code: str
    batch_no: str
    expiry: date
    quantity: int
    unit_cost_inr: float
    total_cost_inr: float
    shortage_reduction: int
    expiry_avoided: int
    vehicle_id: Optional[str] = None
    route_id: Optional[str] = None
    status: str = "PROPOSED"
    usable_quantity: int = 0
    term_breakdown: Optional[Dict[str, Any]] = None
    candidate_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.order_id,
            "plan_id": self.plan_id,
            "source_facility_id": self.source_facility_id,
            "destination_facility_id": self.destination_facility_id,
            "drug_code": self.drug_code,
            "batch_no": self.batch_no,
            "expiry": self.expiry.isoformat() if isinstance(self.expiry, date) else str(self.expiry),
            "quantity": self.quantity,
            "usable_quantity": self.usable_quantity if self.usable_quantity > 0 else self.quantity,
            "unit_cost_inr": self.unit_cost_inr,
            "total_cost_inr": self.total_cost_inr,
            "shortage_reduction": self.shortage_reduction,
            "expected_expiry_avoidance": self.expiry_avoided,
            "vehicle_id": self.vehicle_id,
            "route_id": self.route_id,
            "status": self.status,
            "term_breakdown": self.term_breakdown or {},
            "candidate_id": self.candidate_id,
        }


@dataclass
class RegretEntry:
    """Record of an unchosen or infeasible alternative destination for explainability."""
    order_id: str
    alternate_destination_id: str
    delta_h: float = 0.0
    chosen_reward: float = 0.0
    alternate_reward: float = 0.0
    regret_delta: float = 0.0
    reason_code: str = "LOWER_USABLE"  # LOWER_USABLE, HIGHER_COST, LOWER_VEN, FAILED_RULE_Fx, WORSE_FILL
    reason_text: str = ""
    rejected_destination_id: str = ""
    regret_inr: float = 0.0
    reason: str = ""
    candidate_id: Optional[str] = None
    sample_rank: int = 0

    def __post_init__(self):
        if not self.rejected_destination_id:
            self.rejected_destination_id = self.alternate_destination_id
        if not self.regret_delta:
            self.regret_delta = self.delta_h
        if not self.reason:
            self.reason = self.reason_text
        if not self.reason_text:
            self.reason_text = self.reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "candidate_id": self.candidate_id,
            "alternate_destination_id": self.alternate_destination_id,
            "rejected_destination_id": self.rejected_destination_id or self.alternate_destination_id,
            "delta_h": round(self.delta_h, 4),
            "regret_delta": round(self.regret_delta, 4),
            "chosen_reward": round(self.chosen_reward, 4),
            "alternate_reward": round(self.alternate_reward, 4),
            "regret_inr": round(self.regret_inr, 2),
            "reason_code": self.reason_code,
            "reason_text": self.reason_text,
            "reason": self.reason or self.reason_text,
            "sample_rank": self.sample_rank,
        }

