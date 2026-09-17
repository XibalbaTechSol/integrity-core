//! Off-chain Zero-Knowledge proof verification for scoring purposes, via
//! Barretenberg's `bb verify` CLI (§5 of the interface contract).
//!
//! Design choice — shelling out vs. a Rust binding: as of this writing there is
//! no maintained Rust crate binding the installed `bb` 5.0.0-nightly's UltraHonk
//! verifier (the old prototype's `bb_rs` was a hand-written FFI stub that never
//! called real Barretenberg code — see its one-line `!proof.is_null()` "verifier").
//! `bb` itself is a real, actively-developed CLI that `integrity-sdk`'s prover
//! also shells out to (§5.4), so using the same CLI here keeps oracle verification
//! and SDK-side local verification behaviorally identical by construction — they
//! run literally the same binary. Shelling out is the practical, honest choice;
//! revisit if/when a real safe Rust binding exists for this bb version.
//!
//! Trust boundary: the verification key comes from *this service's own config*
//! (`vk_paths`, populated from `ZK_VK_PATHS` at startup), never from the request.
//! If a caller could supply their own VK, "verification" would be meaningless —
//! anyone can produce a valid proof against a circuit they made up themselves.
//! Only the proof and public inputs come from the request; the VK is always ours.

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use alloy::primitives::{Address, U256};
use tokio::process::Command;

const PUBLIC_INPUT_BYTES: usize = 32;
const PUBLIC_INPUT_COUNT: usize = 6;
const BN254_SCALAR_FIELD: U256 = U256::from_limbs([
    0x3c208c16d87cfd47,
    0x97816a916871ca8d,
    0xb85045b68181585d,
    0x30644e72e131a029,
]);

/// Bind the circuit's public inputs to the telemetry request before invoking
/// Barretenberg. `bb verify` proves only that the proof matches caller-supplied
/// bytes; it does not know which request or registry the caller intended.
pub fn validate_telemetry_public_inputs(
    public_inputs: &[u8],
    nonce: i64,
    chain_id: u64,
    reputation_registry: Address,
    identity_commitment: &[u8],
    leaf_hash: &[u8],
) -> Result<(), String> {
    if nonce <= 0 {
        return Err("telemetry nonce must be positive".to_string());
    }
    if public_inputs.len() != PUBLIC_INPUT_BYTES * PUBLIC_INPUT_COUNT {
        return Err(format!(
            "expected {PUBLIC_INPUT_COUNT} public inputs ({} bytes), got {}",
            PUBLIC_INPUT_BYTES * PUBLIC_INPUT_COUNT,
            public_inputs.len()
        ));
    }
    if identity_commitment.len() != PUBLIC_INPUT_BYTES || leaf_hash.len() != PUBLIC_INPUT_BYTES {
        return Err("zk identity commitment and telemetry leaf hash must each be exactly 32 bytes".to_string());
    }
    let field = |index: usize| {
        U256::from_be_slice(
            &public_inputs[index * PUBLIC_INPUT_BYTES..(index + 1) * PUBLIC_INPUT_BYTES],
        )
    };
    if field(1) != U256::from(nonce as u64) {
        return Err("zk proof nonce is not bound to the telemetry nonce".to_string());
    }
    if field(0) != U256::from_be_slice(identity_commitment) {
        return Err("zk proof identity is not bound to the registered commitment".to_string());
    }
    if field(3) != U256::from(chain_id) {
        return Err("zk proof chain id is not bound to the oracle chain".to_string());
    }
    let mut registry_bytes = [0u8; PUBLIC_INPUT_BYTES];
    registry_bytes[12..].copy_from_slice(reputation_registry.as_slice());
    if field(4) != U256::from_be_bytes(registry_bytes) {
        return Err("zk proof registry is not bound to the agent registry".to_string());
    }
    if field(5) != (U256::from_be_slice(leaf_hash) % BN254_SCALAR_FIELD) {
        return Err("zk proof leaf is not bound to the telemetry leaf".to_string());
    }
    Ok(())
}

