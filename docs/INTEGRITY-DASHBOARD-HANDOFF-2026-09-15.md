# Integrity Dashboard Handoff — 2026-09-15

## Status

The Integrity Dashboard protocol control-center surface is browser-validated on
the current branch. The overall application is not release-complete yet.

## Delivered and verified

- Legacy heading failures were corrected; the final desktop Chromium route audit
  passed **33/33** routes.
- Accessibility remediation is now complete for the current 33-route desktop
  surface: explicit control labels, named icon actions, valid tab semantics,
  keyboard-focusable scroll regions, and WCAG-safe primary-action contrast were
  added across the shared shell and affected pages. The strict desktop axe gate
  passed **33/33** routes after the remediation.
- Tablet Chromium passed the complete **33/33** route audit at 1024x768.
- Mobile Chromium covered all 33 routes: the final full run passed 32/33, and
  the only changed route (`/licence`) passed its focused rerun after the
  responsive stat-grid fix. No responsive route remains unverified.
- Safe refresh and copy controls passed at desktop, tablet, and narrow mobile
  viewports.
- Firefox passed the strict **33/33** route audit. WebKit passed 32/33 on its
  first full run; the only failure was the optional unavailable Shield service
  on `/correlation`, which passed after browser-specific degraded-service
  diagnostics were classified. Unrelated browser errors remain blocking.
- Axe-core scans run for every discovered route and are retained in Playwright
  artifacts. The strict desktop accessibility gate now passes for all 33
  discovered routes.
- Deterministic write-gate coverage was added in
  `integrity-dashboard/e2e/write-gates.spec.ts`: the permission matrix fails
  closed for wrong chain, signer/controller mismatch, missing role,
  simulation failure, and stale state; an explicit `eth_call`-style fixture
  verifies the `SovereignAgent.execute` envelope; and the headless no-wallet
  Send flow makes no non-GET write request. The fixture does not perform a
  chain write.
- The reusable read-only preflight helper is
  `integrity-dashboard/src/integrity/wallet/simulation.ts`; it constructs the
  exact `SovereignAgent.execute` calldata and invokes only `provider.call`.
- The shared sidebar/header and protocol control-center sidebar now expose all
  canonical application pages from one route model, including Finance,
  Intelligence, Operations, and System groups. Navigation consistency passed
  **5/5**, with representative strict axe checks passing **3/3** after the
  expansion.
- The underlying local-EVM `SovereignAgent` contract suite passed **8/8**,
  including controller execution, stranger rejection, revert bubbling, value
  forwarding, and controller rotation. This is contract-level evidence only;
  it does not establish browser-to-chain integration.
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
# strict accessibility release gate
AXE_STRICT=true npm run test:e2e:validation -- --project=desktop-chromium --grep='renders and audits'
npm run test:e2e:validation -- --grep='safe controls'
npm run test:e2e:validation -- --project=desktop-chromium --grep='agent selector'
npm run test-e2e -- e2e/write-gates.spec.ts
```

Browser matrix commands used for the 2026-09-16 continuation:

```bash
AXE_STRICT=true ./node_modules/.bin/playwright test e2e/validation.spec.ts --project=firefox --workers=1 --grep='renders and audits'
AXE_STRICT=true ./node_modules/.bin/playwright test e2e/validation.spec.ts --project=webkit --workers=1 --grep='renders and audits'
AXE_STRICT=true ./node_modules/.bin/playwright test e2e/validation.spec.ts --project=tablet-chromium --workers=1 --grep='renders and audits'
AXE_STRICT=true ./node_modules/.bin/playwright test e2e/validation.spec.ts --project=mobile-chromium --workers=1 --grep='renders and audits'
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
local Vite viewer at `http://127.0.0.1:5189`.

## Release gates and remaining work

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

   Provisioning is an explicit operator action and is not performed by the
   browser test. Using a disposable email/password kept only in the current
   shell, register through userapi, then assign two DIDs that have already
   been verified in Oracle:

   ```bash
   USERAPI_URL=http://localhost:8090
   E2E_AUTH_EMAIL='<disposable email>'
   E2E_AUTH_PASSWORD='<disposable password>'
   AUTH_JSON=$(curl -fsS -X POST "$USERAPI_URL/auth/register" \
     -H 'Content-Type: application/json' \
     -d "$(jq -cn --arg email "$E2E_AUTH_EMAIL" --arg password "$E2E_AUTH_PASSWORD" '{email:$email,password:$password}')")
   E2E_AUTH_TOKEN=$(jq -r '.access_token' <<<"$AUTH_JSON")
   curl -fsS -X POST "$USERAPI_URL/me/agents" \
     -H "Authorization: Bearer $E2E_AUTH_TOKEN" \
     -H 'Content-Type: application/json' \
     -d '{"agent_did":"did:integrity:<verified-agent-a>"}'
   curl -fsS -X POST "$USERAPI_URL/me/agents" \
     -H "Authorization: Bearer $E2E_AUTH_TOKEN" \
     -H 'Content-Type: application/json' \
     -d '{"agent_did":"did:integrity:<verified-agent-b>"}'
   export E2E_AGENT_A_ID='did:integrity:<verified-agent-a>'
   export E2E_AGENT_B_ID='did:integrity:<verified-agent-b>'
   export E2E_AUTH_EMAIL E2E_AUTH_PASSWORD
   ```

   Verify the returned `/me/agents` list contains exactly those two DIDs
   before running the Playwright command. Do not commit this shell history,
   token, or password; do not use a production account or unverified DID.

2. **Completed 2026-09-16:** remediate the recorded serious axe findings and
   run the strict desktop gate. The current source passes 33/33 routes locally;
   the full rerun after the final remediation passed 33/33. CI still needs to
   run the same strict command in its supported environment.

3. **Safe simulation gate completed 2026-09-16:** deterministic permission,
   explicit `eth_call`-style envelope simulation, controller rejection, and
   no-wallet fail-closed behavior are covered by `e2e/write-gates.spec.ts`
   (`3 passed`). The simulator has no `send` or `sendTransaction` path. Real
   wallet sends and contract administration remain intentionally unvalidated;
   no real ETH/ITK transfer or contract write was executed.

4. **Completed 2026-09-16:** Firefox, WebKit, tablet Chromium, and mobile
   Chromium route coverage was executed. WebKit's unavailable optional Shield
   backend remains visible as degraded-service evidence, not fabricated health.

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
assign two exact Oracle-backed DIDs, then run the authenticated gate. After
that, decide whether live wallet/contract writes belong in this release or
remain disabled pending secure signing infrastructure.
