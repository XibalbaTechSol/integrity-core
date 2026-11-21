# Integrity Protocol v1 Specification

**Status:** Normative Specification
**Normative:** this document
**Informative:** `WHITEPAPER.md`, `CONTROLS_MATRIX.md`, `EXECUTION_PLAN.md`
**Version:** 1.0.0
**Date:** November 2026
**Author:** Jacob S. Vickers, Xibalba Solutions, LLC

Implementations claim conformance only against this file. The current explanatory whitepaper is `WHITEPAPER.md` (v3.2); older v3, v0.3, v0.4, and v0.5-proposed documents are archived.

The key words MUST, MUST NOT, SHOULD, MAY are RFC 2119.

Status tags on a requirement:

| Tag | Meaning |
|---|---|
| `[BUILT]` | Present in `integrity-core` (or the named product repo) on `main` and treated as the live path |
| `[PARTIAL]` | Exists; this document's semantics supersede older docs. The reduction is disclosed here. |
| `[PLANNED]` | Normative when shipped; not required to claim v1 kernel conformance |
| `[EXPERIMENTAL]` | Exists as a non-deployed, non-production slice. MUST NOT be claimed as the live path. |

A tag applies to the nearest heading or bullet. Untagged text is definitional.

**How to read this file**

| If you are… | Read |
|---|---|
| Deciding whether to buy or enclose an agent | `WHITEPAPER.md`, then stop. Come back here only for a status tag. |
| Implementing the hook, oracle, SDK, or a pack | This file, in order. §4–§7 are the contract. |
| Mapping a control to HIPAA / NIST / OWASP | `CONTROLS_MATRIX.md`. It does not add requirements. |
| Sequencing the work | `EXECUTION_PLAN.md`. It does not add requirements. |
| Tracking what this file names but doesn't yet define | [`docs/design/spec-open-definitions.md`](design/spec-open-definitions.md). It does not add requirements either — it proposes fills for gaps this file already discloses (e.g. `scope` in §4.5). |

---

## 1. Conformance

A **v1 Core** implementation MUST provide:

1. An enclosed account whose state transitions are mediated by the hook in §6.
2. Evaluation of a constraint vector \(C\) on the **post-state** per §5.
3. An evidence plane (§8) that stores signed packages and exposes epoch cursors.
4. An oracle that verifies those packages and submits roots (§8.3).
5. Pack loading per §7. A Core MAY ship with zero packs installed; it MUST accept a pack that satisfies the schema.

A **v1 Pack** MUST be conservative (§7.2 R4). A pack MUST NOT be required to implement Integrity Health, ZK ingest, or a second chain.

**Conformance levels:**

| Level | Required |
|---|---|
| **L0 — Record** | Signed spans + evidence store + oracle verify/anchor. No hook. |
| **L1 — Constrain + record** | L0 plus a hook that evaluates a pack's \(C\) on the enclosed account. |
| **L2 — Full v1** | L1 plus escalate (deny-on-timeout) and at least one non-stub pack. |

v1.0 targets **L1/L2 on EVM chains, multi-OS runtime agents, and modular pack loading**. Independent audit and a machine-checked invariance argument are the continuous verification gate for production releases.

### 1.1 Closed-Loop Dynamical Systems Model

Integrity treats autonomous agent execution as a bounded continuous/discrete feedback control system:

\[
\dot{x}(t) = A x(t) + B u(t) + w(t)
\]

where:
- \(x(t) \in X\) is the agent's verifiable internal state vector (balances \(b\), allowances \(\ell\), nonces \(n\), consumable resource meters \(q\), installed modules \(m\), policy parameters \(\pi\), and memory hash-chain head \(h\)).
- \(u(t) \in U\) is the control action vector chosen by the agent's LLM/policy harness (target contract, value transfer, calldata, operation).
- \(w(t) \in W\) represents exogenous disturbances (market slippage, counterparty actions, RPC latencies, environment changes).
- The admissible safe state set is defined by the constraint vector \(C = (g_1, \ldots, g_m)\):
  \[
  S_C = \{\, x \in X \mid g_i(x) \le 0 \quad \forall i = 1,\ldots,m \,\}
  \]

The protocol guarantees forward invariance: if \(x(0) \in S_C\), then for all \(t \ge 0\), \(x(t) \in S_C\). The enforcement hook acts as a real-time Lyapunov barrier / projection operator that checks the post-state \(T(x_k, a)\). If any \(g_i(T(x_k, a)) > 0\), the execution reverts with zero state mutation, preventing the system from ever departing \(S_C\).

Furthermore, the agent's reinforcement learning / policy gradient objective incorporates the Agent Integrity Score (AIS) via bounded reward shaping:

\[
R_{\text{total}} = R_{\text{task}} + \lambda \cdot \text{AIS}
\]

where \(\lambda \ge 0\) aligns optimization incentives with boundary compliance. AIS widens finite operational envelopes within strict upper bounds (\(c_i^{\max} < \infty\)), but MUST NEVER turn a hard constraint `deny` into `allow`.

---

## 2. Objects and planes

v1 is a three-plane system. No other top-level plane is defined.

| Plane | Object | Role | MUST NOT |
|---|---|---|---|
| **Enforce** | Account \(A\), Hook | Modular smart account (`SovereignAgent` or Safe+Safe7579). `IntegrityHook` (ERC-7579) evaluates \(C\) post-state and reverts on violation. | Become an analytics platform |
| **Record** | Super-Cortex (reference), Oracle | Persistent evidence, neural memory, hash-chained spans; verify and anchor roots | Become the final authority to move funds; be a second hook |
| **Learn** | AIS | Evidence-derived integrity measurement and reward shaping | Create unbounded authority; turn deny into allow |
| **Settle** | Chain (StateAnchor, account, singletons) | Tamper-evident commitments and high-value settlement | Store raw telemetry or PHI |

```mermaid
flowchart TB
    subgraph DR["Device / runtime — own repos, own release trains"]
        SHIELD["xibalba-shield<br/>senses · contains · OPA policy · emits signed spans"]
        CORTEX["super-cortex<br/>hash-chained memory · 3D fabric · session Merkle root"]
    end
    subgraph CORE["integrity-core — the protocol"]
        PACK["Pack<br/>Integrity Health first"]
        HOOK["IntegrityHook (Enforce)<br/>post-state C, revert on violation"]
        ORACLE["Oracle (Record)<br/>verify sig/leaf → epoch → anchor"]
        AIS["AIS (Learn)<br/>finite bounds only, never a permission"]
    end
    CHAIN["Public chain (Base / EVM)<br/>StateAnchor, SovereignAgent, Singletons, Settlement"]

    SHIELD -- "signed spans, local allow/deny" --> PACK
    CORTEX -- "session roots (not a verifier)" --> ORACLE
    PACK --> HOOK
    HOOK -- "admit / revert" --> CHAIN
    ORACLE -- "verified evidence" --> AIS
    AIS -. "widen finite bound only" .-> PACK
    ORACLE -- "anchorRoot" --> CHAIN
```

Shield can run with no Core; Super-Cortex can run with no Core. The closed loop is Shield and Super-Cortex both calling Core: local containment plus durable memory plus an account that cannot leave the box.

**Shield** (`xibalba-shield`, own repo) is a runtime security product that provides local process containment, response governance, OPA Rego policy evaluation, and signed telemetry span emission. It is not an on-chain protocol object.

**Console** (`integrity-console`, own repo) is an operator verification and governance interface providing unified surfaces (`view-graph`, `view-timeline`, `view-dialogue`, `view-fabric`). It is not an on-chain protocol object.

**Super-Cortex** (`super-cortex`, formerly `xibalba-cortex`, own repo) is Integrity v1's persistent evidence and memory plane in the **reference architecture**. It provides a 3D neural knowledge graph, RFC 8628 agent pairing, session hash chaining, and Merkle root anchoring. A conforming enterprise deployment MAY substitute a certified store. Super-Cortex MUST NOT be a second verifier. The oracle verifies; Super-Cortex stores, indexes, and serves replay.

