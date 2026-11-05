# Supabase, Render, and Integrity Protocol Runtime Boundary

**Status:** Architecture contract for implementation planning  
**Date:** 2026-11-05  
**Scope:** integrity-core, xibalba-shield, xibalba-cortex, integrity-console

## Decision

Use Supabase as the shared application backend platform and Render as the
managed application runtime and UI platform:

- Supabase owns application persistence, authentication, tenant isolation,
  object storage, realtime delivery where needed, and narrowly scoped Edge
  Functions.
- Render hosts the browser UIs as static sites and runs the long-lived
  Integrity Protocol backend services that require Python processes, workers,
  chain RPC access, durable outbound queues, or controlled secret handling.
- Shield's endpoint sensor and deterministic enforcement remain on the managed
  device. A Supabase or Render outage must not turn a usable local Shield
  installation into an implicit all-deny configuration.
- Integrity cryptographic, BCC, Oracle, and chain authority remains in the
  Integrity Protocol services and SDK. Supabase is a persistence and delivery
  substrate, not a replacement authority.

This is intentionally a two-layer backend design. "Supabase for all backend"
means all SaaS state and browser-facing application data uses Supabase. It does
not mean moving the protocol's long-running authority processes into browser
JavaScript or pretending that Postgres is the BCC, Oracle, or chain.

The ecosystem is one product family but not one authority or one process. Core,
Shield, Cortex, and Console share identity, tenant context, deployment
operations, and evidence correlation; they keep separate service contracts,
data ownership, failure domains, and authority boundaries.

Supabase is the common data plane. Render is the common managed runtime. This
keeps Python services in a normal Python process model while avoiding a separate
database, authentication stack, and ad hoc frontend backend for each product.

## Target topology

```text
Browser
  |
  +--> Render Static Site: Shield UI
  +--> Render Static Site: Cortex UI
  +--> Render Static Site: Integrity Console UI
          |
          +--> Supabase Auth / Postgres / RLS / Storage / Realtime
          +--> Supabase Edge Functions for bounded application operations
          +--> Render protocol services over authenticated service APIs

Render protocol services
  +--> Integrity user/API service
  +--> BCC middleware and acceptance/receipt service
  +--> Oracle/AIS ingestion, scoring, and reporting service
  +--> chain anchoring and public-readback workers
  +--> Cortex managed API and background workers
  +--> Shield cloud control-plane API and command broker
          |
          +--> Supabase persistence, queues, audit metadata, and object storage
          +--> Integrity SDK and signed evidence primitives
          +--> external chains, RPC providers, and bounded integrations

Managed endpoint
  +--> Shield sensor, OPA policy, containment, redaction, and local outbox
          |
          +--> optional authenticated delivery to Render/Supabase
          +--> local enforcement continues during cloud unavailability
```

## Service ownership

| Service or data | Runtime / authority | Supabase role |
|---|---|---|
| Shield sensor and enforcement | Shield device; deterministic local authority | Store enrollment, cloud summaries, and delivery metadata only |
| Shield cloud control plane | Render private/web service | Store tenant/device state, commands, metrics, and indexes with RLS |
| Cortex local mode | Cortex process and local store | No dependency; remains the offline/local mode |
| Cortex managed API | Render web/private service | Store managed memories, sessions, provenance, retention metadata, and exports |
| Integrity user API | Render web/private service | Store accounts, profiles, API keys, and application metadata |
| BCC middleware | Render private worker/service | Store accepted-event metadata, nonce/circuit state snapshots, and durable queue references |
| Oracle/AIS | Render private worker/service | Store telemetry inputs, derived reports, and audit metadata; scoring authority remains Oracle |
| Chain anchoring/readback | Render worker with bounded RPC credentials | Store queued jobs, transaction references, and readback evidence; chain remains authoritative |
| Signed receipts and evidence | Integrity SDK/core services | Store indexed copies or export objects; signatures and canonical bytes remain independently verifiable |
| UI assets and static bundles | Render Static Sites | No private credentials or service-role keys |

## Non-negotiable boundaries

1. Browser clients use Supabase's publishable/anonymous key only. Supabase
   service-role keys, chain keys, BCC secrets, Oracle signing keys, and Shield
   control-plane secrets never ship to a Render static site.
