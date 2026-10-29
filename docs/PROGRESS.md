# Project Progress Log

## Status Overview
- Current Phase: P11 QAOA Max-Cut Graph Zoning, Scale Mode Decomposition, Exact Classical MILP Baseline, and Solver Benchmarking Complete
- Updated: 2026-10-30

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
- [x] `services/genai` fully implemented:
  - **Prompt Registry (`genai_service/registry.py`)**: Loads `prompts/*.yaml` (`id`, `version`, `model: fast|smart`, `temperature`, `max_tokens`, `system`, Jinja2 `user_template`, `json_schema`, `tools`), with dev hot-reload.
  - **Provider Adapters (`genai_service/providers/`)**:
    - `ClaudeProvider`: Anthropic Python SDK (`AsyncAnthropic`), forced single-tool schema enforcement (`tool_choice={"type": "tool", "name": "record_output"}`), copilot multi-tool support, model resolution from `LLM_MODEL_FAST` / `LLM_MODEL_SMART`.
    - `GeminiProvider`: Direct REST adapter env-guarded by `GEMINI_API_KEY`.
    - `OllamaProvider`: Offline local model adapter connecting via `OLLAMA_HOST`.
    - `FakeProvider`: Deterministic mock provider for comprehensive automated testing.
  - **Validation & Retries**: JSON schema validation via `jsonschema`; on violation, appends invalid output and error diagnostic to message history, retrying up to 2 times before returning `{ok: false, error, fallback: true}`.
  - **Redis Replay Cache (`genai_service/cache.py`)**: Key = `sha256(prompt_id@version + model + canonical_json(input))`.
    - `DEMO_MODE=live`: Uses cache as speed-up, populates on miss.
    - `DEMO_MODE=record`: Always queries LLM provider and refreshes cache.
    - `DEMO_MODE=replay`: Serves *only* from cache; on miss returns `{ok: false, fallback: true}` with zero network calls.
  - **Call Logging (`genai_service/db_models.py`)**: Logs all attempts to PostgreSQL table `llm_call` (`purpose`, `provider`, `model`, `prompt_id`, `version`, `input_hash`, `cached`, `execution_time_sec`, `tokens`, `ok`, `error`).
  - **Health & Metrics (`genai_service/metrics.py`, `GET /ai/health`)**: Reports provider info, fast/smart models, cache mode, firewall status, and 24-hour rolling metrics (`total_calls`, `cache_hits`, `cache_hit_rate`, `p50_latency_sec`, `p95_latency_sec`, `schema_failures`, `fallbacks`, `firewall_blocks`, and per-purpose breakdown).
  - **Concurrency & Timeouts**: 4-worker semaphore, 20s fast timeout, 45s smart timeout.
- [x] `services/optimizer` CP1 deterministic planning pipeline fully implemented:
  - **Feasibility Rules F1–F6 (`optimizer/feasibility.py`)**: Pure deterministic rule functions returning `(feasible: bool, failed_rules: List[Dict[str, str]], usable_qty: int)` for explainability and regret ledgers.
  - **Candidates & Chunk Splitting (`optimizer/candidates.py`)**: Splits transferable quantities into $\le 3$ pack-rounded chunks (50/25/25%), computes sequential usable quantity across chunks, calculates economic rewards and trip cost shares, keeps top-3 feasible destinations per chunk, and retains all infeasible pairs for regret tracking.
  - **Greedy Baselines (`optimizer/baselines.py`)**:
    - `greedy_phone_call`: Simulates current manual hospital practice (checks F1–F3 only, ignores usable capacity, moves waste).
    - `greedy_f4`: Safe greedy allocator with full F1–F6 enforcement, reserve protection, and usable quantity capping (guarantees zero waste moved).
  - **Plan Metrics (`optimizer/metrics.py`)**: Evaluates FEFO-grounded shortage reduction, expiry avoided units and INR, waste moved units and INR, trips, total km, transport cost, and net benefit.
  - **Snapshot & Positions (`optimizer/snapshot.py`, `optimizer/positions.py`)**: Indexing snapshot data with fallback to fixtures, and wrapping FEFO positions calculation.
  - **Pipeline Orchestrator (`optimizer/solver.py`, `POST /plan/run`)**: Multi-stage progress tracking via Redis Streams `plan.progress`, plan persistence via `core-api POST /plans`, and publication of `plan.completed`.
  - **FastAPI Endpoints (`optimizer/routers/plan.py`)**: `POST /plan/run`, `GET /plan/{id}`, `GET /plan/{id}/benchmark`, `GET /plan/{id}/regret`, `GET /whynot`, `POST /whatif`, `POST /eval/replay`, `GET /eval/{id}`.
