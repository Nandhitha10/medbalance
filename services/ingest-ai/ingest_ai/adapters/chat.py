"""Bilingual Kannada + English informal chat adapter for H3."""

from datetime import date
import logging
import re
from typing import Any, Dict, List, Optional

from ingest_ai.adapters.base import BaseReportAdapter, ExtractedLot
from ingest_ai.client import ServiceClients
from ingest_ai.date_utils import resolve_clinical_date
from ingest_ai.grounding import GroundingEngine
from ingest_ai.unit_utils import normalize_quantity_and_unit

logger = logging.getLogger("ingest-ai.adapters.chat")


class ChatAdapter(BaseReportAdapter):
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

        # 1. Candidate extraction via RapidFuzz grounding
        candidates = self.grounding.extract_candidates_for_text(raw_content, top_k=5)

        # 2. Try LLM extraction via GenAI Gateway
        items, tier = await self.clients.call_genai_extract(
            facility=facility_code,
            report_date=report_date,
            raw_text=raw_content,
            candidates=candidates,
        )

        if items:
            return self._process_genai_items(items, facility_code, report_date)

        # 3. Deterministic regex & grounding fallback
        return self._deterministic_chat_parse(raw_content, facility_code, report_date)

    def _process_genai_items(
        self, items: List[Dict[str, Any]], facility_code: str, report_date: date
    ) -> List[ExtractedLot]:
        results: List[ExtractedLot] = []
        for i, item in enumerate(items):
            code = item.get("drug_code")
            if code and code not in self.grounding.drug_meta and code != "UNKNOWN":
                # Verify code against formulary
                matches = self.grounding.match_mention(code, top_k=1)
                code = matches[0].drug_code if matches else "UNKNOWN"

            raw_qty = int(item.get("qty", 0) or 0)
            unit_str = item.get("unit")
            pack_size = self.grounding.get_pack_size(code) if code else 1
            qty, base_unit = normalize_quantity_and_unit(raw_qty, unit_str, pack_size)

            exp_str = item.get("expiry")
            exp_date = resolve_clinical_date(exp_str, report_date) if exp_str else None

            batch_no = item.get("batch_no") or f"BATCH-CHAT-{facility_code}-{i+1}"
            conf = float(item.get("confidence", 0.90) or 0.90)

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

    def _deterministic_chat_parse(
        self, text: str, facility_code: str, report_date: date
    ) -> List[ExtractedLot]:
        """Regex + Grounding parser for Kannada and English chat patterns."""
        results: List[ExtractedLot] = []

        patterns = [
            # ORS patterns: ORS {qty} sachets (exp {exp}) | ORS-{qty} | ORS={qty}
            (
                r"(?:ORS|ಒಆರ್‌ಎಸ್)[\s\-=:]*(\d+)[\s]*(sachets?|pkt|packets?|nos|boxes)?(?:[\s\w\(\)]*?(?:exp|expiring)[\s:]*([0-9/\-]+))?(?:[\s\w\(\)]*?LOT:[\s]*([\w\-]+))?",
                "ORS-20",
                "sachet",
            ),
            # PCM patterns: Paracetamol|PCM|ಪ್ಯಾರಸಿಟಮಾಲ್ {qty} tabs (exp {exp}) | strips
            (
                r"(?:Paracetamol|PCM|ಪ್ಯಾರಸಿಟಮಾಲ್|Dolo)[\s\w]*?[\s\-=:]*(\d+)[\s]*(tabs?|strips?|nos|tablets)?(?:[\s\w\(\)]*?(?:exp|expiring)[\s:]*([0-9/\-]+))?(?:[\s\w\(\)]*?LOT:[\s]*([\w\-]+))?",
                "PCM-500",
                "tablet",
            ),
            # Amoxicillin patterns: Amoxicillin|Amoxy|ಅಮಾಕ್ಸಿಸಿಲಿನ್ {qty} tabs
            (
                r"(?:Amoxicillin|Amoxy|ಅಮಾಕ್ಸಿಸಿಲಿನ್)[\s\w]*?[\s\-=:]*(\d+)[\s]*(tabs?|strips?|caps?|tablets)?(?:[\s\w\(\)]*?(?:exp|expiring)[\s:]*([0-9/\-]+))?",
                "AMOX-500",
                "tablet",
            ),
            # Metformin patterns: Metformin|ಮೆಟ್‌ಫಾರ್ಮಿನ್ {qty}
            (
                r"(?:Metformin|ಮೆಟ್‌ಫಾರ್ಮಿನ್)[\s\w]*?[\s\-=:]*(\d+)[\s]*(tabs?|strips?|tablets)?(?:[\s\w\(\)]*?(?:exp|expiring)[\s:]*([0-9/\-]+))?",
                "MET-500",
                "tablet",
            ),
        ]

        found_codes = set()
        for regex, code, default_unit in patterns:
            for match in re.finditer(regex, text, re.IGNORECASE):
                qty_raw = int(match.group(1))
                unit_matched = match.group(2) if len(match.groups()) >= 2 else default_unit
                exp_raw = match.group(3) if len(match.groups()) >= 3 else None
                batch_raw = match.group(4) if len(match.groups()) >= 4 else None

                pack_size = self.grounding.get_pack_size(code)
                qty, base_unit = normalize_quantity_and_unit(qty_raw, unit_matched or default_unit, pack_size)
                exp_date = resolve_clinical_date(exp_raw, report_date) if exp_raw else None
                batch_no = batch_raw or f"BATCH-CHAT-{facility_code}-{code}"

                results.append(
                    ExtractedLot(
                        drug_code=code,
                        batch_no=batch_no,
                        expiry=exp_date,
                        quantity=qty,
                        unit=base_unit,
                        raw_text=match.group(0),
                        confidence=0.92,
                    )
                )
                found_codes.add(code)

        # Check for zero stock mentions (e.g. ಇನ್ಸುಲಿನ್ ಇಲ್ಲ / zero insulin)
        if re.search(r"(?:ಇನ್ಸುಲಿನ್|insulin)[\s]*(?:ಇಲ್ಲ|ಸ್ಟಾಕ್ ಇಲ್ಲ|0\s*vials|zero|none)", text, re.IGNORECASE):
            results.append(
                ExtractedLot(
                    drug_code="INS-REG",
                    batch_no=f"BATCH-OUT-OF-STOCK-{facility_code}",
                    expiry=report_date,
                    quantity=0,
                    unit="vial",
                    raw_text="ಇನ್ಸುಲಿನ್ ಇಲ್ಲ (no insulin in stock)",
                    confidence=0.95,
                    ambiguity_note="Reported zero stock",
                )
            )

        return results
