#!/usr/bin/env python3
"""Deterministic Seed Generator for MedBalance-Q (Bengaluru Urban District).

Generates:
1. db/init/002_seed.sql (Full PostgreSQL seed file)
2. data/seed/hospitals/h1.json .. h4.json (Simulated hospital node initial states)
"""

import argparse
from datetime import date, datetime, timedelta
import json
import math
from pathlib import Path
import random
from typing import Any, Dict, List
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_SEED_DIR = ROOT_DIR / "data" / "seed"
DB_INIT_DIR = ROOT_DIR / "db" / "init"
HOSPITALS_DIR = DATA_SEED_DIR / "hospitals"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance between two points on the earth in km."""
    R = 6371.0  # Earth radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def sample_poisson(rng: random.Random, lam: float) -> int:
    """Sample a Poisson random variable deterministically."""
    if lam <= 0:
        return 0
    if lam < 30.0:
        L = math.exp(-lam)
        k = 0
        p = 1.0
        while p > L:
            k += 1
            p *= rng.random()
        return max(0, k - 1)
    # Gaussian approximation for larger lambda
    val = rng.gauss(lam, math.sqrt(lam))
    return max(0, int(round(val)))


def escape_sql(val: Any) -> str:
    """Format Python values into valid PostgreSQL literals."""
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, (date, datetime)):
        return f"'{val.isoformat()}'"
    s = str(val).replace("'", "''")
    return f"'{s}'"


def load_yaml(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def generate_seed(seed_val: int = 42) -> None:
    rng = random.Random(seed_val)

    # 1. Load YAML inputs
    district_cfg = load_yaml(DATA_SEED_DIR / "district.yaml")
    drugs_cfg = load_yaml(DATA_SEED_DIR / "drugs.yaml")

    facilities = district_cfg["facilities"]
    vehicles = district_cfg["vehicles"]
    drugs = drugs_cfg["drugs"]

    anchor_date = date.fromisoformat(district_cfg["district"].get("anchor_date", "2026-11-01"))

    # Facility lookup
    fac_map = {f["id"]: f for f in facilities}
    drug_map = {d["code"]: d for d in drugs}

    # 2. Build SQL Statements
    sql_lines: List[str] = [
        "-- MedBalance-Q Deterministic District Seed Data",
        f"-- Deterministically generated with seed={seed_val}",
        "BEGIN;",
        "",
    ]

    # --- Facilities ---
    sql_lines.append("-- 1. Facilities")
    for f in facilities:
        sql = (
            "INSERT INTO facility (id, code, name, level, taluk, district, latitude, longitude, adapter_type, language, cold_storage_ok, cold_storage_note) "
            f"VALUES ({escape_sql(f['id'])}, {escape_sql(f['code'])}, {escape_sql(f['name'])}, {escape_sql(f['level'])}, "
            f"{escape_sql(f.get('taluk'))}, {escape_sql(district_cfg['district']['name'])}, {f['latitude']}, {f['longitude']}, "
            f"{escape_sql(f['adapter_type'])}, {escape_sql(f.get('language', 'en'))}, {escape_sql(f['cold_storage_ok'])}, {escape_sql(f.get('cold_storage_note'))}) "
            "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, cold_storage_ok = EXCLUDED.cold_storage_ok;"
        )
        sql_lines.append(sql)
    sql_lines.append("")

    # --- Drugs ---
    sql_lines.append("-- 2. Drugs")
    for d in drugs:
        sql = (
            "INSERT INTO drug (code, name, category, unit, pack_size, cold_chain, min_temp_c, max_temp_c, unit_cost_inr, min_residual_days, is_controlled) "
            f"VALUES ({escape_sql(d['code'])}, {escape_sql(d['name'])}, {escape_sql(d['category'])}, {escape_sql(d['unit'])}, "
            f"{d['pack_size']}, {escape_sql(d['cold_chain'])}, {escape_sql(d.get('min_temp_c'))}, {escape_sql(d.get('max_temp_c'))}, "
            f"{d['unit_cost_inr']}, {d['min_residual_days']}, {escape_sql(d.get('is_controlled', False))}) "
            "ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, unit_cost_inr = EXCLUDED.unit_cost_inr;"
        )
        sql_lines.append(sql)
    sql_lines.append("")

    # --- Drug Aliases ---
    sql_lines.append("-- 3. Drug Aliases")
    for d in drugs:
        for alias_obj in d.get("aliases", []):
            sql = (
                "INSERT INTO drug_alias (drug_code, alias, language, notes) "
                f"VALUES ({escape_sql(d['code'])}, {escape_sql(alias_obj['alias'])}, {escape_sql(alias_obj.get('language', 'en'))}, {escape_sql(alias_obj.get('notes'))});"
            )
            sql_lines.append(sql)
    sql_lines.append("")

    # --- Vehicles ---
    sql_lines.append("-- 4. Vehicles")
    for v in vehicles:
        sql = (
            "INSERT INTO vehicle (id, name, vehicle_type, cold_capable, is_active, cost_per_km_inr) "
            f"VALUES ({escape_sql(v['id'])}, {escape_sql(v['name'])}, {escape_sql(v['vehicle_type'])}, {escape_sql(v['cold_capable'])}, "
            f"{escape_sql(v.get('is_active', True))}, {v.get('cost_per_km_inr', 15.0)}) "
            "ON CONFLICT (id) DO UPDATE SET cold_capable = EXCLUDED.cold_capable;"
        )
        sql_lines.append(sql)
    sql_lines.append("")

    # --- Routes ---
    sql_lines.append("-- 5. Routes (all facility pairs: km = haversine x 1.3)")
    for f1 in facilities:
        for f2 in facilities:
            if f1["id"] == f2["id"]:
                continue
            dist_straight = haversine_km(f1["latitude"], f1["longitude"], f2["latitude"], f2["longitude"])
            km = round(dist_straight * 1.3, 2)
            # transit_days = ceil(km / 40 / 8h day) min 1 -> ceil(km / 320) min 1
            transit_days = max(1, math.ceil(km / (40.0 * 8.0)))
            transit_hours = round(max(0.5, km / 30.0), 2)
            cost_inr = round(km * 22.50, 2)
            # Cold capable when both endpoints can receive/send cold or cold van available
            cold_capable = True
            route_id = f"RTE-{f1['id']}-{f2['id']}"

            sql = (
                "INSERT INTO route (id, source_id, destination_id, distance_km, transit_days, transit_hours, cost_inr, cold_capable) "
                f"VALUES ({escape_sql(route_id)}, {escape_sql(f1['id'])}, {escape_sql(f2['id'])}, {km}, {transit_days}, {transit_hours}, {cost_inr}, {escape_sql(cold_capable)}) "
                "ON CONFLICT (id) DO UPDATE SET distance_km = EXCLUDED.distance_km, transit_hours = EXCLUDED.transit_hours;"
            )
            sql_lines.append(sql)
    sql_lines.append("")

    # --- Policies ---
    sql_lines.append("-- 6. Policies (facility x drug)")
    for f in facilities:
        level = f["level"]
        for d in drugs:
            if level == "PHC":
                min_reserve = 3
                target = 10
                max_stock = 30
                lead_time = 2
            elif level == "CHC":
                min_reserve = 5
                target = 14
                max_stock = 45
                lead_time = 2
            elif level == "TH":
                min_reserve = 7
                target = 21
                max_stock = 60
                lead_time = 3
            elif level == "DH":
                min_reserve = 7
                target = 21
                max_stock = 60
                lead_time = 3
            else:  # WH
                min_reserve = 14
                target = 45
                max_stock = 120
                lead_time = 5

            sql = (
                "INSERT INTO policy (facility_id, drug_code, min_reserve_days, target_days, max_stock_days, lead_time_days) "
                f"VALUES ({escape_sql(f['id'])}, {escape_sql(d['code'])}, {min_reserve}, {target}, {max_stock}, {lead_time}) "
                "ON CONFLICT (facility_id, drug_code) DO UPDATE SET min_reserve_days = EXCLUDED.min_reserve_days, target_days = EXCLUDED.target_days;"
            )
            sql_lines.append(sql)
    sql_lines.append("")

    # --- 90 Days Consumption Daily ---
    sql_lines.append("-- 7. 90-Day Consumption Daily (Poisson with weekly seasonality)")
    baseline_rates = {
        "INS-REG": 15.0,
        "OXY-10": 12.0,
        "ASV-10": 1.5,
        "TD-VAC": 8.0,
        "CEFT-1000": 18.0,
        "RL-500": 25.0,
        "ORS-20": 40.0,
        "PCM-500": 120.0,
        "AMOX-500": 45.0,
        "MET-500": 60.0,
        "AML-5": 50.0,
        "IFA-W": 80.0,
        "MOR-10": 3.0,
    }

    scale_factors = {
        "DH": 1.5,
        "TH": 1.2,
        "CHC": 0.8,
        "PHC": 0.3,
        "WH": 0.0,  # Warehouse holds buffer stock, no patient consumption
    }

    day_seasonality = [1.2, 1.1, 1.1, 1.0, 1.0, 0.8, 0.6]  # Mon=0 .. Sun=6

    for day_offset in range(90, 0, -1):
        curr_date = anchor_date - timedelta(days=day_offset)
        weekday = curr_date.weekday()
        season_factor = day_seasonality[weekday]

        for f in facilities:
            fac_scale = scale_factors.get(f["level"], 1.0)
            if fac_scale == 0.0:
                continue

            for d in drugs:
                base = baseline_rates.get(d["code"], 20.0)
                lam = base * fac_scale * season_factor
                qty = sample_poisson(rng, lam)

                sql = (
                    "INSERT INTO consumption_daily (facility_id, drug_code, date, quantity) "
                    f"VALUES ({escape_sql(f['id'])}, {escape_sql(d['code'])}, {escape_sql(curr_date)}, {qty}) "
                    "ON CONFLICT (facility_id, drug_code, date) DO UPDATE SET quantity = EXCLUDED.quantity;"
                )
                sql_lines.append(sql)
    sql_lines.append("")

    # --- Lots Engineered for the Story ---
    sql_lines.append("-- 8. Engineered Inventory Lots for Demo Story")

    lots_to_insert: List[Dict[str, Any]] = [
        # 1. H1 (SIM-DH Jayanagar): Near-zero insulin and oxytocin
        {
            "facility_id": "H1",
            "drug_code": "INS-REG",
            "batch_no": "LOT-INS-H1-01",
            "expiry": anchor_date + timedelta(days=20),
            "quantity": 2,  # Near-zero!
        },
        {
            "facility_id": "H1",
            "drug_code": "OXY-10",
            "batch_no": "LOT-OXY-H1-01",
            "expiry": anchor_date + timedelta(days=22),
            "quantity": 3,  # Near-zero!
        },
        {
            "facility_id": "H1",
            "drug_code": "AMOX-500",
            "batch_no": "LOT-AMX-H1-01",
            "expiry": anchor_date + timedelta(days=60),
            "quantity": 2000,
        },
        {
            "facility_id": "H1",
            "drug_code": "PCM-500",
            "batch_no": "LOT-PCM-H1-01",
            "expiry": anchor_date + timedelta(days=90),
            "quantity": 5000,
        },
        {
            "facility_id": "H1",
            "drug_code": "RL-500",
            "batch_no": "LOT-RL-H1-01",
            "expiry": anchor_date + timedelta(days=120),
            "quantity": 800,
        },

        # 2. H4 (SIM-PHC Hesaraghatta): 50-vial insulin lot expiring in ~18 days with tiny usage; cold_storage_ok=false
        {
            "facility_id": "H4",
            "drug_code": "INS-REG",
            "batch_no": "LOT-INS-H4-01",
            "expiry": anchor_date + timedelta(days=18),  # Expiring in exactly 18 days!
            "quantity": 50,  # 50 vials!
        },
        {
            "facility_id": "H4",
            "drug_code": "PCM-500",
            "batch_no": "LOT-PCM-H4-01",
            "expiry": anchor_date + timedelta(days=45),
            "quantity": 300,
        },
        {
            "facility_id": "H4",
            "drug_code": "ORS-20",
            "batch_no": "LOT-ORS-H4-01",
            "expiry": anchor_date + timedelta(days=90),
            "quantity": 150,
        },

        # 3. H2 (SIM-TGH Anekal): Over-stocked IFA, PCM, amoxicillin near expiry; 1 morphine lot (F6 demo)
        {
            "facility_id": "H2",
            "drug_code": "IFA-W",
            "batch_no": "LOT-IFA-H2-01",
            "expiry": anchor_date + timedelta(days=25),  # Near expiry!
            "quantity": 12000,  # Over-stocked!
        },
        {
            "facility_id": "H2",
            "drug_code": "PCM-500",
            "batch_no": "LOT-PCM-H2-01",
            "expiry": anchor_date + timedelta(days=20),  # Near expiry!
            "quantity": 8000,  # Over-stocked!
        },
        {
            "facility_id": "H2",
            "drug_code": "AMOX-500",
            "batch_no": "LOT-AMX-H2-01",
            "expiry": anchor_date + timedelta(days=22),  # Near expiry!
            "quantity": 3500,  # Over-stocked!
        },
        {
            "facility_id": "H2",
            "drug_code": "MOR-10",
            "batch_no": "LOT-MOR-H2-01",
            "expiry": anchor_date + timedelta(days=45),
            "quantity": 250,  # Morphine lot for F6 controlled drug check!
        },
        {
            "facility_id": "H2",
            "drug_code": "ASV-10",
            "batch_no": "LOT-ASV-H2-01",
            "expiry": anchor_date + timedelta(days=60),
            "quantity": 40,
        },

        # 4. H3 (SIM-CHC Yelahanka): Low ORS before dengue scenario
        {
            "facility_id": "H3",
            "drug_code": "ORS-20",
            "batch_no": "LOT-ORS-H3-01",
            "expiry": anchor_date + timedelta(days=35),
            "quantity": 15,  # Low ORS!
        },
        {
            "facility_id": "H3",
            "drug_code": "PCM-500",
            "batch_no": "LOT-PCM-H3-01",
            "expiry": anchor_date + timedelta(days=50),
            "quantity": 1500,
        },
        {
            "facility_id": "H3",
            "drug_code": "AMOX-500",
            "batch_no": "LOT-AMX-H3-01",
            "expiry": anchor_date + timedelta(days=40),
            "quantity": 600,
        },
        {
            "facility_id": "H3",
            "drug_code": "MET-500",
            "batch_no": "LOT-MET-H3-01",
            "expiry": anchor_date + timedelta(days=90),
            "quantity": 1200,
        },

        # 5. W0 (SIM District Drug Warehouse): Central buffers
        {
            "facility_id": "W0",
            "drug_code": "INS-REG",
            "batch_no": "LOT-INS-W0-01",
            "expiry": anchor_date + timedelta(days=180),
            "quantity": 500,
        },
        {
            "facility_id": "W0",
            "drug_code": "OXY-10",
            "batch_no": "LOT-OXY-W0-01",
            "expiry": anchor_date + timedelta(days=210),
            "quantity": 600,
        },
        {
            "facility_id": "W0",
            "drug_code": "ORS-20",
            "batch_no": "LOT-ORS-W0-01",
            "expiry": anchor_date + timedelta(days=300),
            "quantity": 10000,
        },
        {
            "facility_id": "W0",
            "drug_code": "ASV-10",
            "batch_no": "LOT-ASV-W0-01",
            "expiry": anchor_date + timedelta(days=360),
            "quantity": 300,
        },
        {
            "facility_id": "W0",
            "drug_code": "CEFT-1000",
            "batch_no": "LOT-CEF-W0-01",
            "expiry": anchor_date + timedelta(days=240),
            "quantity": 2500,
        },
    ]

    for lt in lots_to_insert:
        sql = (
            "INSERT INTO lot (facility_id, drug_code, batch_no, expiry, quantity) "
            f"VALUES ({escape_sql(lt['facility_id'])}, {escape_sql(lt['drug_code'])}, {escape_sql(lt['batch_no'])}, {escape_sql(lt['expiry'])}, {lt['quantity']}) "
            "ON CONFLICT (facility_id, drug_code, batch_no) DO UPDATE SET quantity = EXCLUDED.quantity, expiry = EXCLUDED.expiry;"
        )
        sql_lines.append(sql)
    sql_lines.append("")

    sql_lines.append("COMMIT;")

    # 3. Write db/init/002_seed.sql
    DB_INIT_DIR.mkdir(parents=True, exist_ok=True)
    seed_sql_path = DB_INIT_DIR / "002_seed.sql"
    with open(seed_sql_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sql_lines))
    print(f"Wrote {len(sql_lines)} lines to {seed_sql_path}")

    # 4. Write data/seed/hospitals/h1..h4.json
    HOSPITALS_DIR.mkdir(parents=True, exist_ok=True)
    for hosp_id in ["H1", "H2", "H3", "H4"]:
        fac = fac_map[hosp_id]
        hosp_lots = [
            {
                "drug_code": lt["drug_code"],
                "batch_no": lt["batch_no"],
                "expiry": lt["expiry"].isoformat(),
                "quantity": lt["quantity"],
            }
            for lt in lots_to_insert
            if lt["facility_id"] == hosp_id
        ]

        hosp_data = {
            "hospital_id": hosp_id,
            "code": fac["code"],
            "name": fac["name"],
            "level": fac["level"],
            "adapter_type": fac["adapter_type"],
            "language": fac["language"],
            "cold_storage_ok": fac["cold_storage_ok"],
            "cold_storage_note": fac.get("cold_storage_note"),
            "stock_items_count": len(hosp_lots),
            "inventory": hosp_lots,
        }

        hosp_json_path = HOSPITALS_DIR / f"{hosp_id.lower()}.json"
        with open(hosp_json_path, "w", encoding="utf-8") as f:
            json.dump(hosp_data, f, indent=2, ensure_ascii=False)
        print(f"Wrote {hosp_json_path}")


def main():
    parser = argparse.ArgumentParser(description="Deterministic Seed Generator for MedBalance-Q")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    generate_seed(seed_val=args.seed)


if __name__ == "__main__":
    main()
