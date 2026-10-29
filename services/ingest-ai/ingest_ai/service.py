"""Central Ingest-AI service orchestrating parsing, anomaly gating, reviews, and sync."""

from datetime import date
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from medbal_common import audit
from medbal_common.clock import now, today
from ingest_ai.adapters.chat import ChatAdapter
from ingest_ai.adapters.csv_adapter import CsvAdapter
from ingest_ai.adapters.fhir import FhirAdapter
from ingest_ai.adapters.text import TextAdapter
from ingest_ai.anomaly import AnomalyDetector
from ingest_ai.client import ServiceClients
from ingest_ai.date_utils import resolve_clinical_date
from ingest_ai.db_models import (
    DrugAliasModel,
    DrugModel,
    ExtractionItemModel,
    FacilityModel,
    LotModel,
    StockReportModel,
)
from ingest_ai.events import EventPublisher
from ingest_ai.grounding import GroundingEngine

logger = logging.getLogger("ingest-ai.service")


class IngestService:
    def __init__(
        self,
        session: Session,
        clients: Optional[ServiceClients] = None,
        publisher: Optional[EventPublisher] = None,
    ) -> None:
        self.session = session
        self.clients = clients or ServiceClients()
        self.publisher = publisher or EventPublisher()
        self.grounding = GroundingEngine.from_db(session)
        self.anomaly_detector = AnomalyDetector(session)

        # Adapters
        self.fhir_adapter = FhirAdapter(self.grounding)
        self.csv_adapter = CsvAdapter(self.grounding)
        self.chat_adapter = ChatAdapter(self.grounding, self.clients)
        self.text_adapter = TextAdapter(self.grounding, self.clients)

    async def ingest_report(
        self,
        facility_code: str,
        raw_content: str,
        source_type: str,
        file_name: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StockReportModel:
        """Ingest raw document, parse lots, run anomaly gate, and persist."""
        meta = metadata or {}
        report_date = today()
        today_slug = report_date.strftime("%Y%m%d")
        report_id = f"REP-{facility_code.upper()}-{today_slug}-{uuid.uuid4().hex[:6]}"

        # 1. Create StockReport entry
        stock_report = StockReportModel(
            id=report_id,
            facility_id=facility_code,
            received_at=now(),
            source_type=source_type.lower(),
            file_name=file_name or f"{facility_code}_{source_type}.txt",
            status="RECEIVED",
            raw_content=raw_content,
            report_metadata=meta,
        )
        self.session.add(stock_report)
        self.session.flush()

        # Publish report.received event
        await self.publisher.publish_report_received(
            report_id=report_id,
            facility_code=facility_code,
            source_type=source_type.lower(),
            file_name=file_name,
            file_size_bytes=len(raw_content.encode("utf-8")),
        )

        # 2. Select Adapter and Parse
        adapter = self._resolve_adapter(source_type, facility_code)
        extracted_lots = await adapter.parse(
            raw_content=raw_content,
            facility_code=facility_code,
            report_date=report_date,
            metadata=meta,
        )

        clean_lots_for_core_api: List[Dict[str, Any]] = []
        anomalies_count = 0
        known_codes = set(self.grounding.drug_meta.keys())

        # 3. Anomaly Evaluation & Item Persistence
        for lot in extracted_lots:
            # Check anomalies
            evaluation = self.anomaly_detector.evaluate_item(
                facility_id=facility_code,
                drug_code=lot.drug_code,
                batch_no=lot.batch_no,
                expiry=lot.expiry,
                quantity=lot.quantity,
                confidence=lot.confidence,
                report_date=report_date,
                known_drug_codes=known_codes,
            )

            suggested_patch = {
                "drug_code": lot.drug_code,
                "batch_no": lot.batch_no,
                "expiry": lot.expiry.isoformat() if lot.expiry else None,
                "quantity": lot.quantity,
            }

            if evaluation.is_anomalous:
                anomalies_count += 1
                # Generate explanation via GenAI gateway or template
                explanation, _ = await self.clients.call_genai_anomaly_explain(
                    facility=facility_code,
                    drug_code=lot.drug_code,
                    batch_no=lot.batch_no,
                    expiry=lot.expiry.isoformat() if lot.expiry else None,
                    qty=lot.quantity,
                    triggered_rules=evaluation.triggered_rules,
                    details=evaluation.details,
                )

                item_model = ExtractionItemModel(
                    report_id=report_id,
                    raw_text=lot.raw_text,
                    drug_code=lot.drug_code if lot.drug_code in known_codes else None,
                    batch_no=lot.batch_no,
                    expiry=lot.expiry,
                    quantity=lot.quantity,
                    confidence=lot.confidence,
                    is_anomalous=True,
                    anomaly_reason=explanation,
                    review_status="PENDING",
                    suggested_patch=suggested_patch,
                )
                self.session.add(item_model)
                self.session.flush()

                # Publish anomaly.flagged
                await self.publisher.publish_anomaly_flagged(
                    review_id=str(item_model.id),
                    facility_code=facility_code,
                    anomaly_type=evaluation.anomaly_type,
                    confidence=lot.confidence,
                    details=explanation,
                )
            else:
                # Clean item
                item_model = ExtractionItemModel(
                    report_id=report_id,
                    raw_text=lot.raw_text,
                    drug_code=lot.drug_code,
                    batch_no=lot.batch_no,
                    expiry=lot.expiry,
                    quantity=lot.quantity,
                    confidence=lot.confidence,
                    is_anomalous=False,
                    anomaly_reason=None,
                    review_status="CLEAN",
                    suggested_patch=suggested_patch,
                )
                self.session.add(item_model)
                self.session.flush()

                if lot.drug_code and lot.expiry and lot.quantity is not None:
                    clean_lots_for_core_api.append({
                        "facility_id": facility_code,
                        "drug_code": lot.drug_code,
                        "batch_no": lot.batch_no or f"BATCH-{uuid.uuid4().hex[:6]}",
                        "expiry": lot.expiry.isoformat(),
                        "quantity": lot.quantity,
                        "source_item_id": item_model.id,
                        "confidence": lot.confidence,
                    })

                    # Also directly update/upsert lot in local DB
                    self._upsert_local_lot(
                        facility_id=facility_code,
                        drug_code=lot.drug_code,
                        batch_no=lot.batch_no or f"BATCH-{uuid.uuid4().hex[:6]}",
                        expiry=lot.expiry,
                        quantity=lot.quantity,
                    )

        # 4. Push verified clean lots to core-api
        if clean_lots_for_core_api:
            await self.clients.upsert_lots_to_core_api(clean_lots_for_core_api)

        # 5. Update StockReport status
        stock_report.status = "NEEDS_REVIEW" if anomalies_count > 0 else "PROCESSED"
        meta["extracted_items_count"] = len(extracted_lots)
        meta["anomalies_detected"] = anomalies_count
        stock_report.report_metadata = meta

        audit.append(
            session=self.session,
            actor="ingest-ai",
            action="stock_report.ingested",
            entity="stock_report",
            entity_id=report_id,
            payload={
                "facility_code": facility_code,
                "source_type": source_type,
                "extracted_count": len(extracted_lots),
                "anomalies_count": anomalies_count,
            },
        )
        self.session.commit()
        return stock_report

    def _resolve_adapter(self, source_type: str, facility_code: str):
        src = source_type.lower()
        if src == "fhir":
            return self.fhir_adapter
        if src in ("csv", "excel"):
            return self.csv_adapter
        if src == "chat":
            return self.chat_adapter
        if src in ("text", "pdf"):
            return self.text_adapter

        # Facility code heuristics
        if facility_code == "H1":
            return self.fhir_adapter
        if facility_code == "H2":
            return self.csv_adapter
        if facility_code == "H3":
            return self.chat_adapter
        return self.text_adapter

    def _upsert_local_lot(
        self, facility_id: str, drug_code: str, batch_no: str, expiry: date, quantity: int
    ) -> None:
        """Directly upsert lot in local DB session."""
        try:
            existing = self.session.scalars(
                select(LotModel).where(
                    LotModel.facility_id == facility_id,
                    LotModel.drug_code == drug_code,
                    LotModel.batch_no == batch_no,
                )
            ).first()
            if existing:
                existing.quantity = quantity
                existing.expiry = expiry
                existing.updated_at = now()
            else:
                new_lot = LotModel(
                    facility_id=facility_id,
                    drug_code=drug_code,
                    batch_no=batch_no,
                    expiry=expiry,
                    quantity=quantity,
                    created_at=now(),
                    updated_at=now(),
                )
                self.session.add(new_lot)
        except Exception as e:
            logger.debug("Local lot upsert error: %s", e)

    def list_reports(self) -> List[Dict[str, Any]]:
        """List all ingested stock reports."""
        reports = self.session.scalars(
            select(StockReportModel).order_by(StockReportModel.received_at.desc())
        ).all()
        result = []
        for r in reports:
            meta = r.report_metadata or {}
            result.append({
                "id": r.id,
                "facility_code": r.facility_id,
                "received_at": r.received_at.isoformat() if r.received_at else None,
                "status": r.status,
                "source_type": r.source_type,
                "extracted_items_count": meta.get("extracted_items_count", 0),
                "anomalies_detected": meta.get("anomalies_detected", 0),
            })
        return result

    def list_reviews(self) -> List[Dict[str, Any]]:
        """List all pending anomaly review items."""
        query = (
            select(ExtractionItemModel, StockReportModel)
            .join(StockReportModel, ExtractionItemModel.report_id == StockReportModel.id)
            .where(
                ExtractionItemModel.is_anomalous == True,
                ExtractionItemModel.review_status.in_(["PENDING", "needs_review"]),
            )
            .order_by(ExtractionItemModel.id.desc())
        )
        rows = self.session.execute(query).all()
        results = []
        for item, report in rows:
            patch = item.suggested_patch or {
                "drug_code": item.drug_code,
                "batch_no": item.batch_no,
                "expiry": item.expiry.isoformat() if item.expiry else None,
                "quantity": item.quantity,
            }
            results.append({
                "id": str(item.id),
                "report_id": item.report_id,
                "facility_code": report.facility_id,
                "anomaly_type": self._classify_anomaly_type(item.anomaly_reason),
                "raw_text": item.raw_text,
                "suggested_patch": patch,
                "confidence": float(item.confidence or 0.85),
                "status": item.review_status or "PENDING",
                "anomaly_reason": item.anomaly_reason,
            })
        return results

    def _classify_anomaly_type(self, reason: Optional[str]) -> str:
        if not reason:
            return "SUSPICIOUS_EXPIRY"
        r = reason.upper()
        if "UNKNOWN" in r:
            return "UNKNOWN_DRUG"
        if "QUANTITY" in r or "SPIKE" in r:
            return "QUANTITY_SPIKE"
        if "CORRUPTED" in r or "OCR" in r or "CONFIDENCE" in r:
            return "CORRUPTED_TEXT"
        return "SUSPICIOUS_EXPIRY"

    async def resolve_review(
        self,
        review_id: str,
        action: str,
        override_data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """Pharmacist review resolution (ACCEPT, OVERRIDE/CORRECT, REJECT)."""
        try:
            item_id = int(review_id)
        except ValueError:
            return False, f"Invalid review ID: {review_id}"

        item = self.session.get(ExtractionItemModel, item_id)
        if not item:
            return False, f"Review item {review_id} not found"

        report = self.session.get(StockReportModel, item.report_id)
        facility_id = report.facility_id if report else "UNKNOWN"

        action_norm = action.strip().upper()

        if action_norm in ("ACCEPT", "APPROVED"):
            item.review_status = "RESOLVED"
            # Upsert lot
            if item.drug_code and item.expiry and item.quantity is not None:
                lot_payload = [{
                    "facility_id": facility_id,
                    "drug_code": item.drug_code,
                    "batch_no": item.batch_no or f"BATCH-{item_id}",
                    "expiry": item.expiry.isoformat(),
                    "quantity": item.quantity,
                }]
                await self.clients.upsert_lots_to_core_api(lot_payload)
                self._upsert_local_lot(
                    facility_id=facility_id,
                    drug_code=item.drug_code,
                    batch_no=item.batch_no or f"BATCH-{item_id}",
                    expiry=item.expiry,
                    quantity=item.quantity,
                )

        elif action_norm in ("OVERRIDE", "CORRECT"):
            patch = override_data or {}
            corrected_drug = patch.get("drug_code") or item.drug_code
            corrected_batch = patch.get("batch_no") or item.batch_no or f"BATCH-{item_id}"
            exp_val = patch.get("expiry")
            corrected_exp = resolve_clinical_date(str(exp_val)) if exp_val else item.expiry
            qty_val = patch.get("quantity")
            corrected_qty = int(qty_val) if qty_val is not None else item.quantity

            item.review_status = "RESOLVED"
            item.drug_code = corrected_drug
            item.batch_no = corrected_batch
            item.expiry = corrected_exp
            item.quantity = corrected_qty

            if corrected_drug and corrected_exp and corrected_qty is not None:
                lot_payload = [{
                    "facility_id": facility_id,
                    "drug_code": corrected_drug,
                    "batch_no": corrected_batch,
                    "expiry": corrected_exp.isoformat(),
                    "quantity": corrected_qty,
                }]
                await self.clients.upsert_lots_to_core_api(lot_payload)
                self._upsert_local_lot(
                    facility_id=facility_id,
                    drug_code=corrected_drug,
                    batch_no=corrected_batch,
                    expiry=corrected_exp,
                    quantity=corrected_qty,
                )

            # Insert new drug_alias so system learns local misspellings/dialects
            self._learn_alias_from_correction(corrected_drug, item.raw_text, item_id)

        elif action_norm in ("REJECT", "REJECTED"):
            item.review_status = "REJECTED"
        else:
            return False, f"Unknown action: {action}"

        audit.append(
            session=self.session,
            actor="pharmacist",
            action="review.resolved",
            entity="extraction_item",
            entity_id=str(item_id),
            payload={
                "action": action_norm,
                "review_id": review_id,
                "override_data": override_data,
            },
        )
        self.session.commit()
        return True, "resolved"

    def _learn_alias_from_correction(self, drug_code: Optional[str], raw_text: str, item_id: int) -> None:
        """Add learned alias to drug_alias and refresh grounding."""
        if not drug_code or not raw_text:
            return

        # Extract plausible raw mention (strip timestamps or trailing notes)
        clean_alias = raw_text.strip()
        clean_alias = re.split(r"[:\(\-]", clean_alias)[0].strip()
        if len(clean_alias) > 64:
            clean_alias = clean_alias[:64].strip()

        if len(clean_alias) < 2:
            return

        # Detect Kannada script
        is_kannada = bool(re.search(r"[\u0C80-\u0CFF]", clean_alias))
        lang = "kn" if is_kannada else "en"

        try:
            alias_model = DrugAliasModel(
                drug_code=drug_code,
                alias=clean_alias,
                language=lang,
                notes=f"Pharmacist learned alias from review {item_id}",
                created_at=now(),
            )
            self.session.add(alias_model)
            self.session.flush()

            # Refresh in-memory grounding
            self.grounding = GroundingEngine.from_db(self.session)
        except Exception as e:
            logger.debug("Failed to record learned alias: %s", e)

    async def poll_hospitals(self) -> Dict[str, Any]:
        """Poll H1 (FHIR) and H2 (CSV) simulated hospital endpoints."""
        reports_count = 0

        # Poll H1 (FHIR)
        h1_data, err1 = await self.clients.fetch_h1_fhir()
        if h1_data:
            await self.ingest_report(
                facility_code="H1",
                raw_content=json.dumps(h1_data),
                source_type="fhir",
                file_name="h1_fhir_inventory.json",
            )
            reports_count += 1
        else:
            logger.debug("H1 poll note: %s", err1)

        # Poll H2 (CSV)
        h2_csv, err2 = await self.clients.fetch_h2_csv()
        if h2_csv:
            await self.ingest_report(
                facility_code="H2",
                raw_content=h2_csv,
                source_type="csv",
                file_name="h2_stock_export.csv",
            )
            reports_count += 1
        else:
            logger.debug("H2 poll note: %s", err2)

        return {
            "status": "completed",
            "facilities_polled": 2,
            "reports_ingested": reports_count,
        }
