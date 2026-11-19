// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { SafeOperationContext } from "./SafeOperationContext.sol";
import { IntegrityHook, IAgentRegistryView, IAISRegistryView, IStakeVaultView } from "./IntegrityHook.sol";

interface ISafeGuard {
    function checkTransaction(
        address to,
        uint256 value,
        bytes memory data,
        uint8 operation,
        uint256 safeTxGas,
        uint256 baseGas,
        uint256 gasPrice,
        address gasToken,
        address payable refundReceiver,
        bytes memory signatures,
        address msgSender
    ) external;

    function checkAfterExecution(bytes32 txHash, bool success) external;
}

/// @title IntegrityGuard
/// @notice Safe transaction guard for Safe v1.4.1 accounts operating with IntegrityHook.
/// Secures direct Safe execTransaction executions by:
/// 1. Flagging direct execution on SafeOperationContext so roleOf(account) resolves to Role.Owner.
/// 2. Preventing tampering with Safe7579 module or removing IntegrityGuard.
/// 3. Enforcing protocol-level safety gates (not frozen, registered, AIS floor & freshness)
///    on all value-moving direct owner executions.
contract IntegrityGuard is ISafeGuard {
    error Frozen();
    error NotRegistered();
    error AwaitingFirstCheckpoint();
    error AisStale(uint64 postedAt);
    error AisBelowFloor(uint32 score, uint32 floor);
    error GuardProtected();
    error ModuleProtected();
    error Unauthorized();

    bytes4 internal constant SET_GUARD_SELECTOR = 0xe19a9dd9;
    bytes4 internal constant DISABLE_MODULE_SELECTOR = 0xe009cfde;

    SafeOperationContext public immutable context;
    IntegrityHook public immutable hook;
    address public immutable safe7579;

    constructor(SafeOperationContext context_, IntegrityHook hook_, address safe7579_) {
        context = context_;
        hook = hook_;
        safe7579 = safe7579_;
    }

    /// @inheritdoc ISafeGuard
    function checkTransaction(
        address to,
        uint256 value,
        bytes memory data,
        uint8, /* operation */
        uint256, /* safeTxGas */
        uint256, /* baseGas */
        uint256, /* gasPrice */
        address, /* gasToken */
        address payable, /* refundReceiver */
        bytes memory, /* signatures */
        address /* msgSender */
    ) external override {
        address account = msg.sender;

        // 1. Set direct execution flag on SafeOperationContext
        context.setDirectExecution(account, true);

        // 2. Classify execution
        bool isAdmin = false;

        if (to == account) {
            // Self-call: administrative configuration on the Safe
            if (data.length >= 4) {
                bytes4 sel;
                assembly {
                    sel := mload(add(data, 32))
                }
                // Prohibit changing or removing IntegrityGuard
                if (sel == SET_GUARD_SELECTOR) {
                    revert GuardProtected();
                }
                // Prohibit disabling Safe7579 adapter
                if (sel == DISABLE_MODULE_SELECTOR && data.length >= 68) {
                    address moduleToDisable;
                    assembly {
                        moduleToDisable := mload(add(data, 68))
                    }
                    if (moduleToDisable == safe7579) {
                        revert ModuleProtected();
                    }
                }
            }
            isAdmin = true;
        } else if (to == address(hook) || to == safe7579) {
            // Module admin call
            isAdmin = true;
        } else if (hook.isProtocolTarget(to) && value == 0) {
            // Protocol targets (ActionAnchor, XNS) with zero native value
            isAdmin = true;
        }

        // 3. For value-moving operations, enforce protocol safety gates
        if (!isAdmin) {
            IStakeVaultView vault = hook.vault();
            if (vault.stakeOf(account).frozen) {
                revert Frozen();
            }

            IAgentRegistryView registry = hook.registry();
            if (!registry.isRegisteredAgent(account)) {
                revert NotRegistered();
            }

            IAISRegistryView ais = hook.ais();
            uint64 posted = ais.postedAt(account);
            if (posted == 0) {
                revert AwaitingFirstCheckpoint();
            }
            if (block.timestamp - posted > hook.maxCheckpointAge()) {
                revert AisStale(posted);
            }

            (uint32 score,,) = ais.latest(account);
            (, uint32 ownerFloor,,) = hook.config(account);
            uint32 protocolFloor = hook.protocolFloor();
            uint32 floor = protocolFloor > ownerFloor ? protocolFloor : ownerFloor;
            if (score < floor) {
                revert AisBelowFloor(score, floor);
            }
        }
    }

    /// @inheritdoc ISafeGuard
    function checkAfterExecution(bytes32, /* txHash */ bool /* success */) external override {
        address account = msg.sender;
        context.setDirectExecution(account, false);
    }
}
