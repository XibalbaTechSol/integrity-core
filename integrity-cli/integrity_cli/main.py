"""
Integrity CLI -- Typer entry point.

Command groups:
  identity  DID/keypair management (local, Ed25519)
  agent     Registration/lookup against integrity-oracle, and the BCC
            pre-execution intercept gate against bcc_middleware
  config    ~/.integrity-cli/config.json management
  auth      Auth token management (no insecure default -- see config.py)
  xns       XibalbaNameService: human-readable handles for registered agents
            (contracts/src/framework/XibalbaNameService.sol, added 2026-07-11)

Scope note: the old prototype (see old repo's integrity_cli/main.py) also
had `governance`, `shield`, `credit`, and `factory` sub-apps covering things
like Smart BAAs, credit facilities, and contract factories. None of that
surface is part of docs/INTERFACE_CONTRACT.md's "core seven" packages for
this rewrite (it doesn't appear in integrity-oracle's or bcc_middleware's
pinned endpoints), so it's intentionally left out here rather than rebuilt
against guessed endpoints. Re-add it once/if a real backend contract for it
exists.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import typer
from dotenv import load_dotenv
from eth_utils import keccak
from rich.console import Console
from rich.table import Table
from web3 import Web3

from . import bcc, chain, config, hooks, identity, pack, vault, verify, wallet
from .client import ApiError, BccClient, IntegrityClient
from .config import get_auth_token, load_config, set_config_value
from integrity_sdk.did import Keypair
from integrity_sdk.registration_offchain import OffchainRegistrationError, register_offchain

# Load a local .env (if present) into os.environ *without* overriding
# variables the shell already set -- env vars set directly in the shell
# should always win over a stray .env file, same precedence dotenv itself
# defaults to. This is what lets ORACLE_URL/BCC_MIDDLEWARE_URL/AUTH_TOKEN be
# configured the same way as the other Python packages in this monorepo
# (INTERFACE_CONTRACT.md section 3), without requiring `export` in every shell.
load_dotenv()

app = typer.Typer(help="Integrity Protocol developer CLI")
console = Console()

identity_app = typer.Typer(help="Local agent identity: Ed25519 keypairs and DID documents")
app.add_typer(identity_app, name="identity")

agent_app = typer.Typer(help="Agent registration/lookup (integrity-oracle) and BCC intercept")
app.add_typer(agent_app, name="agent")

config_app = typer.Typer(help="Manage CLI configuration")
app.add_typer(config_app, name="config")

auth_app = typer.Typer(help="Manage the auth token used for Oracle/BCC middleware calls")
app.add_typer(auth_app, name="auth")

xns_app = typer.Typer(help="XibalbaNameService (XNS): human-readable handles for registered agents")
app.add_typer(xns_app, name="xns")

domain_app = typer.Typer(help="DomainRegistry: the namespace an agent joins on-chain")
app.add_typer(domain_app, name="domain")

vault_app = typer.Typer(help="Trust Vault (Persistent Memory) commands")
app.add_typer(vault_app, name="vault")

wallet_app = typer.Typer(help="EVM wallet keystores -- import a raw key once, then reference it by name")
app.add_typer(wallet_app, name="wallet")

hooks_app = typer.Typer(help="Install/uninstall harness PreToolUse and memory hooks (gate: bcc or shield; memory: cortex)")
app.add_typer(hooks_app, name="hooks")

pack_app = pack.pack_app
app.add_typer(pack_app, name="pack")


@hooks_app.command("install")
def hooks_install(
    harness: str = typer.Option(..., "--harness", help=f"Harness to install into; supported: {', '.join(hooks.SUPPORTED_HARNESSES)}"),
    gate: str = typer.Option(..., "--gate", help=f"PreToolUse gate; supported: {', '.join(hooks.SUPPORTED_GATES)}"),
    memory: Optional[str] = typer.Option(None, "--memory", help=f"PostToolUse memory target; supported: {', '.join(hooks.SUPPORTED_MEMORY)}"),
    profile_root: Optional[Path] = typer.Option(None, "--profile-root", help="Harness root; defaults to $CLAUDE_CONFIG_DIR or ~/.claude for claude-code"),
    agent_id: str = typer.Option("default", "--agent-id", help="Local identity name for this harness profile"),
):
    """
    Write a public agent.did.json into the harness root (private key stored
    outside it, via integrity_sdk's harness-root DID layout) and marker-tagged
    PreToolUse/PostToolUse hooks into the harness's settings.json.

    Idempotent: running this twice leaves settings.json unchanged beyond the
    first run (no duplicate entries, no new key, same DID).
    """
    try:
        result = hooks.install(harness=harness, gate=gate, memory=memory, profile_root=profile_root, agent_id=agent_id)
    except hooks.HookInstallError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)
    console.print(f"[bold green]Installed[/bold green] hooks for {harness!r} at [cyan]{result['profile_root']}[/cyan]")
    console.print_json(data=result)
    shield = result.get("shield_gate")
    if shield is not None:
        # The runner fails OPEN when its gate is unreachable, so an installed shield hook with no
        # daemon behind it enforces nothing -- which is exactly what the old install-time refusal
        # prevented. Say so here rather than leave it to be discovered from a silent allow.
        if not shield["listening"]:
            console.print(
                f"[bold yellow]Warning:[/bold yellow] no Shield gate daemon is listening at "
                f"[cyan]{shield['socket']}[/cyan]. Until one is, tool calls proceed [bold]UNCHECKED[/bold] "
                "(the runner fails open and logs each one to stderr)."
            )
        console.print(
            "Shield denies tool calls from any agent not registered with the daemon. Start it with:\n"
            f"  shield gate-daemon --device-id <id> --register-agent {shield['register_agent']}"
        )


@hooks_app.command("uninstall")
def hooks_uninstall(
    harness: str = typer.Option(..., "--harness", help=f"Harness to uninstall from; supported: {', '.join(hooks.SUPPORTED_HARNESSES)}"),
    profile_root: Optional[Path] = typer.Option(None, "--profile-root", help="Harness root; defaults to $CLAUDE_CONFIG_DIR or ~/.claude for claude-code"),
):
    """
    Remove exactly the marker-tagged hook entries `hooks install` wrote.
    Leaves agent.did.json and the private key in place -- identity outlives
    hook configuration. A no-op if nothing is installed.
    """
    try:
        result = hooks.uninstall(harness=harness, profile_root=profile_root)
    except hooks.HookInstallError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)
    console.print(f"[green]done[/green] removed {result['removed_hook_entries']} hook entr{'y' if result['removed_hook_entries'] == 1 else 'ies'} from [cyan]{result['settings_file']}[/cyan]")
    console.print_json(data=result)


@app.command("verify")
def verify_command(
    receipts: Path = typer.Option(..., "--receipts", exists=True, readable=True, help="Receipt bundle JSON file or JSON array"),
    trusted_signer: list[str] = typer.Option([], "--trusted-signer", help="Trusted z-prefixed Ed25519 public key; repeatable"),
    checkpoint: Optional[Path] = typer.Option(None, "--checkpoint", exists=True, readable=True, help="Checkpoint JSON file"),
    proof: Optional[Path] = typer.Option(None, "--proof", exists=True, readable=True, help="Inclusion proof JSON file"),
    anchor_root: Optional[str] = typer.Option(None, "--anchor-root", help="Read-back anchor root for local comparison (0x + 32 bytes)"),
    anchor_contract: Optional[str] = typer.Option(None, "--anchor-contract", help="StateAnchor address for local Anvil read-back"),
    rpc_url: Optional[str] = typer.Option(None, "--rpc-url", help="RPC URL used with --anchor-contract (defaults to RPC_URL or localhost)"),
    decision_trace: Optional[Path] = typer.Option(None, "--decision-trace", exists=True, readable=True, help="DecisionTrace events JSON file (array of DecisionEnvelope-shaped objects, each optionally carrying an 'advisory' field)"),
    trace_evidence: Optional[Path] = typer.Option(None, "--trace-evidence", exists=True, readable=True, help="DecisionTraceEvidence JSON file (trace_id, root, event_count, receipt_hash?, checkpoint_root?)"),
    json_output: bool = typer.Option(False, "--json-output", help="Emit machine-readable JSON"),
) -> None:
    """Verify receipt signatures, chain, checkpoint, and optional inclusion proof offline.

    This command never claims public-chain finality.  ``--anchor-root`` only
    compares a supplied read-back root to the verified checkpoint root.

    ``--decision-trace``/``--trace-evidence`` additionally verify a B4
    DecisionTrace's parent links and domain-separated Merkle inclusion
    (``integrity_sdk.core.verify_decision_trace_offline``), and report any
    carried Jev advisory status (``available``/``unavailable``/``rejected``)
    separately from evidence validity -- a missing or failed advisory never
    fails this command on its own; only a genuinely broken trace does.
    """
    result: dict[str, Any] = {
        "scope": "local", "valid": False, "signature": "not_checked", "chain": "not_checked",
        "checkpoint": "not_requested", "inclusion": "not_requested", "anchor": "not_requested",
        "decision_trace": "not_requested", "advisory_status": "not_requested",
    }
    try:
        if not trusted_signer:
            raise verify.VerifyError("MALFORMED", "at least one --trusted-signer is required")
        if trace_evidence is not None and decision_trace is None:
            raise verify.VerifyError("MALFORMED", "--trace-evidence requires --decision-trace")
        if decision_trace is not None and trace_evidence is None:
            raise verify.VerifyError("MALFORMED", "--decision-trace requires --trace-evidence")
        bundle = verify.load_json(receipts)
        if isinstance(bundle, list):
            receipt_values = bundle
            bundle_checkpoint = None
        elif isinstance(bundle, dict) and isinstance(bundle.get("receipts"), list):
            receipt_values = bundle["receipts"]
            bundle_checkpoint = bundle.get("checkpoint")
        else:
            raise verify.VerifyError("MALFORMED", "receipt input must be an array or {receipts, checkpoint}")
        selected_checkpoint = verify.load_json(checkpoint) if checkpoint else bundle_checkpoint
        summary = verify.verify_bundle(receipt_values, trusted_signer, selected_checkpoint)
        result.update({"signature": "pass", "chain": "pass", "receipts": summary["receipts"], "log_id": summary["log_id"]})
        if selected_checkpoint is not None:
            result["checkpoint"] = "pass"
        if proof:
            proof_doc = verify.load_json(proof)
            if not isinstance(proof_doc, dict) or not isinstance(proof_doc.get("proof"), list):
                raise verify.VerifyError("MALFORMED", "proof input must be {receipt, proof, checkpoint?}")
            proof_checkpoint = proof_doc.get("checkpoint", selected_checkpoint)
            if proof_checkpoint is None:
                raise verify.VerifyError("MALFORMED", "inclusion proof requires a checkpoint")
            verify.verify_inclusion(proof_doc.get("receipt"), proof_doc["proof"], proof_checkpoint, trusted_signer)
            result["inclusion"] = "pass"
        if anchor_contract is not None:
            if selected_checkpoint is None or not proof:
                raise verify.VerifyError("MALFORMED", "--anchor-contract requires a checkpoint and --proof")
            if not isinstance(proof_doc.get("receipt"), dict):
                raise verify.VerifyError("MALFORMED", "proof receipt must be a JSON object")
            try:
                w3 = chain.get_w3(rpc_url or os.getenv("RPC_URL", "http://localhost:8545"))
                if not w3.is_connected():
                    raise RuntimeError("RPC is not reachable")
                state_anchor = chain._contract(w3, "StateAnchor", address=anchor_contract)
                # Not `latestRoot() == checkpoint.root`: B4's dedicated protocol evidence
                # anchor is shared across every agent/gate, so a checkpoint anchored a
                # moment before a different one is no less valid -- StateAnchor.sol keeps
                # every root it has ever anchored individually verifiable
                # (`isAnchoredRoot`), and `verifyLeaf` already checks exactly that. Requiring
                # "latest" here would make this command spuriously fail for any checkpoint
                # that wasn't the single most recent one anchored to a shared contract.
                proof_nodes = [bytes.fromhex(node.removeprefix("0x")) for node in proof_doc["proof"]]
                if not state_anchor.functions.verifyLeaf(
                    bytes.fromhex(selected_checkpoint["root"][2:]),
                    verify.receipt_leaf(proof_doc["receipt"]),
                    proof_nodes,
                ).call():
                    raise verify.VerifyError("NOT_INCLUDED", "StateAnchor did not anchor this root, or rejected the inclusion proof")
                result["anchor"] = "pass"
                result["anchor_scope"] = "local_rpc"
            except verify.VerifyError:
                raise
            except (ValueError, TypeError, OSError, RuntimeError) as exc:
                raise verify.VerifyError("ANCHOR_UNAVAILABLE", str(exc)) from exc
        if anchor_root is not None:
            if selected_checkpoint is None:
                raise verify.VerifyError("MALFORMED", "--anchor-root requires a checkpoint")
            if not verify.is_hex32(anchor_root):
                raise verify.VerifyError("MALFORMED", "--anchor-root must be 0x + 64 lowercase hex")
            result["anchor"] = "pass" if anchor_root == selected_checkpoint["root"] else "fail"
            if result["anchor"] == "fail":
                raise verify.VerifyError("ROOT_MISMATCH", "anchor root differs from checkpoint root")
        if decision_trace is not None:
            from integrity_sdk.core import (
                DecisionEnvelope, DecisionTrace, DecisionTraceError, DecisionTraceEvidence,
                verify_decision_trace_offline,
            )

            raw_events = verify.load_json(decision_trace)
            if not isinstance(raw_events, list) or not raw_events:
                raise verify.VerifyError("MALFORMED", "--decision-trace must be a non-empty JSON array")
            advisory_statuses: list[str] = []
            try:
                envelopes = []
                for item in raw_events:
                    if not isinstance(item, dict):
                        raise verify.VerifyError("MALFORMED", "each decision-trace event must be a JSON object")
                    fields = {k: v for k, v in item.items() if k not in ("envelope_version", "advisory")}
                    advisory = item.get("advisory")
                    if isinstance(advisory, dict) and advisory.get("status"):
                        advisory_statuses.append(str(advisory["status"]))
                    envelopes.append(DecisionEnvelope(**fields))
                trace = DecisionTrace(envelopes[0].trace_id, envelopes[0].tenant_id, envelopes[0].agent_id)
                for envelope in envelopes:
                    trace = trace.append(envelope)
                evidence_doc = verify.load_json(trace_evidence)
                if not isinstance(evidence_doc, dict):
                    raise verify.VerifyError("MALFORMED", "--trace-evidence must be a JSON object")
                evidence = DecisionTraceEvidence(
                    trace_id=evidence_doc["trace_id"], root=evidence_doc["root"],
                    event_count=evidence_doc["event_count"], receipt_hash=evidence_doc.get("receipt_hash"),
                    checkpoint_root=evidence_doc.get("checkpoint_root"),
                )
                # Cross-check against this same invocation's already-verified receipt, when the
                # evidence names one and exactly one receipt was supplied -- never a network call.
                linked_receipt = receipt_values[0] if evidence.receipt_hash is not None and len(receipt_values) == 1 else None
                trace_result = verify_decision_trace_offline(
                    trace, evidence, receipt=linked_receipt, trusted_signers=trusted_signer,
                )
            except (DecisionTraceError, KeyError, TypeError) as exc:
                raise verify.VerifyError("TRACE_INVALID", str(exc)) from exc
            if not trace_result.valid:
                raise verify.VerifyError("TRACE_INVALID", trace_result.detail)
            result["decision_trace"] = "pass"
            # Advisory status is reported, never a reason this command fails: a provider
            # outage or a missing projection is a visible fact about the trace, not a
            # defect in the evidence (C11 -- Jev is advisory, never authoritative).
            if not advisory_statuses:
                result["advisory_status"] = "not_present"
            elif all(status == "available" for status in advisory_statuses):
                result["advisory_status"] = "available"
            elif any(status == "rejected" for status in advisory_statuses):
                result["advisory_status"] = "rejected"
            else:
                result["advisory_status"] = "unavailable"
        result["valid"] = True
    except verify.VerifyError as exc:
        result.update({"valid": False, "error": {"code": exc.code, "detail": exc.detail}})
    if json_output:
        # Rich wraps long strings to terminal width; machine-readable output
        # must remain one valid JSON document even for verbose error details.
        typer.echo(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        console.print("[green]PASS[/green] local receipt verification" if result["valid"] else f"[red]FAIL[/red] {result.get('error', {}).get('code', 'verification failed')}")
        console.print(json.dumps(result, indent=2, sort_keys=True))
    if not result["valid"]:
        raise typer.Exit(1)


# --------------------------------------------------------------------------
# wallet
# --------------------------------------------------------------------------

@wallet_app.command("import")
def wallet_import(
    identity_name: str = typer.Option(..., "--identity", help="Local wallet identity name to store this key under (e.g. 'operator')"),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing keystore for this identity instead of refusing"),
) -> None:
    """
    Import an existing raw private key into an encrypted keystore, ONE TIME,
    so it never has to be typed or pasted again after this.

    Added 2026-09-14: the protocol's single operator key (DEFAULT_ADMIN_ROLE/
    MINTER_ROLE/governance/arbitrator/disputer on Base Sepolia) was pasted
    into a chat session during troubleshooting and subsequently lost -- every
    agent identity already got proper keystore protection via
    `generate_or_load_evm_wallet`, but the operator/funder key never did.
    Run this once for a recovered or freshly rotated operator key, so on-chain
    commands can use the encrypted keystore instead of a raw FUNDER_PRIVATE_KEY
    env var. Requires INTEGRITY_WALLET_PASSWORD in the environment
    (same as every other keystore in this CLI) to encrypt the imported key.

    The private key is read from a hidden interactive prompt only -- never
    a CLI argument (would leak into shell history / `ps`) or an env var
    (would leak into the process's environment listing / any logging that
    dumps env). This command is the intended way to get a raw key onto disk
    at all; after this, only INTEGRITY_WALLET_PASSWORD is ever needed.
    """
    import getpass

    raw_key = getpass.getpass(f"Private key to import for identity '{identity_name}' (input hidden): ").strip()
    if not raw_key:
        console.print("[bold red]Error:[/bold red] no key entered")
        raise typer.Exit(1)
    try:
        account = wallet.import_evm_wallet(identity_name, raw_key, force=force)
    except wallet.WalletAlreadyExistsError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)
    except wallet.WalletPasswordNotSet as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)
    finally:
        # Best-effort: drop our only in-process reference to the plaintext
        # promptly rather than leaving it reachable for the rest of the
        # process's life. Python can't guarantee secure erasure of a str,
        # but there's no reason to hold it longer than needed either.
        raw_key = "0" * len(raw_key)
    console.print(f"[green]done[/green] imported and encrypted -- identity [cyan]{identity_name}[/cyan] now at [cyan]{account.address}[/cyan]")
    console.print(f"  Keystore: {wallet.wallet_dir(identity_name) / 'keystore.json'}")
    console.print("  The raw key was never written to disk and is no longer needed -- only INTEGRITY_WALLET_PASSWORD from here on.")


@wallet_app.command("address")
def wallet_address(
    identity_name: str = typer.Option(..., "--identity", help="Local wallet identity name to look up"),
) -> None:
    """Read-only address lookup -- does not require INTEGRITY_WALLET_PASSWORD."""
    addr = wallet.load_evm_address(identity_name)
    if addr is None:
        console.print(f"[yellow]no keystore found for identity[/yellow] {identity_name!r}")
        raise typer.Exit(1)
    console.print(addr)


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------

@config_app.command("set")
def config_set(key: str, value: str):
    """Set a configuration value (e.g. ORACLE_URL, BCC_MIDDLEWARE_URL)."""
    set_config_value(key, value)
    console.print(f"[green]Config updated:[/green] {key} = {value}")


@config_app.command("show")
def config_show():
    """Show the effective configuration, and for each key, whether its value
    came from an environment variable, the on-disk config file, or is just
    the built-in default (helps debug "why isn't my ORACLE_URL override
    taking effect" style questions)."""
    effective = load_config()
    on_disk: dict = {}
    if config.CONFIG_FILE.exists():
        try:
            on_disk = json.loads(config.CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            on_disk = {}

    table = Table(title="Integrity CLI Configuration")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="magenta")
    table.add_column("Source", style="dim")
    for key in sorted(effective):
        if key in os.environ:
            value, source = os.environ[key], "env"
        elif key in on_disk:
            value, source = on_disk[key], "config file"
        else:
            value, source = effective[key], "default"
        if key == "AUTH_TOKEN" and value:
            # Never print a real token to the terminal/scrollback in full.
            value = f"{value[:4]}…(masked)"
        table.add_row(key, value if value else "(unset)", source)
    console.print(table)


# --------------------------------------------------------------------------
# auth
# --------------------------------------------------------------------------

@auth_app.command("set-token")
def auth_set_token(
    token: str = typer.Argument(..., help="Bearer token for Oracle/BCC middleware auth")
):
    """
    Store an auth token in the local config file.

    There is no default token shipped with this CLI -- the old prototype's
    hardcoded "mock_demo_token" default was exactly the kind of insecure
    default that quietly authenticates against a real deployment if the
    config is ever copied somewhere it shouldn't be. You must set a real
    token explicitly, or export AUTH_TOKEN in your environment instead.
    """
    set_config_value("AUTH_TOKEN", token)
    console.print("[green]AUTH_TOKEN saved.[/green]")


@auth_app.command("show")
def auth_show():
    """Show whether an auth token is configured (masked; never printed in full)."""
    try:
        token = get_auth_token()
    except ValueError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)
    if not token:
        console.print("[yellow]No AUTH_TOKEN configured.[/yellow] "
                      "Set one with `integrity auth set-token <token>`.")
        raise typer.Exit(1)
    console.print(f"AUTH_TOKEN: {token[:4]}…(masked)")


# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------

@identity_app.command("keygen")
def identity_keygen(
    name: str = typer.Option("default", "--name", help="Local identity name (for managing multiple keys)"),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing identity with this name"),
):
    """
    Generate a new Ed25519 keypair and print its DID document
    (INTERFACE_CONTRACT.md section 4.1).

    The private key is written to $INTEGRITY_DID_HOME/<name>/private_key.pem
    (default ~/.integrity/did/<name>/private_key.pem -- the same location
    integrity-sdk uses, see identity.py's module docstring)
    (file mode 0600) and is never printed to the terminal.
    """
    try:
        doc = identity.generate_identity(name, force=force)
    except FileExistsError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)
    console.print(f"[bold green]Identity '{name}' created.[/bold green]")
    console.print_json(data=doc)


@identity_app.command("show")
def identity_show(
    name: str = typer.Option("default", "--name", help="Local identity name"),
):
    """Print the DID document for a local identity."""
    try:
        doc = identity.did_document(name)
    except (FileNotFoundError, TypeError) as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)
    console.print_json(data=doc)


# --------------------------------------------------------------------------
# agent
# --------------------------------------------------------------------------

@agent_app.command("register")
def agent_register(
    identity_name: str = typer.Option(
        "default", "--identity", help="Local identity to register (see `integrity identity keygen`)"
    ),
    handle: Optional[str] = typer.Option(
        None, "--handle", help="Optional unique XNS handle to claim for this agent"
    ),
    oracle_url: Optional[str] = typer.Option(
        None, "--oracle-url", help="integrity-oracle base URL (env/config ORACLE_URL)"
    ),
):
    """
    Register a local identity with the Oracle, gas-free.

    Proves control of the identity's Ed25519 key by signing a registration
    message; no chain state is touched, so no funder wallet, RPC endpoint or
    deployments file is needed. A proven key is verification tier 1.
    Re-running is safe: an already-registered DID is reported, never lowered.
    """
    try:
        doc = identity.did_document(identity_name)
        private_key = identity.load_private_key(identity_name)
    except (FileNotFoundError, TypeError) as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)
    agent_did = doc["id"]
    oracle_url = oracle_url or config.get_config_value("ORACLE_URL")

    try:
        with console.status("[bold blue]Registering with Oracle..."):
            result = register_offchain(
                oracle_url, agent_did, Keypair(private_key), handle=handle, did_document=doc
            )
    except OffchainRegistrationError as e:
        if e.status is None:
            console.print(f"[bold red]Error:[/bold red] Oracle unreachable at {oracle_url}: {e.detail}")
        else:
            console.print(f"[bold red]Error:[/bold red] Oracle rejected the registration ({e.status}): {e.detail}")
        raise typer.Exit(1)
    typer.echo(f"registered {result.agent_id} tier={result.verification_tier} ({result.outcome})")


