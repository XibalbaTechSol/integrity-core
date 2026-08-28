// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {StdStorage, stdStorage} from "forge-std/StdStorage.sol";
import {Clones} from "@openzeppelin/contracts/proxy/Clones.sol";
import {
    ERC7579Utils,
    Mode,
    CallType,
    ExecType,
    ModeSelector,
    ModePayload
} from "@openzeppelin/contracts/account/utils/draft-ERC7579Utils.sol";
import {IntegrityAccount} from "../../src/kernel/IntegrityAccount.sol";
import {IntegrityKernel} from "../../src/kernel/IntegrityKernel.sol";
import {ReputationRegistry} from "../../src/oracle/ReputationRegistry.sol";
import {AdapterRegistry} from "../../src/registry/AdapterRegistry.sol";
import {ReputationFloorAdapter} from "../../src/registry/ReputationFloorAdapter.sol";

/// @notice The Phase III `registryHook`/`registryAdapter` slot on `IntegrityKernel`
/// (`PRODUCTION_GAPS.md` §54) -- a SECOND, independent additive precondition in `preCheck`,
/// alongside the existing cached reputation/assurance-tier checks. Deliberately a standalone
/// test file, not folded into `IntegrityAccount.t.sol`, matching how `LicenceAccountHook.t.sol`
/// isolated its own registry-hook coverage.
/// @dev **Halmos coverage does NOT extend to this configuration.** `HalmosKernelFixture.sol`
/// always constructs the kernel with `AdapterRegistry(address(0))` (disabled) -- Halmos verified
/// the six kernel properties still hold in that reachable configuration (6/6 passed,
/// `PRODUCTION_GAPS.md` §54's own record of the run), which proves adding this feature does not
/// regress the properties for anyone who leaves it off. It does NOT prove the properties hold
/// with the registry ENABLED -- that branch was unreachable in every path Halmos explored. This
/// file's coverage is concrete Foundry only, same disclosed gap category as `LicenceAccount`'s
/// own `hook`/`registryHook` slots.
contract IntegrityKernelRegistryHookTest is Test {
    using stdStorage for StdStorage;

    IntegrityAccount account;
    IntegrityKernel kernel;
    ReputationRegistry reputation;
    AdapterRegistry registry;
    ReputationFloorAdapter adapter;

    address signer;
    address guardian1;
    address guardian2;
    address guardian3;
    address[] guardianSet;
    address recipient;

    uint256 constant MODULE_ACTION_TIMELOCK = 3 days;
    uint256 constant RESCUE_TIMELOCK = 1 days;
    uint256 constant GUARDIAN_THRESHOLD = 2;
    uint256 constant PER_OP_BUDGET = 1 ether;
    uint256 constant CUMULATIVE_BUDGET = 3 ether;
    uint256 constant MIN_EFFECTIVE_SCORE = 500;
    uint256 constant REPUTATION_EPOCH_LENGTH = 3 days; // must be >= MODULE_ACTION_TIMELOCK
    uint256 constant REGISTRY_MIN_SCORE = 700; // deliberately a DIFFERENT, higher floor than the
    // kernel's own MIN_EFFECTIVE_SCORE, so a test can isolate which check actually fired.

    function setUp() public {
        signer = makeAddr("signer");
        guardian1 = makeAddr("guardian1");
        guardian2 = makeAddr("guardian2");
        guardian3 = makeAddr("guardian3");
        guardianSet = [guardian1, guardian2, guardian3];
        recipient = makeAddr("recipient");

        address reputationImpl = address(new ReputationRegistry());
        reputation = ReputationRegistry(Clones.clone(reputationImpl));
        reputation.initialize(address(this), address(this), address(0), address(0));

        registry = new AdapterRegistry();
        adapter = new ReputationFloorAdapter(reputation, REGISTRY_MIN_SCORE);
        registry.register(address(adapter), 200_000, keccak256("reputation-floor-v1"));

        address predictedAccount = vm.computeCreateAddress(address(this), vm.getNonce(address(this)) + 1);
        reputation.updateScore(predictedAccount, MIN_EFFECTIVE_SCORE); // above the KERNEL's own
        // floor but BELOW the registry adapter's higher floor -- isolates the new check.
        _setZkBoostExpiry(predictedAccount, block.timestamp + 7 days);

        kernel = new IntegrityKernel(
            predictedAccount,
            PER_OP_BUDGET,
            CUMULATIVE_BUDGET,
            address(reputation),
            MIN_EFFECTIVE_SCORE,
            REPUTATION_EPOCH_LENGTH,
            address(0),
            0,
            0,
            registry,
            address(adapter)
        );
        account = new IntegrityAccount(
            signer, address(kernel), MODULE_ACTION_TIMELOCK, guardianSet, GUARDIAN_THRESHOLD, RESCUE_TIMELOCK
        );
        assertEq(address(account), predictedAccount, "CREATE address prediction must match actual deployment");
        vm.deal(address(account), 10 ether);
    }

    function _setZkBoostExpiry(address subject, uint256 expiry) internal {
        stdstore.target(address(reputation)).sig("scores(address)").with_key(subject).depth(2).checked_write(expiry);
    }

    function _singleCallMode() internal pure returns (bytes32) {
        return Mode.unwrap(
            ERC7579Utils.encodeMode(
                ERC7579Utils.CALLTYPE_SINGLE, ERC7579Utils.EXECTYPE_DEFAULT, ModeSelector.wrap(0), ModePayload.wrap(0)
            )
        );
    }

    function test_constructorRevertsWhenRegistrySetButAdapterIsZero() public {
        vm.expectRevert(IntegrityKernel.ZeroRegistryAdapter.selector);
        new IntegrityKernel(
            address(account),
            PER_OP_BUDGET,
            CUMULATIVE_BUDGET,
            address(reputation),
            MIN_EFFECTIVE_SCORE,
            REPUTATION_EPOCH_LENGTH,
            address(0),
            0,
            0,
            registry,
            address(0)
        );
    }

    function test_executeRevertsWhenAccountBelowRegistryFloorEvenThoughKernelsOwnFloorPasses() public {
        // setUp's score (MIN_EFFECTIVE_SCORE = 500) clears the kernel's OWN floor but not the
        // registry adapter's higher one (700) -- isolates that the NEW check is what fires.
        uint256 accountBalanceBefore = address(account).balance;
        bytes memory executionCalldata = abi.encodePacked(recipient, uint256(0.1 ether), bytes(""));

        // effectiveScore applies the ZK boost this setUp granted -- 500 * 1.15 = 575, not the
        // raw 500 baseScore.
        uint256 boostedScore = (MIN_EFFECTIVE_SCORE * reputation.ZK_BOOST_BPS()) / reputation.BPS_DENOMINATOR();
        vm.expectRevert(
            abi.encodeWithSelector(
                ReputationFloorAdapter.ReputationBelowFloor.selector, address(account), boostedScore, REGISTRY_MIN_SCORE
            )
        );
        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);

        assertEq(address(account).balance, accountBalanceBefore, "a reverted execute must move zero funds");
    }

    function test_executeSucceedsWhenAccountMeetsBothFloors() public {
        reputation.updateScore(address(account), REGISTRY_MIN_SCORE);
        kernel.refreshReputationSnapshot();

        uint256 recipientBalanceBefore = recipient.balance;
        uint256 sendAmount = 0.1 ether;
        bytes memory executionCalldata = abi.encodePacked(recipient, sendAmount, bytes(""));

        vm.prank(address(account));
        account.execute(_singleCallMode(), executionCalldata);

        assertEq(recipient.balance, recipientBalanceBefore + sendAmount);
    }
}
