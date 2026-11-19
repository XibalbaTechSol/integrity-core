// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import { Test } from "forge-std/Test.sol";
import { AgentRegistry } from "../../src/framework/AgentRegistry.sol";
import { DomainRegistry } from "../../src/framework/DomainRegistry.sol";
import { MockGovernedAccount } from "../wallet/mocks/MockGovernedAccount.sol";
import { MockAccountVerifier } from "../wallet/mocks/MockAccountVerifier.sol";
import { MockOperationContext } from "../wallet/mocks/MockOperationContext.sol";
import {
    MockAgentRegistry,
    MockAISRegistry,
    MockStakeVault
} from "../wallet/mocks/MockTrustLayer.sol";
import { IntegrityHook, IAgentRegistryView, IAISRegistryView, IStakeVaultView } from "../../src/wallet/IntegrityHook.sol";
import { IOperationContext } from "../../src/wallet/IOperationContext.sol";
import { IAccountVerifier } from "../../src/wallet/IAccountVerifier.sol";

contract LyingAccount {
    function isModuleInstalled(uint256, address, bytes calldata) external pure returns (bool) {
        return true;
    }
}

contract AgentRegistryV3Test is Test {
    bytes32 internal constant PUBKEY = 0xea4a6c63e29c520abef5507b132ec5f9954776aebebe7b92421eea691446d22c;
    bytes32 internal constant FINGERPRINT = 0xfe812c12f3ab4ce6ac5db69ac352f906cb1b11ef43fb33e252ef7ff552263889;

    address internal admin = makeAddr("admin");
    uint256 internal attesterPk = 0xA77E57;
    address internal attester;
    address internal guardian = makeAddr("guardian");
    address internal otherOwner = makeAddr("otherOwner");

    AgentRegistry internal registry;
    DomainRegistry internal domains;
    IntegrityHook internal hook;
    MockAccountVerifier internal verifier;
    MockOperationContext internal ctx;
    MockAISRegistry internal ais;
    MockStakeVault internal vault;

    bytes32 internal domainId;
    bytes32 internal bareDomainId;

    function setUp() public {
        attester = vm.addr(attesterPk);

        domains = new DomainRegistry(admin);
        registry = new AgentRegistry(admin, address(domains));

        ctx = new MockOperationContext();
        verifier = new MockAccountVerifier();
        ais = new MockAISRegistry();
        vault = new MockStakeVault();

        hook = new IntegrityHook(
            admin,
            IAgentRegistryView(address(registry)),
            IAISRegistryView(address(ais)),
            IStakeVaultView(address(vault)),
            IOperationContext(address(ctx)),
            0,
            1 days
        );

        vm.startPrank(admin);
        domains.grantRole(domains.REGISTRAR_ROLE(), address(registry));
        registry.addAttester(attester);
        registry.setIntegrityHook(address(hook));
        registry.setAccountVerifier(IAccountVerifier(address(verifier)));
        domainId = domains.registerDomain("health", DomainRegistry.JoinMode.Open);
        bareDomainId = domains.registerDomain("bare", DomainRegistry.JoinMode.Open);
        vm.stopPrank();
    }

    function _attest(bytes32 pubkey, address g, address actor, bytes32 dom, string memory uri, uint256 deadline)
        internal
        view
        returns (bytes memory)
    {
        bytes32 digest = registry.registerDigest(pubkey, g, actor, dom, uri, deadline);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(attesterPk, digest);
        return abi.encodePacked(r, s, v);
    }

    function _createGovernedAccount(address owner) internal returns (MockGovernedAccount acc) {
        acc = new MockGovernedAccount();
        verifier.setAccount(address(acc), true, owner);
        acc.installModule(4, address(hook), abi.encode(uint32(1 days), uint32(0)));
    }

    function test_bind_governed_actor_succeeds_without_domain() public {
        MockGovernedAccount acc = _createGovernedAccount(guardian);
        uint256 dl = block.timestamp + 1 hours;
        bytes memory proof = _attest(PUBKEY, guardian, address(acc), bytes32(0), "ipfs://meta", dl);

        // Actor registers existence + binds actor without domain (domainId = 0)
        vm.prank(address(acc));
        bytes32 fp = registry.register(
            PUBKEY, guardian, address(acc), bytes32(0), "ipfs://meta", dl, 1, proof, ""
        );

        assertEq(fp, FINGERPRINT);
        assertTrue(registry.isRegisteredAgent(address(acc)));
        assertEq(registry.agentOf(address(acc)), FINGERPRINT);
        assertEq(registry.resolve(fp).actor, address(acc));
        assertEq(registry.resolve(fp).domainId, bytes32(0));
    }

    function test_bind_reverts_GovernanceNotWired() public {
        // Fresh registry without hook or verifier wired
        AgentRegistry rawRegistry = new AgentRegistry(admin, address(domains));
        vm.prank(admin);
        rawRegistry.addAttester(attester);

        MockGovernedAccount acc = _createGovernedAccount(guardian);
        uint256 dl = block.timestamp + 1 hours;
        bytes32 digest = rawRegistry.registerDigest(PUBKEY, guardian, address(acc), bytes32(0), "", dl);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(attesterPk, digest);
        bytes memory proof = abi.encodePacked(r, s, v);

        vm.prank(address(acc));
        vm.expectRevert(AgentRegistry.GovernanceNotWired.selector);
        rawRegistry.register(PUBKEY, guardian, address(acc), bytes32(0), "", dl, 1, proof, "");
    }

    function test_bind_reverts_NotGoverned_when_hook_not_installed() public {
        MockGovernedAccount unhooked = new MockGovernedAccount();
        verifier.setAccount(address(unhooked), true, guardian);
        // Hook is not installed on unhooked

        assertFalse(registry.isGoverned(address(unhooked)));

        uint256 dl = block.timestamp + 1 hours;
        bytes memory proof = _attest(PUBKEY, guardian, address(unhooked), bytes32(0), "", dl);

        vm.prank(address(unhooked));
        vm.expectRevert(abi.encodeWithSelector(AgentRegistry.NotGoverned.selector, address(unhooked)));
        registry.register(PUBKEY, guardian, address(unhooked), bytes32(0), "", dl, 1, proof, "");
    }

    function test_lying_account_not_governed() public {
        LyingAccount liar = new LyingAccount();
        // Liar claims isModuleInstalled returns true, but verifier.verify(liar) returns genuine=false
        verifier.setAccount(address(liar), false, guardian);

        assertFalse(registry.isGoverned(address(liar)));

        uint256 dl = block.timestamp + 1 hours;
        bytes memory proof = _attest(PUBKEY, guardian, address(liar), bytes32(0), "", dl);

        vm.prank(address(liar));
        vm.expectRevert(abi.encodeWithSelector(AgentRegistry.NotGoverned.selector, address(liar)));
        registry.register(PUBKEY, guardian, address(liar), bytes32(0), "", dl, 1, proof, "");
    }

    function test_bind_reverts_GuardianNotOwner() public {
        // Account owner is otherOwner, but registration guardian is guardian
        MockGovernedAccount acc = _createGovernedAccount(otherOwner);

        assertTrue(registry.isGoverned(address(acc)));

        uint256 dl = block.timestamp + 1 hours;
        bytes memory proof = _attest(PUBKEY, guardian, address(acc), bytes32(0), "", dl);

        vm.prank(address(acc));
        vm.expectRevert(abi.encodeWithSelector(AgentRegistry.GuardianNotOwner.selector, guardian, otherOwner));
        registry.register(PUBKEY, guardian, address(acc), bytes32(0), "", dl, 1, proof, "");
    }

    function test_hook_uninstall_makes_actor_ungoverned() public {
        MockGovernedAccount acc = _createGovernedAccount(guardian);
        assertTrue(registry.isGoverned(address(acc)));

        // Uninstall hook module by Owner
        ctx.setRole(address(acc), IOperationContext.Role.Owner);
        acc.uninstallModule(4, address(hook), "");

        assertFalse(registry.isGoverned(address(acc)));
    }

    function test_setIntegrityHook_only_once() public {
        // Already set in setUp(), setting again reverts HookAlreadySet
        vm.prank(admin);
        vm.expectRevert(AgentRegistry.HookAlreadySet.selector);
        registry.setIntegrityHook(makeAddr("anotherHook"));

        // Non-admin call reverts
        vm.prank(makeAddr("nonAdmin"));
        vm.expectRevert();
        registry.setIntegrityHook(makeAddr("anotherHook"));
    }

    function test_setDomain_no_policy_required() public {
        MockGovernedAccount acc = _createGovernedAccount(guardian);
        uint256 dl = block.timestamp + 1 hours;
        bytes memory proof = _attest(PUBKEY, guardian, address(acc), bytes32(0), "", dl);

        vm.prank(address(acc));
        bytes32 fp = registry.register(
            PUBKEY, guardian, address(acc), bytes32(0), "", dl, 1, proof, ""
        );

        // bareDomainId has NO policy in policy registry
        vm.prank(guardian);
        registry.setDomain(fp, bareDomainId);

        assertEq(registry.resolve(fp).domainId, bareDomainId);
        assertTrue(domains.isMember(bareDomainId, address(acc)));
    }
}