@agent_app.command("show")
def agent_show(agent_id: str = typer.Argument(..., help="Agent DID, e.g. did:integrity:...")):
    """Look up an agent's record from integrity-oracle."""
    client = IntegrityClient()
    try:
        with console.status(f"[bold blue]Fetching {agent_id}..."):
            result = client.get(f"/v1/agent/{agent_id}")
    except ApiError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)
    console.print_json(data=result)


@agent_app.command("ais")
def agent_ais(agent_id: str = typer.Argument(..., help="Agent DID")):
    """
    Fetch the Agent Integrity Score for an agent from integrity-oracle.

    AIS is computed once, centrally, in integrity-oracle/scoring-core
    (INTERFACE_CONTRACT.md section 4.3) -- this command intentionally does
    not recompute the formula locally, it only displays the oracle's
    answer, since the oracle is the single source of truth for the score.
    """
    client = IntegrityClient()
    try:
        with console.status(f"[bold blue]Fetching AIS for {agent_id}..."):
            result = client.get(f"/v1/agent/{agent_id}/ais")
    except ApiError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)
    console.print_json(data=result)


@agent_app.command("intercept")
def agent_intercept(
    identity_name: str = typer.Option(
        "default", "--identity", help="Local identity signing this commitment"
    ),
    intent_type: str = typer.Option(
        ..., "--intent-type", "-t",
        help="Intent type, e.g. 'payment', 'data_access', 'contract_call'",
    ),
    payload_json: str = typer.Option(
        "{}", "--payload", "-p", help="JSON intent payload to hash and commit to"
    ),
    covered_entity: str = typer.Option(
        None,
        "--covered-entity",
        help="0x EVM address of the covered entity (hospital) for a healthcare/clinical intent; "
        "required whenever the intent triggers OPA's requires_baa (e.g. EMR_WRITE)",
    ),
    deployments_file: Optional[str] = typer.Option(
        None, "--deployments-file", help="Path to deployments.local.json (env DEPLOYMENTS_FILE)"
    ),
):
    """
    Build a real BCC Commitment (INTERFACE_CONTRACT.md section 4.2), sign it
    with the local identity's Ed25519 key, and POST it to bcc_middleware's
    pre-execution policy gate (POST /v1/bcc/intercept).

    This is the CLI-driven equivalent of an agent calling the same endpoint
    via integrity-sdk before acting -- useful for developers debugging
    policy decisions without running a full agent.
    """
    try:
        intent_payload = json.loads(payload_json)
    except json.JSONDecodeError as e:
        console.print(f"[bold red]Invalid --payload JSON:[/bold red] {e}")
        raise typer.Exit(1)

    try:
        private_key = identity.load_private_key(identity_name)
    except FileNotFoundError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    # docs/plans/2026-08-18-phase1-canonical-intent-encoding-proposal.md: every
    # commitment now binds the chain/registry it was signed against. Read
    # straight from the deployments file's top-level "chainId" rather than
    # opening an RPC connection -- this command otherwise never touches the
    # chain, and adding a live RPC dependency here would be a bigger change
    # than this command needs.
    deployments_file = deployments_file or os.getenv("DEPLOYMENTS_FILE", "../deployments.local.json")
    try:
        deployments = chain.load_deployments(deployments_file)
        target_chain_id = deployments["chainId"]
        verifying_contract = deployments["singletons"]["XibalbaAgentRegistry"]
    except (chain.DeploymentsFileMissing, KeyError) as e:
        console.print(f"[bold red]Error:[/bold red] could not resolve chain_id/verifying_contract from {deployments_file}: {e}")
        raise typer.Exit(1)

    agent_did = identity.did_document_for_key(private_key.public_key())["id"]
    commitment = bcc.build_commitment(
        private_key,
        agent_did,
        intent_type,
        intent_payload,
        target_chain_id,
        verifying_contract,
        covered_entity_address=covered_entity,
    )

    client = BccClient()
    try:
        with console.status("[bold blue]Submitting BCC commitment..."):
            # INTERFACE_CONTRACT.md section 4.2: "This exact shape is POSTed"
            # -- the commitment object itself is the request body, not
            # wrapped in an envelope.
            result = client.post("/v1/bcc/intercept", json_data=commitment)
    except ApiError as e:
        console.print(f"[bold red]Error querying BCC middleware:[/bold red] {e}")
        raise typer.Exit(1)

    authorized = bool(result.get("authorized", False))
    reason = result.get("reason", "n/a")
    color = "green" if authorized else "red"
    console.print(f"Commitment: [dim]{commitment['agent_id']} nonce={commitment['nonce']}[/dim]")
    console.print(
        f"BCC Decision: [bold {color}]{'AUTHORIZED' if authorized else 'REJECTED'}[/bold {color}]"
    )
    console.print(f"Reason: [yellow]{reason}[/yellow]")
    if authorized and result.get("verification_token"):
        console.print(f"Verification Token: [dim]{result['verification_token']}[/dim]")
    if not authorized:
        raise typer.Exit(1)


