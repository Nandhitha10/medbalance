"""Scenario manager and IDSP-like epidemiological signal feed."""

import asyncio
from datetime import timedelta
import json
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from medbal_common.bus import get_redis_client
from src.clock import clock

logger = logging.getLogger(__name__)


class Scenario:
    def __init__(
        self,
        name: str,
        description: str,
        signal_type: str,
        facility_id: Optional[str] = None,
        taluk: Optional[str] = None,
        drugs_affected: Optional[List[str]] = None,
        multipliers: Optional[Dict[str, float]] = None,
        duration_days: int = 14,
        text: str = "",
        device_fault: Optional[Dict[str, Any]] = None,
        route_closure: Optional[str] = None,
    ):
        self.name = name
        self.description = description
        self.signal_type = signal_type
        self.facility_id = facility_id
        self.taluk = taluk or ("Yelahanka" if facility_id == "H3" else ("Anekal" if facility_id == "H2" else "Bengaluru South"))
        self.drugs_affected = drugs_affected or []
        self.multipliers = multipliers or {}
        self.duration_days = duration_days
        self.text = text
        self.device_fault = device_fault
        self.route_closure = route_closure

        self.active = False
        self.start_day = 0
        self.effective_from = ""
        self.effective_to = ""
        self.signal_id = f"SIG-{name.upper()}-01"


