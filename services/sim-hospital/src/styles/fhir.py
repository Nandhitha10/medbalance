"""FHIR R5 / R4 compliant InventoryReport generator for H1."""

from datetime import datetime
from typing import Any, Dict, List


DRUG_NAME_MAP = {
    "INS-REG": ("Insulin Regular 100 IU/ml", "vial"),
    "OXY-10": ("Oxytocin Injection 10 IU", "ampoule"),
    "AMOX-500": ("Amoxicillin 500mg", "tablet"),
    "PCM-500": ("Paracetamol 500mg", "tablet"),
    "RL-500": ("Ringer Lactate 500ml", "bottle"),
    "ORS-20": ("Oral Rehydration Salts 20.5g", "sachet"),
    "IFA-W": ("Iron Folic Acid (WIFS)", "tablet"),
    "MET-500": ("Metformin 500mg", "tablet"),
    "AML-5": ("Amlodipine 5mg", "tablet"),
    "CEFT-1000": ("Ceftriaxone Injection 1g", "vial"),
    "Td": ("Tetanus and Diphtheria Toxoid", "vial"),
    "ASV-10": ("Anti Snake Venom 10ml", "vial"),
    "MOR-10": ("Morphine Sulfate 10mg", "tablet"),
}


def generate_fhir_inventory_report(
    hospital_id: str,
    hospital_name: str,
    inventory: List[Dict[str, Any]],
    current_time: datetime,
) -> Dict[str, Any]:
    """Generate a standard FHIR InventoryReport resource."""
    today_str = current_time.strftime("%Y%m%d")
    report_id = f"rep-{hospital_id.lower()}-{today_str}"

    items_listing = []
    r4_items = []

    for lt in inventory:
        code = lt["drug_code"]
        name, unit = DRUG_NAME_MAP.get(code, (code, "unit"))

        listing_entry = {
            "item": {
                "concept": {
                    "coding": [
                        {
                            "system": "https://medbalance.mohfw.gov.in/drugs",
                            "code": code,
                            "display": name,
                        }
                    ]
                }
            },
            "lot": lt["batch_no"],
            "expiry": lt["expiry"],
            "quantity": {
                "value": lt["quantity"],
                "unit": unit,
            },
        }
        items_listing.append(listing_entry)

        # FHIR R4 item schema compatibility
        r4_items.append({
            "category": "medication",
            "quantity": lt["quantity"],
            "item": {
                "code": code,
                "display": name,
                "batch": lt["batch_no"],
                "expiry": lt["expiry"],
            },
        })

    return {
        "resourceType": "InventoryReport",
        "id": report_id,
        "status": "completed",
        "countType": "snapshot",
        "reportedDateTime": current_time.isoformat(),
        "reporter": {
            "reference": f"Location/SIM-{hospital_id.upper()}",
            "display": hospital_name,
        },
        "inventoryListing": items_listing,
        "item": r4_items,
    }
