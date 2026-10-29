# Redis Streams Event Specifications

This document defines the 10 core event streams used for asynchronous messaging across MedBalance-Q services.

---

## 1. `report.received`
Published when an inventory report (PDF, Excel, or FHIR) is received from a hospital facility.

- **Producer**: `ingest-ai`
- **Consumer**: `ingest-ai` (processing queue)

### JSON Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["event_id", "event_type", "timestamp", "data"],
  "properties": {
    "event_id": { "type": "string" },
    "event_type": { "type": "string", "const": "report.received" },
    "timestamp": { "type": "string", "format": "date-time" },
    "data": {
      "type": "object",
      "required": ["report_id", "facility_code", "source_type", "file_name"],
      "properties": {
        "report_id": { "type": "string" },
        "facility_code": { "type": "string" },
        "source_type": { "type": "string", "enum": ["pdf", "excel", "csv", "fhir"] },
        "file_name": { "type": "string" },
        "file_size_bytes": { "type": "integer" }
      }
    }
  }
}
```

### Example
```json
{
  "event_id": "evt-rep-001",
  "event_type": "report.received",
  "timestamp": "2026-11-01T08:15:00+05:30",
  "data": {
    "report_id": "REP-H1-20261101",
    "facility_code": "H1",
    "source_type": "pdf",
    "file_name": "h1_stock_nov01.pdf",
    "file_size_bytes": 142050
  }
}
```

---

## 2. `inventory.updated`
Published when inventory lots are ingested, verified, or updated.

- **Producer**: `ingest-ai`, `core-api`
- **Consumer**: `core-api`, `forecast`, `optimizer`

### JSON Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["event_id", "event_type", "timestamp", "data"],
  "properties": {
    "event_id": { "type": "string" },
    "event_type": { "type": "string", "const": "inventory.updated" },
    "timestamp": { "type": "string", "format": "date-time" },
    "data": {
      "type": "object",
      "required": ["facility_code", "updated_lots_count", "lots"],
      "properties": {
        "facility_code": { "type": "string" },
        "updated_lots_count": { "type": "integer" },
        "lots": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["drug_code", "batch_no", "expiry", "quantity"],
            "properties": {
              "drug_code": { "type": "string" },
              "batch_no": { "type": "string" },
              "expiry": { "type": "string", "format": "date" },
              "quantity": { "type": "integer" }
            }
          }
        }
      }
    }
  }
}
```

### Example
```json
{
  "event_id": "evt-inv-002",
  "event_type": "inventory.updated",
  "timestamp": "2026-11-01T08:20:00+05:30",
  "data": {
    "facility_code": "H1",
    "updated_lots_count": 2,
    "lots": [
      {
        "drug_code": "INS-REG",
        "batch_no": "LOT-INS-001",
        "expiry": "2026-11-20",
        "quantity": 50
      },
      {
        "drug_code": "AMOX-500",
        "batch_no": "LOT-AMX-101",
        "expiry": "2026-12-15",
        "quantity": 600
      }
    ]
  }
}
```

---

## 3. `anomaly.flagged`
Published when LLM extraction or rule checks detect unexpected lot quantities, dates, or missing codes.

- **Producer**: `ingest-ai`
- **Consumer**: `core-api`, UI review queue

### JSON Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["event_id", "event_type", "timestamp", "data"],
  "properties": {
    "event_id": { "type": "string" },
    "event_type": { "type": "string", "const": "anomaly.flagged" },
    "timestamp": { "type": "string", "format": "date-time" },
    "data": {
      "type": "object",
      "required": ["review_id", "facility_code", "anomaly_type", "confidence", "details"],
      "properties": {
        "review_id": { "type": "string" },
        "facility_code": { "type": "string" },
        "anomaly_type": { "type": "string", "enum": ["UNKNOWN_DRUG", "SUSPICIOUS_EXPIRY", "QUANTITY_SPIKE", "CORRUPTED_TEXT"] },
        "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
        "details": { "type": "string" }
      }
    }
  }
}
```

### Example
```json
{
  "event_id": "evt-anom-003",
  "event_type": "anomaly.flagged",
  "timestamp": "2026-11-01T08:21:00+05:30",
  "data": {
    "review_id": "REV-0091",
    "facility_code": "H2",
    "anomaly_type": "SUSPICIOUS_EXPIRY",
    "confidence": 0.88,
    "details": "Parsed expiry 2024-01-01 is in the past; potential OCR error on '2026'."
  }
}
```

---

## 4. `forecast.updated`
Published when Holt-Winters + LLM context forecasts are computed.

- **Producer**: `forecast`
- **Consumer**: `optimizer`, `core-api`

### JSON Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["event_id", "event_type", "timestamp", "data"],
  "properties": {
    "event_id": { "type": "string" },
    "event_type": { "type": "string", "const": "forecast.updated" },
    "timestamp": { "type": "string", "format": "date-time" },
    "data": {
      "type": "object",
      "required": ["facility_code", "drug_code", "daily_rate", "target_days", "multiplier", "multiplier_reason"],
      "properties": {
        "facility_code": { "type": "string" },
        "drug_code": { "type": "string" },
        "daily_rate": { "type": "number", "minimum": 0 },
        "target_days": { "type": "integer" },
        "multiplier": { "type": "number" },
        "multiplier_reason": { "type": "string" }
      }
    }
  }
}
```

