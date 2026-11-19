// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

// THROWAWAY (Plan 1 Task 1 wallet-stack spike). Fork-only evidence for
// docs/superpowers/specs/2026-11-18-wallet-stack-spike.md. Deleted in Plan 1b once the fork tests
// replace it. Never broadcasts. Every key is a forge test key.
//
// Run (fork pinned so the evidence is reproducible):
//   forge test --match-path test/spike/WalletStackSpike.t.sol \
//     --fork-url https://sepolia.base.org --fork-block-number 60684000 -vv
// Without a Base Sepolia fork every test skips itself, so plain `forge test` (CI) is unaffected.

import { Test, console2 } from "forge-std/Test.sol";
import "./SpikeInterfaces.sol";
import { StubHook, StubGuard, SpikeSafe7579Setup, SpikeTarget } from "./SpikeStubs.sol";

contract WalletStackSpikeTest is Test {
    // ── Canonical Base Sepolia addresses (sources in the decision record) ──────────────────────
    IEntryPointV07 constant EP = IEntryPointV07(0x0000000071727De22E5E9d8BAf0edAc6f37da032);
    address constant SAFE_141_SINGLETON = 0x41675C099F32341bf84BFc5382aF534df5C7461a;
    ISafeProxyFactorySpike constant SAFE_141_FACTORY =
        ISafeProxyFactorySpike(0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67);
    address constant SAFE_150_SINGLETON = 0xFf51A5898e281Db6DfC7855790607438dF2ca44b;
    address constant SAFE_150_FACTORY = 0x14F2982D601c9458F93bd70B218933A6f8165e7b;
    address constant SAFE7579 = 0x7579EE8307284F293B1927136486880611F20002; // adapter v1.0.0
    address constant SAFE7579_LAUNCHPAD = 0x7579011aB74c46090561ea277Ba79D510c6C00ff;
    address constant SMART_SESSIONS = 0x00000000008bDABA73cD9815d79069c247Eb4bDA;
    address constant SMART_SESSIONS_COMPAT_FALLBACK = 0x000000000052e9685932845660777DF43C2dC496;
    address constant OWNABLE_VALIDATOR = 0x000000000013fdB5234E4E3162a810F54d9f7E98;
    address constant SUDO_POLICY = 0x0000003111cD8e92337C100F22B7A9dbf8DEE301;
    address constant RHINESTONE_REGISTRY = 0x000000000069E2a187AEFFb852bF3cCdC95151B2;
    IAgent0RegistrySpike constant AGENT0 = IAgent0RegistrySpike(0x8004A818BFB912233c491871b3d84c89A494BD9e);
    address constant SAFE_SINGLETON_CREATE2_FACTORY = 0x914d7Fec6aaC8cd542e72Bca78B30650d45643d7;

    bytes32 constant FALLBACK_HANDLER_SLOT = 0x6c9a6c4a39284e37ed1cf53d337577d14212a4870fb976a4366c693b939918d5;
    bytes32 constant GUARD_SLOT = 0x4a204f620c8c5ccdca3fd54d003badd85ba500436a431f0cbda4f558c93c34c8;
    address constant SENTINEL = address(1);
    bytes32 constant SAFE_MSG_TYPEHASH = 0x60b3cbf8b4a223d68d641b3b6ddf9a298e7f33710cf3d3a9d1146b5a6150fbca;
    bytes32 constant MODE_SINGLE = bytes32(0); // CALLTYPE_SINGLE | EXECTYPE_DEFAULT
    // Selectors IntegrityHook is installed on as Safe7579 SIG hooks (see test_Q4_globalHook_breaksStaticFallback
    // for why it cannot be the GLOBAL hook on Safe7579).
    bytes4 constant SEL_EXECUTE = 0xe9ae5c53; // execute(bytes32,bytes)
    bytes4 constant SEL_EXECUTE_FROM_EXECUTOR = 0xd691c964; // executeFromExecutor(bytes32,bytes)
    bytes4 constant SEL_INSTALL = 0x9517e29f; // installModule(uint256,address,bytes)
    bytes4 constant SEL_UNINSTALL = 0xa71763a8; // uninstallModule(uint256,address,bytes)

    StubHook hook;
    StubGuard guard;
    SpikeSafe7579Setup setupHelper;
    SpikeTarget target;

    address owner;
    uint256 ownerKey;
    address sessionKey;
    uint256 sessionKeyPk;
    address bundler = makeAddr("bundler");

    address safe; // the agent wallet
    uint256 constant SALT = 7579;
    bytes initializer; // kept for the CREATE2 provenance check
    bytes32 sessionPermissionId; // production-shaped agent session (no 1271)

    modifier onlyBaseSepoliaFork() {
        if (block.chainid != 84532) {
            vm.skip(true);
        }
        _;
    }

    function setUp() public {
        if (block.chainid != 84532) return; // not on the fork: tests skip themselves
        (owner, ownerKey) = makeAddrAndKey("owner-human");
        (sessionKey, sessionKeyPk) = makeAddrAndKey("agent-session-key");
        hook = new StubHook();
        guard = new StubGuard();
        setupHelper = new SpikeSafe7579Setup();
        target = new SpikeTarget();

        Session[] memory sessions = new Session[](1);
        sessions[0] = _agentSession(address(target), SpikeTarget.ping.selector, bytes32(0));
        sessionPermissionId = ISmartSessionSpike(SMART_SESSIONS).getPermissionId(sessions[0]);
        (safe, initializer) = _deploySafe(SAFE_141_SINGLETON, address(SAFE_141_FACTORY), owner, SALT, sessions, false);
        vm.deal(safe, 1 ether);
    }

    // ═════════════════════════════════════════════════════════════════════════════════════════
    // Q1 — component code on Base Sepolia, and the account deploys from the factory
    // ═════════════════════════════════════════════════════════════════════════════════════════
    function test_Q1_componentsHaveCode_andAccountDeploys() public onlyBaseSepoliaFork {
        address[13] memory a = [
            address(EP),
            SAFE_141_SINGLETON,
            address(SAFE_141_FACTORY),
            SAFE_150_SINGLETON,
            SAFE_150_FACTORY,
            SAFE7579,
            SAFE7579_LAUNCHPAD,
            SMART_SESSIONS,
            SMART_SESSIONS_COMPAT_FALLBACK,
            OWNABLE_VALIDATOR,
            SUDO_POLICY,
            RHINESTONE_REGISTRY,
            address(AGENT0)
        ];
        for (uint256 i; i < a.length; i++) {
            console2.log("code", a[i], a[i].code.length);
            assertGt(a[i].code.length, 0, "component has no code");
        }
        console2.log("safe", safe);
        console2.log("safe VERSION", ISafeSpike(safe).VERSION());
        console2.log("accountId", ISafe7579Spike(safe).accountId());
        assertEq(ISafeSpike(safe).getOwners()[0], owner);
        assertTrue(ISafeSpike(safe).isModuleEnabled(SAFE7579));
        assertTrue(ISafe7579Spike(safe).isModuleInstalled(1, SMART_SESSIONS, ""));
        assertTrue(ISafe7579Spike(safe).isModuleInstalled(1, OWNABLE_VALIDATOR, ""));
        assertEq(ISafe7579Spike(safe).getActiveHook(), address(0), "no GLOBAL hook");
        assertEq(ISafe7579Spike(safe).getActiveHook(SEL_EXECUTE), address(hook), "SIG hook on execute");
        assertTrue(ISmartSessionSpike(SMART_SESSIONS).isPermissionEnabled(sessionPermissionId, safe));
    }

    // ═════════════════════════════════════════════════════════════════════════════════════════
    // Q2 — execution paths: which ones the 7579 hook sees
    // ═════════════════════════════════════════════════════════════════════════════════════════

    /// The session key's UserOperation, sent straight to EntryPoint v0.7 handleOps (no bundler).
    function test_Q2_sessionKeyUserOp_runsThroughHook() public onlyBaseSepoliaFork {
        _setGuard(address(guard));
        uint256 guardBefore = guard.count();
        uint256 hooksBefore = hook.count();

        _sendSessionOp(sessionPermissionId, address(target), 0, abi.encodeCall(SpikeTarget.ping, (3)));

        assertEq(target.pings(), 3, "session op did not execute");
        assertEq(target.lastCaller(), safe);
        assertEq(hook.count(), hooksBefore + 1, "hook did not see the session op");
        StubHook.Seen memory s = hook.seen(hook.count() - 1);
        console2.log("hook.account", s.account);
        console2.log("hook.msgSender", s.msgSender);
        console2.logBytes4(bytes4(s.msgData));
        assertEq(s.account, safe);
        assertEq(s.msgSender, address(EP), "session op: hook sees EntryPoint as sender");
        assertEq(bytes4(s.msgData), ISafe7579Spike.execute.selector);
        assertEq(guard.count(), guardBefore, "Safe 1.4.1 guard does not see module (7579) txs");
    }

    /// Owner signs a Safe-native execTransaction: the 7579 hook does NOT run. A Safe Guard does.
    function test_Q2_ownerExecTransaction_skipsHook_guardSeesIt() public onlyBaseSepoliaFork {
        _setGuard(address(guard));
        uint256 hooksBefore = hook.count();
        uint256 guardBefore = guard.count();

        _execSafe(address(target), 0, abi.encodeCall(SpikeTarget.ping, (5)), 0);

        assertEq(target.pings(), 5);
        assertEq(hook.count(), hooksBefore, "execTransaction bypasses the 7579 hook");
        assertEq(guard.count(), guardBefore + 1, "guard sees execTransaction");
        assertEq(guard.lastTo(), address(target));
        console2.log("hook count unchanged", hook.count());
        console2.log("guard count", guard.count());
    }

    /// Any other Safe-native module skips both the 7579 hook and (on Safe 1.4.1) the Guard.
    function test_Q2_otherSafeModule_skipsHookAndGuard_on141() public onlyBaseSepoliaFork {
        _setGuard(address(guard));
        address rogue = makeAddr("owner-enabled-safe-module");
        _execSafe(safe, 0, abi.encodeCall(ISafeSpike.enableModule, (rogue)), 0);
        uint256 hooksBefore = hook.count();
        uint256 guardBefore = guard.count();

        vm.prank(rogue);
        bool ok = ISafeSpike(safe).execTransactionFromModule(address(target), 0, abi.encodeCall(SpikeTarget.ping, (7)), 0);

        assertTrue(ok);
        assertEq(target.pings(), 7);
        assertEq(hook.count(), hooksBefore, "Safe module path bypasses the 7579 hook");
        assertEq(guard.count(), guardBefore, "Safe 1.4.1 guard does not see module txs");
        // and verify() flags the account as not genuine any more
        (bool genuine,, string memory why) = _verify(safe);
        assertFalse(genuine);
        console2.log("verify after extra module:", why);
    }

    /// Owner routes through the 7579 path by calling the account's own execute() from
    /// execTransaction: the hook runs and reports msgSender == the account itself.
    function test_Q2_ownerSelfExecute_hookSeesAccountAsSender() public onlyBaseSepoliaFork {
        uint256 hooksBefore = hook.count();
        bytes memory inner = abi.encodeCall(
            ISafe7579Spike.execute,
            (MODE_SINGLE, abi.encodePacked(address(target), uint256(0), abi.encodeCall(SpikeTarget.ping, (11))))
        );
        _execSafe(safe, 0, inner, 0);
        assertEq(target.pings(), 11);
        assertEq(hook.count(), hooksBefore + 1);
        StubHook.Seen memory s = hook.seen(hook.count() - 1);
        console2.log("owner self-execute hook.msgSender", s.msgSender);
        assertEq(s.msgSender, safe, "owner via execTransaction->self: hook sees msgSender == account");
    }

    // ═════════════════════════════════════════════════════════════════════════════════════════
    // Q3 — role source
    // ═════════════════════════════════════════════════════════════════════════════════════════

    /// An owner-signed UserOperation (OwnableValidator nonce key) is indistinguishable, at the
    /// hook, from a session-key UserOperation: both report msgSender == EntryPoint and the same
    /// execute() calldata shape. Path-based classification must therefore treat EVERY
    /// EntryPoint-originated execution as non-owner (fail closed).
    function test_Q3_ownerUserOp_lookslikeSessionOp_atHook() public onlyBaseSepoliaFork {
        bytes memory call_ = abi.encodeCall(SpikeTarget.ping, (1));
        _sendSessionOp(sessionPermissionId, address(target), 0, call_);
        StubHook.Seen memory sess = hook.seen(hook.count() - 1);

        _sendOwnerOp(address(target), 0, call_);
        StubHook.Seen memory own = hook.seen(hook.count() - 1);

        assertEq(target.pings(), 2);
        console2.log("session op msgSender", sess.msgSender);
        console2.log("owner   op msgSender", own.msgSender);
        assertEq(sess.msgSender, own.msgSender, "hook cannot tell owner op from session op");
        assertEq(keccak256(sess.msgData), keccak256(own.msgData), "identical msgData too");
    }

    /// Escalation path for path-based roles: a session op whose 7579 target is the account's own
    /// execute() would make the INNER preCheck report msgSender == account (the owner path).
    /// Smart Sessions refuses this itself (PolicyLib: `InvalidSelfCall`) even when the owner
    /// grants an action for (account, execute) — shown here by calling the live validator directly
    /// and by handleOps rejecting the op. The hook must still deny non-owner target == account.
    function test_Q3_sessionSelfExecute_refusedBySmartSessions() public onlyBaseSepoliaFork {
        Session[] memory s = new Session[](1);
        s[0] = _agentSession(safe, SEL_EXECUTE, bytes32(uint256(1))); // owner (mis)grants account.execute
        bytes32 pid = ISmartSessionSpike(SMART_SESSIONS).getPermissionId(s[0]);
        _execSafe(SMART_SESSIONS, 0, abi.encodeCall(ISmartSessionSpike.enableSessions, (s)), 0);
        assertTrue(ISmartSessionSpike(SMART_SESSIONS).isPermissionEnabled(pid, safe));

        bytes memory inner = abi.encodeCall(
            ISafe7579Spike.execute,
            (MODE_SINGLE, abi.encodePacked(address(target), uint256(0), abi.encodeCall(SpikeTarget.ping, (13))))
        );
        bytes memory outer = abi.encodeCall(ISafe7579Spike.execute, (MODE_SINGLE, abi.encodePacked(safe, uint256(0), inner)));
        SpikeUserOp memory op = _baseOp(SMART_SESSIONS, outer);
        op.signature = _sessionSig(pid, EP.getUserOpHash(op));
        _expectRejected(op, abi.encodeWithSelector(ISmartSessionSpike.InvalidSelfCall.selector));
        assertEq(target.pings(), 0);
    }

    // ═════════════════════════════════════════════════════════════════════════════════════════
    // Q4 — session-key EIP-1271
    // ═════════════════════════════════════════════════════════════════════════════════════════

    /// Production config (no ERC-7739 content, no 1271 policy) refuses session 1271 on every route.
    function test_Q4_productionSession_refuses1271_everyRoute() public onlyBaseSepoliaFork {
        bytes32 h = keccak256("x402 / EIP-3009 authorization digest");

        // Route A: SmartSessions, before the compatibility fallback is installed -> reverts
        // (Safe has no eip712Domain(); SmartSessions' nested-712 path needs it).
        bytes memory sigA = _session7739Sig(sessionPermissionId, h, false);
        vm.expectRevert();
        ISafe7579Spike(safe).isValidSignature(h, sigA);

        // Install the compatibility fallback so the remaining routes are tested on a 1271-capable account.
        _installCompatFallback();
        bytes memory sigB = _session7739Sig(sessionPermissionId, h, true);
        bytes4 r = ISafe7579Spike(safe).isValidSignature(h, sigB);
        console2.log("route SmartSessions (prod config):");
        console2.logBytes4(r);
        assertEq(r, bytes4(0xffffffff), "production session must refuse 1271");

        // Route C: validator = address(0) -> Safe checkSignatures over the SafeMessage digest.
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
        // control: the owner's signature over the same digest on the same route is accepted
        (v, rr, ss) = vm.sign(ownerKey, safeMsg);
        assertEq(ISafe7579Spike(safe).isValidSignature(h, abi.encodePacked(address(0), rr, ss, v)), bytes4(0x1626ba7e));

        // Route D: empty data -> Safe signedMessages (only an owner tx can approve a hash).
        vm.expectRevert(bytes("Hash not approved"));
        ISafe7579Spike(safe).isValidSignature(h, "");
    }

    /// Positive control: the SAME encoding returns the magic value when the session is configured
    /// to allow 1271 (ERC-7739 content enabled + a 1271 policy). This proves the refusal above is
    /// the configuration, not a malformed signature. It also probes whether the 1271 `hash`
    /// argument is bound to the signature.
    function test_Q4_positiveControl_permissiveSessionAccepts1271() public onlyBaseSepoliaFork {
        _installCompatFallback();
        bytes32 appSep = keccak256("spike app domain");
        Session[] memory s = new Session[](1);
        s[0] = _agentSession(address(target), SpikeTarget.ping.selector, bytes32(uint256(2)));
        s[0].erc7739Policies.allowedERC7739Content = new ERC7739Context[](1);
        s[0].erc7739Policies.allowedERC7739Content[0].appDomainSeparator = appSep;
        s[0].erc7739Policies.allowedERC7739Content[0].contentNames = new string[](1);
        s[0].erc7739Policies.allowedERC7739Content[0].contentNames[0] = CONTENTS_TYPE;
        s[0].erc7739Policies.erc1271Policies = new PolicyData[](1);
        s[0].erc7739Policies.erc1271Policies[0] = PolicyData(SUDO_POLICY, "");
        bytes32 pid = ISmartSessionSpike(SMART_SESSIONS).getPermissionId(s[0]);
        _execSafe(SMART_SESSIONS, 0, abi.encodeCall(ISmartSessionSpike.enableSessions, (s)), 0);

        bytes32 contents = keccak256("Mail(to=bob, body=hi)");
        bytes32 h = keccak256(abi.encodePacked(hex"1901", appSep, contents));
        bytes memory sig = _session7739SigFor(pid, appSep, contents);
        bytes4 r = ISafe7579Spike(safe).isValidSignature(h, sig);
        console2.log("permissive session, matching hash:");
        console2.logBytes4(r);
        assertEq(r, bytes4(0x1626ba7e), "positive control must pass");

        // Same signature, unrelated hash
        bytes4 r2 = ISafe7579Spike(safe).isValidSignature(keccak256("unrelated digest"), sig);
        console2.log("permissive session, UNRELATED hash:");
        console2.logBytes4(r2);
        // FINDING (observed, live 0x00000000008bDABA…): the 1271 `hash` argument is not bound to the
        // ERC-7739 signature, so ANY digest validates once a session may sign any content.
        assertEq(r2, bytes4(0x1626ba7e), "FINDING: SmartSessions 1271 ignores the hash argument");
    }

    /// The session key cannot reach admin calls: removing the hook / installing a module from a
    /// session UserOp fails validation (no action policy covers account.uninstallModule).
    function test_Q4_sessionCannotUninstallHookOrInstallModule() public onlyBaseSepoliaFork {
        bytes memory uninstall = abi.encodeCall(
            ISafe7579Spike.uninstallModule, (4, address(hook), abi.encode(uint8(1), SEL_EXECUTE, bytes("")))
        );
        SpikeUserOp memory op = _baseOp(SMART_SESSIONS, uninstall);
        op.signature = _sessionSig(sessionPermissionId, EP.getUserOpHash(op));
        _expectRejected(op, abi.encodeWithSelector(ISmartSessionSpike.NoPoliciesSet.selector, sessionPermissionId));
        assertEq(ISafe7579Spike(safe).getActiveHook(SEL_UNINSTALL), address(hook), "hook still installed");

        // same via execute(target = account)
        bytes memory viaExec = abi.encodeCall(
            ISafe7579Spike.execute, (MODE_SINGLE, abi.encodePacked(safe, uint256(0), uninstall))
        );
        op = _baseOp(SMART_SESSIONS, viaExec);
        op.signature = _sessionSig(sessionPermissionId, EP.getUserOpHash(op));
        _expectRejected(op, abi.encodeWithSelector(ISmartSessionSpike.NoPoliciesSet.selector, sessionPermissionId));

        bytes memory install = abi.encodeCall(ISafe7579Spike.installModule, (2, makeAddr("evil-executor"), ""));
        op = _baseOp(SMART_SESSIONS, install);
        op.signature = _sessionSig(sessionPermissionId, EP.getUserOpHash(op));
        _expectRejected(op, abi.encodeWithSelector(ISmartSessionSpike.NoPoliciesSet.selector, sessionPermissionId));
        assertEq(ISafe7579Spike(safe).getActiveHook(SEL_UNINSTALL), address(hook));
    }

    /// Safe7579 runs a GLOBAL hook on EVERY fallback-routed call, through
    /// Safe.execTransactionFromModuleReturnData (state-changing: emits events). Any fallback call
    /// reached by STATICCALL then reverts — including eip712Domain(), which SmartSessions and
    /// every ERC-7739 signer read during EIP-1271. Installing the hook as SIG hooks on the
    /// execution selectors instead keeps fallback views working.
    function test_Q4_globalHook_breaksStaticFallback_sigHooksDoNot() public onlyBaseSepoliaFork {
        // SIG-hook account (setUp's): eip712Domain via the compat fallback works
        _installCompatFallback();
        (bool okSig,) = safe.staticcall(abi.encodeWithSelector(0x84b0196e));
        assertTrue(okSig, "SIG-hook account: static fallback works");

        // GLOBAL-hook account: same call reverts
        address saved = safe;
        (address g,) = _deploySafe(SAFE_141_SINGLETON, address(SAFE_141_FACTORY), owner, 99, new Session[](0), true);
        safe = g;
        assertEq(ISafe7579Spike(g).getActiveHook(), address(hook), "GLOBAL hook installed");
        _installCompatFallback();
        (bool okGlobal,) = g.staticcall(abi.encodeWithSelector(0x84b0196e));
        assertFalse(okGlobal, "GLOBAL-hook account: static fallback reverts");
        console2.log("static eip712Domain ok? SIG-hook:", okSig, "GLOBAL-hook:", okGlobal);
        safe = saved;
    }

    // ═════════════════════════════════════════════════════════════════════════════════════════
    // Q5 — the wallet mints its own agent0 passport on the live registry
    // ═════════════════════════════════════════════════════════════════════════════════════════
    function test_Q5_walletMintsPassport_agentWalletIsWallet() public onlyBaseSepoliaFork {
        MetadataEntry[] memory md = new MetadataEntry[](2);
        md[0] = MetadataEntry("integrityDid", bytes("did:integrity:spike"));
        md[1] = MetadataEntry("sovereignActor", abi.encodePacked(safe));
        bytes memory reg = abi.encodeCall(IAgent0RegistrySpike.register, ("ipfs://spike", md));
        uint256 hooksBefore = hook.count();

        vm.recordLogs();
        _sendOwnerOp(address(AGENT0), 0, reg); // owner-signed UserOp through the 7579 path
        uint256 agentId = _registeredAgentId();

        console2.log("agentId", agentId);
        console2.log("ownerOf", AGENT0.ownerOf(agentId));
        console2.log("agentWallet", AGENT0.getAgentWallet(agentId));
        assertEq(AGENT0.ownerOf(agentId), safe, "NFT held by the wallet");
        assertEq(AGENT0.getAgentWallet(agentId), safe, "agentWallet == wallet");
        assertEq(string(AGENT0.getMetadata(agentId, "integrityDid")), "did:integrity:spike");
        assertEq(hook.count(), hooksBefore + 1, "mint went through the hook");
    }

    /// Negative control: without the Safe7579 fallback handler, the mint's onERC721Received
    /// check fails, so the receiver is what makes the mint work.
    function test_Q5_negativeControl_noFallbackHandler_mintReverts() public onlyBaseSepoliaFork {
        _execSafe(safe, 0, abi.encodeCall(ISafeSpike.setFallbackHandler, (address(0))), 0);
        MetadataEntry[] memory md = new MetadataEntry[](0);
        bytes memory reg = abi.encodeCall(IAgent0RegistrySpike.register, ("ipfs://spike", md));
        bytes32 txHash = _safeTxHash(address(AGENT0), 0, reg, 0);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(ownerKey, txHash);
        vm.expectRevert(bytes("GS013")); // inner call (the mint) reverted
        ISafeSpike(safe).execTransaction(
            address(AGENT0), 0, reg, 0, 0, 0, 0, address(0), payable(address(0)), abi.encodePacked(r, s, v)
        );
    }

    // ═════════════════════════════════════════════════════════════════════════════════════════
    // Q6 — IAccountVerifier.verify(account) -> (genuine, owner)
    // ═════════════════════════════════════════════════════════════════════════════════════════
    function test_Q6_verify_genuineAccount_andProvenance() public onlyBaseSepoliaFork {
        (bool genuine, address o, string memory why) = _verify(safe);
        console2.log("verify:", genuine, o, why);
        assertTrue(genuine, why);
        assertEq(o, owner);

        // proxy runtime is owner-independent: a second Safe with another owner has the same codehash
        (address other,) = _deploySafe(SAFE_141_SINGLETON, address(SAFE_141_FACTORY), makeAddr("other"), 1, new Session[](0), false);
        assertEq(other.codehash, safe.codehash, "SafeProxy runtime codehash is a constant");
        console2.logBytes32(safe.codehash);

        // provenance: CREATE2 recompute from (factory, singleton, initializer, saltNonce)
        bytes32 salt = keccak256(abi.encodePacked(keccak256(initializer), SALT));
        bytes32 initHash = keccak256(abi.encodePacked(SAFE_141_FACTORY.proxyCreationCode(), uint256(uint160(SAFE_141_SINGLETON))));
        address predicted = address(uint160(uint256(keccak256(abi.encodePacked(bytes1(0xff), address(SAFE_141_FACTORY), salt, initHash)))));
        assertEq(predicted, safe, "account provably came from the canonical SafeProxyFactory");
    }

    function test_Q6_verify_rejects_secondSafeOwner() public onlyBaseSepoliaFork {
        _execSafe(safe, 0, abi.encodeCall(ISafeSpike.addOwnerWithThreshold, (makeAddr("second"), 1)), 0);
        (bool genuine,, string memory why) = _verify(safe);
        assertFalse(genuine);
        console2.log("verify after 2nd Safe owner:", why);
    }

    /// Two owner sets exist on this stack (Safe owners, OwnableValidator owners); they can drift.
    function test_Q6_verify_rejects_validatorOwnerDrift() public onlyBaseSepoliaFork {
        _execSafe(OWNABLE_VALIDATOR, 0, abi.encodeWithSignature("addOwner(address)", makeAddr("drift")), 0);
        (bool genuine,, string memory why) = _verify(safe);
        assertFalse(genuine);
        console2.log("verify after OwnableValidator owner drift:", why);
    }

    function test_Q6_verify_rejects_hookRemoved() public onlyBaseSepoliaFork {
        _execSafe(
            safe,
            0,
            abi.encodeCall(
                ISafe7579Spike.uninstallModule, (4, address(hook), abi.encode(uint8(1), SEL_EXECUTE, bytes("")))
            ),
            0
        );
        (bool genuine,, string memory why) = _verify(safe);
        assertFalse(genuine);
        console2.log("verify after owner removed hook:", why);
    }

    // ═════════════════════════════════════════════════════════════════════════════════════════
    // Q7 — build compatibility / fresh-Anvil deployment by replaying published init code
    // ═════════════════════════════════════════════════════════════════════════════════════════

    /// Replays SmartSessions' and Safe7579's original CREATE2 deployment transactions (salt +
    /// init code read from the chain) after wiping the canonical address. The code lands at the
    /// canonical address with the same codehash: the same replay works on a fresh Anvil once the
    /// Safe singleton CREATE2 factory is present there.
    function test_Q7_replayPublishedInitCode_landsOnCanonicalAddress() public onlyBaseSepoliaFork {
        _replay(SMART_SESSIONS, "0x447b34882dbdf8d27575929d64cab42920a12986cf5f3a115e53ea54d172658e");
        _replay(SAFE7579, "0x0f71467776febbca5625f5e929affc884b062eaecc6df9fecb3d02f5ec39a9ed");
    }

    function _replay(address canonical, string memory txHash) internal {
        bytes memory input = _txInput(txHash);
        bytes32 salt;
        assembly {
            salt := mload(add(input, 32))
        }
        bytes memory initCode = new bytes(input.length - 32);
        for (uint256 i; i < initCode.length; i++) {
            initCode[i] = input[i + 32];
        }
        address predicted = address(
            uint160(uint256(keccak256(abi.encodePacked(bytes1(0xff), SAFE_SINGLETON_CREATE2_FACTORY, salt, keccak256(initCode)))))
        );
        assertEq(predicted, canonical, "CREATE2(factory, salt, initcode) == canonical");
        bytes32 liveHash = canonical.codehash;
        vm.etch(canonical, ""); // simulate a chain without the component
        vm.resetNonce(canonical); // CREATE2 collides on nonce != 0 even with empty code
        // Safe7579's constructor CREATEs its Safe7579DCUtil (nonce 1) — wipe that too, as on fresh Anvil
        address child = vm.computeCreateAddress(canonical, 1);
        bytes32 childHash = child.codehash;
        if (child.code.length != 0) {
            vm.etch(child, "");
            vm.resetNonce(child);
        }
        (bool ok,) = SAFE_SINGLETON_CREATE2_FACTORY.call(input);
        assertTrue(ok, "replay deploy");
        assertEq(canonical.codehash, liveHash, "replayed runtime == live runtime");
        if (childHash != bytes32(0) && childHash != keccak256("")) {
            assertEq(child.codehash, childHash, "constructor child redeployed identically");
            console2.log("  constructor child", child, child.code.length);
        }
        console2.log("replayed", canonical, canonical.code.length);
    }

    function _slice(bytes memory b, uint256 from, uint256 n) internal pure returns (bytes memory out) {
        out = new bytes(n);
        for (uint256 i; i < n; i++) {
            out[i] = b[from + i];
        }
    }

    function _txInput(string memory txHash) internal returns (bytes memory) {
        string memory params = string.concat("[\"", txHash, "\"]");
        // vm.rpc returns the tx object ABI-encoded (forge 1.7.1 has no rpcJson). The `input` field is
        // the only dynamic bytes of the form salt(32) | init code starting 0x6080/0x60a0: find it.
        bytes memory raw = vm.rpc("eth_getTransactionByHash", params);
        for (uint256 i; i + 96 <= raw.length; i += 32) {
            uint256 len;
            assembly {
                len := mload(add(add(raw, 32), i))
            }
            if (len < 1000 || i + 32 + len > raw.length) continue;
            if (raw[i + 64] == 0x60 && raw[i + 66] == 0x60 && (raw[i + 65] == 0x80 || raw[i + 65] == 0xa0)) {
                return _slice(raw, i + 32, len);
            }
        }
        revert("tx input not found");
    }

    // ═════════════════════════════════════════════════════════════════════════════════════════
    // verify() candidate — property-based genuineness for Safe + Safe7579
    // ═════════════════════════════════════════════════════════════════════════════════════════
    function _verify(address a) internal view returns (bool, address, string memory) {
        if (a.code.length == 0) return (false, address(0), "no code");
        (bool ok, bytes memory ret) = a.staticcall(abi.encodeWithSelector(0xa619486e)); // masterCopy()
        if (!ok || abi.decode(ret, (address)) != SAFE_141_SINGLETON) return (false, address(0), "singleton");
        ISafeSpike s = ISafeSpike(a);
        if (address(uint160(uint256(bytes32(s.getStorageAt(uint256(FALLBACK_HANDLER_SLOT), 1))))) != SAFE7579) {
            return (false, address(0), "fallback handler != Safe7579");
        }
        (address[] memory mods,) = s.getModulesPaginated(SENTINEL, 10);
        if (mods.length != 1 || mods[0] != SAFE7579) return (false, address(0), "Safe modules != [Safe7579]");
        address[] memory owners = s.getOwners();
        if (owners.length != 1 || s.getThreshold() != 1) return (false, address(0), "not single-owner 1/1");
        address o = owners[0];
        if (o.code.length != 0) return (false, address(0), "owner is not an EOA");
        ISafe7579Spike a7 = ISafe7579Spike(a);
        if (a7.getActiveHook() != address(0)) return (false, o, "unexpected GLOBAL hook");
        if (
            a7.getActiveHook(SEL_EXECUTE) != address(hook) || a7.getActiveHook(SEL_EXECUTE_FROM_EXECUTOR) != address(hook)
                || a7.getActiveHook(SEL_INSTALL) != address(hook) || a7.getActiveHook(SEL_UNINSTALL) != address(hook)
        ) return (false, o, "IntegrityHook missing on an execution selector");
        (address[] memory execs,) = a7.getExecutorsPaginated(SENTINEL, 10);
        if (execs.length != 0) return (false, o, "unexpected 7579 executor");
        (address[] memory vals,) = a7.getValidatorsPaginated(SENTINEL, 10);
        for (uint256 i; i < vals.length; i++) {
            if (vals[i] == OWNABLE_VALIDATOR) {
                address[] memory vo = IOwnableValidatorSpike(OWNABLE_VALIDATOR).getOwners(a);
                if (vo.length != 1 || vo[0] != o) return (false, o, "OwnableValidator owners != Safe owner");
            } else if (vals[i] != SMART_SESSIONS) {
                return (false, o, "unexpected 7579 validator");
            }
        }
        // guard slot is read too; the spike installs none by default
        bytes32 g = bytes32(s.getStorageAt(uint256(GUARD_SLOT), 1));
        if (g != bytes32(0) && address(uint160(uint256(g))) != address(guard)) return (false, o, "unknown guard");
        return (true, o, "ok");
    }

    // ═════════════════════════════════════════════════════════════════════════════════════════
    // helpers
    // ═════════════════════════════════════════════════════════════════════════════════════════
    string constant CONTENTS_TYPE = "Mail(address to,string body)";

    function _agentSession(address tgt, bytes4 sel, bytes32 salt) internal view returns (Session memory s) {
        address[] memory keys = new address[](1);
        keys[0] = sessionKey;
        s.sessionValidator = OWNABLE_VALIDATOR; // as ISessionValidator (stateless)
        s.sessionValidatorInitData = abi.encode(uint256(1), keys);
        s.salt = salt;
        s.actions = new ActionData[](1);
        s.actions[0].actionTargetSelector = sel;
        s.actions[0].actionTarget = tgt;
        s.actions[0].actionPolicies = new PolicyData[](1);
        s.actions[0].actionPolicies[0] = PolicyData(SUDO_POLICY, "");
        // erc7739Policies left EMPTY: no content, no 1271 policy => session cannot sign 1271
    }

    function _deploySafe(
        address singleton,
        address factory,
        address o,
        uint256 salt,
        Session[] memory sessions,
        bool globalHook
    )
        internal
        returns (address proxy, bytes memory init)
    {
        address[] memory ownerArr = new address[](1);
        ownerArr[0] = o;
        ModuleInit[] memory validators = new ModuleInit[](2);
        validators[0] = ModuleInit(OWNABLE_VALIDATOR, abi.encode(uint256(1), ownerArr));
        validators[1] = ModuleInit(
            SMART_SESSIONS, sessions.length == 0 ? bytes("") : abi.encodePacked(uint8(1), abi.encode(sessions))
        );
        ModuleInit[] memory hooks;
        if (globalHook) {
            hooks = new ModuleInit[](1);
            hooks[0] = ModuleInit(address(hook), abi.encode(uint8(0), bytes4(0), bytes(""))); // GLOBAL
        } else {
            bytes4[4] memory sels = [SEL_EXECUTE, SEL_EXECUTE_FROM_EXECUTOR, SEL_INSTALL, SEL_UNINSTALL];
            hooks = new ModuleInit[](4);
            for (uint256 i; i < 4; i++) {
                hooks[i] = ModuleInit(address(hook), abi.encode(uint8(1), sels[i], bytes(""))); // SIG
            }
        }
        bytes memory initAcct = abi.encodeCall(
            ISafe7579Spike.initializeAccount,
            (validators, new ModuleInit[](0), new ModuleInit[](0), hooks, RegistryInit(address(0), new address[](0), 0))
        );
        init = abi.encodeCall(
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

    function _safeTxHash(address to, uint256 value, bytes memory data, uint8 op) internal view returns (bytes32) {
        return ISafeSpike(safe).getTransactionHash(
            to, value, data, op, 0, 0, 0, address(0), address(0), ISafeSpike(safe).nonce()
        );
    }

    function _execSafe(address to, uint256 value, bytes memory data, uint8 op) internal {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(ownerKey, _safeTxHash(to, value, data, op));
        bool ok = ISafeSpike(safe).execTransaction(
            to, value, data, op, 0, 0, 0, address(0), payable(address(0)), abi.encodePacked(r, s, v)
        );
        require(ok, "execTransaction failed");
    }

    function _setGuard(address g) internal {
        _execSafe(safe, 0, abi.encodeCall(ISafeSpike.setGuard, (g)), 0);
    }

    function _installCompatFallback() internal {
        _execSafe(
            safe,
            0,
            abi.encodeCall(
                ISafe7579Spike.installModule,
                (3, SMART_SESSIONS_COMPAT_FALLBACK, abi.encode(bytes4(0x84b0196e), bytes1(0xFE), bytes("")))
            ),
            0
        );
    }

    function _baseOp(address validator, bytes memory callData) internal view returns (SpikeUserOp memory op) {
        op.sender = safe;
        op.nonce = ISafe7579Spike(safe).getNonce(safe, validator);
        op.callData = callData;
        op.accountGasLimits = bytes32((uint256(3_000_000) << 128) | uint256(3_000_000));
        op.preVerificationGas = 100_000;
        op.gasFees = bytes32(0); // zero fees: no prefund needed in the fork
    }

    function _sessionSig(bytes32 pid, bytes32 userOpHash) internal view returns (bytes memory) {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(sessionKeyPk, userOpHash); // v=27/28: raw ecrecover
        return abi.encodePacked(uint8(0), pid, abi.encodePacked(r, s, v)); // SmartSessionMode.USE
    }

    function _sendSessionOp(bytes32 pid, address to, uint256 value, bytes memory data) internal {
        bytes memory callData =
            abi.encodeCall(ISafe7579Spike.execute, (MODE_SINGLE, abi.encodePacked(to, value, data)));
        SpikeUserOp memory op = _baseOp(SMART_SESSIONS, callData);
        op.signature = _sessionSig(pid, EP.getUserOpHash(op));
        _handle(op);
    }

    function _sendOwnerOp(address to, uint256 value, bytes memory data) internal {
        bytes memory callData =
            abi.encodeCall(ISafe7579Spike.execute, (MODE_SINGLE, abi.encodePacked(to, value, data)));
        SpikeUserOp memory op = _baseOp(OWNABLE_VALIDATOR, callData);
        bytes32 h = EP.getUserOpHash(op);
        bytes32 ethHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", h));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(ownerKey, ethHash);
        op.signature = abi.encodePacked(r, s, v);
        _handle(op);
    }

    function _handle(SpikeUserOp memory op) internal {
        SpikeUserOp[] memory ops = new SpikeUserOp[](1);
        ops[0] = op;
        vm.prank(bundler, bundler);
        EP.handleOps(ops, payable(bundler));
    }

    /// Asserts (1) the live SmartSessions validator itself reverts with `expected` for this op, and
    /// (2) EntryPoint.handleOps rejects the op (AA23, the validator revert wrapped by Safe7579).
    function _expectRejected(SpikeUserOp memory op, bytes memory expected) internal {
        bytes32 h = EP.getUserOpHash(op);
        uint256 snap = vm.snapshotState();
        vm.prank(safe);
        vm.expectRevert(expected);
        ISmartSessionSpike(SMART_SESSIONS).validateUserOp(op, h);
        vm.revertToState(snap);

        SpikeUserOp[] memory ops = new SpikeUserOp[](1);
        ops[0] = op;
        vm.prank(bundler, bundler);
        (bool ok, bytes memory ret) = address(EP).call(abi.encodeCall(IEntryPointV07.handleOps, (ops, payable(bundler))));
        assertFalse(ok, "handleOps should reject the session op");
        assertEq(bytes4(ret), IEntryPointV07.FailedOpWithRevert.selector);
        console2.log("rejected; SmartSessions error:");
        console2.logBytes(expected);
    }

    function _registeredAgentId() internal returns (uint256) {
        Vm.Log[] memory logs = vm.getRecordedLogs();
        bytes32 topic = keccak256("Registered(uint256,string,address)");
        for (uint256 i; i < logs.length; i++) {
            if (logs[i].emitter == address(AGENT0) && logs[i].topics[0] == topic) return uint256(logs[i].topics[1]);
        }
        revert("no Registered event");
    }

    // ERC-7739 nested TypedDataSign signature from the session key, wrapped for Safe7579 routing:
    // validator(20) | permissionId(32) | sig(65) | appDomainSep(32) | contents(32) | contentsType | uint16(len)
    function _session7739Sig(bytes32 pid, bytes32 h, bool haveDomain) internal returns (bytes memory) {
        bytes32 appSep = keccak256("spike app domain");
        if (!haveDomain) {
            // any well-formed bytes: the call reverts before the signature is examined
            return abi.encodePacked(SMART_SESSIONS, pid, new bytes(65), appSep, h, CONTENTS_TYPE, uint16(bytes(CONTENTS_TYPE).length));
        }
        return _session7739SigFor(pid, appSep, h);
    }

    function _session7739SigFor(bytes32 pid, bytes32 appSep, bytes32 contents) internal returns (bytes memory) {
        (, bytes memory dom) = safe.staticcall(abi.encodeWithSelector(0x84b0196e)); // eip712Domain() via compat fallback
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

import { Vm } from "forge-std/Vm.sol";
