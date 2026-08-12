"""
integrity_sdk.mcp_server — Model Context Protocol server for the Integrity SDK.

Exposes the SDK's core capabilities as MCP tools so any agent harness that
speaks MCP (Claude Desktop, Cursor, Antigravity CLI, custom harnesses) can
discover and call them natively — no framework-specific adapter required.

## Why MCP here

The SDK's existing integration layer (`integrations/openai_integrity.py`,
`integrations/langchain_callback.py`) requires an agent to be built on a
*specific* framework and to import those adapters at construction time.  MCP
inverts that: the harness connects once, discovers tools at runtime, and calls
them over JSON-RPC regardless of what language or framework the agent is
implemented in.  This module is the SDK's "one wire" into any MCP-capable
harness.

## Available tools

  integrity_log_telemetry       — log one telemetry entry under agent_id (local queue only)
  integrity_agent_info          — read back the SDK client's current state
  integrity_resolve_did         — look up an agent's on-chain SovereignAgent

## Disabled by default: signing and on-chain writes (2026-08-05)

  integrity_flush_telemetry     — flush accumulated batch to integrity-oracle (signs)
  integrity_invoke_intent       — BCC-commit + OPA-gate an intent (signs)
  integrity_register_agent      — run the full on-chain registration sequence (signs + writes)
  integrity_commit_memory       — write facts to the Trust Vault (writes)

These four are advertised and callable only if `INTEGRITY_MCP_ALLOW_SIGNING_TOOLS=1` is set
(supervised local experimentation only — never in a real agent session's config). An LLM's
own tool-selection judgment is not an acceptable gate for a real signature or an irreversible
on-chain write; that boundary must be a human running integrity-cli/the SDK directly. See
`docs/design/mcp-signing-boundary.md` for the full reasoning and
`xibalba-cortex/docs/session-log/2026-08-05-integrity-coupling-session.md` for how this
was found (a Devil's Advocate review commissioned for a *different*, not-yet-built proposal
discovered this module already shipped the exact gap it was reviewing).

## Running the server

  uv run python -m integrity_sdk.mcp_server \
      --agent-id xibalba.integrity \
      --oracle-url http://localhost:8080

Or add to an MCP-capable harness config:

  {
    "mcpServers": {
      "integrity": {
        "command": "uv",
        "args": [
          "run", "--directory", "/path/to/integrity-sdk",
          "python", "-m", "integrity_sdk.mcp_server",
          "--agent-id", "xibalba.integrity",
          "--oracle-url", "http://localhost:8080"
        ]
      }
    }
  }

## Identity / keypair

The server loads the agent's Ed25519 keypair from the standard identity store
(`~/.integrity-cli/identity/<agent-id>/`) so every flush and intent call is
correctly signed.  If no keypair is found, the server still starts and provides
telemetry logging but flushes will receive a 401 from the oracle (as documented
in client.py's `flush_telemetry` docstring).

## Dependency

`mcp>=1.0.0` must be installed.  It is listed under
`[project.optional-dependencies] mcp` in pyproject.toml so it is not pulled
in by default (`pip install integrity-sdk[mcp]` opts in).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("integrity_sdk.mcp_server")

# Tools that sign, transmit a signed payload, or write to the vault/chain.
#
# Security decision, 2026-08-05: an MCP tool call is an LLM deciding to invoke a function
# based on its own reasoning over context -- including context an attacker controls (a
# poisoned memory, a malicious webpage, an adversarial tool result). That is not an
# acceptable gate for a real Ed25519/secp256k1 signature or an irreversible on-chain write.
# A Devil's Advocate review (full account: xibalba-cortex's
# docs/session-log/2026-08-05-integrity-coupling-session.md) found this module already
# exposed `integrity_register_agent` as a live, callable tool loading a real identity key
# with no gate covering it -- not hypothetical, already shipped. Verified independently
# before this fix: not currently wired into any running MCP client config on this
# machine, but reachable the moment someone did wire it in.
#
# Remediation: these four tools are disabled by default, at BOTH tool discovery (so a
# client never even sees them as callable) and dispatch (defense in depth, in case some
# other code path calls the handler directly). Signing and on-chain writes stay exclusively
# in integrity-sdk / integrity-cli, run directly by a human -- never behind a tool call an
# agent's own judgment triggers. See docs/design/mcp-signing-boundary.md.
_SIGNING_TOOLS = {
    "integrity_flush_telemetry",
    "integrity_invoke_intent",
    "integrity_register_agent",
    "integrity_commit_memory",
}
# Escape hatch for local, supervised experimentation only -- never set this in a config a
# real agent session loads. Off by default on purpose.
_SIGNING_TOOLS_ENABLED = os.environ.get("INTEGRITY_MCP_ALLOW_SIGNING_TOOLS") == "1"


def _load_keypair_for(agent_id: str) -> Optional[Any]:
    """Load the Ed25519 Keypair for *agent_id* from the default identity store,
    or return None if not found (server still starts, flushes will 401)."""
    from .did import Keypair

    # Strip the DID prefix if the caller passed a full DID.
    bare = agent_id.replace("did:integrity:", "")
    candidates = [
        Path.home() / ".integrity-cli" / "identity" / bare / "private.pem",
        Path.home() / ".integrity-cli" / "identity" / bare / f"{bare}.pem",
        Path.home() / ".integrity-cli" / "identity" / f"{bare}.pem",
    ]
    for path in candidates:
        if path.exists():
            try:
                return Keypair.from_pem(path.read_bytes())
            except Exception as exc:
                logger.warning("found %s but could not load keypair: %s", path, exc)
    logger.warning(
        "no keypair found for agent_id=%r — flushes will be unsigned (401 from oracle)", agent_id
    )
    return None


def _load_doc_for(agent_id: str) -> Optional[Dict[str, Any]]:
    """Load the DID document for *agent_id* to resolve the canonical DID string."""
    bare = agent_id.replace("did:integrity:", "")
    candidates = [
        Path.home() / ".integrity-cli" / "identity" / bare / "document.json",
        Path.home() / ".integrity-cli" / "identity" / f"{bare}.document.json",
    ]
    for path in candidates:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except Exception:
                pass
    return None


def build_server(agent_id: str, oracle_url: str) -> Any:
    """
    Construct and return the MCP `Server` instance with all Integrity tools
    registered.  Kept as a named function (rather than module-level) so tests
    can call it without running `main()`.

    Uses the mcp>=2.x constructor-based API (on_list_tools / on_call_tool kwargs).
    """
    try:
        from mcp.server import Server
        from mcp.server.models import InitializationOptions
        try:
            import mcp_types as types  # mcp>=2.x splits types into mcp_types
        except ImportError:
            import mcp.types as types  # mcp<2 fallback
    except ImportError as exc:
        raise ImportError(
            "The MCP server requires the `mcp` package: "
            "pip install integrity-sdk[mcp]  or  pip install mcp>=1.0.0"
        ) from exc

    from .client import IntegrityClient
    from .did import Keypair
    from .memory import TrustVault, JSONLBackend

    # Resolve canonical DID from stored document if available.
    doc = _load_doc_for(agent_id)
    canonical_did = doc["id"] if doc else agent_id
    keypair = _load_keypair_for(agent_id)

    client = IntegrityClient(
        agent_id=canonical_did,
        oracle_url=oracle_url,
        keypair=keypair,
        auto_flush=False,
        enable_otel_export=True,
    )

    # ------------------------------------------------------------------ #
    # Tool definitions advertised to the harness on connect               #
    # ------------------------------------------------------------------ #
    _TOOLS = [
        types.Tool(
            name="integrity_log_telemetry",
            description=(
                "Append one telemetry entry to the Integrity SDK batch for the "
                "current agent session.  Call this after each significant agent "
                "action to build up observability data before flushing."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "metadata": {
                        "type": "object",
                        "description": "Arbitrary JSON metadata for this telemetry entry (model, tokens, completion text, tool name, etc.)",
                    },
                    "entropy": {
                        "type": "number",
                        "description": "Optional pre-computed entropy signal [0,1]",
                    },
                    "grounding": {
                        "type": "number",
                        "description": "Optional pre-computed grounding signal [0,1]",
                    },
                },
                "required": ["metadata"],
            },
        ),
        types.Tool(
            name="integrity_flush_telemetry",
            description=(
                "Flush the accumulated telemetry batch to integrity-oracle via "
                "POST /v1/telemetry/ingest.  Returns {success: bool}.  Call "
                "at end-of-session or when the batch is large enough."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "zk_proof": {
                        "type": "object",
                        "description": "Optional ZK proof to attach to this flush",
                    },
                },
            },
        ),
        types.Tool(
            name="integrity_invoke_intent",
            description=(
                "BCC-commit an intent and run it through the OPA policy gate.  "
                "Returns {status: 'allowed'|'error', result}.  The agent must "
                "have a loaded keypair; call integrity_agent_info to check."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "intent_type": {
                        "type": "string",
                        "description": "Intent type string (e.g. 'tool_call', 'data_access')",
                    },
                    "intent_payload": {
                        "type": "object",
                        "description": "Arbitrary JSON payload for the intent",
                    },
                    "goal": {"type": "string", "description": "High-level agent goal"},
                    "plan": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ordered list of planned steps",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Chain-of-thought reasoning text",
                    },
                    "policy_scope": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "OPA policy scope identifiers",
                    },
                    "covered_entity_address": {
                        "type": "string",
                        "description": "On-chain CoveredEntity address for HIPAA-gated intents",
                    },
                },
                "required": ["intent_type"],
            },
        ),
        types.Tool(
            name="integrity_agent_info",
            description=(
                "Return the current Integrity SDK client state: canonical DID, "
                "oracle URL, current nonce, keypair presence, pending batch size."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="integrity_resolve_did",
            description=(
                "Resolve a DID string to its on-chain registration record via "
                "integrity-oracle.  Defaults to the server's own agent DID."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "did": {
                        "type": "string",
                        "description": "DID to resolve (defaults to this agent's DID)",
                    },
                },
            },
        ),
        types.Tool(
            name="integrity_register_agent",
            description=(
                "[PLANNED partial] Run the on-chain agent registration sequence. "
                "Currently delegates to integrity_sdk.registration.register_agent "
                "if that function is present; otherwise returns an error directing "
                "the caller to use integrity-cli agent register instead.  "
                "Requires FUNDER_PRIVATE_KEY and INTEGRITY_WALLET_PASSWORD in env."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "alias": {"type": "string", "description": "Human-readable alias"},
                    "description": {"type": "string", "description": "Agent description"},
                    "rpc_url": {"type": "string", "description": "EVM RPC endpoint"},
                    "deployments_file": {
                        "type": "string",
                        "description": "Path to deployments.local.json",
                    },
                },
            },
        ),
        types.Tool(
            name="integrity_commit_memory",
            description=(
                "Commit a summary of facts to the agent's Trust Vault and anchor the state root. "
                "Uses the configured memory backend (default: JSONL)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "facts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "role": {"type": "string"},
                                "content": {"type": "string"}
                            },
                            "required": ["role", "content"]
                        },
                        "description": "List of facts or observations from the session"
                    },
                    "platform": {
                        "type": "string",
                        "description": "The platform the session took place on (e.g. hermes)",
                        "default": "mcp-session"
                    }
                },
                "required": ["facts"]
            }
        ),
    ]

    # ------------------------------------------------------------------ #
    # Handler: list_tools                                                  #
    # ------------------------------------------------------------------ #
    async def _on_list_tools(ctx: Any, params: Any) -> Any:
        # Signing/writing tools are never advertised unless explicitly opted into -- a
        # client shouldn't even discover them as callable. See _SIGNING_TOOLS above.
        visible = _TOOLS if _SIGNING_TOOLS_ENABLED else [
            t for t in _TOOLS if t.name not in _SIGNING_TOOLS
        ]
        return types.ListToolsResult(tools=visible)

    # ------------------------------------------------------------------ #
    # Handler: call_tool — dispatches by tool name                        #
    # ------------------------------------------------------------------ #
    async def _on_call_tool(ctx: Any, params: Any) -> Any:
        name: str = params.name
        arguments: Dict[str, Any] = params.arguments or {}

        def _text(payload: Any) -> List[Any]:
            return [types.TextContent(type="text", text=json.dumps(payload))]

        # Defense in depth: even if a caller reaches this handler directly, bypassing
        # _on_list_tools' discovery-time filter, a disabled signing tool still refuses to
        # execute. See _SIGNING_TOOLS above.
        if name in _SIGNING_TOOLS and not _SIGNING_TOOLS_ENABLED:
            return types.CallToolResult(
                content=_text({
                    "status": "disabled",
                    "error": (
                        f"{name} is disabled by default. Signing and on-chain writes must "
                        "go through integrity-cli or the SDK directly, run by a human -- "
                        "not an MCP tool call an agent's own judgment triggers. See "
                        "docs/design/mcp-signing-boundary.md. (Set "
                        "INTEGRITY_MCP_ALLOW_SIGNING_TOOLS=1 only for supervised local "
                        "experimentation -- never in a real agent session's config.)"
                    ),
                }),
                isError=True,
            )

        # ---- integrity_log_telemetry ---------------------------------- #
        if name == "integrity_log_telemetry":
            metadata: Dict[str, Any] = arguments.get("metadata", {})
            entropy: Optional[float] = arguments.get("entropy")
            grounding: Optional[float] = arguments.get("grounding")
            client.log_telemetry(metadata=metadata, entropy=entropy, grounding=grounding)
            return types.CallToolResult(content=_text({"status": "queued"}))

        # ---- integrity_flush_telemetry -------------------------------- #
        elif name == "integrity_flush_telemetry":
            zk_proof: Optional[Dict[str, Any]] = arguments.get("zk_proof")
            success = client.flush_telemetry(zk_proof=zk_proof)
            return types.CallToolResult(
                content=_text({"success": success, "agent_id": canonical_did})
            )

        # ---- integrity_invoke_intent ---------------------------------- #
        elif name == "integrity_invoke_intent":
            try:
                result = client.invoke_intent(
                    intent_type=arguments["intent_type"],
                    intent_payload=arguments.get("intent_payload", {}),
                    goal=arguments.get("goal"),
                    plan=arguments.get("plan"),
                    planned_action=arguments.get("planned_action"),
                    policy_scope=arguments.get("policy_scope"),
                    reasoning=arguments.get("reasoning"),
                    covered_entity_address=arguments.get("covered_entity_address"),
                )
                return types.CallToolResult(
                    content=_text({"status": "allowed", "result": str(result)})
                )
            except Exception as exc:
                return types.CallToolResult(
                    content=_text({"status": "error", "error": str(exc)})
                )

        # ---- integrity_agent_info ------------------------------------- #
        elif name == "integrity_agent_info":
            info = {
                "agent_id": client.agent_id,
                "oracle_url": client.oracle_url,
                "nonce": client._nonce,
                "nonce_synced": client._nonce_synced,
                "has_keypair": client._keypair is not None,
            }
            return types.CallToolResult(content=_text(info))

        # ---- integrity_resolve_did ------------------------------------ #
        elif name == "integrity_resolve_did":
            import requests as _req

            did = arguments.get("did", canonical_did)
            try:
                resp = _req.get(f"{client.oracle_url}/v1/agent/{did}", timeout=10)
                resp.raise_for_status()
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text=resp.text)]
                )
            except Exception as exc:
                return types.CallToolResult(content=_text({"error": str(exc)}))

        # ---- integrity_register_agent --------------------------------- #
        elif name == "integrity_register_agent":
            try:
                from . import registration as reg_module

                rpc_url = arguments.get("rpc_url", os.getenv("RPC_URL", "http://localhost:8545"))
                deployments_file = arguments.get(
                    "deployments_file",
                    os.getenv("DEPLOYMENTS_FILE", str(Path.cwd() / "deployments.local.json")),
                )
                alias = arguments.get("alias", agent_id)
                description = arguments.get("description", "")

                if hasattr(reg_module, "register_agent"):
                    result = reg_module.register_agent(
                        agent_id=canonical_did,
                        keypair=keypair,
                        rpc_url=rpc_url,
                        deployments_file=deployments_file,
                        oracle_url=oracle_url,
                        alias=alias,
                        description=description,
                    )
                    return types.CallToolResult(
                        content=_text({"status": "registered", "result": str(result)})
                    )
                else:
                    return types.CallToolResult(
                        content=_text(
                            {
                                "status": "error",
                                "error": "registration.register_agent not found — use integrity-cli agent register instead",
                            }
                        )
                    )
            except Exception as exc:
                return types.CallToolResult(content=_text({"status": "error", "error": str(exc)}))

        # ---- integrity_commit_memory ---------------------------------- #
        elif name == "integrity_commit_memory":
            facts = arguments.get("facts", [])
            platform = arguments.get("platform", "mcp-session")
            
            # Simple assumption that the vault lives in the agent's identity directory
            bare = canonical_did.replace("did:integrity:", "")
            vault_path = Path.home() / ".integrity-cli" / "identity" / bare / "memory_log.jsonl"
            backend = JSONLBackend(vault_path)
            vault = TrustVault(agent_did=canonical_did, backend=backend)
            
            try:
                with vault.session(platform=platform) as session:
                    for fact in facts:
                        session.add_fact(fact["role"], fact["content"])
                
                return types.CallToolResult(
                    content=_text({"status": "success", "message": f"Successfully committed {len(facts)} facts to the Trust Vault. State anchored."})
                )
            except Exception as exc:
                return types.CallToolResult(
                    content=_text({"status": "error", "error": str(exc)})
                )

        else:
            return types.CallToolResult(
                content=_text({"error": f"unknown tool: {name}"}),
                isError=True,
            )

    server = Server(
        "integrity-sdk",
        on_list_tools=_on_list_tools,
        on_call_tool=_on_call_tool,
    )

    return server


def main() -> None:
    """CLI entrypoint: `python -m integrity_sdk.mcp_server [--agent-id] [--oracle-url]`."""
    parser = argparse.ArgumentParser(
        description="Integrity SDK MCP server — exposes SDK tools to any MCP-capable agent harness."
    )
    parser.add_argument(
        "--agent-id",
        default=os.getenv("INTEGRITY_AGENT_ID", "default"),
        help="Local identity name or full DID (default: INTEGRITY_AGENT_ID env or 'default')",
    )
    parser.add_argument(
        "--oracle-url",
        default=os.getenv("ORACLE_URL", "http://localhost:8080"),
        help="integrity-oracle base URL (default: ORACLE_URL env or http://localhost:8080)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)

    try:
        import mcp.server.stdio as stdio_server
    except ImportError:
        print(
            "ERROR: mcp package not installed. Run: pip install integrity-sdk[mcp]",
            file=sys.stderr,
        )
        sys.exit(1)

    server = build_server(agent_id=args.agent_id, oracle_url=args.oracle_url)

    import asyncio

    async def _run() -> None:
        async with stdio_server.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    logger.info(
        "Integrity MCP server starting — agent_id=%s, oracle_url=%s",
        args.agent_id,
        args.oracle_url,
    )
    asyncio.run(_run())


if __name__ == "__main__":
    main()
