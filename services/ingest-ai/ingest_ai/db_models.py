"""SQLAlchemy ORM models for ingest-ai service."""

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


class FacilityModel(Base):
    __tablename__ = "facility"
    __table_args__ = {"extend_existing": True}

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
    __table_args__ = {"extend_existing": True}

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
    __table_args__ = {"extend_existing": True}

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
        {"extend_existing": True},
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
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    facility_id: Mapped[str] = mapped_column(String(64), ForeignKey("facility.id", ondelete="CASCADE"), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="RECEIVED")
    raw_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    report_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSON, default=dict)


class ExtractionItemModel(Base):
    __tablename__ = "extraction_item"
    __table_args__ = {"extend_existing": True}

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
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    facility_id: Mapped[str] = mapped_column(String(64), ForeignKey("facility.id", ondelete="CASCADE"), nullable=False)
    drug_code: Mapped[str] = mapped_column(String(64), ForeignKey("drug.code", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
