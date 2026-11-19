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

interface IERC20Minimal {
    function balanceOf(address account) external view returns (uint256);
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
    error LimitExceeded(address token, uint256 attempted, uint256 remaining);
    error NotAllowlisted(address target);
    error UnknownSelector(address token, bytes4 selector);
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

    struct TokenLimit {
        uint128 perCall;
        uint128 perWindow;
    }

    struct WindowRecord {
        uint64 windowStart;
        uint192 spent;
    }

    IAgentRegistryView public registry;
    IAISRegistryView public ais;
    IStakeVaultView public vault;
    IOperationContext public ctx;

    uint32 public protocolFloor;
    uint64 public maxCheckpointAge;

    mapping(address => AccountConfig) public config;
    mapping(address => bool) public isProtocolTarget;

    // Spend limits & allowlist
    mapping(address => mapping(address => TokenLimit)) public tokenLimits;
    mapping(address => mapping(address => WindowRecord)) internal _windows;
    mapping(address => mapping(address => bool)) public isAllowlisted;
    mapping(address => bool) public allowlistDisabled;

    // Known tokens (governance-set)
    mapping(address => bool) public isKnownToken;
    address[] public knownTokens;
    mapping(address => uint256) internal _knownTokenIndex;

    modifier onlyAccountOwner() {
        if (ctx.roleOf(msg.sender) != IOperationContext.Role.Owner) revert NotOwner();
        _;
    }

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

    // ── Account Setters (Owner only) ───────────────────────────────────────

    function setTokenLimit(address token, uint128 perCall, uint128 perWindow) external onlyAccountOwner {
        tokenLimits[msg.sender][token] = TokenLimit({ perCall: perCall, perWindow: perWindow });
    }

    function setNativeLimit(uint128 perCall, uint128 perWindow) external onlyAccountOwner {
        tokenLimits[msg.sender][address(0)] = TokenLimit({ perCall: perCall, perWindow: perWindow });
    }

    function setWindow(uint32 windowSeconds) external onlyAccountOwner {
        config[msg.sender].windowSeconds = windowSeconds;
    }

    function setAllowlisted(address target, bool allowed) external onlyAccountOwner {
        isAllowlisted[msg.sender][target] = allowed;
    }

    function setAllowlistEnabled(bool enabled) external onlyAccountOwner {
        allowlistDisabled[msg.sender] = !enabled;
    }

    // ── Governance Setters (GOVERNANCE_ROLE) ───────────────────────────────

    function setKnownToken(address token, bool known) external onlyRole(GOVERNANCE_ROLE) {
        if (known && !isKnownToken[token]) {
            isKnownToken[token] = true;
            _knownTokenIndex[token] = knownTokens.length;
            knownTokens.push(token);
        } else if (!known && isKnownToken[token]) {
            isKnownToken[token] = false;
            uint256 idx = _knownTokenIndex[token];
            address last = knownTokens[knownTokens.length - 1];
            knownTokens[idx] = last;
            _knownTokenIndex[last] = idx;
            knownTokens.pop();
            delete _knownTokenIndex[token];
        }
    }

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

    // ── View Helpers ───────────────────────────────────────────────────────

    function windowSpent(address account, address token) external view returns (uint256) {
        uint32 winSecs = config[account].windowSeconds;
        WindowRecord memory w = _windows[account][token];
        if (winSecs == 0 || block.timestamp >= w.windowStart + winSecs) {
            return 0;
        }
        return w.spent;
    }

    // ── ERC-7579 Hook Entrypoints ──────────────────────────────────────────

