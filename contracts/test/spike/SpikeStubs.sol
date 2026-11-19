// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

// THROWAWAY (Plan 1 Task 1 wallet-stack spike). Deleted in Plan 1b.

import { ISafeSpike, ISafeGuardSpike } from "./SpikeInterfaces.sol";

/// ERC-7579 hook stub: records every preCheck (who the account says sent it, and the calldata the
/// account handed over). It never reverts, so it observes; it does not enforce.
contract StubHook {
    struct Seen {
        address account; // msg.sender of preCheck == the smart account
        address msgSender; // what the account reports as the original caller
        uint256 msgValue;
        bytes msgData;
    }

    Seen[] internal _seen;
    mapping(address => bool) public initialized;

    function onInstall(bytes calldata) external {
        initialized[msg.sender] = true;
    }

    function onUninstall(bytes calldata) external {
        initialized[msg.sender] = false;
    }

    function isModuleType(uint256 typeId) external pure returns (bool) {
        return typeId == 4;
    }

    function isInitialized(address a) external view returns (bool) {
        return initialized[a];
    }

    function preCheck(address msgSender, uint256 msgValue, bytes calldata msgData)
        external
        returns (bytes memory hookData)
    {
        _seen.push(Seen(msg.sender, msgSender, msgValue, msgData));
        return "";
    }

    function postCheck(bytes calldata) external { }

    function count() external view returns (uint256) {
        return _seen.length;
    }

    function seen(uint256 i) external view returns (Seen memory) {
        return _seen[i];
    }
}

/// Safe Guard stub (Safe 1.4.1 `Guard`): records every checkTransaction.
contract StubGuard is ISafeGuardSpike {
    uint256 public count;
    address public lastMsgSender;
    address public lastTo;

    function checkTransaction(
        address to,
        uint256,
        bytes memory,
        uint8,
        uint256,
        uint256,
        uint256,
        address,
        address payable,
        bytes memory,
        address msgSender
    ) external {
        count++;
        lastMsgSender = msgSender;
        lastTo = to;
    }

    function checkAfterExecution(bytes32, bool) external { }

    function supportsInterface(bytes4 id) external pure returns (bool) {
        return id == type(ISafeGuardSpike).interfaceId || id == 0x01ffc9a7;
    }
}

/// Delegatecalled from Safe.setup(): enables Safe7579 as a Safe module, then calls
/// Safe7579.initializeAccount on the Safe itself (which reaches the adapter via the fallback
/// handler that setup() already set, with _msgSender() == the Safe, so onlyEntryPointOrSelf passes).
/// Stand-in for Rhinestone's Safe7579Launchpad, which does the same in the first UserOp.
contract SpikeSafe7579Setup {
    function enable7579(address safe7579, bytes calldata initializeAccountCall) external {
        ISafeSpike(address(this)).enableModule(safe7579);
        (bool ok, bytes memory ret) = address(this).call(initializeAccountCall);
        if (!ok) {
            assembly {
                revert(add(ret, 0x20), mload(ret))
            }
        }
    }
}

/// A plain value-moving target for session-key actions.
contract SpikeTarget {
    uint256 public pings;
    address public lastCaller;

    function ping(uint256 n) external payable {
        pings += n;
        lastCaller = msg.sender;
    }
}
