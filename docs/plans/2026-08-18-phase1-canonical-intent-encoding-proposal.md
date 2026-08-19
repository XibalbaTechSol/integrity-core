# Canonical intent encoding — chain_id + verifying_contract binding — go/no-go proposal

**Status:** built and tested, authorized as scoped (option 1). See `PRODUCTION_GAPS.md` §30 for
the closure entry, including a real, disclosed design adjustment made during implementation:
`verifying_contract` is enforced only when this deployment has a configured `XibalbaAgentRegistry`
address, not unconditionally as originally described below — see that entry's "real, disclosed
design adjustment" paragraph. `chain_id` is enforced unconditionally, as originally scoped.

Implemented across `integrity-sdk` (`bcc.py`, `markets.py`, `telemetry/intent.py`, `client.py`,
`mcp_server.py`), `integrity-cli` (`bcc.py`, `main.py`), `bcc_middleware` (`schemas.py`,
`canonical.py`, `main.py`), plus the cross-repo `xibalba-shield` consumer
(`integrity_exporter/exporter.py`, `config/loader.py`, `cli.py`) and `integrity-dashboard/demo`.
Full test suites green: `integrity-sdk` 262 passed, `integrity-cli` full suite passed,
`bcc_middleware` 129 passed (new: `tests/test_deployment_binding.py`), `xibalba-shield` 135
passed/9 skipped. A genuine pre-existing bug was found and fixed along the way: the repo-root
`.env`'s `DEPLOYMENTS_FILE` still pointed at the pre-rename `INTEGRITY-LATEST` path.

What follows below is the original proposal, left as written for the historical record of what
was scoped before implementation — re-read `PRODUCTION_GAPS.md` §30 for what actually shipped
where it differs.

## Why this slice, and why now

`docs/plans/2026-08-17-phase1-tracer-bullet-proposal.md` explicitly deferred this as "real,
verified gap ... but separable work" when it scoped the account/kernel tracer bullet. That
tracer bullet and its three reference adapters plus module governance are now built, tested, and
merged onto this branch (`PRODUCTION_GAPS.md` §29). Item 6 of the Phase I plan
(`CLAUDE_HANDOFF_2026-08-17.md` §8.1) — canonical intent encoding — is the smallest remaining
named gap; item 7 (formal constraint grammar, independent audit, machine-checked invariance) is
the heavier production gate and is not this slice.

