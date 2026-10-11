# BCC signed policy pack: sign, dual-run, cut over, roll back

Operations for `bcc_middleware`'s move from `policies/bcc.rego` to the signed pack `packs/bcc`
(design and findings: `docs/design/bcc-shared-pack-migration.md`; code: `bcc_middleware/app/pack_policy.py`).
Nothing here is required to run BCC: with no pack configured it decides with `bcc.rego` as before.

## Decisions this runbook encodes

| Decision | Choice | Cost, stated |
|---|---|---|
| Rollout | **Dual-run, then flag** | Two policy evaluations per request until cutover (run concurrently; the pack can never change a response while `BCC_POLICY_ENGINE=rego`). |
| Pack-signing key | **Reuse Shield's operator key** (owner's decision, 2026-10-10) | One key now signs policy for two products: a leak of it lets an attacker sign a pack BCC and Shield would both trust. Mitigation here: pin the exact hash with `BCC_POLICY_PACK_HASH` so a *different* validly-signed pack is still refused. |
| Clinical allowlist | **A hot-reloaded file** | Replaces the unauthenticated `PUT /v1/admin/clinical-allowlist`, which is refused (409) in pack mode. An invalid file authorizes **no** extra agents. |
| Reasons | One reason code per denial (highest priority) | `bcc.rego` reported every violation message. The set of denials is unchanged. |

## 1. Sign the pack

Signing is `shield sign-pack` with the operator key (it signs the manifest and every file, and prints the
two values you need):

```bash
cp -r packs/bcc /secure/workdir/bcc-pack          # sign a COPY; never write signatures into the repo
shield sign-pack --pack-dir /secure/workdir/bcc-pack --key /path/to/operator-pack-key.pem
# OK   signed pack /secure/workdir/bcc-pack  pack_hash=sha256:...  signer_public_key=z6Mk...
```

* `signer_public_key` is `BCC_TRUSTED_PACK_SIGNERS` (comma-separate several during a key rotation).
* `pack_hash` is `BCC_POLICY_PACK_HASH`. Set it: it is what stops "a different pack, signed by the same key".
* The signed directory goes where BCC can read it read-only (`bcc_middleware/pack-config/pack/` for compose).
* Any edit to any file after signing (even whitespace) makes the pack fail verification. That is the point.

## 2. Start a dedicated OPA and the allowlist file

* Run an OPA that **only** BCC's pack uses (`opa-bcc-pack` in `docker-compose.yml`, `--profile policy-pack`) and
  point `BCC_PACK_OPA_URL` at it. Do not point it at the `opa` that serves `bcc.rego`, or at Shield's: the pack
  installer owns and replaces everything under one policy-id prefix, and every pack's file is `policy.rego`.
* Create `clinical-allowlist.json` with the same agents `bcc.rego` has in its data document
  (`GET /v1/admin/clinical-allowlist` shows them): `{"agents": ["did:integrity:..."]}`.
  Edit it by **atomic replace** (write a temp file, `mv` it over). A typo that breaks the JSON authorizes no extra
  agents until fixed; it does *not* keep a revoked agent. Watch `/health` → `policy.pack.allowlist.ok`.

## 3. Dual-run

Set `BCC_POLICY_PACK_DIR`, `BCC_TRUSTED_PACK_SIGNERS`, `BCC_POLICY_PACK_HASH`, `BCC_PACK_OPA_URL`,
`BCC_CLINICAL_ALLOWLIST_FILE` and restart. `bcc.rego` still decides.

* `GET /health` → `policy.pack.dual_run`: `compared`, `divergences`, `pack_errors`, `last_divergence`.
* Logs: `POLICY DIVERGENCE agent=... intent_type=...: <what differs>`.
* If the pack fails to load, BCC keeps running on `bcc.rego` and `/health` → `policy.pack_error` says why. Dual-run
  that is silently off proves nothing, so check this field.

**Do not cut over until** `divergences` is 0 over a period that includes your real traffic mix (every clinical
intent type, every agent-tool class), `pack_errors` is 0, and `allowlist.ok` is true. A divergence while you are
still editing the allowlist in two places (the file and the `PUT` endpoint) is expected; fix the file.

## 4. Cut over, and back

* Cut over: `BCC_POLICY_ENGINE=pack`, restart. In pack mode **the service refuses to start** if the pack does not
  verify or install, rather than quietly deciding with a different policy. If the pack's OPA is unreachable at
  request time every request is denied as `BCC_POLICY_ENGINE_UNAVAILABLE` and no agent's circuit breaker is
  charged. If that OPA restarts and forgets the pack, one request triggers a throttled re-install.
* `PUT /v1/admin/clinical-allowlist` returns 409 in pack mode; `GET` returns the file's current list.
* Roll back: `BCC_POLICY_ENGINE=rego`, restart. The pack stays loaded and keeps dual-running.

## 5. Signed decision receipts

Independent of the policy engine: works under `bcc.rego`, dual-run and pack mode.

1. Make an Ed25519 receipt-signing key (`integrity_sdk.did.Keypair.generate().private_pem()`) and a >= 32-byte HMAC
   key (`head -c 32 /dev/urandom`). Both files mode `0600`, readable only by the BCC user. Publish the signing
   key's multibase public key (`GET /health` -> `receipts.signer_key`) to whoever will verify.
