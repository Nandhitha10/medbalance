"""Context Multiplier Evaluation: Signals, Static Calendar, LLM Gateway, and Guardrails."""

import time
from datetime import date
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
import httpx

from medbal_common.settings import get_settings
from forecast.calendar import get_calendar_signals

logger = logging.getLogger(__name__)

# Fast circuit breaker for unreachable GenAI gateway
_genai_offline_until: float = 0.0


def find_relevant_signals(
    facility_id: str,
    drug_code: str,
    active_signals: List[Dict[str, Any]],
    current_date: Optional[date] = None,
    include_calendar: bool = True,
) -> List[Dict[str, Any]]:
    """Filter signals that apply to a specific (facility_id, drug_code) pair."""
    all_signals = list(active_signals)
    if include_calendar and current_date:
        cal_signals = get_calendar_signals(current_date)
        all_signals.extend(cal_signals)

    relevant: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()

    for s in all_signals:
        sig_id = s.get("id") or s.get("signal_id") or ""
        if not sig_id or sig_id in seen_ids:
            continue

        fac = s.get("facility") or s.get("facility_id")
        fac_match = (fac in (facility_id, "ALL") or not fac)

        d_affected = s.get("drugs_affected") or []
        primary_d = s.get("drug_code")

        if d_affected:
            drug_match = drug_code in d_affected
        elif primary_d:
            drug_match = (primary_d == "ALL" or primary_d == drug_code)
        else:
            drug_match = True

        if fac_match and drug_match:
            seen_ids.add(sig_id)
            relevant.append(s)

    return relevant


def apply_guardrails(
    raw_multiplier: float,
    confidence: float,
    cited_signal_ids: List[str],
    valid_signal_ids: Set[str],
) -> Tuple[float, float, List[str], str]:
    """Strictly apply CLAUDE.md guardrails to context multiplier:
    
    1. Clamp multiplier to [0.5, 3.0].
    2. If confidence < 0.5 -> reset multiplier to 1.0.
    3. If no valid signal ID cited (or empty) -> reset multiplier to 1.0.
    """
    # 1. Clamp to [0.5, 3.0]
    clamped_mult = round(max(0.5, min(3.0, float(raw_multiplier))), 3)

    # 2. Check confidence
    if confidence < 0.5:
        return 1.0, confidence, [], "Guardrail triggered: confidence below 0.5 threshold; multiplier reset to 1.0"

    # 3. Check citation validity
    valid_citations = [sid for sid in cited_signal_ids if sid in valid_signal_ids]
    if not valid_citations:
        return 1.0, confidence, [], "Guardrail triggered: no valid active signal ID cited; multiplier reset to 1.0"

    return clamped_mult, confidence, valid_citations, "Valid signal-cited adjustment"


async def fetch_sim_control_signals(sim_control_url: Optional[str] = None, timeout: float = 1.0) -> List[Dict[str, Any]]:
    """Fetch active epidemiological and infrastructure signals from sim-control GET /signals."""
    settings = get_settings()
    base_url = (sim_control_url or settings.SIM_CONTROL_URL or "http://sim-control:8100").rstrip("/")
    url = f"{base_url}/signals"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        logger.debug(f"Could not fetch signals from sim-control ({url}): {e}")

    return []


async def evaluate_context_multiplier(
    facility_id: str,
    drug_code: str,
    baseline_rate: float,
    recent_14_day_series: List[float],
    active_signals: List[Dict[str, Any]],
    current_date: Optional[date] = None,
    genai_url: Optional[str] = None,
    timeout: float = 0.5,
) -> Dict[str, Any]:
    """Evaluate context multiplier for facility x drug.
    
    CRITICAL RULE: Only call the LLM when at least one relevant signal exists.
    When no relevant signal is present, make ZERO LLM calls and return 1.0 immediately.
    """
    global _genai_offline_until

    relevant_signals = find_relevant_signals(
        facility_id=facility_id,
        drug_code=drug_code,
        active_signals=active_signals,
        current_date=current_date,
    )

    valid_signal_ids = {s.get("id") or s.get("signal_id") for s in relevant_signals if s.get("id") or s.get("signal_id")}

    # Path 1: Zero relevant signals -> ZERO LLM calls
    if not relevant_signals:
        return {
            "multiplier": 1.0,
            "confidence": 1.0,
            "signal_ids": [],
            "reasoning": "Normal seasonal baseline; no active epidemiological alerts.",
            "llm_called": False,
        }

    # Path 2: Relevant signal exists -> Query GenAI gateway prompt forecast_ctx_v1 (if not in offline backoff)
    settings = get_settings()
    base_genai = (genai_url or settings.GENAI_URL or "http://genai:8000").rstrip("/")
    complete_url = f"{base_genai}/llm/complete"

    if time.time() >= _genai_offline_until:
        payload = {
            "purpose": "forecast_multiplier",
            "prompt_id": "forecast_ctx",
            "version": 1,
            "input": {
                "facility": facility_id,
                "drug": drug_code,
                "baseline_rate": baseline_rate,
                "recent_14_day_series": recent_14_day_series,
                "relevant_signals": relevant_signals,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(complete_url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    out = data.get("output", {})
                    raw_mult = float(out.get("multiplier", 1.0))
                    raw_conf = float(out.get("confidence", 0.0))
                    cited_ids = list(out.get("signal_ids", []))
                    raw_reason = str(out.get("reasoning", "LLM context adjustment"))

                    # Apply code guardrails
                    final_mult, final_conf, final_signals, guard_note = apply_guardrails(
                        raw_multiplier=raw_mult,
                        confidence=raw_conf,
                        cited_signal_ids=cited_ids,
                        valid_signal_ids=valid_signal_ids,
                    )

                    reason = raw_reason if final_mult != 1.0 or not cited_ids else f"{raw_reason} ({guard_note})"

                    return {
                        "multiplier": final_mult,
                        "confidence": final_conf,
                        "signal_ids": final_signals,
                        "reasoning": reason,
                        "llm_called": True,
                    }
        except Exception as e:
            _genai_offline_until = time.time() + 10.0
            logger.debug(f"GenAI gateway call failed ({e}); activating deterministic signal fallback")

    # Path 3: Deterministic Fallback if GenAI is unreachable
    # Pick the most relevant active signal and compute its deterministic multiplier
    best_sig = None
    best_mult = 1.0

    for s in relevant_signals:
        mults = s.get("multipliers", {})
        m_val = float(mults.get(drug_code, s.get("multiplier", 1.0)))
        if abs(m_val - 1.0) > abs(best_mult - 1.0):
            best_mult = m_val
            best_sig = s

    if best_sig and best_mult != 1.0:
        sig_id = best_sig.get("id") or best_sig.get("signal_id")
        clamped_mult = round(max(0.5, min(3.0, best_mult)), 3)
        reason = f"Active {best_sig.get('type', 'epidemiological')} alert ({sig_id}): {best_sig.get('text', 'Demand increase')} shifts {drug_code} consumption at {facility_id}."
        return {
            "multiplier": clamped_mult,
            "confidence": 0.95,
            "signal_ids": [sig_id],
            "reasoning": reason,
            "llm_called": False,
        }

    return {
        "multiplier": 1.0,
        "confidence": 1.0,
        "signal_ids": [],
        "reasoning": "Normal seasonal baseline; no active epidemiological alerts.",
        "llm_called": False,
    }
