# Handoff — Integrity ecosystem restructure, 2026-09-28

**For:** the next Claude session (or human) picking this up.
**Plan authority:** `integrity-core/docs/EXECUTION_PLAN.md` — always re-read it and run
`python3 scripts/plan_progress.py` before trusting any number below; it drifts.
**Progress at handoff:** 46/201 (22%). Phase A0, A1, A2, A4 fully checked off. Phase A3 in progress.
**Branch convention:** `claude/quirky-wright-g7yl7g` in every repo touched (integrity-core,
integrity-console, integrity-lab, xibalba-shield, xibalba-cortex). If a repo's PR on that branch
has already merged, restart the branch from that repo's latest `main` before adding new commits —
don't stack on merged history.

## Open PRs right now

| Repo | PR | State | What it does |
|---|---|---|---|
| integrity-core | [#108](https://github.com/XibalbaTechSol/integrity-core/pull/108) | draft, open | Plan doc update recording A3 progress below |
| xibalba-cortex | [#30](https://github.com/XibalbaTechSol/xibalba-cortex/pull/30) | draft, open | OTLP receiver auth + Merkle domain fix (see below) |
| xibalba-shield | [#36](https://github.com/XibalbaTechSol/xibalba-shield/pull/36) | **merged** | opa_client breakage fix |

All three are subscribed in this session (webhook-driven CI/review events arrive automatically);
if you're a fresh session, re-subscribe with `subscribe_pr_activity` so you get woken on activity,
and check current state with `pull_request_read` rather than trusting this table's snapshot.

## What's merged and done (Phase A0/A1/A2/A4, all of them)

Don't redo any of this — it's real, tested, and on `main`:

- **A0:** toolchain installer, secret-scan script, Jules-conflict workflow paused.
- **A4:** `IntegrityKernel` no longer imports `registry/`; `requireAssuranceTier` flag added;
  `evm_version = cancun`. Halmos verified (`make verify-kernel`).
- **A2:** SDK core package (`integrity_sdk/core/`: jcs, merkle, packs, decision, receipts, opa,
  signed_body, memory) — dependency-light, import-hygiene tested. Lazy `__init__` (PEP 562).
  `[connector]` extra defined.
- **A1:** ZK tooling, markets, licence, CCIP, governance, the on-chain adapter registry, and the
  dashboard/userapi/demo all cut from integrity-core. Cut code preserved with history in
  **integrity-lab**; dashboard/userapi/demo moved with history to **integrity-console**
  (both merged, console#4 also removed the console's pages for the cut features).
- **A3 (integrity-core's own share):** the three ad-hoc canonicalizations
  (`telemetry/envelope.canonical_bytes`, `memory_dag.canonical`, `harness_hooks._hash`) now
  delegate to `core.jcs`. Schema versions bumped (envelope v1→v2, memory-node v1→v2); old versions
  kept as historical artifacts, not deleted.

Identity: agent private keys live outside every harness root (`~/.integrity/did/profiles/...`),
only a public `agent.did.json` sits in the harness root. This landed early (`ad56d97`) and is
**load-bearing for everything downstream** — Shield and Cortex both already consume it correctly
via `integrity_sdk.did.load_or_create_did`.

## What's in flight (Phase A3, Shield + Cortex)

### xibalba-shield — PR #36 (merged)

**Found and fixed a real breakage, not a plan item per se:** `shield/policy_engine/engine.py`
imported `integrity_sdk.policy.opa_client`, which integrity-core's A1 deleted (it was BCC
middleware's own vendored client, never used by the SDK itself). Since Shield pins `integrity-sdk`
as an editable path to the sibling `integrity-core` checkout, **this meant
`import shield.policy_engine.engine` raised `ModuleNotFoundError` against any post-A1
integrity-core checkout** — Shield's entire policy engine was unusable. Fixed with a
behavior-preserving port (`shield/opa_client.py`, new file) — same request/response handling,
same fail-closed semantics, just relocated. Also moved `integrity-sdk` → `integrity-sdk[connector]`
in `pyproject.toml` (Shield needs `did`/`agent_identity`/`client`/`bcc`/`telemetry.tracing`, none
of which are in the SDK's dependency-light core) and added a direct `httpx` dependency.

**442 passed, 17 skipped** locally (root-free). Two failures are pre-existing and unrelated —
this sandbox runs as root, which defeats the `chmod`-based unwritable-directory setup two tests
rely on (`test_chaos_adversarial.py`, `test_cortex_outbox_unavailable.py`); confirmed by `id`
(`uid=0`) and that neither test touches the changed code.

**Deliberately NOT done:** migrating the policy engine onto `integrity_sdk.core.opa.OpaClient`
and real signed packs (the plan's actual "Policy bundles become signed packs..." bullet). This is
a much bigger change than the import fix:
- Shield's Rego currently returns `{"action", "message", "rule_id", "name", "version"}`; the new
  decision contract (`core.decision.resolve`) requires exactly `{"decision", "reason_code",
  "controls"}` with `reason_code` matching `^[A-Z][A-Z0-9_]{0,63}$` (uppercase, no hyphens) — all
  three Rego profiles (`smb.rego`, `professional-services.rego`, `regulated.rego`) need rewriting,
  not just re-signing.
- **Who signs Shield's production packs is an open operational question** the plan itself doesn't
  answer (§6 says "the organization holds the guardian... keys" in the abstract). Don't invent an
  answer unilaterally — this needs the repo owner's input before code.
- `core.decision.py`'s own docstring literally names Shield's exact current bug as the motivation:
  *"Shield previously read its OPA `allow` rule as 'some rule matched', which turned an unmatched
  event into a deny that a mocked test hid."* — so this migration is also a **semantics change**,
  not just a re-plumbing. Don't bundle a semantics change into an urgent unbreak fix.
- The still-unticked plan bullets that depend on this: "permit means permitted", "missing/
  malformed/evaluator-error denies", "replace the mocked test with real OPA output", "Exports
  carry labels and HMAC-protected paths, never raw cmdline", "Separate device-auth and agent
  keys", "Replace the seven canonical-JSON copies with SDK JCS, re-sign bundles, bump the schema".

**Already true, ticked with no code change:** `mlflow` isn't a Shield dependency at all (checked
`pyproject.toml`); DID-file identity is already in place (`integrity_exporter/exporter.py` and
`preflight.py` already call `load_or_create_did`, no `.integrity/identity.json` reference
anywhere). These likely landed from Shield's own independent development after `ad56d97`.

### xibalba-cortex — PR #30 (open, awaiting review/merge)

Two independent real bugs, both fixed and tested:

1. **`export_provider_telemetry` always raised.** `store.py` called
   `domain_merkle_root(..., domain="provider_telemetry_export")` but that domain was never in
   `events.MERKLE_DOMAINS` — `ValueError: unknown Merkle domain` on every call, zero test
   coverage. Registered the domain; added tests in `test_merkle_domains.py` and `test_store.py`.
2. **The OTLP receiver had zero authentication.** Any local process (or any network caller with a
   non-default `--host`) could inject arbitrary telemetry as real provenance evidence. Added the
   same mandatory bearer-token check `local_api.py` already uses (same `ingest_tokens` store, same
   "no unauthenticated fallback" posture, `memory:write` scope). Updated 3 existing HTTP
   integration tests to pass a token; added 4 new tests for missing/invalid/revoked/wrong-scope
   tokens. **This is a real behavior change** — anyone currently exporting to this receiver
   unauthenticated will get 401 until they issue a token and set `OTEL_EXPORTER_OTLP_HEADERS`.
   Flagged in the PR body in case the owner wants a softer transition instead of a hard cutover.

Also: `integrity-sdk` → `integrity-sdk[connector]` (same reasoning as Shield; Cortex's
`agent_identity.resolve_agent_identities` needs `requests`).

**Full suite:** 2 pre-existing failures, both extras-related and unrelated to this change
(`test_drive_ingest.py`, `test_otel_core.py` — need `--extra drive`/an `otel` extra not installed
in this sandbox; matches the README's own documented setup). Everything else passes, including
23/23 in the updated `test_otlp_receiver.py`.

**Deliberately NOT done, and why — read this before touching either:**

- **"Use SDK JCS."** `store.py`'s `_canonical_json` underlies the *entire* hash-chain/Merkle-proof
  system — dozens of call sites (retrieval traces, checkpoint reconciliation, memory events,
  leaf-payload hashes...). Changing it would silently invalidate every already-provisioned Cortex
  profile's stored hashes and inclusion proofs. **The repo's own README declares the store schema,
  hash-chain and Merkle model "frozen for v1" as of 2026-08-12** — this postdates and conflicts
  with the plan's original premise that this was a free swap (the same premise that *was* true and
  safe for integrity-core's own SDK-internal modules, which had no live persisted data depending
  on them). If this is ever done, it needs a domain/schema version bump plus a transition window
  where both the old and new hash are checked — not a drop-in replacement. Treat this as blocked
  on an owner decision (does the v1 freeze allow a versioned migration, or is it truly frozen?),
  not as a to-do to pick up casually.
- **"Resolve agents from the DID file; `XIBALBA_AGENT_ID` becomes an explicit override only."**
  `XIBALBA_AGENT_ID` is read as a *required* identifier in ~10 call sites across `server.py`,
  `store.py`, `provider_bridge.py`, `hermes_observer.py`, `codex_mcp_backfill.py`,
  `codex_probe.py`, `agy_hook_bridge.py`. `server.py`'s own docstring: *"XIBALBA_AGENT_ID is
  required: without it this server cannot scope memory access."* This is a real, multi-file
  behavior change (make DID-file resolution the primary path, env var becomes an override), not
  a quick fix — it deserves its own dedicated pass with its own test coverage, not to ride along
  with the two bug fixes above.
- Both are recorded as unticked in the plan with this same reasoning inline, so the next session
  doesn't have to re-derive it from scratch.

## Process notes for whoever continues this

- **Always run `git status`/`git branch --show-current` before trusting a snapshot** — this repo
  set's own CLAUDE.md says so, and it was true this session too (each sibling repo needed fresh
  reconnaissance before any of the above was known).
- **`scripts/secret_scan.sh origin/main`** (or `gitleaks protect --staged` in Shield/Cortex, which
  don't have that script) before every push. All clean this session.
- **The `github-advanced-security` check is a known, unfixable-from-the-PR false failure** in
  integrity-core specifically — it's GitHub's own Copilot code-scanning agent hitting
  `SessionModelError: CAPIError: 400 The requested model is not supported`, a GitHub-account-side
  model-entitlement issue, not anything in the diff. Confirmed via job logs and a failed
  `rerun_failed_jobs` (403, not retriable). Already documented on PR #101 and #105; don't
  re-investigate it, just note it once per new PR if it recurs and move on.
- **This sandbox runs as root** (`uid=0`). Any test that relies on `chmod` to make a path
  genuinely unwritable will spuriously fail here and pass in real (non-root) CI. Don't "fix" these
  — verify they're unrelated to your diff (check imports, revert-and-compare) and move on.
- Before attaching a new sibling repo with push access, remember: it needs its own venv
  (`uv venv` + `uv pip install -e ".[dev]"` or `uv sync`), and its `pyproject.toml` almost
  certainly pins `integrity-sdk` as an **editable path to `../integrity-core/integrity-sdk`** —
  so it always reflects whatever is currently checked out there, for better (you get to test
  against real integration) or worse (a checked-out-but-unmerged integrity-core change can make a
  sibling repo's tests reflect work that isn't on `main` yet).
- Two read-only reference clones exist from earlier work and can be deleted if disk space is
  needed: `/home/user/integrity-lab` (has push access, keep) vs.
  `/home/user/xibalbatechsol/xibalba-cortex` (an earlier read-only clone, superseded by the
  push-access one at `/home/user/xibalba-cortex`).

## Suggested next steps, roughly in order

1. **Watch PR #30 (Cortex) to merge** — it's a real fix with real tests, just needs review/CI.
2. **Get the owner's answer on Shield's pack-signing key custody** before attempting the signed-packs
   migration — this unblocks four other Shield A3 bullets at once.
3. **Get the owner's read on Cortex's "frozen for v1" JCS conflict** — is a versioned migration
   in scope, or does "frozen" mean genuinely don't touch it before a v2?
4. Once those two are unblocked, the Shield Rego rewrite and the Cortex `XIBALBA_AGENT_ID`→DID-file
   migration are the two largest remaining A3 items — each probably deserves its own focused
   session rather than being squeezed alongside other work.
5. After A3: **A5** (consolidate plans/docs — merge `AGENTS.md`/`.agents/AGENTS.md`, archive
   superseded plan docs, `STATUS.md`) and **A6** (stable SaaS seams) are the remaining Phase A
   items before Gate A. Neither has been started.
