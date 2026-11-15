"""One output contract for every v3 command: a JSON shape and an exit-code table.

`--json` emits exactly one JSON document on stdout, tagged
``"schema": "integrity.cli.<group>.<cmd>.v1"``; any human-readable text goes to stderr so a
pipe into `jq` never sees it. Without `--json`, human text goes to stdout as usual.

Exit codes, for every query command:

====  ========================================================================
0     yes / ok
1     a definite no: taken, invalid, not in the map, denied, frozen, mismatch
2     usage error (Click's own; never reused for anything else)
3     unverified / unreachable: Oracle down, RPC timeout, `onchain: unverified`
4     the chain refused a write (a revert)
====  ========================================================================

3 is deliberately not 1: "can't tell right now" is something a script retries, while "no" is an
answer. Folding them together is how an outage gets read as a refusal (or the reverse).
"""
from __future__ import annotations

import json
from typing import Any, NoReturn, Optional

import typer
from rich.console import Console

EXIT_OK = 0
EXIT_NO = 1
EXIT_USAGE = 2
EXIT_UNVERIFIED = 3
EXIT_REVERT = 4

JSON_OPTION_HELP = "Emit one machine-readable JSON document on stdout (human text goes to stderr)"


def schema_id(group: str, cmd: Optional[str] = None) -> str:
    return f"integrity.cli.{group}.{cmd}.v1" if cmd else f"integrity.cli.{group}.v1"


def dumps(doc: dict[str, Any]) -> str:
    # One line, sorted keys: stable for diffs, and Rich never wraps it.
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), default=str)


class Reporter:
    """Routes one command's output: human lines vs the single JSON result."""

    def __init__(self, group: str, cmd: Optional[str] = None, *, json_mode: bool = False):
        self.schema = schema_id(group, cmd)
        self.json_mode = json_mode
        # Built per call (not at import) so it binds whatever stdout/stderr is current.
        self.console = Console(stderr=json_mode, highlight=False, soft_wrap=True)

    def info(self, text: str) -> None:
        self.console.print(text)

    def result(self, data: dict[str, Any]) -> None:
        if self.json_mode:
            typer.echo(dumps({"schema": self.schema, **data}))

    def fail(self, exit_code: int, detail: str, *, code: Optional[str] = None, **data: Any) -> NoReturn:
        self.info(f"[bold red]Error:[/bold red] {detail}")
        if self.json_mode:
            error = {"code": code, "detail": detail} if code else {"detail": detail}
            typer.echo(dumps({"schema": self.schema, "ok": False, "error": error, **data}))
        raise typer.Exit(exit_code)


def exit_code_for_chain_error(exc: BaseException) -> int:
    """4 for a revert, 3 when the node could not be reached or answered, else 1."""
    from web3.exceptions import ContractCustomError, ContractLogicError, TimeExhausted

    if isinstance(exc, (ContractLogicError, ContractCustomError)):
        return EXIT_REVERT
    if isinstance(exc, (TimeExhausted, TimeoutError, ConnectionError)):
        return EXIT_UNVERIFIED
    try:
        import requests

        if isinstance(exc, requests.RequestException):
            return EXIT_UNVERIFIED
    except ImportError:  # pragma: no cover -- web3 depends on requests
        pass
    return EXIT_NO
