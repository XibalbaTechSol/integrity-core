---
title: Zero-Knowledge Proving Pipeline
acronyms: [ZKP]
created: 2026-07-07
updated: 2026-07-15
type: concept
tags: [cryptography]
confidence: high
source_files:
  - integrity-zkp/src/main.nr
  - integrity-zkp/README.md
  - integrity-zkp/Makefile
  - integrity-zkp/generated/UltraPlonkVerifier.sol
  - contracts/src/oracle/UltraPlonkVerifier.sol
  - contracts/src/oracle/IZkVerifier.sol
  - contracts/src/oracle/VerifierRegistry.sol
  - contracts/src/oracle/ReputationRegistry.sol
  - contracts/script/Deploy.s.sol
  - integrity_sdk/prover.py
  - integrity-sdk/circuits/poc_commitment/src/main.nr
  - integrity-oracle/backend/src/handlers.rs
  - integrity-oracle/backend/src/chain.rs
  - integrity-oracle/backend/src/db.rs
  - docs/INTERFACE_CONTRACT.md
---

**Correction to the previous version of this page**: it claimed the pipeline
was "real at every layer." That overclaimed. Every *individual* stage below
is real (no `assert(true)`, no hardcoded-`true` verifier) — but the stages
are not yet wired to each other end to end. Three concrete gaps, detailed in
§4-§6: the deployed on-chain verifier is a fail-closed placeholder, not the
real generated verifier; `integrity-sdk`'s prover targets a different,
stand-in circuit, not the one in `integrity-zkp`; and nothing in this repo
currently calls `ReputationRegistry.submitZkAttestation`. This is a large
improvement over the old prototype (which failed *open* — a mock verifier
that accepted any non-empty proof) but "real, not yet connected" is the
accurate description, not "real end to end."

## Table of contents

