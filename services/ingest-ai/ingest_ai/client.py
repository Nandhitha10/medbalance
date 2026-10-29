"""HTTP clients for calling GenAI gateway, Core-API, and simulated hospital endpoints."""

from datetime import date
import logging
from typing import Any, Dict, List, Optional, Tuple
import httpx

from medbal_common.settings import get_settings

logger = logging.getLogger("ingest-ai.client")


class ServiceClients:
    def __init__(
        self,
        genai_url: Optional[str] = None,
        core_api_url: Optional[str] = None,
        h1_url: Optional[str] = None,
        h2_url: Optional[str] = None,
        timeout: float = 0.5,
    ) -> None:
        settings = get_settings()
        self.genai_url = (genai_url or settings.GENAI_URL).rstrip("/")
        self.core_api_url = (core_api_url or settings.CORE_API_URL).rstrip("/")
        self.h1_url = (h1_url or settings.SIM_HOSPITAL_H1_URL).rstrip("/")
        self.h2_url = (h2_url or settings.SIM_HOSPITAL_H2_URL).rstrip("/")
        self.timeout = timeout

    async def call_genai_extract(
        self,
        facility: str,
        report_date: date,
        raw_text: str,
        candidates: List[str],
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Call GenAI gateway /llm/complete for structured stock extraction, with fallback."""
        url = f"{self.genai_url}/llm/complete"
        payload = {
            "purpose": "stock_extraction",
            "prompt_id": "extract",
            "version": 1,
            "input": {
                "facility": facility,
                "report_date": report_date.isoformat(),
                "candidates": candidates,
                "raw_text": raw_text,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    output = data.get("output", {})
                    items = output.get("items", [])
                    return items, "genai_gateway"
                else:
                    logger.warning("GenAI gateway returned status %s: %s", resp.status_code, resp.text)
        except Exception as e:
            logger.debug("GenAI gateway unavailable (%s), using deterministic fallback", e)

        return [], "deterministic_fallback"

    async def call_genai_anomaly_explain(
        self,
        facility: str,
        drug_code: Optional[str],
        batch_no: Optional[str],
        expiry: Optional[str],
        qty: Optional[int],
        triggered_rules: List[str],
        details: str,
    ) -> Tuple[str, str]:
        """Call GenAI gateway to get a one-sentence plain English explanation, with fallback."""
        url = f"{self.genai_url}/llm/complete"
        payload = {
            "purpose": "anomaly_explanation",
            "prompt_id": "anomaly_explain",
            "version": 1,
            "input": {
                "facility": facility,
                "drug_code": drug_code or "UNKNOWN",
                "batch_no": batch_no or "N/A",
                "expiry": expiry or "N/A",
                "qty": qty if qty is not None else 0,
                "triggered_rules": triggered_rules,
                "details": details,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    explanation = data.get("output", {}).get("explanation")
                    if explanation:
                        return explanation, "genai_gateway"
        except Exception as e:
            logger.debug("GenAI gateway explain failed (%s), using template fallback", e)

        # Deterministic template fallback
        rules_str = ", ".join(triggered_rules)
        return f"Item flagged due to {rules_str}: {details}", "deterministic_fallback"

    async def upsert_lots_to_core_api(self, lots: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """Push verified lots to core-api /lots/upsert-batch."""
        if not lots:
            return True, "No lots to upsert"

        url = f"{self.core_api_url}/lots/upsert-batch"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json={"lots": lots})
                if resp.status_code in (200, 201):
                    return True, "Success"
                return False, f"core-api returned {resp.status_code}: {resp.text}"
        except Exception as e:
            logger.warning("core-api upsert failed (%s)", e)
            return False, str(e)

    async def fetch_h1_fhir(self) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Fetch FHIR inventory report from H1."""
        url = f"{self.h1_url}/fhir/InventoryReport"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return resp.json(), None
                return None, f"H1 HTTP {resp.status_code}"
        except Exception as e:
            return None, str(e)

    async def fetch_h2_csv(self) -> Tuple[Optional[str], Optional[str]]:
        """Fetch e-Aushadhi CSV stock export from H2."""
        url = f"{self.h2_url}/export/stock.csv"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return resp.text, None
                return None, f"H2 HTTP {resp.status_code}"
        except Exception as e:
            return None, str(e)
