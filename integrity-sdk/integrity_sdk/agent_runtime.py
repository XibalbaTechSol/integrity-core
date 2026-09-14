"""Harness-neutral agent runtime for Integrity identity and telemetry.

Harness adapters should only translate their lifecycle callbacks into this
class. Identity loading, DID continuity, device policy, and telemetry
attribution stay in the SDK so every harness follows the same rules.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional

from .client import IntegrityClient
from .did import IdentityInconsistentError, Keypair, load_or_create_did

_AGENT_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class AgentIdentityError(ValueError):
    """Raised when a harness supplies an invalid or conflicting identity."""


class AgentNotRegisteredError(RuntimeError):
    """Raised when strict startup requires an Oracle-registered agent."""


class IntegrityAgent:
    """Stable identity and lifecycle telemetry façade for any harness."""

    def __init__(
        self,
        *,
        agent_slug: str,
        did: str,
        keypair: Keypair,
        did_document: dict[str, Any],
        client: IntegrityClient,
        harness: str,
        profile: str | None,
        device_id: str | None,
        require_device_binding: bool,
    ) -> None:
        self.agent_slug = agent_slug
        self.did = did
        self.keypair = keypair
        self.did_document = did_document
        self.client = client
        self.harness = harness
        self.profile = profile
        self.device_id = device_id
        self.require_device_binding = require_device_binding
        self._session_id: str | None = None
        self._closed = False

    @classmethod
    def open(
        cls,
        agent_slug: str,
        *,
        harness: str,
        profile: str | None = None,
        device_id: str | None = None,
        require_device_binding: bool = False,
        expected_did: str | None = None,
        require_registered: bool = False,
        oracle_url: str | None = None,
        client_kwargs: Optional[Mapping[str, Any]] = None,
    ) -> "IntegrityAgent":
        """Open one stable agent identity for a harness.

        A missing identity creates exactly one new keypair under the SDK DID
        store. Existing identity state is validated by ``load_or_create_did``
        and is never silently replaced. Registration is checked only when
        ``require_registered`` is true, which keeps first-time provisioning
        offline and makes production gates explicit.
        """
        if not isinstance(agent_slug, str) or not _AGENT_SLUG_RE.fullmatch(agent_slug):
            raise AgentIdentityError("agent_slug must be 1-128 ASCII letters, digits, '.', '_' or '-'")
        if not isinstance(harness, str) or not harness.strip():
            raise AgentIdentityError("harness is required")
        if require_device_binding and not device_id:
            raise AgentIdentityError("device_id is required when device binding is enabled")

        did, keypair, did_document = load_or_create_did(agent_slug)
        if expected_did and did != expected_did:
            raise AgentIdentityError(
                f"agent {agent_slug!r} resolved to {did}, expected {expected_did}; refusing attribution"
            )

        options = dict(client_kwargs or {})
        options.setdefault("background_flush", False)
        options.setdefault("keypair", keypair)
        client = IntegrityClient(agent_id=did, oracle_url=oracle_url, **options)
        runtime = cls(
            agent_slug=agent_slug,
            did=did,
            keypair=keypair,
            did_document=did_document,
            client=client,
            harness=harness,
            profile=profile,
            device_id=device_id,
            require_device_binding=require_device_binding,
        )
        if require_registered and runtime.registration_status() is not True:
            client.close()
            raise AgentNotRegisteredError(
                f"agent {agent_slug!r} ({did}) is not confirmed registered with the Integrity Oracle"
            )
        return runtime

    def registration_status(self) -> bool | None:
        """Return Oracle registration state, or ``None`` when inconclusive."""
        return self.client.registration_status()

    def emit(self, event: str, metadata: Mapping[str, Any] | None = None, **fields: Any) -> None:
        """Queue one standard lifecycle event with immutable attribution fields."""
        if self._closed:
            raise RuntimeError("cannot emit telemetry after IntegrityAgent.close()")
        if not isinstance(event, str) or not event.strip():
            raise ValueError("event is required")
        entry = dict(metadata or {})
        entry.update(fields)
        entry.update({
            "event": event,
            "agent_did": self.did,
            "agent_slug": self.agent_slug,
            "harness": self.harness,
            "profile": self.profile,
            "device_id": self.device_id,
        })
        self.client.log_telemetry(entry)

    def start_session(self, session_id: str, **fields: Any) -> None:
        self._session_id = session_id
        self.emit("session_started", session_id=session_id, **fields)

    def model_call(self, *, session_id: str | None = None, **fields: Any) -> None:
        self.emit("model_call", session_id=session_id or self._session_id, **fields)

    def tool_call(self, *, session_id: str | None = None, **fields: Any) -> None:
        self.emit("tool_call", session_id=session_id or self._session_id, **fields)

    def tool_result(self, *, session_id: str | None = None, **fields: Any) -> None:
        self.emit("tool_result", session_id=session_id or self._session_id, **fields)

    def complete(self, *, session_id: str | None = None, **fields: Any) -> None:
        self.emit("session_completed", session_id=session_id or self._session_id, **fields)

    def flush(self) -> bool:
        return self.client.flush_telemetry()

    def close(self, *, flush: bool = True) -> bool:
        if self._closed:
            return True
        self._closed = True
        if flush:
            result = self.client.close()
        else:
            self.client.shutdown()
            result = True
        return result

    def __enter__(self) -> "IntegrityAgent":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()


__all__ = ["AgentIdentityError", "AgentNotRegisteredError", "IntegrityAgent", "IdentityInconsistentError"]
