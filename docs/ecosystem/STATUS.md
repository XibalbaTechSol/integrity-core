# Ecosystem Status

This is the current-gap register. It is intentionally short; historical plans and completed evidence belong in the archive.

## Required before Phase A outcome gate

- Create the canonical documentation namespace and archive competing active plans.
- Define the four-repository worktree map and preserve existing dirty/broken worktrees.
- Publish SDK JCS, identity, pack, receipt, memory, tenant, and verification contracts.
- Prove Shield/BCC pack-hash and deny-by-default conformance.
- Prove Cortex authenticated ingestion, provenance binding, and tenant/store isolation.
- Define signed DID-file rotation and universal Shield/BCC fail-closed fallback.
- Give the SDK's shipped fail-open hooks (`integrity_sdk.hook_runner`) a watched health signal (a user-visible alert on unchecked allows). A 3.12→3.14 interpreter change left the BCC hooks failing open from 2026-09-28 to 2026-11-14 unnoticed; see WIKI_LOG 2026-11-14. The operator workstation is covered as of 2026-11-14 (an in-session warning plus a 15-minute out-of-band check); customer installs are not.
- Publish pure pack-adapter versus network-connector contracts.

## Required before Gate B-local

- Demonstrate a single-tenant customer-local or managed single-tenant pilot.
- Prove tenant isolation, device revocation, entitlements, retention, purge, export, and queue recovery.
- Keep optional Jev/DecisionTrace out of core authorization and make its absence non-blocking.

## Required before Gate C

- Select one account-authorization model and prove kernel mediation.
- Verify canonical account implementation and reject unapproved proxies/upgrades.
- Prove provider-backed memory spot-checks and purge behavior.
- Complete registration, approval replay, rescue recovery, and regenesis evidence.

## External or deferred

- Testnet StateAnchor deployment, Oracle connectivity, Vanta sandbox, hosted Jev, hosted multi-tenant scale, billing, payment processing, additional harness hooks, and real-PHI operation remain separate gates or deferred work.
