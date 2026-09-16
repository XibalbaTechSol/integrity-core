import { ethers } from 'ethers';

const EXECUTE_INTERFACE = new ethers.Interface([
  'function execute(address target,uint256 value,bytes data)',
]);

export interface ReadOnlyCallProvider {
  call(transaction: ethers.TransactionRequest): Promise<string>;
}

/**
 * Run the exact SovereignAgent execution envelope as a read-only eth_call.
 *
 * This is deliberately separate from executeAsAgent(): it never requests a
 * signature and never broadcasts a transaction. The node still evaluates the
 * target call (including controller/policy/revert behavior) against its current
 * state, which is the required preflight boundary before any future write UI is
 * allowed to request an external signature.
 */
export async function simulateAgentExecution(
  provider: ReadOnlyCallProvider,
  signerAddress: string,
  sovereignAgent: string,
  target: string,
  data: string,
  value: bigint = 0n,
): Promise<string> {
  if (!ethers.isAddress(signerAddress)) throw new Error('Invalid simulation signer');
  if (!ethers.isAddress(sovereignAgent)) throw new Error('Invalid simulation agent');
  if (!ethers.isAddress(target)) throw new Error('Invalid simulation target');
  if (!ethers.isHexString(data)) throw new Error('Invalid simulation calldata');

  const executeData = EXECUTE_INTERFACE.encodeFunctionData('execute', [target, value, data]);
  return provider.call({
    from: signerAddress,
    to: sovereignAgent,
    data: executeData,
    value,
  });
}
