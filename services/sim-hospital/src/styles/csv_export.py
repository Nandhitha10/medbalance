"""e-Aushadhi style CSV export for H2 with unit conversions and real-world irregularities."""

import csv
from datetime import date, datetime
import io
from typing import Any, Dict, List

DRUG_DISPLAY_MAP = {
    "INS-REG": "Inj. Insulin Regular 100 IU/ml",
    "OXY-10": "Inj. Oxytocin 10 IU/ml 1ml",
    "AMOX-500": "Amoxicillin Capsules IP 500mg",
    "PCM-500": "Paracetamol Tablets IP 500mg",
    "RL-500": "Ringer Lactate Infusion 500ml",
    "ORS-20": "Oral Rehydration Salts IP 20.5g",
    "IFA-W": "Iron and Folic Acid Tablets (WIFS Blue)",
    "MET-500": "Metformin Hydrochloride Tabs 500mg",
    "AML-5": "Amlodipine Tablets IP 5mg",
    "CEFT-1000": "Inj. Ceftriaxone Sodium 1g",
    "Td": "Tetanus and adult Diphtheria Vaccine",
    "ASV-10": "Anti Snake Venom Serum Polyvalent 10ml",
    "MOR-10": "Morphine Sulfate Tablets IP 10mg",
}


def _format_mmyyyy(iso_date_str: str) -> str:
    """Convert YYYY-MM-DD date to MM/YYYY format."""
    try:
        parts = iso_date_str.split("-")
        return f"{int(parts[1]):02d}/{parts[0]}"
    except Exception:
        return iso_date_str


def generate_stock_csv(inventory: List[Dict[str, Any]]) -> str:
    """Generate e-Aushadhi format CSV with strip conversions and occasional missing batch numbers."""
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["Drug Name", "Batch No", "Exp Date", "Qty", "Unit"])

    for idx, item in enumerate(inventory):
        drug_code = item["drug_code"]
        name = DRUG_DISPLAY_MAP.get(drug_code, drug_code)
        batch = item["batch_no"]
        qty = int(item["quantity"])
        exp_mmyyyy = _format_mmyyyy(item["expiry"])

        # Irregularity 1: Represent some tablet drugs as strips (1 strip = 10 tablets)
        if drug_code in ("PCM-500", "AMOX-500", "IFA-W", "MET-500") and qty >= 10:
            qty_val = qty // 10
            unit_val = "strip"
        elif drug_code in ("INS-REG", "CEFT-1000", "Td", "ASV-10"):
            qty_val = qty
            unit_val = "vial"
        elif drug_code == "OXY-10":
            qty_val = qty
            unit_val = "ampoule"
        elif drug_code == "ORS-20":
            qty_val = qty
            unit_val = "sachet"
        else:
            qty_val = qty
            unit_val = "tablet"

        # Irregularity 2: One row missing batch number (e-Aushadhi manual entry defect)
        if idx == 1:
            batch = ""

        writer.writerow([name, batch, exp_mmyyyy, qty_val, unit_val])

    return output.getvalue()
