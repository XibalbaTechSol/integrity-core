# Archive and cutover plan (planning only — no git operations until approved)

**Scope:** `XibalbaTechSol/integrity-core`, `xibalba-shield`, `xibalba-cortex`
**Rule:** `git mv` into `docs/archive/<date>/`. Do not rewrite archived files. Do not delete.
**When:** After these three drafts are approved and merged as the new constitution. Not before.

Every README after cutover carries:

```text
Canonical documents
- docs/WHITEPAPER.md          public narrative
- docs/SPEC.md                normative protocol
- docs/CONTROLS_MATRIX.md     auditor map
- docs/IMPLEMENTATION_PLAN.md build order (informative)

Everything else under docs/archive/ is historical.
Working notes go in /notes and are deleted or merged within 14 days.
PRs that add a new "source of truth" without retiring an old one will be rejected.
```

---

## A. integrity-core — freeze one constitution

### Become canonical (new files, this session's drafts)

| Path | Role |
|---|---|
| `docs/WHITEPAPER.md` | Public v1 narrative |
| `docs/SPEC.md` | Normative Integrity Protocol v1 |
| `docs/CONTROLS_MATRIX.md` | Auditor map |
| `docs/IMPLEMENTATION_PLAN.md` | Build order; not normative |
| `docs/ARCHIVE_PLAN.md` | This file, until cutover finishes |
| `README.md` | Rewrite to 1 page: problem, guarantee, three products, canonical doc links, "archived material is not normative" |
| `docs/archive/README.md` | "Do not implement from these." |

### `git mv` into `docs/archive/2026-08/`

These currently compete with the constitution. After the move they are provenance, not requirements.

**Prior protocol specs and whitepapers**

- `spec/integrity-protocol-v0.4.md`
- `spec/integrity-protocol-v0.5-proposed.md`
- `spec/integrity-protocol-v3.2.md` (if present; repo README claims it)
- `docs/releases/Integrity_Protocol_Whitepaper_v3.1.html`
- `docs/releases/Integrity_Protocol_Whitepaper_v3.1.pdf`
- `docs/releases/Integrity_Protocol_Whitepaper_v3.1_designed.html`
- `docs/releases/Integrity_Protocol_Whitepaper_v3.1_designed.pdf`
- `docs/releases/Integrity_Protocol_Whitepaper_v3.1_rendered.html`
- `integrity-dashboard/public/integrity-protocol-specification-v0.3.pdf`

**Repo-level "second constitutions"**

- `SPECIFICATION.md` (repository-ownership spec; its useful bits fold into README + `docs/INTERFACE_CONTRACT.md`)
- `IMPLEMENTATION_PLAN.md` (ledger of the old plan; freeze as of cutover date)
- `HANDOFF.md`

**Phase-1 proposal pile (the old kernel-tracer-bullet plan, not Freeze Core)**

- `docs/plans/2026-08-17-*.md`
- `docs/plans/2026-08-18-*.md`
- `docs/design/phase1-*.md`
- `docs/design/three-foundational-primitives.md`
- `docs/design/thesis-extensions-formal.md`
- `docs/design/primitive-set-coherence.md`

**Wiki-as-constitution**

- `docs/wiki/concepts/integrity-specification.md`
- `docs/wiki/WIKI_INDEX.md` (already marked legacy)
- Leave `docs/wiki/` itself in place for now as working memory, but strip any "current status" claims that contradict `docs/SPEC.md`. A later pass can archive the whole wiki; doing it in the same PR as the constitution is optional, not required.

### Keep where they are (operational, not protocol)

| Path | Why it stays |
|---|---|
| `docs/INTERFACE_CONTRACT.md` | Package ports, env, coordination — engineering contract, not a second protocol |
| `PRODUCTION_GAPS.md` | Gap register; add a header pointing at `docs/SPEC.md` as protocol authority |
| `docs/MAINNET_READINESS.md` | Consequence-ordered blockers |
| `docs/audits/` | Evidence, dated |
| `docs/packs/trading/` | Working pack draft; not canonical protocol. Move to `notes/packs/trading/` or leave with a header "not v1 kernel" |
| `contracts/`, `bcc_middleware/`, `integrity-oracle/`, `integrity-sdk/`, `integrity-cli/`, `integrity-dashboard/` | Code. Docs follow code; code is not archived |

### README rewrite (substance, not the full text)

After cutover the root README says, in this order:

1. One-paragraph problem (the compliance gap).
2. One-paragraph guarantee (constrain / record / escalate).
3. Three-product diagram: Core / Shield / Cortex, with Core owning the hook + oracle, Shield and Cortex as producers.
4. Links to the three canonical docs.
5. Honest implementation status by pointing at `SPEC.md` §13 — no aspirational current tense.
6. "Archived material is not normative."

Drop: biological analogy as the primary explanation, token/markets as current surfaces, "four foundational primitives" as the public story, EU AI Act as spine.

