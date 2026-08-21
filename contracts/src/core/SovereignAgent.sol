// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {IAccount} from "./IAccount.sol";
import {IExecutionPolicy} from "./IExecutionPolicy.sol";

/// @title SovereignAgent
/// @notice The per-agent on-chain account for a single AI agent.
/// @dev Mainnet custody requirements are normative in SPEC.md §5.4:
/// ORACLE_ROLE / ORACLE_SIGNER_ROLE and RESOLVER_SIGNER_ROLE are process-held
/// keys; DEFAULT_ADMIN_ROLE is a multisig or stricter governance authority.
contract SovereignAgent is AccessControl, IAccount {
    bytes32 public constant ORACLE_ROLE = keccak256("ORACLE_ROLE");
    bytes32 public constant ORACLE_SIGNER_ROLE = keccak256("ORACLE_SIGNER_ROLE");
    bytes32 public constant RESOLVER_SIGNER_ROLE = keccak256("RESOLVER_SIGNER_ROLE");

    string private _agentDID;
    uint256 public ais;
    uint256 public executionNonce;
    address public immutable factory;

    /// @notice Controller-selected policy hook for execution. Mainnet value paths
    /// MUST have a non-zero policy; zero preserves the disclosed testnet posture.
    IExecutionPolicy public executionPolicy;

    event AISUpdated(uint256 oldScore, uint256 newScore);
    event ControllerRotated(address indexed oldController, address indexed newController);
    event AgentExecuted(address indexed target, uint256 value, bytes data, uint256 nonce);
    event ExecutionPolicyUpdated(address indexed oldPolicy, address indexed newPolicy);

    error NotController();
    error ExecutionPolicyDenied();

    modifier onlyController() {
        if (!hasRole(DEFAULT_ADMIN_ROLE, msg.sender)) revert NotController();
        _;
    }

    constructor(string memory did_, address controller_, address oracle_, address factory_) {
        require(controller_ != address(0), "SovereignAgent: zero controller");
        _agentDID = did_;
        factory = factory_;
        _grantRole(DEFAULT_ADMIN_ROLE, controller_);
        if (oracle_ != address(0)) {
            _grantRole(ORACLE_ROLE, oracle_);
            _grantRole(ORACLE_SIGNER_ROLE, oracle_);
        }
        ais = 0;
    }

    function agentDID() external view returns (string memory) {
        return _agentDID;
    }

    /// @dev Checks the installed policy before the external call. A reverting policy
    /// bubbles its revert and therefore fails closed.
    function execute(address target, uint256 value, bytes calldata data)
        external
        onlyController
        returns (bytes memory)
    {
        uint256 nonce = ++executionNonce;
        IExecutionPolicy policy = executionPolicy;
        if (address(policy) != address(0)) {
            if (!policy.checkExecution(address(this), msg.sender, target, value, data, nonce)) {
                revert ExecutionPolicyDenied();
            }
        }

        (bool success, bytes memory result) = target.call{value: value}(data);
        if (!success) {
            assembly {
                revert(add(result, 32), mload(result))
            }
        }
        emit AgentExecuted(target, value, data, nonce);
        return result;
    }

    function updateAIS(uint256 newScore) external onlyRole(ORACLE_ROLE) {
        uint256 old = ais;
        ais = newScore;
        emit AISUpdated(old, newScore);
    }

    function rotateController(address newController) external onlyController {
        require(newController != address(0), "SovereignAgent: zero controller");
        _revokeRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(DEFAULT_ADMIN_ROLE, newController);
        emit ControllerRotated(msg.sender, newController);
    }

    function setExecutionPolicy(IExecutionPolicy policy) external onlyController {
        emit ExecutionPolicyUpdated(address(executionPolicy), address(policy));
        executionPolicy = policy;
    }

    receive() external payable {}
}
