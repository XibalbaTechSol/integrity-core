# Standardizing Merkle commitment across all collected content

**Status:** design — **not implemented, not tested.** Written without shell access
(see `e2e-audit-2026-07-31.md` "Method"). Every convention change below must be
validated by the conformance vectors in §6 before any of it is believed.

**Goal:** every artifact the protocol collects is committed under a Merkle root,
using one convention, so that conclusions drawn from the data are provable rather
than merely stored.

---

## 1. Why the current state blocks that goal

Two independent problems, and they need fixing in this order.

**(a) The convention is not pinned.** `docs/INTERFACE_CONTRACT.md` §4.4 and
`StateAnchor.sol:12-23` pin exactly two rules — keccak256 leaves, sorted-pair
parents — and are **silent on odd-width levels**. Three implementations filled
that silence differently (E9): `merkle.rs` and `merkle.py` duplicate the odd node,
`vault.py` promotes it. All three honestly claim compliance and all three are
right about the spec as written. Nothing is broken today only because each
component builds, anchors, and verifies within its own tree. The first
cross-system verification breaks — which is exactly what standardization means.

**(b) Almost nothing is actually committed.** Coverage today:

| Content | Committed? |
|---|---|
| BCC intent commitments | yes (`bcc_middleware`) |
| Git commit leaves | yes (`vault.py`), but `test_result_hash` is `unverified` on all 21 |
| Telemetry events | **no** — `leaf_hash` computed, batching is dead code (`db.rs:412-428`) |
| OTel spans | **no** |
| `identity_verifications` (tier proofs) | **no** |
| Gate decisions, incl. fail-open events | **no** |

AIS is computed from telemetry. Telemetry is uncommitted mutable rows. So the
protocol's headline number is not currently derivable from provable data — which
is the actual thing to fix.

---

## 2. The v2 convention (normative — proposed §4.4 amendment)

Adopt **OpenZeppelin standard Merkle tree semantics** wholesale, rather than
adjudicating between the two house conventions. It resolves both weaknesses, and
it is a published standard with an existing reference implementation
(`@openzeppelin/merkle-tree`) that conformance vectors can be checked against.

1. **Hash:** `keccak256`. *(unchanged)*
2. **Parents:** sorted-pair — `keccak256(a < b ? a‖b : b‖a)`. *(unchanged; keeps
   stock `MerkleProof.verify` working on-chain)*
3. **Odd node: PROMOTE unchanged. Never duplicate.** *(changes `merkle.rs`,
   `merkle.py`; `vault.py` already conforms)*
4. **Leaves are double-hashed:**
   `leaf = keccak256(keccak256(preimage))`. *(new for all three)*
5. **Leaf preimages are domain-separated:**
   `"integrity.merkle.<kind>.v2" ‖ "|" ‖ <fields…>` *(new for `merkle.rs` and
   `merkle.py`; `vault.py:118` already does this)*

### Why these two changes specifically

**Rule 3 kills a real root ambiguity.** Under duplication, `[A,B,C]` and
`[A,B,C,C]` produce the *identical* root — `H(H(A,B), H(C,C))` both times
(verified by hand). So the root does not determine the leaf list, and any
conclusion of the form "this root covers N events" is unsound. This directly
contradicts `StateAnchor.sol:22-23`'s claim that the root is "a true function of
the *set* of leaves." Under promotion, `[A,B,C]` → `H(H(A,B), C)` while
`[A,B,C,C]` → `H(H(A,B), H(C,C))` — distinct.

**Rule 4 kills promotion's own weakness,** which is what `merkle.rs:92-96` was
right to worry about even though it named it imprecisely. With promotion, an
internal node appears at a leaf position, so a 2-leaf tree `[H(A,B), C]` collides
with the 3-leaf tree `[A,B,C]`. Double-hashing makes leaves structurally
distinguishable from internal nodes (internal = one keccak over 64 bytes; leaf =
two keccaks over a tagged preimage), so no valid leaf can equal an internal node
without a preimage attack. This is OZ's own documented mitigation, not an
invention here.

