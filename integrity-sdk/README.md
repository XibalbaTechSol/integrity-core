# integrity-sdk

The agent-facing Python library for the Integrity Protocol. It gives an AI agent
everything it needs to become a self-sovereign, on-chain, reputation-bearing
participant:

- **Decentralized identity** — a real Ed25519 DID (`did:integrity:<sha256-fingerprint>`).
- **An EVM wallet** — a separate secp256k1 keypair the agent uses to deploy and
  control its own on-chain contracts.
- **Self-sovereign registration** — one call deploys the agent's 2 direct
  primitives + 5 clones and registers them on-chain, signed by the agent's own key.
- **Behavioral Commitment Chain (BCC)** — signed pre-execution intent commitments.
- **Telemetry** — OpenTelemetry + MLflow tracing, with AIS-signal derivation.
- **Zero-knowledge proving** — real `nargo`/`bb` proof generation for attestations.

> Ground rule (repo-wide): **no silent mocks.** Every function here is real, or
> an honestly-documented gap. See [`../docs/INTERFACE_CONTRACT.md`](../docs/INTERFACE_CONTRACT.md).

## Install

```bash
uv sync                              # base install + dev dependency group (pytest, etc.)
uv pip install -e ".[openai]"        # + OpenAI autolog (adds openai, pandas)
uv pip install -e ".[langchain]"     # + LangChain autolog (adds langchain-core, pandas)
```

