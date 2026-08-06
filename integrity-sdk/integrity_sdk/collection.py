"""
Collection profiles — the control plane that makes "collect broadly now, restrict later" a
configuration change rather than a migration.

L2/L3 of `docs/design/sdk-data-collection-strategy.md`. One environment variable widens or
narrows the whole surface:

    INTEGRITY_COLLECTION_PROFILE = development | standard | regulated

**Redaction is OFF by default, deliberately** (operator decision, 2026-07-29). The
development and standard profiles capture content as-is; only `regulated` turns redaction on,
and it disables content capture outright. That ordering matters: an operator running the
regulated profile has said their data is regulated, so the safe setting is not merely
redacting content but not collecting it.

Note the boundary this does NOT control: `integrity-oracle` runs its own PHI backstop and
**rejects** a payload whose content trips it (`AppError::PhiDetected` -> 400). Capturing
content here does not by itself make the oracle accept it — see that handler.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Dict, Optional

#: Metadata keys treated as free-text content, subject to the content policy below. Anything
#: not listed is structural (token counts, model ids, latencies) and always collected — those
#: are the fields the protocol actually scores on.
CONTENT_KEYS = ("text_output", "prompt", "completion", "system_prompt", "tool_result")


class CollectionProfile(str, Enum):
    #: Everything on, content unredacted and unsampled. For building and debugging.
    DEVELOPMENT = "development"
    #: Structural data on; content sampled rather than captured wholesale.
    STANDARD = "standard"
    #: No content capture at all, and redaction forced on for anything that slips through.
    REGULATED = "regulated"


@dataclass(frozen=True)
class CollectionConfig:
    profile: CollectionProfile
    #: Whether free-text content (completions, prompts, tool results) is collected at all.
    capture_content: bool
    #: Whether captured content is run through the redactor first.
    redact_content: bool
    #: Fraction of entries that keep their content, 0.0–1.0. Structural fields are never
    #: sampled away — only content is, so a sampled-out entry still scores.
    content_sample_rate: float
    #: Hard cap per content field. Prevents one pathological completion from dominating a
    #: batch, which matters more once collection widens.
    max_content_chars: int

    @staticmethod
    def for_profile(profile: CollectionProfile) -> "CollectionConfig":
        if profile is CollectionProfile.REGULATED:
            return CollectionConfig(profile, capture_content=False, redact_content=True, content_sample_rate=0.0, max_content_chars=0)
        if profile is CollectionProfile.STANDARD:
            return CollectionConfig(profile, capture_content=True, redact_content=False, content_sample_rate=0.1, max_content_chars=4_096)
        return CollectionConfig(profile, capture_content=True, redact_content=False, content_sample_rate=1.0, max_content_chars=16_384)

    @staticmethod
    def from_env(env: Optional[Dict[str, str]] = None) -> "CollectionConfig":
        """Resolves a profile, then applies any per-field override.

        An unrecognized profile name falls back to `development` with a warning rather than
        raising: a typo in an env var should not take an agent down, and development is the
        profile that collects most, so the failure mode is noisy data rather than silent loss.
        Overrides exist so a deployment can deviate on one axis without inventing a profile.
        """
        source = os.environ if env is None else env
        raw = (source.get("INTEGRITY_COLLECTION_PROFILE") or "development").strip().lower()
        try:
            profile = CollectionProfile(raw)
        except ValueError:
            import logging

            logging.getLogger("integrity_sdk.collection").warning(
                "unknown INTEGRITY_COLLECTION_PROFILE %r — falling back to 'development'; valid: %s",
                raw, ", ".join(p.value for p in CollectionProfile),
            )
            profile = CollectionProfile.DEVELOPMENT

        config = CollectionConfig.for_profile(profile)

        def _bool(key: str) -> Optional[bool]:
            value = source.get(key)
            if value is None:
                return None
            return value.strip().lower() in ("1", "true", "yes", "on")

        capture = _bool("INTEGRITY_CAPTURE_CONTENT")
        redact = _bool("INTEGRITY_REDACT_CONTENT")
        rate = source.get("INTEGRITY_CONTENT_SAMPLE_RATE")
        max_chars = source.get("INTEGRITY_MAX_CONTENT_CHARS")

        if capture is not None:
            config = replace(config, capture_content=capture)
        if redact is not None:
            config = replace(config, redact_content=redact)
        if rate is not None:
            try:
                config = replace(config, content_sample_rate=min(1.0, max(0.0, float(rate))))
            except ValueError:
                pass  # keep the profile default rather than guessing at a malformed number
        if max_chars is not None:
            try:
                config = replace(config, max_content_chars=max(0, int(max_chars)))
            except ValueError:
                pass
        return config

    def apply(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Returns metadata with the content policy applied. Structural fields pass untouched.

        Content that is dropped or truncated leaves a marker (`<content not collected:
        profile=...>` / a `…[truncated]` suffix) rather than vanishing. A missing field and a
        deliberately-withheld field look identical otherwise, and the difference matters when
        reading an audit trail later.
        """
        present = [k for k in CONTENT_KEYS if isinstance(metadata.get(k), str)]
        if not present:
            return metadata

        out = dict(metadata)

        if not self.capture_content:
            for key in present:
                out[key] = f"<content not collected: profile={self.profile.value}>"
            return out

        # Sampling decision is per entry, not per field, so one entry's content is either
        # wholly present or wholly withheld — a half-captured call is harder to reason about
        # than a skipped one.
        if self.content_sample_rate < 1.0 and random.random() > self.content_sample_rate:
            for key in present:
                out[key] = f"<content sampled out: rate={self.content_sample_rate}>"
            return out

        for key in present:
            text = out[key]
            if self.redact_content:
                from .security.redactor import redact_text

                text = redact_text(text)
            if self.max_content_chars and len(text) > self.max_content_chars:
                text = text[: self.max_content_chars] + "…[truncated]"
            out[key] = text
        return out
