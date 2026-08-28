"""
Wire schemas for bcc_middleware.

`BCCCommitment` mirrors docs/INTERFACE_CONTRACT.md §4.2 EXACTLY -- field
names are load-bearing across integrity-sdk, integrity-cli, and this
service, so nothing here gets renamed for local taste even where a
different name would read better in isolation.
"""

from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, Field, field_validator, model_validator

_HEX32 = re.compile(r"^0x[0-9a-fA-F]{64}$")  # 32 bytes hex, e.g. a sha256 digest
_HEX_SIG = re.compile(r"^0x[0-9a-fA-F]+$")
_HEX_ADDR = re.compile(r"^0x[0-9a-fA-F]{40}$")  # 20 bytes hex, an EVM address


class BCCCommitment(BaseModel):
    """
    The Behavioral Commitment Chain intent-lock object (§4.2). This is the
    literal, un-wrapped JSON body POSTed to `/v1/bcc/intercept` -- there is
    no enclosing `{"commitment": ...}` wrapper, because the interface
    contract's example is a flat object and sibling packages (integrity-sdk,
    integrity-cli) are being built against that flat shape.
    """

    agent_id: str = Field(..., description="did:integrity:<hex-pubkey-fingerprint>")
    intent_type: str = Field(..., min_length=1, max_length=256)
    intended_state_hash: str = Field(..., description="0x-prefixed sha256 hex digest of the canonical intent payload")
    nonce: int = Field(..., ge=0, description="monotonic per-agent integer")
    timestamp: int = Field(..., gt=0, description="unix ms")
    signature: str = Field(..., description="0x-prefixed hex Ed25519 signature over the canonical JSON of the other fields")

    # --- BAA-vertical extension (NOT yet in the frozen §4.2 shape) ---------
    # `contracts/`'s real `SmartBAAFactory.isBAAActive` takes TWO addresses --
    # `coveredEntity` (the hospital/healthcare org) and `businessAssociate`
    # (the agent) -- not one. §4.2 only ever gave us an agent identity, with
    # no way to say *which* covered entity a healthcare-vertical commitment
    # (e.g. `EMR_WRITE`, `CLINICAL_DATA_ACCESS` -- see policies/bcc.rego's
    # `clinical_intent_types`) is claiming access against. This field closes
    # that gap: it's optional so non-healthcare intent types (`payment`,
    # `contract_call`, ...) can omit it entirely, but any commitment whose
    # `intent_type` causes OPA to set `requires_baa := true` MUST carry it,
    # or app/baa.py's `check_baa_status` fails closed with CANNOT_VERIFY (see
    # that module for why an unset covered entity is never treated as
    # "compliant"). Deliberately an address, not a DID -- unlike agents,
    # covered entities are registered directly by EVM address in
    # `contracts/src/health/CoveredEntityRegistry.sol`, there is no DID layer
    # for them.
    covered_entity_address: str | None = Field(
        default=None,
        description="0x-prefixed EVM address of the covered entity (hospital) this data_access/healthcare intent is against; required whenever OPA flags requires_baa",
    )

    # --- Self-certifying public key (reconciles the DID-fingerprint scheme) ---
    # integrity-sdk's DID fingerprint is `sha256(pubkey)`, NOT the raw Ed25519
    # public key (this module originally assumed the latter — see canonical.py's
    # INTEGRATION FLAG). A sha256 digest can't be turned back into the key it
    # hashed, so a verifier holding only `agent_id` cannot recover the pubkey to
    # check the signature. The agent therefore carries its own public key here,
    # in the same multibase form as the DID document's `publicKeyMultibase`
    # (§4.1). It's safe to trust a *carried* key because verification binds it:
    # `sha256(decoded_pubkey)` must equal the DID's fingerprint, so a swapped key
    # fails before the signature is ever checked (see canonical.py).
    agent_public_key: str = Field(
        ...,
        description="Agent's Ed25519 public key, multibase (z-base58btc, multicodec ed25519-pub) — must hash to agent_id's fingerprint",
    )

    # --- AOS-Observability Gating attributes ---
    trace_id: str | None = Field(
        default=None,
        description="W3C trace ID associated with this action's execution context",
    )
    span_id: str | None = Field(
        default=None,
        description="W3C parent span ID representing the planning/reasoning phase",
    )
    intent_rationale: str | None = Field(
        default=None,
        description="Public-safe intent rationale for this action; signed and preferred by policy",
    )
    agent_thought: str | None = Field(
        default=None,
        description="Legacy alias for intent_rationale; retained for backward compatibility",
    )
    token_count: int | None = Field(
        default=None,
        ge=0,
        description="Total LLM tokens consumed generating this action (prompt + completion); used for tier-based daily budget enforcement",
    )

    # --- Canonical intent encoding (docs/plans/2026-08-18-phase1-canonical-
    # intent-encoding-proposal.md) -------------------------------------------
    # Before these two fields, a commitment signed once was valid, byte-for-
    # byte, against any chain or any deployment of the protocol sharing the
    # signing agent's DID -- neither `nonce` (monotonic per-agent, but not
    # deployment-scoped) nor anything else in §4.2 bound a commitment to a
    # specific chain/deployment. Both REQUIRED, both signed (see
    # canonical.py's canonical_commitment_bytes) so neither can be swapped
    # post-signature. `app/main.py`'s deployment-binding check enforces
    # `chain_id` unconditionally (Settings.chain_id always has a value) but
    # enforces `verifying_contract` only when this deployment has a
    # configured XibalbaAgentRegistry address -- see that check's own
    # docstring for why that asymmetry is a disclosed limitation, not a
    # silent downgrade.
    chain_id: int = Field(..., gt=0, description="EVM chain ID this commitment is scoped to")
    verifying_contract: str = Field(
        ...,
        description="0x-prefixed XibalbaAgentRegistry address for the target chain -- the root every downstream primitive in this architecture resolves through",
    )
    invocation_id: str | None = Field(
        default=None,
        description="Canonical UUID identifying one attempted action; signed when present",
    )

    @field_validator("invocation_id")
    @classmethod
    def _invocation_id_shape(cls, v: str | None) -> str | None:
        if v is None:
            return None
        try:
            parsed = uuid.UUID(v)
            canonical = str(parsed)
        except (ValueError, AttributeError) as exc:
            raise ValueError("invocation_id must be a canonical UUID") from exc
        if v != canonical or parsed.int == 0:
            raise ValueError("invocation_id must be a non-nil lowercase canonical UUID")
        return v

    @field_validator("verifying_contract")
    @classmethod
    def _verifying_contract_shape(cls, v: str) -> str:
        if not _HEX_ADDR.match(v):
            raise ValueError("verifying_contract must be 0x-prefixed 20-byte hex (an EVM address)")
        return v

    @field_validator("trace_id")
    @classmethod
    def _trace_id_shape(cls, v: str | None) -> str | None:
        if v is not None and not re.match(r"^[0-9a-fA-F]{32}$", v):
            raise ValueError("trace_id must be 32 hex characters")
        return v

    @field_validator("span_id")
    @classmethod
    def _span_id_shape(cls, v: str | None) -> str | None:
        if v is not None and not re.match(r"^[0-9a-fA-F]{16}$", v):
            raise ValueError("span_id must be 16 hex characters")
        return v

    @model_validator(mode="after")
    def _normalize_rationale(self):
        if self.intent_rationale and self.agent_thought and self.intent_rationale != self.agent_thought:
            raise ValueError("intent_rationale and agent_thought must match when both are provided")
        if not self.intent_rationale and self.agent_thought:
            self.intent_rationale = self.agent_thought
        if not self.agent_thought and self.intent_rationale:
            self.agent_thought = self.intent_rationale
        return self

    @field_validator("covered_entity_address")
    @classmethod
    def _covered_entity_address_shape(cls, v: str | None) -> str | None:
        if v is not None and not _HEX_ADDR.match(v):
            raise ValueError("covered_entity_address must be 0x-prefixed 20-byte hex (an EVM address)")
        return v

    @field_validator("agent_id")
    @classmethod
    def _agent_id_shape(cls, v: str) -> str:
        if not v.startswith("did:integrity:"):
            raise ValueError("agent_id must be a did:integrity:<fingerprint> DID")
        fingerprint = v.removeprefix("did:integrity:")
        if not fingerprint:
            raise ValueError("agent_id DID is missing its fingerprint")
        return v

    @field_validator("intended_state_hash")
    @classmethod
    def _hash_shape(cls, v: str) -> str:
        if not _HEX32.match(v):
            raise ValueError("intended_state_hash must be 0x-prefixed 32-byte hex (sha256 digest)")
        return v

    @field_validator("signature")
    @classmethod
    def _sig_shape(cls, v: str) -> str:
        if not _HEX_SIG.match(v) or len(v) != 2 + 128:  # 0x + 64 bytes hex for Ed25519
            raise ValueError("signature must be 0x-prefixed 64-byte hex (Ed25519)")
        return v


