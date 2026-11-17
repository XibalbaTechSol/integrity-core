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

`integrity register` is **gas-free and off-chain**. It signs a registration
message with the identity's Ed25519 key (proof of possession) and sends it to the
Oracle; no chain state is touched and no funder wallet, RPC endpoint or deployments
file is needed. A proven key is verification tier 1. The on-chain "self-sovereign
contracts" registration (the old seven-primitives sequence) was removed from this
command (registration v3 PR 3.4 deleted that path from the CLI); the `domain` and
`handle` commands still use the on-chain helpers.

## Install

Requires Python 3.12 and [`uv`](https://docs.astral.sh/uv/). `anvil`/`forge` on
`PATH` are needed for the on-chain commands.

```bash
cd integrity-cli
uv venv .venv && uv pip install -e ".[dev]"
.venv/bin/integrity --help
```

## Configuration

Layered, highest precedence first: a command's own **flag** → **env vars** (`ORACLE_URL`,
`BCC_MIDDLEWARE_URL`, `RPC_URL`, `DEPLOYMENTS_FILE`, `AUTH_TOKEN`, `ENVIRONMENT` —
the names pinned in [`../docs/INTERFACE_CONTRACT.md`](../docs/INTERFACE_CONTRACT.md)
§3; a local `.env` is loaded into the environment, so it counts as env) → the
**`--network` profile** → `~/.integrity-cli/config.json` (`integrity config set`) →
built-in local-docker defaults. `integrity config show` prints each value's source.

`--network local|base-sepolia` (or `$INTEGRITY_NETWORK`, or config `NETWORK`) sets
`RPC_URL`, `DEPLOYMENTS_FILE` and `ORACLE_URL` together:

```bash
integrity --network base-sepolia doctor
```

Because env beats the profile, an `RPC_URL` left in `.env` overrides `--network`.

## Output and exit codes

Every v3 command takes `--json`: exactly one JSON document on stdout, tagged
`"schema": "integrity.cli.<group>.<cmd>.v1"`; human text goes to stderr in that mode.

