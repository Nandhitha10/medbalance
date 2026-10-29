-- MedBalance-Q PostgreSQL Schema
-- Database initialization script 001_schema.sql

-- Drop existing tables in reverse dependency order
DROP TABLE IF EXISTS chat_message CASCADE;
DROP TABLE IF EXISTS chat_session CASCADE;
DROP TABLE IF EXISTS llm_call CASCADE;
DROP TABLE IF EXISTS audit_log CASCADE;
DROP TABLE IF EXISTS credit_memo CASCADE;
DROP TABLE IF EXISTS custody_event CASCADE;
DROP TABLE IF EXISTS regret_entry CASCADE;
DROP TABLE IF EXISTS transfer_order CASCADE;
DROP TABLE IF EXISTS candidate CASCADE;
DROP TABLE IF EXISTS plan_run CASCADE;
DROP TABLE IF EXISTS sensor_reading CASCADE;
DROP TABLE IF EXISTS vehicle CASCADE;
DROP TABLE IF EXISTS route CASCADE;
DROP TABLE IF EXISTS policy CASCADE;
DROP TABLE IF EXISTS forecast CASCADE;
DROP TABLE IF EXISTS consumption_daily CASCADE;
DROP TABLE IF EXISTS extraction_item CASCADE;
DROP TABLE IF EXISTS stock_report CASCADE;
DROP TABLE IF EXISTS lot CASCADE;
DROP TABLE IF EXISTS drug_alias CASCADE;
DROP TABLE IF EXISTS drug CASCADE;
DROP TABLE IF EXISTS facility CASCADE;

