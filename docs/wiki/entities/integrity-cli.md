---
title: integrity-cli
created: 2026-07-07
updated: 2026-07-15
type: entity
tags: [sdk, identity]
confidence: high
source_files:
  - integrity-cli/integrity_cli/main.py
  - integrity-cli/integrity_cli/identity.py
  - integrity-cli/integrity_cli/wallet.py
  - integrity-cli/integrity_cli/chain.py
  - integrity-cli/integrity_cli/bcc.py
  - integrity-cli/integrity_cli/config.py
  - integrity-cli/integrity_cli/vault.py
  - integrity-cli/tests/test_register_oracle_e2e.py
  - integrity-cli/tests/test_chain.py
---

## Table of contents

- [Overview](#overview)

## Overview

Developer CLI (Python/Typer) — the human-driven counterpart to
[integrity-sdk](integrity-sdk.md), carrying its own copy of the identity/wallet/
chain logic (no sibling-import) but kept wire-compatible byte-for-byte.

`integrity agent register` runs the **real self-sovereign on-chain sequence** —
fund the agent's own EVM wallet → mint testnet $ITK → deploy `SovereignAgent` +
`StateAnchor` → grant anchor role via `execute` →
`AgentPrimitivesFactory.registerPrimitives` → POST to the oracle. It is a
multi-transaction, multi-second command, not a single HTTP POST. See
[agent primitives](../concepts/agent-primitives.md).

Other commands: `identity keygen/show` (Ed25519 [DID](../concepts/did.md), full
`sha256(pubkey)` fingerprint), `agent show/ais` (oracle lookups), and
`agent intercept --covered-entity` (build a signed [BCC commitment](../concepts/bcc.md)
and POST it to the policy gate; exit 1 on a policy rejection, so it's scriptable).

**`vault` command group, added 2026-07-30** (`sync`), bridging the CLI with the
Trust Vault primitive-level persistent memory architecture (mirrors `integrity_sdk/memory.py`).
Allows local tools to directly parse session facts (e.g. from `transcript.jsonl`) into the
`MemoryBackend` (default: `JSONLBackend`), calculate a new cryptographic state root, and
anchor it on-chain to the agent's `StateAnchor` contract.

**`xns` command group, added 2026-07-11** (`register`/`resolve`/`primary-handle`/
`set-primary`/`release`), covering the new [XibalbaNameService](contracts.md)
contract. All three writes route through `SovereignAgent.execute` — calling
XNS directly with the controller EOA as signer makes `msg.sender` the wrong
address (`XibalbaAgentRegistry.isRegisteredAgent` only recognizes the
`SovereignAgent` *contract* address), a real bug an early version of this
work shipped and only caught via the real anvil end-to-end test in
`test_chain.py`, not the Solidity-side unit tests (which correctly `vm.prank`
the `SovereignAgent` address directly and so never exercised the CLI's own
calling convention). `register`/`set-primary`/`release` resolve the caller's
own `SovereignAgent` address via a `GET /v1/agent/{did}` oracle lookup first
(that mapping isn't persisted locally by `agent register`).

Security: no insecure default auth token (the old prototype's `"mock_demo_token"`
is gone); placeholder tokens are refused outside `ENVIRONMENT=local`.

**57 tests** (`pytest`, incl. 1 opt-in `ORACLE_E2E` test): CliRunner + httpx-mock unit
tests, a real anvil integration test (`test_chain.py`) that spins up a live
chain, runs the real `Deploy.s.sol`, and exercises the CLI's on-chain code
for real — including, as of 2026-07-11, the new `xns` commands and a
negative test proving `isRegisteredAgent` rejects a real-but-unindexed
`SovereignAgent` — plus `test_register_oracle_e2e.py` (opt-in via
`ORACLE_E2E=1`, see below).

**Resolved gap (found 2026-07-09, fixed 2026-07-09):** `main.py`'s
`agent register` command hand-builds its own oracle POST body (it does not
call `integrity_sdk.registration.register_agent`, per this page's "carrying
its own copy" note above) — it used to send `{"agent_id": agent_did, "alias",
"description", "did_document": doc, "primitives": registration.to_dict()}`,
the exact same schema drift `integrity-sdk/integrity_sdk/registration.py` had
until 2026-07-09 (see [integrity-sdk](integrity-sdk.md)'s fix note and
`docs/INTERFACE_CONTRACT.md` §6.3's documented real schema): missing the
required `did` field (sent as `agent_id` instead) and never sending
`eth_address_hex`/`ed25519_pubkey_hex`, so `integrity agent register` without
`--skip-oracle` 422/400'd against a real oracle the same way the SDK used to.
Fixed the same day by rewriting the payload in `main.py`'s `agent_register` to
send `{"did", "did_document", "primitives": {the 7 real fields, built
explicitly rather than via `registration.to_dict()}, "ed25519_pubkey_hex":
"0x"+private_key.public_key().public_bytes_raw().hex(), "eth_address_hex":
evm_account.address, "alias", "description"}` — `alias`/`description` are
kept as CLI-only metadata the oracle's struct has no `deny_unknown_fields`
for, so it silently ignores them, same reasoning `integrity-sdk` used.
Verified for real against a live local `cargo run` oracle (fresh anvil +
`Deploy.s.sol`/`DeployMarkets.s.sol`, ephemeral Postgres/Redis via Docker):
`integrity agent register --alias verify-cli-bot ...` (no `--skip-oracle`)
printed "Oracle accepted the registration", and a real `GET /v1/agent/{did}`
on that same oracle returned `has_ed25519_key: true, has_eth_address: true`
with matching primitives, and the DID appeared in a real `GET /v1/agents`.
New regression test `integrity-cli/tests/test_register_oracle_e2e.py` (opt-in
via `ORACLE_E2E=1`, same gate name `integrity-oracle/backend/tests/e2e.rs`
and `integrity-sdk/tests/test_registration_oracle_e2e.py` use, mirroring that
SDK test's `oracle_backend` fixture pattern — ephemeral Docker Postgres/Redis
+ real `cargo run`) drives the CLI's actual `agent register` Typer command via
`CliRunner`, asserts success, and independently re-confirms via real
`GET /v1/agent/{did}` + `GET /v1/agents` calls. Ran green standalone
(`ORACLE_E2E=1 uv run pytest tests/test_register_oracle_e2e.py`) and as part
of the full suite (skipped when `ORACLE_E2E` unset, as designed).

Related: [integrity-sdk](integrity-sdk.md),
[agent primitives](../concepts/agent-primitives.md),
[BCC](../concepts/bcc.md), [DID](../concepts/did.md).
