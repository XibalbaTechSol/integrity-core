// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

interface IOperationContext {
    enum Role { None, Owner, Session, Maintenance }

    /// Role that authorized the operation currently executing on `account`.
    function roleOf(address account) external view returns (Role);

    /// Shield co-signature carried with the current operation (empty if none).
    function coSignatureOf(address account) external view returns (bytes memory);
}