- [x] Docker Compose updated: `optimizer` wired with `USE_FIXTURES: "0"`, `core-api`, and `redis` dependencies.
- [x] `services/ingest-ai` fully implemented:
  - **Adapters (`ingest_ai/adapters/`)**:
    - `FhirAdapter`: Parses FHIR R5/R4 `InventoryReport` resources from H1 (`http://sim-hospital-h1:8101/fhir/InventoryReport`).
    - `CsvAdapter`: Parses e-Aushadhi CSV exports from H2 (`http://sim-hospital-h2:8102/export/stock.csv`), converting 10-pack strips to tablets and handling missing batch numbers.
    - `ChatAdapter`: Parses informal Kannada + English chat from H3 (`POST /ingest/H3`), resolving relative short dates (e.g. `15/11`) to the next occurrence on or after the report date.
    - `TextAdapter`: Parses messy handwritten physical register notes from H4 (`POST /ingest/H4`), grounding clerical typos (`inzulin`, `paracetmol`).
  - **Grounding Engine (`ingest_ai/grounding.py`)**:
    - RapidFuzz matching over drug codes, molecule names, and multilingual aliases (including Kannada script "ಇನ್ಸುಲಿನ್", "ಪ್ಯಾರಸಿಟಮಾಲ್", "ಒಆರ್‌ಎಸ್").
    - Extracted candidates provide closed enum choices to the LLM (no invented codes).
  - **Deterministic Utilities (`ingest_ai/date_utils.py`, `ingest_ai/unit_utils.py`)**:
    - `MM/YYYY` parsed to last calendar day of the month (`calendar.monthrange`).
    - Package units (`strip`, `pkt`) converted deterministically to base units (`tablet`, `sachet`).
  - **Anomaly Gate (`ingest_ai/anomaly.py`)**:
    - Evaluates 5 safety conditions: (1) `QUANTITY_SPIKE` (>10x typical 90-day on-hand), (2) `SUSPICIOUS_EXPIRY` (past or >5 years ahead), (3) `BATCH_EXPIRY_MISMATCH` (cross-facility batch expiry conflict), (4) `UNKNOWN_DRUG`, (5) `LOW_CONFIDENCE` (<0.85).
    - Explanation requested from GenAI gateway (`prompts/anomaly_explain_v1.yaml`) with deterministic template fallback.
    - Emits `anomaly.flagged` event on Redis Streams.
  - **Pharmacist Review Queue (`ingest_ai/routers/reviews.py`)**:
    - `GET /reviews`: Lists pending items requiring pharmacist verification.
    - `POST /reviews/{id}/resolve`: Supports `ACCEPT`, `OVERRIDE`/`CORRECT`, and `REJECT`.
    - Active learning on correction: inserts new alias into `drug_alias` (`alias=raw_span`, detected language) to improve grounding continuously.
  - **Background Polling & Streams**:
    - `POST /pull/run`: Actively polls H1 and H2.
    - Lifespan Redis consumer on `clock.tick` stream triggers automated daily hospital inventory pulls.
    - Emits `report.received` event on Redis Streams.
  - **Evals Golden Dataset**:
    - 40 realistic raw reports (10 FHIR, 10 CSV, 10 Chat, 10 Text) generated in `evals/golden/raw/` for benchmark verification.
  - **Docker Compose**: Updated `ingest-ai` with `USE_FIXTURES: "0"`, PostgreSQL connection, and Redis dependency.
- [x] `web/` Frontend Dashboard (MedBalance-Q) fully implemented per CLAUDE.md §1 & §4:
  - **Stack & Architecture**: React 18, Vite, TypeScript (strict), Tailwind CSS, TanStack Query, React Leaflet, Recharts, and Lucide icons. Robust fallback system (`USE_FIXTURES=1` / transparent offline resilience via `fetchWithFallback`) ensuring demo and projector presentations never fail.
  - **App Shell & Projector-Ready Design**: Calm clinical palette (teal primary `#0d9488`, amber warnings `#d97706`, red stockout `#e11d48`), high contrast for projector legibility, and responsive layout.
  - **Top Bar**: Live simulation clock display with play/pause/speed controls, connection status pill, and animated live event ticker showing the 5 most recent domain events (`clock.tick`, `inventory.updated`, `report.received`, `anomaly.flagged`, `plan.progress`, `plan.completed`, `coldchain.alert`, `order.status`).
  - **District Map**: Leaflet interactive GIS map with custom HTML markers and stock-health rings (VEN-weighted shortage color: Red for Vital shortage, Amber for Warning/Surplus, Green for Healthy). Displays active transfer arcs for the latest plan and interactive legend. Automatic fallback to bundled high-contrast SVG district outline when tile providers are offline.
  - **Facility Inspection Drawer**: Deep-linkable sliding drawer (`?page=map&facility=H3`) showing level, cold storage status, 4 KPI cards (On Hand, Effective, At-Risk, Shortage), per-drug positions read-model table with VEN categorization, and interactive FEFO lot expiry timeline bars.
  - **Plan & DTA Orders View**: "Run Redistribution Plan" trigger with live animated solving progress bar, 4 large projector KPI metrics (Shortage Reduced, Expiry Avoided in ₹, Dispatched Trips, 0 Violations), auditable transfer orders table with DTA voucher numbering, temperature control flags, and instant pharmacist order approval.
  - **Hospital Ingestion & Review Queue**: Inbound channel overview (H1 FHIR, H2 CSV, H3 Kannada WhatsApp, H4 Vision OCR) and pharmacist anomaly review queue with confidence scores, raw text inspection, suggested lot patches, and one-click accept/override actions.
  - **Additional Control Screens**: Coldchain monitor (`/coldchain`), Baseline benchmark (`/benchmark`), Cumulative results (`/results`), AI gateway health & firewall (`/ai-health`), and Scenarios trigger panel (`/scenarios`).
  - **Screenshots**: High-resolution screenshots captured and documented in `docs/screens/`:
    - `docs/screens/01_district_map.png`: District Map with stock-health rings and transfer arcs
    - `docs/screens/02_facility_drawer.png`: Facility Inspection Drawer with per-drug positions & FEFO expiry bars
    - `docs/screens/03_plan_page.png`: Redistribution Plan view with KPI header and DTA orders
    - `docs/screens/04_hospital_ingest.png`: Ingestion channels and Pharmacist Anomaly Review Queue
