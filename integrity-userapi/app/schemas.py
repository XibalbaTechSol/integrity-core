"""Wire schemas (pydantic request/response models) for integrity-userapi."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


# --- Auth ---------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=256)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    created_at: datetime


# --- API keys -------------------------------------------------------------


class ApiKeyCreateResponse(BaseModel):
    id: UUID
    raw_key: str  # returned exactly once, never persisted or shown again
    ais_trust_ceiling: int
    created_at: datetime


class ApiKeyResponse(BaseModel):
    id: UUID
    ais_trust_ceiling: int
    revoked_at: datetime | None
    created_at: datetime


# --- Agent ownership --------------------------------------------------------


class AddAgentRequest(BaseModel):
    agent_did: str = Field(..., min_length=1)


class OwnedAgentResponse(BaseModel):
    agent_did: str
    added_at: datetime
    # Live data fanned out from integrity-oracle's GET /v1/agent/{id}. `None`
    # (with `error` set) if the oracle was unreachable or the lookup failed
    # -- this endpoint never crashes the whole response over one bad lookup,
    # and never fabricates agent data when the oracle can't be reached.
    live_data: dict[str, Any] | None = None
    error: str | None = None


# --- Demo runs -------------------------------------------------------------


class DemoRunResponse(BaseModel):
    id: UUID
    status: str
    started_at: datetime
    finished_at: datetime | None
    result_summary: dict[str, Any] | None


_DEMO_RUN_UPDATE_STATUSES = {"running", "completed", "failed"}


class DemoRunUpdateRequest(BaseModel):
    """The completion-callback shape a demo-run executor (e.g.
    `integrity-dashboard/demo`) reports back through -- see PATCH /demo/runs/{id}.
    `status` is deliberately restricted to non-initial states: a run is
    always created as 'pending' by POST /demo/run itself, never set back to
    it here."""

    status: str = Field(..., description="one of: running, completed, failed")
    result_summary: dict[str, Any] | None = None

    @field_validator("status")
    @classmethod
    def _status_is_a_valid_transition(cls, value: str) -> str:
        if value not in _DEMO_RUN_UPDATE_STATUSES:
            raise ValueError(f"status must be one of {sorted(_DEMO_RUN_UPDATE_STATUSES)}, got {value!r}")
        return value


# --- Custodial app wallet -----------------------------------------------


class WalletResponse(BaseModel):
    """The user's custodial app wallet — address + current $ITK balance (human units)."""

    app_wallet_address: str
    balance: float


class TransferRequest(BaseModel):
    recipient_address: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0)


class TransferResponse(BaseModel):
    status: str = "ok"
    new_balance: float
