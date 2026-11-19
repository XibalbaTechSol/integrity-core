# Integrity SDK and CLI — architecture redesign

Status: **proposed (revised after builder check)**. Date: 2026-11-18.
Companion to `2026-11-18-agent-wallet-custody-design.md` (approved, branch
`docs/agent-wallet-custody`). That design's §6.8 (SDK) and the CLI flows it names are built
**inside** the layout defined here.

## 1. Intent and why

The SDK and CLI were built around an on-chain architecture that no longer exists. That
architecture had per-agent `SovereignAgent` + `StateAnchor` primitives, `XibalbaAgentRegistry`,
`AgentPrimitivesFactory`, an agent-held "controller" key, and the Phase I kernel. The protocol has
since moved to:

- **Off-chain identity first.** A `did:integrity` Ed25519 key and gas-free Oracle registration.
  The agent0 / ERC-8004 passport and XNS handles sit on top.
- **Signed policy packs** evaluated in-process by the WASM engine.
- **Enforcement** at Shield, at harness hooks, and (per the wallet design) at the agent's standard
  smart wallet through `IntegrityHook`.
- **Evidence.** BCC commitments, signed chained receipts, decision traces, anchored on
  `ActionAnchor`.
- **Feedback.** AIS (`AISRegistry` checkpoints, local AIS) and telemetry.
- **Access.** Tenancy, entitlements, billing, and the session-key wallet.

The owner's goal is for the SDK and CLI to **reflect this architecture**, so that a developer, an
agent, or a sibling product can find each capability where the architecture says it lives.

**Goals.**
- **Package layout follows ADR-0001's six functions:** Identity, Rules, Enforcement, Evidence,
  Feedback, Access.
- **One SDK entry point** replaces `IntegrityClient` / `IntegrityAgent` / `SDKAgent` /
  `integrity()`.
- **The CLI uses the same six-function vocabulary.**
- **Legacy on-chain code is removed:**
  - `SovereignAgent`, the XAR/primitives deploy paths, `StateAnchor`, `--confined` and "controller"
  - replaced by v3 registration and the smart-wallet account
- **No existing import or command breaks on upgrade.** Old paths keep working, with deprecation
  warnings, for one release (owner decision, option A).

**Non-goals.**
- Changing any wire format or hash. Receipts, BCC commitments, envelopes, JCS bytes, Merkle
  conventions, DID documents and pack signatures stay byte-identical.
- Rewriting the rules engine, the receipt logic or telemetry internals. They move; they don't
  change.
- A TypeScript SDK. The console's `agent0.ts` / `oracle.ts` stay where they are.
- Shield and Cortex internals.

**Anti-goals.**
- A live service breaks when it upgrades the SDK.
- The facade becomes a god-object that imports the whole connector stack. The base install must
  stay light.
- Two places implement the same thing after the move. Shims re-export; they never duplicate.

## 2. Current state (verified 2026-11-18, `origin/main` c4a20aeb)

- **SDK**: 88 modules, ~17.5k lines.
  - Top level mixes identity (`did`, `wallet`, `agent_identity`, `identity_registry`), chain
    (`chain.py` 997 lines, `registration_onchain`, `erc8004`, `xns`, `evidence_anchor`) and hooks
    (`bcc`, `hook_runner`, `harness_hooks`).
  - Subpackages: `core/` (~5.8k), `telemetry/` (~2.5k), `integrations/`, `security/`, `billing/`.
- **Legacy references** to `SovereignAgent`, `XibalbaAgentRegistry`, primitives, `StateAnchor`,
  controller and confined:
  - `chain.py` 126
  - CLI `main.py` 28
  - `health.py` 25
  - `erc8004.py` 17
  - `registration_onchain.py` 12
  - a handful elsewhere
- **The dependency boundary is real and tested.**
  - The base install (`core`, `did`, `bcc`, `harness_hooks.normalize_hook`) imports no `requests`,
    web3 or OpenTelemetry. The `[connector]` extra adds them.
  - `tests/unit/test_import_hygiene.py` guards this, and the lazy `__getattr__` in `__init__.py`
    exists for it.
- **External consumers** (grep of the sibling repos):