# --------------------------------------------------------------------------
# domain
# --------------------------------------------------------------------------

_RPC_URL_OPTION = typer.Option(None, "--rpc-url", help="EVM RPC endpoint (env RPC_URL, default http://localhost:8545)")
_DEPLOYMENTS_FILE_OPTION = typer.Option(
    None, "--deployments-file", help="Path to deployments.local.json (env DEPLOYMENTS_FILE)"
)


def _domain_setup(rpc_url: Optional[str], deployments_file: Optional[str]) -> tuple[Web3, str, int]:
    """Shared connect/resolve-address logic for domain_app commands, mirroring _xns_setup below."""
    rpc_url = rpc_url or os.getenv("RPC_URL", "http://localhost:8545")
    deployments_file = deployments_file or os.getenv("DEPLOYMENTS_FILE", "../deployments.local.json")

    try:
        w3 = chain.get_w3(rpc_url)
        if not w3.is_connected():
            console.print(f"[bold red]Error:[/bold red] RPC {rpc_url} is unreachable.")
            raise typer.Exit(1)
        chain_id = w3.eth.chain_id
    except typer.Exit:
        raise
    except Exception as e:  # noqa: BLE001
        console.print(f"[bold red]Error:[/bold red] could not connect to RPC {rpc_url}: {e}")
        raise typer.Exit(1)

    try:
        deployments = chain.load_deployments(deployments_file)
        domain_registry_address = deployments["singletons"]["DomainRegistry"]
    except (chain.DeploymentsFileMissing, KeyError) as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    return w3, domain_registry_address, chain_id


