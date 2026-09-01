#!/usr/bin/env python3
"""
Comprehensive dashboard-audit seeder for integrity-oracle's Postgres.

Goal: populate every DB-backed data source the integrity-dashboard reads so a human
can do a full UI audit — every panel showing realistic *historical* and *live* data —
using the 5 real, already-registered testnet identities under ~/.integrity.

Honesty framing (this is a LABELED TEST HARNESS, not a product mock):
  * It reuses REAL registered agent identities (real DIDs, real Ed25519 keys, real
    on-chain primitive addresses read from each agent's keystore) — nothing fabricated
    about *who* the agents are.
  * It writes backdated rows directly per the migration schema so deep multi-week
    history exists instantly. This is the user-approved "hybrid" path: real ingestion
    (see demo/main.py) covers live signed telemetry; this backfill covers the history
    that real-time ingestion cannot produce. Every row is clearly attributable to these
    5 test DIDs and the whole set is idempotently re-seedable.
  * It does NOT touch chain state. Chain-direct dashboard reads (stake, credit, BAAs,
    owned contracts, wallet balance) are intentionally out of scope for this pass and
    read Base Sepolia live.

Run (needs the oracle Postgres up — `make up` or the compose `postgres` service on :5436):

    cd integrity-dashboard/demo && uv run integrity-seed-audit
    # or point at a different DB:
    DATABASE_URL=postgres://integrity:integrity_dev_only@localhost:5436/integrity \
        uv run integrity-seed-audit
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import psycopg
from cryptography.hazmat.primitives import serialization

DEFAULT_DATABASE_URL = "postgres://integrity:integrity_dev_only@localhost:5436/integrity"
HOME = Path.home()
N_DAYS = 30  # AIS reporting window; history spans this so scores + history views fill.
CHAIN_ID = int(os.getenv("CHAIN_ID", "84532"))

# bytes32 domain ids from deployments.baseSepolia.json (general / healthcare verticals).
DOMAIN_GENERAL = "0x595cceb222da8b2d14f13ddd254b38c4c99285925da5d4f854461514dad57e00"
DOMAIN_HEALTHCARE = "0x83064d690f7098fe67923a009c2f7ee6651571d8fbf9071c0c0a340c1ebf63a7"


@dataclass
class Profile:
    """Shapes the seeded telemetry so each agent lands at a distinct, believable AIS.

    AIS math (integrity-oracle/scoring-core): entropy=exp(-1.5*var^2)*1000,
    grounding=hgi*1000, sacrifice=(log10(sum_gpu+1)/3)*1000, compliance=(1-flag_ratio)*1000,
    AIS=(0.3E+0.3G+0.2S+0.2C)*zk_boost.
    """
    variance: tuple[float, float]
    hgi: tuple[float, float]
    gpu: tuple[float, float]
    flag_rate: float
    zk: bool
    events: int          # telemetry events over the window
    block_rate: float     # fraction of BCC audit decisions that are BLOCK


PROFILES: dict[str, Profile] = {
    "stellar":   Profile((0.03, 0.12), (0.93, 0.98), (10, 18), 0.00, True, 150, 0.03),
    "compliant": Profile((0.08, 0.18), (0.88, 0.95), (7, 14), 0.00, True, 140, 0.02),
    "steady":    Profile((0.30, 0.45), (0.70, 0.80), (3, 7), 0.04, True, 110, 0.10),
    "volatile":  Profile((0.55, 0.80), (0.55, 0.68), (1, 4), 0.15, False, 90, 0.22),
    "reckless":  Profile((1.05, 1.55), (0.28, 0.42), (0.05, 0.6), 0.42, False, 60, 0.45),
}


@dataclass
class Agent:
    name: str              # descriptive display name
    keystore: str          # keystore dir under ~/.integrity
    vertical: int          # 0 general, 1 healthcare
    profile: str
    # populated from the keystore
    did: str = ""
    pubkey: bytes = b""
    eth_address: str = ""
    primitives: dict = field(default_factory=dict)


# The 5 audit agents — real registered identities, curated for a full behavior + vertical
# spectrum (high→low AIS, plus a healthcare agent for the Integrity Health panels).
AGENTS: list[Agent] = [
    Agent("Atlas Trading",     "did/trading_agent",             0, "stellar"),
    Agent("Sentinel Health",   "did/healthcare_agent",          1, "compliant"),
    Agent("Meridian Capital",  "did/capital_allocation_agent",  0, "steady"),
    Agent("Oracle Forecast",   "did/prediction_market_agent",   0, "volatile"),
    Agent("Rogue Reckless",    "demo-fleet/did/reckless-beta",  0, "reckless"),
]

INTENT_TYPES = ["data_write", "trade_execution", "clinical_access", "capital_release",
                "market_entry", "model_inference", "system_call"]
JUDGE_MODELS = ["claude-opus-4-8", "claude-sonnet-5", "gpt-4o", "gemini-2.5-pro"]
SPAN_NAMES = ["plan.intent", "tool.retrieve", "tool.execute", "bcc.commit",
              "policy.evaluate", "telemetry.emit", "chain.anchor"]


def _rand32() -> bytes:
    return random.randbytes(32)


def _hexbytes(n: int) -> str:
    return "0x" + random.randbytes(n).hex()


def load_identity(agent: Agent) -> bool:
    """Populate did/pubkey/eth_address/primitives from the agent's real keystore."""
    base = HOME / ".integrity" / agent.keystore
    prim_f, doc_f, key_f = base / "primitives.json", base / "document.json", base / "private_key.pem"
    if not (prim_f.exists() and key_f.exists()):
        print(f"  ! keystore missing for {agent.name} at {base} — skipping", file=sys.stderr)
        return False
    prim = json.loads(prim_f.read_text())
    agent.did = prim["did"]
    agent.eth_address = prim.get("evm_address", "")
    agent.primitives = prim
    # Real Ed25519 public key (32 raw bytes) derived from the agent's private key.
    priv = serialization.load_pem_private_key(key_f.read_bytes(), password=None)
    agent.pubkey = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    # Sanity: the DID fingerprint is sha256(pubkey) — verify we loaded the right key.
    fp = hashlib.sha256(agent.pubkey).hexdigest()
    if not agent.did.endswith(fp):
        print(f"  ! WARNING: {agent.name} pubkey fingerprint {fp[:12]}… != DID — using anyway", file=sys.stderr)
    _ = doc_f  # document.json is the DID doc; we synthesize a minimal one below.
    return True


