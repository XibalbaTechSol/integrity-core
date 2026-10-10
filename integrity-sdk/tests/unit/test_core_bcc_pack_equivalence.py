"""`packs/bcc` decides exactly like `bcc_middleware/policies/bcc.rego` (B2 stage 1).

bcc_middleware does not load the shared pack yet; it queries bcc.rego for `allow`, `violation` and
`requires_baa`. Moving it onto the signed-pack decision contract means re-expressing 11 rules, and a
re-expression is exactly where an authorization gate quietly changes behaviour. So both policies run
here, side by side, in two real OPA servers (never a mock: Shield's old test mocked OPA's reply, which
is how "no rule matched" came to mean deny unnoticed), over a deterministic corpus, and any
disagreement fails the build.

What "equivalent" means, stated so it cannot be quietly weakened:

1. **Same verdict.** `bcc.rego` allows iff `count(violation) == 0`; the pack permits iff it returns
   `permit`. Every corpus case must agree. This is the security property.
2. **A defined, independently derived reason.** The contract carries one reason code where bcc.rego
   carries a set of messages. The expected code is recomputed here from the *old policy's* messages
   (each message's prefix before the colon) and the priority table below, not read back from the pack.
3. **Equivalence is claimed on the gate's real input domain.** bcc_middleware always sends `agent_id`
   and `intent_type` (required, validated fields), so the equivalence cases all carry both. Requests
   *without* either are tested separately, because there the old policy and the pack differ on
   purpose: see `test_on_a_malformed_commitment_the_pack_denies_where_bcc_rego_fails_open`.
4. **The same clinical sets.** `requires_baa` moves out of the policy in stage 2, to a constant in
   the gate. The intent set and the static agent set are compared here so that constant can be pinned.

The corpus is every single-factor deviation from a normal request plus a seeded random sample of
combinations (a full cartesian product is hundreds of thousands of cases). The seed is fixed, so a
failure is reproducible, and a coverage guard fails the test if the corpus stops exercising a rule.
"""

from __future__ import annotations

import http.client
import json
import random
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from integrity_sdk.core import decision as d
from integrity_sdk.core import packs
from integrity_sdk.core.opa import OpaClient
from integrity_sdk.did import Keypair, public_key_multibase

OPA = shutil.which("opa") or (str(Path.home() / ".local/bin/opa") if (Path.home() / ".local/bin/opa").exists() else None)
pytestmark = pytest.mark.skipif(OPA is None, reason="opa binary not installed (scripts/install_toolchain.sh)")

ROOT = Path(__file__).parents[3]
BCC_REGO = ROOT / "bcc_middleware" / "policies" / "bcc.rego"
PACK_DIR = ROOT / "packs" / "bcc"
GOLDEN_PACK_HASH = "sha256:71e47b0430f489c68926f827a40b7a4c74e4989406f04b9be5c897f5118d4955"

#: The reporting order the pack must follow. Deliberately a second, hand-written copy of the table in
#: policy.rego: if the two ever differ, equivalence fails rather than one silently winning.
EXPECTED_PRIORITY = [
    "HIPAA_ACCESS_CONTROL_VIOLATION",
    "VERIFICATION_TIER_INSUFFICIENT",
    "TOOL_RISK_TIER_INSUFFICIENT",
    "HIPAA_TECHNICAL_SAFEGUARD_FAILURE",
    "POLICY_VIOLATION",
    "AOS_VIOLATION",
    "TOKEN_BUDGET_OPA",
]
#: Pairs of codes that cannot fire together by construction: the two clinical-intent rules key on an exact
#: set of intent types, none of which contains a suspicious word, an SSN shape or a tool prefix, and so
#: cannot also trip the pattern, safeguard, tool-risk or AOS rules. Asserted to never co-occur, so a
#: change to either policy that makes one reachable fails this table instead of leaving it stale.
_CLINICAL = ("HIPAA_ACCESS_CONTROL_VIOLATION", "VERIFICATION_TIER_INSUFFICIENT")
_NON_CLINICAL = ("TOOL_RISK_TIER_INSUFFICIENT", "HIPAA_TECHNICAL_SAFEGUARD_FAILURE", "POLICY_VIOLATION", "AOS_VIOLATION")
IMPOSSIBLE_PAIRS = {(a, b) for a in _CLINICAL for b in _NON_CLINICAL}
EXTRA_AGENT = "did:key:z6MkExtraClinicalAgent"
STATIC_AGENT = "did:integrity:agent_scribe_01"
UNLISTED_AGENT = "did:integrity:random_unlisted_agent"
ABSENT = object()  # the field is omitted from the request entirely

