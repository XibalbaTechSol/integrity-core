// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {LicenceToken} from "../../src/licence/LicenceToken.sol";
import {LicenceAccount} from "../../src/licence/LicenceAccount.sol";
import {IERC6551Account, IERC6551Registry} from "../../src/licence/IERC6551.sol";

/// @notice Phase II tracer-bullet slice
/// (`docs/plans/2026-08-24-phase2-licence-account-tracer-bullet-proposal.md`): proves
/// `LicenceAccount` behaves identically whether reached directly (as `LicenceAccount.t.sol`
/// tests it) or through the REAL, live canonical ERC-6551 registry's minimal-proxy mechanism
/// (`createAccount`/`account`). Forks Base Sepolia rather than mocking the registry, matching
/// this repo's own "no silent mocks" ground rule -- the registry's `createAccount` deploys a
/// real ERC-1167 minimal proxy that `delegatecall`s into whatever implementation address it's
/// given; this test deploys a `LicenceAccount` as that implementation and confirms the proxy
/// the real registry produces actually works, not merely that the interface compiles.
///
/// @dev Skips (rather than failing) when no fork RPC is configured, since a live network
/// dependency should never silently break `forge test` in an offline environment -- this
/// mirrors the `Deploy*.s.sol` scripts' own network-dependent-but-not-default posture.
contract Erc6551RegistryIntegrationTest is Test {
    address constant REGISTRY = 0x000000006551c19487814612e58FE06813775758;

    LicenceToken licenceToken;
    LicenceAccount implementation;
    address licensee = makeAddr("licensee");

    uint256 constant VOLUME_CAP = 100;
    uint256 constant ROYALTY_PER_UNIT = 0.01 ether;
    uint256 licenceStart;
    uint256 licenceEnd;
    uint256 tokenId;

    function setUp() public {
        string memory rpcUrl = vm.envOr("BASE_SEPOLIA_RPC_URL", string("https://base-sepolia-rpc.publicnode.com"));
        try vm.createSelectFork(rpcUrl) {
            // forked successfully
        } catch {
            vm.skip(true);
        }

        // The registry must actually be live at the canonical address on whatever fork we
        // landed on -- refuse to silently pass against an empty address.
        if (REGISTRY.code.length == 0) {
            vm.skip(true);
        }

        licenceStart = block.timestamp;
        licenceEnd = block.timestamp + 30 days;

        licenceToken = new LicenceToken(address(this));
        tokenId = licenceToken.mint(licensee);

        // Per this contract's own NatSpec, one implementation contract per licence -- the
        // implementation's immutables are baked into ITS bytecode; a delegatecall proxy reads
        // them as inlined constants, not storage, so this works correctly through a proxy too.
        implementation =
            new LicenceAccount(address(licenceToken), tokenId, VOLUME_CAP, ROYALTY_PER_UNIT, licenceStart, licenceEnd);
    }

    function _predictedAndActual() internal returns (address predicted, address actual) {
        bytes32 salt = bytes32(0);
        predicted = IERC6551Registry(REGISTRY).account(
            address(implementation), salt, block.chainid, address(licenceToken), tokenId
        );
        actual = IERC6551Registry(REGISTRY).createAccount(
            address(implementation), salt, block.chainid, address(licenceToken), tokenId
        );
    }

    function test_registryProducesTheAddressItPredicts() public {
        (address predicted, address actual) = _predictedAndActual();
        assertEq(actual, predicted, "the real registry's account() prediction must match what createAccount() deploys");
        assertGt(predicted.code.length, 0, "the registry must have actually deployed proxy bytecode there");
    }

    function test_createAccountIsIdempotent() public {
        (, address first) = _predictedAndActual();
        bytes32 salt = bytes32(0);
        address second = IERC6551Registry(REGISTRY).createAccount(
            address(implementation), salt, block.chainid, address(licenceToken), tokenId
        );
        assertEq(second, first, "calling createAccount again for the same params must return the existing proxy, not redeploy");
    }

    function test_proxyDelegatesTokenCorrectly() public {
        (, address proxyAddr) = _predictedAndActual();
        LicenceAccount proxy = LicenceAccount(payable(proxyAddr));

        (uint256 chainId, address tokenContract, uint256 returnedTokenId) = proxy.token();
        assertEq(chainId, block.chainid);
        assertEq(tokenContract, address(licenceToken));
        assertEq(returnedTokenId, tokenId);
    }

    function test_proxyOwnerResolvesThroughTheRealNft() public {
        (, address proxyAddr) = _predictedAndActual();
        LicenceAccount proxy = LicenceAccount(payable(proxyAddr));
        assertEq(proxy.owner(), licensee);
    }

    function test_proxyEnforcesVolumeCapIdenticallyToDirectConstruction() public {
        (, address proxyAddr) = _predictedAndActual();
        LicenceAccount proxy = LicenceAccount(payable(proxyAddr));

        vm.deal(licensee, 10 ether);
        vm.prank(licensee);
        proxy.consume{value: VOLUME_CAP * ROYALTY_PER_UNIT}(VOLUME_CAP);
        assertEq(proxy.consumedUnits(), VOLUME_CAP);

        vm.prank(licensee);
        vm.expectRevert(abi.encodeWithSelector(LicenceAccount.VolumeCapExceeded.selector, 1, 0));
        proxy.consume{value: ROYALTY_PER_UNIT}(1);
    }

    function test_proxyEnforcesTransferDrainGuardIdenticallyToDirectConstruction() public {
        (, address proxyAddr) = _predictedAndActual();
        LicenceAccount proxy = LicenceAccount(payable(proxyAddr));

        vm.deal(licensee, 10 ether);
        vm.prank(licensee);
        proxy.consume{value: 10 * ROYALTY_PER_UNIT}(10);

        vm.prank(licensee);
        proxy.armTransfer(8 * ROYALTY_PER_UNIT);

        address payable recipient = payable(makeAddr("recipient"));
        vm.prank(licensee);
        vm.expectRevert(
            abi.encodeWithSelector(LicenceAccount.TransferArmedWithdrawalBlocked.selector, 7 * ROYALTY_PER_UNIT, 8 * ROYALTY_PER_UNIT)
        );
        proxy.execute(recipient, 3 * ROYALTY_PER_UNIT, "", 0);
    }
}
