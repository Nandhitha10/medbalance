"""SQLAlchemy ORM models for core-api matching db/init/001_schema.sql."""

from datetime import date, datetime
from typing import Any, Dict, Optional
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from medbal_common.db import Base
from medbal_common.audit import AuditLog  # Exported/reused


class FacilityModel(Base):
    __tablename__ = "facility"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[str] = mapped_column(String(32), nullable=False)
    taluk: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(64), default="Bengaluru Urban")
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    adapter_type: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[Optional[str]] = mapped_column(String(32), default="en")
    cold_storage_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    cold_storage_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class DrugModel(Base):
    __tablename__ = "drug"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(1), nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)
    pack_size: Mapped[int] = mapped_column(Integer, default=1)
    cold_chain: Mapped[bool] = mapped_column(Boolean, default=False)
    min_temp_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_temp_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit_cost_inr: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    min_residual_days: Mapped[int] = mapped_column(Integer, default=30)
    is_controlled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class DrugAliasModel(Base):
    __tablename__ = "drug_alias"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    drug_code: Mapped[str] = mapped_column(String(64), ForeignKey("drug.code", ondelete="CASCADE"), nullable=False)
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[Optional[str]] = mapped_column(String(16), default="en")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class LotModel(Base):
    __tablename__ = "lot"
    __table_args__ = (
        UniqueConstraint("facility_id", "drug_code", "batch_no", name="uq_facility_drug_batch"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    facility_id: Mapped[str] = mapped_column(String(64), ForeignKey("facility.id", ondelete="CASCADE"), nullable=False)
    drug_code: Mapped[str] = mapped_column(String(64), ForeignKey("drug.code", ondelete="CASCADE"), nullable=False)
    batch_no: Mapped[str] = mapped_column(String(128), nullable=False)
    expiry: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class StockReportModel(Base):
    __tablename__ = "stock_report"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    facility_id: Mapped[str] = mapped_column(String(64), ForeignKey("facility.id", ondelete="CASCADE"), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="RECEIVED")
    raw_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    report_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSON, nullable=True)


class ExtractionItemModel(Base):
    __tablename__ = "extraction_item"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    report_id: Mapped[str] = mapped_column(String(64), ForeignKey("stock_report.id", ondelete="CASCADE"), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    drug_code: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("drug.code"), nullable=True)
    batch_no: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    expiry: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(4, 3), nullable=True)
    is_anomalous: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    anomaly_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    review_status: Mapped[Optional[str]] = mapped_column(String(32), default="PENDING")
    suggested_patch: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)


class ConsumptionDailyModel(Base):
    __tablename__ = "consumption_daily"
    __table_args__ = (
        UniqueConstraint("facility_id", "drug_code", "date", name="uq_consumption_facility_drug_date"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    facility_id: Mapped[str] = mapped_column(String(64), ForeignKey("facility.id", ondelete="CASCADE"), nullable=False)
    drug_code: Mapped[str] = mapped_column(String(64), ForeignKey("drug.code", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)


class ForecastModel(Base):
    __tablename__ = "forecast"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    facility_id: Mapped[str] = mapped_column(String(64), ForeignKey("facility.id", ondelete="CASCADE"), nullable=False)
    drug_code: Mapped[str] = mapped_column(String(64), ForeignKey("drug.code", ondelete="CASCADE"), nullable=False)
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    baseline_daily_rate: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    llm_multiplier: Mapped[float] = mapped_column(Numeric(6, 3), default=1.0)
    effective_daily_rate: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    target_days: Mapped[int] = mapped_column(Integer, default=14)
    projected_consumption: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class PolicyModel(Base):
    __tablename__ = "policy"
    __table_args__ = (
        UniqueConstraint("facility_id", "drug_code", name="uq_policy_facility_drug"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    facility_id: Mapped[str] = mapped_column(String(64), ForeignKey("facility.id", ondelete="CASCADE"), nullable=False)
    drug_code: Mapped[str] = mapped_column(String(64), ForeignKey("drug.code", ondelete="CASCADE"), nullable=False)
    min_reserve_days: Mapped[int] = mapped_column(Integer, default=7)
    target_days: Mapped[int] = mapped_column(Integer, default=21)
    max_stock_days: Mapped[int] = mapped_column(Integer, default=60)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=3)


class RouteModel(Base):
    __tablename__ = "route"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), ForeignKey("facility.id", ondelete="CASCADE"), nullable=False)
    destination_id: Mapped[str] = mapped_column(String(64), ForeignKey("facility.id", ondelete="CASCADE"), nullable=False)
    distance_km: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    transit_days: Mapped[int] = mapped_column(Integer, default=1)
    transit_hours: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    cost_inr: Mapped[float] = mapped_column(Numeric(10, 2), default=0.00)
    cold_capable: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=True)
    status_reason: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)


