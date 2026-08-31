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
from dataclasses import asdict, dataclass
from typing import Optional

import typer
from dotenv import load_dotenv
from eth_account import Account
from eth_utils import keccak
from rich.console import Console
from rich.table import Table
from web3 import Web3

from . import bcc, chain, config, identity, vault, wallet
from .client import ApiError, BccClient, IntegrityClient
from .config import get_auth_token, load_config, set_config_value

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

domain_app = typer.Typer(help="DomainRegistry: the namespace an agent joins via `agent register --domain`")
app.add_typer(domain_app, name="domain")

vault_app = typer.Typer(help="Trust Vault (Persistent Memory) commands")
app.add_typer(vault_app, name="vault")


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

    The private key is written to ~/.integrity-cli/identity/<name>.pem
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

# ComplianceGate.Vertical enum values (contracts/src/health/ComplianceGate.sol),
# same mapping integrity-sdk's registration.py uses.
_VERTICALS = {"none": 0, "healthcare": 1}

_DEFAULT_AGENT_FUND_WEI = Web3.to_wei(0.01, "ether")
_DEFAULT_TESTNET_ITK_ALLOCATION_WEI = Web3.to_wei(10_000, "ether")


@dataclass
class AgentRegistration:
    """Same shape as integrity_sdk.registration.AgentRegistration -- see that
    module's docstring. Kept as a CLI-local dataclass (not imported) per
    identity.py's "no sibling dependency on integrity-sdk" philosophy."""

    did: str
    evm_address: str
    sovereign_agent: str
    state_anchor: str
    reputation_registry: str
    slasher: str
    verifier_registry: str
    compliance_gate: str
    agent_profile: str
    domain_id: str
    oracle_registered: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _registration_progress_path(identity_name: str):
    """Where a not-yet-fully-registered identity's already-deployed SovereignAgent/
    StateAnchor addresses are recorded, mirroring `integrity_sdk.registration`'s
    `registration_progress.json` (PRODUCTION_GAPS.md §28). Separate file from
    `<name>.primitives.json` (written only on full success) so the two can never be
    confused -- this file's existence means "incomplete," the other's means "done."
    """
    return identity.IDENTITY_DIR / f"{identity_name}.registration_progress.json"


