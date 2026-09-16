# Integrity Dashboard Integration Inventory

Audit date: 2026-09-15
Repository: `integrity-core`, branch `feat/harness-neutral-agent-runtime`

## Runtime inventory

| Domain | Existing source | Current frontend state | Required integration | Validation method |
|---|---|---|---|---|
| Frontend | React 18, Vite 8, TypeScript 5.5, React Router 7 | `src/App.tsx`, `src/layouts/MainAppLayout.tsx`, `src/pages/ProtocolDashboardPage.tsx` | Preserve route shell; centralize protocol reads and state | `npm run build`, browser route journeys |
| Auth | `integrity-userapi`, HttpOnly session cookie, `/auth/*`, `/me` | `src/services/userapi.ts`, `DashboardContext` bootstrap | Use cookie session for user scope; never treat `sessionStorage` marker as credential | userapi auth tests; browser login/session journey |
| Agent identity | Oracle `/v1/agent/{id}`, `/v1/agent/{id}/erc8004`; userapi `/me/agents` | `DashboardContext` now uses authenticated ownership projection; global directory is opt-in only | Resolve DID, ERC-8004, controller, device, and SovereignAgent separately | API response validation; on-chain registry readback |
| AIS | Oracle `/v1/agent/{id}/ais` and history | Read-only DTO in `oracle.ts`; overview displays AIS | Preserve Oracle calculation; label source and freshness; never use AIS as authority | API contract tests; browser unavailable/stale states |
| ITK | Oracle wallet read plus deployed `IntegrityToken` manifest address | ITK balance is read from `/v1/agent/{id}/wallet`; existing write components use direct ethers | Centralize ERC-20 read/write boundary; agent treasury is `SovereignAgent`, controller is signer | RPC balance read; simulated/preflight transaction; confirmed receipt |
| ETH | Deployment RPC + `SovereignAgent` balance | Shared `src/integrity/wallet/chainClient.ts` reads ETH and chain/block context | Keep reads on active manifest network; expose freshness and wrong-network state | RPC read against active chain; wrong-network test |
| Wallet custody | Integrity SDK encrypted EVM keystore; browser wallet via EIP-1193 | Browser `connectWallet` only; no secure agent-key export | Keep keys in SDK/vault/hardware boundary; expose redacted status only; no raw key route exists | secret scan; DOM/console/screenshot scan; signer approval test |
| Transactions | Oracle wallet history is explicitly `null` until event indexing; ethers provider can read receipts | UI shows history if returned, but no lifecycle/detail client | Add indexed/on-chain transaction read model; do not claim success on submission | pending/confirmed/reverted/dropped fixtures from real provider |
| Provenance | Oracle `/v1/agent/{id}/provenance`, audit, reconciliation; Cortex sessions/roots | Current page only reads one Cortex session Merkle root and AIS proof flag | Add typed provenance, audit, reconciliation, telemetry, roots, and source labels | API fixture validation; cross-source correlation checks |
| Merkle proofs | Oracle event fields include leaf/root/index; Cortex exposes retrieval evidence | No complete proof-path UI or Oracle Merkle endpoint | Use backend/SDK canonical proof data; no client cryptography reimplementation | real proof verification result or explicit unavailable |
| ZK proofs | Oracle `ZkProofDto` ingestion/read fields; SDK prover/verifier; deployed verifier manifest | UI displays only `zk_proof_verified` boolean | Expose proof metadata and distinguish off-chain Oracle verification from on-chain attestation | real verifier response; negative proof state |
| BCC intents | bcc middleware audit schema, Oracle audit/reconciliation endpoints, SDK BCC intent | No typed intent detail client in dashboard surface | Add signed intent canonical payload, nonce, signature, domain, outcome linkage | audit join/reconciliation response; replay/failure state |
| Contracts | Root deployment manifest + generated artifacts; Oracle contracts endpoint only markets | Current page displays primitives and IntegrityMarket summaries | Build manifest/ABI registry and permission-aware read model; no generic write endpoint exists | deployed bytecode/ABI checks; owner/role reads |
| Events | Oracle `/events`, `/audit-log`, `/provenance`; chain logs available through ethers | No unified event feed in protocol page | Add agent-scoped normalized event model with stable IDs/source | indexed event vs chain receipt comparison |
| Shield/Cortex | Shield backend and Cortex local API are separate services | Existing clients exist outside new protocol page | Keep links/data provenance separate; never merge identities by address | service health and scoped-access tests |

## Source-of-truth policy

- Oracle/userapi responses are backend-indexed application data and must carry a source/freshness label.
- Contract reads use the active deployment manifest and selected chain ID.
- SDK owns DID/key serialization and signing semantics; browser code never reconstructs them.
- Browser wallets provide approval/signing only; they do not prove agent ownership by address resemblance.
- A submission is `submitted` until an independently read receipt is confirmed.
- Missing backend, RPC, indexer, proof input, or authority is an explicit fail-closed state.

## Current blockers discovered in audit

1. Oracle read routes are not wired to the frontend user session; when `ORACLE_API_KEY` is enabled, the browser cannot safely embed the secret. A same-origin authenticated proxy or public-read policy is required.
2. Resolved in this pass: authenticated agent ownership is now the source for `DashboardContext.agents`; Oracle `/v1/agents` is opt-in only for explicit operator/dev use.
3. The Oracle wallet DTO explicitly returns `transaction_history: null` because event indexing is not implemented.
4. Userapi `/me/wallet` is a custodial application ledger, not the ERC-8004/SovereignAgent on-chain treasury. It must not be presented as the agent wallet.
5. No backend transaction submission/simulation/vault endpoint exists for agent ETH/ITK transfers. Existing components call `window.ethereum` directly and are not a complete secure agent-signing boundary.
6. Oracle contract discovery currently returns IntegrityMarket clones; it does not expose a generic owner/role/proxy/event administration model.
7. Current frontend API helpers still cast JSON directly and do not yet provide a full abort/retry/query-cache layer; the new typed metadata/error/wallet/permission primitives are the migration boundary, not a claim that every legacy route has been migrated.

The authenticated agent-scope blocker is addressed in the current dashboard context. The remaining blockers are preserved as visible capability states rather than filled with mocks or guessed addresses.