-- 1. Facility
CREATE TABLE facility (
    id VARCHAR(64) PRIMARY KEY,
    code VARCHAR(32) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    level VARCHAR(32) NOT NULL, -- DH, TH, CHC, PHC, WH
    taluk VARCHAR(64),
    district VARCHAR(64) DEFAULT 'Bengaluru Urban',
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    adapter_type VARCHAR(32) NOT NULL, -- fhir, csv, chat, text
    language VARCHAR(32) DEFAULT 'en',
    cold_storage_ok BOOLEAN NOT NULL DEFAULT true,
    cold_storage_note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Drug
CREATE TABLE drug (
    code VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(1) NOT NULL CHECK (category IN ('V', 'E', 'N')), -- Vital, Essential, Non-essential
    unit VARCHAR(64) NOT NULL, -- vial, tablet, ampoule, sachet, bottle
    pack_size INT NOT NULL DEFAULT 1 CHECK (pack_size > 0),
    cold_chain BOOLEAN NOT NULL DEFAULT false,
    min_temp_c DOUBLE PRECISION,
    max_temp_c DOUBLE PRECISION,
    unit_cost_inr NUMERIC(10, 2) NOT NULL CHECK (unit_cost_inr >= 0),
    min_residual_days INT NOT NULL DEFAULT 30 CHECK (min_residual_days > 0),
    is_controlled BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Drug Alias (Multilingual and common misspellings)
CREATE TABLE drug_alias (
    id BIGSERIAL PRIMARY KEY,
    drug_code VARCHAR(64) NOT NULL REFERENCES drug(code) ON DELETE CASCADE,
    alias VARCHAR(255) NOT NULL,
    language VARCHAR(16) DEFAULT 'en',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Lot (Current Inventory)
CREATE TABLE lot (
    id BIGSERIAL PRIMARY KEY,
    facility_id VARCHAR(64) NOT NULL REFERENCES facility(id) ON DELETE CASCADE,
    drug_code VARCHAR(64) NOT NULL REFERENCES drug(code) ON DELETE CASCADE,
    batch_no VARCHAR(128) NOT NULL,
    expiry DATE NOT NULL,
    quantity INT NOT NULL CHECK (quantity >= 0),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_facility_drug_batch UNIQUE (facility_id, drug_code, batch_no)
);

-- 5. Stock Report (Inbound reports from facilities)
CREATE TABLE stock_report (
    id VARCHAR(64) PRIMARY KEY,
    facility_id VARCHAR(64) NOT NULL REFERENCES facility(id) ON DELETE CASCADE,
    received_at TIMESTAMPTZ NOT NULL,
    source_type VARCHAR(32) NOT NULL, -- fhir, csv, pdf, excel, text, chat
    file_name VARCHAR(255),
    status VARCHAR(32) NOT NULL DEFAULT 'RECEIVED', -- RECEIVED, PROCESSED, NEEDS_REVIEW, FAILED
    raw_content TEXT,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- 6. Extraction Item (Extracted lots from reports)
CREATE TABLE extraction_item (
    id BIGSERIAL PRIMARY KEY,
    report_id VARCHAR(64) NOT NULL REFERENCES stock_report(id) ON DELETE CASCADE,
    raw_text TEXT NOT NULL,
    drug_code VARCHAR(64) REFERENCES drug(code),
    batch_no VARCHAR(128),
    expiry DATE,
    quantity INT CHECK (quantity >= 0),
    confidence NUMERIC(4, 3),
    is_anomalous BOOLEAN DEFAULT false,
    anomaly_reason TEXT,
    review_status VARCHAR(32) DEFAULT 'PENDING',
    suggested_patch JSONB DEFAULT '{}'::jsonb
);

-- 7. Consumption Daily (Historical daily consumption)
CREATE TABLE consumption_daily (
    id BIGSERIAL PRIMARY KEY,
    facility_id VARCHAR(64) NOT NULL REFERENCES facility(id) ON DELETE CASCADE,
    drug_code VARCHAR(64) NOT NULL REFERENCES drug(code) ON DELETE CASCADE,
    date DATE NOT NULL,
    quantity INT NOT NULL CHECK (quantity >= 0),
    CONSTRAINT uq_consumption_facility_drug_date UNIQUE (facility_id, drug_code, date)
);

-- 8. Forecast (Consumption projections)
CREATE TABLE forecast (
    id BIGSERIAL PRIMARY KEY,
    facility_id VARCHAR(64) NOT NULL REFERENCES facility(id) ON DELETE CASCADE,
    drug_code VARCHAR(64) NOT NULL REFERENCES drug(code) ON DELETE CASCADE,
    forecast_date DATE NOT NULL,
    baseline_daily_rate NUMERIC(10, 3) NOT NULL CHECK (baseline_daily_rate >= 0),
    llm_multiplier NUMERIC(6, 3) NOT NULL DEFAULT 1.0,
    effective_daily_rate NUMERIC(10, 3) NOT NULL CHECK (effective_daily_rate >= 0),
    target_days INT NOT NULL DEFAULT 14,
    projected_consumption INT NOT NULL CHECK (projected_consumption >= 0),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 9. Policy (Inventory management parameters)
CREATE TABLE policy (
    id BIGSERIAL PRIMARY KEY,
    facility_id VARCHAR(64) NOT NULL REFERENCES facility(id) ON DELETE CASCADE,
    drug_code VARCHAR(64) NOT NULL REFERENCES drug(code) ON DELETE CASCADE,
    min_reserve_days INT NOT NULL DEFAULT 7,
    target_days INT NOT NULL DEFAULT 21,
    max_stock_days INT NOT NULL DEFAULT 60,
    lead_time_days INT NOT NULL DEFAULT 3,
    CONSTRAINT uq_policy_facility_drug UNIQUE (facility_id, drug_code)
);

-- 10. Route (Transit between facilities)
CREATE TABLE route (
    id VARCHAR(128) PRIMARY KEY,
    source_id VARCHAR(64) NOT NULL REFERENCES facility(id) ON DELETE CASCADE,
    destination_id VARCHAR(64) NOT NULL REFERENCES facility(id) ON DELETE CASCADE,
    distance_km NUMERIC(8, 2) NOT NULL,
    transit_days INT NOT NULL DEFAULT 1 CHECK (transit_days >= 1),
    transit_hours NUMERIC(6, 2) NOT NULL,
    cost_inr NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    cold_capable BOOLEAN NOT NULL DEFAULT false,
    status VARCHAR(32) DEFAULT 'active',
    status_reason TEXT
);

-- 11. Vehicle (Transport fleet)
CREATE TABLE vehicle (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    vehicle_type VARCHAR(64) NOT NULL, -- Ambient Van, Refrigerated Van, Two-Wheeler
    cold_capable BOOLEAN NOT NULL DEFAULT false,
    is_active BOOLEAN NOT NULL DEFAULT true,
    cost_per_km_inr NUMERIC(8, 2) NOT NULL DEFAULT 15.00
);

-- 12. Sensor Reading (Cold chain telemetry)
CREATE TABLE sensor_reading (
    id BIGSERIAL PRIMARY KEY,
    vehicle_id VARCHAR(64) REFERENCES vehicle(id),
    facility_id VARCHAR(64) REFERENCES facility(id),
    device_id VARCHAR(64) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    temperature_c NUMERIC(5, 2) NOT NULL,
    humidity_pct NUMERIC(5, 2),
    battery_pct INT,
    is_excursion BOOLEAN DEFAULT false
);

-- 13. Plan Run (Optimization run records)
CREATE TABLE plan_run (
    id VARCHAR(64) PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'COMPLETED',
    mode VARCHAR(32) NOT NULL DEFAULT 'live',
    solver_tier VARCHAR(64) NOT NULL DEFAULT 'greedy',
    execution_time_sec NUMERIC(8, 3) NOT NULL DEFAULT 0.0,
    total_orders INT NOT NULL DEFAULT 0,
    total_units INT NOT NULL DEFAULT 0,
    shortage_reduction INT NOT NULL DEFAULT 0,
    expiry_avoided INT NOT NULL DEFAULT 0,
    total_savings_inr NUMERIC(12, 2) DEFAULT 0.00,
    summary JSONB DEFAULT '{}'::jsonb
);

-- 14. Candidate (Transfer candidates evaluated by optimizer)
CREATE TABLE candidate (
    id VARCHAR(64) PRIMARY KEY,
    plan_run_id VARCHAR(64) NOT NULL REFERENCES plan_run(id) ON DELETE CASCADE,
    lot_batch_no VARCHAR(128) NOT NULL,
    drug_code VARCHAR(64) NOT NULL REFERENCES drug(code),
    source_facility_id VARCHAR(64) NOT NULL REFERENCES facility(id),
    destination_facility_id VARCHAR(64) NOT NULL REFERENCES facility(id),
    chunk_quantity INT NOT NULL CHECK (chunk_quantity > 0),
    usable_quantity INT NOT NULL CHECK (usable_quantity >= 0),
    is_feasible BOOLEAN NOT NULL DEFAULT true,
    feasibility_flags JSONB DEFAULT '{}'::jsonb,
    reward NUMERIC(8, 4) DEFAULT 0.0,
    cost NUMERIC(8, 4) DEFAULT 0.0
);

-- 15. Transfer Order (DTA vouchers)
CREATE TABLE transfer_order (
    id VARCHAR(64) PRIMARY KEY, -- Format: DTA/BLR-U/2026/000123
    plan_run_id VARCHAR(64) REFERENCES plan_run(id) ON DELETE SET NULL,
    source_facility_id VARCHAR(64) NOT NULL REFERENCES facility(id),
    destination_facility_id VARCHAR(64) NOT NULL REFERENCES facility(id),
    drug_code VARCHAR(64) NOT NULL REFERENCES drug(code),
    batch_no VARCHAR(128) NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    usable_quantity INT CHECK (usable_quantity >= 0),
    status VARCHAR(32) NOT NULL DEFAULT 'DRAFT', -- DRAFT, APPROVED, IN_TRANSIT, DELIVERED, CANCELLED
    temperature_controlled BOOLEAN NOT NULL DEFAULT false,
    savings_inr NUMERIC(10, 2) DEFAULT 0.00,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ
);

-- 16. Regret Entry (Alternative destination comparisons)
CREATE TABLE regret_entry (
    id BIGSERIAL PRIMARY KEY,
    plan_run_id VARCHAR(64) NOT NULL REFERENCES plan_run(id) ON DELETE CASCADE,
    order_id VARCHAR(64) NOT NULL REFERENCES transfer_order(id) ON DELETE CASCADE,
    alternate_destination_id VARCHAR(64) NOT NULL REFERENCES facility(id),
    chosen_reward NUMERIC(8, 4) NOT NULL,
    alternate_reward NUMERIC(8, 4) NOT NULL,
    regret_delta NUMERIC(8, 4) NOT NULL,
    reason TEXT
);

-- 17. Custody Event (Physical chain of custody tracking)
CREATE TABLE custody_event (
    id BIGSERIAL PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL REFERENCES transfer_order(id) ON DELETE CASCADE,
    actor VARCHAR(128) NOT NULL,
    event_type VARCHAR(32) NOT NULL, -- DISPATCH, HANDOVER, RECEIVE
    timestamp TIMESTAMPTZ NOT NULL,
    location VARCHAR(255),
    temperature_c NUMERIC(5, 2),
    signature_hash VARCHAR(128),
    notes TEXT
);

-- 18. Credit Memo (Financial vouchers)
CREATE TABLE credit_memo (
    id VARCHAR(64) PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL REFERENCES transfer_order(id) ON DELETE CASCADE,
    creditor_facility_id VARCHAR(64) NOT NULL REFERENCES facility(id),
    debtor_facility_id VARCHAR(64) NOT NULL REFERENCES facility(id),
    drug_code VARCHAR(64) NOT NULL REFERENCES drug(code),
    quantity INT NOT NULL CHECK (quantity > 0),
    unit_cost_inr NUMERIC(10, 2) NOT NULL,
    total_credit_inr NUMERIC(12, 2) NOT NULL,
    issue_date DATE NOT NULL,
    authorized_by VARCHAR(128)
);

-- 19. Audit Log (Tamper-evident hash chain)
CREATE TABLE audit_log (
    seq BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    actor VARCHAR(128) NOT NULL,
    action VARCHAR(128) NOT NULL,
    entity VARCHAR(128) NOT NULL,
    entity_id VARCHAR(128) NOT NULL,
    payload JSONB NOT NULL,
    prev_hash VARCHAR(64) NOT NULL,
    hash VARCHAR(64) NOT NULL
);

-- 20. LLM Call (LLM gateway telemetry and audit)
CREATE TABLE llm_call (
    id VARCHAR(64) PRIMARY KEY,
    purpose VARCHAR(64) NOT NULL,
    prompt_id VARCHAR(64) NOT NULL,
    version VARCHAR(16) NOT NULL,
    model VARCHAR(64) NOT NULL,
    input_hash VARCHAR(64) NOT NULL,
    input JSONB NOT NULL,
    output JSONB NOT NULL,
    confidence NUMERIC(4, 3),
    execution_time_sec NUMERIC(6, 3),
    cached BOOLEAN DEFAULT false,
    provider VARCHAR(64) DEFAULT 'anthropic',
    tokens INT DEFAULT 0,
    ok BOOLEAN DEFAULT true,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 21. Chat Session (Copilot interactive sessions)
CREATE TABLE chat_session (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64),
    facility_id VARCHAR(64) REFERENCES facility(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 22. Chat Message (Copilot messages)
CREATE TABLE chat_message (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES chat_session(id) ON DELETE CASCADE,
    role VARCHAR(32) NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,
    tool_calls JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- Indexes for Performance & Query Patterns
-- ============================================================================
CREATE INDEX idx_facility_level ON facility(level);
CREATE INDEX idx_drug_category ON drug(category);
CREATE INDEX idx_drug_alias_code ON drug_alias(drug_code);
CREATE INDEX idx_lot_facility_drug ON lot(facility_id, drug_code);
CREATE INDEX idx_consumption_facility_drug ON consumption_daily(facility_id, drug_code);
CREATE INDEX idx_forecast_facility_drug ON forecast(facility_id, drug_code);
CREATE INDEX idx_policy_facility_drug ON policy(facility_id, drug_code);
CREATE INDEX idx_route_source_dest ON route(source_id, destination_id);
CREATE INDEX idx_sensor_vehicle ON sensor_reading(vehicle_id);
CREATE INDEX idx_candidate_plan_run ON candidate(plan_run_id);
CREATE INDEX idx_transfer_order_plan_run ON transfer_order(plan_run_id);
CREATE INDEX idx_transfer_order_status ON transfer_order(status);
CREATE INDEX idx_regret_plan_run ON regret_entry(plan_run_id);
CREATE INDEX idx_custody_order ON custody_event(order_id);
CREATE INDEX idx_credit_memo_order ON credit_memo(order_id);
CREATE INDEX idx_audit_log_seq ON audit_log(seq);
CREATE INDEX idx_audit_log_entity ON audit_log(entity, entity_id);
CREATE INDEX idx_chat_message_session ON chat_message(session_id);

