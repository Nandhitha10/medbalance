# QpiAI QCloud & Quantum SDK (`qpiai_quantum`) Architecture Notes

## Package Overview

- **Package**: `qpiai-quantum` (version 0.7.5)
- **Primary Modules**:
  - `qpiai_quantum.QpiAIQuantumAuth`: API authentication and token verification against QpiAI QCloud.
  - `qpiai_quantum.circuit.Circuit`: Quantum circuit construction, gate application, and job submission.
  - `qpiai_quantum.Backend`: Target compute resources (`LOCAL_SIMULATOR`, `STATEVECTOR_SIMULATOR_CPU`, `DENSITY_MATRIX_SIMULATOR_CPU`, `TENSOR_NETWORK_SIMULATOR_CPU`, `INDUS_QPU`).
  - `qpiai_quantum.simulator.StatevectorSimulator`: Local high-performance CPU statevector engine returning `QasmSimulatorResult`.

---

## 1. Authentication (`QpiAIQuantumAuth`)

QCloud authentication operates as specified in `CLAUDE.md §7`:
```python
from qpiai_quantum import QpiAIQuantumAuth as Auth

# Login with QCloud API key
Auth.login(api_key="your_qpiai_api_key")

# Verify token validity
is_valid = Auth.verify_api_key()
```
- When `QPIAI_QUANTUM_API_KEY` or `QPIAI_API_KEY` is present in the environment, the client logs in to access remote cloud backends.
- If unconfigured or offline, the solver architecture gracefully records the authentication status and falls back to local execution (`QSVLocal` via `StatevectorSimulator`).

---

## 2. Quantum Circuit Construction & API Conventions

`Circuit(n_qubits: int, n_clbits: int = 0)`

### Gate Signatures (Important: Qubits First, Angles Second)
- **Hadamard**: `qc.h(qubit: int)`
- **Rotation X**: `qc.rx(qubit: int, theta: float)`
- **Rotation Z**: `qc.rz(qubit: int, theta: float)`
- **Two-Qubit RZZ**: `qc.rzz(qubit1: int, qubit2: int, theta: float)`
  - *Note*: `qpiai_quantum.Circuit.rzz` requires qubit indices as the first two arguments, followed by `theta`.
- **Controlled-NOT**: `qc.cx(control: int, target: int)`
- **Measurement**: `qc.measure_all()`

### Bitstring Conventions
- Measurements returned by `QasmSimulatorResult.get_counts()` are strings formatted in little-endian order (e.g. `'01'` means qubit 0 is 1 and qubit 1 is 0).
- Qubit $i$'s measurement outcome corresponds to `int(bitstring[-(i + 1)])`.

---

## 3. QAOA for Max-Cut Graph Partitioning

Max-Cut partitions graph vertices $V$ into two disjoint subsets $(S, V \setminus S)$ maximizing the sum of edge weights traversing the cut:
$$\text{Cut}(z) = \sum_{(u, v) \in E} w_{uv} \frac{1 - (-1)^{z_u \oplus z_v}}{2}$$

### QAOA Ansatz ($p$ layers)
1. **Initial State**: Uniform superposition $|+\rangle^{\otimes n}$ via Hadamard on all qubits.
2. **Problem Hamiltonian**:
   $$H_C = \sum_{(u, v) \in E} \frac{w_{uv}}{2} Z_u Z_v$$
   Implemented via `qc.rzz(u, v, gamma * w_{uv})` for each edge $(u, v) \in E$.
3. **Mixer Hamiltonian**:
   $$H_B = \sum_{u \in V} X_u$$
   Implemented via `qc.rx(u, 2 * beta)` for each qubit $u \in V$.
4. **Measurement**: `qc.measure_all()`.
5. **Optimization**: Variational parameters $(\gamma, \beta)$ optimized via grid scan or classical optimizer (COBYLA/Nelder-Mead) over $p \in \{1, 2\}$ layers.

---

## 4. MaxCutPort Solver Hierarchy

The zoning engine wraps all graph partitioning behind the `MaxCutPort` protocol:

| Tier | Class | Description | Use Case |
|---|---|---|---|
| **Tier 1** | `QCloudSimulator` | Remote QpiAI cloud simulator (`STATEVECTOR_SIMULATOR_CPU`) | Production / Connected mode |
| **Tier 2** | `QSVLocal` | Local CPU `StatevectorSimulator` | Fast local quantum simulation |
| **Tier 3** | `ExactBruteForce` | Classical exhaustive search over $2^n$ bitstrings ($n \le 16$) | Ground truth benchmark & small instances |
| **Tier 4** | `NetworkXGreedy` | NetworkX greedy 2-approximation / spectral cut | Fast heuristic baseline |

Every call persists execution evidence to `evidence/qcloud_runs/<ts>_<hash>.json`, tracking:
`{tier, depth, shots, cut_value, approximation_ratio, time_ms, partition, evidence_file}`.

