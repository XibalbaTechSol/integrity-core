"""XNS availability client: a thin reader of the Oracle's dual-namespace check."""
import json
from unittest import mock

import pytest
import requests

from integrity_sdk.xns import HandleAvailability, XnsAvailabilityError, check_handle_availability

URL = "https://oracle.example/"


def resp(status: int, body=None, text: str = ""):
    r = mock.Mock()
    r.status_code = status
    r.text = text or json.dumps(body or {})
    r.json.side_effect = None
    if body is not None:
        r.json.return_value = body
    else:
        r.json.side_effect = ValueError("no json")
    return r


def body(**over):
    b = {
        "handle": "atlas",
        "available": True,
        "valid": True,
        "directory_available": True,
        "onchain": "free",
        "suggestions": [],
    }
    b.update(over)
    return b


def check(payload, status=200):
    with mock.patch("integrity_sdk.xns.requests.get", return_value=resp(status, payload)) as get:
        result = check_handle_availability(URL, "atlas")
    return result, get


def test_free_in_both_namespaces():
    r, get = check(body())
    assert r == HandleAvailability("atlas", True, True, True, "free", ())
    assert r.taken_by is None and not r.unverified
    assert get.call_args.args[0] == "https://oracle.example/v1/xns/available/atlas"


@pytest.mark.parametrize(
    "directory, onchain, taken_by",
    [(False, "free", "directory"), (True, "taken", "onchain"), (False, "taken", "both")],
)
def test_reports_which_namespace_holds_it(directory, onchain, taken_by):
    r, _ = check(body(available=False, directory_available=directory, onchain=onchain, suggestions=["atlas1"]))
    assert not r.available
    assert r.taken_by == taken_by
    assert r.suggestions == ("atlas1",)


def test_unverified_is_not_taken():
    r, _ = check(body(available=False, onchain="unverified"))
    assert not r.available and r.unverified and r.taken_by is None


def test_malformed_handle_is_an_answer_not_an_error():
    r, _ = check(body(handle="A!", available=False, valid=False, directory_available=None, onchain=None))
    assert not r.valid and not r.available and r.onchain is None


def test_handle_is_url_encoded():
    with mock.patch("integrity_sdk.xns.requests.get", return_value=resp(200, body(handle="a/b"))) as get:
        check_handle_availability(URL, "a/b")
    assert get.call_args.args[0].endswith("/v1/xns/available/a%2Fb")


def test_legacy_oracle_without_namespace_fields_is_never_upgraded_to_free():
    r, _ = check({"handle": "atlas", "available": False, "suggestions": []})
    assert not r.available and r.directory_available is None and r.onchain is None


def test_unknown_onchain_status_is_rejected():
    with pytest.raises(XnsAvailabilityError, match="malformed"):
        check(body(onchain="maybe"))


def test_http_error_and_unreachable():
    with pytest.raises(XnsAvailabilityError) as e:
        check(None, status=502)
    assert e.value.status == 502
    with mock.patch("integrity_sdk.xns.requests.get", side_effect=requests.ConnectionError("down")):
        with pytest.raises(XnsAvailabilityError) as e:
            check_handle_availability(URL, "atlas")
    assert e.value.status is None
