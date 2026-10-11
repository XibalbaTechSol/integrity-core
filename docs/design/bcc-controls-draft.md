# Draft: control citations for the four uncited BCC rules

**Status:** UNREVIEWED proposal. Nothing here is in `packs/bcc/controls.yaml`, and the pack hash is unchanged. The compliance owner
decides each row; until then the gap stays pinned by
`test_the_rules_that_cite_no_control_are_exactly_the_known_gap` in `integrity-sdk/tests/unit/test_core_bcc_pack_equivalence.py`.
This is an engineering reading of what each rule *does*, not a legal conclusion (`docs/CONTROLS_MATRIX.md` section 0: the evidence
does not certify compliance). Primary text: [45 CFR 164.312](https://www.ecfr.gov/current/title-45/section-164.312) (technical
safeguards) and [45 CFR 164.502(b)](https://www.ecfr.gov/current/title-45/section-164.502) (minimum necessary).

`packs/bcc/controls.yaml` today cites only `HIPAA-164.312(a)(1)` (access control) and `HIPAA-164.312(b)` (audit controls), the two
`docs/CONTROLS_MATRIX.md` maps.

| Rule code | What the rule actually does (`packs/bcc/policy.rego`) | Candidate citation | Why, and what it would claim | Alternative |
|---|---|---|---|---|
| `BCC_MALFORMED_COMMITMENT` | Denies a commitment whose `agent_id` or `intent_type` is not a string, so no other rule runs on garbage. | [164.312(c)(1)](https://www.ecfr.gov/current/title-45/section-164.312) integrity | Input validation protecting what reaches the policy; it claims nothing about PHI itself. | Cite none: it is a parser guard, not a safeguard. |
| `POLICY_VIOLATION` | Denies an `intent_type` containing `exfiltrat`, `backdoor`, `spoof` or `bypass` (case-insensitive substring). | `HIPAA-164.312(a)(1)` | Defense-in-depth on access control: a label that names an attack is refused even from an authorized agent. A substring heuristic, so it supports the control and is not evidence of it. | Cite none: a keyword filter is easy to evade and over-claiming it is the risk. |
| `HIPAA_TECHNICAL_SAFEGUARD_FAILURE` | Denies an `intent_type` that matches `\d{3}-\d{2}-\d{4}` (an SSN-shaped identifier in a label). | [164.502(b)](https://www.ecfr.gov/current/title-45/section-164.502) minimum necessary, with `docs/CONTROLS_MATRIX.md` "PHI redaction before export" | Keeps an identifier out of a field that is logged and anchored. It covers one pattern in one field only. | `HIPAA-164.312(e)(1)` transmission security, which fits the name less well than the behavior. |
| `TOKEN_BUDGET_OPA` | Denies once `daily_token_spend + token_count` exceeds a per-verification-tier budget. | None under HIPAA | A resource limit, not a HIPAA safeguard. It belongs under NIST AI RMF (`docs/CONTROLS_MATRIX.md` section 2) if the owner wants it cited. | Leave uncited and keep it on the pinned list. |

## Decisions needed from the compliance owner

1. For each row: cite, cite a different control, or keep it on the pinned gap list (with the reason the test already records).
2. `HIPAA_TECHNICAL_SAFEGUARD_FAILURE` is named after a HIPAA safeguard but implements one regex. Rename it, or accept the name and
   cite only what the regex does. A rename changes the reason code, so it needs the shared decision vectors and the `bcc.rego` mapping
   updated in the same change.
3. Any edit to `controls.yaml` changes the pack hash: re-sign, re-pin `BCC_POLICY_PACK_HASH`, and update `GOLDEN_PACK_HASH` deliberately.
