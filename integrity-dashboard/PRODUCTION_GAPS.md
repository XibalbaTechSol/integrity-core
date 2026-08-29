# integrity-mvp: Production Gap Analysis

> **Current audit pointer — 2026-08-06:** [`docs/audits/2026-08-06-status.md`](docs/audits/2026-08-06-status.md) records the clean-branch build, test, dependency, lint, and integration-verification status. Historical gap entries below remain evidence records and are not silently rewritten.

Following the pass that wired this frontend's core surfaces to real `integrity-oracle`
and on-chain data (agent fleet, AIS, stake, staking writes, ERC-20 transfers, audit log,
credit allocation, telemetry traces), the following gaps remain — documented per the
repo's no-silent-mocks rule rather than left as unmarked placeholder data.

## Closed this pass

* `DashboardContext` now sources `agents`, `selectedAgent`, `stats`, `user`, and
  `apiKeys` from `oracle.listAgents()`/`getAis()`/`getStake()`/`getLeaderboard()` and
  `userapi`, instead of a single hardcoded `agent_1` and static mock arrays.
* `Dashboard.tsx`, `COTPlatform.tsx`, `ShieldPage.tsx`, `TokenWallet.tsx`,
  `StakingPanel.tsx`, `IntegrityRadar.tsx` — all previously branched on
  `selectedAgent.id === 'agent_2'` or returned `setTimeout`-faked data; now read real
  AIS components, stake, trace trees, and audit-log entries.
* `PredictionMarketsPage.tsx` (a fully fake `markets = [...]` array, no oracle/chain
  imports) deleted; `/prediction-markets` now renders the real `ActuarialHub`.
* `AuthPage.tsx` now calls real `userapi.login`/`register`; the fake "Continue with
  Google" button (no Firebase project wired in this repo) was removed rather than left
  as a dead click.
* `SettingsContext`'s `createApiKey`/`deleteApiKey` now call real `userapi` endpoints;
  the UI's former name/expiry/permissions fields were dropped since the backend has no
  such per-key concept (only an AIS trust ceiling and revocation state).
* Fabricated numeric fallbacks (`?? 850`, `?? 895`, `?? 2500`, `tee_verified ?? true`)
  in `IdentityPage.tsx` and `IntegrityRadar.tsx` replaced with honest "no reading yet"
  states — these silently substituted a plausible-looking number for missing data,
  which is worse than an empty state because it's indistinguishable from real.
* Unit bug: `oracle.getWallet`/`getStake`/`getCredit` return raw on-chain wei strings
  (`U256::to_string()` server-side, confirmed against `integrity-oracle/backend/src/
  handlers.rs`), not human-readable ITK. `TokenWallet.tsx`, `StakingPanel.tsx`, and the
  `Dashboard.tsx`/`DashboardContext.tsx` stake displays were rendering these raw
  (e.g. a real 10,000 ITK balance showing as `10,000,000,000,000,000,000`) until caught
  by live-testing against a running oracle; now formatted with `ethers.formatEther()`
  everywhere, matching the convention `CreditPanel.tsx`/`ActuarialHub.tsx` already used.
* Two live "empty ABI" bugs found and fixed: `StakingPanel.tsx` and `CreditPanel.tsx`
  each built an `ethers.Contract(ITK_TOKEN_ADDRESS, [], signer)` with no ABI, so
  `allowance()`/`approve()` would have thrown on the very first real stake/allocation
  attempt. Both now use the shared `ERC20_ABI` from `src/chain/markets.ts`.
