// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title IExecutionPolicy
/// @notice Swappable check invoked by `SovereignAgent.execute` before any external call.
/// @dev SPEC.md §5.3. address(0) on the host is the testnet skip path. Once set, a false
///      return or revert MUST fail closed (no value movement, nonce is not consumed).
interface IExecutionPolicy {
    /// @param agent The SovereignAgent whose `execute` is in flight.
    /// @param target Callee of the proposed call.
    /// @param value Native value attached to the proposed call.
    /// @param data Calldata of the proposed call.
    /// @return allowed True iff the host may proceed with `target.call`.
    function check(address agent, address target, uint256 value, bytes calldata data)
        external
        view
        returns (bool);
}
