"""FHIR InventoryReport adapter for H1."""

from datetime import date
import json
import logging
from typing import Any, Dict, List, Optional

from ingest_ai.adapters.base import BaseReportAdapter, ExtractedLot
from ingest_ai.date_utils import resolve_clinical_date
from ingest_ai.grounding import GroundingEngine
from ingest_ai.unit_utils import normalize_quantity_and_unit

logger = logging.getLogger("ingest-ai.adapters.fhir")


class FhirAdapter(BaseReportAdapter):
    def __init__(self, grounding: Optional[GroundingEngine] = None) -> None:
        self.grounding = grounding or GroundingEngine()

    async def parse(
        self,
        raw_content: str,
        facility_code: str,
        report_date: date,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[ExtractedLot]:
        try:
            data = json.loads(raw_content)
        except Exception as e:
            logger.error("Failed to parse FHIR JSON: %s", e)
            return []

        results: List[ExtractedLot] = []

        # Check inventoryListing (FHIR standard)
        listing = data.get("inventoryListing", [])
        if listing:
            for item in listing:
                concept = item.get("item", {}).get("concept", {})
                codings = concept.get("coding", [])
                code = None
                display_name = ""
                for c in codings:
                    if c.get("code"):
                        code = c.get("code")
                        display_name = c.get("display", "")
                        break

                if not code and display_name:
                    matches = self.grounding.match_mention(display_name, top_k=1)
                    if matches:
                        code = matches[0].drug_code

                batch_no = item.get("lot") or item.get("batch") or "UNKNOWN-BATCH"
                exp_raw = item.get("expiry")
                exp_date = resolve_clinical_date(exp_raw, report_date)

                qty_info = item.get("quantity", {})
                raw_qty = qty_info.get("value", 0) if isinstance(qty_info, dict) else qty_info
                unit_str = qty_info.get("unit") if isinstance(qty_info, dict) else "unit"

                pack_size = self.grounding.get_pack_size(code) if code else 1
                qty, unit = normalize_quantity_and_unit(int(raw_qty or 0), unit_str, pack_size)

                results.append(
                    ExtractedLot(
                        drug_code=code or "UNKNOWN",
                        batch_no=str(batch_no),
                        expiry=exp_date,
                        quantity=qty,
                        unit=unit,
                        raw_text=json.dumps(item),
                        confidence=1.0,
                    )
                )
            return results

        # Fallback to item[] (FHIR R4 flat style)
        items = data.get("item", [])
        for entry in items:
            it = entry.get("item", {})
            code = it.get("code")
            display_name = it.get("display", "")
            if not code and display_name:
                matches = self.grounding.match_mention(display_name, top_k=1)
                if matches:
                    code = matches[0].drug_code

            batch_no = it.get("batch") or entry.get("batch") or "UNKNOWN-BATCH"
            exp_raw = it.get("expiry") or entry.get("expiry")
            exp_date = resolve_clinical_date(exp_raw, report_date)

            raw_qty = entry.get("quantity", 0)
            pack_size = self.grounding.get_pack_size(code) if code else 1
            qty, unit = normalize_quantity_and_unit(int(raw_qty or 0), None, pack_size)

            results.append(
                ExtractedLot(
                    drug_code=code or "UNKNOWN",
                    batch_no=str(batch_no),
                    expiry=exp_date,
                    quantity=qty,
                    unit=unit,
                    raw_text=json.dumps(entry),
                    confidence=1.0,
                )
            )

        return results
