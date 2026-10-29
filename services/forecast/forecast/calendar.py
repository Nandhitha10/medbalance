"""Static Epidemiological and Seasonal Calendar for District Health Demand."""

from datetime import date
from typing import Any, Dict, List


SEASONAL_CALENDAR_EVENTS: List[Dict[str, Any]] = [
    {
        "id": "SIG-CAL-DENGUE-POSTMONSOON",
        "name": "Post-Monsoon Vector-Borne & Dengue Transmission Window",
        "start_month": 9,
        "start_day": 1,
        "end_month": 11,
        "end_day": 30,
        "drugs_affected": ["ORS-20", "PCM-500"],
        "facility": "ALL",
        "type": "SEASONAL_CLIMATE",
        "multiplier": 1.25,
        "text": "Karnataka State Epidemiological Advisory: Post-monsoon mosquito breeding and vector-borne dengue transmission surge",
    },
    {
        "id": "SIG-CAL-DIWALI-FESTIVAL",
        "name": "Deepavali Festival & Winter Air Inversion",
        "start_month": 10,
        "start_day": 20,
        "end_month": 11,
        "end_day": 10,
        "drugs_affected": ["SALB-100"],
        "facility": "ALL",
        "type": "FESTIVAL_ENVIRONMENTAL",
        "multiplier": 1.30,
        "text": "Urban Environmental Health Advisory: Seasonal air quality degradation and festival fireworks exacerbating bronchospasm",
    },
    {
        "id": "SIG-CAL-WINTER-RESPIRATORY",
        "name": "Winter Upper Respiratory Infection Window",
        "start_month": 12,
        "start_day": 1,
        "end_month": 2,
        "end_day": 28,
        "drugs_affected": ["AMOX-500", "AZI-500", "PCM-500"],
        "facility": "ALL",
        "type": "SEASONAL_CLIMATE",
        "multiplier": 1.20,
        "text": "IDSP Seasonal Bulletin: Winter temperature drops leading to seasonal spike in acute respiratory infections",
    },
]


def get_calendar_signals(current_date: date) -> List[Dict[str, Any]]:
    """Return active calendar-driven seasonal and environmental signals for current date."""
    active_signals = []
    m, d = current_date.month, current_date.day

    for evt in SEASONAL_CALENDAR_EVENTS:
        sm, sd = evt["start_month"], evt["start_day"]
        em, ed = evt["end_month"], evt["end_day"]

        is_active = False
        if sm <= em:
            if (m > sm or (m == sm and d >= sd)) and (m < em or (m == em and d <= ed)):
                is_active = True
        else:
            # Spans year end (e.g. Dec to Feb)
            if (m > sm or (m == sm and d >= sd)) or (m < em or (m == em and d <= ed)):
                is_active = True

        if is_active:
            sig = dict(evt)
            sig["effective_from"] = current_date.isoformat()
            active_signals.append(sig)

    return active_signals

