"""Snapshot retrieval and in-memory indexing for optimizer."""

from datetime import date
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import httpx
from medbal_common.settings import get_settings

logger = logging.getLogger(__name__)


def find_snapshot_fixture() -> Path:
    candidates = [
        Path.cwd() / "contracts" / "fixtures" / "snapshot.json",
        Path(__file__).resolve().parent.parent.parent.parent / "contracts" / "fixtures" / "snapshot.json",
        Path("/app/contracts/fixtures/snapshot.json"),
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    return Path.cwd() / "contracts" / "fixtures" / "snapshot.json"


def load_fixture_snapshot() -> Dict[str, Any]:
    fixture_path = find_snapshot_fixture()
    if fixture_path.exists():
        with open(fixture_path, "r", encoding="utf-8") as f:
            return json.load(f)
    logger.warning("Snapshot fixture not found, returning minimal empty snapshot")
    return {
        "timestamp": "2026-11-01T08:00:00+05:30",
        "today": "2026-11-01",
        "facilities": [],
        "drugs": [],
        "routes": [],
        "vehicles": [],
        "lots": [],
        "positions": [],
        "forecasts": [],
        "policies": [],
        "snapshot_hash": "empty",
    }


async def fetch_snapshot(core_api_url: Optional[str] = None) -> Dict[str, Any]:
    """Fetch complete district snapshot from core-api or fallback to fixture."""
    settings = get_settings()
    base_url = core_api_url or settings.CORE_API_URL

    if base_url:
        endpoints = [f"{base_url}/snapshot", f"{base_url}/api/core/snapshot"]
        async with httpx.AsyncClient(timeout=0.5) as client:
            for url in endpoints:
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        logger.info(f"Successfully fetched snapshot from {url} (hash: {data.get('snapshot_hash')})")
                        return data
                except Exception as e:
                    logger.debug(f"Could not reach {url}: {e}")

    return load_fixture_snapshot()


class SnapshotIndex:
    """Indexed in-memory representation of the optimizer snapshot for O(1) query performance."""

    def __init__(self, raw: Dict[str, Any]) -> None:
        self.raw = raw
        today_val = raw.get("today", "2026-11-01")
        self.today: date = date.fromisoformat(today_val) if isinstance(today_val, str) else today_val

        self.facilities: Dict[str, Dict[str, Any]] = {
            f["id"]: f for f in raw.get("facilities", [])
        }
        self.drugs: Dict[str, Dict[str, Any]] = {
            d["code"]: d for d in raw.get("drugs", [])
        }
        self.routes: Dict[Tuple[str, str], Dict[str, Any]] = {
            (r["source_facility_id"], r["destination_facility_id"]): r
            for r in raw.get("routes", [])
        }
        self.vehicles: List[Dict[str, Any]] = raw.get("vehicles", [])

        # Index lots by (facility_id, drug_code) sorted ascending by expiry
        self.lots: List[Dict[str, Any]] = raw.get("lots", [])
        self.lots_by_facility_drug: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for lt in self.lots:
            key = (lt["facility_id"], lt["drug_code"])
            if key not in self.lots_by_facility_drug:
                self.lots_by_facility_drug[key] = []
            self.lots_by_facility_drug[key].append(lt)

        for key in self.lots_by_facility_drug:
            self.lots_by_facility_drug[key].sort(
                key=lambda x: date.fromisoformat(x["expiry"]) if isinstance(x["expiry"], str) else x["expiry"]
            )

        # Index positions by (facility_id, drug_code)
        self.positions: Dict[Tuple[str, str], Dict[str, Any]] = {
            (p["facility_id"], p["drug_code"]): p
            for p in raw.get("positions", [])
        }

        # Index forecasts by (facility_id, drug_code)
        self.forecasts: Dict[Tuple[str, str], float] = {
            (fc["facility_id"], fc["drug_code"]): float(fc.get("effective_daily_rate", 0.0))
            for fc in raw.get("forecasts", [])
        }

        # Index policies by (facility_id, drug_code)
        self.policies: Dict[Tuple[str, str], Dict[str, Any]] = {
            (p["facility_id"], p["drug_code"]): p
            for p in raw.get("policies", [])
        }

        self.snapshot_hash: str = raw.get("snapshot_hash", "")

    def get_route(self, src_id: str, dst_id: str) -> Optional[Dict[str, Any]]:
        return self.routes.get((src_id, dst_id))

    def get_drug(self, code: str) -> Optional[Dict[str, Any]]:
        return self.drugs.get(code)

    def get_facility(self, fac_id: str) -> Optional[Dict[str, Any]]:
        return self.facilities.get(fac_id)

    def get_daily_rate(self, fac_id: str, drug_code: str) -> float:
        rate = self.forecasts.get((fac_id, drug_code), 0.0)
        if rate <= 0.0:
            pos = self.positions.get((fac_id, drug_code))
            if pos:
                rate = float(pos.get("daily_consumption_rate", 0.0))
        return rate
