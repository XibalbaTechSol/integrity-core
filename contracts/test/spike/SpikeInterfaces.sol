// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

// THROWAWAY (Plan 1 Task 1 wallet-stack spike). Minimal local interfaces for contracts that are
// already deployed on Base Sepolia. Nothing here is vendored source: every signature below was
// read from the Sourcify-verified source of the deployed contract (addresses in
// docs/superpowers/specs/2026-11-18-wallet-stack-spike.md). Deleted in Plan 1b.

/// EntryPoint v0.7 PackedUserOperation (same layout as eth-infinitism v0.7).
struct SpikeUserOp {
    address sender;
    uint256 nonce;
    bytes initCode;
    bytes callData;
    bytes32 accountGasLimits;
    uint256 preVerificationGas;
    bytes32 gasFees;
    bytes paymasterAndData;
    bytes signature;
}

interface IEntryPointV07 {
    function handleOps(SpikeUserOp[] calldata ops, address payable beneficiary) external;
    function getUserOpHash(SpikeUserOp calldata userOp) external view returns (bytes32);
    function getNonce(address sender, uint192 key) external view returns (uint256);
    error FailedOp(uint256 opIndex, string reason);
    error FailedOpWithRevert(uint256 opIndex, string reason, bytes inner);
}

/// Safe v1.4.1 / v1.5.0 (subset).
interface ISafeSpike {
    function setup(
        address[] calldata owners,
        uint256 threshold,
        address to,
        bytes calldata data,
        address fallbackHandler,
        address paymentToken,
        uint256 payment,
        address payable paymentReceiver
    ) external;
    function execTransaction(
        address to,
        uint256 value,
        bytes calldata data,
        uint8 operation,
        uint256 safeTxGas,
        uint256 baseGas,
        uint256 gasPrice,
        address gasToken,
        address payable refundReceiver,
        bytes calldata signatures
    ) external payable returns (bool);
    function getTransactionHash(
        address to,
        uint256 value,
        bytes calldata data,
        uint8 operation,
        uint256 safeTxGas,
        uint256 baseGas,
        uint256 gasPrice,
        address gasToken,
        address refundReceiver,
        uint256 nonce
    ) external view returns (bytes32);
    function nonce() external view returns (uint256);
    function enableModule(address module) external;
    function setGuard(address guard) external;
    function setFallbackHandler(address handler) external;
    function addOwnerWithThreshold(address owner, uint256 threshold) external;
    function getOwners() external view returns (address[] memory);
    function getThreshold() external view returns (uint256);
    function isModuleEnabled(address module) external view returns (bool);
    function getModulesPaginated(address start, uint256 pageSize)
        external
        view
        returns (address[] memory array, address next);
    function getStorageAt(uint256 offset, uint256 length) external view returns (bytes memory);
    function execTransactionFromModule(address to, uint256 value, bytes calldata data, uint8 operation)
        external
        returns (bool success);
    function VERSION() external view returns (string memory);
    function domainSeparator() external view returns (bytes32);
}

interface ISafeProxyFactorySpike {
    function createProxyWithNonce(address singleton, bytes memory initializer, uint256 saltNonce)
        external
        returns (address proxy);
    function proxyCreationCode() external pure returns (bytes memory);
}

/// Safe 1.4.1 Guard. `type(ISafeGuardSpike).interfaceId` == Safe's `type(Guard).interfaceId`
/// (inherited IERC165 members are excluded from interfaceId).
interface ISafeGuardSpike {
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

struct ModuleInit {
    address module;
    bytes initData;
}

struct RegistryInit {
    address registry;
    address[] attesters;
    uint8 threshold;
}

/// Rhinestone Safe7579 adapter v1.0.0 (0x7579EE83…0002).
interface ISafe7579Spike {
    function initializeAccount(
        ModuleInit[] calldata validators,
        ModuleInit[] calldata executors,
        ModuleInit[] calldata fallbacks,
        ModuleInit[] calldata hooks,
        RegistryInit calldata registryInit
    ) external;
    function execute(bytes32 mode, bytes calldata executionCalldata) external;
    function installModule(uint256 moduleType, address module, bytes calldata initData) external;
    function uninstallModule(uint256 moduleType, address module, bytes calldata deInitData) external;
    function isModuleInstalled(uint256 moduleType, address module, bytes calldata additionalContext)
        external
        view
        returns (bool);
    function getActiveHook() external view returns (address);
    function getActiveHook(bytes4 selector) external view returns (address);
    function getValidatorsPaginated(address cursor, uint256 size)
        external
        view
        returns (address[] memory array, address next);
    function getExecutorsPaginated(address cursor, uint256 size)
        external
        view
        returns (address[] memory array, address next);
    function getNonce(address safe, address validator) external view returns (uint256);
    function accountId() external view returns (string memory);
    function isValidSignature(bytes32 hash, bytes calldata data) external view returns (bytes4);
}

// ── Smart Sessions (0x00000000008bDABA…4bDA, module-sdk 0.4.0 SMART_SESSIONS_ADDRESS) ──────────
struct PolicyData {
    address policy;
    bytes initData;
}

struct ActionData {
    bytes4 actionTargetSelector;
    address actionTarget;
    PolicyData[] actionPolicies;
}

struct ERC7739Context {
    bytes32 appDomainSeparator;
    string[] contentNames;
}

struct ERC7739Data {
    ERC7739Context[] allowedERC7739Content;
    PolicyData[] erc1271Policies;
}

struct Session {
    address sessionValidator;
    bytes sessionValidatorInitData;
    bytes32 salt;
    PolicyData[] userOpPolicies;
    ERC7739Data erc7739Policies;
    ActionData[] actions;
    bool permitERC4337Paymaster;
}

interface ISmartSessionSpike {
    function enableSessions(Session[] calldata sessions) external returns (bytes32[] memory permissionIds);
    function removeSession(bytes32 permissionId) external;
    function getPermissionId(Session calldata session) external pure returns (bytes32);
    function isPermissionEnabled(bytes32 permissionId, address account) external view returns (bool);
    function validateUserOp(SpikeUserOp calldata userOp, bytes32 userOpHash) external returns (uint256);
    error InvalidSelfCall();
    error NoPoliciesSet(bytes32 permissionId);
}

interface IOwnableValidatorSpike {
    function getOwners(address account) external view returns (address[] memory);
    function threshold(address account) external view returns (uint256);
}

// ── agent0 / ERC-8004 identity registry (0x8004A818…BD9e, impl 0x7274e874…9c02) ─────────────
struct MetadataEntry {
    string metadataKey;
    bytes metadataValue;
}

interface IAgent0RegistrySpike {
    function register(string memory agentURI, MetadataEntry[] memory metadata) external returns (uint256);
    function getAgentWallet(uint256 agentId) external view returns (address);
    function ownerOf(uint256 tokenId) external view returns (address);
    function getMetadata(uint256 agentId, string memory metadataKey) external view returns (bytes memory);
    event Registered(uint256 indexed agentId, string agentURI, address indexed owner);
}
