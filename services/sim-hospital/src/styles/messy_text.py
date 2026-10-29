"""H4 messy handwritten register text with typos and bad_data scenario anomalies."""

from datetime import datetime
from typing import Any, Dict, List


def generate_messy_register_note(
    inventory: List[Dict[str, Any]],
    current_time: datetime,
    bad_data_active: bool = False,
) -> str:
    """Generate messy physical register entry note with common clerical typos."""
    inv_map = {item["drug_code"]: item for item in inventory}

    ins_item = inv_map.get("INS-REG", {"quantity": 50, "expiry": "2026-11-19", "batch_no": "LOT-INS-H4-01"})
    pcm_item = inv_map.get("PCM-500", {"quantity": 300, "expiry": "2026-12-16", "batch_no": "LOT-PCM-H4-01"})
    ors_item = inv_map.get("ORS-20", {"quantity": 150, "expiry": "2027-01-30", "batch_no": "LOT-ORS-H4-01"})

    date_str = current_time.strftime("%d/%m/%Y")

    if bad_data_active:
        # Corrupted OCR text with quantity spike (10000) and year 1999
        return f"""DAILY STOCK REGISTER - HESARAGHATTA PHC
Date: {date_str}
Physical count taken at ILR & ambient rack:
---------------------------------------------------------
10000 inzulin reg 100iu vials b.no B-999 exp 14/08/1999
paracetmol 500mg tabs: {pcm_item['quantity']} tab b.no {pcm_item['batch_no']} exp {pcm_item['expiry']}
ors oral salt sachet: {ors_item['quantity']} pkt exp {ors_item['expiry']}
---------------------------------------------------------
ILR status: under repair / compressor defect
Checked by: Staff Nurse Lalitha K.
"""

    return f"""DAILY STOCK REGISTER - HESARAGHATTA PHC
Date: {date_str}
Physical count taken at ILR & ambient rack:
---------------------------------------------------------
inzulin reg 100iu: {ins_item['quantity']} vials b.no {ins_item['batch_no']} exp {ins_item['expiry']} (ILR under repair, temp rising)
paracetmol 500mg: {pcm_item['quantity']} tab b.no {pcm_item['batch_no']} exp {pcm_item['expiry']}
ors sachet 20.5g: {ors_item['quantity']} pkt b.no {ors_item['batch_no']} exp {ors_item['expiry']}
---------------------------------------------------------
ILR status: breakdown since 3 days
Signed: Staff Nurse Lalitha K.
"""

