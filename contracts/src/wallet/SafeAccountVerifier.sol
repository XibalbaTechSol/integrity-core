// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { IAccountVerifier } from "./IAccountVerifier.sol";

interface ISafeMinimal {
    function masterCopy() external view returns (address);
    function getThreshold() external view returns (uint256);
    function getOwners() external view returns (address[] memory);
    function isModuleEnabled(address module) external view returns (bool);
    function getModulesPaginated(address start, uint256 pageSize)
        external
        view
        returns (address[] memory array, address next);
    function getStorageAt(uint256 offset, uint256 length) external view returns (bytes memory);
}

/// @title SafeAccountVerifier
/// @notice Account verifier for Safe v1.4.1 accounts operating under the Safe7579 adapter.
/// Enforces:
/// 1. Safe mastercopy matches canonical safeSingleton
/// 2. Threshold == 1
/// 3. Exactly 1 owner, which must be an EOA
/// 4. Safe7579 is the fallback handler
/// 5. Safe7579 is the SOLE enabled module on Safe (preventing rogue module execution bypasses)
/// 6. IntegrityGuard is configured as the Safe transaction guard (if set)
contract SafeAccountVerifier is IAccountVerifier {
    address internal constant SENTINEL_MODULES = address(0x1);
    bytes32 internal constant GUARD_STORAGE_SLOT = 0x4a204f620c8c5ccdca3fd54d003badd85ba500436a431f0cbda4f558c93c34c8;
    bytes32 internal constant FALLBACK_HANDLER_STORAGE_SLOT = 0x6c9a6c4a39284e37ed1cf53d337577d14212a4870fb976a4366c693b939918d5;

    address public immutable safeSingleton;
    address public immutable safe7579;
    address public immutable integrityGuard;

    constructor(address safeSingleton_, address safe7579_, address integrityGuard_) {
        safeSingleton = safeSingleton_;
        safe7579 = safe7579_;
        integrityGuard = integrityGuard_;
    }

    /// @inheritdoc IAccountVerifier
    function verify(address account) external view override returns (bool genuine, address owner) {
        if (account == address(0) || account.code.length == 0) {
            return (false, address(0));
        }

        // 1. Mastercopy check
        try ISafeMinimal(account).masterCopy() returns (address mc) {
            if (mc != safeSingleton) return (false, address(0));
        } catch {
            return (false, address(0));
        }

        // 2. Threshold check
        try ISafeMinimal(account).getThreshold() returns (uint256 threshold) {
            if (threshold != 1) return (false, address(0));
        } catch {
            return (false, address(0));
        }

        // 3. Single EOA owner check
        try ISafeMinimal(account).getOwners() returns (address[] memory owners) {
            if (owners.length != 1) return (false, address(0));
            owner = owners[0];
            if (owner == address(0) || owner.code.length != 0) return (false, address(0));
        } catch {
            return (false, address(0));
        }

        // 4. Fallback handler check (must be Safe7579)
        if (safe7579 != address(0)) {
            try ISafeMinimal(account).getStorageAt(uint256(FALLBACK_HANDLER_STORAGE_SLOT), 1) returns (bytes memory data) {
                if (data.length < 32) return (false, address(0));
                address handler = address(uint160(uint256(bytes32(data))));
                if (handler != safe7579) return (false, address(0));
            } catch {
                return (false, address(0));
            }
        }

        // 5. Sole enabled module check (Safe7579 must be the ONLY enabled module)
        if (safe7579 != address(0)) {
            try ISafeMinimal(account).getModulesPaginated(SENTINEL_MODULES, 10) returns (
                address[] memory modules,
                address next
            ) {
                if (modules.length != 1 || modules[0] != safe7579 || next != SENTINEL_MODULES) {
                    return (false, address(0));
                }
            } catch {
                return (false, address(0));
            }
        }

        // 6. Guard check (if integrityGuard is configured)
        if (integrityGuard != address(0)) {
            try ISafeMinimal(account).getStorageAt(uint256(GUARD_STORAGE_SLOT), 1) returns (bytes memory data) {
                if (data.length < 32) return (false, address(0));
                address currentGuard = address(uint160(uint256(bytes32(data))));
                if (currentGuard != integrityGuard) return (false, address(0));
            } catch {
                return (false, address(0));
            }
        }

        return (true, owner);
    }
}
