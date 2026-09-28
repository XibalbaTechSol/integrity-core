# Integrity Ecosystem Source-of-Truth Reconciliation

**Date:** 2026-09-15
**Scope:** Scope 2 of the SDK integration work
**Status:** source/API reconciliation recorded; no identity, registration, or deployment mutation

This document records the current authority boundaries and the discrepancies found while
comparing the normative documents, implementation, tests, and live local services. Evidence
labels are deliberately separated: source inspection is not a substitute for a test, API read,
or chain read.

## Authority order

| Subject | Canonical authority | Evidence | Notes |
|---|---|---|---|
| Protocol grammar and invariants | `docs/SPEC.md` v1.0.0-draft | Documentation-confirmed | `DOCUMENT_STATUS.yaml` and README identify it as normative. Archived protocol drafts are not live contracts. |
| Cross-package wire contracts | `docs/INTERFACE_CONTRACT.md` | Documentation-confirmed | Governs internal schemas, ports, environment variables, and package boundaries. |
| Protocol identity and registration | Base Sepolia contracts as read by Integrity Oracle | API-confirmed; on-chain-confirmed when independently read | Oracle is the operational read surface; registration claims require exact chain evidence. |
| Local DID and signing-key continuity | `~/.integrity/did/<agent-id>/` (or `INTEGRITY_DID_HOME`) | Source-confirmed; filesystem-confirmed | `load_or_create_did()` refuses ambiguous existing state and does not casually regenerate keys. |
| Wallet/controller relationship | On-chain `SovereignAgent` and live authorization state | Documentation-confirmed; source-confirmed | A funder, deployer, controller, wallet, and contract owner are distinct roles. |
| Cortex canonical memory | Cortex `GraphStore` SQLite store | Documentation-confirmed; source-confirmed | Graph/vector/embedding/retrieval outputs are projections or bounded providers. |
| Cortex authorization | Authenticated Cortex principal plus its bound `agent_ids` | Source-confirmed; API-confirmed in live fixture | A supplied agent identifier cannot expand a principal's namespace. |
| Shield device identity | Shield enrollment database and device-bound assertion key | Documentation-confirmed; source-confirmed | `device_id` and `integrity_agent_id` are separate fields and are checked as a pair. |
| Shield policy decision | Local Shield policy engine and enforcement outcome | Documentation-confirmed; source-confirmed | Cloud/oracle telemetry is evidence of reporting, not proof that local enforcement occurred. |
| Oracle signed telemetry | Oracle `POST /v1/telemetry/ingest` schema version 2 | Source-confirmed; API-confirmed | Requires the Oracle's signed envelope, monotonic nonce, and agent key verification. |
| Developer telemetry | SDK `telemetry-envelope-v1.json` | Source-confirmed; test-confirmed | This is an integration envelope for local persistence/Cortex/Shield correlation; it is not silently treated as an Oracle signed envelope. |
| Dashboard display | Dashboard API clients and typed projections | Source-confirmed; API-confirmed | Dashboard is not an authority and must distinguish observed, indexed, confirmed, pending, and unavailable data. |

## Identity separation

The following identities must not be collapsed:

```text
end user / operator
  -> authenticated principal
     -> authorized Integrity agent DID(s)
        -> runtime instance / harness
           -> session -> invocation -> events
        -> optional Shield device binding
        -> EVM wallet/controller and agent-owned contracts
```

| Object | Canonical meaning | Must not be inferred from |
|---|---|---|
| Harness | Claude, Codex, Hermes, Agy, custom runtime, or other execution host | Wallet address, device ID, or display label |
| Integrity agent | Stable logical subject represented by the DID | Harness process, session, or human account |
| DID | Key-derived Integrity identity/document reference | A local alias or Oracle display name |
| Principal | Authenticated human, service, or runtime credential | Payload `agent_id` |
| Device | Shield installation/enrollment identity | Portable agent DID |
| Wallet | EVM account used for defined chain operations | Funder or deployment operator |
| Controller | Address authorized by the agent contract | Historical registration snapshot alone |
| Contract owner/control | Contract-specific ownership/admin state | DID existence or wallet funding |
| Cortex partition | Authenticated principal's authorized agent namespace | Session ID or arbitrary memory source field |

## Reconciled findings

### R1 — Normative-document drift is resolved

- **Finding:** `docs/SPEC.md` is normative; `docs/WHITEPAPER.md` is informative; archived v0.4,
  v0.5-proposed, and other archived protocol files are historical.
- **Evidence:** Documentation-confirmed from `README.md`, `docs/DOCUMENT_STATUS.yaml`, and
  `docs/INTERFACE_CONTRACT.md`.
- **Implementation:** Source-confirmed by current registration, contract, Oracle, and SDK paths.
- **Disposition:** Do not claim v2 or v0.5 conformance from `SPEC-v2.0.0-proposed.md`. Treat it as
  design/review material until formally accepted.

### R2 — Chain-bound registration caches are no longer authoritative without chain identity

- **Historical finding:** An earlier `primitives.json` cache format omitted `chain_id`, allowing
  local Anvil addresses to be mistaken for Base Sepolia state.
