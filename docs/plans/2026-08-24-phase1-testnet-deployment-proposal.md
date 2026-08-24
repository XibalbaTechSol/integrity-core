# Phase I kernel testnet deployment — go/no-go proposal

**Status:** proposal only. Nothing in this document is authorized. Workstream 4 of completing
whitepaper Phase I (`spec/integrity-protocol-v3.2.md` §10.3, Table 8), following workstream 1
(promotion, §40), workstream 2 (declared-asset conservation, accepted with a disclosed boundary,
§41), and workstream 3 (four properties machine-checked, §42-43). This is a real, external,
semi-irreversible action (a broadcast Base Sepolia transaction, using the real
`FUNDER_PRIVATE_KEY`) and is not something to execute without explicit authorization, independent
of this repo's own documentation discipline.

## What Table 8 actually asks for here

"Testnet deployment" is listed as one of Phase I's five deliverables (hook module, constraint
grammar, reference adapters, testnet deployment, published formal specification) — a component of
Phase I itself, not gated behind the Phase II transition (which requires audit + machine-checked
invariance, both separately tracked). Nothing in the whitepaper or this repo's own
`docs/MAINNET_READINESS.md` blocks TESTNET deployment on an audit — the "independent audit...
before any mainnet value is at risk" language (README, §9.3) is explicitly a mainnet gate. Testnet
ETH has no real value at risk, so proceeding here without an audit is defensible — but it is still
a real action worth deciding deliberately, not by default.

## A directly-relevant finding from workstream 3, carried forward

Building the Halmos harness required solving the exact circularity `IntegrityKernel`/
`IntegrityAccount` share: each contract's constructor needs the other's real, final address before
either exists. Two of three approaches tried there failed —
`docs/plans/2026-08-24-phase1-halmos-harness-proposal.md`'s own findings:

