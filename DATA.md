# Data and evidence boundary

**Status:** current architecture decision
**Authority:** data classes, retention boundaries, and evidence semantics across Integrity,
Shield, and Cortex.

## Data classes

| Class | Examples | Default boundary |
|---|---|---|
| Identity | DID document, public keys, device binding | Public identity material; private keys stay outside harness roots |
| Policy | Signed pack metadata, rules, pack hash, version | Customer/operator control plane |
| Decision evidence | Decision, reason code, sequence, receipt references, hashes | Signed and locally verifiable; identifiers may be HMAC-protected |
| Provenance metadata | Event IDs, timestamps, content commitments, receipt references | Append-only; no customer content by implication |
| Customer content | Prompts, tool arguments, file contents, model output, PHI | Customer boundary; not exported by default |
| Derived data | FTS indexes, blobs, embeddings, cached projections | Purgeable within the declared retention boundary |
| External evidence | Anchor roots, checkpoints, Oracle/AIS results | Availability enhancement; never the only local enforcement path |

## Evidence semantics

Signed receipts prove signer validity, chain position, inclusion, and—when present—anchoring.
HMAC-protected identifiers remain opaque without the organization key. An anchor root proves a
commitment, not recovery of the records or content behind it.

Shield exports bounded labels and redacted references. Raw command lines, prompts, tool
arguments, file contents, environment variables, and other content-bearing values do not cross
the product boundary unless a separately documented contract explicitly permits them.

Cortex separates immutable provenance metadata from purgeable content. A content commitment or
historical root does not authorize reconstruction after purge. Spot-checks, when implemented,
prove current provider retrieval using a nonce-bound proof rather than returning unrestricted
content to an external verifier.

## Retention and outage behavior

Local queues preserve receipts for later delivery or anchoring. External outage does not erase
local decisions or make Shield enforcement dependent on a remote service. Retention, purge,
backup, export, encryption-at-rest, and tenant teardown remain product/gate work where the
execution plan marks them open.

Claims about live Oracle, BCC, public-chain, vendor, or production-PHI behavior require the
corresponding runtime evidence; source-level support alone is not deployment proof.
