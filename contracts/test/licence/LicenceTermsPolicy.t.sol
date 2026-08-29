// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {ILicenceHook} from "../../src/licence/ILicenceHook.sol";
import {LicenceAccount} from "../../src/licence/LicenceAccount.sol";
import {LicenceToken} from "../../src/licence/LicenceToken.sol";
import {LicenceTermsPolicy, IAssuranceTierProvider} from "../../src/licence/LicenceTermsPolicy.sol";
import {AdapterRegistry} from "../../src/registry/AdapterRegistry.sol";
import {LicenceTermsContext} from "../../src/licence/ILicenceTermsHook.sol";
import {LicenceDelegationView} from "../../src/licence/ILicenceDelegationView.sol";

contract MockAssuranceTierProvider is IAssuranceTierProvider {
    mapping(address subject => uint256 tier) public tiers;

    function setTier(address subject, uint256 tier) external {
        tiers[subject] = tier;
    }

    function assuranceTier(address subject) external view returns (uint256) {
        return tiers[subject];
    }
}

contract LicenceTermsPolicyTest is Test {
    uint256 constant PRICE = 0.001 ether;
    bytes32 constant PURPOSE = keccak256("research");
    bytes32 constant INITIAL_HEAD = keccak256("genesis");
    address owner;
    LicenceAccount account;
    LicenceTermsPolicy policy;
    MockAssuranceTierProvider assurance;

    function setUp() public {
        owner = makeAddr("terms-owner");
        assurance = new MockAssuranceTierProvider();
        assurance.setTier(owner, 3);
        policy = new LicenceTermsPolicy(owner, PURPOSE, owner, true, false, assurance, 2, 1, INITIAL_HEAD);

        LicenceToken token = new LicenceToken(owner);
        vm.prank(owner);
        uint256 tokenId = token.mint(owner);
        account = new LicenceAccount(
            address(token), tokenId, 100, PRICE, 0, type(uint256).max, address(0), 0, ILicenceHook(address(policy)),
            AdapterRegistry(address(0)), address(0)
        );
        deal(address(account), 1 ether);
        deal(owner, 1 ether);
    }

    function test_allSixTermsPassOnTypedConsumption() public {
        bytes32 evidence = keccak256("evidence-1");
        LicenceTermsContext memory context = _context(INITIAL_HEAD, 1, evidence);
        vm.prank(owner);
        account.consumeWithTerms{value: PRICE}(1, context);
        assertEq(account.consumedUnits(), 1);
        assertEq(policy.memoryHead(owner), context.nextMemoryHead);
        assertEq(policy.memorySequence(owner), 1);
        assertTrue(policy.activeLicensee(owner));
    }

    function test_untypedConsumptionFailsClosedWhenFullPolicyInstalled() public {
        vm.prank(owner);
        vm.expectRevert(LicenceTermsPolicy.TermsContextRequired.selector);
        account.consume{value: PRICE}(1);
    }

    function test_fieldOfUseAndDerivativeTermsAreEnforced() public {
        LicenceTermsContext memory wrongPurpose = _context(INITIAL_HEAD, 1, keccak256("a"));
        wrongPurpose.purposeHash = keccak256("wrong");
        vm.prank(owner);
        vm.expectRevert(abi.encodeWithSelector(LicenceTermsPolicy.FieldOfUseDenied.selector, PURPOSE, wrongPurpose.purposeHash));
        account.consumeWithTerms{value: PRICE}(1, wrongPurpose);

        LicenceTermsContext memory derivative = _context(INITIAL_HEAD, 1, keccak256("b"));
        derivative.derivative = true;
        vm.prank(owner);
        vm.expectRevert(LicenceTermsPolicy.DerivativeRightsDenied.selector);
        account.consumeWithTerms{value: PRICE}(1, derivative);
    }

    function test_assuranceAndMemoryContinuityAreEnforced() public {
        assurance.setTier(owner, 1);
        vm.prank(owner);
        vm.expectRevert(abi.encodeWithSelector(LicenceTermsPolicy.AssuranceTierInsufficient.selector, owner, 1, 2));
        account.consumeWithTerms{value: PRICE}(1, _context(INITIAL_HEAD, 1, keccak256("c")));

        assurance.setTier(owner, 3);
        LicenceTermsContext memory forked = _context(keccak256("wrong-prior"), 1, keccak256("d"));
        vm.prank(owner);
        vm.expectRevert(
            abi.encodeWithSelector(LicenceTermsPolicy.MemoryPriorHeadMismatch.selector, INITIAL_HEAD, forked.priorMemoryHead)
        );
        account.consumeWithTerms{value: PRICE}(1, forked);
    }

    function test_licenseeAndExclusivityAreEnforcedByPolicy() public {
        address stranger = makeAddr("stranger-licensee");
        LicenceTermsContext memory context = _context(INITIAL_HEAD, 1, keccak256("e"));
        vm.expectRevert(abi.encodeWithSelector(LicenceTermsPolicy.LicenseeNotAllowed.selector, stranger));
        policy.preConsumeWithTerms(address(account), stranger, 1, PRICE, context);

        vm.prank(owner);
        policy.setAllowedLicensee(stranger, true);
        vm.expectRevert(abi.encodeWithSelector(LicenceTermsPolicy.ExclusiveLicenseeMismatch.selector, owner, stranger));
        policy.preConsumeWithTerms(address(account), stranger, 1, PRICE, context);
    }

    function test_sharedDelegationViewReturnsPolicyAndConsumerState() public {
        LicenceDelegationView memory beforeView = policy.delegationView(owner);
        assertEq(beforeView.fieldOfUseHash, PURPOSE);
        assertEq(beforeView.requiredLicensee, owner);
        assertTrue(beforeView.exclusive);
        assertFalse(beforeView.derivativeRights);
        assertEq(beforeView.observedAssuranceTier, 3);
        assertTrue(beforeView.allowedLicensee);
        assertFalse(beforeView.activeLicensee);
        assertEq(beforeView.memoryHead, bytes32(0));
        assertEq(beforeView.memorySequence, 0);

        vm.prank(owner);
        account.consumeWithTerms{value: PRICE}(1, _context(INITIAL_HEAD, 1, keccak256("view")));

        LicenceDelegationView memory afterView = policy.delegationView(owner);
        assertTrue(afterView.activeLicensee);
        assertEq(afterView.activeLicenseeCount, 1);
        assertEq(afterView.memorySequence, 1);
        assertEq(afterView.memoryHead, _context(INITIAL_HEAD, 1, keccak256("view")).nextMemoryHead);
        assertEq(afterView.exclusiveLicensee, owner);
    }

    function _context(bytes32 prior, uint256 sequence, bytes32 evidence)
        internal
        view
        returns (LicenceTermsContext memory context)
    {
        context.purposeHash = PURPOSE;
        context.priorMemoryHead = prior;
        context.memorySequence = sequence;
        context.evidenceHash = evidence;
        context.nextMemoryHead = keccak256(abi.encode(block.chainid, address(account), owner, sequence, evidence, prior));
    }
}
