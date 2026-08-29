# integrity-zkp — Makefile
#
# Wires up the real nargo/bb pipeline described in
# docs/INTERFACE_CONTRACT.md §5 so CI (and humans) run the exact same
# commands used to develop this package — nothing here is a stand-in.
#
# `make test`  — fast, CI-friendly: constraint unit tests only (no bb). Runs
#                across the whole workspace (the `circuit` proving package
#                AND `tools/commitment_calc`, the offline commitment
#                calculator prover.py shells out to — see its own docstring
#                for why it exists and why its test must keep matching
#                circuit/Prover.toml's fixture).
# `make build` — full pipeline: compile -> execute -> prove -> verify ->
#                write_vk -> write_solidity_verifier, using the Prover.toml
#                fixture checked into this repo. This is slower (invokes
#                bb, which does real elliptic-curve work) but is what
#                actually exercises the ZK toolchain end to end; run it in
#                CI on top of `make test`, not instead of it. Operates on
#                the `circuit` package only (the default workspace member) —
#                commitment_calc has no proof/verifier of its own.

NARGO ?= nargo
BB ?= bb
TARGET_DIR := target
CIRCUIT := $(TARGET_DIR)/integrity_zkp.json
WITNESS := $(TARGET_DIR)/witness.gz
VK_DIR := $(TARGET_DIR)/vk
PROOF_DIR := $(TARGET_DIR)/proof
GENERATED_DIR := generated
VERIFIER_TARGET := evm

.PHONY: test compile execute prove verify vk solidity-verifier build clean

test:
	$(NARGO) test --workspace

compile:
	$(NARGO) compile

execute: compile
	$(NARGO) execute witness

vk: compile
	mkdir -p $(VK_DIR)
	$(BB) write_vk -b $(CIRCUIT) -o $(VK_DIR) -t $(VERIFIER_TARGET)

prove: execute vk
	mkdir -p $(PROOF_DIR)
	$(BB) prove -b $(CIRCUIT) -w $(WITNESS) -o $(PROOF_DIR) -k $(VK_DIR)/vk -t $(VERIFIER_TARGET)

verify: prove
	$(BB) verify -k $(VK_DIR)/vk -p $(PROOF_DIR)/proof -i $(PROOF_DIR)/public_inputs -t $(VERIFIER_TARGET)

solidity-verifier: vk
	mkdir -p $(GENERATED_DIR)
	$(BB) write_solidity_verifier -k $(VK_DIR)/vk -o $(GENERATED_DIR)/UltraPlonkVerifier.sol -t $(VERIFIER_TARGET)

build: test verify solidity-verifier

clean:
	rm -rf $(TARGET_DIR) $(GENERATED_DIR)