### Example
```json
{
  "event_id": "evt-fc-004",
  "event_type": "forecast.updated",
  "timestamp": "2026-11-01T08:25:00+05:30",
  "data": {
    "facility_code": "H2",
    "drug_code": "INS-REG",
    "daily_rate": 2.5,
    "target_days": 14,
    "multiplier": 1.25,
    "multiplier_reason": "Monsoon disease surge bulletin active in taluk"
  }
}
```

---

## 5. `coldchain.alert`
Published when vehicle or facility cold storage detects a temperature excursion.

- **Producer**: `coldchain`
- **Consumer**: `core-api`, `optimizer`, notification alert bus

### JSON Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["event_id", "event_type", "timestamp", "data"],
  "properties": {
    "event_id": { "type": "string" },
    "event_type": { "type": "string", "const": "coldchain.alert" },
    "timestamp": { "type": "string", "format": "date-time" },
    "data": {
      "type": "object",
      "required": ["device_id", "severity", "temperature_c", "min_allowed_c", "max_allowed_c", "duration_minutes"],
      "properties": {
        "device_id": { "type": "string" },
        "vehicle_id": { "type": "string" },
        "order_id": { "type": "string" },
        "severity": { "type": "string", "enum": ["WARNING", "CRITICAL"] },
        "temperature_c": { "type": "number" },
        "min_allowed_c": { "type": "number" },
        "max_allowed_c": { "type": "number" },
        "duration_minutes": { "type": "integer" }
      }
    }
  }
}
```

### Example
```json
{
  "event_id": "evt-cc-005",
  "event_type": "coldchain.alert",
  "timestamp": "2026-11-01T08:30:00+05:30",
  "data": {
    "device_id": "DEV-VEH-01",
    "vehicle_id": "VEH-COLD-01",
    "order_id": "DTA/BLR-U/2026/000101",
    "severity": "CRITICAL",
    "temperature_c": 11.4,
    "min_allowed_c": 2.0,
    "max_allowed_c": 8.0,
    "duration_minutes": 25
  }
}
```

---

## 6. `plan.progress`
Published periodically while the optimizer is solving the QUBO allocation.

- **Producer**: `optimizer`
- **Consumer**: `core-api`, UI progress bar

### JSON Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["event_id", "event_type", "timestamp", "data"],
  "properties": {
    "event_id": { "type": "string" },
    "event_type": { "type": "string", "const": "plan.progress" },
    "timestamp": { "type": "string", "format": "date-time" },
    "data": {
      "type": "object",
      "required": ["plan_id", "stage", "percent_complete", "active_tier"],
      "properties": {
        "plan_id": { "type": "string" },
        "stage": { "type": "string" },
        "percent_complete": { "type": "number", "minimum": 0, "maximum": 100 },
        "active_tier": { "type": "string" }
      }
    }
  }
}
```

### Example
```json
{
  "event_id": "evt-prog-006",
  "event_type": "plan.progress",
  "timestamp": "2026-11-01T08:35:10+05:30",
  "data": {
    "plan_id": "PLAN-20261101-01",
    "stage": "QUBO_SOLVER",
    "percent_complete": 65.0,
    "active_tier": "LocalProvider"
  }
}
```

---

## 7. `plan.completed`
Published when a redistribution plan has been successfully solved and persisted.

- **Producer**: `optimizer`
- **Consumer**: `core-api`, UI dashboard

