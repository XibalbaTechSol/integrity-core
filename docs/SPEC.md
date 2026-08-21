# Integrity Protocol v1 Specification

**Status:** Draft
**Normative:** this document
**Informative:** `WHITEPAPER.md`, `CONTROLS_MATRIX.md`, `IMPLEMENTATION_PLAN.md`
**Version:** 1.0.0-draft
**Date:** August 2026
**Author:** Jacob S. Vickers, Xibalba Solutions, LLC

Implementations claim conformance only against this file. Whitepaper v3, specification v0.3/v0.4, and v0.5-proposed are archive.

The key words MUST, MUST NOT, SHOULD, MAY are RFC 2119.

## 1. Conformance

A v1 Core implementation MUST provide an enclosed account mediated by the hook, post-state constraint evaluation, a signed evidence plane, an oracle that verifies and anchors roots, and pack loading. Until M1–M5 are demonstrated, implementations MUST describe themselves as a testnet/prototype protocol specification with a narrow experimental reference implementation.

## 2. Objects and planes

v1 has four named planes: Enforce (account and hook), Record (Cortex and Oracle), Learn (AIS), and Settle (chain). AIS is evidence-derived and never a permission. Cortex stores and replays; the oracle verifies; the hook admits or reverts value-moving actions.

## 3. Types

Constraints are keyed by durable agent identity, never solely by a rotatable EOA. Account state includes balances, allowances, nonce, meters, modules, bounded parameters, and a memory commitment head. `kill_epoch` is monotonic and mismatched intents MUST fail.

## 4. Constraint grammar

Constraints evaluate post-state. A pack compiler lowers authoring syntax onto a closed family of bounded on-chain checks. Unknown identifiers, unbounded iteration, exception-as-success, and fail-open cursor staleness on a value path are non-conformant.

## 5. Verification rule

A transition commits only where every installed constraint holds. Rejection MUST revert. `preCheck` MAY reject based on projected post-state; `postCheck` MUST verify conserved quantities against realized post-state and revert the whole transition if they fail.

### 5.1 Forward invariance `[PLANNED]`

If the initial state is admissible and every transition is mediated by the verification rule, all reachable states remain admissible. The proposition is void, not merely degraded, if any of M1–M5 fail. Independent audit and a machine-checked argument gate non-draft v1.0.0.

### 5.2 Placement `[EXPERIMENTAL]`

The kernel MUST be an ERC-7579 type-4 hook. `preCheck` and `postCheck` MUST cover direct execution, executor paths, and module installation/removal. The live production `SovereignAgent.execute()` does not yet dispatch through such a hook; the kernel slice is experimental and non-deployed.

### 5.3 Upgradeability of per-agent contracts `[PLANNED]`

Decided 2026-08-20. v1 uses a hybrid; implementations MUST NOT introduce a third upgrade shape without a specification revision.

| Contract | Bytecode | How behavior changes | Compromised-authority effect |
|---|---|---|---|
| `StateAnchor` | Frozen after deployment | Replace `IAnchorPolicy` at the `anchorRoot` chokepoint | May deny anchoring; MUST NOT rewrite, reorder, or un-anchor history. |
| `SovereignAgent` | MAY be a proxy | Replace `IExecutionPolicy` at `execute`; delayed, multi-authorized implementation upgrade under M4 | Policy-key compromise is disruption. Upgrade-key compromise can rewrite fund handling and is theft. |

`anchorRoot` MUST call `IAnchorPolicy.checkAnchor(...)` before writing a root. `execute` MUST call `IExecutionPolicy.checkExecution(...)` before moving value or performing a call. A policy that returns false or reverts MUST deny. A zero policy is the disclosed testnet/development posture; mainnet value paths MUST use a non-zero policy and fail closed.

`StateAnchor` MUST remain frozen: `isAnchoredRoot`, `rootAtEpoch`, and monotonic `latestEpoch` are sacred. An additive satellite is permitted; a proxy on `StateAnchor` is non-conformant.

`SovereignAgent` MAY be proxied because an unanticipated bug in call/return handling, or value locked in the account, cannot be repaired by a hook. If proxied, controller pin/opt-out authority belongs to the agent controller, never the protocol; storage layout is append-only; implementation changes are M4 transitions (delayed and multi-authorized); same-transaction swaps MUST revert; proxy code is in the independent-audit scope.

Guardian actions that remove or replace the kernel MAY bypass the hook. The hook cannot gate its own removal without becoming unremovable. This is a permanent named M4 exception; every other state-changing path remains mediated.

Pre-existing Base Sepolia agents remain frozen testnet artifacts. Mainnet deploys the hybrid from genesis. Fleet-wide `StateAnchor` beacon control, fully frozen hookless `SovereignAgent`, and per-agent UUPS as the sole upgrade path are rejected for v1.

### 5.4 Protocol roles and key custody `[OPEN]` on testnet — P0 for mainnet

