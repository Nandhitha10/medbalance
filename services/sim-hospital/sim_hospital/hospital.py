"""Simulated hospital node engine: local stock, FEFO dispensing, demand modeling, and reporting."""

import asyncio
from datetime import date, datetime
import json
import logging
import os
from pathlib import Path
import random
from typing import Any, Dict, List, Optional
from uuid import uuid4

from medbal_common.clock import KOLKATA_TZ, now as sim_now
from medbal_common.http import create_client
try:
    from sim_hospital.db import HospitalDB
    from sim_hospital.styles.chat import generate_chat_report
    from sim_hospital.styles.csv_export import generate_stock_csv
    from sim_hospital.styles.fhir import generate_fhir_inventory_report
    from sim_hospital.styles.messy_text import generate_messy_register_note
except ImportError:
    from src.db import HospitalDB
    from src.styles.chat import generate_chat_report
    from src.styles.csv_export import generate_stock_csv
    from src.styles.fhir import generate_fhir_inventory_report
    from src.styles.messy_text import generate_messy_register_note

logger = logging.getLogger(__name__)

# Base consumption rate parameters (daily Poisson lambda) per facility and drug
BASE_LAMBDAS = {
    "H1": {"INS-REG": 22.0, "OXY-10": 5.0, "AMOX-500": 35.0, "PCM-500": 80.0, "RL-500": 15.0},
    "H2": {"IFA-W": 40.0, "PCM-500": 60.0, "AMOX-500": 25.0, "MOR-10": 2.0, "ASV-10": 1.0, "INS-REG": 2.5},
    "H3": {"ORS-20": 2.0, "PCM-500": 15.0, "AMOX-500": 8.0, "MET-500": 12.0},
    "H4": {"INS-REG": 0.3, "PCM-500": 5.0, "ORS-20": 3.0},
}


