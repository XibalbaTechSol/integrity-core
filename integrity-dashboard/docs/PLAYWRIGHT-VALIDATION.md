# Rendered Playwright validation

The dashboard has two real-browser configurations. `playwright.config.ts` is
the current five-project matrix (desktop Chromium, Firefox, WebKit, tablet,
and mobile Chromium); `playwright.validation.config.ts` is the report-oriented
wrapper used by the npm validation scripts.

```bash
npm run test:e2e:validation
npm run test:e2e:validation:headed
npm run test:e2e:validation:all-browsers
npm run test:e2e:validation:report
```

Both configs default to Vite at `http://127.0.0.1:5189` with the explicit
development directory flag used by the local live-data viewer. Direct matrix
commands use `--project=desktop`, `firefox`, `webkit`, `tablet-chromium`, or
`mobile-chromium`; report-wrapper projects use the corresponding
`desktop-chromium`, `desktop-firefox`, and `desktop-webkit` names.

The suite discovers the route inventory from the current application route
map, visits every declared route in headless Chromium, and exercises the
protocol routes at desktop, tablet, and mobile widths. It captures full-page
and viewport screenshots, DOM assertions, basic accessibility assertions,
console output, failed requests, traces/videos on failure, HTML, JSON, and
JUnit reports. It checks that private-key/recovery-material patterns do not
appear in rendered DOM or screenshot-tested control surfaces.

Artifacts are written to `test-results/`: `route-inventory.json`, reporter
outputs under `reports/`, and per-test attachments under `artifacts/`.

The validation is live-service aware. It records authentication failures,
indexer lag, RPC/provider errors, and unavailable Cortex state instead of
injecting mocks or turning unavailable data into success. It does not submit
real ETH/ITK or administrative contract writes.

The suite runs axe-core on every discovered route and records all violations.
Set `AXE_STRICT=true` (automatically enabled in CI) to fail on critical or
serious violations. It also retains structural landmark, heading, form-label,
and secret-pattern assertions. Set `E2E_AUTH_EMAIL` and
`E2E_AUTH_PASSWORD` to exercise the live userapi authenticated fail-closed
scope check; set `E2E_AUTH_STORAGE_STATE` or
`E2E_RESTRICTED_STORAGE_STATE` to add authenticated Playwright projects.
Set `E2E_AGENT_A_ID` and `E2E_AGENT_B_ID` to the exact DIDs already assigned to
that authenticated principal to run the live two-agent isolation journey.

The browser test does not create accounts or assign agents. For an explicit
disposable setup, register a temporary user with `POST /auth/register`, then
call authenticated `POST /me/agents` twice with two DIDs already verified by
Oracle. Keep the email, password, bearer token, and DID values in the current
shell only; verify `GET /me/agents` returns exactly the two intended DIDs,
then export `E2E_AUTH_EMAIL`, `E2E_AUTH_PASSWORD`, `E2E_AGENT_A_ID`, and
`E2E_AGENT_B_ID` before running the isolation test.

Current limitations: authenticated two-agent switching is skipped unless the
test principal and exact agent assignments are provided; real transaction and
contract writes remain intentionally disabled; and the in-app Browser surface
may be unavailable, in which case the documented fallback is regular
headless Playwright. The isolation test does not create users or assign agents.
