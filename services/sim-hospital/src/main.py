"""Simulated Hospital Node Service entrypoint."""

import asyncio
from contextlib import asynccontextmanager
from datetime import date
import logging
import os
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from medbal_common.bus import consume, get_redis_client
from medbal_common.clock import now as sim_now
from medbal_common.fastapi_base import create_app
from medbal_common.http import create_client
from medbal_common.settings import get_settings
from medbal_common import fixtures

from src.hospital import HospitalNode

logger = logging.getLogger(__name__)

hospital_id = os.getenv("HOSPITAL_ID", "H1").upper()
hospital_node = HospitalNode(hospital_id=hospital_id)


class InboundTransferPayload(BaseModel):
    order_id: str
    drug_code: str
    batch_no: str
    quantity: int = Field(gt=0)
    expiry: Optional[str] = "2026-12-31"


class OutboundTransferPayload(BaseModel):
    order_id: str
    drug_code: str
    batch_no: str
    quantity: int = Field(gt=0)


class TickPayload(BaseModel):
    day_index: int = 1
    date: str = "2026-11-02"
    multipliers: Optional[Dict[str, float]] = None
    bad_data_active: Optional[bool] = False


async def _clock_tick_consumer(stop_event: asyncio.Event) -> None:
    """Listen to Redis clock.tick events and advance hospital dispensing."""
    try:
        redis_client = get_redis_client()
        await asyncio.wait_for(redis_client.ping(), timeout=0.2)
    except Exception:
        logger.debug("Redis unavailable for sim-hospital tick consumer; running local mode")
        return

    async def handle_tick(msg_id: str, payload: Dict[str, Any]) -> None:
        try:
            data = payload.get("data", payload)
            day_idx = int(data.get("day_index", 0))
            date_str = str(data.get("date", "2026-11-01"))
            sim_d = date.fromisoformat(date_str)

            # Query sim-control for active multipliers / signals if available
            multipliers = {}
            bad_data = False
            sim_ctrl_url = os.getenv("SIM_CONTROL_URL", "http://sim-control:8100")
            async with create_client(timeout=0.5) as client:
                try:
                    resp = await client.get(f"{sim_ctrl_url}/signals")
                    if resp.status_code == 200:
                        signals = resp.json()
                        for s in signals:
                            if s.get("facility") in (hospital_id, "ALL"):
                                if "multipliers" in s:
                                    multipliers.update(s["multipliers"])
                                if s.get("signal_type") == "DATA_ANOMALY" and hospital_id == "H4":
                                    bad_data = True
                except Exception:
                    pass

            await hospital_node.on_clock_tick(
                day_index=day_idx,
                sim_date=sim_d,
                demand_multipliers=multipliers,
                bad_data_active=bad_data,
            )
        except Exception as err:
            logger.error(f"Error handling clock.tick in {hospital_id}: {err}")

    try:
        await consume(
            stream="clock.tick",
            group=f"hospital-{hospital_id.lower()}",
            consumer=f"node-{hospital_id.lower()}",
            handler=handle_tick,
            redis_client=redis_client,
            stop_event=stop_event,
        )
    except Exception as exc:
        logger.debug(f"Consumer loop ended: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background tick listener on startup."""
    stop_event = asyncio.Event()
    task = asyncio.create_task(_clock_tick_consumer(stop_event))
    yield
    stop_event.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def build_app() -> FastAPI:
    settings = get_settings()
    app = create_app(
        name=f"sim-hospital-{hospital_id.lower()}",
        title=f"MedBalance Simulated Hospital {hospital_id}",
        lifespan=lifespan,
    )

    if settings.USE_FIXTURES:
        fixtures.serve(app, "sim-hospital")
        return app

    @app.get("/fhir/InventoryReport")
    def get_fhir_report() -> Dict[str, Any]:
        """Export current stock as FHIR R5/R4 InventoryReport (H1 style)."""
        return hospital_node.render_fhir_report()

    @app.get("/export/stock.csv")
    def get_stock_csv() -> Response:
        """Export current stock as e-Aushadhi style CSV (H2 style)."""
        csv_text = hospital_node.render_csv_export()
        return Response(content=csv_text, media_type="text/csv")

    @app.get("/state", response_model=Dict[str, Any])
    def get_state() -> Dict[str, Any]:
        """Return ground truth local inventory for evaluation and testing only."""
        return hospital_node.get_state()

    @app.post("/transfers/outbound", response_model=Dict[str, Any])
    def dispatch_outbound_transfer(payload: OutboundTransferPayload) -> Dict[str, Any]:
        """Dispatch outbound transfer from hospital."""
        try:
            ts = sim_now().isoformat()
            remaining = hospital_node.db.record_outbound_transfer(
                order_id=payload.order_id,
                drug_code=payload.drug_code,
                batch_no=payload.batch_no,
                quantity=payload.quantity,
                timestamp_str=ts,
            )
            return {
                "status": "dispatched",
                "order_id": payload.order_id,
                "remaining_stock": remaining,
            }
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    @app.post("/transfers/inbound", response_model=Dict[str, Any])
    def receive_inbound_transfer(payload: InboundTransferPayload) -> Dict[str, Any]:
        """Acknowledge and receive inbound transfer arrival into hospital stock."""
        ts = sim_now().isoformat()
        hospital_node.db.record_inbound_transfer(
            order_id=payload.order_id,
            drug_code=payload.drug_code,
            batch_no=payload.batch_no,
            expiry_str=payload.expiry or "2026-12-31",
            quantity=payload.quantity,
            timestamp_str=ts,
        )
        return {
            "status": "received",
            "order_id": payload.order_id,
            "stock_updated": True,
        }

    @app.post("/tick", response_model=Dict[str, Any])
    async def trigger_sim_tick(payload: TickPayload) -> Dict[str, Any]:
        """Trigger simulated day tick for testing or manual progression."""
        sim_d = date.fromisoformat(payload.date)
        res = await hospital_node.on_clock_tick(
            day_index=payload.day_index,
            sim_date=sim_d,
            demand_multipliers=payload.multipliers,
            bad_data_active=payload.bad_data_active or False,
        )
        return {"status": "ok", "summary": res}

    @app.post("/reset", response_model=Dict[str, Any])
    def reset_hospital(seed: int = Query(42, description="Simulation seed")) -> Dict[str, Any]:
        """Reset hospital node stock back to seed ground truth."""
        hospital_node.reset(seed=seed)
        return {
            "status": "reset",
            "hospital_id": hospital_id,
            "stock_items_count": len(hospital_node.db.get_inventory()),
        }

    return app


app = build_app()
