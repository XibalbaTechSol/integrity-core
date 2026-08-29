from __future__ import annotations

import json

import pytest

from integrity_sdk.chain import DeploymentsFileMissing, load_deployments


def test_load_deployments_success(tmp_path):
    data = {"some": "deployments"}
    path = tmp_path / "deployments.local.json"
    path.write_text(json.dumps(data))

    result = load_deployments(str(path))
    assert result == data


def test_load_deployments_missing(tmp_path):
    missing_path = tmp_path / "nonexistent.json"
    with pytest.raises(DeploymentsFileMissing, match="does not exist — run `forge script"):
        load_deployments(str(missing_path))
