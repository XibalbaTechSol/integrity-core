"""
Real ZK proof generation via `nargo` + `bb` — docs/INTERFACE_CONTRACT.md §5.

The old prototype's `NoirProver.generate_proof` never invoked `nargo` at all:

    integrity_commitment = "0x" + hashlib.sha256(commitment_payload.encode()).hexdigest()
    return {
        "zk_proof": integrity_commitment,  # For MVP, the commitment acts as proof-of-work
        ...
    }

A SHA-256 hash is not a zero-knowledge proof — there is no circuit, no
witness, nothing for a verifier to check beyond "did you hash the right
string", which anyone can do without owning any secret. This module shells
out to the real toolchain: `nargo execute` solves the circuit and produces a
witness, `bb prove` produces an actual UltraHonk proof over that witness,
and `bb verify` really checks it.

Circuit: this drives the real attestation circuit in the sibling
`integrity-zkp` package's `circuit/` workspace member (`../../integrity-zkp/
circuit/src/main.nr`) — NOT a copy. As of 2026-08-18 this module also drives
`integrity-zkp/tools/commitment_calc`, a second workspace member that exists
solely because there is no Python Pedersen-hash implementation in this repo
(deliberately: reimplementing Barretenberg's Pedersen hash from scratch in a
second language is exactly the "two hashes, both look canonical" divergence
risk `circuit/src/main.nr`'s own docstring warns about). `commitment_calc`
computes `agent_id_commitment`/`intent_commitment` through the real
Noir/Barretenberg toolchain and its own test pins that output against
`circuit/Prover.toml`'s checked-in fixture — this catches drift in
`commitment_calc`'s own logic, not (a Noir test can't read another
package's source) `circuit/src/main.nr`'s hash shape changing out from
under it; see `commitment_calc/src/main.nr`'s own docstring for exactly
what does and doesn't catch that.
Earlier versions of this module pointed at `circuits/poc_commitment/`, a
small stand-in circuit with a different, simpler ABI — that circuit is now
unreferenced by any code in this repo (dead, not deleted, since other
sessions may still be iterating on it; nothing here imports it).
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .did import Keypair

# The BN254 scalar field modulus that Barretenberg/Noir's default proving
# backend operates over. Any Field value in the circuit is implicitly taken
# mod this prime. A raw SHA-256 digest is a 256-bit number, which can exceed
# this ~254-bit prime, so we reduce it mod the prime before handing it to
# the circuit ("hash-to-field"). This is lossy (a small fraction of digests
# collide after reduction) and standard, disclosed practice — see
# integrity-zkp/circuit/src/main.nr's own docstring for the canonical
# statement of this conversion.
FR_MODULUS = 21888242871839275222246405745257275088548364400416034343698204186575808495617

# Must be "evm" (Ethereum/Solidity target, keccak-based) to match
# `contracts/src/oracle/UltraPlonkVerifier.sol`, which is generated with
# `bb write_solidity_verifier -t evm` (see integrity-zkp/Makefile). A proof
# generated against a different verifier_target (e.g. the Noir-recursive
# targets) uses a different hash function internally and will NOT verify
# against the on-chain Solidity verifier even though `bb verify` locally
# reports success against a vk built with the same wrong target.
DEFAULT_VERIFIER_TARGET = "evm"

_CIRCUIT_OUTPUT_RE = re.compile(r"Circuit output:\s*\((0x[0-9a-fA-F]+),\s*(0x[0-9a-fA-F]+)\)")


class ProverError(RuntimeError):
    """Raised on any failure in the real proving pipeline (missing
    toolchain, nargo/bb non-zero exit, malformed output). Deliberately NOT
    caught-and-faked anywhere — a failed proof must surface as a failure,
    not silently degrade to a placeholder value."""


@dataclass
class ZKProof:
    circuit: str
    verifier_target: str
    proof_hex: str
    public_inputs_hex: str
    intent_hash_field: str  # decimal string, for debugging/audit logs
    agent_id_commitment_field: str
    intent_commitment_field: str
    nonce: str
    chain_id: str
    verifying_contract: str

    def to_dict(self) -> dict:
        return {
            "circuit": self.circuit,
            "verifier_target": self.verifier_target,
            "zk_proof": self.proof_hex,
            "public_inputs": self.public_inputs_hex,
            "intent_hash_field": self.intent_hash_field,
            "agent_id_commitment_field": self.agent_id_commitment_field,
            "intent_commitment_field": self.intent_commitment_field,
            "nonce": self.nonce,
            "chain_id": self.chain_id,
            "verifying_contract": self.verifying_contract,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ZKProof":
        return cls(
            circuit=data["circuit"],
            verifier_target=data["verifier_target"],
            proof_hex=data["zk_proof"],
            public_inputs_hex=data["public_inputs"],
            intent_hash_field=data["intent_hash_field"],
            agent_id_commitment_field=data["agent_id_commitment_field"],
            intent_commitment_field=data["intent_commitment_field"],
            nonce=data["nonce"],
            chain_id=data["chain_id"],
            verifying_contract=data["verifying_contract"],
        )


def _pack_hash_to_field(intended_state_hash_hex: str) -> int:
    """Reduce a `0x`-prefixed sha256 hex digest into the BN254 scalar field."""
    h = intended_state_hash_hex[2:] if intended_state_hash_hex.startswith("0x") else intended_state_hash_hex
    return int(h, 16) % FR_MODULUS


def _pack_address_to_field(address_hex: str) -> int:
    """Pack an EVM address into a Field. An address is at most 160 bits and
    the BN254 scalar field is ~254 bits, so `int(address, 16)` is an
    injective, lossless packing — no reduction, no truncation, unlike the
    SHA-256 digest case above. Must match circuit/src/main.nr's
    `verifying_contract` packing exactly (same conversion, no keccak, no
    padding games) — see that file's "CHAIN / CONTRACT BINDING" section."""
    h = address_hex[2:] if address_hex.startswith("0x") else address_hex
    return int(h, 16)


