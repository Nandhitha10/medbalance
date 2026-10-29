# MedBalance-Q Demo Script

## 1. Setup & Environment
1. Clone repository and copy configuration:
   ```bash
   cp .env.example .env
   ```
2. Start infrastructure and core services:
   ```bash
   make up
   ```
3. Check health of services:
   ```bash
   make ps
   curl http://localhost:8080/api/core/health
   ```

## 2. Walkthrough Steps
- Step 1: Ingest facility inventories.
- Step 2: Forecast consumption and detect stockout / expiry risks.
- Step 3: Run QUBO optimizer to generate transfer recommendations (DTAs).
- Step 4: Validate feasibility (cold chain, transport, reserve limits).
- Step 5: Dispatch transfers and monitor temperature excursions via MQTT.
