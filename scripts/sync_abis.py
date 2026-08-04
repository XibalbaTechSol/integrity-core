#!/usr/bin/env python3
"""
Extracts {abi, bytecode} for the contracts integrity-sdk's chain.py needs to
deploy directly or call, out of Foundry's `contracts/out/*.sol/*.json` build
artifacts, and writes trimmed JSON files into
integrity-sdk/integrity_sdk/abis/.

Run via `make sync-abis` from the repo root (that target runs `forge build`
first so this always reads fresh artifacts). This is a one-way, run-when-
contracts-change sync step, not a runtime dependency — integrity-sdk never
reads contracts/out/ directly, only these trimmed copies, so the SDK package
stays installable/usable without a Foundry toolchain present.

Also writes the identical trimmed JSON into integrity-cli/integrity_cli/abis/
-- integrity-cli's chain.py needs the exact same {abi, bytecode} artifacts
to deploy/call the same contracts, but per identity.py's "no sibling
dependency on integrity-sdk" philosophy the CLI carries its own copy rather
than importing integrity_sdk.abis. Single source of truth stays
contracts/out/; this script is what keeps both packages' copies in sync
rather than hand-copying whenever contracts change.

Does NOT write frontend ABIs/deployments. It used to, into a directory named
`integrity-mvp/` — the predecessor of today's `integrity-dashboard/` — but
that target was never renamed when the frontend was, so every `make
sync-abis` run silently regenerated a dead, untracked directory nothing
consumed. `integrity-dashboard` maintains its own ABI copies by hand
(`src/components/abi/*.json`, same trimmed-abi-array shape this script
produces) and its own deployments mirror (`src/deployments.baseSepolia.json`,
a curated singletons-only subset, NOT a raw copy of the root file — copying
this script's full deployments.*.json over it would silently drop that
curation). Re-add a real dashboard sync step deliberately, if one is wanted,
rather than resurrecting the stale path.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_OUT = REPO_ROOT / "contracts" / "out"
SDK_ABIS_DIR = REPO_ROOT / "integrity-sdk" / "integrity_sdk" / "abis"
CLI_ABIS_DIR = REPO_ROOT / "integrity-cli" / "integrity_cli" / "abis"

# (contract name, source file stem) — Foundry nests artifacts as
# out/<SourceFile>.sol/<ContractName>.json; every contract here happens to
# share its name with its source file stem, but this table stays explicit
# rather than assuming that always holds.
CONTRACTS = [
    ("SovereignAgent", "SovereignAgent"),
    ("StateAnchor", "StateAnchor"),
    ("AgentPrimitivesFactory", "AgentPrimitivesFactory"),
    # IntegrityToken: only `mint` is used (the funder wallet, holding
    # MINTER_ROLE, allocates each freshly-registered agent some testnet ITK
    # stake collateral — see registration.py). Not deployed by the SDK itself,
    # just called.
    ("IntegrityToken", "IntegrityToken"),
    # Market/application layer (see integrity_sdk/markets.py): MarketFactory
    # is called to deploy+own a market; IntegrityMarket's ABI is needed to
    # call the resulting clone's enterPosition/resolve/claimPayout (its
    # address is only known at runtime, so the SDK reads this same ABI
    # against whatever clone address MarketFactory.deployMarket returned);
    # A2ACapitalPool is a fixed-address singleton.
    ("MarketFactory", "MarketFactory"),
    ("IntegrityMarket", "IntegrityMarket"),
    ("A2ACapitalPool", "A2ACapitalPool"),
    # Integrity Health vertical (added for integrity-dashboard/demo's Clinician-Delta
    # persona, which is the first consumer to call these from Python):
    # ComplianceGate.setSelfDeclaredCompliance/isHealthcareCompliant,
    # CoveredEntityRegistry.registerEntity (REGISTRAR_ROLE, held by the funder/
    # governance address on the single-operator testnet deploy), and the real
    # BAA lifecycle (SmartBAAFactory.createBAA -> SmartBAA.sign).
    ("ComplianceGate", "ComplianceGate"),
    ("CoveredEntityRegistry", "CoveredEntityRegistry"),
    ("SmartBAAFactory", "SmartBAAFactory"),
    ("SmartBAA", "SmartBAA"),
    # EHRGate: the actual PHI-access enforcement contract (ComplianceGate does NOT
    # replace it, see EHRGate.sol's own NatSpec) — was missing from this list despite
    # being real, deployed (Deploy.s.sol), and needed by integrity-dashboard/demo's
    # Clinician-Delta persona for grantAccess/checkAccess/verifyAndLogAccess
    # (PRODUCTION_GAPS.md Sec3).
    ("EHRGate", "EHRGate"),
    # XibalbaNameService (XNS, added 2026-07-11): self-service handle
    # registration/resolution — see contracts/src/framework/
    # XibalbaNameService.sol's NatSpec. Needed by both packages' new `xns`
    # CLI/SDK commands to call register/resolve/setPrimaryHandle/release.
    ("XibalbaNameService", "XibalbaNameService"),
    # XibalbaAgentRegistry: not called directly by the SDK/CLI's own
    # transaction-building today (they resolve DIDs off-chain via the
    # oracle), but integrity-dashboard's frontend reads resolveAgent(sovereignAgent)
    # directly on-chain (e.g. to confirm a connected wallet's EOA is the
    # `controller` of the agent it's about to act as) — added for that.
    ("XibalbaAgentRegistry", "XibalbaAgentRegistry"),
]


def main() -> None:
    for abis_dir, package_name in ((SDK_ABIS_DIR, "integrity-sdk"), (CLI_ABIS_DIR, "integrity-cli")):
        abis_dir.mkdir(parents=True, exist_ok=True)
        (abis_dir / "__init__.py").write_text(
            f'"""Trimmed {{abi, bytecode}} JSON for contracts {package_name} deploys/calls '
            'directly. Synced from contracts/out/ via `make sync-abis` — do not hand-edit."""\n'
        )

    for contract_name, source_stem in CONTRACTS:
        artifact_path = CONTRACTS_OUT / f"{source_stem}.sol" / f"{contract_name}.json"
        if not artifact_path.exists():
            raise SystemExit(
                f"Missing forge artifact: {artifact_path} — run `forge build` in "
                f"contracts/ first (make sync-abis does this automatically)."
            )
        artifact = json.loads(artifact_path.read_text())

        trimmed = {
            "contractName": contract_name,
            "abi": artifact["abi"],
            "bytecode": artifact["bytecode"]["object"],
        }

        for abis_dir in (SDK_ABIS_DIR, CLI_ABIS_DIR):
            out_path = abis_dir / f"{contract_name}.json"
            out_path.write_text(json.dumps(trimmed, indent=2) + "\n")
            print(f"wrote {out_path.relative_to(REPO_ROOT)} ({len(trimmed['abi'])} ABI entries)")


if __name__ == "__main__":
    main()
