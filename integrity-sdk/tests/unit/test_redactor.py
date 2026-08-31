from integrity_sdk.security.redactor import Redactor, classify_metadata, redact_text


def test_clean_text_untouched():
    result = redact_text("The weather in Austin is 72 degrees today.")
    assert result.text == "The weather in Austin is 72 degrees today."
    assert result.categories_found == []
    assert not result.had_redactions


def test_redacts_ssn():
    result = redact_text("Patient SSN is 123-45-6789 on file.")
    assert "123-45-6789" not in result.text
    assert "[REDACTED:SSN]" in result.text
    assert result.categories_found == ["SSN"]


def test_redacts_email():
    result = redact_text("Contact jane.doe@example.com for follow-up.")
    assert "jane.doe@example.com" not in result.text
    assert "[REDACTED:EMAIL]" in result.text


def test_redacts_phone():
    result = redact_text("Call the patient at (512) 555-0182 tomorrow.")
    assert "512" not in result.text or "[REDACTED:PHONE]" in result.text
    assert "[REDACTED:PHONE]" in result.text


def test_redacts_credit_card():
    result = redact_text("Card on file: 4111 1111 1111 1111.")
    assert "4111 1111 1111 1111" not in result.text
    assert "[REDACTED:CREDIT_CARD]" in result.text


def test_redacts_openai_api_key():
    key = "sk-" + "a" * 40
    result = redact_text(f"My key is {key} don't share it.")
    assert key not in result.text
    assert "[REDACTED:API_KEY]" in result.text


def test_redacts_aws_access_key():
    result = redact_text("AKIAABCDEFGHIJKLMNOP is our access key id.")
    assert "AKIAABCDEFGHIJKLMNOP" not in result.text
    assert "[REDACTED:API_KEY]" in result.text


def test_redacts_bearer_token():
    result = redact_text("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig")
    assert "eyJhbGciOiJIUzI1NiJ9" not in result.text
    assert "[REDACTED:API_KEY]" in result.text


def test_redacts_private_key_block():
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIB...redacted...\n-----END RSA PRIVATE KEY-----"
    result = redact_text(f"here is the key: {pem}")
    assert "MIIB" not in result.text
    assert "[REDACTED:PRIVATE_KEY]" in result.text


def test_redacts_mrn():
    result = redact_text("MRN: A123456 confirmed for admission.")
    assert "A123456" not in result.text
    assert "[REDACTED:MRN]" in result.text


def test_multiple_categories_in_one_string():
    result = redact_text("Email jane@example.com or SSN 123-45-6789 for verification.")
    assert set(result.categories_found) == {"EMAIL", "SSN"}


def test_empty_string_is_noop():
    result = redact_text("")
    assert result.text == ""
    assert not result.had_redactions


def test_redactor_instance_is_reusable_and_stateless():
    r = Redactor()
    first = r.redact("SSN 123-45-6789")
    second = r.redact("clean text, no secrets here")
    assert first.had_redactions
    assert not second.had_redactions


def test_classify_metadata_with_nothing_supplied_is_low_risk():
    result = classify_metadata()
    assert result.categories == []
    assert result.risk_level == "low"


def test_classify_metadata_flags_secret_paths_as_critical():
    result = classify_metadata(file_paths=["/home/user/.ssh/id_rsa"])
    assert "secret" in result.categories
    assert result.risk_level == "critical"


def test_classify_metadata_flags_phi_data_sources_as_high():
    result = classify_metadata(data_sources=["clinical_notes_db"])
    assert "phi" in result.categories
    assert result.risk_level == "high"


def test_classify_metadata_flags_external_endpoints_as_medium():
    result = classify_metadata(model_endpoint="https://api.openai.com/v1/chat/completions")
    assert "external_model" in result.categories
    assert result.risk_level == "medium"


def test_classify_metadata_takes_the_highest_risk_across_matches():
    result = classify_metadata(
        file_paths=["/secrets/api_key.pem"],
        model_endpoint="https://api.example.com",
    )
    assert {"secret", "external_model"} <= set(result.categories)
    assert result.risk_level == "critical"  # secret's severity, not external_model's


def test_classify_metadata_preserves_explicitly_supplied_categories():
    result = classify_metadata(supplied_categories=["custom_tag"])
    assert result.categories == ["custom_tag"]
    assert result.risk_level == "low"  # supplied categories don't imply a risk bump on their own


def test_classify_metadata_glob_matching_is_case_insensitive():
    result = classify_metadata(file_paths=["/Home/User/.SSH/ID_RSA"])
    assert "secret" in result.categories
