---
title: integrity-userapi
created: 2026-07-09
updated: 2026-07-25
type: entity
tags: [infrastructure, identity]
confidence: high
source_files:
  - integrity-userapi/app/main.py
  - integrity-userapi/app/db.py
  - integrity-userapi/app/deps.py
  - integrity-userapi/app/security.py
  - integrity-userapi/app/login_limiter.py
  - integrity-userapi/app/oracle_client.py
  - integrity-userapi/app/schemas.py
  - integrity-userapi/app/config.py
  - integrity-userapi/migrations/0001_init.sql
  - integrity-userapi/migrations/0002_jwt_revocation.sql
  - integrity-userapi/migrations/0003_user_wallets.sql
  - integrity-userapi/tests/conftest.py
  - integrity-dashboard/demo/src/integrity_demo/userapi_bridge.py
  - docker-compose.yml
---

FastAPI + Postgres service owning **user-facing account data only** —
accounts, developer API keys, which agent DIDs a human user has claimed as
theirs, and demo-run request history. It is the strictly non-chain half of
the backend split (see [Interface Contract](../../INTERFACE_CONTRACT.md)
§6.10, §13): it never imports `web3`/`alloy`-equivalent tooling and never
reads a `deployments.*.json` file. `app/oracle_client.py` is the *only*
place this package talks to another service — a plain `httpx` HTTP client
fanning out to [integrity-oracle](integrity-oracle.md), never a direct
chain RPC.

## Endpoints

