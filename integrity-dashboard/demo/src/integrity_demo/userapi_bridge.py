"""
Best-effort completion callback into integrity-userapi's `demo_runs` bookkeeping
table (`PATCH /demo/runs/{id}`).

This engine has no concept of a logged-in dashboard user or session -- it's an
operator-run scenario script (`make demo`), not something the frontend can
launch directly. The bridge is therefore opt-in via three environment
variables the *operator* sets when they want this specific invocation tied
back to a `demo_runs` row that was already created (e.g. by a prior
`POST /demo/run` call, made with the operator's own bearer token, before
kicking off this script):

    USERAPI_URL    -- e.g. http://localhost:8090
    USERAPI_TOKEN  -- a bearer JWT (or a `uak_...` developer API key) for the
                      SAME user who owns the run being updated
    USERAPI_RUN_ID -- the demo_runs.id returned by that POST /demo/run call

If any of the three is unset, every function here is a no-op -- this keeps
running the demo standalone (the common case, e.g. local dev with no
userapi running at all) exactly as before this bridge existed. If all three
ARE set, callback failures (userapi unreachable, run_id not found, token
expired) are logged and swallowed, never raised -- reporting status is
strictly secondary to the demo run itself actually happening.
"""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger("integrity_demo.userapi_bridge")


def _config() -> tuple[str, str, str] | None:
    url = os.getenv("USERAPI_URL")
    token = os.getenv("USERAPI_TOKEN")
    run_id = os.getenv("USERAPI_RUN_ID")
    if not url or not token or not run_id:
        return None
    return url, token, run_id


def report_status(status: str, result_summary: dict | None = None) -> None:
    """status: one of 'running' / 'completed' / 'failed', matching
    integrity-userapi's DemoRunUpdateRequest. Best-effort: never raises."""
    config = _config()
    if config is None:
        return
    url, token, run_id = config

    # A bearer JWT and a `uak_...` API key are both valid credentials for
    # integrity-userapi (see its app/deps.py::get_current_user_id) but use
    # different headers -- auto-detect by prefix so the operator can supply
    # either without a separate env var to pick between them.
    headers = (
        {"X-API-Key": token} if token.startswith("uak_") else {"Authorization": f"Bearer {token}"}
    )

    try:
        resp = requests.patch(
            f"{url}/demo/runs/{run_id}",
            json={"status": status, "result_summary": result_summary},
            headers=headers,
            timeout=5.0,
        )
        resp.raise_for_status()
        logger.info(f"Reported demo run {run_id} status={status} to userapi")
    except requests.RequestException as exc:
        logger.warning(f"Could not report demo run {run_id} status={status} to userapi: {exc}")