@domain_app.command("status")
def domain_status(
    name: str = typer.Argument(..., help="Domain name, e.g. 'my-agent.integrity'"),
    identity_name: str = typer.Option(
        "default", "--identity", help="Whose wallet address to check canJoin for (no signing, read-only)"
    ),
    rpc_url: Optional[str] = _RPC_URL_OPTION,
    deployments_file: Optional[str] = _DEPLOYMENTS_FILE_OPTION,
):
    """Read-only: does `name` exist in DomainRegistry, and can --identity's wallet join it?
    Run this before joining a domain on-chain for any domain you haven't already
    verified."""
    w3, domain_registry_address, _chain_id = _domain_setup(rpc_url, deployments_file)
    domain_id = keccak(text=name)
    exists = chain.domain_exists(w3, domain_registry_address, domain_id)
    if not exists:
        console.print(f"[yellow]does not exist[/yellow]  domain {name!r} has not been registered in DomainRegistry")
        raise typer.Exit(1)

    evm_account = wallet.generate_or_load_evm_wallet(identity_name)
    can_join = chain.can_join_domain(w3, domain_registry_address, domain_id, evm_account.address)
    status_text = "[green]can join[/green]" if can_join else "[red]cannot join[/red]"
    console.print(f"{status_text}  domain {name!r} exists; {identity_name}'s wallet {evm_account.address} {'can' if can_join else 'cannot'} join it")
    if not can_join:
        raise typer.Exit(1)


