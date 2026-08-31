# integrity-zkp

The zero-knowledge circuit for the Integrity Protocol. It proves that an AI
agent's action matches a previously-committed intent, and that the prover
holds the agent's real key material — without revealing the secret key or
the full intent payload. Implements `docs/INTERFACE_CONTRACT.md` §5.

Written in [Noir](https://noir-lang.org/) (`nargo` 1.0.0-beta.22), proven
with [Barretenberg](https://github.com/AztecProtocol/barretenberg) (`bb`
5.0.0-nightly.20260522). Both were actually run to produce everything under
`target/` and `generated/` in this repo — nothing here is a description of
a circuit that hasn't been compiled and proven; see "Exact commands run"
below for the real transcript.

## What the circuit proves

Given:
- a private `secret_key` (a Field element KDF'd, off-circuit, from the
  agent's real Ed25519 secret seed — see "Scope limitation" below),
- a private `intent_payload_hash` (the SHA-256 `intended_state_hash` from
  the agent's BCC commitment object, §4.2, reduced to a Field — see "Hash
  function choice"),
- a public `nonce` (the same per-agent monotonic nonce from that BCC
  object — already public on the wire, not a secret),
- a public `agent_id_commitment` (the agent's long-lived ZK identity
  commitment, published once at DID-creation time),
- a public `intent_commitment` (the specific, per-action public commitment
  this proof must reproduce), and
- as of 2026-08-18, a public `chain_id` and public `verifying_contract` (the
  EVM chain and `XibalbaAgentRegistry` deployment this proof is valid
  for — see "CHAIN / CONTRACT BINDING" in `circuit/src/main.nr`, mirroring
  the same binding already required for the non-ZK BCC commitment object),

the circuit asserts:

1. `pedersen_hash([DOMAIN_IDENTITY, secret_key]) == agent_id_commitment`
   — the prover holds the exact secret behind this agent's published
   identity, not just anyone who saw a public commitment. Prevents
   proof-of-identity spoofing.
2. `pedersen_hash([DOMAIN_INTENT, secret_key, intent_payload_hash, nonce, chain_id, verifying_contract]) == intent_commitment`
   — the prover actually knows the intent payload that was locked in for
   *this specific* nonce/action, not a fabricated or substituted one, on
   *this specific* chain and deployment. Binding the nonce in prevents a
   valid proof for one action being replayed as if it covered a different
   action; binding `chain_id`/`verifying_contract` prevents a valid proof
   for one deployment being replayed verbatim against another.
3. `nonce != 0` — defensive rejection of an uninitialized/sentinel nonce.

Both `assert`s are real constraints on real Pedersen hash gates — not
`assert(true)`. See `circuit/src/main.nr` for the fully commented source
(the comments explain the *why* — what attack each constraint stops — per
INTERFACE_CONTRACT.md §10).

Six `#[test]` functions in `circuit/src/main.nr` exercise this: one valid
binding, and five invalid ones (wrong secret / substituted payload / zero
nonce / wrong `chain_id` / wrong `verifying_contract`) that must each fail
to satisfy the constraints — run with `nargo test --workspace` (output
pasted below; all six pass, including the five `should_fail` cases
correctly failing).

## Hash function choice — the one thing sibling packages MUST match

**We use Pedersen hash (`std::hash::pedersen_hash`) inside the circuit, not
SHA-256.**

The outer BCC wire object's `intended_state_hash` (§4.2) stays SHA-256 —
that's fixed by the interface contract and is used outside this circuit,
for the Ed25519 signature over the BCC JSON object. It does not change and
this package does not touch it.

Inside the circuit, SHA-256 would be very expensive: it's a bitwise hash
(rotations/XORs/ANDs over 32-bit words) and costs thousands of gates per
call in an arithmetic circuit. Pedersen hash is:
- a **native gate** in Barretenberg's UltraPlonk/UltraHonk backend (a
  handful of constraints instead of thousands), and
- already the convention the *other* Noir circuits in this protocol use
  (`integrity-oracle/circuits/telemetry` and `.../reputation` both commit
  private data with `std::hash::pedersen_hash`), so this keeps one ZK-hash
  convention across the whole protocol instead of introducing a third
  scheme (we considered Poseidon, but it isn't a native Barretenberg gate
  and would cost more constraints for no benefit here).

This means there are now **two distinct hashes** for the same logical
action, and every sibling package needs to keep them straight:

| Value | Hash | Computed by | Purpose |
|---|---|---|---|
| `intended_state_hash` | SHA-256 | integrity-sdk / integrity-cli | Signed BCC JSON object (§4.2), audit trail |
| `intent_commitment` | Pedersen | integrity-zkp circuit / integrity-sdk's `prover.py` | ZK-only, feeds this circuit and the oracle's `ZK_boost` (§4.3) check |

**Exact definition** (this is the load-bearing part — reproduce this
*exactly*, including array order and the domain tag, or your Pedersen
output will differ and every proof will fail to verify even though the
underlying data is "the same"):

```
agent_id_commitment = pedersen_hash([DOMAIN_IDENTITY, secret_key])            // DOMAIN_IDENTITY = 1
intent_commitment   = pedersen_hash([DOMAIN_INTENT, secret_key,
                                      intent_payload_hash, nonce,
                                      chain_id, verifying_contract])           // DOMAIN_INTENT = 2
```

**Converting bytes to a Field** (needed for both `secret_key` and
`intent_payload_hash`, which start life as byte strings): take the
big-endian byte string, interpret it as an unsigned integer, and reduce it
mod the BN254 scalar field prime
`21888242871839275222246405745257275088548364400416034343698204186575808495617`.
Reference Python (what `integrity-sdk/prover.py` and `integrity-oracle`
must both use):

```python
BN254_FR = 21888242871839275222246405745257275088548364400416034343698204186575808495617

def bytes_be_to_field_mod_r(b: bytes) -> int:
    return int.from_bytes(b, "big") % BN254_FR

# secret_key: KDF'd from the raw 32-byte Ed25519 seed
secret_key_field = bytes_be_to_field_mod_r(blake2s(ed25519_seed).digest())

# intent_payload_hash: the BCC object's own intended_state_hash bytes
intent_payload_hash_field = bytes_be_to_field_mod_r(bytes.fromhex(intended_state_hash[2:]))
```

**`chain_id`/`verifying_contract` need no reduction** — an EVM chain ID and
address are both well under the ~254-bit BN254 scalar field, so packing is
just `int(chain_id)` and `int(verifying_contract_address_hex, 16)`, lossless
and injective (no keccak, no padding, no truncation). This differs from the
SHA-256 packing above, which IS lossy — don't conflate the two conversions.

**Domain separation** (`DOMAIN_IDENTITY = 1`, `DOMAIN_INTENT = 2`): both
hashes start with the same `secret_key` element; without a domain tag, a
Field that is "some Pedersen commitment" elsewhere in the protocol could in
principle be confused for one of these two commitment *kinds*. Tagging the
domain removes that ambiguity for one extra constraint. If a third
sibling introduces another Pedersen commitment over `secret_key`, it must
pick a new, unused domain tag.

## Scope limitation — honest, not silently mocked

A *full* Ed25519 signature-verification circuit (elliptic-curve scalar
multiplication and point addition over Curve25519, expressed as
non-native field arithmetic inside a BN254/Grumpkin proving system) is a
substantial undertaking on its own — it needs a bignum/foreign-field
gadget library and is typically its own audited circuit in production ZK
stacks. This package does not reimplement that from scratch.

Instead — and this is a real, checked cryptographic binding, not a mock —
`secret_key` is a Field element that `integrity-sdk` derives from the
agent's real Ed25519 seed via a KDF (`derive_circuit_secret()`, see the
Python snippet above) at DID-creation time. `agent_id_commitment =
pedersen_hash([DOMAIN_IDENTITY, secret_key])` is published once, alongside
the DID Document (§4.1), as the agent's long-lived ZK identity commitment.
This circuit proves "the prover holds the exact preimage of that published
commitment," which is a real proof-of-possession — it is just not itself
an Ed25519 signature check on an arbitrary message. This mirrors the
honesty rule the interface contract sets for TEE attestation (§8): say
plainly what's real and what's out of scope, rather than silently
pretending the boundary isn't there.

## Fixture values (`circuit/Prover.toml`)

The checked-in `circuit/Prover.toml` fixture uses `secret_key = 0xf00d`,
`intent_payload_hash = 0xc0ffee`, `nonce = 7`, `chain_id = 31337` (local
anvil), `verifying_contract = 0x5FC8...875707` (the `XibalbaAgentRegistry`
singleton address from `deployments.local.json`) — as 32-byte hex strings —
with `agent_id_commitment` / `intent_commitment` precomputed to match via
Pedersen hash. As of 2026-08-18, regenerating these no longer needs a
temporary `#[test]`+`println` round-trip: `tools/commitment_calc` (a second
workspace member — see "Directory layout" below) computes both commitments
directly. Run:

```
cd tools/commitment_calc
# write a Prover.toml with secret_key/intent_payload_hash/nonce/chain_id/
# verifying_contract for your chosen values, then:
nargo execute out
```

and read the two Field values off the printed `Circuit output: (0x.., 0x..)`
line — this is also exactly what `integrity-sdk`'s `prover.py` does
programmatically at proof-generation time (see "`integrity-sdk` handoff"
below).

## Exact commands run (real output)

All commands below were actually executed against `nargo` 1.0.0-beta.22
and `bb` 5.0.0-nightly.20260522 in this environment. `-t evm` targets the
Ethereum/Solidity-compatible proving configuration (Keccak transcript) so
the same circuit's proof/vk can be verified both natively via `bb verify`
and, once contracts/ consumes `generated/UltraPlonkVerifier.sol`, on-chain.

### 1. `nargo test --workspace` — constraint unit tests, both workspace members

```
$ nargo test --workspace
[commitment_calc] Running 1 test function
[commitment_calc] Testing test_matches_main_circuit_fixture ... ok
[commitment_calc] 1 test passed
[integrity_zkp] Running 6 test functions
[integrity_zkp] Testing test_invalid_binding_wrong_secret ... ok
[integrity_zkp] Testing test_invalid_binding_wrong_verifying_contract ... ok
[integrity_zkp] Testing test_invalid_binding_wrong_payload ... ok
[integrity_zkp] Testing test_invalid_binding_wrong_chain_id ... ok
[integrity_zkp] Testing test_invalid_binding_zero_nonce ... ok
[integrity_zkp] Testing test_valid_binding ... ok
[integrity_zkp] 6 tests passed
```

All five `should_fail` tests (wrong secret, substituted payload, zero
nonce, wrong `chain_id`, wrong `verifying_contract`) correctly fail to
satisfy the circuit's constraints; the valid binding correctly succeeds.
`commitment_calc`'s one test cross-checks its output against
`circuit/Prover.toml`'s checked-in fixture — see "Directory layout" below
for why that package exists.

### 2. `nargo compile` — produce ACIR bytecode

```
$ nargo compile
$ ls target/
integrity_zkp.json
```

(No stdout on success — `nargo compile` is silent when it succeeds.)

### 3. `nargo execute witness` — generate the witness for the `Prover.toml` fixture

```
$ nargo execute witness
[integrity_zkp] Circuit witness successfully solved
[integrity_zkp] Witness saved to target/witness.gz
```

### 4. `bb write_vk` — verification key

```
$ bb write_vk -b target/integrity_zkp.json -o target/vk -t evm
Scheme is: ultra_honk, num threads: 4 (mem: 5.05 MiB)
CircuitProve: Proving key computed in 40 ms (mem: 24.55 MiB)
VK saved to "target/vk/vk" (mem: 25.10 MiB)
VK Hash saved to "target/vk/vk_hash" (mem: 25.10 MiB)
```

### 5. `bb prove` — generate the proof

```
$ bb prove -b target/integrity_zkp.json -w target/witness.gz -o target/proof -k target/vk/vk -t evm
Scheme is: ultra_honk, num threads: 4 (mem: 5.11 MiB)
CircuitProve: Proving key computed in 42 ms (mem: 24.37 MiB)
Public inputs saved to "target/proof/public_inputs" (mem: 31.30 MiB)
Proof saved to "target/proof/proof" (mem: 31.30 MiB)
```

### 6. `bb verify` — verify the real proof

```
$ bb verify -k target/vk/vk -p target/proof/proof -i target/proof/public_inputs -t evm
Scheme is: ultra_honk, num threads: 4 (mem: 5.05 MiB)
Proof verified successfully (mem: 7.65 MiB)
```

Exit code `0`. As a negative-control sanity check, flipping a single byte
in `public_inputs` and re-running `bb verify` against the same proof
produces:

```
Scheme is: ultra_honk, num threads: 4 (mem: 7.65 MiB)
UltraVerifier: verification failed at reduction step (mem: 7.65 MiB)
Proof verification failed
```

Exit code `1` — confirming the verifier is actually checking the proof
against the public inputs, not returning a hardcoded success.

### 7. `bb write_solidity_verifier` — the on-chain verifier hand-off

```
$ bb write_solidity_verifier -k target/vk/vk -o generated/UltraPlonkVerifier.sol -t evm
Scheme is: ultra_honk, num threads: 4 (mem: 5.38 MiB)
ZK Honk solidity verifier saved to "generated/UltraPlonkVerifier.sol" (mem: 6.30 MiB)
```

Produces `generated/UltraPlonkVerifier.sol` — **2465 lines**, a real
generated Solidity verifier contract (not a stub), keyed to the exact
verification key computed above (`VK_HASH` constant in the file equals the
contents of `target/vk/vk_hash`,
`285b392aa3c3050313f432ce1a71562d8e2145e6d0a1475780705a68860e6b5f` as of the
2026-08-18 chain_id/verifying_contract binding — this changes every time the
circuit's public-input shape changes, so treat any specific hash value here
as a snapshot, not a pin).

**Naming note for `contracts/`:** the file is named
`UltraPlonkVerifier.sol` to match the placeholder path
`contracts/src/oracle/UltraPlonkVerifier.sol` expected by
INTERFACE_CONTRACT.md §5.3/§9, but `bb`'s printed scheme is
`ultra_honk` — Barretenberg 5.0.0-nightly's current default proving
system is **UltraHonk**, not the older UltraPlonk. The generated contract
is a real Honk verifier; treat "UltraPlonkVerifier.sol" as the *filename
contracts/ is expecting*, not a claim about the underlying proof system.
The contract also declares `NUMBER_OF_PUBLIC_INPUTS = 13`, not 5 — Honk
verifiers append 8 internal protocol accumulator/pairing-point public
inputs after this circuit's own 5 (`agent_id_commitment`, `nonce`,
`intent_commitment`, `chain_id`, `verifying_contract`); `contracts/` must
pass through whatever `bb`'s `public_inputs` output contains verbatim to
the verifier's `verify()` call rather than assuming a 5-element array. Note
`bb prove`'s own `public_inputs` output file only ever contains the
circuit's real public inputs (160 bytes = 5 × 32 for this circuit) — the 8
pairing-point words are carried inside the proof bytes themselves, not
this file; `NUMBER_OF_PUBLIC_INPUTS = 13` describes what the Solidity
verifier's `verify()` expects internally, not the shape of `public_inputs`.