def _load_registration_progress(identity_name: str) -> Optional[dict]:
    path = _registration_progress_path(identity_name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _save_registration_progress(identity_name: str, **fields: str) -> None:
    path = _registration_progress_path(identity_name)
    existing = _load_registration_progress(identity_name) or {}
    existing.update(fields)
    path.write_text(json.dumps(existing))


def _clear_registration_progress(identity_name: str) -> None:
    path = _registration_progress_path(identity_name)
    if path.exists():
        path.unlink()


def _post_registration_to_oracle(
    oracle_url: str,
    agent_did: str,
    doc: dict,
    registration: "AgentRegistration",
    identity_name: str,
    evm_account,
    alias: str,
    description: str,
    *,
    idempotent: bool,
) -> None:
    """POSTs to integrity-oracle's `/v1/agent/register`, mutating `registration.
    oracle_registered` on success. Payload shape pinned by `RegisterAgentRequest`
    (handlers.rs) -- see docs/INTERFACE_CONTRACT.md §6.3 and the original inline
    comment this was factored out of for the three payload-shape gotchas already
    found and fixed here on 2026-07-09. `idempotent` only changes the console
    message on success/failure, not the request itself -- the oracle's own
    `POST /v1/agent/register` handler is itself idempotent for an already-registered
    DID (re-verifies on-chain state and accepts it again), so there's nothing
    conditionally different to send.
    """
    oracle_client = IntegrityClient(base_url=oracle_url)
    private_key = identity.load_private_key(identity_name)
    payload = {
        "did": agent_did,
        "did_document": doc,
        "primitives": {
            "sovereign_agent": registration.sovereign_agent,
            "state_anchor": registration.state_anchor,
            "reputation_registry": registration.reputation_registry,
            "slasher": registration.slasher,
            "verifier_registry": registration.verifier_registry,
            "compliance_gate": registration.compliance_gate,
            "agent_profile": registration.agent_profile,
        },
        "ed25519_pubkey_hex": "0x" + private_key.public_key().public_bytes_raw().hex(),
        "eth_address_hex": evm_account.address,
        "alias": alias,
        "description": description,
    }
    try:
        with console.status("[bold blue]Registering with Oracle..."):
            oracle_client.post("/v1/agent/register", json_data=payload)
        registration.oracle_registered = True
        console.print("  [green]done[/green] Oracle accepted the registration" + (" (idempotent re-post)" if idempotent else ""))
    except ApiError as e:
        console.print(
            f"[bold red]Error:[/bold red] on-chain registration succeeded (SovereignAgent "
            f"{registration.sovereign_agent}) but Oracle registration failed: {e}"
        )
        raise typer.Exit(1)


@agent_app.command("register")
def agent_register(
    identity_name: str = typer.Option(
        "default", "--identity", help="Local identity to register (see `integrity identity keygen`)"
    ),
    alias: str = typer.Option(..., "--alias", help="Human-readable alias for the agent"),
    description: str = typer.Option("", "--desc", help="Short description of the agent"),
    domain: str = typer.Option(
        "general.integrity", "--domain", help="Domain name to register under (see DomainRegistry)"
    ),
    vertical: str = typer.Option(
        "none", "--vertical", help="Compliance vertical: 'none' or 'healthcare' (ComplianceGate.Vertical)"
    ),
    rpc_url: Optional[str] = typer.Option(
        None, "--rpc-url", help="EVM RPC endpoint (env RPC_URL, default http://localhost:8545)"
    ),
    deployments_file: Optional[str] = typer.Option(
        None, "--deployments-file", help="Path to deployments.local.json (env DEPLOYMENTS_FILE)"
    ),
    oracle_url: Optional[str] = typer.Option(
        None, "--oracle-url", help="integrity-oracle base URL (env/config ORACLE_URL)"
    ),
    skip_oracle: bool = typer.Option(
        False, "--skip-oracle", help="Run only the on-chain registration sequence; skip the final Oracle POST"
    ),
    auto_register_domain: bool = typer.Option(
        True, "--auto-register-domain/--no-auto-register-domain",
        help="Self-register --domain in DomainRegistry (Open mode) if it doesn't exist yet -- "
             "ONLY when --domain is exactly '<identity>.integrity', the personal-domain convention. "
             "A missing non-personal domain is always a hard error regardless of this flag.",
    ),
):
    """
    Run the real self-sovereign on-chain registration sequence for a local
    identity (fund wallet -> mint testnet ITK -> deploy SovereignAgent ->
    deploy StateAnchor -> grant oracle ANCHOR_ROLE -> registerPrimitives),
    then (unless --skip-oracle) POST the result to integrity-oracle for
    independent on-chain re-verification.

    This is a multi-transaction, multi-second flow signed by the identity's
    own EVM wallet (see wallet.py) -- not a single HTTP POST. Mirrors
    integrity-sdk's registration.py sequence (see docs/INTERFACE_CONTRACT.md
    §6.3), reimplemented CLI-locally per wallet.py/chain.py's module
    docstrings rather than importing integrity_sdk.

    Requires INTEGRITY_WALLET_PASSWORD (gates the EVM keystore, see
    wallet.py) and FUNDER_PRIVATE_KEY (the protocol funder wallet that pays
    to seed the new agent wallet with gas -- see
    docs/INTERFACE_CONTRACT.md §3) in the environment. Neither has a CLI
    flag, deliberately -- they're secrets that shouldn't end up in shell
    history or a process list.
    """
    if vertical not in _VERTICALS:
        console.print(
            f"[bold red]Error:[/bold red] --vertical must be one of {sorted(_VERTICALS)}, got {vertical!r}"
        )
        raise typer.Exit(1)

    try:
        doc = identity.did_document(identity_name)
    except (FileNotFoundError, TypeError) as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)
    agent_did = doc["id"]

    rpc_url = rpc_url or os.getenv("RPC_URL", "http://localhost:8545")
    deployments_file = deployments_file or os.getenv("DEPLOYMENTS_FILE", "../deployments.local.json")
    oracle_url = oracle_url or config.get_config_value("ORACLE_URL")

    funder_key = os.getenv("FUNDER_PRIVATE_KEY")
    if not funder_key:
        console.print(
            "[bold red]Error:[/bold red] FUNDER_PRIVATE_KEY is not set -- required to fund "
            "the agent's new wallet (see docs/INTERFACE_CONTRACT.md §3)."
        )
        raise typer.Exit(1)

    try:
        w3 = chain.get_w3(rpc_url)
        if not w3.is_connected():
            console.print(f"[bold red]Error:[/bold red] RPC {rpc_url} is unreachable -- cannot register an agent.")
            raise typer.Exit(1)
        chain_id = w3.eth.chain_id
    except typer.Exit:
        raise
    except Exception as e:  # noqa: BLE001 -- surfaced to the user, not swallowed
        console.print(f"[bold red]Error:[/bold red] could not connect to RPC {rpc_url}: {e}")
        raise typer.Exit(1)

    try:
        deployments = chain.load_deployments(deployments_file)
        factory_address = deployments["singletons"]["AgentPrimitivesFactory"]
        itk_address = deployments["singletons"]["IntegrityToken"]
        registry_address = deployments["singletons"]["XibalbaAgentRegistry"]
        domain_registry_address = deployments["singletons"]["DomainRegistry"]
        oracle_signer = deployments["protocolAddresses"]["oracleSigner"]
    except (chain.DeploymentsFileMissing, KeyError) as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    try:
        evm_account = wallet.generate_or_load_evm_wallet(identity_name)
    except wallet.WalletPasswordNotSet as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    doc = identity.attach_evm_account(doc, evm_account.address, chain_id)
    funder = Account.from_key(funder_key)

    console.print(f"[bold]Registering[/bold] {agent_did}")
    console.print(f"  EVM wallet: [cyan]{evm_account.address}[/cyan]  (chain {chain_id} @ {rpc_url})")

    # Idempotency check (PRODUCTION_GAPS.md §28): before spending any gas or testnet ITK,
    # ask XibalbaAgentRegistry whether this exact DID is already fully registered. This CLI
    # previously had NO such check at all -- every invocation for an already-registered DID
    # deployed a second, orphaned SovereignAgent/StateAnchor pair, worse than even the SDK's
    # pre-fix behavior (which at least had this one check, just not the deploy-resume one
    # below it).
    existing = chain.resolve_did(w3, registry_address, agent_did)
    if existing is not None:
        console.print(f"  [dim]skip[/dim] {agent_did} is already registered on-chain (SovereignAgent [cyan]{existing.sovereign_agent}[/cyan]) -- returning existing registration, no new on-chain work")
        registration = AgentRegistration(
            did=agent_did,
            evm_address=evm_account.address,
            sovereign_agent=existing.sovereign_agent,
            state_anchor=existing.state_anchor,
            reputation_registry=existing.reputation_registry,
            slasher=existing.slasher,
            verifier_registry=existing.verifier_registry,
            compliance_gate=existing.compliance_gate,
            agent_profile=existing.agent_profile,
            domain_id=existing.domain_id,
            oracle_registered=False,
        )
        doc_path = identity.IDENTITY_DIR / f"{identity_name}.document.json"
        primitives_path = identity.IDENTITY_DIR / f"{identity_name}.primitives.json"
        doc_path.write_text(json.dumps(doc, indent=2) + "\n")
        primitives_path.write_text(json.dumps(registration.to_dict(), indent=2) + "\n")
        _clear_registration_progress(identity_name)
        if not skip_oracle:
            _post_registration_to_oracle(
                oracle_url, agent_did, doc, registration, identity_name, evm_account, alias, description, idempotent=True
            )
        console.print(f"\n[bold green]Already registered:[/bold green] {agent_did}")
        return

    # Precondition checks -- fail fast, before any gas is spent, rather than deep inside
    # the deploy sequence. Regression guard for the 2026-08-30 incident: a real
    # SovereignAgent/StateAnchor pair got orphaned on Base Sepolia because
    # registerPrimitives reverted DomainJoinNotApproved() at the very last step, after
    # the deploy gas was already spent, and nothing checked DomainRegistry beforehand
    # (its ABI wasn't even synced to this package until this fix).
    if not chain.factory_has_registrar_role(w3, registry_address, factory_address):
        console.print(
            f"[bold red]Error:[/bold red] AgentPrimitivesFactory {factory_address} does not hold "
            f"REGISTRAR_ROLE on XibalbaAgentRegistry {registry_address} -- registerPrimitives would "
            f"revert. This is a protocol-level misconfiguration, not something this command can fix."
        )
        raise typer.Exit(1)

    personal_domain_name = f"{identity_name}.integrity"
    domain_id = keccak(text=domain)
    domain_needs_registration = False
    if chain.domain_exists(w3, domain_registry_address, domain_id):
        if not chain.can_join_domain(w3, domain_registry_address, domain_id, evm_account.address):
            console.print(
                f"[bold red]Error:[/bold red] domain {domain!r} exists but is Permissioned and "
                f"{evm_account.address} is not an approved joiner -- ask the domain's owner to call "
                f"DomainRegistry.approveJoiner, or choose a different --domain."
            )
            raise typer.Exit(1)
    else:
        if domain == personal_domain_name and auto_register_domain:
            domain_needs_registration = True  # registered below, once the wallet is funded
        else:
            console.print(
                f"[bold red]Error:[/bold red] domain {domain!r} does not exist in DomainRegistry "
                f"{domain_registry_address}. "
                + (f"Pass --auto-register-domain to self-register it (it matches {identity_name}'s own "
                   f"personal-domain convention)." if domain == personal_domain_name else
                   f"This is not {identity_name}'s own personal domain ({personal_domain_name!r}), so it "
                   f"will never be auto-registered -- run `integrity domain register {domain!r}` "
                   f"explicitly if you intend to claim this name, or use the correct existing shared domain.")
            )
            raise typer.Exit(1)

    try:
        _MIN_OPERATING_BALANCE_WEI = Web3.to_wei(0.001, "ether")
        current_balance = w3.eth.get_balance(evm_account.address)
        if current_balance < _MIN_OPERATING_BALANCE_WEI:
            funder_balance = w3.eth.get_balance(funder.address)
            # Leave 0.001 ETH for funder gas fee
            fund_amount = min(_DEFAULT_AGENT_FUND_WEI, max(0, funder_balance - Web3.to_wei(0.001, "ether")))
            if fund_amount < _MIN_OPERATING_BALANCE_WEI:
                console.print(f"[bold red]Error:[/bold red] Funder wallet has insufficient balance: {Web3.from_wei(funder_balance, 'ether'):.4f} ETH")
                raise typer.Exit(1)
            with console.status("[bold blue]Funding agent wallet..."):
                chain.fund_agent_wallet(w3, funder, evm_account.address, fund_amount, chain_id)
            console.print(f"  [green]done[/green] funded agent wallet ({Web3.from_wei(fund_amount, 'ether'):.4f} ETH)")
            import time
            time.sleep(10)  # Wait for balance to sync across load-balanced nodes
        else:
            console.print(
                f"  [dim]skip[/dim] agent wallet already funded "
                f"({Web3.from_wei(current_balance, 'ether'):.4f} ETH)"
            )

        # Self-register the personal domain now that the agent's own wallet is funded and
        # can pay for (and own) the DomainRegistry.registerDomain transaction itself --
        # doing this before funding would either fail (empty wallet) or require the
        # funder to pay and thus become the domain's owner, which is wrong for a domain
        # meant to be agent-controlled.
        if domain_needs_registration:
            with console.status(f"[bold blue]Registering domain {domain!r}..."):
                chain.register_domain(w3, evm_account, domain_registry_address, domain, chain_id, open_mode=True)
            console.print(f"  [green]done[/green] self-registered domain {domain!r} (Open), owned by {evm_account.address}")

        next_nonce = w3.eth.get_transaction_count(evm_account.address)

        import time

        # Resume-from-partial-failure (PRODUCTION_GAPS.md §28): before deploying
        # anything, check whether a prior invocation already got a SovereignAgent/
        # StateAnchor on-chain for this identity and simply never finished (steps
        # after this failing, e.g. a missing role grant -- the exact incidents that
        # motivated this fix). Verify each recorded address genuinely has deployed
        # bytecode before trusting it -- never trust a locally-recorded address
        # blindly, the same lesson the phantom-factory incident taught the hard way.
        progress = _load_registration_progress(identity_name)
        sovereign_agent = progress.get("sovereign_agent") if progress else None
        state_anchor = progress.get("state_anchor") if progress else None
        if sovereign_agent and w3.eth.get_code(Web3.to_checksum_address(sovereign_agent)) in (b"", "0x"):
            console.print(f"  [yellow]warn[/yellow] recorded SovereignAgent {sovereign_agent} has no bytecode -- discarding stale progress")
            sovereign_agent = None
            state_anchor = None

        if sovereign_agent:
            console.print(f"  [dim]skip[/dim] reusing already-deployed SovereignAgent [cyan]{sovereign_agent}[/cyan] (no new deploy)")
        else:
            with console.status("[bold blue]Deploying SovereignAgent..."):
                sovereign_agent = chain.deploy_sovereign_agent(w3, evm_account, agent_did, oracle_signer, chain_id, nonce=next_nonce)
            console.print(f"  [green]done[/green] SovereignAgent deployed at [cyan]{sovereign_agent}[/cyan]")
            next_nonce += 1
            time.sleep(5)  # Wait for contract bytecode to propagate
            _save_registration_progress(identity_name, sovereign_agent=sovereign_agent)

        if state_anchor and w3.eth.get_code(Web3.to_checksum_address(state_anchor)) in (b"", "0x"):
            console.print(f"  [yellow]warn[/yellow] recorded StateAnchor {state_anchor} has no bytecode -- discarding stale progress")
            state_anchor = None

        if state_anchor:
            console.print(f"  [dim]skip[/dim] reusing already-deployed StateAnchor [cyan]{state_anchor}[/cyan] (no new deploy)")
        else:
            with console.status("[bold blue]Deploying StateAnchor..."):
                state_anchor = chain.deploy_state_anchor(w3, evm_account, sovereign_agent, chain_id, nonce=next_nonce)
            console.print(f"  [green]done[/green] StateAnchor deployed at [cyan]{state_anchor}[/cyan]")
            next_nonce += 1
            time.sleep(5)  # Wait for contract bytecode to propagate
            _save_registration_progress(identity_name, sovereign_agent=sovereign_agent, state_anchor=state_anchor)

        # Minted to the SovereignAgent CONTRACT, not the wallet, and only after that
        # contract exists (PRODUCTION_GAPS.md Sec3) -- IntegrityMarket/A2ACapitalPool pull
        # ITK from msg.sender, which is always the SovereignAgent address when a call is
        # routed through its own execute(), never the raw EOA wallet. Minting to the
        # wallet (the previous order here) left testnet ITK stranded on an address that
        # can never spend it through that call path. Mirrors integrity-sdk's
        # registration.py, which was already fixed the same way.
        #
        # Checked first on a retry, unlike grant_anchor_role below (idempotent by
        # construction) -- minting again would genuinely double-issue ITK.
        if chain.itk_balance(w3, itk_address, sovereign_agent) >= _DEFAULT_TESTNET_ITK_ALLOCATION_WEI:
            console.print("  [dim]skip[/dim] SovereignAgent already holds enough testnet ITK -- skipping mint")
        else:
            with console.status("[bold blue]Minting testnet ITK..."):
                chain.mint_testnet_itk(
                    w3, funder, itk_address, sovereign_agent, _DEFAULT_TESTNET_ITK_ALLOCATION_WEI, chain_id
                )
            console.print("  [green]done[/green] minted testnet ITK")
            time.sleep(2)

        # OZ's grantRole no-ops if already held, but checked first anyway to skip the
        # transaction entirely on a retry rather than pay gas for a no-op.
        if chain.has_anchor_role(w3, state_anchor, oracle_signer):
            console.print("  [dim]skip[/dim] StateAnchor already granted ANCHOR_ROLE to oracle signer")
        else:
            with console.status("[bold blue]Granting oracle ANCHOR_ROLE..."):
                chain.grant_anchor_role(w3, evm_account, sovereign_agent, state_anchor, oracle_signer, chain_id, nonce=next_nonce)
            console.print("  [green]done[/green] granted ANCHOR_ROLE to oracle signer")
            next_nonce += 1
            time.sleep(3)

        # Re-anchoring against a StateAnchor that already has a non-zero root is
        # unverified/likely-unsafe territory (see integrity_sdk.chain.anchor_genesis_root's
        # docstring) -- checked explicitly rather than assumed safe to retry.
        if chain.state_anchor_latest_root(w3, state_anchor) != b"\x00" * 32:
            console.print("  [dim]skip[/dim] StateAnchor already has a non-zero root -- skipping re-anchor")
        else:
            with console.status("[bold blue]Anchoring genesis memory root..."):
                chain.anchor_root(w3, evm_account, sovereign_agent, state_anchor, chain_id, nonce=next_nonce)
            console.print("  [green]done[/green] anchored genesis memory root")
            next_nonce += 1
            time.sleep(3)

        # domain_id was already computed above, in the precondition-check block that ran
        # before any gas was spent.
        with console.status("[bold blue]Registering primitives..."):
            result = chain.register_primitives(
                w3,
                evm_account,
                factory_address,
                sovereign_agent,
                state_anchor,
                agent_did,
                domain_id,
                _VERTICALS[vertical],
                "",
                chain_id,
                nonce=next_nonce,
            )
        console.print("  [green]done[/green] registered 7 primitives")
    except typer.Exit:
        raise
    except Exception as e:  # noqa: BLE001 -- a partially-completed registration must be visible, not swallowed
        console.print(f"[bold red]Error during on-chain registration:[/bold red] {e}")
        raise typer.Exit(1)

    registration = AgentRegistration(
        did=agent_did,
        evm_address=evm_account.address,
        sovereign_agent=result.sovereign_agent,
        state_anchor=result.state_anchor,
        reputation_registry=result.reputation_registry,
        slasher=result.slasher,
        verifier_registry=result.verifier_registry,
        compliance_gate=result.compliance_gate,
        agent_profile=result.agent_profile,
        domain_id=result.domain_id,
        oracle_registered=False,
    )

    # Persist next to the identity's own files (<name>.pem, <name>.wallet.json),
    # same convention -- mirrors integrity-sdk's document.json/primitives.json.
    doc_path = identity.IDENTITY_DIR / f"{identity_name}.document.json"
    primitives_path = identity.IDENTITY_DIR / f"{identity_name}.primitives.json"
    doc_path.write_text(json.dumps(doc, indent=2) + "\n")
    primitives_path.write_text(json.dumps(registration.to_dict(), indent=2) + "\n")
    # registerPrimitives just succeeded -- resolve_did's idempotency check (top of this
    # command) now covers this DID going forward, so the progress file has done its job.
    _clear_registration_progress(identity_name)

    if not skip_oracle:
        _post_registration_to_oracle(
            oracle_url, agent_did, doc, registration, identity_name, evm_account, alias, description, idempotent=False
        )

    console.print(f"[bold green]Registered:[/bold green] {agent_did}")
    console.print_json(data=registration.to_dict())


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
    Run this before `agent register --domain <name>` for any domain you haven't already
    verified -- see `agent register`'s own precondition checks, which run this same logic
    automatically but only report a problem after computing everything else."""
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
    first-come-first-served, same trust model as ENS second-level names. `agent register`
    does this automatically (Open mode) for an identity's own '<identity>.integrity'
    domain when it's missing (see its --auto-register-domain flag, default on) -- use this
    command directly for any other domain name, or to register --permissioned.
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
    persisted locally by `integrity agent register`, so it's resolved the
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
