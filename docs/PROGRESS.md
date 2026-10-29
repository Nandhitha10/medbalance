# Project Progress Log

## Status Overview
- Current Phase: Cold Chain & Sensor Telemetry Pipeline (HX2 Live Story) Complete
- Updated: 2026-10-29

## Completed Tasks
- [x] Monorepo directory layout established per CLAUDE.md §4.
- [x] Shared library `libs/medbal_common` created with Pydantic settings, SQLAlchemy 2.0 DB session factory, Redis Streams bus helpers, deterministic clock, tamper-evident SHA-256 audit chain, structured JSON logging, Pydantic domain models, and FastAPI base factory.
- [x] `docker/py-base.Dockerfile` created with `python:3.12-slim`, `uv`, and `medbal_common`.
- [x] Placeholder FastAPI services created for all services in CLAUDE.md §3 with individual `pyproject.toml` and `Dockerfile` (`core-api`, `ingest-ai`, `genai`, `forecast`, `optimizer`, `coldchain`, `sim-control`, `sim-hospital`, `sensors`).
- [x] Multi-profile `docker-compose.yml` configured (`core`, `ai`, `opt`, `sim`, `full`) with healthchecks and restart policies.
- [x] Nginx API Gateway configured with service reverse proxying and SSE-friendly streaming buffers.
- [x] `contracts/openapi/`: 8 OpenAPI 3.1 YAML specifications created + canonical `components.yaml` for shared data schemas.
- [x] `contracts/events.md`: 10 core Redis Streams specifications documented with JSON Schema and examples.
- [x] `contracts/fixtures/`: Realistic JSON fixtures for all service responses, featuring cross-facility consistency (H1..H4, W0) and an optimization plan with 6 orders (including 28 vials of insulin usable from a 50-vial lot).
- [x] `medbal_common.fixtures.serve(app, service_name)` implemented to mock all API endpoints when `USE_FIXTURES=1`.
- [x] Contract validation tests (`contracts/test_contracts.py`) written and passing.
- [x] `db/init/001_schema.sql` created containing all 21 tables (`facility`, `drug`, `drug_alias`, `lot`, `stock_report`, `extraction_item`, `consumption_daily`, `forecast`, `policy`, `route`, `vehicle`, `sensor_reading`, `plan_run`, `candidate`, `transfer_order`, `regret_entry`, `custody_event`, `credit_memo`, `audit_log`, `llm_call`, `chat_session`, `chat_message`) with proper FKs, indexes, check constraints (`qty >= 0`), and JSONB support.
- [x] `data/seed/district.yaml` created: Bengaluru Urban district with H1 (DH), H2 (TH), H3 (CHC), H4 (PHC), W0 (WH), taluks, and 5 vehicles (ambient, cold vans with sensors, two-wheeler).
- [x] `data/seed/drugs.yaml` created: 13 essential drugs with VEN classification, temperature specifications, unit costs in INR, pack sizes, and multilingual aliases (including English typos and Kannada script).
- [x] `data/seed/generate.py` implemented with `--seed 42`: generates 90-day Poisson consumption history with weekly seasonality, 20 routes with haversine distance and transit times, per-facility inventory policies, and writes `db/init/002_seed.sql` + `data/seed/hospitals/h1..h4.json`.
- [x] Seed invariant tests (`data/seed/test_seed.py`) passing.
- [x] Shared FEFO mathematics module created in `libs/medbal_common/medbal_common/fefo.py`: worked example verified (50 vials, 2/day, 14 days -> 28 effective, 22 at risk), reserve protection from longest-dated lots, shortage calculation, and Rule F4 usable quantity logic.
- [x] `services/core-api` fully implemented against PostgreSQL/SQLAlchemy:
  - Master data: `GET /facilities`, `GET /drugs`, `GET /routes`, `GET /vehicles` (with dual routing `/api/core/*`).
  - Lots: Idempotent batch upsert `POST /lots/upsert-batch` with audit entries and Redis stream `inventory.updated` emission.
  - Positions: `GET /positions` computed via FEFO with per-lot detail; rate dynamically selected from latest forecast or 28-day consumption history.
  - Optimizer snapshot: `GET /snapshot` with deterministic SHA-256 `snapshot_hash` over canonical JSON.
  - Plans: `POST /plans` persisting PlanRun, candidates, transfer orders with sequential `DTA/BLR-U/2026/NNNNNN` numbering, HMAC-SHA256 QR tokens, regret entries, and `plan.completed` emission.
  - Orders: `GET /orders`, `GET /orders/{id}`, `POST /orders/{id}/approve`, `POST /orders/{id}/reject` with audit log tracking and `order.status` stream publication.
  - Custody: `POST /custody/scan` returning 501 Not Implemented per milestone rules; `GET /custody/{order_id}` returning custody history.
  - Provenance: `GET /provenance/{order_id}` delivering full DAG nodes and edges (`stock_report -> extraction_item -> lot -> candidate -> order -> custody_event`) with feasibility proofs and audit sequence numbers.
  - Audit chain: `GET /audit/verify` and `GET /audit?entity=&id=`, verified for integrity and cryptographic tamper detection.
  - Real-time events: `GET /events` Server-Sent Events (SSE) streaming Redis Streams with 15-second heartbeats.
  - Vehicle status: `POST /vehicles/{id}/status` allowing cold chain status updates and marking associated routes safe/unsafe.