@domain_app.command("register")
def domain_register(
    name: str = typer.Argument(..., help="Domain name to claim, e.g. 'my-agent.integrity'"),
    identity_name: str = typer.Option(
        "default", "--identity", help="Whose wallet signs and becomes the domain's owner"
    ),
    permissioned: bool = typer.Option(
        False, "--permissioned", help="Restrict joining to addresses the owner explicitly approves "
                                       "(default: Open -- anyone can join, appropriate for a personal per-agent domain)"
    ),
    rpc_url: Optional[str] = _RPC_URL_OPTION,
    deployments_file: Optional[str] = _DEPLOYMENTS_FILE_OPTION,
):
    """
    Claims `name` in DomainRegistry, owned by --identity's wallet -- permissionless,
    first-come-first-served, same trust model as ENS second-level names. Use --permissioned
    to register the domain in permissioned mode.
    """
    w3, domain_registry_address, chain_id = _domain_setup(rpc_url, deployments_file)
    domain_id = keccak(text=name)
    if chain.domain_exists(w3, domain_registry_address, domain_id):
        console.print(f"[bold red]Error:[/bold red] domain {name!r} already exists in DomainRegistry.")
        raise typer.Exit(1)

    try:
        evm_account = wallet.generate_or_load_evm_wallet(identity_name)
    except wallet.WalletPasswordNotSet as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    with console.status(f"[bold blue]Registering domain {name!r}..."):
        tx_hash = chain.register_domain(w3, evm_account, domain_registry_address, name, chain_id, open_mode=not permissioned)
    console.print(
        f"[bold green]Registered:[/bold green] {name!r} ({'Permissioned' if permissioned else 'Open'}), "
        f"owned by {evm_account.address} (tx {tx_hash})"
    )


# --------------------------------------------------------------------------
# xns
# --------------------------------------------------------------------------