def _find_hospital_seed_file(hospital_id: str) -> Path:
    """Find hospital JSON seed file across execution roots."""
    candidates = [
        Path.cwd() / "data" / "seed" / "hospitals" / f"{hospital_id.lower()}.json",
        Path(__file__).resolve().parent.parent.parent.parent / "data" / "seed" / "hospitals" / f"{hospital_id.lower()}.json",
        Path(f"/app/data/seed/hospitals/{hospital_id.lower()}.json"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


class HospitalNode:
    """Simulated hospital facility with independent inventory and reporting behavior."""

    def __init__(self, hospital_id: str = "H1", db_path: Optional[str] = None):
        self.hospital_id = hospital_id.upper()
        self.seed_file = _find_hospital_seed_file(self.hospital_id)
        
        # Load metadata and baseline lots from seed file
        self.config_data = self._read_seed_file()
        self.name = self.config_data.get("name", f"SIM-Hospital {self.hospital_id}")
        self.code = self.config_data.get("code", f"SIM-HOSP-{self.hospital_id}")
        self.level = self.config_data.get("level", "DH")
        self.adapter_type = self.config_data.get("adapter_type", "fhir")
        self.language = self.config_data.get("language", "en")
        self.cold_storage_ok = self.config_data.get("cold_storage_ok", True)

        # Database initialization
        if not db_path:
            db_path = os.getenv("SQLITE_DB_PATH", f"data/hospital_{self.hospital_id.lower()}.db")
            if db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.db = HospitalDB(db_path=db_path)
        self.reset(seed=42)

        self.current_sim_date: date = date(2026, 11, 1)
        self.current_day_index: int = 0
        self.rng = random.Random(42)

    def _read_seed_file(self) -> Dict[str, Any]:
        if self.seed_file.exists():
            with open(self.seed_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"hospital_id": self.hospital_id, "inventory": []}

    def reset(self, seed: int = 42) -> None:
        """Reload ground truth initial inventory and seed random generator."""
        self.rng = random.Random(seed)
        self.config_data = self._read_seed_file()
        initial_lots = self.config_data.get("inventory", [])
        self.db.load_initial_stock(initial_lots)
        self.current_day_index = 0
        self.current_sim_date = date(2026, 11, 1)

    def get_state(self) -> Dict[str, Any]:
        """Return ground truth local inventory for evaluation and diagnostics."""
        inventory = self.db.get_inventory()
        return {
            "hospital_id": self.hospital_id,
            "name": self.name,
            "stock_items_count": len(inventory),
            "last_synced_at": sim_now().isoformat(),
            "pending_transfers_in": 0,
            "pending_transfers_out": 0,
            "inventory": inventory,
        }

    def draw_poisson_demand(self, lam: float) -> int:
        """Deterministic Poisson random variate generator using Knuth algorithm."""
        if lam <= 0.0:
            return 0
        L = 2.718281828459045 ** (-lam)
        k = 0
        p = 1.0
        while p > L:
            k += 1
            p *= self.rng.random()
        return k - 1

    async def on_clock_tick(
        self,
        day_index: int,
        sim_date: date,
        demand_multipliers: Optional[Dict[str, float]] = None,
        bad_data_active: bool = False,
    ) -> Dict[str, Any]:
        """Execute daily dispensing, expire lots, and dispatch daily report."""
        self.current_day_index = day_index
        self.current_sim_date = sim_date
        date_str = sim_date.isoformat()

        multipliers = demand_multipliers or {}
        facility_lambdas = BASE_LAMBDAS.get(self.hospital_id, {})
        dispense_summary = {}

        # 1. Dispense demand per drug
        for drug_code, base_lam in facility_lambdas.items():
            mult = multipliers.get(drug_code, 1.0)
            effective_lam = base_lam * mult
            demand = self.draw_poisson_demand(effective_lam)
            dispensed, stockout = self.db.dispense_fefo(drug_code, demand, day_index, date_str)
            dispense_summary[drug_code] = {"demand": demand, "dispensed": dispensed, "stockout": stockout}

        # 2. Expire lots reaching or passing shelf-life
        expired_count = self.db.expire_lots(date_str)

        # 3. Automatic push report for chat (H3) and text (H4)
        await self._dispatch_daily_report(sim_date, bad_data_active=bad_data_active)

        return {
            "day_index": day_index,
            "date": date_str,
            "dispensed": dispense_summary,
            "expired_lots_count": expired_count,
        }

    async def _dispatch_daily_report(self, sim_date: date, bad_data_active: bool = False) -> None:
        """Send daily inventory stock reports to ingest-ai for chat and text styles."""
        ingest_url = os.getenv("INGEST_AI_URL", "http://ingest-ai:8002")
        now_dt = datetime.combine(sim_date, datetime.min.time(), tzinfo=KOLKATA_TZ)
        inventory = self.db.get_inventory()

        if self.adapter_type == "chat":
            chat_msg = generate_chat_report(inventory, now_dt, seed=self.current_day_index)
            payload = {"text": chat_msg, "source_type": "chat", "facility_code": self.hospital_id}
            async with create_client(timeout=1.0) as client:
                try:
                    await client.post(f"{ingest_url}/ingest/{self.hospital_id}", json=payload)
                except Exception as exc:
                    logger.debug(f"Chat report post notice: {exc}")

        elif self.adapter_type == "text":
            text_note = generate_messy_register_note(inventory, now_dt, bad_data_active=bad_data_active)
            payload = {"text": text_note, "source_type": "text", "facility_code": self.hospital_id}
            async with create_client(timeout=1.0) as client:
                try:
                    await client.post(f"{ingest_url}/ingest/{self.hospital_id}", json=payload)
                except Exception as exc:
                    logger.debug(f"Text report post notice: {exc}")

    def render_fhir_report(self) -> Dict[str, Any]:
        """Render FHIR InventoryReport for H1."""
        inventory = self.db.get_inventory()
        now_dt = datetime.combine(self.current_sim_date, datetime.min.time(), tzinfo=KOLKATA_TZ)
        return generate_fhir_inventory_report(
            hospital_id=self.hospital_id,
            hospital_name=self.name,
            inventory=inventory,
            current_time=now_dt,
        )

    def render_csv_export(self) -> str:
        """Render e-Aushadhi CSV for H2."""
        inventory = self.db.get_inventory()
        return generate_stock_csv(inventory)
