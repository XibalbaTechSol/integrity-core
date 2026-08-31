//! Regenerates `spec/ais-api/v1/openapi.yaml` from the live `utoipa` annotations in
//! `handlers.rs` (see `src/openapi.rs`). Run with `cargo run --bin gen-openapi` from
//! `integrity-oracle/backend/`. Wire into CI as a diff-check (regenerate, `git diff
//! --exit-code` the spec dir) so a handler change without a matching spec regeneration
//! fails the build instead of silently drifting.

use std::path::PathBuf;

use backend::openapi::combined_openapi;

fn main() {
    let yaml = combined_openapi().to_yaml().expect("OpenApi -> YAML serialization should never fail");

    // Anchor to the crate manifest, not the caller's current directory. Cargo can run
    // this binary from the workspace root or backend crate; both must update the same
    // in-repository specification.
    let out_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../spec/ais-api/v1");
    std::fs::create_dir_all(&out_dir).expect("failed to create spec/ais-api/v1");
    let out_path = out_dir.join("openapi.yaml");
    std::fs::write(&out_path, yaml).expect("failed to write openapi.yaml");

    println!("wrote {}", out_path.display());
}