_BASE = {
    "agent_id": "did:integrity:some_generic_agent",
    "intent_type": "payment",
    "intended_state_hash": "0x" + "11" * 32,
    "nonce": 1,
    "timestamp": 1730000000000,
    "verification_tier": 1,
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
    "span_id": "00f067aa0ba902b7",
    "intent_rationale": "Verifiable public intent rationale validating agent compliance and intent.",
    "token_count": 0,
    "daily_token_spend": 0,
}

_FACTORS = {
    "agent_id": [STATIC_AGENT, UNLISTED_AGENT, EXTRA_AGENT, "did:integrity:some_generic_agent", ABSENT],
    "intent_type": [
        "payment", "EMR_WRITE", "DISPENSE_MEDICATION", "BILLING_SUBMISSION", "SECURE_EMR_WRITE",
        "CLINICAL_DATA_ACCESS", "claude_tool:Bash", "claude_tool:Bash:readonly", "claude_tool:Bash:destructive",
        "claude_tool:Read:credential", "hermes_tool:coinbase_trade:financial", "hermes_tool:x:privileged",
        "hermes_tool:x:chain_write", "claude_tool_bypass", "EXFILTRATE_records", "Backdoor_install",
        "telemetry_SPOOF", "note 123-45-6789", "emr_write", "", ABSENT,
        # Intent types that fire SEVERAL rules at once. Priority between two codes is only observable
        # when both fire, and the first version of this corpus had no input where POLICY_VIOLATION and
        # AOS_VIOLATION co-occurred, so swapping their order went unnoticed (found by mutation).
        "claude_tool:bypass_step", "hermes_tool:exfiltrate:destructive",
        "claude_tool:123-45-6789:credential", "backdoor 123-45-6789",
    ],
    "verification_tier": [ABSENT, 0, 1, 2, 3, -1, "1", None],
    "trace_id": [ABSENT, None, "", "abc123"],
    "span_id": [ABSENT, None, "", "def456"],
    "intent_rationale": [ABSENT, None, "", "too short", "123456789012345", "x" * 14, "a sufficiently long rationale"],
    "agent_thought": [ABSENT, "legacy agent thought that is long enough", ""],
    "token_count": [ABSENT, 0, 1, 5000, 99999, -5],
    "daily_token_spend": [ABSENT, 0, 9000, 95000, 999999],
}

_SAMPLE_SIZE = 2500
_SEED = 20261006


def _build(choice: dict) -> dict:
    case = dict(_BASE)
    for key, value in choice.items():
        if value is ABSENT:
            case.pop(key, None)
        else:
            case[key] = value
    case.setdefault("agent_thought", ABSENT)
    if case["agent_thought"] is ABSENT:
        del case["agent_thought"]
    return case