class ScenarioManager:
    """Manages simulation shocks, demand multipliers, device faults, and signal broadcasts."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.scenarios: Dict[str, Scenario] = {}
        self._init_scenarios()

    def _init_scenarios(self) -> None:
        self.scenarios = {
            "baseline": Scenario(
                name="baseline",
                description="Normal operations with baseline Poisson consumption and intact infrastructure",
                signal_type="BASELINE",
                text="Baseline operational state; standard seasonal demands active",
            ),
            "dengue_outbreak": Scenario(
                name="dengue_outbreak",
                description="Acute dengue & diarrheal surge in Yelahanka taluk affecting ORS and PCM at H3",
                signal_type="OUTBREAK",
                facility_id="H3",
                taluk="Yelahanka",
                drugs_affected=["ORS-20", "PCM-500"],
                multipliers={"ORS-20": 4.0, "PCM-500": 2.5},
                duration_days=14,
                text="IDSP Bulletin: Dengue and acute diarrheal disease cluster reported in Yelahanka taluk (H3)",
            ),
            "fridge_failure": Scenario(
                name="fridge_failure",
                description="Refrigeration compressor breakdown on cold transport van CV-02",
                signal_type="COLDCHAIN_EXCURSION",
                duration_days=3,
                text="Cold chain telemetry warning: CV-02 refrigeration unit temperature excursion above 8°C",
                device_fault={"vehicle_id": "CV-02", "device_id": "DEV-VEH-02", "fault": "EXCURSION", "temperature_c": 11.4},
            ),
            "bad_data": Scenario(
                name="bad_data",
                description="Corrupted OCR reading at Hesaraghatta PHC producing extreme spike and 1999 expiry",
                signal_type="DATA_ANOMALY",
                facility_id="H4",
                taluk="North",
                drugs_affected=["INS-REG"],
                duration_days=7,
                text="OCR parsing anomaly: extreme quantity spike (10000) and invalid century date (1999) from H4 register",
            ),
            "ilr_repaired": Scenario(
                name="ilr_repaired",
                description="Hesaraghatta PHC Ice-Lined Refrigerator successfully repaired by biomedical engineer",
                signal_type="FACILITY_UPDATE",
                facility_id="H4",
                taluk="North",
                duration_days=30,
                text="Biomedical engineering update: Ice-Lined Refrigerator at Hesaraghatta PHC (H4) repaired and verified",
            ),
            "road_closure": Scenario(
                name="road_closure",
                description="State Highway 9 bridge structural maintenance closing route RTE-H3-H4",
                signal_type="ROUTE_DISRUPTION",
                duration_days=5,
                route_closure="RTE-H3-H4",
                text="State Highway 9 bridge structural maintenance: Route RTE-H3-H4 transit suspended for heavy vehicles",
            ),
            "td_campaign": Scenario(
                name="td_campaign",
                description="National School Health Td vaccination & adolescent anaemia drive in South zone",
                signal_type="CAMPAIGN",
                facility_id="H1",
                taluk="South",
                drugs_affected=["Td", "IFA-W"],
                multipliers={"Td": 3.0, "IFA-W": 2.5},
                duration_days=10,
                text="National School Health Programme Td vaccination and adolescent anaemia campaign launched in South zone",
            ),
        }
        # Baseline is active by default
        self.scenarios["baseline"].active = True

    async def activate_scenario(self, name: str) -> Scenario:
        """Activate a scenario, compute effective dates, and publish device faults to Redis."""
        if name not in self.scenarios:
            raise ValueError(f"Unknown scenario '{name}'. Available: {list(self.scenarios.keys())}")

        sc = self.scenarios[name]
        sc.active = True
        sc.start_day = clock.day_index

        current_date = clock.current_sim_time.date()
        sc.effective_from = current_date.isoformat()
        sc.effective_to = (current_date + timedelta(days=sc.duration_days)).isoformat()
        sc.signal_id = f"SIG-{name.upper()}-{uuid4().hex[:6]}"

        # If scenario includes device faults, publish to Redis key 'sensors:faults'
        if sc.device_fault:
            try:
                r_client = get_redis_client()
                await asyncio.wait_for(
                    r_client.set("sensors:faults", json.dumps(sc.device_fault)),
                    timeout=0.5,
                )
            except Exception as e:
                logger.debug(f"Redis fault publish notice: {e}")

        logger.info(f"Scenario '{name}' activated: {sc.text}")
        return sc

    def get_demand_multiplier(self, facility_id: str, drug_code: str) -> float:
        """Get aggregate demand multiplier for a facility and drug under active scenarios."""
        multiplier = 1.0
        for sc in self.scenarios.values():
            if not sc.active:
                continue
            if sc.facility_id and sc.facility_id != facility_id:
                continue
            if drug_code in sc.multipliers:
                multiplier *= sc.multipliers[drug_code]
        return multiplier

    def is_scenario_active(self, name: str) -> bool:
        """Check if a specific scenario is currently active."""
        sc = self.scenarios.get(name)
        return sc.active if sc else False

    def get_signals_feed(self) -> List[Dict[str, Any]]:
        """Return active signals feed conforming to OpenAPI and IDSP format."""
        signals = []
        for sc in self.scenarios.values():
            if not sc.active or sc.name == "baseline":
                continue

            primary_drug = sc.drugs_affected[0] if sc.drugs_affected else "ALL"
            primary_mult = sc.multipliers.get(primary_drug, 1.0) if sc.multipliers else 1.0

            signals.append({
                "id": sc.signal_id,
                "type": sc.signal_type,
                "signal_type": sc.signal_type,
                "facility": sc.facility_id or "ALL",
                "district": "Bengaluru Urban",
                "taluk": sc.taluk or "All",
                "drug_code": primary_drug,
                "drugs_affected": sc.drugs_affected,
                "multiplier": primary_mult,
                "multipliers": sc.multipliers,
                "start_day": sc.start_day,
                "effective_from": sc.effective_from or clock.current_sim_time.date().isoformat(),
                "effective_to": sc.effective_to or (clock.current_sim_time.date() + timedelta(days=sc.duration_days)).isoformat(),
                "text": sc.text,
                "notes": sc.text,
            })
        return signals

    def get_scenarios_list(self) -> List[Dict[str, Any]]:
        """Return list of all scenarios with their active status."""
        return [
            {
                "name": sc.name,
                "description": sc.description,
                "active": sc.active,
            }
            for sc in self.scenarios.values()
        ]

    def reset(self, seed: Optional[int] = None) -> None:
        """Reset scenario state back to baseline."""
        if seed is not None:
            self.seed = seed
        self._init_scenarios()


# Global singleton instance
scenario_manager = ScenarioManager()
