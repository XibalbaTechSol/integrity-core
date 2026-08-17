# Shield → integrity-core → dashboard: bring-up runbook

Written 2026-08-14 while actually standing this up for the first time against real Base
Sepolia — the sensor → policy → signed BCC commitment → oracle ingestion → dashboard pipeline
existed in config on both repos but had never been run end-to-end before this. Every step below
was verified live, not inferred from reading code. Several real bugs were found and fixed along
the way; they're listed at the bottom so the next person (or agent) doesn't rediscover them the
hard way.

## What "working" means here, precisely

Two separate milestones, not one:

1. **Sensor → signed commitment → oracle visibility (no on-chain registration needed).** Shield
   signs a real BCC commitment and POSTs it to `bcc-middleware`, which accepts it (`200 OK`) and
   forwards to the oracle. The agent's DID shows up in `GET /v1/shield/unregistered-agents`. Raw
   telemetry (`POST /v1/telemetry/ingest`) is honestly refused for an unregistered agent — not
   silently dropped, not faked — with a clear log line and the batch re-queued. **This milestone
   is real and demoable today, independent of registration.**
2. **Full registration** (`scripts/register_with_oracle.py`) promotes the agent into the main
   per-agent dashboard views with real telemetry, not just the unregistered-agents panel. This is
   the harder, on-chain half — see "Registration" below.

## Bring-up steps

1. `cd integrity-core && make up` (or `docker compose up --build`). Brings up postgres, redis,
   opa, oracle-backend (`:8080`), bcc-middleware (`:8000`), dashboard (`:5173`), shield.
2. Confirm health: `curl localhost:8080/healthz` and `curl localhost:8000/health` should both
   return 200 before trusting anything Shield does next — Shield starts before these
   healthchecks finish and will log real (transient) connection-refused errors until they're up.
   Restart the `shield` container after both are healthy if you want clean logs:
   `docker restart integrity-core-shield-1`.
3. Watch `docker logs integrity-core-shield-1 --since 10s` and
   `docker logs integrity-core-bcc-middleware-1 --since 10s`. A working milestone-1 pipeline
   shows `POST /v1/bcc/intercept HTTP/1.1" 200 OK` on the middleware side and, at most, an honest
   "not registered... refusing to send telemetry" line on the Shield side (not a 404 — a 404
   means nothing is listening on the URL Shield is configured with).
4. Check `curl localhost:8080/v1/shield/unregistered-agents` for Shield's DID.

## Registration (milestone 2)

```bash
cd integrity-core
source .env
docker compose exec \
    -e FUNDER_PRIVATE_KEY="$ORACLE_SIGNER_PRIVATE_KEY" \
    -e INTEGRITY_WALLET_PASSWORD \
    shield python scripts/register_with_oracle.py
```

Two things about this that aren't obvious from the script's own docstring or `.env`:

