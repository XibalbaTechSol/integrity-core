# Documentation migration manifest

## Authority

The active cross-product authority is the `docs/ecosystem/` namespace:

- `INTEGRITY_ECOSYSTEM_PLAN.md` — outcomes, sequencing, gates, and non-goals;
- `ECOSYSTEM.md` — product and authority boundaries;
- `DATA.md` — data, retention, purge, provider, and evidence boundaries;
- `STATUS.md` — current open gaps only;
- `ADR-0001-six-function-test.md` — scope and authority test.

`docs/SPEC.md` remains the normative protocol grammar and invariant authority. `DOCUMENT_STATUS.yaml` is the machine-readable pointer to document authority.

## Classification rules

| Class | Treatment |
|---|---|
| Current protocol grammar or invariant | Keep authoritative in `docs/SPEC.md` or a linked ADR |
| Current cross-product plan or boundary | Merge into `docs/ecosystem/` |
| Repository-local implementation or runbook | Keep in its repository; it must not redefine cross-product authority |
| Historical plan, handoff, audit, or superseded proposal | Move to the dated archive and mark historical |
| Generated wiki or compiled projection | Treat as a derived view; never edit it as the source |
| Duplicate normative register | Remove after its authoritative replacement is linked |

## Initial migration performed

- The former `docs/EXECUTION_PLAN.md` is preserved at `docs/archive/2026-11/EXECUTION_PLAN-superseded.md`.
- `docs/EXECUTION_PLAN.md` is now a compatibility redirect.
- `docs/DOCUMENT_STATUS.yaml` points to the canonical ecosystem namespace.
- Active README and plan references are updated to the canonical plan.
- Cortex, Shield, and Console each expose a local documentation-authority pointer.

## Remaining migration gate

Before Gate A closes, every active Markdown document must be classified, duplicate normative claims must be removed or linked, and CI must check links, authority pointers, and the `STATUS.md` line cap. Archive and wiki history must not be silently rewritten.
