// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {ITK} from "../../src/trust/ITK.sol";

contract ITKTest is Test {
    ITK itk;
    address admin = makeAddr("admin");
    address minter = makeAddr("minter");
    address alice = makeAddr("alice");

    function setUp() public {
        itk = new ITK(admin, 1_000_000 ether);
    }

    function test_metadata() public view {
        assertEq(itk.name(), "Integrity Token");
        assertEq(itk.symbol(), "ITK");
    }

    function test_initialMint() public view {
        assertEq(itk.balanceOf(admin), 1_000_000 ether);
        assertEq(itk.totalMinted(), 1_000_000 ether);
    }

    function test_mintCapEnforced() public {
        uint256 maxSupply = itk.MAX_SUPPLY();
        uint256 remaining = maxSupply - itk.totalMinted();

        // Exactly the remaining headroom succeeds.
        vm.prank(admin);
        itk.mint(alice, remaining);
        assertEq(itk.totalMinted(), maxSupply);

        // One wei over the cap reverts with the remaining headroom (zero now).
        vm.prank(admin);
        vm.expectRevert(abi.encodeWithSelector(ITK.ExceedsMaxSupply.selector, uint256(1), uint256(0)));
        itk.mint(alice, 1);
    }

    function test_cannotExceedMaxSupplyInSingleMint() public {
        uint256 maxSupply = itk.MAX_SUPPLY();
        uint256 remaining = maxSupply - itk.totalMinted();
        vm.prank(admin);
        vm.expectRevert(abi.encodeWithSelector(ITK.ExceedsMaxSupply.selector, maxSupply, remaining));
        itk.mint(alice, maxSupply);
    }

    function test_nonMinterCannotMint() public {
        vm.prank(alice);
        vm.expectRevert();
        itk.mint(alice, 100 ether);

        bytes32 minterRole = itk.MINTER_ROLE();
        vm.prank(admin);
        itk.grantRole(minterRole, minter);

        vm.prank(minter);
        itk.mint(alice, 100 ether);
        assertEq(itk.balanceOf(alice), 100 ether);
    }

    /// @notice Burning must not reopen mint headroom: the cap is on lifetime issuance,
    /// not circulating supply.
    function test_burnDoesNotReopenMintHeadroom() public {
        vm.prank(admin);
        itk.transfer(alice, 500_000 ether);

        vm.prank(alice);
        itk.burn(500_000 ether);

        assertEq(itk.totalSupply(), 500_000 ether);
        assertEq(itk.totalMinted(), 1_000_000 ether);

        // Headroom is MAX_SUPPLY - totalMinted, NOT MAX_SUPPLY - totalSupply().
        uint256 remaining = itk.MAX_SUPPLY() - itk.totalMinted();
        vm.prank(admin);
        vm.expectRevert(abi.encodeWithSelector(ITK.ExceedsMaxSupply.selector, remaining + 1, remaining));
        itk.mint(alice, remaining + 1);
    }

    function test_zeroAmountMintReverts() public {
        vm.prank(admin);
        vm.expectRevert(ITK.ZeroAmount.selector);
        itk.mint(alice, 0);
    }

    function test_constructorRejectsOverCapInitialMint() public {
        uint256 maxSupply = 100_000_000 ether;
        vm.expectRevert(abi.encodeWithSelector(ITK.ExceedsMaxSupply.selector, maxSupply + 1, maxSupply));
        new ITK(admin, maxSupply + 1);
    }
}
