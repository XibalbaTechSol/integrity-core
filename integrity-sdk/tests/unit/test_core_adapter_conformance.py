import pytest

from integrity_sdk.core import AdapterConformanceError, run_adapter_conformance
from integrity_sdk.integrations.sample_adapter import adapt_event


def test_sample_third_party_adapter_passes_deterministic_conformance():
    result = run_adapter_conformance(adapt_event)
    assert result["schema_version"] == "integrity.adapter-event/1"
    assert result["payload_hash"].startswith("sha256:")
    assert "synthetic-search" not in str(result)


def test_conformance_rejects_nondeterministic_adapter():
    counter = iter(("one", "two"))

    def nondeterministic(_event):
        return {"value": next(counter)}

    with pytest.raises(AdapterConformanceError, match="not deterministic"):
        run_adapter_conformance(nondeterministic)
