"""Inventory positions computation reusing medbal_common.fefo."""

from datetime import date
from typing import Any, Dict, List, Optional
from medbal_common.fefo import PositionResult, calculate_fefo_position


def compute_positions_for_snapshot(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Compute FEFO position read-model for all facility × drug combinations in snapshot."""
    today_str = snapshot.get("today", "2026-11-01")
    today = date.fromisoformat(today_str) if isinstance(today_str, str) else today_str

    facilities = snapshot.get("facilities", [])
    drugs = snapshot.get("drugs", [])
    lots = snapshot.get("lots", [])
    forecasts = {
        (fc["facility_id"], fc["drug_code"]): float(fc.get("effective_daily_rate", 0.0))
        for fc in snapshot.get("forecasts", [])
    }
    policies = {
        (p["facility_id"], p["drug_code"]): p
        for p in snapshot.get("policies", [])
    }

    # Group lots by (facility_id, drug_code)
    lots_by_fac_drug: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for lt in lots:
        key = (lt["facility_id"], lt["drug_code"])
        if key not in lots_by_fac_drug:
            lots_by_fac_drug[key] = []
        lots_by_fac_drug[key].append(lt)

    results: List[Dict[str, Any]] = []

    for fac in facilities:
        fac_id = fac["id"]
        for drug in drugs:
            dcode = drug["code"]
            fac_lots = lots_by_fac_drug.get((fac_id, dcode), [])

            rate = forecasts.get((fac_id, dcode), 0.0)
            pol = policies.get((fac_id, dcode), {})
            min_res = int(pol.get("min_reserve_days", fac.get("min_reserve_days", 7)))
            target_days = int(pol.get("target_days", 21))
            lead_time = int(pol.get("lead_time_days", 3))

            pos: PositionResult = calculate_fefo_position(
                facility_id=fac_id,
                drug_code=dcode,
                lots=fac_lots,
                daily_rate=rate,
                today=today,
                min_reserve_days=min_res,
                target_days=target_days,
                lead_time_days=lead_time,
            )

            results.append({
                "facility_id": pos.facility_id,
                "drug_code": pos.drug_code,
                "daily_consumption_rate": pos.daily_consumption_rate,
                "stock_on_hand": pos.stock_on_hand,
                "effective_stock": pos.effective_stock,
                "at_risk_stock": pos.at_risk_stock,
                "reserve": pos.reserve,
                "shortage": pos.shortage,
                "lots": [
                    {
                        "batch_no": l.batch_no,
                        "expiry": l.expiry.isoformat(),
                        "quantity": l.quantity,
                        "days_to_expiry": l.days_to_expiry,
                        "effective_quantity": l.effective_quantity,
                        "at_risk_quantity": l.at_risk_quantity,
                        "reserved_quantity": l.reserved_quantity,
                        "transferable_quantity": l.transferable_quantity,
                    }
                    for l in pos.lots
                ],
            })

    return results