| Consumer | Imports |
|---|---|
| xibalba-shield | `did` (`Keypair` ×29, `public_key_multibase`, `verify_signature`, `fingerprint_for_pubkey`, `load_or_create_did`), `core.packs.LoadedPack`, `core.opa`, `core.decision_trace`, `registration_offchain`, `billing.stripe_gateway` |
| xibalba-cortex | `normalize_hook`, `did` (`key_store_for_profile`, `load_or_create_did`, `write_did_file`, `read_did_file`, `DidFileError`, …), `core.JevAnalysis`, `core.jcs`, `core.decision_trace`, `crypto.merkle`, `integrations.cortex` |
| integrity-console (userapi) | `client.IntegrityClient`, `registration_offchain`, `did`, `bcc` |
| integrity-console (`integrity-dashboard/demo`) | tracks the SDK by git `branch=main` |
| bcc_middleware (in-repo, **live**) | `chain._contract` (private), `core.*`, `core.wasm_engine`; uses the `[wasm]` extra |
| integrity-core `scripts/`, `integrity-oracle` test-support scripts | assorted old paths |

  - **Every row above is a consumer** for the shim table, the migration PRs and the 0.3.0 gate,
    in-repo and private imports included (designer's call). `chain._contract`, `get_w3` and
    `load_deployments` stay exported as shims for bcc_middleware.

  - Shield's live install is a frozen copy in `/opt`.
  - Cortex's base checkout is pinned to `local`.
  - Upgrades reach the two live services at different times, which is why shims are mandatory.

- **CLI**: ~4.5k lines, entry point `integrity = integrity_cli.main:app` (Typer). Command groups:

| Group | Commands |
|---|---|
| `identity` | new, list, show |
| `wallet` | address, import |
| `handle` | available, claim, register, release, resolve, primary-handle, set-primary |
| `domain` | register, status |
| `vault` | sync |
| `receipts` | verify |
| `gate` | check |
| `pack` | build-wasm, verify-wasm |
| `policy` | check, compile, diff, map, prove, publish, set, show |
| `tenant` | register, show, backup, restore, export, delete |
| `role` | assign, list, revoke |
| `device` | revoke |
| `erc8004` | card, link, publish |
| `hooks` | install, uninstall |
| `auth` | set-token, show |
| `config` | set, show |
| top level | `register`, `status`, `doctor` |

## 3. Approaches

### 3.1 Compatibility (owner chose A)

| | **A. New layout + old-path shims (chosen)** | B. Clean break | C. Rework chain/wallet/CLI only |
|---|---|---|---|
| Consumers on upgrade | Keep working; deprecation warnings | Must change in the same wave | Mostly unaffected |
| Live-service risk | Lowest | Three coordinated releases | Low |
| End state | Fully reorganized after shim removal | Fully reorganized | Half reorganized |

### 3.2 Layout principle (designer's call)

The rejected alternative was a by-layer layout (`offchain/`, `onchain/`, `local/`). It fails
because each function spans layers. Identity, for example, covers the DID key, Oracle
registration and the passport, so a by-layer layout scatters one function across three packages.
The six-function layout matches ADR-0001, which is already the rule every component must name.
On-chain code is reached through a thin `chain/` layer used by the functions; it never sits
beside them as a seventh function.

## 4. SDK design

### 4.1 Package layout and module map

Base means importable with the base install. `[chain]`, `[telemetry]` and `[http]` are new
narrower extras, and `[connector]` stays as the union.

```
integrity_sdk/
  __init__.py            Integrity facade + lazy exports (+ old names as shims)
  identity/              WHO the agent is
  rules/                 WHAT is allowed
  enforce/               WHERE it is applied
  evidence/              WHAT happened, provably
  feedback/              HOW it is scored and observed
  access/                WHO may use what, and pays
  chain/                 thin on-chain plumbing (bindings, RPC, UserOps)
  integrations/          third-party adapters (unchanged)
  verticals/health/      HIPAA vertical (quarantined, §4.5)
  _shims/                generated old-path modules (§4.4)
```

| New location | From | Extra |
|---|---|---|
| `identity/keys.py` | `did.py` (Keypair, DID docs, key store, migration, `fingerprint_for_pubkey`, `verify_signature`) | base |
| `identity/registry.py` | `identity_registry.py`, `agent_identity.py` | base / http |
| `identity/subject.py` | `agent_subject.py` | base |
| `identity/registration.py` | `registration_offchain.py` plus the v3 on-chain handoff (wallet design §6.9: pending record, `--owner`) replacing `registration_onchain.py` | http, chain |
| `identity/passport.py` | `erc8004.py`: agent0 passport minted **by the wallet**; no `agentWallet` metadata | chain |
| `identity/handles.py` | `xns.py` | http |
| `identity/readiness.py` | `readiness.py` plus the wallet checks (`wallet_invariant`, `session_key_not_owner`, `hook_installed`) | base / chain |
| `rules/packs.py`, `rules/distribution.py` | `core/packs.py`, `core/pack_distribution.py` | base |
| `rules/engine.py`, `rules/wasm_build.py`, `rules/opa.py` | `core/wasm_engine.py`, `core/wasm_build.py`, `core/opa.py` | base |
| `rules/decision.py` | `core/decision.py` | base |
| `rules/onchain.py` | `core/pack_onchain.py`, `policy_registry.py` (`PolicyRegistry` roots) | chain |
| `enforce/hooks.py` | `harness_hooks.py` (`normalize_hook`, `IntegrityHookAdapter`) | base |
| `enforce/hook_runner.py` | `hook_runner.py` | http |
| `enforce/gate.py` | **local first** (owner decision S-I): evaluate with the installed signed pack through `rules/engine.py`, then fall back to bcc_middleware `/v1/bcc/intercept` when no pack is installed. The result says which path decided. bcc_middleware's evaluator stays in bcc_middleware; Shield internals are untouched | base (local) / http (fallback) |
| `enforce/break_glass.py` | `core/break_glass.py` | base |
| `enforce/account.py` | **new**: `AgentAccount` from wallet design §6.8 (counterfactual address, I1, UserOps, typed hook errors) | chain |
| `evidence/canonical.py` | `core/jcs.py`, `core/signing.py`, `core/signed_body.py` | base |
| `evidence/merkle.py` | `core/merkle.py` (+ `crypto/merkle.py` becomes a shim) | base |
| `evidence/bcc.py`, `evidence/posttool.py` | `bcc.py`, `posttool_report.py` | base |
| `evidence/receipts.py` (`writer`, `queue`) | `core/receipts.py`, `core/receipt_writer.py`, `core/receipt_queue.py` | base |
| `evidence/trace.py` | `core/decision_trace.py` | base |
| `evidence/anchor.py` | `evidence_anchor.py` (`ActionAnchor`) | chain |
| `evidence/vault.py`, `evidence/memory.py` | `vault.py`, `memory_dag.py`, `memory.py`, `core/memory.py`, `core/store_identity.py` | base |
| `evidence/offline.py` | `core/offline.py` | base |
| `evidence/attestation.py` | `security/attestation.py` (Nitro) | http |
| `feedback/ais.py` | `core/ais_local.py`, `core/ais_reward.py`, plus an `AISRegistry` reader | base / chain |
| `feedback/telemetry/` | `telemetry/*`, `client.py` (renamed `TelemetryClient`; `IntegrityClient` kept as alias), `batcher.py`, `collection.py` | telemetry |
| `feedback/privacy.py` | `security/redactor.py`, `telemetry/privacy.py` | base |
| `access/tenancy.py`, `access/export.py` | `core/tenancy.py`, `core/tenant_export.py` | base |
| `access/entitlements.py`, `access/usage.py` | `core/entitlements.py`, `core/usage.py` | base |
| `access/billing/` | `billing/*` | http |
| `access/keystore.py` | `wallet.py`: the **session-key** keystore and `Signer` protocol (wallet design §1.1) | chain |
| `access/secrets.py` | `security/vault.py` (interface only) | base |
| `chain/rpc.py` | the reusable parts of `chain.py`: `_send_signed` nonce/insufficient-funds retry, `_call_with_retry`, receipt waits | chain |
| `chain/contracts.py` | ABI loading + per-network addresses from `deployments.<network>.json`, **shipped as package data** in the wheel (so `/opt` installs and wheels resolve them), and overridable by `INTEGRITY_DEPLOYMENTS` (designer's call) | chain |
| `chain/userops.py` | **new**: bundler client, UserOperation build/sign/send, EntryPoint v0.7 | chain |
| `core/adapter_conformance.py` → `integrations/conformance.py` | | base |
| `core.JevAnalysis` | lives in `core/decision_trace.py`, so it moves with it to `evidence/trace.py`; `integrity_sdk.core.JevAnalysis` stays as a shim (Cortex imports it) | base |
| `agent_runtime.py`, `integrity.py` | folded into the facade (§4.2) | — |
| **deleted** | `hardware.py` (self-documented unused); legacy parts of `chain.py` (fund/deploy `SovereignAgent`, `StateAnchor`, primitives factory, XAR); the confined path of `registration_onchain.py`; the `controller` field in `agent_identity.py` | — |

### 4.2 One entry point

```python
from integrity_sdk import Integrity

ig = Integrity.load("claude")            # resolves the key store, config, network; no network I/O
ig.identity.did                          # did:integrity:…
ig.identity.register()                   # off-chain, gas-free (Oracle)
ig.identity.register_onchain(owner=…)    # pending record for console finish-setup
d = ig.enforce.gate(action)              # rules.evaluate + receipt + BCC commit → Decision
ig.evidence.receipts.verify(path)
ig.feedback.ais()                        # local + latest AISRegistry checkpoint
ig.account.spend(token, to, amount)      # session-key UserOp; typed errors with console URL
```

- **Namespaces load lazily** on first attribute access, so `Integrity.load` with the base install
  works. Touching `ig.account` without `[chain]` raises a clear `MissingExtra("chain")`, not an
  `ImportError` from deep inside.
- **The facade holds no logic.** Each namespace is a thin object over the subpackage functions,
  and everything it does is reachable without it.
- **Old entry points stay as real deprecated classes** (designer's call; the builder check found
  they cannot be same-object aliases of `Integrity`).
  - `IntegrityAgent`, `SDKAgent` and `integrity()` keep their full current API: `emit`, `prompt`,
    `response`, `tool_call`, `start_session`, `export_cortex`, `export_otlp`,
    `record_shield_decision`, and `open(harness, profile_root, expected_did, require_registered,
    device_id)`.
  - Their bodies delegate to the new packages, and they warn on construction.
  - The facade gains `ig.session` (the telemetry/session verbs) and `Integrity.load(harness=…,
    profile_root=…)`, so every old call has a new home.
  - Cortex's user-facing `connect.py` snippets move to `Integrity` in phase 4, before 0.3.0.
  - `IntegrityClient` is a same-object alias of `feedback.telemetry.TelemetryClient`.

### 4.3 Configuration

- A single `IntegrityConfig` resolves, in this order:
  1. explicit arguments
  2. env (`INTEGRITY_*`, existing names kept)
  3. `~/.config/integrity/config.toml` (the CLI's `config set` writes here)
  4. network defaults from `chain/contracts.py`
- The networks are `anvil`, `base-sepolia` and `base` (reserved).
- Today's ad-hoc `os.getenv` reads move behind it.
- `INTEGRITY_WALLET_PASSWORD` keeps its name (now the session-key password).

### 4.4 Compatibility shims (option A)

- **Each old public path** (every module and name a consumer imports, §2, plus every name in the
  current `_LAZY_EXPORTS`) becomes a module under `_shims/`, installed at the old dotted path. It
  re-exports from the new home and emits one `DeprecationWarning` per process naming the new
  path.
- **Shims are generated from a single table** (old path → new path). A test imports every row,
  asserts the object is the *same object* (`is`, not a copy), and asserts the warning fires.
  The three wrapper classes above are the only exception; they get a behaviour test instead.
- **Mechanism (designer's call):** old module paths are aliased in `sys.modules` to the new module
  objects, so monkeypatching through an old path still patches the real module.
- **Lifetime:** shims ship in **0.2.x** and are removed in **0.3.0**, after Shield, Cortex and the
  console have migrated (§6, phase 4). Removal is gated on a grep of those repos returning
  zero old-path imports.
- **`test_import_hygiene.py` extends to the new layout:** every module marked "base" must import
  with only the base dependencies, and so must every shim of a base module.

### 4.5 Health vertical

`health.py` (`CoveredEntityRegistry`, `SmartBAA`, `EHRGate`) is written against `SovereignAgent`.
It moves to `verticals/health/` **unchanged in behaviour**, behind an `[health]` extra, and is
marked experimental. Its `SovereignAgent` calls are removed and raise `NotPorted`. Porting it to
`AgentAccount` is a follow-up. (Designer's call; the alternative of deleting it loses a vertical
the contracts still carry.)

## 5. CLI design

**Same vocabulary as the SDK.** Every group maps to one of the six functions or to setup. Each
command is a thin layer over an SDK call; no business logic lives in `integrity_cli`.

| Command | Function | Replaces / notes |
|---|---|---|
| `integrity init` | setup | **new**: create identity + config, optional `--register`; replaces `identity new` + `config set` for first run |
| `integrity register [--onchain --owner 0x…]` | identity | v3 + wallet-design handoff; `--confined` removed |
| `integrity status`, `integrity doctor` | setup | `doctor` gains the wallet invariant checks |
| `integrity identity new\|list\|show\|migrate` | identity | |
| `integrity handle …` | identity | verbs unchanged. Off-chain `available`/`resolve` are unchanged; on-chain `register`/`set-primary`/`release` **prepare for the owner** the same way as `evidence anchor` (S-J) |
| `integrity passport card\|link\|publish\|show` | identity | was `erc8004` |
| `integrity rules build\|verify\|compile\|check\|diff\|map\|prove\|publish\|set\|show` | rules | merges `pack` + `policy` |
| `integrity gate check`, `integrity hooks install\|uninstall` | enforce | |
| `integrity wallet show\|limits\|session rotate\|spend\|approvals` | enforce/access | per the wallet design. **`wallet show` prints the one agent address (the smart wallet)**, with the session key as a labelled sub-field. `wallet address` keeps printing the keystore EOA for 0.2.x, but with a stderr deprecation line and JSON field `session_key`, never `address`, so no second "agent wallet" is ever presented (designer's call) |
| `integrity evidence verify\|sync\|anchor` | evidence | merges `receipts verify` + `vault sync` + anchoring. **`anchor` prepares, the owner signs** (owner decision S-J): it builds the unsigned wallet operation, stores it with the Oracle like an approval (wallet design D-G), and prints the console link. Agents never write on-chain anchors directly |
| `integrity ais show` | feedback | **new** |
| `integrity tenant …`, `role …`, `device …`, `auth …`, `config …` | access | unchanged |
| `integrity domain …` | — | **deprecated**: domain policy is optional (wallet design D-L); kept as alias, warns |

**Rules for every command:**
- `--json` gives machine output with a stable schema, plus `--network`.
- **Exit codes keep today's published contract** in `integrity_cli/output.py` (designer's call;
  option A means nothing breaks):
  - 0 ok, 1 negative result, 2 usage
  - 3 unverified or unreachable (retryable)
  - 4 chain revert
  - **new 5:** not configured or missing extra (not retryable)
  - **new 6:** wallet policy denial: a typed hook error such as `LimitExceeded` or `AisStale`;
    the JSON carries the error name and console URL
  - Unavailable is never reported as "absent", per the evidence-boundary rule.
- **JSON schema ids** stay `integrity.cli.<group>.<cmd>.v1`. Hidden aliases emit the **old**
  schema ids and codes during 0.2.x.
- Errors carry a one-line fix (and the console URL where one exists).

**Aliases.** Every old command path (`pack …`, `policy …`, `receipts verify`, `vault sync`,
`erc8004 …`, `domain …`) stays as a hidden alias for 0.2.x, prints one deprecation line to stderr
(never stdout, so `--json` stays parseable), and is removed in 0.3.0.

## 6. Delivery phases

Each phase is its own PR or PRs, green CI, merged at the commit CI ran on.

1. **Skeleton + move, with no behaviour change.**
   - Create the subpackages.
   - Move the modules (with `git mv`, to keep history).
   - Generate the shims, extend import hygiene, and run the full existing suite unchanged
     through shims.
   - Bump to 0.2.0.
   - Consumers keep working untouched.
2. **Chain layer.** Detailed only after the wallet spike (wallet Plan 1, Task 1) picks the
   stack, because `chain/userops.py`, the counterfactual-address maths and session-key signing
   depend on it. This phase **is** wallet Plan 3: the wallet design's §6.8 is built here, at
   these paths, never first at its own top-level paths. Phases 1 and 3 stand alone.

   - Delete the legacy on-chain code, add `chain/contracts.py` + `chain/rpc.py` +
     `chain/userops.py`.
   - Build `enforce/account.py`, `identity/registration.py` (handoff) and `identity/passport.py`
     to the wallet design, against Anvil.
   - This phase is the SDK half of the wallet plan, and depends on its contracts.
3. **Facade + config + CLI regroup**, with aliases and the exit-code table.
4. **Consumer migration**, one PR per repo:
   - **xibalba-shield**: fix the frozen `/opt` snapshot on deploy.
   - **xibalba-cortex**: lands on `main`, then onto `local` deliberately (pin rule).
   - **integrity-console** userapi.
5. **0.3.0**: remove the shims and aliases once the consumer grep is zero.

## 7. Verification

- **Wire formats.** Golden vectors are captured from 0.1.0 *before* phase 1, for receipts, BCC
  commitments, envelopes, JCS, Merkle roots, DID documents and pack signatures. The tests assert
  byte equality after each phase.
- **Shim table test.** Same object, warning fires, and base shims stay import-hygienic.
- **The current suite passes** unchanged in phase 1, run through the shims. Any edit to a test in
  phase 1 needs a written reason in the PR.
- **Consumer smoke.** Each consumer's own test suite runs against the 0.2.0 wheel before its
  migration PR.
- **CLI tests:**
  - every command's `--json` schema is snapshot-tested
  - every alias resolves and warns on stderr only
  - exit codes follow the table
- **Facade tests:**
  - `Integrity.load` works on a base install
  - `ig.account` without `[chain]` raises `MissingExtra`

## 8. Decisions record

| # | Decision | Source |
|---|---|---|
| S-A | Goal: SDK/CLI reflect the current architecture | Owner, 2026-11-18 |
| S-B | Compatibility: new layout + old-path shims for one release (0.2.x), removed in 0.3.0 | Owner, 2026-11-18 |
| S-C | Six-function layout (ADR-0001) with a thin `chain/` layer | Designer's call |
| S-D | One `Integrity` facade; old entry points become shims | Designer's call |
| S-E | Narrow extras `[chain]`, `[telemetry]`, `[http]`, `[health]`; `[connector]` kept as union | Designer's call |
| S-F | CLI regrouped to the same vocabulary; old commands as hidden aliases for 0.2.x | Designer's call |
| S-G | Health vertical quarantined under `verticals/health`, not deleted | Designer's call |
| S-H | `gate` check moves into the SDK (`enforce/gate.py`) | Designer's call |
| S-I | Gate is **local first**: signed pack in-process, bcc_middleware as fallback | Owner, 2026-11-18 |
| S-J | Non-payment on-chain writes (evidence anchors, XNS handle writes) are **owner-signed in the console**; the CLI/SDK prepares them | Owner, 2026-11-18 |
| S-K | Exit-code table kept; 5 and 6 added; aliases keep old codes and schema ids | Designer's call |
| S-L | Old entry-point classes are real deprecated wrappers; the facade gains `session` | Designer's call |
| S-M | BCC `verifying_contract` = `XibalbaAgentRegistry` where deployed, else `AgentRegistry` v3. bcc_middleware and Oracle config gain the v3 key in the same phase. The commitment *format* is unchanged | Designer's call |
| S-N | All consumers count, including bcc_middleware, in-repo scripts and the console demo | Designer's call |

## 9. Left to the builder

- exact module splits inside each subpackage
- shim generation mechanism (generated files vs. a `sys.modules` import hook), as long as §4.4's
  tests hold
- `--json` schema field names, as long as they are stable and snapshot-tested
- config file schema
- bundler choice for Anvil tests
