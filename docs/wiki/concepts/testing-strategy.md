---
title: Testing Strategy
created: 2026-07-09
updated: 2026-09-08
type: concept
tags: [infrastructure]
confidence: high
source_files:
  - docs/TESTING.md
  - docs/CONTRIBUTOR_VALIDATION.md
  - Makefile
  - .github/workflows/ci.yml
  - integrity-dashboard/package.json
  - integrity-dashboard/playwright.config.ts
  - integrity-dashboard/e2e/test-utils.ts
---

The full package, browser, and hosted Continuous Integration (CI) boundaries
live in [`docs/TESTING.md`](../../TESTING.md). This page is the canonical wiki
summary.

## Table of contents

- [Validation layers](#validation-layers)
- [Dashboard boundary](#dashboard-boundary)
- [Ground rule](#ground-rule)
- [Convention going forward](#convention-going-forward)

## Validation layers

```mermaid
flowchart TB
    L1["Local package validation (make test)<br/>forge / nargo / cargo / pytest<br/>dashboard build + lint"]
    L2["Playwright E2E (make test-e2e)<br/>real Chromium; backend stack<br/>prepared separately"]
    L3["GitHub Actions<br/>package jobs on push/PR to main<br/>Playwright excluded"]

    L1 --> L2
    L1 --> L3
```

1. **Package validation** (`make test`) runs the Solidity, Noir, Rust, and Python
   suites, then validates the dashboard with
   `npm run build && npm run lint`. The
   root runner records every suite against one run ID and tested-tree hash, runs
   all declared suites, and fails at finalization if any result is missing,
   mixed-tree, malformed, or red. Test counts are intentionally not frozen here.
2. **Playwright end-to-end** (`make test-e2e`) drives the real Vite application
   in Chromium. `playwright.config.ts` starts only the frontend. Chain, Oracle,
   middleware, databases, and optional Cortex memory Application Programming
   Interface (API) must be started separately as documented in
   [`docs/TESTING.md`](../../TESTING.md).
3. **Hosted CI** (`.github/workflows/ci.yml`) runs package jobs on pushes and
   pull requests to `main`. It excludes Playwright, opt-in full-stack Oracle
   coverage, and live Base Sepolia demo activity. Unlike local `make test`, hosted
   Continuous Integration runs Noir with `--workspace`, runs the real Open Policy
   Agent (OPA) policy suite, and adds the dashboard demo's Python regression suite.

`make verify-kernel` is the separate pinned Halmos 0.3.3 symbolic pass. It builds
Foundry artifacts with AST output and covers the governance-swap harness plus the
registry-disabled and registry-enabled kernel property suites; it is not evidence
of deployment, gas cost, or independent audit.

## Dashboard boundary

The dashboard currently has no `npm test` script, Vitest dependency, or
component-test suite. Its static gate is production build + ESLint; its
behavioral gate is Playwright. Documentation must not invent a mocked
component-test layer or claim Playwright starts its own backend stack.

## Ground rule

No silent mocks. A test either exercises a real dependency or identifies an
intentionally isolated seam. Source capability, local test evidence, hosted-CI
coverage, and deployed behavior are separate claims.

## Convention going forward

Every changed dashboard route should receive Playwright coverage for honest
empty/unavailable states and reachable real-data states. Browser verification
requires direct visual inspection as well as passing assertions. If a future
component-test layer is added, add the manifest script and dependencies first,
then update `Makefile`, CI, `docs/TESTING.md`, and this page in the same change.