- [x] `services/sim-control` fully implemented:
  - Simulation clock: configurable day length (`SIM_DAY_SECONDS=30` default), start/pause/speed control, advances virtual datetime starting at `SIM_START_DATE`.
  - Publishes `clock.tick` event to Redis Streams on each new sim day turnover.
  - 7 deterministic scenarios (`baseline`, `dengue_outbreak`, `fridge_failure`, `bad_data`, `ilr_repaired`, `road_closure`, `td_campaign`) setting facility×drug demand multipliers, route closures, and publishing refrigeration excursions to Redis key `sensors:faults`.
  - IDSP-style signal feed: `GET /signals` exposing active epidemiological and infrastructure shocks.
  - Cluster reset: `POST /reset?seed=` resets clock, scenarios, and broadcasts reset notifications concurrently to all hospital nodes.
- [x] `services/sim-hospital` fully implemented (single Docker image configured by `HOSPITAL_ID=H1..H4`):
  - Private SQLite stock inventory (`hospital_stock`, `dispense_history`, `transfer_events`) per node.
  - Reactive `clock.tick` Redis consumer: draws Poisson demand ($\lambda \times \text{multiplier}$), dispenses FEFO, logs stockouts, and expires lots at end of day.
  - Stock transfer endpoints: `POST /transfers/inbound` adds received stock, `POST /transfers/outbound` decrements dispatched stock.
  - Ground truth introspection: `GET /state` returns internal inventory for verification.
  - 4 diverse real-world reporting styles:
    - **H1 (FHIR)**: `GET /fhir/InventoryReport` returning FHIR R5/R4 `InventoryReport` resource with nested `inventoryListing` items.
    - **H2 (CSV)**: `GET /export/stock.csv` returning e-Aushadhi export with 10-pack strip conversions and missing batch number clerical defects.
    - **H3 (Chat)**: Daily bilingual Kannada + English informal chat report with 15 template variants pushed to `ingest-ai /ingest/H3`.
    - **H4 (Handwritten/Text)**: Messy physical stock register note with common clerical typos (`inzulin`, `paracetmol`); when `bad_data` is active, outputs anomalous quantity (10000) and corrupted year (1999) pushed to `ingest-ai /ingest/H4`.
- [x] `services/sensors` fully implemented:
  - Simulates temperature devices across cold transport vans (`DEV-CV-01`, `DEV-CV-02`) and facility ILRs (`DEV-ILR-H1`..`H4`, `W0`).
  - Publishes telemetry every 5 real seconds to MQTT topic `district/coldchain/{device_id}/telemetry` with payload `{ts, temp_c, door_open, battery}`.
  - Normal operation: 4.5 °C ± 1.0 with Gaussian noise.
  - Fault mode: polls Redis key `sensors:faults`; when `fridge_failure` triggers, drifts `CV-02` temperature up towards ~11.4 °C over 60 seconds.
  - H4 ILR starts in `offline` state until `ilr_repaired` signal received.
