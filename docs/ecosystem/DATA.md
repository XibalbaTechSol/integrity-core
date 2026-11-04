# Data and Evidence Authority

## Boundary

Shield and Cortex keep customer content inside the declared customer boundary. Telemetry is metadata-first and edge-derived. Prompts, tool arguments, file contents, environment variables, stdout/stderr, URLs, filenames, repository names, exception messages, and stack traces are prohibited from export unless explicitly classified as permitted metadata.

## Integrity evidence

Receipts contain signed decisions and HMAC-protected identifiers. StateAnchor receives roots and opaque checkpoint commitments, not raw records, paths, identifiers, or PHI. Optional DecisionTrace annotations are labeled model-generated and non-authoritative.

## Cortex content

- Provenance metadata and content storage are separate.
- Content, indexes, blobs, embeddings, replicas, and encryption keys are purgeable.
- Historical roots may remain as non-content evidence but must not reconstruct PHI.
- A spot-check proves current provider retrieval for a fresh nonce; it does not prove permanent persistence.

## Retention and deletion

Retention is pack- and tenant-scoped. Purge removes content and required decryption material within the declared retention boundary, including searchable and replicated copies. The deletion evidence must identify what was removed, what non-content commitments remain, and what remains unverified.

## Provider and key handling

Remote provider keys remain host-managed and never enter browser-visible settings or trace payloads. Non-loopback provider endpoints require HTTPS. Device signing keys, agent identity keys, HMAC keys, and encryption keys have separate scopes and rotation/revocation procedures.