`POST /auth/register`, `POST /auth/login`, `GET /me` — JWT bearer auth
(`app/security.py`: argon2 password hashing via `passlib` — deliberately
`argon2`, not `bcrypt`, since `passlib[bcrypt]` 1.7.4 breaks against
`bcrypt>=4.1`'s removed `__about__.__version__`). `POST /api-keys` /
`GET /api-keys` / `DELETE /api-keys/{id}` — developer API keys are random
high-entropy tokens (`uak_<43 b64url chars>`), returned once, persisted only
as a sha256 hash (fast deterministic hash is correct here since the input is
already 256 bits of entropy, unlike a human password). `GET /me/agents` /
`POST /me/agents` — `user_agents` stores an ownership **pointer** only
(`user_id`, `agent_did`); every `GET` fans out live to
`integrity-oracle`'s `GET /v1/agent/{id}` per owned DID rather than caching
agent state locally. `POST /demo/run` / `GET /demo/runs` — records that a
run was *requested*, starting at `status='pending'`; this service never
orchestrates a demo or fabricates a `'completed'` result (that's
[integrity-dashboard](integrity-dashboard.md)'s `demo/` engine, a separate process).

## Custodial app-wallet (added 2026-07-25)

`GET /me/wallet` / `POST /me/wallet/transfer` back a per-user **custodial $ITK
ledger** — the honest counterpart to the dashboard's self-custodial (MetaMask)
path. `migrations/0003_user_wallets.sql` adds `user_wallets(user_id PK,
app_wallet_address UNIQUE, itk_balance_wei NUMERIC(78,0) CHECK >= 0)` — a
`NUMERIC(78,0)` covers the full uint256 range exactly (no f64 loss). `GET
/me/wallet` is get-or-create (first call mints a deterministic app-wallet address
+ a dev faucet balance); `POST /me/wallet/transfer` is a real transactional
debit/credit (`SELECT … FOR UPDATE`), not a mocked number — a genuine custodial
account whose balance is an authoritative internal ledger. A production deployment
would back the address with a real custodied keypair + on-chain settlement; the
ledger semantics are already real. Consumed by the dashboard's `TokenWallet`.

## The oracle tri-state

`oracle_client.fetch_agent` never raises and never fabricates data. It
returns `AgentLookupResult(live_data, error)` in exactly one of three
states: live data (`error=None`), not found (`live_data=None,
error="agent not found on oracle"` on a 404), or oracle unreachable
(`live_data=None, error="oracle unreachable: ..."` on any `httpx.HTTPError`
— connection refused, timeout, DNS failure). A single bad lookup in
`GET /me/agents`'s per-agent loop never crashes the whole response; the
caller always gets an honest state, never a silently-empty
`live_data: null` standing in for "couldn't check."

## Four gaps closed 2026-07-15 (all four of this package's `PRODUCTION_GAPS.md` §6 findings)

- **API keys now actually authenticate requests.** `app/deps.py::get_current_user_id`
  accepts either a JWT bearer token *or* an `X-API-Key` header carrying a raw
  `uak_...` key (sha256-hashed, looked up against `api_keys.key_hash WHERE
  revoked_at IS NULL`) — the gap this section used to describe ("no code
  path that uses a raw key at all") is closed. **Deliberate exception**:
  minting (`POST /api-keys`) and revoking (`DELETE /api-keys/{id}`) a key
  stay JWT-only (a new `get_current_token` dependency, not
  `get_current_user_id`) — an API key that could mint further keys would
  let one leaked long-lived credential outlive its own revocation.
- **JWTs are now revocable.** `create_access_token` stamps a per-token `jti`
  (uuid4); `decode_access_token` returns `DecodedToken(user_id, jti,
  expires_at)`. New `migrations/0002_jwt_revocation.sql` adds
  `revoked_tokens(jti PK, user_id, revoked_at, expires_at)`. New
  `POST /auth/logout` inserts the presented token's `jti` there — and,
  since it already has the transaction open, opportunistically sweeps
  already-expired `revoked_tokens` rows first, so the table self-prunes
  without a separate cron job (a revoked token whose `exp` has already
  passed could never be replayed anyway).
- **Login is now rate-limited.** New `app/login_limiter.py`
  (`LoginRateLimiter`) mirrors `bcc_middleware/app/circuit_breaker.py`'s
  in-memory per-key-counter-plus-timed-lockout shape (same accepted
  single-process state tradeoff), keyed on the lowercased login email
  rather than an agent DID, with deliberately looser defaults
  (`failure_threshold=5`/`lockout=300s` vs. bcc's `3`/`900s`) since a login
  form has a much higher legitimate-typo rate than a signed agent
  commitment. `POST /auth/login` 429s (with a `Retry-After` header) once
  tripped — even against the *correct* password.
- **`demo_runs` has a real completion path.** New `PATCH /demo/runs/{id}`
  (`DemoRunUpdateRequest`) lets the owning user transition their run
  through `running` → `completed`/`failed`, stamping `finished_at` only on
  a terminal status and storing a real `result_summary` JSONB payload
  (asyncpg now round-trips `jsonb` as plain dicts everywhere via a codec
  registered in `app/db.py::create_pool`, previously unregistered since
  nothing had ever written non-null JSONB before this). New
  `integrity-dashboard/demo/src/integrity_demo/userapi_bridge.py` calls this
  endpoint from the scenario engine itself — `main()` reports `running` at
  start and `completed`/`failed` (with a real summary) at the end, entirely
  opt-in via three env vars (`USERAPI_URL`/`USERAPI_TOKEN`/`USERAPI_RUN_ID`)
  an operator sets when they want a specific `make demo` invocation tied
  back to a `demo_runs` row created beforehand. **Still genuinely out of
  scope, not fixed**: nothing in `integrity-dashboard`'s dashboard UI creates a
  `demo_runs` row or launches this CLI process — `make demo` remains an
  operator-run script against live Base Sepolia using a funder private key,
  not something the frontend can trigger yet.

## Tests and Postgres wiring

**51 pytest tests** (up from 33 — the 2026-07-15 additions above), plus **6
new tests** in `integrity-dashboard/demo/tests/test_userapi_bridge.py` (against a
real local `ThreadingHTTPServer`, same pattern as this package's own
`_FakeOracleServer` — no-op when the three env vars are unset,
bearer-vs-`X-API-Key` header selection, HTTP/connection errors swallowed
not raised). All against a real Postgres — never sqlite, never a
mocked DB. `docker-compose.yml` has a dedicated `userapi-postgres`
service (`postgres:16-alpine`, `integrity`/`integrity_dev_only`, db
`integrity_userapi`, host port **5435** — its own instance, deliberately
never sharing integrity-oracle's `postgres` service on 5432 or its ad hoc
5434 e2e-test convention, since two separate Postgres instances per trust
domain is the point of the §6.10 split) and a `userapi` app service
(`integrity-userapi/Dockerfile`, uv-based like `bcc_middleware`'s, port
8090). `tests/conftest.py` auto-creates a dedicated
`integrity_userapi_test` database on the same server, forces `DATABASE_URL`
and `ORACLE_URL` before `app.config` is ever imported (so a dev/CI shell's
ambient `ORACLE_URL` — a documented shared env var — can never leak into
the "oracle unreachable" test and make it flaky-green), truncates all
tables between tests, and drives the real FastAPI startup/shutdown lifespan
via `asgi-lifespan`'s `LifespanManager` so `app/db.py`'s real
`run_migrations` runs on every test's setup — not a hand-rolled schema
substitute. The `GET /me/agents` tri-state is tested against a real local
`ThreadingHTTPServer` standing in for the oracle (real socket, real HTTP,
real JSON parsing through `fetch_agent`), never a mock of
`oracle_client`'s internals. Unlike `integrity-oracle`'s opt-in/env-gated
e2e test, this suite has **no skip path** — it fails hard at collection if
`userapi-postgres` isn't reachable, matching the package's stated
completion gate.

Verified manually (not just via pytest): `docker compose build userapi`
succeeds; `docker compose up -d --no-deps userapi` boots against
`userapi-postgres` over the compose network, `GET /health` returns
`{"status":"online","service":"integrity-userapi"}`, and
`schema_migrations` shows `0001_init.sql` applied.

## CORS (added 2026-07-09, real gap)

`app/main.py` had no CORS policy before this pass — a real, hard-blocking
gap for the one browser caller this service exists to serve
([integrity-dashboard](integrity-dashboard.md)'s dashboard, a different origin by
construction). Fixed with `CORSMiddleware` (`allow_origins=["*"]`,
`allow_credentials=False` — every authenticated call carries a bearer JWT,
never a cookie, so this is safe). Verified: all 51 pytest tests unaffected
(CORS is a browser-enforced concern, invisible server-side); a real
cross-origin call from `integrity-dashboard` now succeeds
(`integrity-dashboard/e2e/auth.spec.ts`, against a real `uvicorn` instance
`integrity-dashboard/e2e/global-setup.ts` now boots on its own ephemeral
Postgres database, port 8093 for E2E — see
[Interface Contract](../../INTERFACE_CONTRACT.md) §14).

Related: [integrity-oracle](integrity-oracle.md) (the only service this
one talks to), [DID](../concepts/did.md), [Interface Contract](../../INTERFACE_CONTRACT.md) §13-§14,
[integrity-dashboard](integrity-dashboard.md) (the one real caller of this service's
auth endpoints).
