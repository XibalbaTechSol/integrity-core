# integrity-cli

The developer command line for the Integrity Protocol. It does everything an
agent operator needs from a terminal: manage local identity, **register gas-free
off-chain** (a signed proof of key possession; on-chain listing is separate), look up agents and their Agent Integrity Scores, and
drive the Behavioral Commitment Chain (BCC) pre-execution policy gate.

> Ground rule (repo-wide): **no silent mocks.** See
> [`../docs/INTERFACE_CONTRACT.md`](../docs/INTERFACE_CONTRACT.md).

## Goal and relationship to the SDK

`integrity-cli` is the human-driven counterpart to `integrity-sdk`. Where the SDK
is imported by an agent process, the CLI lets a developer perform the same
operations by hand — register an agent, inspect its on-chain reputation, test a
policy decision — without writing code.

By deliberate design, the CLI **does not import `integrity-sdk`.** It carries its
own copy of the identity, wallet, and on-chain logic (`identity.py`, `wallet.py`,
`chain.py`, `bcc.py`) so its build order never couples to the SDK's. The two are
kept byte-for-byte compatible on the wire (DID fingerprints, BCC signatures, the
registration sequence) — verified by cross-package round-trip tests — but they
ship independently.

## How registration works

`integrity agent register` is **gas-free and off-chain**. It signs a registration
message with the identity's Ed25519 key (proof of possession) and sends it to the
Oracle; no chain state is touched and no funder wallet, RPC endpoint or deployments
file is needed. A proven key is verification tier 1. The on-chain "self-sovereign
contracts" registration (the old seven-primitives sequence) was removed from this
command; the `domain` and `xns` commands still use the on-chain helpers.

## Install

