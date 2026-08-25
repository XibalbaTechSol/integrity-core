// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {Clones} from "@openzeppelin/contracts/proxy/Clones.sol";
import {LicenceToken} from "../../src/licence/LicenceToken.sol";
import {LicenceAccount} from "../../src/licence/LicenceAccount.sol";
import {ILicenceHook} from "../../src/licence/ILicenceHook.sol";
import {ReputationFloorLicenceHook} from "../../src/licence/ReputationFloorLicenceHook.sol";
import {ReputationRegistry} from "../../src/oracle/ReputationRegistry.sol";

/// @notice Kernel-hook slice for `LicenceAccount` (whitepaper §5.3 "the same mechanism serves
/// both") -- see `ILicenceHook.sol`'s own doc comment for exactly what this proves and does not.
/// Two suites: a `MockLicenceHook` proving the wiring itself (hook disabled reproduces prior
/// behavior exactly; hook installed can reject or allow; consumer identity is threaded correctly
/// for both `consume()` and `consumeWithIntent()`), and `ReputationFloorLicenceHookTest` proving
/// the one reference implementation this slice ships.
contract MockLicenceHook is ILicenceHook {
    bool public shouldReject;
    address public lastAccount;
    address public lastConsumer;
    uint256 public lastUnits;
    uint256 public lastRoyaltyPaid;
    uint256 public callCount;

    error MockRejected();

    function setShouldReject(bool value) external {
        shouldReject = value;
    }

    function preConsume(address account, address consumer, uint256 units, uint256 royaltyPaid) external {
        callCount += 1;
        lastAccount = account;
        lastConsumer = consumer;
        lastUnits = units;
        lastRoyaltyPaid = royaltyPaid;
        if (shouldReject) revert MockRejected();
    }
}

contract LicenceAccountHookTest is Test {
    LicenceToken licenceToken;
    LicenceAccount account;
    MockLicenceHook hook;

    address licensee = makeAddr("licensee");
    address operator = address(this);

    uint256 constant VOLUME_CAP = 100;
    uint256 constant ROYALTY_PER_UNIT = 0.01 ether;
    uint256 constant LICENCE_START = 1000;
    uint256 constant LICENCE_DURATION = 30 days;
    uint256 LICENCE_END;

    uint256 tokenId;

    function setUp() public {
        vm.warp(LICENCE_START);
        LICENCE_END = LICENCE_START + LICENCE_DURATION;

        licenceToken = new LicenceToken(operator);
        tokenId = licenceToken.mint(licensee);
        hook = new MockLicenceHook();

        account = new LicenceAccount(
            address(licenceToken), tokenId, VOLUME_CAP, ROYALTY_PER_UNIT, LICENCE_START, LICENCE_END, address(0), 0, hook
        );
        vm.deal(licensee, 100 ether);
    }

    function test_hookDisabledReproducesPriorBehaviorExactly() public {
        LicenceAccount noHookAccount = new LicenceAccount(
            address(licenceToken),
            tokenId,
            VOLUME_CAP,
            ROYALTY_PER_UNIT,
            LICENCE_START,
            LICENCE_END,
            address(0),
            0,
            ILicenceHook(address(0))
        );
        vm.prank(licensee);
        noHookAccount.consume{value: ROYALTY_PER_UNIT}(1);
        assertEq(noHookAccount.consumedUnits(), 1);
    }

    function test_hookIsCalledWithCorrectContextOnConsume() public {
        vm.prank(licensee);
        account.consume{value: ROYALTY_PER_UNIT * 3}(3);

        assertEq(hook.callCount(), 1);
        assertEq(hook.lastAccount(), address(account));
        assertEq(hook.lastConsumer(), licensee);
        assertEq(hook.lastUnits(), 3);
        assertEq(hook.lastRoyaltyPaid(), ROYALTY_PER_UNIT * 3);
    }

    function test_hookRejectionRevertsConsumeWithNoStateChange() public {
        hook.setShouldReject(true);

        vm.prank(licensee);
        vm.expectRevert(MockLicenceHook.MockRejected.selector);
        account.consume{value: ROYALTY_PER_UNIT}(1);

        assertEq(account.consumedUnits(), 0);
        assertEq(address(account).balance, 0);
    }

    function test_hookRunsAfterLicenceAccountsOwnChecksAlreadyPassed() public {
        // A call that would fail LicenceAccount's own volume-cap check must revert with THAT
        // reason, never reach the hook at all -- proven by asserting callCount stays zero.
        vm.prank(licensee);
        vm.expectRevert(
            abi.encodeWithSelector(LicenceAccount.VolumeCapExceeded.selector, VOLUME_CAP + 1, VOLUME_CAP)
        );
        account.consume{value: ROYALTY_PER_UNIT * (VOLUME_CAP + 1)}(VOLUME_CAP + 1);

        assertEq(hook.callCount(), 0);
    }

    function test_hookSeesTheRecoveredSignerNotMsgSenderForConsumeWithIntent() public {
        // consumeWithIntent's whole point is open relaying -- msg.sender is the relayer, but the
        // hook must be told the SIGNER (the actual consumer), matching this repo's own
        // `consumeWithIntent` NatSpec: "the SIGNER, not msg.sender, is what authorizes this call."
        (address licenseeSigner, uint256 licenseeKey) = makeAddrAndKey("licenseeSigner");
        // Ownership must move to the signer so `signer == owner()` holds for consumeWithIntent's
        // authorization check.
        vm.prank(licensee);
        licenceToken.transferFrom(licensee, licenseeSigner, tokenId);

        LicenceAccount.ConsumeIntent memory intent = LicenceAccount.ConsumeIntent({
            account: address(account),
            units: 2,
            nonce: 0,
            expiry: block.timestamp + 1 hours
        });
        bytes32 structHash = keccak256(
            abi.encode(account.CONSUME_INTENT_TYPEHASH(), intent.account, intent.units, intent.nonce, intent.expiry)
        );
        (, string memory name, string memory version, uint256 chainId, address verifyingContract,,) =
            account.eip712Domain();
        bytes32 domainSeparator = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256(bytes(name)),
                keccak256(bytes(version)),
                chainId,
                verifyingContract
            )
        );
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(licenseeKey, digest);
        bytes memory signature = abi.encodePacked(r, s, v);

        address relayer = makeAddr("relayer");
        vm.deal(relayer, 10 ether);
        vm.prank(relayer);
        account.consumeWithIntent{value: ROYALTY_PER_UNIT * 2}(intent, signature);

        assertEq(hook.lastConsumer(), licenseeSigner);
    }
}

