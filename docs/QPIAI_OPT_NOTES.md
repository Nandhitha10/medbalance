# QpiAI Opt Package Introspection Notes

**Date**: 2026-10-29  
**Package Version**: `qpiai-opt==0.0.9`  
**Python Runtime**: 3.12 (CPython x86_64)  
**Dependencies**: `scipy==1.18.1`, `highspy==1.15.1`, `requests==2.34.2`, `pydantic>=2`

---

## 1. Top-Level Module Hierarchy

`qpiai_opt` exposes two primary submodules:
1. `qpiai_opt.opt_modeller`: Domain modelling primitives, expressions, variables (`Binary`, `Integer`, `Continuous`), converters (`QUBOToIsingConvert`, `IsingToQUBOConvert`, `MILPToQUBOConvert`), and high-level `Model`.
2. `qpiai_opt.opt_solvers`: Platform client, job submission, local heuristics, and problem schemas.
   - `qpiai_opt.opt_solvers.client`: `Client(api_key, experiment_id, experiment_name, base_url, timeout)`
   - `qpiai_opt.opt_solvers.local`: `LocalProvider(client)`, `QUBOProblem`, `QUBOSolveResult`, `SolveResult`
   - `qpiai_opt.opt_solvers.solve`: `solve(problem, mode='local', client=None, allow_platform=False, ...)`

---

## 2. Key Classes, Signatures & Behavior

### A. `qpiai_opt.opt_solvers.client.Client`
```python
Client(
    *,
    api_key: Optional[str] = None,
    experiment_id: Optional[str] = None,
    experiment_name: Optional[str] = None,
    base_url: str = "https://opt-server.qpiai.tech/api",
    timeout: float = 60.0,
    session: Optional[requests.Session] = None
) -> None
```
**Methods**:
- `submit_job(problem_id, solver_id, config)`: Asynchronous remote job dispatch
- `wait_for_job(job_id, timeout)`: Polling loop waiting for remote solution
- `download_result(job_id)`: Fetches solution payload
- `verify_api_key()`: Verifies validity of API credential

### B. `qpiai_opt.opt_solvers.local.LocalProvider`
```python
LocalProvider(client: Client | None = None) -> None
```
**Capabilities**:
- Solves problem classes: `'LP'`, `'MILP'`, `'QP'`, `'QUBO'`, `'HUBO'`, `'ISING'`.
- Method:
  ```python
  solve(
      problem: Any,
      *,
      problem_class: str,
      time_limit: float | None = None,
      mip_rel_gap: float | None = None,
      node_limit: int | None = None,
      num_reads: int | None = None,
      num_sweeps: int | None = None,
      seed: int | None = None,
      **options: Any
  ) -> SolveResult
  ```

> [!IMPORTANT]
> **Authentication Requirement**: `LocalProvider()` requires a valid `client=Client(api_key=...)`. If `api_key` is not provided or the remote authentication check fails, it raises `qpiai_opt.opt_solvers.exceptions.AuthenticationError`.

### C. `qpiai_opt.opt_solvers.local.QUBOProblem`
Pydantic V2 schema for representing QUBO instances:
- `problem_type`: Literal `'QUBO'`
- `num_variables`: `int` (number of binary variables)
- `matrix_format`: Literal `'upper'` (upper-triangular) or `'symmetric'`
- `sense`: Literal `'MIN'` (default) or `'MAX'`
- `offset`: `float` scalar constant
- `variable_names`: `List[str]`
- `qubo_dict`: `Dict[Tuple[int, int], float]` mapping integer indices `(i, j)` to coefficients:
  - When `matrix_format='upper'`, requires $i \le j$.
  - When `matrix_format='symmetric'`, requires symmetric keys $(i, j)$ and $(j, i)$.

### D. `qpiai_opt.opt_solvers.local.QUBOSolveResult`
Output schema returned upon solution:
- `solution`: Dict mapping variable indices to $\{0, 1\}$
- `objective`: Scalar float objective value
- `solver_time_s`: Duration in seconds
- `compute_time_s`: Backend execution duration
- `job_id`: Generated or tracked execution ID

---

## 3. Solver Tiering & Failover Architecture

Per CLAUDE.md §7:
1. **Tier 1 — `QpiAIOptPlatform`**: Connects via `qpiai_opt.opt_solvers.client.Client` using `QPIAI_API_KEY` and `QPIAI_ENDPOINT`. Dispatches to QpiAI Opt cloud solver with a 20s timeout.
2. **Tier 2 — `QpiAIOptLocal`**: Uses `LocalProvider(client=Client(api_key=...))` for local heuristic/exact solving.
3. **Tier 3 — `NealSA`**: Local simulated annealing using `dwave-neal` (`neal.SimulatedAnnealingSampler()`). Fast, robust, offline-capable, and completely dependency-free.
4. **Tier 4 — `GreedyDescent`**: Deterministic 1-bit-flip steepest gradient descent with restarts. Guaranteed to run anywhere in pure Python without third-party dependencies.

---

## 4. Evidence Artifacts
Every solver execution outputs a JSON record to `evidence/qpiai_runs/<ts>_<hash>.json`:
- `tier`: The successful solver tier name
- `time_ms`: Execution latency in milliseconds
- `energy`: Resulting objective energy
- `n_vars`: Variable count
- `error`: Error string if a higher tier failed before fallback
- `sample`: Selected binary assignment vector
- `term_breakdown`: Decomposed energy contributions
