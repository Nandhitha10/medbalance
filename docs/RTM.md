# Requirements Traceability Matrix (RTM)

| Req ID | Requirement Description | Architecture Component | Verification Method | Status |
|---|---|---|---|---|
| REQ-01 | Monorepo folder layout & documentation | Repository structure | Inspection / Tree | Done |
| REQ-02 | Shared common library (`medbal_common`) | `libs/medbal_common` | `uv run pytest libs/medbal_common` | Done |
| REQ-03 | Tamper-evident audit chain with verify() | `medbal_common.audit` | Unit test with tampering detection | Done |
| REQ-04 | Base Docker image with uv & medbal_common | `docker/py-base.Dockerfile` | Docker build | Done |
| REQ-05 | Service placeholder containers with /health | `services/*` | Compose build & healthcheck | Done |
| REQ-06 | Nginx reverse proxy gateway with SSE support | `docker/nginx` | Curl /api/core/health | Done |
| REQ-07 | Multi-profile Docker compose stack | `docker-compose.yml` | `docker compose ps` | Done |
| REQ-08 | Automated task runner | `Makefile` | `make help` | Done |