| exit | meaning |
|-----:|---------|
| 0 | yes / ok |
| 1 | a definite no: refused, not in the map, roots differ, mismatch |
| 2 | usage error |
| 3 | unverified / unreachable: Oracle down or 5xx, RPC unreachable — retry, don't treat as "no" |
| 4 | the chain refused a write (revert) |

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
integrity identity new  [--name alice]   # ~/.integrity-cli/identity/<name>/, mode 0600
integrity identity show [--name alice]
integrity identity list [--json]         # names and DIDs; never prints a key
```

Real Ed25519 (via `cryptography`), producing the DID-document shape from
[`../docs/INTERFACE_CONTRACT.md`](../docs/INTERFACE_CONTRACT.md) §4.1. The DID
fingerprint is the **full** `sha256(pubkey)` — matching the SDK exactly, and
required by the reconciled BCC signature scheme (see below). This is a developer
CLI, not a KMS; don't reuse these keys for anything that matters.

### `integrity register` — gas-free off-chain registration

```bash
integrity register [--identity default] [--handle my-agent] [--oracle-url …] [--json]
```

Signs an RFC 8785 canonical registration message with the identity's Ed25519 key and
POSTs it to the Oracle's `/v1/agent/register/offchain`. On success it prints
`registered <did> tier=<n> (<outcome>)` and exits 0; an Oracle rejection (for
example a taken handle) exits 1, and an unreachable or 5xx Oracle exits 3. It never
needs `FUNDER_PRIVATE_KEY`, `INTEGRITY_WALLET_PASSWORD` or an RPC. `--oracle-url`
defaults to the configured `ORACLE_URL`. Registering again is safe and never lowers
an existing tier.

#### `--onchain [--confined --domain ID]` — the AgentRegistry record

```bash
integrity register --onchain [--rpc-url …] [--deployments-file …] [--json]
integrity register --onchain --confined --domain general.integrity
```

Without `--onchain`, `register` never touches an RPC or a wallet. With it, after the
off-chain step it:

1. asks the Oracle for an attestation (`/v1/agent/{id}/onchain/attestation`): the agent
   signs the EIP-712 `RegisterAgent` digest with its Ed25519 key, and the CLI refuses
   an attestation over any digest other than the one this chain's `AgentRegistry`
   computes, before spending gas;
2. sends one `AgentRegistry.register(...)` from the identity's guardian wallet
   (`INTEGRITY_WALLET_PASSWORD`; fund it first);
3. asks the Oracle to sync the record (`/v1/agent/{id}/onchain/sync`).

`--confined --domain` also deploys a `SovereignAgent` controlled by the guardian and binds
it as the actor. The agent consents by calling `register` through its own `execute`
(`msg.sender == actor`). `--domain` is a domain name (keccak-hashed, as
`integrity domain register` creates it) or a `0x` bytes32 id. `--confined` and
`--domain` go together and need `--onchain`. Without `--confined` the record is
existence-only (no actor, so not settlement-eligible). Re-running on a registered DID
sends nothing and just syncs (`"outcome": "already_registered"`).

Exit 0 written and synced; 1 refused (Oracle 4xx, no `AgentRegistry` in the deployments
file); 2 bad flags; 3 Oracle or RPC unreachable, or an Oracle 5xx (including an Oracle
with no `AgentRegistry` configured); 4 contract revert, with the decoded error name
(for example `DomainJoinNotAllowed`).

### `integrity status` — one view of an agent

```bash
integrity status [<agent-did>] [--identity default] [--json]
```

Folds the old `agent show` and `agent ais`: the Oracle record, verification tier and
AIS (computed once, centrally, in `integrity-oracle/scoring-core`; never recomputed
here). Exit 0 registered, 1 not registered, 3 Oracle unreachable. The on-chain rows read
the v3 AgentRegistry (`singletons.AgentRegistry`): `record` present/absent/retired, `actor`
bound/none. An absent record is optional in v3, not a failure; an unreadable one is
`unverified`; neither changes the exit code. `trust` is the bound actor's stake as the
execute gate reads it (`AgentRegistry.trustConfig()` → `TrustConfig.stakeVault()` →
`StakeVault.stakeOf(actor)`): `frozen`, `staked` or `unstaked`, with `amount`, `locked`,
`frozen` and `available` in the JSON; `n/a` with no bound actor; `unverified` when the trust
layer is unwired or a read fails (never reported as `unstaked`).

### `integrity doctor` — is this machine's view of the network sane?

```bash
integrity [--network base-sepolia] doctor [--pack ./my-pack] [--attester 0x…] [--json]
```

Checks the Oracle `/healthz`, the deployments file, RPC reachability, chain id, and that
XibalbaNameService, PolicyRegistry and AgentRegistry have code, and that AgentRegistry's
TrustConfig is set and deployed; with `--attester`, that the address holds ATTESTER_ROLE
(otherwise that check is `skipped`); with `--pack`, that PolicyRegistry holds the pack's root. Fails closed: anything unreachable is exit 3, any failed check exit 1.

### `integrity policy` — a pack's on-chain map

```bash
integrity policy compile ./pack [--out compiled.json]     # the root governance publishes
integrity policy map     ./pack                           # every target/selector/risk edge
integrity policy check   ./pack --call 0xTarget:0xa9059cbb[:500]   # 0 in map, 1 not
integrity policy prove   ./pack --target 0x… --selector 0x… [--risk 500]  # proof + execute() claim
integrity policy diff    ./pack                           # 0 same root on-chain, 1 differs, 3 unreadable
integrity policy publish ./pack --print-tx                # PRINTS setGraphRoot; never signs
```

All read-only. `publish` only prints the unsigned governance transaction: a root change
is signed by the `GRAPH_CURATOR_ROLE` holder, never by this CLI.

### `integrity handle` — agent handles (was `xns`)

```bash
integrity handle available atlas [--json]   # 0 free, 1 taken/invalid, 3 can't confirm
integrity handle register atlas [--json]    # Oracle directory claim for your identity (no wallet, no gas)
integrity handle register atlas --onchain   # on-chain XibalbaNameService, via your bound SovereignAgent
integrity handle set-primary|release atlas --onchain   # on-chain only; refused (exit 1) without --onchain
integrity handle claim <agent-did> atlas    # operator form: directory claim for ANY agent DID
integrity handle resolve atlas.integrity    # on-chain XibalbaNameService lookup
integrity handle primary-handle 0x…         # on-chain primary handle of a SovereignAgent
```

The on-chain writes act through the SovereignAgent that the v3 `AgentRegistry` binds to your
DID (`resolveDID(did).actor`) — the same read `integrity status` shows as `onchain actor`.
Only confined agents have one: no bound actor (or a retired record) exits 1 before any wallet
is loaded; an unreadable registry exits 3; an on-chain revert exits 4.

`handle available` checks BOTH the Oracle directory and on-chain XibalbaNameService; when the
on-chain side cannot be read it reports "unverified" (exit 3), never "free".

### `integrity gate check` — the BCC policy gate

```bash
integrity gate check \
  --intent-type EMR_WRITE \
  --payload '{"patient": "P-1002", "action": "append-note"}' \
  --covered-entity 0x…            # the hospital, for healthcare/clinical intents
```

Builds a real, signed BCC commitment and POSTs it (as the bare object, per the
contract) to `bcc_middleware`'s `POST /v1/bcc/intercept`. Exit code `1` on a
policy rejection, `3` when the middleware is unreachable or answers 5xx, so it's
scriptable: `integrity gate check … && do_the_thing`.

### `integrity receipts verify` — offline receipt verification

Verify a signed receipt bundle without contacting an Oracle, chain, or hosted
service. The input is either a JSON array of receipts or an object containing
`receipts` and an optional signed `checkpoint`.

```bash
integrity receipts verify \
  --receipts receipt-bundle.json \
  --trusted-signer z<base58btc-ed25519-public-key> \
  [--proof inclusion-proof.json] \
  [--anchor-root 0x<checkpoint-root>] \
  [--anchor-contract 0x<StateAnchor> --rpc-url http://127.0.0.1:8545] \
  --json
```

The command checks Ed25519 signatures, receipt sequence and hash-chain
continuity, checkpoint roots, and optional Merkle inclusion proofs. A bundle
with no receipts fails with `EMPTY_BUNDLE` (exit 1): zero receipts are not
evidence of anything. An
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
