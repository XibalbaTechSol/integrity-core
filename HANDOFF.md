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
non-interactively. **Do not `docker system prune -a`** — `integrity-latest_pgdata` holds
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
cd ~/Projects/INTEGRITY-LATEST
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