def _corpus() -> list[dict]:
    cases = [dict(_BASE)]
    for key, values in _FACTORS.items():
        for value in values:
            cases.append(_build({key: value}))
    rng = random.Random(_SEED)
    for _ in range(_SAMPLE_SIZE):
        cases.append(_build({key: rng.choice(values) for key, values in _FACTORS.items()}))
    unique, seen = [], set()
    for case in cases:
        fingerprint = json.dumps(case, sort_keys=True, default=str)
        if fingerprint not in seen:
            seen.add(fingerprint)
            unique.append(case)
    return unique


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _Server:
    """A real `opa run --server`, with a persistent connection for the thousands of queries."""

    def __init__(self, *args: str):
        self.port = _free_port()
        self.process = subprocess.Popen(
            [OPA, "run", "--server", "--addr", f"127.0.0.1:{self.port}", "--log-level", "error", *args],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self.url = f"http://127.0.0.1:{self.port}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + 15
        while True:
            try:
                opener.open(self.url + "/health", timeout=1).close()
                break
            except OSError:
                if time.monotonic() > deadline:
                    self.stop()
                    raise
                time.sleep(0.1)
        self._conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)

    def query(self, path: str, payload: dict | None = None) -> dict:
        body = json.dumps({"input": payload} if payload is not None else {}).encode()
        self._conn.request("POST", "/v1/data/" + path, body, {"Content-Type": "application/json"})
        response = self._conn.getresponse()
        data = response.read()
        assert response.status == 200, data
        return json.loads(data)

    def stop(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()


@pytest.fixture(scope="module")
def old_policy(tmp_path_factory):
    """bcc.rego exactly as bcc_middleware runs it, with its runtime allowlist as a data document."""
    data = tmp_path_factory.mktemp("bcc-data") / "data.json"
    data.write_text(json.dumps({"clinical_allowlist": {"agents": [EXTRA_AGENT]}}))
    server = _Server(str(BCC_REGO), str(data))
    yield server
    server.stop()


@pytest.fixture(scope="module")
def loaded_pack(tmp_path_factory):
    work = tmp_path_factory.mktemp("bcc-pack") / "bcc"
    shutil.copytree(PACK_DIR, work)
    signer = Keypair.generate()
    packs.sign_pack(work, signer)
    return packs.load_pack(work, trusted_signers=[public_key_multibase(signer.public_bytes())])


@pytest.fixture(scope="module")
def new_policy(loaded_pack):
    server = _Server()
    OpaClient(server.url).install(loaded_pack)
    yield server
    server.stop()


@pytest.fixture(scope="module")
def pack_client(new_policy, loaded_pack):
    client = OpaClient(new_policy.url)
    client.install(loaded_pack)
    return client


def _old(server: _Server, case: dict) -> tuple[bool, set[str], bool]:
    result = server.query("integrity/bcc", case)["result"]
    codes = {message.split(":", 1)[0] for message in result.get("violation", [])}
    return result["allow"], codes, result["requires_baa"]


def _new(client: OpaClient, loaded_pack, case: dict) -> d.Decision:
    raw = client.query(loaded_pack, {**case, "event_class": "agent.tool_call", "clinical_allowlist": [EXTRA_AGENT]})
    return d.resolve(
        "agent.tool_call", raw, event_defaults=loaded_pack.event_defaults, mode=d.ENFORCE, pack_hash=loaded_pack.pack_hash
    )


def _expected_reason(codes: set[str]) -> str:
    return next(code for code in EXPECTED_PRIORITY if code in codes)


# ---------------------------------------------------------------- the pack itself


def test_the_pack_compiles_and_its_hash_is_pinned():
    compiled = packs.compile_pack(PACK_DIR)
    assert compiled.manifest["name"] == "bcc"
    assert set(compiled.manifest["event_classes"]) == {"agent.tool_call"}
    assert compiled.pack_hash == GOLDEN_PACK_HASH, "policy.rego/pack.yaml/controls.yaml changed: re-pin deliberately"


def test_every_control_the_pack_cites_is_declared_in_controls_yaml(loaded_pack, new_policy, pack_client):
    declared = {
        line.split(":", 1)[0] for line in loaded_pack.files["controls.yaml"].decode().splitlines()
        if line and not line.startswith((" ", "#"))
    }
    cited: set[str] = set()
    for case in _corpus()[:400]:
        cited.update(_new(pack_client, loaded_pack, case).controls)
    assert cited and cited <= declared


def test_an_event_class_the_pack_does_not_declare_denies(loaded_pack, pack_client):
    raw = pack_client.query(loaded_pack, {**_BASE, "event_class": "device.sensor"})
    decision = d.resolve("device.sensor", raw, event_defaults=loaded_pack.event_defaults, pack_hash=loaded_pack.pack_hash)
    assert (decision.decision, decision.reason_code) == (d.DENY, d.REASON_UNKNOWN_EVENT_CLASS)


def test_a_request_with_no_event_class_takes_the_no_match_default_deny(loaded_pack, pack_client):
    raw = pack_client.query(loaded_pack, dict(_BASE))  # no event_class: both decision rules are undefined
    decision = d.resolve("agent.tool_call", raw, event_defaults=loaded_pack.event_defaults, pack_hash=loaded_pack.pack_hash)
    assert (decision.decision, decision.reason_code) == (d.DENY, d.REASON_NO_MATCH)


# ------------------------------------------------------------------ equivalence


def test_the_pack_and_bcc_rego_agree_on_every_corpus_case(old_policy, new_policy, pack_client, loaded_pack):
    corpus = [case for case in _corpus() if "agent_id" in case and "intent_type" in case]
    assert len(corpus) > 1500
    disagreements: list[str] = []
    codes_seen: set[str] = set()
    pairs_seen: set[tuple[str, str]] = set()
    all_pairs = {(a, b) for i, a in enumerate(EXPECTED_PRIORITY) for b in EXPECTED_PRIORITY[i + 1:]}
    verdicts = {"permit": 0, "deny": 0}
    for case in corpus:
        allow, old_codes, _ = _old(old_policy, case)
        new = _new(pack_client, loaded_pack, case)
        codes_seen |= old_codes
        pairs_seen |= {pair for pair in all_pairs if set(pair) <= old_codes}
        verdicts[new.decision] += 1
        problems = []
        if allow != (new.decision == d.PERMIT):
            problems.append(f"verdict: bcc.rego allow={allow}, pack={new.decision}")
        if old_codes:
            if new.decision != d.DENY:
                problems.append(f"pack did not deny although {sorted(old_codes)} fired")
            elif new.reason_code != _expected_reason(old_codes):
                problems.append(f"reason: expected {_expected_reason(old_codes)}, pack said {new.reason_code}")
        elif new.reason_code != "BCC_POLICY_PERMIT":
            problems.append(f"permit reason was {new.reason_code}")
        if new.reason_code.startswith(d.RESERVED_REASON_PREFIX):
            problems.append(f"pack produced a reserved/gate-level reason code {new.reason_code}")
        if problems:
            disagreements.append(f"{json.dumps(case, sort_keys=True, default=str)} -> {'; '.join(problems)}")
    assert not disagreements, f"{len(disagreements)} disagreement(s); first 5:\n" + "\n".join(disagreements[:5])

    # Coverage guards: an equivalence proof over a corpus that never fires a rule proves nothing about it,
    # and the reporting order is only checked where two rules fire together.
    assert codes_seen == set(EXPECTED_PRIORITY), f"corpus never exercised: {set(EXPECTED_PRIORITY) - codes_seen}"
    assert verdicts["permit"] > 50 and verdicts["deny"] > 500, verdicts
    feasible = {pair for pair in all_pairs if pair not in IMPOSSIBLE_PAIRS}
    assert feasible <= pairs_seen, f"priority never exercised for: {sorted(feasible - pairs_seen)}"
    assert not (IMPOSSIBLE_PAIRS & pairs_seen), f"IMPOSSIBLE_PAIRS is stale, these co-occurred: {IMPOSSIBLE_PAIRS & pairs_seen}"


def test_on_a_malformed_commitment_the_pack_denies_where_bcc_rego_fails_open(old_policy, pack_client, loaded_pack):
    """FINDING, found by this harness. In Rego a rule that reads an absent field, or negates a
    membership test on one (`not input.agent_id in S` is undefined, not true), silently does not fire.
    So bcc.rego allows a commitment with no `agent_id` (its allowlist rule is inert, and its tier and
    tool-risk rules cannot build their `sprintf` message) and one with no `intent_type` (every rule keys
    on it). That cannot happen through bcc_middleware, which requires and validates both before calling
    OPA, so this is a policy-level weakness, not a live bypass. The pack denies instead.

    Pinned, not merely fixed: the old half of each assertion documents bcc.rego's current behaviour, so
    anyone who repairs bcc.rego gets a failing test telling them to delete this divergence.
    """
    leaks = [
        {"agent_id": ABSENT, "intent_type": "SECURE_EMR_WRITE", "verification_tier": 0},
        {"agent_id": ABSENT, "intent_type": "hermes_tool:x:privileged", "verification_tier": 0},
        {"agent_id": ABSENT, "intent_type": "EMR_WRITE", "verification_tier": 1},
        {"intent_type": ABSENT},
    ]
    for override in leaks:
        case = _build(override)
        old_allow, old_codes, _ = _old(old_policy, case)
        new = _new(pack_client, loaded_pack, case)
        assert old_allow is True and not old_codes, f"bcc.rego no longer fails open for {override}: remove this divergence"
        assert (new.decision, new.reason_code) == (d.DENY, "BCC_MALFORMED_COMMITMENT"), override

    # The general property over every malformed corpus case: wherever bcc.rego denies, so does the pack,
    # and every such case is denied for the right reason.
    stricter = 0
    for case in (c for c in _corpus() if "agent_id" not in c or "intent_type" not in c):
        old_allow, _, _ = _old(old_policy, case)
        new = _new(pack_client, loaded_pack, case)
        assert (new.decision, new.reason_code) == (d.DENY, "BCC_MALFORMED_COMMITMENT"), case
        stricter += old_allow
    assert stricter > 0


def test_a_non_string_identity_field_is_malformed_too(pack_client, loaded_pack):
    for override in ({"agent_id": None}, {"agent_id": 7}, {"intent_type": None}, {"intent_type": ["EMR_WRITE"]}):
        new = _new(pack_client, loaded_pack, _build(override))
        assert (new.decision, new.reason_code) == (d.DENY, "BCC_MALFORMED_COMMITMENT"), override


def test_every_violation_prefix_in_bcc_rego_is_a_ranked_code():
    """A new `violation` rule added to bcc.rego without a rank here would be unreportable by the pack."""
    import re

    source = BCC_REGO.read_text()
    prefixes = set(re.findall(r'msg\s*:=\s*(?:sprintf\()?\s*"([A-Z_]+):', source))
    assert prefixes, "no violation message prefixes found: has bcc.rego's message format changed?"
    assert prefixes <= set(EXPECTED_PRIORITY), prefixes - set(EXPECTED_PRIORITY)


#: The five intent types that need an authorized agent, a verified tier and an active BAA. Stage 2 keeps
#: this set as a constant in bcc_middleware (the contract has no `requires_baa` output) and pins it to
#: this table, so a sixth type added to one place and not the other fails a test.
CLINICAL_INTENT_TYPES = {"EMR_WRITE", "DISPENSE_MEDICATION", "BILLING_SUBMISSION", "SECURE_EMR_WRITE", "CLINICAL_DATA_ACCESS"}


def test_the_clinical_intent_set_and_authorized_agents_match_by_behaviour(old_policy, pack_client, loaded_pack):
    """The pack's sets are private rules, so compare them through what they do: for every intent type
    in the corpus, an unlisted agent is denied for access control, and `requires_baa` is set, in
    exactly the clinical set; and each kind of authorized agent passes in both policies."""
    for intent in _FACTORS["intent_type"]:
        if intent is ABSENT:
            continue
        unlisted = _build({"intent_type": intent, "agent_id": UNLISTED_AGENT})
        _, old_codes, requires_baa = _old(old_policy, unlisted)
        new = _new(pack_client, loaded_pack, unlisted)
        clinical = intent in CLINICAL_INTENT_TYPES
        assert requires_baa is clinical, intent
        assert ("HIPAA_ACCESS_CONTROL_VIOLATION" in old_codes) is clinical, intent
        assert (new.reason_code == "HIPAA_ACCESS_CONTROL_VIOLATION") is clinical, intent
    for agent in (STATIC_AGENT, "did:integrity:agent_billing_v1", "did:integrity:guardian_admin", EXTRA_AGENT):
        for intent in CLINICAL_INTENT_TYPES:
            authorized = _build({"intent_type": intent, "agent_id": agent})
            assert _old(old_policy, authorized)[0] is True, (agent, intent)
            assert _new(pack_client, loaded_pack, authorized).decision == d.PERMIT, (agent, intent)
