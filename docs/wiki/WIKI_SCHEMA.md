# Integrity Protocol Wiki — Schema (v1)

## Domain
The compiled knowledge base for the Integrity Protocol monorepo: on-chain
agent identity/reputation, zero-knowledge attestation, behavioral policy
gating, off-chain scoring, and the SDK/CLI/dashboard/demo that use them.

## Conventions
- **Canonical source**: `INTEGRITY-LATEST/docs/wiki/` on the main branch is the
  only authoring source of truth. The Integrity MVP `/wiki` route and the
  repository's GitHub Wiki are generated, read-only projections of these files.
  Do not author or reconcile content in a downstream mirror; the next sync may
  overwrite it.
- **Table of contents**: every canonical article contains a generated
  `## Table of contents` block covering its level-two and level-three headings.
  Run `python3 scripts/wiki_toc.py` after heading changes and
  `python3 scripts/wiki_toc.py --check` in validation. Do not hand-edit the
  generated block.
- **Filenames**: lowercase, hyphenated, `.md` (e.g. `behavioral-commitment-chain.md`).
- **Solidity contracts**: document the contract suite in `entities/contracts.md` by default. Create a dedicated `entities/<Contract>.sol.md` page only when a contract needs deep standalone API documentation that would make the aggregate page hard to navigate.
- **Wikilinks**: use `[Title](relative/path.md)` to interlink entities/concepts/acronyms. Minimum 2 outbound links per page.
- **Frontmatter**: required on every page (template below).
- **Index sync**: every new page is added to `WIKI_INDEX.md` in the same pass it's created.
- **Append log**: every creation/update is logged in `WIKI_LOG.md` (append-only).
- **No aspirational content**: only document what exists in the code. Planned-but-unbuilt is marked `[PLANNED]`.
- **No duplication**: each fact lives on exactly one canonical page; others link to it.
- **Code over prose**: include real function signatures, schemas, or CLI commands, not paraphrase.

## Frontmatter template
```yaml
---
title: Page Title
acronyms: [optional, e.g. AIS, BCC]
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: entity | concept | comparison | query
tags: [see taxonomy below]
confidence: high | medium | low
source_files:
  - relative/path/to/file
---
```

### Confidence scoring
| Level | Meaning |
|---|---|
| `high` | Verified against source within the last 14 days |
| `medium` | Previously verified; source may have changed since — needs review |
| `low` | Carried over from a spec/plan, not yet verified against real code |

## Tag taxonomy
- `cryptography` — ZK proofs, hashing, signing
- `identity` — DIDs, key management
- `compliance` — HIPAA/OPA policy, guardrails
- `metrics` — AIS formula, scoring
- `tokenomics` — staking, slashing, $ITK
- `layer-2` — on-chain registries, anchoring
- `sdk` — client libraries, integrations
- `infrastructure` — oracle, middleware, deploy, CI

## Directory structure
- `entities/` — packages, services, and contract suites (aggregate pages are preferred when they keep one canonical owner for related contract facts)
- `concepts/` — protocols, algorithms, cryptographic conventions shared across packages
- `architecture/` — cross-cutting data-flow / sequence docs
- `queries/` — open research questions, investigation notes (not conclusions)

## Publication flow

```text
INTEGRITY-LATEST/docs/wiki
        ├── scripts/sync_wiki.py ──> GitHub Wiki
        └── integrity-mvp/scripts/sync-wiki.mjs ──> Integrity MVP /wiki
```

The GitHub Wiki mirror is flattened to satisfy GitHub Wiki routing, while the
MVP stores a generated JSON snapshot for fast rendering. Those packaging
differences do not create independent content ownership.

## Source binding rule
Every entity page's `source_files` must list real files that exist right
now. If a listed file is deleted or renamed, the page is stale — fix it or
remove the page in the same pass that changes the code.