- [x] `services/coldchain` fully implemented:
  - Subscribes to MQTT topic `district/coldchain/+/telemetry`.
  - Deterministic per-device state machine: `OK` -> `WARNING` (1 reading out of 2–8 °C) -> `EXCURSION` (3 consecutive out of 2–8 °C or door open > 2 min) -> `RECOVERED` (6 consecutive good readings).
  - Excursion action: marks vehicle `cold_ok=false` and its routes `status=unsafe` with `status_reason` via core-api (`POST /vehicles/{id}/status`), and publishes `coldchain.alert` to Redis Streams (`{device, vehicle, route_ids, temp_c, since, severity="CRITICAL"}`).
  - Recovery action: marks vehicle `cold_ok=true` and routes `status=safe` via core-api, and publishes recovery `coldchain.alert` (`severity="NORMAL"`). Alerts published exactly once per state transition.
  - Downsampled persistence: writes telemetry rows (at most 1 per 60s per device) into PostgreSQL `sensor_reading` table.
  - Endpoints: `GET /status`, `GET /devices/{id}/telemetry?since=` for sparklines, `POST /telemetry` for test injection.
- [x] Docker Compose updated with `sensors` and `coldchain` wired with `USE_FIXTURES: "0"`, Mosquitto MQTT, and Redis dependency.
- [x] Comprehensive test suites passing (61 total tests passing across monorepo).

## Table of Engineered Story Lots (For L2, L3, L4 Lanes)

| Facility | Drug Code | Batch No | Expiry | Qty | Story Context & Purpose |
|---|---|---|---|---|---|
| **H4** (SIM-PHC Hesaraghatta) | `INS-REG` | `LOT-INS-H4-01` | **2026-11-19** (18 days) | **50 vials** | **CORE STORY LOT**: Expiring in 18 days with tiny local usage (~0.3/day). H4's ILR is under repair (`cold_storage_ok = false`). Must be redistributed immediately to prevent total wastage. |
| **H1** (SIM-DH Jayanagar) | `INS-REG` | `LOT-INS-H1-01` | 2026-11-20 (19 days) | **2 vials** | **CRITICAL SHORTAGE**: High-volume district hospital consumption (~22/day) with near-zero stock on hand. Prime destination for H4's surplus insulin! |
| **H1** (SIM-DH Jayanagar) | `OXY-10` | `LOT-OXY-H1-01` | 2026-11-22 (21 days) | **3 ampoules** | **CRITICAL SHORTAGE**: Labour room essential with acute deficit. |
| **H2** (SIM-TGH Anekal) | `IFA-W` | `LOT-IFA-H2-01` | 2026-11-25 (24 days) | **12,000 tabs** | **SURPLUS**: Massive overstock expiring in 24 days. Needs redistribution to PHCs/CHCs. |
| **H2** (SIM-TGH Anekal) | `PCM-500` | `LOT-PCM-H2-01` | 2026-11-20 (19 days) | **8,000 tabs** | **SURPLUS**: Near-expiry paracetamol overstock. |
| **H2** (SIM-TGH Anekal) | `AMOX-500` | `LOT-AMX-H2-01` | 2026-11-22 (21 days) | **3,500 tabs** | **SURPLUS**: Antibiotic surplus exceeding local 21-day target reserve. |
| **H2** (SIM-TGH Anekal) | `MOR-10` | `LOT-MOR-H2-01` | 2026-12-15 (44 days) | **250 tabs** | **F6 FEASIBILITY DEMO**: Schedule X / controlled narcotic (`is_controlled = true`). Optimizer feasibility rule F6 must explicitly flag and reject automated transfer without special permits. |
| **H3** (SIM-CHC Yelahanka) | `ORS-20` | `LOT-ORS-H3-01` | 2026-12-05 (35 days) | **15 sachets** | **PRE-OUTBREAK DEFICIT**: Near-empty stock before the monsoon dengue/diarrhea surge scenario triggers. |
| **W0** (District Warehouse) | `INS-REG`, `OXY-10`, `ORS-20`, `CEFT-1000` | `LOT-*-W0-01` | 6–12 months | 500–10,000 units | **BUFFER RESERVE**: Central buffer with long shelf lives for normal replenishment. |

## Sample Hospital Reporting Outputs

### 1. H1 (SIM-DH Jayanagar) - FHIR R5/R4 InventoryReport (`GET /fhir/InventoryReport`)
```json
{
  "resourceType": "InventoryReport",
  "id": "rpt-H1-20261101-080000",
  "status": "completed",
  "countType": "snapshot",
  "reportedDateTime": "2026-11-01T08:00:00+05:30",
  "reporter": {
    "reference": "Location/H1",
    "display": "SIM-DH Jayanagar"
  },
  "inventoryListing": [
    {
      "item": {
        "concept": {
          "coding": [
            {
              "system": "https://nhm.gov.in/drugs",
              "code": "INS-REG",
              "display": "Insulin Regular 100 IU/ml"
            }
          ]
        }
      },
      "lot": "LOT-INS-H1-01",
      "expiry": "2026-11-20",
      "quantity": {
        "value": 2,
        "unit": "vial"
      }
    }
  ]
}
```