2. Every tenant-owned Supabase table has RLS enabled before production data is
   connected. Policies bind access to authenticated subject and tenant
   membership, not to a UI-supplied tenant identifier.
3. Edge Functions are adapters and bounded application operations. They do not
   replace the Integrity SDK, BCC acceptance, Oracle scoring, Shield OPA policy,
   or chain finality.
4. Signed receipts, Merkle roots, canonical payloads, and anchors remain
   independently verifiable without trusting Supabase row contents.
5. Shield local enforcement remains available without Supabase, Render, Cortex,
   Oracle, or a public chain. Cloud delivery failure is an evidence/telemetry
   condition, not permission to rewrite local policy.
6. Cortex local mode remains supported. Supabase-backed managed memory is a
   separate deployment mode with explicit synchronization and provenance rules.
7. Protocol services are independently deployable and health-checked. A green
   UI deployment is not evidence that BCC, Oracle, chain anchoring, Shield
   control-plane, or Cortex managed APIs are live.
8. Each environment has its own Supabase project and Render service group:
   development, staging, and production are not mixed in one database or one
   service namespace.
9. The Console does not become a second backend authority. It calls product
   APIs or bounded Supabase functions and renders their results; it does not
   implement Shield policy, Cortex provenance, Oracle scoring, BCC acceptance,
   or chain truth.

## Supabase project and schema model

Use one Supabase project per environment, with ownership-separated schemas and
RLS policies rather than one unbounded public schema:

| Schema | Owner | Examples |
|---|---|---|
| `identity` | shared account boundary | tenant membership, roles, product entitlements |
| `shield` | Shield cloud control plane | devices, enrollment, commands, metrics, delivery state |
| `cortex` | Cortex managed mode | stores, sessions, memories, provenance, retention, exports |
| `integrity_ops` | Integrity operations | outbox metadata, audit indexes, anchor jobs, service health |
| `console` | Console presentation | saved views, operator preferences, cross-product read-model references |

The exact schema names may change during migration, but ownership must remain
explicit. Python services use restricted database roles or server-side service
credentials. Browser clients use the publishable key and RLS-safe operations.
The service-role key is never a frontend build variable.

Render services should expose product APIs rather than requiring the browser to
coordinate direct writes across `shield`, `cortex`, and `integrity_ops`. A
Supabase Edge Function is appropriate for a small, bounded transaction or
webhook adapter; it is not the default runtime for protocol workers.

## Required Render services

The deployment target must make these services explicit rather than hiding all
backend behavior inside one UI service:

- `integrity-userapi`
- `integrity-bcc`
- `integrity-oracle`
- `integrity-anchor-worker`
- `cortex-managed-api`
- `shield-control-plane`
- `shield-ui` (static)
- `cortex-ui` (static)
- `integrity-console-ui` (static)

The exact process split may be reduced after measured resource and failure-mode
testing, but each authority and health contract must remain independently
observable. Combining processes for cost is acceptable; combining authority is
not.

## Migration order

1. Define Supabase migrations, RLS policies, auth claims, storage buckets,
   idempotency keys, audit records, and service-role boundaries.
2. Stand up Render health-checked protocol service skeletons with no production
   credentials and verify startup, readiness, and dependency reporting.
3. Move Cortex managed persistence from service-local storage to Supabase while
   retaining local SQLite mode and provenance compatibility.
4. Move Shield cloud control-plane persistence to Supabase while keeping local
   enforcement and outbox semantics unchanged.
5. Deploy the Integrity user API, BCC, Oracle/AIS, and anchoring workers on
   Render with explicit queue, retry, key, and chain-readback evidence.
6. Convert Shield, Cortex, and Integrity Console to independent Render static
   sites backed by authenticated Supabase/Render service APIs.
7. Run tenant-isolation, auth-revocation, outage, replay, receipt-verification,
   chain-readback, and browser journeys before retiring any existing backend
   deployment.

## Readiness evidence

The following claims must remain separate:

- Supabase schema and RLS tests are not live tenant-isolation proof until run
  against the deployed project.
- Render build success is not protocol-service readiness.
- A healthy API is not evidence of BCC acceptance, Oracle scoring, or chain
  finality.
- A browser-rendered UI is not live-provider evidence unless it is explicitly
  run against the deployed services with authenticated test data.
- Local signed receipts and queued anchors do not prove public-chain finality.

The deployment plan must report these evidence classes independently for each
service and each product.
