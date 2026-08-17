# Handoff — 2026-08-17 (whitepaper v3.2, AIS scoring defect, registration root-caused)

Cross-repo session. **Nothing was committed** — all changes are uncommitted working-tree edits.
Every claim below was verified directly (tests run, chain reads, PDFs parsed), not inferred.

## 0. If you take away nothing else

- **AIS has a live scoring vulnerability. This is the highest-value open item and it is ~6 lines.**
  `integrity-oracle/backend/src/derive.rs`: `derive_entropy` and `derive_grounding` return **1.0
  (maximum)** when no values are present, and `self_reported_compliance` returns 1.0 for an empty
  batch. Missing data therefore reads as *perfect*. Only `derive_sacrifice` fails closed. Verified
  numerically: a submission carrying token counts but **no analysable content** scores
  r = **0.923** at 100 claimed GPU-hours, while an honest agent with real-but-mediocre telemetry
  scores **0.465** — the content-free agent outscores the honest one roughly two-to-one. Fix:
  return 0 on absent evidence. Independently valuable regardless of any v3 work.
- **Compliance is self-reported for every non-healthcare agent.** `handlers.rs`'s
  `oracle_compliance` falls back to `derive::self_reported_compliance` in six paths, including
  `compliance_vertical != 1`. Only a live healthcare BAA read can override it downward. The
  agent tells the oracle whether it violated policy.
- **Registration was root-caused and is no longer a mystery.** `REGISTRAR_ROLE` on
  `XibalbaAgentRegistry` had been granted **only to an `AgentPrimitivesFactory` address with zero
  deployed bytecode** since 2026-08-13. A prior rotation's `CREATE` never broadcast (only 3 of 22
  txs in `broadcast/RotateOperatorKeyGrant.s.sol/84532/run-latest.json` have real hashes;
  `receipts: []`), but `deployments.baseSepolia.json` was updated with the predicted address
  anyway, and a later manual `cast send` granted the role to that phantom address while revoking
  it from the real factory. A call to a codeless address trivially "succeeds" with empty return
  data — which is exactly the `status: 1`, ~29k-gas, zero-log symptom every attempt produced.
  **Fixed:** deployments files repointed to the real factory `0xC19fc9cB2cB87297EfDF11DA7e211e44A6C1181D`
  and `REGISTRAR_ROLE` re-granted (verified `hasRole == true`). One registration retry away from done.
- **Lesson now encoded in `docs/demo-shield-integration.md`:** never write a deployed-contract
  address to a deployments file or grant it a role without first confirming `eth_getCode` returns
  real bytecode.
- **`.env` key naming is actively misleading.** `FUNDER_PRIVATE_KEY` and `DEPLOYER_PRIVATE_KEY`
  are the **public Anvil test key** (`0xf39Fd6e5…`), useless on Base Sepolia. The key controlling
  the funded `funderWallet` (`0x7530bd7C…`) is `ORACLE_SIGNER_PRIVATE_KEY`. Use that one.

## 1. What was produced

| Artefact | Notes |
|---|---|
| `spec/integrity-protocol-v3.2.md` | 1,646 lines. Markdown+LaTeX, 13 mermaid diagrams, 13 "In plain terms" on-ramps, Appendix D change register. Non-normative; proposes changes for `v0.5-proposed`. |
| `spec/Integrity_Protocol_Whitepaper_v3.2.pdf` | 64pp. Built markdown → HTML (`marked` + `mermaid@11` + KaTeX) → headless chromium print. **No LaTeX/pandoc on this machine.** Chromium is snap-confined and cannot write to or serve from `/tmp` — stage under `$HOME`. |
| `docs/demo-shield-integration.md` | Shield↔integrity-core bring-up runbook, incl. the funder-key trap above. |
| `docs/signer-role-rotation-2026-08.md` | Operator-side steps for the 2-of-3 Safe + distinct EOAs. |
| `PRODUCTION_GAPS.md` | New dated entries: registration root cause, nonce race, RPC read-after-write lag. |