**On-chain impact: none.** `MerkleProof.verify` is agnostic to how leaf bytes were
derived and already implements sorted-pair folding. `StateAnchor.sol` needs **no
code change** — only a NatSpec correction, since its "true function of the set of
leaves" claim is false under the convention two of three implementations
currently use.

### Correct the record while amending

Three code comments state the security argument wrongly and should be fixed with
the implementations, because they are what the next author will read:

- `vault.py:49-52` overstates: duplication permits leaf-list ambiguity, **not**
  proving "a non-existent fourth leaf." The leaf proven is `C`, genuinely present.
- `merkle.rs:92-96` and `merkle.py:28-34` claim duplication is "OpenZeppelin
  standard." It is not — `@openzeppelin/merkle-tree` does not duplicate.
- `merkle.py:4-7` and `merkle.rs:1-14` claim to match the others "bit-for-bit."
  Unfalsifiable until §6's vectors exist; delete the claim or make it testable.

---

## 3. One envelope for every leaf kind

The coverage gap closes by making every collected artifact a leaf of the same
shape, distinguished only by `kind`:

```
preimage = "integrity.merkle." ‖ kind ‖ ".v2|"
         ‖ agent_id ‖ "|" ‖ epoch_ms ‖ "|" ‖ content_hash ‖ "|" ‖ source
leaf     = keccak256(keccak256(preimage))
```

