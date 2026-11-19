// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test, console2 } from "forge-std/Test.sol";
import { SessionPolicyLib } from "../../src/wallet/SessionPolicyLib.sol";
import {
    ISafeSpike,
    ISafe7579Spike,
    ISafeProxyFactorySpike,
    ISmartSessionSpike,
    IOwnableValidatorSpike,
    ModuleInit,
    RegistryInit,
    Session,
    PolicyData,
    ActionData,
    ERC7739Data,
    ERC7739Context
} from "../spike/SpikeInterfaces.sol";
import { SpikeSafe7579Setup, SpikeTarget } from "../spike/SpikeStubs.sol";

contract SessionPolicyHarness {
    function validateSession(SessionPolicyLib.Session memory session) external pure {
        SessionPolicyLib.validateSession(session);
    }
}

/// @title SmartSessionsPolicyCheckTest
/// @notice Verifies Invariant I4 / F4:
/// Ephemeral session keys must NEVER be permitted to produce valid EIP-1271 signatures.
/// Tested via unit verification of SessionPolicyLib and Base Sepolia fork validation of Smart Sessions.
contract SmartSessionsPolicyCheckTest is Test {
    SessionPolicyHarness harness;

    // ── Canonical Base Sepolia addresses ──────────────────────────────────────────
    address constant SAFE_141_SINGLETON = 0x41675C099F32341bf84BFc5382aF534df5C7461a;
    address constant SAFE_141_FACTORY = 0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67;
    address constant SAFE7579 = 0x7579EE8307284F293B1927136486880611F20002;
    address constant SMART_SESSIONS = 0x00000000008bDABA73cD9815d79069c247Eb4bDA;
    address constant SMART_SESSIONS_COMPAT_FALLBACK = 0x000000000052e9685932845660777DF43C2dC496;
    address constant OWNABLE_VALIDATOR = 0x000000000013fdB5234E4E3162a810F54d9f7E98;
    address constant SUDO_POLICY = 0x0000003111cD8e92337C100F22B7A9dbf8DEE301;

    bytes32 constant SAFE_MSG_TYPEHASH = 0x60b3cbf8b4a223d68d641b3b6ddf9a298e7f33710cf3d3a9d1146b5a6150fbca;
    string constant CONTENTS_TYPE = "Mail(address to,string body)";

    address owner;
    uint256 ownerKey;
    address sessionKey;
    uint256 sessionKeyPk;

    SpikeSafe7579Setup setupHelper;
    SpikeTarget target;
    address safe;
    bytes32 sessionPermissionId;

    modifier onlyBaseSepoliaFork() {
        if (block.chainid != 84532) {
            vm.skip(true);
        }
        _;
    }

    function setUp() public {
        harness = new SessionPolicyHarness();
        (owner, ownerKey) = makeAddrAndKey("owner-human");
        (sessionKey, sessionKeyPk) = makeAddrAndKey("agent-session-key");

        if (block.chainid == 84532) {
            setupHelper = new SpikeSafe7579Setup();
            target = new SpikeTarget();

            Session[] memory sessions = new Session[](1);
            sessions[0] = _agentSession(address(target), SpikeTarget.ping.selector, bytes32(0));
            sessionPermissionId = ISmartSessionSpike(SMART_SESSIONS).getPermissionId(sessions[0]);
            safe = _deploySafe(SAFE_141_SINGLETON, SAFE_141_FACTORY, owner, 9999, sessions);
        }
    }

    // ═════════════════════════════════════════════════════════════════════════════════
    // Unit Tests: SessionPolicyLib
    // ═════════════════════════════════════════════════════════════════════════════════

    function test_validateSession_success_whenErc7739Empty() public view {
        SessionPolicyLib.Session memory session;
        session.sessionValidator = address(0x123);
        // Both allowedERC7739Content and erc1271Policies are empty arrays by default
        harness.validateSession(session);
    }

    function test_validateSession_reverts_whenAllowedContentNonEmpty() public {
        SessionPolicyLib.Session memory session;
        session.erc7739Policies.allowedERC7739Content = new SessionPolicyLib.ERC7739Context[](1);
        session.erc7739Policies.allowedERC7739Content[0] = SessionPolicyLib.ERC7739Context({
            appDomainSeparator: bytes32(uint256(1)),
            contentNames: new string[](0)
        });

        vm.expectRevert(SessionPolicyLib.Erc7739PoliciesForbidden.selector);
        harness.validateSession(session);
    }

    function test_validateSession_reverts_when1271PoliciesNonEmpty() public {
        SessionPolicyLib.Session memory session;
        session.erc7739Policies.erc1271Policies = new SessionPolicyLib.PolicyData[](1);
        session.erc7739Policies.erc1271Policies[0] = SessionPolicyLib.PolicyData({
            policy: address(0x456),
            initData: hex""
        });

        vm.expectRevert(SessionPolicyLib.Erc7739PoliciesForbidden.selector);
        harness.validateSession(session);
    }

    // ═════════════════════════════════════════════════════════════════════════════════
    // Fork Tests: EIP-1271 Invariant Enforcement
    // ═════════════════════════════════════════════════════════════════════════════════

    /// @notice Confirms that a session configured in accordance with Invariant I4
    /// (empty erc7739Policies) cannot validate 1271 signatures across all available routes.
    function test_fork_productionSession_refuses1271_everyRoute() public onlyBaseSepoliaFork {
        bytes32 h = keccak256("EIP-3009 authorization digest");

        // Route A: SmartSessions before compatibility fallback installed -> reverts
        bytes memory sigA = _session7739Sig(sessionPermissionId, h, false);
        vm.expectRevert();
        ISafe7579Spike(safe).isValidSignature(h, sigA);

        // Route B: SmartSessions after compatibility fallback installed -> returns 0xffffffff
        _installCompatFallback();
        bytes memory sigB = _session7739Sig(sessionPermissionId, h, true);
        bytes4 r = ISafe7579Spike(safe).isValidSignature(h, sigB);
        assertEq(r, bytes4(0xffffffff), "production session must refuse 1271");

        // Route C: validator = address(0) -> Safe checkSignatures over SafeMessage digest
        bytes32 safeMsg = keccak256(
            abi.encodePacked(
                bytes1(0x19),
                bytes1(0x01),
                ISafeSpike(safe).domainSeparator(),
                keccak256(abi.encodePacked(SAFE_MSG_TYPEHASH, abi.encode(keccak256(abi.encode(h)))))
            )
        );
        (uint8 v, bytes32 rr, bytes32 ss) = vm.sign(sessionKeyPk, safeMsg);
        vm.expectRevert(bytes("GS026")); // session key is not a Safe owner
        ISafe7579Spike(safe).isValidSignature(h, abi.encodePacked(address(0), rr, ss, v));

        // Control: owner signature on Route C succeeds
        (v, rr, ss) = vm.sign(ownerKey, safeMsg);
        assertEq(
            ISafe7579Spike(safe).isValidSignature(h, abi.encodePacked(address(0), rr, ss, v)),
            bytes4(0x1626ba7e)
        );

        // Route D: empty data -> Safe signedMessages
        vm.expectRevert(bytes("Hash not approved"));
        ISafe7579Spike(safe).isValidSignature(h, "");
    }

    /// @notice Positive control: proves that if erc7739Policies WERE configured,
    /// Smart Sessions would permit 1271 verification.
    function test_fork_positiveControl_permissiveSessionAccepts1271() public onlyBaseSepoliaFork {
        _installCompatFallback();
        bytes32 appSep = keccak256("integrity app domain");
        Session[] memory s = new Session[](1);
        s[0] = _agentSession(address(target), SpikeTarget.ping.selector, bytes32(uint256(2)));
        s[0].erc7739Policies.allowedERC7739Content = new ERC7739Context[](1);
        s[0].erc7739Policies.allowedERC7739Content[0].appDomainSeparator = appSep;
        s[0].erc7739Policies.allowedERC7739Content[0].contentNames = new string[](1);
        s[0].erc7739Policies.allowedERC7739Content[0].contentNames[0] = CONTENTS_TYPE;
        s[0].erc7739Policies.erc1271Policies = new PolicyData[](1);
        s[0].erc7739Policies.erc1271Policies[0] = PolicyData(SUDO_POLICY, "");
        bytes32 pid = ISmartSessionSpike(SMART_SESSIONS).getPermissionId(s[0]);

        _execSafe(SMART_SESSIONS, 0, abi.encodeCall(ISmartSessionSpike.enableSessions, (s)));

        bytes32 contents = keccak256("Mail(to=agent, body=ping)");
        bytes32 h = keccak256(abi.encodePacked(hex"1901", appSep, contents));
        bytes memory sig = _session7739SigFor(pid, appSep, contents);
        bytes4 r = ISafe7579Spike(safe).isValidSignature(h, sig);
        assertEq(r, bytes4(0x1626ba7e), "permissive session must accept matching signature");
    }

    // ═════════════════════════════════════════════════════════════════════════════════
    // Helpers
    // ═════════════════════════════════════════════════════════════════════════════════

    function _agentSession(address tgt, bytes4 sel, bytes32 salt) internal view returns (Session memory s) {
        address[] memory keys = new address[](1);
        keys[0] = sessionKey;
        s.sessionValidator = OWNABLE_VALIDATOR;
        s.sessionValidatorInitData = abi.encode(uint256(1), keys);
        s.salt = salt;
        s.actions = new ActionData[](1);
        s.actions[0].actionTargetSelector = sel;
        s.actions[0].actionTarget = tgt;
        s.actions[0].actionPolicies = new PolicyData[](1);
        s.actions[0].actionPolicies[0] = PolicyData(SUDO_POLICY, "");
        // erc7739Policies left empty intentionally
    }

    function _deploySafe(
        address singleton,
        address factory,
        address o,
        uint256 salt,
        Session[] memory sessions
    ) internal returns (address proxy) {
        address[] memory ownerArr = new address[](1);
        ownerArr[0] = o;
        ModuleInit[] memory validators = new ModuleInit[](2);
        validators[0] = ModuleInit(OWNABLE_VALIDATOR, abi.encode(uint256(1), ownerArr));
        validators[1] = ModuleInit(
            SMART_SESSIONS, sessions.length == 0 ? bytes("") : abi.encodePacked(uint8(1), abi.encode(sessions))
        );
        bytes memory initAcct = abi.encodeCall(
            ISafe7579Spike.initializeAccount,
            (validators, new ModuleInit[](0), new ModuleInit[](0), new ModuleInit[](0), RegistryInit(address(0), new address[](0), 0))
        );
        bytes memory init = abi.encodeCall(
            ISafeSpike.setup,
            (
                ownerArr,
                1,
                address(setupHelper),
                abi.encodeCall(SpikeSafe7579Setup.enable7579, (SAFE7579, initAcct)),
                SAFE7579,
                address(0),
                0,
                payable(address(0))
            )
        );
        proxy = ISafeProxyFactorySpike(factory).createProxyWithNonce(singleton, init, salt);
    }

    function _execSafe(address to, uint256 value, bytes memory data) internal {
        bytes32 txHash = ISafeSpike(safe).getTransactionHash(
            to, value, data, 0, 0, 0, 0, address(0), address(0), ISafeSpike(safe).nonce()
        );
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(ownerKey, txHash);
        bool ok = ISafeSpike(safe).execTransaction(
            to, value, data, 0, 0, 0, 0, address(0), payable(address(0)), abi.encodePacked(r, s, v)
        );
        require(ok, "execTransaction failed");
    }

    function _installCompatFallback() internal {
        _execSafe(
            safe,
            0,
            abi.encodeCall(
                ISafe7579Spike.installModule,
                (3, SMART_SESSIONS_COMPAT_FALLBACK, abi.encode(bytes4(0x84b0196e), bytes1(0xFE), bytes("")))
            )
        );
    }

    function _session7739Sig(bytes32 pid, bytes32 h, bool haveDomain) internal view returns (bytes memory) {
        bytes32 appSep = keccak256("integrity app domain");
        if (!haveDomain) {
            return abi.encodePacked(SMART_SESSIONS, pid, new bytes(65), appSep, h, CONTENTS_TYPE, uint16(bytes(CONTENTS_TYPE).length));
        }
        return _session7739SigFor(pid, appSep, h);
    }

    function _session7739SigFor(bytes32 pid, bytes32 appSep, bytes32 contents) internal view returns (bytes memory) {
        (, bytes memory dom) = safe.staticcall(abi.encodeWithSelector(0x84b0196e));
        (, string memory name, string memory version, uint256 chainId, address verifying, bytes32 dsalt,) =
            abi.decode(dom, (bytes1, string, string, uint256, address, bytes32, uint256[]));
        bytes32 typeHash = keccak256(
            abi.encodePacked(
                "TypedDataSign(Mail contents,string name,string version,uint256 chainId,address verifyingContract,bytes32 salt)",
                CONTENTS_TYPE
            )
        );
        bytes32 structHash = keccak256(
            abi.encode(typeHash, contents, keccak256(bytes(name)), keccak256(bytes(version)), chainId, verifying, dsalt)
        );
        bytes32 finalHash = keccak256(abi.encodePacked(hex"1901", appSep, structHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(sessionKeyPk, finalHash);
        return abi.encodePacked(
            SMART_SESSIONS, pid, r, s, v, appSep, contents, CONTENTS_TYPE, uint16(bytes(CONTENTS_TYPE).length)
        );
    }
}
