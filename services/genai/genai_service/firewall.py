"""Numeric and factual grounding firewall for GenAI narrations and credit memos.

Extracts numbers, percentages, currencies, and dates; verifies each against
the canonical fact set (exact, or ±0.5% for derived percentages);
blocks ungrounded outputs and replaces them with deterministic templates.
"""

from datetime import date, datetime
import logging
import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from genai_service.metrics import metrics_tracker

logger = logging.getLogger(__name__)

# Patterns for extracting entities
DATE_PATTERNS = [
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),                    # 2026-11-20
    re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b"),               # 20/11/2026
    re.compile(r"\b(\d{1,2}-\d{1,2}-\d{4})\b"),               # 20-11-2026
    re.compile(r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b", re.IGNORECASE),
    re.compile(r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})\b", re.IGNORECASE),
]

# Mask patterns for entity codes (e.g. H1, H2, DTA/..., LOT-..., DEV-..., VEH-..., KA-01-...)
ENTITY_MASK_PATTERNS = [
    re.compile(r"\b(?:District Hospital|Hospital|PHC|CHC|Taluk Hospital|Sub-Center|Sub-Centre|Facility|Store|Warehouse|Zone|Tier)\s*\d+\b", re.IGNORECASE),
    re.compile(r"\b[A-Z]{1,4}\d{1,4}\b"),                      # H1, H2, CHC1, PHC12
    re.compile(r"\bDTA/[A-Z0-9\-_/]+\b", re.IGNORECASE),       # DTA/...
    re.compile(r"\bLOT-[A-Z0-9\-_]+\b", re.IGNORECASE),        # LOT-...
    re.compile(r"\bDEV-[A-Z0-9\-_]+\b", re.IGNORECASE),        # DEV-...
    re.compile(r"\bVEH-[A-Z0-9\-_]+\b", re.IGNORECASE),        # VEH-...
    re.compile(r"\b[A-Z]{2}-\d{2}-[A-Z]{1,2}-\d{4}\b"),       # KA-01-EA-1001
    re.compile(r"\bPLAN-[A-Z0-9\-_]+\b", re.IGNORECASE),       # PLAN-...
    re.compile(r"\bCM/[A-Z0-9\-_/]+\b", re.IGNORECASE),        # CM/...
    re.compile(r"\bCOVID-19\b", re.IGNORECASE),                # COVID-19
]

# Currency patterns: ₹ 4,074.00, Rs. 145.50, INR 4074
CURRENCY_PATTERN = re.compile(
    r"(?:₹|Rs\.?|INR)\s*([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)"
)

# Percentage pattern: 93%, 93.3%
PERCENTAGE_PATTERN = re.compile(
    r"([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)\s*%"
)

# Number pattern (Indian comma format or standard float/integer, with optional unit suffix like -vial, -day)
NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_/-])([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)(?:-(?:vial|unit|day|tablet|pack|dose|hr|hour|km|kg|l|ml))?(?![A-Za-z0-9_/-])"
)


def _parse_number_str(s: str) -> float:
    """Parse a number string with potential Indian comma grouping into float."""
    cleaned = s.replace(",", "").strip()
    return float(cleaned)


