"""Base adapter definitions for inbound stock reports."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional


@dataclass
class ExtractedLot:
    drug_code: Optional[str]
    batch_no: Optional[str]
    expiry: Optional[date]
    quantity: Optional[int]
    unit: str
    raw_text: str
    confidence: float
    ambiguity_note: Optional[str] = None


class BaseReportAdapter(ABC):
    @abstractmethod
    async def parse(
        self,
        raw_content: str,
        facility_code: str,
        report_date: date,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[ExtractedLot]:
        """Parse raw report content into a list of canonical extracted lot items."""
        pass
