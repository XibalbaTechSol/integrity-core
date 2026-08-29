"""Cross-language conformance for token accounting.

`integrity_sdk.telemetry.derive.entry_token_total` and integrity-oracle's
`backend/src/derive.rs::entry_token_total` must agree on every vector in
`spec/token-accounting/vectors.json`. Both test suites read that one file, so the two
implementations cannot drift apart silently.

This exists because they previously drifted into the *same* bug — summing `total_tokens`
AND `prompt_tokens` AND `completion_tokens`, so every OpenAI-shaped entry counted twice —
and because both sides were wrong in the same direction, no reconciliation between them
could reveal it. Each side's own unit tests passed, because neither covered the all-three
shape that OpenAI actually emits.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from integrity_sdk.telemetry.derive import entry_token_total

VECTORS_PATH = Path(__file__).resolve().parent.parent.parent / "spec" / "token-accounting" / "vectors.json"


def _load_vectors() -> list[dict]:
    assert VECTORS_PATH.exists(), (
        f"shared conformance vectors missing at {VECTORS_PATH} — the oracle's Rust test reads "
        "the same file, so a missing file means the two implementations are unpinned"
    )
    doc = json.loads(VECTORS_PATH.read_text())
    vectors = doc["vectors"]
    # A silently empty list would make every parametrized case vanish and the suite would
    # still report green — assert the file has content rather than trusting it.
    assert vectors, "vector file must not be empty"
    return vectors


@pytest.mark.parametrize("vector", _load_vectors(), ids=lambda v: v["name"])
def test_entry_token_total_matches_shared_vector(vector: dict) -> None:
    actual = entry_token_total(vector["entry"])
    assert actual == vector["expected"], (
        f"vector '{vector['name']}' disagrees ({vector.get('why', '')}): "
        f"expected {vector['expected']}, got {actual}"
    )


def test_openai_all_three_keys_is_not_double_counted() -> None:
    """The specific regression, asserted directly as well as via the vector file — the
    vector file could in principle be edited to match a broken implementation, whereas this
    states the invariant in prose-backed code."""
    entry = {"metadata": {"token_usage": {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}}}
    assert entry_token_total(entry) == 1500, "total_tokens already includes prompt+completion"


def test_anthropic_cache_tokens_are_additive_but_openai_cached_tokens_are_not() -> None:
    """The two providers use opposite semantics, and confusing them re-introduces a
    double-count in whichever direction you get wrong."""
    anthropic = {
        "metadata": {
            "token_usage": {
                "input_tokens": 1000,
                "output_tokens": 100,
                "cache_read_input_tokens": 5000,
            }
        }
    }
    # Cache reads are billed and processed IN ADDITION to input_tokens.
    assert entry_token_total(anthropic) == 6100

    openai = {
        "metadata": {
            "token_usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 100,
                "total_tokens": 1100,
                "prompt_tokens_details": {"cached_tokens": 900},
            }
        }
    }
    # cached_tokens is a SUBSET of prompt_tokens — already counted inside total_tokens.
    assert entry_token_total(openai) == 1100