**AIS** is derived from verified evidence. It is a parameter of \(C\), never a permission.

---

## 3. Types

### 3.1 Account state

Let \(X\) be the finite set of EVM state assignments reachable by \(A\).

At step \(k\):

\[
x_k = (b_k, \ell_k, n_k, q_k, m_k, \pi_k, h_k) \in X
\]

| Field | Type | Meaning |
|---|---|---|
| \(b\) | balances | Native and token balances controlled by \(A\) |
| \(\ell\) | allowances | ERC-20 / operator approvals |
| \(n\) | nonce | Replay counter |
| \(q\) | meters | Remaining consumable units, keyed by meter id |
| \(m\) | modules | Installed ERC-7579 modules and their config |
| \(\pi\) | params | Operator / pack parameters (finite bounds, allowlists). Not the agent's policy. |
| \(h\) | `bytes32` | StateAnchor head: commitment to durable memory |

The agent policy (model + harness) is **not** a field of \(x\). It is outside the TCB.

`kill_epoch` is a monotone meter on the account. An intent whose `kill_epoch` does not equal the account's MUST fail.

### 3.2 Action

\[
a \in U = \{(\mathit{to}, \mathit{value}, \mathit{calldata}, \mathit{op})\}
\]

`op` is call, delegatecall, or batch. A batch is one \(a\) whose components MUST each be mediated.

### 3.3 Identity: The 3-Tier Identity and Actor Topology `[BUILT]`

Constraints MUST be keyed by a durable agent id, not a raw key.

```text
AgentId      = IntegrityDid | ERC8004TokenId
IntegrityDid = "did:integrity:" || sha256(pubkey)
ChainRef     = EIP155ChainId
AccountRef   = CAIP10Account
PackId       = name "@" semver
MeterId      = bytes32
```

\(C\) is a function of identity. Key rotation MUST NOT drop \(C\). An implementation that binds \(C\) only to `msg.sender` when that sender is a rotatable EOA is non-conformant.

The protocol defines a three-tier modular identity and actor stack:

```mermaid
flowchart TD
    T0["Tier 0: Off-Chain Cryptographic DID<br/>did:integrity:<sha256(pubkey)><br/>Ed25519 keypair · zero-gas · RFC 8785 canonical JSON"]
    T1["Tier 1: On-Chain Actor & Smart Account Stack<br/>AgentRegistry singleton · SovereignAgent / Safe+Safe7579<br/>IntegrityHook · IntegrityGuard · SafeAccountVerifier · TrustLayer singletons"]
    T2["Tier 2: Modular ERC-8004 / Agent0 Public Passport<br/>Public discovery layer · two-way DID backlink (RFC 8785)<br/>CAIP-10 registrations · Oracle-verified wallet_confined: true"]

    T0 -- "Registers with Oracle & binds CAIP-10" --> T1
    T1 -- "Enforces wallet confinement & AIS" --> T2
    T2 -. "Resolves via DID service backlink" .-> T0
```

1. **Tier 0: Gasless Off-Chain Ed25519 DID (`did:integrity:<sha256(pubkey)>`) `[BUILT]`**
   - Pure cryptographic root identity. Generated locally with zero gas cost.
   - Identified by `did:integrity:<hex-sha256(ed25519_pubkey)>`.
   - Used by autonomous agents for high-frequency signing of telemetry spans, BCC intent messages, and peer-to-peer agent negotiation over RFC 8785 canonical JSON (JCS).
   - Registered off-chain with the Integrity Oracle via `POST /v1/agent/register/offchain`.

2. **Tier 1: On-Chain Actor & Smart Account (`AgentRegistry` + `SovereignAgent` Wallet Stack) `[BUILT]`**
   - Enclosed on-chain execution identity on Base Sepolia (`chainId: 84532`) or target EVM network.
   - Keyed in the canonical `AgentRegistry` singleton (`isRegisteredAgent(address) -> bool`).
   - All high-value or state-mutating actions execute through a policy-confined smart contract account: either `SovereignAgent.sol` or an enclosed Safe v1.4.1 account operating under the `Safe7579` adapter.
   - Enforced by the modular wallet security stack:
     - `IntegrityHook.sol`: ERC-7579 execution hook evaluating pre/post-state constraints, spend limits, AIS reputation floors, and staking gates.
     - `IntegrityGuard.sol`: Safe transaction guard preventing direct execution bypass or module tampering.
     - `SafeAccountVerifier.sol`: Validates account mastercopy, threshold == 1, single EOA owner, `Safe7579` sole module, and active `IntegrityGuard`.
     - Trust Layer singletons (`StakeVault`, `AISRegistry`, `ActionAnchor`, `PolicyRegistry`, `TrustConfig`) provide shared economic staking and reputation enforcement.

3. **Tier 2: Modular ERC-8004 / Agent0 Public Discovery Passport `[BUILT]`**
   - Standardized public discovery layer compliant with ERC-8004 ("Trustless Agents") and the Agent0 ecosystem.
   - Pinned on Base Sepolia (`0x8004A818BFB912233c491871b3d84c89A494BD9e`).
   - Registration document schema (`registration-v1`) enforces a cryptographic two-way `DID` service backlink (`services[name=DID]` -> `did:integrity:<sha256>`) and CAIP-10 `registrations` references (`eip155:<chainId>:<registry>`).
   - The registered `agentWallet` MUST point to the agent's policy-confined smart account (e.g. `SovereignAgent`), not an unconfined EOA.
   - The Integrity Oracle verifies this binding via `POST /v1/agent/{id}/erc8004` and reports `wallet_confined: bool`.
   - Feedback and reputation sync through `IntegrityERC8004Registry.sol` / `ERC8004ReputationRegistry` with the `https://integrity.xibalba.solutions/ext/erc8004-ais-feedback-v1` extension.

### 3.4 Account Profiles and Singleton Trust Layer `[BUILT]`

Both enclosed enterprise agents and sovereign economic agents use the same hook, evidence format, memory chain, AIS inputs, and packs.

| Profile | Ownership | On-chain footprint | v1 commercial default |
|---|---|---|---|
| **Enclosed enterprise agent** | Organization-owned ERC-4337 account; agent session keys; operator governance | Account + `StateAnchor` head + `AgentRegistry` record. No per-agent clone set. | Yes |
| **Sovereign economic agent** | Identity bound to agent-controlled `SovereignAgent` smart account | `SovereignAgent` + `StateAnchor` head + `AgentRegistry` record + shared Trust Layer. | Optional, not required |

#### 3.4.1 Architecture Evolution: From 7 Clones to Singleton Trust Layer

Early prototype revisions (v0.3–v0.4) deployed 7 distinct EIP-1167 clones per agent (`ReputationRegistry`, `Slasher`, `VerifierRegistry`, `ComplianceGate`, `AgentProfile`). 

In v1.0, the protocol has unified around **shared canonical singletons** to eliminate per-agent deployment gas, consolidate liquidity, and eliminate fragmented state:

- **`AgentRegistry.sol`** (singleton): Authoritative registry of all active agents, controller addresses, lineage (`AgentLineageRegistry`), and policy configurations.
- **`StakeVault.sol`** (singleton): Shared economic collateral vault holding $ITK stake, locking stake per-action, managing the unbonding queue, and latching freeze state when AIS falls below threshold.
- **`AISRegistry.sol`** (singleton): On-chain score checkpoints (basis points, `0..10000`) and evidence Merkle roots posted by the Integrity Oracle.
- **`ActionAnchor.sol`** (singleton): Global Merkle root anchor recording verified action traces.
- **`PolicyRegistry.sol`** (singleton): Domain-level action graphs, risk weights, and policy modules.
- **`TrustConfig.sol`** (singleton): Governance-owned configuration linking the vault, policy registry, and reward modules.

