# Integrity Protocol — wire-protocol specs

This directory holds the **versioned, externally-supported wire surfaces** of Integrity
Protocol — the interfaces third-party tooling/SDKs/agent frameworks can integrate
against directly, without cloning or reading this whole monorepo.

This is deliberately separate from [`docs/INTERFACE_CONTRACT.md`](../docs/INTERFACE_CONTRACT.md),
which stays exactly what it already is: an internal coordination document for the
engineers (human or agent) building the packages in this repo. `docs/INTERFACE_CONTRACT.md`
can and does change as internals get reworked; the specs here are the promises made to
people outside this repo.

## The design specification

[`integrity-protocol-v0.4.md`](integrity-protocol-v0.4.md) is the **normative design
specification** — foundational primitives, AIS, memory, authority, interop. It supersedes
`Integrity_Protocol_Specification_v0.3.pdf`.

It lives here, in markdown and under version control, deliberately: a specification that
cannot be diffed, reviewed in a pull request, or kept in step with the code by any mechanism
other than someone remembering is a coherence problem in a protocol whose premise is
independently checkable state.

Note it is a different kind of document from the wire surfaces below: the spec states what the
protocol *is*; the surfaces are the interfaces third parties integrate against.

## Surfaces

| Surface | Status | Directory |
|---|---|---|
| AIS API (read-side: agent identity, AIS score, compliance, markets, wallet) | v1, frozen | [`ais-api/`](ais-api/) |
| BCC intent schema (write-side: pre-execution intent commitments) | not yet started | `bcc/` (planned) |
| Xibalba Shield protocol-facing boundary | v1 companion spec | [`xibalba-shield-v1.md`](xibalba-shield-v1.md) |

## Specification ownership

The Integrity Protocol spec owns protocol primitives, invariant rules, and externally-supported wire surfaces. Xibalba Shield is a separate endpoint-security product that consumes those primitives. Its comprehensive implementation specification lives in XibalbaTechSol/xibalba-shield as SPECIFICATION.md; this repo keeps spec/xibalba-shield-v1.md as the protocol-facing companion so the dependency boundary is reviewable with the protocol.

A Shield implementation change that only affects endpoint behavior belongs in the Shield repo. A change that alters BCC, telemetry ingest, AIS computation, Merkle anchoring, delegation, or public wire shape belongs here and must update the relevant Integrity spec/interface docs.

## Versioning policy

Sized for a single-vendor-operated API (think Stripe/OpenAI API versioning), not a
neutral multi-implementer standards process — no RFC process, no external governance
body, no formal deprecation committee.

- **Additive-only within a major version.** `/v1/*` may only gain new optional fields
  and new endpoints for its lifetime. Any field rename, type change, or removal
  requires a `/v2/*` prefix.
- **Semver applies to wire shape and semantics, not to computed values.** An agent's
  AIS score changing because the scoring weights were retuned is not a breaking
  change. Renaming the `ais` field, or changing what its numeric range means, is.
- **Unbuilt/unenforced semantics are marked, never silent.** Any field that ships on
  the wire before its behavior is fully built (example: `verification_tier`, which is
  accepted and echoed back today but not yet enforced by anything) is documented as
  **RESERVED** in its surface's README/schema, not left to imply a guarantee that
  doesn't exist yet. This is the direct fix for the kind of drift that already caused
  one real bug (`docs/INTERFACE_CONTRACT.md` §6.3's `agent_id`/`did` field-name
  mismatch) — silence about a field's actual guarantee level is what let that happen.
- **Deprecation window**: when a breaking change requires a `/v2`, the old surface
  stays live and documented for a minimum of 90 days after `/v2` ships, or until
  explicitly announced otherwise. This is a stated intention appropriate to an
  early-stage, single-operator protocol, not a formal SLA.
- **Generated, not hand-authored.** Each surface's schema artifact (`openapi.yaml`,
  `schema.json`, ...) is generated directly from the source code that implements it
  (see each surface's own README for the generation command), specifically so the
  spec can't silently drift from what the code actually does.

## Adding a new surface

1. Create `spec/<surface>/v1/`.
2. Generate the schema artifact from source rather than hand-writing it.
3. Write a `README.md` with a base URL/auth/example-request integration guide, plus an
   explicit statement of the versioning policy above (or a link back to this file).
4. Start a `CHANGELOG.md` (Keep-a-Changelog style, one entry per wire-visible change —
   not per commit) with a `v1.0.0 — initial published surface` entry.
