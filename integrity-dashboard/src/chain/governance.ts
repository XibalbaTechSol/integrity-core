// Minimal ABI for IntegrityGovernance (contracts/src/oracle/IntegrityGovernance.sol) — only
// castVote, the one write this dashboard wires up. propose/queue/execute are deliberately
// NOT included here: propose takes an arbitrary (target, value, callData) action and executes
// it verbatim after the timelock, which is real financial/governance risk to expose through a
// generic UI without dedicated design review — see PRODUCTION_GAPS.md §4 for the explicit
// scoping decision. Proposing/queuing/executing remain a CLI/SDK-only path for now.
export const GOVERNANCE_ABI = [
  'function castVote(uint256 id, bool support, uint256 amount)',
] as const;