- **`.env`'s `FUNDER_PRIVATE_KEY` and `DEPLOYER_PRIVATE_KEY` are the public, well-known
  Anvil/Hardhat default test key** (`0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266`) — fine for
  local anvil, useless on Base Sepolia (funding it further does nothing). The key that actually
  controls the funded `funderWallet` role address (`0x7530bd7Cb142C50d5cC742EdF02263f368e89E2f`
  in `deployments.baseSepolia.json`, per the role-concentration issue in `MAINNET_READINESS.md`
  P0 #1 — `funderWallet`/`governance`/`oracleSigner` are currently the same EOA) is `.env`'s
  `ORACLE_SIGNER_PRIVATE_KEY`. Use that one, passed as `FUNDER_PRIVATE_KEY` to the script as
  shown above — don't assume the var named `FUNDER_PRIVATE_KEY` is the right key just because
  the name matches.
- **Re-running after a partial failure is NOT idempotent** — see the script's own corrected
  docstring. `register_agent`'s idempotency check only starts matching after `registerPrimitives`
  (the final step) succeeds; a run that fails at any earlier step (funding, `deploy_sovereign_agent`,
  `deploy_state_anchor`, `grant_anchor_role`, `anchor_genesis_root`) is invisible to that check on
  retry, so the next attempt deploys a fresh `SovereignAgent`/`StateAnchor` pair from scratch and
  orphans whatever the failed attempt already put on-chain. There is currently no automated
  cleanup or resume-from-partial-state path. Real testnet gas, real abandoned contracts — check
  the failed run's error message for addresses it already deployed before blindly retrying.

## Real bugs found and fixed getting here (2026-08-14)

All of these were previously undiscovered because this path had never actually been run
end-to-end before. See `PRODUCTION_GAPS.md` and each repo's own commit history for full detail.

1. **`integrity-core/docker-compose.yml`'s `mvp` service pointed at `../integrity-mvp`**, a repo
   that no longer exists (folded into `integrity-dashboard/` on 2026-08-12) — this broke
   `docker compose up --build` entirely, for any service, not just Shield's. Removed the dead
   service; `dashboard` already covers the same functionality.
2. **`shield/cli.py`'s `_run()` loaded `--device-config`'s `bcc_middleware_url`/`oracle_url` but
   never applied them** — only the raw `--bcc-middleware-url`/`--oracle-url` CLI flags reached
   the exporter. Fixed: an explicit flag still wins, but omitting it now correctly falls back to
   the device-config file's value instead of silently ignoring it.
3. **`docker-compose.yml`'s `shield` service hardcoded `DEPLOYMENTS_FILE: /deployments.local.json`**
   regardless of `DOCKER_RPC_URL`/`DOCKER_DEPLOYMENTS_FILE` overrides in `.env` — so pointing
   `RPC_URL` at real Base Sepolia (via `.env`) while this stayed on the local-anvil deployments
   file made every `resolveDID`-style contract read fail with `BadFunctionCallOutput` (an address
   that only exists in the local file has no code on the real chain). Fixed to follow the same
   override the other services already use, and mounted `deployments.baseSepolia.json` into the
   container alongside the existing local one.
4. **`integrity_sdk/chain.py`'s sequential agent-signed transactions raced nonce reads against
   the public Base Sepolia RPC** — see the `PRODUCTION_GAPS.md` entry for full detail. Fixed with
   `"pending"` nonce reads plus a shared retry-on-stale-nonce helper.

## Root-caused and fixed: registration was broken for everyone, not an SDK bug

`REGISTRAR_ROLE` on `XibalbaAgentRegistry` was granted only to an `AgentPrimitivesFactory`
address with **zero deployed bytecode** — a botched prior rotation (`RotateOperatorKeyGrant.s.sol`)
recorded a predicted-but-never-broadcast `CREATE` address into `deployments.baseSepolia.json`,
and a later manual fix-up granted `REGISTRAR_ROLE` to that same phantom address (and revoked it
from the real, working factory) trusting that same wrong JSON record. A call to an address with
no code always trivially "succeeds" with empty return data — which is exactly the `status: 1`,
near-zero-gas, zero-log symptom every registration attempt hit this session. Full forensic
detail (on-chain log history, cross-checked via two independent RPC providers, not trusted from
any JSON file) is in the `PRODUCTION_GAPS.md` entry. Fix: `REGISTRAR_ROLE` granted back to the
real factory `0xC19fc9cB2cB87297EfDF11DA7e211e44A6C1181D`. **Lesson applied going forward**: never
write a deployed-contract address to `deployments.baseSepolia.json` or grant it any role without
first confirming `eth_getCode` returns real bytecode — see `docs/signer-role-rotation-2026-08.md`,
which will redeploy the factory properly (with the new Safe/EOA roles) and supersede this stopgap.

- Registration's non-idempotent partial-failure behavior — no automated recovery for orphaned
  `SovereignAgent`/`StateAnchor` pairs from a failed prior attempt. At least four such pairs exist
  on Base Sepolia from this session alone (see `PRODUCTION_GAPS.md`), all doomed from the start
  since they were calling the empty factory address, not because of anything registration-flow
  specific.
- The single-signer role concentration this runbook's funder-key confusion is itself a symptom
  of (`funderWallet == governance == oracleSigner`) is a deliberate open decision, not a bug — see
  `docs/MAINNET_READINESS.md` P0 #1. Don't "fix" it unilaterally; it's a key-custody decision.

## Status as of 2026-08-14

Milestone 1 (sensor → signed commitment → oracle visibility) is done and verified live.
Milestone 2 (full on-chain registration) is not complete — see the open item above. Treat
registration as a known, documented gap, not a blocker to demoing milestone 1.
