"""
Semantic conventions for span/metric attribute names, aligned with
OpenTelemetry's GenAI semantic conventions where applicable so traces from
this SDK are legible in any standard OTel backend, plus Integrity-specific
extensions for compliance/behavioral attributes.
"""


class GenAIAttributes:
    SYSTEM = "gen_ai.system"
    AGENT_NAME = "gen_ai.agent.name"
    OPERATION_NAME = "gen_ai.operation.name"
    REQUEST_MODEL = "gen_ai.request.model"
    RESPONSE_MODEL = "gen_ai.response.model"
    INPUT_TOKENS = "gen_ai.usage.input_tokens"
    OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
    # L1 token taxonomy (docs/design/sdk-data-collection-strategy.md). These classes price
    # and behave differently from fresh input, so collapsing them into INPUT_TOKENS misstates
    # both cost and effort:
    #
    #   * cache read/creation — Anthropic reports these IN ADDITION to input_tokens, so they
    #     are additive. OpenAI's prompt_tokens_details.cached_tokens is a SUBSET of
    #     prompt_tokens and is NOT. See spec/token-accounting/vectors.json.
    #   * reasoning — extended thinking / o-series. A subset of output tokens.
    CACHE_READ_TOKENS = "gen_ai.usage.cache_read_input_tokens"
    CACHE_CREATION_TOKENS = "gen_ai.usage.cache_creation_input_tokens"
    REASONING_TOKENS = "gen_ai.usage.reasoning_tokens"
    # Provider-reported cost. `sacrifice` currently uses a token proxy precisely because no
    # verified cost figure was available at this layer; where a provider or runtime reports
    # one, record it rather than re-deriving it from a price table that would drift.
    COST_USD = "gen_ai.usage.cost_usd"
    STOP_REASON = "gen_ai.response.stop_reason"
    FINISH_REASONS = "gen_ai.response.finish_reasons"
    PROMPT = "gen_ai.content.prompt"
    COMPLETION = "gen_ai.content.completion"


class IntegrityAttributes:
    ENTROPY = "integrity.behavior.entropy"
    GROUNDING = "integrity.behavior.grounding"

    STORAGE_FLUX_RW_RATIO = "integrity.host.storage_flux.rw_ratio"
    ACCESS_PATH_ENTROPY = "integrity.host.storage_flux.path_entropy"
    DESTINATION_IP_ENTROPY = "integrity.host.network.ip_entropy"

    COMPLIANCE_HIPAA_ELIGIBLE = "integrity.compliance.hipaa_eligible"
    COMPLIANCE_ZDR_ENABLED = "integrity.compliance.zdr_enabled"
    COMPLIANCE_EXTERNAL_WEB_ACCESS = "integrity.compliance.external_web_access"
    COMPLIANCE_DATA_RESIDENCY_REGION = "integrity.compliance.data_residency_region"
    COMPLIANCE_API_DOMAIN_PREFIX = "integrity.compliance.api_domain_prefix"
    COMPLIANCE_EKM_PROVIDER = "integrity.compliance.ekm_provider"

class EconomicAttributes:
    BCC_INTENT_HASH = "bcc.intent_hash"
    BCC_RESOLUTION_STATUS = "bcc.resolution_status"
    MARKETS_TRADE_YIELD = "markets.trade_yield"
    ITK_BALANCE_DELTA = "itk.balance_delta"
    SYNERGY_DELEGATION_TARGET = "synergy.delegation_target"
    SYNERGY_DELEGATION_SUCCESS = "synergy.delegation_success"


def get_gen_ai_span_name(system: str, model: str) -> str:
    return f"{system} {model} inference"


class AOSAttributes:
    """
    Agent Observability Standard (AOS / OWASP AOS) semantic conventions.

    These extend the OTel GenAI conventions with agent-specific attributes
    that bind the agent's reasoning (agent.thought) to execution telemetry,
    following the AOS spec at aos.owasp.org.
    """
    # The latent Chain-of-Thought monologue for the current action (AOS §1.2)
    AGENT_THOUGHT = "agent.thought"
    # sha256 hex of agent.thought — for tamper detection without exposing the full text
    AGENT_THOUGHT_HASH = "agent.thought_hash"
    # Unique identifier for the agent run (top-level session span)
    RUN_ID = "agent.run_id"
    # Current phase: "planning" | "execution" | "reflection"
    PHASE = "agent.phase"
    # The tool/API being invoked in an atomic action span
    TOOL_NAME = "tool.name"
    # The outcome of the tool call
    TOOL_RESULT = "tool.result"
    # Aggregated token count for this entire action (prompt + completion)
    TOKEN_COUNT_TOTAL = "gen_ai.usage.token_count_total"
    # The BCC intent_type this action is associated with
    BCC_INTENT_TYPE = "bcc.intent_type"
    # AOS compliance gate decision: "allow" | "deny"
    BCC_DECISION = "bcc.decision"
    # AOS violation reason code (e.g. "AOS_VIOLATION", "TOKEN_BUDGET_EXCEEDED")
    BCC_VIOLATION_CODE = "bcc.violation_code"

