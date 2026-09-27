# Codex Handoff - 2026-08-18

## Current objective
Configure Hermes/xibalba automation for the Integrity ecosystem and continue CI repair across:
- `XibalbaTechSol/integrity-core`
- `XibalbaTechSol/xibalba-cortex`
- `XibalbaTechSol/xibalba-shield`

User is restarting the PC. Resume from this file after reboot.

## Hermes status
Telegram gateway is configured and working.
- Telegram home channel/user id: `8056909526`
- Last notification command succeeded:
  `hermes send --to telegram --subject "[xibalba] Hermes routing and CI update" ...`

Hermes model routing configured in `/home/xibalba/.hermes/config.yaml`:
- Primary/default: `openai-codex / gpt-5.6-luna`
- Fallback chain:
  1. `gemini / gemini-2.5-flash-lite`
  2. `copilot / gpt-5.4-mini`

High-reasoning cron jobs pinned to `openai-codex / gpt-5.6-sol`:
- `1692a2d6a18d` - `xibalba-protocol-implementation-cycle`
- `c3ec3c0e8e84` - `Daily Integrity Compliance Integration Brief`

Important: the current `openai-codex` OAuth grant is rate-limited with `usage_limit_reached (429)`. User has a second Codex account and may switch with:
```bash
hermes logout --provider openai-codex
hermes model --no-browser
```
Then select OpenAI Codex and authenticate in a browser signed into the second account.

## Completed GitHub CI fixes

### xibalba-cortex
Repo: `/home/xibalba/Projects/xibalba-cortex` plus clean worktree `/home/xibalba/tmp/xibalba-cortex-main-ci-fix`

Fix:
- Regenerated TOC for `docs/wiki/concepts/hybrid-extraction-and-retrieval.md`.
- PR `#3` merged: `https://github.com/XibalbaTechSol/xibalba-cortex/pull/3`
- Main workflow passed:
  `Sync GitHub Wiki`, run `32197822543`, completed success.

### xibalba-shield
Clean worktree used: `/home/xibalba/tmp/xibalba-shield-ci-fix`

Fixes:
- `pyproject.toml`: replaced local absolute `integrity-sdk` path dependency with Git subdirectory dependency:
  `integrity-sdk @ git+https://github.com/XibalbaTechSol/integrity-core.git@main#subdirectory=integrity-sdk`
- `.github/workflows/ci.yml`: added OPA install step before pytest.

Validation:
- Local clean pytest passed: `135 passed, 7 skipped in 32.29s`
- Local policy validations passed for:
  - `policies/defaults/smb.json`
  - `policies/defaults/professional-services.json`
  - `policies/defaults/regulated.json`
- PR `#13` merged: `https://github.com/XibalbaTechSol/xibalba-shield/pull/13`
- Main CI passed: run `32197861052`, completed success.

## integrity-core current state
Main repo local checkout:
- Path: `/home/xibalba/Projects/integrity-core`
- Current local branch: `audit/harness-loop-2026-07-30`
- It has many existing dirty changes from user/Claude/other agents. Do not reset or overwrite them.

Dirty files observed in main local checkout:
```text
 M PRODUCTION_GAPS.md
 M bcc_middleware/app/canonical.py
 M bcc_middleware/app/main.py
 M bcc_middleware/app/schemas.py
 M bcc_middleware/tests/helpers.py
 M docs/INTERFACE_CONTRACT.md
 M docs/wiki/concepts/bcc.md
 M gas_usage.jsonl
 M integrity-cli/integrity_cli/bcc.py
 M integrity-cli/integrity_cli/main.py
 M integrity-cli/tests/test_bcc.py
 M integrity-cli/tests/test_main.py
 M integrity-dashboard/demo/src/integrity_demo/heartbeat.py
 M integrity-sdk/gas_usage.jsonl
 M integrity-sdk/integrity_sdk/bcc.py
 M integrity-sdk/integrity_sdk/client.py
 M integrity-sdk/integrity_sdk/markets.py
 M integrity-sdk/integrity_sdk/mcp_server.py
 M integrity-sdk/integrity_sdk/telemetry/intent.py
 M integrity-sdk/tests/unit/test_client.py
 M integrity-sdk/tests/unit/test_intent.py
?? CLAUDE_HANDOFF_2026-08-17.md
?? bcc_middleware/tests/test_deployment_binding.py
?? docs/plans/2026-08-18-phase1-canonical-intent-encoding-proposal.md
```

Use the clean worktree for CI fixes:
- Clean worktree path: `/tmp/integrity-core-ci-fix.3fIHpM`
- Based on `origin/main` at `74c46a8733434cfc4b12bf2adc9a0dcfa636eb8c`