`dev` is a [dependency-group](https://packaging.python.org/en/latest/specifications/dependency-groups/),
not a `[project.optional-dependencies]` extra — only `uv sync` (or
`uv pip install --group dev`) installs it. `uv pip install -e ".[dev]"` looks
plausible but silently installs *no* dev tools (`dev` isn't a valid extra),
leaving `pytest` missing from `.venv/bin` even though base dependencies like
`web3` install fine.

Requires Python 3.12. The on-chain features need `anvil`/`forge` on `PATH` and
the trimmed contract ABIs synced in (`make sync-abis` from the repo root).

## Two keypairs, on purpose

An agent holds two **separate** keys, and mixing them would be cryptographically
wrong (different curves) and a security smell:

| Key | Curve | Stored as | Signs |
|---|---|---|---|
| DID key (`did.py`) | Ed25519 | PKCS8 PEM (mode 0600) | BCC commitments, telemetry, ZK secrets |
| EVM wallet (`wallet.py`) | secp256k1 | encrypted V3 keystore (`INTEGRITY_WALLET_PASSWORD`) | on-chain deploys + transactions |

The DID document binds them: `attach_evm_account()` adds a CAIP-10
`blockchainAccountId` verification method, so anyone resolving the DID learns the
agent's on-chain address.

## Self-sovereign registration

```python
from integrity_sdk import registration

reg = registration.register_agent(
    "clinical-assistant-01",
    domain_name="healthcare.integrity",
    compliance_vertical="healthcare",   # "none" | "healthcare"
    profile_uri="ipfs://…",
)
```

This runs the full dependency-ordered on-chain sequence, each step signed by the
agent's own wallet (except the initial ETH/ITK funding, which comes from the
protocol's faucet wallet — a wallet with zero balance can't pay for the
transaction that funds it):

1. Load/create the Ed25519 DID and the secp256k1 EVM wallet; bind them.
2. Fund the agent wallet with ETH from `FUNDER_PRIVATE_KEY`.
3. Mint a testnet `$ITK` allocation to the agent (stake-ready collateral).
4. Deploy `SovereignAgent` (direct).
5. Deploy `StateAnchor` (direct), admin = the SovereignAgent contract.
6. Grant the oracle `ANCHOR_ROLE` on the StateAnchor, via `SovereignAgent.execute`.
7. Call `AgentPrimitivesFactory.registerPrimitives` — clones the other 5 and
   registers all 7 in `XibalbaAgentRegistry`.
8. Persist the addresses next to `document.json`; POST to the oracle, which
   independently re-verifies the claimed primitives against on-chain state.

Returns an `AgentRegistration` with `.did`, `.evm_address`, and all 7 addresses.

**Required env:** `FUNDER_PRIVATE_KEY` (0x-prefixed testnet faucet key),
`INTEGRITY_WALLET_PASSWORD`. Optional: `RPC_URL`, `DEPLOYMENTS_FILE`,
`ORACLE_URL`, `TESTNET_AGENT_ITK_ALLOCATION`.

## BCC commitments

```python
from integrity_sdk import bcc, did

agent_did, keypair, _ = did.load_or_create_did("clinical-assistant-01")
commitment = bcc.build_bcc_commitment(
    agent_id=agent_did,
    intent_type="EMR_WRITE",
    intent_payload={"patient": "P-1002", "action": "append-note"},
    nonce=bcc.NonceStore(...).next(),
    keypair=keypair,
    covered_entity_address="0x…",   # the hospital, for healthcare intents
)
# POST commitment to bcc_middleware /v1/bcc/intercept
```

The commitment is a self-verifying, signed intent-lock. Because the DID
fingerprint is `sha256(pubkey)` (not the raw key), the commitment carries the
agent's public key (`agent_public_key`, multibase) so a verifier can recover and
bind it — see [`../docs/wiki/concepts/bcc.md`](../docs/wiki/concepts/bcc.md) for
the exact signed field set, shared byte-for-byte with `integrity-cli` and
`bcc_middleware`.

## Telemetry: OpenTelemetry + MLflow, unified

The SDK captures rich agent traces two complementary ways and feeds them into the
AIS pipeline:

- **OpenTelemetry** (`telemetry/core.py`) — the vendor-neutral wire/transport
  layer; spans flow to any OTLP collector.
- **MLflow** (`telemetry/mlflow_tracing.py`) — GenAI-shaped auto-instrumentation
  (`@mlflow.trace`, `mlflow.openai.autolog()`, `mlflow.langchain.autolog()`) with
  the right span types, inputs/outputs, and token-usage attributes.

They compose rather than compete: with an OTLP endpoint configured, **MLflow
exports its spans *through* OpenTelemetry**, so one collector sees both the SDK's
own spans and MLflow's auto-captured GenAI spans as a single unified stream.

```python
from integrity_sdk.telemetry import mlflow_tracing
from integrity_sdk.client import IntegrityClient

mlflow_tracing.configure_tracing(
    agent_id="clinical-assistant-01",
    otlp_endpoint="http://localhost:4317",   # unifies MLflow + OTel; omit for local file store
    enable_autolog=True,                      # openai/langchain if installed
)

client = IntegrityClient("clinical-assistant-01", oracle_url="http://localhost:8080")

@client.traceable(name="answer_query", run_type="chain")
def answer(q): ...

client.flush_telemetry()   # derives AIS signals from the batch, POSTs to the oracle
```

### AIS-signal derivation (`telemetry/derive.py`)

The SDK produces the *inputs* to the AIS formula; the oracle owns the formula
itself. All four signals are normalized to `[0, 1]` with `1.0 = most trustworthy`:

- `derive_entropy` — real Shannon entropy over the completion's word distribution,
  inverted so stable output scores high.
- `derive_grounding` — first-pass heuristic over uncertainty markers.
- `derive_sacrifice` — log-scaled total tokens processed (honestly-observable
  proxy for verified compute; the oracle re-weights against its own evidence).
- `derive_compliance` — self-reported policy signals, overridden by a live
  on-chain `ComplianceGate.isHealthcareCompliant` read when available (on-chain
  wins).

### Working with LangChain / LLM evaluations

The SDK's tracing was designed against the LangChain/LangSmith run-tree model
(`telemetry/tracing.py`), so `mlflow.langchain.autolog()` and the
`IntegrityLangChainCallback` (`integrations/langchain_callback.py`) drop into an
existing LangChain app. Captured traces are usable both for reputation scoring
*and* as evaluation datasets — the same spans that drive AIS can be exported to
an eval harness (LangSmith or otherwise). See
[LangChain's LLM-evals overview](https://www.langchain.com/resources/llm-evals)
for the evaluation side; the SDK's job is producing faithful, structured traces
to evaluate.

## Zero-knowledge proving

`prover.py` shells out to the real `nargo execute` + `bb prove` pipeline to
generate a proof that an action matches its committed intent, verifiable on-chain
by the agent's `VerifierRegistry` → `UltraPlonkVerifier`. See
[`../integrity-zkp/README.md`](../integrity-zkp/README.md).

## TEE attestation (honest gap)

`security/attestation.py` implements **real** AWS Nitro Enclave attestation
*verification* (COSE_Sign1/CBOR parse, signature check, cert-chain to AWS's Nitro
root) against AWS's published test vector. Proof *generation* needs real enclave
hardware this environment doesn't have — documented, not faked.

## Tests

```bash
uv sync                                    # ensures .venv has pytest + all deps (see Install)
uv run pytest tests/                       # 97 tests, +1 opt-in (ORACLE_E2E=1) = 98
```

`uv run` (or `.venv/bin/python -m pytest tests/` after `uv sync`) — running a
bare `pytest`/`python -m pytest` against an interpreter that never had `uv sync`
run against it will fail collection at `tests/conftest.py`'s `from web3 import
Web3` even though `web3` is a declared base dependency, because that
interpreter was never populated by `uv sync` in the first place.

Unit tests (`tests/unit/`) cover wallet, DID, derivation, client, PII/PHI
redaction (`test_redactor.py`), intent hashing/deviation (`test_intent.py`),
and both tracing surfaces — MLflow autolog (`test_mlflow_tracing.py`) and the
run-tree `trace_run`/`traceable` API (`test_tracing.py`). Integration tests
(`tests/test_chain.py`, `tests/test_registration.py`, `tests/test_markets.py`)
run the **real** registration and market sequences against a live anvil
chain running the real `contracts/script/Deploy.s.sol` — no mocked web3.
`tests/test_registration_oracle_e2e.py` is opt-in (`ORACLE_E2E=1`, needs
Docker + cargo on `PATH`) and re-verifies registration against a real
`integrity-oracle` binary rather than the SDK's own chain reads.

## Layout

```
integrity_sdk/
  did.py            Ed25519 DID + CAIP-10 EVM binding
  wallet.py         encrypted secp256k1 EVM keystore
  chain.py          fund / deploy / register on-chain (web3.py)
  registration.py   the full self-sovereign registration orchestrator
  bcc.py            signed BCC commitment construction
  client.py         telemetry client → oracle
  prover.py         nargo/bb ZK proof generation
  abis/             trimmed contract ABIs (synced via make sync-abis)
  telemetry/        OTel core, MLflow tracing, run-tree tracing, AIS derivation
  integrations/     openai_integrity.py, langchain_callback.py
  security/         attestation.py, vault.py, AWS Nitro trust root
```