For agents operating under the sovereign profile, the agent deploys its own `SovereignAgent` account and signs its own identity initialization. Enterprise agents utilize standard ERC-4337 or Safe accounts. Neither profile requires minting an NFT or deploying legacy clone sets.

### 3.5 Reputation parameter

Let \(r \in [0,1]\) be an attested score (AIS, or ERC-8004 if the operator pins it). For each numeric bound \(c_i\):

\[
c_i(r) = c_i^{\min} + r\,(c_i^{\max} - c_i^{\min}), \qquad c_i^{\max} < \infty
\]

An implementation MUST reject configuration with \(c_i^{\max} = \infty\). \(r\) MAY widen a bound. \(r\) MUST NOT remove a constraint. \(r\) MUST NOT change a pack `deny` into `allow`.

### 3.6 Memory commitment `[PARTIAL]`

\[
h_{k+1} = H(h_k \,\|\, H(\delta_k))
\]

\(H\) is a collision-resistant hash (SHA-256 or keccak256; a deployment MUST name one). Only \(h_k\) is required on-chain. Payload lives in the evidence plane, content-addressed by the leaf. Presenting a history inconsistent with \(h_k\) MUST fail verification.

Genesis: registration SHOULD require a non-zero \(h_0\). Enforcing `latestRoot != 0` at `registerPrimitives` and oracle ingest is `[PLANNED]` (P0).

### 3.7 Domain separator `[BUILT]` (BCC path)

An intent is valid in exactly one domain, exactly once.

```text
Domain = lenpref(chainId) || lenpref(account) || lenpref(packId)
       || lenpref(licenceOrMeterId) || lenpref(epoch)
```

Encoding MUST be length-prefixed. Concatenation of raw strings is non-conformant. Nonce MUST be strictly monotone in that domain.

Live BCC commitments bind `chain_id` and `verifying_contract`. The ZK circuit
also binds its intent commitment to the chain, receiving ReputationRegistry
clone, and exact anchored BCC leaf. `[PLANNED]`: a kernel hook-frame
replay-domain binding (the experimental slice's was archived 2026-11-16).

**Canonical JSON `[BUILT]`:** all signed BCC/telemetry payloads use RFC 8785
JCS: Python consumers use `jcs` and the Rust oracle uses `serde_jcs`. This is
the normative byte representation for number formatting and non-ASCII UTF-8.

---

## 4. Constraint grammar

This section is the v1 language. Packs compile into it. The hook evaluates it. Nothing else is enforced on-chain.

### 4.1 Sign convention

A constraint is \(g : X \to \mathbb{R} \cup \{+\infty\}\).

\[
g(x) \le 0 \quad\text{means satisfied.}
\]

The admissible set is

\[
S_C = \{\, x \in X \mid g_i(x) \le 0 \text{ for all } i = 1,\ldots,m \,\}.
\]

The margin of a state is \(\min_i (-g_i(x))\). The hook SHOULD expose per-\(g_i\) margin to the console.

### 4.2 Abstract syntax `[PARTIAL]`

```text
C            = g ("," g)*
g            = g_id ":" expr
expr         = cmp | "AND" "(" expr ("," expr)+ ")"
             | "OR"  "(" expr ("," expr)+ ")"   ; pack-local only; see 4.4
cmp          = term op term
op           = "<=" | ">=" | "==" | "!="
term         = UINT | ADDR | BYTES32 | BOOL
             | state_ref | param_ref | call
state_ref    = "pre." path | "post." path
path         = "balance" "[" ADDR "]"
             | "allowance" "[" ADDR "]" "[" ADDR "]"
             | "nonce"
             | "meter" "[" MeterId "]"
             | "module" "[" ADDR "]" ".installed"
             | "head"
             | "timestamp"
param_ref    = "param." IDENT
             | "id." IDENT
             | "r"
call         = "sum_out" "(" window "," destset ")"
             | "attestation_age" "(" AgentId ")"
             | "owner_of" "(" ADDR ")"
```

`pre` is \(x_k\). `post` is \(T(x_k, a)\). A constraint that reads only `pre` and ignores `post` for a quantity the action can change is non-conformant for that quantity.

The experimental kernel slice (`IntegrityKernel`, formerly `IntegrityKernelV1Experimental`) implemented a **reduced** grammar: native-value spend budget, a reputation-floor precondition, and a ZK-assurance-tier precondition. It was not this grammar. It was archived on 2026-11-16 and has no implementation on `main` (`docs/archive/2026-11/kernel-phase1/README.md`). Status: `[PLANNED]`. It MUST NOT write storage in `preCheck`. Projected checks belong in `preCheck`; conservation of realized post-state belongs in `postCheck`.

### 4.3 Concrete YAML (pack surface)

```yaml
pack: integrity-health@1.0.0
constraints:
  - id: daily_outbound
    g: post.sum_out(24h, NOT allowlist) - param.daily_cap
  - id: meter_nonneg
    g: 0 - post.meter[ehr_write]
  - id: no_self_uninstall
    g: 1 - post.module[KERNEL].installed
  - id: spend_cap
    g: (pre.balance[USDC] - post.balance[USDC]) - param.max_usdc_out
```

`g` in YAML is the real-valued expression. Compilers MUST NOT invert the sign. Unknown identifiers MUST fail closed.

### 4.4 Conjunction at the hook

\[
V(a,x,C) = \prod_{i=1}^{m} \mathbf{1}[g_i(T(x,a)) \le 0] \in \{0,1\}
\]

`OR` MAY appear **inside a single pack-local** \(g_i\). `OR` MUST NOT be used to let one pack disable another pack's \(g_j\).

**Hook wins:** if Rego returns allow and \(V = 0\), the transition MUST NOT commit.

### 4.5 Primitive families `[PARTIAL]`

**Value conservation (settlement).** For participant set \(P\) and declared fee to a named recipient:

\[
\sum_{j \in P} \Delta b_j = 0
\]

A transition that mints, burns, or leaks MUST revert unless a constraint **explicitly** authorizes that class. Native ETH balance alone is non-conformant as the conservation check; ERC-20/721 and allowances MUST be in scope for any pack that claims value conservation.

**Monotone meters.** Working **and** inbound orders update meters in `preCheck` on the projected book. A reject rolls the projection back. Caps apply to working + filled, not filled only.

\[
q_{k+1} = q_k - c_k,\quad c_k \ge 0,\quad q_{k+1} \ge 0,\quad q_0 = Q
\]

A meter MUST NOT increase except by an operator-signed refill that is itself constrained. AIS MUST NOT refill a loss cap.

**Replay domain.**

\[
n_{k+1} > n_k,\qquad d(a) = d_{\text{declared}}
\]

**Delegation / license (`delegation_active`).** A principal-to-agent grant: `(principal, agent, scope_hash) → {active, expires, meter}`. The hook MUST treat a missing, expired, revoked, or out-of-scope grant as \(V = 0\) when the installed pack requires one. Integrity Health's `SmartBAA` is the first on-chain body of this family (covered entity = principal, business associate = agent, PHI class = scope). An IP-license pack is the same family with a different principal and scope. Packs MUST NOT each invent a second `checkAccess` idiom that bypasses this family.

Status: `[PARTIAL]` — `SmartBAA` is `[BUILT]`; a kernel-level view `(principal, agent, scope_hash)` that both Health and IP consume is `[PLANNED]`. The client supplies `covered_entity_address` only as a lookup key: BCC authorization and Healthcare oracle scoring resolve the exact live `(covered entity, SovereignAgent)` pair through `CoveredEntityRegistry` and `SmartBAAFactory`, failing closed when it is not bound. Generalizing that relationship into the cross-domain authority view remains planned.

**`scope` is not yet defined — a known hole, not an omission by oversight.** This section
requires an "out-of-scope grant" check and a "PHI class = scope" / "IP-license = same family,
different scope" reading, but never says what a scope *is* beyond an opaque `scope_hash`.
Containment against an opaque value is undecidable, so today's enforcement is exactly what
`SmartBAA` hard-codes, not a general capability check. A typed capability algebra is proposed in
[`docs/design/spec-open-definitions.md`](design/spec-open-definitions.md) §1 and must land
before the `[PLANNED]` kernel-level view above is implementable.

### 4.6 Gas bound

Each \(g_i\) MUST declare `gas_max`. Evaluation MUST use a metered call. Exceeding `gas_max` MUST be treated as \(V = 0\), not as "skip this constraint."

The v3 whitepaper's 40k `preCheck` budget is a target, not a silent requirement of this spec. For the current reference implementation, the measured target profile is one direct, cold external `IntegrityKernel.preCheck` call, including call and `onlyBoundAccount` modifier overhead, with the registry-adapter and tracked-token branches disabled. It includes the cached reputation/assurance checks, native-budget checks, and balance snapshot; it excludes the account's hook-dispatch overhead, `postCheck`, snapshot refresh, token balance calls, adapter calls, and transaction intrinsic gas. The compiler, optimizer, EVM revision, cold/warm state, enabled branches, and measured commit MUST accompany any exact figure.

Live reads of foreign registries MUST be amortized (epoch snapshots) or named as a separate adapter-inclusive profile outside that 40k target. Such an exception MUST identify the adapter, enabled branches, measurement profile, and regression band; it MUST NOT be described as a protocol maximum or generalized to arbitrary adapters. A self-declared adapter stipend is only the requested call stipend unless the caller also enforces a reviewed maximum and reserve; it is not by itself an end-to-end operation gas bound. Do not claim both a 40k cap and live ERC-8004 / licence TBA reads on every call.

### 4.7 Forbidden

A conformant compiler MUST reject:

- Unbounded loops over attacker-supplied arrays
- Reads of `block.coinbase` or `prevrandao` to decide \(g_i\)
- A constraint that is satisfied when evaluation throws
- \(c^{\max} = \infty\)
- Relaxation of another pack's \(g_j\)
- World-event predicates ("the election result is X")
- Fail-open on oracle-cursor staleness, for the value path
- Storage writes in `preCheck`

---

## 5. Verification rule

Let \(T\) be the EVM transition of \(A\).

\[
x_{k+1} =
\begin{cases}
T(x_k, a_k) & \text{if } V(a_k, x_k, C) = 1 \\
x_k & \text{otherwise (revert)}
\end{cases}
\]

Rejection MUST be a revert. It MUST NOT be a compensating transaction.

`preCheck` MAY reject on **projected** post-state. `postCheck` MUST re-check conserved quantities on the **realized** post-state and revert if they do not hold. A pass in `preCheck` and a fail in `postCheck` MUST leave \(x_{k+1} = x_k\).

This is the errata to whitepaper v3 Appendix A. Projected arithmetic is not \(T(x,a)\). Claiming Proposition 1 of a `preCheck`-only native-balance gate is non-conformant.

```mermaid
flowchart LR
    A["Proposed action a_k"] --> B{"preCheck: g_i(projected<br/>post-state) ≤ 0 ∀i ?"}
    B -- "no — revert" --> X1["x_k+1 = x_k"]
    B -- "yes" --> C["Execute T(x_k, a_k)"]
    C --> D{"postCheck: conserved<br/>quantities on realized<br/>post-state hold?"}
    D -- "no — revert" --> X2["x_k+1 = x_k"]
    D -- "yes — commit" --> E["x_k+1 = T(x_k, a_k)"]
```

### 5.1 Forward invariance `[PLANNED]` as machine-checked

**Proposition 1.** If \(x_0 \in S_C\) and every transition of \(A\) is mediated by the rule above, then \(x_k \in S_C\) for all \(k \ge 0\), for every sequence \(a_0, a_1, \ldots\), including adversarial sequences and sequences signed with stolen keys.

Proof is induction on \(k\): a revert leaves \(x_k \in S_C\); an accept has \(T(x_k,a_k) \in S_C\) by definition of \(V\).

Proposition 1 does not say \(S_C\) is a good box. A catastrophe that \(C\) permits is permitted with assurance. If any of M1–M5 fail, Proposition 1 is **void**, not degraded.

Independent audit plus a machine-checked argument is the named gate for non-draft v1.0.0.

### 5.2 Placement `[PLANNED]`

The kernel MUST be an ERC-7579 type-4 hook. `preCheck` / `postCheck` MUST run on every execution path named in §6, including `executeFromExecutor` and module install/remove.

Live production `SovereignAgent.execute()` does **not** dispatch through this full ERC-7579 hook. A disclosed, non-production reference instance (`IntegrityKernel` + `IntegrityAccount`, Halmos-checked) was archived on 2026-11-16; its source is no longer on `main`, and its Base Sepolia contracts (`deployments.baseSepolia.json` → `experimentalPhase1Reference`) remain deployed but unused (`docs/archive/2026-11/kernel-phase1/README.md`). A reference instance MUST NOT be wired to any real registered agent, and MUST NOT be referenced by *production* deployment tooling. §5.3 describes the narrower mechanism actually live in production accounts today.

A companion type-1 validator MAY enforce session keys. Rich policy that reads foreign account state MUST NOT be placed only in the ERC-4337 validation phase.

### 5.3 Live execution/anchor policy hooks `[BUILT]`

Distinct from, and narrower than, §5.2's full ERC-7579 kernel hook: live `SovereignAgent.execute()` and `StateAnchor.anchorRoot()` each consult a swappable, fail-closed policy contract set by the controller -- `IExecutionPolicy` / `IAnchorPolicy` (`contracts/src/core/`), installed via `setExecutionPolicy` / `setAnchorPolicy`. `address(0)` on the host is the skip path (no policy installed, matching today's already-registered agents). Once a policy is set, a `false` return or a revert from it MUST fail closed: no value movement, no root write, no nonce consumption.

