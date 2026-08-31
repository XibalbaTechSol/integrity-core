// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {IAdapter} from "./IAdapter.sol";

/// @title AdapterRegistry
/// @notice Phase III tracer-bullet slice
/// (`docs/plans/2026-08-25-phase3-adapter-registry-tracer-bullet-proposal.md`): permissionless
/// registration of `IAdapter` contracts, plus metered-call enforcement of each adapter's own
/// self-declared gas bound (`docs/SPEC.md` §7.2 obligation R3).
/// @dev **What this proves:** R3 (bounded cost) is real -- `evaluate` never forwards more than
/// an adapter's own `declaredGasBound` to it, and a call that exhausts that stipend is
/// distinguished from an ordinary rejection (see `evaluate`'s own doc comment for the exact
/// heuristic and its disclosed limitation). Registration is permissionless and idempotent-safe:
/// registering the identical `(adapter, declaredGasBound, specHash)` twice is a harmless no-op;
/// registering the same `adapter` address with DIFFERENT params reverts -- there is no
/// re-registration path in this slice, conflicting or not.
///
/// **R5 corrected 2026-08-31.** The obligation table this file originally cited (whitepaper
/// §6.2's staking/audit-attestation framing) predates `docs/SPEC.md`'s spec cutover.
/// `docs/SPEC.md` §7.2 (the current normative source, `docs/DOCUMENT_STATUS.yaml`) redefines R5
/// as **Identity**: "published with source, machine-readable semantics, and a version hash the
/// account pins" -- no bonds, no audit attestation. `publishIdentity` below closes that,
/// tied to the SAME `specHash` every consuming account (`IntegrityKernel`, `LicenceAccount`)
/// already immutably pins at construction, rather than adding a second, parallel hash.
///
/// **What this does NOT prove:** R1 (determinism) -- needs an off-chain differential-replay
/// admission suite (`AdapterAdmissionSuite.s.sol`, `contracts/test/registry/
/// AdapterAdmissionSuite.t.sol`), not a contract-level check. R4 (conservatism) -- structural
/// only, by construction, IF a future caller only ever ANDs multiple adapters together; this
/// registry evaluates exactly ONE adapter per call and has no composition logic of its own.
/// Wired into `IntegrityKernel` and `LicenceAccount` as an optional additive precondition, with
/// enabled-path coverage in their focused Foundry suites.
///
/// **`docs/SPEC.md` §7.1 note, not a contradiction to silently ignore:** "No on-chain adapter
/// registry is required for v1." This contract remains genuinely optional -- both consuming
/// accounts disable it via `AdapterRegistry(address(0))` -- and is not itself the `[PLANNED]`
/// "attested registry" §7.1 names; it is a smaller, already-shipped step toward it.
contract AdapterRegistry {
    error AdapterAlreadyRegisteredWithDifferentParams(
        address adapter, uint256 existingGasBound, bytes32 existingSpecHash
    );
    error AdapterNotRegistered(address adapter);
    error ZeroDeclaredGasBound();
    error ZeroAdapterAddress();
    error AdapterExceededGasBound(address adapter, uint256 declaredGasBound);
    error EmptyMetadataURI();
    error IdentityAlreadyPublishedWithDifferentURI(address adapter, string existingMetadataURI);

    struct AdapterInfo {
        uint256 declaredGasBound;
        bytes32 specHash;
        bool registered;
    }

    mapping(address adapter => AdapterInfo info) public adapters;
    /// @dev Empty string means "not published" -- checked via `bytes(...).length == 0`, same
    /// idiom `publishIdentity` uses to reject an empty URI in the first place, so a not-yet-
    /// published adapter and a rejected-empty-URI call are indistinguishable by design (both
    /// never reach a stored non-empty value).
    mapping(address adapter => string metadataURI) public identityMetadataURI;

    event AdapterRegistered(address indexed adapter, uint256 declaredGasBound, bytes32 specHash);
    /// @param specHash Echoed from the adapter's own registration -- `publishIdentity` does not
    /// take a separate hash parameter; see its own doc comment for why.
    event AdapterIdentityPublished(address indexed adapter, string metadataURI, bytes32 specHash);

    /// @notice Permissionless registration. Anyone may register any adapter address -- this
    /// registry does not check that `msg.sender` deployed, owns, or has any relationship to
    /// `adapter`; whitepaper §6.4 explicitly wants authorship to be permissionless.
    function register(address adapter, uint256 declaredGasBound, bytes32 specHash) external {
        if (adapter == address(0)) revert ZeroAdapterAddress();
        if (declaredGasBound == 0) revert ZeroDeclaredGasBound();

        AdapterInfo memory existing = adapters[adapter];
        if (existing.registered) {
            if (existing.declaredGasBound != declaredGasBound || existing.specHash != specHash) {
                revert AdapterAlreadyRegisteredWithDifferentParams(
                    adapter, existing.declaredGasBound, existing.specHash
                );
            }
            return;
        }

        adapters[adapter] = AdapterInfo({declaredGasBound: declaredGasBound, specHash: specHash, registered: true});
        emit AdapterRegistered(adapter, declaredGasBound, specHash);
    }

    /// @notice Publishes machine-readable identity for an already-registered adapter, closing
    /// `docs/SPEC.md` §7.2 R5 ("Identity"): published with source, machine-readable semantics,
    /// and a version hash the account pins.
    /// @dev Deliberately does NOT take a separate hash parameter. `specHash` was already pinned,
    /// immutably, at `register()` time, and every consuming account (`IntegrityKernel`,
    /// `LicenceAccount`) already trusts that exact value forever. Requiring a second hash here
    /// would create two "versions" of the same adapter with no way to reconcile them if they
    /// ever disagreed. Instead, `metadataURI` MUST point to a document whose content hashes to
    /// the adapter's EXISTING `specHash` -- publishing identity means "here is what that hash you
    /// already trust actually is," not "trust this new hash too."
    /// @dev Permissionless, same posture as `register()` itself (whitepaper §6.4: authorship
    /// permissionless) -- anyone who has the real metadata content (and therefore knows it
    /// hashes to the pinned `specHash`) may publish its location. Idempotent-safe on an
    /// identical repeat, same convention as `register()`; a DIFFERENT `metadataURI` for an
    /// already-published adapter reverts -- there is no update path, matching every other
    /// "no re-registration" surface in this contract.
    /// @dev **Disclosed limitation, inherent to on-chain hash commitments, not unique to this
    /// function:** this contract cannot and does not fetch `metadataURI` or verify its content
    /// actually hashes to `specHash` -- the same "commitments on-chain, content off-chain"
    /// posture BCC commitments and pack content hashes (`docs/SPEC.md` §7.1) already use
    /// throughout this protocol. A caller relying on `isInstallable() == true` SHOULD
    /// independently fetch `metadataURI` and verify `keccak256(content) == specHash` before
    /// trusting it; this function only proves SOMEONE claimed a location, not that the claim is
    /// honest.
    function publishIdentity(address adapter, string calldata metadataURI) external {
        AdapterInfo memory info = adapters[adapter];
        if (!info.registered) revert AdapterNotRegistered(adapter);
        if (bytes(metadataURI).length == 0) revert EmptyMetadataURI();

        string memory existing = identityMetadataURI[adapter];
        if (bytes(existing).length != 0) {
            if (keccak256(bytes(existing)) != keccak256(bytes(metadataURI))) {
                revert IdentityAlreadyPublishedWithDifferentURI(adapter, existing);
            }
            return;
        }

        identityMetadataURI[adapter] = metadataURI;
        emit AdapterIdentityPublished(adapter, metadataURI, info.specHash);
    }

    /// @notice Whether `adapter` may be installed into some future gate path WITHOUT an explicit
    /// operator override.
    /// @dev `true` iff `adapter` is registered AND has a published identity (`publishIdentity`)
    /// -- both halves of `docs/SPEC.md` §7.2 R5 this registry can express on-chain: a pinned
    /// version hash (`specHash`, set at registration) and a claimed location for its published,
    /// machine-readable source (`identityMetadataURI`, set here). What this function CANNOT and
    /// does not verify -- whether that location actually resolves to real content matching the
    /// hash -- is R5's own disclosed limitation (see `publishIdentity`), not something a future
    /// caller should treat this `true` as covering. A caller wiring this registry into an actual
    /// gate path that wants a stronger guarantee still needs its own independent verification or
    /// operator-override mechanism; this function gives it a real, checkable floor, not a proof.
    function isInstallable(address adapter) external view returns (bool) {
        AdapterInfo memory info = adapters[adapter];
        return info.registered && bytes(identityMetadataURI[adapter]).length != 0;
    }

    /// @notice Calls `adapter.check(subject, amount)`, forwarding at most that adapter's own
    /// registered `declaredGasBound`. Returns `true` if the call succeeds; otherwise reverts.
    /// @dev Two distinct revert paths, deliberately not collapsed into one:
    /// - The adapter's OWN rejection reason is bubbled up UNCHANGED (the exact revert data,
    ///   selector and all) -- a caller inspecting the revert sees precisely what the adapter
    ///   itself would have thrown, as if it had been called directly.
    /// - `AdapterExceededGasBound` fires when the call fails with ZERO-LENGTH returndata -- the
    ///   signature of exhausting the forwarded gas stipend before any revert reason could be
    ///   produced.
    /// **Disclosed limitation, not proven:** a bare `revert()` with no reason string or custom
    /// error from an otherwise well-behaved adapter is INDISTINGUISHABLE from true out-of-gas by
    /// this heuristic -- both produce zero-length returndata, and both are reported as
    /// `AdapterExceededGasBound` even when the real cause was the adapter choosing not to explain
    /// itself. Every adapter registered here should always revert with a typed error (R2's own
    /// totality obligation already asks for this), which sidesteps the ambiguity in practice, but
    /// this contract has no way to enforce that an adapter actually does so.
    function evaluate(address adapter, address subject, uint256 amount) external returns (bool) {
        AdapterInfo memory info = adapters[adapter];
        if (!info.registered) revert AdapterNotRegistered(adapter);

        try IAdapter(adapter).check{gas: info.declaredGasBound}(subject, amount) {
            return true;
        } catch (bytes memory reason) {
            if (reason.length == 0) {
                revert AdapterExceededGasBound(adapter, info.declaredGasBound);
            }
            assembly {
                revert(add(reason, 32), mload(reason))
            }
        }
    }
}
