# Registration Readiness Evidence — 2026-09-15

**Scope:** read-only birth-certificate/readiness gate
**Network:** Base Sepolia, chain ID `84532`
**Registry:** `XibalbaAgentRegistry` from `deployments.baseSepolia.json`
**Mutation status:** none; no key unlock, funding, registration, or transaction submission

## Method

The matrix combines four separate evidence sources:

1. Local persisted DID documents and key-continuity loading through
   `integrity_sdk.did.load_or_create_did()`.
2. The canonical local profile mapping in `~/.integrity/agents.json` where present.
3. Per-agent Oracle records from `GET /v1/agent/{did}`.
4. Direct read-only `XibalbaAgentRegistry.resolveDID(did)` calls against Base Sepolia.

The readiness implementation also checks the DID-scoped memory DAG and wallet address material.
It intentionally leaves the full chain preflight as `unknown` unless a `PreflightResult` is
explicitly supplied. Therefore an Oracle/on-chain registration result does not automatically
become `ready=true`.

## Canonical profile matrix

| Requested profile | Canonical local slot | DID continuity | Oracle registration | Base Sepolia registry | Persistent memory | Genesis | Wallet address | Overall |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| xibalba | `xibalba` | pass | pass | pass | pass | pass | pass | **blocked: preflight unknown** |
| quant | `xibalba-quant` | pass | pass | pass | pass | pass | pass | **blocked: preflight unknown** |
| shield | `xibalba-shield` | pass | pass | pass | pass | pass | pass | **blocked: preflight unknown** |
| claude | `claude` | pass | fail | fail | unknown | fail | unknown | **blocked: unregistered** |
| codex | `codex` | pass | fail | fail | unknown | fail | unknown | **blocked: unregistered** |
| agy | `agy` | pass | fail | fail | unknown | fail | unknown | **blocked: unregistered** |

`quant` is deliberately mapped to `xibalba-quant` because that is the canonical profile entry
in `~/.integrity/agents.json` and its DID is the one registered in both Oracle and the chain.
The separate local slot `~/.integrity/did/quant/` is a different DID and must not be merged into
the quantitative agent by label similarity.

## Exact chain-read results

The direct registry read returned a complete primitive record for the three registered DIDs,
including controller, `SovereignAgent`, `StateAnchor`, and domain. The other three returned the
registry's unknown-DID result, represented by the SDK as `None`.

| Profile | Controller | SovereignAgent | StateAnchor | Chain evidence |
|---|---|---|---|---|
| xibalba | `0x14bB099e3ADD7341a987a3FB435F051908F46EE2` | `0x360E2a56eb23e383B81E5bB42Ee5c3966688558a` | `0x09DCBBd0D7B0f39db315a8C4f913C162D73Cc68b` | on-chain-confirmed |
| quant | `0x8D63d24f6D2f32a565F479Fd712e719D35950E5f` | `0x1a252A024A8230180720b991FccccA166B0181e8` | `0x509f37c40562cd7ddf3945c02A640EB7821D76f7` | on-chain-confirmed |
| shield | `0xB5831537150cCF80A21B069F8E10a7FB072AA0D4` | `0xDef665Fd3722160AeBF1e8Cb7D4E43da7E9432dC` | `0xddC4517B0df0383959C64cbc2BA922d3649f8957` | on-chain-confirmed |
| claude | — | — | — | on-chain-confirmed absent |
| codex | — | — | — | on-chain-confirmed absent |
| agy | — | — | — | on-chain-confirmed absent |

The registry read proves that the DID has a registered primitive record. It does not, by itself,
prove that the current local wallet can control the record, that every primitive's admin role is
correct, that the genesis root is non-zero, or that the registration event is finalized.

## Fail-closed interpretation

The following statuses are intentionally not promoted to pass from a cache or display label:

- `on_chain_preflight`: **unknown** for all six; no preflight result was injected.
- Controller ownership/control: **unknown** beyond the registry's recorded controller field.
- Primitive role integrity: **unknown**; factory registrar role and per-primitive admin reads were
  not run in this matrix.
- Genesis root anchoring: **pass for xibalba, quant, and Shield** from direct non-zero
  `StateAnchor.latestRoot()` reads; unknown for the three unregistered profiles.
- Finality: **unknown**; registry resolution is a chain read, not a finalized-log proof.
- Shield device binding: **unknown** for this run; device enrollment is a separate Shield authority.

Consequently, no profile is registration-ready. This is the intended fail-closed outcome.

## Evidence classification

| Finding | Classification |
|---|---|
| DID documents and key continuity loaded without regeneration | Source-confirmed; filesystem-confirmed |
| `xibalba`, `xibalba-quant`, and Shield DIDs are Oracle-registered | API-confirmed |
| Those three DIDs resolve to primitive records on Base Sepolia | On-chain-confirmed |
| Claude, Codex, and Agy are absent from Oracle and registry | API-confirmed; on-chain-confirmed |
| `xibalba`, `xibalba-quant`, and Shield have DID-scoped Cortex memory | Filesystem-confirmed; source-confirmed |
| Those three registered profiles have non-zero StateAnchor roots | On-chain-confirmed |
| Full controller, role, ownership, and finality readiness | Unknown / not tested |

## Remediation order

1. Run a read-only chain preflight using the intended network and deployment manifest.
2. Verify the exact local wallet address against the recorded controller without unlocking or
   regenerating keys unless an authorized signing operation is separately approved.
3. Read all seven primitive addresses and their required ownership/control roles.
4. Verify a non-zero genesis root and finalized registration event/log range.
5. Preserve and continue ingesting the existing DID-scoped Cortex stores for quant and Shield;
   do not create duplicate SDK vaults merely to make a readiness report pass.
6. Register Claude, Codex, or Agy only after their explicit identity-to-profile mapping,
   controller, wallet, memory, and deployment prerequisites are approved.
