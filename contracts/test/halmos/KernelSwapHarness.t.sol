// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {HalmosKernelFixture, AlwaysPassingPlaceholderKernel} from "./HalmosKernelFixture.sol";
import {IntegrityKernel} from "../../src/kernel/IntegrityKernel.sol";

/// @title Halmos-only harness: proving the genesis-placeholder-then-governance-swap pattern
/// @notice `docs/plans/2026-08-24-phase1-halmos-harness-proposal.md` (Option B, authorized
/// 2026-08-24 after Options A and A' were both found infeasible -- A because Halmos does not
/// model plain CREATE addresses via real RLP/nonce semantics at all (confirmed by reading
/// `halmos/sevm.py`'s `create()`, which assigns addresses from an internal synthetic counter,
/// `new_address()`, unrelated to any real-world-computable formula); A' because predicting BOTH
/// `IntegrityKernel`'s and `IntegrityAccount`'s CREATE2 addresses in advance is a genuine
/// two-variable fixed point over `keccak256` (each contract's real constructor args must embed
/// the OTHER's real final address) -- unsolvable in general, independent of Halmos, on real
/// Ethereum too.
/// @dev THIS FILE proves the swap MECHANISM itself works under Halmos, driving `proposeKernelSwap`/
/// `approveKernelSwap`/`executeKernelSwap` explicitly (not through `HalmosKernelFixture`'s
/// `_swapToKernel` helper, which exists for OTHER harnesses that just need a real kernel
/// installed without re-testing how it got there -- this file's whole point is testing exactly
/// that mechanism, so hiding it behind a helper here would test less, not the same thing). NOT
/// reusing `IntegrityAccountTest`'s own `setUp()` (deliberately -- that fixture is the concrete
/// test suite's own, drifts with it, and depends on `vm.getNonce`/CREATE-address prediction, both
/// confirmed unsupported by Halmos).
contract KernelSwapHarnessTest is HalmosKernelFixture {
    function setUp() public {
        _deployPlaceholderGenesisAccount();
    }

    /// @dev Proves the full real governance path -- propose, two guardian approvals, timelock
    /// elapse, execute -- swaps the placeholder out for a SECOND placeholder (still not the real
    /// kernel; that is `check_realKernelSwapInSucceeds` below), using nothing but the account's
    /// own actual `IntegrityAccount.sol` code, unmodified. If this passes, the swap mechanism
    /// itself is confirmed Halmos-compatible independent of whatever complexity the real
    /// `IntegrityKernel` adds on top.
    function check_placeholderSwapSucceedsViaRealGovernancePath() public {
        AlwaysPassingPlaceholderKernel secondKernel = new AlwaysPassingPlaceholderKernel();

        vm.prank(address(account));
        account.proposeKernelSwap(address(secondKernel));

        (address pendingKernel, uint256 readyAt) = account.pendingKernelSwap();
        assert(pendingKernel == address(secondKernel));

        // Read the nonce into a local BEFORE pranking -- calling account.kernelSwapNonce()
        // inline as an argument would itself be the "next call" vm.prank affects, consuming the
        // prank before it ever reaches approveKernelSwap. A real bug, caught by a concrete
        // sanity run before trusting this under Halmos (NotAGuardian, sender = the harness
        // contract's own default address, not the intended guardian).
        uint256 swapNonce = account.kernelSwapNonce();

        vm.prank(guardian1);
        account.approveKernelSwap(swapNonce, address(secondKernel));
        vm.prank(guardian2);
        account.approveKernelSwap(swapNonce, address(secondKernel));

        vm.warp(readyAt);

        vm.prank(address(account));
        account.executeKernelSwap(address(secondKernel));

        assert(account.hook() == address(secondKernel));
    }

    /// @dev THE target harness step: swap the placeholder out for the REAL, unmodified
    /// `IntegrityKernel` -- now bound to `address(account)`, which is already concrete (the
    /// account was deployed for real in `setUp`, no address was ever predicted). This is the
    /// step `docs/plans/2026-08-24-phase1-formal-verification-proposal.md`'s four target
    /// properties actually build on -- if this passes, the harness itself is complete and
    /// Halmos-compatible; the properties are a separate step, in `KernelProperties.t.sol`.
    function check_realKernelSwapInSucceeds() public {
        IntegrityKernel realKernel = _deployRealKernel(address(0), 0, 0);

        vm.prank(address(account));
        account.proposeKernelSwap(address(realKernel));

        (, uint256 readyAt) = account.pendingKernelSwap();
        uint256 swapNonce = account.kernelSwapNonce();

        vm.prank(guardian1);
        account.approveKernelSwap(swapNonce, address(realKernel));
        vm.prank(guardian2);
        account.approveKernelSwap(swapNonce, address(realKernel));

        vm.warp(readyAt);

        vm.prank(address(account));
        account.executeKernelSwap(address(realKernel));

        assert(account.hook() == address(realKernel));
    }
}