# ────────────────────────── identity tables ──────────────────────────

def seed_identity(cur, a: Agent, chain_id: int = CHAIN_ID) -> None:
    did_doc = {
        "id": a.did,
        "controller": a.did,
        "verificationMethod": [{
            "id": f"{a.did}#key-1",
            "type": "Ed25519VerificationKey2020",
            "publicKeyHex": a.pubkey.hex(),
        }],
        "alsoKnownAs": [a.name],
    }
    cur.execute(
        """
        INSERT INTO agents (id, ed25519_pubkey, eth_address, verification_tier, last_nonce, created_at, did_document)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            ed25519_pubkey = EXCLUDED.ed25519_pubkey,
            eth_address = EXCLUDED.eth_address,
            verification_tier = EXCLUDED.verification_tier,
            did_document = EXCLUDED.did_document
        """,
        (a.did, a.pubkey, a.eth_address, 2 if a.vertical == 1 else 1,
         PROFILES[a.profile].events,
         datetime.now(timezone.utc) - timedelta(days=N_DAYS + 5),
         json.dumps(did_doc)),
    )
    p = a.primitives
    cur.execute(
        """
        INSERT INTO agent_primitives (agent_id, sovereign_agent_address, state_anchor_address,
            reputation_registry_address, slasher_address, verifier_registry_address,
            compliance_gate_address, agent_profile_address, controller_address, domain_id,
            chain_id, resolved_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
        ON CONFLICT (agent_id) DO UPDATE SET
            sovereign_agent_address = EXCLUDED.sovereign_agent_address,
            slasher_address = EXCLUDED.slasher_address,
            compliance_gate_address = EXCLUDED.compliance_gate_address,
            agent_profile_address = EXCLUDED.agent_profile_address,
            domain_id = EXCLUDED.domain_id,
            chain_id = EXCLUDED.chain_id
        """,
        (a.did, p["sovereign_agent"], p["state_anchor"], p["reputation_registry"],
         p["slasher"], p["verifier_registry"], p["compliance_gate"], p["agent_profile"],
         a.eth_address or p["sovereign_agent"],
         DOMAIN_HEALTHCARE if a.vertical == 1 else DOMAIN_GENERAL, chain_id),
    )