## 2. Substantive spec decisions (don't silently reverse these)

- **AIS redefined** as a *gated* weighted geometric mean over *admissible* evidence (§3.1.1):
  requirements N1–N5, an evidence-admissibility rule (unverifiable assertion scores 0),
  per-component floors enforced by a conjunctive Θ gate reusing the kernel's own constraint form,
  and `r(ι)` normalised from the **pre-boost** score clamped to [0,1]. A bare geometric mean does
  **not** prevent compensation — only exact zero collapses it, and a 90%-violation agent still
  reached r = 0.631. §3.1.4 is a 6-row implementation-delta table; the code does not satisfy it yet.
- **Identity: bridge, not adopt.** Keep `XibalbaAgentRegistry` as substrate; expose a read-only
  ERC-8004-shaped adapter for external legibility. AIS stays the single authoritative `r(ι)` —
  running two reputation systems would reintroduce the commensurability failure §1.2 diagnoses.
  Convergence deferred with explicit revisit triggers.
- **Shield is Untrusted tier** (§9.4), deliberately not part of the guarantee, with a stated
  four-condition path to graduate (hardware root of trust, on-chain remote attestation,
  freshness-with-expiry, honest sensor coverage).
- **Three v3.2 amendments implemented differently from the source register**, each because
  verbatim transcription contradicted an existing section: ZK-telemetry → research horizon, not a
  roadmap phase; hybrid TEE → joint coverage, not "complete mediation achieved"; grace modes →
  operate strictly inside AIS floors. Appendix D records each with reasoning.
- **Cortex corrected the spec, not the reverse:** v3.0's Eq. 5 used naive `∥` concatenation while
  §4.4 warns that construction is an attack surface; Cortex already used an injective encoding.

## 3. Open items, priority order

1. **`derive.rs` items 1–2** — invert the fail-open defaults (§3.1.4 rows 1–2). ~6 lines.
2. **Cortex Merkle malleability** — `events.py`'s `merkle_parent` sorts the pair before hashing and
   promotes odd nodes with no leaf/internal domain tag (CVE-2012-2459 shape). Anchored roots are
   safe (root = chain head); impact is limited to inclusion evidence via `session_merkle_evidence`,
   which calls the **un-domained** `merkle_proof`. Fix before that evidence is used in a dispute.
3. **Registration retry** — stack is up, fix is in, one run to confirm end-to-end.
4. **Doc alignment** — `CLAUDE.md` architecture map, `docs/INTERFACE_CONTRACT.md` (planned v3
   schemas), cortex/shield cross-repo notes. README already has a marked-planned v3 section.
5. **Signer-role rotation** — blocked on operator: needs the 2-of-3 Safe address plus three new
   EOA addresses (see `docs/signer-role-rotation-2026-08.md`). Then adapt
   `RotateOperatorKeyGrant.s.sol` and hand back a `forge script --broadcast` command.
6. **Orphaned testnet contracts** — at least four `SovereignAgent`/`StateAnchor` pairs from failed
   registration attempts against the phantom factory. Real gas spent, no cleanup path. Listed in
   `PRODUCTION_GAPS.md`.

## 4. Caveats

- **Nothing is committed.** Working tree only, across `integrity-core`, `xibalba-shield`
  (`shield/cli.py` device-config fix), and `integrity-sdk` (`chain.py` nonce/read retries).
- `integrity-sdk` suite is green at **259 passed / 3 skipped** after fixing a stale
  `.venv/bin/pytest` shebang carrying the pre-rename path. The README's old "242 passed, 2 failed"
  was unreproducible.
- The docker-compose `mvp` service was removed — it pointed at the deleted `integrity-mvp` repo and
  broke `docker compose up` entirely.
- `DOCKER_RPC_URL` switched to `https://sepolia.base.org`; the previous third-party endpoint was
  responsible for a nonce race and stale role reads.

---