def _parse_date_to_iso(date_str: str) -> Optional[str]:
    """Parse varying date formats to YYYY-MM-DD string."""
    date_str = date_str.strip()
    # Try ISO
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date().isoformat()
    except ValueError:
        pass
    # Try DD/MM/YYYY
    try:
        return datetime.strptime(date_str, "%d/%m/%Y").date().isoformat()
    except ValueError:
        pass
    # Try DD-MM-YYYY
    try:
        return datetime.strptime(date_str, "%d-%m-%Y").date().isoformat()
    except ValueError:
        pass
    # Try "20 Nov 2026"
    for fmt in ("%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(date_str.replace(",", ""), fmt).date().isoformat()
        except ValueError:
            pass
    return None


def extract_facts_numbers(facts: Dict[str, Any]) -> Tuple[Set[float], Set[float], Set[str]]:
    """Extract standard allowed numbers, derived percentages, and dates from facts."""
    allowed_numbers: Set[float] = set()
    allowed_percentages: Set[float] = set()
    allowed_dates: Set[str] = set()

    def _walk(val: Any, key_hint: str = ""):
        if val is None:
            return
        if isinstance(val, (int, float)):
            f_val = float(val)
            if "pct" in key_hint or "percent" in key_hint:
                allowed_percentages.add(f_val)
            else:
                allowed_numbers.add(f_val)
        elif isinstance(val, (date, datetime)):
            allowed_dates.add(val.strftime("%Y-%m-%d"))
        elif isinstance(val, str):
            iso_d = _parse_date_to_iso(val)
            if iso_d:
                allowed_dates.add(iso_d)
            # Try float conversion for numeric strings
            try:
                cleaned = val.replace(",", "").strip()
                if re.match(r"^-?\d+(?:\.\d+)?$", cleaned):
                    f_val = float(cleaned)
                    if "pct" in key_hint or "percent" in key_hint:
                        allowed_percentages.add(f_val)
                    else:
                        allowed_numbers.add(f_val)
            except Exception:
                pass
        elif isinstance(val, dict):
            for k, v in val.items():
                _walk(v, k.lower())
        elif isinstance(val, (list, tuple, set)):
            for item in val:
                _walk(item, key_hint)

    _walk(facts)

    # Pre-compute standard derived percentages if facts has shortage and quantity
    qty = facts.get("quantity") or facts.get("usable_quantity")
    shortage_before = facts.get("shortage_before")
    lot_qty = facts.get("lot_quantity")

    if qty and shortage_before and float(shortage_before) > 0:
        pct = (float(qty) / float(shortage_before)) * 100.0
        allowed_percentages.add(round(pct, 1))
        allowed_percentages.add(round(pct, 0))
        allowed_percentages.add(pct)

    if qty and lot_qty and float(lot_qty) > 0:
        pct = (float(qty) / float(lot_qty)) * 100.0
        allowed_percentages.add(round(pct, 1))
        allowed_percentages.add(round(pct, 0))
        allowed_percentages.add(pct)

    # Any explicit entries
    if "allowed_numbers" in facts and isinstance(facts["allowed_numbers"], list):
        for num in facts["allowed_numbers"]:
            allowed_numbers.add(float(num))

    if "allowed_percentages" in facts and isinstance(facts["allowed_percentages"], list):
        for pct_val in facts["allowed_percentages"]:
            allowed_percentages.add(float(pct_val))

    if "allowed_dates" in facts and isinstance(facts["allowed_dates"], list):
        for d_str in facts["allowed_dates"]:
            iso = _parse_date_to_iso(str(d_str))
            if iso:
                allowed_dates.add(iso)

    return allowed_numbers, allowed_percentages, allowed_dates


def extract_tokens_from_text(text: str, facts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Extract dates, currencies, percentages, and numbers from text."""
    working_text = text

    # Mask known facility names from facts if present
    if facts:
        for k in ("source_facility_name", "destination_facility_name", "donor_facility_name", "recipient_facility_name", "creditor_facility_name", "debtor_facility_name"):
            val = facts.get(k)
            if val and isinstance(val, str) and val in working_text:
                working_text = working_text.replace(val, " " * len(val))

    # 1. Extract dates and mask them out
    extracted_dates: List[str] = []
    for pat in DATE_PATTERNS:
        for match in pat.finditer(working_text):
            raw_match = match.group(1)
            iso = _parse_date_to_iso(raw_match)
            if iso:
                extracted_dates.append(iso)
            # Mask out date in working text
            working_text = (
                working_text[:match.start()]
                + (" " * (match.end() - match.start()))
                + working_text[match.end():]
            )

    # 2. Mask out known entity identifiers (H1, LOT-..., DTA/...)
    for pat in ENTITY_MASK_PATTERNS:
        def _mask_match(m):
            return " " * len(m.group(0))
        working_text = pat.sub(_mask_match, working_text)

    # 3. Extract Currencies and mask them out
    extracted_currencies: List[float] = []
    for match in CURRENCY_PATTERN.finditer(working_text):
        val = _parse_number_str(match.group(1))
        extracted_currencies.append(val)
        working_text = (
            working_text[:match.start()]
            + (" " * (match.end() - match.start()))
            + working_text[match.end():]
        )

    # 4. Extract Percentages and mask them out
    extracted_percentages: List[float] = []
    for match in PERCENTAGE_PATTERN.finditer(working_text):
        val = _parse_number_str(match.group(1))
        extracted_percentages.append(val)
        working_text = (
            working_text[:match.start()]
            + (" " * (match.end() - match.start()))
            + working_text[match.end():]
        )

    # 5. Extract Standalone Numbers
    extracted_numbers: List[float] = []
    for match in NUMBER_PATTERN.finditer(working_text):
        val = _parse_number_str(match.group(1))
        extracted_numbers.append(val)

    return {
        "dates": extracted_dates,
        "currencies": extracted_currencies,
        "percentages": extracted_percentages,
        "numbers": extracted_numbers,
    }


def verify_grounding(
    text: str,
    facts: Dict[str, Any],
    tolerance_pct: float = 0.5,
) -> Dict[str, Any]:
    """Verify that every number, currency, percentage, and date in text is grounded in facts.

    Returns:
        Dict with:
            passed: bool
            verified_numbers: List[float]
            unverified_numbers: List[float]
            unverified_dates: List[str]
    """
    allowed_numbers, allowed_percentages, allowed_dates = extract_facts_numbers(facts)
    tokens = extract_tokens_from_text(text, facts=facts)

    verified_numbers: List[float] = []
    unverified_numbers: List[float] = []
    unverified_dates: List[str] = []

    # 1. Verify Dates
    for d in tokens["dates"]:
        if d in allowed_dates:
            pass  # Grounded
        else:
            unverified_dates.append(d)

    # 2. Verify Percentages (tolerance ±0.5%)
    for pct in tokens["percentages"]:
        matched = False
        for allowed in allowed_percentages:
            if abs(pct - allowed) <= tolerance_pct:
                matched = True
                break
        # Also allow percentage if directly matching a number in facts (e.g. 50% matching 50)
        if not matched:
            for num in allowed_numbers:
                if abs(pct - num) <= tolerance_pct:
                    matched = True
                    break

        if matched:
            # Cast integer floats to int if appropriate for clean representation
            verified_numbers.append(int(pct) if pct.is_integer() else pct)
        else:
            unverified_numbers.append(int(pct) if pct.is_integer() else pct)

    # 3. Verify Currencies (exact match against allowed numbers)
    for curr in tokens["currencies"]:
        matched = False
        for num in allowed_numbers:
            if math.isclose(curr, num, rel_tol=1e-4, abs_tol=1e-2):
                matched = True
                break
        if matched:
            verified_numbers.append(int(curr) if curr.is_integer() else curr)
        else:
            unverified_numbers.append(int(curr) if curr.is_integer() else curr)

    # 4. Verify Numbers (exact match against allowed numbers)
    for num in tokens["numbers"]:
        matched = False
        for allowed in allowed_numbers:
            if math.isclose(num, allowed, rel_tol=1e-4, abs_tol=1e-4):
                matched = True
                break
        # Also check against allowed percentages
        if not matched:
            for allowed in allowed_percentages:
                if abs(num - allowed) <= tolerance_pct:
                    matched = True
                    break

        if matched:
            verified_numbers.append(int(num) if num.is_integer() else num)
        else:
            unverified_numbers.append(int(num) if num.is_integer() else num)

    passed = (len(unverified_numbers) == 0) and (len(unverified_dates) == 0)

    return {
        "passed": passed,
        "verified_numbers": verified_numbers,
        "unverified_numbers": unverified_numbers,
        "unverified_dates": unverified_dates,
    }


def generate_deterministic_narration(facts: Dict[str, Any]) -> str:
    """Generate deterministic, guaranteed grounded narration fallback from facts."""
    drug = facts.get("drug_name") or facts.get("drug_code", "Medicine")
    code = facts.get("drug_code", "")
    qty = facts.get("quantity") or facts.get("usable_quantity", 0)
    batch = facts.get("batch_no", "N/A")
    expiry = facts.get("lot_expiry") or facts.get("expiry_date", "N/A")
    src = facts.get("source_facility_name") or facts.get("source_facility_id", "source facility")
    dst = facts.get("destination_facility_name") or facts.get("destination_facility_id", "destination facility")
    shortage_before = facts.get("shortage_before")
    shortage_after = facts.get("shortage_after")

    shortage_text = (
        f"addressing an immediate deficit of {shortage_before} units"
        if shortage_before is not None
        else "addressing immediate clinical demand"
    )
    if shortage_after is not None:
        shortage_text += f" (residual deficit: {shortage_after} units)"

    return (
        f"Reallocation of {qty} units of {drug} ({code}, Batch: {batch}, Expiry: {expiry}) "
        f"from {src} to {dst}. This transfer optimizes stock balance by {shortage_text} "
        f"while protecting reserves and avoiding expiration loss at the donor facility."
    )


def generate_deterministic_credit_memo(facts: Dict[str, Any]) -> str:
    """Generate deterministic, guaranteed grounded credit memo paragraph from facts."""
    donor = facts.get("creditor_facility_name") or facts.get("donor_facility_name") or facts.get("creditor_facility_id") or "Donor Facility"
    recipient = facts.get("debtor_facility_name") or facts.get("recipient_facility_name") or facts.get("debtor_facility_id") or "Receiving Facility"
    drug = facts.get("drug_name") or facts.get("drug_code", "Medicine")
    code = facts.get("drug_code", "")
    qty = facts.get("quantity", 0)
    unit_cost = facts.get("unit_cost_inr", 0.0)
    total_val = facts.get("total_credit_inr") or facts.get("value_inr", 0.0)

    return (
        f"This Inter-Facility Credit Memo certifies that {donor} has transferred {qty} units of {drug} ({code}) "
        f"valued at ₹{total_val:.2f} (unit cost ₹{unit_cost:.2f}) to {recipient}. This transfer avoided complete "
        f"expiration loss at the donor store. It is recommended that {donor} receive a credit of ₹{total_val:.2f} "
        f"against its next quarterly drug indent allocation."
    )


def process_narration_through_firewall(
    raw_narration: str,
    headline: Optional[str],
    facts: Dict[str, Any],
    record_metric: bool = True,
) -> Dict[str, Any]:
    """Check narration against facts with numeric firewall; replace with deterministic template on failure."""
    grounding_result = verify_grounding(raw_narration, facts)

    if grounding_result["passed"]:
        final_narration = raw_narration
        final_headline = headline or f"Transfer of {facts.get('quantity', '')} units of {facts.get('drug_code', '')}"
    else:
        logger.warning(
            f"Numeric firewall BLOCKED narration for order {facts.get('order_id', 'unknown')}. "
            f"Unverified numbers: {grounding_result['unverified_numbers']}, "
            f"Unverified dates: {grounding_result['unverified_dates']}"
        )
        if record_metric:
            metrics_tracker.record(
                purpose="narration",
                cached=False,
                latency_sec=0.0,
                ok=False,
                firewall_block=True,
            )

        final_narration = generate_deterministic_narration(facts)
        final_headline = f"Stock Reallocation: {facts.get('drug_name', facts.get('drug_code', 'Medicine'))}"
        # Recalculate grounding on deterministic fallback (guaranteed to pass)
        grounding_result = verify_grounding(final_narration, facts)
        # Mark that firewall caught an issue initially
        grounding_result["fallback_used"] = True

    return {
        "headline": final_headline,
        "explanation": final_narration,
        "grounding_check": {
            "passed": grounding_result["passed"],
            "verified_numbers": grounding_result["verified_numbers"],
            "unverified_numbers": grounding_result["unverified_numbers"],
        },
    }
