#!/usr/bin/env python3
"""Reports whether the AIS per-component floor gate's population graduation criterion
(docs/design/ais-floor-interim-decision-2026-09-05.md, criterion 1) is currently met.

Zero-dependency, stdlib only, deliberately independent of this repo's own packages -- same
convention as xibalba-cortex's scripts/verify_provenance_export.py -- so it stays runnable by
anyone with only a Python interpreter and a reachable oracle, not a full dev environment.

Checks ONLY criterion 1 (population: >= MIN_AGENTS distinct registered agents). Criterion 2
(a minimum shadow-observation window) is NOT checked here -- the oracle does not currently
expose a "how long has shadow telemetry been collected" endpoint, a real, disclosed gap in this
checker, not something silently assumed satisfied. Criterion 3 (explicit human sign-off) can
never be automated by design; this script only ever REPORTS readiness for that review, it never
grants it.

Usage:
    python3 scripts/check_ais_floor_graduation.py [--oracle-url URL] [--min-agents N]

Exit code 0 if criterion 1 is met, 1 if not met, 2 on a failure to reach the oracle at all.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_ORACLE_URL = "http://localhost:8080"
DEFAULT_MIN_AGENTS = 5


def fetch_agent_count(oracle_url: str, *, timeout: float = 5.0) -> int:
    url = f"{oracle_url.rstrip('/')}/v1/agents"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        body = json.loads(resp.read())
    if not isinstance(body, list):
        raise ValueError(f"unexpected response shape from {url}: expected a JSON array")
    return len(body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracle-url", default=DEFAULT_ORACLE_URL)
    parser.add_argument("--min-agents", type=int, default=DEFAULT_MIN_AGENTS)
    args = parser.parse_args(argv)

    try:
        agent_count = fetch_agent_count(args.oracle_url)
    except (urllib.error.URLError, ValueError, TimeoutError) as exc:
        print(json.dumps({"error": f"could not reach oracle at {args.oracle_url}: {exc}"}))
        return 2

    criterion_1_met = agent_count >= args.min_agents
    report = {
        "criterion_1_population": {
            "registered_agent_count": agent_count,
            "required": args.min_agents,
            "met": criterion_1_met,
        },
        "criterion_2_observation_window": {
            "checked": False,
            "reason": "oracle does not currently expose a shadow-telemetry-duration endpoint",
        },
        "criterion_3_human_signoff": {
            "checked": False,
            "reason": "never automated by design -- see docs/design/ais-floor-interim-decision-2026-09-05.md",
        },
        "overall_ready_for_review": criterion_1_met,
    }
    print(json.dumps(report, indent=2))
    return 0 if criterion_1_met else 1


if __name__ == "__main__":
    sys.exit(main())