# Handoff — 2026-08-12 (ecosystem stabilization + dual rename: xibalba-graph-memory → xibalba-cortex, INTEGRITY-LATEST → integrity-core)

Cross-repo session covering `integrity-core` (this repo), `xibalba-shield`, and `xibalba-cortex`.
All three repos are clean, tested, fully committed, and fully pushed as of this writing. Nothing
below is inferred — every claim was verified directly (test suites run, files read, git history
checked) during the session.

## 0. If you take away nothing else

- Old names are gone. `INTEGRITY-LATEST` and `xibalba-graph-memory` no longer exist as
  directories or GitHub repos — they are `integrity-core` and `xibalba-cortex` now (old GitHub
  URLs redirect). Don't reintroduce the old names anywhere.
- **Shield currently has NO path to a signed BCC commitment.** The `shield/integrity_exporter`
  module (real signing + submission to `bcc_middleware`) was removed and replaced with plain
  OTel spans that nothing on the `bcc_middleware` side ingests. Tracked in
  `xibalba-shield/IMPLEMENTATION_PLAN.md`'s "Known gap — 2026-08-12" section. This is a real
  regression from previously-working behavior, not a planned-but-unbuilt gap — treat it as
  higher priority than most open items below.
- **The real ZK verifier is live but untested.** `contracts/src/oracle/UltraPlonkVerifier.sol`
  is the actual `bb`-generated verifier now, not the placeholder — `forge build`/`forge test`
  both pass clean (195/195). But there is zero test coverage exercising it with a real proof.
  Tracked in `PRODUCTION_GAPS.md` #26.
- **This repo's own `CLAUDE.md` is stale on that exact point** — its "ZK proof pipeline"
  section still says `UltraPlonkVerifier.sol` "is an explicit placeholder that reverts... until
  replaced wholesale by `make generate-verifier`." That's no longer true. Not fixed this
  session (out of scope of the rename work); fix it before trusting that section again.

## 1. What actually happened, in order

1. **Full audit** of `xibalba-shield`, `xibalba-cortex` (then `xibalba-graph-memory`), and this
   repo (then `INTEGRITY-LATEST`) — git state, uncommitted work, dependency direction, what's
   real vs. documented-only.
2. **Stabilized all three repos' pre-existing uncommitted work** rather than renaming a broken
   tree:
   - `bcc_middleware/app/opa_client.py` had been accidentally deleted (unstaged) while
     `main.py` still imported it — `bcc_middleware` genuinely could not import. Restored
     byte-identical from git history.
   - `contracts/src/oracle/UltraPlonkVerifier.sol`'s dropped `IZkVerifier` conformance and the
     deleted `contracts/test/UltraPlonkVerifier.t.sol` / one test in
     `ReputationRegistry.t.sol` were initially suspected as damage — verified they're actually
     the correct, necessary consequence of swapping in the real `bb`-generated verifier (adding
     back `is IZkVerifier` reproduces a genuine Solidity diamond-conflict compile error;
     confirmed by reproducing then reverting). The removed tests only asserted placeholder-only
     behavior and are correctly gone, not restorable. See §0 for the resulting gap.
   - `xibalba-cortex`'s `store.py` had drifted its event-schema constant from
     `"xibalba.memory.event.v1"` to `"xibalba.memory_event.v1"` in the same uncommitted diff
     that delegated hashing to `integrity_sdk.crypto.merkle.compute_node_hash`. Since
     `verify_chain()` recomputes every stored event's hash using the *current* schema constant,
     this would have made all 366 real memories in the live
     `~/.hermes/xibalba-cortex/graph-memory.sqlite3` fail chain verification with a false
     "corrupted" result. Reverted just the schema string; verified all sampled chains valid
     against the real store afterward.
   - `xibalba-shield`'s uncommitted `integrity_exporter` → OTel + in-process rules → real-OPA
     refactor was mostly done but left stray references to the deleted module in scripts,
     dead test scaffolding (`_RecordingExporter` classes, unused after a `fix_tests.py` scratch
     script had already run once), and zero test coverage for the new span-based telemetry path
     in `agent_core/router.py`. Cleaned up; added 2 new tests (success + tracer-failure paths).
   - **Found a real structural bug in this repo**: `integrity-dashboard/` had its own separate,
     live `.git` (a real, unregistered clone of `integrity-mvp`, not a submodule), while this
     outer repo separately tracked a *stale, directly-committed snapshot* of the same path from
     2026-08-04 — silently diverged for over a week. Confirmed with the user this was leftover
     from the `integrity-mvp`-into-`integrity-core` migration, not the intended state. Removed
     the nested `.git`, reconciled the outer repo to `integrity-mvp`'s actual current state
     (249 files: old single-page panel UI → new routed multi-page app with real
     `shieldBackend.ts`/`graphMemory.ts`/`bccMiddleware.ts` integration clients). One file
     (`gas_usage.jsonl`, an append-only ledger) had disappeared with no successor in that
     diff — restored from its last known state rather than silently dropped.
   - Removed `integrity-dashboard/demo/src/integrity_demo/framework/` (19MB, ~788 files) — an
     unreferenced directory closely mirroring `~/.hermes/hermes-agent`'s own
     skills/hermes_cli/acp_registry layout, sitting unused in a **public** repo
     (`integrity-mvp`) since before this session. Confirmed zero imports from it anywhere in
     the demo package before removing.
