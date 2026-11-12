"""AIS control-zone gate: restrict a tool call by the agent's control zone.

The oracle computes an Agent Integrity Score and, from it, a control zone (`green` / `yellow` / `red`,
`GET /v1/agent/{id}/ais` -> `closed_loop_reward.control_zone`). This module is the table that turns
that zone into "which kinds of action may this agent take right now". It is pure: no I/O, no settings
object, no clock. Reading the zone is `app.chain.resolve_control_zone`; deciding what to do with a
restriction (deny, or only record it) is `app.main` step 5a.

Two tables, both deliberately here and not imported from `integrity-sdk`:

* **intent type -> action class** (`classify`). An exact-match map. Anything not in the map is
  `execute`, the most restricted ordinary class. There is no prefix, suffix or case-insensitive
  matching, because every one of those is a way for a label nobody reviewed to be treated as a read.
  In particular `claude_tool:Read:credential` (the hook appended a risk class) is NOT
  `claude_tool:Read`, and `hermes_tool:Read` is not either.
* **zone -> permitted action classes** (`permits`). green: read, draft, execute. yellow: read, draft.
  red: read. `escalate` (asking a human) is permitted in every zone: a demoted agent must always be
  able to hand the decision to a person.

What this module does NOT do: it does not compute a score or a zone. The SDK's
`ClosedLoopAISController.step()` recomputes AIS with its own weights; calling it here would give the
gate a second, different opinion about the same agent. The oracle's zone is the only input.

Precondition for turning the gate on in `enforce` (see README "AIS control-zone gate"): the oracle
caps AIS by registration tier (ceilings 300 / 600 / 850 / 1000 for tiers 0-3) while red is below 750
and green starts at 900. A tier 0 or tier 1 agent therefore cannot leave red, and a tier 2 agent
cannot reach green. That is why the default mode is `off`.
"""

from __future__ import annotations

from typing import Mapping

READ = "read"
DRAFT = "draft"
EXECUTE = "execute"
ESCALATE = "escalate"
ACTION_CLASSES = (READ, DRAFT, EXECUTE, ESCALATE)

GREEN = "green"
YELLOW = "yellow"
RED = "red"
#: The oracle's exact vocabulary (integrity-oracle scoring-core). Anything else is "unavailable".
ZONES = (GREEN, YELLOW, RED)

MODE_OFF = "off"
MODE_SHADOW = "shadow"
MODE_ENFORCE = "enforce"
MODES = (MODE_OFF, MODE_SHADOW, MODE_ENFORCE)

UNAVAILABLE_ALLOW = "allow"
UNAVAILABLE_RESTRICT = "restrict"
UNAVAILABLE_POSTURES = (UNAVAILABLE_ALLOW, UNAVAILABLE_RESTRICT)

#: Reason code of a zone denial, on the response, the audit row and the receipt.
REASON_AIS_ZONE_RESTRICTED = "AIS_ZONE_RESTRICTED"

#: What an intent type classifies as when it is not in the map.
DEFAULT_ACTION_CLASS = EXECUTE

#: Shipped map for the Claude Code hook's `claude_tool:<ToolName>` labels. Small on purpose: a tool is
#: listed only when its class is not in doubt. WebFetch / WebSearch / Task and every MCP tool are left
#: out and so classify as `execute` (they reach outside the workspace). `BCC_AIS_ZONE_ACTION_CLASSES`
#: adds to or overrides this.
DEFAULT_ACTION_CLASSES: dict[str, str] = {
    "claude_tool:Read": READ,
    "claude_tool:Glob": READ,
    "claude_tool:Grep": READ,
    "claude_tool:LS": READ,
    "claude_tool:NotebookRead": READ,
    "claude_tool:Write": DRAFT,
    "claude_tool:Edit": DRAFT,
    "claude_tool:MultiEdit": DRAFT,
    "claude_tool:NotebookEdit": DRAFT,
    "claude_tool:TodoWrite": DRAFT,
    "claude_tool:Bash": EXECUTE,
    "claude_tool:AskUserQuestion": ESCALATE,
}

_ZONE_PERMITS: dict[str, frozenset[str]] = {
    GREEN: frozenset({READ, DRAFT, EXECUTE}),
    YELLOW: frozenset({READ, DRAFT}),
    RED: frozenset({READ}),
}
_ALWAYS_PERMITTED = frozenset({ESCALATE})

#: Classes every zone permits. For these the zone cannot change the decision, so `app.main` does not
#: ask the oracle for it at all. Derived from the table so the two cannot drift apart.
PERMITTED_IN_EVERY_ZONE: frozenset[str] = _ALWAYS_PERMITTED | frozenset.intersection(*_ZONE_PERMITS.values())


def classify(intent_type: str, action_classes: Mapping[str, str]) -> str:
    """The action class of `intent_type`: its exact entry in `action_classes`, else `execute`."""
    return action_classes.get(intent_type, DEFAULT_ACTION_CLASS)


def permitted_classes(zone: str | None) -> frozenset[str]:
    """What `zone` permits. A zone outside the vocabulary gets only what every zone permits: turning
    "could not read the zone" into a posture is `restriction`'s job (it knows the configured posture), and this
    function must never be where an unknown string becomes green."""
    return _ALWAYS_PERMITTED | _ZONE_PERMITS.get(zone, PERMITTED_IN_EVERY_ZONE)  # type: ignore[arg-type]


def permits(zone: str | None, action_class: str) -> bool:
    return action_class in permitted_classes(zone)


def validate_action_classes(action_classes: object) -> dict[str, str]:
    """Check an intent-type -> action-class map. Raises ValueError naming the bad entry."""
    if not isinstance(action_classes, Mapping):
        raise ValueError("BCC_AIS_ZONE_ACTION_CLASSES must be a JSON object of intent_type -> action class")
    for intent_type, action_class in action_classes.items():
        if not isinstance(intent_type, str) or not intent_type:
            raise ValueError(f"BCC_AIS_ZONE_ACTION_CLASSES has a key that is not a non-empty string: {intent_type!r}")
        if action_class not in ACTION_CLASSES:
            raise ValueError(
                f"BCC_AIS_ZONE_ACTION_CLASSES maps {intent_type!r} to {action_class!r}; must be one of {', '.join(ACTION_CLASSES)}"
            )
    return dict(action_classes)


def restriction(*, zone: str | None, unavailable: str, intent_type: str, action_class: str) -> str | None:
    """The denial reason (`AIS_ZONE_RESTRICTED: ...`) if the zone does not permit this action, else None.

    `zone` is what `resolve_control_zone` answered: a zone, or None for "could not be read". None is
    permitted under the `allow` posture and treated as red under `restrict`; the reason then says
    "unavailable" so an operator can tell a demoted agent from an oracle that could not be reached.
    """
    if zone is None:
        if unavailable != UNAVAILABLE_RESTRICT:
            return None
        effective, described = RED, f"control zone unavailable, treated as {RED} (BCC_AIS_ZONE_UNAVAILABLE={UNAVAILABLE_RESTRICT})"
    else:
        effective, described = zone, f"control zone {zone}"
    allowed = permitted_classes(effective)
    if action_class in allowed:
        return None
    return (
        f"{REASON_AIS_ZONE_RESTRICTED}: {described} permits {', '.join(c for c in ACTION_CLASSES if c in allowed)}; "
        f"intent_type '{intent_type}' is class {action_class}"
    )