Requires Python 3.12 and [`uv`](https://docs.astral.sh/uv/). `anvil`/`forge` on
`PATH` are needed for the on-chain commands.

```bash
cd integrity-cli
uv venv .venv && uv pip install -e ".[dev]"
.venv/bin/integrity --help
```

## Configuration

Layered, highest precedence first: **env vars** (`ORACLE_URL`,
`BCC_MIDDLEWARE_URL`, `RPC_URL`, `DEPLOYMENTS_FILE`, `AUTH_TOKEN`, `ENVIRONMENT` —
the names pinned in [`../docs/INTERFACE_CONTRACT.md`](../docs/INTERFACE_CONTRACT.md)
§3) → a local `.env` → `~/.integrity-cli/config.json` (`integrity config set`) →
built-in local-docker defaults.

On-chain commands additionally need `FUNDER_PRIVATE_KEY` (the testnet faucet
wallet that seeds new agent wallets) and `INTEGRITY_WALLET_PASSWORD` (encrypts the
agent's EVM keystore). Both are **secrets with no CLI flag on purpose** — they'd
end up in shell history or a process list.

### No insecure default auth token

The old prototype shipped `AUTH_TOKEN = "mock_demo_token"`. This rewrite ships no
default token; an obvious placeholder is tolerated only while `ENVIRONMENT=local`
and refused loudly otherwise.

## Commands

### `integrity identity` — local Ed25519 keys + DID documents

```bash
integrity identity keygen [--name alice]   # ~/.integrity-cli/identity/<name>.pem, mode 0600
integrity identity show  [--name alice]
```

Real Ed25519 (via `cryptography`), producing the DID-document shape from
[`../docs/INTERFACE_CONTRACT.md`](../docs/INTERFACE_CONTRACT.md) §4.1. The DID
fingerprint is the **full** `sha256(pubkey)` — matching the SDK exactly, and
required by the reconciled BCC signature scheme (see below). This is a developer
CLI, not a KMS; don't reuse these keys for anything that matters.

### `integrity agent register` — gas-free off-chain registration

```bash
integrity agent register [--identity default] [--handle my-agent] [--oracle-url …]
```

Signs an RFC 8785 canonical registration message with the identity's Ed25519 key and
POSTs it to the Oracle's `/v1/agent/register/offchain`. On success it prints
`registered <did> tier=<n> (<outcome>)` and exits 0; on an Oracle rejection (for
example a taken handle) or an unreachable Oracle it prints why and exits 1. It never
needs `FUNDER_PRIVATE_KEY`, `INTEGRITY_WALLET_PASSWORD` or an RPC. `--oracle-url`
defaults to the configured `ORACLE_URL`. Registering again is safe and never lowers
an existing tier.

### `integrity agent show` / `ais`

```bash
integrity agent show <agent-did>   # GET /v1/agent/{id} — record + 7 primitive addresses
integrity agent ais  <agent-did>   # GET /v1/agent/{id}/ais — the score, computed by the oracle
```

The AIS is computed once, centrally, in `integrity-oracle/scoring-core`; this
command only displays the oracle's answer, never recomputes it.

### `integrity agent intercept` — the BCC policy gate

```bash
integrity agent intercept \
  --intent-type EMR_WRITE \
  --payload '{"patient": "P-1002", "action": "append-note"}' \
  --covered-entity 0x…            # the hospital, for healthcare/clinical intents
```

Builds a real, signed BCC commitment and POSTs it (as the bare object, per the
contract) to `bcc_middleware`'s `POST /v1/bcc/intercept`. Exit code `1` on a
policy rejection, so it's scriptable: `integrity agent intercept … && do_the_thing`.

### `integrity verify` — offline receipt verification

Verify a signed receipt bundle without contacting an Oracle, chain, or hosted
service. The input is either a JSON array of receipts or an object containing
`receipts` and an optional signed `checkpoint`.

```bash
integrity verify \
  --receipts receipt-bundle.json \
  --trusted-signer z<base58btc-ed25519-public-key> \
  [--proof inclusion-proof.json] \
  [--anchor-root 0x<checkpoint-root>] \
  [--anchor-contract 0x<StateAnchor> --rpc-url http://127.0.0.1:8545] \
  --json-output
```

The command checks Ed25519 signatures, receipt sequence and hash-chain
continuity, checkpoint roots, and optional Merkle inclusion proofs. An
`--anchor-root` value is only compared locally with the verified checkpoint;
it does not claim public-chain anchoring or finality. With
`--anchor-contract`, the CLI performs a read-only `latestRoot` and
`verifyLeaf` check against the supplied RPC (intended for local Anvil); this
is reported as local RPC evidence, not testnet or production finality.

## The BCC signature scheme (reconciled)

The commitment signs 7 fields in canonical JSON (`sort_keys`, no whitespace,
`ensure_ascii=True`): `agent_id`, `intent_type`, `intended_state_hash`, `nonce`,
`timestamp`, `covered_entity_address`, and `agent_public_key`. The last is
required because the DID fingerprint is `sha256(pubkey)` — not the raw key — so the
commitment carries the public key (multibase) and `bcc_middleware` binds it by
checking `sha256(pubkey) == fingerprint` before verifying the signature. The CLI,
`integrity-sdk`, and `bcc_middleware` all agree on this byte-for-byte, verified by
cross-package round-trip tests. See
[`../docs/wiki/concepts/bcc.md`](../docs/wiki/concepts/bcc.md).

Nonces are tracked per-agent in `~/.integrity-cli/identity/nonces.json` (a fresh
CLI invocation is a new process). That's a single-machine best-effort counter; a
single identity driven from multiple machines needs a shared nonce authority.

## Tests

```bash
.venv/bin/python -m pytest tests/     # 49 tests
```

Command-level tests use `typer.testing.CliRunner` + `pytest-httpx` (testing this
CLI's own request-building/signing/error-handling, not standing in for the
servers). `tests/test_chain.py` is a **real** integration test: it spins up a live
anvil, runs the real `Deploy.s.sol`, and exercises the CLI's on-chain
`wallet.py`/`chain.py` for real. Cryptographic primitives are checked against
known-good vectors, not just internal consistency.

## Layout

```
integrity_cli/
  identity.py   Ed25519 DID (full sha256 fingerprint, multibase pubkey)
  wallet.py     encrypted secp256k1 EVM keystore
  chain.py      fund / deploy / register on-chain (web3.py)
  bcc.py        signed BCC commitment construction
  client.py     oracle / bcc_middleware HTTP clients
  config.py     layered config + auth-token handling
  abis/         trimmed contract ABIs (synced via make sync-abis)
  main.py       the Typer command surface
```
