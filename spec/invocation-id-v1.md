# Invocation Correlation Profile v1

**Status:** Accepted cross-repository wire profile  
**Version:** `xibalba.invocation.v1`  
**Date:** 2026-08-28

## Purpose

`invocation_id` identifies exactly one attempted action from pre-execution intent through policy,
execution, effect reporting, and investigation. It is distinct from:

- `intended_state_hash`, which identifies canonical intent *content* and therefore repeats when
  the same tool and input repeat;
- BCC `nonce`, which orders commitments for one agent but is not the shared runtime correlation
  key;
- provider `tool_call_id`, which may be scoped to one runtime or session;
- OTel trace/span identifiers, which describe telemetry topology rather than protocol identity;
- Shield `event_id`, which identifies one normalized endpoint event.

## Canonical representation

- JSON field name: `invocation_id`.
- Value: lowercase RFC 4122 UUID string in canonical 8-4-4-4-12 form.
- Producers SHOULD generate UUIDv4 before policy evaluation.
- An adapter MAY generate UUIDv5 from a collision-resistant namespace plus a runtime-native,
  session-scoped call identifier when it must reproduce the same ID independently in pre- and
  post-tool hooks.
- Empty strings, noncanonical forms, and nil UUIDs MUST be rejected by strict wire validators.
- The identifier is opaque. Consumers MUST NOT infer time, tenant, identity, or authorization
  from it.

## Lifecycle

1. The earliest component observing a proposed protected action creates the ID.
2. Every downstream record copies the exact value; no component remints it for the same attempt.
3. A retry that can cause a second external effect receives a new `invocation_id` and carries an
   explicit causal/idempotency reference separately.
4. A reporting retry for the same already-produced effect reuses the original `invocation_id`.
5. Pre-intent, Shield decision, BCC commitment, execution result, effect report, Cortex event,
   Oracle audit row, and outcome label use the same value when they describe the same attempt.

## Trust and signing

When present on a BCC commitment, `invocation_id` is part of the Ed25519-signed canonical
commitment payload. Middleware MUST reject a signature produced before insertion or after
substitution of the ID.

The field is additive for migration. A commitment without it remains parseable as a legacy
commitment, but downstream reconciliation MUST label it `legacy_hash_only` and MUST NOT claim an
unambiguous intent/outcome match merely because `intended_state_hash` matches.

## Component obligations

### integrity-sdk

- `invoke_intent` generates a UUID when the caller does not supply one.
- `build_bcc_commitment` validates and signs a supplied ID.
- post-tool effect reports require the same ID.
- OTel spans expose it as `integrity.invocation.id`.

### bcc_middleware

- validates canonical UUID form;
- includes it in signature verification when present;
- records it on the durable ALLOW audit metadata;
- preserves legacy verification when the field is absent.

### integrity-oracle

- effect ingest requires a UUID;
- reconciliation joins new records only by `invocation_id`;
- repeated content hashes do not merge distinct invocations;
- records without the ID remain visible as legacy evidence.

### xibalba-shield

- every `PolicyDecision` has an invocation ID;
- an instrumented `AgentEvent` may supply the upstream ID;
- otherwise Shield generates a new ID for the endpoint action it observed;
- exporter passes the decision ID into an SDK version supporting this profile;
- local decision and export status retain the ID even when remote export fails.

### xibalba-cortex

- runtime bridge v2 stores `invocation_id` as a first-class event field;
- pre- and post-tool events use the same value;
- the Claude adapter deterministically derives UUIDv5 from
  `(runtime, session_id, tool_call_id)` only when no canonical upstream ID is supplied;
- investigation joins prefer `invocation_id`; `tool_call_id` fallback is visibly legacy.

## Reconciliation states

- `reconciled`: exactly one intent and an outcome share a non-null `invocation_id`.
- `intent_without_outcome`: intent exists but no outcome exists for the ID.
- `outcome_without_intent`: outcome exists but no authorized intent exists for the ID.
- `duplicate_invocation`: more than one logically distinct intent or effect claims the ID.
- `correlation_conflict`: the ID matches but the outcome reports a different
  `intended_state_hash`; consumers MUST NOT classify this as reconciled.
- `legacy_hash_only`: one or both records predate this profile and can only be compared by
  content hash; this is not an unambiguous reconciliation.

## Security boundary

An invocation ID provides correlation, not truth. It does not prove that the action occurred,
that its effect report is accurate, that the caller was authorized, or that evidence is
complete. Those properties require signed intent, deterministic policy, independently observed
effects, receipt verification, and the relevant Integrity/Shield/Cortex evidence checks.

The Oracle's authoritative `posttool_effect` record takes precedence over an equivalent telemetry
projection. A telemetry copy carrying the same `invocation_id` MUST NOT be counted as a second
logical outcome. Conflicting reuse, however, remains visible and MUST NOT overwrite the first
durable outcome.