This is real and already live in `SovereignAgent.sol` / `StateAnchor.sol`'s deployed-going-forward source, not a proposal. `ConstraintExecutionPolicy.sol` (AIS floor, native-value cap, target allowlist, ERC-20/721 caps) and `AllowlistAnchorPolicy.sol` are working reference implementations, covered by `contracts/test/PolicyHooks.t.sol`.

**Deployed-vs-live gap, disclosed, not glossed over:** `SovereignAgent` / `StateAnchor` are deployed directly per agent, not behind a shared upgradeable proxy (§16's file-authority table's own upgradeability item; `docs/design/upgradeability-decision.md`; `MAINNET_READINESS.md` P0-6). This hook therefore only reaches an agent whose registration happened after the hook landed in the bytecode that registration deployed. Verified directly on-chain 2026-08-31: `executionPolicy()` reverts against all three currently-registered real agents on Base Sepolia (`xibalba.integrity`, `xibalba-health` -- registered 2026-08-30, still predates this -- and `xibalba-quant`), while a genuinely-supported call (`ais()`) succeeds against the same contracts, confirming the gap is "feature absent from that deployment," not a network or ABI-mismatch artifact. A new registration going forward gets the hook automatically; an already-registered agent cannot, short of resolving the open upgradeability decision.

---

## 6. Complete mediation `[PLANNED]`

Let \(E\) be the set of paths that can change \(A\)'s state. The hook MUST be invoked on every path in \(E\).

A deployment is **mediated** only if all of the following hold:

| ID | Rule |
|---|---|
| M1 | No value that the operator treats as in-scope MAY live in an EOA or contract the hook does not mediate. |
| M2 | Direct execute, executor modules, fallback handlers, and batches MUST route through the hook. |
| M3 | Module install and removal MUST be constrained transitions. |
| M4 | Kernel removal MUST be delayed and multi-authorized. Immediate self-uninstall MUST revert. |
| M5 | A new executor that bypasses the hook MUST be uninstallable only via M3–M4, and MUST fail mediation audit until removed. |

