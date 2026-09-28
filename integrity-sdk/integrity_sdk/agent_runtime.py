"""Harness-neutral agent runtime for Integrity identity and telemetry.

Harness adapters should only translate their lifecycle callbacks into this
class. Identity loading, DID continuity, device policy, and telemetry
attribution stay in the SDK so every harness follows the same rules.
"""

from __future__ import annotations

import re
import time
import json
from pathlib import Path
from typing import Any, Mapping, Optional

from .client import IntegrityClient
from .did import (
    AmbiguousProfileRootError,
    DidFileError,
    IdentityInconsistentError,
    KeyStoreInsideProfileRootError,
    Keypair,
    _relocate_legacy_identity,
    agent_dir,
    key_store_for_profile,
    legacy_in_root_store,
    load_or_create_did,
    read_did_file,
    resolve_profile_root,
    write_did_file,
)
from .identity_registry import record_identity

_AGENT_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class AgentIdentityError(ValueError):
    """Raised when a harness supplies an invalid or conflicting identity."""


class AgentNotRegisteredError(RuntimeError):
    """Raised when strict startup requires an Oracle-registered agent."""


def _legacy_binding_path(profile_root: Path) -> Path:
    """Pre-DID-file binding, written by earlier builds next to the in-root key store."""
    return profile_root / ".integrity" / "identity.json"


def _read_legacy_binding(profile_root: Path) -> dict[str, Any] | None:
    """Read the legacy binding so an existing profile keeps its identity while migrating.

    Only the fields that identify the agent are trusted (`agent_id`, `did`,
    `profile_root`); the recorded `identity_store` path is ignored because the
    key store is now derived from the root.
    """
    path = _legacy_binding_path(profile_root)
    if not path.exists():
        return None
    try:
        binding = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentIdentityError(f"invalid profile identity binding at {path}") from exc
    if not isinstance(binding, dict) or not isinstance(binding.get("agent_id"), str) or not isinstance(binding.get("did"), str):
        raise AgentIdentityError(f"invalid profile identity binding at {path}")
    if binding.get("profile_root") != str(profile_root):
        raise AgentIdentityError(f"profile identity binding root mismatch at {path}")
    return binding


def _retire_legacy_layout(profile_root: Path) -> None:
    """Remove the legacy binding and any now-empty legacy directories from the root.

    Called only after the public DID file has been written and the key has
    been relocated, so nothing here holds information that exists nowhere else.
    Non-empty directories are left alone.
    """
    _legacy_binding_path(profile_root).unlink(missing_ok=True)
    for directory in (legacy_in_root_store(profile_root), profile_root / ".integrity"):
        try:
            directory.rmdir()
        except OSError:
            break


