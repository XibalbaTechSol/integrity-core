# MCP Signing Boundary

**Status:** enforced, 2026-08-05. Not a proposal — this documents a fix already applied to
`integrity_sdk/mcp_server.py` and `~/.claude/xibalba/pretool_gate.py`, and the reasoning behind
it, so the boundary doesn't quietly erode the next time someone adds an MCP tool.

## The rule

**Signing a real key, or writing to the chain, is never behind an MCP tool call an agent's own
tool-selection judgment can trigger.** Read-only and local-queue-only operations may be MCP
tools freely. Anything that produces a real Ed25519/secp256k1 signature, submits a signed
telemetry envelope, or writes to `StateAnchor`/`ReputationRegistry`/the Trust Vault must be run
by a human directly via `integrity-cli` or the SDK's own Python API — never mediated by an
agent deciding to call a tool.

## Why

An MCP tool call is not a deliberate human action — it's an LLM deciding to invoke a function
based on its own reasoning over context, including context an attacker controls (a poisoned
memory, a malicious webpage, an adversarial tool result). That is not an acceptable gate for
something irreversible and signed. This is the same reasoning
`xibalba-cortex`'s security invariants already state for recalled content ("untrusted
evidence... cannot silently become instructions, system authority, or tool permissions") —
applied here to the far higher-stakes case of a real signature instead of a recalled fact.

**This was not a hypothetical risk being pre-empted.** A Devil's Advocate review commissioned to
evaluate a *proposed, not-yet-built* "MCP server wrapping SDK capabilities" found that
`integrity_sdk/mcp_server.py` already shipped exactly this gap: `integrity_register_agent` was a
live, callable tool that loaded a real identity key from `~/.integrity-cli/identity/<agent>/` and
could run a full on-chain registration, with zero coverage from the one gate
(`~/.claude/xibalba/pretool_gate.py`) anyone was relying on. Verified independently before any
fix: not wired into any running MCP client config on this machine at the time, so not an active
incident — but reachable the moment someone did wire it in. Full narrative:
`xibalba-cortex/docs/session-log/2026-08-05-integrity-coupling-session.md`.

## What changed

### `integrity_sdk/mcp_server.py`

Four tools — `integrity_flush_telemetry`, `integrity_invoke_intent`, `integrity_register_agent`,
`integrity_commit_memory` — sign, transmit a signed payload, or write to the vault. They are now
disabled by default at **both** layers:

- **Discovery**: `_on_list_tools` filters them out of what's advertised — a client never sees
  them as callable tools at all.
- **Dispatch**: `_on_call_tool` refuses to execute them even if called directly, in case some
  other code path (a forked copy, an older cached tool list) reaches the handler bypassing
  discovery.

`INTEGRITY_MCP_ALLOW_SIGNING_TOOLS=1` re-enables both, for supervised local experimentation
only — never set in a config a real agent session loads.

Remaining tools (`integrity_log_telemetry` — local queue, no transmission;
`integrity_agent_info`, `integrity_resolve_did` — read-only) stay enabled; they were never the
problem.

### `~/.claude/xibalba/pretool_gate.py`

Defense in depth, in case the above is ever bypassed: `RISKY_TOOLS` (the existing
Bash/Write/Edit/MultiEdit/NotebookEdit set) had zero MCP-tool-name coverage — any
`mcp__<server>__<tool>` call skipped this gate entirely, silently. Added
`MCP_SIGNING_TOOL_NAMES` (mirrors `mcp_server.py`'s `_SIGNING_TOOLS`) matched by tool-name
**suffix**, not a fixed server-alias prefix, so a renamed server entry in config still gets
caught.

Critically, this new coverage is **fail-closed**, not fail-open. The existing
Bash/Write/Edit class stays exactly as it was — that fail-open posture was a deliberate,
ratified tradeoff for a developer shell (documented at length in the module's own docstring:
bricking every `Bash` call whenever `bcc_middleware` restarts gets the hook set disabled
wholesale). That tradeoff does not transfer to a real signature. `evaluate_tool_intent()` gained
a `fail_closed` parameter; every pre-verdict failure path (identity unavailable, middleware
unreachable, request error, bad response) denies instead of allowing when set, without touching
any existing call site's behavior.

## What this does not do

- Does not add a confirmation-dialog / elicitation-based "are you sure" step. The Devil's
  Advocate review examined MCP's elicitation primitive specifically and found it insufficient
  for this purpose — its own docstring states a client "might" ask a human "or automatically
  generate a response." That is not a safety property; treating it as one would have been the
  mistake, not the fix.
- Does not change `bcc_middleware`'s own OPA gate, which was already fail-closed and is the real
  authorization backstop for `integrity_invoke_intent` specifically — this fix is about the
  layers *outside* that gate (whether an MCP tool can reach it at all, and what happens when it
  can't be reached).
- Does not audit every other MCP server in this workspace for the same pattern. This fix is
  scoped to `integrity_sdk/mcp_server.py`, the one flagged by the review. Any future MCP server
  that touches signing should be checked against the rule stated at the top of this document
  before it ships, not after.
