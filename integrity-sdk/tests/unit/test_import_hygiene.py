"""Import hygiene: the SDK core must not drag in the connector stack.

docs/EXECUTION_PLAN.md A2: xibalba-shield and xibalba-cortex depend on the SDK
core (canonical bytes, DID/DID file, BCC signing, receipts, packs, hook
normalization) and must not inherit requests/web3/eth-account/OpenTelemetry/
MLflow through it. The package `__init__` is lazy (PEP 562), so this also
proves that modules scheduled for removal are not imported just because
`integrity_sdk` is.

Each check runs in a fresh interpreter: within this pytest process other tests
have already imported the heavy modules, so `sys.modules` here says nothing
about what a given import pulls in by itself.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

# The connector stack: must stay out of every core import below.
HEAVY = ("requests", "httpx", "web3", "eth_account", "eth_utils", "opentelemetry", "mlflow", "psutil", "cbor2")

# Modules that make up the dependency-light core; `normalize_hook` lives in harness_hooks.
CORE_MODULES = (
    "integrity_sdk",
    "integrity_sdk.core",
    "integrity_sdk.vault",
    "integrity_sdk.did",
    "integrity_sdk.bcc",
    "integrity_sdk.crypto.merkle",
    "integrity_sdk.harness_hooks",
)

# Modules A1 cuts. Importing the package must not load them.
SCHEDULED_FOR_REMOVAL = (
    "integrity_sdk.markets",
    "integrity_sdk.mcp_server",
    "integrity_sdk.integrity",
    "integrity_sdk.prover",
    "integrity_sdk.opa_client",
    "integrity_sdk.integrations.auto_hook",
)


def _modules_after_import(statement: str) -> set[str]:
    probe = f"import json, sys\n{statement}\nprint(json.dumps(sorted(sys.modules)))"
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True)
    return set(json.loads(result.stdout.strip().splitlines()[-1]))


def _heavy_roots(modules: set[str]) -> set[str]:
    return {name.split(".")[0] for name in modules} & set(HEAVY)


@pytest.mark.parametrize("module", CORE_MODULES)
def test_core_module_imports_no_connector_dependency(module):
    assert _heavy_roots(_modules_after_import(f"import {module}")) == set()


def test_package_import_loads_no_module_scheduled_for_removal():
    loaded = _modules_after_import("import integrity_sdk")
    assert loaded.isdisjoint(SCHEDULED_FOR_REMOVAL)


def test_lazy_exports_still_resolve():
    # The public surface is unchanged: every exported name resolves on access.
    import integrity_sdk

    for name in integrity_sdk.__all__:
        assert getattr(integrity_sdk, name) is not None, name


def test_normalize_hook_is_usable_without_the_connector_stack():
    loaded = _modules_after_import(
        "from integrity_sdk.harness_hooks import normalize_hook\n"
        "assert normalize_hook('PreToolUse', {'tool_name': 'Bash'})['tool_name'] == 'Bash'"
    )
    assert _heavy_roots(loaded) == set()
