"""Generate 10 golden raw reports per format (FHIR, CSV, Chat, Text)."""

from datetime import datetime, timedelta
import json
from pathlib import Path
import random
import sys

sys.path.insert(0, "services/sim-hospital")

from sim_hospital.styles.fhir import generate_fhir_inventory_report
from sim_hospital.styles.csv_export import generate_stock_csv
from sim_hospital.styles.chat import generate_chat_report
from sim_hospital.styles.messy_text import generate_messy_register_note


def main():
    base_dir = Path("evals/golden/raw")
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "fhir").mkdir(exist_ok=True)
    (base_dir / "csv").mkdir(exist_ok=True)
    (base_dir / "chat").mkdir(exist_ok=True)
    (base_dir / "text").mkdir(exist_ok=True)

    start_date = datetime(2026, 11, 1, 8, 0, 0)

    # 1. Generate 10 FHIR reports
    with open("data/seed/hospitals/h1.json", "r", encoding="utf-8") as f:
        h1_data = json.load(f)

    for i in range(1, 11):
        dt = start_date + timedelta(days=i - 1)
        # Add slight variations to inventory
        inv = []
        for it in h1_data["inventory"]:
            item_copy = dict(it)
            item_copy["quantity"] = max(1, item_copy["quantity"] + random.randint(-5, 10))
            inv.append(item_copy)

        report = generate_fhir_inventory_report(
            hospital_id="H1",
            hospital_name="SIM-DH Jayanagar",
            inventory=inv,
            current_time=dt,
        )
        out_path = base_dir / "fhir" / f"report_{i:02d}.json"
        with open(out_path, "w", encoding="utf-8") as f_out:
            json.dump(report, f_out, indent=2)

    # 2. Generate 10 CSV reports
    with open("data/seed/hospitals/h2.json", "r", encoding="utf-8") as f:
        h2_data = json.load(f)

    for i in range(1, 11):
        inv = []
        for it in h2_data["inventory"]:
            item_copy = dict(it)
            item_copy["quantity"] = max(10, item_copy["quantity"] + random.randint(-100, 200))
            inv.append(item_copy)

        csv_content = generate_stock_csv(inv)
        out_path = base_dir / "csv" / f"report_{i:02d}.csv"
        with open(out_path, "w", encoding="utf-8") as f_out:
            f_out.write(csv_content)

    # 3. Generate 10 Chat reports
    with open("data/seed/hospitals/h3.json", "r", encoding="utf-8") as f:
        h3_data = json.load(f)

    for i in range(1, 11):
        dt = start_date + timedelta(days=i - 1)
        chat_content = generate_chat_report(
            inventory=h3_data["inventory"],
            current_time=dt,
            seed=42 + i,
        )
        out_path = base_dir / "chat" / f"report_{i:02d}.txt"
        with open(out_path, "w", encoding="utf-8") as f_out:
            f_out.write(chat_content)

    # 4. Generate 10 Text reports (including bad_data anomalies for some)
    with open("data/seed/hospitals/h4.json", "r", encoding="utf-8") as f:
        h4_data = json.load(f)

    for i in range(1, 11):
        dt = start_date + timedelta(days=i - 1)
        bad_data = (i in (3, 7))  # days 3 and 7 simulate bad_data
        note = generate_messy_register_note(
            inventory=h4_data["inventory"],
            current_time=dt,
            bad_data_active=bad_data,
        )
        out_path = base_dir / "text" / f"report_{i:02d}.txt"
        with open(out_path, "w", encoding="utf-8") as f_out:
            f_out.write(note)

    print("Generated 40 golden raw reports successfully in evals/golden/raw/")


if __name__ == "__main__":
    main()