def _derive_secret_field(keypair: Keypair) -> int:
    """
    Derive the circuit's private `secret_key` witness from the agent's
    Ed25519 private key material, WITHOUT ever feeding the raw private key
    bytes into the circuit directly. Signing keys should never leave the
    process they belong to in any form (not even as a "just a witness,
    nobody sees it" argument) — instead we hash the private key bytes with a
    domain-separation tag before reducing into the field. If this derivation
    or the proof ever leaked (e.g. a buggy witness-debug dump), the output
    doesn't hand an attacker anything closer to the actual signing key than
    a generic hash would.
    """
    seed = keypair.private_bytes_raw()
    digest = hashlib.sha256(b"integrity-sdk:zk-secret:v1:" + seed).digest()
    return int.from_bytes(digest, "big") % FR_MODULUS


class NoirProver:
    """Shells out to `nargo`/`bb` for a given agent's proofs, against the
    real integrity-zkp circuit workspace. One instance per (circuit, calc)
    pair; safe to share across an app's lifetime since every call uses
    unique witness/output filenames (no shared mutable proving state)."""

    def __init__(
        self,
        circuit_dir: Optional[Path] = None,
        calc_dir: Optional[Path] = None,
        verifier_target: str = DEFAULT_VERIFIER_TARGET,
    ):
        repo_root = Path(__file__).resolve().parent.parent.parent
        self.circuit_dir = Path(circuit_dir) if circuit_dir else (
            repo_root / "integrity-zkp" / "circuit"
        )
        self.calc_dir = Path(calc_dir) if calc_dir else (
            repo_root / "integrity-zkp" / "tools" / "commitment_calc"
        )
        # Both are members of the same `integrity-zkp` Nargo workspace, so
        # nargo places every member's build output under one shared
        # workspace-root `target/` directory (verified empirically: running
        # `nargo compile`/`execute` from inside a member directory still
        # writes to `<workspace_root>/target/<package_name>.*`, not a local
        # `target/` next to that member's own Nargo.toml).
        self.workspace_root = self.circuit_dir.parent
        self.circuit_name = "integrity_zkp"
        self.calc_name = "commitment_calc"
        self.verifier_target = verifier_target

        self._nargo = shutil.which("nargo")
        self._bb = shutil.which("bb")
        if self._nargo is None or self._bb is None:
            raise ProverError(
                "nargo and/or bb not found on PATH. Real ZK proving requires the "
                "actual Noir/Barretenberg toolchain (nargo 1.0.0-beta.22, bb "
                "5.0.0-nightly per docs/INTERFACE_CONTRACT.md §1) — there is no "
                "mock fallback. Add $HOME/.nargo/bin and $HOME/.bb to PATH."
            )

        self._target_dir = self.workspace_root / "target"
        self._bytecode_path = self._target_dir / f"{self.circuit_name}.json"
        self._calc_bytecode_path = self._target_dir / f"{self.calc_name}.json"
        self._vk_dir = self._target_dir / "vk"
        self._vk_path = self._vk_dir / "vk"

        self._ensure_compiled(self.circuit_dir, self._bytecode_path)
        self._ensure_compiled(self.calc_dir, self._calc_bytecode_path)
        self._ensure_vk()

    def _run(self, args: list, cwd: Path) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(
                args,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProverError(f"Command timed out: {' '.join(args)}") from exc
        if result.returncode != 0:
            raise ProverError(
                f"Command failed ({' '.join(args)}):\nstdout: {result.stdout}\nstderr: {result.stderr}"
            )
        return result

    def _ensure_compiled(self, package_dir: Path, bytecode_path: Path) -> None:
        if bytecode_path.exists():
            return
        self._run([self._nargo, "compile"], cwd=package_dir)
        if not bytecode_path.exists():
            raise ProverError(f"nargo compile did not produce expected bytecode at {bytecode_path}")

    def _ensure_vk(self) -> None:
        if self._vk_path.exists():
            return
        self._run(
            [
                self._bb, "write_vk",
                "-b", str(self._bytecode_path),
                "-o", str(self._vk_dir),
                "-t", self.verifier_target,
            ],
            cwd=self.circuit_dir,
        )
        if not self._vk_path.exists():
            raise ProverError(f"bb write_vk did not produce expected key at {self._vk_path}")

    def _compute_commitments(
        self,
        secret_field: int,
        intent_payload_hash_field: int,
        nonce_field: int,
        chain_id_field: int,
        verifying_contract_field: int,
    ) -> tuple:
        """Run `tools/commitment_calc` to compute
        `(agent_id_commitment, intent_commitment)` for the given witnesses —
        see this module's docstring and commitment_calc's own for why this
        goes through the real Noir toolchain instead of a Python
        reimplementation of the Pedersen hash."""
        call_id = uuid.uuid4().hex[:12]
        prover_toml_name = f"Prover_{call_id}"
        witness_name = f"calc_witness_{call_id}"
        prover_toml_path = self.calc_dir / f"{prover_toml_name}.toml"
        witness_path = self._target_dir / f"{witness_name}.gz"

        try:
            prover_toml_path.write_text(
                f'secret_key = "{secret_field}"\n'
                f'intent_payload_hash = "{intent_payload_hash_field}"\n'
                f'nonce = "{nonce_field}"\n'
                f'chain_id = "{chain_id_field}"\n'
                f'verifying_contract = "{verifying_contract_field}"\n'
            )
            result = self._run(
                [self._nargo, "execute", "-p", prover_toml_name, witness_name],
                cwd=self.calc_dir,
            )
            match = _CIRCUIT_OUTPUT_RE.search(result.stdout)
            if not match:
                raise ProverError(
                    f"Could not parse commitment_calc's circuit output from nargo execute "
                    f"stdout: {result.stdout!r}"
                )
            agent_id_commitment = int(match.group(1), 16)
            intent_commitment = int(match.group(2), 16)
            return agent_id_commitment, intent_commitment
        finally:
            prover_toml_path.unlink(missing_ok=True)
            witness_path.unlink(missing_ok=True)

    def generate_proof(
        self,
        intended_state_hash_hex: str,
        nonce: int,
        chain_id: int,
        verifying_contract: str,
        keypair: Keypair,
    ) -> ZKProof:
        """
        Produce a real UltraHonk proof binding `keypair`'s (domain-separated)
        secret to `intended_state_hash_hex` (the BCC commitment's
        `intended_state_hash`), the BCC per-agent `nonce`, and — as of
        2026-08-18 — `chain_id`/`verifying_contract`, matching the same
        deployment-binding fields already required for the non-ZK BCC
        commitment object (bcc.py). `verifying_contract` is the
        `XibalbaAgentRegistry` singleton address for the target deployment
        (the same value markets.py sources via
        `chain.load_deployments(deployments_file)["singletons"]
        ["XibalbaAgentRegistry"]`), not fetched here — callers must pass it
        explicitly, matching bcc.py's existing convention. Every step here
        is a real subprocess call; any failure raises `ProverError` rather
        than returning a placeholder.
        """
        call_id = uuid.uuid4().hex[:12]
        prover_toml_name = f"Prover_{call_id}"
        witness_name = f"witness_{call_id}"

        secret_field = _derive_secret_field(keypair)
        intent_payload_hash_field = _pack_hash_to_field(intended_state_hash_hex)
        nonce_field = int(nonce)
        chain_id_field = int(chain_id)
        verifying_contract_field = _pack_address_to_field(verifying_contract)

        agent_id_commitment, intent_commitment = self._compute_commitments(
            secret_field, intent_payload_hash_field, nonce_field, chain_id_field, verifying_contract_field
        )

        prover_toml_path = self.circuit_dir / f"{prover_toml_name}.toml"
        witness_path = self._target_dir / f"{witness_name}.gz"
        output_dir = self._target_dir / f"proof_{call_id}"

        try:
            prover_toml_path.write_text(
                f'secret_key = "{secret_field}"\n'
                f'intent_payload_hash = "{intent_payload_hash_field}"\n'
                f'agent_id_commitment = "{agent_id_commitment}"\n'
                f'nonce = "{nonce_field}"\n'
                f'intent_commitment = "{intent_commitment}"\n'
                f'chain_id = "{chain_id_field}"\n'
                f'verifying_contract = "{verifying_contract_field}"\n'
            )

            self._run(
                [self._nargo, "execute", "-p", prover_toml_name, witness_name],
                cwd=self.circuit_dir,
            )
            if not witness_path.exists():
                raise ProverError(f"nargo execute did not produce witness at {witness_path}")

            output_dir.mkdir(parents=True, exist_ok=True)
            self._run(
                [
                    self._bb, "prove",
                    "-b", str(self._bytecode_path),
                    "-w", str(witness_path),
                    "-k", str(self._vk_path),
                    "-o", str(output_dir),
                    "-t", self.verifier_target,
                ],
                cwd=self.circuit_dir,
            )

            proof_bytes = (output_dir / "proof").read_bytes()
            public_inputs_bytes = (output_dir / "public_inputs").read_bytes()

            return ZKProof(
                circuit=self.circuit_name,
                verifier_target=self.verifier_target,
                proof_hex=proof_bytes.hex(),
                public_inputs_hex=public_inputs_bytes.hex(),
                intent_hash_field=str(intent_payload_hash_field),
                agent_id_commitment_field=str(agent_id_commitment),
                intent_commitment_field=str(intent_commitment),
                nonce=str(nonce_field),
                chain_id=str(chain_id_field),
                verifying_contract=verifying_contract,
            )
        finally:
            # Best-effort cleanup of this call's scratch files; the compiled
            # circuit + vk are left in place and reused across calls.
            prover_toml_path.unlink(missing_ok=True)
            witness_path.unlink(missing_ok=True)
            if output_dir.exists():
                for f in output_dir.iterdir():
                    f.unlink(missing_ok=True)
                output_dir.rmdir()

    def verify_proof(self, proof: ZKProof) -> bool:
        """Run `bb verify` against a proof this prover (or any prover using
        the same circuit/vk) produced. Returns False on verification
        failure OR on any error reading/writing the proof files — this is a
        yes/no trust check, not something that should raise for a bad proof."""
        call_id = uuid.uuid4().hex[:12]
        proof_path = self._target_dir / f"verify_proof_{call_id}"
        public_inputs_path = self._target_dir / f"verify_public_inputs_{call_id}"
        try:
            proof_path.write_bytes(bytes.fromhex(proof.proof_hex))
            public_inputs_path.write_bytes(bytes.fromhex(proof.public_inputs_hex))
            result = subprocess.run(
                [
                    self._bb, "verify",
                    "-k", str(self._vk_path),
                    "-p", str(proof_path),
                    "-i", str(public_inputs_path),
                    "-t", self.verifier_target,
                ],
                cwd=str(self.circuit_dir),
                capture_output=True,
                text=True,
                timeout=60,
            )
            return result.returncode == 0
        finally:
            proof_path.unlink(missing_ok=True)
            public_inputs_path.unlink(missing_ok=True)
