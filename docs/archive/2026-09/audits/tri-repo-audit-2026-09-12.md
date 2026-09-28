# Tri-repository high-resolution audit — 2026-09-12

**Scope:** `integrity-core`, `xibalba-shield`, `xibalba-cortex`
**Method:** claim verification against current source and live on-disk state. Every finding below was reproduced in this session or carries a `file:line` citation. Prior-session assertions were re-verified, not inherited.
**Framing:** findings are tagged with `docs/SPEC-v2.0.0-proposed.md` §1 status tags and mapped to its §11 acceptance gates.
**Authority note:** `docs/SPEC.md` remains normative. This audit does not change that. `SPEC-v2.0.0-proposed.md` is used here as the organizing frame only.

---

## 0. Headline

The cross-platform identity work did not fail because Shield's registration was misconfigured. It failed because **there are two disjoint identity stores that can never converge**, and because **the SDK destroys private keys on a recoverable error**. The missing `MINTER_ROLE` recorded in the 2026-09-11 handoff is a third, shallower problem that merely stopped a registration already aimed at the wrong DID.

Three distinct, independently verified defects:

| # | Defect | Severity | Gate |
|---|---|---|---|
| F1 | SDK `load_or_create_did()` silently generates a new keypair **and overwrites the existing private key** when `document.json` is missing or mismatched | Critical — irreversible identity loss | Gate 1 |
| F2 | SDK and CLI use **separate identity homes**; the DID being registered is not the DID Shield signs with | Critical — registration can never take effect | Gate 1 |
| F3 | `primitives.json` registration cache carries **no chain id**; a local-anvil (31337) registration is read as authoritative while pointed at Base Sepolia | High — false "registered" state | Gate 1 / Gate 5 |

Confirmed by live on-chain readback (§2.1): **neither Shield DID is registered on Base Sepolia**, while `xibalba`, `xibalba-health` and `xibalba-quant` are. Shield has never had a live registration — the local `primitives.json` suggesting otherwise is an anvil artifact.

---

## 1. F1 — Destructive identity regeneration `[BUILT]` defect, Gate 1

**Location:** `integrity-sdk/integrity_sdk/did.py:234-249`

```python
if key_path.exists() and doc_path.exists():
    keypair = Keypair.from_pem(key_path.read_bytes())
    doc = json.loads(doc_path.read_text())
    if doc.get("id") == f"did:{_DID_METHOD}:{fingerprint_for_pubkey(...)}":
        return doc["id"], keypair, doc

keypair = Keypair.generate()          # ← falls through
...
key_path.write_bytes(keypair.private_pem())   # ← OVERWRITES the original key
```

The fallthrough triggers when **either** file is missing or when the document does not match the key. The recorded intent (source comment at `did.py:237-239`) is "regenerate rather than serve an inconsistent identity" — but regeneration writes over `private_key.pem`, so the original Ed25519 key is destroyed, not merely bypassed.

**Reproduced in this session** (isolated `INTEGRITY_DID_HOME`, no production data touched):

```
1. original DID : did:integrity:0b64a292…
   key sha256   : 6cd8fee160f8dcd4
   [delete document.json only]
2. after doc.json deleted -> did:integrity:eede3a82…
   key sha256   : 0b828a25194b42ae
   SAME DID?    : False
   ORIGINAL PRIVATE KEY STILL ON DISK?: False
```

Deleting one **non-secret JSON file** permanently destroys the agent's signing key and mints a new DID. Any of the following triggers it: partial backup restore, container/service recreation, a volume mounted with only the key, an interrupted write, or a hand-copied document.

This is the mechanism behind the reported "key rotation" — it is not rotation. It is **automatic recovery by replacement**, which `SPEC-v2.0.0-proposed.md` §4.3 explicitly forbids: *"Missing or inconsistent key state MUST fail closed. Ordinary startup MUST NOT generate a replacement key."* §12 already records the intent to fix this ("Key recovery → Replace with fail-closed recovery workflow"); this audit confirms the defect is live in source and quantifies it as **destructive**, which the ledger row does not say.

**Test coverage gap:** `integrity-sdk/tests/unit/test_did.py` covers fresh generation, stability across reloads, and per-agent separation. **No test covers the mismatch/missing-document path** — the one that destroys keys.

### Required fix (Gate 1)

1. Fail closed on inconsistent state: raise, do not regenerate.
2. Never write to an existing `private_key.pem`. Reconstruct `document.json` from the key when only the document is missing — that case is losslessly recoverable and should not be an error at all.
3. Require an explicit, separately authorized operation for key replacement, with a recorded successor relationship (§4.3).
4. Add regression tests for: missing document, mismatched document, unreadable key, partially written key.

---

## 2. F2 — Two disjoint identity stores `[BUILT]` defect, Gate 1

This is the finding that explains why Shield registration "never completes."

There are two independent identity homes, written by two independent implementations (`CLAUDE.md` records that `integrity-cli` deliberately does not import `integrity-sdk`):

| Store | Owner | Shield identity | Status |
|---|---|---|---|
| `~/.integrity/did/xibalba-shield/` | **SDK** — what Shield's runtime loads and signs with | `did:integrity:2ea17967…` | has a full 7-address `primitives.json` |
| `~/.integrity-cli/identity/shield-replacement.pem` | **CLI** — what `scripts/register_shield_with_funder.sh` registers | `did:integrity:b3324032…` | registration incomplete |

Verified by deriving the DID directly from each private key: `shield-replacement.pem` → `did:integrity:b3324032b6248bec2b61b8d3ccb46df708680aab6c57762e3303e14437a861fb`, exactly the "replacement DID" in `docs/runbooks/shield-registration-handoff-2026-09-11.md`. That key exists **only** in the CLI store; nothing under `~/.integrity/did/` holds it.