#[derive(Debug, thiserror::Error)]
pub enum ZkVerifyError {
    #[error("unknown circuit id '{0}' — not present in ZK_VK_PATHS config")]
    UnknownCircuit(String),
    #[error("failed to write scratch file for verification: {0}")]
    Io(#[from] std::io::Error),
    #[error("failed to launch `bb` (checked path: {path}): {source}")]
    SpawnFailed { path: String, source: std::io::Error },
    #[error("`bb verify` produced output that was neither a clear pass nor a clear fail — treating as an error rather than guessing. stdout={stdout:?} stderr={stderr:?}")]
    AmbiguousOutput { stdout: String, stderr: String },
}

/// Wraps the `bb verify` CLI. One instance is shared (via `Arc`) across the Axum
/// app; it holds no mutable state, just config (paths), so sharing is trivial.
#[derive(Clone)]
pub struct ZkVerifier {
    /// circuit_id -> path of the trusted verification key for that circuit.
    vk_paths: HashMap<String, PathBuf>,
    /// Must match the `--verifier_target` the proof was generated with (`bb
    /// prove`'s target determines the transcript hash function — mismatched
    /// targets fail verification even for an otherwise-valid proof). "evm" is the
    /// default because that's the target `contracts/`'s Solidity verifier also
    /// needs, so the sdk's proof generation and this oracle's off-chain
    /// verification stay aligned with what will eventually be checked on-chain too.
    verifier_target: String,
    bb_binary: PathBuf,
    /// Scratch directory for the proof/public-inputs files `bb` reads — `bb
    /// verify` takes file paths, not stdin, so the request's bytes have to land
    /// on disk momentarily. Cleaned up after every call, success or failure.
    scratch_dir: PathBuf,
}

impl ZkVerifier {
    pub fn new(
        vk_paths: HashMap<String, PathBuf>,
        verifier_target: impl Into<String>,
        bb_binary: impl Into<PathBuf>,
        scratch_dir: impl Into<PathBuf>,
    ) -> Self {
        Self {
            vk_paths,
            verifier_target: verifier_target.into(),
            bb_binary: bb_binary.into(),
            scratch_dir: scratch_dir.into(),
        }
    }

    pub fn known_circuits(&self) -> impl Iterator<Item = &str> {
        self.vk_paths.keys().map(|s| s.as_str())
    }

    /// Verifies a proof for `circuit_id` against this oracle's own trusted VK.
    /// `proof_bytes` and `public_inputs_bytes` are exactly the binary blobs
    /// `bb prove` produced (i.e. the raw contents of its `proof` / `public_inputs`
    /// output files) — the caller (a telemetry submission) supplies these; the VK
    /// never comes from the caller.
    pub async fn verify(
        &self,
        circuit_id: &str,
        proof_bytes: &[u8],
        public_inputs_bytes: &[u8],
    ) -> Result<bool, ZkVerifyError> {
        let vk_path = self
            .vk_paths
            .get(circuit_id)
            .ok_or_else(|| ZkVerifyError::UnknownCircuit(circuit_id.to_string()))?;

        tokio::fs::create_dir_all(&self.scratch_dir).await?;
        let request_id = uuid::Uuid::new_v4();
        let proof_path = self.scratch_dir.join(format!("proof-{request_id}.bin"));
        let inputs_path = self.scratch_dir.join(format!("public_inputs-{request_id}.bin"));

        // Best-effort cleanup guard: write files, run bb, then always remove them,
        // even on error paths, so a burst of failed verifications can't fill disk
        // with abandoned scratch files.
        let result = self
            .run_bb_verify(&proof_path, &inputs_path, vk_path, proof_bytes, public_inputs_bytes)
            .await;
        let _ = tokio::fs::remove_file(&proof_path).await;
        let _ = tokio::fs::remove_file(&inputs_path).await;
        result
    }

    async fn run_bb_verify(
        &self,
        proof_path: &Path,
        inputs_path: &Path,
        vk_path: &Path,
        proof_bytes: &[u8],
        public_inputs_bytes: &[u8],
    ) -> Result<bool, ZkVerifyError> {
        tokio::fs::write(proof_path, proof_bytes).await?;
        tokio::fs::write(inputs_path, public_inputs_bytes).await?;

        let output = Command::new(&self.bb_binary)
            .arg("verify")
            .arg("-p")
            .arg(proof_path)
            .arg("-k")
            .arg(vk_path)
            .arg("-i")
            .arg(inputs_path)
            .arg("--verifier_target")
            .arg(&self.verifier_target)
            .output()
            .await
            .map_err(|source| ZkVerifyError::SpawnFailed {
                path: self.bb_binary.display().to_string(),
                source,
            })?;

        let stdout = String::from_utf8_lossy(&output.stdout).to_string();
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();

        // `bb verify`'s exit status is the authoritative signal (0 = verified,
        // nonzero = not verified); the message check is a belt-and-suspenders
        // sanity check so a `bb` CLI/flag mismatch (e.g. wrong verifier_target
        // producing some other error) surfaces as `AmbiguousOutput` rather than
        // silently being read as "invalid proof".
        //
        // The success banner is checked on BOTH streams: current `bb`
        // (Barretenberg 5.x, the version pinned in the interface contract §1)
        // writes "Proof verified successfully" to STDERR alongside its memory
        // stats, not stdout — matching the failure check below, which already
        // scans both streams for the same reason.
        let verified_banner = "Proof verified successfully";
        if output.status.success() && (stdout.contains(verified_banner) || stderr.contains(verified_banner)) {
            return Ok(true);
        }
        if !output.status.success()
            && (stdout.contains("verification failed") || stderr.contains("verification failed") || stderr.contains("public inputs file size must be a multiple of 32 bytes"))
        {
            return Ok(false);
        }
        Err(ZkVerifyError::AmbiguousOutput { stdout, stderr })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Fixture generated once, by hand, exactly as documented in
    /// `backend/tests/fixtures/zk_smoke/circuit/` — a tiny Noir circuit proving
    /// knowledge of a `secret` whose Pedersen hash equals a public commitment.
    /// This mirrors the *shape* of the real `integrity-zkp` attestation circuit
    /// (prove knowledge of a private value matching a public commitment) without
    /// its Ed25519 machinery, which doesn't exist yet since that's a sibling
    /// package being built in parallel. Regenerate with:
    ///   cd backend/tests/fixtures/zk_smoke/circuit
    ///   nargo compile
    ///   nargo execute witness
    ///   bb write_vk -b target/test_circuit.json -o ../out_vk --verifier_target evm
    ///   bb prove -b target/test_circuit.json -w target/witness.gz -k ../out_vk/vk -o ../out_proof --verifier_target evm
    fn fixtures_dir() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/zk_smoke")
    }