### 2. H2 (SIM-TGH Anekal) - e-Aushadhi CSV Export (`GET /export/stock.csv`)
*(Includes 10-pack strip unit conversions and missing batch number clerical defects)*
```csv
Drug Name,Batch No,Exp Date,Qty,Unit
Paracetamol Tablets IP 500mg,LOT-PCM-H2-01,11/2026,800,strip
Amoxicillin Capsules IP 500mg,,11/2026,350,strip
Inj. Insulin Regular 100 IU/ml,LOT-INS-H2-01,12/2026,50,vial
Iron and Folic Acid Tablets (WIFS Blue),LOT-IFA-H2-01,11/2026,1200,strip
```

### 3. H3 (SIM-CHC Yelahanka) - Kannada + English Informal Chat Report
*(Pushed daily to `ingest-ai /ingest/H3` from 15 bilingual template variants)*
```text
ನಮಸ್ಕಾರ / Hello sir, Yelahanka CHC stock update for 01/11: ORS 15 sachets (exp 05/12), Paracetamol 1500 tabs (exp 16/12). ಇನ್ಸುಲಿನ್ ಇಲ್ಲ (no insulin in stock). Please arrange emergency supply.
```

### 4. H4 (SIM-PHC Hesaraghatta) - Handwritten Register Physical Count
*(Pushed daily to `ingest-ai /ingest/H4` with clerical typos; triggers OCR anomaly during `bad_data` scenario)*

**Normal messy register note:**
```text
DAILY STOCK REGISTER - HESARAGHATTA PHC
Date: 01/11/2026
Physical count taken at ILR & ambient rack:
- 50 vials inzulin (reg 100iu) batch LOT-INS-H4-01 exp 19/11/2026
- 300 tabs paracetmol batch LOT-PCM-H4-01 exp 16/12/2026
- 150 ors sachets batch LOT-ORS-H4-01 exp 30/01/2027
Remarks: Fridge repair pending technician visit.
Signed, Pharmacist Hesaraghatta PHC
```

**Anomalous `bad_data` scenario note (corrupted quantity & invalid year):**
```text
DAILY STOCK REGISTER - HESARAGHATTA PHC
Date: 01/11/2026
Physical count taken at ILR & ambient rack:
- 10000 inzulin batch LOT-INS-H4-01 exp 19/11/1999
- 300 tabs paracetmol batch LOT-PCM-H4-01 exp 16/12/2026
- 150 ors sachets batch LOT-ORS-H4-01 exp 30/01/2027
Remarks: Fridge repair pending technician visit.
Signed, Pharmacist Hesaraghatta PHC
```



## How to Verify
- **Contract tests**:
  ```bash
  uv run pytest contracts
  ```
- **Shared library & audit tamper tests**:
  ```bash
  uv run pytest libs/medbal_common
  ```
- **Full test suite**:
  ```bash
  uv run pytest
  ```
- **Start Docker stack (with Docker installed)**:
  ```bash
  make build && make up
  ```
- **Test gateway health**:
  ```bash
  curl http://localhost:8080/api/core/health
  ```
- **Test demo plan (with USE_FIXTURES=1)**:
  ```bash
  curl http://localhost:8080/api/optimizer/plan/demo
  ```

## Service API Endpoints Summary

### 1. `core-api` (Port 8001 / Gateway: `/api/core/*`)
- `GET /facilities`: List district facilities (H1..H4, W0)
- `GET /drugs`: List drug formulary
- `GET /routes`: List transit routes and transit times
- `GET /vehicles`: List transport fleet and cold capabilities
- `POST /vehicles/{id}/status`: Update vehicle cold chain status and associated routes safe/unsafe
- `GET /lots?facility=&drug=`: Query inventory lots
- `POST /lots/upsert-batch`: Batch upsert inventory lots
- `GET /positions?facility=&drug=`: Computed stock positions (shortage, reserve, at-risk)
- `GET /snapshot`: Complete district snapshot for optimizer
- `POST /plans`: Persist plan run, candidates, orders, and regret entries
- `GET /orders?plan_id=&status=`: List transfer orders
- `GET /orders/{id}`: Get transfer order by ID
- `POST /orders/{id}/approve`: Approve transfer order (DTA)
- `POST /orders/{id}/reject`: Reject transfer order
- `POST /custody/scan`: Record barcode/QR custody scan event
- `GET /custody/{order_id}`: Get custody chain of custody events
- `GET /audit/verify`: Verify SHA-256 audit chain integrity
- `GET /audit?entity=&id=`: Query audit log records
- `GET /events`: Real-time SSE stream (`text/event-stream`)
- `GET /provenance/{order_id}`: Full mathematical and audit provenance

