// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Minimal stand-in for the real `contracts/` SmartBAAFactory.
/// This is a TEST FIXTURE, not a production contract: it exists purely so
/// bcc_middleware's `app/baa.py` on-chain eth_call code path can be proven
/// against a real deployed contract on a real (local anvil) chain, cheaply
/// and without spinning up the full Integrity Health stack (CoveredEntityRegistry +
/// SmartBAAFactory + SmartBAA + IntegrityToken collateral -- see
/// tests/test_baa_health_integration.py for a test against those real
/// contracts specifically).
///
/// The function signature below, `isBAAActive(address coveredEntity,
/// address businessAssociate) returns (bool)`, mirrors the REAL
/// `contracts/src/health/SmartBAAFactory.sol::isBAAActive` exactly (fixed
/// from an earlier one-argument version of this mock that matched a
/// one-argument ABI in app/baa.py -- both were wrong the same way, since
/// this fixture was written before the real contract existed to check
/// against; see app/baa.py's module docstring for the full story).
contract MockBAARegistry {
    /// @dev coveredEntity => businessAssociate => active, same keying as
    /// the real SmartBAAFactory.baaOf mapping.
    mapping(address => mapping(address => bool)) public active;

    function setActive(address coveredEntity, address businessAssociate, bool isActive) external {
        active[coveredEntity][businessAssociate] = isActive;
    }

    function isBAAActive(address coveredEntity, address businessAssociate) external view returns (bool) {
        return active[coveredEntity][businessAssociate];
    }
}
