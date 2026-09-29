# Handoff: Gate A validation pass, after A6

**Date:** 2026-09-28 (superseded 2026-09-29 — see status update below)
**Repository:** `integrity-core`
**Authority:** [`docs/EXECUTION_PLAN.md`](EXECUTION_PLAN.md)
**Current status:** A6 complete; Gate A not passed. A full validation pass ran against all 10 open
items this session (superseding the same-day handoff written right after A6 merged). No
`EXECUTION_PLAN.md` checkboxes were ticked in this pass — nothing in the text below should be read
as the gate passing on its own. **Later passes the same day (integrity-core#132, #133, #134) ticked
9 of this handoff's 10 open items, leaving only Docs** — see the status update immediately below
before reading the rest of this document as current.

## Status update (2026-09-29)

Following this handoff's "Recommended next sequence": `xibalba-cortex#34`/`#35` and
`xibalba-shield#40` merged (all CI-green); the Cortex suite was re-run fresh against `origin/main`
in an isolated worktree (551 passed, 0 failed, 2 skipped, resolving the "1 commit behind" caveat
below); Shield's six sub-items were re-run fresh against `origin/main` in an isolated worktree
(98/98 pass); import hygiene was checked (`integrity-sdk`'s `test_import_hygiene.py` 15/15, plus a
grep sweep of Shield/Cortex/CLI/bcc_middleware/contracts for A1-cut modules, clean); both repos'
CI was confirmed pinning `integrity-core` to a full SHA as a sibling checkout, green post-merge;
the console build was re-run clean. **Gate A moved from 2/12 to 10/12** (`integrity-core#132`,
`STATUS.md` and `docs/EXECUTION_PLAN.md` updated with the evidence), **then to 11/12**
(`integrity-core#134`, this same day) once Identity was resolved. **Docs** (partial progress
2026-09-29: checked Shield's `PRODUCTION_READINESS_PLAN.md` (explicitly disclaims authority over
`SPECIFICATION.md` — fine), Cortex's `SPECIFICATION.md` / `spec/xibalba-cortex-v1.md` (a deliberate
two-tier entry-point/normative split, not a conflict — fine) and `PROJECT_STATE.md` (declares
itself "the single resume authority" but scoped to Cortex's own resume state, not competing with
protocol authority — fine, though its "Last verified: 2026-09-14" is 15 days stale and worth a
refresh), and found + fixed one real drift: the console's `integrity-dashboard/SPECIFICATION.md`,
`IMPLEMENTATION_PLAN.md`, and `README.md` still said this directory was "a component of
`integrity-core`, not a separate/fourth repository" — true when written, wrong since
`integrity-core`#A1 split it back out into its own repo on 2026-09-28 (fixed in
`integrity-console#5`). **Not yet done:** the item's full text asks that "every active normative
document has an identified authority" — this pass spot-checked for competing-plan/authority
conflicts specifically, not an exhaustive per-document authority audit across all four repos'
active docs. Docs remains the sole open Gate A item.

**Identity (2026-09-29): resolved, with one disclosed follow-up.** The 18 extraneous legacy keys
were relocated/quarantined via an owner-run script (agent-run writes to key files are blocked by
the permission classifier, by design — a dry-run/`--apply` script was handed to the owner instead
of attempted directly): `agy` relocated cleanly (no conflict); 2 unregistered orphans and 2
duplicate copies of the live on-chain `xibalba` identity's key material (found unexpectedly
scattered across the `xibalba-quant` and `xibalba-shield` Hermes profile roots in addition to its
one correct copy under main `.hermes`) and 12 dead Antigravity subagent-worktree fixture keys were
all quarantined (moved to `~/.integrity-quarantine-2026-09-29/`, not deleted). **Side effect, still
under the owner's own investigation, not this session's:** quarantining 2 of the orphans (main
`.hermes` profile's `xibalba` slot and `xibalba-quant` profile's own `xibalba-quant` slot)
triggered a live process — not yet root-caused, candidates are the Hermes gateway or
`xibalba-quant-framework`'s paper-trading loop — to mint a brand-new unregistered DID in each spot
within seconds. Stable since (no further regeneration), and confirmed paper-trading only (no real
capital). Whatever resolves identity for those two profiles is bypassing `integrity_sdk`'s
profile-scoped key-home design and reading/writing the legacy in-root path directly; finding that
call site is the actual next step here, separate from the original 18-key cleanup this item was
about.