### JSON Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["event_id", "event_type", "timestamp", "data"],
  "properties": {
    "event_id": { "type": "string" },
    "event_type": { "type": "string", "const": "plan.completed" },
    "timestamp": { "type": "string", "format": "date-time" },
    "data": {
      "type": "object",
      "required": ["plan_id", "orders_count", "units_transferred", "shortage_reduction", "expiry_avoided", "solver_tier", "execution_time_sec"],
      "properties": {
        "plan_id": { "type": "string" },
        "orders_count": { "type": "integer" },
        "units_transferred": { "type": "integer" },
        "shortage_reduction": { "type": "integer" },
        "expiry_avoided": { "type": "integer" },
        "solver_tier": { "type": "string" },
        "execution_time_sec": { "type": "number" }
      }
    }
  }
}
```

### Example
```json
{
  "event_id": "evt-plan-007",
  "event_type": "plan.completed",
  "timestamp": "2026-11-01T08:35:15+05:30",
  "data": {
    "plan_id": "PLAN-20261101-01",
    "orders_count": 6,
    "units_transferred": 1428,
    "shortage_reduction": 1350,
    "expiry_avoided": 1428,
    "solver_tier": "platform",
    "execution_time_sec": 4.12
  }
}
```

---

## 8. `plan.revised`
Published when an order in an active plan is rejected or modified, triggering a re-plan or delta update.

- **Producer**: `core-api`, `optimizer`
- **Consumer**: UI, audit chain

### JSON Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["event_id", "event_type", "timestamp", "data"],
  "properties": {
    "event_id": { "type": "string" },
    "event_type": { "type": "string", "const": "plan.revised" },
    "timestamp": { "type": "string", "format": "date-time" },
    "data": {
      "type": "object",
      "required": ["original_plan_id", "new_plan_id", "rejected_order_id", "reason"],
      "properties": {
        "original_plan_id": { "type": "string" },
        "new_plan_id": { "type": "string" },
        "rejected_order_id": { "type": "string" },
        "reason": { "type": "string" }
      }
    }
  }
}
```

### Example
```json
{
  "event_id": "evt-rev-008",
  "event_type": "plan.revised",
  "timestamp": "2026-11-01T08:40:00+05:30",
  "data": {
    "original_plan_id": "PLAN-20261101-01",
    "new_plan_id": "PLAN-20261101-02",
    "rejected_order_id": "DTA/BLR-U/2026/000103",
    "reason": "Destination facility cold storage freezer under maintenance"
  }
}
```

---

## 9. `order.status`
Published when a transfer order changes status (e.g. APPROVED, DISPATCHED, DELIVERED).

- **Producer**: `core-api`
- **Consumer**: `coldchain`, `sim-hospital`, audit log

### JSON Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["event_id", "event_type", "timestamp", "data"],
  "properties": {
    "event_id": { "type": "string" },
    "event_type": { "type": "string", "const": "order.status" },
    "timestamp": { "type": "string", "format": "date-time" },
    "data": {
      "type": "object",
      "required": ["order_id", "old_status", "new_status", "actor"],
      "properties": {
        "order_id": { "type": "string" },
        "old_status": { "type": "string" },
        "new_status": { "type": "string", "enum": ["DRAFT", "APPROVED", "IN_TRANSIT", "DELIVERED", "CANCELLED"] },
        "actor": { "type": "string" },
        "notes": { "type": "string" }
      }
    }
  }
}
```

### Example
```json
{
  "event_id": "evt-ord-009",
  "event_type": "order.status",
  "timestamp": "2026-11-01T08:45:00+05:30",
  "data": {
    "order_id": "DTA/BLR-U/2026/000101",
    "old_status": "DRAFT",
    "new_status": "APPROVED",
    "actor": "dr_sharma_district_officer",
    "notes": "Approved for priority morning cold-chain dispatch"
  }
}
```

---

## 10. `custody.scanned`
Published when a QR barcode or custody scan event occurs at dispatch, handover, or delivery.

- **Producer**: `core-api`, mobile app
- **Consumer**: `core-api`, audit chain, `coldchain`

### JSON Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["event_id", "event_type", "timestamp", "data"],
  "properties": {
    "event_id": { "type": "string" },
    "event_type": { "type": "string", "const": "custody.scanned" },
    "timestamp": { "type": "string", "format": "date-time" },
    "data": {
      "type": "object",
      "required": ["order_id", "event_type", "actor", "location"],
      "properties": {
        "order_id": { "type": "string" },
        "event_type": { "type": "string", "enum": ["DISPATCH", "HANDOVER", "RECEIVE"] },
        "actor": { "type": "string" },
        "location": { "type": "string" },
        "temperature_c": { "type": "number" },
        "signature_hash": { "type": "string" }
      }
    }
  }
}
```

### Example
```json
{
  "event_id": "evt-scan-010",
  "event_type": "custody.scanned",
  "timestamp": "2026-11-01T09:00:00+05:30",
  "data": {
    "order_id": "DTA/BLR-U/2026/000101",
    "event_type": "DISPATCH",
    "actor": "pharmacist_h1",
    "location": "SIM-HOSP-H1 Main Pharmacy",
    "temperature_c": 4.2,
    "signature_hash": "a8f5b2149e3...b7c"
  }
}
```
