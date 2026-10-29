"""Synthetic in-memory scale mode generator for 40 facilities across 5 taluks."""

from datetime import date, timedelta
import random
from typing import Any, Dict, List, Tuple


TALUK_CONFIGS = [
    {"name": "Bengaluru North", "code": "BN", "center_lat": 13.080, "center_lon": 77.560},
    {"name": "Bengaluru South", "code": "BS", "center_lat": 12.925, "center_lon": 77.590},
    {"name": "Anekal", "code": "AK", "center_lat": 12.710, "center_lon": 77.695},
    {"name": "Yelahanka", "code": "YH", "center_lat": 13.110, "center_lon": 77.610},
    {"name": "Bengaluru East", "code": "BE", "center_lat": 12.975, "center_lon": 77.710},
]

CANONICAL_DRUGS = [
    {"code": "INS-REG", "name": "Insulin Regular", "category": "V", "unit": "vial", "pack_size": 1, "storage_condition": "cold_chain", "min_residual_days": 10, "unit_cost_inr": 145.50},
    {"code": "OXY-10", "name": "Oxytocin Injection", "category": "V", "unit": "ampoule", "pack_size": 5, "storage_condition": "cold_chain", "min_residual_days": 14, "unit_cost_inr": 28.00},
    {"code": "ASV-10", "name": "Anti-Snake Venom", "category": "V", "unit": "vial", "pack_size": 1, "storage_condition": "cold_chain", "min_residual_days": 30, "unit_cost_inr": 450.00},
    {"code": "TD-VAC", "name": "Tetanus-Diphtheria Vaccine", "category": "E", "unit": "vial", "pack_size": 10, "storage_condition": "cold_chain", "min_residual_days": 45, "unit_cost_inr": 12.50},
    {"code": "CEFT-1000", "name": "Ceftriaxone 1g", "category": "E", "unit": "vial", "pack_size": 1, "storage_condition": "ambient", "min_residual_days": 21, "unit_cost_inr": 85.00},
    {"code": "AMOX-500", "name": "Amoxicillin 500mg", "category": "E", "unit": "capsule", "pack_size": 10, "storage_condition": "ambient", "min_residual_days": 30, "unit_cost_inr": 4.50},
    {"code": "MET-500", "name": "Metformin 500mg", "category": "E", "unit": "tablet", "pack_size": 10, "storage_condition": "ambient", "min_residual_days": 30, "unit_cost_inr": 2.20},
    {"code": "AML-5", "name": "Amlodipine 5mg", "category": "E", "unit": "tablet", "pack_size": 10, "storage_condition": "ambient", "min_residual_days": 30, "unit_cost_inr": 1.80},
    {"code": "PARA-500", "name": "Paracetamol 500mg", "category": "E", "unit": "tablet", "pack_size": 10, "storage_condition": "ambient", "min_residual_days": 30, "unit_cost_inr": 1.20},
    {"code": "RL-500", "name": "Ringer Lactate 500ml", "category": "E", "unit": "bottle", "pack_size": 1, "storage_condition": "ambient", "min_residual_days": 30, "unit_cost_inr": 35.00},
    {"code": "ORS-20", "name": "Oral Rehydration Salts", "category": "N", "unit": "sachet", "pack_size": 1, "storage_condition": "ambient", "min_residual_days": 30, "unit_cost_inr": 18.00},
    {"code": "IFA-W", "name": "Iron Folic Acid", "category": "N", "unit": "tablet", "pack_size": 100, "storage_condition": "ambient", "min_residual_days": 45, "unit_cost_inr": 0.45},
    {"code": "MOR-10", "name": "Morphine 10mg", "category": "V", "unit": "tablet", "pack_size": 10, "storage_condition": "ambient", "min_residual_days": 60, "unit_cost_inr": 8.00, "is_controlled": True},
]