`content_hash` is a keccak256 over the artifact's own canonical bytes, so payloads
never leave the agent — same privacy property the BCC hash-only commitment already
has. `source` is the runtime discriminator F8 added (`claude-code` / `hermes` /
`agy` / `oracle`), which is what finally makes AIS groupable by runtime (open
item #2).

Kinds to define — the first three exist, the rest are the coverage work:

| `kind` | Status | Closes |
|---|---|---|
| `commit` | exists (`vault.py`) | — |
| `bcc_commitment` | exists (`merkle.py`) | — |
| `telemetry` | leaf exists, **never batched** | the AIS provenance gap |
| `test_result` | **new** | F5 — leaves that attest to something |
| `gate_decision` | **new** | fail-open events become evidence, not just a log counter |
| `identity_verification` | **new** | tier claims become provable |
| `trace_span` | **new** | OTel spans |

`VaultLeaf` already anticipates this — it carries a `kind` field and
`vault.py:115-116` notes the domain separation exists "once more kinds exist."
Only `for_commit` was ever written. Add constructors, do not add trees.

---

## 4. Two anchoring authorities — deliberately not one

The instinct to collapse three anchoring paths into one service is wrong here,
and the reason is a protocol invariant rather than a preference.

Root CLAUDE.md: the genesis memory root must be **signed by the agent's
controller, never by the protocol**, and the oracle is **read-only and never signs
or submits transactions**. So:

- **Agent-signed tree** — `commit`, `test_result`, and the memory/vault lineage.
  Anchored by the agent via `anchor_vault.py` to its own `StateAnchor`. Collapsing
  this into a protocol service would destroy the sovereignty property that makes
  anchored memory meaningful.
- **Protocol-signed tree** — `telemetry`, `bcc_commitment`, `gate_decision`,
  `identity_verification`, `trace_span`. Anchored by `bcc_middleware` (it already
  holds `ANCHOR_SIGNER_PRIVATE_KEY` and already batches per-agent). The oracle
  computes and stores leaves; it must **not** anchor.

This coexists safely and is already proven to: `StateAnchor.isAnchoredRoot` is a
permanent mapping, `rootAtEpoch` retains history, and `verifyLeaf(root, …)` takes
an explicit root — so two writers to one `StateAnchor` never invalidate each
other's proofs. Only `verifyLeafAtLatest` is last-writer-wins; **deprecate it**,
since with two authorities its answer is meaningless.

**Consequence for the oracle's dead code.** `fetch_pending_leaves` /
`create_merkle_root_and_assign` (`db.rs:412-476`) implement a single global
cross-agent root — incompatible with per-agent anchoring and with §4 above.
Under this design they stay dead. Either delete them with the
`merkle_root_id`/`leaf_index` columns, or repurpose the columns to reference the
**bcc_middleware-anchored** per-agent root so `GET /v1/agent/{id}/telemetry` stops
returning `null`. Recommend the latter — it is what makes telemetry provable, and
the columns are already exposed in the API.

---

## 5. Migration — historical roots can never be rewritten

Anchored roots are permanent on-chain. v1 roots must keep verifying under v1
rules forever; this is not optional and it is the part most likely to be botched.

1. **Version every stored root.** Add `convention_version SMALLINT NOT NULL
   DEFAULT 1` to `merkle_roots`; add `"convention": 1` to each `anchors.jsonl`
   entry in `TrustVault.record_anchor`. Backfill existing rows/lines as `1`.
2. **Dispatch proof generation on the stored version.** Keep the v1 tree builders
   reachable — renamed, not deleted — and select by the anchored root's recorded
   version. A proof generator that assumes v2 silently produces invalid proofs for
   every historical root.
3. **Cut over per component**, new roots only. No re-anchoring, no backfill of
   trees. The 21 existing vault leaves stay under v1 roots.
4. **Do not mix versions within one root.** A batch is entirely v1 or entirely v2.
5. **`StateAnchor.sol`:** NatSpec correction only (§2). No redeploy — it is
   deployed per agent, so a code change would reach only future agents, the same
   constraint recorded in `PRODUCTION_GAPS.md` §19.

---

## 6. Conformance vectors — the enforcement mechanism

The convention spans Rust, Python (×2) and Solidity, so **shared code is
impossible; shared test data is not.** This is the same problem BCC canonical JSON
already has, solved the same way.

Add `docs/vectors/merkle-v2.json` — checked in, language-neutral, generated
**independently** of all three implementations (from `@openzeppelin/merkle-tree`
and `cast keccak`, exactly as `merkle.rs`'s existing tests already do for
`hash_pair`):

- leaf preimage → leaf hash, for every `kind` in §3
- roots for leaf counts **1, 2, 3, 5, 7, 21** — odd counts are the whole point;
  the current bug is invisible at powers of two
- an inclusion proof per leaf for the 7- and 21-leaf trees
- the **negative** vector that pins the fix: the v1 duplication root for
  `[A,B,C]`, asserted **not equal** to the v2 promotion root
- the ambiguity vector: v1 `[A,B,C]` root **equals** v1 `[A,B,C,C]` root, and the
  v2 equivalents **differ**

Each package gets a test that reads this file and reproduces every vector. A
convention drift then fails a test instead of silently producing roots nobody can
cross-verify. Without this, §2 is a comment change.

---

## 7. Order of work

Convention first because it is small and gates proof correctness; coverage second
because it is the actual goal and is the larger job.

| # | Step | Verify by |
|---|---|---|
| 1 | Write `docs/vectors/merkle-v2.json` from an independent generator | vectors self-check vs `cast keccak` |
| 2 | Amend §4.4; correct `StateAnchor.sol` NatSpec + the three wrong comments | review |
| 3 | Add version columns/fields + v1 dispatch (§5.1–5.2) | `cargo test`, `pytest` |
| 4 | Move `merkle.rs`, `merkle.py`, `vault.py` to v2 | §6 vectors pass in all three |
| 5 | Add the §3 envelope + new leaf kinds | unit tests per kind |
| 6 | Wire `telemetry` leaves into bcc_middleware's per-agent batch (§4) | `merkle_root_id` non-null in API |
| 7 | Populate `test_result` leaves | closes F5 |
| 8 | Cross-system proof test: leaf anchored by one component, verified by another | the property this whole doc exists for |

Step 8 is the acceptance test. Until it passes, standardization is asserted rather
than demonstrated — and asserting it is the failure mode this repo was rewritten
to avoid.

**Blocked on the shell for every step from 3 onward.**