- **CREATE-nonce prediction failed specifically because Halmos doesn't model real RLP/nonce
  addressing** (confirmed by reading Halmos's own source). That limitation is Halmos-specific,
  not a real-EVM one — a genuine Foundry deploy script (`forge script`, not Halmos) computes
  `vm.computeCreateAddress(deployer, nonce)` correctly, exactly as `IntegrityAccountTest`'s own
  concrete `setUp()` already does successfully, every run, throughout this repo's existing test
  suite. **This means the harness's own workaround (Option B, placeholder-then-swap) is NOT
  needed for a real deploy script** — the simpler, original CREATE-nonce prediction pattern this
  repo's concrete tests already use is directly reusable here.
- **CREATE2 dual-prediction remains genuinely infeasible** regardless of tooling (a real
  mathematical fixed point, not a Halmos artifact) — not relevant to a CREATE-nonce-based deploy
  script anyway.

## Design questions this proposal surfaces, decides none of

**1. What does the deployed `IntegrityAccount` protect — a new agent, or nothing in particular?**
`IntegrityKernel`/`IntegrityAccount` are deliberately separate from the `PrimitiveSet`/
`XibalbaAgentRegistry` model `SovereignAgent`-based agents use (README: "the production
`SovereignAgent.execute()` still dispatches without any such gate"). A testnet deployment has no
natural "agent" to attach to — it would be a standalone reference instance, not integrated with
any existing registered agent's identity, reputation, or PrimitiveSet. Options: (a) deploy a bare
reference instance with its own fresh `ReputationRegistry` clone (mirrors exactly how the Halmos
harness and every concrete test already construct one — cheap, fully understood, zero
interaction with real agent state); (b) bind it to an EXISTING real agent's `ReputationRegistry`
(e.g. `xibalba.integrity`'s own) — more "real," but couples an experimental, unaudited artifact to
a live agent's actual reputation state, a bigger blast radius for no clearly named benefit at this
stage.

**2. Budget parameters.** The Foundry test suite's constants (`PER_OP_BUDGET = 1 ether`,
`CUMULATIVE_BUDGET = 3 ether`, `MIN_EFFECTIVE_SCORE = 500`, `REPUTATION_EPOCH_LENGTH = 3 days`)
are arbitrary test-scoped values, never chosen with any real economic reasoning. A testnet
instance could reuse them (cheap, already-understood, zero risk since it's testnet ETH) or use
different, more "production-shaped" values — no basis exists yet for the latter, so reuse is the
practical default unless there's a specific reason not to.

**3. Where does this live in the deploy pipeline?** Not folding this into `Deploy.s.sol` (which
deploys the entire production primitive-set + markets + governance stack in one broadcast,
already large and separately audited-by-use) — a dedicated `DeployKernelReference.s.sol`, run and
verified independently, matching the existing precedent of `DeployMarkets.s.sol`/
`DeployEHRGate.s.sol`/`DeployXnsGovernance.s.sol` as separate, incremental app-layer scripts
rather than one monolithic deploy.

**4. Naming/labeling on-chain.** Given this is explicitly experimental (un-audited, disclosed
Table 4 gas crossing accepted, narrow declared-asset-conservation scope), the deployment record
(`deployments.baseSepolia.json`, README, any public-facing material) must state plainly that this
is a Phase I reference instance, not a production-ready account type agents should actually use
to hold real value — matching this repo's own no-aspirational-current-tense discipline throughout.

## What this proposal recommends, precisely

**Authorize scoping and building a dedicated `DeployKernelReference.s.sol`** using CREATE-nonce
address prediction (the pattern already proven throughout this repo's concrete tests, now
confirmed viable for a real deploy script specifically because it's not constrained by Halmos),
deploying: a fresh `ReputationRegistry` clone (option 1a above — no coupling to a real agent),
`IntegrityKernel` and `IntegrityAccount` reusing the test suite's existing budget constants,
broadcast to Base Sepolia, with the deployment record explicitly labeled as an experimental Phase
I reference instance. Actual broadcast execution requires a SEPARATE, explicit authorization after
the script itself is written and dry-run (`forge script ... ` without `--broadcast` first,
matching this repo's own established deploy discipline) — this proposal covers scoping and
building the script only, not running it.

## Real risk, stated before any script is written

- **This is real money, even on testnet** — gas costs (small but nonzero) drawn from the funder
  wallet (`FAUCET_INFO.md`), and a public, permanent on-chain record under this project's real
  deployed-contract reputation. Mistakes here are visible and not privately correctable the way a
  local Foundry test's mistakes are.
- **No audit exists.** Deploying to testnet is explicitly lower-stakes than mainnet, but a
  testnet-deployed experimental account with real (if valueless) ETH could still be targeted,
  probed, or referenced by third parties as if it were more mature than it is — the labeling
  requirement above exists specifically to prevent that misreading.
- **The Table 4 gas crossing (§41) becomes concretely relevant here for the first time.**
  Everything before this was Foundry-test-only, where gas cost is a number, not a real bundler
  constraint. A live Base Sepolia deployment is the first point where ~41k `preCheck` gas (with
  `trackedToken` enabled) could actually affect real UserOp inclusion economics, if this instance
  is ever exercised through a real ERC-4337 bundler rather than a direct `vm.prank`-equivalent
  call. Worth deploying WITHOUT `trackedToken` enabled first (native-only, ~35.5k, safely under
  budget) to avoid conflating this deployment's own findings with that already-disclosed issue.

## Decision needed

1. **Authorize scoping and building `DeployKernelReference.s.sol`** as described (fresh
   `ReputationRegistry`, existing test budget constants, native-only `trackedToken` disabled) —
   broadcast execution still requires its own separate authorization after the script exists.
2. **Authorize with changes** — different design-question answers than the recommendation above.
3. **Not yet** — hold workstream 4 until workstream 5 (external audit) is at least scoped, in case
   an auditor's own requirements change what's worth deploying to testnet first.

This document does not authorize itself.

## Outcome (2026-08-24)

**Authorized (option 1, all four design-question calls confirmed as recommended) and built.**
`contracts/script/DeployKernelReference.s.sol` exists, compiles, and was verified via a local
dry run (anvil, chain 31337) -- NOT broadcast to Base Sepolia or any live network. Two real bugs
found and fixed by that dry run, neither visible from compilation alone: an off-by-one in the
CREATE-nonce address prediction (a separate broadcast transaction between the prediction read and
the kernel deployment wasn't counted, so the reputation score and the kernel's `boundAccount`
binding both targeted the wrong address), and a JSON re-serialization bug in the `domains` merge
helper (dot-path concatenation breaks on domain names that themselves contain a dot, inherited
uncritically from `DeployEHRGate.s.sol`'s own version of the same pattern, never previously
exercised because the real `domains` section was empty when that script was written). Post-fix,
`cast call` confirmed both directions of the account/kernel binding on the locally deployed
instance. Full write-up: `PRODUCTION_GAPS.md` §44.

**What remains, per this proposal's own scope:** actual broadcast to Base Sepolia is a separate,
not-yet-granted authorization -- real testnet ETH from the real funder key, a permanent public
record. This proposal's "Decision needed" only ever covered scoping and building the script.