Implementations SHOULD expose a `mediation_ok` boolean from a published audit checklist. Console SHOULD refuse "enclosed" labeling when `mediation_ok` is false.

The archived experimental slice covered `execute()` against three reference conditions and a **single-signer** kernel swap, a disclosed reduction of M4. No implementation exists on `main` since 2026-11-16.

Re-enable of a killed account is `Escalate` class `reenable`: two humans, or one human plus delay. The agent MUST NOT clear its own kill.

---

## 7. Packs

v1 extension surface. A pack compiles to \(C\) plus off-chain policy. A new vertical that needs a new daemon, a new brand, or a fourth verb is not a pack.

### 7.0 Three layers, two extra words

Keep this small:

```text
integrity-core          protocol: hook + oracle + singletons + pack loader     (this repo)
xibalba-shield          product: device / network agent / OPA containment      (own repo)
super-cortex            product: evidence / memory plane / 3D knowledge fabric  (own repo)
```

Inside Core, specialization is only a **pack**. An **adapter** is not a pack and not a product. It is a translator that maps someone else's schema into a pack. It adds no constraint of its own.

| | Lives | Example |
|---|---|---|
| **Pack** | `integrity-core` folder | Integrity Health (`packs/integrity-health`) |
| **Adapter** | next to a pack, or in a product SDK | AP2 mandate → Integrity Health params; FIX → `packs/trading`; loopback test broker |
| **Product** | its own GitHub repo | Shield, Super-Cortex, Integrity Console |

Integrity Health is the first pack, not an adapter and not Shield. `contracts/src/health/` (`CoveredEntityRegistry`, `SmartBAA`, `ComplianceGate`, `EHRGate`, `HIPAAGuardrailRegistry`) is the current `[PARTIAL]` on-chain body of that pack. The pack-folder form is `[PLANNED]`. Shield **loads** Integrity Health; it does not own it.

If a new venue or mandate format needs a new constraint id, write an adapter. If a new vertical needs new constraints, write a pack. If it needs a new daemon or a new brand, it is a product repo, not Core.

### 7.1 Schema `[PLANNED]` as the only extension API

```text
packs/<id>/
  pack.yaml           required — manifest
  constraints.yaml    required — compile input for the hook
  policy.rego         required — off-chain allow / deny / escalate
  redact.rules        required — what Path A may upload
  controls.yaml       required — officer-facing form fields
  profile.md          informative — vertical map (HIPAA, IP, trading, …)
  views.yaml          informative — console widgets
```

```yaml
# pack.yaml
id: integrity-health
version: 1.0.0
kernel: ">=1.0.0-draft <2.0.0"
gas_max_total: 350000
params:
  daily_cap:        { type: uint256, c_max: "50000e6", default: "10000e6" }
  min_ais:          { type: uint256, c_max: 1000,      default: 600 }
  license_required: { type: bool,                      default: true }
escalation:
  classes: [ehr_write, baa_missing, license_missing]
  timeout: deny          # MUST be deny; allow is non-conformant
redact: enforce          # off | warn | enforce — see §7.7
domain: server-resolved  # never client-asserted
```

`PackId = id@version` plus content hash. Pin in the account. Installing or replacing a pack is a constrained transition. No on-chain adapter registry is required for v1. `[PLANNED]`: attested registry.

`constraints.yaml` is the authoring syntax of §4.3. The compiler **lowers** each `g` onto a closed family (§7.6). If it cannot lower, it rejects. The hook does not interpret arbitrary YAML on-chain.

`controls.yaml` is the officer UI contract: one form field per `params.*` id, labels in the buyer's language, no Solidity. Natural language MAY fill the form. The form is what gets hashed and pinned.

`policy.rego` input/output is the live BCC shape:

```text
input:  { agent_id, intent_type, covered_entity_address, pack_id, ... }
output: { allow: bool, violations: [string], escalate: string|null, requires_delegation: bool }
```

`requires_delegation` is the generic flag. Integrity Health's `requires_baa` is an alias of it, not a second protocol.

### 7.2 Obligations (was v3 adapter R1–R5)

| ID | Rule |
|---|---|
| R1 Determinism | Same payload → same \(C\). No time/coinbase/rand in compilation. |
| R2 Totality | Unparseable input → reject with a typed reason. Never silent accept. |
| R3 Bounded cost | Declared `gas_max`. No unbounded attacker iteration. |
| R4 Conservatism | MAY only add constraints. MUST NOT relax another pack or the base mandate. |
| R5 Identity | Published with source, machine-readable semantics, and a version hash the account pins. |

### 7.3 Composition

**Proposition 2.** If packs \(1..n\) induce \(C_1..C_n\), then

\[
S_{C} = \bigcap_{j=1}^{n} S_{C_j} \subseteq S_{C_j} \quad \forall j.
\]

Installing a pack MUST NOT enlarge the reachable set. Liveness MAY degrade. Console SHOULD show the binding \(g_i\) (least margin).

```mermaid
flowchart TB
    P1["Pack 1 constraints → S_C1"]
    P2["Pack 2 constraints → S_C2"]
    P3["Pack n constraints → S_Cn"]
    INT["Admissible set S_C = S_C1 ∩ S_C2 ∩ ... ∩ S_Cn"]
    P1 --> INT
    P2 --> INT
    P3 --> INT
    INT --> HOOK["Hook evaluates V(a,x,C) over S_C"]
    HOOK -.->|"installing a pack can only shrink S_C, never enlarge it"| INT
```

### 7.4 Policy vs constraints

`policy.rego` MAY `allow`, `deny`, or `escalate` off-chain or pre-hook. It MUST NOT authorize a transition that any installed \(g_i\) rejects. Hook wins. Rego is never compiled to Solidity.

### 7.5 Compiler `[PLANNED]`

Off-chain, in `integrity-sdk` (or a small `pack-compiler` module in `integrity-core`). Deterministic (R1). Unparseable input → typed reject, never accept (R2). The compiler MUST NOT emit a new Solidity contract per pack.

```text
compile(pack_dir, param_values) -> Result
  ok:
    pack_id, pack_hash, kernel_range
    constraints: [ConstraintRecord]
    policy_hash, redact_hash, controls_hash
    gas_max_total
  err:
    code: unknown_id | cannot_lower | unbounded | c_max_infinite
        | relaxes_other_pack | gas_max_missing | redact_required
    path, message
```

`ConstraintRecord` is what the hook stores. Closed v1 families — YAML may grow; this enum MUST NOT change without a spec revision:

| Family | Meaning | Status |
|---|---|---|
| `native_value_budget` | per-op + cumulative wei | `[PLANNED]` (experimental kernel archived 2026-11-16) |
| `token_out_cap` | ERC-20/721 out, allowlist dest | `[PLANNED]` |
| `meter` | monotone remaining units | `[PLANNED]` |
| `reputation_floor` | snapshot score ≥ min | `[PLANNED]` (experimental kernel archived 2026-11-16) |
| `assurance_tier` | ZK-boost / tier required | `[PLANNED]` (experimental kernel archived 2026-11-16) |
| `module_installed` | kernel cannot self-uninstall | `[PLANNED]` |
| `delegation_active` | principal→agent grant in scope | `[PARTIAL]` — SmartBAA body `[BUILT]`; kernel view `[PLANNED]` |

```mermaid
flowchart LR
    FORM["Officer form<br/>controls.yaml"] --> YAML["constraints.yaml + params"]
    YAML --> COMP["compile()"]
    COMP -->|cannot lower| REJ["typed reject"]
    COMP --> REC["ConstraintRecord[] + pack_hash"]
    REC --> PIN["account pins hash"]
    PIN --> HOOK["hook evaluates families"]
    REGO["policy.rego"] --> BCC["BCC / OPA"]
    BCC --> HOOK
```

### 7.6 First packs (informative)