2. Set `BCC_RECEIPT_DIR`, `BCC_RECEIPT_KEY_FILE`, `BCC_RECEIPT_HMAC_KEY_FILE` and restart. The service **refuses to
   start** if the log in that directory does not verify with this key (tampered, truncated below a checkpoint,
   another gate's, signed by a rotated key). Move it aside deliberately; there is no auto-repair.
3. **Strict is the default.** With `BCC_SHADOW_MODE=false`, an allow that cannot be recorded (disk full, I/O error)
   is denied as `BCC_RECEIPT_UNAVAILABLE` and the agent's breaker is not charged. Recovery needs no repair: a failed
   write never advances the chain. `BCC_LENIENT_RECEIPTS=true` trades that for availability. Shadow mode never blocks.
4. Verify offline, no BCC needed: put the epoch's `receipts.jsonl` lines and its newest checkpoint into a bundle
   `{"receipts": [...], "checkpoint": {...}}` and run `integrity verify --receipts bundle.json --trusted-signer <signer_key>`; or
   `integrity_sdk.core.verify_epoch_directory(dir, base_log_id=..., trusted_signers=[...])` for every epoch.
5. Watch `GET /health` -> `receipts` (`log_id`, `epoch`, `receipts_in_epoch`, `strict`). Responses carry
   `receipt` (`log_id`, `seq`, `hash`) and `receipt_status` (`recorded` / `failed` / absent).

What a receipt does **not** cover: denials before the signature verifies (open breaker, chain mismatch, bad
signature). Rotating the signing or HMAC key starts a new log; keep the old directory for audit. Nothing links an
epoch to the next, so deleting the newest epoch is undetectable unless closed epochs are anchored (section 7).

## 6. Replacing the pack without a restart

`POST /v1/admin/policy-pack/reload` (admin bearer token) with `{"expected_pack_hash": "sha256:..."}`.

1. Sign the new pack with a key already in `BCC_TRUSTED_PACK_SIGNERS` and put it in `BCC_POLICY_PACK_DIR` (replace the files
   there). Note its hash.
2. Call the endpoint naming that hash. The candidate is verified FIRST (signature, manifest, every file hash, expiry,
   declared event class) and must hash to what you named; a pack swapped on disk by someone else cannot be activated by a
   call that does not know its hash. Only then is it installed.
3. All-or-nothing: on any failure the previous pack keeps enforcing (HTTP 409 with the reason). If the install fails after
   verification, the previous pack is put back; if even that fails, **every decision denies** until a reload succeeds or
   the service restarts (CRITICAL in the log). Reloading the pack already running is a no-op (`changed: false`).
4. Decisions that start during the swap wait (up to 5 s) instead of being denied; a decision already in flight when OPA's
   policy is replaced fails closed as `BCC_POLICY_ENGINE_UNAVAILABLE` and is never charged to the agent. Nothing can be
   allowed by the wrong pack: each decision uses one snapshot of the pack for its hash, defaults and evaluated policy.
5. `GET /health` -> `policy.pack` shows the running `hash`, `reloads` and `last_reload`.

What a reload does **not** change: the trusted signers and `BCC_PACK_OPA_URL` (startup configuration; who may sign policy is
not a runtime call). It also does not edit `BCC_POLICY_PACK_HASH`: **if you pin it, update the pin when you reload**, or the
next restart will refuse the new pack, which is the pin working as designed. The reload is logged and counted but is not a
signed receipt `[PLANNED]`.

## 7. Anchoring closed receipt epochs

With receipt epochs on (section 5) set `BCC_RECEIPT_ANCHOR_ENABLED=true`. BCC then anchors each CLOSED epoch's signed final
checkpoint root on the dedicated evidence `StateAnchor` (the same signer, address and nonce lock as the Merkle-leaf
anchoring; `BCC_RECEIPT_ANCHOR_INTERVAL_SECONDS`, default 300), oldest first, and records it in `anchors.jsonl` in the receipt
directory. `POST /v1/admin/receipts/anchor` runs one sweep now; `GET /health` -> `receipts.pending_anchors` is what is waiting.

* **Best-effort.** An unreachable chain, a missing evidence-anchor address or a missing signer leaves the epoch pending and
  retried; a sweep stops at its first failure. It never blocks recording a receipt or a decision. If a closed epoch's final
  checkpoint no longer verifies, that is logged CRITICAL and nothing is anchored for it: investigate, do not retry.
* **Verify against the chain.** Collect the roots this gate anchored (the evidence anchor's `RootAnchored` events from the gate's
  anchoring account; the contract also holds other gates' and agents' roots) and run
  `verify_epoch_directory(dir, base_log_id=..., trusted_signers=[...], anchored_roots=[...])`. Every root must equal some
  epoch's final checkpoint root: one that matches none means an epoch was removed or rewritten. If `anchors.jsonl` survives, it
  is cross-checked against the epochs too.
* **What it does not cover.** The OPEN epoch is not anchored until it closes, so removing only the open epoch is undetectable
  for up to one epoch. `anchors.jsonl` is a worklist, not evidence: the signed checkpoints and the chain are. A root anchored
  on-chain whose ledger write then failed is anchored again next sweep (a duplicate root is harmless to verification).

## What is not built

A signed receipt for a pack reload itself (it is logged and counted on `/health`, not signed) `[PLANNED]`.