## Handoff to `contracts/`

1. `contracts/src/oracle/UltraPlonkVerifier.sol` should be replaced
   **entirely** by `integrity-zkp/generated/UltraPlonkVerifier.sol` (copy
   it over — it's a generated artifact, don't hand-edit either copy).
2. Whenever this circuit changes (new constraints, new public inputs),
   regenerate with `make solidity-verifier` (below) and re-copy — the
   verifier is coupled 1:1 to the verification key, which is coupled 1:1
   to the compiled circuit.
3. `contracts/`'s deployment script registers the deployed verifier's
   address as `UltraPlonkVerifier` in `deployments.local.json` (§6);
   `integrity-oracle` and `integrity-sdk` read that address when they need
   to submit/verify proofs against the chain rather than only locally via
   `bb verify`.

## `integrity-sdk` handoff (`prover.py`)

As of 2026-08-18, `integrity-sdk`'s `prover.py` (`NoirProver.generate_proof`)
actually drives this package's real toolchain — it is not a placeholder and
does not point at any other circuit:
1. Compute `secret_key_field` (KDF'd from the agent's Ed25519 seed) and
   `intent_payload_hash_field` (reduced SHA-256 `intended_state_hash`) per
   the Python snippet above; pack `nonce`/`chain_id` as plain ints and
   `verifying_contract` as `int(address, 16)` (lossless — see
   `circuit/src/main.nr`'s "CHAIN / CONTRACT BINDING").
2. Run `tools/commitment_calc` (via `nargo execute`, parsing its
   `Circuit output: (0x.., 0x..)` stdout line) to get
   `agent_id_commitment` / `intent_commitment` — see "Fixture values" above
   for why this goes through the real toolchain instead of a Python
   Pedersen-hash reimplementation.
3. Write `circuit/Prover.toml` with all 7 named fields (2 private, 5
   public) and run `nargo execute` there, then `bb prove -t evm` / `bb
   verify -t evm` — `-t evm` (not `-t noir-recursive-no-zk`, an earlier
   default this module used before it was wired to a real circuit) is
   required for on-chain compatibility with `contracts/src/oracle/
   UltraPlonkVerifier.sol`, which is generated with the same target.

Both `circuit/` and `tools/commitment_calc/` are members of one Nargo
workspace, so `prover.py` only ever needs to know the workspace root
(`integrity-sdk/../integrity-zkp`) — build output for every member lands in
one shared `<workspace_root>/target/`, confirmed empirically (see
"Directory layout" below).

## Makefile targets (CI-runnable)

```
make test               # nargo test — fast, no bb, run on every CI build
make compile             # nargo compile
make execute             # nargo execute witness (uses checked-in Prover.toml)
make vk                  # bb write_vk
make prove               # bb prove
make verify              # bb verify (fails the build if verification fails)
make solidity-verifier   # bb write_solidity_verifier -> generated/UltraPlonkVerifier.sol
make build               # test + verify + solidity-verifier, i.e. the full pipeline above
make clean               # remove target/ and generated/
```

`make build` is what CI should run for this package — it is the exact
sequence of commands transcribed above, not a separate/looser check.

## Directory layout

As of 2026-08-18 this is a two-member Nargo workspace, not a single
package — `circuit` is the real proving circuit (`default-member`, so
plain `nargo compile`/`test`/`execute` run from the workspace root target
it without `--package`); `tools/commitment_calc` is a small sibling package
that exists purely so `integrity-sdk`'s `prover.py` (and anyone else who
needs `agent_id_commitment`/`intent_commitment` before writing
`circuit/Prover.toml`) can compute those two Pedersen hashes through the
real toolchain instead of a second, divergence-prone implementation — see
`tools/commitment_calc/src/main.nr`'s own docstring.

```
integrity-zkp/
  Nargo.toml                    # [workspace] members = ["circuit", "tools/commitment_calc"]
  Makefile
  circuit/
    Nargo.toml                  # package "integrity_zkp"
    Prover.toml                 # checked-in real fixture (see "Fixture values")
    src/main.nr                 # the circuit + its #[test]s
  tools/commitment_calc/
    Nargo.toml                  # package "commitment_calc"
    src/main.nr                 # offline agent_id_commitment/intent_commitment calculator + cross-check test
  target/                       # nargo/bb build artifacts for EVERY workspace member (gitignored, regenerate with `make build`)
  generated/
    UltraPlonkVerifier.sol      # hand-off artifact for contracts/ (checked in)
```
