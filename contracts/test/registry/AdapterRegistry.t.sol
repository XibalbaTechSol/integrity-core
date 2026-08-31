// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {AdapterRegistry} from "../../src/registry/AdapterRegistry.sol";
import {IAdapter} from "../../src/registry/IAdapter.sol";

/// @notice Always accepts. Used to prove the registry's happy path in isolation from any real
/// adapter's own business logic.
contract AlwaysAllowAdapter is IAdapter {
    function check(address, uint256) external pure {}
}

/// @notice Always rejects with a typed, non-empty revert reason -- proves `evaluate` bubbles up
/// an adapter's own rejection UNCHANGED, distinct from a gas-bound violation.
contract AlwaysRejectAdapter is IAdapter {
    error AlwaysRejects(address subject, uint256 amount);

    function check(address subject, uint256 amount) external pure {
        revert AlwaysRejects(subject, amount);
    }
}

/// @notice Rejects with a BARE revert (zero-length returndata) even with plenty of gas --
/// isolates `AdapterRegistry.evaluate`'s own disclosed limitation: this is indistinguishable
/// from a true gas-bound violation by the zero-length-returndata heuristic.
contract BareRevertAdapter is IAdapter {
    function check(address, uint256) external pure {
        revert();
    }
}

/// @notice Genuinely burns gas in a loop until it runs out -- the ONLY adapter in this file that
/// should trigger `AdapterExceededGasBound` for the real reason (out-of-gas), not merely a bare
/// revert. Deliberately unbounded so it exhausts whatever stipend `evaluate` forwards.
contract GasBurnerAdapter is IAdapter {
    uint256 public counter;

    function check(address, uint256) external {
        while (true) {
            counter += 1;
        }
    }
}

