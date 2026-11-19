// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import {
    IntegrityHook,
    IAgentRegistryView,
    IAISRegistryView,
    IStakeVaultView
} from "../../src/wallet/IntegrityHook.sol";
import { IOperationContext } from "../../src/wallet/IOperationContext.sol";
import { MockOperationContext } from "./mocks/MockOperationContext.sol";
import { MockAccountVerifier } from "./mocks/MockAccountVerifier.sol";
import { MockGovernedAccount, Execution } from "./mocks/MockGovernedAccount.sol";
import {
    MockAgentRegistry,
    MockAISRegistry,
    MockStakeVault
} from "./mocks/MockTrustLayer.sol";

contract IntegrityHookBase is Test {
    address public governance;
    address public owner;
    address public sessionKey;

    MockOperationContext public ctx;
    MockAccountVerifier public verifier;
    MockAgentRegistry public registry;
    MockAISRegistry public ais;
    MockStakeVault public vault;

    IntegrityHook public hook;
    MockGovernedAccount public account;

    uint32 public constant DEFAULT_PROTOCOL_FLOOR = 0;
    uint64 public constant DEFAULT_MAX_CHECKPOINT_AGE = 1 days;

    function setUp() public virtual {
        governance = makeAddr("governance");
        owner = makeAddr("owner");
        sessionKey = makeAddr("sessionKey");

        ctx = new MockOperationContext();
        verifier = new MockAccountVerifier();
        registry = new MockAgentRegistry();
        ais = new MockAISRegistry();
        vault = new MockStakeVault();

        hook = new IntegrityHook(
            governance,
            IAgentRegistryView(address(registry)),
            IAISRegistryView(address(ais)),
            IStakeVaultView(address(vault)),
            IOperationContext(address(ctx)),
            DEFAULT_PROTOCOL_FLOOR,
            DEFAULT_MAX_CHECKPOINT_AGE
        );

        account = new MockGovernedAccount();
        verifier.setAccount(address(account), true, owner);

        // Standard setup from spec: registers mock account, posts checkpoint at 8000
        registry.setRegistered(address(account), true);
        ais.setCheckpoint(
            address(account),
            8000,
            100,
            bytes32(0),
            uint64(block.timestamp)
        );

        // Install hook on account with windowSeconds = 1 days, ownerFloor = 0
        account.installModule(4, address(hook), abi.encode(uint32(1 days), uint32(0)));
    }

    function _singleCall(address target, uint256 val, bytes memory data)
        internal
        pure
        returns (bytes memory)
    {
        return abi.encodePacked(target, val, data);
    }
}
