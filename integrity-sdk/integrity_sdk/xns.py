"""XNS handle availability, as the Integrity Oracle reports it.

A handle lives in two namespaces: the Oracle directory (`xns_handles`, used by off-chain
registration) and the on-chain `XibalbaNameService`. The Oracle's
`GET /v1/xns/available/{handle}` checks both and is the single implementation of that merge;
this module is a thin client so the SDK, the CLI and any UI agree on one answer.

`available` is True only when the handle is well-formed and verified free in both namespaces
(or XNS is not deployed). When the on-chain read could not be verified, `available` is False
and `onchain == "unverified"`: that means "can't confirm right now", not "taken".
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import requests

ONCHAIN_STATUSES = ("free", "taken", "not_deployed", "unverified")


@dataclass(frozen=True)
class HandleAvailability:
    handle: str
    available: bool
    valid: bool
    directory_available: bool | None
    onchain: str | None  # one of ONCHAIN_STATUSES, or None when the handle is malformed
    suggestions: tuple[str, ...]

    @property
    def unverified(self) -> bool:
        """The answer is unknown (on-chain XNS unreachable), not a refusal."""
        return self.onchain == "unverified"

    @property
    def taken_by(self) -> str | None:
        """Which namespace holds it: "directory", "onchain", "both", or None."""
        directory = self.directory_available is False
        onchain = self.onchain == "taken"
        if directory and onchain:
            return "both"
        if directory:
            return "directory"
        if onchain:
            return "onchain"
        return None


class XnsAvailabilityError(RuntimeError):
    """`status` is the HTTP status, or None when the Oracle was unreachable."""

    def __init__(self, status: int | None, detail: str):
        super().__init__(f"xns availability check failed ({status if status is not None else 'unreachable'}): {detail}")
        self.status = status
        self.detail = detail


def check_handle_availability(oracle_url: str, handle: str, *, timeout: float = 30.0) -> HandleAvailability:
    """Asks the Oracle whether `handle` is free in BOTH the directory and on-chain XNS.

    A malformed handle is not an error: it comes back `valid=False, available=False`.
    `timeout` defaults high enough to cover a free-tier cold start.
    """
    url = f"{oracle_url.rstrip('/')}/v1/xns/available/{quote(handle, safe='')}"
    try:
        resp = requests.get(url, timeout=timeout)
    except requests.RequestException as exc:
        raise XnsAvailabilityError(None, str(exc)) from exc
    if resp.status_code != 200:
        raise XnsAvailabilityError(resp.status_code, resp.text)
    try:
        body = resp.json()
        onchain = body.get("onchain")
        if onchain is not None and onchain not in ONCHAIN_STATUSES:
            raise ValueError(f"unknown onchain status {onchain!r}")
        return HandleAvailability(
            handle=body["handle"],
            available=bool(body["available"]),
            # Pre-dual-namespace Oracles omit these; treat "absent" as unknown, never as free.
            valid=bool(body.get("valid", body["available"])),
            directory_available=body.get("directory_available"),
            onchain=onchain,
            suggestions=tuple(body.get("suggestions") or ()),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise XnsAvailabilityError(resp.status_code, f"malformed response: {resp.text}") from exc