- [x] Full monorepo test suite green: **109 passed out of 109 tests**.
- [x] **P10 QUBO (v3) Formulation, Verification by Enumeration & QpiAI Opt Engine**:
  - `services/optimizer/optimizer/qubo_builder.py`: Closed-form expansion of $H$ (v3) matching CLAUDE.md §6. Returns upper-triangular dict $Q[(i, j)]$ ($i \le j$) and scalar offset from candidates. Integrates normalized reward, $P_1$ one-place conflict pairs, $P_2$ shortage square (diagonal $\pi(u^2/n^2 - 2u/n)$, off-diagonal $2\pi u_i u_j/n^2$, offset $\pi$), $P_3$ chunk ordering ($+P_3$ on $x_j$, $-P_3$ on $x_j x_{j-1}$), $-\gamma$ shared trip bonuses, and zero-demand guards ($n=0$). Exposes `energy(Q, offset, x)` and `term_breakdown(candidates, snapshot, x)`.
  - `tests/test_qubo_bruteforce.py`: 8 exhaustive brute-force test instances (3 lots $\times$ 2 facilities, $\le 12$ variables) covering: one-place conflict, two lots competing for one shortage, overfill penalty, zero-demand guard, cold-chain infeasible pair absent, shared-trip bonus tie-breaker, chunk order precedence, and VEN priority. In all 8 cases, $\operatorname{argmin} E(x)$ matches the exact best plan found by enumerating all feasible allocations.
  - `docs/QPIAI_OPT_NOTES.md`: Comprehensive introspection and API guide for `qpiai_opt` (`opt_modeller.Binary`, `opt_modeller.Model`, `opt_solvers.client.Client`, `opt_solvers.local.LocalProvider`, `QUBOProblem`, `QUBOSolveResult`), parameter formatting (`matrix_format="upper"`, integer tuple keys `(i, j)` where $i \le j$, `variable_names`), and API key requirements.
  - `services/optimizer/optimizer/solvers/`: Tiered solver architecture under `SolverPort` protocol:
    - `QpiAIOptPlatform`: Remote platform solver client via QpiAI API.
    - `QpiAIOptLocal`: Fast local quantum/classical simulator via `LocalProvider`.
    - `NealSA`: Simulated annealing solver fallback using `dwave-neal`.
    - `GreedyDescent`: Deterministic 1-bit-flip local descent baseline.
    - `solve_chain`: Cascading tiered failover with 20s platform timeout, telemetry recording, and automated JSON run artifact persistence in `evidence/qpiai_runs/<ts>_<hash>.json`.
  - `services/optimizer/optimizer/validator.py`: Post-solver exact FEFO simulation and invariant validation:
    - Strictly enforces 7 invariants: no negative stock, no double shipping, reserve protected from longest-dated lots, cold chain compliance (destination cold storage, route safe, cold van), realised usable quantity $> 0$ (trims order to realised usable), destination overfill ceiling (45-day consumption), no controlled substances.
    - `repair()`: Drops lowest-benefit conflicting orders, trims quantities, and supports `resolve_callback` to re-solve with $P_1 \times 2$ (up to 3 attempts) upon detecting solver one-place violations. Guarantees 0 violations in output.
  - `tests/test_validator_hypothesis.py`: Hypothesis property tests proving validator `repair()` output always satisfies all invariants across randomized snapshots and proposed order sets.
  - Default solver integration in `services/optimizer/optimizer/solver.py` and `services/optimizer/optimizer/routers/plan.py`:
    - Default solver in `POST /plan/run` set to `"qubo"` with graceful fallbacks (`"greedy_f4"`, `"greedy"`).
    - Persists `top_k` samples summary and term breakdown per order (`transfer_order.term_breakdown`).
    - Exposes solver tier, execution timings, penalty parameters, and evidence artifact path in `plan_run.solver_meta` and `summary`.
  - `scripts/sweep_p2.py`: Swept $P_2 \in \{0.5, 1.0, 1.5, 2.0, 3.0\}$ across 5 random seeds (42..46). Documented findings in `docs/DECISIONS.md` (ADR-005): $P_2 = 1.5$ achieves maximum shortage reduction (496.4 units) and expiry avoidance (Rs. 45,628.00) with minimum pre-repair constraint violations (32.20) and 0 post-repair violations.
  - Evidence file written and verified: `evidence/qpiai_runs/20261029_174952_fd9adf47.json`.
  - Monorepo test suite green: **All 31 automated tests passing** across brute-force, property tests, optimizer, and core-api.