class VehicleModel(Base):
    __tablename__ = "vehicle"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    vehicle_type: Mapped[str] = mapped_column(String(64), nullable=False)
    cold_capable: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    cost_per_km_inr: Mapped[float] = mapped_column(Numeric(8, 2), default=15.00)


class SensorReadingModel(Base):
    __tablename__ = "sensor_reading"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    vehicle_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("vehicle.id"), nullable=True)
    facility_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("facility.id"), nullable=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    temperature_c: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    humidity_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    battery_pct: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_excursion: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)


class PlanRunModel(Base):
    __tablename__ = "plan_run"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="COMPLETED")
    mode: Mapped[str] = mapped_column(String(32), default="live")
    solver_tier: Mapped[str] = mapped_column(String(64), default="greedy")
    execution_time_sec: Mapped[float] = mapped_column(Numeric(8, 3), default=0.0)
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    total_units: Mapped[int] = mapped_column(Integer, default=0)
    shortage_reduction: Mapped[int] = mapped_column(Integer, default=0)
    expiry_avoided: Mapped[int] = mapped_column(Integer, default=0)
    total_savings_inr: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), default=0.00)
    solver_meta: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    summary: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)


class CandidateModel(Base):
    __tablename__ = "candidate"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_run_id: Mapped[str] = mapped_column(String(64), ForeignKey("plan_run.id", ondelete="CASCADE"), nullable=False)
    lot_batch_no: Mapped[str] = mapped_column(String(128), nullable=False)
    drug_code: Mapped[str] = mapped_column(String(64), ForeignKey("drug.code"), nullable=False)
    source_facility_id: Mapped[str] = mapped_column(String(64), ForeignKey("facility.id"), nullable=False)
    destination_facility_id: Mapped[str] = mapped_column(String(64), ForeignKey("facility.id"), nullable=False)
    chunk_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    usable_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    is_feasible: Mapped[bool] = mapped_column(Boolean, default=True)
    feasibility_flags: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    reward: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), default=0.0)
    cost: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), default=0.0)


class TransferOrderModel(Base):
    __tablename__ = "transfer_order"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # DTA/BLR-U/2026/000123
    plan_run_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("plan_run.id", ondelete="SET NULL"), nullable=True)
    source_facility_id: Mapped[str] = mapped_column(String(64), ForeignKey("facility.id"), nullable=False)
    destination_facility_id: Mapped[str] = mapped_column(String(64), ForeignKey("facility.id"), nullable=False)
    drug_code: Mapped[str] = mapped_column(String(64), ForeignKey("drug.code"), nullable=False)
    batch_no: Mapped[str] = mapped_column(String(128), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    usable_quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")  # DRAFT, APPROVED, IN_TRANSIT, DELIVERED, CANCELLED
    temperature_controlled: Mapped[bool] = mapped_column(Boolean, default=False)
    savings_inr: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), default=0.00)
    term_breakdown: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    qr_token: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    audit_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    narration: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    headline: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class RegretEntryModel(Base):
    __tablename__ = "regret_entry"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    plan_run_id: Mapped[str] = mapped_column(String(64), ForeignKey("plan_run.id", ondelete="CASCADE"), nullable=False)
    order_id: Mapped[str] = mapped_column(String(64), ForeignKey("transfer_order.id", ondelete="CASCADE"), nullable=False)
    alternate_destination_id: Mapped[str] = mapped_column(String(64), ForeignKey("facility.id"), nullable=False)
    chosen_reward: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    alternate_reward: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    regret_delta: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class CustodyEventModel(Base):
    __tablename__ = "custody_event"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    order_id: Mapped[str] = mapped_column(String(64), ForeignKey("transfer_order.id", ondelete="CASCADE"), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)  # DISPATCH, HANDOVER, RECEIVE
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    temperature_c: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    signature_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class CreditMemoModel(Base):
    __tablename__ = "credit_memo"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(64), ForeignKey("transfer_order.id", ondelete="CASCADE"), nullable=False)
    creditor_facility_id: Mapped[str] = mapped_column(String(64), ForeignKey("facility.id"), nullable=False)
    debtor_facility_id: Mapped[str] = mapped_column(String(64), ForeignKey("facility.id"), nullable=False)
    drug_code: Mapped[str] = mapped_column(String(64), ForeignKey("drug.code"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost_inr: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    total_credit_inr: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    authorized_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

