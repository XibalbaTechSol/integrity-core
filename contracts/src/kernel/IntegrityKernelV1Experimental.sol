// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {IERC7579Hook, MODULE_TYPE_HOOK} from "@openzeppelin/contracts/interfaces/draft-IERC7579.sol";

/// @title IntegrityKernelV1Experimental
/// @notice Phase I tracer-bullet slice (docs/plans/2026-08-17-phase1-tracer-bullet-proposal.md).
/// @dev NOT the full Phase I `IntegrityKernel` the plan describes. This kernel enforces exactly
/// ONE conserved quantity -- a native-value spend budget, per-operation and cumulative -- and
/// nothing else. It is bound to exactly one account at construction (immutable, no rebind) and
/// is intended to be installed exactly once, atomically, by that account's own constructor.
///
/// Guarantee this kernel actually provides, stated precisely (do not extend this claim beyond
/// what's written here): while installed and while the bound account's `execute()` is invoked
/// with `(CALLTYPE_SINGLE, EXECTYPE_DEFAULT)` (the only mode the paired account contract
/// permits), a single execution can never move more than `perOpBudgetWei` of the account's own
/// native-token balance out, and the running total across all such executions can never exceed
/// `cumulativeBudgetWei`. This kernel does NOT verify calldata content, does NOT constrain ERC-20
/// or other token transfers, does NOT enforce anything about batch/delegatecall/executor/fallback
/// paths (the paired account is responsible for making those paths unreachable, not this kernel),
/// and does NOT implement module governance -- `onUninstall` is intentionally left reachable only
/// via the bound account's own (also intentionally disabled, in this slice) module-mutation path.
contract IntegrityKernelV1Experimental is IERC7579Hook {
    error Unauthorized(address caller);
    error AlreadyArmed();
    error NotArmed();
    error PerOperationBudgetExceeded(uint256 spent, uint256 budget);
    error CumulativeBudgetExceeded(uint256 spentSoFar, uint256 attempted, uint256 budget);
    error ZeroAccount();
    error ZeroBudget();

    address public immutable boundAccount;
    uint256 public immutable perOpBudgetWei;
    uint256 public immutable cumulativeBudgetWei;

    uint256 public cumulativeSpentWei;

    /// @dev Reentrancy/replay guard (see docs/design/phase1-slice-dependency-inventory-2026-08-17.md
    /// for why this is necessary, not decorative): without it, a call that reenters `execute()`
    /// before the outer call's `postCheck` has run could get its own preCheck/postCheck pair
    /// evaluated against `cumulativeSpentWei` before the outer call's spend is accounted for,
    /// letting two nested calls each independently pass a budget check that their combined spend
    /// would fail.
    bool public armed;

    modifier onlyBoundAccount() {
        if (msg.sender != boundAccount) revert Unauthorized(msg.sender);
        _;
    }

    constructor(address boundAccount_, uint256 perOpBudgetWei_, uint256 cumulativeBudgetWei_) {
        if (boundAccount_ == address(0)) revert ZeroAccount();
        if (perOpBudgetWei_ == 0 || cumulativeBudgetWei_ == 0) revert ZeroBudget();
        boundAccount = boundAccount_;
        perOpBudgetWei = perOpBudgetWei_;
        cumulativeBudgetWei = cumulativeBudgetWei_;
    }

    // ----------------------------------------------------------------- IERC7579Module ---

    function onInstall(bytes calldata) external view onlyBoundAccount {}

    /// @dev Left callable (per IERC7579Module's interface requirement) but this slice's paired
    /// account never exposes a reachable uninstall path -- see IntegrityAccountV1Experimental's
    /// own module comment. Not a guarantee this kernel itself provides.
    function onUninstall(bytes calldata) external view onlyBoundAccount {}

    function isModuleType(uint256 moduleTypeId) external pure returns (bool) {
        return moduleTypeId == MODULE_TYPE_HOOK;
    }

    // ------------------------------------------------------------------- IERC7579Hook ---

    /// @dev Snapshots the bound account's native balance. Returns it ABI-encoded as `hookData`,
    /// threaded directly to `postCheck` by the account's own `withHook` modifier -- no kernel
    /// storage needed for the snapshot itself, only for the `armed` guard.
    function preCheck(address, uint256, bytes calldata) external onlyBoundAccount returns (bytes memory hookData) {
        if (armed) revert AlreadyArmed();
        armed = true;
        return abi.encode(boundAccount.balance);
    }

    function postCheck(bytes calldata hookData) external onlyBoundAccount {
        if (!armed) revert NotArmed();
        armed = false;

        uint256 balanceBefore = abi.decode(hookData, (uint256));
        uint256 balanceAfter = boundAccount.balance;
        uint256 spent = balanceBefore > balanceAfter ? balanceBefore - balanceAfter : 0;

        if (spent > perOpBudgetWei) revert PerOperationBudgetExceeded(spent, perOpBudgetWei);

        uint256 newCumulative = cumulativeSpentWei + spent;
        if (newCumulative > cumulativeBudgetWei) {
            revert CumulativeBudgetExceeded(cumulativeSpentWei, spent, cumulativeBudgetWei);
        }
        cumulativeSpentWei = newCumulative;
    }
}