---

## B. xibalba-shield — product spec only

Shield already has `SPECIFICATION.md` and a `docs/archive/2026-08-06/` folder. The job is to stop it from implying it *is* the protocol.

### Keep

- `README.md` (edit: ecosystem section points at `integrity-core` `docs/WHITEPAPER.md` + `docs/SPEC.md`, not at v0.4 / v3.2)
- `SPECIFICATION.md` (product spec — device/network/enforcement)
- `docs/wiki/` as product working memory
- `docs/runbooks/`, `docs/audits/`, `docs/ASSETS.md`

### `git mv` into `docs/archive/2026-08/`

- `docs/design/2026-08-18-a2a-escalation-schema-proposal.md`
- `IMPLEMENTATION_PLAN.md` (old ledger)
- `docs/archive/2026-08-06/HANDOFF.md` is already archived; leave it

### Drive counterparts (already classified, do not re-edit)

- `ARCHIVED — Xibalba Shield State-Graph Product Vision.md`
- `RESEARCH A — Xibalba Shield Endpoint Security Architecture`
- `RESEARCH B — Xibalba Shield AI-Native Endpoint Blueprint`

These stay on Drive as `ARCHIVED` / `RESEARCH`. Do not import them back into the repo.

### README sentence to add

> Integrity Protocol is specified in [`XibalbaTechSol/integrity-core`](https://github.com/XibalbaTechSol/integrity-core) `docs/SPEC.md`. This repository does not define protocol invariants. Shield is a producer of signed evidence and a local enforcement agent.

---

## C. xibalba-cortex — product spec only

Cortex already froze a product v1 (`SPECIFICATION.md`, `spec/xibalba-cortex-v1.md`) on 2026-08-12. Do not rewrite that product spec. Do stop it from colliding with the protocol oracle.

### Keep

- `README.md` (edit: ecosystem section — Cortex is a **producer** of session roots into the Integrity oracle; it is not the verifier)
- `SPECIFICATION.md` and `spec/xibalba-cortex-v1.md` (product)
- `docs/operations/`, `docs/integrity/xibalba-cortex-crypto-profile-v1.md`
- `docs/wiki/` as product working memory
- `docs/audits/`

### `git mv` into `docs/archive/2026-08/`

- `docs/plans/2026-08-05-xibalba-advanced-memory.md`
- `docs/plans/2026-08-13-*.md`
- `docs/research/2026-08-05-agent-memory-landscape.md`
- `docs/session-log/2026-08-05-integrity-coupling-session.md`
- `IMPLEMENTATION_PLAN.md`
- `docs/archive/2026-08-06/` is already archived; leave it
- `spec/latest-hybrid-extraction.md` — working note; archive or move to `notes/`

### README sentence to add

> Session Merkle roots MAY be anchored into Integrity Protocol's oracle. Cortex is not the Integrity oracle and MUST NOT be described as a second verifier. Protocol specification: `integrity-core` `docs/SPEC.md`.

---

## D. Drive

Drive is already classified (INDEX dated 2026-08-05). Do not silently rewrite those files.

After GitHub cutover, add one line to the Drive INDEX (new version, new file id per the INDEX's own rule):

> As of YYYY-MM-DD the normative Integrity Protocol sources are GitHub `XibalbaTechSol/integrity-core` `docs/SPEC.md`, `docs/WHITEPAPER.md`, and `docs/CONTROLS_MATRIX.md`. Drive copies of v0.3 / research notes remain `ARCHIVED` / `RESEARCH`.

Do not upload the new constitution to Drive as a competing source of truth. If a Drive snapshot is wanted, label it `RELEASE — Integrity Protocol v1.0.0-draft` and pin the git commit.

---

## E. Cutover sequence (when you say go)

1. Open branch `docs/v1-constitution` on `integrity-core`.
2. Add `docs/archive/README.md`.
3. `git mv` the archive list in §A.
4. Add `docs/WHITEPAPER.md`, `docs/SPEC.md`, `docs/CONTROLS_MATRIX.md`, `docs/IMPLEMENTATION_PLAN.md`.
5. Rewrite root `README.md`.
6. Open analogous branches on `xibalba-shield` and `xibalba-cortex` for the README sentence + archive moves in §B and §C.
7. Do not touch Solidity, middleware, or product code in the same PR.
8. Stop. No new plans until a stranger can read the two (three) docs without asking which version is real.

---

## F. What this plan deliberately does not do

- Rename packages, redeploy contracts, or start `integrity-core-v1` as a second implementation repo.
- Archive `PRODUCTION_GAPS.md` or `docs/INTERFACE_CONTRACT.md`.
- Fold Shield or Cortex product specs into the protocol spec.
- Treat the experimental kernel slice as production complete-mediation.
- Publish a token chapter, a market, or an EU-master-spec.