def _xns_setup(rpc_url: Optional[str], deployments_file: Optional[str]) -> tuple[Web3, str, int]:
    """
    Shared connect/resolve-address logic for every xns_app command:
    connects to the RPC, loads the deployments file, and pulls
    `singletons.XibalbaNameService`'s address out of it. Factored out since
    all five xns commands below need exactly this, mirroring how
    `agent_register` inlines the equivalent connect+load steps for its own
    single command (xns has five, so it's worth sharing here).
    """
    rpc_url = rpc_url or os.getenv("RPC_URL", "http://localhost:8545")
    deployments_file = deployments_file or os.getenv("DEPLOYMENTS_FILE", "../deployments.local.json")

    try:
        w3 = chain.get_w3(rpc_url)
        if not w3.is_connected():
            console.print(f"[bold red]Error:[/bold red] RPC {rpc_url} is unreachable.")
            raise typer.Exit(1)
        chain_id = w3.eth.chain_id
    except typer.Exit:
        raise
    except Exception as e:  # noqa: BLE001 -- surfaced to the user, not swallowed
        console.print(f"[bold red]Error:[/bold red] could not connect to RPC {rpc_url}: {e}")
        raise typer.Exit(1)

    try:
        deployments = chain.load_deployments(deployments_file)
        xns_address = deployments["singletons"]["XibalbaNameService"]
    except (chain.DeploymentsFileMissing, KeyError) as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    return w3, xns_address, chain_id




def _resolve_own_sovereign_agent(identity_name: str) -> str:
    """
    Every XNS write call must be routed through the caller's own
    `SovereignAgent.execute` (see chain.py's `_xns_send_via_agent` docstring
    on why -- `isRegisteredAgent` only recognizes that contract address, not
    the controller EOA). This identity's `SovereignAgent` address isn't
    persisted locally (off-chain `integrity agent register` deploys nothing), so it's resolved the
    same way `agent_show`/`agent_ais` already resolve agent state: a
    `GET /v1/agent/{did}` against integrity-oracle, which caches exactly
    this mapping (see `integrity-oracle`'s `primitives.sovereign_agent`).
    """
    try:
        doc = identity.did_document(identity_name)
    except (FileNotFoundError, TypeError) as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)
    did = doc["id"]

    client = IntegrityClient()
    try:
        result = client.get(f"/v1/agent/{did}")
    except ApiError as e:
        console.print(f"[bold red]Error:[/bold red] could not resolve {did} from integrity-oracle: {e}")
        raise typer.Exit(1)

    primitives = result.get("primitives") or {}
    sovereign_agent = primitives.get("sovereign_agent")
    if not sovereign_agent:
        console.print(
            f"[bold red]Error:[/bold red] integrity-oracle has no SovereignAgent address for {did} -- "
            "register this identity first with `integrity agent register`."
        )
        raise typer.Exit(1)
    return sovereign_agent


@xns_app.command("register")
def xns_register(
    handle: str = typer.Argument(..., help='Handle to claim, e.g. "hermes.integrity"'),
    identity_name: str = typer.Option("default", "--identity", help="Local identity claiming the handle"),
    rpc_url: Optional[str] = _RPC_URL_OPTION,
    deployments_file: Optional[str] = _DEPLOYMENTS_FILE_OPTION,
):
    """
    Self-service claim a handle for a local identity's already-registered
    agent. Reverts on-chain (surfaced below) if this identity isn't a real
    registered agent yet (`integrity agent register` it first) or if the
    handle is already taken -- see XibalbaNameService.sol's NatSpec.
    """
    w3, xns_address, chain_id = _xns_setup(rpc_url, deployments_file)
    sovereign_agent = _resolve_own_sovereign_agent(identity_name)
    try:
        evm_account = wallet.generate_or_load_evm_wallet(identity_name)
    except wallet.WalletPasswordNotSet as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    try:
        with console.status(f"[bold blue]Registering handle '{handle}'..."):
            receipt = chain.xns_register(w3, evm_account, sovereign_agent, xns_address, handle, chain_id)
    except Exception as e:  # noqa: BLE001 -- includes on-chain reverts (NotRegisteredAgent, HandleAlreadyRegistered)
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    console.print(f"[bold green]Registered[/bold green] '{handle}' -> {sovereign_agent}")
    console.print(f"[dim]tx: {receipt['transactionHash'].hex()}[/dim]")


@xns_app.command("resolve")
def xns_resolve(
    handle: str = typer.Argument(..., help="Handle to resolve"),
    rpc_url: Optional[str] = _RPC_URL_OPTION,
    deployments_file: Optional[str] = _DEPLOYMENTS_FILE_OPTION,
):
    """Resolve a handle to its owning agent's SovereignAgent address."""
    w3, xns_address, _chain_id = _xns_setup(rpc_url, deployments_file)
    result = chain.xns_resolve(w3, xns_address, handle)
    if result is None:
        console.print(f"[bold red]Not found:[/bold red] '{handle}' is not registered.")
        raise typer.Exit(1)
    console.print(f"{handle} -> [bold]{result}[/bold]")


@xns_app.command("primary-handle")
def xns_primary_handle(
    sovereign_agent: str = typer.Argument(..., help="SovereignAgent address to look up"),
    rpc_url: Optional[str] = _RPC_URL_OPTION,
    deployments_file: Optional[str] = _DEPLOYMENTS_FILE_OPTION,
):
    """Look up an agent's current primary handle (empty string if it has none)."""
    w3, xns_address, _chain_id = _xns_setup(rpc_url, deployments_file)
    handle = chain.xns_primary_handle(w3, xns_address, sovereign_agent)
    if not handle:
        console.print(f"[yellow]{sovereign_agent} has no registered handle.[/yellow]")
        raise typer.Exit(1)
    console.print(f"{sovereign_agent} -> [bold]{handle}[/bold]")


