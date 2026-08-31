"""
Runtime configuration for the BCC middleware.

Every knob here is read from the environment (with `.env` support for local
dev) rather than hardcoded, because this service's security posture depends
on operators being able to point it at the right OPA server, chain RPC, and
deployed contract addresses per environment (local anvil vs. a real testnet)
without editing code.
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # no-op in prod if no .env file is present; picks it up for local dev


def _bool_env(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    # --- Cross-package shared env vars (see docs/INTERFACE_CONTRACT.md §3) ---
    opa_url: str = field(default_factory=lambda: os.getenv("OPA_URL", "http://localhost:8181"))
    oracle_url: str = field(default_factory=lambda: os.getenv("ORACLE_URL", "http://localhost:8080"))
    rpc_url: str = field(default_factory=lambda: os.getenv("RPC_URL", "http://localhost:8545"))
    chain_id: int = field(default_factory=lambda: int(os.getenv("CHAIN_ID", "31337")))
    deployments_file: str = field(
        default_factory=lambda: os.getenv("DEPLOYMENTS_FILE", str(Path(__file__).resolve().parents[2] / "deployments.local.json"))
    )
    # CORS origins for browser callers (e.g. the dashboard's health checks / Guided System
    # Test wizard) -- comma-separated, or "*". Without this, a browser fetch from a
    # different origin is blocked before it ever reaches an endpoint, even though a plain
    # curl (no CORS enforcement) works fine -- this was a real, previously-silent gap.
    cors_allowed_origins: str = field(default_factory=lambda: os.getenv("CORS_ALLOWED_ORIGINS", "*"))

    # --- OPA policy document coordinates (§7) ---
    # We evaluate the whole `integrity/bcc` package document in one call rather
    # than only the `/allow` leaf so we can also read `violation` (for audit
    # logging) and `requires_baa` (to decide whether the on-chain BAA gate
    # applies) out of the *same* OPA evaluation as the allow/deny decision.
    # This is the identical Rego rule set the interface contract's
    # `/v1/data/integrity/bcc/allow` path evaluates -- see README "Integration
    # reconciliation" section for why integrity-sdk calling the narrower path
    # is still guaranteed to agree with us.
    opa_package_path: str = field(default_factory=lambda: os.getenv("OPA_PACKAGE_PATH", "/v1/data/integrity/bcc"))
    opa_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("OPA_TIMEOUT_SECONDS", "3.0")))

    # --- Commitment freshness / replay window ---
    # A signed commitment older than this is refused even if everything else
    # checks out -- this bounds how long a captured-and-replayed commitment
    # stays valid.
    max_commitment_age_ms: int = field(default_factory=lambda: int(os.getenv("BCC_MAX_AGE_MS", "60000")))

    # --- Shadow (monitor-only) mode ---------------------------------------
    # The enterprise-adoption on-ramp: when true, run_intercept still runs the
    # full authorization gauntlet (signature, replay, freshness, OPA, BAA) and
    # still records every would-be decision to the audit trail, but it NEVER
    # blocks -- a commitment that would be denied under enforcement returns
    # `authorized=True, enforced=False, shadow_would_deny=True` with the reason
    # it *would* have been denied for. This lets an operator deploy the gate in
    # front of real agent traffic with zero production risk, watch the
    # "would-have-blocked" report accumulate, and only then flip to enforcement.
    # In shadow mode the circuit breaker is never tripped (observing, not
    # enforcing -- locking out a well-behaved agent for a violation we didn't
    # act on would be wrong). Default false: enforce, matching prior behavior.
    shadow_mode: bool = field(default_factory=lambda: _bool_env("BCC_SHADOW_MODE", False))

    # --- Circuit breaker ---
    circuit_breaker_violation_threshold: int = field(
        default_factory=lambda: int(os.getenv("BCC_CB_VIOLATION_THRESHOLD", "3"))
    )
    # DEV-TUNED DEFAULT, not a production recommendation: 60s, not the original 900s (15min).
    # Found live 2026-08-18: this shares one circuit breaker per agent DID across BOTH the
    # Claude Code hook (pretool_gate.py) and the Hermes/agy runtime (same identity, see that
    # file's own docstring on why they're deliberately unified) -- so background Hermes
    # activity tripping a real OPA policy denial (an agent-attributable violation, same as a
    # bad signature) locks out an unrelated interactive Claude Code session's Bash/Write/Edit
    # tools too, for however long this is set to. 900s of that during local development is
    # dead time with no attacker on the other end -- a real, observed adoption/DX cost, not a
    # hypothetical one. A production deployment facing real adversarial traffic should set
    # BCC_CB_LOCKOUT_SECONDS explicitly back up (900 or higher) -- this default trades away
    # containment speed against a genuine attacker for local-dev ergonomics, deliberately,
    # and that tradeoff is wrong for anything internet-facing.
    circuit_breaker_lockout_seconds: int = field(
        default_factory=lambda: int(os.getenv("BCC_CB_LOCKOUT_SECONDS", "60"))
    )

    # --- On-chain BAA check ---
    # Key looked up in deployments.<network>.json's `singletons` section (§6.6).
    # It's `SmartBAAFactory`, not `SmartBAA`: the FACTORY implements
    # `isBAAActive(coveredEntity, businessAssociate)`; the per-pair `SmartBAA`
    # escrow instances it creates do not. This is now a real deployed singleton
    # (bootstrapped by contracts/script/Deploy.s.sol), no longer a §6 gap.
    baa_contract_name: str = field(default_factory=lambda: os.getenv("BAA_CONTRACT_NAME", "SmartBAAFactory"))
    baa_check_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("BAA_CHECK_TIMEOUT_SECONDS", "5.0")))

    # --- Verification token (app/verification_token.py) ---
    # HMAC key for `POST /v1/bcc/intercept`'s `verification_token`. Unlike
    # the chain signer keys above, this doesn't custody real value -- it's
    # what makes the token an unforgeable (rather than trivially
    # recomputable-by-anyone) proof that THIS process actually evaluated and
    # approved a specific commitment, checkable later via
    # `POST /v1/bcc/verify_token` (PRODUCTION_GAPS.md §5). If unset, a random
    # secret is generated per-process-start: tokens are short-lived
    # "did this service just approve this" proofs, not long-term credentials,
    # so not surviving a restart is an accepted tradeoff (same in-memory,
    # single-process posture as nonce_store.py / circuit_breaker.py) -- set
    # this explicitly only if tokens need to remain verifiable across restarts.
    bcc_verification_secret: str = field(
        default_factory=lambda: os.getenv("BCC_VERIFICATION_SECRET") or secrets.token_hex(32)
    )

    # --- Merkle anchoring ---
    # NOTE: StateAnchor is now a PER-AGENT primitive, not a global singleton, so
    # there is no single deployments-file key for it — anchoring resolves each
    # agent's own StateAnchor clone via the oracle (see app/anchor.py). This
    # setting is retained only as a legacy/override escape hatch.
    state_anchor_contract_name: str = field(
        default_factory=lambda: os.getenv("STATE_ANCHOR_CONTRACT_NAME", "StateAnchor")
    )
    merkle_batch_size: int = field(default_factory=lambda: int(os.getenv("BCC_MERKLE_BATCH_SIZE", "8")))
    # Dev-only signer used to submit the anchorRoot() transaction. Never a
    # populated real value in committed config -- see .env.example.
    anchor_signer_private_key: str | None = field(
        default_factory=lambda: os.getenv("ANCHOR_SIGNER_PRIVATE_KEY")
    )

    # --- Reputation sync / slashing (app/reputation.py, app/scoring_loop.py) ---
    # Closes the loop nothing else in the monorepo does: pushes each agent's
    # oracle-computed AIS to its ReputationRegistry clone, and raises a
    # Slasher dispute when the oracle's own flagged-telemetry ratio crosses a
    # threshold. See app/reputation.py's module docstring for why this lives
    # in bcc_middleware rather than a new service or integrity-oracle itself.
    #
    # Falls back to anchor_signer_private_key when unset -- on today's
    # single-operator testnet deployment (deployments.baseSepolia.json's
    # protocolAddresses) oracleSigner/disputer/the anchor signer are the same
    # address, so a distinct key would just duplicate the same secret. Set
    # this explicitly once production key-separation happens.
    reputation_signer_private_key: str | None = field(
        default_factory=lambda: os.getenv("REPUTATION_SIGNER_PRIVATE_KEY")
    )
    score_sync_enabled: bool = field(default_factory=lambda: _bool_env("SCORE_SYNC_ENABLED", True))
    score_sync_interval_seconds: int = field(default_factory=lambda: int(os.getenv("SCORE_SYNC_INTERVAL_SECONDS", "300")))
    dispute_enabled: bool = field(default_factory=lambda: _bool_env("DISPUTE_ENABLED", True))
    # Minimum telemetry events in the lookback window before a flagged-ratio
    # is even considered -- prevents one flagged event out of one total from
    # reading as "100% flagged".
    dispute_min_events: int = field(default_factory=lambda: int(os.getenv("DISPUTE_MIN_EVENTS", "5")))
    dispute_flagged_ratio_threshold: float = field(default_factory=lambda: float(os.getenv("DISPUTE_FLAGGED_RATIO_THRESHOLD", "0.5")))
    # Bucket window the flagged-ratio is computed over -- one of the oracle's
    # allowed history buckets (backend::handlers::parse_bucket_interval).
    dispute_lookback_bucket: str = field(default_factory=lambda: os.getenv("DISPUTE_LOOKBACK_BUCKET", "1h"))
    # Basis points of an agent's currently-AVAILABLE (unlocked) stake to lock
    # per raised dispute, not the whole stake -- raising only locks funds
    # (see Slasher.sol's own NatSpec), so this is deliberately conservative;
    # an arbiter decides the actual slash amount at resolveDispute time.
    dispute_stake_bps: int = field(default_factory=lambda: int(os.getenv("DISPUTE_STAKE_BPS", "1000")))
    # Per-agent cooldown between automated disputes, so one ongoing
    # misbehavior pattern doesn't raise a fresh dispute every sync cycle.
    dispute_cooldown_seconds: int = field(default_factory=lambda: int(os.getenv("DISPUTE_COOLDOWN_SECONDS", "86400")))

    def load_deployments(self) -> dict:
        """
        Best-effort read of the shared deployments.local.json (§6). Missing
        file (common in dev before `contracts/` has deployed anything) or a
        missing key is NOT an error here -- callers (baa.py, anchor.py) are
        responsible for treating "no address configured" as "cannot verify"
        and failing closed where that matters (BAA), vs. best-effort where
        it doesn't (anchoring, see README).
        """
        path = Path(self.deployments_file)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def contract_address(self, name: str) -> str | None:
        """
        Resolve a deployed contract address by name from the nested
        deployments-file shape (§6.6): `singletons` first (the common case —
        SmartBAAFactory, XibalbaAgentRegistry, DomainRegistry, …), then
        `cloneTemplates` (the 5 implementation contracts). Per-agent primitive
        instances are deliberately NOT in this file and are never resolved here
        — they come from the on-chain registry / oracle (see app/anchor.py).

        Also accepts the old flat `contracts` map as a fallback so a legacy
        deployments file still works, though nothing writes that shape anymore.
        """
        data = self.load_deployments()
        for section in ("singletons", "cloneTemplates", "contracts"):
            addr = data.get(section, {}).get(name)
            if addr:
                return addr
        return None


settings = Settings()