### QpiAI Run Evidence Excerpt (`evidence/qpiai_runs/20261029_174952_fd9adf47.json`)

```json
{
  "timestamp": "2026-10-29T17:49:52.472285+00:00",
  "tier": "dwave_neal_sa",
  "time_ms": 474.47,
  "energy": -1.508823,
  "n_vars": 6,
  "variable_names": [
    "cand-LOT-INS-H1-01_c0-H2",
    "cand-LOT-INS-H1-01_c1-H2",
    "cand-LOT-INS-H1-01_c2-H2",
    "cand-LOT-PAR-H3-01_c0-H4",
    "cand-LOT-PAR-H3-01_c1-H4",
    "cand-LOT-PAR-H3-01_c2-H4"
  ],
  "top_k_count": 3,
  "best_sample": {
    "0": 1,
    "1": 1,
    "2": 1,
    "3": 0,
    "4": 1,
    "5": 1
  },
  "top_k_energies": [
    -1.508823,
    -1.502768,
    -1.409491
  ],
  "prior_tier_errors": [
    "qpiai_opt_platform failed: QPIAI_API_KEY is not configured or dummy credential",
    "qpiai_opt_local failed: QPIAI_API_KEY is not configured for LocalProvider"
  ],
  "tier_attempts": [
    {
      "tier": "qpiai_opt_platform",
      "time_ms": 0.01,
      "status": "error",
      "error": "QPIAI_API_KEY is not configured or dummy credential"
    },
    {
      "tier": "qpiai_opt_local",
      "time_ms": 0.01,
      "status": "error",
      "error": "QPIAI_API_KEY is not configured for LocalProvider"
    },
    {
      "tier": "dwave_neal_sa",
      "time_ms": 474.47,
      "status": "success",
      "samples_count": 3
    }
  ]
}
```

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
- `POST /llm/complete`: Central LLM gateway with structured output, prompt registry, validation retries, and replay cache.
- `GET /ai/health`: Model status, primary provider, and 24h rolling metrics.
- `POST /narrate/{order_id}`: Generate grounded order narration with numeric firewall.
- `POST /docs/dta/{order_id}`: Generate printable DTA voucher PDF.
- `POST /docs/credit-memo/{order_id}`: Generate financial credit memo.
- `POST /copilot/chat`: SSE interactive copilot stream.

#### Calling the Gateway from Other Services

All LLM calls across lanes must route through `POST /llm/complete` (via direct port 8003 or gateway `/api/genai/llm/complete`). Services must never import LLM provider SDKs directly (CLAUDE.md §8).

**1. Example HTTP Request (`curl`):**
```bash
curl -X POST http://localhost:8080/api/genai/llm/complete \
  -H "Content-Type: application/json" \
  -d '{
    "purpose": "extraction",
    "prompt_id": "extract_stock",
    "version": 1,
    "input": {
      "text": "Physical count: 50 vials inzulin (reg 100iu) batch LOT-INS-H4-01 exp 19/11/2026"
    },
    "model": "fast"
  }'
```

**2. Example HTTP Response:**
```json
{
  "request_id": "llm-a1b2c3d4e5f6",
  "purpose": "extraction",
  "prompt_id": "extract_stock",
  "version": "1",
  "model": "claude-3-5-haiku-20241022",
  "confidence": 0.95,
  "output": {
    "drug_code": "INS-REG",
    "batch_no": "LOT-INS-H4-01",
    "expiry": "2026-11-19",
    "quantity": 50
  },
  "cached": false,
  "execution_time_sec": 0.8124,
  "ok": true,
  "fallback": false
}
```

**3. Example Python Client Integration (e.g. Ingest-AI / Forecast):**
```python
import httpx
from medbal_common.settings import get_settings

settings = get_settings()

async def call_llm(purpose: str, prompt_id: str, version: int, input_vars: dict, model: str = "fast") -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{settings.GENAI_URL}/llm/complete",
            json={
                "purpose": purpose,
                "prompt_id": prompt_id,
                "version": version,
                "input": input_vars,
                "model": model,
            },
        )
        response.raise_for_status()
        res = response.json()
        if not res.get("ok"):
            # Handle fallback
            raise RuntimeError(f"LLM failure: {res.get('error')}")
        return res["output"]  # Validated structured dictionary
```

**4. Cache and Replay Semantics:**
- `DEMO_MODE=live`: Queries Redis cache first (`sha256(prompt_id@version + model + canonical_json(input))`). On cache miss, calls LLM provider, validates output, and caches result.
- `DEMO_MODE=record`: Always calls LLM provider and refreshes cache.
- `DEMO_MODE=replay`: Serves *only* from cache. On cache miss, immediately returns `{ "ok": false, "fallback": true }` without performing any network call.

### 4. `forecast` (Port 8004 / Gateway: `/api/forecast/*`)
- `POST /forecast/run`: Trigger Holt-Winters consumption forecast calculation
- `GET /forecast?facility=&drug=`: Query computed consumption rates
- `GET /forecast/backtest`: Get backtest MAPE and RMSE accuracy reports

