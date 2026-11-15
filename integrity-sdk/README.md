# integrity-sdk

The agent-facing Python library for the Integrity Protocol. It gives an AI agent
everything it needs to become a self-sovereign, on-chain, reputation-bearing
participant:

- **Decentralized identity** — a real Ed25519 DID (`did:integrity:<sha256-fingerprint>`).
- **An EVM wallet** — a separate secp256k1 keypair the agent uses to deploy and
  control its own on-chain contracts.
- **Gasless registration** — one signed call registers the agent's DID with the
  Integrity Oracle (registration v3); no funder key, RPC or on-chain deploy.
- **Behavioral Commitment Chain (BCC)** — signed pre-execution intent commitments.
- **Telemetry** — OpenTelemetry + MLflow tracing, with AIS-signal derivation.
- **Zero-knowledge proving** — real `nargo`/`bb` proof generation for attestations.

> Ground rule (repo-wide): **no silent mocks.** Every function here is real, or
> an honestly-documented gap. See [`../docs/INTERFACE_CONTRACT.md`](../docs/INTERFACE_CONTRACT.md).

## Install

```bash
uv sync                              # core install + dev dependency group (pytest, etc.)
uv sync --extra connector            # + chain, registration, telemetry and HTTP connectors
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
| DID key (`did.py`) | Ed25519 | PKCS8 PEM (mode 0600) | BCC commitments, telemetry |
| EVM wallet (`wallet.py`) | secp256k1 | encrypted V3 keystore (`INTEGRITY_WALLET_PASSWORD`) | on-chain deploys + transactions |

The DID document binds them: `attach_evm_account()` adds a CAIP-10
`blockchainAccountId` verification method, so anyone resolving the DID learns the
agent's on-chain address.

## Registration (v3: off-chain, gasless)

```python
from integrity_sdk.did import load_or_create_did
from integrity_sdk.registration_offchain import register_offchain
from integrity_sdk.xns import check_handle_availability

did, keypair, _ = load_or_create_did("clinical-assistant-01")
if check_handle_availability(oracle_url, "clinical.assistant").available:
    reg = register_offchain(oracle_url, did, keypair, handle="clinical.assistant")
print(reg.agent_id, reg.verification_tier, reg.outcome)
```

The agent signs `(did, pubkey, timestamp)` with its own Ed25519 key, and the Oracle
records it at verification tier 1. Nothing touches the chain. A handle is checked
in both namespaces: the Oracle directory and the on-chain `XibalbaNameService`.

The on-chain path is optional, and it is not in this SDK yet. It adds an
`AgentRegistry` existence record and a confined `SovereignAgent` actor, and arrives
in Phase 4 of the registration v3 spec. The v2 primitives flow
(`registration.register_agent`: `AgentPrimitivesFactory`, genesis `StateAnchor`,
funder key) was removed in registration v3 PR 3.4.

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

### One-line agent integration

For a persistent local identity and redacted append-only telemetry, the minimal
integration is:

```python
from integrity_sdk import integrity

agent = integrity.auto()
```

The façade exposes explicit lifecycle helpers and preserves the existing
runtime identity. A typical application can add structured events without
changing its model provider:

```python
with agent.session("request-123"):
    agent.prompt("hello", metadata={"channel": "api"})
    agent.model_request(provider="openai", model="gpt-4o-mini")
    agent.response("world")
    agent.token_usage({"input_tokens": 4, "output_tokens": 2})
    agent.tool_call("search", arguments={"query": "integrity"})
    agent.tool_result("search", result={"items": []})
```

Use explicit configuration when the deployment has a required memory boundary
or a SQLite telemetry queue:

```python
agent = integrity.init(
    agent_id="my-agent",
    harness="custom-openai-compatible",
    memory="required",
    memory_home="/path/to/cortex",  # optional; DID-scoped Cortex SQLite store
    telemetry="sqlite",
    identity="persistent",
)
```

`memory="required"` fails closed unless a DID-scoped persistent store is
detected. `telemetry="disabled"` disables this local developer event store;
security-sensitive runtime telemetry and policy decisions retain their own
runtime configuration. Content is redacted before local persistence by the
active collection policy. Unsupported host lifecycle hooks are reported by
the adapter rather than synthesized.

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
- `derive_sacrifice` — log-scaled total tokens processed, retained as an
  explicitly labelled audit proxy; it is not verified compute and the Oracle
  supplies zero to authoritative AIS until validator/TEE evidence exists.
- `derive_compliance` — client-side audit proxy. The Oracle independently reads
  admissible on-chain/attested evidence and fails the authoritative component
  closed when that evidence is unavailable; client flags never silently become
  verified compliance.

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

## TEE attestation (honest gap)

`security/attestation.py` implements **real** AWS Nitro Enclave attestation
*verification* (COSE_Sign1/CBOR parse, signature check, cert-chain to AWS's Nitro
root) against AWS's published test vector. Proof *generation* needs real enclave
hardware this environment doesn't have — documented, not faked.

## Tests

```bash
uv sync --extra connector                  # ensures .venv has pytest + connector deps
uv run pytest tests/                       # 97 tests, +1 opt-in (ORACLE_E2E=1) = 98
```

`uv run` (or `.venv/bin/python -m pytest tests/` after `uv sync --extra connector`) — running a
bare `pytest`/`python -m pytest` against an interpreter that never had `uv sync`
run against it will fail collection at `tests/conftest.py`'s `from web3 import
Web3` because that
interpreter was never populated by `uv sync` in the first place.

Unit tests (`tests/unit/`) cover wallet, DID, derivation, client, PII/PHI
redaction (`test_redactor.py`), intent hashing/deviation (`test_intent.py`),
and both tracing surfaces — MLflow autolog (`test_mlflow_tracing.py`) and the
run-tree `trace_run`/`traceable` API (`test_tracing.py`). Integration tests
(`tests/test_chain.py`, `tests/test_health.py`, `tests/test_trust_wiring.py`)
run real on-chain sequences against a live anvil chain running the real
`contracts/script/Deploy.s.sol`, with no mocked web3. Agents are bound through
`AgentRegistry` via `tests/v3_onchain.py`.

## Layout

```
integrity_sdk/
  did.py            Ed25519 DID + CAIP-10 EVM binding
  wallet.py         encrypted secp256k1 EVM keystore
  chain.py          fund / deploy / register on-chain (web3.py)
  registration_offchain.py  gasless Oracle registration (v3 default)
  xns.py            handle availability across both namespaces
  bcc.py            signed BCC commitment construction
  client.py         telemetry client → oracle
  core/             JCS, Merkle, signed packs, decision contract, receipts, OPA client
  abis/             trimmed contract ABIs (synced via make sync-abis)
  telemetry/        OTel core, MLflow tracing, run-tree tracing, AIS derivation
  integrations/     openai_integrity.py, langchain_callback.py
  security/         attestation.py, vault.py, AWS Nitro trust root
```