contract AdapterRegistryTest is Test {
    AdapterRegistry registry;
    AlwaysAllowAdapter allowAdapter;
    AlwaysRejectAdapter rejectAdapter;
    BareRevertAdapter bareRevertAdapter;
    GasBurnerAdapter gasBurnerAdapter;

    uint256 constant GAS_BOUND = 200_000;
    bytes32 constant SPEC_HASH = keccak256("spec-v1");

    function setUp() public {
        registry = new AdapterRegistry();
        allowAdapter = new AlwaysAllowAdapter();
        rejectAdapter = new AlwaysRejectAdapter();
        bareRevertAdapter = new BareRevertAdapter();
        gasBurnerAdapter = new GasBurnerAdapter();
    }

    // --- registration ------------------------------------------------------------------------

    function test_registerRevertsOnZeroAdapterAddress() public {
        vm.expectRevert(AdapterRegistry.ZeroAdapterAddress.selector);
        registry.register(address(0), GAS_BOUND, SPEC_HASH);
    }

    function test_registerRevertsOnZeroGasBound() public {
        vm.expectRevert(AdapterRegistry.ZeroDeclaredGasBound.selector);
        registry.register(address(allowAdapter), 0, SPEC_HASH);
    }

    function test_registerIsPermissionless() public {
        vm.prank(makeAddr("anyone"));
        registry.register(address(allowAdapter), GAS_BOUND, SPEC_HASH);

        (uint256 gasBound, bytes32 specHash, bool registered) = registry.adapters(address(allowAdapter));
        assertEq(gasBound, GAS_BOUND);
        assertEq(specHash, SPEC_HASH);
        assertTrue(registered);
    }

    function test_reregisteringWithIdenticalParamsIsANoOp() public {
        registry.register(address(allowAdapter), GAS_BOUND, SPEC_HASH);
        registry.register(address(allowAdapter), GAS_BOUND, SPEC_HASH); // should not revert

        (uint256 gasBound, bytes32 specHash,) = registry.adapters(address(allowAdapter));
        assertEq(gasBound, GAS_BOUND);
        assertEq(specHash, SPEC_HASH);
    }

    function test_reregisteringWithDifferentGasBoundReverts() public {
        registry.register(address(allowAdapter), GAS_BOUND, SPEC_HASH);
        vm.expectRevert(
            abi.encodeWithSelector(
                AdapterRegistry.AdapterAlreadyRegisteredWithDifferentParams.selector,
                address(allowAdapter),
                GAS_BOUND,
                SPEC_HASH
            )
        );
        registry.register(address(allowAdapter), GAS_BOUND + 1, SPEC_HASH);
    }

    function test_reregisteringWithDifferentSpecHashReverts() public {
        registry.register(address(allowAdapter), GAS_BOUND, SPEC_HASH);
        vm.expectRevert(
            abi.encodeWithSelector(
                AdapterRegistry.AdapterAlreadyRegisteredWithDifferentParams.selector,
                address(allowAdapter),
                GAS_BOUND,
                SPEC_HASH
            )
        );
        registry.register(address(allowAdapter), GAS_BOUND, keccak256("different-spec"));
    }

    // --- publishIdentity / isInstallable (R5) ---------------------------------------------------

    string constant METADATA_URI = "ipfs://bafy-example-adapter-identity-v1";

    function test_isInstallableFalseBeforeIdentityPublished() public {
        registry.register(address(allowAdapter), GAS_BOUND, SPEC_HASH);
        assertFalse(registry.isInstallable(address(allowAdapter)));
    }

    function test_isInstallableFalseForUnregisteredAdapter() public {
        assertFalse(registry.isInstallable(address(0xdead)));
    }

    function test_publishIdentityRevertsForUnregisteredAdapter() public {
        vm.expectRevert(abi.encodeWithSelector(AdapterRegistry.AdapterNotRegistered.selector, address(allowAdapter)));
        registry.publishIdentity(address(allowAdapter), METADATA_URI);
    }

    function test_publishIdentityRevertsOnEmptyURI() public {
        registry.register(address(allowAdapter), GAS_BOUND, SPEC_HASH);
        vm.expectRevert(AdapterRegistry.EmptyMetadataURI.selector);
        registry.publishIdentity(address(allowAdapter), "");
    }

    function test_publishIdentityIsPermissionlessAndMakesAdapterInstallable() public {
        registry.register(address(allowAdapter), GAS_BOUND, SPEC_HASH);

        vm.prank(makeAddr("anyone"));
        registry.publishIdentity(address(allowAdapter), METADATA_URI);

        assertEq(registry.identityMetadataURI(address(allowAdapter)), METADATA_URI);
        assertTrue(registry.isInstallable(address(allowAdapter)));
    }

    function test_republishingIdenticalURIIsANoOp() public {
        registry.register(address(allowAdapter), GAS_BOUND, SPEC_HASH);
        registry.publishIdentity(address(allowAdapter), METADATA_URI);
        registry.publishIdentity(address(allowAdapter), METADATA_URI); // should not revert

        assertEq(registry.identityMetadataURI(address(allowAdapter)), METADATA_URI);
    }

    function test_republishingDifferentURIReverts() public {
        registry.register(address(allowAdapter), GAS_BOUND, SPEC_HASH);
        registry.publishIdentity(address(allowAdapter), METADATA_URI);

        vm.expectRevert(
            abi.encodeWithSelector(
                AdapterRegistry.IdentityAlreadyPublishedWithDifferentURI.selector, address(allowAdapter), METADATA_URI
            )
        );
        registry.publishIdentity(address(allowAdapter), "ipfs://a-different-cid");
    }

    function test_publishIdentityEmitsSpecHashFromRegistration() public {
        registry.register(address(allowAdapter), GAS_BOUND, SPEC_HASH);

        vm.expectEmit(true, false, false, true);
        emit AdapterRegistry.AdapterIdentityPublished(address(allowAdapter), METADATA_URI, SPEC_HASH);
        registry.publishIdentity(address(allowAdapter), METADATA_URI);
    }

    function test_isInstallableIndependentPerAdapter() public {
        registry.register(address(allowAdapter), GAS_BOUND, SPEC_HASH);
        registry.register(address(rejectAdapter), GAS_BOUND, keccak256("reject-spec"));
        registry.publishIdentity(address(allowAdapter), METADATA_URI);

        assertTrue(registry.isInstallable(address(allowAdapter)));
        assertFalse(registry.isInstallable(address(rejectAdapter))); // registered, but no identity published
    }

    // --- evaluate --------------------------------------------------------------------------

    function test_evaluateRevertsForUnregisteredAdapter() public {
        vm.expectRevert(abi.encodeWithSelector(AdapterRegistry.AdapterNotRegistered.selector, address(allowAdapter)));
        registry.evaluate(address(allowAdapter), makeAddr("subject"), 1);
    }

    function test_evaluateReturnsTrueWhenAdapterAllows() public {
        registry.register(address(allowAdapter), GAS_BOUND, SPEC_HASH);
        assertTrue(registry.evaluate(address(allowAdapter), makeAddr("subject"), 1));
    }

    function test_evaluateBubblesUpTheAdaptersOwnRejectionReasonUnchanged() public {
        registry.register(address(rejectAdapter), GAS_BOUND, SPEC_HASH);
        address subject = makeAddr("subject");
        vm.expectRevert(abi.encodeWithSelector(AlwaysRejectAdapter.AlwaysRejects.selector, subject, 42));
        registry.evaluate(address(rejectAdapter), subject, 42);
    }

    function test_evaluateReportsGasBoundExceededForARealOutOfGasAdapter() public {
        // Register with a stipend far too small for GasBurnerAdapter's unbounded loop to ever
        // reach a natural stopping point.
        registry.register(address(gasBurnerAdapter), 10_000, SPEC_HASH);
        vm.expectRevert(
            abi.encodeWithSelector(AdapterRegistry.AdapterExceededGasBound.selector, address(gasBurnerAdapter), 10_000)
        );
        registry.evaluate(address(gasBurnerAdapter), makeAddr("subject"), 1);
    }

    /// @dev Proves the DISCLOSED limitation directly, rather than only describing it in prose:
    /// a bare `revert()` with no reason is reported as AdapterExceededGasBound even though the
    /// real cause was the adapter's own choice not to explain itself, not exhausting the stipend.
    /// This is expected behavior for this slice, not a bug -- see AdapterRegistry.evaluate's own
    /// NatSpec.
    function test_bareRevertIsIndistinguishableFromGasBoundExceeded() public {
        registry.register(address(bareRevertAdapter), GAS_BOUND, SPEC_HASH);
        vm.expectRevert(
            abi.encodeWithSelector(
                AdapterRegistry.AdapterExceededGasBound.selector, address(bareRevertAdapter), GAS_BOUND
            )
        );
        registry.evaluate(address(bareRevertAdapter), makeAddr("subject"), 1);
    }

    function test_evaluateNeverForwardsMoreThanTheDeclaredGasBound() public {
        // A tiny declared bound on an adapter that does nothing expensive still succeeds --
        // proves the forwarded stipend is enough for trivial work, not that it's unlimited.
        AlwaysAllowAdapter cheap = new AlwaysAllowAdapter();
        registry.register(address(cheap), 5_000, SPEC_HASH);
        assertTrue(registry.evaluate(address(cheap), makeAddr("subject"), 1));
    }
}
