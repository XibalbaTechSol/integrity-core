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

## Not started — still "all of the above"

1. **AgentSubject persistence** (§4.1/§11 Gate 1 bullet 1) — real design work, not done. Open questions:
   where does it live (new contract? off-chain index in Cortex? a new integrity-sdk module?), what's the
   minimal schema per §4.1's table, how does it map to the existing `did:integrity:` + `XibalbaAgentRegistry`
   on-chain model without duplicating authority. Start by rereading spec §4.1–§4.3 and
   `docs/wiki/concepts/foundational-primitives.md`.
2. **ERC-8004 revision content hash** (§5.1) — revision `ethereum/ERCs@503591a6e80e6e1affdd6403341e25269141f046`
   is already pinned in `contracts/src/kernel/IntegrityERC8004Registry.sol:36` and
   `docs/INTERFACE_CONTRACT.md:521`, but no content hash accompanies it. Needs fetching the actual
   referenced ERC document at that commit and hashing it — will need `WebFetch` (deferred tool, not yet
   loaded this session).
3. **The actual on-chain registration** — repoint `scripts/register_shield_with_funder.sh` (or a new
   script) at the SDK-store DID `2ea17967f7a65589d570ca7e800844701fb36e6aa7374243e8766de8651f6bc4`
   (confirmed unregistered on Base Sepolia per the audit's §2.1 on-chain readback — no history to
   preserve, so this is the right target) rather than the CLI-store `shield-replacement` identity. User
   explicitly deferred this — needs a private key entered interactively and a real broadcast, with the
   user present. **Do not run `register_shield_with_funder.sh` as currently written** — it targets the
   wrong DID.
4. Untracked files from before this session, still untracked, related to that registration attempt:
   `integrity-core/contracts/fund-deployment-wallet.html`,
   `integrity-core/docs/runbooks/shield-registration-handoff-2026-09-11.md`,
   `integrity-core/scripts/register_shield_with_funder.sh`. Left alone deliberately — decide what to do
   with them alongside item 3.
5. The live systemd fix from `3569781` above (item under xibalba-shield) — needs root + user presence.

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