- [1. What Noir/Barretenberg are (context, not the point)](#1-what-noir-barretenberg-are-context-not-the-point)
- [2. What this repo's circuit actually proves](#2-what-this-repo-s-circuit-actually-proves)
- [3. The real build/prove/verify pipeline, as it exists in integrity-zkp/](#3-the-real-build-prove-verify-pipeline-as-it-exists-in-integrity-zkp)
- [4. How the pieces are (and are not yet) wired together](#4-how-the-pieces-are-and-are-not-yet-wired-together)
- [5. Is the deployed UltraPlonkVerifier on Base Sepolia real or a placeholder?](#5-is-the-deployed-ultraplonkverifier-on-base-sepolia-real-or-a-placeholder)
- [6. Regenerating the verifier when the circuit changes — a real gap](#6-regenerating-the-verifier-when-the-circuit-changes-a-real-gap)
- [Pipeline, visually: what's real vs. what's a documented gap](#pipeline-visually-what-s-real-vs-what-s-a-documented-gap)
- [Summary: pipeline stage → real or gap](#summary-pipeline-stage-real-or-gap)

## 1. What Noir/Barretenberg are (context, not the point)

[Noir](https://noir-lang.org/) is a Rust-like DSL for writing zero-knowledge
circuits: you write a `fn main(...)` whose `assert`s become the circuit's
constraints, `nargo` compiles it to ACIR (an intermediate arithmetic-circuit
representation), and a separate proving backend turns a satisfying
assignment ("witness") into a succinct proof that the constraints hold,
without revealing the private inputs. This repo uses
[Barretenberg](https://github.com/AztecProtocol/barretenberg) (`bb`) as that
backend, on the UltraHonk proving system (see §3 for why the generated
contract is still named "UltraPlonk"). Pinned versions: `nargo`
1.0.0-beta.22, `bb` 5.0.0-nightly.20260522 (`docs/INTERFACE_CONTRACT.md`).

## 2. What this repo's circuit actually proves

The one real circuit is `integrity-zkp/src/main.nr` — a **key/intent binding
proof**, not a proof about AIS computation or any behavioral-metric
arithmetic. Full formula and domain-tag detail lives on
[integrity-zkp](../entities/integrity-zkp.md); summarized here only for
pipeline context: given a private `secret_key` (KDF'd off-circuit from the
agent's real Ed25519 seed) and a private `intent_payload_hash` (the BCC
object's SHA-256 `intended_state_hash`, reduced to a `Field`), the circuit
asserts two Pedersen-hash equalities against public inputs
(`agent_id_commitment`, `nonce`, `intent_commitment`):

1. `pedersen_hash([DOMAIN_IDENTITY, secret_key]) == agent_id_commitment` —
   the prover holds the exact secret behind the agent's published identity,
   not just anyone who observed the public commitment.
2. `pedersen_hash([DOMAIN_INTENT, secret_key, intent_payload_hash, nonce]) == intent_commitment` —
   the prover actually knows the payload locked in for *this* nonce/action,
   binding the proof to one specific action and blocking replay as a
   different action.

Both are real constraints on real Pedersen gates, exercised by 4 `nargo
test` cases (1 valid, 3 `should_fail` negative controls: wrong secret,
substituted payload, zero nonce — all 4 pass). **Explicit scope limit**:
this is proof-of-possession of a KDF-derived secret, not a full in-circuit
Ed25519 signature check (that would need a non-native Curve25519
bignum/foreign-field gadget library — a separate undertaking, documented
rather than silently skipped).

## 3. The real build/prove/verify pipeline, as it exists in `integrity-zkp/`

Exact commands, all actually run (full transcripts in
`integrity-zkp/README.md`):

```
nargo test                                              # 4/4 constraint unit tests pass
nargo compile                                           # -> target/integrity_zkp.json (ACIR)
nargo execute witness                                   # -> target/witness.gz, using Prover.toml
bb write_vk   -b target/integrity_zkp.json -o target/vk -t evm
bb prove      -b target/integrity_zkp.json -w target/witness.gz -k target/vk/vk -o target/proof -t evm
bb verify     -k target/vk/vk -p target/proof/proof -i target/proof/public_inputs -t evm   # exit 0
bb write_solidity_verifier -k target/vk/vk -o generated/UltraPlonkVerifier.sol -t evm       # 2465 lines
```

`bb verify` was confirmed to actually check the proof (not hardcode
success): flipping one byte of `public_inputs` and re-running produces
`UltraVerifier: verification failed at reduction step`, exit 1.

Two naming/shape traps for anyone consuming the output:
- `bb`'s printed scheme is `ultra_honk` (Barretenberg 5.0.0-nightly's
  current default), not classic UltraPlonk. The generated contract is a
  real **Honk** verifier; `UltraPlonkVerifier.sol` is only the filename
  `contracts/` expects, not a claim about the proving system.
- The generated contract declares `NUMBER_OF_PUBLIC_INPUTS = 11`, not the
  circuit's logical 3 (`agent_id_commitment`, `nonce`, `intent_commitment`)
  — Honk appends internal accumulator/pairing-point public inputs. Callers
  must pass `bb`'s `public_inputs` output through verbatim, not assume a
  3-element array.

Makefile targets (`integrity-zkp/Makefile`): `make test` (nargo only, fast,
CI-safe), `make compile`, `make execute`, `make vk`, `make prove`, `make
verify`, `make solidity-verifier`, `make build` (= test + verify +
solidity-verifier, the full sequence above), `make clean`.

## 4. How the pieces are (and are not yet) wired together

**On-chain contract shape** (all real code, per `contracts/src/oracle/`):
`IZkVerifier` defines `verify(bytes calldata proof, bytes32[] calldata
publicInputs) external view returns (bool)` — the exact signature `bb
write_solidity_verifier` emits. `ReputationRegistry.submitZkAttestation`
(only callable by `agent == msg.sender`, blocking cross-agent replay) checks
the leaf against a `StateAnchor`-anchored Merkle root, then calls
`zkVerifier.verify(proof, publicInputs)`; on success it sets a 7-day
`zkBoostExpiry`, and `effectiveScore()` applies the 1.15x (`ZK_BOOST_BPS =
11_500/10_000`) multiplier while that window is live. The verifier call is
indirected through `VerifierRegistry` (a per-agent clone mapping circuit
*version* → verifier address) so a global circuit upgrade doesn't force
every agent onto a new verifier simultaneously.

**What's not yet connected**:
- **Nothing calls `submitZkAttestation`.** `grep -rln "submitZkAttestation"`
  across the repo matches only Solidity contracts and Solidity tests — no
  Python (`integrity-sdk`, `integrity-cli`) or Rust (`integrity-oracle`)
  caller submits a proof on-chain anywhere in this repo today. `[PLANNED]`.
- **`integrity-sdk`'s prover targets a different circuit.**
  `integrity_sdk/prover.py`'s `NoirProver.generate_proof()` really shells
  out to `nargo execute` and `bb prove` (`subprocess.run(...)`, not a
  mock) — but against `integrity-sdk/circuits/poc_commitment/src/main.nr`,
  a smaller stand-in circuit (`fn main(secret: Field, intent_hash: pub
  Field) -> pub Field`) built to exercise the SDK's proving code path
  *before* `integrity-zkp`'s real circuit existed. Its own docstring says
  so explicitly. It also derives its field element with SHA-256 +
  `int.from_bytes(...) % FR_MODULUS`, not the `blake2s`-based
  `derive_circuit_secret()` convention `integrity-zkp/README.md` specifies
  for the real circuit's `secret_key`. Repointing `prover.py` at
  `integrity-zkp/src/main.nr` and reconciling the KDF is `[PLANNED]`, not
  done.
- **The oracle does not run `bb verify`.** `integrity-oracle`'s AIS
  response has two related-but-distinct fields
  (`integrity-oracle/backend/src/handlers.rs`):
  `zk_proof_verified` is set straight from an off-chain telemetry
  aggregate (`aggregate.zk_verified_this_period`, itself
  `COALESCE(BOOL_OR(zk_verified), false)` over ingested telemetry rows,
  `backend/src/db.rs`) — i.e. a **self-reported flag**, not a recomputed
  proof check. `onchain_zk_boost_consistent: Option<bool>` is a genuine
  on-chain cross-check, calling `ReputationRegistry.isZkBoosted(agent)` via
  `alloy` (`backend/src/chain.rs::is_zk_boosted`) and comparing it against
  the telemetry flag — but it only *detects disagreement* between the two;
  it never verifies a Barretenberg proof itself, and given §4/§6 below,
  on-chain `isZkBoosted` can currently never be `true` at all (nothing sets
  `zkBoostExpiry`, and even if something called `submitZkAttestation`, the
  deployed verifier reverts unconditionally — see §5).

## 5. Is the deployed `UltraPlonkVerifier` on Base Sepolia real or a placeholder?

**It is the fail-closed placeholder, confirmed.** `contracts/src/` contains
exactly one `UltraPlonkVerifier` contract in source:
`contracts/src/oracle/UltraPlonkVerifier.sol`, 52 lines. Its own NatSpec
states this plainly:

> PLACEHOLDER — THIS FILE WILL BE REPLACED WHOLESALE, NOT EDITED. ... This
> placeholder instead fails CLOSED: every call to `verify` reverts,
> unconditionally.

```solidity
function verify(bytes calldata, bytes32[] calldata) external pure override returns (bool) {
    revert PlaceholderVerifierNotYetGenerated();
}
```

`contracts/script/Deploy.s.sol` instantiates exactly this contract
(`verifier = new UltraPlonkVerifier();`, line 108) and registers its address
under `singletons.UltraPlonkVerifier` in the deployments file. Cross-checked
against `deployments.baseSepolia.json`: the live Base Sepolia address is
`0xD6eE9031320382831c8C96627D02aEE573089226` under `singletons` — that is
the placeholder, deployed. Any call to its `verify()` reverts
unconditionally; it is not a mock that returns `true`/`false`, it simply
cannot be exercised on-chain at all right now, by design (contrast with the
old `/INTEGRITY/` prototype, whose equivalent contract returned `true` for
any non-empty proof — a fail-*open* silent mock). Tests that need to
exercise the rest of `submitZkAttestation` (Merkle-anchor check, boost
bookkeeping) do so against a `vm.mockCall`-controlled `IZkVerifier` stand-in
in `contracts/test/ReputationRegistry.t.sol`, not against this contract.

The real, 2465-line generated verifier exists only at
`integrity-zkp/generated/UltraPlonkVerifier.sol` and has never been copied
into `contracts/src/oracle/UltraPlonkVerifier.sol`. Diffing the two files
confirms they are unrelated beyond sharing a filename and the `IZkVerifier`
signature — the placeholder doesn't even import Honk verification-key
constants.

## 6. Regenerating the verifier when the circuit changes — a real gap

`integrity-zkp/README.md` documents the *circuit-side* regeneration step,
and it's real and runnable today: `make solidity-verifier` (or `make
build`) in `integrity-zkp/` re-runs `bb write_vk` + `bb
write_solidity_verifier` and rewrites `integrity-zkp/generated/UltraPlonkVerifier.sol`.

The *hand-off* step — copying that generated file into
`contracts/src/oracle/UltraPlonkVerifier.sol` and redeploying — is where the
gap is. The placeholder's own NatSpec and `docs/wiki`'s root `CLAUDE.md`
both reference a `make generate-verifier` target and a
`contracts/script/GenerateVerifier.sh` script as the intended way to do
this. **Neither exists.** Checked: no `Makefile` anywhere in the repo (root
or `contracts/`) defines a `generate-verifier` target — `contracts/` has no
`Makefile` at all — and `contracts/script/GenerateVerifier.sh` is not
present on disk. `grep -rln "generate-verifier"` across the repo matches
only prose references (`CLAUDE.md`, the placeholder's NatSpec, two test
files' comments), never a target definition. This is a genuine, documented
tooling gap, not something to paper over: today, replacing the placeholder
is a manual copy (`cp integrity-zkp/generated/UltraPlonkVerifier.sol
contracts/src/oracle/UltraPlonkVerifier.sol`) followed by a manual
`forge script script/Deploy.s.sol` redeploy — no single command does both
steps. `[PLANNED]`.

## Pipeline, visually: what's real vs. what's a documented gap

```mermaid
flowchart LR
    subgraph Real["Real, working today"]
        Circuit["Circuit constraints<br/>(main.nr, 4/4 nargo test)"]
        Prove["nargo compile → witness →<br/>bb prove / bb verify"]
        Verifier["bb write_solidity_verifier<br/>(2465-line Honk verifier)"]
        OracleChain["oracle: onchain_zk_boost_consistent<br/>(real isZkBoosted read)"]
    end
    subgraph Gaps["Documented gaps — [PLANNED]"]
        Handoff["Manual copy into contracts/,<br/>no generate-verifier tooling"]
        Deployed["Deployed verifier is the<br/>fail-closed PLACEHOLDER"]
        SDKProver["SDK prover.py targets<br/>poc_commitment, not this circuit"]
        Submit["Nothing calls<br/>submitZkAttestation"]
        OracleFlag["oracle: zk_proof_verified is a<br/>self-reported telemetry flag"]
    end

    Circuit --> Prove --> Verifier --> Handoff --> Deployed
    SDKProver -.-> Prove
    Submit -.-> Deployed
    OracleFlag -.-> OracleChain
    OracleChain -.->|can only detect disagreement| Deployed
```

## Summary: pipeline stage → real or gap

| Stage | Status |
|---|---|
| Circuit constraints (`integrity-zkp/src/main.nr`) | Real, tested (4/4 `nargo test`) |
| `nargo compile` → witness → `bb prove`/`bb verify` | Real, real transcripts, real negative control |
| `bb write_solidity_verifier` output | Real, 2465-line generated Honk verifier |
| Deployed on-chain verifier (Base Sepolia) | **Placeholder** — fails closed, `revert`s unconditionally |
| Circuit → contracts hand-off tooling | **Missing** — `make generate-verifier` / `GenerateVerifier.sh` referenced, not built |
| `integrity-sdk` proof generation | Real toolchain calls, but against `poc_commitment`, **not** `integrity-zkp`'s circuit |
| Proof submission to `ReputationRegistry.submitZkAttestation` | **Nothing calls it** anywhere in this repo |
| Oracle `zk_proof_verified` field | Self-reported telemetry flag, not a recomputed proof check |
| Oracle `onchain_zk_boost_consistent` field | Real on-chain read (`isZkBoosted` via `alloy`), but only ever detects disagreement — can't currently observe `true` given the gaps above |

See [Interface Contract §5](../../INTERFACE_CONTRACT.md#5-zero-knowledge-proving-pipeline-must-be-real-end-to-end)
for the pipeline's original spec, and [integrity-zkp](../entities/integrity-zkp.md)
for the concrete hash-function/domain-separation decisions every consumer
must replicate exactly.
