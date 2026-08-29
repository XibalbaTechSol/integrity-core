// Read-only ABI slices for IntegrityAccount + IntegrityKernel (contracts/src/kernel/) --
// Phase I's guardian-governed account and its bound kernel (the three reference adapters --
// budget, reputation-floor, assurance-tier -- live INSIDE the kernel, not as separate
// contracts). Signatures cross-checked directly against source, not the whitepaper/docs.
export const INTEGRITY_ACCOUNT_ABI = [
  'function hook() view returns (address)',
  'function guardians() view returns (address[])',
  'function guardianThreshold() view returns (uint256)',
  'function moduleActionTimelockSeconds() view returns (uint256)',
  'function rescueTimelockSeconds() view returns (uint256)',
  'function pendingKernelSwap() view returns (address newKernel, uint256 readyAt)',
  'function kernelSwapNonce() view returns (uint256)',
  'function kernelSwapApprovalCount(uint256) view returns (uint256)',
  'function swapInProgress() view returns (bool)',
  'function pendingGuardianAction() view returns (bool active, bool isCancel, address newKernel, uint256 targetKernelSwapNonce)',
  'function guardianActionNonce() view returns (uint256)',
  'function guardianActionApprovalCount(uint256) view returns (uint256)',
  'function pendingGuardianRotation() view returns (bool active, bool isAddition, address guardian)',
  'function guardianRotationNonce() view returns (uint256)',
  'function guardianRotationApprovalCount(uint256) view returns (uint256)',
  'function pendingRescueSweep() view returns (bool active, address to, uint256 amount, bool sweepFullBalance, uint256 readyAt)',
  'function rescueSweepNonce() view returns (uint256)',
  'function rescueSweepApprovalCount(uint256) view returns (uint256)',
] as const;

export const INTEGRITY_KERNEL_ABI = [
  'function boundAccount() view returns (address)',
  'function armed() view returns (bool)',
  'function perOpBudgetWei() view returns (uint256)',
  'function cumulativeBudgetWei() view returns (uint256)',
  'function cumulativeSpentWei() view returns (uint256)',
  'function trackedToken() view returns (address)',
  'function tokenPerOpBudgetWei() view returns (uint256)',
  'function tokenCumulativeBudgetWei() view returns (uint256)',
  'function tokenCumulativeSpentWei() view returns (uint256)',
  'function reputationRegistry() view returns (address)',
  'function minEffectiveScore() view returns (uint256)',
  'function snapshotScore() view returns (uint256)',
  'function snapshotIsZkBoosted() view returns (bool)',
  'function snapshotTakenAt() view returns (uint256)',
  'function epochLengthSeconds() view returns (uint256)',
] as const;