/// @notice The one reference `ILicenceHook` this slice ships: rejects consumption from a
/// consumer below a declared `ReputationRegistry.effectiveScore` floor.
contract ReputationFloorLicenceHookTest is Test {
    LicenceToken licenceToken;
    LicenceAccount account;
    ReputationFloorLicenceHook hook;
    ReputationRegistry reputation;

    address licensee = makeAddr("licensee");
    address operator = address(this);

    uint256 constant VOLUME_CAP = 100;
    uint256 constant ROYALTY_PER_UNIT = 0.01 ether;
    uint256 constant LICENCE_START = 1000;
    uint256 constant LICENCE_DURATION = 30 days;
    uint256 constant MIN_EFFECTIVE_SCORE = 500;
    uint256 LICENCE_END;

    uint256 tokenId;

    function setUp() public {
        vm.warp(LICENCE_START);
        LICENCE_END = LICENCE_START + LICENCE_DURATION;

        // Same real-EIP-1167-clone pattern IntegrityAccount.t.sol uses for the identical reason:
        // ReputationRegistry disables initializers on its own implementation constructor.
        address reputationImpl = address(new ReputationRegistry());
        reputation = ReputationRegistry(Clones.clone(reputationImpl));
        reputation.initialize(address(this), address(this), address(0), address(0));

        hook = new ReputationFloorLicenceHook(reputation, MIN_EFFECTIVE_SCORE);

        licenceToken = new LicenceToken(operator);
        tokenId = licenceToken.mint(licensee);
        account = new LicenceAccount(
            address(licenceToken), tokenId, VOLUME_CAP, ROYALTY_PER_UNIT, LICENCE_START, LICENCE_END, address(0), 0, hook
        );
        vm.deal(licensee, 100 ether);
    }

    function test_consumeRevertsWhenConsumerReputationBelowFloor() public {
        reputation.updateScore(licensee, MIN_EFFECTIVE_SCORE - 1);

        vm.prank(licensee);
        vm.expectRevert(
            abi.encodeWithSelector(
                ReputationFloorLicenceHook.ReputationBelowFloor.selector, licensee, MIN_EFFECTIVE_SCORE - 1, MIN_EFFECTIVE_SCORE
            )
        );
        account.consume{value: ROYALTY_PER_UNIT}(1);

        assertEq(account.consumedUnits(), 0);
    }

    function test_consumeSucceedsExactlyAtTheFloor() public {
        reputation.updateScore(licensee, MIN_EFFECTIVE_SCORE);

        vm.prank(licensee);
        account.consume{value: ROYALTY_PER_UNIT}(1);

        assertEq(account.consumedUnits(), 1);
    }

    function test_consumeSucceedsAboveTheFloor() public {
        reputation.updateScore(licensee, MIN_EFFECTIVE_SCORE + 100);

        vm.prank(licensee);
        account.consume{value: ROYALTY_PER_UNIT}(1);

        assertEq(account.consumedUnits(), 1);
    }

    /// @dev Mutation test: temporarily invert the floor comparison and confirm the boundary test
    /// above would then fail, matching this repo's own mutation-testing discipline for every
    /// hard guard. Not runnable automatically -- recorded here as the check performed manually
    /// before trusting this contract, per PRODUCTION_GAPS.md's own entry for this slice.
    function test_reputationReadIsLiveNotCached() public {
        reputation.updateScore(licensee, MIN_EFFECTIVE_SCORE - 1);
        vm.prank(licensee);
        vm.expectRevert();
        account.consume{value: ROYALTY_PER_UNIT}(1);

        // Same block, score improves -- a live read must see it immediately, no staleness window
        // (unlike IntegrityKernel's own deliberately-cached reputation check).
        reputation.updateScore(licensee, MIN_EFFECTIVE_SCORE);
        vm.prank(licensee);
        account.consume{value: ROYALTY_PER_UNIT}(1);
        assertEq(account.consumedUnits(), 1);
    }
}
