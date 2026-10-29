"""Report adapters for FHIR, CSV, Chat, and Text."""

from ingest_ai.adapters.base import BaseReportAdapter, ExtractedLot
from ingest_ai.adapters.chat import ChatAdapter
from ingest_ai.adapters.csv_adapter import CsvAdapter
from ingest_ai.adapters.fhir import FhirAdapter
from ingest_ai.adapters.text import TextAdapter

__all__ = [
    "BaseReportAdapter",
    "ExtractedLot",
    "FhirAdapter",
    "CsvAdapter",
    "ChatAdapter",
    "TextAdapter",
]