| Pack | Question | Phase |
|---|---|---|
| stub | Can the loop run? | 1 |
| `integrity-health@*` | May this principal touch PHI? | 2 |
| `agents@*` | Is this workload a principal at all? | 3 |
| `ip-license@*` | May this principal read, infer from, or train on this proprietary scope? | 3 |
| `trading@*` | May this approved principal spend at this venue, this size, still alive? | 3+ |
| `markets@*` | May this principal list, bid, or settle in an AIS-gated market? | 3+ |
| `eu-ai-act@*` | Optional profile | only if a buyer asks |

`ip-license` and `markets` are packs. They are not kernel types. v3.2 Metered IP (ERC-6551 licence TBAs, ATCP/IP, adapter marketplace) remains archive; the access-gating pack does not require it. Existing `IntegrityMarket.sol` / `A2ACapitalPool.sol` stay in the repo as the first on-chain body of `markets@*`, not as v1 spine.

### 7.7 Redaction obligation `[PARTIAL]`

`pack.yaml` `redact` is one of `off | warn | enforce`.

| Mode | Path A unsigned/unredacted payload |
|---|---|
| `off` | Accept (non-regulated packs only) |
| `warn` | Accept and mark the package `redact_incomplete` |
| `enforce` | BCC and the oracle MUST reject. SDK constructor defaults MUST NOT be able to override this. |

Integrity Health and `ip-license` MUST ship `redact: enforce`. A deployment that claims either pack while Path A can upload raw PHI or proprietary content is non-conformant.

**Disclosed gap:** `integrity-sdk` integrations (`IntegrityOpenAI`, `IntegrityLangChainCallback`) default `redact_phi=False`. The SDK cannot infer the installed pack. Until BCC/oracle enforce `redact: enforce` server-side, default-off redaction is a Health and IP blocker, not an SDK preference. `trace_run` redacts unconditionally; the named integrations do not.

---

## 8. Evidence plane, oracle, and hybrid ledger `[PARTIAL]`

### 8.1 Split of duties

| Job | Who |
|---|---|
| Ingest, store, index, redact, replay | Cortex (reference) or a conforming store |
| Verify signatures, proofs, heads; advance `oracle_verified`; submit roots | Oracle |
| Hold \(h_k\) and settle value | Chain |

The oracle MUST NOT be renamed Cortex. Cortex MUST NOT submit roots except through the oracle, other than a documented disaster-recovery path that is itself audited.

### 8.2 Ingest contract (the dual-span rule)

Two pipes exist. They MUST NOT be confused.

| Path | Transport | May feed AIS? | Notes |
|---|---|---|---|
| **A — signed ingest** | HTTP `POST /v1/telemetry/ingest` (or BCC intercept) | Yes | Only AIS input. Oracle re-derives numeric signals; client `derived_signals` are audit-only. `[BUILT]` |
| **B — OTLP** | gRPC `:4317` | No | Operator traces. Unauthenticated. Stored separately. `[BUILT]` |

`otel_spans` on a signed Path A request are **not** the Path B OTLP table. Integrators MUST NOT score Path B as AIS. A signed-OTLP bridge is optional and MUST carry `integrity.agent.id` plus a signature before it may become Path A.

```mermaid
flowchart LR
    SDK["SDK / Shield / agent"] --> A["Path A — signed ingest<br/>POST /v1/telemetry/ingest"]
    SDK --> B["Path B — OTLP gRPC :4317<br/>unauthenticated"]
    A --> AIS["May feed AIS"]
    B --> OPS["Operator traces only<br/>never AIS"]
```

OpenTelemetry is the canonical collection convention. Integrity-specific attributes (agent id, pack id, policy version, decision, approval, tool, evidence hash) ride on the span. Hierarchical convention, informative: `agent.run` → `agent.plan_and_reason` (`agent.thought`) → `agent.execute_tool` (`gen_ai.*`).

When the installed pack sets `redact: enforce` (§7.7), PHI and proprietary content MUST be redacted before Path A egress, and BCC/oracle MUST reject an unredacted Path A package. SDK constructor flags MUST NOT override a pack `enforce`. `[PARTIAL]` — see §7.7 disclosed gap.

### 8.3 Package and verify

```text
Package = {
  agent_id, account, pack_id, domain,
  leaf,           # H(span)
  head_claimed,   # claimed h_k
  span_or_proof,  # redacted span XOR zk public inputs + proof
  decision,       # allow | deny | escalate | resolved
  V_reasons[],
  cursor,
  sig
}
```

In default mode the SDK MAY send a redacted span. In `profile: zk` the SDK MUST NOT send raw regulated content.

The oracle MUST:

1. Check `sig` against the agent's current keys (`sha256(pubkey)` matches `AgentId`).
2. Check `domain` and nonce.
3. Check `leaf` inclusion against `head_claimed`, or verify the ZK statement.
4. Reject if `head_claimed` is not a descendant of the last accepted head (no forks).
5. Independently re-derive any numeric signals used as AIS inputs. `[BUILT]` for entropy/grounding/sacrifice on Path A.
6. Advance `oracle_verified`.
7. Submit `anchorRoot` to StateAnchor. After inclusion, advance `chain_anchored`.

High-risk actions, approvals, policy changes, and incidents SHOULD be anchored immediately. Low-value spans MAY batch. Cadence is a deployment parameter.

### 8.4 Cursors

```text
Cursor = observed | oracle_verified | chain_anchored
```

Always \(\textit{chain_anchored} \le \textit{oracle_verified}\).

Policy that evaluates a decision MUST record the cursor pair it used. A later, more authoritative epoch that would have denied MUST be attributable to those decisions (replay), not silently overwritten.

Stale cursor on a value-increasing path MUST fail closed when the pack requires a fresh cursor. Reduce-only MAY remain open if `allow_reduce_on_stale = 1`.

### 8.5 Cortex responsibilities (reference)

- Canonical event ingestion from SDK, Shield, tool gateways, and account receipts.
- Persistent agent memory as an append-only commitment chain.
- Evidence bundles for audit, incident response, and model evaluation.
- Derived features for AIS.
- Cursor management.
- Policy and pack version pinning.
- Replay APIs: what the agent knew, which policy applied, what it attempted, and why it was allowed or denied.

Cortex MAY inform a future action. The hook decides whether a specific value-moving action commits.

### 8.6 Cortex reference implementation — disclosed anchoring gaps `[PARTIAL]`

The reference evidence store's local hash-chain and session-Merkle-root construction (§3.6) are `[BUILT]` and independently sound, but the step that anchors a Cortex session root into this protocol's on-chain commitment (§8.3) has four open, named gaps. A deployment MUST NOT claim "session evidence anchored and ancestry-verified end to end" until these are closed.

| Gap | What's true today | Why it matters |
|---|---|---|
| Hash-space mismatch | Cortex's session Merkle root is a sorted-pair root over **SHA-256** leaves. This protocol's on-chain `StateAnchor`/`TrustVault` convention is a sorted-pair root over **keccak256** leaves. The two are never converted or compared. | A root anchored from Cortex cannot be verified against on-chain state without an explicit re-hash step that does not exist yet. Per §3.6, a deployment MUST name one hash function — Cortex and the chain currently name different ones for the same session. |
| No receiving contract or schema | Cortex's `anchor_session_root()` posts to an operator-configured `XIBALBA_ANCHOR_URL`. Neither repo documents what that endpoint must accept, validate, or return. | §8.3's oracle verification steps (sig, domain, leaf inclusion, head-descendant check) have no defined counterpart for a Cortex-originated root. |
| Unauthenticated anchor submission | The anchor POST carries no DID signature, no nonce — unlike every other producer's Path A telemetry (§8.2). | Anyone who can reach the configured URL and knows the expected shape could submit a claimed root. §8.3 Step 1 ("check `sig` against the agent's current keys") has nothing to check for this path today. |
| Conformance vectors are a stub | The "portable event kernel" batch-Merkle profile is documented as reproducible by an independent implementation, with test vectors meant to prove it. The vector file is a 16-line placeholder. | Interoperable, cross-implementation verification of Cortex evidence is not yet demonstrable. |