- **Evidence:** Documentation-confirmed in the 2026-09-12 Gate 1 handoff and source-confirmed by
  current `registration.py` and its regression tests.
- **Current disposition:** The SDK records `chain_id` in registration progress and primitive
  caches and discards mismatched progress. Existing cache files still require an exact network
  read before use; cache presence is not registration proof.

### R3 — Signed Oracle telemetry and developer telemetry are different contracts

- **Finding:** Oracle ingestion accepts a signed version-2 payload containing nonce, `otel_spans`,
  derived signals, and signature. The new SDK envelope v1 carries richer developer provenance,
  privacy state, hashes, and delivery state.
- **Evidence:** Source-confirmed in `integrity_sdk/client.py`, Oracle handlers, and
  `integrity_sdk/telemetry/envelope.py`; test-confirmed by SDK envelope tests and live API-confirmed
  by the signed `xibalba` canary.
- **Disposition:** The SDK may map a redacted developer envelope into an Oracle signed payload,
  but neither schema may be renamed or claimed equivalent. Unknown event types and missing
  authority remain explicit failures/unknowns.

### R4 — Cortex agent scoping is principal-bound, not payload-bound

- **Finding:** Cortex accepts bearer/cookie-authenticated requests and derives writable agent
  scope from the principal. Requested agent IDs are checked against that authorization set.
- **Evidence:** Source-confirmed in `auth_middleware.py`, `ingest_tokens.py`, and `local_api.py`;
  API-confirmed by the live Cortex fixture export and duplicate-event replay test.
- **Disposition:** SDK transports must authenticate with a bound credential. `agent_id` in an
  event is attribution and correlation data, not authorization.

### R5 — Shield device binding remains separate from portable agent identity

- **Finding:** Shield stores `integrity_agent_id` on an enrolled device and verifies device
  assertions against that recorded binding. Device and agent bindings have lifecycle history.
- **Evidence:** Documentation-confirmed in `spec/xibalba-shield-v1.md` and
  `INTERFACE_CONTRACT.md`; source-confirmed in `shield/backend/store.py` and
  `shield/device_assertion.py`.
- **Disposition:** The SDK exposes device context only when supplied by a trusted Shield path;
  it must not synthesize a device from a harness or hostname.

### R6 — Display-name resolution is intentionally non-authoritative

- **Finding:** Shared `integrity_sdk.agent_identity` prefers Oracle handle/name, then local label,
  then a shortened DID. Oracle reachability failure returns an unknown/off-chain display state.
- **Evidence:** Source-confirmed in `integrity_sdk/agent_identity.py`.
- **Disposition:** Display labels cannot authorize actions, establish registration, or prove
  ownership. This fail-open naming behavior must not be reused for security gates.

### R7 — Deployment image drift remains open

- **Finding:** The running Shield container emitted `CLIENT SIGNABLE BYTES` while the current
  checked-out SDK source no longer contains that debug print.
- **Evidence:** API/runtime observation from Compose logs; source-confirmed absence in the current
  local SDK file. This is deployment evidence, not proof of the current source being shipped.
- **Disposition:** Rebuild and restart the Shield image only through an explicit deployment gate;
  until then classify the running image as stale relative to source. Do not claim the logging fix
  is live merely because source inspection passes.

## Current canonical data-flow

```text
Harness/runtime
  -> SDK envelope v1 (redact, hash, correlate, persist locally)
  -> Cortex authenticated ingestion (principal-bound agent partition)
  -> optional Oracle signed telemetry v2 mapping (agent key + nonce)
  -> Oracle derivation / scoring / anchoring projections
  -> Dashboard typed read projections

Shield edge
  -> local policy decision + enforcement outcome
  -> device-bound evidence/export
  -> Oracle/BCC correlation when accepted
  -> Dashboard projection
```

The chain remains the authority for deployed contract state and finalized registration facts.
Cortex remains the authority for its canonical local memory records. Shield remains the authority
for local device enforcement outcomes. The dashboard combines these facts but does not promote
one subsystem's observation into another subsystem's authority.

## Open or blocked reconciliation items

| Item | Classification | Required next action |
|---|---|---|
| Live Shield image differs from checked-out source | Blocked / runtime deployment drift | Rebuild the image and verify logs after an explicit deployment approval. |
| Shield production device-to-DID mapping | Unknown for the current Compose instance | Read the authenticated Shield registry without mutation; do not register a replacement DID. |
| Dashboard rendered browser proof | Blocked | In-app Browser was unavailable; run approved Playwright fallback or restore Browser access. |
| Cortex browser session auth versus dashboard token mode | Partially verified | Validate the actual deployed Caddy/browser path; source/API evidence alone is insufficient. |
| Full on-chain ownership/control for every local identity | Not tested | Perform exact read-only contract calls per DID and chain; cache files are insufficient. |

## Scope 2 conclusion

The canonical boundaries are sufficiently reconciled for SDK work to proceed. The safe integration
rule is: load the existing local DID/key, authenticate Cortex with a principal bound to that DID,
use Shield device context only from enrollment/assertion evidence, map developer events to the
Oracle's separate signed schema, and use exact chain reads for registration/control claims.