def generate_scale_district(scale: int = 40, seed: int = 42) -> Dict[str, Any]:
    """Generate in-memory synthetic district snapshot for 40 facilities across 5 taluks."""
    rng = random.Random(seed)
    today = date(2026, 11, 1)

    facilities: List[Dict[str, Any]] = []
    routes: List[Dict[str, Any]] = []
    lots: List[Dict[str, Any]] = []
    positions: List[Dict[str, Any]] = []
    forecasts: List[Dict[str, Any]] = []

    # 1. Generate 40 Facilities across 5 taluks
    fac_counter = 1
    lot_counter = 1

    # Baseline daily rates by drug
    base_rates = {
        "INS-REG": 10.0, "OXY-10": 8.0, "ASV-10": 1.0, "TD-VAC": 5.0,
        "CEFT-1000": 12.0, "AMOX-500": 35.0, "MET-500": 45.0, "AML-5": 40.0,
        "PARA-500": 80.0, "RL-500": 20.0, "ORS-20": 25.0, "IFA-W": 60.0, "MOR-10": 2.0,
    }

    tier_multipliers = {"TH": 1.5, "CHC": 0.9, "PHC": 0.35}

    for taluk_idx, t_conf in enumerate(TALUK_CONFIGS):
        t_name = t_conf["name"]
        t_code = t_conf["code"]

        # 8 facilities per taluk: 1 TH, 2 CHCs, 5 PHCs
        levels = ["TH", "CHC", "CHC", "PHC", "PHC", "PHC", "PHC", "PHC"]
        for l_idx, lvl in enumerate(levels):
            fac_id = f"FAC-{t_code}-{lvl}{l_idx+1}"
            lat = round(t_conf["center_lat"] + rng.uniform(-0.035, 0.035), 4)
            lon = round(t_conf["center_lon"] + rng.uniform(-0.035, 0.035), 4)
            has_cold = True if lvl in ("TH", "CHC") else (rng.random() > 0.4)

            fac_record = {
                "id": fac_id,
                "name": f"SIM-{lvl} {t_name} #{l_idx+1}",
                "level": lvl,
                "tier": lvl,
                "taluk": t_name,
                "latitude": lat,
                "longitude": lon,
                "cold_storage_available": has_cold,
                "cold_storage_ok": has_cold,
            }
            facilities.append(fac_record)

            # Generate forecasts, positions, and lots for this facility
            scale_fac = tier_multipliers[lvl]
            for drug in CANONICAL_DRUGS:
                dcode = drug["code"]
                rate = round(base_rates[dcode] * scale_fac * rng.uniform(0.8, 1.2), 1)

                forecasts.append({
                    "facility_id": fac_id,
                    "drug_code": dcode,
                    "effective_daily_rate": rate,
                })

                shortage = 0
                at_risk = 0

                # Stochastic shortage at ~15% of facility-drug pairs
                if rng.random() < 0.15 and not drug.get("is_controlled"):
                    shortage = int(rate * rng.randint(4, 12))

                # Stochastic at-risk lot at ~15% of facility-drug pairs
                if rng.random() < 0.15:
                    qty = rng.randint(20, 150)
                    days_exp = rng.randint(16, 32)
                    exp_date = today + timedelta(days=days_exp)

                    lots.append({
                        "id": lot_counter,
                        "facility_id": fac_id,
                        "drug_code": dcode,
                        "batch_no": f"LOT-{dcode}-{t_code}-{lot_counter:04d}",
                        "expiry": exp_date.isoformat(),
                        "quantity": qty,
                    })
                    lot_counter += 1
                    at_risk += qty

                positions.append({
                    "facility_id": fac_id,
                    "drug_code": dcode,
                    "daily_consumption_rate": rate,
                    "stock_on_hand": at_risk + (50 if shortage == 0 else 0),
                    "effective_stock": at_risk,
                    "at_risk_stock": at_risk,
                    "reserve": int(rate * 7),
                    "shortage": shortage,
                })

            fac_counter += 1

    # 2. Generate Routes (Intra-taluk mesh + Inter-taluk arterial highway routes)
    # Facilities grouped by taluk
    taluk_facs: Dict[str, List[Dict[str, Any]]] = {}
    for f in facilities:
        taluk_facs.setdefault(f["taluk"], []).append(f)

    route_id_counter = 1
    # Intra-taluk routes
    for t_name, f_list in taluk_facs.items():
        th = f_list[0]  # TH is the first
        for ch in f_list[1:]:
            dist = round(rng.uniform(6.0, 16.0), 1)
            time_h = round(dist / 22.0, 2)
            routes.append({
                "id": f"R-INTRA-{route_id_counter:04d}",
                "source_facility_id": th["id"],
                "destination_facility_id": ch["id"],
                "distance_km": dist,
                "transit_hours": time_h,
                "cold_chain_compliant": True,
                "status": "active",
            })
            route_id_counter += 1
            routes.append({
                "id": f"R-INTRA-{route_id_counter:04d}",
                "source_facility_id": ch["id"],
                "destination_facility_id": th["id"],
                "distance_km": dist,
                "transit_hours": time_h,
                "cold_chain_compliant": True,
                "status": "active",
            })
            route_id_counter += 1

    # Inter-taluk arterial routes between THs
    ths = [f_list[0] for f_list in taluk_facs.values()]
    for i in range(len(ths)):
        for j in range(i + 1, len(ths)):
            u, v = ths[i], ths[j]
            dist = round(rng.uniform(22.0, 48.0), 1)
            time_h = round(dist / 32.0, 2)
            routes.append({
                "id": f"R-INTER-{route_id_counter:04d}",
                "source_facility_id": u["id"],
                "destination_facility_id": v["id"],
                "distance_km": dist,
                "transit_hours": time_h,
                "cold_chain_compliant": True,
                "status": "active",
            })
            route_id_counter += 1
            routes.append({
                "id": f"R-INTER-{route_id_counter:04d}",
                "source_facility_id": v["id"],
                "destination_facility_id": u["id"],
                "distance_km": dist,
                "transit_hours": time_h,
                "cold_chain_compliant": True,
                "status": "active",
            })
            route_id_counter += 1

    # 3. Fleet
    vehicles = [
        {"id": "CV-01", "name": "Cold Van North", "cold_chain_capable": True, "is_active": True, "current_temp_c": 4.5},
        {"id": "CV-02", "name": "Cold Van South", "cold_chain_capable": True, "is_active": True, "current_temp_c": 4.8},
        {"id": "CV-03", "name": "Cold Van East", "cold_chain_capable": True, "is_active": True, "current_temp_c": 5.1},
        {"id": "CV-04", "name": "Cold Van Central", "cold_chain_capable": True, "is_active": True, "current_temp_c": 4.2},
        {"id": "AV-01", "name": "Ambient Van 1", "cold_chain_capable": False, "is_active": True, "current_temp_c": 24.0},
        {"id": "AV-02", "name": "Ambient Van 2", "cold_chain_capable": False, "is_active": True, "current_temp_c": 23.5},
        {"id": "AV-03", "name": "Ambient Van 3", "cold_chain_capable": False, "is_active": True, "current_temp_c": 24.2},
        {"id": "AV-04", "name": "Ambient Van 4", "cold_chain_capable": False, "is_active": True, "current_temp_c": 23.8},
    ]

    return {
        "today": today.isoformat(),
        "timestamp": "2026-11-01T08:00:00+05:30",
        "scale": scale,
        "facilities": facilities,
        "drugs": CANONICAL_DRUGS,
        "routes": routes,
        "vehicles": vehicles,
        "lots": lots,
        "positions": positions,
        "forecasts": forecasts,
        "snapshot_hash": f"scale-{scale}-seed-{seed}",
    }