* **(2026-08-04) Shield's Shadow AI Discovery is now real.** New oracle endpoint
  `GET /v1/shield/unregistered-agents` (`db::list_unregistered_agents`,
  `handlers::get_unregistered_agents`) surfaces DIDs with real `otel_spans`/`audit_log`
  evidence that never registered via `POST /v1/agent/register` — a genuine, zero-new-infra
  detector using data the oracle already durably stores (no foreign key from either table
  to `agents`). `ShieldPage.tsx`'s panel now lists real results instead of a simulated
  scan. Deliberately not literal network/process scanning — see
  `bcc_middleware/spec/xibalba-shield-v1.md`'s `[PLANNED]` kernel-sensor design for that
  separate, out-of-scope vision. **Policy Rules panel is now real too** — new
  `bcc_middleware` endpoints `GET`/`PUT /v1/admin/clinical-allowlist` proxy OPA's Data
  API against the pre-designed `data.clinical_allowlist.agents` extension point in
  `bcc_middleware/policies/bcc.rego`; `ShieldPage.tsx` add/removes agents from the
  runtime allowlist for real (via a new `src/services/bccMiddleware.ts` client). Still
  honestly scoped: this is the ONE policy surface that doesn't need a redeploy — every
  other rule (thresholds, new rule types) still requires editing the read-only-mounted
  `.rego` files and restarting the `opa` container, which the panel's remaining
  `SeededDataBadge` says plainly. The write is in-memory on OPA's side only — lost on
  container restart, since nothing persists it to a mounted data file.