**This is BCC-schema work, not kernel work.** The Devil's Advocate review's own language
("canonical intent must bind account, kernel/profile, chain, ... verifier semantics, nonce
namespace, deadline") was written about the experimental kernel's internal hook-frame replay
domain — a separate, contract-side problem, already partly addressed there by ERC-4337's own
per-account nonce and the epoch-snapshotting just landed. This proposal is about the other,
general-purpose gap: the BCC intent commitment (§4.2) that every intent type — not just
kernel-mediated ones — signs and sends to `bcc_middleware`, and that carries nothing binding it
to a specific chain or deployment.

## The gap, verified today

`docs/INTERFACE_CONTRACT.md` §4.2's wire schema is 8 signed fields: `agent_id`, `intent_type`,
`intended_state_hash`, `nonce`, `timestamp`, `agent_public_key`, `covered_entity_address`,
`intent_rationale`. None of `integrity-sdk/bcc.py`, `integrity-cli/bcc.py`, or
`bcc_middleware/app/{schemas,canonical}.py` include a chain identifier or a target-contract
address in the signed payload — confirmed by direct read of all three implementations, not
inferred from the doc. A commitment signed once is therefore valid, byte-for-byte, against any
chain or any deployment of the protocol that shares the signing agent's DID — including a
different `XibalbaAgentRegistry` deployment (a redeployed testnet instance, a future mainnet
instance, or a malicious lookalike middleware) than the one the agent believed it was
authorizing against. The `nonce` is monotonic per-agent but carries no deployment scope, so it
does not close this — a fresh, never-used nonce is just as replayable across deployments as a
reused one.

This is not a new pattern for this schema: `agent_public_key`, `covered_entity_address`, and
`intent_rationale` were all added the same way — as **✅ RECONCILED** post-draft extensions to
§4.2, each landing in all three implementations plus the wiki doc plus round-trip tests. This
proposal follows that same precedent rather than inventing a new process.

## Scope: the slice itself

- Two new signed fields in the §4.2 wire schema:
  - `chain_id` (integer, **required**) — the EVM chain ID this commitment is scoped to.
  - `verifying_contract` (0x-address, **required**) — the `XibalbaAgentRegistry` address for
    that chain, the one address every downstream primitive in this architecture already resolves
    through (`CLAUDE.md`: "the canonical DID↔primitive-set index every downstream contract...
    resolves through live"). Binding to the registry, not to a per-intent-type contract, keeps
    this general-purpose rather than reintroducing per-intent-type special-casing.
- `bcc_middleware` validates both server-side against its own config before checking anything
  else: `chain_id` must equal `settings.chain_id` (`bcc_middleware/app/config.py`, already
  populated from `CHAIN_ID` env var — no new config surface needed), `verifying_contract` must
  equal the registry address the middleware is actually configured against. Mismatch on either
  is a hard deny, same failure register as an invalid signature — not a warning, not a soft
  policy input.
- `integrity-sdk`'s `sign_commitment` (or equivalent) and `integrity-cli`'s `bcc.py` both gain
  required parameters for these two fields — callers must supply them explicitly rather than the
  SDK silently defaulting to "whatever chain the RPC client happens to be pointed at," so a
  misconfigured caller fails loudly instead of signing a commitment for the wrong chain.
- Canonicalization updated identically in all three implementations (`bcc.py` x2,
  `canonical.py`), same `sort_keys=True, ensure_ascii=True` rule as every other field — no new
  serialization rule introduced.
- `docs/INTERFACE_CONTRACT.md` §4.2 and `docs/wiki/concepts/bcc.md` updated with the same
  "✅ RECONCILED" treatment the three prior extensions got, including the rationale above.
- Cross-package round-trip tests extended: a commitment signed with one chain_id/verifying
  address fails middleware validation when middleware is configured for a different one; a
  commitment missing either field is rejected at the schema level, not signature level.

## Explicitly deferred — not attempted here

- The experimental kernel's own hook-frame replay-domain binding (account, kernel/profile,
  execution depth, action digest, pre-state digest, configuration epoch — the full list from
  `CLAUDE_HANDOFF_2026-08-17.md` §9). That is a Solidity-side, `IntegrityAccountV1Experimental`/
  `IntegrityKernelV1Experimental`-specific problem, materially different code and materially
  different (much larger) blast radius than a Python wire-schema change. Separate proposal if
  pursued.
- Binding `chain_id` into the ZK circuit's `intent_commitment`
  (`integrity-zkp/src/main.nr`) — today the Pedersen hash covers `secret_key`,
  `intent_payload_hash`, `agent_id_commitment`, and `nonce` only. Adding a public input changes
  the circuit, the verifying key, and `UltraPlonkVerifier` regeneration — real, larger,
  cross-package work (Noir + `bb` + Solidity verifier regen), out of scope for this slice. Will
  be named as a known residual gap in the updated wiki doc, not silently dropped.
- Any change to `intent_type` namespace extensions (§15.1) or the healthcare BAA fields —
  untouched by this proposal.
- Backward compatibility shims for already-in-flight commitments signed under the 8-field shape
  — see Real risks below; this is a breaking wire-format change, not an additive-optional one,
  because an optional `chain_id` would defeat the point (a downgrade attack could simply omit it).

## Acceptance criteria

- Real tests, passing, proving: (a) a commitment signed for the middleware's actual configured
  chain_id + registry address is accepted exactly as before; (b) a commitment with a mismatched
  `chain_id` is denied; (c) a commitment with a mismatched `verifying_contract` is denied; (d) a
  commitment missing either field fails Pydantic validation before signature verification is even
  attempted (fail fast, cheapest check first — same ordering discipline `canonical.py` already
  uses for `agent_public_key` binding).
- All existing BCC round-trip tests updated, not just new ones added — a stale test still
  signing the old 8-field shape would silently mean the new fields are optional in practice.
- `docs/INTERFACE_CONTRACT.md` §4.2 and `docs/wiki/concepts/bcc.md` updated in the same commit,
  same as every other piece of Phase I work this session.
- `PRODUCTION_GAPS.md` updated: this closes part of the item-6 gap named in §29, and explicitly
  does not close the kernel hook-frame or ZK-circuit residuals named above.

## Real risks

- **This is a breaking wire-format change**, not additive. Any already-deployed agent code
  (SDK, CLI, or a third party integrating directly against §4.2) signing the old 8-field shape
  will have every future commitment rejected once `bcc_middleware` requires the new fields. This
  is a single-operator testnet setup today (`CLAUDE.md`: "all protocol roles currently point at
  one address"), so the blast radius is contained, but it is still a real compatibility break to
  disclose, not a silent one.
- **Choice of `verifying_contract` as the registry, not a per-intent contract, is a real
  design decision, not a neutral default** — it binds a commitment to "this deployment of the
  protocol" rather than "this specific downstream contract," which is coarser than the kernel
  review's per-call binding. That coarseness is deliberate (matches this schema's existing
  general-purpose, not-kernel-specific scope) but should be stated plainly, not left implicit.
- Lower blast radius than the kernel work: no Solidity changes, no deployment, no on-chain state
  — pure Python wire-schema + middleware validation + docs + tests. Still real production-path
  code (`bcc_middleware` is the one gate every intent already passes through).

## Decision needed

1. **Authorize as scoped above** — add `chain_id` + `verifying_contract` as required signed
   fields, breaking change, update all three implementations + docs + tests.
2. **Authorize with changes** — e.g. optional-with-deprecation-window instead of immediately
   required, or a different binding target than the registry address.
3. **Not yet** — stay at proposal stage; revisit later, possibly bundled with the deferred
   kernel hook-frame or ZK-circuit binding work instead of ahead of it.
