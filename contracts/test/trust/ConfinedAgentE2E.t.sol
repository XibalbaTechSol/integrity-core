// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {GateRegistryFixture} from "./GateRegistryFixture.sol";
import {SovereignAgent} from "../../src/core/SovereignAgent.sol";
import {TrustConfig} from "../../src/trust/TrustConfig.sol";
import {PolicyRegistry} from "../../src/trust/PolicyRegistry.sol";

/// @dev Records the last selector it received; etched at the pack's fixed target addresses.
contract SelectorSink {
    bytes4 public last;

    fallback() external payable {
        last = msg.sig;
    }
}

/// @title ConfinedAgentE2E
/// @notice Registration v3 Phase 3: a policy pack compiled OFF-CHAIN by the SDK
/// (`integrity_sdk.core.pack_onchain.compile_onchain`, PR 3.1) confines a bound agent ON-CHAIN.
/// Every constant below was produced by the SDK from the same 3-edge section its unit test
/// (`tests/unit/test_core_pack_onchain.py::_section`) uses — this test is the cross-language
/// check that a Python-compiled root and Python-generated proofs verify in `PolicyRegistry`.
/// Regenerate with `compile_onchain(section)` + `proof_for(policy, edge)` if the leaf format changes.
contract ConfinedAgentE2E is GateRegistryFixture {
    address constant TOKEN = 0x00000000000000000000000000000000000000ca;
    address constant SPENDER = 0x00000000000000000000000000000000000000CB;

    bytes32 constant ROOT = 0x90c058f8926fcdcc16db49dc438cff3154ab14e504017983b90b5ab595a1c71a;
    bytes32 constant DOMAIN = 0x9005b4bf3e8c5705ff2b172ed7c0ff76f0096efed0943457e640b66da01b97d2; // keccak256("health")

    // Plain-call naming defaults: from = keccak256("agent"), relation = keccak256("calls"),
    // to = keccak256("<target lowercase>:<selector>").
    bytes32 constant FROM = 0x314c1dfbbccab41a44cf9fefc21e632eb8e01bc0346d4414114d4c3dd0e9fdf1;
    bytes32 constant REL = 0x57c33777248e86b84732f59da732bdb93102638009db91414866aaf3c52a8025;
    bytes32 constant TO_TRANSFER = 0x522caeb88bdfc2bec530a5fa4a6740c1ff8830ad3d77fe5b979c6469f42397d2;
    bytes32 constant TO_APPROVE = 0x33307dc3a27b18d1c7e744553fbc232c2125743460a43365db63a11b7ee42479;
    bytes32 constant TO_TRANSFER_FROM = 0x2dc82d12ce85a0d524a2d3931141d53ac476a94d5cc8cef854a40bc80e67e044;

    address governance = makeAddr("governance");
    SovereignAgent agent;
    address controller;

    function setUp() public {
        _deployRegistry(governance);
        bytes32 dom = _ensureDomain("health");
        assertEq(dom, DOMAIN, "SDK domain_id must equal DomainRegistry.domainId");

        TrustConfig cfg = new TrustConfig(governance);
        PolicyRegistry policy = new PolicyRegistry(governance);
        vm.startPrank(governance);
        policy.setGraphRoot(dom, ROOT);
        cfg.setPolicyRegistry(address(policy));
        agentRegistry.setTrustConfig(address(cfg));
        vm.stopPrank();

        SelectorSink sink = new SelectorSink();
        vm.etch(TOKEN, address(sink).code);
        vm.etch(SPENDER, address(sink).code);

        uint256 pk;
        (controller, pk) = makeAddrAndKey("confined-controller");
        agent = _newAgent("did:integrity:confined", controller);
        _bind(agent, pk, dom, controller);
    }

    function _p(bytes32 a, bytes32 b) internal pure returns (bytes32[] memory p) {
        p = new bytes32[](2);
        (p[0], p[1]) = (a, b);
    }

    function _transferProof() internal pure returns (bytes32[] memory) {
        return _p(
            0x3a072b6d10764c38e0ecb1b45ae926915dba874db2432a4156d9b8081afba6ce,
            0xee95a10756ff2c13bad0772c3403b4724d611c55529a234c07745c62b13c8caa
        );
    }

    function _approveProof() internal pure returns (bytes32[] memory) {
        return _p(
            0xd4f3a328d0999d3a5d985bb0893f6759510a233c7042c14dc64e1b6558298ee6,
            0xee95a10756ff2c13bad0772c3403b4724d611c55529a234c07745c62b13c8caa
        );
    }

    function _transferFromProof() internal pure returns (bytes32[] memory p) {
        p = new bytes32[](1);
        p[0] = 0x7824f38dcda25f42af9f48a655ba5424f8241e3395b1321a86b01b75ff329f40;
    }

    function test_everyEdgeInTheMapExecutes() public {
        vm.startPrank(controller);
        agent.execute(
            TOKEN, 0, abi.encodeWithSelector(0xa9059cbb, address(1), 1), FROM, REL, TO_TRANSFER, 500, _transferProof()
        );
        assertEq(SelectorSink(payable(TOKEN)).last(), bytes4(0xa9059cbb));

        agent.execute(
            SPENDER, 0, abi.encodeWithSelector(0x095ea7b3, address(1), 1), FROM, REL, TO_APPROVE, 0, _approveProof()
        );
        assertEq(SelectorSink(payable(SPENDER)).last(), bytes4(0x095ea7b3));

        agent.execute(
            TOKEN,
            0,
            abi.encodeWithSelector(0x23b872dd, address(1), address(2), 1),
            FROM,
            REL,
            TO_TRANSFER_FROM,
            9000,
            _transferFromProof()
        );
        assertEq(SelectorSink(payable(TOKEN)).last(), bytes4(0x23b872dd));
        vm.stopPrank();
    }

    /// The approve edge is mapped on SPENDER only: replaying its proof against TOKEN is outside the map.
    function test_mappedSelectorOnUnmappedTargetReverts() public {
        bytes memory data = abi.encodeWithSelector(0x095ea7b3, address(1), 1);
        bytes32[] memory proof = _approveProof();
        vm.prank(controller);
        vm.expectRevert(SovereignAgent.EdgeNotProven.selector);
        agent.execute(TOKEN, 0, data, FROM, REL, TO_APPROVE, 0, proof);
    }

    /// Understating the risk weight (9000 -> 0) changes the leaf, so the proof no longer verifies.
    function test_understatedRiskWeightReverts() public {
        bytes memory data = abi.encodeWithSelector(0x23b872dd, address(1), address(2), 1);
        bytes32[] memory proof = _transferFromProof();
        vm.prank(controller);
        vm.expectRevert(SovereignAgent.EdgeNotProven.selector);
        agent.execute(TOKEN, 0, data, FROM, REL, TO_TRANSFER_FROM, 0, proof);
    }

    /// A call that appears nowhere in the pack cannot borrow another edge's proof.
    function test_unmappedCallReverts() public {
        bytes memory data = abi.encodeWithSignature("burn(uint256)", 1);
        bytes32[] memory proof = _transferProof();
        vm.prank(controller);
        vm.expectRevert(SovereignAgent.EdgeNotProven.selector);
        agent.execute(TOKEN, 0, data, FROM, REL, TO_TRANSFER, 500, proof);
    }

    /// A graph-governed domain never accepts the proof-less overload, even for a mapped call.
    function test_plainOverloadRequiresAnEdgeClaim() public {
        bytes memory data = abi.encodeWithSelector(0xa9059cbb, address(1), 1);
        vm.prank(controller);
        vm.expectRevert(SovereignAgent.EdgeClaimRequired.selector);
        agent.execute(TOKEN, 0, data);
    }
}