## Outcome at handoff (as of 2026-09-28, historical)

The execution plan is at **78/201 checkboxes (38%)**, unchanged this session. A0-A6 are complete
(see prior handoff content, preserved below under "A6 recap"). Gate A is now **2/12 items
complete**, same as before — this session found one item that's effectively done but never
checked off (cut-path manifest) and confirmed the other open items with a real blocker in one
case (Identity), not a change to the count itself.

## Gate A: item-by-item, with evidence

- [x] **Kernel** — `forge test -vvv` in `contracts/`: 335 passed, 0 failed, 27 suites, including
  `IntegrityKernelAssuranceTier.t.sol` tier-off coverage. Confirmed no `registry/` import in
  `contracts/src/*.sol`.
- [x] **Receipts** — `uv run --directory integrity-sdk pytest -q`: 458 passed, 3 skipped, including
  the full `test_core_receipts.py` class (17 tests: sign/verify, chain, checkpoint, inclusion,
  tamper/truncation/foreign-key refusals).
- [ ] **Builds** — mixed:
  - Suites green locally: contracts 335/0, oracle (`cargo test --workspace`) 182/0, SDK 458/3-skip,
    CLI (`uv run pytest -q`) 70/1-skip, bcc_middleware (`uv run pytest -q`) 161 passed + OPA
    (`opa test policies/ -v`) 48/48, integrity-console dashboard (`npm run build`) clean.
  - `xibalba-shield` root-free suite (`.venv/bin/python -m pytest -q`): 465 passed, 12 skipped, 1
    deselected — `tests/test_release_manager.py::test_default_installer_really_installs_a_real_trivial_wheel`
    hangs its ensurepip/pip subprocess in a stopped (`T`) job-control state when run backgrounded;
    unrelated to Gate A's Shield checklist (installer/packaging scope), unverified this pass, not
    blocking.
  - `xibalba-cortex` suite: all tests pass (pytest's own final summary line is swallowed by an
    mlflow-autolog teardown hook — confirmed via dot-count and exit code 0, not via junitxml this
    pass) — but the local checkout was **1 commit behind `origin/main`** at test time (missing PR
    #32, an A3 identity-binding change); results should be re-confirmed against current main.
  - **CI found broken and fixed**: `xibalba-cortex`'s CI on `main` has been failing since PR #33
    merged (`ci: pin Cortex to SDK core revision`) — it pinned the sibling `integrity-core`
    checkout to a **short** SHA (`ef5bf607`), which `actions/checkout@v4` cannot resolve via its
    shallow-fetch ref-matching path (it tries `refs/heads/ef5bf607*` instead of fetching the commit
    directly), so every run has failed at checkout before any test executes. Fixed in
    [xibalba-cortex#34](https://github.com/XibalbaTechSol/xibalba-cortex/pull/34) (full 40-char SHA)
    — **CI now passes on that PR; PR is open, not merged** (merge needs explicit owner action, not
    auto-mode). `xibalba-shield`'s CI is green on current `main` (some earlier UI-typography
    commits failed and were fixed forward same day).
  - Cut-path manifest: confirmed present and populated in `integrity-lab` (91 files, four
    categories: ZK proving, prediction markets/A2A capital pool, licence layer, and more) —
    **this sub-item is satisfied**, just never marked as checked before.
  - **One SDK JCS implementation — RESOLVED.** An earlier pass of this same handoff (same day)
    reported this as an open violation with three independent implementations, based on reading
    `xibalba-shield` and `xibalba-cortex` checkouts that had **not been fetched** and were stale by
    exactly the commits that fix this. Re-checked directly against `origin/main` for both repos:
    - `xibalba-shield` (`xibalba-shield#39`, merged 2026-09-28): both `shield/config/signing.py`
      (policy-bundle signatures) and `shield/release/signing.py` (release attestations) now call
      SDK JCS via a shared `shield/canonical.py`, with explicit schema-version tags
      (`xibalba.shield.policy-signature.v2`, `xibalba.shield.release-attestation.v2`) so
      pre-migration and post-migration signed artifacts stay distinguishable. No backfill of
      already-signed bundles was needed or attempted.
    - `xibalba-cortex` (`xibalba-cortex#32`, merged 2026-09-28): `store.py`'s hash-chain/Merkle
      canonicalization dispatches on a per-store flag set at store-open time
      (`current_version == 0` → SDK JCS for brand-new stores; existing stores stay permanently on
      the old convention) — the same new-writes-only, schema-versioned, no-backfill pattern
      `integrity-sdk`'s own `memory_dag.py` used for its internal v1→v2 migration. One remaining
      duplicate, `telemetry_outbox.py`'s separate `_canonical_json` (local/ephemeral outbox-queue
      hashing, not part of the permanent hash chain), was found and fixed this pass in
      [xibalba-cortex#35](https://github.com/XibalbaTechSol/xibalba-cortex/pull/35) — switched to
      the same SDK JCS via `canonical.py`, no version gate needed since outbox rows are transient
      (drained/purged, never a permanent ledger).

    Lesson for future sessions: **always `git fetch` a live-service repo's checkout before reading
    its source to answer a Gate A question** — a stale local tree produced a false "violated"
    finding here that took real investigation to walk back.
  - Not checked this pass: import hygiene beyond the kernel/registry check above.
- **Shield** — suite green (465/12/1-deselected); re-checked each sub-item against `origin/main`
  (not a stale local read this time):
  - **Pack hash equality — confirmed enforced**, not just computed.
    `tests/test_config.py::test_loads_policy_bundle_metadata_and_hash` only confirms a hash gets
    computed with the right shape; the real enforcement is
    `tests/test_distribution_siem_dlp.py::test_fetch_tenant_policy_rejects_untrusted_hash` and
    `tests/test_hot_reload.py::test_rejects_untrusted_policy_hash_on_reload`, both of which reject
    a policy whose hash isn't in `trusted_policy_hashes`.
  - **Tamper/malformed/expired refusal — confirmed**: `tests/test_config_signing.py`'s
    `test_verify_rejects_tampered_policy_content`, `test_verify_rejects_a_tampered_signature`,
    `test_verify_rejects_an_expired_policy`, `test_verify_rejects_malformed_wrapper_shape`.
  - **"Incompatible pack" — confirmed**, via `test_verify_rejects_legacy_canonicalization_metadata`
    (added in `xibalba-shield#39` this morning alongside the JCS migration): a bundle whose
    `schema`/`canonicalization` fields don't match the current version is rejected with
    `"unsupported signed-bundle schema or canonicalization"`.
  - **No-match default — confirmed**: `test_policy_engine.py::test_real_opa_unmatched_agent_event_defaults_to_deny_on_the_regulated_profile`.
  - **Malformed/unknown/evaluator-error deny — confirmed**, all three cases now isolated:
    `test_policy_engine.py::test_unknown_event_class_denies_in_enforce_mode`,
    `::test_malformed_raw_decision_denies_in_enforce_mode`, and — the one this pass actually
    found by reading `shield/policy_engine/engine.py`'s exception handler (it calls
    `resolve_decision(..., evaluator_error=exc)` when OPA itself raises) —
    `::test_opa_unavailable_fails_closed`, which asserts `decision.action == "deny"` when OPA
    raises `OpaError`.
  - **No raw command content in exports — confirmed**:
    `tests/test_distribution_siem_dlp.py::test_content_classifier_uses_metadata_without_raw_content`.
  - **Distinct device/agent keys — CONFIRMED, tests added.** `device_assertion.py`'s
    `load_device_keypair()` reads from an explicit `SHIELD_DEVICE_KEY_PATH` env var, structurally
    separate from the agent DID key path, but had zero direct test coverage. Added three tests in
    [xibalba-shield#40](https://github.com/XibalbaTechSol/xibalba-shield/pull/40):
    `test_load_device_keypair_returns_none_without_a_configured_path` (no silent fallback),
    `test_load_device_keypair_reads_the_key_at_the_configured_path` (round-trip fidelity), and
    `test_device_key_is_cryptographically_distinct_from_the_agent_identity_key` (the load-bearing
    one — asserts the device key differs from whatever `load_or_create_did()` mints for the agent
    identity in the same harness root). 12/12 pass in `test_device_assertion.py`.

    **Unrelated finding while running the full suite from a worktree**: 11 failures in
    `test_cli.py`/`test_privileged_socket_sensor.py` reproduce identically on an untouched
    checkout of current `main`, but the latest `main` CI run is green — local-machine
    environmental noise (this machine runs a live Shield systemd install concurrently), not a
    real regression. Not investigated further; flagged in case it recurs.
- **Cortex** — suite green (own checkout, 1 commit stale — see above):
  - reject unauthenticated OTLP: `tests/test_otlp_receiver.py`'s `test_missing_bearer_token_is_rejected`,
    `test_invalid_bearer_token_is_rejected`, `test_read_only_token_is_rejected_for_ingestion`,
    `test_revoked_token_is_rejected` — solid coverage.
  - **Provenance export — CONFIRMED**, and it's rigorous, not just a self-reported hash:
    `test_store.py::test_export_provider_telemetry_returns_a_verifiable_merkle_export` exports
    provider telemetry, then independently re-derives and checks the Merkle proof via
    `verify_domain_merkle_proof` for every leaf — not just trusting `export()`'s own claimed root.
  - **`content_hash` on create — CONFIRMED**: `test_store.py::test_store_memory_preserves_provenance_and_is_idempotent`
    asserts `store_memory`'s primary create path returns a correctly-shaped `content_hash`
    (`re.fullmatch(r"sha256:[0-9a-f]{64}", ...)`).
- [ ] **Identity — partially resolved.** 23 live `private_key.pem` files were found under
  harness/profile roots on this machine, all matching the **legacy in-root layout**
  (`<harness root>/.integrity/did/<agent>/private_key.pem`) that `integrity_sdk/did.py`'s current
  design (comment block, lines ~205-226) already moved away from by policy: DID document in the
  harness root, private key in `<key home>` (`$INTEGRITY_DID_HOME` or `~/.integrity/did`) —
  **outside** any harness root, confirmed as the intended design. The owner narrowed scope to the
  five identities that matter (`xibalba.agent`, `xibalba.shield`, `xibalba.quant`, `codex`,
  `claude`) — the other 18 (subagent worktree copies, test/demo agent fixtures) are extraneous and
  were left untouched.

  For each of the five, on-chain registration was checked against `XibalbaAgentRegistry`
  (`0x72e21e44AdD6d6e7CAa02eaedF078630afC40819`, Base Sepolia) via `integrity-cli`'s `resolve_did`
  before touching anything:

  | Identity | Finding | Action |
  |---|---|---|
  | `claude` | Already fully migrated in both profiles that use it; no legacy key exists anywhere. | None needed. |
  | `xibalba.agent` | Two candidate keys existed for the same (profile, agent) slot: a legacy in-root copy (**not registered on-chain**) and an already-migrated copy (**registered on-chain**). The registered one is already correctly placed. | None needed. The unregistered legacy copy is a stale orphan, left alone (not urgent cleanup). |
  | `xibalba.quant` | Same pattern as `xibalba.agent` — unregistered legacy copy vs. registered, already-migrated copy. | None needed; unregistered orphan left alone. |
  | `codex` | Single legacy in-root key, not registered on-chain (no conflict risk). | **Relocated** — ran `_relocate_legacy_identity('codex', ...)`; DID confirmed unchanged (`did:integrity:d73b98dd...`) before and after; legacy directory now empty. |
  | `xibalba.shield` | Single legacy in-root key, **registered on-chain** (the real, sole identity). | **Relocated** — ran `_relocate_legacy_identity('xibalba-shield', ...)`; DID confirmed unchanged (`did:integrity:2ea17967...`) before and after; on-chain registration unaffected (same DID, no re-registration needed). Confirmed `shield/integrity_exporter/exporter.py`, `preflight.py`, and `device_assertion.py` all resolve keys through `agent_dir()`/`load_or_create_did()` (which use `key_store_for_profile`, not a hardcoded legacy path), so the live systemd service is unaffected now and will resolve correctly on any future restart.

  Both relocations used the SDK's existing copy-verify-delete logic directly (no new code written) —
  copy first, confirm the copy derives an identical DID, only then delete the source. Executed by
  the machine owner directly (agent-run write to private-key files was blocked by the permission
  classifier, by design). The **uncommitted edit in `integrity-sdk/integrity_sdk/did.py`** (14 lines
  added to `migrate_identity_store`, still present and untouched in this checkout) remains
  in-progress work on a related edge case (a destination directory with non-secret state but no
  key/doc yet) and was not needed for this relocation.

  **Still open:** the 18 extraneous legacy keys (subagent worktree copies, test/demo fixtures) are
  untouched by owner choice — this item can't be marked fully passed while they remain, but they're
  explicitly out of scope for now, not an oversight. (Confirmed the only `PRIVATE KEY` string in the
  SDK's own test fixtures, `tests/unit/test_redactor.py:56`, is a truncated synthetic placeholder,
  not live key material.)
- [ ] **Docs** — `scripts/check_docs.py` passes for `integrity-core` itself (49 authoritative, 55
  merge-required, 72 historical, 0 removable; authority/links/wiki-index/STATUS.md-cap all pass).
  One drift found and not yet fixed: `AGENTS.md` line 11 says "Eight packages" but the table under
  it (lines 15-20) lists six, including `integrity-zkp/` which was already cut from the repo in A1
  (`3739d3c5`) — only a stale `target/` build-artifact directory remains, no `Nargo.toml`/source.
  Cross-repository doc-authority checks (competing plans/architecture registers in
  `xibalba-shield`, `xibalba-cortex`, `integrity-console`) were not run this pass.

## A6 recap (unchanged from the prior handoff)

A6 delivered the eight local-first seams without billing or hosted-service dependencies: tenant/
organization identity and tenant-scoped agent/device registration; signed pack hash/version
pinning; durable signed-receipt queueing; offline pack and receipt verification; Cortex-compatible
provider/store identity; tenant-scoped entitlement and capability checks; aggregate-only usage and
audit metrics. Merged A6 PRs: #118-#124.

## Side effects from this session's validation (disclosed, not reverted)

1. `xibalba-cortex/.venv` was touched and restored. A `uv sync` (no extras) run to fix an
   unrelated `ModuleNotFoundError: google.auth` collection error uninstalled the `drive` and
   `otel` optional-dependency-group packages that venv already had (it serves ~10 running Cortex
   processes: `local_api` on ports 8420/8422-8424/8427-8428, the embedding worker, MCP stdio
   servers). Restored via `uv sync --extra drive --extra otel` plus a direct `uv pip install`
   pinning `opentelemetry-exporter-otlp-proto-http==1.45.0`,
   `opentelemetry-exporter-http-transport==0.66b0`, and
   `opentelemetry-exporter-otlp-common==0.66b0` back to their exact original versions (confirmed
   via `importlib.metadata.version()`). No process was restarted mid-session, so nothing live was
   affected, but this is worth knowing if anything in that venv looks different after a future
   restart.
2. Something else modified `xibalba-shield/ui/src/components/TransactionWorkbench.jsx` and
   `ui/src/App.css` at 12:03 and 12:05 local time, mid-session — not from this session (nothing
   here touched the `ui/` tree). Left untouched; `xibalba-shield` is a live editable install
   (`/opt/xibalba-shield` venv points at this checkout, systemd eBPF service) with something else
   apparently editing it concurrently. Worth checking what.
3. `xibalba-cortex`'s CI on `main` was broken (bad short SHA, see above) and is now fixed in an
   open, unmerged PR (#34) — CI passes there. No merge was performed.

## Useful validation commands

From `/home/xibalba/Projects/integrity-core`:

```bash
python3 scripts/plan_progress.py
python3 scripts/check_docs.py
python3 scripts/wiki_toc.py --check
uv run --directory integrity-sdk pytest -q
```

Cross-repo, from each repo's root: `forge test -vvv` (contracts), `cargo test --workspace`
(integrity-oracle), `uv run pytest -q` (integrity-sdk, integrity-cli, xibalba-cortex),
`uv run pytest -q && opa test policies/ -v` (bcc_middleware), `.venv/bin/python -m pytest -q`
(xibalba-shield, `--system-site-packages` venv), `npm run build` (integrity-console/integrity-dashboard).

## Working-tree and runtime safety

- The current checkout still contains the pre-existing user edit in
  `integrity-sdk/integrity_sdk/did.py`; preserve it and do not stage it unless explicitly
  requested. It is mid-work on the exact legacy-key migration path the Identity gate item needs.
- This handoff was written from a fresh branch off `origin/main`
  (`docs/handoff-gate-a-followup`) rather than reusing `handoff/gate-a-after-a6`, which was
  already merged via PR #125 — do not rewrite or force-push merged branches.
- The Shield checkout is a live editable install used by a systemd eBPF enforcement service. Do
  not checkout branches or leave incomplete changes in `/home/xibalba/Projects/xibalba-shield`.
  Something is already editing files there concurrently with agent sessions (see side effects
  above) — investigate before assuming a clean tree.
- Keep Gate A validation local-first. Do not restart live services or broadcast transactions as
  part of source/test validation.
- Any `uv sync` (without matching `--extra` flags) against a live-service repo's checked-in-place
  `.venv` can silently drop optional-dependency-group packages that venv already had installed
  outside the lockfile. Prefer an isolated `git worktree` for anything beyond running the existing
  test suite, and if you must sync a live venv, capture `pip`/`uv pip` output before and after.

## Recommended next sequence

1. JCS consolidation is done — resolved this pass (see Builds above). `xibalba-shield#39` and
   `xibalba-cortex#32` already migrated Shield's policy/release signing and Cortex's store hash
   chain to SDK JCS with proper schema-version gating; `xibalba-cortex#35` (this pass) closed the
   last duplicate in `telemetry_outbox.py`. Merge #35 when ready; nothing else pending here.
2. `codex` and `xibalba-shield` legacy keys relocated (owner-executed, verified — see Identity
   above). Still open by owner choice: the 18 extraneous legacy keys (subagent worktrees, test/demo
   fixtures) remain untouched, and `did.py`'s in-progress `migrate_identity_store` edit is still
   uncommitted (a separate edge case, not required for the relocations done this pass).
3. `xibalba-cortex#34` (CI fix) merged — Cortex's CI is green on `main` again.
4. Re-run the Cortex suite against current `origin/main` (it was 1 commit behind at test time).
5. `AGENTS.md` "eight packages" / six-row table drift fixed in
   [integrity-core#129](https://github.com/XibalbaTechSol/integrity-core/pull/129) (also dropped
   the stale `integrity-zkp` row from the wiki-entity map) — merge when ready.
6. All Shield and Cortex sub-item test mappings now confirmed — pack-hash enforcement,
   incompatible-pack, evaluator-error, no-match default, tamper/malformed refusal, export
   redaction, distinct device/agent keys (test added in
   [xibalba-shield#40](https://github.com/XibalbaTechSol/xibalba-shield/pull/40)), and Cortex's
   provenance-export/`content_hash` binding — see Shield and Cortex above. Nothing left unconfirmed
   in this list.
7. Check `gh run list --branch main` results going forward now that Cortex's CI is fixed, and run
   the Shield/Cortex independence CI check the Builds item actually asks for (a passing CI run,
   not just a local suite).
8. Update `STATUS.md`, `docs/EXECUTION_PLAN.md`, and this handoff only after the above evidence is
   fresh — nothing in this pass ticked a checkbox. With items 1, 5, and 6 now resolved, Gate A's
   remaining open work is narrower: the CI-vs-local-suite distinction in item 7, the 18 extraneous
   legacy keys (owner choice, item 2), and re-running Cortex fresh (item 4).