### 5. `optimizer` (Port 8005 / Gateway: `/api/optimizer/*`)
- `POST /plan/run`: Run redistribution optimizer (`mode: live|whatif|eval`, provisional greedy_f4 solver, persisted via core-api)
- `GET /plan/{id}`: Retrieve optimization plan (proxies to core-api or local plan store)
- `GET /plan/{id}/benchmark`: Compare solver vs classical exact MILP gap
- `GET /plan/{id}/regret?order_id=`: Inspect regret analysis and alternate destinations
- `GET /whynot?facility=&drug=`: Explain non-allocation with F1–F6 rule breakdown
- `POST /whatif`: Simulate allocation scenario without persistence
- `POST /eval/replay`: Replay historical simulation days
- `GET /eval/{id}`: Get evaluation run details

#### Optimizer Public Functions & Modules Summary

All mathematical computations are pure functions with zero I/O so they can be reused across QUBO solvers (P10), copilot explainability (P14), and historical evaluation replays (P19):

1. **`optimizer.feasibility`** ([`optimizer/feasibility.py`](file:///services/optimizer/optimizer/feasibility.py)):
   - `check_f1_rule(source_id: str, dest_id: str) -> (bool, Optional[str])`: Verifies that source and destination are distinct facilities.
   - `check_f2_rule(route: Optional[dict]) -> (bool, Optional[str])`: Verifies that a valid transit route exists and its status is not marked `unsafe` or `closed`.
   - `check_f3_rule(is_cold_drug, dest_has_cold_storage, route_is_cold, vehicles) -> (bool, Optional[str])`: Enforces cold chain requirements: destination cold storage availability, cold route compliance, and availability of at least one active cold vehicle operating within 2°C–8°C without temperature excursion.
   - `check_f4_rule(lot_qty, lot_expiry, today, destination_daily_rate, transit_hours, min_residual_days, destination_stock_expiring_before, buffer_days=2) -> (bool, Optional[str], int)`: Validates that arrival residual shelf life $\ge \text{drug.min\_residual\_days}$, effective consumption window $> 0$, and calculates usable units subtracting destination stock expiring before the lot.
   - `check_f5_rule(chunk_qty: int, transferable_qty: int) -> (bool, Optional[str])`: Verifies that transferred quantity does not violate the source facility's protected inventory reserve.
   - `check_f6_rule(drug_code: str, is_controlled: bool) -> (bool, Optional[str])`: Prohibits automated transfers of Schedule X controlled narcotics (e.g., `MOR-10` morphine) without special drug-controller permits.
   - `evaluate_feasibility(...) -> (bool, List[dict], int)`: Evaluates all rules F1–F6 simultaneously, accumulating all rule violations for regret analysis and copilot explainability.

2. **`optimizer.candidates`** ([`optimizer/candidates.py`](file:///services/optimizer/optimizer/candidates.py)):
   - `split_lot_into_chunks(total_qty: int, pack_size: int = 1, lot_meta: Optional[dict] = None) -> List[Chunk]`: Splits transferable lot quantity into $\le 3$ chunks (50%, 25%, 25%) rounded to pack size, dropping any non-positive chunks.
   - `calculate_sequential_chunk_usable(chunk_qty: int, dest_capacity: int, allocated_so_far: int) -> int`: Sequentially bounds usable quantity for chunk $j$ as $\min(q_j, U_{ld} - \sum_{i < j} u_i)$.
   - `generate_candidates(snapshot: dict, top_k_per_chunk: int = 3) -> (List[Candidate], List[Candidate])`: Evaluates all (chunk, destination) pairs against F1–F6, computes rewards $s = \text{usable} \times \text{unit\_cost}$ and trip cost share $c$, filters top-3 feasible destinations per chunk by $(s - c)$, and retains all infeasible pairs for regret tracking.

3. **`optimizer.baselines`** ([`optimizer/baselines.py`](file:///services/optimizer/optimizer/baselines.py)):
   - `greedy_phone_call(snapshot: dict) -> List[TransferOrder]`: Models current manual hospital practice; sorts shortages by VEN then size descending, matches nearest source with at-risk stock, validates F1–F3 only, and demonstrates the risk of moving waste.
   - `greedy_f4(snapshot: dict) -> List[TransferOrder]`: Safe greedy allocator enforcing full F1–F6 validation, reserve protection, and usable quantity capping that guarantees zero waste moved.

4. **`optimizer.metrics`** ([`optimizer/metrics.py`](file:///services/optimizer/optimizer/metrics.py)):
   - `calculate_plan_metrics(orders: List[TransferOrder], snapshot: dict) -> dict`: Computes FEFO-grounded shortage reduction, expiry avoided units and INR, waste moved units and INR, unique trips, total km, transport cost, and net benefit.

5. **`optimizer.snapshot`** ([`optimizer/snapshot.py`](file:///services/optimizer/optimizer/snapshot.py)):
   - `fetch_snapshot(core_api_url: Optional[str] = None) -> dict`: Fetches district snapshot from `core-api /snapshot` with fast fallback to fixture.
   - `SnapshotIndex`: Indexed in-memory data structure providing $O(1)$ lookups for facilities, drugs, routes, vehicles, lots, positions, and forecasts.

6. **`optimizer.positions`** ([`optimizer/positions.py`](file:///services/optimizer/optimizer/positions.py)):
   - `compute_positions_for_snapshot(snapshot: dict) -> List[dict]`: Computes FEFO stock positions, effective stock, at-risk units, and reserve protection across all facility × drug combinations.

7. **`optimizer.solver`** ([`optimizer/solver.py`](file:///services/optimizer/optimizer/solver.py)):
   - `run_planning_pipeline(mode="live", overrides=None, solver_choice="greedy_f4") -> dict`: Orchestrates the 6-stage planning pipeline, publishes `plan.progress` stage updates to Redis Streams, persists to `core-api POST /plans`, and emits `plan.completed`.

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

## CP1 Issues & End-to-End Walking Skeleton Verification

### Pass/Fail Table

| Step | Operation / Test Case | Target / Service | Status | Owning Lane (CLAUDE.md §3) | Failure Summary |
|---|---|---|---|---|---|
| **Step 1a** | `make down -v` | Compose Stack | **FAIL** | L1 (Infrastructure) | `make` / `docker` command not found on Windows host |
| **Step 1b** | `make build` | Docker Images | **FAIL** | L1 (Infrastructure) | `docker compose build` cannot execute without Docker daemon |
| **Step 1c** | `make seed` | Data Seed | **PARTIAL** | L1 (Data / Postgres) | `python data/seed/generate.py` passed; `psql` insert blocked by absent Postgres container |
| **Step 1d** | `make up` | Microservices | **FAIL** | L1 (Infrastructure) | Cannot launch containers without Docker |
| **Step 2** | `test_01_reset_sim_seed_42` | `POST /api/sim/reset?seed=42` | **FAIL** | L4 (Sim-Control) / L1 (Gateway) | `ConnectError: [WinError 10061]` connection refused on port 8080 |
| **Step 3** | `test_02_start_clock_and_wait_2_sim_days` | `POST /api/sim/clock/start` & poll | **FAIL** | L4 (Sim-Control) / L1 (Gateway) | `ConnectError: [WinError 10061]` connection refused on port 8080 |
| **Step 4** | `test_03_assert_lots_exist_for_h1_to_h4` | `GET /api/core/lots` | **FAIL** | L3 (Ingest-AI) / L1 (Core-API) | `ConnectError: [WinError 10061]` connection refused on port 8080 |
| **Step 5** | `test_04_run_plan_and_assert_orders` | `POST /api/optimizer/plan/run` | **FAIL** | L2 (Optimizer) | `ConnectError: [WinError 10061]` connection refused on port 8080 |
| **Step 6** | `test_05_audit_verify` | `GET /api/core/audit/verify` | **FAIL** | L1 (Core-API) | `ConnectError: [WinError 10061]` connection refused on port 8080 |

---

### Detailed Failures, Root Causes & Fixes by Lane

#### 1. L1 (Infrastructure, Gateway & Core-API)
- **Failure 1.1**: Host execution environment lacks Docker and GNU Make.
  - *Exact Error*: `docker : The term 'docker' is not recognized as the name of a cmdlet...` and `make : The term 'make' is not recognized...`
  - *Root Cause*: On the current Windows development laptop, Docker Desktop and GNU Make are not installed or configured in the system PATH.
  - *Suggested Fix (L1)*: Install Docker Desktop with WSL2 backend or run the stack inside a Linux development VM. Alternatively, provide a native PowerShell orchestration script (`scripts/run_stack.ps1`) for Windows development.
- **Failure 1.2**: Database password mismatch between `.env.example` and `docker-compose.yml`.
  - *Exact Error*: `.env.example` specified `DATABASE_URL=...medbal:medbal@postgres:5432...` while `docker-compose.yml` configured `POSTGRES_PASSWORD=medbal_secret_pw`.
  - *Fix Applied (Shared Code)*: Updated `.env.example` line 9 to use `medbal_secret_pw` across all service connections.
- **Failure 1.3**: Audit verification endpoint unreachable.
  - *Exact Error*: `httpx.ConnectError: [WinError 10061]` on `GET /api/core/audit/verify`.
  - *Suggested Fix (L1)*: Once container stack is running, verify that `core-api`'s `verify_audit` endpoint verifies the SHA-256 tamper-evident audit hash chain over PostgreSQL `audit_log`.

#### 2. L2 (Optimizer)
- **Failure 2.1**: TransferOrder schema mismatch for `usable_quantity`.
  - *Exact Error / Observation*: `services/optimizer/optimizer/models.py` defines `TransferOrder` without `usable_quantity`, and `to_dict()` exports only `"quantity"`. However, `contracts/openapi/components.yaml` lines 322-324 explicitly requires `usable_quantity: integer`.
  - *Root Cause*: `TransferOrder` dataclass in optimizer did not store the computed usable quantity from `greedy_f4`.
  - *Suggested Fix (L2)*: In `services/optimizer/optimizer/models.py`, add `usable_quantity: int` to `TransferOrder` and export `"usable_quantity": self.usable_quantity` in `to_dict()`. Update `greedy_f4` in `services/optimizer/optimizer/baselines.py` to pass `usable_quantity=transfer_qty`.

#### 3. L3 (Ingest-AI)
- **Failure 3.1**: Lot propagation to core-api for H1..H4.
  - *Exact Error / Observation*: `test_03_assert_lots_exist_for_h1_to_h4` expects lots to exist for all four facilities in `core-api`.
  - *Root Cause*: When running dynamically, `ingest-ai` must receive `clock.tick` from Redis, pull H1 (FHIR) and H2 (CSV), and process inbound push reports from H3 (Chat) and H4 (Text), then upsert them to `core-api POST /lots/upsert-batch`.
  - *Suggested Fix (L3)*: Ensure `ingest-ai` starts after Redis and PostgreSQL, and verify that `handle_clock_tick` completes polling within the 30s sim day cycle without unhandled timeouts.

#### 4. L4 (ColdChain & Sim-Control)
- **Failure 4.1**: `sim-control` missing explicit `REDIS_URL` and `depends_on: redis` in compose.
  - *Exact Error / Observation*: `sim-control` attempted to publish `clock.tick` events to `redis://redis:6379/0` on tick rollover, but in `docker-compose.yml` it lacked `REDIS_URL` in its environment block and did not specify `depends_on: redis`.
  - *Fix Applied (Shared Code)*: Added `REDIS_URL: redis://redis:6379/0` and `depends_on: redis: condition: service_healthy` to `sim-control` in `docker-compose.yml`.
- **Failure 4.2**: `sim-hospital-h1` race condition against Redis.
  - *Exact Error / Observation*: Hospital nodes start background tick consumers during `lifespan`. If Redis is not yet healthy, the consumer loop logs an error and terminates.
  - *Fix Applied (Shared Code)*: Added `depends_on: redis: condition: service_healthy` to `sim-hospital-h1` in `docker-compose.yml`.

---

---

## P11: QAOA Max-Cut Zoning, Exact MILP Baseline, Scale-Mode District, & Solver Benchmarks

### 1. Quantum Architecture & QpiAI SDK Introspection
- **SDK Version**: `qpiai_quantum==0.7.5`.
- **Introspection Reference**: `docs/QPIAI_QCLOUD_NOTES.md`.
- **API Guard**: Introspected `QpiAIQuantumAuth.login()` and `verify_api_key()`. When `QPIAI_QUANTUM_API_KEY` is unset or invalid, the solver transparently logs the error and falls back to local simulation without crashing.
- **Circuit Gate Signatures**:
  - $R_{ZZ}(\theta)$: `qc.rzz(qubit1: int, qubit2: int, theta: float)` strictly takes qubit indices first, angle second.
  - $R_X(\theta)$: `qc.rx(qubit: int, theta: float)` takes qubit index first, angle second.
- **Bitstring Convention**: `StatevectorSimulator.run(qc).get_counts()` returns little-endian bitstrings where qubit $i$ corresponds to `bitstring[-(i + 1)]`.
- **MaxCutPort & Solver Hierarchy** (`services/optimizer/optimizer/qaoa/`):
  1. `QCloudSimulatorMaxCut`: Remote execution on QpiAI QCloud (guarded by API key).
  2. `QSVLocalMaxCut`: Local `StatevectorSimulator` with COBYLA variational optimization over $(\gamma, \beta)$ parameters.
  3. `ExactBruteForceMaxCut`: Global optimum enumeration for $n \le 16$.
  4. `NetworkXGreedyMaxCut`: Classical 1-flip greedy local search heuristic.
- **Evidence Persistence**: Every run records an immutable JSON audit log to `evidence/qcloud_runs/<ts>_<hash>.json`.

### 2. Graph Zoning: QAOA Max-Cut vs Euclidean K-Means
- **Graph Construction** (`services/optimizer/optimizer/zoning.py`):
  - **Live Mode**: 5 facilities as nodes ($n=5$). Edge weight $w_{uv} = \text{distance\_km} \times \text{transit\_hours}$, representing transit impedance. Heavy edges denote travel bottlenecks or terrain barriers.
  - **Scale Mode**: 5 taluk super-nodes (`Anekal`, `Bengaluru East`, `Bengaluru North`, `Bengaluru South`, `Yelahanka`), aggregating inter-taluk route transit costs.
- **Max-Cut Separation**:
  - By maximizing cut value, Max-Cut places facilities separated by large transit impedance or closed routes into different zones, keeping tightly connected facilities within the same zone.
- **Empirical Comparison against Coordinate K-Means ($k=2$)**:
  - **QAOA Cut Value**: **3.8660** vs **K-Means**: **2.7123** (**+42.5% cut improvement**).
  - **Intra-Zone Transit Impedance**: **1.6198** for QAOA vs **2.7735** for K-Means (**-41.6% reduction in internal transit impedance**).

### 3. Scale-Mode Synthetic District (40 Facilities, In-Memory)
- **Generator** (`services/optimizer/optimizer/scale_mode.py`):
  - 40 health facilities across 5 taluks (8 facilities per taluk: 1 District/General Hospital, 2 Taluk Hospitals, 3 CHCs, 2 PHCs).
  - 90 transit routes with realistic intra-taluk and inter-taluk transit times and distances.
  - 13 canonical drugs matching seed data.
  - 79 at-risk medicine lots, 520 position records, and 520 forecast series.
  - Strictly in-memory: enables testing large-scale allocation pipelines without a PostgreSQL or Redis database.
- **API Wiring**: `POST /plan/run` with payload `{"mode": "eval", "scale": 40}` triggers the scale mode pipeline.

### 4. Zone Decomposition Pipeline
- **Decomposition Engine** (`services/optimizer/optimizer/decomposition.py`):
  1. Partition candidates into **Zone 0** (internal to zone 0), **Zone 1** (internal to zone 1), and **Boundary** (cross-zone).
  2. Solve Zone 0 QUBO independently using active solver tier.
  3. Solve Zone 1 QUBO independently using active solver tier.
  4. Compute residual shortages and remaining transferable lot stock.
  5. Formulate and solve Boundary QUBO on residual candidates.
  6. Merge orders, assign sequential DTA order IDs, and execute post-decomposition FEFO validator repair.

### 5. Exact Classical MILP Baseline (Google OR-Tools CP-SAT)
- **Engine** (`services/optimizer/optimizer/milp.py`):
  - Models redistribution as an exact integer programming problem.
  - Binary decision variable $x_i \in \{0, 1\}$ per candidate chunk.
  - Exact quadratic product linearization: $z_{ij} = x_i \cdot x_j$ via `model.add_multiplication_equality(z_{ij}, [x_i, x_j])`.
  - Integer scaling ($\times 10^6$) of float matrix coefficients $Q_{ij}$ and offset.
  - 20-second timeout with 4 parallel worker threads.
- **Verification**: Verified that CP-SAT matches the global minimum of brute-force exhaustive enumeration across all 8 test instances with zero gap ($0.0\%$).

### 6. Benchmark Endpoint (`GET /plan/{id}/benchmark`)
- **API Contract Compliance**: Fully implements the OpenAPI schema `[plan_id, solver_tier, milp_optimal_energy, solver_energy, optimality_gap_percent, solver_time_sec, milp_time_sec]`.
- **Policy Comparison Table**: Evaluates 5 policies on the identical snapshot:
  1. `no-transfer`: 0 orders, zero transport cost, baseline shortage/expiry.
  2. `greedy`: Phone-call heuristic (F1–F3 only, ignores shelf life, moves waste).
  3. `greedy_f4`: Safe greedy allocator (full F1–F6, zero waste moved).
  4. `qubo`: Active solver tier (QpiAI Opt Platform / Neal SA / Greedy Descent).
  5. `milp`: Global exact optimum via OR-Tools CP-SAT.
- **Metrics Evaluated**: Policy name, objective value (energy), shortage reduction, expiry avoided ₹, waste moved units, vehicle trips, and solve time in seconds.
- **Optimality Gap**:
  $$\text{gap} = \frac{|E_{\text{solver}} - E_{\text{milp}}^*|}{|E_{\text{milp}}^*|} \times 100\%$$
- **Zoning Report**: Embedded comparison of QAOA Max-Cut vs K-Means clustering.

---

### Verification & Test Suite Summary

All 40 tests passed cleanly across the entire optimizer test suite:
- `tests/test_maxcut_small_graphs.py`: **14 passed** (Exact Max-Cut on Triangle, 4-Cycle, Path P4, K4; QAOA QSVLocal on Triangle and 4-Cycle; NetworkX baseline; MILP exact match on all 8 tiny instances).
- `tests/test_qubo_bruteforce.py`: **8 passed** (All 8 QUBO v3 formulation instances).
- `tests/test_validator_hypothesis.py`: **1 passed** (Hypothesis stateful invariant validation).
- `services/optimizer/tests/test_api.py`: **4 passed** (Plan run, retrieve, benchmark, regret, whynot, whatif, scale mode 40 facilities, and benchmark table).
- `services/optimizer/tests/test_feasibility_f4.py`: **9 passed** (All F1–F6 feasibility invariants).
- `services/optimizer/tests/test_optimizer.py`: **4 passed** (Chunk splitting, sequential usable quantity, controlled drug exclusion, greedy comparison).

---

## Decisions
- See [docs/DECISIONS.md](DECISIONS.md) (ADR-001 through ADR-008)

## Requests & Next Steps for Lanes
- **L1 (Core)**: Added `POST /vehicles/{id}/status` and `/internal/coldchain/vehicle-status` to `contracts/openapi/core-api.yaml` and implemented in `services/core-api/src/routers/master.py` to allow coldchain status updates to mark vehicles and routes safe/unsafe with audit tracking.
- **L2 (Optimizer)**: Integrate QUBO solver and QpiAI adapters in `services/optimizer`.
- **L3 (AI & Forecast)**: Wire GenAI gateway and Holt-Winters forecasting engine.
- **L4 (ColdChain & Sim)**: [COMPLETED] `sim-control`, `sim-hospital` (all 4 styles), `sensors`, and `coldchain` fully implemented and tested.