Closing these is protocol-side work (define the receiving contract, pick who owns the hash-space conversion) as much as Cortex-side work; see `EXECUTION_PLAN.md` §6.

---

## 9. Decision grammar

Off-chain / pack policy. Does not replace \(V\).

```text
Decision     = Allow | Deny | Escalate
Allow        = { "allow", cursor, reasons[] }
Deny         = { "deny",  cursor, constraint_id | rule_id, reasons[] }
Escalate     = { "escalate", class, until, cursor, reasons[] }
```

`Escalate` means: the hook MUST treat the action as denied until an authorized human (or listed multi-party) emits `Allow` for that `class` and body hash, or the pack defines a timeout **deny**. Timeout MUST NOT default to allow.

Human approval MUST be domain-separated and single-use (§3.7). The agent MUST NOT resolve its own escalation.

Integrity Health intents: when Shield domain is set, missing BAA MUST deny (403), not warn. `[PARTIAL]` — advisory on some `bcc_middleware` paths today; hard deny is P0.

### 9.1 BCC gate flow (live pre-execution path) `[BUILT]`

This is the concrete decision pipeline behind §9's grammar on the live path today — `POST /v1/bcc/intercept`, before the account is asked to admit anything.

```mermaid
flowchart TD
    A["Intent commitment received"] --> B{"Schema valid?"}
    B -- no --> D1["Deny: schema"]
    B -- yes --> C{"Circuit breaker:<br/>agent locked out?"}
    C -- yes --> D2["Deny: locked out"]
    C -- no --> E{"Signature valid?"}
    E -- no --> D3["Deny: bad signature"]
    E -- yes --> F{"Nonce fresh,<br/>not replayed?"}
    F -- no --> D4["Deny: replay/stale"]
    F -- yes --> G{"OPA policy allow?<br/>(fail-closed if unreachable)"}
    G -- no --> D5["Deny: policy"]
    G -- yes --> H{"Verification-tier<br/>gate met?"}
    H -- no --> D6["Deny: tier"]
    H -- yes --> I{"Quarantine check<br/>(fails OPEN by design)"}
    I -- locked --> D7["Deny: quarantined"]
    I -- open/clear --> J{"On-chain BAA active?<br/>(fails closed)"}
    J -- no --> D8["Deny: BAA_CANNOT_VERIFY"]
    J -- yes --> K["Admit to Merkle batch"]
    K --> L["Best-effort anchor"]
```

Each deny path is typed and reported; a reachable audit endpoint is not required for the decision itself, so an unreachable audit log cannot flip a deny into an allow.

---

## 10. AIS `[PARTIAL]`

AIS is an evidence-derived integrity measurement, not a global reputation token.

\[
AIS_{a,t} = f(E_{a,0:t}, P_{a,0:t}, B_{a,0:t}, A_{a,0:t})
\]

| Symbol | Meaning |
|---|---|
| \(E\) | Verified evidence completeness and signature validity |
| \(P\) | Policy compliance, denials, exceptions, escalation outcomes |
| \(B\) | Behavioral consistency, drift, anomaly indicators |
| \(A\) | Assurance: signed workload identity, hardware or ZK attestations |

The live formula, configurable component-floor evaluation/conjunctive result, pre-boost normalized `constraint_score`, optional ZK boost, and identity-ceiling clamp are `[BUILT]` in `scoring-core`. The floor result is shadow/observational output only; no enforcement path is implemented. Keyword grounding is `[PARTIAL]`.

```mermaid
flowchart LR
    E["S_entropy^0.30"] --> GM["Weighted geometric mean<br/>AIS_raw"]
    G["S_grounding^0.30"] --> GM
    S["S_sacrifice^0.20"] --> GM
    Cp["S_compliance^0.20"] --> GM
    GM --> ZB{"ZK-verified<br/>this period?"}
    ZB -- yes --> B1["× 1.15 boost"]
    ZB -- no --> B2["× 1.0"]
    B1 --> CL["clamp to tier ceiling<br/>(300 / 600 / 850 / uncapped)"]
    B2 --> CL
    CL --> OUT["AIS_final"]
    OUT -.->|"widen a finite c_max only"| PACKC["Pack constraint bound"]
    OUT -. "MUST NOT" .-> DENY["flip a deny into allow"]
```

A single exact-zero input component annihilates `AIS_raw` (weighted geometric mean, not a weighted average) — this is `[BUILT]` and numerically verified server-side, closing a real scoring exploit where a content-free submission with a claimed compute-time input previously outscored an honest agent under the old fail-open defaults. `[PARTIAL]`: fail-closed defaults, configurable per-component-floor evaluation, a conjunctive floor result, and the tier-capped pre-boost `[0,1]` `constraint_score` are `[BUILT]`; the floor result is shadow reporting only and is not wired into score pushes, disputes, or another enforcement path. The current profile (`ais/v1-geometric-2`, amended 2026-11-15) separates an *observed zero* from an *unobserved axis*. Compliance without an independently readable gate or attestation, and sacrifice without validator/TEE evidence, are **unobserved**: that axis gets weight 0, the remaining observed weights are renormalized to sum to 1, and the response lists it in `missing_axes`. An axis backed by independent evidence that measures zero still annihilates `AIS_raw`. Signed flagged ratios and token-derived compute estimates remain audit-only proxy fields and never count as observation, so a claimed compute input still cannot raise the score (the exploit above stays closed). If every weighted axis is unobserved, scoring fails closed to the configured weights. `[BUILT]` (Oracle migrations 0025 compliance, 0026 sacrifice). The superseded `ais/v1-geometric-1` profile resolved both unobserved axes to zero, which annihilated every agent's AIS while no validator/TEE evidence path existed.

AIS MAY drive one of four bounded outcomes:

| Outcome | Permitted effect |
|---|---|
| High confidence | Larger but finite quota |
| Normal | Standard controls |
| Reduced | Narrow quotas or step-up |
| Integrity failure | Quarantine, revoke session, require human |

AIS MUST NEVER:

- Change a policy `deny` into `allow`
- Set \(c^{\max} = \infty\)
- Be computed from Path B (unsigned OTLP)
- Be treated as the reason a hook passed

ZK boost, if used, SHOULD bind to the specific event. The oracle now scales the
multiplier by the fraction of proof-bearing events instead of a period-wide
`BOOL_OR`. Proof public inputs now bind identity, nonce, chain, receiving
registry, and the exact anchored BCC leaf, preventing event substitution. The
on-chain registry still grants a period-wide boost after that event-bound proof,
so the end-to-end scoring path remains `[PARTIAL]` and MUST be disclosed.

---

## 11. Trust tiers

| Tier | Components | Failure |
|---|---|---|
| Trusted | Chain + EVM, EntryPoint, kernel bytecode, constraint grammar | Total. Keep this set small. |
| Attested | Packs, oracle binary, Cortex binary, validators | Wrong \(C\) faithfully enforced; pin versions; audit |
| Untrusted | Agent policy \(\pi\), prompts, tools, bundlers, counterparties | Contained if M1–M5 hold |

\(\pi\) MUST NOT be trusted. Proposition 1 is stated over adversarial \(a_k\) for that reason.

TEE attestation verifiers MAY exist. Wiring them into a live Tier-3 admission path is `[PLANNED]`.

---

## 12. Residual non-goals (normative exclusions)

A conformant implementation MUST NOT claim:

