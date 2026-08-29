"""
Real OPA REST client -- the single most security-critical module in this
service.

docs/INTERFACE_CONTRACT.md §7 is unambiguous: "if OPA is unreachable, the
request must fail closed (deny), not silently approve." The old prototype
violated this by falling back to a hardcoded keyword scan when OPA was down
(masking an infra outage as "policy says yes" is a fail-OPEN bug -- an OPA
outage would have silently disabled all HIPAA guardrails). This module has
exactly one way to say "allowed": a well-formed HTTP 200 from a real OPA
server with `result.allow == true`. Every other outcome -- connection
refused, timeout, non-200, malformed JSON, missing `result` key -- raises
`OPAUnavailableError`, and the caller (main.py) treats that identically to
an explicit policy denial.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx



class OPAUnavailableError(Exception):
    """
    OPA could not be reached or returned something we can't trust. Callers
    MUST deny the request when this is raised -- there is no fallback path.
    """


@dataclass
class OPADecision:
    allow: bool
    violations: list[str] = field(default_factory=list)
    requires_baa: bool = False
    raw_result: dict = field(default_factory=dict)


async def evaluate(opa_url: str, opa_package_path: str, opa_timeout_seconds: float, opa_input: dict) -> OPADecision:
    """
    Evaluate the `integrity/bcc` policy package against `opa_input`.

    We query the package root (`/v1/data/integrity/bcc`) rather than only
    the `/allow` leaf named in §7 so we get `violation` and `requires_baa`
    out of the same round trip -- see config.py's `opa_package_path`
    docstring for why this is still the identical `allow` rule the spec'd
    endpoint would evaluate.
    """
    url = f"{opa_url.rstrip('/')}{opa_package_path}"
    try:
        async with httpx.AsyncClient(timeout=opa_timeout_seconds) as client:
            resp = await client.post(url, json={"input": opa_input})
    except httpx.HTTPError as exc:
        # Connection refused, DNS failure, timeout, TLS error, etc. -- OPA is
        # not reachable. Fail closed: this is NOT a policy decision, so we
        # never synthesize `allow=False` here and pretend it came from Rego;
        # we raise, and the caller must treat "can't reach OPA" as its own
        # explicit deny path (and, importantly, NOT count it as an agent
        # circuit-breaker violation -- see main.py).
        raise OPAUnavailableError(f"OPA request failed: {exc}") from exc

    if resp.status_code != 200:
        raise OPAUnavailableError(f"OPA returned HTTP {resp.status_code}: {resp.text[:500]}")

    try:
        body = resp.json()
    except ValueError as exc:
        raise OPAUnavailableError(f"OPA response was not valid JSON: {exc}") from exc

    if "result" not in body:
        # A package with no matching rules (e.g. typo'd package path) comes
        # back as `{}` with no `result` key at all -- this must NOT be
        # silently treated as `allow=False` via `.get(..., False)`, because
        # that would mask a broken deployment (wrong policy path) as a
        # normal policy denial forever. Surface it loudly instead.
        raise OPAUnavailableError(f"OPA response missing 'result' (bad policy path {opa_package_path}?): {body}")

    result = body["result"]
    if not isinstance(result, dict) or "allow" not in result or not isinstance(result["allow"], bool):
        raise OPAUnavailableError(f"OPA result missing boolean 'allow' field: {result!r}")

    violations = result.get("violation", [])
    if not isinstance(violations, list):
        violations = [str(violations)]

    return OPADecision(
        allow=result["allow"],
        violations=[str(v) for v in violations],
        requires_baa=bool(result.get("requires_baa", False)),
        raw_result=result,
    )


async def is_reachable(opa_url: str) -> bool:
    """Cheap liveness probe for /health -- failures here are not security decisions."""
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(f"{opa_url.rstrip('/')}/health")
        return resp.status_code == 200
    except httpx.HTTPError:
        return False
