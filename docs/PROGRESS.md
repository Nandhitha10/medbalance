# Project Progress Log

## Status Overview
- Current Phase: Foundation & API Contracts Complete
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
- **L1 (Core)**: Implement endpoints in `services/core-api` backed by PostgreSQL and audit chain.
- **L2 (Optimizer)**: Integrate QUBO solver and QpiAI adapters in `services/optimizer`.
- **L3 (AI & Forecast)**: Wire GenAI gateway and Holt-Winters forecasting engine.
- **L4 (ColdChain & Sim)**: Implement MQTT ingestion in `services/coldchain` and hospital SQLite instances.