@xns_app.command("set-primary")
def xns_set_primary(
    handle: str = typer.Argument(..., help="Handle (already owned by this identity) to make primary"),
    identity_name: str = typer.Option("default", "--identity", help="Local identity whose primary handle to change"),
    rpc_url: Optional[str] = _RPC_URL_OPTION,
    deployments_file: Optional[str] = _DEPLOYMENTS_FILE_OPTION,
):
    """Change which of an agent's owned handles `primary-handle` returns for it."""
    w3, xns_address, chain_id = _xns_setup(rpc_url, deployments_file)
    sovereign_agent = _resolve_own_sovereign_agent(identity_name)
    try:
        evm_account = wallet.generate_or_load_evm_wallet(identity_name)
    except wallet.WalletPasswordNotSet as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    try:
        with console.status(f"[bold blue]Setting primary handle to '{handle}'..."):
            receipt = chain.xns_set_primary_handle(w3, evm_account, sovereign_agent, xns_address, handle, chain_id)
    except Exception as e:  # noqa: BLE001 -- includes on-chain reverts (HandleNotFound, NotHandleOwner)
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    console.print(f"[bold green]Primary handle set[/bold green] to '{handle}' for {sovereign_agent}")
    console.print(f"[dim]tx: {receipt['transactionHash'].hex()}[/dim]")


@xns_app.command("release")
def xns_release(
    handle: str = typer.Argument(..., help="Handle (owned by this identity) to release"),
    identity_name: str = typer.Option("default", "--identity", help="Local identity releasing the handle"),
    rpc_url: Optional[str] = _RPC_URL_OPTION,
    deployments_file: Optional[str] = _DEPLOYMENTS_FILE_OPTION,
):
    """Voluntarily release a handle this identity's agent owns, freeing it for anyone to claim."""
    w3, xns_address, chain_id = _xns_setup(rpc_url, deployments_file)
    sovereign_agent = _resolve_own_sovereign_agent(identity_name)
    try:
        evm_account = wallet.generate_or_load_evm_wallet(identity_name)
    except wallet.WalletPasswordNotSet as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    try:
        with console.status(f"[bold blue]Releasing handle '{handle}'..."):
            receipt = chain.xns_release(w3, evm_account, sovereign_agent, xns_address, handle, chain_id)
    except Exception as e:  # noqa: BLE001 -- includes on-chain reverts (HandleNotFound, NotHandleOwner)
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    console.print(f"[bold green]Released[/bold green] '{handle}'")
    console.print(f"[dim]tx: {receipt['transactionHash'].hex()}[/dim]")


# The commands above (register/resolve/primary-handle/set-primary/release) are all
# on-chain, wallet-signed calls against the deployed XibalbaNameService contract -- an
# optional "list this handle as an on-chain alias" step. The two below are unrelated:
# they talk to Oracle's own local `xns_handles` directory (integrity-oracle migration
# 0022) -- no wallet, no gas, no chain at all. This is the mandatory, primary handle
# every agent gets at `integrity agent register`; on-chain listing is separate and optional.

@xns_app.command("available")
def xns_available(
    handle: str = typer.Argument(..., help="Candidate handle to check"),
    oracle_url: Optional[str] = typer.Option(
        None, "--oracle-url", help="integrity-oracle base URL (env/config ORACLE_URL)"
    ),
):
    """Check whether a handle is free in Oracle's local XNS directory (no chain, no wallet)."""
    oracle_client = IntegrityClient(base_url=oracle_url or config.get_config_value("ORACLE_URL"))
    result = oracle_client.get(f"/v1/xns/available/{handle}")
    if result.get("available"):
        console.print(f"[bold green]Available:[/bold green] '{handle}'")
    else:
        console.print(f"[yellow]Taken:[/yellow] '{handle}'")
        for s in result.get("suggestions", []):
            console.print(f"  suggestion: {s}")


@xns_app.command("claim")
def xns_claim(
    agent_id: str = typer.Argument(..., help="Agent DID (or bare agent_id) claiming this handle"),
    handle: str = typer.Argument(..., help="Handle to claim"),
    oracle_url: Optional[str] = typer.Option(
        None, "--oracle-url", help="integrity-oracle base URL (env/config ORACLE_URL)"
    ),
):
    """Claim a handle in Oracle's local XNS directory for an agent that already has one
    without one, or that was registered before this feature existed. Not needed for a
    fresh `integrity agent register`."""
    oracle_client = IntegrityClient(base_url=oracle_url or config.get_config_value("ORACLE_URL"))
    try:
        result = oracle_client.post("/v1/xns/claim", json_data={"agent_id": agent_id, "handle": handle})
    except ApiError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)
    console.print(f"[bold green]Claimed[/bold green] '{result['handle']}' for {result['agent_id']}")


# --------------------------------------------------------------------------
# vault
# --------------------------------------------------------------------------

@vault_app.command("sync")
def vault_sync(
    agent_name: str = typer.Argument(..., help="Agent name (e.g. xibalba)"),
    transcript: str = typer.Option(..., "--transcript", help="Path to transcript.jsonl file"),
    rpc_url: Optional[str] = _RPC_URL_OPTION,
    deployments_file: Optional[str] = _DEPLOYMENTS_FILE_OPTION,
):
    """Sync a session transcript into the trust vault."""
    import pathlib
    transcript_path = pathlib.Path(transcript)
    if not transcript_path.exists():
        console.print(f"[bold red]Error:[/bold red] Transcript not found at {transcript}")
        raise typer.Exit(1)
        
    rpc_url = rpc_url or os.getenv("RPC_URL", "http://localhost:8545")
    deployments_file = deployments_file or os.getenv("DEPLOYMENTS_FILE", "../deployments.local.json")
    
    with console.status(f"[bold blue]Syncing vault for {agent_name}..."):
        try:
            result = vault.sync_vault(agent_name, transcript_path, rpc_url, deployments_file)
        except Exception as e:
            console.print(f"[bold red]Error syncing vault:[/bold red] {e}")
            raise typer.Exit(1)
            
    console.print(f"[bold green]Vault synced successfully[/bold green] for {agent_name}")
    console.print(f"Memory file: [cyan]{result['memory_file']}[/cyan]")
    console.print(f"New state root: [cyan]{result['state_root']}[/cyan]")
    console.print(f"Anchored on-chain: [cyan]{result.get('anchored_on_chain', False)}[/cyan]")


if __name__ == "__main__":
    app()
