"""H3 Kannada + English informal chat stock reports (15 template variants)."""

from datetime import datetime
import random
from typing import Any, Dict, List, Optional


CHAT_TEMPLATES = [
    # Variant 1
    "ನಮಸ್ಕಾರ / Hello sir, Yelahanka CHC stock update for {date}: ORS {ors_qty} sachets (exp {ors_exp}), Paracetamol {pcm_qty} tabs (exp {pcm_exp}). ಇನ್ಸುಲಿನ್ ಇಲ್ಲ (no insulin in stock). Please arrange emergency supply.",
    # Variant 2
    "Sir YLH CHC pharmacy report: PCM 500mg {pcm_qty} nos, ORS {ors_qty} pkt exp {ors_exp}, Amoxicillin {amx_qty} tabs. Stock very low, OPD rush ಜಾಸ್ತಿ ಇದೆ.",
    # Variant 3
    "Emergency notice: Dengue cases increasing in taluk. ORS packet {ors_qty} only available. ಪ್ಯಾರಸಿಟಮಾಲ್ {pcm_qty} strips left. Urgent requirement sir.",
    # Variant 4
    "CHC Yelahanka daily stock: ORS {ors_qty} pkt, Amoxy 500 {amx_qty} tabs, PCM {pcm_qty} tabs. Metformin {met_qty}. ಇನ್ಸುಲಿನ್ ಸ್ಟಾಕ್ ಇಲ್ಲ (zero insulin).",
    # Variant 5
    "Sir, today count at pharmacy: ORS-{ors_qty} sachets exp {ors_exp}, PCM-{pcm_qty} nos exp {pcm_exp}. Kindly send indent.",
    # Variant 6
    "Good morning sir, Yelahanka store report: PCM {pcm_qty} tablets, Amoxy {amx_qty} caps, ORS {ors_qty} sachets. ದಯವಿಟ್ಟು ಬೇಗ ಕಳುಹಿಸಿ (please send soon).",
    # Variant 7
    "Stock status YLH: ORS count {ors_qty} pkt exp {ors_exp}. PCM 500mg {pcm_qty} tabs exp {pcm_exp}. Diarrhea cases high, ORS shortage imminent.",
    # Variant 8
    "Yelahanka CHC indent request: ORS balance {ors_qty} pkt only. PCM balance {pcm_qty} nos. No regular insulin available.",
    # Variant 9
    "Sir, Yelahanka daily register: ORS {ors_qty} pkt, Paracetamol {pcm_qty} tab, Amoxycillin {amx_qty} tab. ಎಲ್ಲವೂ ಮುಗಿಯುತ್ತಿದೆ (everything is getting over).",
    # Variant 10
    "Yelahanka CHC stock alert: ORS {ors_qty} packets expiring on {ors_exp}, PCM {pcm_qty} nos expiring {pcm_exp}. Fever cases heavy today.",
    # Variant 11
    "YLH CHC daily update: ORS {ors_qty} sachet, PCM {pcm_qty} tabs, Metformin {met_qty} tabs. ಇನ್ಸುಲಿನ್ ರೆಗ್ಯುಲರ್ 0 vials.",
    # Variant 12
    "Sir please note, Yelahanka CHC ORS {ors_qty} pkt balance today {date}. PCM {pcm_qty} tablets left. Kindly approve transfer.",
    # Variant 13
    "Yelahanka CHC evening stock check: ORS={ors_qty}, PCM={pcm_qty}, AMOX={amx_qty}. ಮಳೆಗಾಲದ ರೋಗಗಳು ಹೆಚ್ಚಾಗಿವೆ (monsoon illnesses increased).",
    # Variant 14
    "Sir, YLH CHC stock count on {date}: ORS {ors_qty} packets (LOT: {ors_batch}), PCM {pcm_qty} tabs (LOT: {pcm_batch}). Need replenishment.",
    # Variant 15
    "Yelahanka Community Health Centre daily log: ORS {ors_qty} pkt, PCM {pcm_qty} tabs. ಇಂದಿನ ಸ್ಟಾಕ್ ವರದಿ (today's stock report).",
]


def _format_short_date(iso_date_str: str) -> str:
    """Format date as DD/MM."""
    try:
        parts = iso_date_str.split("-")
        return f"{int(parts[2]):02d}/{int(parts[1]):02d}"
    except Exception:
        return iso_date_str


def generate_chat_report(
    inventory: List[Dict[str, Any]],
    current_time: datetime,
    seed: Optional[int] = None,
) -> str:
    """Generate informal bilingual chat report using a 15-template variant bank."""
    rng = random.Random(seed) if seed is not None else random

    inv_map = {item["drug_code"]: item for item in inventory}

    ors_item = inv_map.get("ORS-20", {"quantity": 0, "expiry": "2026-12-06", "batch_no": "LOT-ORS-01"})
    pcm_item = inv_map.get("PCM-500", {"quantity": 0, "expiry": "2026-12-21", "batch_no": "LOT-PCM-01"})
    amx_item = inv_map.get("AMOX-500", {"quantity": 0, "expiry": "2026-12-11", "batch_no": "LOT-AMX-01"})
    met_item = inv_map.get("MET-500", {"quantity": 0, "expiry": "2027-01-30", "batch_no": "LOT-MET-01"})

    template = rng.choice(CHAT_TEMPLATES)
    return template.format(
        date=current_time.strftime("%d/%m"),
        ors_qty=ors_item["quantity"],
        ors_exp=_format_short_date(str(ors_item["expiry"])),
        ors_batch=ors_item["batch_no"],
        pcm_qty=pcm_item["quantity"],
        pcm_exp=_format_short_date(str(pcm_item["expiry"])),
        pcm_batch=pcm_item["batch_no"],
        amx_qty=amx_item["quantity"],
        met_qty=met_item["quantity"],
    )
