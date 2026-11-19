// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

interface IAccountVerifier {
    /// genuine: deployed by the chosen stack's factory; owner: its single EOA owner (D-M).
    function verify(address account) external view returns (bool genuine, address owner);
}