class BCCInterceptResponse(BaseModel):
    authorized: bool
    invocation_id: str | None = None
    reason: str | None = None
    # --- Shadow (monitor-only) mode signalling (see app/config.py) ---------
    # `enforced` is False whenever this response was produced in shadow mode --
    # i.e. `authorized` reflects "what the caller should do" (always True in
    # shadow) but the decision was NOT gated. `shadow_would_deny` is True when
    # enforcement WOULD have denied this commitment; `reason` then carries the
    # would-be denial code/detail even though `authorized` is True. In normal
    # enforce mode both fields keep their defaults (enforced=True, would_deny
    # meaningless) and callers that predate shadow mode are unaffected.
    enforced: bool = True
    shadow_would_deny: bool = False
    # Only present when authorized=True: an HMAC-keyed, persisted token
    # (see app/verification_token.py) proving THIS middleware evaluated and
    # approved this exact commitment -- checkable via
    # POST /v1/bcc/verify_token, unlike the plain-sha256-of-public-fields
    # value this used to be (PRODUCTION_GAPS.md §5), which anyone could
    # recompute themselves and nothing ever checked. Also carries which
    # pending merkle batch slot it landed in (useful for callers to later
    # look up the anchoring transaction once the batch flushes).
    verification_token: str | None = None
    batch_index: int | None = None
    # Remaining daily token budget for this agent after this request (None if
    # token_count was not provided or agent is unlimited-tier).
    token_budget_remaining: int | None = None


class VerifyTokenRequest(BaseModel):
    """Body for POST /v1/bcc/verify_token -- the caller supplies the token
    it was given plus the commitment fields it claims that token covers;
    the response says whether this service actually issued that exact
    combination (see app/verification_token.py)."""

    token: str
    agent_id: str
    nonce: int
    intended_state_hash: str


class VerifyTokenResponse(BaseModel):
    valid: bool


class ClinicalAllowlistRequest(BaseModel):
    """Full replacement list for the runtime clinical-agent allowlist OPA data
    document (bcc.rego's `data.clinical_allowlist.agents` extension point)."""

    agents: list[str] = Field(default_factory=list)


class ClinicalAllowlistResponse(BaseModel):
    agents: list[str]


class HealthResponse(BaseModel):
    status: str
    opa_reachable: bool
    chain_reachable: bool
    pending_batch_size: int
    # "enforce" (denies actually block) or "shadow" (monitor-only; nothing is
    # blocked, would-be denials are recorded). Lets operators/the dashboard
    # see at a glance which posture the gate is deployed in.
    mode: str = "enforce"
