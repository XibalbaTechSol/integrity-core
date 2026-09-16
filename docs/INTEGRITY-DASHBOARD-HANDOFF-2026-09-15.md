# Integrity Dashboard Handoff — 2026-09-15

## Status

The Integrity Dashboard protocol control-center surface is browser-validated on
the current branch. The overall application is not release-complete yet.

## Delivered and verified

- Legacy heading failures were corrected; the final desktop Chromium route audit
  passed **33/33** routes.
- Protocol routes passed **27/27** responsive checks at desktop, tablet, and
  narrow mobile viewports.
- Safe refresh and copy controls passed at all three tested viewports.
- Axe-core scans run for every discovered route and are retained in Playwright
  artifacts. Strict blocking is intentionally separate because the legacy shell
  still contains known serious accessibility findings.
- The dashboard uses authenticated userapi `/me/agents` scope when a session is
  present. Unscoped Oracle directory access is available only through the explicit
  development flag `VITE_ALLOW_UNSCOPED_AGENT_DIRECTORY=true`.
- The validator checks rendered DOM for private-key, seed-phrase, and recovery
  material patterns. No such patterns were found.
- Optional Oracle provider degradation is recorded as a warning where the route
  remains usable; it is not turned into fabricated success.

## Evidence and commands

From `integrity-dashboard/`:

```bash
npm run build
git diff --check
npm run test:e2e:validation -- --project=desktop-chromium --grep='renders and audits'
npm run test:e2e:validation -- --grep='safe controls'
npm run test:e2e:validation -- --project=desktop-chromium --grep='agent selector'
```

The SDK verification gate passed with the deterministic content-capture setting:

```bash
cd integrity-sdk
INTEGRITY_CONTENT_SAMPLE_RATE=1 uv run pytest -q
# 339 passed, 3 skipped, 1 warning
```

Without that explicit test setting, the balanced collection profile samples
content at 0.1 and five content-sensitive tests report sampled-out output; this
is a test-environment distinction, not a hidden retry or ignored failure.

Artifacts are generated under `integrity-dashboard/test-results/` locally:

- `route-inventory.json`
- `reports/html/`
- `reports/playwright.json`
- `reports/junit.xml`
- per-test screenshots, DOM assertions, console logs, network summaries, axe
  results, traces, and videos on failure

The in-app Browser runtime was unavailable (`No browser is available`); the
rendered evidence therefore comes from regular headless Playwright against the
local Vite viewer at `http://127.0.0.1:5193`.

## Remaining release gates

1. Run authenticated multi-agent isolation with a disposable userapi principal
   and two exact DIDs already assigned through `/me/agents`:

   ```bash
   E2E_AUTH_EMAIL=... E2E_AUTH_PASSWORD=... \\
   E2E_AGENT_A_ID=did:... E2E_AGENT_B_ID=did:... \\
   npm run test:e2e:validation
   ```

   The test switches A to B, verifies the selected-agent panel, reloads, and
   fails closed if A-specific identity remains visible. It skips when the
   explicit variables are absent; skipped is not browser-verified.

2. Remediate the recorded serious axe findings, then run
   `AXE_STRICT=true npm run test:e2e:validation` and in CI.

3. Add safe local-chain or explicit simulation fixtures before validating wallet
   sends or contract administration. No real ETH/ITK transfer or contract write
   was executed in this pass.

4. Complete Firefox/WebKit and full legacy-route responsive coverage if those
   browsers and viewports are part of the release support matrix.

## Security boundaries

- No private keys, seed phrases, passwords, bearer tokens, cookies, or raw
  keystore contents belong in the dashboard UI or test artifacts.
- A wallet address is not treated as proof of DID ownership or controller
  authority.
- Submission is not confirmation; chain, backend indexing, and cached state are
  separate states.
- Missing authority, stale state, unavailable Oracle/RPC, and unverified proof
  data remain fail-closed.

## Ownership and next action

The next operator should provision only a disposable local/test principal and
assign two exact Oracle-backed DIDs, run the authenticated gate, review the axe
report, and then decide whether the remaining wallet/contract write gates belong
in this release or remain disabled pending secure signing infrastructure.
