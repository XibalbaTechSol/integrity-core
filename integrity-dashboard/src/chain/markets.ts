import { ethers } from 'ethers';
import { SOVEREIGN_AGENT_ABI } from './bytecode';

// Minimal ABIs for the real application-layer market contracts. Signatures copied from
// contracts/src/markets/{MarketFactory,IntegrityMarket}.sol and framework/AgentProfile.sol.
// Kept minimal (only what the dashboard calls/reads/parses) in the same spirit as
// StakingPanel's inline SLASHER_ABI.

export const MARKET_FACTORY_ABI = [
  'function deployMarket(string question, uint8 outcomeCount, uint256 minAisToEnter, uint256 resolveDeadline, address resolver) returns (address market)',
  'event MarketDeployed(address indexed market, address indexed creator, string question, uint8 outcomeCount, address indexed resolver)',
] as const;

export const INTEGRITY_MARKET_ABI = [
  'function enterPosition(uint8 outcomeIndex, uint256 amount, bytes32 bccCommitmentHash)',
  'function resolve(uint8 winningOutcome)',
  'function claimPayout()',
  'function positions(address) view returns (uint256 amount, uint8 outcomeIndex, bytes32 bccCommitmentHash, bool claimed)',
] as const;

export const ERC20_ABI = [
  'function approve(address spender, uint256 amount) returns (bool)',
  'function allowance(address owner, address spender) view returns (uint256)',
  'function balanceOf(address) view returns (uint256)',
  'function transfer(address to, uint256 amount) returns (bool)',
] as const;

export const AGENT_PROFILE_ABI = [
  'function setProfile(bytes32 primaryDomain, string profileURI)',
  'function primaryDomain() view returns (bytes32)',
  'function profileURI() view returns (string)',
] as const;

/**
 * Route a call through the agent's own SovereignAgent.execute — the protocol's calling
 * convention for every registered-agent-gated contract (MarketFactory.deployMarket,
 * IntegrityMarket.enterPosition, AgentProfile.setProfile, ...). `msg.sender` inside the
 * target is then the SovereignAgent, which is what XibalbaAgentRegistry resolves against.
 * The connected signer MUST be the agent's controller (SovereignAgent.execute is
 * onlyController) or the tx reverts with NotController.
 */
export async function executeAsAgent(
  signer: ethers.Signer,
  sovereignAgent: string,
  target: string,
  data: string,
  value: bigint = 0n,
): Promise<ethers.TransactionReceipt> {
  const sa = new ethers.Contract(sovereignAgent, SOVEREIGN_AGENT_ABI, signer);
  const tx = await sa.execute(target, value, data);
  return tx.wait();
}