3. **Renamed `xibalba-graph-memory` → `xibalba-cortex`** end-to-end: GitHub repo, local folder,
   Python package (`xibalba_graph` → `xibalba_cortex`), env vars (`XIBALBA_GRAPH_MEMORY_*` →
   `XIBALBA_CORTEX_*`), console scripts, MCP server registration name, default state-directory
   paths, the live `~/.hermes/xibalba-graph-memory` state dir → `~/.hermes/xibalba-cortex`
   (366 real memories moved intact, verified), `~/.hermes/config.yaml`, the Hermes plugin
   directory + hardcoded bridge paths, `~/.hermes/cron/jobs.json`, `~/.claude.json`'s
   project/mcpServers/githubRepoPaths entries (backed up first — see `~/.claude.json.bak-*`).
4. **Renamed `INTEGRITY-LATEST` → `integrity-core`** end-to-end, same pattern: GitHub repo
   (`integrity-protocol` was considered and rejected — collides with an existing archived
   private repo in the org), local folder, `contracts/foundry.toml`'s CI-runner path,
   `integrity-dashboard/scripts/copy_shield.cjs`, CI workflows (`e2e.yml`/`wiki-sync.yml` —
   including renaming the required PAT secret `INTEGRITY_LATEST_PAT` → `INTEGRITY_CORE_PAT`,
   **which does not exist yet** — user is handling secret creation separately),
   `wiki-data.json` regenerated via its own sync script (not hand-edited), both sibling repos'
   (`xibalba-shield`, `xibalba-cortex`) dependency paths, `~/.hermes/config.yaml`'s
   `pre_tool_call` hook path, `~/.claude.json` entries, workspace-level
   `/home/xibalba/Projects/CLAUDE.md`.
5. Discovered mid-rename that the branch being worked on (`audit/harness-loop-2026-07-30`) had
   **already been merged into `main` via PR #50 on 2026-08-07** — local `main` was just stale
   (87 commits behind), not genuinely diverged. All new work this session is additional commits
   on top of that already-merged branch, pushed to its own remote ref, **not yet landed into
   `main` via a fresh PR/fast-forward**.

## 2. Verification performed (all passing except where noted)

