# Architecture Decisions (ADR)

## ADR-001: Monorepo Structure and Shared Library
- **Date**: 2026-10-29
- **Status**: Accepted
- **Context**: 4 developers working simultaneously across 10+ services need shared models, standardized logging, audit chain, and settings without circular dependencies or copy-paste drift.
- **Decision**: Centralize common utilities in `libs/medbal_common` installable via `uv`. All services derive from a base image `medbal-py-base` containing `medbal_common`.
- **Consequences**: Standardized configuration, zero duplication of audit chain logic, uniform healthchecks and error handling across all services.

## ADR-002: Deterministic Clock Isolation
- **Date**: 2026-10-29
- **Status**: Accepted
- **Context**: FEFO, expiry tracking, and simulation replay require a reproducible time reference rather than arbitrary system time.
- **Decision**: Disallow `datetime.now()` in domain logic. All services reference `medbal_common.clock.today()` / `now()`, querying `sim-control` with a 1-second in-memory cache and a deterministic fallback.
- **Consequences**: Fast simulation stepping without breaking domain calculations.

## ADR-003: Tamper-Evident SHA-256 Audit Chain
- **Date**: 2026-10-29
- **Status**: Accepted
- **Context**: Healthcare regulatory compliance and trust require an immutable audit trail of lot movements, DTA approvals, and custody handovers.
- **Decision**: Implement a canonical JSON + SHA-256 hash chain in `medbal_common.audit` persisted in the same DB transaction as entity modifications.
- **Consequences**: Any database tampering or retroactive modification of audit logs breaks the chain and is detected by `audit.verify()`.

## ADR-004: Currency Representation as Decimal INR
- **Date**: 2026-10-29
- **Status**: Accepted
- **Context**: Drug valuations, transfer savings, credit memos, and transport costs must be represented uniformly across all APIs, UI displays, and optimization models.
- **Decision**: Represent monetary values as standard INR floats/numbers rounded to 2 decimal places (e.g., `1250.50`), with field names suffixed with `_inr` (e.g. `unit_cost_inr`, `savings_inr`).
- **Consequences**: Consistent with Indian procurement standards and simplifies UI formatting without integer-paise division bugs across frontend components.

