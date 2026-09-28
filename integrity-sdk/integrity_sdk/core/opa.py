"""The one OPA client: runs a verified pack in an OPA server and resolves its result.

Replaces the SDK's two unused OPA clients (`opa_client.py`, `policy/opa_client.py`)
with one that speaks the decision contract (`core.decision`). Two guarantees:

1. **OPA runs exactly the signed bytes.** `install` replaces every module this
   client owns (ids under ``integrity-pack/``) with the Rego sources of a
   `LoadedPack`, the bytes `load_pack` verified, then reads the policies back
   from OPA and refuses (`OpaError("INSTALLED_POLICY_MISMATCH")`) unless OPA
   holds exactly those sources. Evaluation is refused for any pack other than
   the one installed.
2. **Every failure fails closed.** A transport error, a non-200 response,
   unparseable JSON or a pack mismatch becomes ``evaluator_error``, which
   `resolve` turns into a deny with ``INTEGRITY_EVALUATOR_ERROR``. An undefined
   result (OPA returns ``{}`` with no ``result`` key when no rule matched)
   becomes `NO_MATCH`, which takes the pack's declared per-class default.

OPA REST API used: ``PUT/GET/DELETE /v1/policies`` and ``POST /v1/data/<path>``
(https://www.openpolicyagent.org/docs/latest/rest-api/). It is standard-library
HTTP only, so the SDK core stays dependency-light. OPA is a sidecar here, local
to the gate, so environment proxy settings are deliberately ignored: a policy
query must never be routed through, or blocked by, an egress proxy.

An install and the evaluations after it are serialized by a lock, so an
evaluation never observes the moment between removing the old modules and
adding the new ones. The gate should give this client its own OPA instance.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Any, Dict, Mapping, Optional

from .decision import ENFORCE, NO_MATCH, Decision, resolve
from .packs import LoadedPack

POLICY_ID_PREFIX = "integrity-pack/"


class OpaError(Exception):
    """OPA could not be driven into the verified state; the gate must not enforce with it."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def entrypoint_path(entrypoint: str) -> str:
    """``data.integrity.pack.decision`` -> ``integrity/pack/decision`` (the /v1/data URL path)."""
    if not entrypoint.startswith("data."):
        raise ValueError(f"not a Rego data path: {entrypoint!r}")
    return entrypoint[len("data."):].replace(".", "/")


class OpaClient:
    def __init__(self, base_url: str, *, timeout_seconds: float = 2.0):
        self._base = base_url.rstrip("/")
        self._timeout = timeout_seconds
        # No ProxyHandler entries: never route the local policy sidecar through a proxy.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self._lock = threading.Lock()
        self._installed_pack_hash: Optional[str] = None

    @property
    def installed_pack_hash(self) -> Optional[str]:
        return self._installed_pack_hash

    # ------------------------------------------------------------------------ transport ---

    def _request(self, method: str, path: str, body: Optional[bytes] = None, content_type: str = "application/json") -> Any:
        request = urllib.request.Request(self._base + path, data=body, method=method)
        if body is not None:
            request.add_header("Content-Type", content_type)
        with self._opener.open(request, timeout=self._timeout) as response:
            if response.status != 200:
                raise OpaError("OPA_HTTP_ERROR", f"{method} {path} returned {response.status}")
            raw = response.read()
        return json.loads(raw) if raw else {}

    def _owned_policies(self) -> Dict[str, str]:
        listing = self._request("GET", "/v1/policies")
        return {
            entry["id"]: entry.get("raw", "")
            for entry in listing.get("result", [])
            if isinstance(entry, dict) and str(entry.get("id", "")).startswith(POLICY_ID_PREFIX)
        }

    # -------------------------------------------------------------------------- install ---

    def install(self, pack: LoadedPack) -> None:
        """Make OPA run exactly `pack`'s verified Rego, or raise `OpaError`.

        On failure the client records no installed pack, so every evaluation
        denies until a later install succeeds.
        """
        modules = {POLICY_ID_PREFIX + path: source for path, source in pack.policy_modules().items()}
        with self._lock:
            self._installed_pack_hash = None
            try:
                for policy_id in self._owned_policies():
                    self._request("DELETE", "/v1/policies/" + policy_id)
                for policy_id, source in modules.items():
                    self._request("PUT", "/v1/policies/" + policy_id, source.encode("utf-8"), "text/plain")
                installed = self._owned_policies()
            except urllib.error.HTTPError as exc:
                # OPA answered but refused, e.g. 400 for Rego that does not compile.
                raise OpaError("OPA_HTTP_ERROR", f"OPA returned {exc.code}: {exc.reason}") from exc
            except (urllib.error.URLError, OSError, ValueError) as exc:
                raise OpaError("OPA_UNAVAILABLE", str(exc)) from exc
            if installed != modules:
                raise OpaError("INSTALLED_POLICY_MISMATCH", "OPA does not hold exactly the verified pack sources")
            self._installed_pack_hash = pack.pack_hash

    # ------------------------------------------------------------------------- evaluate ---

    def query(self, pack: LoadedPack, opa_input: Mapping[str, Any]) -> Any:
        """Raw entrypoint result, or `NO_MATCH` when undefined. Raises on any failure."""
        if self._installed_pack_hash != pack.pack_hash:
            raise OpaError("PACK_NOT_INSTALLED", "the pack being enforced is not the one installed in OPA")
        body = json.dumps({"input": dict(opa_input)}).encode("utf-8")
        response = self._request("POST", "/v1/data/" + entrypoint_path(pack.entrypoint), body)
        if not isinstance(response, dict):
            raise OpaError("OPA_MALFORMED_RESPONSE", "OPA returned a non-object response")
        return response["result"] if "result" in response else NO_MATCH

    def decide(
        self,
        pack: Optional[LoadedPack],
        event_class: str,
        opa_input: Mapping[str, Any],
        *,
        mode: str = ENFORCE,
    ) -> Decision:
        """Evaluate and resolve under the decision contract. Never raises for policy/transport failures."""
        if pack is None:
            return resolve(event_class, None, event_defaults=None, mode=mode)
        with self._lock:
            try:
                result = self.query(pack, opa_input)
            except (OpaError, urllib.error.URLError, OSError, ValueError) as exc:
                return resolve(
                    event_class, None, event_defaults=pack.event_defaults, mode=mode,
                    pack_hash=pack.pack_hash, evaluator_error=exc,
                )
        return resolve(event_class, result, event_defaults=pack.event_defaults, mode=mode, pack_hash=pack.pack_hash)
