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

## ADR-005: QUBO P2 Shortage Penalty Parameter Selection
- **Date**: 2026-10-29
- **Status**: Accepted
- **Context**: The QUBO objective function $H(x)$ balances reward maximization (avoiding drug expiry) against quadratic shortage penalties governed by $P_2 \cdot \sum_{d, g} \pi_{VEN}(g) \left(1 - \frac{1}{n_{dg}} \sum_i u_i x_i\right)^2$. If $P_2$ is set too low ($< 1.0$), the solver deprioritizes critical shortages in favor of easy ambient transfers with low transport costs. If $P_2$ is set too high ($> 2.0$), the quadratic penalty gradient overwhelms one-place constraints ($P_1$) and chunk sequencing ($P_3$), resulting in duplicate candidate selection and high constraint violations requiring post-solver repair.
- **Decision**: Set the default shortage quadratic penalty weight to $P_2 = 1.5$. This parameter was empirically validated via `scripts/sweep_p2.py` across 5 random seeds ($42, 43, 44, 45, 46$) over $P_2 \in \{0.5, 1.0, 1.5, 2.0, 3.0\}$.
- **Results**:
  - $P_2 = 0.5$: Under-allocates transfers (avg 2.00 orders, 350.4 shortage units reduced, Rs. 35,768.00 expiry avoided, 34.60 pre-repair violations).
  - $P_2 = 1.0$: Intermediate performance (avg 2.40 orders, 443.4 shortage units reduced, Rs. 40,426.00 expiry avoided).
  - **$P_2 = 1.5$**: Optimal balance (avg 2.60 orders, **496.4 shortage units reduced**, **Rs. 45,628.00 expiry avoided**, minimum pre-repair violations **32.20**, 0 post-repair violations, fastest avg solve time 114.54 ms).
  - $P_2 = 2.0$: Plateaus on shortage/expiry metrics while pre-repair violations increase to 33.20.
  - $P_2 = 3.0$: Shortage reduction degrades to 449.4 units as conflicting high-penalty terms induce local optima traps and higher repair burden (33.40 pre-repair violations).
- **Consequences**: $P_2 = 1.5$ provides maximum clinical utility (highest VEN shortage reduction) and economic benefit (highest expiry avoided) while maintaining numerical stability and low validator intervention.