* **(2026-08-04) Health's Smart BAA flow is now real**, mirroring
  `integrity-dashboard/src/components/tabs/HealthPanel.tsx` (the validated reference
  implementation) exactly: `handleProposeBAA` calls `SmartBAAFactory.createBAA` after
  checking `CoveredEntityRegistry.isActiveCoveredEntity` (self-registers inline if the
  connected wallet holds `REGISTRAR_ROLE` — no separate bootstrap script needed),
  `handleSignBAA` funds+approves+signs via `SovereignAgent.execute`, and two flows
  dashboard never built are new here: `handleRaiseDispute` (CE-gated
  `SmartBAA.raiseDispute`) and `handleRevokeBAA` (`SmartBAA.revoke`). `handleArbitrate`
  is gated on `walletAddress === ARBITRATOR_ADDRESS`, matching dashboard's pattern
  exactly, not a `SeededDataBadge`. The BAA registry and Compliance Review Queue now read
  real `oracle.getAgentBaas()`/`getAuditLog()` data — the old fake `loadDefaultData()`
  seed arrays are gone. The "Enclave Integrity: 100%" stat was removed outright (no
  probability model exists anywhere in the protocol for it, same conclusion
  independently reached for `integrity-dashboard`'s `TriMetricWidget`).
* **(2026-08-04) Quarantine tab is now real** — found the actual backend already exists:
  `bcc_middleware/app/quarantine.py` defines quarantine as `Slasher.lockedStakeOf(agent)
  > 0`, which is exactly `StakeDto.locked_stake` the oracle already returns per agent.
  `HealthPage.tsx`'s Quarantine tab now fans out `oracle.getStake()` across the
  registered fleet (same bounded client-side pattern `DashboardContext` already uses)
  and flags any agent with locked stake. No "Force Restore" action — there isn't one on
  bcc_middleware's side either; quarantine clears itself the instant the arbitrator
  resolves the dispute via `SmartBAA.arbitrate`, which now triggers a live re-scan.
* **(2026-08-04) Arbitrator now gets a network-wide dispute queue.** The Compliance
  Review Queue was scoped to whichever agent happened to be selected — useless for an
  actual arbitrator, who needs every disputed `SmartBAA` across the whole fleet, not
  one agent at a time. When the connected wallet matches `ARBITRATOR_ADDRESS`, the panel
  now fans `oracle.getAgentBaas()` out across every registered agent and shows the
  union of `Disputed`-status BAAs instead — same client-side fan-out pattern as
  Quarantine above, gated so it only runs for the one wallet that can act on it.
* **(2026-08-04) EHRGate/consent is now real.** `EHRGate` deployed to Base Sepolia at
  `0x684E31dc51667E37803EBeA7a781172A27D55B16` (verified on Sourcify and via a live
  `minAisThreshold()` read returning `800`). `HealthPage.tsx`'s "EHR Gates" tab now
  calls real `grantAccess`/`revokeAccess` (patient-wallet-signed) and reads real
  `accessGates` state. Since `EHRGate` has no on-chain enumeration (no "list all
  gates" getter — `accessGates` is keyed by a specific `(patient, recordHash, agent)`
  triplet), the visible list is a browser-local watchlist of triplets to re-check, not
  a source of truth; every row's status is always re-read live from the contract on
  render, never cached in the watchlist itself. The existing WebAuthn passkey ceremony
  is kept as a local pre-authorization UX gate before the real wallet signature — it
  has no cryptographic link to the transaction, and the copy says so plainly.
  Deploying it also caught a real bug in `DeployEHRGate.s.sol`'s merge step: it
  silently dropped `network`, `domains`, and the `IntegrityGovernance` singleton from
  `deployments.baseSepolia.json` on write (`vm.writeJson` replaces the whole file, so
  any field not explicitly re-parsed is lost, not merged) — fixed in the same commit.
* **Investigated and deliberately NOT built: a server-side `/v1/stats/network`
  endpoint.** `docs/design/dashboard-wiring.md` records that `integrity-dashboard`'s team
  rejected this exact endpoint to avoid two disagreeing `protocol_staked_itk` numbers (a
  cached aggregate vs. a live per-agent read shown on the same page — a real risk here
  too, since `StakingPanel` shows "Protocol TVL" and "Your Stake" side by side and the
  latter refetches live after every tx). The AIS half would also have been a no-op:
  `effective_score` is already cached server-side (`leaderboard_cache`) and mvp already
  fetches it in one call via `getLeaderboard()` — only the stake fan-out had real cost,
  and that's the contradicted part. **Before re-proposing this, re-read
  `dashboard-wiring.md`'s reasoning first** — this was a considered decision, not an
  oversight. Client-side aggregation stays as-is: correct, just not infinitely scalable,
  which is fine at current (~10-agent) testnet scale.
* **No linear "AIS boost from stake" formula** — the real formula is a weighted
  geometric mean (`AIS = (S_e^0.30 · S_g^0.30 · S_s^0.20 · S_c^0.20) · ZK_boost`), so
  `StakingPanel`'s old "+X pts" estimate was fabricated and has been removed rather than
  replaced with another guess. There's no cheap client-side way to show a real estimate
  without duplicating `scoring-core`'s formula in TypeScript.
* **User identity has no real name/email absent a userapi session** — `DashboardContext`
  falls back to a wallet-address-derived display name (`0x1234...abcd`) and an
  identicon. This is honest (derived from the real connected address) but means most
  users browsing without signing in see a generic identity, not a personalized one.
* **Per-component null-safety audit is not exhaustive** — `selectedAgent` is now
  correctly typed `Agent | null` (there may be zero registered agents, or the fleet may
  still be loading). This pass added guards to `Dashboard.tsx`, `AppHeader.tsx`,
  `Sidebar.tsx`, `ShieldPage.tsx`, and `IntelligencePage.tsx`, the components that
  accessed `selectedAgent.*` unconditionally. `CreditPanel.tsx`, `PrivacyPanel.tsx`,
  `IdentityPanel.tsx`, `FactoryPanel.tsx`, `XNSRegisterForm.tsx`, and the two
  `TraceAnalysisPanel.tsx` copies were not individually re-audited for the null case in
  this pass — they already null-check before rendering their primary UI, but a
  root-cause review of every `selectedAgent.eth_address` call site against a genuinely
  empty fleet hasn't been done.
* **(2026-08-04) Real Playwright e2e suite added** (`playwright.config.ts`, `e2e/`) —
  21 tests across 4 spec files, run against a real dev server hitting the real
  oracle/bcc_middleware/chain stack (`npm run test-e2e`), no route mocking. Caught a
  real bug on first run: `TelemetryGraphs.tsx` crashed with `Cannot read properties of
  null (reading 'split')` on `/intelligence` whenever any agent in the fleet has a null
  `alias` (no XNS handle or DID-document name yet) — fixed by falling back to
  `name`/`id`. Hosted package CI now exists, but deliberately does not call
  `test-e2e`; Playwright remains a human/agent-run step because its real backend
  stack must be prepared separately.
