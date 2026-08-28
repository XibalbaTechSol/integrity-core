// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {IAdapter} from "./IAdapter.sol";

/// @title AdapterRegistry
/// @notice Phase III tracer-bullet slice
/// (`docs/plans/2026-08-25-phase3-adapter-registry-tracer-bullet-proposal.md`): permissionless
/// registration of `IAdapter` contracts, plus metered-call enforcement of each adapter's own
/// self-declared gas bound (whitepaper §6.2 obligation R3).
/// @dev **What this proves:** R3 (bounded cost) is real -- `evaluate` never forwards more than
/// an adapter's own `declaredGasBound` to it, and a call that exhausts that stipend is
/// distinguished from an ordinary rejection (see `evaluate`'s own doc comment for the exact
/// heuristic and its disclosed limitation). Registration is permissionless and idempotent-safe:
/// registering the identical `(adapter, declaredGasBound, specHash)` twice is a harmless no-op;
/// registering the same `adapter` address with DIFFERENT params reverts -- there is no
/// re-registration path in this slice, conflicting or not.
///
/// **What this does NOT prove:** R1 (determinism) -- needs an off-chain differential-replay
/// admission suite this repo has never built, not a contract-level check. R4 (conservatism) --
/// structural only, by construction, IF a future caller only ever ANDs multiple adapters
/// together; this registry evaluates exactly ONE adapter per call and has no composition logic
/// of its own. R5 (attestation/staking) -- `isInstallable` always returns `false`; see its own
/// doc comment. Not wired into `IntegrityKernel` or `LicenceAccount`'s actual gate path -- this
/// slice proves the registry's own admission/metered-call machinery in isolation.
contract AdapterRegistry {
    error AdapterAlreadyRegisteredWithDifferentParams(
        address adapter, uint256 existingGasBound, bytes32 existingSpecHash
    );
    error AdapterNotRegistered(address adapter);
    error ZeroDeclaredGasBound();
    error ZeroAdapterAddress();
    error AdapterExceededGasBound(address adapter, uint256 declaredGasBound);

    struct AdapterInfo {
        uint256 declaredGasBound;
        bytes32 specHash;
        bool registered;
    }

    mapping(address adapter => AdapterInfo info) public adapters;

    event AdapterRegistered(address indexed adapter, uint256 declaredGasBound, bytes32 specHash);

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

    /// @notice Whether `adapter` may be installed into some future gate path WITHOUT an explicit
    /// operator override.
    /// @dev Always `false` in this slice. R5 ("published with source, a machine-readable spec,
    /// and at least one independent audit attestation before it is installable without operator
    /// override" -- whitepaper §6.2) needs the full §8 staking/attestation economics, not
    /// implemented here. This is the honest state of an unattested registry, not a bug -- see the
    /// proposal's own "real risk" section. A future caller wiring this registry into an actual
    /// gate path must supply its own operator-override mechanism; this function gives it nothing
    /// to lean on instead.
    function isInstallable(address) external pure returns (bool) {
        return false;
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
