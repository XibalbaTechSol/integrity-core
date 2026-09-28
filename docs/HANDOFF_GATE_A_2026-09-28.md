# Handoff: Gate A validation pass, after A6

**Date:** 2026-09-28
**Repository:** `integrity-core`
**Authority:** [`docs/EXECUTION_PLAN.md`](EXECUTION_PLAN.md)
**Current status:** A6 complete; Gate A not passed. A full validation pass ran against all 10 open
items this session (superseding the same-day handoff written right after A6 merged). No
`EXECUTION_PLAN.md` checkboxes were ticked — nothing here should be read as the gate passing.

## Outcome at handoff

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
  - **One SDK JCS implementation — found violated, not fixed.** At least three independent
    canonicalization implementations exist across the ecosystem, not one shared SDK JCS:
    - `integrity-sdk`'s own `jcs` dependency (the intended single implementation);
    - `xibalba-shield/shield/config/signing.py`'s `canonical_policy_json()` — plain
      `json.dumps(sort_keys=True, separators=(",", ":"))`, not RFC 8785 JCS, used to compute the
      bytes a policy-bundle signature covers;
    - `xibalba-cortex`'s own `_canonical_json` (two separate definitions: `telemetry_outbox.py:37`
      and `store.py:1776`).

    Shield's own docstring in `signing.py` explicitly acknowledges this: "matching the
    canonicalization convention already used elsewhere in this ecosystem (e.g. xibalba-cortex's
    `_canonical_json`)" — i.e. the duplication was a deliberate choice to match an existing
    non-SDK convention, not an oversight. **This touches signature verification across repos — an
    identity/security boundary. Per SOUL, consolidating these needs owner review (and likely a
    Devil's Advocate pass on the migration plan) before any code change, not a unilateral fix.**
    Left untouched this pass; flagged here as the item blocking "Builds" most concretely.
  - Not checked this pass: import hygiene beyond the kernel/registry check above.
- **Shield** — suite green (465/12/1-deselected); mapped each sub-item to existing tests (not all
  confirmed to assert the exact Gate A wording):
  - pack hash: `tests/test_config.py::test_loads_policy_bundle_metadata_and_hash` — plausible
    match, not read line-by-line to confirm it asserts *enforced* hash equality specifically.
  - tamper/malformed/expired(~stale) refusal: `tests/test_config_signing.py`'s
    `test_verify_rejects_tampered_policy_content`, `test_verify_rejects_a_tampered_signature`,
    `test_verify_rejects_an_expired_policy`, `test_verify_rejects_malformed_wrapper_shape`.
    "Incompatible pack" (version-mismatch) specifically not found as a named test.
  - no-match default: `tests/test_policy_engine.py::test_real_opa_unmatched_agent_event_defaults_to_deny_on_the_regulated_profile`.
  - malformed/unknown/evaluator-error deny: `test_policy_engine.py::test_unknown_event_class_denies_in_enforce_mode`,
    `::test_malformed_raw_decision_denies_in_enforce_mode`. "Evaluator-error" specifically not
    isolated as its own test.
  - no raw command content in exports: `tests/test_distribution_siem_dlp.py::test_content_classifier_uses_metadata_without_raw_content`.
  - distinct device/agent keys: several binding tests exist (`test_backend.py`'s
    `test_backend_binding_proof_requires_device_possession_and_agent_signature`,
    `test_backend_cortex_memory_proxy_is_bound_to_device_agent_pair`) but none directly asserts
    the two keys are cryptographically distinct — **not confirmed, treat as open**.
- **Cortex** — suite green (own checkout, 1 commit stale — see above):
  - reject unauthenticated OTLP: `tests/test_otlp_receiver.py`'s `test_missing_bearer_token_is_rejected`,
    `test_invalid_bearer_token_is_rejected`, `test_read_only_token_is_rejected_for_ingestion`,
    `test_revoked_token_is_rejected` — solid coverage.
  - provenance export / `content_hash` binding: matches found in `tests/test_store.py` and
    `tests/test_retrieval_completeness.py` — not read line-by-line to confirm they assert the
    exact Gate A wording.
- [ ] **Identity — confirmed BLOCKED, not just unchecked.** 23 live `private_key.pem` files
  currently exist under harness/profile roots on this machine (paths, not contents, listed —
  never print key material):
  - `~/.codex/.integrity/did/codex/private_key.pem`
  - `~/.gemini/antigravity-cli/.integrity/did/agy/private_key.pem`
  - 12 more under `~/.gemini/antigravity-cli/brain/.../worktrees/subagent-*/.integrity/did/*/private_key.pem`
  - `~/.hermes/did/*` (7 files) and `~/.hermes/.integrity/did/xibalba/private_key.pem`
  - `~/.hermes/profiles/{xibalba-quant,xibalba-shield}/.integrity/did/*/private_key.pem` (4 files)

  All match the **legacy in-root layout** (`<harness root>/.integrity/did/<agent>/private_key.pem`)
  that `integrity_sdk/did.py`'s current design (comment block, lines ~205-226) already moved away
  from by policy: DID document in the harness root, private key in `<key home>`
  (`$INTEGRITY_DID_HOME` or `~/.integrity/did`) — **outside** any harness root, exactly the split
  the user confirmed is the intended design. `migrate_identity_store()` is meant to relocate
  legacy in-root keys on first use; these 23 are un-migrated. The **uncommitted edit in
  `integrity-sdk/integrity_sdk/did.py`** (14 lines added to `migrate_identity_store`, still
  present and untouched in this checkout) is mid-work on exactly this migration path — it handles
  a destination directory that already has non-secret state (e.g. `bcc_nonce`) but no key/doc yet,
  so migration doesn't wrongly treat it as corrupt. This item cannot pass until migration actually
  runs against these 23 keys and is re-verified; **migrating live keys is an identity-boundary
  change and was not performed this pass** — it needs explicit sign-off before executing, not
  bundled into a validation pass. (Confirmed the only `PRIVATE KEY` string in the SDK's own test
  fixtures, `tests/unit/test_redactor.py:56`, is a truncated synthetic placeholder, not live key
  material, so the test suite itself isn't part of the blocker.)
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

1. **Owner decision needed**: whether/how to consolidate the three canonicalization
   implementations (SDK `jcs`, Shield `canonical_policy_json`, Cortex `_canonical_json`) onto one
   SDK-owned JCS implementation — this is the most concrete open "Builds" blocker, and it's a
   signature-verification boundary change across repos.
2. **Owner decision needed**: whether to run the legacy-key migration now against the 23 in-root
   keys found on this machine, once `did.py`'s in-progress `migrate_identity_store` edit is
   finished and reviewed — this is the Identity item's actual blocker.
3. Merge or close `xibalba-cortex#34` (CI fix, currently green, unmerged).
4. Re-run the Cortex suite against current `origin/main` (it was 1 commit behind at test time).
5. Fix the `AGENTS.md` "eight packages" / six-row table drift.
6. Finish the unconfirmed Shield/Cortex sub-item test mappings above (pack-hash exact assertion,
   incompatible-pack refusal, evaluator-error isolation, device-vs-agent key distinctness,
   provenance-export/content_hash exact assertions).
7. Check `gh run list --branch main` results going forward now that Cortex's CI is fixed, and run
   the Shield/Cortex independence CI check the Builds item actually asks for (a passing CI run,
   not just a local suite).
8. Update `STATUS.md`, `docs/EXECUTION_PLAN.md`, and this handoff only after the above evidence is
   fresh — nothing in this pass ticked a checkbox.
