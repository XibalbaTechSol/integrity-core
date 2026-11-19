// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { AccessControl } from "@openzeppelin/contracts/access/AccessControl.sol";
import { IOperationContext } from "./IOperationContext.sol";

interface IAgentRegistryView {
    function isRegisteredAgent(address agent) external view returns (bool);
}

interface IAISRegistryView {
    function latest(address agent)
        external
        view
        returns (uint32 score, uint64 windowEnd, bytes32 evidenceRoot);
    function postedAt(address agent) external view returns (uint64);
}

interface IStakeVaultView {
    struct Stake {
        uint256 amount;
        uint256 locked;
        bool frozen;
        uint64 cooldownEnd;
    }

    function stakeOf(address agent) external view returns (Stake memory);
}

interface IERC7579Account {
    function isModuleInstalled(uint256 moduleTypeId, address module, bytes calldata additionalContext)
        external
        view
        returns (bool);
}

struct Execution {
    address target;
    uint256 value;
    bytes callData;
}

/// @title IntegrityHook
/// @notice Standard ERC-7579 Hook enforcing agent spend limits, AIS reputation floors, and staking gates.
contract IntegrityHook is AccessControl {
    bytes32 public constant GOVERNANCE_ROLE = keccak256("GOVERNANCE_ROLE");

    // ERC-7579 selectors
    bytes4 internal constant EXECUTE_SELECTOR = 0xe9ae5c53;
    bytes4 internal constant EXECUTE_FROM_EXECUTOR_SELECTOR = 0xd691c964;

    // Public hook errors (mapped by SDK §6.8)
    error LimitExceeded();
    error AisBelowFloor(uint32 score, uint32 floor);
    error AisStale(uint64 postedAt);
    error CoSignerRequired();
    error OwnerApprovalRequired();
    error Frozen();
    error AwaitingFirstCheckpoint();
    error NotOwner();
    error NotRegistered();
    error DelegatecallDenied();
    error ZeroMaxCheckpointAge();
    error FloorBelowProtocol(uint32 floor, uint32 protocolFloor);
    error LoosenNotAllowed();

    struct AccountConfig {
        uint32 windowSeconds;
        uint32 ownerFloor;
        bool initialized;
        bytes32 reservedCollateralSlot; // Reserved for future stake collateral (D-L)
    }

    IAgentRegistryView public registry;
    IAISRegistryView public ais;
    IStakeVaultView public vault;
    IOperationContext public ctx;

    uint32 public protocolFloor;
    uint64 public maxCheckpointAge;

    mapping(address => AccountConfig) public config;
    mapping(address => bool) public isProtocolTarget;

    constructor(
        address governance,
        IAgentRegistryView _registry,
        IAISRegistryView _ais,
        IStakeVaultView _vault,
        IOperationContext _ctx,
        uint32 _protocolFloor,
        uint64 _maxCheckpointAge
    ) {
        if (_maxCheckpointAge == 0) revert ZeroMaxCheckpointAge();

        _grantRole(DEFAULT_ADMIN_ROLE, governance);
        _grantRole(GOVERNANCE_ROLE, governance);

        registry = _registry;
        ais = _ais;
        vault = _vault;
        ctx = _ctx;
        protocolFloor = _protocolFloor;
        maxCheckpointAge = _maxCheckpointAge;
    }

    // ── ERC-7579 Module Lifecycle ──────────────────────────────────────────

    function onInstall(bytes calldata initConfig) external {
        (uint32 windowSeconds, uint32 ownerFloor) = abi.decode(initConfig, (uint32, uint32));
        config[msg.sender] = AccountConfig({
            windowSeconds: windowSeconds,
            ownerFloor: ownerFloor,
            initialized: true,
            reservedCollateralSlot: bytes32(0)
        });
    }

    function onUninstall(bytes calldata) external {
        delete config[msg.sender];
    }

    function isModuleType(uint256 t) external pure returns (bool) {
        return t == 4; // MODULE_TYPE_HOOK
    }

    function isInitialized(address account) external view returns (bool) {
        return config[account].initialized;
    }

    function isConfigured(address account) external view returns (bool) {
        return config[account].initialized;
    }

    // ── Governance Setters (GOVERNANCE_ROLE) ───────────────────────────────

    function setProtocolTarget(address target, bool isProtocol) external onlyRole(GOVERNANCE_ROLE) {
        isProtocolTarget[target] = isProtocol;
    }

    function setProtocolFloor(uint32 floor) external onlyRole(GOVERNANCE_ROLE) {
        protocolFloor = floor;
    }

    function setMaxCheckpointAge(uint64 age) external onlyRole(GOVERNANCE_ROLE) {
        if (age == 0) revert ZeroMaxCheckpointAge();
        maxCheckpointAge = age;
    }

    function setOperationContext(IOperationContext _ctx) external onlyRole(GOVERNANCE_ROLE) {
        ctx = _ctx;
    }

    // ── ERC-7579 Hook Entrypoints ──────────────────────────────────────────

    function preCheck(address /*msgSender*/, uint256 /*msgValue*/, bytes calldata msgData)
        external
        returns (bytes memory hookData)
    {
        address account = msg.sender;
        IOperationContext.Role role = ctx.roleOf(account);

        if (msgData.length >= 4) {
            bytes4 sel = bytes4(msgData[:4]);
            if (sel != EXECUTE_SELECTOR && sel != EXECUTE_FROM_EXECUTOR_SELECTOR) {
                // Admin selector on the account itself (e.g. installModule, uninstallModule, etc.)
                if (role != IOperationContext.Role.Owner) revert NotOwner();
                return "";
            }

            bytes32 mode = bytes32(msgData[4:36]);
            uint256 offset = uint256(bytes32(msgData[36:68]));
            uint256 len = uint256(bytes32(msgData[4 + offset:4 + offset + 32]));
            bytes calldata executionCalldata = msgData[4 + offset + 32:4 + offset + 32 + len];
            bytes1 callType = bytes1(mode);

            if (callType == 0xff) {
                // Delegatecall mode reverts unless role is Owner
                if (role != IOperationContext.Role.Owner) revert DelegatecallDenied();
                // For Owner, delegatecall falls through to value-moving checks 1–3
            } else if (callType == 0x00) {
                // Single call: target (20) + value (32) + callData
                if (executionCalldata.length < 52) revert LimitExceeded();
                address callTarget = address(bytes20(executionCalldata[:20]));
                uint256 callVal = uint256(bytes32(executionCalldata[20:52]));

                if (_isInstalledModule(account, callTarget)) {
                    // Target is account itself, this hook, or an installed module -> Admin
                    if (role != IOperationContext.Role.Owner) revert NotOwner();
                    return "";
                }

                if (isProtocolTarget[callTarget]) {
                    // Protocol target (ActionAnchor, XNS): owner-only admin when value == 0
                    if (role == IOperationContext.Role.Owner && callVal == 0) {
                        return "";
                    }
                    revert NotOwner();
                }
            } else if (callType == 0x01) {
                // Batch call
                Execution[] memory execs = abi.decode(executionCalldata, (Execution[]));
                bool allAdmin = true;

                for (uint256 i = 0; i < execs.length; i++) {
                    address t = execs[i].target;
                    uint256 v = execs[i].value;

                    if (_isInstalledModule(account, t)) {
                        continue;
                    }
                    if (isProtocolTarget[t]) {
                        if (role == IOperationContext.Role.Owner && v == 0) {
                            continue;
                        }
                        revert NotOwner();
                    }
                    allAdmin = false;
                    break;
                }

                if (allAdmin) {
                    if (role != IOperationContext.Role.Owner) revert NotOwner();
                    return "";
                }
            }
        }

        // ── Value-Moving Operations: Checks 1–3 ─────────────────────────────

        // Check 1: StakeVault freeze check
        if (vault.stakeOf(account).frozen) {
            revert Frozen();
        }

        // Check 2: AgentRegistry registration check
        if (!registry.isRegisteredAgent(account)) {
            revert NotRegistered();
        }

        // Check 3: AIS reputation checks
        uint64 posted = ais.postedAt(account);
        if (posted == 0) {
            revert AwaitingFirstCheckpoint();
        }
        if (block.timestamp - posted > maxCheckpointAge) {
            revert AisStale(posted);
        }

        (uint32 score,,) = ais.latest(account);
        uint32 floor = protocolFloor > config[account].ownerFloor ? protocolFloor : config[account].ownerFloor;
        if (score < floor) {
            revert AisBelowFloor(score, floor);
        }

        return "";
    }

    function postCheck(bytes calldata /*hookData*/) external {}

    // ── Internal Helpers ───────────────────────────────────────────────────

    function _isInstalledModule(address account, address target) internal view returns (bool) {
        if (target == account || target == address(this)) return true;
        for (uint256 t = 1; t <= 4; t++) {
            try IERC7579Account(account).isModuleInstalled(t, target, "") returns (bool installed) {
                if (installed) return true;
            } catch {}
        }
        return false;
    }
}