Today `arbitrator`, `disputer`, `funderWallet`, `governance`, `oracleSigner`, `resolverSigner`, `MINTER_ROLE`, and `DEFAULT_ADMIN_ROLE` are one EOA. That is accepted testnet posture and non-conformant on mainnet.

A mainnet deployment MUST complete this sequence:

1. Give every named authority a distinct key.
2. Hold `oracleSigner` and `resolverSigner` in separate oracle and middleware process custody, never a human wallet.
3. Constrain ITK supply: fixed supply, or `MINTER_ROLE` held only by governance. Governance MUST NOT be represented as decentralized while a funder EOA can mint voting power.
4. Only then place governance, `DEFAULT_ADMIN_ROLE`, and `SovereignAgent` upgrade authority behind a 2-of-3 or stricter multisig or timelock. Transfer to `IntegrityGovernance` happens only after supply is constrained.

A `SovereignAgent` proxy MUST NOT deploy to mainnet before this sequence. The theft-versus-disruption analysis in §5.3 is void while upgrade authority and `MINTER_ROLE` share an EOA.

## 6. Complete mediation `[PLANNED]`

M1–M5 require in-scope value to remain in mediated accounts; all direct, executor, fallback, and batch paths to route through the hook; module changes to be constrained; kernel removal to be delayed and multi-authorized; and bypassing executors to remain removable only through M3–M4.

## 7. Packs

Packs compile into constraints plus off-chain policy. They are conservative: a pack may only add restrictions, never relax another installed pack. A compiler MUST use a closed family of constraint records and reject an expression it cannot lower.

## 8. Evidence plane, oracle, and hybrid ledger

Path A signed ingest may feed AIS; unauthenticated OTLP Path B may not. The oracle verifies signatures, domains, nonce, leaf inclusion, ancestry, and independently derives AIS signals before anchoring. Cortex stores, indexes, and replays; it is not a second verifier.

## 9. Decision grammar

Off-chain policy may allow, deny, or escalate, but never overrides a hook denial. Escalation remains deny until an authorized human authorizes the body-hash in its domain; timeout defaults to deny.

## 10. AIS

AIS is an evidence-derived bounded integrity measurement. It may widen a finite bound and may require step-up or quarantine. It MUST NOT turn deny into allow, remove a constraint, be computed from unsigned OTLP, or explain why a hook passed.

## 11. Trust tiers

Trusted: chain, EVM, EntryPoint, kernel bytecode, and constraint grammar. Attested: packs, oracle, Cortex, and validators. Untrusted: agent policy, prompts, tools, bundlers, and counterparties. The agent policy is not in the TCB.

## 12. Residual non-goals

v1 does not claim policy correctness, DRM after delivery, complete mediation without M1–M5, AIS deny overrides, token economy as protocol spine, a second verifier in Cortex, scoring unsigned OTLP, or world-event/price-oracle authority.

## 13. Liveness

Ambiguity MUST produce a typed rejection. Each pack declares bounded gas. Kernel removal is delayed and multi-party. An unattested hook requires an explicit operator override.

## 14. Implementation status (Core)

Grounded against `XibalbaTechSol/integrity-core` `main` as of 2026-08-20.

| Item | Tag |
|---|---|
| SDK signed telemetry and BCC intercept | `[BUILT]` |
| Oracle ingest, verify, store, AIS API | `[BUILT]` |
| ERC-7579 hook and post-state verification | `[EXPERIMENTAL]` |
| M1–M5 mediation checklist | `[PLANNED]` |
| Pack schema and compiler | `[PLANNED]` |
| Independent audit and invariance proof | `[PLANNED]` |
| Upgradeability of `SovereignAgent` / `StateAnchor` | `[PLANNED]` — hybrid decided: frozen `StateAnchor` plus `IAnchorPolicy`; `SovereignAgent` MAY proxy plus `IExecutionPolicy`. See §5.3. |
| Protocol role concentration | `[OPEN]` / P0 — accepted only on testnet. Mainnet MUST complete §5.4 before a `SovereignAgent` proxy deploys. |
| ZK verifier source vs deployed | `[PARTIAL]` |
| Single RPC dependency | `[OPEN]` |

## 15. Machine-readable fragment (canonical)

```yaml
protocol: integrity
version: 1.0.0-draft
verbs: [constrain, record, escalate]
hook:
  grammar: post-state
  hook_wins: true
upgradeability:
  state_anchor: frozen_with_anchor_policy
  sovereign_agent: policy_hook_then_optional_m4_proxy
mainnet_custody:
  distinct_keys: required
  process_signers: required
  itk_supply_constrained_before_governance: required
  multisig_minimum: 2-of-3
```

## 16. File authority

`docs/SPEC.md` is normative. `WHITEPAPER.md`, `CONTROLS_MATRIX.md`, and `IMPLEMENTATION_PLAN.md` are informative and MUST NOT conflict with this file. Archive documents are historical and MUST NOT direct implementation.
