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

## ADR-006: Local Simulation vs Remote Cloud Execution Tiers for Quantum and Optimization Solvers
- **Date**: 2026-10-29
- **Status**: Accepted
- **Context**: MedBalance incorporates QpiAI Quantum (`qpiai_quantum` v0.7.5) and QpiAI Opt for QAOA graph zoning and combinatorial optimization. However, development, CI/CD, and offline deployment environments may not have live QCloud API credentials (`QPIAI_QUANTUM_API_KEY` / `QPIAI_API_KEY`) or network access. The system must remain deterministic, self-contained, and completely functional without failing silently.
- **Decision**: Implement a strict multi-tier execution failover chain for both quantum circuits and QUBO optimization:
  1. **Quantum QAOA Max-Cut Tier Chain** (`services/optimizer/optimizer/qaoa/chain.py`):
     - Tier 1: `qpiai_qcloud_simulator` (remote QpiAI QCloud API, env-guarded by `QPIAI_QUANTUM_API_KEY`).
     - Tier 2: `qsv_local` (local `qpiai_quantum.simulator.StatevectorSimulator`, fully offline, parameterized $R_{ZZ}$ and $R_X$ gates with COBYLA optimization).
     - Tier 3: `exact_bruteforce` (exact combinatorial enumeration for small graphs $n \le 16$, guarantees global optimum for benchmarking).
     - Tier 4: `networkx_greedy` (classical 1-flip greedy heuristic baseline).
  2. **QUBO Solver Tier Chain** (`services/optimizer/optimizer/solvers/chain.py`):
     - Tier 1: `qpiai_opt_platform` (remote QpiAI Opt SaaS platform).
     - Tier 2: `qpiai_opt_local` (QpiAI LocalProvider).
     - Tier 3: `dwave_neal_sa` (D-Wave Simulated Annealing library `neal`).
     - Tier 4: `greedy_descent` (local deterministic 1-flip local search).
  Every invocation generates an immutable execution telemetry record saved to `evidence/qcloud_runs/` or `evidence/qpiai_runs/` logging the attempted tiers, timings, bitstrings, and errors.
- **Consequences**: Zero test flakiness in offline/CI environments, transparent logging of remote service status, and complete reproducibility across developer laptops and production servers.

## ADR-007: Graph-Theoretic QAOA Max-Cut Zoning vs Euclidean K-Means for Logistics Partitioning
- **Date**: 2026-10-29
- **Status**: Accepted
- **Context**: Scaling redistribution optimization across a large healthcare district ($n=40$ facilities) requires decomposing the problem into smaller, independently solvable zones. Classical logistics often applies spatial clustering ($k$-means) on GPS coordinates. However, healthcare logistics depends on road network topography, actual transit times, barrier bottlenecks, and dynamic road closures rather than Euclidean straight-line distance.
- **Decision**: Formulate district decomposition as a weighted Max-Cut problem solved via QAOA on the road network transit graph:
  - Vertices $V$ are health facilities (in live 5-node mode) or taluk super-nodes (in 40-facility scale mode).
  - Edge weights $w_{uv} = \text{distance\_km} \times \text{transit\_hours}$ represent normalized transit impedance. Heavy edges denote high transit impedance or physical barriers.
  - Max-Cut objective $\max \sum_{(u,v) \in E} w_{uv} \frac{1 - z_u z_v}{2}$ cuts the heaviest edges, placing facilities separated by bottlenecks into different zones while preserving tightly connected clusters within the same zone.
- **Results**:
  - QAOA Max-Cut cut value: **3.866** vs Coordinate K-Means: **2.712** (+42.5% cut improvement).
  - Intra-zone transit impedance: **1.620** for QAOA vs **2.774** for K-Means (-41.6% reduction in internal transit barriers).
  - QAOA respects route closures and terrain bottlenecks that Euclidean $k$-means ignores.
- **Consequences**: Subproblems solved inside each zone experience shorter transit delays and fewer cross-taluk vehicle dispatches, while residual cross-zone shortages are cleanly addressed by a small boundary QUBO.

## ADR-008: Exact Classical MILP Baseline with Google OR-Tools CP-SAT for Honest Optimality Benchmarking
- **Date**: 2026-10-29
- **Status**: Accepted
- **Context**: Quantum-inspired heuristics and simulated annealing must be objectively benchmarked against exact ground truth. In clinical logistics, making false claims of "quantum advantage" without measuring the true optimality gap is irresponsible. We need an exact classical baseline that formulates the exact same objective and constraints.
- **Decision**: Formulate and solve the redistribution decision problem to global optimality using Google OR-Tools CP-SAT (`services/optimizer/optimizer/milp.py`):
  - Binary decision variable $x_i \in \{0, 1\}$ for each candidate chunk.
  - Integer scaling ($\times 10^6$) over continuous float coefficients.
  - Exact quadratic product linearization via `model.add_multiplication_equality(z_{ij}, [x_i, x_j])`.
  - 20-second timeout limit.
  - Return exact optimal energy $E^*(x)$ and report `optimality_gap_percent` on `GET /plan/{id}/benchmark`:
    $$\text{optimality\_gap} = \frac{|E_{\text{solver}} - E_{\text{milp}}^*|}{|E_{\text{milp}}^*|} \times 100\%$$
- **Verification**: Verified that CP-SAT matches the global minimum of brute-force exhaustive enumeration across all 8 test instances with zero gap ($0.0\%$).
- **Consequences**: Establishes MedBalance as an honest, scientifically grounded system that reports verified optimality gaps against global mathematical baselines.