    function preCheck(address /*msgSender*/, uint256 /*msgValue*/, bytes calldata msgData)
        external
        returns (bytes memory hookData)
    {
        address account = msg.sender;
        IOperationContext.Role role = ctx.roleOf(account);

        bool isOwner = (role == IOperationContext.Role.Owner);
        bool enforceLimits = !isOwner;

        if (msgData.length >= 4) {
            bytes4 sel = bytes4(msgData[:4]);
            if (sel != EXECUTE_SELECTOR && sel != EXECUTE_FROM_EXECUTOR_SELECTOR) {
                // Admin selector on the account itself (e.g. installModule, uninstallModule, etc.)
                if (!isOwner) revert NotOwner();
                return "";
            }

            bytes32 mode = bytes32(msgData[4:36]);
            uint256 offset = uint256(bytes32(msgData[36:68]));
            uint256 len = uint256(bytes32(msgData[4 + offset:4 + offset + 32]));
            bytes calldata executionCalldata = msgData[4 + offset + 32:4 + offset + 32 + len];
            bytes1 callType = bytes1(mode);

            if (callType == 0xff) {
                // Delegatecall mode reverts unless role is Owner
                if (!isOwner) revert DelegatecallDenied();
                // For Owner, delegatecall falls through to value-moving checks 1–3
            } else if (callType == 0x00) {
                // Single call: target (20) + value (32) + callData
                if (executionCalldata.length < 52) revert LimitExceeded(address(0), 0, 0);
                address callTarget = address(bytes20(executionCalldata[:20]));
                uint256 callVal = uint256(bytes32(executionCalldata[20:52]));

                if (_isInstalledModule(account, callTarget)) {
                    // Target is account itself, this hook, or an installed module -> Admin
                    if (!isOwner) revert NotOwner();
                    return "";
                }

                if (isProtocolTarget[callTarget]) {
                    // Protocol target (ActionAnchor, XNS): owner-only admin when value == 0
                    if (isOwner && callVal == 0) {
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
                        if (isOwner && v == 0) {
                            continue;
                        }
                        revert NotOwner();
                    }
                    allAdmin = false;
                    break;
                }

                if (allAdmin) {
                    if (!isOwner) revert NotOwner();
                    return "";
                }
            }
        }

        // ── Value-Moving Operations: Checks 1–3 (In Strict Order) ──────────

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

        // ── Value-Moving Operations: Checks 4–6 (Allowlist, Decoding, Limits)
        if (msgData.length >= 4) {
            bytes4 sel = bytes4(msgData[:4]);
            if (sel == EXECUTE_SELECTOR || sel == EXECUTE_FROM_EXECUTOR_SELECTOR) {
                bytes32 mode = bytes32(msgData[4:36]);
                uint256 offset = uint256(bytes32(msgData[36:68]));
                uint256 len = uint256(bytes32(msgData[4 + offset:4 + offset + 32]));
                bytes calldata executionCalldata = msgData[4 + offset + 32:4 + offset + 32 + len];
                bytes1 callType = bytes1(mode);

                if (callType == 0x00) {
                    address callTarget = address(bytes20(executionCalldata[:20]));
                    uint256 callVal = uint256(bytes32(executionCalldata[20:52]));
                    bytes calldata callPayload = executionCalldata[52:];
                    _checkExecution(account, callTarget, callVal, callPayload, enforceLimits);
                } else if (callType == 0x01) {
                    Execution[] memory execs = abi.decode(executionCalldata, (Execution[]));
                    for (uint256 i = 0; i < execs.length; i++) {
                        _checkExecution(account, execs[i].target, execs[i].value, execs[i].callData, enforceLimits);
                    }
                }
            }
        }

        // ── Snapshot Pre-Balances for postCheck ─────────────────────────────
        uint256 tokenCount = knownTokens.length;
        address[] memory activeTokens = new address[](tokenCount);
        uint256[] memory preBalances = new uint256[](tokenCount);

        for (uint256 i = 0; i < tokenCount; i++) {
            address t = knownTokens[i];
            activeTokens[i] = t;
            preBalances[i] = IERC20Minimal(t).balanceOf(account);
        }

        return abi.encode(account, isOwner, account.balance, activeTokens, preBalances);
    }

    function postCheck(bytes calldata hookData) external {
        if (hookData.length == 0) return;

        (
            address account,
            bool isOwner,
            uint256 preNative,
            address[] memory tokens,
            uint256[] memory preBals
        ) = abi.decode(hookData, (address, bool, uint256, address[], uint256[]));

        bool enforceLimits = !isOwner;

        // Measured native decrease
        if (account.balance < preNative) {
            uint256 nativeDelta = preNative - account.balance;
            _recordSpend(account, address(0), nativeDelta, enforceLimits);
        }

        // Measured known token decreases
        for (uint256 i = 0; i < tokens.length; i++) {
            uint256 postBal = IERC20Minimal(tokens[i]).balanceOf(account);
            if (postBal < preBals[i]) {
                uint256 tokenDelta = preBals[i] - postBal;
                _recordSpend(account, tokens[i], tokenDelta, enforceLimits);
            }
        }
    }

    // ── Internal Helpers ───────────────────────────────────────────────────

    function _checkExecution(
        address account,
        address callTarget,
        uint256 callVal,
        bytes memory data,
        bool enforceLimits
    ) internal {
        if (callVal > 0 && enforceLimits) {
            uint256 nativeCap = tokenLimits[account][address(0)].perCall;
            if (nativeCap == 0 || callVal > nativeCap) {
                revert LimitExceeded(address(0), callVal, nativeCap);
            }
        }

        if (isKnownToken[callTarget]) {
            _checkTokenCall(account, callTarget, data, enforceLimits);
        } else {
            if (enforceLimits && !allowlistDisabled[account] && !isAllowlisted[account][callTarget]) {
                revert NotAllowlisted(callTarget);
            }
        }
    }

    function _loadWord(bytes memory data, uint256 offset) internal pure returns (bytes32 word) {
        assembly {
            word := mload(add(add(data, 32), offset))
        }
    }