class IntegrityAgent:
    """Stable identity and lifecycle telemetry façade for any harness."""

    def __init__(
        self,
        *,
        agent_slug: str | None,
        did: str,
        keypair: Keypair,
        did_document: dict[str, Any],
        client: IntegrityClient,
        harness: str,
        profile: str | None,
        profile_root: Path | None,
        did_home_root: Path | None,
        principal: str | None,
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
        self.profile_root = profile_root
        self.did_home_root = did_home_root
        self.principal = principal
        self.device_id = device_id
        self.require_device_binding = require_device_binding
        self._session_id: str | None = None
        self._closed = False

    @classmethod
    def open(
        cls,
        agent_slug: str | None = None,
        *,
        harness: str,
        profile: str | None = None,
        profile_root: str | Path | None = None,
        principal: str | None = None,
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
        if not isinstance(harness, str) or not harness.strip():
            raise AgentIdentityError("harness is required")
        if require_device_binding and not device_id:
            raise AgentIdentityError("device_id is required when device binding is enabled")

        # The harness root holds only the public DID file; the private key lives
        # in a store outside it (see did.py's layout notes). The root comes from
        # the explicit argument, $INTEGRITY_PROFILE_ROOT, or the harness
        # variables -- which must agree, never resolved by precedence.
        did_home_root: Path | None = None
        legacy_home: Path | None = None
        profile_binding: dict[str, Any] | None = None
        binding_is_legacy = False
        try:
            resolved_profile_root = resolve_profile_root(profile_root)
        except AmbiguousProfileRootError as exc:
            raise AgentIdentityError(str(exc)) from exc
        if resolved_profile_root is not None:
            if not resolved_profile_root.is_dir():
                raise AgentIdentityError("profile_root must resolve to an existing directory")
            try:
                did_home_root = key_store_for_profile(resolved_profile_root)
            except KeyStoreInsideProfileRootError as exc:
                raise AgentIdentityError(str(exc)) from exc
            legacy_home = legacy_in_root_store(resolved_profile_root)

            try:
                profile_binding = read_did_file(resolved_profile_root)
            except DidFileError as exc:
                raise AgentIdentityError(str(exc)) from exc
            if profile_binding is None:
                profile_binding = _read_legacy_binding(resolved_profile_root)
                binding_is_legacy = profile_binding is not None
            if profile_binding is not None:
                bound_slug = profile_binding["agent_id"]
                if agent_slug is None:
                    agent_slug = bound_slug
                elif agent_slug != bound_slug:
                    raise AgentIdentityError(
                        f"profile root is bound to agent {bound_slug!r}, not {agent_slug!r}"
                    )
                bound_did = profile_binding["did"]
                if expected_did and expected_did != bound_did:
                    raise AgentIdentityError("expected DID conflicts with the profile identity binding")
                expected_did = bound_did
            elif agent_slug is None:
                raise AgentIdentityError("profile_root has no identity binding; agent_slug is required for provisioning")
            elif expected_did or require_registered:
                raise AgentIdentityError(
                    "profile_root has no identity binding; provision and bind its existing identity before runtime startup"
                )

        if not isinstance(agent_slug, str) or not _AGENT_SLUG_RE.fullmatch(agent_slug):
            raise AgentIdentityError("agent_slug must be 1-128 ASCII letters, digits, '.', '_' or '-'")

        # Relocate a pre-existing in-root key before any existence check, so a
        # legacy identity is found (and never shadowed by a new key). Runs only
        # after the slug is validated, since the slug becomes a path component.
        if legacy_home is not None and did_home_root is not None:
            _relocate_legacy_identity(agent_slug, legacy_home=legacy_home, store_home=did_home_root)

        identity_path = agent_dir(agent_slug, did_home_root=did_home_root)
        if expected_did and not (identity_path / "private_key.pem").exists() and not (identity_path / "document.json").exists():
            raise AgentIdentityError(
                f"agent {agent_slug!r} has no existing identity at {identity_path}; refusing to create one while an expected DID is set"
            )
        if require_registered and not identity_path.exists():
            raise AgentIdentityError(
                f"agent {agent_slug!r} has no existing identity at {identity_path}; refusing to create an unregistered identity during runtime startup"
            )

        did, keypair, did_document = load_or_create_did(
            agent_slug, did_home_root=did_home_root, legacy_home=legacy_home
        )
        if profile_binding is not None and did != profile_binding["did"]:
            raise AgentIdentityError("profile identity binding DID does not match the stored key")
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
            profile_root=resolved_profile_root,
            did_home_root=did_home_root,
            principal=principal,
            device_id=device_id,
            require_device_binding=require_device_binding,
        )
        if require_registered and runtime.registration_status() is not True:
            client.close()
            raise AgentNotRegisteredError(
                f"agent {agent_slug!r} ({did}) is not confirmed registered with the Integrity Oracle"
            )
        if resolved_profile_root is not None and (profile_binding is None or binding_is_legacy):
            try:
                write_did_file(
                    resolved_profile_root,
                    did=did,
                    public_key=keypair.public_bytes(),
                    agent_id=agent_slug,
                    harness=harness,
                    profile=profile,
                )
            except DidFileError as exc:
                raise AgentIdentityError(str(exc)) from exc
            _retire_legacy_layout(resolved_profile_root)
        snapshot = runtime.identity_snapshot()
        snapshot["last_seen_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        record_identity(snapshot, event="identity_loaded", path=did_home_root)
        return runtime

    def registration_status(self) -> bool | None:
        """Return Oracle registration state, or ``None`` when inconclusive."""
        return self.client.registration_status()

    def identity_snapshot(self) -> dict[str, Any]:
        """Return a non-secret identity registry projection.

        The DID directory and DID document remain canonical. This projection
        deliberately does not create a second key store or claim that a
        controller, wallet, principal, or device are interchangeable.
        """
        wallet_refs = [
            method.get("blockchainAccountId")
            for method in self.did_document.get("verificationMethod", [])
            if isinstance(method, dict) and method.get("blockchainAccountId")
        ]
        created = self.did_document.get("created")
        return {
            "identity_version": 1,
            "agent_id": self.agent_slug,
            "harness": self.harness,
            "profile": self.profile,
            "profile_root": str(self.profile_root) if self.profile_root else None,
            "did": self.did,
            "did_controller": self.did_document.get("controller"),
            "principal": self.principal,
            "device_id": self.device_id,
            "wallet_references": wallet_refs,
            "key_fingerprint": self.did.removeprefix("did:integrity:"),
            "memory_store_reference": str(
                agent_dir(self.agent_slug, did_home_root=self.did_home_root)
            ),
            "identity_store_reference": str(
                agent_dir(self.agent_slug, did_home_root=self.did_home_root)
            ),
            "registration_status": self.registration_status(),
            "created_at": created,
            "last_seen_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "provenance_history": [{"event": "identity_created", "timestamp": created}],
        }

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
            "profile_root": str(self.profile_root) if self.profile_root else None,
            "principal": self.principal,
            "device_id": self.device_id,
        })
        self.client.log_telemetry(entry)

    def start_session(self, session_id: str, *, emit: bool = True, **fields: Any) -> None:
        self._session_id = session_id
        if emit:
            self.emit("session_started", session_id=session_id, **fields)

    def model_call(self, *, session_id: str | None = None, **fields: Any) -> None:
        self.emit("model_call", session_id=session_id or self._session_id, **fields)

    def tool_call(self, *, session_id: str | None = None, **fields: Any) -> None:
        self.emit("tool_call", session_id=session_id or self._session_id, **fields)

    def tool_result(self, *, session_id: str | None = None, **fields: Any) -> None:
        self.emit("tool_result", session_id=session_id or self._session_id, **fields)

    def complete(self, *, session_id: str | None = None, **fields: Any) -> None:
        self.emit("session_completed", session_id=session_id or self._session_id, **fields)

    def end_session(self, session_id: str | None = None, *, emit: bool = True, **fields: Any) -> None:
        if emit:
            self.emit("session_ended", session_id=session_id or self._session_id, **fields)
        self._session_id = None

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
