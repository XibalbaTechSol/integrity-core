"""Integrity SDK.

Public names are resolved lazily (PEP 562 module ``__getattr__``,
https://peps.python.org/pep-0562/). Importing the package, or any submodule
such as ``integrity_sdk.did`` or ``integrity_sdk.core``, therefore does not
pull in the network/chain/telemetry stack (requests, web3, eth-account,
OpenTelemetry, MLflow) -- each name below is imported only on first access.

This is what lets xibalba-shield and xibalba-cortex depend on the SDK core
without inheriting the connector dependencies (docs/EXECUTION_PLAN.md, A2),
and it is what lets modules scheduled for removal (A1) leave without breaking
``import integrity_sdk``. ``tests/unit/test_import_hygiene.py`` guards both.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

# Public name -> (submodule, attribute). The submodule is imported on first access.
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "IntegrityClient": (".client", "IntegrityClient"),
    "IntegrityAgent": (".agent_runtime", "IntegrityAgent"),
    "AgentIdentityError": (".agent_runtime", "AgentIdentityError"),
    "AgentNotRegisteredError": (".agent_runtime", "AgentNotRegisteredError"),
    "IntegrityHookAdapter": (".harness_hooks", "IntegrityHookAdapter"),
    "normalize_hook": (".harness_hooks", "normalize_hook"),
    "enable_auto_hooks": (".integrations.auto_hook", "enable_auto_hooks"),
    "integrity": (".integrity", "integrity"),
    "SDKAgent": (".integrity", "SDKAgent"),
    "ReadinessCheck": (".readiness", "ReadinessCheck"),
    "RegistrationReadiness": (".readiness", "RegistrationReadiness"),
    "assess_local_readiness": (".readiness", "assess_local_readiness"),
    "migrate_identity_store": (".did", "migrate_identity_store"),
    "identity_history": (".identity_registry", "history"),
    "latest_identity": (".identity_registry", "latest"),
    "PrivacyPolicy": (".telemetry.privacy", "PrivacyPolicy"),
    "HttpTelemetryTransport": (".telemetry.transports", "HttpTelemetryTransport"),
    "OTLPHttpTransport": (".telemetry.transports", "OTLPHttpTransport"),
    "MCPTelemetryTransport": (".telemetry.transports", "MCPTelemetryTransport"),
}

__all__ = list(_LAZY_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _LAZY_EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    value = getattr(importlib.import_module(module_name, __name__), attribute)
    globals()[name] = value  # cache, so later lookups skip __getattr__
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


if TYPE_CHECKING:  # static analysers and IDEs see the real names
    from .agent_runtime import AgentIdentityError, AgentNotRegisteredError, IntegrityAgent
    from .client import IntegrityClient
    from .did import migrate_identity_store
    from .harness_hooks import IntegrityHookAdapter, normalize_hook
    from .identity_registry import history as identity_history, latest as latest_identity
    from .integrations.auto_hook import enable_auto_hooks
    from .integrity import SDKAgent, integrity
    from .readiness import ReadinessCheck, RegistrationReadiness, assess_local_readiness
    from .telemetry.privacy import PrivacyPolicy
    from .telemetry.transports import HttpTelemetryTransport, MCPTelemetryTransport, OTLPHttpTransport
