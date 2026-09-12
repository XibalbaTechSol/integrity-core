# Gate 1 (identity boundary) handoff — 2026-09-12

Continuation of `docs/audits/tri-repo-audit-2026-09-12.md`. User accepted `docs/SPEC-v2.0.0-proposed.md`
as the implementation target (not yet formally accepted per its own §14 checklist — `docs/SPEC.md`
remains normative) and asked to implement Gate 1 (§11), then said "all of the above" to: quick fixes,
AgentSubject design, ERC-8004 revision hash, and negative tests. This session ran out of context before
finishing; resume here.

## Done and pushed this session

**integrity-core** (`docs/rescope-registry-precheck-gas` branch):
- `99c786a` tracked `docs/SPEC-v2.0.0-proposed.md` (was untracked since written)
- `2dc6e38` **F1**: `integrity-sdk/integrity_sdk/did.py` `load_or_create_did()` now fails closed
  (`IdentityInconsistentError`) instead of silently regenerating/overwriting a private key on a missing
  or mismatched `document.json`. Missing-document case is losslessly auto-repaired instead. Tests in
  `tests/unit/test_did.py`.
- `2dc6e38` **F3**: `integrity_sdk/registration.py` now records `chain_id` in
  `registration_progress.json` and `primitives.json`, and discards cached progress if `chain_id`
  doesn't match the currently-connected chain — closes the cross-chain address-collision hole (CREATE
  addresses don't depend on chain, so a reused wallet+nonce sequence can derive the identical address
  on two different chains). Test in `tests/test_registration.py::test_register_agent_discards_progress_from_a_different_chain`
  reproduces this against a real anvil chain.
- `afbcf58` committed the user's own concurrent edit: Shield edge/cloud/hybrid deployment modes added
  to `SPEC-v2.0.0-proposed.md` §3.2/§4.5 (not mine — theirs, done in parallel).

**xibalba-shield** (`main`):
- `3569781` documented (template only) that `packaging/systemd/shield.env.example` needs
  `INTEGRITY_DID_HOME=/var/lib/xibalba-shield/integrity-did` — the live systemd unit runs as
  `User=xibalba-shield` whose home doesn't exist under `ProtectHome=read-only`, so identity storage
  silently resolves nowhere real. **Not applied to the live unit** — that's root-owned
  (`/etc/xibalba-shield/shield.env`), the service is `active` right now, and fixing it for real means
  copying (never regenerating) the existing key pair with correct ownership before restarting a live
  security-enforcement daemon. Needs the user present with sudo.
- `042f587` fixed a stale comment in `shield/integrity_exporter/exporter.py` that described exactly the
  device-identity-determines-portable-subject coupling §4.4 forbids. Comment-only, no behavior change.
- `242eb95` added `tests/test_machine_identity_boundary.py` — negative tests proving `agent_label`
  (portable identity) and `device_id` (machine identity) cannot influence each other, per §4.4.

**Also this session, outside Gate 1 (see prior context):** moved
`~/.integrity/wallet/xibalba-shield/WALLET_PASSWORD.txt` → `~/.integrity/secrets/xibalba-shield-wallet-password.txt`
(mode 600, dir mode 700) — was sitting cleartext next to its encrypted keystore, nullifying at-rest
encryption. **This is not a real fix, just damage control** — the user should move that password into
an actual secret manager and delete the file. Never read/printed its contents.

