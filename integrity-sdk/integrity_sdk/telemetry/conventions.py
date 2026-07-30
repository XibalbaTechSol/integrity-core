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


def get_gen_ai_span_name(system: str, model: str) -> str:
    return f"{system} {model} inference"
