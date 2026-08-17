from __future__ import annotations

import math

from integrity_sdk.telemetry import derive


def test_lexical_stability_perfectly_repetitive_text_is_max_stable():
    # All identical words = zero entropy = maximally stable = 1.0
    assert derive.lexical_stability_score("yes yes yes yes") == 1.0


def test_lexical_stability_all_distinct_words_is_least_stable():
    # Every word distinct = maximum entropy for that count = normalized 1.0
    # inverted to ~0.0.
    score = derive.lexical_stability_score("alpha beta gamma delta epsilon")
    assert score < 0.01


def test_lexical_stability_empty_or_single_word_returns_max():
    assert derive.lexical_stability_score("") == 1.0
    assert derive.lexical_stability_score("solo") == 1.0


def test_lexical_stability_is_between_zero_and_one():
    score = derive.lexical_stability_score("the cat sat on the mat the cat ran")
    assert 0.0 <= score <= 1.0


def test_keyword_grounding_penalizes_uncertainty_markers():
    assert derive.keyword_grounding_score("I'm not sure about this") == 0.40
    assert derive.keyword_grounding_score("The answer is 42") == 0.95


def test_derive_entropy_prefers_precomputed_value():
    batch = [{"entropy": 0.7, "metadata": {"text_output": "all distinct words here now"}}]
    # Precomputed 0.7 must win over recomputing from text.
    assert derive.derive_entropy(batch) == 0.7


def test_derive_entropy_recomputes_from_text_when_no_precomputed():
    batch = [{"metadata": {"text_output": "yes yes yes yes"}}]
    assert derive.derive_entropy(batch) == 1.0


def test_derive_entropy_empty_batch_fails_closed_to_zero():
    assert derive.derive_entropy([]) == 0.0


def test_derive_grounding_empty_batch_fails_closed_to_zero():
    assert derive.derive_grounding([]) == 0.0


def test_derive_compliance_empty_batch_fails_closed_to_zero():
    assert derive.derive_compliance([]) == 0.0


def test_content_free_submission_with_token_counts_fails_closed_on_entropy_and_grounding():
    # Regression for the attack this fix closes (spec/integrity-protocol-v3.2.md
    # §3.1.1): a submission carrying token counts (so sacrifice is nonzero) but no
    # analysable text_output must not read as maximally stable and grounded.
    batch = [{"metadata": {"token_usage": {"total_tokens": 5_000_000}}}]
    assert derive.derive_entropy(batch) == 0.0
    assert derive.derive_grounding(batch) == 0.0
    assert derive.derive_sacrifice(batch) > 0.0


def test_derive_sacrifice_scales_with_total_tokens():
    small = [{"metadata": {"token_usage": {"total_tokens": 100}}}]
    large = [{"metadata": {"token_usage": {"total_tokens": 100_000}}}]
    assert derive.derive_sacrifice(large) > derive.derive_sacrifice(small)
    assert 0.0 <= derive.derive_sacrifice(small) <= 1.0
    assert 0.0 <= derive.derive_sacrifice(large) <= 1.0


def test_derive_sacrifice_zero_tokens_is_zero():
    assert derive.derive_sacrifice([{"metadata": {}}]) == 0.0


def test_derive_compliance_self_reported_penalizes_flagged_entries():
    batch = [
        {"metadata": {"flagged": True}},
        {"metadata": {"flagged": False}},
        {"metadata": {}},
        {"metadata": {}},
    ]
    # 1 of 4 flagged -> 0.75 clean.
    assert derive.derive_compliance(batch) == 0.75


def test_derive_compliance_no_flags_is_perfect():
    batch = [{"metadata": {}}, {"metadata": {}}]
    assert derive.derive_compliance(batch) == 1.0


def test_derive_ais_signals_returns_all_four_keys():
    batch = [{"metadata": {"text_output": "hello world", "token_usage": {"total_tokens": 500}}}]
    signals = derive.derive_ais_signals(batch)
    assert set(signals.keys()) == {"entropy", "grounding", "sacrifice", "compliance"}
    for value in signals.values():
        assert 0.0 <= value <= 1.0
