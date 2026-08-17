// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {SovereignAgent} from "../src/core/SovereignAgent.sol";
import {XibalbaAgentRegistry} from "../src/framework/XibalbaAgentRegistry.sol";
import {IntegrityIdentityReadV1} from "../src/kernel/IntegrityIdentityReadV1.sol";

contract ProfileURIStub {
    string public profileURI;

    constructor(string memory profileURI_) {
        profileURI = profileURI_;
    }

    function setProfileURI(string calldata profileURI_) external {
        profileURI = profileURI_;
    }
}

contract IntegrityIdentityReadV1Test is Test {
    string constant DID = "did:integrity:phase-zero-agent";
    string constant PROFILE_URI = "ipfs://phase-zero-registration";

    address admin = makeAddr("admin");
    address registrar = makeAddr("registrar");
    address controller = makeAddr("controller");
    address rotatedController = makeAddr("rotatedController");
    address oracle = makeAddr("oracle");

    XibalbaAgentRegistry registry;
    SovereignAgent sovereignAgent;
    ProfileURIStub profile;
    IntegrityIdentityReadV1 identityRead;
    XibalbaAgentRegistry.PrimitiveSet primitives;
    bytes32 domainId = keccak256("general.integrity");

    function setUp() public {
        registry = new XibalbaAgentRegistry(admin);
        sovereignAgent = new SovereignAgent(DID, controller, oracle, makeAddr("factory"));
        profile = new ProfileURIStub(PROFILE_URI);
        identityRead = new IntegrityIdentityReadV1(address(registry));

        bytes32 registrarRole = registry.REGISTRAR_ROLE();
        vm.prank(admin);
        registry.grantRole(registrarRole, registrar);

        primitives = _primitives(address(sovereignAgent), address(profile));
        _register(DID, primitives, controller);
    }

    function test_facadeExplicitlyRejectsERC8004Conformance() public view {
        assertFalse(identityRead.isERC8004Conformant());
        assertEq(identityRead.INTERFACE_PROFILE(), keccak256("xibalba.integrity.identity-read.v1"));
        assertEq(address(identityRead.sourceRegistry()), address(registry));

        (bool ownerOfSuccess,) = address(identityRead).staticcall(abi.encodeWithSignature("ownerOf(uint256)", 0));
        (bool tokenURISuccess,) = address(identityRead).staticcall(abi.encodeWithSignature("tokenURI(uint256)", 0));
        (bool walletSuccess,) = address(identityRead).staticcall(abi.encodeWithSignature("getAgentWallet(uint256)", 0));
        (bool erc165Success,) =
            address(identityRead).staticcall(abi.encodeWithSignature("supportsInterface(bytes4)", bytes4(0)));

        assertFalse(ownerOfSuccess);
        assertFalse(tokenURISuccess);
        assertFalse(walletSuccess);
        assertFalse(erc165Success);
    }

    function test_resolveByDIDHashAndAddressReturnsSameCanonicalRecord() public view {
        bytes32 didHash_ = registry.didHash(DID);
        IntegrityIdentityReadV1.IdentityView memory byDID = identityRead.resolveDID(DID);
        IntegrityIdentityReadV1.IdentityView memory byHash = identityRead.resolveDIDHash(didHash_);
        IntegrityIdentityReadV1.IdentityView memory byAddress = identityRead.resolveAgent(address(sovereignAgent));

        assertEq(byDID.didHash, didHash_);
        assertEq(byHash.didHash, didHash_);
        assertEq(byAddress.didHash, didHash_);
        assertEq(byDID.sovereignAgent, address(sovereignAgent));
        assertEq(byDID.domainId, domainId);
        assertGt(byDID.registeredAt, 0);
        assertEq(byDID.primitives.reputationRegistry, primitives.reputationRegistry);
    }

    function test_profileURITracksLiveAgentControlledProfileAndAllowsEmptyURI() public {
        bytes32 didHash_ = registry.didHash(DID);
        assertEq(identityRead.profileURI(didHash_), PROFILE_URI);

        profile.setProfileURI("");
        assertEq(identityRead.profileURI(didHash_), "");

        profile.setProfileURI("https://agent.example/registration.json");
        assertEq(identityRead.profileURI(didHash_), "https://agent.example/registration.json");
    }

    function test_controllerCheckUsesLiveAccountRoleAfterRotation() public {
        assertTrue(identityRead.isController(address(sovereignAgent), controller));
        assertFalse(identityRead.isController(address(sovereignAgent), rotatedController));

        vm.prank(controller);
        sovereignAgent.rotateController(rotatedController);

        assertFalse(identityRead.isController(address(sovereignAgent), controller));
        assertTrue(identityRead.isController(address(sovereignAgent), rotatedController));
    }

    function test_unknownLookupsFailClosedThroughCanonicalRegistry() public {
        vm.expectRevert(XibalbaAgentRegistry.UnknownAgent.selector);
        identityRead.resolveAgent(makeAddr("unknown"));

        vm.expectRevert(XibalbaAgentRegistry.UnknownDID.selector);
        identityRead.resolveDID("did:integrity:unknown");

        vm.expectRevert(XibalbaAgentRegistry.UnknownDID.selector);
        identityRead.resolveDIDHash(keccak256("unknown"));
    }

    function test_duplicateSovereignAgentRegistrationMakesStaleMappingFailClosed() public {
        string memory secondDID = "did:integrity:second-subject";
        _register(secondDID, primitives, controller);

        bytes32 firstHash = registry.didHash(DID);
        bytes32 secondHash = registry.didHash(secondDID);

        vm.expectRevert(
            abi.encodeWithSelector(IntegrityIdentityReadV1.IdentityMappingMismatch.selector, firstHash, secondHash)
        );
        identityRead.resolveDID(DID);

        vm.expectRevert(
            abi.encodeWithSelector(IntegrityIdentityReadV1.DeclaredDIDMismatch.selector, secondHash, firstHash)
        );
        identityRead.resolveAgent(address(sovereignAgent));
    }

    function test_registryDIDMustMatchSovereignAgentsDeclaredDID() public {
        SovereignAgent mismatchedAgent =
            new SovereignAgent("did:integrity:declared", controller, oracle, makeAddr("secondFactory"));
        ProfileURIStub secondProfile = new ProfileURIStub("");
        XibalbaAgentRegistry.PrimitiveSet memory mismatchedPrimitives =
            _primitives(address(mismatchedAgent), address(secondProfile));
        string memory registeredDID = "did:integrity:registered-but-not-declared";
        _register(registeredDID, mismatchedPrimitives, controller);

        bytes32 registeredHash = registry.didHash(registeredDID);
        bytes32 declaredHash = registry.didHash("did:integrity:declared");
        vm.expectRevert(
            abi.encodeWithSelector(IntegrityIdentityReadV1.DeclaredDIDMismatch.selector, registeredHash, declaredHash)
        );
        identityRead.resolveDID(registeredDID);
    }

    function test_subjectWithoutDIDReadSurfaceFailsClosed() public {
        address fakeSubject = address(new ProfileURIStub("not-an-agent"));
        XibalbaAgentRegistry.PrimitiveSet memory badPrimitives = _primitives(fakeSubject, address(profile));
        string memory badDID = "did:integrity:no-readable-subject";
        _register(badDID, badPrimitives, controller);

        vm.expectRevert(abi.encodeWithSelector(IntegrityIdentityReadV1.DeclaredDIDUnavailable.selector, fakeSubject));
        identityRead.resolveDID(badDID);
    }

    function test_profileFailureDoesNotBlockFixedIdentityResolution() public {
        string memory did = "did:integrity:broken-profile";
        SovereignAgent agent = new SovereignAgent(did, controller, oracle, makeAddr("profileFailureFactory"));
        address nonContractProfile = makeAddr("nonContractProfile");
        _register(did, _primitives(address(agent), nonContractProfile), controller);

        bytes32 didHash_ = registry.didHash(did);
        IntegrityIdentityReadV1.IdentityView memory identity = identityRead.resolveDIDHash(didHash_);
        assertEq(identity.sovereignAgent, address(agent));
        assertEq(identity.primitives.agentProfile, nonContractProfile);

        vm.expectRevert();
        identityRead.profileURI(didHash_);
    }

    function test_zeroRegistryIsRejected() public {
        vm.expectRevert(IntegrityIdentityReadV1.ZeroRegistry.selector);
        new IntegrityIdentityReadV1(address(0));
    }

    function _register(
        string memory did,
        XibalbaAgentRegistry.PrimitiveSet memory primitiveSet,
        address registrationController
    ) internal {
        bytes32 didHash_ = registry.didHash(did);
        vm.prank(registrar);
        registry.registerPrimitives(didHash_, primitiveSet, registrationController, domainId);
    }

    function _primitives(address agent, address agentProfile)
        internal
        returns (XibalbaAgentRegistry.PrimitiveSet memory)
    {
        return XibalbaAgentRegistry.PrimitiveSet({
            sovereignAgent: agent,
            stateAnchor: makeAddr(string.concat("stateAnchor-", vm.toString(agent))),
            reputationRegistry: makeAddr(string.concat("reputationRegistry-", vm.toString(agent))),
            slasher: makeAddr(string.concat("slasher-", vm.toString(agent))),
            verifierRegistry: makeAddr(string.concat("verifierRegistry-", vm.toString(agent))),
            complianceGate: makeAddr(string.concat("complianceGate-", vm.toString(agent))),
            agentProfile: agentProfile
        });
    }
}
