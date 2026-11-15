"""`integrity xns available`: exit codes keep "unknown" (3) distinct from "taken" (1), "free" (0)
and Click's usage error (2)."""
from __future__ import annotations

import json
from unittest import mock

import pytest
from typer.testing import CliRunner

from integrity_cli.main import app
from integrity_sdk.xns import HandleAvailability, XnsAvailabilityError

runner = CliRunner()


def _invoke(result=None, error=None, *extra):
    target = "integrity_cli.main.check_handle_availability"
    kw = {"side_effect": error} if error else {"return_value": result}
    with mock.patch(target, **kw) as check:
        out = runner.invoke(app, ["xns", "available", "atlas", "--oracle-url", "http://oracle.test", *extra])
    return out, check


def avail(**over):
    base = dict(handle="atlas", available=True, valid=True, directory_available=True, onchain="free", suggestions=())
    base.update(over)
    return HandleAvailability(**base)


def test_available_exits_zero():
    out, check = _invoke(avail())
    assert out.exit_code == 0 and "Available" in out.output
    check.assert_called_once_with("http://oracle.test", "atlas")


@pytest.mark.parametrize("directory, onchain, where", [
    (False, "free", "Oracle directory"), (True, "taken", "on-chain XNS"), (False, "taken", "and on-chain XNS"),
])
def test_taken_exits_one_and_names_the_namespace(directory, onchain, where):
    out, _ = _invoke(avail(available=False, directory_available=directory, onchain=onchain, suggestions=("atlas1",)))
    assert out.exit_code == 1
    assert where in out.output and "atlas1" in out.output


def test_invalid_exits_one():
    out, _ = _invoke(avail(available=False, valid=False, directory_available=None, onchain=None))
    assert out.exit_code == 1 and "Invalid" in out.output


def test_unverified_exits_three_not_taken():
    out, _ = _invoke(avail(available=False, onchain="unverified"))
    assert out.exit_code == 3 and "Unverified" in out.output and "Taken" not in out.output


def test_oracle_unreachable_exits_three():
    out, _ = _invoke(error=XnsAvailabilityError(None, "connection refused"))
    assert out.exit_code == 3 and "unreachable" in out.output


def test_json_output():
    out, _ = _invoke(avail(available=False, onchain="taken", suggestions=("atlas1",)), None, "--json")
    assert out.exit_code == 1
    assert json.loads(out.output) == {
        "handle": "atlas", "available": False, "valid": True,
        "directory_available": True, "onchain": "taken", "suggestions": ["atlas1"],
    }


def test_usage_error_is_clicks_two_not_unverified():
    out = runner.invoke(app, ["xns", "available"])
    assert out.exit_code == 2
