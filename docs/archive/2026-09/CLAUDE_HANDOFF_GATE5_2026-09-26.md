# Claude Handoff — Gate 5 and Claude Registration

Date: 2026-09-26  
Owner handoff: Codex → Claude  
Scope: local Gate 5 cross-product validation and registration of the Claude agent identity

## Current status

The local runtime is healthy and configured for observation-first behavior:

- Shield backend: `http://127.0.0.1:8435`, systemd service active.
- BCC middleware: `http://127.0.0.1:8000`, user service `xibalba-bcc-middleware.service` active.
- BCC mode: `shadow` / observation. Registration alone must not deny tools.
- Integrity Oracle: `http://127.0.0.1:8080`, healthy.
- UserAPI: `http://127.0.0.1:8090`, healthy.
- Dashboard preview target: `http://127.0.0.1:4173`.
- Active Shield DID is registered with the local Oracle and has persisted telemetry.

The Shield integration check passed:

```bash
cd /home/xibalba/Projects/xibalba-shield
sudo BCC_MIDDLEWARE_URL=http://127.0.0.1:8000 \
  ./scripts/verify_local_realtime_integrations.sh
```

Observed result: `RESULT PASS — local realtime integration checks are healthy.`

The dashboard’s real UserAPI authentication suite also passed:

```bash
cd /home/xibalba/Projects/integrity-core/integrity-dashboard
npm run test-e2e -- e2e/auth.spec.ts --project=desktop
```

Observed result: `8 passed (27.8s)`. It covered new registration, dashboard navigation after registration, duplicate-registration conflict handling, invalid credentials, nonexistent accounts, wallet fallback, and uncaught frontend errors.

## Gate 5 objective

Complete independent rendered evidence across Shield, Cortex, and Integrity Dashboard. Keep product boundaries separate; do not merge their authorities or treat mock/source evidence as live evidence.

The flow under test is:

```text
dashboard /auth → real UserAPI registration/login → /dashboard → live data surfaces
```

For the dashboard, validate:

1. Authenticated registration and login.
2. Agent Registry data and ownership scoping.
3. Evidence Ledger data and empty/loading/error states.
4. Shield controls/status without implying that Dashboard is the Shield authority.
5. Settings/policy-pack surfaces and their observation-first wording.
6. Browser console, network, accessibility, and first-viewport evidence.

The connected browser previously had a saved permission block for local origins. If that remains, report Dashboard browser evidence as blocked/unverified and use the checked-in Playwright validation workflow only as a clearly labeled fallback. Do not bypass the browser permission boundary with alternate browser surfaces or raw CDP.

Known operational warnings that are not Gate 5 passes:

- Oracle logs contain repeated `signature verification failed` warnings from stale/unrelated attempts; active DID integration still passed.
- Some BCC audit publication attempts previously returned Oracle `401`; investigate separately from authorization behavior.
- The Shield virtualenv has a dangling `~ntegrity_sdk-0.1.0.dist-info` temporary directory warning.

## Register Claude as a separate agent

Use a dedicated Claude identity. Do not reuse the Shield DID or the Codex identity, and do not expose private keys in the handoff or logs.

First inspect the existing local identity without creating a duplicate:

```bash
cd /home/xibalba/Projects/integrity-core
integrity identity show --name claude
```

If the identity does not exist, create it using the CLI’s protected local key store:

```bash
integrity identity keygen --name claude
```

Run the read-only preflight before registration. Use the local Base Sepolia deployment and local Oracle configuration already used by the workspace. Confirm the current DID, domain, wallet funding, memory-root requirements, and deployment addresses before mutating chain state.

Register the core identity with the simplified default:

```bash
integrity agent register \
  --identity claude \
  --alias claude \
  --domain claude.integrity \
  --vertical none \
  --rpc-url "$RPC_URL" \
  --deployments-file /home/xibalba/Projects/integrity-core/deployments.baseSepolia.json \
  --oracle-url http://127.0.0.1:8080
```

Use the required wallet-password and funder configuration from the protected operator environment. Do not put secrets in this file, shell history, screenshots, or chat output.

Important registration policy:

- The default command registers the core identity and memory surface.
- Do not add `--full` unless the operator explicitly approves provisioning optional primitives and the 100 ITK bond.
- Registration does not enable BCC enforcement and must not remove Claude’s tool access.
- BCC remains observation-only until a deliberate policy-pack and enforcement decision is made.

After registration, verify the result through both local authorities:

```bash
integrity agent show <CLAUDE_DID>
curl -sS http://127.0.0.1:8080/v1/agent/<CLAUDE_DID>
```

Then exercise one harmless observation-mode BCC path and confirm that the decision is recorded without blocking the action. Preserve the DID document, transaction hashes, Oracle response, and BCC decision evidence, but redact keys, passwords, cookies, and private payloads.

## Completion evidence to return

Return a concise Gate 5 report containing:

- Claude DID and registration status.
- Registration transaction hashes and deployment addresses, with secrets excluded.
- Oracle registration response and `agent show` result.
- BCC mode and harmless observation decision.
- Dashboard auth result and rendered route evidence.
- Shield/Cortex/Dashboard provenance boundary for each screenshot.
- Any remaining `BLOCKED`, `UNVERIFIED`, or `DEFERRED` item; do not convert unavailable evidence into a pass.

## Dirty-worktree rule

This workspace contains user changes across multiple repositories. Preserve unrelated modifications. Before committing anything, review exact staged files, run `git diff --cached --check`, and perform a secret scan. Do not reset, clean, or discard worktree artifacts.
