"""Messy physical register text adapter for H4."""

from datetime import date
import logging
import re
from typing import Any, Dict, List, Optional

from ingest_ai.adapters.base import BaseReportAdapter, ExtractedLot
from ingest_ai.client import ServiceClients
from ingest_ai.date_utils import resolve_clinical_date
from ingest_ai.grounding import GroundingEngine
from ingest_ai.unit_utils import normalize_quantity_and_unit

logger = logging.getLogger("ingest-ai.adapters.text")


class TextAdapter(BaseReportAdapter):
    def __init__(
        self,
        grounding: Optional[GroundingEngine] = None,
        clients: Optional[ServiceClients] = None,
    ) -> None:
        self.grounding = grounding or GroundingEngine()
        self.clients = clients or ServiceClients()

    async def parse(
        self,
        raw_content: str,
        facility_code: str,
        report_date: date,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[ExtractedLot]:
        if not raw_content or not raw_content.strip():
            return []

        # 1. Candidate extraction
        candidates = self.grounding.extract_candidates_for_text(raw_content, top_k=5)

        # 2. Try LLM extraction
        items, tier = await self.clients.call_genai_extract(
            facility=facility_code,
            report_date=report_date,
            raw_text=raw_content,
            candidates=candidates,
        )

        if items:
            return self._process_genai_items(items, facility_code, report_date)

        # 3. Deterministic messy register parser
        return self._deterministic_text_parse(raw_content, facility_code, report_date)

    def _process_genai_items(
        self, items: List[Dict[str, Any]], facility_code: str, report_date: date
    ) -> List[ExtractedLot]:
        results: List[ExtractedLot] = []
        for i, item in enumerate(items):
            code = item.get("drug_code")
            if code and code not in self.grounding.drug_meta and code != "UNKNOWN":
                matches = self.grounding.match_mention(code, top_k=1)
                code = matches[0].drug_code if matches else "UNKNOWN"

            raw_qty = int(item.get("qty", 0) or 0)
            unit_str = item.get("unit")
            pack_size = self.grounding.get_pack_size(code) if code else 1
            qty, base_unit = normalize_quantity_and_unit(raw_qty, unit_str, pack_size)

            exp_str = item.get("expiry")
            exp_date = resolve_clinical_date(exp_str, report_date) if exp_str else None

            batch_no = item.get("batch_no") or f"BATCH-TXT-{facility_code}-{i+1}"
            conf = float(item.get("confidence", 0.88) or 0.88)

            results.append(
                ExtractedLot(
                    drug_code=code,
                    batch_no=str(batch_no),
                    expiry=exp_date,
                    quantity=qty,
                    unit=base_unit,
                    raw_text=item.get("raw_span") or str(item),
                    confidence=conf,
                    ambiguity_note=item.get("ambiguity_note"),
                )
            )
        return results

    def _deterministic_text_parse(
        self, text: str, facility_code: str, report_date: date
    ) -> List[ExtractedLot]:
        results: List[ExtractedLot] = []
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        for i, line in enumerate(lines):
            # Ignore headers and footers
            if any(k in line.lower() for k in ("daily stock", "date:", "date :", "physical count", "ilr status", "signed", "checked", "---")):
                continue

            # Case A: Qty first (e.g. 10000 inzulin reg 100iu vials b.no B-999 exp 14/08/1999)
            m_qty_first = re.match(
                r"^(\d+)\s+([a-zA-Z0-9\.\s]+?)(?:\s+(vials?|tabs?|tablets?|strips?|sachets?|pkt|ampoules?))?\s+(?:b\.no|batch|lot)[:\s]*([\w\-]+)\s+(?:exp|expiring)[:\s]*([0-9/\-]+)",
                line,
                re.IGNORECASE,
            )
            if m_qty_first:
                qty_raw = int(m_qty_first.group(1))
                drug_text = m_qty_first.group(2)
                unit_text = m_qty_first.group(3) or "unit"
                batch_no = m_qty_first.group(4)
                exp_text = m_qty_first.group(5)

                matches = self.grounding.match_mention(drug_text, top_k=1, min_score=0.40)
                code = matches[0].drug_code if matches else "UNKNOWN"
                confidence = matches[0].score if matches else 0.40

                pack_size = self.grounding.get_pack_size(code) if code != "UNKNOWN" else 1
                qty, base_unit = normalize_quantity_and_unit(qty_raw, unit_text, pack_size)
                exp_date = resolve_clinical_date(exp_text, report_date)

                results.append(
                    ExtractedLot(
                        drug_code=code,
                        batch_no=batch_no,
                        expiry=exp_date,
                        quantity=qty,
                        unit=base_unit,
                        raw_text=line,
                        confidence=confidence,
                    )
                )
                continue

            # Case B: Drug name first (e.g. inzulin reg 100iu: 50 vials b.no LOT-INS-H4-01 exp 2026-11-19)
            m_name_first = re.match(
                r"^([a-zA-Z0-9\.\s]+?)[:\-]\s*(\d+)\s*([a-zA-Z]+)?(?:\s+(?:b\.no|batch|lot)[:\s]*([\w\-]+))?(?:\s+(?:exp|expiring)[:\s]*([0-9/\-]+))?",
                line,
                re.IGNORECASE,
            )
            if m_name_first:
                drug_text = m_name_first.group(1)
                qty_raw = int(m_name_first.group(2))
                unit_text = m_name_first.group(3) or "unit"
                batch_no = m_name_first.group(4) or f"BATCH-TXT-{facility_code}-{i+1}"
                exp_text = m_name_first.group(5)

                matches = self.grounding.match_mention(drug_text, top_k=1, min_score=0.40)
                code = matches[0].drug_code if matches else "UNKNOWN"
                confidence = matches[0].score if matches else 0.40

                pack_size = self.grounding.get_pack_size(code) if code != "UNKNOWN" else 1
                qty, base_unit = normalize_quantity_and_unit(qty_raw, unit_text, pack_size)
                exp_date = resolve_clinical_date(exp_text, report_date) if exp_text else None

                results.append(
                    ExtractedLot(
                        drug_code=code,
                        batch_no=batch_no,
                        expiry=exp_date,
                        quantity=qty,
                        unit=base_unit,
                        raw_text=line,
                        confidence=confidence,
                    )
                )
                continue

            # Case C: Freeform token line
            matches = self.grounding.match_mention(line, top_k=1, min_score=0.60)
            if matches:
                code = matches[0].drug_code
                qty_match = re.search(r"\b(\d+)\b", line)
                qty_val = int(qty_match.group(1)) if qty_match else 0
                exp_match = re.search(r"\b(\d{1,2}[/\-]\d{1,2}(?:[/\-]\d{2,4})?|\d{4}-\d{2}-\d{2})\b", line)
                exp_date = resolve_clinical_date(exp_match.group(1), report_date) if exp_match else None
                pack_size = self.grounding.get_pack_size(code)
                qty, base_unit = normalize_quantity_and_unit(qty_val, None, pack_size)

                results.append(
                    ExtractedLot(
                        drug_code=code,
                        batch_no=f"BATCH-TXT-{facility_code}-{i+1}",
                        expiry=exp_date,
                        quantity=qty,
                        unit=base_unit,
                        raw_text=line,
                        confidence=matches[0].score,
                    )
                )

        return results