### 2. `ingest-ai` (Port 8002 / Gateway: `/api/ingest/*`)
- `POST /ingest/{facility_code}`: Ingest PDF/Excel/CSV/FHIR report
- `POST /pull/run`: Trigger active polling across hospital nodes
- `GET /reports`: List ingested stock reports
- `GET /reviews`: List anomaly review queue items
- `POST /reviews/{id}/resolve`: Resolve anomaly review item

### 3. `genai` (Port 8003 / Gateway: `/api/genai/*`)
- `POST /llm/complete`: Central LLM gateway with Pydantic structured output
- `POST /narrate/{order_id}`: Generate grounded order narration with numeric firewall
- `POST /docs/dta/{order_id}`: Generate printable DTA voucher PDF
- `POST /docs/credit-memo/{order_id}`: Generate financial credit memo
- `POST /copilot/chat`: SSE interactive copilot stream
- `GET /ai/health`: Model status and cache health

### 4. `forecast` (Port 8004 / Gateway: `/api/forecast/*`)
- `POST /forecast/run`: Trigger Holt-Winters consumption forecast calculation
- `GET /forecast?facility=&drug=`: Query computed consumption rates
- `GET /forecast/backtest`: Get backtest MAPE and RMSE accuracy reports

### 5. `optimizer` (Port 8005 / Gateway: `/api/optimizer/*`)
- `POST /plan/run`: Run QUBO redistribution solver (`live`, `whatif`, `eval`)
- `GET /plan/{id}`: Retrieve optimization plan (e.g. `/plan/demo`)
- `GET /plan/{id}/benchmark`: Compare solver vs classical exact MILP gap
- `GET /plan/{id}/regret?order_id=`: Inspect regret analysis and alternate destinations
- `GET /whynot?facility=&drug=`: Explain non-allocation with F1–F6 rule breakdown
- `POST /whatif`: Simulate allocation scenario without persistence
- `POST /eval/replay`: Replay historical simulation days
- `GET /eval/{id}`: Get evaluation run details

### 6. `coldchain` (Port 8006 / Gateway: `/api/coldchain/*`)
- `GET /status`: Overall temperature sensor and excursion status
- `GET /devices/{id}/telemetry?since=`: Retrieve device telemetry timeseries

### 7. `sim-control` (Port 8100 / Gateway: `/api/sim/*`)
- `GET /clock`: Query simulation clock state
- `POST /clock/start`: Start simulation clock
- `POST /clock/pause`: Pause simulation clock
- `POST /clock/speed`: Set speed multiplier
- `POST /scenario/{name}`: Apply named scenario
- `POST /reset?seed=`: Reset simulation clock and DB state
- `GET /signals`: Active outbreak and epidemiological signals
- `GET /scenarios`: List available simulation scenarios

### 8. `sim-hospital` (Ports 8101..8104)
- `GET /fhir/InventoryReport`: Export stock in FHIR R4 format
- `GET /export/stock.csv`: Export stock in CSV format
- `GET /state`: Hospital internal stock state
- `POST /transfers/inbound`: Acknowledge inbound medicine arrival
- `POST /transfers/outbound`: Dispatch outbound transfer

## Decisions
- See [docs/DECISIONS.md](DECISIONS.md) (ADR-001 through ADR-004)

## Requests & Next Steps for Lanes
- **L1 (Core)**: Added `POST /vehicles/{id}/status` and `/internal/coldchain/vehicle-status` to `contracts/openapi/core-api.yaml` and implemented in `services/core-api/src/routers/master.py` to allow coldchain status updates to mark vehicles and routes safe/unsafe with audit tracking.
- **L2 (Optimizer)**: Integrate QUBO solver and QpiAI adapters in `services/optimizer`.
- **L3 (AI & Forecast)**: Wire GenAI gateway and Holt-Winters forecasting engine.
- **L4 (ColdChain & Sim)**: [COMPLETED] `sim-control`, `sim-hospital` (all 4 styles), `sensors`, and `coldchain` fully implemented and tested.
