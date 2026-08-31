// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title Minimal ERC-6551 interfaces, hand-written against the EIP-6551 spec text
/// @notice `docs/plans/2026-08-24-phase2-licence-account-tracer-bullet-proposal.md`'s own
/// dependency-inventory step: this repo has no vendored ERC-6551 package (`grep` across
/// `node_modules` for `IERC6551`/`erc6551` returned nothing before this file was written), so
/// these are hand-written, not copied. The `account(...)` view function's signature is
/// cross-validated against the REAL, live registry deployed at
/// `0x000000006551c19487814612e58FE06813775758` on Base Sepolia (the same canonical address on
/// every EVM chain by EIP-6551 design) -- see
/// `test/licence/Erc6551InterfaceCrossValidation.t.fork.sol` for the forked-RPC check that
/// confirms this interface's ABI actually matches what's really deployed, not merely what the
/// EIP text says it should be.
interface IERC6551Registry {
    event ERC6551AccountCreated(
        address account,
        address indexed implementation,
        bytes32 salt,
        uint256 chainId,
        address indexed tokenContract,
        uint256 indexed tokenId
    );

    error AccountCreationFailed();

    function createAccount(address implementation, bytes32 salt, uint256 chainId, address tokenContract, uint256 tokenId)
        external
        returns (address account);

    function account(address implementation, bytes32 salt, uint256 chainId, address tokenContract, uint256 tokenId)
        external
        view
        returns (address account);
}

/// @dev The core account interface every ERC-6551 token-bound account must implement.
/// `operation` in `execute` follows the same convention as `Safe`/multisig `execTransaction`
/// calls this EIP borrows from: 0 = CALL, 1 = DELEGATECALL, 2 = CREATE, 3 = CREATE2. This slice's
/// own account (`LicenceAccount.sol`) only ever needs CALL and will reject anything else -- see
/// that contract's own NatSpec.
interface IERC6551Account {
    receive() external payable;

    function execute(address to, uint256 value, bytes calldata data, uint8 operation)
        external
        payable
        returns (bytes memory);

    function isValidSigner(address signer, bytes calldata context) external view returns (bytes4 magicValue);

    function token() external view returns (uint256 chainId, address tokenContract, uint256 tokenId);

    function state() external view returns (uint256);
}
