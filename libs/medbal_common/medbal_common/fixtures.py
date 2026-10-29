"""Fixture serving helper for MedBalance services when USE_FIXTURES=1."""

import json
import logging
import os
from pathlib import Path
from typing import Any
from fastapi import FastAPI, Response
from fastapi.responses import PlainTextResponse

logger = logging.getLogger(__name__)


def find_fixtures_dir() -> Path:
    """Locate contracts/fixtures directory across execution contexts."""
    candidates = [
        Path.cwd() / "contracts" / "fixtures",
        Path(__file__).resolve().parent.parent.parent.parent / "contracts" / "fixtures",
        Path("/app/contracts/fixtures"),
    ]
    for c in candidates:
        if c.exists() and c.is_dir():
            return c
    return Path.cwd() / "contracts" / "fixtures"


def load_fixture(name: str) -> Any:
    """Load JSON fixture file from contracts/fixtures."""
    fixtures_dir = find_fixtures_dir()
    filepath = fixtures_dir / name
    if not filepath.exists():
        logger.warning(f"Fixture file not found: {filepath}")
        return {}
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def serve(app: FastAPI, service_name: str) -> None:
    """Register mock routes serving realistic fixtures when USE_FIXTURES is active."""
    use_fixtures_env = os.getenv("USE_FIXTURES", "").lower() in ("1", "true", "yes")
    if not use_fixtures_env:
        return

    logger.info(f"Registering mock fixture endpoints for service '{service_name}'")

    # Common / Shared
    if service_name in ("core-api", "core"):
        @app.get("/facilities")
        async def get_facilities():
            return load_fixture("facilities.json")

        @app.get("/drugs")
        async def get_drugs():
            return load_fixture("drugs.json")

        @app.get("/routes")
        async def get_routes():
            return load_fixture("routes.json")

        @app.get("/vehicles")
        async def get_vehicles():
            return load_fixture("vehicles.json")

        @app.get("/lots")
        async def get_lots():
            return load_fixture("lots.json")

        @app.post("/lots/upsert-batch")
        async def upsert_lots():
            return {"status": "ok", "upserted_count": 2}

        @app.get("/positions")
        async def get_positions():
            return load_fixture("positions.json")

        @app.get("/snapshot")
        async def get_snapshot():
            return load_fixture("snapshot.json")

        @app.post("/plans")
        async def persist_plan():
            return {"status": "created", "plan_id": "PLAN-20261101-01"}

        @app.get("/orders")
        async def get_orders():
            return load_fixture("orders.json")

        @app.get("/orders/{id}")
        async def get_order_by_id(id: str):
            order = load_fixture("order_single.json")
            order["id"] = id
            return order

        @app.post("/orders/{id}/approve")
        async def approve_order(id: str):
            order = load_fixture("order_single.json")
            order["id"] = id
            order["status"] = "APPROVED"
            return order

        @app.post("/orders/{id}/reject")
        async def reject_order(id: str):
            order = load_fixture("order_single.json")
            order["id"] = id
            order["status"] = "CANCELLED"
            return order

        @app.post("/custody/scan")
        async def custody_scan():
            return {"status": "recorded", "event_id": 1}

        @app.get("/custody/{order_id}")
        async def get_custody(order_id: str):
            return load_fixture("custody_events.json")

        @app.get("/audit/verify")
        async def audit_verify():
            return load_fixture("audit_verify.json")

        @app.get("/audit")
        async def audit_entries():
            return load_fixture("audit_entries.json")

        @app.get("/provenance/{order_id}")
        async def get_provenance(order_id: str):
            prov = load_fixture("provenance.json")
            prov["order_id"] = order_id
            return prov

    elif service_name == "optimizer":
        @app.post("/plan/run")
        async def plan_run():
            return load_fixture("plan.json")

        @app.get("/plan/{id}")
        async def get_plan(id: str):
            plan = load_fixture("plan.json")
            if id != "demo":
                plan["id"] = id
            return plan


        @app.get("/plan/{id}/benchmark")
        async def get_benchmark(id: str):
            return {
                "plan_id": id,
                "solver_tier": "platform",
                "milp_optimal_energy": -142.50,
                "solver_energy": -142.10,
                "optimality_gap_percent": 0.28,
                "solver_time_sec": 4.12,
                "milp_time_sec": 8.45,
            }

        @app.get("/plan/{id}/regret")
        async def get_regret(id: str):
            plan = load_fixture("plan.json")
            return plan.get("regret", [])

        @app.get("/whynot")
        async def whynot():
            return {
                "facility_id": "H1",
                "drug_code": "INS-REG",
                "candidates_evaluated": 4,
                "feasible_candidates": 1,
                "reasons": [
                    "F3 cold chain: destination H3 lacks cold storage",
                    "F5 reserve: 10 units protected at H1",
                ],
            }

        @app.post("/whatif")
        async def whatif():
            plan = load_fixture("plan.json")
            plan["mode"] = "whatif"
            return plan

        @app.post("/eval/replay")
        async def eval_replay():
            return {
                "eval_id": "EVAL-001",
                "status": "completed",
                "days_replayed": 14,
                "total_stockout_reduction": 1350,
                "total_expiry_avoided": 1428,
            }

        @app.get("/eval/{id}")
        async def get_eval(id: str):
            return {
                "eval_id": id,
                "status": "completed",
                "days_replayed": 14,
                "total_stockout_reduction": 1350,
                "total_expiry_avoided": 1428,
            }

    elif service_name == "ingest-ai":
        @app.post("/ingest/{facility_code}")
        async def ingest_facility(facility_code: str):
            reports = load_fixture("reports.json")
            rep = reports[0] if reports else {"id": "REP-01"}
            rep["facility_code"] = facility_code
            return rep

        @app.post("/pull/run")
        async def pull_run():
            return {"status": "completed", "facilities_polled": 4, "reports_ingested": 4}

        @app.get("/reports")
        async def get_reports():
            return load_fixture("reports.json")

        @app.get("/reviews")
        async def get_reviews():
            return load_fixture("reviews.json")

        @app.post("/reviews/{id}/resolve")
        async def resolve_review(id: str):
            return {"status": "resolved", "review_id": id}

    elif service_name == "genai":
        @app.post("/llm/complete")
        async def llm_complete():
            return load_fixture("llm_complete.json")

        @app.post("/narrate/{order_id}")
        async def narrate_order(order_id: str):
            narration = load_fixture("narration.json")
            narration["order_id"] = order_id
            return narration

        @app.post("/docs/dta/{order_id}")
        async def docs_dta(order_id: str):
            dummy_pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 612 792]>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000010 00000 n\n0000000053 00000 n\n0000000102 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n162\n%%EOF"
            return Response(content=dummy_pdf, media_type="application/pdf")

        @app.post("/docs/credit-memo/{order_id}")
        async def docs_credit_memo(order_id: str):
            memo = load_fixture("credit_memo.json")
            memo["order_id"] = order_id
            return memo

        @app.get("/ai/health")
        async def ai_health():
            return load_fixture("ai_health.json")

    elif service_name == "forecast":
        @app.post("/forecast/run")
        async def forecast_run():
            return {"status": "completed", "forecasts_generated": 24}

        @app.get("/forecast")
        async def get_forecast():
            return load_fixture("forecast.json")

        @app.get("/forecast/backtest")
        async def forecast_backtest():
            return load_fixture("forecast_backtest.json")

    elif service_name == "coldchain":
        @app.get("/status")
        async def coldchain_status():
            return load_fixture("coldchain_status.json")

        @app.get("/devices/{id}/telemetry")
        async def device_telemetry(id: str):
            telem = load_fixture("coldchain_telemetry.json")
            for t in telem:
                t["device_id"] = id
            return telem

    elif service_name == "sim-control":
        @app.get("/clock")
        async def sim_clock():
            return load_fixture("clock.json")

        @app.post("/clock/start")
        async def clock_start():
            return {"status": "started", "is_running": true}

        @app.post("/clock/pause")
        async def clock_pause():
            return {"status": "paused", "is_running": false}

        @app.post("/clock/speed")
        async def clock_speed():
            return {"status": "updated", "speed": 2.0}

        @app.post("/scenario/{name}")
        async def scenario_apply(name: str):
            return {"status": "applied", "scenario": name}

        @app.post("/reset")
        async def sim_reset():
            return {"status": "reset", "seed": 42, "reset_time": "2026-11-01T08:00:00+05:30"}

        @app.get("/signals")
        async def sim_signals():
            return load_fixture("signals.json")

        @app.get("/scenarios")
        async def sim_scenarios():
            return load_fixture("scenarios.json")

    elif service_name.startswith("sim-hospital"):
        @app.get("/fhir/InventoryReport")
        async def fhir_inventory_report():
            return load_fixture("fhir_inventory_report.json")

        @app.get("/export/stock.csv")
        async def export_stock_csv():
            csv_content = "drug_code,batch_no,expiry,quantity\nINS-REG,LOT-INS-H1-01,2026-11-20,50\nAMOX-500,LOT-AMX-H1-02,2026-11-25,800\n"
            return PlainTextResponse(content=csv_content, media_type="text/csv")

        @app.get("/state")
        async def hospital_state():
            return load_fixture("hospital_state.json")

        @app.post("/transfers/inbound")
        async def inbound_transfer():
            return {"status": "received", "order_id": "DTA/BLR-U/2026/000101", "stock_updated": True}

        @app.post("/transfers/outbound")
        async def outbound_transfer():
            return {"status": "dispatched", "order_id": "DTA/BLR-U/2026/000101", "remaining_stock": 22}