Latest failing integrity-core main CI inspected:
- Run: `32185923067`
- Branch: `main`
- Commit: `74c46a8733434cfc4b12bf2adc9a0dcfa636eb8c`
- Failed jobs:
  - `integrity-dashboard (build + lint)`: ESLint could not import package `globals` from `integrity-dashboard/eslint.config.js`.
  - `integrity-cli (pytest)`, `integrity-sdk (pytest)`, `contracts (forge test)`: Foundry could not resolve Chainlink import `@openzeppelin/contracts@5.3.0/utils/introspection/IERC165.sol`.

## integrity-core clean worktree edits made so far
In `/tmp/integrity-core-ci-fix.3fIHpM`:

Dashboard fix:
- Added `globals` as a dev dependency in `integrity-dashboard/package.json`.
- Updated `integrity-dashboard/package-lock.json` using:
  `npm install globals --save-dev --package-lock-only --legacy-peer-deps`
- Note: npm also changed some lockfile metadata (`libc` fields and dev flags). Review before committing; may be acceptable due npm version, but keep diff tight if possible.

Contracts remapping fix:
- Added this line to `contracts/remappings.txt`:
  `@openzeppelin/contracts@5.3.0/=node_modules/@openzeppelin/contracts-5.3.0/`
- Added the same line to `contracts/foundry.toml` remappings.
- A malformed intermediate line in `contracts/remappings.txt` was corrected; verify final diff before commit.

## Validation status before reboot
Dashboard:
- First `npm run lint` failed because `node_modules` was absent.
- Ran `npm ci --legacy-peer-deps` in `/tmp/integrity-core-ci-fix.3fIHpM/integrity-dashboard`; it completed.
- Reran `npm run lint`; it passed with warnings only (`0 errors, 56 warnings`).

Contracts:
- Ran `npm install --legacy-peer-deps` in `/tmp/integrity-core-ci-fix.3fIHpM/contracts`; completed with dependency audit warnings only.
- Started `forge test -vvv` in `/tmp/integrity-core-ci-fix.3fIHpM/contracts`.
- At handoff time, it was still running and had printed:
  `Compiling 128 files with Solc 0.8.28`
- The running exec session id before reboot was `46187`, but after PC restart it will be gone. Rerun:
```bash
cd /tmp/integrity-core-ci-fix.3fIHpM/contracts
forge test -vvv
```

Recommended resume sequence:
```bash
cd /tmp/integrity-core-ci-fix.3fIHpM
sed -n '24,40p' contracts/foundry.toml
sed -n '1,8p' contracts/remappings.txt
git diff -- contracts/foundry.toml contracts/remappings.txt integrity-dashboard/package.json integrity-dashboard/package-lock.json
cd integrity-dashboard && npm run lint
cd ../contracts && forge test -vvv
```

If Forge passes, run the Python tests that previously failed through their CI-style commands. Inspect `.github/workflows/ci.yml` for exact working directories, then run the relevant `uv sync` / `uv run pytest` in:
- `integrity-cli`
- `integrity-sdk`

Then create branch, commit, push, and open PR:
```bash
cd /tmp/integrity-core-ci-fix.3fIHpM
git switch -c fix/main-ci-deps-20260818
git add contracts/foundry.toml contracts/remappings.txt integrity-dashboard/package.json integrity-dashboard/package-lock.json
git commit -m "Fix integrity-core CI dependency resolution"
git push -u origin fix/main-ci-deps-20260818
gh pr create --repo XibalbaTechSol/integrity-core --base main --head fix/main-ci-deps-20260818 --title "Fix integrity-core CI dependency resolution" --body "## Summary\n- Add missing dashboard globals dev dependency used by eslint.config.js.\n- Add the OpenZeppelin 5.3.0 Foundry remapping required by Chainlink CCIP imports.\n\n## Verification\n- npm run lint (integrity-dashboard)\n- forge test -vvv (contracts)\n- uv run pytest in integrity-cli and integrity-sdk, if rerun before PR"
```

After PR checks pass, merge and send Telegram status:
```bash
hermes send --to telegram --subject "[xibalba] integrity-core CI update" "integrity-core CI dependency fix PR merged/passing: dashboard globals dependency and OpenZeppelin 5.3.0 Foundry remapping."
```

## Cautions
- Do not edit or reset `/home/xibalba/Projects/integrity-core` dirty branch unless explicitly asked.
- Use the clean worktree `/tmp/integrity-core-ci-fix.3fIHpM` for CI repair.
- If `/tmp` is cleared by reboot, recreate a clean worktree from `origin/main` and reapply the edits from this file.
- `apply_patch` has repeatedly failed with `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`; targeted `perl -0pi` edits worked with escalation.
