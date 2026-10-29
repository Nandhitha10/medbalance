"""Anomaly detection gate and explanation generation for extracted inventory lots."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from ingest_ai.db_models import ConsumptionDailyModel, DrugModel, LotModel


@dataclass
class AnomalyEvaluation:
    is_anomalous: bool
    triggered_rules: List[str]
    anomaly_type: str
    details: str


class AnomalyDetector:
    """Evaluates extracted items against safety and integrity rules."""

    def __init__(self, session: Optional[Session] = None) -> None:
        self.session = session

    def evaluate_item(
        self,
        facility_id: str,
        drug_code: Optional[str],
        batch_no: Optional[str],
        expiry: Optional[date],
        quantity: Optional[int],
        confidence: Optional[float],
        report_date: date,
        known_drug_codes: Optional[set[str]] = None,
    ) -> AnomalyEvaluation:
        """Run the 5 anomaly detection checks."""
        triggered_rules: List[str] = []
        details_list: List[str] = []
        primary_anomaly_type = "SUSPICIOUS_EXPIRY"

        # Check 1: UNKNOWN drug
        is_unknown = False
        if not drug_code or drug_code == "UNKNOWN":
            is_unknown = True
        elif known_drug_codes and drug_code not in known_drug_codes:
            is_unknown = True

        if is_unknown:
            triggered_rules.append("UNKNOWN_DRUG")
            details_list.append(f"Drug '{drug_code}' could not be matched to a known formulary code")
            primary_anomaly_type = "UNKNOWN_DRUG"

        # Check 2: Expiry in past or > 5 years ahead
        if expiry is None:
            triggered_rules.append("MISSING_EXPIRY")
            details_list.append("Expiry date is missing or unparseable")
            primary_anomaly_type = "SUSPICIOUS_EXPIRY"
        else:
            five_years_ahead = report_date.replace(year=report_date.year + 5)
            if expiry < report_date:
                triggered_rules.append("SUSPICIOUS_EXPIRY_PAST")
                details_list.append(f"Parsed expiry {expiry} is in the past (report date {report_date})")
                primary_anomaly_type = "SUSPICIOUS_EXPIRY"
            elif expiry > five_years_ahead:
                triggered_rules.append("SUSPICIOUS_EXPIRY_FUTURE")
                details_list.append(f"Parsed expiry {expiry} exceeds 5 years from report date")
                primary_anomaly_type = "SUSPICIOUS_EXPIRY"

        # Check 3: Quantity spike (> 10 * typical on-hand)
        qty_val = quantity if quantity is not None else 0
        typical_on_hand = self._get_typical_on_hand(facility_id, drug_code)
        if typical_on_hand > 0 and qty_val > 10 * typical_on_hand:
            triggered_rules.append("QUANTITY_SPIKE")
            details_list.append(
                f"Reported quantity {qty_val} is {round(qty_val / typical_on_hand, 1)}x typical on-hand ({typical_on_hand})"
            )
            primary_anomaly_type = "QUANTITY_SPIKE"

        # Check 4: Same batch at another facility with different expiry
        if batch_no and drug_code and expiry and self.session:
            batch_clean = batch_no.strip()
            if batch_clean and not batch_clean.upper().startswith("UNKNOWN"):
                mismatch_facility = self._check_batch_expiry_mismatch(facility_id, drug_code, batch_clean, expiry)
                if mismatch_facility:
                    triggered_rules.append("BATCH_EXPIRY_MISMATCH")
                    details_list.append(
                        f"Batch '{batch_clean}' exists at facility {mismatch_facility} with a different expiry date"
                    )
                    if primary_anomaly_type != "QUANTITY_SPIKE":
                        primary_anomaly_type = "SUSPICIOUS_EXPIRY"

        # Check 5: Low confidence (< 0.85)
        if confidence is not None and confidence < 0.85:
            triggered_rules.append("LOW_CONFIDENCE")
            details_list.append(f"Extraction confidence {confidence:.2f} is below safety threshold 0.85")
            if not is_unknown and primary_anomaly_type == "SUSPICIOUS_EXPIRY" and "SUSPICIOUS_EXPIRY_PAST" not in triggered_rules:
                primary_anomaly_type = "CORRUPTED_TEXT"

        is_anomalous = len(triggered_rules) > 0
        details = "; ".join(details_list) if details_list else "Clean item"

        return AnomalyEvaluation(
            is_anomalous=is_anomalous,
            triggered_rules=triggered_rules,
            anomaly_type=primary_anomaly_type,
            details=details,
        )

    def _get_typical_on_hand(self, facility_id: str, drug_code: Optional[str]) -> int:
        """Estimate typical 90-day on-hand stock from consumption or existing lots."""
        if not drug_code:
            return 500

        if not self.session:
            # Baseline heuristic defaults per category
            if drug_code.startswith("INS-") or drug_code.startswith("OXY-") or drug_code.startswith("ASV-"):
                return 100
            if drug_code.startswith("PCM-") or drug_code.startswith("AMOX-") or drug_code.startswith("IFA-"):
                return 3000
            return 500

        try:
            # 1. Check existing lots quantity at this facility
            lots = self.session.scalars(
                select(LotModel).where(
                    LotModel.facility_id == facility_id,
                    LotModel.drug_code == drug_code,
                )
            ).all()
            if lots:
                total_qty = sum(lt.quantity for lt in lots)
                if total_qty > 0:
                    return total_qty

            # 2. Check 90-day daily consumption sum or average
            consumptions = self.session.scalars(
                select(ConsumptionDailyModel).where(
                    ConsumptionDailyModel.facility_id == facility_id,
                    ConsumptionDailyModel.drug_code == drug_code,
                )
            ).all()
            if consumptions:
                # 30-day demand estimate
                avg_daily = sum(c.quantity for c in consumptions) / max(1, len(consumptions))
                return max(10, int(avg_daily * 30))
        except Exception:
            pass

        return 500

    def _check_batch_expiry_mismatch(
        self, facility_id: str, drug_code: str, batch_no: str, expiry: date
    ) -> Optional[str]:
        """Return the conflicting facility_id if the same batch has a different expiry elsewhere."""
        try:
            conflicts = self.session.scalars(
                select(LotModel).where(
                    LotModel.drug_code == drug_code,
                    LotModel.batch_no == batch_no,
                    LotModel.facility_id != facility_id,
                )
            ).all()
            for c in conflicts:
                if c.expiry != expiry:
                    return c.facility_id
        except Exception:
            pass
        return None
