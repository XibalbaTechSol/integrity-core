# bcc_middleware pack configuration (mounted read-only at `/pack-config`)

Runtime inputs for the signed policy pack. Nothing here is built into the image, and nothing in this
directory except this file and `.gitignore` is tracked.

| Path | What it is |
|---|---|
| `pack/` | A **signed** copy of `packs/bcc` (it must contain `pack.sig.json`). Produced by the signing step in `docs/runbooks/bcc-policy-pack.md`. |
| `clinical-allowlist.json` | `{"agents": ["did:integrity:..."]}`, the extra agents allowed to commit clinical intents. Re-read when it changes; an invalid file authorizes **no** extra agents. Edit it by atomic replace (write a temp file, `mv` over it). |

Enable with `BCC_POLICY_PACK_DIR=/pack-config/pack` and `BCC_CLINICAL_ALLOWLIST_FILE=/pack-config/clinical-allowlist.json`
(see the `bcc-middleware` service in `docker-compose.yml`). With neither set, bcc.rego decides alone.
