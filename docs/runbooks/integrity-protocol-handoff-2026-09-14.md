# Integrity Protocol handoff — 2026-09-14

## Current verified state

This handoff records the live state after the Shield registration recovery,
CORE finality approval, Cortex binding, dashboard redeploy, and rendered
verification work. Local runtime evidence is not a claim about a remote
production deployment.

### Base Sepolia and CORE

- Network: Base Sepolia, chain ID `84532`.
- Registry: `XibalbaAgentRegistry` at the address in
  `deployments.baseSepolia.json`.
- The stale `AgentPrimitivesFactory` Slasher clone template was the contract
  cause of the earlier empty-data registration revert. The replacement Slasher
  and factory are recorded in the deployment manifest, and the factory has the
  required registrar roles.
- Read-only historical `resolveDID` calls at finalized block `46830231`
  returned `exists=true` for all five current directory agents.
- Oracle restarted with `AGENT_DIRECTORY_FINALIZED=true` and returned:
  `finalized=true`, `block_number=46830231`,
  `finalized_block_number=46830231`, and five agents.

### Shield

- Canonical DID: `did:integrity:2ea17967f7a65589d570ca7e800844701fb36e6aa7374243e8766de8651f6bc4`.
- Controller: `0xB5831537150cCF80A21B069F8E10a7FB072AA0D4`.
- Direct Base Sepolia read: `isRegisteredAgent(0xDef665...) = true`.
- Direct `resolveDID` read returned all seven nonzero primitives and
  `exists=true`.
- `StateAnchor.latestRoot()` is nonzero.
- The old `shield-replacement` identity remains preserved but unregistered;
  its encrypted keystore could not be unlocked with the currently available
  password and must not be regenerated.

### Cortex

- Account UUID: `395a2ffd-d8ad-48b0-9032-935afbc4b0c0`.
- Explicit controller binding: `0x14bb099e3add7341a987a3fb435f051908f46ee2`.
- The binding is recorded in Cortex's `accounts.controller_address` and in a
  `controller_bound` audit event.
- `xibalba-cortex-core-sync.timer` is enabled and active.
- The first successful sync exited `0` and projected the Xibalba DID into
  `user_agent_registrations` at chain ID `84532`, block `46830231`, with
  `finalized=1`.
- The service uses `uv run --project %h/Projects/xibalba-cortex` so its local
  `integrity-sdk` path dependency is executable under systemd.

### Dashboard and source/runtime verification

- Added the missing `http://127.0.0.1:5173` user API CORS origin.
- Rebuilt and recreated the live `dashboard` and `userapi` containers.
- Headless Playwright verified HTTP 200 landing-page rendering, meaningful DOM
  content, navigation to `/auth`, and a mobile viewport. Remaining console
  responses were expected unauthenticated `401` responses from `/me`; no CORS
  errors remained.
- This evidence is local container/runtime evidence and does not prove a
  separate remote deployment.

## Verification commands

```bash
curl -fsS http://127.0.0.1:8080/v1/agents/snapshot | jq .
systemctl --user is-enabled xibalba-cortex-core-sync.timer
systemctl --user is-active xibalba-cortex-core-sync.timer
systemctl --user status xibalba-cortex-core-sync.service
cd /home/xibalba/Projects/integrity-core/integrity-sdk
UV_CACHE_DIR=/tmp/integrity-uv-cache uv run pytest -q tests/unit/test_agent_runtime.py
node /tmp/integrity-dashboard-qa.mjs
```

Observed SDK result: `5 passed`. The Playwright script is a local temporary
QA harness; its screenshots were written under `/tmp/`.

## Remaining blockers and next actions

1. Codex, Claude, and Antigravity have distinct local DID identities and
   passed local attribution canaries, but their DIDs are not in the live CORE
   directory. Register their complete primitive sets through authorized wallet
   paths before claiming strict live canaries.
2. The Oracle log has unrelated rate-limit and malformed-signature warnings;
   investigate those separately before any production burn-in claim.
3. Keep private keys, wallet passwords, API tokens, and the old replacement
   keystore out of commits and handoff messages.
4. Re-run the live snapshot, Cortex service, and Playwright checks after any
   deployment or RPC change.

## Repository state at handoff

- `integrity-core`: branch `feat/harness-neutral-agent-runtime`; documentation
  handoff commit series ending with this file.
- `xibalba-cortex`: branch `feat/otel-compatible-integrity-telemetry`; account
  and CORE sync commit `cc5f11b`.
- `xibalba-shield`: clean `main` checkout; no source change was needed for the
  confirmed canonical registration.