def purge(cur, dids: list[str], chain_id: int = CHAIN_ID) -> None:
    """Idempotency: drop this run's prior seeded rows for these DIDs (labeled test data)."""
    cur.execute("DELETE FROM judge_evaluations WHERE agent_id = ANY(%s)", (dids,))
    cur.execute("DELETE FROM telemetry_events WHERE agent_id = ANY(%s)", (dids,))
    cur.execute("DELETE FROM otel_spans WHERE agent_id = ANY(%s)", (dids,))
    cur.execute("DELETE FROM audit_log WHERE agent_id = ANY(%s)", (dids,))
    cur.execute("DELETE FROM anchor_events WHERE agent_id = ANY(%s)", (dids,))
    cur.execute(
        "DELETE FROM leaderboard_cache WHERE agent_id = ANY(%s) AND chain_id = %s",
        (dids, chain_id),
    )


# ────────────────────────── time-series backfill ──────────────────────────

def seed_telemetry(cur, a: Agent) -> list[tuple[str, datetime]]:
    """Insert the agent's telemetry_events (+ a daily merkle_root) across N_DAYS.

    Returns [(event_id, created_at)] for later judge_evaluations linkage.
    """
    prof = PROFILES[a.profile]
    now = datetime.now(timezone.utc)
    per_day = max(1, prof.events // N_DAYS)
    nonce = 0
    made: list[tuple[str, datetime]] = []
    for day in range(N_DAYS, -1, -1):
        day_start = now - timedelta(days=day)
        root_id = str(uuid.uuid4())
        leaves = []
        day_events = []
        count = per_day + random.randint(-1, 2)
        for _ in range(max(1, count)):
            nonce += 1
            ts = day_start + timedelta(minutes=random.randint(0, 1439))
            if ts > now:
                ts = now
            variance = round(random.uniform(*prof.variance), 4)
            hgi = round(random.uniform(*prof.hgi), 4)
            gpu = round(random.uniform(*prof.gpu), 3)
            flagged = random.random() < prof.flag_rate
            zk = prof.zk and random.random() < 0.7
            leaf = _rand32()
            leaves.append(leaf)
            eid = str(uuid.uuid4())
            payload = {
                "intent_type": random.choice(INTENT_TYPES),
                "batch_size": random.randint(1, 12),
                "avg_entropy": round(1.0 - min(variance, 1.0), 4),
                "avg_grounding": hgi,
                "region": random.choice(["us-east-1", "eu-central-1", "ap-northeast-1"]),
                "model": random.choice(JUDGE_MODELS),
            }
            day_events.append((eid, a.did, nonce, variance, hgi, gpu, flagged, zk, leaf,
                               json.dumps(payload), root_id, len(leaves) - 1, ts))
            made.append((eid, ts))
        # One anchored merkle root per day covering that day's leaves.
        root_hash = hashlib.sha256(b"".join(leaves)).digest()
        cur.execute(
            "INSERT INTO merkle_roots (id, root_hash, leaf_count, tx_hash, created_at) VALUES (%s,%s,%s,%s,%s)",
            (root_id, root_hash, len(leaves), _hexbytes(32), day_start),
        )
        cur.executemany(
            """INSERT INTO telemetry_events
               (id, agent_id, nonce, performance_variance, hgi_raw, gpu_hours_verified,
                flagged, zk_verified, leaf_hash, payload, merkle_root_id, leaf_index, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            day_events,
        )
    cur.execute("UPDATE agents SET last_nonce = %s WHERE id = %s", (nonce, a.did))
    return made


def seed_traces(cur, a: Agent) -> None:
    """OTel traces: ~1 trace/day, each a small root+children span tree."""
    now = datetime.now(timezone.utc)
    rows = []
    for day in range(N_DAYS, -1, -1):
        if random.random() < 0.15:
            continue
        start = now - timedelta(days=day, minutes=random.randint(0, 1400))
        trace_id = random.randbytes(16).hex()
        root_span = random.randbytes(8).hex()
        n_spans = random.randint(3, 7)
        spans = [(root_span, None, "agent.run")]
        for _ in range(n_spans - 1):
            spans.append((random.randbytes(8).hex(), root_span, random.choice(SPAN_NAMES)))
        cursor = start
        for span_id, parent, name in spans:
            dur = timedelta(milliseconds=random.randint(20, 900))
            status = "ERROR" if (a.profile in ("volatile", "reckless") and random.random() < 0.18) else "OK"
            rows.append((str(uuid.uuid4()), a.did, trace_id, span_id, parent, name,
                         "INTERNAL" if parent else "SERVER", cursor, cursor + dur, status,
                         json.dumps({"integrity.agent.id": a.did, "component": name.split(".")[0],
                                     "duration_ms": int(dur.total_seconds() * 1000)}), cursor))
            cursor = cursor + dur
    cur.executemany(
        """INSERT INTO otel_spans
           (id, agent_id, trace_id, span_id, parent_span_id, name, kind, start_time, end_time,
            status_code, attributes, created_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )


def seed_audit(cur, a: Agent) -> None:
    """BCC/compliance decisions -> audit_log (Integrity Health interactions + audit page)."""
    prof = PROFILES[a.profile]
    now = datetime.now(timezone.utc)
    n = random.randint(30, 55)
    rows = []
    for _ in range(n):
        ts = now - timedelta(days=random.uniform(0, N_DAYS), minutes=random.randint(0, 1439))
        block = random.random() < prof.block_rate
        intent = random.choice(INTENT_TYPES)
        decision = "BLOCK" if block else "PASS"
        reason = random.choice(["policy_ok", "within_scope", "bcc_verified"]) if not block \
            else random.choice(["phi_scope_violation", "missing_baa", "intent_mismatch", "rate_limit"])
        detail = (f"{'Denied' if block else 'Permitted'} {intent} for {a.name} "
                  f"({'HIPAA gate' if a.vertical == 1 else 'policy gate'})")
        rows.append((str(uuid.uuid4()), a.did, "bcc-middleware", intent, decision, reason,
                     detail, intent, json.dumps({"agent": a.name}), ts))
    cur.executemany(
        """INSERT INTO audit_log (id, agent_id, source, event_type, decision, reason_code,
            detail, intent_type, metadata, created_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )


def seed_anchors(cur, a: Agent) -> None:
    """StateAnchor root anchoring events -> provenance/diagnostics panel."""
    now = datetime.now(timezone.utc)
    rows = []
    for i in range(random.randint(12, 22)):
        ts = now - timedelta(days=random.uniform(0, N_DAYS))
        rows.append((str(uuid.uuid4()), a.did, _hexbytes(32), _hexbytes(32), _hexbytes(32), ts))
    cur.executemany(
        "INSERT INTO anchor_events (id, agent_id, leaf, root, tx_hash, anchored_at) VALUES (%s,%s,%s,%s,%s,%s)",
        rows,
    )


def seed_judge(cur, a: Agent, events: list[tuple[str, datetime]]) -> None:
    """LLM-as-judge evaluations attached to some telemetry events."""
    prof = PROFILES[a.profile]
    sample = random.sample(events, min(len(events), random.randint(12, 24)))
    rows = []
    for eid, ts in sample:
        good = random.random() > (prof.flag_rate + 0.1)
        score = round(random.uniform(0.75, 0.99) if good else random.uniform(0.2, 0.55), 3)
        rows.append((str(uuid.uuid4()), a.did, f"run-{uuid.uuid4().hex[:8]}",
                     random.choice(JUDGE_MODELS), "PASS" if good else "FLAG", score,
                     ("Behavior consistent with committed intent."
                      if good else "Deviation between intent and execution context."),
                     eid, ts))
    cur.executemany(
        """INSERT INTO judge_evaluations (id, agent_id, run_id, judge_model, verdict, score,
            rationale_summary, telemetry_event_id, created_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )


def compute_ais(a: Agent) -> int:
    """Approximate the scoring-core AIS from the profile centers (for leaderboard_cache)."""
    import math
    p = PROFILES[a.profile]
    var = sum(p.variance) / 2
    hgi = sum(p.hgi) / 2
    gpu_sum = (sum(p.gpu) / 2) * p.events
    e = math.exp(-1.5 * var * var) * 1000
    g = min(hgi, 1.0) * 1000
    s = min(math.log10(gpu_sum + 1) / 3, 1.0) * 1000
    c = (1 - min(p.flag_rate, 1.0)) * 1000
    base = 0.3 * e + 0.3 * g + 0.2 * s + 0.2 * c
    return int(base * (1.15 if p.zk else 1.0))


def seed_leaderboard(cur, agents: list[Agent], chain_id: int = CHAIN_ID) -> None:
    for a in agents:
        cur.execute(
            """INSERT INTO leaderboard_cache
                   (agent_id, chain_id, sovereign_agent_address, effective_score, refreshed_at)
               VALUES (%s,%s,%s,%s, now())
               ON CONFLICT (agent_id, chain_id) DO UPDATE SET
                   sovereign_agent_address = EXCLUDED.sovereign_agent_address,
                   effective_score = EXCLUDED.effective_score,
                   refreshed_at = now()""",
            (a.did, chain_id, a.primitives["sovereign_agent"], str(compute_ais(a))),
        )
    cur.execute(
        """INSERT INTO leaderboard_sync (id, chain_id, agent_count, synced_at)
           VALUES (TRUE, %s, %s, now())
           ON CONFLICT (chain_id) DO UPDATE SET
               agent_count = EXCLUDED.agent_count,
               synced_at = now()""",
        (chain_id, len(agents)),
    )


def seed_markets(cur, agents: list[Agent]) -> None:
    """markets_cache: agent-owned prediction markets (read by GET /v1/markets). A pure cache
    table, so seeding it directly is the intended fill path; index_sync is marked fresh so the
    list endpoint serves these without a chain re-enumeration."""
    now_s = int(datetime.now(timezone.utc).timestamp())
    questions = [
        ("Will BTC close above $120k by Friday?", 2, False),
        ("Which model wins the Q3 grounding benchmark?", 4, False),
        ("Will the Fed cut rates at the next meeting?", 2, True),
        ("Will this agent's AIS stay above 800 for 30 days?", 2, False),
        ("Top-performing vertical this quarter?", 3, True),
        ("Will BidderX default on its capital allocation?", 2, False),
    ]
    n = 0
    for i, (q, outcomes, resolved) in enumerate(questions):
        creator = agents[i % len(agents)]
        addr = "0x" + hashlib.sha256(f"market-{i}-{creator.did}".encode()).hexdigest()[:40]
        total = random.randint(500, 25000) * 10**18
        splits = [random.random() for _ in range(outcomes)]
        ssum = sum(splits) or 1.0
        outcome_staked = [str(int(total * s / ssum)) for s in splits]
        cur.execute(
            """INSERT INTO markets_cache (address, creator_address, question, outcome_count,
                min_ais_to_enter, resolve_deadline, resolved, winning_outcome, total_staked,
                outcome_staked, refreshed_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
               ON CONFLICT (address) DO UPDATE SET total_staked = EXCLUDED.total_staked,
                 resolved = EXCLUDED.resolved, outcome_staked = EXCLUDED.outcome_staked""",
            (addr, creator.primitives["sovereign_agent"].lower(), q, outcomes,
             str(random.choice([0, 300, 500, 700]) * 10**0),
             now_s + (random.randint(-5, 20) * 86400), resolved,
             random.randint(0, outcomes - 1) if resolved else 0, str(total),
             json.dumps(outcome_staked)),
        )
        n += 1
    cur.execute(
        """INSERT INTO markets_index_sync (id, market_count, synced_at) VALUES (TRUE, %s, now())
           ON CONFLICT (id) DO UPDATE SET market_count = EXCLUDED.market_count, synced_at = now()""",
        (n,),
    )


def main() -> None:
    random.seed(20260725)  # deterministic, reproducible seed set
    db_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    print("── Integrity dashboard AUDIT SEED (labeled test data) ──")
    print(f"   DB: {db_url.rsplit('@', 1)[-1]}")

    loaded = [a for a in AGENTS if load_identity(a)]
    if not loaded:
        print("No identities loaded — is ~/.integrity/did populated?", file=sys.stderr)
        sys.exit(1)
    print(f"   Agents: {', '.join(f'{a.name}({a.profile}, AIS~{compute_ais(a)})' for a in loaded)}")

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            dids = [a.did for a in loaded]
            purge(cur, dids)
            for a in loaded:
                seed_identity(cur, a)
                events = seed_telemetry(cur, a)
                seed_traces(cur, a)
                seed_audit(cur, a)
                seed_anchors(cur, a)
                seed_judge(cur, a, events)
                print(f"   ✓ {a.name}: {len(events)} telemetry events + traces/audit/anchors/judge")
            seed_leaderboard(cur, loaded)
            seed_markets(cur, loaded)
        conn.commit()

    # Summary counts.
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        for tbl in ("agents", "telemetry_events", "otel_spans", "audit_log", "anchor_events",
                    "judge_evaluations", "leaderboard_cache", "markets_cache"):
            cur.execute(f"SELECT count(*) FROM {tbl}")
            print(f"   {tbl:20s} {cur.fetchone()[0]}")
    print("── done. Point the dashboard's oracle at this DB to audit historical + live data. ──")


if __name__ == "__main__":
    main()
