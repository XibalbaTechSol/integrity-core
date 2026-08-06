"""Collection profiles — L2/L3 of `docs/design/sdk-data-collection-strategy.md`.

The property under test throughout: narrowing a profile restricts the CONTENT layer only.
Structural fields (token counts, model ids, latencies) are what the protocol scores on and are
always collected, so no profile can silently weaken a score.

Redaction being off by default is an explicit operator decision, asserted here so a future
change to it is a deliberate test edit rather than a silent drift.
"""

from __future__ import annotations

from integrity_sdk.client import IntegrityClient
from integrity_sdk.collection import CollectionConfig, CollectionProfile


def test_default_profile_is_development_with_redaction_off() -> None:
    config = CollectionConfig.from_env({})
    assert config.profile is CollectionProfile.DEVELOPMENT
    assert config.capture_content is True
    assert config.redact_content is False, "redaction is off by default — operator decision"


def test_regulated_profile_withholds_content_entirely() -> None:
    """Redaction alone is not the safe setting for a regulated deployment: not collecting is.
    Redaction stays on for anything that slips past `capture_content`."""
    config = CollectionConfig.for_profile(CollectionProfile.REGULATED)
    assert config.capture_content is False
    assert config.redact_content is True

    out = config.apply({"text_output": "patient MRN 12345", "token_usage": {"input_tokens": 10}})
    assert "12345" not in out["text_output"]
    assert out["token_usage"] == {"input_tokens": 10}, "structural fields must survive every profile"


def test_withheld_content_leaves_a_marker_rather_than_vanishing() -> None:
    """A missing field and a deliberately-withheld field must be distinguishable when reading
    an audit trail later."""
    config = CollectionConfig.for_profile(CollectionProfile.REGULATED)
    out = config.apply({"text_output": "something"})
    assert "not collected" in out["text_output"]
    assert "profile=regulated" in out["text_output"]


def test_development_profile_keeps_content_verbatim() -> None:
    config = CollectionConfig.for_profile(CollectionProfile.DEVELOPMENT)
    out = config.apply({"text_output": "exact text, unredacted"})
    assert out["text_output"] == "exact text, unredacted"


def test_content_is_truncated_at_the_cap_with_a_visible_marker() -> None:
    config = CollectionConfig.for_profile(CollectionProfile.DEVELOPMENT)
    long_text = "x" * (config.max_content_chars + 500)
    out = config.apply({"text_output": long_text})
    assert out["text_output"].endswith("…[truncated]")
    assert len(out["text_output"]) < len(long_text)


def test_sampling_is_all_or_nothing_per_entry() -> None:
    """A half-captured call is harder to reason about than a skipped one, so the sampling
    decision covers every content field in an entry together."""
    config = CollectionConfig.for_profile(CollectionProfile.STANDARD)
    zero = CollectionConfig(config.profile, True, False, 0.0, config.max_content_chars)
    out = zero.apply({"text_output": "a", "prompt": "b", "token_usage": {"input_tokens": 1}})
    assert "sampled out" in out["text_output"]
    assert "sampled out" in out["prompt"]
    assert out["token_usage"] == {"input_tokens": 1}


def test_env_overrides_one_axis_without_inventing_a_profile() -> None:
    config = CollectionConfig.from_env(
        {"INTEGRITY_COLLECTION_PROFILE": "development", "INTEGRITY_REDACT_CONTENT": "1", "INTEGRITY_MAX_CONTENT_CHARS": "10"}
    )
    assert config.profile is CollectionProfile.DEVELOPMENT
    assert config.redact_content is True
    assert config.max_content_chars == 10


def test_unknown_profile_falls_back_to_development_rather_than_raising() -> None:
    """A typo in an env var must not take an agent down. Falling back to the profile that
    collects MOST means the failure mode is noisy data, not silent loss."""
    config = CollectionConfig.from_env({"INTEGRITY_COLLECTION_PROFILE": "sooper-secure"})
    assert config.profile is CollectionProfile.DEVELOPMENT


def test_malformed_numeric_override_keeps_the_profile_default() -> None:
    config = CollectionConfig.from_env({"INTEGRITY_CONTENT_SAMPLE_RATE": "not-a-number"})
    assert config.content_sample_rate == 1.0


def test_sample_rate_is_clamped_to_a_valid_fraction() -> None:
    assert CollectionConfig.from_env({"INTEGRITY_CONTENT_SAMPLE_RATE": "5"}).content_sample_rate == 1.0
    assert CollectionConfig.from_env({"INTEGRITY_CONTENT_SAMPLE_RATE": "-2"}).content_sample_rate == 0.0


def test_client_applies_the_policy_at_capture_not_at_flush(captured_posts) -> None:
    """Content the profile withholds must never enter the queue: a crash between log and flush
    would otherwise still expose it from memory, and a queue dump would contain what the
    operator said not to collect."""
    client = IntegrityClient(
        "agent-profile",
        auto_flush=False,
        background_flush=False,
        collection=CollectionConfig.for_profile(CollectionProfile.REGULATED),
    )
    client.log_telemetry({"text_output": "patient MRN 12345", "token_usage": {"input_tokens": 7}})

    queued = client._batcher.queue[0]["metadata"]
    assert "12345" not in queued["text_output"], "withheld content must not be queued at all"

    client.flush_telemetry()
    entry = [s for s in captured_posts[0]["json"]["otel_spans"] if s.get("kind") == "telemetry"][0]
    assert entry["metadata"]["token_usage"] == {"input_tokens": 7}
