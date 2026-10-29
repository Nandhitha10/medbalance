# CLAUDE.md — MedBalance-Q (Quant-A-Maze 3.0, GENAI-04)

You are working on MedBalance-Q: a district-level system that redistributes near-expiry essential medicines, lot by lot, from facilities that will waste them to facilities that are short and can use them before expiry. Read this file fully before every task. It is the single source of truth for architecture and conventions across four laptops.

## 1. Problem statement (verbatim intent)
Some facilities stock out of essential drugs while nearby facilities hold eligible lots close to expiry. Redistribution is constrained by actual inventories, drug identity, minimum stock reserve, shelf life, permitted transport and cold chain. Deliver auditable lot-level transfer orders with quantities, source/destination, temperature requirements, shortage reduction and expected expiry avoidance. Evaluate actual stockout reductions, expiry and inventory feasibility.

## 2. Golden rule
LLMs read and explain; deterministic code decides. An LLM never decides feasibility, never invents a drug code (it chooses from retrieved candidates or returns UNKNOWN), and never states a number that is not in the facts it was given.

## 3. Services (docker compose, network `medbal`)
| service | port | owner | job |
|---|---|---|---|
| gateway (nginx) | 8080 | L1 | routes /api/<service>/* and serves web |
| core-api | 8001 | L1 | facilities, drugs, lots, positions, orders, approvals, custody, audit chain, SSE /events |
| ingest-ai | 8002 | L3 | hospital adapters, LLM extraction with grounding, anomaly gate, review queue |
| genai | 8003 | L3 | LLM gateway (/llm/complete), narration+firewall, DTA/credit-memo PDFs, copilot |
| forecast | 8004 | L3 | Holt-Winters baseline × LLM context multiplier |
| optimizer | 8005 | L2 | positions, feasibility F1–F6, candidates, QUBO, QpiAI Opt, QCloud QAOA zoning, baselines, validator, regret, what-if, replay eval |
| coldchain | 8006 | L4 | MQTT consumer, excursion rules, route/vehicle status |
| sim-control | 8100 | L4 | sim clock, scenarios, reset(seed), outbreak/campaign signals |
| sim-hospital-h1..h4 | 8101–8104 | L4 | one image, 4 configs; each hospital's own SQLite stock + report format |
| sensors | — | L4 | simulated temperature sensors → MQTT |
| postgres 16 / redis 7 / mosquitto 2 | 5432 / 6379 / 1883 | L1/L4 | data, event bus (Redis Streams), MQTT |

## 4. Repository layout
contracts/ (openapi/*.yaml, events.md, fixtures/*.json) · libs/medbal_common/ · services/<name>/ · web/ · db/init/ · data/seed/ · prompts/ · evals/ · evidence/ · tests/ · docs/ (PROGRESS.md, DECISIONS.md, RTM.md, DEMO_SCRIPT.md)

## 5. Domain glossary
- Lot: (facility, drug_code, batch_no, expiry, qty). Quantities are integer base units (tablet, vial, sachet).
- FEFO: first-expiry-first-out. Consumption always uses the earliest-expiring lot first.
- Effective stock: units that will be consumed before their expiry under FEFO at the forecast rate.
- At-risk: units that will expire unconsumed under FEFO.
- Reserve R = max(ceil(r·min_reserve_days), ceil(r·lead_time·1.2)), protected from the longest-dated lots.
- Shortage n = max(0, ceil(r·target_days) − effective stock).
- Chunk: part of a lot's transferable qty (≤3 chunks: 50/25/25%, pack-rounded).
- Usable(k,d) = min(q_k, max(0, r_d·(expiry − today − transit − buffer) − S_d(<expiry))) where S_d(<expiry) is destination stock expiring before the lot.
- VEN: Vital/Essential/Non-essential → π = 3/2/1.
- DTA: Drug Transfer Advice voucher (modelled on NTEP Ni-kshay Aushadhi DTA). Number format DTA/BLR-U/2026/000123. Never call it "Form 19".
- Feasibility rules: F1 identity, F2 route ok, F3 cold chain (cold route + cold vehicle without excursion + destination cold storage ok), F4 usable>0 and residual shelf life ≥ drug.min_residual_days, F5 reserve, F6 not controlled.

## 6. QUBO (v3) — x_i=1 means chunk k → destination d
H = −Σ(s_i − c_i)x_i + P1·Σ_k Σ_{d<d'} x_kd x_kd' + P2·Σ_{d,g} π_g(Σ_{i∈(d,g)} (u_i/n_dg) x_i − 1)² + P3·Σ(x_(l,j),d − x_(l,j),d·x_(l,j−1),d) − γ·Σ_{same src,dst,vehicle} x_i x_i'
Rewards normalised to max 1. Defaults: P1=2, P2=1.5, P3=1, γ=0.3×min normalised trip cost. Shortage term only when n>0. ≤150 variables per QUBO (top-3 destinations per chunk).

## 7. QpiAI usage (verified in our environment)
- QCloud: `pip install qpiai-quantum`; `from qpiai_quantum import QpiAIQuantumAuth as Auth; Auth.login(KEY); Auth.verify_api_key()`. Used for QAOA Max-Cut zoning. Tiers: cloud simulator → QpiAI-QSV-Local → exact brute force → NetworkX.
- QpiAI Opt: `pip install qpiai-opt` (classes seen: Client, QUBOProblem, QUBOSolver, LocalProvider). Used for QUBO allocation. Tiers: platform → LocalProvider → dwave-neal SA → greedy.
- Before writing QpiAI code, introspect the installed package (`python -c "import qpiai_opt, inspect; ..."`) and wrap it behind our own `SolverPort` / `MaxCutPort` interfaces. Never guess signatures.
- Every QpiAI call writes evidence JSON to evidence/qpiai_runs/ (tier, inputs hash, energy, time, result).
- We do not claim quantum advantage. We report the gap to an exact MILP optimum.

## 8. GenAI rules
- All LLM calls go through genai `POST /llm/complete` {purpose, prompt_id, version, input}. No service imports a provider SDK directly.
- Prompts live in prompts/<id>_v<n>.yaml with: system, user_template, json_schema, model (fast|smart), temperature, max_tokens.
- Provider: Claude by default (LLM_MODEL_FAST, LLM_MODEL_SMART from .env); Gemini and Ollama adapters optional.
- Structured output only; validate with Pydantic; max 2 retries with the validation error; then fallback.
- DEMO_MODE=live|record|replay. Cache key = sha256(prompt_id@version + model + canonical_json(input)).
- Every LLM-produced record stores model, prompt_id@version, confidence.
- Narration passes the numeric grounding firewall or is replaced by the template.

## 9. Engineering conventions
- Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0, uv, ruff. TypeScript strict, React 18, Vite, Tailwind, shadcn/ui, TanStack Query.
- "Today" comes from the sim clock (`medbal_common.clock.today()`), never datetime.now() in domain logic. Timezone Asia/Kolkata.
- Every state change calls `medbal_common.audit.append(...)` in the same DB transaction.
- Every service: GET /health, structured JSON logs, settings from env, runs with USE_FIXTURES=1 against contracts/fixtures.
- Every external call has a timeout and a fallback; the fallback tier is recorded and shown in the UI.
- Tests: pytest (+ Hypothesis for invariants). A task is not done until its tests pass and `docker compose build <service>` succeeds.
- Do not edit another service's code. If you need a change in another service, change contracts/ and note it in docs/PROGRESS.md under "Requests".
- Synthetic data only; facility names prefixed SIM-. No patient data.

## 10. Definition of done (every task)
1. Code + tests written; `make test` (or the service's pytest) passes.
2. Service builds and starts healthy in compose.
3. Contracts/fixtures updated if any interface changed.
4. docs/PROGRESS.md updated: what was done, how to verify, decisions, open issues, requests to other lanes.
5. One commit per logical change with a clear message.
