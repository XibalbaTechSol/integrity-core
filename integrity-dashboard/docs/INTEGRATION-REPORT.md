# Integrity Dashboard Integration Report

Date: 2026-09-15
Repository: `integrity-core`
Dashboard branch: `feat/harness-neutral-agent-runtime`

## Delivered

- Replaced the legacy dashboard route surface with the protocol control-center routes: Overview, Agent Identity, Integrity Records, Proofs & Verification, Wallet, Transactions, Contracts, Security & Keys, and Activity Log.
- Added an authenticated agent-scope boundary. `DashboardContext` reads `/me/agents` when a real userapi session exists; the Oracle global directory is disabled by default and only available through `VITE_ALLOW_UNSCOPED_AGENT_DIRECTORY=true`.
- Added explicit ERC-8004 binding reads and displays NFT owner and agent wallet separately from DID, controller, funder, and signer concepts.
- Added a shared on-chain read client using the active Base Sepolia deployment manifest. ETH and ITK reads are tied to the resolved `SovereignAgent`, chain ID, and block number.
- Added typed protocol metadata, normalized errors, and fail-closed permission primitives under `src/integrity/`.
- Added provenance, audit-log, ERC-8004 binding, and reconciliation reads to the protocol page. Missing evidence is rendered as unavailable rather than verified.
- Preserved the key boundary: no private keys, seed phrases, tokens, or credentials are rendered. External signer connection is distinct from agent authority.
- Added the integration inventory and product/security interaction specification.

## Authoritative integrations

| Surface | Source | Current state |
|---|---|---|
| Agent scope | userapi `/me/agents` | Implemented for authenticated sessions |
| Agent projection | Oracle `/v1/agent/{id}` | Implemented read |
| ERC-8004 binding | Oracle `/v1/agent/{id}/erc8004` | Implemented read; no browser-side registration claim |
| AIS | Oracle `/v1/agent/{id}/ais` | Implemented read; labeled projection, not authorization |
| ITK | Oracle wallet projection plus manifest token read | Implemented read paths; source distinction visible |
| ETH | RPC read of resolved SovereignAgent | Implemented read with chain/block context |
| Provenance | Oracle `/provenance` | Implemented read |
| Audit and reconciliation | Oracle `/audit-log`, `/reconciliation` | Implemented read |
| Cortex evidence | Cortex status/session Merkle route | Implemented read when Cortex is available |
| Contracts | Oracle agent market discovery plus manifest primitives | Implemented read-only summary |

## Explicitly unavailable / disabled

- Agent ETH/ITK sends are not claimed complete: no vault-backed agent signing or backend transaction submission/simulation boundary exists in the audited services. The connected browser signer is not proof of controller authority, so no protocol write path is enabled by this work.
- Full transaction history/lifecycle is unavailable because Oracle explicitly returns `transaction_history: null` until event indexing is implemented.
- Generic owned/controlled contract administration, role reads, proxy implementation reads, and permission-aware writes are unavailable because Oracle currently exposes market discovery only and no generic administration API.
- Complete Merkle inclusion-path and ZK public-input detail views remain blocked where the backend does not return canonical verifier inputs. The UI does not infer validity from proof presence or an API success response.
- Oracle API authentication is not embedded in the browser. If an Oracle API key is required, deployment needs a same-origin authenticated proxy or an explicitly approved public-read policy.

## Validation evidence

- `npm run build`: passed.
- `git diff --check`: passed.
- `npm run lint`: baseline failure remains in unrelated legacy files: `src/components/shared/SystemSummaryCard.tsx` references an unavailable eslint rule and `src/pages/KnowledgeControlPage.tsx` has an existing unused-variable warning.
- Elevated Playwright browser suite: 10 passed. Covered all nine protocol routes, page titles/headings, protocol navigation, no page errors, no horizontal overflow, and secret-shaped DOM scan.
- Screenshot: [integrity-dashboard-browser-dashboard.png](/home/xibalba/Pictures/integrity-dashboard-browser-dashboard.png)
- Browser run against local Oracle/Cortex-unavailable state; therefore route rendering and fail-closed states are browser-verified, while live populated agent/balance/proof/contract values remain API/RPC-dependent and are not claimed browser-verified in this environment.

## Final rendered-validation handoff (2026-09-15)

- Browser surface: regular headless Playwright; the in-app Browser runtime was unavailable (`No browser is available`).
- Desktop Chromium route audit: **33/33 passed**. Every discovered route rendered a non-empty DOM with a visible primary heading, a main landmark where applicable, no horizontal overflow, and no rendered private-key or recovery-material pattern.
- Protocol responsive audit: **27/27 route-viewport checks passed** at 1440x900, 834x1194, and 390x844. Safe refresh/copy controls passed at all three viewports.
- Axe-core now runs on every discovered route and writes per-route results. Strict blocking remains a release gate because the legacy shell still has known serious accessibility violations; default validation records them without converting known provider degradation into a false route failure.
- The authenticated isolation journey is implemented in `e2e/validation.spec.ts`, but its live run is **blocked/skipped** until a disposable userapi principal is assigned two exact DIDs through `/me/agents`. No credentials, users, assignments, transactions, or contract writes were created by this validation pass.
- A transient Oracle 502 from an optional `/contracts` read was observed during `/wallets`; the validator preserves it as a warning for provider degradation. The route passed after classification was corrected.

Run the remaining authenticated gate with four environment variables supplied out-of-band:

```bash
E2E_AUTH_EMAIL=... E2E_AUTH_PASSWORD=... \\
E2E_AGENT_A_ID=did:... E2E_AGENT_B_ID=did:... \\
npm run test:e2e:validation
```

Do not place those values in source, committed environment files, screenshots, traces, or reports.

## Changed files in scope

- `src/App.tsx`
- `src/config.ts`
- `src/context/DashboardContext.tsx`
- `src/layouts/MainAppLayout.tsx`
- `src/navigation.tsx`
- `src/services/oracle.ts`
- `src/pages/ProtocolDashboardPage.tsx`
- `src/pages/ProtocolDashboardPage.css`
- `src/integrity/types.ts`
- `src/integrity/errors.ts`
- `src/integrity/wallet/chainClient.ts`
- `src/integrity/permissions/index.ts`
- `e2e/protocol-control-center.spec.ts`
- `docs/INTEGRITY-DASHBOARD-DESIGN.md`
- `docs/INTEGRATION-INVENTORY.md`
- `docs/INTEGRATION-REPORT.md`

Unrelated dirty files in the repository were preserved.
