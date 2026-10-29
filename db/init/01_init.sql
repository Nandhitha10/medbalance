-- MedBalance-Q Initial Database Schema
-- Plain SQL initialization (no Alembic migrations)

CREATE TABLE IF NOT EXISTS audit_log (
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

CREATE INDEX IF NOT EXISTS idx_audit_log_seq ON audit_log(seq);
CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity, entity_id);

CREATE TABLE IF NOT EXISTS facilities (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    facility_type VARCHAR(64) NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    cold_storage_available BOOLEAN DEFAULT FALSE,
    min_reserve_days INT DEFAULT 7
);

CREATE TABLE IF NOT EXISTS drugs (
    code VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(1) NOT NULL, -- V (Vital), E (Essential), N (Non-essential)
    unit VARCHAR(64) NOT NULL,
    pack_size INT DEFAULT 1,
    storage_condition VARCHAR(64) NOT NULL DEFAULT 'ambient', -- ambient, cold_chain
    min_residual_days INT DEFAULT 30
);

CREATE TABLE IF NOT EXISTS lots (
    id BIGSERIAL PRIMARY KEY,
    facility_id VARCHAR(64) REFERENCES facilities(id),
    drug_code VARCHAR(64) REFERENCES drugs(code),
    batch_no VARCHAR(128) NOT NULL,
    expiry DATE NOT NULL,
    quantity INT NOT NULL CHECK (quantity >= 0),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_facility_drug_batch UNIQUE (facility_id, drug_code, batch_no)
);

CREATE TABLE IF NOT EXISTS routes (
    id VARCHAR(128) PRIMARY KEY,
    source_id VARCHAR(64) REFERENCES facilities(id),
    destination_id VARCHAR(64) REFERENCES facilities(id),
    distance_km DOUBLE PRECISION NOT NULL,
    transit_hours DOUBLE PRECISION NOT NULL,
    cold_chain_compliant BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS vehicles (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    vehicle_type VARCHAR(64) NOT NULL,
    cold_chain_capable BOOLEAN DEFAULT FALSE,
    current_temp_c DOUBLE PRECISION,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS transfer_orders (
    id VARCHAR(64) PRIMARY KEY, -- Format: DTA/BLR-U/2026/000123
    source_id VARCHAR(64) REFERENCES facilities(id),
    destination_id VARCHAR(64) REFERENCES facilities(id),
    drug_code VARCHAR(64) REFERENCES drugs(code),
    batch_no VARCHAR(128) NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    status VARCHAR(64) NOT NULL DEFAULT 'DRAFT', -- DRAFT, APPROVED, IN_TRANSIT, DELIVERED, CANCELLED
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS custody_events (
    id BIGSERIAL PRIMARY KEY,
    order_id VARCHAR(64) REFERENCES transfer_orders(id),
    actor VARCHAR(128) NOT NULL,
    event_type VARCHAR(64) NOT NULL, -- DISPATCH, HANDOVER, RECEIVE
    timestamp TIMESTAMPTZ NOT NULL,
    location VARCHAR(255),
    temperature_c DOUBLE PRECISION,
    notes TEXT
);
