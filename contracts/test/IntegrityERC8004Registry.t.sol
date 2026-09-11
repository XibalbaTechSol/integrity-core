// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {SovereignAgent} from "../src/core/SovereignAgent.sol";
import {XibalbaAgentRegistry} from "../src/framework/XibalbaAgentRegistry.sol";
import {IntegrityERC8004Registry} from "../src/kernel/IntegrityERC8004Registry.sol";

contract IntegrityERC8004RegistryTest is Test {
    string constant DID       = "did:integrity:aabbccdd1122334455667788aabbccdd1122334455667788aabbccdd11223344";
    string constant AGENT_URI = "ipfs://QmExampleERC8004RegistrationFile";

    address admin      = makeAddr("admin");
    address minter     = makeAddr("minter");
    address controller = makeAddr("controller");
    address oracle     = makeAddr("oracle");

    XibalbaAgentRegistry      registry;
    SovereignAgent            sovereignAgent;
    IntegrityERC8004Registry  erc8004;

    function setUp() public {
        registry      = new XibalbaAgentRegistry(admin);
        sovereignAgent = new SovereignAgent(DID, controller, oracle, makeAddr("factory"));
        erc8004       = new IntegrityERC8004Registry(address(registry), admin);

        vm.startPrank(admin);
        erc8004.grantRole(erc8004.MINTER_ROLE(), minter);
        vm.stopPrank();
    }

    // ── Capability claims ──────────────────────────────────────────────────────

    function test_isERC8004ConformantReturnsTrue() public view {
        assertTrue(erc8004.isERC8004Conformant());
    }

    function test_supportsERC721Interface() public view {
        // ERC-721 interfaceId = 0x80ac58cd
        assertTrue(erc8004.supportsInterface(0x80ac58cd));
    }

    function test_supportsERC721MetadataInterface() public view {
        // ERC-721 Metadata interfaceId = 0x5b5e139f
        assertTrue(erc8004.supportsInterface(0x5b5e139f));
    }

    // ── tokenId derivation ─────────────────────────────────────────────────────

    function test_tokenIdForDIDMatchesKeccak() public view {
        uint256 expected = uint256(keccak256(bytes(DID)));
        assertEq(erc8004.tokenIdForDID(DID), expected);
    }

    function test_tokenIdForAddressMatchesKeccak() public {
        address agent = makeAddr("enterpriseAgent");
        uint256 expected = uint256(keccak256(abi.encodePacked(agent)));
        assertEq(erc8004.tokenIdForAddress(agent), expected);
    }

    // ── Sovereign mint ─────────────────────────────────────────────────────────

    function test_mintSovereignSucceeds() public {
        vm.prank(minter);
        erc8004.mintSovereign(DID, address(sovereignAgent), AGENT_URI);

        uint256 tokenId = erc8004.tokenIdForDID(DID);
        assertEq(erc8004.ownerOf(tokenId), address(sovereignAgent));
        assertEq(erc8004.tokenURI(tokenId), AGENT_URI);
    }

    function test_mintSovereignEmitsAgentRegistered() public {
        uint256 expectedId = erc8004.tokenIdForDID(DID);
        vm.expectEmit(true, true, false, true, address(erc8004));
        emit IntegrityERC8004Registry.AgentRegistered(expectedId, address(sovereignAgent), AGENT_URI);

        vm.prank(minter);
        erc8004.mintSovereign(DID, address(sovereignAgent), AGENT_URI);
    }

    function test_doubleMintReverts() public {
        uint256 tokenId = erc8004.tokenIdForDID(DID);

        vm.prank(minter);
        erc8004.mintSovereign(DID, address(sovereignAgent), AGENT_URI);

        vm.prank(minter);
        vm.expectRevert(abi.encodeWithSelector(IntegrityERC8004Registry.AlreadyMinted.selector, tokenId));
        erc8004.mintSovereign(DID, address(sovereignAgent), AGENT_URI);
    }

    function test_unauthorizedMintReverts() public {
        vm.expectRevert();
        erc8004.mintSovereign(DID, address(sovereignAgent), AGENT_URI);
    }

    // ── Enterprise mint ────────────────────────────────────────────────────────

    function test_mintEnterpriseSucceeds() public {
        address enterpriseAgent = makeAddr("enterpriseAgent");
        uint256 tokenId = erc8004.tokenIdForAddress(enterpriseAgent);

        vm.prank(minter);
        erc8004.mintEnterprise(enterpriseAgent, AGENT_URI);

        assertEq(erc8004.ownerOf(tokenId), enterpriseAgent);
        assertEq(erc8004.tokenURI(tokenId), AGENT_URI);
    }

    // ── Soulbound ──────────────────────────────────────────────────────────────

    function test_transferReverts() public {
        vm.prank(minter);
        erc8004.mintSovereign(DID, address(sovereignAgent), AGENT_URI);
        uint256 tokenId = erc8004.tokenIdForDID(DID);

        vm.prank(address(sovereignAgent));
        vm.expectRevert(IntegrityERC8004Registry.Soulbound.selector);
        erc8004.transferFrom(address(sovereignAgent), makeAddr("recipient"), tokenId);
    }

    // ── agentURI update ────────────────────────────────────────────────────────

    function test_ownerCanUpdateAgentURI() public {
        vm.prank(minter);
        erc8004.mintSovereign(DID, address(sovereignAgent), AGENT_URI);
        uint256 tokenId = erc8004.tokenIdForDID(DID);

        string memory newURI = "ipfs://QmUpdatedRegistrationFile";
        vm.prank(address(sovereignAgent));
        erc8004.setAgentURI(tokenId, newURI);

        assertEq(erc8004.tokenURI(tokenId), newURI);
    }

    function test_nonOwnerCannotUpdateAgentURI() public {
        vm.prank(minter);
        erc8004.mintSovereign(DID, address(sovereignAgent), AGENT_URI);
        uint256 tokenId = erc8004.tokenIdForDID(DID);

        vm.prank(makeAddr("attacker"));
        vm.expectRevert(IntegrityERC8004Registry.NotTokenOwner.selector);
        erc8004.setAgentURI(tokenId, "ipfs://malicious");
    }

    // ── On-chain metadata ──────────────────────────────────────────────────────

    function test_setAndGetMetadata() public {
        vm.prank(minter);
        erc8004.mintSovereign(DID, address(sovereignAgent), AGENT_URI);
        uint256 tokenId = erc8004.tokenIdForDID(DID);

        bytes memory value = abi.encode("shield-endpoint", "https://shield.example.com");
        vm.prank(address(sovereignAgent));
        erc8004.setMetadata(tokenId, "shieldEndpoint", value);

        assertEq(erc8004.getMetadata(tokenId, "shieldEndpoint"), value);
    }

    function test_reservedAgentWalletKeyReverts() public {
        vm.prank(minter);
        erc8004.mintSovereign(DID, address(sovereignAgent), AGENT_URI);
        uint256 tokenId = erc8004.tokenIdForDID(DID);

        vm.prank(address(sovereignAgent));
        vm.expectRevert(abi.encodeWithSelector(IntegrityERC8004Registry.ReservedKey.selector, "agentWallet"));
        erc8004.setMetadata(tokenId, "agentWallet", bytes("0xdeadbeef"));
    }

    function test_unknownTokenMetadataReturnsEmpty() public view {
        uint256 missing = uint256(keccak256("nonexistent"));
        assertEq(erc8004.getMetadata(missing, "anything").length, 0);
    }
}
