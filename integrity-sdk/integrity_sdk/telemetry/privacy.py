"""Explicit, deterministic privacy policy for developer telemetry."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from ..security.redactor import redact_text

_CONTENT_KEYS = {"content", "prompt", "response", "completion", "result", "arguments", "tool_result", "tool_output"}


@dataclass(frozen=True)
class PrivacyPolicy:
    """Controls what enters a canonical envelope.

    ``redacted`` retains structured content after secret/PII masking;
    ``metadata_only`` removes content values; ``hash_only`` retains only
    deterministic digests and lengths. Location is always removed unless the
    caller explicitly opts in.
    """

    mode: str = "redacted"
    allow_location: bool = False
    max_content_chars: int = 16_384
    retention_days: float | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"redacted", "metadata_only", "hash_only"}:
            raise ValueError("privacy mode must be redacted, metadata_only, or hash_only")
        if self.max_content_chars < 0:
            raise ValueError("max_content_chars must not be negative")
        if self.retention_days is not None and self.retention_days < 0:
            raise ValueError("retention_days must not be negative")

    def apply(self, value: Mapping[str, Any]) -> dict[str, Any]:
        return self._apply_mapping(value)

    def _apply_mapping(self, value: Mapping[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            lowered = name.lower()
            if lowered in {"location", "latitude", "longitude", "lat", "lon"} and not self.allow_location:
                continue
            if self.mode == "metadata_only" and lowered in _CONTENT_KEYS:
                result[name] = "<content not collected: privacy=metadata_only>"
                continue
            result[name] = self._apply_value(item, is_content=lowered in _CONTENT_KEYS)
        return result

    def _apply_value(self, value: Any, *, is_content: bool = False) -> Any:
        if isinstance(value, Mapping):
            return self._apply_mapping(value)
        if isinstance(value, (list, tuple)):
            return [self._apply_value(item, is_content=is_content) for item in value]
        if not isinstance(value, str):
            return value
        redacted = redact_text(value).text
        if self.mode == "hash_only" or (is_content and self.mode == "metadata_only"):
            return {"sha256": hashlib.sha256(redacted.encode()).hexdigest(), "length": len(redacted)}
        if self.max_content_chars and len(redacted) > self.max_content_chars:
            return redacted[:self.max_content_chars] + "…[truncated]"
        return redacted
