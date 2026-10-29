"""e-Aushadhi CSV stock export adapter for H2."""

import csv
from datetime import date
import io
import logging
from typing import Any, Dict, List, Optional

from ingest_ai.adapters.base import BaseReportAdapter, ExtractedLot
from ingest_ai.date_utils import resolve_clinical_date
from ingest_ai.grounding import GroundingEngine
from ingest_ai.unit_utils import normalize_quantity_and_unit

logger = logging.getLogger("ingest-ai.adapters.csv")


class CsvAdapter(BaseReportAdapter):
    def __init__(self, grounding: Optional[GroundingEngine] = None) -> None:
        self.grounding = grounding or GroundingEngine()

    async def parse(
        self,
        raw_content: str,
        facility_code: str,
        report_date: date,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[ExtractedLot]:
        results: List[ExtractedLot] = []
        if not raw_content or not raw_content.strip():
            return results

        reader = csv.reader(io.StringIO(raw_content))
        header = None
        row_idx = 0

        for row in reader:
            if not row or not any(field.strip() for field in row):
                continue

            row_clean = [f.strip() for f in row]
            if header is None:
                # First non-empty row is header
                header = [h.lower().replace(" ", "_") for h in row_clean]
                continue

            row_idx += 1
            row_dict = dict(zip(header, row_clean))

            drug_name = (
                row_dict.get("drug_name")
                or row_dict.get("name")
                or row_dict.get("drug")
                or (row_clean[0] if len(row_clean) > 0 else "")
            )
            batch_no = (
                row_dict.get("batch_no")
                or row_dict.get("batch")
                or row_dict.get("lot")
                or (row_clean[1] if len(row_clean) > 1 else "")
            )
            exp_str = (
                row_dict.get("exp_date")
                or row_dict.get("expiry")
                or row_dict.get("exp")
                or (row_clean[2] if len(row_clean) > 2 else "")
            )
            qty_str = (
                row_dict.get("qty")
                or row_dict.get("quantity")
                or (row_clean[3] if len(row_clean) > 3 else "0")
            )
            unit_str = (
                row_dict.get("unit")
                or (row_clean[4] if len(row_clean) > 4 else "")
            )

            # Match drug code
            matches = self.grounding.match_mention(drug_name, top_k=1, min_score=0.50)
            if matches:
                drug_code = matches[0].drug_code
                confidence = matches[0].score
            else:
                drug_code = "UNKNOWN"
                confidence = 0.40

            # Missing batch number handling
            if not batch_no:
                batch_no = f"BATCH-UNSPECIFIED-{facility_code}-{row_idx}"

            # Date resolution (including MM/YYYY to last day of month)
            expiry_date = resolve_clinical_date(exp_str, report_date)

            try:
                raw_qty = int(qty_str)
            except ValueError:
                raw_qty = 0

            pack_size = self.grounding.get_pack_size(drug_code) if drug_code else 1
            converted_qty, base_unit = normalize_quantity_and_unit(raw_qty, unit_str, pack_size)

            raw_line = ",".join(row_clean)
            results.append(
                ExtractedLot(
                    drug_code=drug_code,
                    batch_no=batch_no,
                    expiry=expiry_date,
                    quantity=converted_qty,
                    unit=base_unit,
                    raw_text=raw_line,
                    confidence=confidence,
                )
            )

        return results