**Second pass, after user said "all of the above" again:**
- `312661b`/`338d424` **ERC-8004 §5.1**: content hash pinned. Fetched `ERCS/erc-8004.md` at the exact
  pinned commit via `gh api repos/ethereum/ERCs/contents/...?ref=<commit>`, verified the blob hash via a
  second, independent path (the commit's git tree object), sha256
  `249dc3d96ad7bbe4afd25cacd14be942eb87751abcf1608bab19a610f3c3f8a9`. Recorded in
  `docs/INTERFACE_CONTRACT.md` §6.1a, `SPEC-v2.0.0-proposed.md` §5.1/§14, and as an on-chain-readable
  constant `ERC8004_DRAFT_CONTENT_SHA256` on `IntegrityIdentityReadV1.sol`, with a pinning test.
- `04ef862` **corrected `isERC8004Conformant()` from a false `true` to `false`** on
  `IntegrityERC8004Registry.sol` — the pinned ERC-8004 text requires transferability
  ("the owner... can transfer ownership"); this contract is deliberately soulbound (`transferFrom`
  always reverts), so it cannot conform. This was disprovable, not just unverified. Also documented the
  contract in `INTERFACE_CONTRACT.md` §6.1b for the first time (existed since `41385d6` with zero doc
  coverage), and corrected two stale spec rows (§6.3, §12, Gate 2 checklist) claiming the
  IntegrityKernel/IntegrityAccount fixtures fail in setup — they don't (121+7 tests pass).

## F2 — resolved this session

User decided: SDK's identity store (`~/.integrity/did/`) is authoritative; `integrity-cli` now reads/writes
the same location and layout, keeping its own independent code (`1843bcf`). Full comparison of every label
in both stores found exactly **one** literal collision — `xibalba` itself — and it was NOT a Shield-style
orphan/real pair: both sides are genuinely distinct, live, Base-Sepolia-registered identities (SDK's
`68fed133…` under `general.integrity`, CLI's `f96ae072…` under `healthcare.integrity`, different
SovereignAgent/StateAnchor addresses, ~21h apart). User confirmed these are legitimately different
registrations that only coincidentally shared a label, the same way `xibalba-shield`/`shield-replacement`
turned out to be two different labels for arguably-the-same intended agent, just inverted (there, one
label, meant-different; here, two real identities, same label by accident). Renamed on migration to
`xibalba-healthcare-cli` rather than merged or discarded.

**Key finding for `AgentSubject` design:** a pure label-matching migration cannot detect a Shield-style
collision at all — `shield-replacement` (CLI) and `xibalba-shield` (SDK) are *different label strings* for
what a human treats as the same logical agent. Only a human (or some out-of-band provenance record) can
declare that correspondence; storage-path unification alone doesn't surface it. This is likely the actual
job `AgentSubject` needs to do — an explicit, human-declared mapping from label/DID to logical agent,
not just "one directory instead of two."

Five other CLI-only labels with no SDK counterpart were copied (never moved) into the unified store as-is:
`mvp-verify`, `quant`, `shield-replacement`, `xibalba-agent-01`, `xibalba-agent-02` — including their
wallet keystores. Two (`shield-replacement`, `xibalba-agent-01`) had no `document.json`; loading them
exercised this session's F1 fix, which reconstructed the document from the key losslessly. Every migrated
DID verified to match its pre-migration fingerprint exactly. Every original CLI-store file is untouched.
Full backup taken before any copy: `~/.integrity-migration-backup-20260912-181545`.

**Still not done, flagged rather than fixed:**
- `integrity-sdk/sync_telemetry.py` hardcodes `~/.integrity-cli/identity/xibalba.pem` — that's the
  healthcare-vertical identity (`f96ae072…`), not the general one Hermes actually runs as (`68fed133…`).
  Unclear whether that was intentional or a stale reference from before the two diverged. Ask the user
  which identity telemetry-sync should actually sign as before touching this — it's a live behavior
  decision (which DID shows up in oracle-recorded telemetry going forward), not a path cleanup.
- `scripts/register_shield_with_funder.sh` still checks the old flat CLI path for `IDENTITY_NAME`. Already
  known to target the wrong DID regardless (see the on-chain registration item below) — fix both together.

## Done and pushed, third pass — AgentSubject (§4.1/§11 Gate 1 bullet 1)

Implemented as `integrity-sdk/integrity_sdk/agent_subject.py`: an append-only
`agent_subjects.jsonl` alongside the per-agent directories under `did.did_home()`
(`$INTEGRITY_DID_HOME`), using §9.2's mapping-record field set verbatim. `MappingType.SAME_SUBJECT`
declares two labels are the same logical agent; `MappingType.DISTINCT_SUBJECT` declares a reviewed
non-identity. `resolve_subject(label)` follows only active `SAME_SUBJECT` edges to a connected
component and returns its lexicographically smallest member — **explicitly documented as not a
stable identifier to persist elsewhere**, since a later mapping can pull a smaller label into an
existing component and change what an unrelated label resolves to. `record_mapping` fails closed
(`SubjectConflictError`) both on a direct contradiction (opposite mapping type already active for
the same pair) and transitively (a `SAME_SUBJECT` edge that would merge across an existing
`DISTINCT_SUBJECT` edge through some other label) — corrections require `revoke_mapping` first,
which appends a new `REVOKED` record pointing at the original via `predecessor_mapping_id` rather
than editing history in place. 17 tests in `tests/unit/test_agent_subject.py`, all passing
alongside the full `did.py` suite.

Deliberately NOT auto-seeded: `created_by_principal` is supposed to be the human who reviewed the
evidence, not this session quoting its own audit back to itself. `integrity-sdk/scripts/
seed_agent_subjects.py` documents the exact two real correspondences the audit found —
`xibalba-shield`≡`shield-replacement`, `xibalba`≠`xibalba-healthcare-cli` — with full basis text,
but the user needs to actually run it (`cd integrity-sdk && .venv/bin/python
scripts/seed_agent_subjects.py`) for the record to exist and to be the real reviewing principal on
it.

Scope note: this is SDK-only and read/write plumbing only — nothing in `integrity-cli`, the
oracle, or Shield/Cortex reads `agent_subjects.jsonl` yet, so it records review but doesn't gate
any behavior. Spec marked `[PARTIAL]`, not `[BUILT]`, for exactly this reason.

## Not started

1. **The actual on-chain registration** — repoint `scripts/register_shield_with_funder.sh` (or a new
   script) at the SDK-store DID `2ea17967f7a65589d570ca7e800844701fb36e6aa7374243e8766de8651f6bc4`
   (confirmed unregistered on Base Sepolia per the audit's §2.1 on-chain readback — no history to
   preserve, so this is the right target) rather than the CLI-store `shield-replacement` identity. User
   explicitly deferred this — needs a private key entered interactively and a real broadcast, with the
   user present. **Do not run `register_shield_with_funder.sh` as currently written** — it targets the
   wrong DID.
2. Untracked files from before this session, still untracked, related to that registration attempt:
   `integrity-core/contracts/fund-deployment-wallet.html`,
   `integrity-core/docs/runbooks/shield-registration-handoff-2026-09-11.md`,
   `integrity-core/scripts/register_shield_with_funder.sh`. Left alone deliberately — decide what to do
   with them alongside item 1.
3. The live systemd fix from `3569781` above (item under xibalba-shield) — needs root + user presence.
4. Run `integrity-sdk/scripts/seed_agent_subjects.py` yourself (see the AgentSubject section
   above) so the two real correspondences the audit found are actually recorded with you as the
   reviewing principal — not run automatically by this session.

## Orientation for whoever resumes

- Full findings: `integrity-core/docs/audits/tri-repo-audit-2026-09-12.md` (has its own §8 "what to do,
  in order" and §9 "corrections to the proposed spec" — still accurate as of this handoff except items
  marked done above).
- `forge`, `cargo`, `uv`, `nargo` are all installed in this environment — a prior session wrongly
  recorded `forge` missing; don't re-trust that claim without checking.
- `sqlite3` CLI is NOT installed — use python3's `sqlite3` module for any DB inspection.
- This machine has ~5GB RAM; running xibalba-shield's full pytest suite in one shot reliably OOMs. Chunk
  it (see the audit session's approach: split `tests/*.py` into groups of ~20 files).
- Real identities on Base Sepolia right now (verified via `resolveDID(string)` against
  `XibalbaAgentRegistry` `0x72e21e44AdD6d6e7CAa02eaedF078630afC40819`): `xibalba`, `xibalba-health`,
  `xibalba-quant` are registered; both Shield DIDs (`2ea17967…` and `b3324032…`) are not.
