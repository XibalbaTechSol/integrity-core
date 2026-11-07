"""Verification-tier cache: TTL + bounded last-known-good.

Safety properties under test (each has a case that must FAIL if the property is removed):
  * a fresh value is served without calling the oracle (no per-commitment WAN hop)
  * a changed tier (e.g. a downgrade) is picked up once the TTL lapses
  * a transient oracle failure serves the last-known-good value, but only up to max_stale
  * past max_stale, or with no prior value, the answer is tier 0 (unchanged fail-low)
  * an authoritative 4xx (agent gone) is NEVER answered from stale cache
"""
from __future__ import annotations

import httpx
import pytest
import respx
from httpx import Response

from app import chain

URL = "http://oracle.test"
AGENT = "did:integrity:cache-test"


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture()
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(chain, "_clock", c)
    monkeypatch.setattr(chain, "_TIER_FRESH_TTL", 60.0)
    monkeypatch.setattr(chain, "_TIER_MAX_STALE", 3600.0)
    chain.clear_tier_cache()
    yield c
    chain.clear_tier_cache()


def _route(mock, **kw):
    return mock.get(f"{URL}/v1/agent/{AGENT}").mock(**kw)


def test_fresh_value_is_served_without_calling_oracle(clock):
    with respx.mock(assert_all_called=False) as mock:
        r = _route(mock, return_value=Response(200, json={"verification_tier": 2}))
        assert chain.resolve_verification_tier(AGENT, oracle_url=URL) == 2
        clock.t += 59
        assert chain.resolve_verification_tier(AGENT, oracle_url=URL) == 2
        assert r.call_count == 1


def test_tier_change_is_picked_up_after_ttl(clock):
    with respx.mock(assert_all_called=False) as mock:
        r = _route(mock, side_effect=[Response(200, json={"verification_tier": 2}),
                                      Response(200, json={"verification_tier": 0})])
        assert chain.resolve_verification_tier(AGENT, oracle_url=URL) == 2
        clock.t += 61
        assert chain.resolve_verification_tier(AGENT, oracle_url=URL) == 0
        assert r.call_count == 2


def test_transient_failure_serves_last_known_good(clock):
    with respx.mock(assert_all_called=False) as mock:
        _route(mock, side_effect=[Response(200, json={"verification_tier": 2}), httpx.ConnectTimeout("asleep")])
        assert chain.resolve_verification_tier(AGENT, oracle_url=URL) == 2
        clock.t += 61
        assert chain.resolve_verification_tier(AGENT, oracle_url=URL) == 2


def test_server_error_serves_last_known_good(clock):
    with respx.mock(assert_all_called=False) as mock:
        _route(mock, side_effect=[Response(200, json={"verification_tier": 1}), Response(503)])
        assert chain.resolve_verification_tier(AGENT, oracle_url=URL) == 1
        clock.t += 61
        assert chain.resolve_verification_tier(AGENT, oracle_url=URL) == 1


def test_last_known_good_expires_after_max_stale(clock):
    with respx.mock(assert_all_called=False) as mock:
        _route(mock, side_effect=[Response(200, json={"verification_tier": 2}), httpx.ConnectTimeout("down")])
        assert chain.resolve_verification_tier(AGENT, oracle_url=URL) == 2
        clock.t += 3601
        assert chain.resolve_verification_tier(AGENT, oracle_url=URL) == 0


def test_no_prior_value_and_oracle_down_is_tier_zero(clock):
    with respx.mock(assert_all_called=False) as mock:
        _route(mock, side_effect=httpx.ConnectError("refused"))
        assert chain.resolve_verification_tier(AGENT, oracle_url=URL) == 0


def test_authoritative_404_is_never_served_from_stale(clock):
    with respx.mock(assert_all_called=False) as mock:
        _route(mock, side_effect=[Response(200, json={"verification_tier": 2}), Response(404),
                                  httpx.ConnectTimeout("down")])
        assert chain.resolve_verification_tier(AGENT, oracle_url=URL) == 2
        clock.t += 61
        assert chain.resolve_verification_tier(AGENT, oracle_url=URL) == 0
        clock.t += 61  # oracle now unreachable: the evicted value must not come back
        assert chain.resolve_verification_tier(AGENT, oracle_url=URL) == 0
