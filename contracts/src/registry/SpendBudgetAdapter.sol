// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {IAdapter} from "./IAdapter.sol";

/// @title SpendBudgetAdapter
/// @notice Reference `IAdapter` implementation: enforces a per-operation and cumulative spend
/// budget, per `subject`. The registry-facing generalization of `IntegrityKernel`'s own
/// per-op/cumulative native-value check.
/// @dev **Real, disclosed difference from `IntegrityKernel`:** `IntegrityKernel`'s `preCheck`/
/// `postCheck` pair snapshots the bound account's ACTUAL balance before and after the wrapped
/// call and measures the real delta -- it does not trust a caller-supplied number.
/// `IAdapter.check` is a single synchronous call with no pre/post pair, so this adapter has no
/// way to independently verify `amount` against a live balance change; it trusts whatever the
/// caller reports. This is a real, disclosed weakening relative to `IntegrityKernel`'s own
/// guarantee, not an oversight -- appropriate for a tracer-bullet slice proving the registry's
/// admission/metered-call machinery, not a claim that this adapter alone is safe to install
/// without a caller that itself measures the real spend.
/// @dev **Generalized to serve many subjects from one deployed instance** (unlike
/// `IntegrityKernel`, which binds to exactly one account at construction) -- `perOpBudgetWei`/
/// `cumulativeBudgetWei` are shared, immutable, set once for this adapter; `cumulativeSpentWei` is
/// tracked independently per `subject`.
contract SpendBudgetAdapter is IAdapter {
    error PerOperationBudgetExceeded(uint256 spent, uint256 budget);
    error CumulativeBudgetExceeded(uint256 priorCumulative, uint256 spent, uint256 budget);
    error ZeroBudget();

    uint256 public immutable perOpBudgetWei;
    uint256 public immutable cumulativeBudgetWei;

    mapping(address subject => uint256 spent) public cumulativeSpentWei;

    constructor(uint256 perOpBudgetWei_, uint256 cumulativeBudgetWei_) {
        if (perOpBudgetWei_ == 0 || cumulativeBudgetWei_ == 0) revert ZeroBudget();
        perOpBudgetWei = perOpBudgetWei_;
        cumulativeBudgetWei = cumulativeBudgetWei_;
    }

    /// @param subject The account whose spend budget is being checked.
    /// @param amount The spend amount to check and, on success, record -- trusted from the
    /// caller, not independently measured (see this contract's own top-level NatSpec).
    function check(address subject, uint256 amount) external {
        if (amount > perOpBudgetWei) revert PerOperationBudgetExceeded(amount, perOpBudgetWei);

        uint256 priorCumulative = cumulativeSpentWei[subject];
        uint256 newCumulative = priorCumulative + amount;
        if (newCumulative > cumulativeBudgetWei) {
            revert CumulativeBudgetExceeded(priorCumulative, amount, cumulativeBudgetWei);
        }
        cumulativeSpentWei[subject] = newCumulative;
    }
}
