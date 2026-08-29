"""
Redactor & Classifier — targeted PII/PHI/secret masking and metadata classification,
applied client-side before any prompt/completion text leaves the agent's process.

Design note (this is the corrected design, not the SDK's original plan):
an earlier draft of this component was going to be a blanket "never
transmit any raw span content" rule. That was wrong. Xibalba Solutions'
prior `OBSERVABILITY_VTL.md` spec already names this exact component and
specifies TARGETED masking instead: oracle-side LLM-as-judge evaluation
(see `client.submit_judge_evaluation`, pending) needs structurally-intact,
if-redacted trace content to actually judge reasoning/tool-use shape — a
blanket hash would make that impossible. So this module finds and masks
specific categories of sensitive content, leaving the rest of the text
untouched.

Honest scope: this is regex/heuristic-based masking, not a certified PHI
de-identification system (e.g. it does not implement full HIPAA Safe
Harbor's 18-identifier removal, and it will miss PHI that doesn't match a
known pattern, like a patient's name mentioned in free text with no
structural marker). It is a real, working backstop for the common
high-confidence cases (SSNs, emails, phone numbers, credit card numbers,
API keys/secrets, private key material, MRN-style medical record numbers)
— not a silent stub, but also not a guarantee. `oracle`'s
`/v1/telemetry/ingest` defense-in-depth rejection (see
docs/INTERFACE_CONTRACT.md) is the second layer for exactly this reason:
this module can miss things, so the oracle independently refuses to store
anything carrying a recognized *unredacted* marker as a backstop.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from typing import List, Pattern, Tuple

# Each rule: (category name, compiled pattern). Order matters only in that
# more specific patterns should run before more general ones if they could
# overlap — checked case by case below, not currently an issue since these
# categories don't overlap in practice.
_RULES: List[Tuple[str, Pattern[str]]] = [
    # Private key material — PEM blocks (RSA/EC/OpenSSH/generic). Checked
    # first since a key block can otherwise get chewed up by narrower rules.
    ("PRIVATE_KEY", re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        re.DOTALL,
    )),
    # Common API key / secret token shapes: OpenAI-style sk-..., AWS access
    # key IDs, Bearer tokens, generic long hex/base64-ish secrets prefixed
    # by a recognizable label.
    ("API_KEY", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("API_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("API_KEY", re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]{20,}=*", re.IGNORECASE)),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("PHONE", re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    # Medical record number: no universal format, but "MRN"/"Medical Record
    # Number" followed by an alphanumeric identifier is a common convention
    # worth catching as a targeted, labeled case.
    ("MRN", re.compile(r"\b(?:MRN|Medical Record (?:Number|No\.?))[:\s#]*[A-Za-z0-9-]{4,}\b", re.IGNORECASE)),
]


@dataclass
class RedactionResult:
    text: str
    categories_found: List[str] = field(default_factory=list)

    @property
    def had_redactions(self) -> bool:
        return bool(self.categories_found)


class Redactor:
    """Applies the targeted masking rules above to a string, replacing each
    match with `[REDACTED:{CATEGORY}]`. Stateless and safe to reuse/share
    across calls."""

    def __init__(self, extra_rules: List[Tuple[str, Pattern[str]]] = None):
        self._rules = list(_RULES)
        if extra_rules:
            self._rules.extend(extra_rules)

    def redact(self, text: str) -> RedactionResult:
        if not text:
            return RedactionResult(text=text, categories_found=[])

        categories_found: List[str] = []

        def _replace(category: str):
            def _sub(match: re.Match) -> str:
                categories_found.append(category)
                return f"[REDACTED:{category}]"
            return _sub

        redacted = text
        for category, pattern in self._rules:
            redacted = pattern.sub(_replace(category), redacted)

        return RedactionResult(text=redacted, categories_found=categories_found)


_default_redactor = Redactor()


def redact_text(text: str) -> RedactionResult:
    """Module-level convenience using the default rule set — the entry
    point integrations (openai_integrity.py, langchain_callback.py) call
    before setting span attributes or logging telemetry metadata."""
    return _default_redactor.redact(text)


@dataclass(frozen=True)
class ClassificationRule:
    category: str
    severity: str = "medium"
    path_globs: tuple[str, ...] = ()
    data_source_globs: tuple[str, ...] = ()
    endpoint_globs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Classification:
    categories: list[str] = field(default_factory=list)
    risk_level: str = "low"


_RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


DEFAULT_CLASSIFICATION_RULES = (
    ClassificationRule("secret", "critical", path_globs=("*.pem", "*.key", "*/.ssh/*", "*/secrets/*")),
    ClassificationRule("phi", "high", data_source_globs=("*ehr*", "*clinical*", "*patient*")),
    ClassificationRule("regulated", "high", data_source_globs=("*pci*", "*financial*", "*payroll*")),
    ClassificationRule("external_model", "medium", endpoint_globs=("http://*", "https://*")),
)


def classify_metadata(
    *,
    supplied_categories: list[str] | tuple[str, ...] = (),
    file_paths: list[str] | tuple[str, ...] = (),
    data_sources: list[str] | tuple[str, ...] = (),
    model_endpoint: str = "",
    rules: tuple[ClassificationRule, ...] = DEFAULT_CLASSIFICATION_RULES,
) -> Classification:
    categories: set[str] = {category.strip().lower() for category in supplied_categories if category.strip()}
    risk = "low"

    for rule in rules:
        if _matches_any(file_paths, rule.path_globs) or _matches_any(data_sources, rule.data_source_globs):
            categories.add(rule.category)
            risk = _max_risk(risk, rule.severity)
        if model_endpoint and any(fnmatch.fnmatch(model_endpoint.lower(), pattern.lower()) for pattern in rule.endpoint_globs):
            categories.add(rule.category)
            risk = _max_risk(risk, rule.severity)

    return Classification(categories=sorted(categories), risk_level=risk)


def _matches_any(values: list[str] | tuple[str, ...], patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(value.lower(), pattern.lower()) for value in values for pattern in patterns)


def _max_risk(left: str, right: str) -> str:
    return left if _RISK_ORDER.get(left, 0) >= _RISK_ORDER.get(right, 0) else right