**Consequence:** completing the runbook's resume procedure — even with the correct `MINTER_ROLE` — registers `b3324032…`. The on-chain `registerPrimitives` would likely succeed; nothing blocks it. What fails is everything downstream, because **Shield's runtime presents `2ea17967…` and always will.** The registration would look successful and leave Shield effectively unregistered. (I did not trace the oracle's DID-matching path in `handlers.rs`, so the exact downstream rejection shape is `[UNVERIFIED]` — but the mismatch itself is verified.)

The same divergence affects the primary agent, so this is systemic rather than Shield-specific:

```
~/.integrity/did/xibalba/        → did:integrity:68fed133…   (SDK)
~/.integrity-cli/identity/xibalba.pem → did:integrity:f96ae072…   (CLI)
```

**Label sprawl (same root cause, Gate 1 §4.4):** `~/.integrity/did/` holds **eight** distinct `xibalba-shield*` identities, each a different DID — `xibalba-shield`, `-adr-live`, `-cli-run-test`, `-local`, `-resource-bench`, `-test`, `-timing`, plus the CLI's `shield-replacement`. Because `agent_dir()` (`did.py:209-214`) keys identity purely on a caller-supplied label, every test run, benchmark, and local variant mints a permanent new protocol identity. This is precisely what §4.1 forbids: *"A deployment, runtime instance, or session MUST NOT silently create a new public agent identity."*

### Required fix (Gate 1)

1. Decide one canonical identity store and have the other read it. Two reimplementations of the wire format are defensible; two identity homes are not.
2. Introduce `AgentSubject` (§4.1) as the join key, with the label demoted to a non-authoritative alias.
3. Before any further registration attempt: **choose which Shield DID is canonical** — `2ea17967…` (what Shield signs with) or `b3324032…` (what has Base Sepolia contracts deployed) — and record the decision as a §9.2 mapping record. Do not register the other.
4. Quarantine the six stale `xibalba-shield-*` label identities rather than deleting them (they are evidence), and stop tests from writing into the production DID home.

### 2.1 On-chain readback — **neither Shield DID is registered on Base Sepolia** `[BUILT]` evidence

Queried live against `XibalbaAgentRegistry` `0x72e21e44AdD6d6e7CAa02eaedF078630afC40819` on Base Sepolia (`resolveDID(string)`, `https://sepolia.base.org`). The probe discriminates correctly — three agents *do* resolve — so a revert here means genuinely unregistered, not a bad call:

| Identity | DID | Base Sepolia |
|---|---|---|
| `xibalba` | `68fed133…` | **REGISTERED** |
| `xibalba-health` | `42b1ead3…` | **REGISTERED** |
| `xibalba-quant` | `7d0ecae5…` | **REGISTERED** |
| `xibalba-shield` (SDK) | `2ea17967…` | **not registered** (`UnknownDID`) |
| `shield-replacement` (CLI) | `b3324032…` | **not registered** (`UnknownDID`, `0x4c2a24b3`) |
| all six `xibalba-shield-*` variants | — | not registered |

Two consequences:

1. **F3 is confirmed decisively.** `~/.integrity/did/xibalba-shield/primitives.json` holds a complete 7-address PrimitiveSet for `2ea17967…`, yet that DID resolves nowhere on Base Sepolia. It is an anvil-31337 artifact being read as authoritative — exactly the chain-ambiguity defect, now demonstrated rather than inferred.
2. **The §8 decision is easier than it looked.** This is not a choice between a registered and an unregistered identity. *Neither* is registered, so there is no on-chain history to preserve on either side — which means the correct choice is plainly `2ea17967…`, the DID Shield's runtime actually loads. Register that one and the mismatch disappears. The `b3324032…` contracts (`SovereignAgent 0xB3521d8d…`, `StateAnchor 0xae36df19…`) are orphaned deployments to archive, not assets to preserve.

---

## 3. F3 — Chain-unqualified registration cache `[BUILT]` defect, Gate 1/5

`~/.integrity/did/xibalba-shield/primitives.json` records a complete 7-address PrimitiveSet:

```json
{"did": "did:integrity:2ea17967…", "evm_address": "0xB5831537…",
 "sovereign_agent": "0x1514bE13…", "state_anchor": "0x4904D8C2…", …,
 "oracle_registered": false}
```

There is **no `chain_id` field**. The 2026-09-11 handoff notes `0xB583…` "belongs to local chain `31337`" — so this file is a **local anvil registration that reads as authoritative on Base Sepolia**. Written at `registration.py:453-454` from `registration.to_dict()`; contrast `registration.py:418`, where the DID *document* does get chain-bound via `attach_evm_account(doc, addr, chain_id)`. The cache was not given the same treatment.

Compounding it, `registration.py:167` defaults `DEPLOYMENTS_FILE` to `../deployments.local.json` — local anvil — so the default path silently produces chain-31337 state in the same file the Base Sepolia flow later reads.

**Three conflicting registration states for "Shield" exist on disk right now:**

| Source | SovereignAgent | StateAnchor |
|---|---|---|
| `~/.integrity/did/xibalba-shield/primitives.json` | `0x1514bE13…` | `0x4904D8C2…` |
| `~/.integrity/did/xibalba-shield/registration_progress.json` | `0x7037744A…` | `0x8CB6F305…` |
| `~/.integrity-cli/identity/shield-replacement.registration_progress.json` | `0xB3521d8d…` | `0xae36df19…` |

None of the three can be distinguished by chain from the file contents alone.

**Operational note:** `~/.integrity/did/xibalba-shield/registration_progress.json` is owned by **root** (mode `rw-r--r--`, dated 2026-09-11 00:35) inside a user-owned tree. Shield ran registration as root at least once; subsequent non-root runs cannot rewrite that file, so progress state can silently desynchronize from reality.

### Required fix (Gate 1/5)

1. Add `chain_id` to `primitives.json` and `registration_progress.json`; refuse to read a cache whose chain does not match the connected RPC.
2. Remove the `deployments.local.json` default, or make the target chain an explicit required argument.
3. Reconcile or archive the three conflicting state files before the next registration attempt.
4. Fix the root-owned file's ownership and stop running registration as root.

---

## 4. F4 — Cortex retrieval returned empty for content that exists `[BUILT]` defect, Gate 3

Reproduced in this session. `memory_recall("shield registration broken cross-platform identity")` returned `{"result": []}`. Direct read-only SQL against `~/.hermes/xibalba-cortex/default/graph-memory.sqlite3` returned ~25 matching rows on a `content LIKE` query, including several created 2026-09-12 that are directly on-topic.

Retrieval silently returning empty is worse than erroring: it reads as "no such memory" and it defeated the stated purpose of storing the registration context in the first place.

**Performance, separately:** `memory_status` and `memory_recall` both exceeded 120 s and had to be backgrounded, against a 6.1 GB store with a 122 MB uncheckpointed WAL. There are also two stores of divergent size (`graph-memory.sqlite3` 6.1 GB vs `default/graph-memory.sqlite3` 2.9 GB), which is itself a profile-resolution hazard.

*(Root cause and the Gate 3 authorization walk are recorded in §6.)*

---

## 5. xibalba-shield

Verified independently against Shield source, systemd units, and on-disk state. Shield's own code is largely correct about *what* it stores; the defects are in *which identity* it selects and where that identity lives.

### 5.1 Two identity stores selected by OS user `[BUILT]` defect, Gate 1 — new

`/etc/systemd/system/xibalba-shield.service:20` runs `User=xibalba-shield`, whose home `/home/xibalba-shield` **does not exist**, with `ProtectHome=read-only` (line 29). `/usr/local/bin/xibalba-shield-run` never passes `--agent-label`.

So the service path resolves its DID home to a nonexistent, read-only location, while the interactive path (as user `xibalba`) resolves to `/home/xibalba/.integrity/did/xibalba-shield/`. **Same label, two disjoint identity stores, selected by which OS user happens to run it.** Combined with F1, a service-context run that cannot read its document is a candidate for silent key replacement.

This is the §4.4 violation in its most concrete form, and it is a fourth identity namespace on top of the two in F2.

### 5.2 Exporter conflates device and agent identity `[BUILT]` defect, Gate 1

`shield/integrity_exporter/exporter.py:83-84`, verbatim:

> "Bootstraps (or reuses) a real local DID/keypair … **one identity per device/deployment**, persisted under integrity-sdk's own agent_dir convention so restarts don't mint a new DID each time."

Directly contradicts §4.4 (*"Machine identity MUST NOT determine the portable agent subject"*). The trailing rationale is also factually false given F1: restarts **do** mint a new DID when `document.json` is missing or mismatched.

### 5.3 Label is a bare string, not a derived identity `[BUILT]` defect, Gate 1

`load_or_create_did(agent_label)` is called at `exporter.py:85` and `preflight.py:90`. The label defaults to `"xibalba-shield"` (`exporter.py:75`, `cli.py:668`, `backend/api.py:732`, `backend/store.py:183,440`), with `cli.py:557` hardcoding `"xibalba-shield-local"` for `local-run`. It is a CLI argument — not derived from tenant or device. `INTEGRITY_DID_HOME` is set nowhere in Shield source or packaging (only in tests). This is the mechanism behind the label sprawl in F2.

### 5.4 Device identity — separate in storage, coupled in schema `[PARTIAL]`, Gate 1

`shield/config/loader.py:154-156` defines `device_id` (required), `tenant_id`, `device_role`; `backend/store.py:454` persists them as distinct columns alongside `agent_label`, and `store.py:753` selects `integrity_agent_id`. The database does **not** conflate them.

The coupling is semantic: `agent_label` is stored **per device row**, so the schema models one agent label per device — the device→agent binding §4.4 forbids. Correct direction, wrong cardinality.

### 5.5 Wallet password stored in cleartext beside the keystore `[BUILT]` defect — new, security

Shield's SDK-side EVM wallet uses a real V3 keystore (`scrypt`/`aes-128-ctr`). But the password sits next to it:

```
/home/xibalba/.integrity/wallet/xibalba-shield/keystore.json
/home/xibalba/.integrity/wallet/xibalba-shield/WALLET_PASSWORD.txt
```

Both mode `600`. At-rest encryption is nullified by co-location — anything that can read the keystore can read the password. Fix before any mainnet or production-funds use.

### 5.6 Hygiene — real divergence, one conflict candidate

`main` is ahead 1 / behind 2.

- Ahead: `04133c9 docs: configure trusted policy issuer secret` — touches only `packaging/systemd/shield.env.example`.
- Behind: `110e10c fix(cli): initialize Cortex options for local-run` and merge `06ed23f` (PR #24) — touch `docs/wiki/WIKI_LOG.md`, `packaging/systemd/shield.env.example`, `shield/cli.py`.
- **Both sides edit `packaging/systemd/shield.env.example`** — that is the conflict candidate on merge or rebase. Resolve it deliberately; do not let a rebase pick a side.

Uncommitted: `ui/src/components/SignIn.jsx:7` and `ui/vite.config.js:37`, one line each, port `8421`→`8765`. No remote commit touches either, so no conflict — but this is uncommitted drift that silently repoints the UI's default control plane. Commit it as an intentional default change or revert it; do not leave it dirty.

---

## 6. xibalba-cortex

### 6.1 F4 root cause — 99.86% of memory is unrecallable `[BUILT]` defect, Gate 3 — critical

The empty `memory_recall` result in §4 is **not** an agent-scope filter and **not** a stale FTS index. Two compounding causes:

**Cause 1 — status filter vs. ingest default, with no promotion path.**

`_lexical_ranked_ids` hard-filters `m.status IN ('active','confirmed')` (`store.py:2161`). But `remember()` defaults to `status: str = "candidate"` (`store.py:1619`, `store.py:1646`), and **nothing ever promotes a candidate**: grepping `store.py` for `def confirm` and `status = 'confirmed'` returns zero matches.

Measured in the store the MCP server actually opens:

| status | count |
|---|---|
| candidate | 708,479 (99.86%) |
| confirmed | 1,268 |
| active | 69 |
| quarantined | 17 |

**Recall can see 1,337 of 709,448 memories.** Traced directly for the failing query: the generated FTS query matched **9 rows**, the join to `memories` kept all 9, and the status filter dropped it to **0** — every match was `candidate` or `quarantined`. The search worked perfectly; the gate discarded the results.

This means memory written via `memory_remember` is, by default, permanently invisible to `memory_recall`. That is the single highest-impact defect in this audit for day-to-day work: it silently defeats the purpose of storing context at all, and it reads as "no such memory" rather than as an error.

**Cause 2 — store split-brain.** Two live databases both self-describe as `profile_id = "default"`:

| Path | Size | Memories | Latest | Written by |
|---|---|---|---|---|
| `~/.hermes/xibalba-cortex/graph-memory.sqlite3` | 6.1 GB | 709,448 | 17:10 | **what the MCP server opens** |
| `~/.hermes/xibalba-cortex/default/graph-memory.sqlite3` | 2.9 GB | 369 (328 confirmed) | 16:33 | the Hermes plugin |

The server resolves `self.db_path = self.home / "graph-memory.sqlite3"` (`store.py:692`, `server.py:96`, `config.py:22`) with **no profile segment**. No file under `src/xibalba_cortex/` constructs a profile-scoped path — but the Hermes plugin asserts one does (`hermes-agent/tests/plugins/test_xibalba_cortex_observer_boundary.py:40`).

So Hermes turn-ingested memories — which *are* written `confirmed` — land where the server never reads, and the store the server does read is 99.86% unrecallable candidates. Both failure modes point the same direction, which is why the symptom was total rather than partial.

**Corroborated after the fact.** Both backgrounded calls eventually returned, and both confirm the diagnosis rather than contradicting it:

- `memory_status` returned `db_path: /home/xibalba/.hermes/xibalba-cortex/graph-memory.sqlite3`, `profile_id: "default"`, `memory_count: 710166` — confirming the server opens the non-profile-scoped 6.1 GB store, exactly as Cause 2 describes.
- A *broader* recall (`"shield registration"`, two terms) returned ~258 KB of results — after roughly 20 minutes. So recall is not wholly broken: it returns whatever survives the status gate. The five-term query failed because all 9 of its matches were `candidate`/`quarantined`. This is the precise shape of the defect — **recall silently returns a filtered subset and reports it as the whole answer**, which is why the failure reads as "no such memory" rather than as an error.

*(Not the cause: FTS is not stale. It holds 709,622 rows against 709,448 memories — 174 rows ahead. Minor desync, worth its own ticket.)*

**Performance:** FTS and indexed lookups return in ~0.0 s. `count(*)` over `memories` exceeds 120 s. The timeouts are full-scan aggregates plus contention on `GraphStore`'s single shared connection behind one `threading.RLock` (`store.py:694-700`) while live writers append to a 122 MB uncheckpointed WAL. `memory_status` additionally runs an integrity check over 6.1 GB, which alone explains its timeout.

### 6.2 Required fixes (Gate 3, ordered)

1. **Decide the contract for `status`.** Either `remember()` defaults to `confirmed`, or a promotion path exists and is called. Today it is neither — a default that nothing can undo. This is a one-line-severity fix with a very large effect.
2. **Backfill or triage the 708,479 candidates.** Even after the default is fixed, existing memory stays invisible.
3. **Resolve the store split-brain.** One profile-resolution rule, used by both the server and the Hermes plugin, with a startup assertion that the resolved path matches the declared `profile_id`.
4. Checkpoint the WAL; replace `count(*)` health probes with cheap approximations.

### 6.3 Gate 3 authorization walk

Audited all 80 `@server.tool()` functions. **35 carry no agent/session/memory scope check at all.**

> **Every tag in this table is conditional on the principal being non-None.** On the stdio transport — how this session calls Cortex — `_assert_memory_scope` returns unchecked (`server.py:165-166`), so even the rows marked `[BUILT]` enforce nothing. Read the tags as "implemented," not "in force."

| Gate 3 item | Tag | Evidence | Gap |
|---|---|---|---|
| Tenant + agent-subject membership records | `[PLANNED]` | `grep -c tenant store.py` → **0**; no `tenant_id`, `visibility`, or `agent_subject` column in any of 30 tables | Nothing exists to build on |
| `agent_id` coverage | `[PARTIAL]` | Only 3/30 tables carry it: `sources:199`, `agent_devices`, `sessions:218`. `memories` has none — scoping is indirect via `memories.source_id → sources.agent_id` (`server.py:167-169`) | attachments, entities, relations, embeddings, otel_events, inference_tasks, integrity_links cannot be agent-scoped even in principle |
| Server-side principal→scope | `[PARTIAL]` | `_bound_agent_id` (`server.py:120-140`) correctly refuses caller-supplied mismatches — but **only when `current_principal() is not None`**. `_assert_memory_scope` returns unchecked if `bound is None` (`server.py:165-166`) | **Over stdio — how this session calls it — principal is None, so all scope checks no-op.** Authorization is transport-conditional, not server-side-mandatory. §8.2 not met |
| `memory_embed` | `[PLANNED]` | `server.py:383-393` no check; `store.store_embedding` (`store.py:2706`) validates model/dimension only | Unscoped at **both** layers. Contrast `memory_similar:371`, which does assert |
| `memory_attach` | `[PLANNED]` | `server.py:405` no check, while sibling `memory_list_attachments:419` asserts | Write unscoped, read scoped |
| Telemetry | `[PARTIAL]` | `memory_record_otel_batch:479` asserts session scope; `runtime_ingest_event:1093` and all 24 `runtime_*` adapter tools do not | Adapter ingest path entirely unscoped |
| Graph traversal / relation mutation | `[PARTIAL]` | `memory_neighbors:611`, `memory_find_path:618` bind agent; `memory_link_entities:596` asserts memory scope | Best-covered area, but no-ops on stdio |
| Export | `[PARTIAL]` | `memory_export_provenance:571` asserts memory scope + agent binding | — |
| Backup | `[PLANNED]` | `memory_backup:671`, `memory_backup_reconcile:689`, `memory_vault_inspect:709` — no checks | §8.3 requires authorization to cover backups |
| Visibility / cross-agent sharing | `[PLANNED]` | No `visibility` column anywhere; no grant table | §8.4's required default `private_agent` is absent |
| Inference claim/completion | `[PARTIAL]` | Lease mechanics exist — `claim_owner`, random `claim_token`, 900 s lease (`store.py:4353-4380`), completion verifies both (`store.py:4560`). But `claim_inference_task` (`server.py:922`) has no scope check and `claimed_by` defaults to `"anonymous-worker"` | Lease-bound, not scope-bound |

The graph and export paths are the best-covered in the codebase — but "best-covered" is not "enforced" while the transport in use bypasses them.

**§8.5 mode, stated plainly:** Cortex today is a single-store SQLite system with application-level filters that are **bypassed entirely on the unauthenticated stdio path**. Per §8.5 this must not be described as production multi-tenant security. It is local single-agent mode — correctly `[BUILT]` for that purpose, `[PLANNED]` for multi-agent service mode.

The transport-conditional authorization is the finding to act on first: it means the scope checks that *do* exist provide no guarantee under the transport actually in use.

---

## 7. integrity-core

`forge` 1.7.1, `cargo` 1.96.0, `uv` 0.11.26, `nargo` 1.0.0-beta.22 and node 22 are all present. The prior session's "forge: command not found" is stale — Solidity claims **are** verifiable in this environment and were verified here.

### 7.1 The spec's own kernel claim is wrong — strike it `[BUILT]`, Gate 2

`SPEC-v2.0.0-proposed.md` §6.3 records an "open test defect": *"the focused account and registry-hook fixtures fail during setup with `Unauthorized(...)`."* §12 repeats it for both `IntegrityKernel` and `IntegrityAccount`.

**This does not reproduce. The suites pass:**

| Suite | Result |
|---|---|
| `--match-contract IntegrityAccount` | **121 passed, 0 failed** |
| `--match-contract IntegrityKernel` | **7 passed, 0 failed** |
| `IntegrityERC8004Registry` + `IntegrityIdentityReadV1` | **26 passed, 0 failed** |

Every `Unauthorized` in `test/IntegrityAccount.t.sol` (`:513`, `:517`, `:1317`, `:1326`, `:1331`, `:2012`) is a deliberate `vm.expectRevert` negative assertion — a **passing** test. That is almost certainly what the earlier audit misread.

The named *mechanism* is real: `test/IntegrityAccount.t.sol:278` does use `vm.computeCreateAddress(address(this), vm.getNonce(address(this)) + 1)`, guarded by an assertion at `:302`. The fixture is genuinely nonce-prediction-dependent — it simply is not failing.

**Action:** strike §6.3's "Current audit finding" paragraph and correct the two §12 ledger rows. Gate 2's first bullet ("repair nonce/address-prediction fixtures") is already satisfied and should be closed.

### 7.2 The HEAD commit's own regression test never asserts `[BUILT]` defect, Gate 2 — unreported

Full suite: **529 passed, 1 failed (530 total)**. The one failure is the regression test for HEAD commit `92ebed2 "fix: reject zero controller registrations"`.

Independently reproduced in this session:

```
[FAIL: next call did not revert as expected] test_registerPrimitivesRejectsZeroController() (gas: 11344)
```

**Test defect, not a source defect.** `contracts/test/XibalbaAgentRegistry.t.sol:115` inlines an external call into the argument list:

```solidity
vm.prank(registrar);
vm.expectRevert(XibalbaAgentRegistry.ZeroController.selector);
registry.registerPrimitives(registry.didHash("did:integrity:zero-controller"), primitives, address(0), domainId);
```

Solidity evaluates `registry.didHash(...)` **first**, so both cheatcodes bind to that pure view call, which never reverts. Every other test in the file hoists it (`bytes32 h = registry.didHash(DID);` at `:100`, `:106`). The sibling `test_registerEnterpriseAgentRejectsZeroController` (`:118`) passes, proving the guard itself works.

The source fix is sound — `XibalbaAgentRegistry.sol:63` and `:85` both `revert ZeroController()`.

**But the claim recorded in Cortex on 2026-09-12 16:15 — that zero-controller rejection landed "with regression coverage" — is false.** The primary regression test does not execute its assertion. This is exactly the `implemented ≠ tested` distinction §1 exists to enforce, caught in the wild. One-line fix: hoist the `didHash` call.

### 7.3 `isERC8004Conformant()` is a hardcoded `true` `[EXPERIMENTAL]`, Gate 4

`contracts/src/kernel/IntegrityERC8004Registry.sol:97-99` returns a hardcoded `true`, with NatSpec reading *"Returns true — this contract IS ERC-8004 conformant."* The title NatSpec (`:10`) declares it an "ERC-8004 conformant Identity Registry."

Its test is a tautology — `test_isERC8004ConformantReturnsTrue` asserts the constant. Worse, the same suite asserts `supportsInterface(0x80ac58cd)` (ERC-721) at `:40` **and** `test_transferReverts` at `:112` — claiming the ERC-721 interface while permanently reverting `transferFrom`. Self-contradictory under §5.2's "transfers and approvals" gate.

**The contract is entirely undocumented:** zero hits in `docs/INTERFACE_CONTRACT.md`, `docs/SPEC.md`, `PRODUCTION_GAPS.md`, or `docs/DOCUMENT_STATUS.yaml`. Every honest `isERC8004Conformant() == false` reference in those docs governs only the older `IntegrityIdentityReadV1` (`:47-49`, correctly `false`). The new contract arrived via `41385d6` carrying an unqualified conformance claim that no INTERFACE_CONTRACT row covers.

**One correction in the spec's favour:** §5.1 tags revision pinning `[PLANNED]`, but a draft revision **is** pinned — `ethereum/ERCs@503591a6e80e6e1affdd6403341e25269141f046`, in both the contract comment (`:36`) and `INTERFACE_CONTRACT.md:521`. No content hash accompanies it, so §5.1 is `[PARTIAL]`, not `[PLANNED]`.

### 7.4 Identity contracts are not on Base Sepolia `[UNVERIFIED]` — confirmed, Gate 5

Neither `IntegrityIdentityReadV1` nor `IntegrityERC8004Registry` appears in `deployments.baseSepolia.json` or any `broadcast/*/84532/` artifact. `IntegrityIdentityReadV1` appears only in `deployments.local.json:30` (anvil 31337). §12's claim stands.

Additionally: **`Deploy.s.sol` has no `84532` broadcast directory at all** — the genesis Base Sepolia deploy left no local broadcast artifact. This is §10's "a deployment file is a claim until independent readback verifies it," in the concrete.

### 7.5 Cross-platform identity commits — confirmed, but split across branches

- `41385d6` (2026-09-10) "complete cross-platform identity and policy loop" — 21 files, +1029/-5. Added `IntegrityERC8004Registry.sol` (+224) and its test (+174), oracle `handlers.rs` (+262), a memory-profiles migration, `bcc.py`, dashboard nav/e2e, Shield policy-publisher systemd units. **On `origin/main`.**
- `5ba7238` (2026-09-11) "harden cross-platform identity registration" — 10 files, +223/-35. `RegisterAgentModal.tsx` (+170), chain-bytecode sync script, `deployments.baseSepolia.json`. **Only on `origin/docs/rescope-registry-precheck-gas` — not on main.**

The hardening half of the cross-platform identity work is not on `main`. Worth a deliberate decision rather than leaving it branch-resident.

### 7.6 Hygiene — clean on secrets, loose on artifacts

Branch `docs/rescope-registry-precheck-gas` is **in sync** with its remote. Nothing staged.

**No secret exposure found.** Only `*.env.example` files are tracked; the real `contracts/.env` exists on disk and is correctly ignored (`.gitignore:2`). `register_shield_with_funder.sh` contains no inline key — it reads via `read -r -s` (`:40`) and unsets on exit (`:36`). `fund-deployment-wallet.html` contains no key literal.

Untracked: `contracts/fund-deployment-wallet.html`, `docs/SPEC-v2.0.0-proposed.md`, `docs/runbooks/shield-registration-handoff-2026-09-11.md`, `scripts/register_shield_with_funder.sh`, and this audit.

**`docs/SPEC-v2.0.0-proposed.md` being untracked is itself a finding.** It is the document meant to organize the project going forward; it currently exists only in one working tree, with no history and no backup.

### 7.7 Document authority — correct, but stale

`docs/DOCUMENT_STATUS.yaml` (`updated: 2026-08-29`) says normative = `docs/SPEC.md` v1.0.0-draft, whitepaper = `docs/WHITEPAPER.md` v3.2 `authority: informative`. This **agrees with CLAUDE.md exactly** — no drift, which is a genuinely good result given CLAUDE.md's own warning that this has drifted before.

It does not mention `SPEC-v2.0.0-proposed.md`, which is correct-by-design per §1 (it should not appear there until accepted). The `updated:` date is two weeks behind current work.

---

## 8. What to do, in order

Gate numbering follows `SPEC-v2.0.0-proposed.md` §11.

### Immediate — do before the next registration attempt

1. **Do not rerun `register_shield_with_funder.sh` as written.** Fixing `MINTER_ROLE` would produce a successful-looking registration of `b3324032…`, a DID Shield does not use (F2). Since §2.1 shows neither Shield DID is registered, there is no history to preserve: **repoint the registration at `2ea17967…`** — the DID Shield's runtime actually loads — and archive the orphaned `b3324032…` contracts.
2. **Fix `did.py` (F1).** It is currently capable of destroying any agent's key on an ordinary restart. Fail closed; never overwrite an existing `private_key.pem`.
3. **Back up the identity key material off-machine, now — carefully.** Every protocol identity you have is a single unreplicated file. Do **not** `cp -r` the whole tree: `~/.integrity/did/xibalba-shield/` contains a root-owned `registration_progress.json` and a 2.3 MB `export_spool.db`, so a naive recursive copy as `xibalba` partially fails — and a partial copy restored later is precisely the F1 trigger documented above. Instead:
   - copy each `private_key.pem` **together with its `document.json`** as a pair, from `~/.integrity/did/*/` and `~/.integrity-cli/identity/*.pem`;
   - include `~/.integrity/wallet/*/keystore.json` — the EVM key is the second independent loss path (§5.5), and losing it orphans the controller even if the Ed25519 key survives;
   - verify each restored pair re-derives its recorded DID before trusting it;
   - **never restore a key without its document** — that is exactly the F1 case that destroys the key on next load.
4. **Move `WALLET_PASSWORD.txt` out of the keystore directory** (§5.5).
5. **Track `docs/SPEC-v2.0.0-proposed.md` in git.** It is the organizing document and it exists in exactly one place.

### Gate 1 — identity boundary (the real blocker)

6. Unify the SDK and CLI identity stores, or make one authoritative and the other a reader (F2).
7. Add `chain_id` to `primitives.json` / `registration_progress.json`; refuse cross-chain cache reads (F3).
8. Fix Shield's systemd identity path — `User=xibalba-shield` with a nonexistent home and `ProtectHome=read-only` (§5.1).
9. Correct the `exporter.py:83-84` "one identity per device/deployment" comment and the per-device `agent_label` column (§5.2, §5.4).
10. Reconcile the three conflicting Shield registration records; archive, do not delete.

### Gate 2 — kernel

11. Hoist the `didHash` call at `XibalbaAgentRegistry.t.sol:115` so the zero-controller regression actually asserts (§7.2).
12. Strike §6.3's fixture-failure paragraph and correct the two §12 rows — the defect does not exist (§7.1).

### Gate 3 — Cortex

13. Fix the `candidate` default / missing promotion path — 99.86% of memory is unrecallable (§6.1). Highest day-to-day impact of anything in this audit.
14. Resolve the two-store split-brain with one profile-resolution rule.
15. Make scope checks unconditional rather than dependent on a non-None principal (§6.3) — today they no-op on stdio.

### Gate 4 — cross-repository

16. Either document `IntegrityERC8004Registry` in `INTERFACE_CONTRACT.md` with an honest conformance status, or change `isERC8004Conformant()` to stop asserting a constant `true` (§7.3).
17. Resolve the ERC-721-interface-plus-reverting-transfer contradiction.

### Housekeeping

18. Merge or rebase Shield's diverged `main`; `packaging/systemd/shield.env.example` is the conflict candidate (§5.6).
19. Decide on Shield's uncommitted `8421`→`8765` port change.
20. Land `5ba7238` on `main` or consciously park it (§7.5).
21. Refresh `docs/DOCUMENT_STATUS.yaml`'s `updated:` date.

---

## 9. Corrections to the proposed spec

Three §12 ledger rows and one §5.1 tag are wrong about current source. Correct them before the acceptance review, or the review inherits false premises:

| Location | Says | Actually |
|---|---|---|
| §6.3 "Current audit finding" | Focused fixtures fail in setup with `Unauthorized(...)` | 121 + 7 + 26 tests pass. Misread negative assertions. **Strike.** |
| §12 `IntegrityKernel` row | "focused fixtures currently fail in setup" | Passing |
| §12 `IntegrityAccount` row | "focused suite currently fails in setup" | Passing |
| §5.1 revision pinning | `[PLANNED]` | `[PARTIAL]` — revision `503591a6…` is pinned; only the content hash is missing |

Two things the spec does **not** record and should:

- `test_registerPrimitivesRejectsZeroController` does not assert (§7.2) — the one real red test in the repo.
- `isERC8004Conformant()` is a hardcoded `true` in an undocumented contract (§7.3). §5.1 forbids using it as evidence but does not say it is a constant.

---

## 10. Remediation completed in this session — 2026-09-12

Work done after the audit above, in the same session. Every item is committed and pushed.

### 10.1 Browser authentication moved to HttpOnly cookies over TLS

Both products held the operator session as a bearer token in `sessionStorage` and sent it on every request, so any XSS could read and exfiltrate it — and operators pasted tokens by hand.

| | Before | After |
|---|---|---|
| Credential | bearer token in `sessionStorage` | `HttpOnly; Secure; SameSite=Strict` cookie |
| Raw token in response body | yes | no |
| Readable from JavaScript | yes | no |
| Manual token entry in UI | Cortex "Use bearer token instead"; Shield "Advanced access" | removed from both |
| TLS | `tls internal` commented out in both Caddyfiles | enabled by default |

`SameSite=Strict` is what makes this safe without a separate CSRF token. Caddy serves the UI and API on one origin, so no CORS-credentials handling was needed. `XIBALBA_CORTEX_INSECURE_COOKIES=1` / `SHIELD_INSECURE_COOKIES=1` drop `Secure` for a plain-HTTP loopback dev server.

**Also fixed — authentication bypass (Cortex):** `local_api.py`'s `_authenticate` accepted the literal token `"dev"` unconditionally, returning a principal with whatever scope the route requested. Not gated by environment. Nothing referenced it. Removed, with a regression test.

**Also fixed — Shield sign-out:** gated its server call on a token the browser no longer holds, so it would never have revoked the session or cleared the cookie.

**Verified end to end** against a live server (throwaway profile, plain HTTP): unauthenticated → `401`; `Bearer dev` → `401`; signup → cookie set `HttpOnly`, **no token in the body**; cookie alone → `200`; after logout → `401`.

`[UNVERIFIED]` **The TLS + browser path was not exercised.** `caddy` is not installed on this machine, so `tls internal` plus a `Secure` cookie in a real browser is untested — and a `Secure` cookie on a plain-HTTP origin is silently dropped, which is exactly where this fails. Install Caddy and confirm sign-in through `https://127.0.0.1:8443` (Cortex) and `:8444` (Shield) before calling this done.

### 10.2 Device agents moved to signed short-lived assertions

`device_token` was a long-lived bearer secret minted at enrollment, resident on every protected endpoint, non-expiring and replayable. Shield's device agents now sign a per-request assertion with the Ed25519 key they already hold (`shield/device_assertion.py`).

Not mTLS: that needs a CA, distribution, renewal, and proxy passthrough this deployment lacks, while the device already signs BCC records through `integrity-sdk`. The assertion is a **distinct namespaced record type**, not a BCC commitment, so the frozen shape in `INTERFACE_CONTRACT.md` is untouched.

Key substitution is blocked the way BCC blocks it: the enrolled `integrity_agent_id` is `did:integrity:sha256(pubkey)`, so the verifier re-derives the fingerprint from the supplied key and requires a match **before** verifying the signature. Assertions bind an audience, expire in 120 s, and are nonce-guarded. Tests cover substitution, replay, expiry, audience confusion, tampering, and unregistered devices.

Migration is additive — `device_token` still works, and a device with no key on disk falls back — so nothing in the fleet breaks. **Relevant to F1:** the key is loaded read-only and never through `load_or_create_did()`, which would destroy the registered identity on a bad `document.json`.

### 10.3 Cortex stdio now binds a principal (Gate 3)

§6.3's finding, closed. stdio has no HTTP layer, so no middleware ran and `current_principal()` was always None — which short-circuits every agent-scope check in `server.py`. The checks existed but enforced nothing on the transport local harnesses actually use.

The server now derives a principal from `XIBALBA_AGENT_ID` at startup and **fails closed** when unset, with `XIBALBA_CORTEX_ALLOW_UNSCOPED_STDIO=1` as a deliberate, visible escape hatch.

This does not claim to *authenticate* a local subprocess — it runs as the same user and can read the store directly. It prevents accidental cross-agent access, which is the actual failure mode.

**Launcher audit — one gap found and fixed.** Failing closed only works if every launcher supplies the identity, and checking the *running* processes is not the same as checking the *launch config*. Every MCP server definition was audited:

| Launcher | `XIBALBA_AGENT_ID` |
|---|---|
| `~/.hermes/config.yaml` | `did:integrity:68fed133…` |
| Hermes `xibalba-cortex-worker` profile | `xibalba.extraction-worker` |
| Hermes `xibalba-quant` profile | `did:integrity:7d0ecae5…` |
| `~/.codex/config.toml` | `xibalba.agent` |
| `~/.claude.json` | **was missing — added as `xibalba.agent`** |

Claude Code's definition set only `XIBALBA_CORTEX_HOME`, so this change would have hard-failed its Cortex MCP server on next start and removed all memory tooling. Fixed in `~/.claude.json` (backup: `.claude.json.bak-pre-stdio-agent-id-20260912`). Verified both directions against the real entrypoint: it starts cleanly with the variable set, and exits with the guard message without it.

`[UNVERIFIED]` **Post-restart retrieval behavior.** Binding a principal means `_bound_agent_id` now raises `PermissionError` when a tool passes an `agent_id` that differs from the launch identity — previously that call succeeded. No adapter was audited for passing an explicit `agent_id`, and no stdio call has been made under the new principal. Confirm memory retrieval still behaves as expected after the next harness restart, and check the runtime adapters for explicit `agent_id` arguments.

### 10.4 Not migrated, with reasons

- **Cortex streamable-HTTP MCP transport** — still bearer. Nothing runs it: port 8420 is the local API, 8421 is shield-backend, and every Cortex MCP process is stdio. Migrating it would be speculative code with no consumer. It is the documented path for a future cloud-hosted agent; migrate it when one exists.
- **Refusing `device_token` outright** — deliberately deferred. Step 4 of the migration, and only safe once no enrolled device needs it. Given §3's three mutually inconsistent registration records, this fleet's state is not clean enough for a flag day.

### 10.5 Repository hygiene closed

- Shield `main` merged (the predicted `shield.env.example` conflict did **not** exist — the remote side never touched that file) and pushed; a second divergence appeared mid-session from another session and was merged too.
- **Port bug found and fixed:** the backend binds `8765` (`api.py:1695`), but the UI default, the Vite dev proxy, **and the packaged Caddyfile** all pointed at `8421`. Any deployment using the packaged Caddyfile reached a closed port. The uncommitted change in the worktree was a partial fix; the Caddyfile was still wrong.
- Cortex's in-progress wordmark work committed separately from the auth change.

### 10.6 Test evidence

| Suite | Result |
|---|---|
| Cortex, full | pass (3 chunks, all exit 0) |
| Shield backend | 35 passed |
| Shield device assertions | 9 passed |
| Shield enroll + CLI + chaos/adversarial | 40 passed |
| Shield chunk 1 (24 files) | 214 passed, 9 skipped |
| Shield remaining | 71 passed across 4 groups |
| Cortex + Shield viewer builds | both clean |

`[UNVERIFIED]` `tests/test_slm_backend.py` was never run — it loads GGUF model weights and OOMs a 5 GB machine. Unrelated to these changes, but not covered.

**Note on test hygiene:** `test_runtime_status.py` was reading the developer's **real** `~/.integrity/did/xibalba-shield/private_key.pem`. It now pins `INTEGRITY_DID_HOME` to a temp directory. Other suites may have the same leak and are worth a sweep.
