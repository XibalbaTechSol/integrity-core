// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { IAccountVerifier } from "../../../src/wallet/IAccountVerifier.sol";

contract MockAccountVerifier is IAccountVerifier {
    mapping(address => bool) public isGenuine;
    mapping(address => address) public owners;

    function setAccount(address account, bool genuine, address owner) external {
        isGenuine[account] = genuine;
        owners[account] = owner;
    }

    function verify(address account) external view override returns (bool genuine, address owner) {
        return (isGenuine[account], owners[account]);
    }
}