    fn make_verifier() -> ZkVerifier {
        let dir = fixtures_dir();
        let mut vk_paths = HashMap::new();
        vk_paths.insert("smoke-test-circuit".to_string(), dir.join("vk"));
        ZkVerifier::new(
            vk_paths,
            "evm",
            // Resolved the same way config.rs does: trust PATH unless BB_BINARY is set.
            std::env::var("BB_BINARY").unwrap_or_else(|_| "bb".to_string()),
            std::env::temp_dir().join("integrity-oracle-zk-test-scratch"),
        )
    }

    #[test]
    fn telemetry_public_inputs_bind_request_context() {
        let registry = Address::from([0x11; 20]);
        let leaf = [0x22; 32];
        let mut inputs = vec![0u8; PUBLIC_INPUT_BYTES * PUBLIC_INPUT_COUNT];
        inputs[32..64].copy_from_slice(&U256::from(7u64).to_be_bytes::<32>());
        inputs[96..128].copy_from_slice(&U256::from(84532u64).to_be_bytes::<32>());
        let mut registry_field = [0u8; 32];
        registry_field[12..].copy_from_slice(registry.as_slice());
        inputs[128..160].copy_from_slice(&registry_field);
        inputs[160..192].copy_from_slice(&U256::from_be_slice(&leaf).to_be_bytes::<32>());

        let identity = [0x33; 32];
        inputs[..32].copy_from_slice(&identity);
        assert!(validate_telemetry_public_inputs(&inputs, 7, 84532, registry, &identity, &leaf).is_ok());
        assert!(validate_telemetry_public_inputs(&inputs, 8, 84532, registry, &identity, &leaf).is_err());
    }

    #[test]
    fn malformed_telemetry_public_inputs_fail_closed() {
        let result = validate_telemetry_public_inputs(
            &[0u8; 32],
            1,
            84532,
            Address::ZERO,
            &[0u8; 32],
            &[0u8; 32],
        );
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn verifies_a_real_bb_generated_proof() {
        let dir = fixtures_dir();
        let proof = tokio::fs::read(dir.join("proof")).await.unwrap();
        let public_inputs = tokio::fs::read(dir.join("public_inputs")).await.unwrap();

        let verifier = make_verifier();
        let result = verifier
            .verify("smoke-test-circuit", &proof, &public_inputs)
            .await
            .expect("bb verify should run successfully against a valid fixture");
        assert!(result, "a genuine bb-generated proof against its matching VK must verify");
    }

    #[tokio::test]
    async fn rejects_a_proof_against_tampered_public_inputs() {
        let dir = fixtures_dir();
        let proof = tokio::fs::read(dir.join("proof")).await.unwrap();
        let tampered = tokio::fs::read(dir.join("tampered_public_inputs")).await.unwrap();

        let verifier = make_verifier();
        let result = verifier
            .verify("smoke-test-circuit", &proof, &tampered)
            .await
            .expect("bb verify should run and report a clean failure, not error out");
        assert!(!result, "tampered public inputs must not verify");
    }

    #[tokio::test]
    async fn unknown_circuit_id_is_rejected_before_ever_shelling_out() {
        let verifier = make_verifier();
        let result = verifier.verify("not-a-registered-circuit", b"junk", b"junk").await;
        assert!(matches!(result, Err(ZkVerifyError::UnknownCircuit(_))));
    }
}
