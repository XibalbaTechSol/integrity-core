"""BCC's side of the shared signed decision receipts (integrity-core B2 stage 3).

The durable writer, the log format and the verifier are the SDK's (`integrity_sdk.core.receipt_writer`,
`integrity_sdk.core.receipts`); this module only decides *what BCC puts in a receipt* and keeps the writer off
the event loop.

What gets a receipt
-------------------
Every decision made after the commitment's Ed25519 signature verifies: replay, expiry, quarantine, policy
deny, token budget, BAA, and allow. **Not** the denials before that (open circuit breaker, chain/contract
mismatch, bad signature): until the signature verifies, `agent_id` is whatever the caller wrote, and a signed
receipt naming a real agent for a forged request would be evidence the protocol manufactured against the
wrong party. Those denials still go to the audit trail they always went to.

What a receipt says
-------------------
* `agent_did`   the agent id (a public DID, safe in the clear)
* `device_id`   the gate id (`BCC_GATE_ID`), HMAC-hashed by the writer
* `action`      ``intent_type|intended_state_hash`` (HMAC-hashed): ties the receipt to the exact signed commitment
* `pack_hash`   the signed pack that *decided*, else `NO_PACK_HASH`. In dual-run `bcc.rego` decides and the pack
                is advisory, so the receipt does not name the pack: it must name the policy actually enforced.
* `reason_code` the gate code (`BCC_NONCE_REPLAY`, `BAA_INACTIVE`, ...); for a policy deny, the pack's code in pack
                mode and `BCC_REGO_POLICY_DENY` under `bcc.rego`
* `mode`        ``shadow`` when `BCC_SHADOW_MODE` is on (the decision is what enforcement WOULD have done), else
                ``enforce``

Failure posture (stated per module)
-----------------------------------
* **Starting fails closed**: a key or log that cannot be used refuses to start the service (the SDK's rule).
* **Recording is strict by default.** In enforce mode an allow whose receipt cannot be written becomes a deny
  (`BCC_RECEIPT_UNAVAILABLE`, which never counts against the agent's circuit breaker: it is our failure).
  `BCC_LENIENT_RECEIPTS=1` lets it through with `receipt_status="failed"` and a CRITICAL log.
* **Shadow mode never blocks on a receipt**; a failure is logged and reported on the response only.
* **A denial is a denial regardless**: failing to record one is logged CRITICAL and reported, but the response
  is already the safe one.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from integrity_sdk.core import (
    DENY, ENFORCE, PERMIT, SHADOW, GateReceiptWriter, ReceiptRef, ReceiptSetupError, ReceiptWriteError,
    RotationPolicy, derive_log_id, load_hmac_key, load_signer,
)

from app.config import Settings

logger = logging.getLogger(__name__)

EVENT_CLASS = "agent.tool_call"
#: pack_hash for a decision no signed pack made (bcc.rego decided, or no policy ran). All zero on purpose: it
#: cannot be mistaken for a real hash, and a verifier can recognise it.
NO_PACK_HASH = "sha256:" + "00" * 32
REASON_REGO_PERMIT = "BCC_REGO_POLICY_PERMIT"
REASON_REGO_DENY = "BCC_REGO_POLICY_DENY"
REASON_RECEIPT_UNAVAILABLE = "BCC_RECEIPT_UNAVAILABLE"


@dataclass(frozen=True)
class RecordResult:
    ref: Optional[ReceiptRef]
    error: Optional[str]

    @property
    def status(self) -> str:
        return "recorded" if self.ref is not None else "failed"

    def as_response(self) -> Optional[dict]:
        if self.ref is None:
            return None
        return {"log_id": self.ref.log_id, "seq": self.ref.seq, "hash": self.ref.hash}


class BccReceipts:
    """Thin async adapter over the SDK's `GateReceiptWriter`."""

    def __init__(self, writer: GateReceiptWriter, *, gate_id: str, lenient: bool) -> None:
        self._writer = writer
        self.gate_id = gate_id
        self.lenient = lenient

    @classmethod
    def from_settings(cls, settings: Settings) -> Optional["BccReceipts"]:
        """None when receipts are not configured. Raises `ReceiptSetupError` when they are but cannot start."""
        if settings.receipt_dir is None:
            return None
        hmac_key = load_hmac_key(settings.receipt_hmac_key_file)  # type: ignore[arg-type]
        signer = load_signer(settings.receipt_key_file)  # type: ignore[arg-type]
        bounds = {}
        if settings.receipt_epoch_max_receipts:
            bounds["max_receipts"] = settings.receipt_epoch_max_receipts
        if settings.receipt_epoch_max_age_seconds:
            bounds["max_age_seconds"] = settings.receipt_epoch_max_age_seconds
        writer = GateReceiptWriter(
            settings.receipt_dir, signer=signer, hmac_key=hmac_key,
            log_id=derive_log_id("bcc-gate", hmac_key, settings.receipt_gate_id),
            checkpoint_every=settings.receipt_checkpoint_every,
            rotation=RotationPolicy(**bounds) if bounds else None,
        )
        return cls(writer, gate_id=settings.receipt_gate_id, lenient=settings.lenient_receipts)

    @property
    def signer_key(self) -> str:
        return self._writer.signer_key

    def health(self) -> dict:
        return {"enabled": True, "log_id": self._writer.log_id, "epoch": self._writer.epoch,
                "receipts_in_epoch": self._writer.receipt_count, "strict": not self.lenient,
                "signer_key": self.signer_key}

    async def record(
        self, *, agent_id: str, intent_type: str, intended_state_hash: str, permit: bool, reason_code: str,
        pack_hash: Optional[str], controls: tuple[str, ...], shadow: bool,
    ) -> RecordResult:
        """Record one decision. Never raises: the caller applies strict/lenient/shadow policy to the result."""
        try:
            ref = await asyncio.to_thread(
                self._writer.record,
                agent_did=agent_id, device_id=self.gate_id, action=f"{intent_type}|{intended_state_hash}",
                event_class=EVENT_CLASS, pack_hash=pack_hash or NO_PACK_HASH,
                decision=PERMIT if permit else DENY, reason_code=reason_code,
                mode=SHADOW if shadow else ENFORCE, controls=controls,
            )
        except ReceiptWriteError as exc:
            return RecordResult(None, str(exc))
        except Exception as exc:  # the writer must never be able to crash a request
            logger.exception("unexpected error recording a receipt")
            return RecordResult(None, f"{type(exc).__name__}: {exc}")
        return RecordResult(ref, None)

    def close(self) -> None:
        self._writer.close()


__all__ = ["BccReceipts", "RecordResult", "NO_PACK_HASH", "ReceiptSetupError"]
