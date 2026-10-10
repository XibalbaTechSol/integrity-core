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

## What is not built

Hot reload of the pack itself (a new pack is a restart); receipts from BCC (stage 3: one shared writer in
`integrity-sdk`); shared conformance vectors (stage 4); authentication on the admin endpoints (see the finding
in the design doc).