| Package | Result |
|---|---|
| `contracts` | `forge build` clean, `forge test`: 195/195 |
| `integrity-sdk` | 262 passed, 2 skipped |
| `integrity-cli` | 68 passed, 1 skipped |
| `bcc_middleware` | 121 passed |
| `integrity-oracle` (Rust) | 130 passed (119 backend + 11 scoring-core) |
| `integrity-userapi` | **not verified** — needs local Postgres on `:5435`, not running in this environment |
| `integrity-dashboard` | `tsc -b && vite build` clean; `eslint .` 0 errors (54 pre-existing unused-var warnings untouched); `playwright test` (`test-e2e`) 20/26 — the 6 failures are `health.spec.ts`/`shield.spec.ts` tests needing a live oracle/bcc_middleware stack that wasn't running, not code bugs |
| `xibalba-shield` | 99 passed, 6 skipped |
| `xibalba-cortex` | 108 passed, 1 skipped |

## 3. Open items, in rough priority order

1. **Shield's BCC-signing gap (§0)** — needs a real design decision: does Shield call
   `integrity_sdk.bcc.build_bcc_commitment` directly again, or does `bcc_middleware` grow a
   real OTLP ingestion endpoint that converts incoming spans to signed commitments? Not started.
2. **Create `INTEGRITY_CORE_PAT`** GitHub secret on `integrity-mvp`'s repo settings (fine-grained
   PAT, read-only Contents access to `XibalbaTechSol/integrity-core`) — user is handling this.
3. **Land `audit/harness-loop-2026-07-30` into `main`** — it's pushed to its own remote ref but
   not yet merged/fast-forwarded into `main` via a fresh PR.
4. **Write real ZK verifier tests** (§0) — feed `UltraPlonkVerifier.sol` an actual proof from
   `integrity-zkp`'s pipeline, confirm valid proofs verify and invalid ones don't.
5. **Fix this repo's own stale `CLAUDE.md`** (§0's third bullet) and do a broader documentation
   accuracy pass — requested by the user at session end, scoped to README/SPECIFICATION/
   IMPLEMENTATION_PLAN/`docs/INTERFACE_CONTRACT.md`/`PRODUCTION_GAPS.md` plus the full
   `docs/wiki/` tree across all three repos, explicitly **not** yet started (survey agents were
   launched, one early finding was `docs/wiki/WIKI_LOG.md` is 6 days stale, then stopped
   without applying fixes so the session could wrap cleanly). Pick this up fresh.
6. **Phase 3 verification from the original plan, not done**: confirm Shield's DID registration
   actually round-trips against `integrity-core`'s oracle for real (not just that scripts
   import); confirm whether `xibalba-cortex`'s `anchor_session_root()` has a live receiver
   configured anywhere on the `integrity-core` side — as of this session, confirmed **no**' —
   `XIBALBA_ANCHOR_URL` is documented as something the operator must configure themselves
   (`xibalba-cortex` commit `572f581`), not something this repo currently serves.