    function _checkTokenCall(
        address account,
        address token,
        bytes memory data,
        bool enforceLimits
    ) internal {
        if (data.length < 4) {
            revert UnknownSelector(token, bytes4(0));
        }

        bytes4 sel = bytes4(_loadWord(data, 0));
        if (sel == 0xa9059cbb) {
            // transfer(address to, uint256 amount)
            if (data.length < 68) revert UnknownSelector(token, sel);
            address to = address(uint160(uint256(_loadWord(data, 4))));
            uint256 amount = uint256(_loadWord(data, 36));
            if (enforceLimits) {
                if (!allowlistDisabled[account] && !isAllowlisted[account][to]) revert NotAllowlisted(to);
                uint256 perCallCap = tokenLimits[account][token].perCall;
                if (perCallCap == 0 || amount > perCallCap) revert LimitExceeded(token, amount, perCallCap);
            }
        } else if (sel == 0x23b872dd) {
            // transferFrom(address from, address to, uint256 amount)
            if (data.length < 100) revert UnknownSelector(token, sel);
            address from = address(uint160(uint256(_loadWord(data, 4))));
            address to = address(uint160(uint256(_loadWord(data, 36))));
            uint256 amount = uint256(_loadWord(data, 68));
            if (from == account && enforceLimits) {
                if (!allowlistDisabled[account] && !isAllowlisted[account][to]) revert NotAllowlisted(to);
                uint256 perCallCap = tokenLimits[account][token].perCall;
                if (perCallCap == 0 || amount > perCallCap) revert LimitExceeded(token, amount, perCallCap);
            }
        } else if (sel == 0x095ea7b3) {
            // approve(address spender, uint256 amount)
            if (data.length < 68) revert UnknownSelector(token, sel);
            address spender = address(uint160(uint256(_loadWord(data, 4))));
            uint256 amount = uint256(_loadWord(data, 36));
            if (enforceLimits) {
                if (!allowlistDisabled[account] && !isAllowlisted[account][spender]) revert NotAllowlisted(spender);
            }
            // approve amounts are added to the window at preCheck time
            _recordSpend(account, token, amount, enforceLimits);
        } else if (sel == 0x42842e0e || sel == 0xb88d4fde) {
            // safeTransferFrom
            if (data.length < 100) revert UnknownSelector(token, sel);
            address from = address(uint160(uint256(_loadWord(data, 4))));
            address to = address(uint160(uint256(_loadWord(data, 36))));
            uint256 amount = uint256(_loadWord(data, 68));
            if (from == account && enforceLimits) {
                if (!allowlistDisabled[account] && !isAllowlisted[account][to]) revert NotAllowlisted(to);
                uint256 perCallCap = tokenLimits[account][token].perCall;
                if (perCallCap == 0 || amount > perCallCap) revert LimitExceeded(token, amount, perCallCap);
            }
        } else if (sel == 0x42966c68) {
            // burn(uint256 amount)
            if (data.length < 36) revert UnknownSelector(token, sel);
            uint256 amount = uint256(_loadWord(data, 4));
            if (enforceLimits) {
                uint256 perCallCap = tokenLimits[account][token].perCall;
                if (perCallCap == 0 || amount > perCallCap) revert LimitExceeded(token, amount, perCallCap);
            }
        } else if (sel == 0x79cc6790) {
            // burnFrom(address from, uint256 amount)
            if (data.length < 68) revert UnknownSelector(token, sel);
            address from = address(uint160(uint256(_loadWord(data, 4))));
            uint256 amount = uint256(_loadWord(data, 36));
            if (from == account && enforceLimits) {
                uint256 perCallCap = tokenLimits[account][token].perCall;
                if (perCallCap == 0 || amount > perCallCap) revert LimitExceeded(token, amount, perCallCap);
            }
        } else {
            revert UnknownSelector(token, sel);
        }
    }

    function _recordSpend(
        address account,
        address token,
        uint256 amount,
        bool enforceLimits
    ) internal {
        if (amount == 0) return;
        uint32 winSecs = config[account].windowSeconds;
        WindowRecord storage w = _windows[account][token];
        uint256 currentSpent = 0;
        if (winSecs > 0 && block.timestamp < w.windowStart + winSecs) {
            currentSpent = w.spent;
        } else {
            w.windowStart = uint64(block.timestamp);
        }

        if (enforceLimits) {
            uint256 cap = tokenLimits[account][token].perWindow;
            uint256 remaining = cap > currentSpent ? cap - currentSpent : 0;
            if (cap == 0 || currentSpent + amount > cap) {
                revert LimitExceeded(token, amount, remaining);
            }
        }

        w.spent = uint192(currentSpent + amount);
    }

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