| Exclusion | Reason |
|---|---|
| Correctness of \(\pi\) | Outside TCB |
| Copy control / DRM after delivery | Access is not copy. Gating access to proprietary data is a pack (`ip-license`, §7.6), not this exclusion. |
| Complete mediation without M1–M5 | Guarantee void |
| AIS or reputation as a deny-override | §3.5, §10 |
| Token economy (governance, implied cap, adapter marketplace) | Not v1 spine. Slashable ERC-20 collateral, including $ITK as the built default, remains a pack parameter. `markets@*` is a pack over existing market contracts, not a kernel type. |
| Metered IP marketplace (v3.2 Phase II: ERC-6551 licence TBAs, ATCP/IP, settlement) | Archive. Access gating does not require it. |
| EU AI Act as kernel types | Profile / pack only |
| Shield as a protocol object | Product on Core |
| Cortex as a second verifier | Evidence plane |
| Chargebacks, legal liability, tax filing, settlement-issuer diversity | Outside protocol |
| World-event / price oracle | Wrong tool |
| Scoring unsigned OTLP | §8.2 |
| Physical RF entropy as identity | Archived research |

---

## 13. Liveness (normative minimum)

| ID | Rule |
|---|---|
| L1 | Ambiguity → reject with typed reason. No silent fail-open on the value path. |
| L2 | Every pack declares `gas_max`; overflow → reject. |
| L3 | Unattested hook installable only by explicit operator override. |
| L4 | Kernel removal is delayed + multi-party (M4). |

v3.x Adaptive Grace Modes, ATCP/IP state channels, and DA-Escrow are archived. They are not v1.

---

## 14. Implementation status (Core)

Grounded against `XibalbaTechSol/integrity-core` `main` as of November 2026, plus `super-cortex` and `xibalba-shield`.

| Item | Tag |
|---|---|
| SDK signed telemetry + BCC intercept | `[BUILT]` |
| Path A vs Path B ingest split | `[BUILT]` |
| Oracle ingest, verify, store, AIS API | `[BUILT]` |
| Server-side AIS re-derivation | `[BUILT]` |
| AIS identity-ceiling clamp | `[BUILT]` |
| Oracle → AISRegistry score checkpoint push | `[BUILT]` |
| StateAnchor + ActionAnchor Merkle batch | `[BUILT]` |
| Super-Cortex evidence / memory plane | `[BUILT]` |
| `IntegrityHook.sol` ERC-7579 hook (pre/post-state V) | `[BUILT]` (`contracts/src/wallet/IntegrityHook.sol`) |
| `IntegrityGuard.sol` Safe transaction guard | `[BUILT]` (`contracts/src/wallet/IntegrityGuard.sol`) |
| `SafeAccountVerifier.sol` account invariants | `[BUILT]` (`contracts/src/wallet/SafeAccountVerifier.sol`) |
| `AgentRegistry.sol` singleton & lineage | `[BUILT]` (`contracts/src/framework/AgentRegistry.sol`) |
| Trust Layer singletons (`StakeVault`, `AISRegistry`, `PolicyRegistry`) | `[BUILT]` (`contracts/src/trust/`) |
| 3-Tier Identity & Agent0 / ERC-8004 Public Passport Bridge | `[BUILT]` (`integrity_sdk.erc8004`, `integrity erc8004` CLI, oracle backend) |
| Constraint grammar §4 | `[PARTIAL]` — freeze this text as the language |
| M1–M5 mediation checklist | `[PLANNED]` as a shipped auditor |
| M4 multi-party kernel swap | `[PLANNED]` |
| Identity keyed \(C\) | `[BUILT]` via AgentRegistry & SafeAccountVerifier |
| Pack schema §7.1 + compiler §7.5 | `[PLANNED]` as the only extension API |
| Closed constraint families §7.5 | `[PARTIAL]` — spend budget, AIS floor, target allowlist |
| Integrity Health pack in this schema | `[PARTIAL]` (BAA/ComplianceGate/PHI scan exist; not this folder form) |
| `ip-license` pack | `[PLANNED]` — same `delegation_active` family as Health |
| `markets` pack | `[PLANNED]` as pack form; `IntegrityMarket.sol` / `A2ACapitalPool.sol` `[BUILT]`, out of spine |
| Pack `redact: enforce` server-side | `[PARTIAL]` — SDK default-off `redact_phi` is a Health/IP blocker until BCC/oracle reject |
| Hard BAA deny on Shield-domain paths | `[PARTIAL]` / P0 |
| Genesis `latestRoot != 0` | `[PLANNED]` / P0 |
| Escalate + deny-on-timeout as first-class OBS | `[PARTIAL]` |
| ZK ingest profile | `[PARTIAL]` off-chain; on-chain verifier is a fail-closed placeholder |
| On-chain licence TBA; IntegrityGovernance; Metered IP marketplace | out of v1 spine (archive). Market contracts stay in repo as `markets@*` body. |
| Independent audit + invariance proof | `[PLANNED]` — gate for non-draft v1.0.0 |
| Upgradeability of `SovereignAgent` / `StateAnchor` | `[BUILT]` for future deployments — frozen hosts with agent-pinned, fail-closed policy hooks; existing Base Sepolia agents retain older bytecode and are not migrated |
| Protocol role concentration | `[OPEN]` — arbitrator/disputer/funderWallet/governance/oracleSigner/resolverSigner + `MINTER_ROLE` + `DEFAULT_ADMIN_ROLE` are one EOA today (testnet posture, named P0 for mainnet) |
| ZK verifier: source vs. deployed | `[PARTIAL]` — real generated verifier (Honk scheme) exists in source; Base Sepolia still runs an older fail-closed placeholder |
| Single RPC dependency, no failover | `[OPEN]` |
| Silence-as-signal (agent stops reporting while still acting) | `[PLANNED]` |
| Uniform minimum stake at registration | `[OPEN]` — an agent can register and hold a score while risking nothing |

**Phase 1 (Freeze Core) exit:**

1. SDK emits a signed span + Merkle leaf. `[BUILT]`
2. Super-Cortex stores; oracle verifies and anchors a root. `[BUILT]`
3. Hook enforces a constraint file from the active pack (`IntegrityHook`). `[BUILT]`
4. Policy engine can allow / deny / escalate. `[PARTIAL]`
5. Console shows replay + pending escalations. `[BUILT]`

Integrity Health pack contents are Phase 2 and MUST NOT block calling this constitution v1.

---

## 15. Machine-readable fragment (canonical)

```yaml
protocol: integrity
version: 1.0.0-draft
verbs: [constrain, record, escalate]
planes: [core, cortex, ais, chain]
profiles: [enclosed_enterprise, sovereign_economic]
hook:
  grammar: post-state
  admit: "forall g_i <= 0"
  hook_wins: true
  preCheck: projected
  postCheck: realized
oracle:
  is_price_feed: false
  is_cortex: false
ingest:
  path_A_scores: true
  path_B_scores: false
ais:
  authority: false
  may_lift_c_max: false
  may_flip_deny: false
escalation:
  timeout: deny
packs:
  composition: conjunction
  widen: false
  families:
    - native_value_budget
    - token_out_cap
    - meter
    - reputation_floor
    - assurance_tier
    - module_installed
    - delegation_active
  redact_enforce_server_side: true
exclusions:
  - token_economy_as_spine
  - metered_ip_marketplace
  - drm_after_delivery
  - world_event_oracle
  - eu_ai_act_as_spine
  - fourth_verb
  - unsigned_otlp_ais
```

---

## 16. File authority (after cutover)

| File | Authority |
|---|---|
| `docs/WHITEPAPER.md` | Informative, public |
| `docs/SPEC.md` | **Normative** |
| `docs/CONTROLS_MATRIX.md` | Informative mapping |
| `docs/ecosystem/INTEGRITY_ECOSYSTEM_PLAN.md` | Informative roadmap. Sequences the work that closes the `[PARTIAL]`/`[PLANNED]`/`[EXPERIMENTAL]` gaps named in this file. It MUST NOT introduce a requirement this file doesn't already state. |
| `docs/archive/` | Historical. Do not implement from these. |

When README, wiki, interface contract, and this file disagree, this file wins for protocol meaning; the disagreement MUST be repaired in the same change.