7. **Phase 4 cleanup, not done**: `/home/xibalba/Projects/INTEGRITY/xibalba-shield` (a stale,
   unrelated Next.js prototype from the legacy `INTEGRITY` tree) still exists; `/home/xibalba/
   Projects/integrity-mvp/integrity-mvp_ARCHIVED/` is still in that confusing nested-folder
   shape (it's the live standalone `integrity-mvp` repo, not actually archived).
8. **Consider purging `demo/framework/`'s git history** if its prior public exposure on GitHub
   matters — removed from the working tree this session, but old commits (back to `94e226a`)
   still contain it in history/GitHub's cache unless separately purged. Not done, not requested.

## 4. Do not

- Don't restart the `hermes mcp serve` processes forcibly. They are children of *running Claude
  Code sessions* (confirmed via process ancestry — parent is a `claude` process), not a
  standalone daemon; killing one breaks that session's live tool access with no warning to
  whoever's using it. Each session picks up the renamed MCP config naturally on its own next
  restart.
- Don't assume `integrity-dashboard/` is a git submodule — it deliberately isn't (see §1.2); it's
  a plain tracked directory in this repo now, matching the intended
  `integrity-mvp`-migrated-into-`integrity-core` architecture.
- Don't treat GitHub's Dependabot warning (94 vulnerabilities: 2 critical, 53 high, 36 moderate,
  3 low, surfaced on every push this session) as something this session addressed — it wasn't
  investigated at all, just observed.

---

# Handoff — 2026-07-31 (recovery session; shell restored, stack green)

Supersedes the previous handoff of the same date, which was written with **no shell**
and whose headline finding did not survive testing. Nothing below is inferred — every
claim was executed.

## 0. The disk is fine. Delete this worry.

The reboot cleared it.

| Check | Result |
|---|---|
| `/sys/fs/ext4/sdc2/errors_count` | **0** |
| `findmnt -no OPTIONS /` | `rw,noatime,errors=remount-ro` — `emergency_ro` **gone** |
| write to `/tmp` | succeeds |

**`~/fix-root-fs.sh` was not needed and was not run.** The two ext4 errors were a single
incident on 2026-07-30, not ongoing degradation.

One piece of collateral damage remains, and it is **not blocking**: containerd's content
store lost a blob (`sha256:dc009236…`), so `docker images` and `docker system df` fail.
All four project images inspect fine, `docker compose` works normally, and the stack
builds and runs. Full repair needs `sudo ctr -n moby …`, which this session could not run
non-interactively. **Do not `docker system prune -a`** — `integrity-core_pgdata` holds
the oracle's telemetry, i.e. the dogfooding record.

## 1. The previous handoff's headline finding was wrong

It reported *"every `/v1` route returns 500 — the oracle's entire functional surface is
down."* Re-measured against a live stack:

| Route | Then (browser) | Now (measured) |
|---|---|---|
| `/v1/agents` | 500 | **200** (1448 b) |
| `/v1/leaderboard` | 500 | **200** (797 b) |
| `/v1/markets` | 500 | **200** (437 b) |
| `/v1/agent/{live-did}` | 500 | **200** |

The oracle's boot log is clean and contains **zero** sqlx/pool/decode/panic errors in its
entire history. Both suspects it named were wrong: Postgres/Redis are ruled out by that
same log, and the uncommitted `db.rs` query is type-safe (migration 0011 declares
`tier_granted INTEGER`) and demonstrably *works* — `xibalba.integrity` now correctly
reports `verification_tier: 2` instead of the registration floor of 1.

Also withdrawn: the `resolveDID` reverts that filled the log are **correct 404s**, not the
outage. `0x4c2a24b3` is `UnknownDID()`, and `error.rs:66` maps `AgentNotFound` → 404. They
are logged at `ERROR`, which is what made a working service look catastrophic.

**What the 500s actually were is not established.** The container that served them was
replaced before a shell existed to inspect it. The honest statement is that the evidence
was destroyed, not that the problem was solved.

## 2. What was actually broken (and is now fixed)

### The protocol was not anchoring its own evidence — for days, silently

`bcc-middleware` signed every transaction for **chain 31337 while connected to Base
Sepolia (84532)**, so every `anchorRoot` and `updateScore` was rejected:

```
could not anchor 8 leaves for agent did:integrity:68fed1… -- retained in logs only
```

Root cause: `app/config.py:37` reads `CHAIN_ID` (default `31337`), and **`bcc-middleware`
was the one service in `docker-compose.yml` that took `RPC_URL` from env without taking
`CHAIN_ID` from the same place.** A second bug sat behind it — `DEPLOYMENTS_FILE` was
hardcoded to `/deployments.local.json`, so even with the right chain it would have used
anvil addresses on Sepolia. **Both fixed; both were required.**

**Verified by on-chain state change, not by absence of errors:**

| Evidence | Result |
|---|---|
| `anchor_events` rows for this DID | **4**, distinct root + tx_hash each |
| newest `anchor_events.root` vs chain `latestRoot` | **identical** (`0x87bfba4278fd8c4a…`) |
| `cast receipt <tx>` | **`status 1 (success)`** |
| `isAnchoredRoot(old root)` — append-only holds | **`true`** |
| `scores(0x360e…).lastUpdated` | **`1785484478`** (this session) |

A root present in **both** the oracle's `anchor_events` table and the contract's
`latestRoot`, backed by a receipt with `status 1`, means the whole path executed:
commitment → batch → Merkle root → signed `anchorRoot` → mined → recorded. Nonce
advancement (260 → 275) is corroborating only and deliberately not load-bearing — a
reverting tx consumes its nonce too.

Both roles were confirmed before wiring the key in, on **two different contracts**:
`ANCHOR_ROLE` on `StateAnchor` (for `anchorRoot`) and `ORACLE_ROLE` on
`ReputationRegistry` (for `updateScore`).

**This session's own evidence is anchored.** The 5 commits below each fired the vault
hook; `anchor_vault.py` was then run explicitly rather than trusting the SessionEnd spawn
(its own docstring records leaves being stranded when a hook is torn down mid-receipt):
`anchors.jsonl` advanced `leaves_through: 21 → 26`, root
`0xb64a41aac24e20fa…`, `isAnchoredRoot == true`, receipt `status 1`.

### `make test` could record a pass but never a failure

Every line read `cd pkg && pytest && cd .. && $(TEST_STATUS) pkg pass || $(TEST_STATUS) pkg fail`.
On failure, `&&` short-circuits so `cd ..` never runs and the recorder is exec'd from
inside the package dir, where it does not exist → crash. **The mechanism feeding test
outcomes into the anchored evidence chain could only ever write `pass`**, and the crash
aborted the target so later packages never ran at all.

Note the trap: fixing only the path makes `|| … fail` exit 0, so `make test` would report
**success on a red suite**. Fixed as `|| { $(TEST_STATUS) pkg fail; false; }` with
`$(CURDIR)`.

### The importer would have written a false lineage

The handoff flagged "file order == commit order" as unverified. It is **half right**:
timestamps *are* strictly monotonic, but chronological order is **not ancestry**. Of 20
consecutive pairs, 19 are real git ancestor pairs and one is not — `6c0c9bf → d7e4deb`
are siblings off merge-base `354c6b5` (branch switch). A linear chain would have asserted
a `derived_from` edge git says does not exist.

Fixed before the first real run: parents now resolve via `git merge-base --is-ancestor`.
Corrected import records `d7e4deb → 36e23d9b` and leaves `6c0c9bf` as the unmerged branch
tip it is.

### F5 is CONFIRMED — and it is a design bug

Predicted last session, now measured: **21/21 vault leaves are `unverified`**, 17 of them
specifically `unverified:stale`. Not one leaf in the entire history has ever recorded a
verified test result. No commit ordering fixes it — `HEAD ‖ diff` cannot be equal across
the commit boundary. The fix (key status to `git write-tree` / `HEAD^{tree}`) is now
unblocked, since the recorder bug above was its other half.

## 3. State of the tree

All previously-unrun code has now been executed:

| Item | State |
|---|---|
| `integrity-sdk/tests/test_memory_dag.py` | **21/21 pass** (first ever execution) |
| `integrity_sdk/memory_dag.py` | exercised by the above; no changes needed |
| `scripts/import_memory_dag.py` | **fixed** (ancestry), run for real, idempotent on re-run |
| memory DAG | **built** — 21 nodes, `root_of_heads = 0xdc4d6644c6ef5884…`, **not anchored** |
| `docker-compose.yml` | bcc chain fix + **5 healthchecks** added |
| `Makefile` | test-status recorder fixed |
| `bcc_middleware/tests/test_evidence_linkage.py` | de-flaked (was 1 pass / 3 fail) |

Test results this session: SDK **230 passed / 2 skipped** · bcc_middleware **99 passed** ·
OPA **37/37** · userapi **51 passed** · contracts **200** · zkp **4** · oracle **133**.

## 4. Read these

- `docs/design/e2e-audit-2026-07-31.md` — resolution pass at the top; new findings
  **E10–E16**; original text preserved with corrections marked in place.
- `PRODUCTION_GAPS.md` **§24** — the full record, including what stayed open.

## 5. Next, in order

1. ~~**Anchor the memory DAG.**~~ **DONE (2026-08-01).** New `scripts/anchor_memory_dag.py`
   — a companion to `import_memory_dag.py`, not the same path as `anchor_vault.py` (that
   script is hardcoded to the vault's own root). Verified on-chain: `isAnchoredRoot(DAG
   root) == true`, receipt `status 1`, `latestRoot` now the DAG root, and the vault's own
   root (`0x51451cc5…`) still independently anchored — append-only holds across both
   trees. Idempotent by construction (checks `isAnchoredRoot` before submitting).
2. ~~**Fix F5 at the root**~~ **DONE (2026-08-03).** `scripts/tree_hash.py` now hashes
   tracked-file content (`git ls-files`) instead of `HEAD ‖ diff HEAD`, so it's invariant
   across the exact commit boundary that broke it. Verified with a `--self-test` harness
   and live: commit `acdae8b` is the first leaf in the vault's history with a real
   `test_result_hash` instead of `unverified`. See `PRODUCTION_GAPS.md` §19/F5.
3. **Make audit reports survive shutdown** — `ensure_future(to_thread(...))` with nothing
   awaiting it drops in-flight reports on worker exit (audit E16). The test is fixed; the
   production drop is not.
4. **Make the primitives cache chain-aware** (E11) — `/v1/agent/{stale-did}` returns 200
   with `eip155:31337` anvil addresses from a Sepolia oracle. **Do not fix by deleting the
   5 stale rows.**
5. **Re-test the nonce race on a dedicated RPC** (E13) — still fails `nonce too low`
   despite `nonce_lock.py`; cannot separate stale-read from real race on publicnode.
6. Lower `resolveDID` not-found logging to `warn` (E12) — one line, and it manufactured an
   entire false audit.
7. **Make the dashboard image buildable** — `npm install` dies inside Docker with
   arborist's `Cannot read properties of null (reading 'edgesOut')`. This is why
   `make check-deploy` **currently exits 1** (see below). The dashboard's own suite passes
   on the host (20 files / 68 tests), so it is a container-build fault, not broken code.
8. `sudo ctr -n moby` cleanup for the containerd blob.

## 6. Running the stack

`bcc-middleware` needs a funded signer for Sepolia. The key is **not** committed:

```bash
cd ~/Projects/integrity-core
set -a; . ./contracts/.env; set +a
export ORACLE_SIGNER_PRIVATE_KEY="$FUNDER_PRIVATE_KEY"
docker compose up -d
docker compose ps          # postgres/redis/userapi-postgres/oracle/bcc should read (healthy)
```

Two harness gotchas that will otherwise cost you an hour:

- **`make test` needs `userapi-postgres` up.** The target does not start it, so a fresh
  checkout running `make test` alone fails `ConnectionRefusedError` on :5435 — which reads
  as a broken suite rather than a missing dependency.
- **`make check-deploy` currently exits 1, and that is expected.** It correctly reports
  the dashboard image STALE (2026-07-18 vs current source) and the image *cannot be
  rebuilt* until item 7 above is fixed. `oracle-backend`, `bcc-middleware`, and `userapi`
  all report **fresh**. Do not read the non-zero exit as new drift.
- **Trust only the `MAKE_TEST_EXIT=` line, not a wrapper's reported exit code.** A
  backgrounded `make test` was reported as "exit code 0" twice while the real exit was 2.
- If a `test_chain.py` run appears to hang, check for an orphaned `anvil`/`forge script`
  pair from a killed run (`pgrep -fa "forge script|anvil --port"`). It passes in ~3s
  standalone; a stuck pair blocks it indefinitely at ~1% CPU, which looks like compiling.

Architecture decision from last session stands: **two memory systems, deliberately
separate** — the Integrity hash graph (evidence, anchored, never forgets) and
`~/Projects/xibalba-memory/` (recall, mutable, forgets). Open question there — embedder
backend, Ollama vs in-container sentence-transformers — is now answerable with a shell but
blocks nothing.
