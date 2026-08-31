# Vendored trust roots

`aws_nitro_root_g1.pem` is AWS's published Nitro Enclaves root CA, from
<https://aws-nitro-enclaves.amazonaws.com/AWS_NitroEnclaves_Root-G1.zip>
(see <https://docs.aws.amazon.com/enclaves/latest/user/verify-root.html>).

**Why it is duplicated here** rather than referenced from
`integrity-sdk/integrity_sdk/security/trust_roots/`: this file is `include_str!`'d
into the oracle binary, and the Docker build context is `./integrity-oracle`, so a
`../../../integrity-sdk/...` path does not exist at image build time. More
importantly, a compile-time dependency on a sibling package's directory layout is
the wrong coupling for a trust anchor — the oracle should own the root it pins.

**Do not edit.** The SHA-256 is pinned in `src/attestation.rs`
(`AWS_NITRO_ROOT_SHA256`) and asserted at verification time, so a swapped file
fails loudly rather than silently changing who the oracle trusts. The Python SDK
keeps its own copy for the same reason; `pinned_root_matches_the_bundled_pem`
guards this one and the SDK's tests guard that one.
